import sqlite3
import re
from datetime import datetime

def extract_date_magic(text: str, url: str) -> datetime | None:
    # 1. 기존 강력 로직 (URL, 메타, 텍스트)
    # [기존 로직 생략 없이 포함]
    ko = re.search(r"(?:입력|등록|발행|일시|날짜|발행일)\s*[:]?\s*(\d{4})[./-]([01]?\d)[./-]([0-3]?\d)", text)
    if ko:
        try: return datetime(int(ko.group(1)), int(ko.group(2)), int(ko.group(3)))
        except: pass

    meta = re.search(r'property="(?:article:published_time|published_date|og:pubdate)"\s+content="(\d{4}-\d{2}-\d{2})', text)
    if meta:
        try: return datetime.strptime(meta.group(1), "%Y-%m-%d")
        except: pass

    # 2. 히든 카드: 본문 내 이미지 URL에서 날짜 추출 (중앙일보 필살기)
    # https://pds.joongang.co.kr/.../202512/26/...
    img_date = re.search(r"/(\d{4})([01]\d)/([0-3]\d)/", text)
    if img_date:
        try:
            return datetime(int(img_date.group(1)), int(img_date.group(2)), int(img_date.group(3)))
        except: pass

    # 3. 영문 월 이름 (다양한 조합)
    months = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December"
    mon_dict = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
    
    en = re.search(fr"({months})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})", text, re.I)
    if en:
        try:
            m = en.group(1)[:3].capitalize()
            return datetime(int(en.group(3)), mon_dict[m], int(en.group(2)))
        except: pass

    # 4. URL에서 숫자 연속 8자리 (YYYYMMDD)
    url_digit = re.search(r"(\d{4})(\d{2})(\d{2})", url)
    if url_digit:
        try:
            y, m, d = int(url_digit.group(1)), int(url_digit.group(2)), int(url_digit.group(3))
            if 2020 <= y <= 2026 and 1 <= m <= 12 and 1 <= d <= 31:
                return datetime(y, m, d)
        except: pass

    return None

def final_magic_backfill():
    conn = sqlite3.connect('k_enter_news.db')
    c = conn.cursor()
    c.execute('SELECT id, content, url FROM raw_news WHERE published_at IS NULL')
    rows = c.fetchall()
    
    count = 0
    for rid, content, url in rows:
        dt = extract_date_magic(content, url)
        if dt:
            dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            c.execute('UPDATE raw_news SET published_at = ? WHERE id = ?', (dt_str, rid))
            c.execute('UPDATE processed_news SET published_at = ? WHERE raw_news_id = ?', (dt_str, rid))
            count += 1
    
    conn.commit()
    print(f"Magic backfill: {count} records recovered via image/URL patterns.")
    conn.close()

if __name__ == "__main__":
    final_magic_backfill()
