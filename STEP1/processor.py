"""
03.processor.py — LLM 가공 + 최신 뉴스 이미지 수집 (3일 기준 분기 처리 버전)

수정 사항:
  1. [대책1] 발행일 누락 시 오늘 날짜 부여 (최신 뉴스 노출 보장)
  2. [대책2] PastNews 저장 시 원본 RawID를 processed_news_id에 백업
  3. [대책3] 마이그레이션 시 artist_tags에서 artist_name 자동 추출
  4. [대책5] 실행 전 Ollama 서버 상태 체크 추가
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
from urllib.parse import quote

# 윈도우 환경 이모지 출력(cp949) 에러 방지
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from openai import OpenAI
from pydantic import ValidationError
import re  # 정규표현식 추가
from database import RawNews, ProcessedNews, PastNews, get_session
from schemas import KpopNewsSummary, summary_to_processed_payload

from prompts.processingprompt import get_summary_prompts

# 파일 로딩 시점에 시스템 프롬프트와 유저 템플릿을 한 번만 불러옵니다.
SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT_TEMPLATE = get_summary_prompts()


# ═══════════════════════════════════════════════════
# Part 0: 불량 데이터 필터링 (Junk Filter)
# ═══════════════════════════════════════════════════


def is_junk_raw_news(raw: RawNews) -> tuple[bool, str]:
    """
    기사 본문이 아닌 네비게이션 메뉴, 포털 메인 페이지,
    혹은 본문 추출에 실패한 쓰레기 데이터를 감지합니다.
    """
    title = (raw.title or "").strip()
    content = (raw.content or "").strip()

    # 1. 본문이 너무 짧은 경우 (ARTIST_HINT 포함 200자 미만)
    if len(content) < 200:
        return True, "본문 내용이 너무 짧음 (추출 실패 가능성)"

    # 2. 제목이 포털이나 방송사 이름 그 자체인 경우
    junk_titles = [
        "KBS",
        "SBS",
        "SBS연예",
        "Daum",
        "MBC",
        "JTBC",
        "네이버",
        "Naver",
        "Daum | 문화",
    ]
    if title in junk_titles:
        return True, f"포털/방송사 메인 페이지 추정 (제목: {title})"

    # 3. 링크 밀도가 너무 높은 경우 (네비게이션/메뉴판)
    links = re.findall(r"\[.*?\]\(.*?\)", content)
    if len(content) > 0:
        link_ratio = (len(links) * 40) / len(content)
        if link_ratio > 0.6:
            return True, "링크 밀도가 높은 메뉴판/네비게이션 데이터"

    # 4. 특정 네비게이션 키워드가 반복되는 경우
    nav_keywords = ["바로가기", "GNB", "LNB", "검색창", "로그인", "About KBS"]
    match_count = sum(1 for kw in nav_keywords if kw in content)
    if match_count >= 3:
        return True, "네비게이션 키워드 다수 발견"

    return False, ""


# ═══════════════════════════════════════════════════
# Part 1: LLM 가공 (raw_news → processed_news)
# ═══════════════════════════════════════════════════


client = OpenAI(
    api_key="ollama",
    base_url="http://localhost:11434/v1",
)
LLM_MODEL = "gemma3:latest"
LLM_DELAY = 0.5


def check_ollama_health():
    """Ollama 서버가 켜져 있는지 확인"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            return True
    except Exception:
        pass
    return False


def repair_json(raw: str) -> str:
    """LLM이 내뱉은 불완전한 JSON을 최소한으로 보정합니다."""
    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"\s*```", "", raw).strip()
    return raw


def extract_names_from_title(title: str) -> list[str]:
    """제목에서 영어 이름 및 한글 이름을 추출하여 힌트로 활용"""
    if not title: return []
    # 1. 영어 이름 (대문자 연속)
    en_names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', title)
    
    # 2. 한글 이름 (따옴표 안의 내용이나 2~4글자 명사 후보)
    # 기사 제목 특성상 이름은 보통 따옴표 안에 있거나 첫머리에 나옵니다.
    ko_names = re.findall(r'[\'"](.+?)[\'"]', title) # 따옴표 안
    # 2~10글자 한글 단어 (방탄소년단 등 긴 이름 대응)
    ko_candidates = re.findall(r'\b[가-힣]{2,10}\b', title)
    
    return list(set(en_names + ko_names + ko_candidates))

