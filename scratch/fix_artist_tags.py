import sys
import os
import json
import time

# 현재 작업 디렉토리를 파이썬 경로에 추가
sys.path.append(os.getcwd())

from database import get_session, RawNews, ProcessedNews, PastNews
from processor import process_single, _loads_maybe

def fix_generic_artist_tags():
    """K-Enter 등 범용 태그로 저장된 뉴스들의 태그를 재추출하여 수정"""
    with get_session() as session:
        # 1. 수정 대상 찾기 (ProcessedNews)
        recent_targets = session.query(ProcessedNews).all()
        past_targets = session.query(PastNews).all()
        
        all_targets = []
        for item in (recent_targets + past_targets):
            tags = _loads_maybe(item.artist_tags)
            # K-Enter가 포함되어 있거나 태그가 아예 없는 경우 대상에 포함
            if not tags or any(t.lower() == "k-enter" for t in tags):
                all_targets.append(item)

        if not all_targets:
            print("수정할 대상(K-Enter 태그 등)이 없습니다.")
            return

        print(f"총 {len(all_targets)}건의 뉴스 태그를 재추출합니다...")

        success_count = 0
        for item in all_targets:
            # 원본 RawNews 찾기
            raw_id = getattr(item, "raw_news_id", None) or getattr(item, "processed_news_id", None)
            if not raw_id:
                continue
                
            raw = session.query(RawNews).filter(RawNews.id == raw_id).first()
            if not raw:
                continue

            try:
                print(f"  → ID={item.id} 재추출 중: {item.ko_title[:30]}...")
                # 개선된 로직으로 다시 가공
                result_payload, _ = process_single(raw)
                new_tags = result_payload.get("artist_tags", [])
                
                if new_tags:
                    print(f"    [변경] {item.artist_tags} -> {new_tags}")
                    item.artist_tags = json.dumps(new_tags, ensure_ascii=False)
                    
                    # PastNews의 경우 artist_name 필드도 업데이트
                    if isinstance(item, PastNews):
                        item.artist_name = new_tags[0] if new_tags else "K-Enter"
                    
                    session.commit()
                    success_count += 1
                
                time.sleep(0.5) # API 부하 방지
            except Exception as e:
                session.rollback()
                print(f"    [오류] ID={item.id}: {e}")

        print(f"최종 완료: {success_count}건의 태그가 정교하게 수정되었습니다.")

if __name__ == "__main__":
    fix_generic_artist_tags()
