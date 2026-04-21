
import sqlite3
import json

def verify_reprocessing():
    conn = sqlite3.connect('k_enter_news.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # 1. Check for K-Enter
    cur.execute("SELECT id, artist_tags, ko_title FROM processed_news WHERE artist_tags LIKE '%K-Enter%'")
    k_rows = cur.fetchall()
    
    # 2. Check for recent processed ones
    cur.execute("SELECT id, artist_tags, ko_title FROM processed_news ORDER BY id DESC LIMIT 10")
    recent = cur.fetchall()
    
    print(f"Total 'K-Enter' in processed_news: {len(k_rows)}")
    print("\n=== Recent 10 Processed Items ===")
    for r in recent:
        print(f"ID {r['id']:<5} {r['artist_tags']:<20} {r['ko_title']}")
    
    conn.close()

if __name__ == "__main__":
    verify_reprocessing()
