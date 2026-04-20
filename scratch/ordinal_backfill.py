import sqlite3
import re
from datetime import datetime

def extract_date_magic_v3(text: str, url: str) -> datetime | None:
    # 1. 서수(7th) 및 By 키워드 지원 영문 로직
    months = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December"
    mon_dict = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
    
    # 패턴 A: By/Published ... 7th April 2026
    en = re.search(fr"(?:Published|Updated|Posted|Date|First published|By).*?(\d{{1,2}})(?:st|nd|rd|th)?\s+({months})\.?\s+(\d{{4}})", text, re.I | re.DOTALL)
    if en:
        try:
            m = en.group(2)[:3].capitalize()
            return datetime(int(en.group(3)), mon_dict[m], int(en.group(1)))
        except: pass
    
    # 패턴 B: By/Published ... April 7th, 2026
    en2 = re.search(fr"(?:Published|Updated|Posted|Date|First published|By).*?({months})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", text, re.I | re.DOTALL)
    if en2:
        try:
            m = en2.group(1)[:3].capitalize()
            return datetime(int(en2.group(3)), mon_dict[m], int(en2.group(2)))
        except: pass

    # 2. 이미지 URL 경로 추적 (중앙일보용)
    img_date = re.search(r"/(\d{4})([01]\d)/([0-3]\d)/", text)
    if img_date:
        try:
            return datetime(int(img_date.group(1)), int(img_date.group(2)), int(img_date.group(3)))
        except: pass

    # 3. 한국어 키워드
    ko = re.search(r"(?:입력|등록|발행|일시|날짜|발행일)\s*[:]?\s*(\d{4})[./-]([01]?\d)[./-]([0-3]?\d)", text)
    if ko:
        try: return datetime(int(ko.group(1)), int(ko.group(2)), int(ko.group(3)))
        except: pass

    return None

def final_ordinal_backfill():
    conn = sqlite3.connect('k_enter_news.db')
    c = conn.cursor()
    c.execute('SELECT id, content, url FROM raw_news WHERE published_at IS NULL')
    rows = c.fetchall()
    
    count = 0
    for rid, content, url in rows:
        dt = extract_date_magic_v3(content, url)
        if dt:
            dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            c.execute('UPDATE raw_news SET published_at = ? WHERE id = ?', (dt_str, rid))
            c.execute('UPDATE processed_news SET published_at = ? WHERE raw_news_id = ?', (dt_str, rid))
            count += 1
    
    conn.commit()
    print(f"Ordinal backfill: {count} records recovered via ordinal/By patterns.")
    conn.close()

if __name__ == "__main__":
    final_ordinal_backfill()
