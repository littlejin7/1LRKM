"""
02.crawler.py — 최신 뉴스 + 과거 뉴스 크롤러 통합 (최종본)

[수정 및 보완 내역]
1. LOOKBACK_DAYS: 7일로 변경 (일주일치 수집)
2. CATEGORY_MAPPING: 대분류/중분류 정의 반영
3. 본문 정제: _NOISE_PATTERNS 및 clean_content 함수 복구 (광고 및 쓰레기 텍스트 제거)
4. 카테고리 할당: 반복문(for cat_name)을 통해 수집 시점에 대/중분류 매핑
5. DB 호환성: database.py의 RawNews 컬럼(category, sub_category)과 100% 일치
"""

import os
import re
import json
import asyncio
import time
import logging
import feedparser
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, quote_plus
from sqlalchemy.exc import IntegrityError
from playwright.async_api import async_playwright
from dotenv import load_dotenv

# database.py에서 필요한 모델 및 세션 헬퍼 임포트
from database import RawNews, get_session

load_dotenv()

# ── 로깅 설정 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("crawler")

# ═══════════════════════════════════════════════════
# 공통 설정 및 카테고리 매핑
# ═══════════════════════════════════════════════════


def _env_int(name: str, default: int) -> int:
    v = (os.getenv(name) or "").strip()
    try:
        return int(v) if v else default
    except Exception:
        return default


# 크롤링 제어 설정값 유지
RAW_CONTENT_MAX_CHARS = _env_int("RAW_CONTENT_MAX_CHARS", 8000)
PW_MIN_CONTENT_LEN = 500
TAVILY_MAX_RESULTS = max(1, _env_int("TAVILY_MAX_RESULTS", 40))  # 엄청난 물량 확보를 위해 40으로 대폭 상향
MAX_PER_DOMAIN = max(1, _env_int("CRAWL_MAX_PER_DOMAIN", 10))
TAVILY_RETRY = 2
LOOKBACK_DAYS = 7  # 일주일치 수집 기준


def get_standard_category(sub_name: str) -> tuple[str, str]:
    """중분류명을 주면 고정된 대분류와 함께 반환 (이미지 계층 구조 기준)"""
    mapping = {
        # 컨텐츠 & 작품
        "음악/차트": "컨텐츠 & 작품",
        "앨범/신곡": "컨텐츠 & 작품",
        "콘서트/투어": "컨텐츠 & 작품",
        "드라마/방송": "컨텐츠 & 작품",
        "예능/방송": "컨텐츠 & 작품",
        "공연/전시": "컨텐츠 & 작품",
        "영화/OTT": "컨텐츠 & 작품",
        # 인물 & 아티스트
        "팬덤/SNS": "인물 & 아티스트",
        "스캔들/논란": "인물 & 아티스트",
        "인사/동정": "인물 & 아티스트",
        "미담/기부": "인물 & 아티스트",
        "연애/결혼": "인물 & 아티스트",
        "입대/군복무": "인물 & 아티스트",
        # 비즈니스 & 행사
        "산업/기획사": "비즈니스 & 행사",
        "해외반응": "비즈니스 & 행사",
        "마케팅/브랜드": "비즈니스 & 행사",
        "행사/이벤트": "비즈니스 & 행사",
        "기타": "비즈니스 & 행사",
    }
    category = mapping.get(sub_name, "비즈니스 & 행사")
    return category, sub_name


# ═══════════════════════════════════════════════════
# 본문 정제 로직 (노이즈 제거)
# ═══════════════════════════════════════════════════

_NOISE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"Advertisement",
        r"Sponsored",
        r"©.*",
        r"All rights reserved.*",
        r"Reporter\s*:\s*.*",
        r"Contact\s*:\s*.*",
        r"Email\s*:\s*.*",
        r"RELATED ARTICLES.*",
        r"Read more.*",
        r"Sign up for.*newsletter.*",
        r"Subscribe\s*(to|for)?\s*.*",
        r"Follow us on.*",
        r"Share this article.*",
        r"Tags\s*:.*",
        r"Photo\s*credit\s*:.*",
        r"Source\s*:.*",
    ]
]


def clean_content(text: str) -> str:
    """본문에서 광고 및 불필요한 텍스트를 제거하고 정제함"""
    if not text:
        return text
    for pat in _NOISE_PATTERNS:
        text = pat.sub("", text)

    # 20자 미만의 짧은 줄(메뉴, 날짜 등) 제거
    lines = [line.strip() for line in text.split("\n") if len(line.strip()) >= 20]
    cleaned = re.sub(r"\n{2,}", "\n", "\n".join(lines)).strip()

    # [추가] 정제 후 최종 글자 수가 200자 미만이면 '함량 미달'로 판단하여 애초에 테이블에 넣지 않음
    if len(cleaned) < 200:
        return ""

    return cleaned


