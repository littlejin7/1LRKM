"""
crawler1.py — 전체 카테고리(컨텐츠, 인물, 비즈니스) 통합 크롤러

1. 모든 카테고리(컨텐츠 & 작품 포함) 유지
2. 본문 최소 글자 수 500자
3. raw_artist_hint 필드 추가:
   - 제목+본문에서 사람 이름으로 보이는 패턴을 정규식으로 추출
   - processor.py가 이를 참고하여 배우/가수가 아닌 메인 인물도 artist_tags에 포함
"""

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


# ═══════════════════════════════════════════════════
# 설정값
# ═══════════════════════════════════════════════════


def _env_int(name: str, default: int) -> int:
    v = (os.getenv(name) or "").strip()
    try:
        return int(v) if v else default
    except Exception:
        return default


RAW_CONTENT_MAX_CHARS = _env_int("RAW_CONTENT_MAX_CHARS", 8000)
TAVILY_MAX_RESULTS = 100  # ★ 수집 극대화: 100건 (Tavily 최대치)
MAX_PER_DOMAIN = max(1, _env_int("CRAWL_MAX_PER_DOMAIN", 10))
TAVILY_RETRY = 2
LOOKBACK_DAYS = 7  # ★ 최근 1주일 범위
RSS_MAX_TOTAL = 9999  # ★ RSS 무제한 (피드가 제공하는 최대치)

# ★ 최소 본문 길이: 일반 200자, RSS 50자
MIN_CONTENT_LEN = 200
RSS_MIN_CONTENT_LEN = 50


# ═══════════════════════════════════════════════════
# 수집 대상 카테고리
# ═══════════════════════════════════════════════════

