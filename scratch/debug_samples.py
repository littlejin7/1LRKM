import sys
import os

sys.path.append(os.getcwd())
from database import get_session, ProcessedNews, PastNews
from processor import _loads_maybe

def debug_k_enter_samples():
    with get_session() as session:
        recent = session.query(ProcessedNews).all()
        past = session.query(PastNews).all()
        
        samples = []
        for item in (recent + past):
            tags = _loads_maybe(item.artist_tags)
            if any(t.lower() == "k-enter" for t in tags):
                samples.append(item)
            if len(samples) >= 5: break
            
        print(f"--- [K-Enter 샘플 점검] ---")
        for s in samples:
            raw_id = getattr(s, "raw_news_id", None) or getattr(s, "processed_news_id", None)
            print(f"ID={s.id} | Table={s.__class__.__name__} | RawID={raw_id} | Title={s.ko_title[:30]}...")

if __name__ == "__main__":
    debug_k_enter_samples()
