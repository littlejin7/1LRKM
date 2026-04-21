
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import RawNews, get_session

def reset_failed_news():
    print("[START] Resetting news that failed with ValidationError...")
    
    with get_session() as session:
        # skip_reason에 ValidationError가 포함된 RawNews 조회
        failed_news = session.query(RawNews).filter(RawNews.skip_reason.like('%ValidationError%')).all()
        
        count = 0
        for raw in failed_news:
            raw.is_processed = False
            raw.skip_reason = None
            count += 1
            
        session.commit()
        print(f"[DONE] Reset {count} failed records for re-processing.")

if __name__ == "__main__":
    reset_failed_news()
