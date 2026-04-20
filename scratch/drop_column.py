import sqlite3
import os

db_path = "c:/oLRKM/k_enter_news.db"

def drop_artist_name_column():
    if not os.path.exists(db_path):
        print("DB 파일이 존재하지 않습니다.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("1. 현재 past_news 구조 확인...")
        cursor.execute("PRAGMA table_info(past_news)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "artist_name" not in columns:
            print("이미 artist_name 컬럼이 존재하지 않습니다.")
            return

        print("2. 새로운 구조로 테이블 마이그레이션 시작...")
        
        # 새 테이블을 만들기 위한 모든 컬럼명 추출 (artist_name 제외)
        cols_to_keep = [c for c in columns if c != "artist_name"]
        cols_str = ", ".join(cols_to_keep)

        # 트랜잭션 시작
        cursor.execute("BEGIN TRANSACTION;")
        
        # 1) 기존 테이블 이름 변경
        cursor.execute("ALTER TABLE past_news RENAME TO past_news_old;")
        
        # 2) 새로운 테이블 생성 (database.py의 최신 정의에 맞게)
        # 간단하게 하기 위해 기존 테이블 생성 SQL에서 artist_name만 빼고 실행하거나, 
        # 직접 필드를 정의합니다. 여기서는 안전하게 기존 데이터를 기반으로 재생성합니다.
        
        # sqlite_master에서 원본 CREATE 문을 가져와서 artist_name 부분만 제거하는 것은 위험할 수 있으므로
        # 명시적으로 새 테이블을 정의합니다. (SQLAlchemy가 나중에 create_all로 부족한걸 채울 것입니다)
        
        # 여기서는 가장 확실한 방법인 '복사 생성' 방식을 씁니다.
        cursor.execute(f"CREATE TABLE past_news AS SELECT {cols_str} FROM past_news_old;")
        
        # 3) 이전 테이블 삭제
        cursor.execute("DROP TABLE past_news_old;")
        
        conn.commit()
        print("✅ 성공: past_news 테이블에서 artist_name 컬럼을 물리적으로 삭제했습니다.")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ 오류 발생: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    drop_artist_name_column()
