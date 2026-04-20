import sqlite3
import re
from datetime import datetime

def extract_date_ultra(text: str, url: str) -> datetime | None:
    # 1. 기존 로직 (URL, 메타태그, 본문 키워드)
    # URL에서 YYYY/MM/DD 또는 YYYY-MM-DD
    url_match = re.search(r"/(\d{4})[./-]([01]?\d)[./-]([0-3]?\d)", url)
    if url_match:
        try: return datetime(int(url_match.group(1)), int(url_match.group(2)), int(url_match.group(3)))
        except: pass

    # 메타 태그 (HTML 소스 포함된 경우)
    meta = re.search(r'content="(\d{4}-\d{2}-\d{2})', text)
    if meta:
        try: return datetime.strptime(meta.group(1), "%Y-%m-%d")
        except: pass

    # 한국어 키워드
    ko = re.search(r"(?:입력|등록|발행|일시|날짜)\s*[:]?\s*(\d{4})[./-]([01]?\d)[./-]([0-3]?\d)", text)
    if ko:
        try: return datetime(int(ko.group(1)), int(ko.group(2)), int(ko.group(3)))
        except: pass

    # 2. 영문 월 이름 기반 (Day가 없는 경우 포함)
    months = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December"
    mon_dict = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
    
    # 패턴: June 3, 2025 또는 3 June 2025
    en = re.search(fr"({months})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})", text, re.I)
    if en:
        try:
            m = en.group(1)[:3].capitalize()
            return datetime(int(en.group(3)), mon_dict[m], int(en.group(2)))
        except: pass
    
    en2 = re.search(fr"(\d{{1,2}})\s+({months})\.?\s+(\d{{4}})", text, re.I)
    if en2:
        try:
            m = en2.group(2)[:3].capitalize()
            return datetime(int(en2.group(3)), mon_dict[m], int(en2.group(1)))
        except: pass

    # 3. 최후의 보류: 연도와 월만 있는 경우 (일은 1일로 설정)
    # 예: June 2025
    en3 = re.search(fr"({months})\.?\s+(\d{{4}})", text, re.I)
    if en3:
        try:
            m = en3.group(1)[:3].capitalize()
            return datetime(int(en3.group(2)), mon_dict[m], 1)
        except: pass

    return None

def final_backfill():
    conn = sqlite3.connect('k_enter_news.db')
    c = conn.cursor()
    c.execute('SELECT id, content, url FROM raw_news WHERE published_at IS NULL')
    rows = c.fetchall()
    
    count = 0
    for rid, content, url in rows:
        dt = extract_date_ultra(content, url)
        if dt:
            dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            c.execute('UPDATE raw_news SET published_at = ? WHERE id = ?', (dt_str, rid))
            c.execute('UPDATE processed_news SET published_at = ? WHERE raw_news_id = ?', (dt_str, rid))
            count += 1
    
    conn.commit()
    print(f"Final backfill: {count} records recovered.")
    conn.close()

if __name__ == "__main__":
    final_backfill()
