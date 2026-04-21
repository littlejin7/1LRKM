
import sys
import os
sys.path.append(os.getcwd())
from database import get_session, RawNews, ProcessedNews, PastNews

def delete_raw_id(rid):
    with get_session() as session:
        raw = session.query(RawNews).filter(RawNews.id == rid).first()
        if not raw:
            print(f"RawNews ID {rid} not found.")
            return
        
        print(f"Found RawNews ID {rid}: {raw.title}")
        
        # Check for ProcessedNews
        processed = session.query(ProcessedNews).filter(ProcessedNews.raw_news_id == rid).first()
        if processed:
            pid = processed.id
            print(f"  Found related ProcessedNews ID {pid}. Deleting it first...")
            
            # Check for PastNews
            past = session.query(PastNews).filter(PastNews.processed_news_id == pid).all()
            if past:
                print(f"    Found {len(past)} related PastNews records. Deleting them...")
                for p in past:
                    session.delete(p)
            
            session.delete(processed)
        
        print(f"Deleting RawNews ID {rid}...")
        session.delete(raw)
        session.commit()
        print("Successfully deleted and committed.")

if __name__ == "__main__":
    delete_raw_id(753)
