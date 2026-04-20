"""
vectorstore.py — 임베딩 + ChromaDB 저장

역할:
  스크립트 실행 시: k_enter_news.db → 임베딩 → ChromaDB 저장 (2개 collection)
  get_stores()  : 저장된 벡터스토어 불러오기
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import sqlite3
import json
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

os.environ["ANONYMIZED_TELEMETRY"] = "False"

EMBED_MODEL = "Snowflake/snowflake-arctic-embed-m"
CHROMA_DIR = "./chroma_db"


# ═══════════════════════════════════════════════════
# 벡터스토어 로드 (다른 모듈에서 import)
# ═══════════════════════════════════════════════════

def get_stores():
    """저장된 ChromaDB 벡터스토어 불러오기"""
    emb = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    recent = Chroma(
        collection_name="recent_news",
        embedding_function=emb,
        persist_directory=CHROMA_DIR,
    )
    past = Chroma(
        collection_name="past_news",
        embedding_function=emb,
        persist_directory=CHROMA_DIR,
    )
    return recent, past


# ── summary JSON → 텍스트 변환 헬퍼 ──
def summary_to_text(summary_raw) -> str:
    """summary JSON(List[{label, content}]) → 텍스트"""
    if not summary_raw:
        return ""
    try:
        items = json.loads(summary_raw) if isinstance(summary_raw, str) else summary_raw
        if isinstance(items, list):
            return " ".join([item.get("content", "") for item in items if isinstance(item, dict)])
        return str(items)
    except Exception:
        return str(summary_raw)


def artists_to_text(artist_tags_raw) -> str:
    """artist_tags JSON → 텍스트"""
    if not artist_tags_raw:
        return ""
    try:
        items = json.loads(artist_tags_raw) if isinstance(artist_tags_raw, str) else artist_tags_raw
        return ", ".join(items) if isinstance(items, list) else str(items)
    except Exception:
        return str(artist_tags_raw)


def keywords_to_list(keywords_raw) -> list:
    if not keywords_raw:
        return []
    try:
        items = json.loads(keywords_raw) if isinstance(keywords_raw, str) else keywords_raw
        return items if isinstance(items, list) else []
    except Exception:
        return []


# ═══════════════════════════════════════════════════
# 임베딩 + 저장 (스크립트 실행 시)
# ═══════════════════════════════════════════════════

def build_and_save():
    conn = sqlite3.connect("k_enter_news.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    embedding = HuggingFaceEmbeddings(model_name=EMBED_MODEL)

    cursor.execute("""
        SELECT p.id, p.raw_news_id, p.category, p.sub_category,
               p.summary, p.keywords, p.artist_tags, p.sentiment,
               p.importance, p.source_name, p.url, p.processed_at,
               p.published_at, p.language,
               p.ko_title
        FROM processed_news p
    """)

    recent_docs = []
    for row in cursor.fetchall():
        keywords = keywords_to_list(row["keywords"])
        artists  = artists_to_text(row["artist_tags"])
        summary  = summary_to_text(row["summary"])
        title    = row["ko_title"] or ""

        content = f"""{title}

{summary}

아티스트: {artists}
키워드: {', '.join(keywords)}
카테고리: {row["sub_category"] or ""}"""

        doc = Document(
            page_content=content,
            metadata={
                "id": row["id"] or 0,
                "raw_news_id": row["raw_news_id"] or 0,
                "title": title,
                "category": row["category"] or "",
                "sub_category": row["sub_category"] or "",
                "sentiment": row["sentiment"] or "",
                "importance": row["importance"] or 0,
                "source": row["source_name"] or "",
                "url": row["url"] or "",
                "language": row["language"] or "",
                "published_at": str(row["published_at"]) if row["published_at"] else "",
            },
        )
        recent_docs.append(doc)

    print(f"recent_news: {len(recent_docs)}건")

    cursor.execute("""
        SELECT p.id, p.processed_news_id, p.category, p.sub_category,
               p.summary, p.keywords, p.artist_tags, p.sentiment,
               p.importance, p.source_name, p.url, p.published_at,
               p.language,
               p.ko_title
        FROM past_news p
    """)

    past_docs = []
    for row in cursor.fetchall():
        keywords = keywords_to_list(row["keywords"])
        summary  = summary_to_text(row["summary"])
        title    = row["ko_title"] or ""

        content = f"""{title}

{summary}

키워드: {', '.join(keywords)}"""

        doc = Document(
            page_content=content,
            metadata={
                "id": row["id"] or 0,
                "processed_news_id": row["processed_news_id"] or 0,
                "title": title,
                "category": row["category"] or "",
                "sub_category": row["sub_category"] or "",
                "sentiment": row["sentiment"] or "",
                "importance": row["importance"] or 0,
                "source": row["source_name"] or "",
                "url": row["url"] or "",
                "language": row["language"] or "",
                "published_at": str(row["published_at"]) if row["published_at"] else "",
            },
        )
        past_docs.append(doc)

    print(f"past_news: {len(past_docs)}건")
    conn.close()

    # ── Chroma 저장 ──
    print("임베딩 시작...")

    recent_store = Chroma.from_documents(
        documents=recent_docs,
        embedding=embedding,
        collection_name="recent_news",
        persist_directory=CHROMA_DIR,
    )
    print(f"recent_news 저장 완료: {recent_store._collection.count()}건")

    past_store = Chroma.from_documents(
        documents=past_docs,
        embedding=embedding,
        collection_name="past_news",
        persist_directory=CHROMA_DIR,
    )
    print(f"past_news 저장 완료: {past_store._collection.count()}건")


if __name__ == "__main__":
    build_and_save()
