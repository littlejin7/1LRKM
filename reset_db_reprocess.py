import sqlite3

def reset_db_for_full_recollect():
    conn = sqlite3.connect('k_enter_news.db')
    c = conn.cursor()
    
    # 1. raw_news 테이블에 skip_reason 컬럼 추가 (있으면 무시)
    try:
        c.execute("ALTER TABLE raw_news ADD COLUMN skip_reason TEXT")
        print("raw_news 테이블에 skip_reason 컬럼 추가 완료.")
    except sqlite3.OperationalError:
        print("skip_reason 컬럼이 이미 존재합니다.")
        
    # 2. 가공된 데이터 완전 삭제
    c.execute("DELETE FROM processed_news")
    deleted_p = c.rowcount
    print(f"processed_news 초기화 완료: {deleted_p}건 삭제됨")
    
    c.execute("DELETE FROM past_news")
    deleted_past = c.rowcount
    print(f"past_news 초기화 완료: {deleted_past}건 삭제됨")
    
    # 3. 원본 데이터 완전 삭제 (날짜 교정 및 재수집을 위해)
    c.execute("DELETE FROM raw_news")
    deleted_raw = c.rowcount
    print(f"raw_news 초기화 완료: {deleted_raw}건 삭제됨 (이제 깨끗한 상태에서 수집을 시작합니다)")
    
    conn.commit()
    conn.close()
    print("\n[성공] DB가 완전히 초기화되었습니다. 이제 crawler1.py를 실행하여 2개월치 데이터를 수집하세요!")

if __name__ == '__main__':
    reset_db_for_full_recollect()