CATEGORY_MAPPING = {
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


def get_standard_category(sub_name: str) -> tuple[str, str]:
    category = CATEGORY_MAPPING.get(sub_name, "비즈니스 & 행사")
    return category, sub_name


# ═══════════════════════════════════════════════════
# 본문 정제
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


def clean_content(text: str, min_len: int = MIN_CONTENT_LEN) -> str:
    """광고·불필요 텍스트 제거 후 정제. ★ 최소 길이 미달 시 빈 문자열 반환."""
    if not text:
        return text
    for pat in _NOISE_PATTERNS:
        text = pat.sub("", text)

    lines = [line.strip() for line in text.split("\n") if len(line.strip()) >= 20]
    cleaned = re.sub(r"\n{2,}", "\n", "\n".join(lines)).strip()

    if len(cleaned) < min_len:
        return ""

    return cleaned





# ═══════════════════════════════════════════════════
# ★ 신규: 인물 힌트 추출
#   - 제목·본문에서 한국어 이름(2~4자 한글) 또는
#     영문 대문자 시작 단어 연속(로마자 예명/영어 이름)을 추출
#   - processor.py의 artist_tags 생성 시 참고용 힌트로만 사용
# ═══════════════════════════════════════════════════

# 한국어 키워드/이름: 한글 + 숫자 + '+' 기호 포함 (디즈니+, 넷플릭스, NCT127 등 대응)
_KO_NAME_RE = re.compile(r"[가-힣0-9\+]{2,10}")
# 영문 예명/이름: 2개 이상 대문자 시작 단어, ex) BTS Jungkook / BLACKPINK Jennie
_EN_NAME_RE = re.compile(r"\b[A-Z][a-zA-Z0-9\+]+(?:\s[A-Z][a-zA-Z0-9\+]+)+\b")

# 기사에서 걸러낼 일반 명사 (제목에 자주 나오는 비인물 단어)
_KO_STOPWORDS = {
    "관련", "기사", "뉴스", "사진", "영상", "공개", "발표", "확인", "인터뷰", "논란",
    "이슈", "업계", "기획사", "엔터", "매니저", "소속사", "방송", "드라마", "영화", "예능",
    "콘서트", "팬미팅", "컴백", "앨범", "노래", "음악", "차트", "1위", "기록", "데뷔",
    "오늘", "어제", "내일", "최근", "현재", "진행", "예정", "계획", "준비", "모습",
    "분위기", "현장", "무대", "활동", "참여", "출연", "소식", "정보", "기대", "응원",
    "성공", "결과", "이후", "이전", "동안", "때문", "관심", "인기", "다양", "가능",
    "시작", "마무리", "결정", "선정", "발탁", "광고", "모델", "화보", "잡지", "표지",
    "글로벌", "국내", "해외", "세계", "미국", "일본", "중국", "유럽", "빌보드", "멜론",
    "우리", "모두", "함께", "진짜", "정말", "매우", "가장", "최고", "최초", "역대",
    "하나", "사람", "대중", "스타", "아이돌", "배우", "가수", "감독", "작가", "피디",
    "현지", "반응", "상태", "상황", "이유", "목적", "방향", "미래", "과거", "생각",
    "마음", "사랑", "행복", "열정", "눈물", "웃음", "감동", "재미", "매력", "개성",
}





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
# ═══════════════════════════════════════════════════

# 한글 문자 포함 여부
_HAS_HANGUL = re.compile(r"[가-힣]")

# K-엔터 연관 영문 키워드 (제목·본문에 하나라도 있으면 통과)
_K_ENT_KEYWORDS = re.compile(
    r"\b(K-?pop|K-?drama|K-?ent|Korean|\bkpop\b|한류|연예"
    r"|아이돌|idol|Hallyu|Seoul|한국|HYBE|하이브"
    r"|SM Entertainment|JYP|YG|Starship|PLEDIS|CUBE"
    r"|Koreaboo|Soompi|allkpop)\b",
    re.IGNORECASE,
)

# 순수 해외(비K엔터) 임을 강하게 시사하는 키워드
# → 이 단어들이 있어도 K-엔터 키워드가 함께 있으면 통과됨
_FOREIGN_ONLY_KEYWORDS = re.compile(
    r"\b(Hollywood|Grammy|Oscar|Emmy|Billboard 200"
    r"|NBA|NFL|MLB|FIFA|Premier League"
    r"|Taylor Swift|Beyoncé|Beyonce|Drake|Rihanna"
    r"|Ariana Grande|Lady Gaga|Justin Bieber|Selena Gomez"
    r"|Harry Styles|Ed Sheeran|Billie Eilish|Olivia Rodrigo"
    r"|White House|Congress|NATO|EU Parliament)\b",
    re.IGNORECASE,
)

# 한국 뉴스 도메인 (이 도메인에서 온 기사는 무조건 통과)
_KOREAN_NEWS_DOMAINS = re.compile(
    r"(dispatch\.co\.kr|starnewskorea\.com|xportsnews\.com"
    r"|newsen\.com|imbc\.com|sbs\.co\.kr|kbs\.co\.kr"
    r"|ytn\.co\.kr|mbn\.co\.kr|yna\.co\.kr"
    r"|news\.naver\.com|news\.daum\.net"
    r"|donga\.com|joongang\.co\.kr|hankyung\.com"
    r"|edaily\.co\.kr|mk\.co\.kr|koreaherald\.com"
    r"|koreatimes\.co\.kr|koreajoongangdaily\.joins\.com)",
    re.IGNORECASE,
)


# ═══════════════════════════════════════════════════
# 아티스트 힌트 추출
# ═══════════════════════════════════════════════════

_KO_STOPWORDS = {
    "기자", "뉴스", "연예", "기사", "오늘", "내일", "이번", "지난", "어제", "내용",
    "이후", "과거", "현재", "사실", "관련", "대해", "통해", "위해", "대한", "때문",
    "가운데", "지난해", "올해", "내년", "오전", "오후", "최근", "하루", "이날", "이후",
    "스타", "연예인", "가수", "배우", "아이돌", "그룹", "팬덤", "무대", "공연", "콘서트",
    "앨범", "차트", "컴백", "데뷔", "활동", "소식", "작품", "드라마", "영화", "예능",
    "장면", "사람", "하나", "모습", "생각", "이야기", "정도", "부분", "상태", "경우",
    "시작", "진행", "예정", "준비", "확인", "발표", "공개", "참여", "함께", "진심",
    "사랑", "응원", "기대", "감동", "화제", "눈길", "인기", "관심", "매력", "분위기",
    "세계", "글로벌", "해외", "국내", "한국", "문화", "산업", "시장", "현장", "지역"
}

def extract_person_hint(title: str, content: str) -> str:
    """
    제목과 본문 앞부분에서 인물 이름이나 주요 키워드(2~10자)를 추출하여
    가공 단계에서 참고할 수 있도록 힌트를 생성합니다.
    """
    import collections
    combined = f"{title} {content[:1000]}"
    
    # 상단 정의된 정규식 사용 (디즈니+, NCT127 등 지원)
    en_names = _EN_NAME_RE.findall(combined)
    ko_keywords = _KO_NAME_RE.findall(combined)
    
    filtered_ko = [k for k in ko_keywords if k not in _KO_STOPWORDS]
    
    # 빈도수 순으로 상위 10개 추출
    counts = collections.Counter(en_names + filtered_ko)
    top_hints = [item[0] for item in counts.most_common(10)]
    
    return ", ".join(top_hints) if top_hints else ""


def is_korean_ent(title: str, content: str, url: str = "") -> bool:
    """
    해당 기사가 한국 연예계(또는 한국에서 활동하는 외국인) 관련인지 판단.
    - True  → 수집 대상
    - False → 순수 해외 셀럽/비K엔터 기사로 판단, 수집 제외

    판단 순서:
    1. 한국 언론사 도메인 → 무조건 통과
    2. 제목+본문에 한글 존재 → 통과
    3. K-엔터 키워드 존재 → 통과
    4. 순수 해외 키워드만 있고 K-엔터 키워드 없음 → 차단
    5. 그 외(판단 불가) → 통과(보수적)
    """
    # 1. 한국 언론사 URL이면 무조건 통과
    if _KOREAN_NEWS_DOMAINS.search(url or ""):
        return True

    sample = f"{title} {content[:800]}"

    # 2. 한글 포함 → 통과
    if _HAS_HANGUL.search(sample):
        return True

    # 3. K-엔터 영문 키워드 → 통과
    if _K_ENT_KEYWORDS.search(sample):
        return True

    # 4. 순수 해외 키워드만 있고 K-엔터 연관 없음 → 차단
    if _FOREIGN_ONLY_KEYWORDS.search(sample):
        return False

    # 5. 판단 불가 → 보수적으로 통과
    return True


# ═══════════════════════════════════════════════════
# 유틸
# ═══════════════════════════════════════════════════


def parse_date(date_string: str) -> datetime | None:
    if not date_string:
        return None
    try:
        return parsedate_to_datetime(date_string)
    except Exception:
        return None


def extract_date_from_text(text: str, url: str) -> datetime | None:
    """URL이나 본문 텍스트에서 '기사 발행일' 패턴을 정교하게 추출합니다."""
    # 1. URL 패턴 (가장 정확함)
    # /2024/03/15/ 또는 /2024-03-15/ 또는 /20240315/ 등
    url_matches = [
        re.search(r"/(\d{4})[./-]([01]?\d)[./-]([0-3]?\d)", url),
        re.search(r"/(\d{4})(\d{2})(\d{2})/", url),
        re.search(r"(_|-)(\d{4})(\d{2})(\d{2})", url),
    ]
    for m in url_matches:
        if m:
            try:
                # 그룹 인덱스가 패턴마다 다를 수 있으므로 유동적 처리
                groups = [g for g in m.groups() if g and g.isdigit()]
                if len(groups) >= 3:
                    return datetime(int(groups[0]), int(groups[1]), int(groups[2]))
            except Exception:
                continue

    # 2. 메타 태그 검색 (Tavily raw_content에 HTML이 포함된 경우)
    # <meta property="article:published_time" content="2025-09-27T00:01:00+09:00" />
    meta_match = re.search(r'property="(?:article:published_time|published_date|og:pubdate)"\s+content="(\d{4}-\d{2}-\d{2})', text)
    if not meta_match:
        # 순서가 바뀐 경우 대응: content="2025-09-27..." property="..."
        meta_match = re.search(r'content="(\d{4}-\d{2}-\d{2}).*?property="(?:article:published_time|published_date|og:pubdate)"', text)
    
    if meta_match:
        try:
            return datetime.strptime(meta_match.group(1), "%Y-%m-%d")
        except Exception:
            pass

    # 3. 본문 전체 검색 (일부 사이트는 날짜가 하단에 있음)
    # 한국어 기사입력 패턴 (입력, 기사입력, 등록, 수정, 발행, 일시 등)
    ko_match = re.search(
        r"(?:입력|기사입력|등록|수정|발행|일시|날짜|발행일)\s*[:]?\s*(\d{4})[./-]([01]?\d)[./-]([0-3]?\d)",
        text,
    )
    if ko_match:
        try:
            return datetime(int(ko_match.group(1)), int(ko_match.group(2)), int(ko_match.group(3)))
        except Exception:
            pass

    # 4. 영문 발행일 패턴 (전체 본문 대상)
    months = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December"
    mon_dict = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
    
    # 패턴 A: 일(서수 포함) 월 년 (ex: 7th April 2026, By ... 7 April 2026)
    en_match_a = re.search(fr"(?:Published|Updated|Posted|Date|First published|By).*?(\d{{1,2}})(?:st|nd|rd|th)?\s+({months})\.?\s+(\d{{4}})", text, re.IGNORECASE | re.DOTALL)
    if en_match_a:
        try:
            mon_str = en_match_a.group(2)[:3].capitalize()
            return datetime(int(en_match_a.group(3)), mon_dict[mon_str], int(en_match_a.group(1)))
        except Exception:
            pass

    # 패턴 B: 월 일(서수 포함), 년 (ex: April 7th, 2026)
    en_match_b = re.search(fr"(?:Published|Updated|Posted|Date|First published|By).*?({months})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", text, re.IGNORECASE | re.DOTALL)
    if en_match_b:
        try:
            mon_str = en_match_b.group(1)[:3].capitalize()
            return datetime(int(en_match_b.group(3)), mon_dict[mon_str], int(en_match_b.group(2)))
        except Exception:
            pass

    # 5. 최후의 보루: 단순 날짜 패턴
    lines = text.split("\n")
    check_text = "\n".join(lines[:10] + lines[-10:])
    simple_match = re.search(r"(\d{4})[./-]([01]?\d)[./-]([0-3]?\d)", check_text)
    if simple_match:
        try:
            return datetime(int(simple_match.group(1)), int(simple_match.group(2)), int(simple_match.group(3)))
        except Exception:
            pass

    return None


def is_within_lookback(published_at: datetime | None) -> bool:
    if not published_at:
        return False
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    return published_at >= cutoff


# ═══════════════════════════════════════════════════
# 수집 함수
# ═══════════════════════════════════════════════════


def fetch_news_from_rss() -> list[dict]:
    all_news: list[dict] = []
    seen_urls: set[str] = set()

    for sub_target, feeds in RSS_FEEDS.items():
        # ★ 전체 합산 30건 초과 시 중단
        if len(all_news) >= RSS_MAX_TOTAL:
            break

        category, sub_category = get_standard_category(sub_target)

        for feed_url in feeds:
            if len(all_news) >= RSS_MAX_TOTAL:
                break
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    if len(all_news) >= RSS_MAX_TOTAL:
                        break
                    url = entry.get("link", "")
                    if not url or url in seen_urls:
                        continue
                    # ★ 블로그 URL 필터
                    if is_blog_url(url):
                        log.debug(f"[RSS 블로그 제외] {url}")
                        continue
                    seen_urls.add(url)

                    pub_at = parse_date(entry.get("published"))
                    if pub_at and not is_within_lookback(pub_at):
                        continue

                    raw_summary = entry.get("summary", "") or ""
                    content = clean_content(re.sub(r"<[^>]+>", " ", raw_summary), min_len=RSS_MIN_CONTENT_LEN)
                    if not content:
                        continue

                    title = entry.get("title", "")

                    # ★ 한국 연예계 비연관 기사 제외
                    if not is_korean_ent(title, content, url):
                        log.debug(f"[RSS 비K엔터 제외] {title[:40]}")
                        continue

                    # 기간 필터링 강화: 날짜가 없거나 기간 밖이면 스킵
                    if not is_within_lookback(pub_at):
                        continue

                    all_news.append(
                        {
                            "title": title,
                            "content": content,
                            "url": url,
                            "published_at": pub_at,
                            "crawled_at": datetime.now(),
                            "is_processed": False,
                            "category": category,
                            "sub_category": sub_category,
                            "raw_artist_hint": extract_person_hint(title, content),
                        }
                    )
            except Exception as e:
                log.error(f"[RSS 오류] {feed_url}: {e}")

    return all_news


def fetch_news_from_tavily(query: str, label: str = "Unknown") -> list[dict]:
    from tavily import TavilyClient

    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    category, sub_category = get_standard_category(label)

    for attempt in range(TAVILY_RETRY + 1):
        try:
            response = client.search(
                query=query,
                search_depth="advanced",
                topic="general",
                days=LOOKBACK_DAYS,
                max_results=TAVILY_MAX_RESULTS,
                include_raw_content=True,
                include_domains=INCLUDE_DOMAINS, # ★ 공신력 있는 도메인으로 다시 제한
                exclude_domains=EXCLUDE_DOMAINS,  # ★ 블로그 차단
            )
            results: list[dict] = []
            for item in response.get("results", []):
                # ★ 블로그 URL 이중 필터 (Tavily가 exclude_domains를 완전히 보장 못할 때 대비)
                if is_blog_url(item.get("url", "")):
                    log.debug(f"[Tavily 블로그 제외] {item.get('url')}")
                    continue

                # 1. 기본 정보 및 본문 정제
                raw_text = item.get("raw_content") or item.get("content", "")
                content = clean_content(raw_text)
                if not content:
                    continue
                title = item.get("title", "")

                # 2. 날짜 확보 (API 우선 -> 없으면 URL/본문에서 추출)
                pub_at = parse_date(item.get("published_date"))
                if not pub_at:
                    pub_at = extract_date_from_text(raw_text, item.get("url", ""))

                # 3. [핵심] 모든 방법으로 찾은 날짜에 대해 '60일 범위' 검증
                if pub_at and not is_within_lookback(pub_at):
                    log.debug(f"[기간 만료 스킵] {pub_at} - {item.get('url')}")
                    continue

                # ★ 한국 연예계 비연관 기사 제외
                if not is_korean_ent(title, content, item.get("url", "")):
                    log.debug(f"[Tavily 비K엔터 제외] {title[:40]}")
                    continue

                results.append(
                    {
                        "title": title,
                        "content": content[:RAW_CONTENT_MAX_CHARS],
                        "url": item.get("url", ""),
                        "published_at": pub_at,
                        "crawled_at": datetime.now(),
                        "is_processed": False,
                        "category": category,
                        "sub_category": sub_category,
                        # ★ 신규: 인물 힌트
                        "raw_artist_hint": extract_person_hint(title, raw_text),
                    }
                )
            return results
        except Exception as e:
            if attempt < TAVILY_RETRY:
                time.sleep(2)
            else:
                log.error(f"[Tavily 최종 실패] {query}: {e}")
    return []


# ═══════════════════════════════════════════════════
# 저장 함수
# ═══════════════════════════════════════════════════


def is_junk_news(title: str, content: str, url: str = "") -> bool:
    """
    기사 본문이 아닌 네비게이션 메뉴, 포털 메인 페이지, 검색 결과,
    혹은 본문 추출에 실패한 쓰레기 데이터를 감지합니다.
    """
    t = (title or "").strip()
    c = (content or "").strip()
    u = (url or "").strip().lower()

    # 1. URL 기반 필터링 (검색 결과, 목록 페이지, PDF 등)
    if any(
        p in u
        for p in [
            "/search/",
            "query=",
            "collection=",
            "list.do",
            "newslist",
            "searchresult",
            "allsearch",
            "page=",
            "index_",
            "/films",
            "/lifestyle",
            "sitemap",
            "latest-articles",
            "/latest/",
            "/archive/",
            "category/",
            "/all-news/",
            "/trending/",
        ]
    ):
        return True
    if u.endswith(".pdf") or ".pdf?" in u:
        return True

    # 2. 본문이 너무 짧은 경우 (추출 실패)
    if len(c) < 150: # Junk 필터 기준도 150자로 완화 (RSS 고려)
        return True

    # 3. 제목이 포털이나 방송사 이름 그 자체이거나 검색 결과인 경우
    junk_titles = [
        "kbs",
        "sbs",
        "sbs연예",
        "daum",
        "mbc",
        "jtbc",
        "네이버",
        "naver",
        "daum | 문화",
        "search results",
        "검색결과",
        "목록",
        "메뉴",
        "index of",
        "찾기",
        "highlights",
        "preview",
        "films",
        "xml",
    ]
    t_lower = t.lower()
    if any(jt == t_lower for jt in junk_titles):  # 정확히 일치하는 경우
        return True

    # 제목에 "검색", "목록", "하이라이트", "논평/칼럼" 등이 포함된 특정 패턴
    if any(
        kw.lower() in t_lower
        for kw in [
            "검색 - ", " - 검색", "목록 | ", " | 목록", "검색결과 :", 
            "highlights", "preview", "roundup", "[xml]",
            "[논평]", "[사설]", "[기자수첩]", "[칼럼]", "[데스크칼럼]", "[시론]", "[기고]",
            "editorial", "opinion", "column", "commentary", "perspectives"
        ]
    ):
        return True

    # 4. 링크 밀도가 너무 높은 경우 (메뉴판/목록페이지)
    # Tavily 등에서 [text](url) 형태로 올 때를 대비
    links = re.findall(r"\[.*?\]\(.*?\)", c)
    if len(c) > 0:
        links_len = sum(len(m) for m in links)
        # 본문의 40% 이상이 링크 문법이거나, 링크 개수가 25개 이상이면 메뉴판 (기준 강화)
        if (links_len / len(c)) > 0.40 or len(links) > 25:
            return True

    # 5. 목록형 페이지(Navigator) 감지: 헤더(#, ##)가 너무 많으면 리스트임
    headers = re.findall(r"^#{1,3} .*$", c, re.MULTILINE)
    if len(headers) >= 4:
        # 헤더당 평균 본문 길이가 400자 미만이면 기사 목록으로 판단 (기준 강화)
        if len(c) / len(headers) < 400:
            return True

    # 6. 네비게이션용 특정 키워드가 너무 많은 경우
    nav_keywords = [
        "바로가기",
        "GNB",
        "LNB",
        "검색창",
        "로그인",
        "About KBS",
        "RSS",
        "TikTok",
        "YouTube",
        "Copyright",
        "All rights reserved",
        "회원가입",
        "마이페이지",
        "고객센터",
        "이용약관",
        "개인정보처리방침",
        "Contact Us",
        "Privacy Policy",
        "Terms of Service",
        "로그아웃",
    ]
    match_count = sum(1 for kw in nav_keywords if kw in c)
    if match_count >= 3:
        return True

    return False


def save_raw_news(session, news_list: list[dict]) -> int:
    """
    raw_artist_hint는 RawNews 테이블에 별도 컬럼이 없으므로
    저장 전에 제거하고, 필요 시 processor.py에서 참조할 수 있도록
    content 맨 앞에 주석 형태로 삽입한다.

    ── 사용 방법 ──
    processor.py의 process_single()에서 raw.content 앞 줄을 파싱하여
    artist_tags를 초기화하는 데 활용하면 됨.
    예) if raw.content.startswith("[ARTIST_HINT]"):
            hint_line, *rest = raw.content.split("\\n", 1)
            artist_hint = hint_line.replace("[ARTIST_HINT]", "").strip()
    """
    if not news_list:
        return 0
    saved_count = 0

    for news in news_list:
        try:
            exists = session.query(RawNews).filter(RawNews.url == news["url"]).first()
            if exists:
                continue

            # ★ 불량 데이터(메인 페이지, 메뉴판 등) 필터링
            if is_junk_news(news.get("title"), news.get("content"), news.get("url")):
                continue

            # ★ raw_artist_hint를 content 앞에 태그로 삽입 (DB 컬럼 추가 없이 전달)
            hint = (news.pop("raw_artist_hint", "") or "").strip()
            if hint:
                news["content"] = f"[ARTIST_HINT]{hint}\n{news['content']}"

            raw = RawNews(
                title=news["title"],
                content=news["content"],
                url=news["url"],
                published_at=news["published_at"],
                crawled_at=news["crawled_at"],
                is_processed=news["is_processed"],
                category=news["category"],
                sub_category=news["sub_category"],
            )
            session.add(raw)
            session.commit()
            saved_count += 1

        except Exception as e:
            session.rollback()
            log.error(f"[저장 실패] {news.get('url', '?')}: {e}")

    return saved_count


# ═══════════════════════════════════════════════════
# 메인 파이프라인
# ═══════════════════════════════════════════════════


def crawl_and_save():
    """크롤러1 메인 파이프라인"""
    with get_session() as session:
        log.info("=== crawler1 시작 (전체 카테고리, 최소 300자) ===")

        log.info("[1단계] RSS 수집 시작")
        rss_news = fetch_news_from_rss()
        log.info(f"  → RSS 수집: {len(rss_news)}건")
        saved_rss = save_raw_news(session, rss_news)
        log.info(f"  → RSS 저장: {saved_rss}건 신규")

        log.info("[2단계] Tavily API 수집 시작")
        for label, query in DEFAULT_QUERIES.items():
            log.info(f"  → [{label}] 쿼리 실행 중...")
            tav_news = fetch_news_from_tavily(query, label=label)
            log.info(f"    - {len(tav_news)}건 수집")
            saved_tav = save_raw_news(session, tav_news)
            log.info(f"    - {saved_tav}건 신규 저장")

        log.info("✅ crawler1 완료")


if __name__ == "__main__":
    crawl_and_save()
