
import sys
import os
import json
sys.path.append(os.getcwd())
from database import get_session, RawNews, ProcessedNews, PastNews

def reset_problematic_records():
    with get_session() as session:
        # 1. Reset silent failures (86 records)
        all_processed_raws = session.query(RawNews).filter(RawNews.is_processed == True).all()
        silent_failure_count = 0
        for raw in all_processed_raws:
            has_processed = session.query(ProcessedNews).filter(ProcessedNews.raw_news_id == raw.id).first()
            has_past = session.query(PastNews).filter(PastNews.url == raw.url).first()
            if not has_processed and not has_past and not raw.skip_reason:
                raw.is_processed = False
                silent_failure_count += 1
        
        # 2. Reset "K-Enter" tags (40 records)
        k_enter_count = 0
        p_news_with_k_enter = session.query(ProcessedNews).all()
        for p in p_news_with_k_enter:
            tags = p.artist_tags
            if isinstance(tags, str):
                try: tags_list = json.loads(tags)
                except: tags_list = [tags]
            else: tags_list = tags
            
            if any('k-enter' in str(t).lower() for t in tags_list):
                # Find the raw news and reset it
                raw = session.query(RawNews).filter(RawNews.id == p.raw_news_id).first()
                if raw:
                    raw.is_processed = False
                    # Also delete the bad processed record to avoid duplicates later
                    session.delete(p)
                    k_enter_count += 1

        session.commit()
        print(f"Reset {silent_failure_count} silent failures.")
        print(f"Reset and deleted {k_enter_count} 'K-Enter' tagged records.")

if __name__ == "__main__":
    reset_problematic_records()
