import sqlite3
import json

db_path = r"c:\oLRKM\k_enter_news.db"

def update_245():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    keywords = ["그래미 어워드", "K팝", "로제", "케데헌", "캐츠 아이", "시상식"]
    
    cursor.execute(
        "UPDATE processed_news SET keywords = ? WHERE id = 245",
        (json.dumps(keywords, ensure_ascii=False),)
    )
    
    conn.commit()
    print("Updated ID 245 successfully.")
    conn.close()

if __name__ == "__main__":
    update_245()
