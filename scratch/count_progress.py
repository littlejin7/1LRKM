import sys
import os

sys.path.append(os.getcwd())
from database import get_session, ProcessedNews, PastNews
from processor import _loads_maybe

def count_empty_tags():
    with get_session() as session:
        recent = session.query(ProcessedNews).all()
        past = session.query(PastNews).all()
        
        empty_count = 0
        filled_count = 0
        for item in (recent + past):
            tags = _loads_maybe(item.artist_tags)
            if not tags:
                empty_count += 1
            else:
                filled_count += 1
        print(f"현재 실명 채워짐: {filled_count}건")
        print(f"아직 빈 태그(가공 대기): {empty_count}건")

if __name__ == "__main__":
    count_empty_tags()
