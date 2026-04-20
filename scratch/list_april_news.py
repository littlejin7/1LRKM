import sqlite3

def list_april_news():
    conn = sqlite3.connect('k_enter_news.db')
    c = conn.cursor()
    # SQLITE는 문자열 비교로 날짜 필터링 가능 (ISO 형식인 경우)
    query = """
        SELECT id, title, published_at, url 
        FROM raw_news 
        WHERE published_at >= '2026-04-01' 
          AND published_at < '2026-05-01' 
        ORDER BY published_at DESC
    """
    c.execute(query)
    rows = c.fetchall()
    
    print(f"=== 2026년 4월 발행 기사 목록 (총 {len(rows)}건) ===")
    for r in rows:
        print(f"ID: {r[0]} | 날짜: {r[2]} | 제목: {r[1]}")
        print(f"   URL: {r[3]}")
        print("-" * 50)
    
    conn.close()

if __name__ == "__main__":
    list_april_news()
