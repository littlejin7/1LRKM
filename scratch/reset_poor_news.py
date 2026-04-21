
import sys
import io
import json
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from database import RawNews, ProcessedNews, PastNews, get_session

def _is_poor_tags(tags_json):
    try:
        if not tags_json: return True
        tags = tags_json if isinstance(tags_json, list) else json.loads(tags_json)
        if not tags: return True
        if len(tags) == 1 and tags[0].lower() == 'k-enter': return True
        return False
    except:
        return True

def reset_poor_processed_news():
    print("[START] Identification and Reset of news with poor artist tags...")
    
    with get_session() as session:
        # 1. ProcessedNews 검사
        processed_list = session.query(ProcessedNews).all()
        reset_raw_ids = set()
        deleted_processed_count = 0
        
        for p in processed_list:
            if p is None: continue
            if _is_poor_tags(p.artist_tags):
                reset_raw_ids.add(p.raw_news_id)
                session.delete(p)
                deleted_processed_count += 1
        
        # 2. PastNews 검사 (URL로 매칭)
        past_list = session.query(PastNews).all()
        reset_urls = set()
        deleted_past_count = 0
        
        for p in past_list:
            if p is None: continue
            if _is_poor_tags(p.artist_tags):
                reset_urls.add(p.url)
                session.delete(p)
                deleted_past_count += 1
        
        session.commit()
        print(f"  → Deleted {deleted_processed_count} poor records from ProcessedNews.")
        print(f"  → Deleted {deleted_past_count} poor records from PastNews.")
        
        # 3. RawNews 상태 초기화
        total_reset = 0
        if reset_raw_ids:
            updated = session.query(RawNews).filter(RawNews.id.in_(list(reset_raw_ids))).update({"is_processed": False}, synchronize_session=False)
            total_reset += updated
            
        if reset_urls:
            updated = session.query(RawNews).filter(RawNews.url.in_(list(reset_urls))).update({"is_processed": False}, synchronize_session=False)
            total_reset += updated
            
        session.commit()
        print(f"\n[DONE] Reset {total_reset} RawNews records for re-processing.")

if __name__ == "__main__":
    reset_poor_processed_news()
