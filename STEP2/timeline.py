"""
timeline.py — 네이버 뉴스 API + LLM으로 6개월 타임라인 생성
실행: python timeline.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import ollama
from database import SessionLocal, ProcessedNews

# ── 아티스트 이름 정규화 매핑 ──
ARTIST_MAP = {
    "babymonster": "베이비몬스터", "baby monster": "베이비몬스터", "베이비 몬스터": "베이비몬스터", "baemon": "베이비몬스터",
    "blackpink": "블랙핑크", "black pink": "블랙핑크", "블랙 핑크": "블랙핑크",
    "newjeans": "뉴진스", "new jeans": "뉴진스", "뉴 진스": "뉴진스",
    "bts": "방탄소년단", "bangtan": "방탄소년단", "방탄": "방탄소년단",
    "aespa": "에스파", "ive": "아이브", "lesserafim": "르세라핌", "le sserafim": "르세라핌",
    "straykids": "스트레이 키즈", "stray kids": "스트레이 키즈",
    "seventeen": "세븐틴", "twice": "트와이스",
}

def normalize_artist(name: str) -> str:
    if not name or not isinstance(name, str):
        return ""
    clean_name = name.lower().replace(" ", "").strip()
    for k, v in ARTIST_MAP.items():
        if k.replace(" ", "") == clean_name:
            return v
    return name.strip()

def _parse_json(val):
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        # 이중 인코딩 처리
        result = val
        for _ in range(3):
            if isinstance(result, list):
                return result
            if isinstance(result, str):
                result = json.loads(result)
        return result if isinstance(result, list) else []
    except:
        return []

def fetch_top_news():
    import sqlite3 as _sqlite3
    _ROOT = Path(__file__).resolve().parent.parent
    conn = _sqlite3.connect(str(_ROOT / "k_enter_news.db"))
    conn.row_factory = _sqlite3.Row
    cursor = conn.cursor()

    cat_limits = {"컨텐츠 & 작품": 30, "인물 & 아티스트": 30, "비즈니스 & 행사": 30}
    raw_rows = []
    for category, limit in cat_limits.items():
        cursor.execute(
            "SELECT id, category, sub_category, ko_title, artist_tags, keywords, importance "
            "FROM processed_news WHERE importance IS NOT NULL AND category = ? "
            "ORDER BY importance DESC, id DESC LIMIT ?",
            (category, limit)
        )
        raw_rows.extend(cursor.fetchall())
    conn.close()
    print(f"raw_rows 총 개수: {len(raw_rows)}")
    for r in raw_rows[:5]:
        print(f"  id={r['id']} cat={r['category']} imp={r['importance']} artist={r['artist_tags'][:50]}")

    seen_artists = set()
    final_list = []
    remained = []

    for category in cat_limits.keys():
        cat_count = 0
        cat_rows = [r for r in raw_rows if r["category"] == category]
        for row in cat_rows:
            tags = _parse_json(row["artist_tags"])
            norm_tags = [normalize_artist(t) for t in tags if isinstance(t, str)]
            primary_artist = next((t for t in norm_tags if t and t.strip()), None)
            is_dup = primary_artist and primary_artist in seen_artists

            news_obj = {
                "id": row["id"],
                "title": row["ko_title"] or "",
                "artist_tags": norm_tags,
                "keywords": _parse_json(row["keywords"]),
                "importance": row["importance"],
                "category": row["category"] or "",
                "sub_category": row["sub_category"] or "",
            }

            if not is_dup and cat_count < 4:
                if primary_artist:
                    seen_artists.add(primary_artist)
                final_list.append(news_obj)
                cat_count += 1
            else:
                remained.append(news_obj)

    if len(final_list) < 10:
        remained = sorted(remained, key=lambda x: x["importance"], reverse=True)
        for news in remained:
            primary_artist = news["artist_tags"][0] if news["artist_tags"] else None
            if primary_artist and primary_artist in seen_artists:
                continue
            if primary_artist:
                seen_artists.add(primary_artist)
            final_list.append(news)
            if len(final_list) >= 10:
                break

    return sorted(final_list, key=lambda x: x["importance"], reverse=True)

load_dotenv()

# ===================== CONFIG =====================
OLLAMA_MODEL = "gemma3:latest"
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"

def search_naver_news(query: str, display: int = 10) -> list:
    """네이버 뉴스 API로 검색"""
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {
        "query": query,
        "display": display,
        "sort": "date",  # 최신순
    }
    try:
        response = requests.get(NAVER_NEWS_URL, headers=headers, params=params)
        response.raise_for_status()
        items = response.json().get("items", [])
        return items
    except Exception as e:
        print(f"  ❌ 네이버 검색 실패 ({query}): {e}")
        return []


def clean_html(text: str) -> str:
    """HTML 태그 제거"""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


def generate_timeline(title: str, artist_tags: list, keywords: list, news_items: list) -> list:
    """네이버 뉴스 날짜 직접 사용 + LLM으로 이벤트 텍스트만 생성"""

    artists = ", ".join(artist_tags) if artist_tags else "없음"
    kw = ", ".join(keywords) if keywords else "없음"

    timeline = []
    seen_dates = set() 

    for item in news_items[:6]:
        pub_date = item.get("pubDate", "")
        try:
            date_obj = datetime.strptime(pub_date[:16], "%a, %d %b %Y")
            date_str = date_obj.strftime("%Y-%m-%d")
        except Exception:
            continue

        #if date_str < "2025-11":
        #    continue

        if date_str in seen_dates:
            continue
        seen_dates.add(date_str)

        news_title = clean_html(item.get("title", ""))
        news_desc = clean_html(item.get("description", ""))

        prompt = f"""
        다음 뉴스의 핵심 이벤트를 한국어 20자 이내로 구체적으로 요약하고,
        감정을 positive, neutral, negative 중 하나로 판단하세요.

        반드시 아래 형식으로만 출력하세요:
        요약|감정

        예시:
        컴백발표|positive
        논란확산|negative

        뉴스 제목: {news_title}
        뉴스 내용: {news_desc[:200]}
        """

        try:
            response = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}]
            )

            result = response["message"]["content"].strip()

            if "|" in result:
                event, sentiment = result.split("|", 1)
                event = event.strip()
                sentiment = sentiment.strip().lower()
            else:
                event = news_title[:10]
                sentiment = "neutral"

            if sentiment not in ["positive", "neutral", "negative"]:
                sentiment = "neutral"

        except Exception:
            event = news_title[:10]
            sentiment = "neutral"

        timeline.append({"date": date_str, "event": event, "sentiment": sentiment, "url": item.get("originallink", "") or item.get("link", "")})

    timeline.sort(key=lambda x: x.get("date", ""), reverse=True)
    return timeline


def save_timeline(news_id: int, timeline: list):
    """timeline 컬럼에 저장"""
    import sqlite3 as _sqlite3
    _ROOT = Path(__file__).resolve().parent.parent
    conn = _sqlite3.connect(str(_ROOT / "k_enter_news.db"))
    try:
        conn.execute(
            "UPDATE processed_news SET timeline = ? WHERE id = ?",
            (json.dumps(timeline, ensure_ascii=False), news_id)
        )
        conn.commit()
    except Exception as e:
        print(f"  timeline DB 저장 실패: {e}")
    finally:
        conn.close()

def main():
    print("🗓️  타임라인 생성 시작\n" + "="*50)

    top_news_list = fetch_top_news()

    for i, news in enumerate(top_news_list):
        print(f"\n{i+1}위. [{news['category']}][중요도:{news['importance']}] {news['title']}")

        # artist_tags + keywords 합쳐서 검색 쿼리 구성
        artists = news["artist_tags"] if isinstance(news["artist_tags"], list) else []
        keywords = news["keywords"] if isinstance(news["keywords"], list) else []
        norm_artists = [a for a in artists if a in ARTIST_MAP.values()]
        query = " ".join(norm_artists[:3] if norm_artists else (artists[:2] + keywords[:3]))
        #query = " ".join(artists[:3] + keywords[:2])  # 너무 길면 검색 품질 저하

        print(f"  🔍 네이버 검색 쿼리: {query}")
        news_items = search_naver_news(query, display=30)
        print(f"  📰 검색 결과: {len(news_items)}건")

        if not news_items:
            print(f"  ⚠️  검색 결과 없음, 스킵")
            continue

        timeline = generate_timeline(
            title=news["title"],
            artist_tags=artists,
            keywords=keywords,
            news_items=news_items
        )

        if timeline:
            save_timeline(news["id"], timeline)
            print(f"  ✅ 타임라인 저장 완료 ({len(timeline)}개 항목)")
            for item in timeline:
                print(f"     {item.get('date')} → {item.get('event')}")
        else:
            print(f"  ⚠️  타임라인 생성 실패")

    print("\n" + "="*50)
    print("✅ 타임라인 생성 완료!")


if __name__ == "__main__":
    main()
