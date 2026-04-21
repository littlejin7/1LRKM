
import sys
import io
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from database import RawNews, get_session

def clean_existing_hints():
    print("[START] Cleaning up digit-only hints from RawNews...")
    
    with get_session() as session:
        # [ARTIST_HINT]가 포함된 모든 뉴스 조회
        all_raw = session.query(RawNews).filter(RawNews.content.like('[ARTIST_HINT]%')).all()
        
        updated_count = 0
        for raw in all_raw:
            try:
                lines = raw.content.split('\n', 1)
                if not lines[0].startswith("[ARTIST_HINT]"):
                    continue
                
                hint_part = lines[0].replace("[ARTIST_HINT]", "").strip()
                rest_content = lines[1] if len(lines) > 1 else ""
                
                # 힌트 토큰 분리 (쉼표 기준)
                tokens = [t.strip() for t in hint_part.split(',') if t.strip()]
                
                # 숫자로만 된 토큰 제거
                cleaned_tokens = [t for t in tokens if not t.isdigit()]
                
                # 만약 변화가 있다면 업데이트
                if len(tokens) != len(cleaned_tokens):
                    if cleaned_tokens:
                        new_hint_line = f"[ARTIST_HINT]{', '.join(cleaned_tokens)}"
                        raw.content = f"{new_hint_line}\n{rest_content}"
                    else:
                        # 힌트가 숫자뿐이어서 다 지워졌다면 태그 자체를 제거하거나 빈 값 처리
                        raw.content = rest_content
                    
                    updated_count += 1
                
            except Exception as e:
                print(f"  [ERROR] ID {raw.id}: {e}")
        
        session.commit()
        print(f"\n[DONE] Cleaned up {updated_count} records by removing digit hints.")

if __name__ == "__main__":
    clean_existing_hints()
