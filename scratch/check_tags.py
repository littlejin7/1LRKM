
import sqlite3
import json

def check_artist_tags():
    conn = sqlite3.connect('k_enter_news.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    print("=== Checking for 'k-enter' or weird tags ===")
    cur.execute("SELECT id, ko_title, artist_tags FROM processed_news")
    rows = cur.fetchall()
    
    count = 0
    for r in rows:
        tags = r['artist_tags']
        if not tags: continue
        
        # tags might be JSON string
        if isinstance(tags, str):
            try:
                tags_list = json.loads(tags)
            except:
                tags_list = [tags]
        else:
            tags_list = tags
            
        if any('k-enter' in str(t).lower() for t in tags_list):
            print(f"ID {r['id']}: {r['ko_title']}")
            print(f"  Tags: {tags_list}")
            count += 1
            
        # Also check for non-person items (just a heuristic: more than 10 chars or containing weird symbols)
        # But for now let's focus on 'k-enter'
            
    print(f"\nTotal 'k-enter' tags found: {count}")
    conn.close()

if __name__ == "__main__":
    check_artist_tags()
