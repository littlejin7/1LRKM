
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import RawNews, get_session

def test_db_write():
    try:
        with get_session() as session:
            # 존재하지 않는 ID로 조회만 해봄 (쓰기 락 확인을 위해 transaction 시작)
            session.query(RawNews).filter(RawNews.id == -1).all()
            print("DB Read OK")
            
            # 실제 쓰기 시도 (나중에 롤백)
            new_raw = RawNews(title="test", content="test", url="test_url_123")
            session.add(new_raw)
            session.flush() # 락 체크
            print("DB Write (flush) OK")
            session.rollback()
    except Exception as e:
        print(f"DB Error: {e}")

if __name__ == "__main__":
    test_db_write()
