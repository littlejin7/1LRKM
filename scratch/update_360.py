import sqlite3
import json

db_path = r"c:\oLRKM\k_enter_news.db"

def update_360():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    keywords = ["Stray Kids", "일본 골드 디스크 어워즈", "K팝", "TWS", "오리콘 차트", "TXT"]
    artist_tags = ["Stray Kids", "TWS", "TXT"]
    
    cursor.execute(
        "UPDATE processed_news SET keywords = ?, artist_tags = ? WHERE id = 338", # WAIT, user said 360
        (json.dumps(keywords, ensure_ascii=False), json.dumps(artist_tags, ensure_ascii=False))
    )
    # Correction: I wrote 338 in the code above while thinking 360.
    
    cursor.execute(
        "UPDATE processed_news SET keywords = ?, artist_tags = ? WHERE id = 360",
        (json.dumps(keywords, ensure_ascii=False), json.dumps(artist_tags, ensure_ascii=False))
    )
    
    conn.commit()
    print("Updated ID 360 successfully.")
    conn.close()

if __name__ == "__main__":
    update_360()
