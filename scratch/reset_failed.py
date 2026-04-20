import sqlite3

def reset_failed_jobs():
    conn = sqlite3.connect('k_enter_news.db')
    c = conn.cursor()
    
    # ValidationError로 실패한 항목들 초기화
    c.execute("UPDATE raw_news SET is_processed = 0, skip_reason = NULL WHERE skip_reason LIKE 'ValidationError%'")
    
    count = conn.total_changes
    conn.commit()
    print(f"Successfully reset {count} failed records for reprocessing.")
    conn.close()

if __name__ == "__main__":
    reset_failed_jobs()
