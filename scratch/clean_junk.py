import sys
import os
import json

sys.path.append(os.getcwd())
from database import get_session, RawNews, ProcessedNews, PastNews
from processor import process_single, _loads_maybe

def clean_junk_tags():
    print("--- [태그 품질 정밀 정화 시작] ---")
    blacklist = ["있어", "똑같", "실물", "사진과", "대통령도", "진짜", "누가", "포착", "근황"]
    
    with get_session() as session:
        recent = session.query(ProcessedNews).all()
        past = session.query(PastNews).all()
        
        targets = []
        for item in (recent + past):
            tags = _loads_maybe(item.artist_tags)
            # 블랙리스트 단어가 포함되어 있다면 재가공 대상으로 선정
            if any(t in blacklist for t in tags):
                targets.append(item)
        
        if not targets:
            print("정화할 대상이 없습니다. (태그 품질이 양호합니다.)")
            return

        print(f"총 {len(targets)}건의 저품질 태그를 발견했습니다. 정밀 정화를 시작합니다...")
        
        success_count = 0
        for item in targets:
            raw_id = getattr(item, "raw_news_id", None) or getattr(item, "processed_news_id", None)
            raw = None
            if raw_id:
                raw = session.query(RawNews).filter(RawNews.id == raw_id).first()
            if not raw and item.url:
                raw = session.query(RawNews).filter(RawNews.url == item.url).first()
            
            if not raw: continue
            
            try:
                print(f"  ID={item.id} 정화 중: {item.ko_title[:20]}...")
                result, _ = process_single(raw)
                new_tags = result.get("artist_tags", [])
                
                print(f"    [변경] {item.artist_tags} -> {new_tags}")
                item.artist_tags = json.dumps(new_tags, ensure_ascii=False)
                session.commit()
                success_count += 1
            except Exception as e:
                print(f"    [에러] ID={item.id}: {e}")
                session.rollback()

if __name__ == "__main__":
    clean_junk_tags()