def process_single(raw: RawNews) -> dict:
    """기존과 동일: LLM을 호출하여 가공된 데이터를 반환"""
    full_content = (raw.content or "")
    
    # 1. 아티스트 힌트 파싱 ([ARTIST_HINT]태그... 추출)
    artist_hint_from_db = ""
    clean_content_text = full_content
    if full_content.startswith("[ARTIST_HINT]"):
        parts = full_content.split("\n", 1)
        artist_hint_from_db = parts[0].replace("[ARTIST_HINT]", "").strip()
        clean_content_text = parts[1] if len(parts) > 1 else ""

    # 2. 제목에서 이름 추가 추출 (AI 보조용)
    title_names = extract_names_from_title(raw.title or "")
    combined_hint = artist_hint_from_db
    if title_names:
        combined_hint = (combined_hint + ", " + ", ".join(title_names)).strip(", ")

    # 3. 본문 길이 제한 (3000자)
    content_for_llm = clean_content_text[:3000]

    user_message = SUMMARY_USER_PROMPT_TEMPLATE.format(
        title=raw.title or "",
        content=content_for_llm,
        raw_category_hint=f"{raw.category} / {raw.sub_category}",
        raw_artist_hint=combined_hint if combined_hint else "없음",
    )
    # AI 압박용 추가 메시지
    user_message += "\n\n[필독] artist_tags에 'K-Enter'를 쓰는 것을 극도로 지양하라. 모르겠다면 [제목]에 언급된 단어라도 반드시 태그에 넣어라."

    response = client.chat.completions.create(
        model=LLM_MODEL,
        temperature=0.3,
        timeout=120,
        response_format={"type": "json_object"},
        extra_body={"keep_alive": 0},
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    raw_text = response.choices[0].message.content or ""
    try:
        fixed_text = repair_json(raw_text)
        result_dict = json.loads(fixed_text)
    except json.JSONDecodeError as e:
        print(f"\n[!!! JSON 에러 발생 원문 시작 !!!]\n{raw_text}\n[!!! 원문 끝 !!!]")
        raise e
    
    # 4. [보강] AI 결과 정제 및 블랙리스트 처리
    ai_tags = result_dict.get("artist_tags", [])
    if not isinstance(ai_tags, list): ai_tags = []
    
    # 꼼꼼한 블랙리스트 (일반 동사, 형용사, 무의미한 단어들)
    blacklist = [
        "k-enter", "k-pop", "kpop", "artist", "k-entertainment", "idol", "actor",
        "pop", "debut", "music", "official", "video", "lyrics", "comeback", "album",
        "있어", "똑같", "실물", "사진과", "대통령도", "진짜", "뉴스", "오늘", "보고",
        "인근", "누가", "모습", "공개", "포착", "근황", "결혼", "이유", "충격", "결국",
        "다시", "누구", "모두", "현재", "과거", "유튜브", "안티", "사진", "데뷔",
        "매력", "비주얼", "분위기", "시선", "관심", "화제", "근황", "열애", "결별",
        "컴백", "발매", "공연", "콘서트", "행사", "응원", "사랑", "우정", "논란",
        "해명", "입장", "공식", "단독", "최초", "영상", "출처", "커뮤니티", "네티즌",
        "팬들", "사람들", "반응", "폭발", "포즈", "패션", "스타일", "미모", "여신", "남신"
    ]
    
    final_tags = []
    # AI 결과물 정제
    for t in ai_tags:
        t_clean = t.strip()
        # 블랙리스트 단어 중 하나라도 태그에 포함되어 있으면 제외
        is_bad = False
        for b in blacklist:
            if b.lower() in t_clean.lower():
                is_bad = True
                break
        
        if not is_bad and len(t_clean) > 1:
            final_tags.append(t_clean)
    
    # 제목에서 추출한 단어들(title_names)은 AI가 놓쳤을 경우를 대비한 '후보'로만 활용
    # AI 결과가 너무 빈약할 때만 제목 단어 중 블랙리스트에 없는 것만 조심스럽게 추가
    if not final_tags and title_names:
        for tn in title_names:
            is_tn_bad = False
            for b in blacklist:
                if b.lower() in tn.lower():
                    is_tn_bad = True
                    break
            if not is_tn_bad and len(tn) > 1:
                final_tags.append(tn)
    
    # 중복 제거
    final_tags = list(dict.fromkeys(final_tags))
    
    result_dict["artist_tags"] = final_tags if final_tags else ["K-Enter"]

    # [수정] source_name이 리스트로 들어올 경우 문자열로 변환 (Pydantic 에러 방지)
    s_name = result_dict.get("source_name", "")
    if isinstance(s_name, list):
        result_dict["source_name"] = ", ".join(map(str, s_name))

    validated = KpopNewsSummary(**result_dict)
    payload = summary_to_processed_payload(raw.id, validated)

    payload["trend_insight"] = None
    payload["url"] = raw.url
    payload["published_at"] = raw.published_at
    payload["crawled_at"] = raw.crawled_at

    if not payload.get("ko_title") or not str(payload["ko_title"]).strip():
        payload["ko_title"] = raw.title

    if not payload.get("source_name") or not str(payload["source_name"]).strip():
        if raw.url:
            from urllib.parse import urlparse

            netloc = urlparse(raw.url).netloc.replace("www.", "")
            payload["source_name"] = netloc.split(".")[0].capitalize()
        else:
            payload["source_name"] = "Unknown"

    return payload, validated.image_search_query


def process_and_save(session, batch_size: int = 50) -> int:
    unprocessed = (
        session.query(RawNews)
        .filter(RawNews.is_processed == False)
        .limit(batch_size)
        .all()
    )

    if not unprocessed:
        print("[가공] 더 이상 처리할 새로운 뉴스(RawNews)가 없습니다! 🎉")
        return -1

    print(f"[가공] {len(unprocessed)}건 처리 시작...")
    processed_count = 0

    now = datetime.now()
    threshold_date = (now - timedelta(days=2)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    for raw in unprocessed:
        try:
            # 0. 불량 데이터(Junk) 1차 필터링 (메뉴판, 포털 메인 등 제외)
            is_junk, junk_reason = is_junk_raw_news(raw)
            if is_junk:
                print(f"    [스킵] {junk_reason}")
                raw.is_processed = True
                raw.skip_reason = f"JunkFilter: {junk_reason}"
                session.commit()
                continue

            # 1. AI 가공 호출 (LLM을 통해 요약 및 태그 생성)
            print(f"  → 가공 중: {raw.title[:40]}...")
            result_payload, ai_query = process_single(raw)
            time.sleep(LLM_DELAY)

            # 2. K-엔터 등재 조건 체크 (해외 전용 뉴스 등 필터링)
            if not result_payload.get("is_k_ent", True):
                print(f"    [스킵] K-엔터 등재 조건 미달 (해외 배우/팝 뉴스 필터링)")
                raw.is_processed = True
                session.commit()
                continue

            # 3. [실시간 이미지 수집] DB 컬럼 추가 없이 즉시 검색하여 thumbnail_url 확보
            if not result_payload.get("thumbnail_url"):
                artists = result_payload.get("artist_tags")
                artist_name = artists[0] if artists else None

                # AI 검색어가 있으면 사용, 없으면 백업 로직(build_query_for_processed) 사용
                if ai_query and ai_query.strip():
                    img_query = ai_query.strip()
                else:
                    # AI 검색어가 없을 경우: [개선] RawNews 대신 가공된 정보를 넘겨 백업 쿼리 생성
                    from types import SimpleNamespace
                    mock_article = SimpleNamespace(**result_payload)
                    img_query, _ = build_query_for_processed(mock_article)

                print(f"    📸 이미지 검색 중: {img_query}")
                image_url = pick_non_duplicate_bing_image(
                    session, img_query, artist_name=artist_name, headless=True
                )
                if image_url:
                    result_payload["thumbnail_url"] = image_url
                    print(f"    [이미지] 성공: {image_url}")

            # 2. 날짜에 따른 분기 저장
            pub_at = raw.published_at
            if pub_at and pub_at >= threshold_date:
                session.add(ProcessedNews(**result_payload))
                print(f"    [결과] ProcessedNews 테이블로 저장됨")
            else:
                result_payload.pop("raw_news_id", None)
                tags = result_payload.get("artist_tags") or []
                # result_payload["artist_name"] = tags[0] if tags else None  # 삭제됨
                session.add(PastNews(**result_payload))
                print(f"    [결과] PastNews 테이블로 저장됨 (과거 기사)")

            raw.is_processed = True
            raw.skip_reason = None  # 성공 시 사유 초기화
            session.commit()
            processed_count += 1

        except ValidationError as e:
            print(f"    [스킵] AI 스키마 파괴 (총 {len(e.errors())}개 분류 탈락)")
            for err in e.errors()[:3]:  # 최대 3개까지만 출력
                loc = ".".join(str(x) for x in err["loc"])
                msg = err["msg"]
                print(f"      - 필드 [{loc}]: {msg}")
            if len(e.errors()) > 3:
                print(f"      - ... 외 {len(e.errors()) - 3}개 오류")

            session.rollback()
            raw.is_processed = True
            raw.skip_reason = (
                f"ValidationError: {e.errors()[0]['msg']}"
                if e.errors()
                else "ValidationError"
            )
            session.commit()

        except json.JSONDecodeError as e:
            print(f"    [스킵] 완벽한 JSON 파괴 (괄호 누락 등): {e}")
            session.rollback()
            raw.is_processed = True
            raw.skip_reason = f"JSONDecodeError: {str(e)}"
            session.commit()

        except Exception as e:
            error_msg = str(e).split("\n")[0]
            print(f"    [스킵] 기타 시스템 오류: {error_msg}")
            session.rollback()
            raw.is_processed = True
            raw.skip_reason = f"SystemError: {str(e)[:200]}"
            session.commit()

    print(f"[가공 세트 완료] 총 {len(unprocessed)}건 시도 중 {processed_count}건 성공")
    return processed_count


def migrate_old_processed_news(session):
    """(추가) 하루가 지나 유통기한(3일)이 지난 ProcessedNews를 PastNews로 이동"""
    now = datetime.now()
    threshold_date = (now - timedelta(days=2)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # 기준일보다 오래된 뉴스 찾기
    old_news_list = (
        session.query(ProcessedNews)
        .filter(ProcessedNews.published_at < threshold_date)
        .all()
    )

    if not old_news_list:
        print("[이동] 이동할 오래된 뉴스가 없습니다.")
        return

    print(f"[이동] {len(old_news_list)}건의 뉴스를 PastNews로 마이그레이션 중...")

    for news in old_news_list:
        # 1. PastNews로 복사 (ID 제외하고 모든 속성 복사)
        # SQLAlchemy 모델 객체의 __dict__를 이용하거나 필요한 컬럼을 매핑합니다.
        news_data = {
            c.name: getattr(news, c.name)
            for c in news.__table__.columns
            if c.name != "id"
        }
        session.add(PastNews(**news_data))

        # 2. ProcessedNews에서 삭제
        session.delete(news)

    session.commit()
    print("[이동] 마이그레이션 완료.")


# ═══════════════════════════════════════════════════
# Part 2: 이미지 수집 (Bing 이미지 검색 → thumbnail_url 저장)
# ═══════════════════════════════════════════════════


def _loads_maybe(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, list) else []
        except Exception:
            return []
    return []


def _clean_query(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _norm_url(url: str | None) -> str:
    return (url or "").strip()


def _is_good_image_url(url: str) -> bool:
    if not url:
        return False
    low = url.lower()

    if not low.startswith("http"):
        return False

    bad_keywords = [
        "logo",
        "sprite",
        "icon",
        "tracker",
        "spacer",
        "blank",
        ".svg",
        "r.bing.com",
        "bing.com/rp/",
        "th.bing.com/th?id=ovp",
    ]
    if any(k in low for k in bad_keywords):
        return False

    return True


def get_all_used_thumbnail_urls(session) -> set[str]:
    """processed_news에 이미 저장된 이미지 URL만 중복 체크 대상으로 사용"""
    used = set()

    processed_rows = (
        session.query(ProcessedNews.thumbnail_url)
        .filter(
            ProcessedNews.thumbnail_url.is_not(None),
            ProcessedNews.thumbnail_url != "",
        )
        .all()
    )
    for (u,) in processed_rows:
        if u:
            used.add(_norm_url(u))

    return used


def get_used_urls_for_artist(session, artist_name: str) -> set[str]:
    """같은 아티스트가 processed_news에서 이미 사용한 이미지 URL만 수집"""
    name = (artist_name or "").strip()
    if not name:
        return set()

    used = set()

    rows = (
        session.query(ProcessedNews.artist_tags, ProcessedNews.thumbnail_url)
        .filter(
            ProcessedNews.thumbnail_url.is_not(None),
            ProcessedNews.thumbnail_url != "",
        )
        .all()
    )
    for tags, thumb in rows:
        arr = _loads_maybe(tags)
        arr = [str(x).strip().lower() for x in arr]
        if name.lower() in arr and thumb:
            used.add(_norm_url(thumb))

    return used


def extract_bing_image_candidates(
    query: str, headless: bool = True, max_candidates: int = 20
) -> list[str]:
    query = _clean_query(query)
    if not query:
        return []

    search_url = f"https://www.bing.com/images/search?q={quote(query)}&form=HDRSC3"

    with sync_playwright() as p:
        browser = None
        context = None

        try:
            browser = p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )

            context = browser.new_context(
                locale="ko-KR",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/135.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
            )

            page = context.new_page()
            page.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """
            )

            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            cards = page.locator("a.iusc")
            count = min(cards.count(), 60)

            results = []
            seen = set()

            for i in range(count):
                card = cards.nth(i)

                m_attr = card.get_attribute("m")
                if m_attr:
                    try:
                        m_json = json.loads(m_attr)
                        for key in ("murl", "turl"):
                            url = _norm_url(m_json.get(key))
                            if _is_good_image_url(url) and url not in seen:
                                seen.add(url)
                                results.append(url)
                    except Exception:
                        pass

                img = card.locator("img").first
                if img.count() > 0:
                    for attr_name in ("src", "data-src", "data-thumb", "data-imageurl"):
                        url = _norm_url(img.get_attribute(attr_name))
                        if _is_good_image_url(url) and url not in seen:
                            seen.add(url)
                            results.append(url)

                if len(results) >= max_candidates:
                    break

            return results

        except Exception as e:
            print(f"[bing_candidates] 예외 발생: {e}")
            return []

        finally:
            try:
                if context:
                    context.close()
            except Exception:
                pass
            try:
                if browser:
                    browser.close()
            except Exception:
                pass


def pick_non_duplicate_bing_image(
    session,
    query: str,
    *,
    artist_name: str | None = None,
    headless: bool = True,
) -> str | None:
    all_used = get_all_used_thumbnail_urls(session)
    artist_used = (
        get_used_urls_for_artist(session, artist_name or "") if artist_name else set()
    )

    candidates = extract_bing_image_candidates(
        query, headless=headless, max_candidates=20
    )
    if not candidates:
        return None

    for url in candidates:
        if url not in all_used and url not in artist_used:
            return url

    for url in candidates:
        if url not in artist_used:
            return url

    return candidates[0]


def build_query_for_processed(article) -> tuple[str, str]:
    # (백업) 기존 방식의 검색어 생성 로직
    artists = _loads_maybe(getattr(article, "artist_tags", None))
    cat = getattr(article, "sub_category", "") or ""
    # RawNews(article)일 경우 title을, ProcessedNews일 경우 ko_title을 우선 참조
    title = getattr(article, "ko_title", "") or getattr(article, "title", "")

    # 제목에서 따옴표 안의 핵심 키워드(곡명, 작품명 등) 추출 시도
    extra_context = ""
    if title:
        # 스마트 따옴표와 일반 따옴표 모두 대응
        match = re.search(r"['\"‘“](.*?)['\"’”]", title)
        if match:
            extra_context = match.group(1).strip()

    if artists:
        artist = str(artists[0]).strip()
        # "K-Enter"는 유효한 아티스트가 아니므로 건너뛰고 키워드/제목으로 넘어감
        if artist and artist.lower() != "k-enter":
            # 1. 드라마/영화/배우 관련
            if any(kw in cat for kw in ["드라마", "영화", "OTT", "배우"]):
                if extra_context:
                    return f"{artist} {extra_context} 2026 drama still cut official recent", artist
                return f"{artist} actor 2026 recent press conference HQ", artist
            # 2. 음악/차트/앨범 관련
            elif any(kw in cat for kw in ["음악", "앨범", "차트", "신곡"]):
                if extra_context:
                    return (
                        f"{artist} {extra_context} 2026 music video concept photo recent",
                        artist,
                    )
                return f"{artist} stage performance 2026 focus cam recent", artist
            # 기본 아티스트 검색
            return f"{artist} 2026 Kpop recent high resolution official photo", artist

    # 아티스트가 없거나 "K-Enter"인 경우: 키워드 또는 제목의 핵심 문구 사용
    keywords = _loads_maybe(getattr(article, "keywords", None))
    if keywords and len(keywords) > 0:
        kw = str(keywords[0]).strip()
        return f"{kw} 2026 K-entertainment recent official press HQ", ""

    if extra_context:
        return f"{extra_context} 2026 K-drama movie recent official still cut HQ", ""

    if title:
        # 제목의 앞부분 20자 정도를 검색어로 활용
        short_title = title[:25].strip()
        return f"{short_title} 2026 recent news photo HQ", ""

    return "Kpop idol 2026 recent stage performance 4k", ""


def fetch_images_for_processed(session, sleep_sec: float = 1.5, headless: bool = True, overwrite: bool = False):
    # ProcessedNews 이미지 수집
    query_recent = session.query(ProcessedNews)
    if not overwrite:
        query_recent = query_recent.filter(
            or_(
                ProcessedNews.thumbnail_url.is_(None), ProcessedNews.thumbnail_url == ""
            )
        )
    recent_articles = query_recent.all()

    # PastNews 이미지 수집
    query_past = session.query(PastNews)
    if not overwrite:
        query_past = query_past.filter(
            or_(PastNews.thumbnail_url.is_(None), PastNews.thumbnail_url == "")
        )
    past_articles = query_past.all()

    articles = recent_articles + past_articles

    print(
        f"\n[이미지 처리] 총 {len(articles)}건 수집 시작 (최신: {len(recent_articles)}, 과거: {len(past_articles)})"
    )

    success = 0
    failed = 0

    for article in articles:
        query, artist_name = build_query_for_processed(article)

        print(f"\n[processed_news] 처리 중 ID={article.id}")
        print(f"  - 검색어: {query}")

        image_url = pick_non_duplicate_bing_image(
            session,
            query,
            artist_name=artist_name,
            headless=headless,
        )

        if image_url:
            try:
                article.thumbnail_url = image_url
                session.commit()
                success += 1
                print(f"  - 성공: {image_url}")
            except SQLAlchemyError as e:
                session.rollback()
                failed += 1
                print(f"  - DB 저장 실패: {e}")
        else:
            failed += 1
            print("  - 실패: 적합한 이미지 없음")

        time.sleep(sleep_sec)

    print(f"\n[processed_news] 완료: {success}/{len(articles)}건 성공")


def fetch_processed_images_only(headless: bool = True):
    """processed_news의 thumbnail_url만 채운다. past_news는 건드리지 않는다."""
    with get_session() as session:
        fetch_images_for_processed(session, headless=headless)


if __name__ == "__main__":
    with get_session() as session:
        print("\n🚀 [뉴스 가공 파이프라인 시작]")

        total_processed = 0
        batch_count = 1

        while True:
            print(f"\n--- [{batch_count}회차 세트] 5개 가공 시작 ---")

            # [핵심] batch_size를 5로 설정합니다.
            count = process_and_save(session, batch_size=5)

            # 더 이상 가공할 뉴스가 없으면 루프 종료
            if count == -1:
                print("\n✅ 모든 미처리 뉴스의 가공이 완벽하게 끝났습니다!")
                break

            total_processed += count
            print(
                f"✔️ {batch_count}회차 세트 완료! (현재까지 성공적으로 누적된 데이터: {total_processed}건)"
            )

            # [수정] 5개 가공이 끝날 때마다 이미지를 수집하도록 주석 해제함
            print("📸 현재 세트 이미지 수집 중...")
            fetch_images_for_processed(session, headless=True)

            batch_count += 1

        print(f"\n🏁 최종 완료! 총 {total_processed}건의 데이터가 처리되었습니다.")
