
import sqlite3
import json

def check_past_k_enter():
    conn = sqlite3.connect('k_enter_news.db')
    cur = conn.cursor()
    cur.execute("SELECT id, artist_tags, ko_title FROM past_news")
    rows = cur.fetchall()
    
    count = 0
    for rid, tags, title in rows:
        if not tags: continue
        try:
            t_list = json.loads(tags)
        except:
            t_list = [tags]
            
        if any('k-enter' in str(t).lower() for t in t_list):
            count += 1
            # print(f"ID {rid}: {title}")
            
    print(f"Total 'K-Enter' in past_news: {count}")
    conn.close()

if __name__ == "__main__":
    check_past_k_enter()
