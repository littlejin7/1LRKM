
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import ProcessedNews, get_session

def count_processed():
    with get_session() as session:
        count = session.query(ProcessedNews).count()
        print(f"Current count of ProcessedNews: {count}")

if __name__ == "__main__":
    count_processed()
