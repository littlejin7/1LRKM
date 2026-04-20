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
    print(msg)

def fix_batch_to_file(limit=5):
    log(f"--- [태그 수정 테스트 시작: {limit}건] ---")
    try:
        with get_session() as session:
            recent = session.query(ProcessedNews).all()
            past = session.query(PastNews).all()
            
            targets = []
            for item in (recent + past):
                tags = _loads_maybe(item.artist_tags)
                if any(t.lower() == "k-enter" for t in tags):
                    targets.append(item)
                if len(targets) >= limit: break
                
            if not targets:
                log("대상이 없습니다.")
                return

            for item in targets:
                raw_id = getattr(item, "raw_news_id", None) or getattr(item, "processed_news_id", None)
                raw = session.query(RawNews).filter(RawNews.id == raw_id).first()
                if not raw: continue
                
                log(f"ID={item.id} 가공 중... ({item.ko_title[:20]})")
                try:
                    result, _ = process_single(raw)
                    new_tags = result.get("artist_tags", [])
                    log(f"  변경: {item.artist_tags} -> {new_tags}")
                    
                    item.artist_tags = json.dumps(new_tags, ensure_ascii=False)
                    session.commit()
                    log("  성공적으로 업데이트됨!")
                except Exception as e:
                    log(f"  에러 발생: {e}")
                    session.rollback()
    except Exception as e:
        log(f"치명적 오류: {e}")

if __name__ == "__main__":
    fix_batch_to_file(10) # 10건 시도
