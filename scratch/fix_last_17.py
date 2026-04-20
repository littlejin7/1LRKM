import sys
import os
import json

sys.path.append(os.getcwd())
from database import get_session, RawNews, ProcessedNews, PastNews
from processor import process_single, _loads_maybe

def fix_last_17():
    print("--- [마지막 17건 정밀 수술 시작] ---")
    with get_session() as session:
        recent = session.query(ProcessedNews).all()
        past = session.query(PastNews).all()
        
        targets = []
        for item in (recent + past):
            tags = _loads_maybe(item.artist_tags)
            if not tags:
                targets.append(item)
        
        print(f"대상: {len(targets)}건")
        
        for item in targets:
            raw_id = getattr(item, "raw_news_id", None) or getattr(item, "processed_news_id", None)
            raw = None
            if raw_id:
                raw = session.query(RawNews).filter(RawNews.id == raw_id).first()
            if not raw and item.url:
                raw = session.query(RawNews).filter(RawNews.url == item.url).first()
            
            if not raw:
                print(f"ID={item.id} 원본 없음")
                continue
            
            print(f"ID={item.id} 가공 중... ({item.ko_title[:20]})")
            try:
                result_payload, _ = process_single(raw)
                tags = result_payload.get("artist_tags", [])
                print(f"  결과: {tags}")
                item.artist_tags = json.dumps(tags, ensure_ascii=False)
                session.commit()
            except Exception as e:
                print(f"  에러: {e}")
                session.rollback()

if __name__ == "__main__":
    fix_last_17()
