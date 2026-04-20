import sys
import os
import json
import time

# 현재 작업 디렉토리를 파이썬 경로에 추가
sys.path.append(os.getcwd())

from database import get_session, RawNews, ProcessedNews, PastNews
from processor import process_single, _loads_maybe

def log(msg):
    with open("c:/oLRKM/scratch/fix_final_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(msg)

def fix_all_artist_tags_v3():
    log("--- [최종 아티스트 태그 정밀 수정 시작] ---")
    log("대상: ProcessedNews + PastNews (K-Enter 태그 기사)")
    
    try:
        with get_session() as session:
            recent = session.query(ProcessedNews).all()
            past = session.query(PastNews).all()
            
            targets = []
            for item in (recent + past):
                tags = _loads_maybe(item.artist_tags)
                # K-Enter가 포함되어 있거나 태그가 없는 경우 대상 포함
                if not tags or any(t.lower() == "k-enter" for t in tags):
                    targets.append(item)
                
            if not targets:
                log("수정할 대상이 없습니다. (모든 기사가 실명 태그를 가지고 있습니다.)")
                return

            log(f"총 {len(targets)}건의 태그를 실명으로 복구합니다.")

            success_count = 0
            for idx, item in enumerate(targets):
                # 1. ID로 찾기 시도
                raw_id = getattr(item, "raw_news_id", None) or getattr(item, "processed_news_id", None)
                raw = None
                if raw_id:
                    raw = session.query(RawNews).filter(RawNews.id == raw_id).first()
                
                # 2. [보강] ID가 없으면 URL로 원본 찾기 시도
                if not raw and item.url:
                    raw = session.query(RawNews).filter(RawNews.url == item.url).first()
                
                if not raw:
                    log(f"  ID={item.id} 원본 기사를 찾을 수 없어 스킵합니다. (URL={item.url[:30]}...)")
                    continue
                
                try:
                    # 개선된 프롬프트와 힌트 로직으로 재추출
                    result_payload, _ = process_single(raw)
                    raw_tags = result_payload.get("artist_tags", [])
                    
                    # 블랙리스트 단어 제거 및 청소
                    blacklist = ["k-enter", "k-pop", "kpop", "artist", "k-entertainment", "idol", "actor"]
                    new_tags = [t for t in raw_tags if t.lower() not in blacklist and len(t) > 1]
                    
                    if new_tags:
                        log(f"  ID={item.id} 성공: {new_tags}")
                        item.artist_tags = json.dumps(new_tags, ensure_ascii=False)
                        session.commit()
                        success_count += 1
                        if success_count % 5 == 0:
                            log(f"진행 상황: {success_count}/{len(targets)}건 성공")
                    else:
                        log(f"  ID={item.id} 기사: 실명 추출 실패 (결과: {raw_tags})")
                    
                    time.sleep(0.5) # API 부하 조절
                except Exception as e:
                    log(f"  ID={item.id} 가공 에러: {e}")
                    session.rollback()
            
            log(f"--- [최종 완료] 총 {success_count}건의 태그가 실명으로 복구되었습니다. ---")
    except Exception as e:
        log(f"치명적 시스템 오류: {e}")

if __name__ == "__main__":
    fix_all_artist_tags_v3()
