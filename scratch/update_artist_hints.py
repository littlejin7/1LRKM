
import os
import sys
from pathlib import Path
from sqlalchemy import text

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import RawNews, get_session
from STEP1.collect import extract_person_hint

import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def update_missing_hints():
    print("[START] RawNews table [ARTIST_HINT] correction started")
    
    with get_session() as session:
        # 1. [ARTIST_HINT] 태그로 시작하지 않는 모든 RawNews 조회
        # (SQLite는 startswith 대신 LIKE ' [ARTIST_HINT]%' 사용 가능하지만, 
        #  단순히 가져와서 파이썬에서 체크하는 것이 안전함)
        all_raw = session.query(RawNews).all()
        
        target_news = []
        for raw in all_raw:
            if not raw.content.startswith("[ARTIST_HINT]"):
                target_news.append(raw)
        
        total = len(target_news)
        print(f"  → 보정 대상: 총 {total}건 발견")
        
        if total == 0:
            print("[OK] No data to correct.")
            return

        updated_count = 0
        for i, raw in enumerate(target_news):
            try:
                # 힌트 추출 (제목과 현재 본문 사용)
                hint = extract_person_hint(raw.title, raw.content).strip()
                
                if hint:
                    # 힌트가 있으면 앞에 붙여줌
                    raw.content = f"[ARTIST_HINT]{hint}\n{raw.content}"
                    updated_count += 1
                
                # 진행률 출력 (10건 단위)
                if (i + 1) % 10 == 0 or (i + 1) == total:
                    print(f"  → 진행 중... ({i + 1}/{total})")
                    session.commit() # 중간 저장
                    
            except Exception as e:
                print(f"  [ERROR] ID: {raw.id}: {e}")
                session.rollback()

        session.commit()
        print(f"\n[DONE] Total {updated_count} RawNews records updated with hints.")

if __name__ == "__main__":
    update_missing_hints()
