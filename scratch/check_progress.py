
import sqlite3
conn = sqlite3.connect('k_enter_news.db')
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM raw_news WHERE is_processed=1")
processed = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM raw_news WHERE is_processed=0")
unprocessed = cur.fetchone()[0]
print(f"Processed: {processed}")
print(f"Remaining: {unprocessed}")
conn.close()
