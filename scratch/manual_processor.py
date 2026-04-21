
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print("DEBUG: Importing session and processor...")
from database import get_session
from STEP1.processor import process_and_save, fetch_images_for_processed

print("DEBUG: Starting session...")
with get_session() as session:
    print("DEBUG: Starting process_and_save...")
    # 1개만 테스트로 가공 시도
    count = process_and_save(session, batch_size=1)
    print(f"DEBUG: Processed count: {count}")
    
    if count > 0:
        print("DEBUG: Fetching images...")
        fetch_images_for_processed(session, headless=True)
        print("DEBUG: Image fetch done.")

print("DEBUG: Script finished.")
