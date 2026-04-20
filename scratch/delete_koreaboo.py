import sqlite3

def delete_koreaboo():
    conn = sqlite3.connect('k_enter_news.db')
    c = conn.cursor()
    
    # 1. processed_news 삭제
    c.execute("DELETE FROM processed_news WHERE raw_news_id IN (SELECT id FROM raw_news WHERE url LIKE '%koreaboo.com%')")
    
    # 2. raw_news 삭제
    c.execute("DELETE FROM raw_news WHERE url LIKE '%koreaboo.com%'")
    
    count = conn.total_changes
    conn.commit()
    print(f"Successfully deleted all Koreaboo articles (Total {count} changes).")
    conn.close()

if __name__ == "__main__":
    delete_koreaboo()
