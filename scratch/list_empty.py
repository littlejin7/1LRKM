import sys
import os

sys.path.append(os.getcwd())
from database import get_session, ProcessedNews, PastNews
from processor import _loads_maybe

def list_empty_titles():
    print("--- [미가공 17건 기사 리스트] ---")
    with get_session() as session:
        recent = session.query(ProcessedNews).all()
        past = session.query(PastNews).all()
        
        count = 0
        for item in (recent + past):
            tags = _loads_maybe(item.artist_tags)
            if not tags:
                count += 1
                title = getattr(item, "ko_title", "") or getattr(item, "title", "")
                print(f"{count}. ID={item.id} | Title: {title}")
        
if __name__ == "__main__":
    list_empty_titles()