# ── RSS 및 Tavily 설정 (기존 쿼리 유지) ──
RSS_FEEDS = {
    "음악/차트": ["https://www.soompi.com/feed", "https://www.allkpop.com/feed"],
    "드라마/방송": ["https://www.soompi.com/feed", "https://www.hancinema.net/rss.xml"],
    "산업/기획사": ["https://www.allkpop.com/feed", "https://www.koreaboo.com/feed/"],
}

DEFAULT_QUERIES = {
    # 컨텐츠 & 작품
    "음악/차트": '(K-pop OR K팝) (Billboard OR 빌보드 OR chart OR 차트 OR Spotify)',
    "앨범/신곡": '(K-pop OR K팝 OR 아이돌) (comeback OR 컴백 OR teaser OR 티저 OR MV OR 뮤비)',
    "콘서트/투어": '(K-pop OR K팝 OR 아이돌) (world tour OR 월드투어 OR concert OR 콘서트 OR 팬미팅)',
    "드라마/방송": '(K-drama OR K드라마 OR 한국 드라마) (casting OR 캐스팅 OR ratings OR 시청률 OR Netflix OR 넷플릭스)',
    "예능/방송": '(Korean variety OR 한국 예능 OR 리얼리티) (cast OR 출연 OR episode OR 회차 OR 방영)',
    "영화/OTT": '(Korean movie OR 한국 영화 OR K-movie) (box office OR 박스오피스 OR release OR 개봉 OR premiere)',
    "공연/전시": '(Korean musical OR 한국 뮤지컬 OR exhibition OR 전시 OR pop-up OR 팝업스토어)',
    
    # 인물 & 아티스트
    "팬덤/SNS": '(K-pop OR K팝) (fandom OR 팬덤 OR trending OR 트렌드 OR viral OR 바이럴 OR Twitter OR TikTok)',
    "스캔들/논란": '(K-pop OR K팝 OR 연예인 OR 배우 OR 아이돌) (scandal OR 스캔들 OR controversy OR 논란 OR rumor OR 루머 OR 사과문)',
    "인사/동정": '(K-pop OR 연예인 OR 배우 OR 아이돌) (award OR 수상 OR interview OR 인터뷰 OR red carpet OR 레드카펫)',
    "미담/기부": '(K-pop OR 연예인 OR 배우 OR 아이돌) (donation OR 기부 OR charity OR 선행 OR 미담)',
    "연애/결혼": '(K-pop OR 연예인 OR 배우 OR 아이돌) (dating OR 열애 OR marriage OR 결혼 OR 결별)',
    "입대/군복무": '(K-pop OR 연예인 OR 배우 OR 아이돌) (military OR 군대 OR enlistment OR 입대 OR discharge OR 전역)',
    
    # 비즈니스 & 행사
    "산업/기획사": '(K-pop agency OR 기획사 OR 엔터테인먼트) (HYBE OR 하이브 OR SM OR JYP OR YG OR Starship OR 스타쉽 OR Cube OR 어도어)',
    "해외반응": '(K-pop OR K팝 OR K-drama) (global response OR 해외 반응 OR international success OR 외신)',
    "마케팅/브랜드": '(K-pop OR 연예인 OR 배우) (ambassador OR 앰버서더 OR campaign OR 캠페인 OR 발탁 OR 광고)',
    "행사/이벤트": '(K-pop OR 연예인 OR 배우) (press conference OR 제작발표회 OR fan sign OR 팬싸인회 OR 행사)',
    "기타": '(Korean entertainment OR 한국 연예계) (news OR 뉴스 OR 이슈)',
}

# ── 유틸리티 함수 ──


def parse_date(date_string: str) -> datetime | None:
    if not date_string:
        return None
    try:
        return parsedate_to_datetime(date_string)
    except Exception:
        try:
            return datetime.fromisoformat(date_string.replace("Z", "+00:00"))
        except Exception:
            return None


def is_within_lookback(published_at: datetime | None) -> bool:
    """7일 이내의 기사인지 확인"""
    if not published_at:
        return False
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    return published_at >= cutoff


# ── 데이터 수집 함수 ──


def fetch_news_from_rss() -> list[dict]:
    """RSS 피드에서 뉴스를 수집함"""
    all_news = []
    seen_urls = set()

    # [수정] RSS_FEEDS의 키(중분류명)를 순회하며 표준 대/중분류를 가져옴
    for sub_target, feeds in RSS_FEEDS.items():
        # 이제 get_standard_category 함수를 사용합니다.
        category, sub_category = get_standard_category(sub_target)

        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    url = entry.get("link", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)

                    pub_at = parse_date(entry.get("published"))
                    if pub_at and not is_within_lookback(pub_at):
                        continue

                    # 본문 정제 적용
                    raw_summary = entry.get("summary", "") or ""
                    content = clean_content(re.sub(r"<[^>]+>", " ", raw_summary))

                    if not content:  
                        continue

                    all_news.append(
                        {
                            "title": entry.get("title", ""),
                            "content": content,
                            "url": url,
                            "published_at": pub_at or datetime.now(timezone.utc),
                            "crawled_at": datetime.now(),
                            "is_processed": False,
                            "category": category,  # RawNews 테이블 category 컬럼
                            "sub_category": sub_category,  # RawNews 테이블 sub_category 컬럼
                        }
                    )
            except Exception as e:
                log.error(f"[RSS 오류] {feed_url}: {e}")
    return all_news


