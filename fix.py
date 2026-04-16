import sqlite3
conn = sqlite3.connect('k_enter_news.db')

columns = [
    "ALTER TABLE past_news ADD COLUMN title VARCHAR(500) DEFAULT NULL",
    "ALTER TABLE past_news ADD COLUMN artist_name VARCHAR(100) DEFAULT NULL",
    "ALTER TABLE past_news ADD COLUMN url VARCHAR(1000) DEFAULT NULL",
    "ALTER TABLE past_news ADD COLUMN relation_type VARCHAR(50) DEFAULT NULL",
    "ALTER TABLE past_news ADD COLUMN relevance_score REAL DEFAULT 0.0",
    "ALTER TABLE past_news ADD COLUMN sentiment VARCHAR(10) DEFAULT NULL",
    "ALTER TABLE past_news ADD COLUMN category VARCHAR(40) DEFAULT NULL",
    "ALTER TABLE past_news ADD COLUMN source_name VARCHAR(100) DEFAULT NULL",
    "ALTER TABLE past_news ADD COLUMN published_at DATETIME DEFAULT NULL",
    "ALTER TABLE past_news ADD COLUMN processed_news_id INTEGER DEFAULT NULL",
]

for sql in columns:
    try:
        conn.execute(sql)
        col = sql.split("COLUMN")[1].strip().split()[0]
        print(f'완료: {col}')
    except Exception as e:
        print(f'스킵: {e}')

conn.commit()
conn.close()
print('전체 완료!')