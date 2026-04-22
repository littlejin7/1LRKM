"""
collect.py — 전체 카테고리(컨텐츠, 인물, 비즈니스) 통합 크롤러

1. 모든 카테고리(컨텐츠 & 작품 포함) 유지
2. 본문 최소 글자 수 500자
3. raw_artist_hint 필드 추가:
   - 제목+본문에서 사람 이름으로 보이는 패턴을 정규식으로 추출
   - processor.py가 이를 참고하여 배우/가수가 아닌 메인 인물도 artist_tags에 포함
"""

import sys
from pathlib import Path

# 프로젝트 루트(Parent Directory)를 모듈 검색 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import re
import json
import time
import logging
import feedparser
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, quote_plus
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv

from database import RawNews, get_session

load_dotenv()

# ── 로깅 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("crawler1")



import os
import re
import json
import time
import logging
import feedparser
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv

from database import RawNews, get_session
from collect_config import (
    DEFAULT_QUERIES, RSS_FEEDS, CATEGORY_MAPPING,
    RAW_CONTENT_MAX_CHARS, TAVILY_MAX_RESULTS, TAVILY_RETRY,
    RSS_MAX_TOTAL, RSS_MIN_CONTENT_LEN,
    INCLUDE_DOMAINS, EXCLUDE_DOMAINS, get_standard_category
)
from collect_utils import (
    clean_content, extract_person_hint, is_korean_ent,
    parse_date, extract_date_from_text, is_within_lookback,
    is_junk_news, is_blog_url
)

# ═══════════════════════════════════════════════════
# Tavily 쿼리

# ═══════════════════════════════════════════════════

DEFAULT_QUERIES: dict[str, str] = {
    # 컨텐츠 & 작품
    "음악/차트": "(K팝 OR 아이돌) (멜론 OR 차트 OR 1위 OR 음원 성적 OR 빌보드)", 
    "앨범/신곡": "(K-pop OR K팝 OR 아이돌) (comeback OR 컴백 OR teaser OR 티저 OR MV OR 신곡)",
    "콘서트/투어": "(K-pop OR K팝 OR 아이돌) (world tour OR 월드투어 OR 현지 반응 OR concert OR 팬미팅)",
    "드라마/방송": "(K드라마 OR 한국 드라마 OR 다큐멘터리) (캐스팅 OR 시청률 OR 티빙 OR 웨이브 OR 디즈니플러스 OR TVING OR Wavve OR Disney+)",
    "예능/방송": "(한국 예능 OR 리얼리티 OR 다큐) (출연진 OR 방영일 OR 티빙 OR 웨이브 OR 디즈니플러스 OR TVING OR Wavve)",
    "영화/OTT": "(한국 영화 OR K-movie OR 오리지널) (티빙 OR 웨이브 OR 디즈니플러스 OR TVING OR Wavve OR Disney+ OR 넷플릭스)",
    "공연/전시": "(한국 뮤지컬 OR 연극 OR exhibition OR 전시 OR 팝업스토어)",
    # 인물 & 아티스트
    "팬덤/SNS": "(K-pop OR K팝) (fandom OR 팬덤 OR 트렌드 OR viral OR 바이럴 OR Twitter)",
    "스캔들/논란": "(K-pop OR K팝 OR 연예인 OR 배우) (scandal OR 스캔들 OR controversy OR 논란 OR rumor OR 루머)",
    "인사/동정": "(K-pop OR 연예인 OR 배우) (award OR 수상 OR interview OR 인터뷰 OR red carpet OR 레드카펫)",
    "미담/기부": "(K팝 OR 연예인 OR 배우) (기부 OR 선행 OR 미담 OR 봉사 OR 전달)",
    "연애/결혼": "(K-pop OR 연예인 OR 배우) (dating OR 열애 OR marriage OR 결혼 OR 결별 OR 데이트)",
    "입대/군복무": "(K팝 OR 연예인 OR 배우) (입대 OR 군대 OR 전역 OR 훈련소 OR 복무)",
    # 비즈니스 & 행사
    "산업/기획사": "(K-pop agency OR 기획사 OR 엔터사) (HYBE OR 하이브 OR SM OR JYP OR YG OR 인수)",
    "해외반응": "(K-pop OR K팝 OR K-drama) (global response OR 해외 반응 OR international success OR 외신)",
    "마케팅/브랜드": "(K-pop OR 연예인 OR 배우) (ambassador OR 앰버서더 OR campaign OR 캠페인 OR 발탁 OR 광고)",
    "행사/이벤트": "(K-pop OR 연예인 OR 배우) (press conference OR 제작발표회 OR fan sign OR 팬사인회 OR 행사)",
    "기타": "(한국 연예계 OR 연예계 소식) (뉴스 OR 이슈 OR 화제)",
}

