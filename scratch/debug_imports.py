
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print("Importing os, time, datetime...")
import os, time
from datetime import datetime

print("Importing sqlalchemy...")
from sqlalchemy.orm import Session

print("Importing local modules...")
from database import get_session, RawNews, ProcessedNews, PastNews

print("Importing processing logic...")
# 이 부분이 의심됨
try:
    from STEP1.processor import process_and_save
    print("Import success!")
except Exception as e:
    print(f"Import failed: {e}")
