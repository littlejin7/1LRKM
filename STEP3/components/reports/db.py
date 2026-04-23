import sys
import json
import sqlite3
from pathlib import Path
from datetime import date
from collections import Counter

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from STEP3.components.news.news_pip import load_from_db, ARTIST_MAP


def _db_path() -> Path:
    return ROOT_DIR / "k_enter_news.db"


def _fetch_recent_distinct_dates(table: str, *, n_days: int = 3) -> list[date]:
    path = _db_path()
    if not path.is_file():
        return []
    con = sqlite3.connect(str(path))
    try:
        cur = con.cursor()
        cur.execute(
            f"""
            SELECT DISTINCT DATE(published_at) AS d
            FROM {table}
            WHERE published_at IS NOT NULL
            ORDER BY DATE(published_at) DESC
            LIMIT ?
            """,
            (n_days,),
        )
        rows = cur.fetchall()
    finally:
        con.close()
    out: list[date] = []
    for (d,) in rows:
        if d:
            out.append(date.fromisoformat(str(d)[:10]))
    out.sort()
    return out


def _j(val) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            v = json.loads(val)
            return v if isinstance(v, list) else []
        except Exception:
            return []
    return []


def _fetch_processed_in_dates(days: list[date]) -> list[dict]:
    if not days:
        return []
    path = _db_path()
    if not path.is_file():
        return []
    placeholders = ",".join(["?"] * len(days))
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute(
            f"""
            SELECT id, category, sub_category, ko_title, sentiment, importance,
                   thumbnail_url, artist_tags, keywords, source_name, published_at
            FROM processed_news
            WHERE published_at IS NOT NULL
              AND DATE(published_at) IN ({placeholders})
            ORDER BY id DESC
            """,
            tuple(d.isoformat() for d in days),
        )
        rows = cur.fetchall()
    finally:
        con.close()
    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "title": r["ko_title"] or "",
                "category": r["category"] or "기타",
                "sub_category": r["sub_category"] or "",
                "sentiment": r["sentiment"] or "중립",
                "importance": r["importance"],
                "thumbnail_url": r["thumbnail_url"] or "",
                "artist_tags": _j(r["artist_tags"]),
                "keywords": _j(r["keywords"]),
                "source_name": r["source_name"] or "",
                "published_at": r["published_at"] or "",
            }
        )
    return out


def _fetch_past_in_dates(days: list[date]) -> list[dict]:
    if not days:
        return []
    path = _db_path()
    if not path.is_file():
        return []
    placeholders = ",".join(["?"] * len(days))
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute(
            f"""
            SELECT id, title, sentiment, category, source_name, published_at
            FROM past_news
            WHERE published_at IS NOT NULL
              AND DATE(published_at) IN ({placeholders})
            ORDER BY id DESC
            """,
            tuple(d.isoformat() for d in days),
        )
        rows = cur.fetchall()
    finally:
        con.close()
    return [
        {
            "id": r["id"],
            "title": r["title"] or "",
            "sentiment": r["sentiment"] or "중립",
            "category": r["category"] or "기타",
            "source_name": r["source_name"] or "",
            "published_at": r["published_at"] or "",
        }
        for r in rows
    ]


def load_all_processed_news():
    conn = sqlite3.connect(ROOT_DIR / "k_enter_news.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, category, sub_category, ko_title, source_name,
               importance, published_at
        FROM processed_news
        WHERE importance IS NOT NULL
        ORDER BY importance DESC, id DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "title": r["ko_title"] or "",
            "category": r["category"] or "",
            "sub_category": r["sub_category"] or "기타",
            "source_name": r["source_name"] or "",
            "importance": r["importance"],
            "published_at": str(r["published_at"]) if r["published_at"] else "",
        }
        for r in rows
    ]


def get_top10():
    """news_pip.py에서 Top 10 뉴스 가져오기"""
    state = load_from_db()
    return state["top_news_list"]


def get_top_keywords(top_n: int = 3) -> list:
    """processed_news 전체 keywords에서 인물 제외 TOP N 키워드 집계"""
    import sqlite3 as _sqlite3
    import json
    from collections import Counter

    conn = _sqlite3.connect(str(ROOT_DIR / "k_enter_news.db"))
    conn.row_factory = _sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT keywords FROM processed_news WHERE keywords IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()

    # ARTIST_MAP 인물 이름 목록
    exclude = set(ARTIST_MAP.values())

    counter = Counter()
    for row in rows:
        keywords = row["keywords"]
        if isinstance(keywords, str):
            try:
                keywords = json.loads(keywords)
            except:
                continue
        if not isinstance(keywords, list):
            continue
        for kw in keywords:
            if not isinstance(kw, str):
                continue
            kw = kw.strip()
            if kw and kw not in exclude:
                counter[kw] += 1

    return counter.most_common(top_n)
