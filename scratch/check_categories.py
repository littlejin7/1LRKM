import sqlite3
import os

db_path = "c:/oLRKM/k_enter_news.db"
if not os.path.exists(db_path):
    print("DB not found")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT category, count(*) FROM processed_news GROUP BY category;")
    rows = cursor.fetchall()
    for row in rows:
        print(f"Category: [{row[0]}], Count: {row[1]}")
    conn.close()
