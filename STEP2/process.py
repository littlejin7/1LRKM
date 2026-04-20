"""
process.py -- 전체 파이프라인 순서대로 실행
실행: python STEP2/process.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import subprocess
import shutil
import os


def main():
    print("[START] 전체 파이프라인 시작\n" + "="*50)

    # 1. 기존 chroma_db 삭제
    chroma_dir = "./chroma_db"
    if os.path.exists(chroma_dir):
        try:
            shutil.rmtree(chroma_dir)
            print("[OK] 기존 chroma_db 삭제 완료")
        except PermissionError:
            print("[WARN] chroma_db 삭제 실패 (다른 프로세스가 점유 중) - 기존 데이터로 진행")
    else:
        print("[SKIP] chroma_db 없음, 스킵")

    # 2. trend_insight 초기화
    print("\n[1] trend_insight 초기화 중...")
    import sqlite3
    conn = sqlite3.connect("k_enter_news.db")
    conn.execute("UPDATE processed_news SET trend_insight = NULL")
    conn.commit()
    conn.close()
    print("  >> trend_insight 초기화 완료")

    # 3. 임베딩
    print("\n[2] 임베딩 시작...")
    subprocess.run([sys.executable, "STEP2/vectorstore.py"], check=True)

    # 4. 한줄평 생성
    print("\n[3] 한줄평 생성 시작...")
    subprocess.run([sys.executable, "STEP2/rag_search.py"], check=True)

    # 5. 타임라인 생성
    print("\n[4] 타임라인 생성 시작...")
    result = subprocess.run([sys.executable, "STEP2/timeline.py"])
    if result.returncode != 0:
        print("  [WARN] timeline.py 실행 실패 또는 파일 없음 - 스킵")

if __name__ == "__main__":
    main()
