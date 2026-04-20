import sys
import os
from collections import Counter

# 현재 작업 디렉토리를 파이썬 경로에 추가
sys.path.append(os.getcwd())

from database import get_session, RawNews

def check_processing_status():
    """RawNews 테이블의 가공 상태를 정밀 점검"""
    with get_session() as session:
        total = session.query(RawNews).count()
        unprocessed = session.query(RawNews).filter(RawNews.is_processed == False).count()
        skipped = session.query(RawNews).filter(RawNews.skip_reason.isnot(None)).all()
        
        print(f"--- [RawNews 통계] ---")
        print(f"전체 데이터: {total}건")
        print(f"가공 대기 중: {unprocessed}건")
        print(f"스킵된 데이터: {len(skipped)}건")
        
        if skipped:
            print(f"\n--- [스킵 사유별 집계] ---")
            reasons = [s.skip_reason.split(":")[0] for s in skipped]
            reason_counts = Counter(reasons)
            for reason, count in reason_counts.items():
                print(f"- {reason}: {count}건")
            
            print(f"\n--- [최근 스킵 샘플 5건] ---")
            for s in skipped[-5:]:
                print(f"ID={s.id} | 사유: {s.skip_reason[:60]}... | 제목: {s.title[:30]}...")

if __name__ == "__main__":
    check_processing_status()
