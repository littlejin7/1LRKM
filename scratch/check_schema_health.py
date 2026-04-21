
import sqlite3
import json
from pathlib import Path

def check_db_health():
    _ROOT = Path(__file__).resolve().parent.parent
    conn = sqlite3.connect(str(_ROOT / "k_enter_news.db"))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=== Database Table Stats ===")
    tables = ["raw_news", "processed_news", "past_news"]
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) as cnt FROM {table}")
        count = cursor.fetchone()["cnt"]
        print(f"Table {table:<15}: {count} records")
    
    print("\n=== Processed News Column Health (Recent 10) ===")
    cursor.execute("""
        SELECT id, category, importance, 
               (trend_insight IS NOT NULL) as has_insight,
               (timeline IS NOT NULL) as has_timeline,
               (keywords IS NOT NULL) as has_keywords
        FROM processed_news
        ORDER BY id DESC LIMIT 10
    """)
    rows = cursor.fetchall()
    print(f"{'ID':<5} {'Cat':<15} {'Imp':<5} {'Insight':<8} {'Timeline':<8} {'Keywords'}")
    for r in rows:
        print(f"{r['id']:<5} {str(r['category']):<15} {str(r['importance']):<5} {bool(r['has_insight']):<8} {bool(r['has_timeline']):<8} {bool(r['has_keywords'])}")
    
    conn.close()

if __name__ == "__main__":
    check_db_health()