def fetch_news_from_tavily(query: str, label: str = "Unknown") -> list[dict]:
    """Tavily API를 통해 뉴스를 수집함"""
    from tavily import TavilyClient

    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

    category, sub_category = get_standard_category(label)

    for attempt in range(TAVILY_RETRY + 1):
        try:
            response = client.search(
                query=query,
                search_depth="advanced",
                topic="general",
                days=7,
                max_results=TAVILY_MAX_RESULTS,
                include_raw_content=True,
                include_domains=[
                    # 해외 K팝/한류 전용 매체
                    "soompi.com",
                    "allkpop.com",
                    "koreaboo.com",
                    "hancinema.net",
                    "kpopmap.com",
                    "kpopstarz.com",
                    
                    # [추가] 글로벌 대형 매체 (빌보드 등은 서구권 팝가수가 너무 섞여서 제외)
                    "bandwagon.asia",

                    # [추가] 국내 초거대 포털 (수집량 폭발의 핵심)
                    "naver.com",
                    "daum.net",
                    "nate.com",

                    # 국내 종합/연예 언론사 및 방송사
                    "dispatch.co.kr",
                    "starnewskorea.com",
                    "xportsnews.com",
                    "newsen.com",
                    "imbc.com",
                    "sbs.co.kr",
                    "kbs.co.kr",
                    "ytn.co.kr",
                    "mbn.co.kr",
                    "yna.co.kr",
                    "koreaherald.com",
                    "koreatimes.co.kr",
                    "koreajoongangdaily.joins.com",
                    "donga.com",
                    "joongang.co.kr",
                    "hankyung.com",
                    "edaily.co.kr",
                    "mk.co.kr"
                ],
            )
            results = []
            for item in response.get("results", []):
                pub_at = parse_date(item.get("published_date"))
                if pub_at and not is_within_lookback(pub_at):
                    continue

                # 본문 정제 적용
                raw_text = item.get("raw_content") or item.get("content", "")
                content = clean_content(raw_text)

                if not content:  # [추가] 너무 짧은 기사는 AI 가공 효율을 위해 제외
                    continue

                results.append(
                    {
                        "title": item.get("title", ""),
                        "content": content[:RAW_CONTENT_MAX_CHARS],
                        "url": item.get("url", ""),
                        "published_at": pub_at or datetime.now(timezone.utc),
                        "crawled_at": datetime.now(),
                        "is_processed": False,
                        "category": category,
                        "sub_category": sub_category,
                    }
                )
            return results
        except Exception as e:
            if attempt < TAVILY_RETRY:
                time.sleep(2)
            else:
                log.error(f"[Tavily 최종 실패] {query}: {e}")
    return []


# ── 저장 함수 (database.py 스키마와 100% 일치) ──


def save_raw_news(session, news_list: list[dict]) -> int:
    """수집된 뉴스를 raw_news 테이블에 저장함"""
    if not news_list:
        return 0
    saved_count = 0
    for news in news_list:
        try:
            # URL 기반 중복 체크
            exists = session.query(RawNews).filter(RawNews.url == news["url"]).first()
            if exists:
                continue

            # database.py의 RawNews 정의에 맞춰 컬럼 매핑
            raw = RawNews(
                title=news["title"],
                content=news["content"],
                url=news["url"],
                published_at=news["published_at"],
                crawled_at=news["crawled_at"],
                is_processed=news["is_processed"],
                category=news["category"],  # 대분류 (ex: 컨텐츠 & 작품)
                sub_category=news["sub_category"],  # 중분류 (ex: 음악/차트)
            )
            session.add(raw)
            session.commit()
            saved_count += 1
        except Exception as e:
            session.rollback()
            log.error(f"[저장 실패] {news['url']}: {e}")
    return saved_count


def crawl_and_save():
    """크롤링 실행 메인 파이프라인 (로그 보강 버전)"""
    with get_session() as session:
        log.info("[1단계] RSS 수집 및 정제 시작")
        rss_news = fetch_news_from_rss()
        log.info(f"  → RSS 수집 완료: {len(rss_news)}건 발견")  # 추가
        saved_rss = save_raw_news(session, rss_news)
        log.info(f"  → RSS 저장 완료: {saved_rss}건 신규 저장")  # 추가

        log.info("[2단계] Tavily API 수집 및 정제 시작")
        for label, query in DEFAULT_QUERIES.items():
            log.info(f"  → Tavily 쿼리 실행 중: [{label}] {query}")  # 추가
            tav_news = fetch_news_from_tavily(query, label=label)
            log.info(f"    - {len(tav_news)}건 발견")  # 추가
            saved_tav = save_raw_news(session, tav_news)
            log.info(f"    - {saved_tav}건 신규 저장")  # 추가

        log.info("✅ 모든 수집 및 저장 프로세스 종료")  # 추가


if __name__ == "__main__":
    crawl_and_save()
