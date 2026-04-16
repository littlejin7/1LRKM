"""
03.processor.py — LLM 가공 + 최신 뉴스 이미지 수집 (3일 기준 분기 처리 버전)

수정 사항:
  1. process_and_save() 내에 3일 기준 날짜 분기 로직 추가
  2. 과거 뉴스는 PastNews 테이블로, 최신 뉴스는 ProcessedNews 테이블로 저장
  3. 마이그레이션 함수(migrate_old_processed_news) 예시 추가
"""

import os
import json
import time
from datetime import datetime
from urllib.parse import quote
from categories import llm_prompt_category_block
from playwright.sync_api import sync_playwright
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from openai import OpenAI
from pydantic import ValidationError
from database import RawNews, ProcessedNews, PastNews, get_session
from schemas import KpopNewsSummary, summary_to_processed_payload

from prompts.summary import get_summary_prompts

# 파일 로딩 시점에 시스템 프롬프트와 유저 템플릿을 한 번만 불러옵니다.
SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT_TEMPLATE = get_summary_prompts()


# ═══════════════════════════════════════════════════
# Part 1: LLM 가공 (raw_news → processed_news)
# ═══════════════════════════════════════════════════


# 26.4.15 기준 주석처리 (용남님쓰던거)
# client = OpenAI(
#     api_key=os.getenv("OPENROUTER_API_KEY"),
#     base_url="https://openrouter.ai/api/v1",
# )

client = OpenAI(
    api_key="ollama",  # Ollama는 키 불필요
    base_url="http://localhost:11434/v1",
)
LLM_MODEL = "gemma3:latest"  # 또는
LLM_DELAY = 0.5