RSS_FEEDS: dict[str, list[str]] = {
    "음악/차트": [
        "https://www.soompi.com/feed",
        "https://www.allkpop.com/feed",
        "https://www.yna.co.kr/rss/entertainment.xml",
    ],
    "드라마/방송": [
        "https://www.soompi.com/feed",
        "https://www.hancinema.net/rss.xml",
        "https://rss.donga.com/entertainment.xml",
    ],
    "스캔들/논란": [
        "https://www.allkpop.com/feed/",
    ],
    "인사/동정": [
        "https://www.soompi.com/feed",
        "https://www.hani.co.kr/rss/entertainment/",
    ],
    "산업/기획사": [
        "https://www.allkpop.com/feed",
        "https://www.chosun.com/arc/outboundfeeds/rss/category/entertainment/?outputType=xml",
    ],
}

# ★ 블로그 제외: naver.com/daum.net/nate.com은 블로그가 섞이므로 제거
#   대신 언론사 도메인만 명시적으로 포함
INCLUDE_DOMAINS = [
    # --- 글로벌 K-엔터 전문지 (빌보드 제외) ---
    "soompi.com",
    "allkpop.com",
    "hancinema.net",
    "kpopmap.com",
    "kpopstarz.com",
    "bandwagon.asia",
    "nme.com",
    # --- 국내 주요 통신사 및 연예 전문지 ---
    "yna.co.kr",        # 연합뉴스
    "newsis.com",       # 뉴시스
    "news1.kr",         # 뉴스1
    "dispatch.co.kr",   # 디스패치
    "starnewskorea.com", # 스타뉴스
    "xportsnews.com",   # 엑스포츠뉴스
    "osen.co.kr",       # OSEN
    "mydaily.co.kr",    # 마이데일리
    "newsen.com",       # 뉴스엔
    "joynews24.com",    # 조이뉴스24
    "inews24.com",      # 아이뉴스24
    "tvdaily.co.kr",    # TV데일리
    "tenasia.hankyung.com", # 텐아시아
    "isplus.com",       # 일간스포츠
    "stoo.com",         # 스포츠투데이
    "sports.chosun.com",
    "sports.donga.com",
    "sports.khan.co.kr",
    "sportsseoul.com",
    "news.naver.com",
    "news.daum.net",
    # --- 주요 일간지 및 경제지 (엔터 섹션) ---
    "chosun.com",
    "donga.com",
    "joongang.co.kr",
    "hani.co.kr",
    "khan.co.kr",
    "hankyung.com",
    "mk.co.kr",
    "edaily.co.kr",
    "mt.co.kr",
    "fnnews.com",
    "asiae.co.kr",
    "sedaily.com",
    "hankookilbo.com",
    "koreaherald.com",
    "koreatimes.co.kr",
    "koreajoongangdaily.joins.com",
    # --- 방송사 뉴스 ---
    "imbc.com",
    "sbs.co.kr",
    "kbs.co.kr",
    "ytn.co.kr",
    "mbn.co.kr",
    "jtbc.co.kr",
    "tvchosun.com",
    "channela.com",
]

# ★ Tavily exclude_domains: 블로그 플랫폼 명시적 차단
EXCLUDE_DOMAINS = [
    "blog.naver.com",
    "blog.daum.net",
    "tistory.com",
    "brunch.co.kr",
    "velog.io",
    "medium.com",
    "wordpress.com",
    "blogspot.com",
    "cafe.naver.com",
    "cafe.daum.net",
    "post.naver.com",
    "koreaboo.com",
]

# ★ URL 패턴 기반 블로그 필터 (RSS 등 exclude_domains 미적용 경로 대비)
_BLOG_URL_PATTERNS = re.compile(
    r"(blog\.naver\.com|blog\.daum\.net|tistory\.com"
    r"|brunch\.co\.kr|velog\.io|medium\.com"
    r"|wordpress\.com|blogspot\.com"
    r"|cafe\.naver\.com|cafe\.daum\.net|post\.naver\.com)",
    re.IGNORECASE,
)


def is_blog_url(url: str) -> bool:
    """URL이 블로그/카페/포스트 계열이거나 특정 국가(중국/일본) 도메인이면 True"""
    u = (url or "").lower()
    if _BLOG_URL_PATTERNS.search(u):
        return True
    # 중국(.cn), 일본(.jp), 대만(.tw) 도메인 차단
    if any(u.endswith(ext) or f"{ext}/" in u for ext in [".cn", ".jp", ".tw"]):
        return True
    return False



# ═══════════════════════════════════════════════════
# ★ 신규: 한국 연예계 연관성 필터
#   통과 조건(하나라도 충족):
#     A) 제목·본문에 한글이 포함된 경우
#     B) K-pop / K-drama / Korean 등 핵심 키워드 포함
#     C) 한국 기반 언론사 URL
#   차단 조건:
#     - 한국 관련 키워드 전혀 없고 순수 해외 셀럽 키워드만 존재

