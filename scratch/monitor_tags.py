import sys
import os

sys.path.append(os.getcwd())
from database import get_session, ProcessedNews, PastNews
from processor import _loads_maybe

def count_k_enter():
    with get_session() as session:
        recent = session.query(ProcessedNews).all()
        past = session.query(PastNews).all()
        
        count = 0
        for item in (recent + past):
            tags = _loads_maybe(item.artist_tags)
            if any(t.lower() == "k-enter" for t in tags):
                count += 1
        print(f"현재 남은 K-Enter 태그 기사: {count}건")

if __name__ == "__main__":
    count_k_enter()
