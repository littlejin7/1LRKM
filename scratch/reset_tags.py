import sys
import os
import json

sys.path.append(os.getcwd())
from database import get_session, ProcessedNews, PastNews
from processor import _loads_maybe

def reset_k_enter_tags():
    print("--- [K-Enter 태그 초기화 시작] ---")
    with get_session() as session:
        recent = session.query(ProcessedNews).all()
        past = session.query(PastNews).all()
        
        reset_count = 0
        for item in (recent + past):
            tags = _loads_maybe(item.artist_tags)
            if any(t.lower() == "k-enter" for t in tags):
                item.artist_tags = json.dumps([], ensure_ascii=False)
                reset_count += 1
        
        session.commit()
        print(f"✅ 총 {reset_count}건의 태그를 성공적으로 비웠습니다. 이제 재가공을 시작합니다!")

if __name__ == "__main__":
    reset_k_enter_tags()
