
import sys
import os
sys.path.append(os.getcwd())
from database import get_session, RawNews, ProcessedNews, PastNews

def check_failed_processing():
    with get_session() as session:
        # Find raw news that are marked as processed but have no outcome and no skip_reason
        # (This indicates a potential silent failure or the rollback bug)
        unaccounted = []
        
        # We only care about recently processed ones (e.g. today)
        raws = session.query(RawNews).filter(RawNews.is_processed == True).all()
        
        for raw in raws:
            # Check if it has a processed or past record
            has_processed = session.query(ProcessedNews).filter(ProcessedNews.raw_news_id == raw.id).first()
            has_past = session.query(PastNews).filter(PastNews.url == raw.url).first() # URL match for past news
            
            if not has_processed and not has_past:
                if not raw.skip_reason:
                    unaccounted.append(raw)
                elif "JunkFilter" in raw.skip_reason:
                    # Skip junk filter items as they are expected to have a reason
                    pass
                else:
                    # Already has a reason, maybe not a bug but let's see
                    pass

        print(f"Total processed: {len(raws)}")
        print(f"Potentially failed without reason: {len(unaccounted)}")
        for r in unaccounted[:10]:
            print(f"  ID: {r.id}, Title: {r.title}")

if __name__ == "__main__":
    check_failed_processing()
