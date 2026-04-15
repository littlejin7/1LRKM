"""
03.processor.py — LLM 가공 + 최신 뉴스 이미지 수집

역할:
  process_and_save()              : raw_news → LLM 가공 → processed_news 저장
  fetch_processed_images_only()   : processed_news 썸네일만 수집

주의:
  - past_news에는 이미지를 저장하지 않음
"""

import os
import json
import time
from datetime import datetime
from urllib.parse import quote

from playwright.sync_api import sync_playwright
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from openai import OpenAI
from pydantic import ValidationError
from schemas import KpopNewsSummary, summary_to_processed_payload, EnglishSummaryCard, KoreanSummaryCard
from database import RawNews, ProcessedNews, get_session


# ═══════════════════════════════════════════════════
# Part 1: LLM 가공 (raw_news → processed_news)
# ═══════════════════════════════════════════════════


#26.4.15 기준 주석처리 (용남님쓰던거)
# client = OpenAI(
#     api_key=os.getenv("OPENROUTER_API_KEY"),
#     base_url="https://openrouter.ai/api/v1",
#)

client = OpenAI(
    api_key="ollama",           # Ollama는 키 불필요
    base_url="http://localhost:11434/v1",
)
LLM_MODEL = "gemma4:latest"       # 또는 "gemma4"
LLM_DELAY = 2


#채은님이 시스템프롬프트 줄예정

SYSTEM_PROMPT = """너는 K-엔터테인먼트 뉴스 분석 전문가야.
주어진 뉴스 기사만 근거로, 아래 JSON 객체 하나만 출력한다. JSON 바깥 텍스트/설명/마크다운/코드펜스 금지.

{
  "summary": [
    {"label": "핵심사실", "content": "본문 근거 한 줄 존댓말"},
    {"label": "맥락배경", "content": "..."},
    {"label": "영향범위", "content": "..."},
    {"label": "추가쟁점", "content": "..."}
  ],
  "summary_en": [
    {"label": "Key fact", "content": "One complete English sentence."},
    {"label": "Context", "content": "..."},
    {"label": "Impact", "content": "..."},
    {"label": "Extra angle", "content": "..."}
  ],
  "artist_tags": ["본문에 실제 등장한 인물·그룹명, 없으면 []"],
  "keywords": ["비인명 키워드만 정확히 5개"],
  "sub_category": "아래 허용 목록 중 정확히 1개",
  "category": "sub_category 와 동일한 문자열(레거시 호환)",
  "sentiment": "긍정|부정|중립 중 하나(한글)",
  "sentiment_score": null,
  "importance": 1,
  "importance_reason": "[IP0+사건0+파급0+기본1=1] 근거 한 문장",
  "trend_insight": "유진님이 만들꺼야",
  "source_name": "출처 사이트명(예: 빌보드, 위버스)",
  "tts_text": "한국어 구어체 라디오 브리핑 150~220자 권장. URL/해시태그/이모지/마크다운 금지."
}

[필드 규칙]
- summary / summary_en: 각각 '요약 카드' 배열. 정확히 4~6개(동일 개수). 순서 1:1 대응. (위 JSON 예시는 최소 4개; 기사에 맞으면 5~6개까지.)
  - summary: label 2~10자 한글 명사구, content 본문 근거 한 줄(존댓말). 카드끼리 중복·복붙 금지.
  - summary_en: label 2~30자 영어, content 영어 한 문장. i번째 카드는 i번째 한국어 카드와 같은 초점.
- artist_tags: 제목/본문에 실제로 나온 이름만. 없으면 [].
- keywords: 정확히 5개. artist_tags 인명/그룹명은 넣지 말고 테마·형식·행사·차트 등 비인명만.
- sub_category: 아래 중 정확히 하나만(오타·영문 라벨 금지).
  음악/차트, 앨범/신곡, 콘서트/투어, 드라마/방송, 예능/방송, 공연/전시, 영화/OTT,
  팬덤/SNS, 스캔들/논란, 인사/동정, 미담/기부, 연애/결혼, 입대/군복무,
  산업/기획사, 해외반응, 마케팅/브랜드, 행사/이벤트, 기타
- category: 반드시 sub_category 와 같은 문자열.
- sentiment: 반드시 한글 "긍정" 또는 "부정" 또는 "중립".
- sentiment_score: 항상 null.
- importance: 1~10 정수.
- importance_reason: `[IPa+사건b+파급c+기본1=총점]` 형식. a,b,c는 0~3 정수, 총점=a+b+c+1 이고 importance 와 일치.
- trend_insight: 유진님이만들꺼야
- tts_text: 한국어 라디오 앵커 톤. 숫자는 읽기 좋게 한글 혼합 표기 가능.
- briefing 필드는 출력하지 않는다."""



