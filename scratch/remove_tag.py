import sqlite3
import json

db_path = r"c:\oLRKM\k_enter_news.db"

def parse_json(val):
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        # Handle potential multiple encoding
        result = val
        for _ in range(3):
            if isinstance(result, list):
                return result
            if isinstance(result, str):
                result = json.loads(result)
        return result if isinstance(result, list) else []
    except:
        return []

def remove_tag(ids, tag_to_remove):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    for record_id in ids:
        cursor.execute("SELECT id, artist_tags FROM processed_news WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        
        if row:
            current_tags = parse_json(row[1])
            print(f"ID {record_id} current tags: {current_tags}")
            
            # Remove "sheesh" (case-insensitive just in case, but user specified "sheesh")
            new_tags = [t for t in current_tags if str(t).lower() != tag_to_remove.lower()]
            
            if len(new_tags) != len(current_tags):
                updated_tags_json = json.dumps(new_tags, ensure_ascii=False)
                cursor.execute("UPDATE processed_news SET artist_tags = ? WHERE id = ?", (updated_tags_json, record_id))
                print(f"  -> Removed '{tag_to_remove}'. New tags: {new_tags}")
            else:
                print(f"  -> Tag '{tag_to_remove}' not found in ID {record_id}.")
        else:
            print(f"ID {record_id} not found in processed_news.")
            
    conn.commit()
    conn.close()

if __name__ == "__main__":
    remove_tag([64, 52], "sheesh")
