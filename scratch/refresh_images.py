import sys
from pathlib import Path
# 루트 폴더를 path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# STEP1 폴더를 path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "STEP1"))

from database import get_session
from STEP1.processor import fetch_images_for_processed

def refresh_all_images():
    print("🚀 [이미지 강제 업데이트 시작] 모든 기사를 2026 키워드로 다시 검색합니다...")
    with get_session() as session:
        # overwrite=True로 설정하여 기존 이미지를 무시하고 새로 가져옵니다.
        # 너무 빠르면 차단될 수 있으니 sleep_sec를 2.0으로 넉넉히 둡니다.
        fetch_images_for_processed(session, sleep_sec=2.0, headless=True, overwrite=True)
    print("\n✅ 모든 이미지 업데이트가 완료되었습니다!")

if __name__ == "__main__":
    refresh_all_images()
