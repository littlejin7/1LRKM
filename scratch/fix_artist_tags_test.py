import sys
import os
import json
import time

sys.path.append(os.getcwd())
from database import get_session, RawNews, ProcessedNews, PastNews
from processor import process_single, _loads_maybe

def fix_batch(limit=5):
    print(f"--- [태그 수정 테스트 시작: {limit}건] ---")
    with get_session() as session:
        recent = session.query(ProcessedNews).all()
        past = session.query(PastNews).all()
        
        targets = []
        for item in (recent + past):
            tags = _loads_maybe(item.artist_tags)
            if any(t.lower() == "k-enter" for t in tags):
                targets.append(item)
            if len(targets) >= limit: break
            
        if not targets:
            print("대상이 없습니다.")
            return

        for item in targets:
            raw_id = getattr(item, "raw_news_id", None) or getattr(item, "processed_news_id", None)
            raw = session.query(RawNews).filter(RawNews.id == raw_id).first()
            if not raw: continue
            
            print(f"ID={item.id} 가공 중...")
            try:
                # 힌트가 본문에 들어있는지 확인
                hint_present = "[ARTIST_HINT]" in raw.content
                print(f"  힌트 존재 여부: {hint_present}")
                
                result, _ = process_single(raw)
                new_tags = result.get("artist_tags", [])
                print(f"  이전 태그: {item.artist_tags}")
                print(f"  새로운 태그: {new_tags}")
                
                item.artist_tags = json.dumps(new_tags, ensure_ascii=False)
                session.commit()
                print("  성공적으로 업데이트됨!")
            except Exception as e:
                print(f"  에러 발생: {e}")
                session.rollback()

if __name__ == "__main__":
    fix_batch(5)
