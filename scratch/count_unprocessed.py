
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import RawNews, get_session

def count_unprocessed():
    with get_session() as session:
        count = session.query(RawNews).filter(RawNews.is_processed == False).count()
        print(f"Current count of Unprocessed RawNews: {count}")

if __name__ == "__main__":
    count_unprocessed()