def process_single(raw: RawNews) -> dict:
    """기존과 동일: LLM을 호출하여 가공된 데이터를 반환"""
    content = (raw.content or "")[:3000]

    user_message = SUMMARY_USER_PROMPT_TEMPLATE.format(
        title=raw.title or "",
        content=content,
        raw_category_hint=f"{raw.category} / {raw.sub_category}",
    )

    response = client.chat.completions.create(
        model=LLM_MODEL,
        temperature=0.3,
        timeout=120,
        response_format={"type": "json_object"},
        extra_body={"keep_alive": 0},
        messages=[
            # [수정] 모듈에서 가져온 SUMMARY_SYSTEM_PROMPT 적용
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    raw_text = response.choices[0].message.content or ""
    result = json.loads(raw_text)
    validated = KpopNewsSummary(**result)

    # AI가 만든 요약 결과를 DB 페이로드로 변환할 때
    payload = summary_to_processed_payload(raw.id, validated)

    # 원래 trend_insight에 들어있던 1줄 요약(AI의 첫 분석)을 briefing으로 옮깁니다.
    # 기존 briefing이 리스트 형태라면 그 앞에 추가하거나 교체합니다.

    if payload.get("trend_insight"):
        # 새로운 브리핑 아이템 생성
        new_briefing_item = {"label": "핵심요약", "content": payload["trend_insight"]}

        # 기존 briefing 리스트에 추가 (null인 경우 방지)
        if not payload.get("briefing"):
            payload["briefing"] = []
        payload["briefing"].insert(0, new_briefing_item)

        # [중요] 원래 trend_insight 자리는 일단 비워둡니다 (나중에 랑그래프가 채움)
        payload["trend_insight"] = ""

    # [수정] RawNews의 원본 정보(URL, 발행일 등)를 페이로드에 합쳐줍니다.
    payload["url"] = raw.url
    payload["published_at"] = raw.published_at
    payload["crawled_at"] = raw.crawled_at
    
    # AI가 ko_title을 백지로 냈거나 빼먹은 경우, 원본 기사의 영어/기존 제목으로 채워넣기
    if not payload.get("ko_title") or not str(payload["ko_title"]).strip():
        payload["ko_title"] = raw.title

    # AI가 source_name을 빼먹은 경우 URL에서 파싱하여 채움
    if not payload.get("source_name") or not str(payload["source_name"]).strip():
        if raw.url:
            from urllib.parse import urlparse
            netloc = urlparse(raw.url).netloc.replace("www.", "")
            payload["source_name"] = netloc.split(".")[0].capitalize()
        else:
            payload["source_name"] = "Unknown"

    return payload


def process_and_save(session, batch_size: int = 50) -> int:
    """미처리된 raw_news를 가공하여 저장"""
    unprocessed = (
        session.query(RawNews)
        .filter(RawNews.is_processed == False)
        .limit(batch_size)
        .all()
    )

    if not unprocessed:
        print("[가공] 처리할 뉴스가 없습니다.")
        return 0

    # --- 실행 영역 시작 ---
    print(f"[가공] {len(unprocessed)}건 처리 시작...")
    processed_count = 0  # 이 변수가 주석 밖에 있어야 숫자를 셉니다!

    # 1. 날짜 기준선 로직 적용
    from datetime import timedelta

    now = datetime.now()
    threshold_date = (now - timedelta(days=2)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    for raw in unprocessed:
        try:
            print(f"  → 가공 중: {raw.title[:40]}...")
            result_payload = process_single(raw)
            time.sleep(LLM_DELAY)

            if not result_payload.get("is_k_ent", True):
                print(f"    [스킵] K-엔터 등재 조건 미달 (해외 배우/팝 뉴스 필터링)")
                # 해당 원본 기사는 가공 완료(스킵) 처리
                raw.is_processed = True
                session.commit()
                continue

            # 2. 날짜에 따른 분기 저장
            pub_at = raw.published_at
            if pub_at and pub_at >= threshold_date:
                session.add(ProcessedNews(**result_payload))
                print(f"    [결과] ProcessedNews 테이블로 저장됨")
            else:
                result_payload.pop("raw_news_id", None)
                session.add(PastNews(**result_payload))
                print(f"    [결과] PastNews 테이블로 저장됨 (과거 기사)")

            raw.is_processed = True
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
            session.commit()
            
        except json.JSONDecodeError as e:
            print(f"    [스킵] 완벽한 JSON 파괴 (괄호 누락 등): {e}")
            session.rollback()
            raw.is_processed = True
            session.commit()
            
        except Exception as e:
            error_msg = str(e).split('\n')[0]
            print(f"    [스킵] 기타 시스템 오류: {error_msg}")
            session.rollback()
            raw.is_processed = True
            session.commit()

    print(f"[가공 완료] {processed_count}/{len(unprocessed)}건 처리됨")
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
    artists = _loads_maybe(getattr(article, "artist_tags", None))
    cat = getattr(article, "sub_category", "") or ""

    if artists:
        artist = str(artists[0]).strip()
        # 드라마/영화/배우/OTT 관련 뉴스라면 화보나 시상식 사진 위주로
        if any(kw in cat for kw in ["드라마", "영화", "OTT", "배우"]):
            return f"{artist} actor photoshoot HQ", artist
        # K-pop 및 그 외 카테고리는 고해상도 잡지 화보나 컨셉 포토
        else:
            return f"{artist} Kpop magazine photoshoot HQ", artist

    keywords = _loads_maybe(getattr(article, "keywords", None))
    if keywords:
        return f"{keywords[0]} K-entertainment high resolution", ""

    source_name = getattr(article, "source_name", None) or ""
    if source_name.strip():
        return f"{source_name} Kpop high quality press", ""

    return "Kpop idol photoshoot HQ", ""


def fetch_images_for_processed(session, sleep_sec: float = 1.5, headless: bool = True):
    # ProcessedNews 이미지 누락본 수집
    recent_articles = (
        session.query(ProcessedNews)
        .filter(
            or_(
                ProcessedNews.thumbnail_url.is_(None), ProcessedNews.thumbnail_url == ""
            )
        )
        .all()
    )

    # PastNews 이미지 누락본 수집
    past_articles = (
        session.query(PastNews)
        .filter(or_(PastNews.thumbnail_url.is_(None), PastNews.thumbnail_url == ""))
        .all()
    )

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
            if count == 0:
                print("\n✅ 모든 미처리 뉴스의 가공이 완료되었습니다.")
                break

            total_processed += count
            print(f"✔️ {batch_count}회차 완료! (현재까지 누적 {total_processed}건)")

            # [수정] 5개 가공이 끝날 때마다 이미지를 수집하도록 주석 해제함
            print("📸 현재 세트 이미지 수집 중...")
            fetch_images_for_processed(session, headless=True)

            batch_count += 1

        print(f"\n🏁 최종 완료! 총 {total_processed}건의 데이터가 처리되었습니다.")
