import sys
import os

# 현재 작업 디렉토리를 파이썬 경로에 추가
sys.path.append(os.getcwd())

from database import get_session, RawNews

def delete_raw_news_by_id(target_id: int):
    """특정 ID의 RawNews 삭제"""
    with get_session() as session:
        target = session.query(RawNews).filter(RawNews.id == target_id).first()
        
        if not target:
            print(f"ID={target_id} 뉴스를 찾을 수 없습니다.")
            return

        print(f"ID={target_id} 뉴스를 삭제합니다... (제목: {target.title[:30]}...)")
        session.delete(target)
        session.commit()
        print("삭제 완료!")

if __name__ == "__main__":
    delete_raw_news_by_id(427)
