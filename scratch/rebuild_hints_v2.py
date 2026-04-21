
import sys
import io
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from database import RawNews, get_session
from STEP1.collect import extract_person_hint

def rebuild_hints_v2():
    print("[START] Rebuilding artist hints with new weighted & filtered logic...")
    
    with get_session() as session:
        # 모든 RawNews 조회
        all_raw = session.query(RawNews).all()
        
        updated_count = 0
        for raw in all_raw:
            try:
                # 기존 힌트가 있다면 제거하고 원본 본문만 추출
                content = raw.content
                if content.startswith("[ARTIST_HINT]"):
                    parts = content.split('\n', 1)
                    original_content = parts[1] if len(parts) > 1 else ""
                else:
                    original_content = content
                
                # 새로운 로직으로 힌트 생성 (제목 가중치 5배 적용 버전)
                new_hint = extract_person_hint(raw.title, original_content).strip()
                
                if new_hint:
                    new_content = f"[ARTIST_HINT]{new_hint}\n{original_content}"
                else:
                    new_content = original_content
                
                # 내용이 바뀌었으면 업데이트
                if raw.content != new_content:
                    raw.content = new_content
                    updated_count += 1
                
                if (updated_count) % 20 == 0:
                    session.commit() # 중간 저장
                    
            except Exception as e:
                print(f"  [ERROR] ID {raw.id}: {e}")
        
        session.commit()
        print(f"\n[DONE] Successfully rebuilt {updated_count} records with high-precision hints.")

if __name__ == "__main__":
    rebuild_hints_v2()