# 스키마 컬럼은 schemas의 summary_to_processed_payload로 옮겼습니다.
def process_single(raw: RawNews) -> dict:
    content = (raw.content or "")[:3000]

    user_message = f"""아래 뉴스를 분석해줘.

제목: {raw.title or ""}
URL: {raw.url or ""}
발행일: {raw.published_at or ""}
본문:
{content}"""

    response = client.chat.completions.create(
        model=LLM_MODEL,
        temperature=0.3,
        timeout=60,
        response_format={"type": "json_object"},
        extra_body={"keep_alive":0},   #멘토님 추천옵션
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    raw_text = response.choices[0].message.content or ""

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM JSON 파싱 실패 (raw_news_id={raw.id})") from e

    try:
        validated = KpopNewsSummary(**result)
    except ValidationError as e:
        raise ValueError(
            f"LLM 스키마 검증 실패 (raw_news_id={raw.id}): {e.errors()} | raw_text={raw_text[:500]}"
        ) from e
    
    payload = summary_to_processed_payload(raw.id, validated)
    payload["url"] = raw.url or ""
    payload["processed_at"] = datetime.now()
    return payload

def process_and_save(session, batch_size: int = 50) -> int:
    """미처리된 raw_news를 LLM으로 가공 → processed_news에 저장"""
    unprocessed = (
        session.query(RawNews)
        .filter(RawNews.is_processed == False)
        .limit(batch_size)
        .all()
    )

    if not unprocessed:
        print("[가공] 처리할 뉴스가 없습니다.")
        return 0

    print(f"[가공] {len(unprocessed)}건 처리 시작...")
    processed_count = 0

    for raw in unprocessed:
        try:
            print(f"  → 가공 중: {raw.title[:40]}...")

            result = process_single(raw)
            time.sleep(LLM_DELAY)

            session.add(ProcessedNews(**result))
            raw.is_processed = True
            session.commit()
            processed_count += 1

        except Exception as e:
            print(f"  [오류] '{raw.title[:30]}...': {e}")
            session.rollback()

    print(f"[가공 완료] {processed_count}/{len(unprocessed)}건 처리됨")
    return processed_count


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
        "logo", "sprite", "icon", "tracker", "spacer", "blank",
        ".svg", "r.bing.com", "bing.com/rp/", "th.bing.com/th?id=ovp",
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


def extract_bing_image_candidates(query: str, headless: bool = True, max_candidates: int = 20) -> list[str]:
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
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

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
    artist_used = get_used_urls_for_artist(session, artist_name or "") if artist_name else set()

    candidates = extract_bing_image_candidates(query, headless=headless, max_candidates=20)
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
    if artists:
        artist = str(artists[0]).strip()
        return f"{artist} official photo", artist

    keywords = _loads_maybe(getattr(article, "keywords", None))
    if keywords:
        return f"{keywords[0]} kpop official photo", ""

    source_name = getattr(article, "source_name", None) or ""
    if source_name.strip():
        return f"{source_name} k-entertainment", ""

    return "kpop idol official photo", ""


def fetch_images_for_processed(session, sleep_sec: float = 1.5, headless: bool = True):
    articles = (
        session.query(ProcessedNews)
        .filter(
            or_(ProcessedNews.thumbnail_url.is_(None), ProcessedNews.thumbnail_url == "")
        )
        .all()
    )

    print(f"\n[processed_news] 총 {len(articles)}건 이미지 처리 시작")

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
    fetch_processed_images_only(headless=True)
