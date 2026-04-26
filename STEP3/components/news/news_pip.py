import sqlite3
import json
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from STEP2.rag_search import build_graph, NewsState
from database import SessionLocal, ProcessedNews

# ── 아티스트 이름 정규화 매핑 ──────────────────────────────────────────────────
ARTIST_MAP = {
    "babymonster": "베이비몬스터",
    "baby monster": "베이비몬스터",
    "베이비 몬스터": "베이비몬스터",
    "baemon": "베이비몬스터",
    "blackpink": "블랙핑크",
    "black pink": "블랙핑크",
    "블랙 핑크": "블랙핑크",
    "newjeans": "뉴진스",
    "new jeans": "뉴진스",
    "뉴 진스": "뉴진스",
    "bts": "방탄소년단",
    "bangtan": "방탄소년단",
    "방탄": "방탄소년단",
    "aespa": "에스파",
    "ive": "아이브",
    "lesserafim": "르세라핌",
    "le sserafim": "르세라핌",
    "straykids": "스트레이 키즈",
    "stray kids": "스트레이 키즈",
    "seventeen": "세븐틴",
    "twice": "트와이스",
    "iu": "아이유",
    "plave": "플레이브"
}

def normalize_artist(name: str) -> str:
    if not name or not isinstance(name, str):
        return ""
    clean_name = name.lower().replace(" ", "").strip()
    for k, v in ARTIST_MAP.items():
        if k.replace(" ", "") == clean_name:
            return v
    return name.strip()

def parse_json(val):
    if not val:
        return []
    if isinstance(val, list):
        return val
    current = val
    for _ in range(3):
        if not isinstance(current, str):
            break
        try:
            cleaned = current.strip()
            if cleaned.startswith("'") or "[ '" in cleaned:
                cleaned = cleaned.replace("'", '"')
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return parsed
            current = parsed
        except:
            break
    if isinstance(current, str) and current.startswith("[") and current.endswith("]"):
        try:
            items = current[1:-1].split(",")
            return [i.strip().strip("'").strip('"') for i in items if i.strip()]
        except:
            pass
    return [current] if current and isinstance(current, str) else []


def load_from_db():
    from STEP2.vectorstore import get_stores

    _ROOT = Path(__file__).resolve().parent.parent.parent.parent
    conn = sqlite3.connect(str(_ROOT / "k_enter_news.db"))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 후보군을 대폭 늘려서 가져옵니다 (각 30개씩)
    category_limits = {
        "컨텐츠 & 작품": 30,
        "인물 & 아티스트": 30,
        "비즈니스 & 행사": 30,
    }

    raw_rows = []
    for category, limit in category_limits.items():
        cursor.execute(
            """
            SELECT p.id, p.raw_news_id, p.category, p.sub_category,
                p.summary, p.summary_en, p.keywords, p.artist_tags,
                p.sentiment, p.importance, p.importance_reason,
                p.trend_insight, p.timeline, p.source_name, p.tts_text,
                p.url, p.published_at, p.ko_title, p.thumbnail_url
            FROM processed_news p
            WHERE p.importance IS NOT NULL AND p.category = ?
            ORDER BY p.importance DESC, p.id DESC
            LIMIT ?
            """,
            (category, limit),
        )
        raw_rows.extend(cursor.fetchall())
    conn.close()

    seen_artists = set()
    final_news_list = []
    remained_news_pool = [] # 4개 채우고 남은 뉴스들 (백업용)
    
    # 1차: 카테고리별 4개씩 채우기
    for category in category_limits.keys():
        cat_count = 0
        cat_rows = [r for r in raw_rows if r["category"] == category]
        
        for row in cat_rows:
            tags = parse_json(row["artist_tags"])
            norm_tags = [normalize_artist(t) for t in tags if isinstance(t, str)]
            
            primary_artist = None
            for t in norm_tags:
                if t and t.strip():
                    primary_artist = t.strip()
                    break
            
            # 아티스트 중복 체크
            is_dup = False
            if primary_artist:
                if primary_artist in seen_artists:
                    is_dup = True
            
            news_obj = {
                "url": row["url"] or "",
                "id": row["id"],
                "title": row["ko_title"] or "",
                "summary": parse_json(row["summary"]),
                "summary_en": parse_json(row["summary_en"]),
                "keywords": parse_json(row["keywords"]),
                "artist_tags": norm_tags,
                "importance": row["importance"],
                "importance_reason": row["importance_reason"] or "",
                "sub_category": row["sub_category"] or "",
                "category": row["category"] or "",
                "sentiment": row["sentiment"] or "neutral",
                "trend_insight": row["trend_insight"] or "",
                "source_name": row["source_name"] or "",
                "published_at": str(row["published_at"]) if row["published_at"] else "",
                "timeline": parse_json(row["timeline"]),
                "thumbnail_url": row["thumbnail_url"] or "",
                "tts_text": row["tts_text"] or ""
            }

            if not is_dup and cat_count < 4:
                if primary_artist:
                    seen_artists.add(primary_artist)
                final_news_list.append(news_obj)
                cat_count += 1
            else:
                remained_news_pool.append(news_obj)

    # 2차: 만약 전체 개수가 10개 미만이면 남은 풀에서 중복 없이 더 채우기
    if len(final_news_list) < 10:
        remained_news_pool = sorted(remained_news_pool, key=lambda x: x["importance"], reverse=True)
        for news in remained_news_pool:
            tags = news.get("artist_tags", [])
            primary_artist = news["artist_tags"][0] if tags else None
            
            if primary_artist and primary_artist in seen_artists:
                continue
            
            if primary_artist:
                seen_artists.add(primary_artist)
            final_news_list.append(news)
            
            if len(final_news_list) >= 10:
                break

    # 최종 정렬 후 상위 10개로 제한
    final_news_list = sorted(final_news_list, key=lambda x: (x["importance"], x["id"]), reverse=True)[:10]

    _, past_store = get_stores()
    related_news_map = {}
    for i, news in enumerate(final_news_list):
        query_text = news["title"] + " " + " ".join(news["keywords"])
        results = past_store.similarity_search_with_score(query_text, k=10)
        related_news_map[i] = [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": score,
            }
            for doc, score in results
        ]

    return {
        "top_news_list": final_news_list,
        "related_news_map": related_news_map,
        "summaries_map": {},
        "report_text": "",
        "tts_output_path": "",
    }


@st.cache_resource(show_spinner="🔄 뉴스 파이프라인 실행 중...")
def run_pipeline():
    session = SessionLocal()
    try:
        already_done = (
            session.query(ProcessedNews)
            .filter(ProcessedNews.importance.isnot(None))
            .count()
        )
    finally:
        session.close()

    if already_done > 0:
        return load_from_db()

    app = build_graph()
    initial_state: NewsState = {
        "top_news_list": [],
        "related_news_map": {},
        "summaries_map": {},
        "report_text": "",
        "tts_output_path": "",
    }
    return app.invoke(initial_state)
