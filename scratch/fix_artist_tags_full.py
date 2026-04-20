import sys
import os
import json
import time

sys.path.append(os.getcwd())
from database import get_session, RawNews, ProcessedNews, PastNews
from processor import process_single, _loads_maybe

def log(msg):
    with open("c:/oLRKM/scratch/fix_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

def fix_all_to_file():
    log("--- [전체 아티스트 태그 정밀 수정 시작] ---")
    try:
        with get_session() as session:
            recent = session.query(ProcessedNews).all()
            past = session.query(PastNews).all()
            
            targets = []
            for item in (recent + past):
                tags = _loads_maybe(item.artist_tags)
                if not tags or any(t.lower() == "k-enter" for t in tags):
                    targets.append(item)
                
            if not targets:
                log("수정할 대상이 없습니다. (모두 정상)")
                return

            log(f"총 {len(targets)}건의 태그 수정을 시작합니다.")

            success_count = 0
            for idx, item in enumerate(targets):
                raw_id = getattr(item, "raw_news_id", None) or getattr(item, "processed_news_id", None)
                raw = session.query(RawNews).filter(RawNews.id == raw_id).first()
                if not raw: continue
                
                try:
                    result, _ = process_single(raw)
                    new_tags = result.get("artist_tags", [])
                    
                    if new_tags:
                        item.artist_tags = json.dumps(new_tags, ensure_ascii=False)
                        # PastNews의 경우 artist_name 필드도 업데이트
                        if isinstance(item, PastNews):
                            item.artist_name = new_tags[0] if new_tags else "K-Enter"
                        
                        session.commit()
                        success_count += 1
                        if success_count % 10 == 0:
                            log(f"진행 중: {success_count}/{len(targets)}건 수정 완료")
                    
                    time.sleep(0.5)
                except Exception as e:
                    log(f"  에러 발생 ID={item.id}: {e}")
                    session.rollback()
            
            log(f"--- [최종 완료] 총 {success_count}건의 태그가 수정되었습니다. ---")
    except Exception as e:
        log(f"치명적 오류: {e}")

if __name__ == "__main__":
    fix_all_to_file()
