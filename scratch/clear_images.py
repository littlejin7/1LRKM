import sys
import os

# 현재 작업 디렉토리를 파이썬 경로에 추가
sys.path.append(os.getcwd())

from database import get_session, ProcessedNews, PastNews

def clear_all_thumbnail_urls():
    """processed_news와 past_news의 모든 이미지 URL을 초기화"""
    with get_session() as session:
        # ProcessedNews 초기화
        p_count = session.query(ProcessedNews).filter(ProcessedNews.thumbnail_url.isnot(None)).update({ProcessedNews.thumbnail_url: None}, synchronize_session=False)
        
        # PastNews 초기화
        past_count = session.query(PastNews).filter(PastNews.thumbnail_url.isnot(None)).update({PastNews.thumbnail_url: None}, synchronize_session=False)
        
        session.commit()
        print(f"초기화 완료: ProcessedNews({p_count}건), PastNews({past_count}건)")
        print("이제 processor.py를 실행하면 고도화된 로직으로 이미지를 다시 수집합니다.")

if __name__ == "__main__":
    clear_all_thumbnail_urls()
