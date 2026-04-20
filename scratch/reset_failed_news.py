import sys
import os

# 현재 작업 디렉토리를 파이썬 경로에 추가
sys.path.append(os.getcwd())

from database import get_session, RawNews

def reset_failed_news():
    """skip_reason이 있는(실패한) 뉴스들을 다시 가공 대기 상태로 변경"""
    with get_session() as session:
        failed_news = session.query(RawNews).filter(RawNews.skip_reason.isnot(None)).all()
        
        if not failed_news:
            print("재시도할 실패 뉴스(skip_reason 존재)가 없습니다.")
            return

        print(f"총 {len(failed_news)}건의 실패 뉴스를 재설정합니다...")
        for news in failed_news:
            news.is_processed = False
            news.skip_reason = None
        
        session.commit()
        print("초기화 완료! 이제 processor.py를 실행하면 이 뉴스들을 다시 가공합니다.")

if __name__ == "__main__":
    reset_failed_news()
