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

load_dotenv()

# ===================== CONFIG =====================
OLLAMA_MODEL = "gemma3:latest"
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"

category_limits = {
    "컨텐츠 & 작품": 4,
    "인물 & 아티스트": 4,
    "비즈니스 & 행사": 4,
}
# ==================================================


def fetch_top_news():
    """카테고리별 Top 10 뉴스 추출"""
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect("k_enter_news.db")
    conn.row_factory = _sqlite3.Row
    cursor = conn.cursor()

    rows = []
    for category, limit in category_limits.items():
        cursor.execute(
            "SELECT id, category, ko_title, artist_tags, keywords, importance"
            " FROM processed_news"
            " WHERE importance IS NOT NULL AND category = ?"
            " ORDER BY importance DESC, id DESC LIMIT ?",
            (category, limit)
        )
        rows.extend(cursor.fetchall())

    conn.close()

    rows = sorted(rows, key=lambda x: (x["importance"], x["id"]), reverse=True)

    top_news_list = []
    for row in rows:
        artist_tags = json.loads(row["artist_tags"]) if row["artist_tags"] and isinstance(row["artist_tags"], str) else (row["artist_tags"] or [])
        keywords = json.loads(row["keywords"]) if row["keywords"] and isinstance(row["keywords"], str) else (row["keywords"] or [])
        top_news_list.append({
            "id": row["id"],
            "title": row["ko_title"] or "",
            "artist_tags": artist_tags,
            "keywords": keywords,
            "importance": row["importance"],
            "category": row["category"] or "",
        })
    return top_news_list


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

    for item in news_items[:15]:
        pub_date = item.get("pubDate", "")
        try:
            date_obj = datetime.strptime(pub_date[:16], "%a, %d %b %Y")
            date_str = date_obj.strftime("%Y-%m-%d")
        except Exception:
            continue

        if not date_str.startswith("2026"):
            continue

        if date_str in seen_dates:
            continue
        seen_dates.add(date_str)

        news_title = clean_html(item.get("title", ""))
        news_desc = clean_html(item.get("description", ""))

        prompt = f"""
        다음 뉴스의 핵심 이벤트를 한국어 10자 이내로 요약하고,
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

        timeline.append({"date": date_str, "event": event,"sentiment": sentiment })

    timeline.sort(key=lambda x: x.get("date", ""), reverse=True)
    return timeline


def save_timeline(news_id: int, timeline: list):
    """timeline 컬럼에 저장"""
    session = SessionLocal()
    try:
        row = session.query(ProcessedNews).filter(ProcessedNews.id == news_id).first()
        if row:
            row.timeline = timeline
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"  ❌ timeline DB 저장 실패: {e}")
    finally:
        session.close()

def main():
    print("🗓️  타임라인 생성 시작\n" + "="*50)

    top_news_list = fetch_top_news()
    print(f"📰 Top {len(top_news_list)}개 뉴스 추출 완료\n")

    for i, news in enumerate(top_news_list):
        print(f"\n{i+1}위. [{news['category']}][중요도:{news['importance']}] {news['title']}")

        # artist_tags + keywords 합쳐서 검색 쿼리 구성
        artists = news["artist_tags"] if isinstance(news["artist_tags"], list) else []
        keywords = news["keywords"] if isinstance(news["keywords"], list) else []
        query = " ".join(artists[:2] + keywords[:3])  # 너무 길면 검색 품질 저하

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
