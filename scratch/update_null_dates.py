import sqlite3
import re
from datetime import datetime

def extract_date_from_text(text: str, url: str) -> datetime | None:
    # 1. URL 패턴
    url_matches = [
        re.search(r"/(\d{4})[./-]([01]?\d)[./-]([0-3]?\d)", url),
        re.search(r"/(\d{4})(\d{2})(\d{2})/", url),
        re.search(r"(_|-)(\d{4})(\d{2})(\d{2})", url),
    ]
    for m in url_matches:
        if m:
            try:
                groups = [g for g in m.groups() if g and g.isdigit()]
                if len(groups) >= 3:
                    return datetime(int(groups[0]), int(groups[1]), int(groups[2]))
            except Exception:
                continue

    # 2. 메타 태그 검색
    meta_match = re.search(r'property="(?:article:published_time|published_date|og:pubdate)"\s+content="(\d{4}-\d{2}-\d{2})', text)
    if not meta_match:
        meta_match = re.search(r'content="(\d{4}-\d{2}-\d{2}).*?property="(?:article:published_time|published_date|og:pubdate)"', text)
    if meta_match:
        try:
            return datetime.strptime(meta_match.group(1), "%Y-%m-%d")
        except Exception:
            pass

    # 3. 본문 전체 검색
    ko_match = re.search(
        r"(?:입력|기사입력|등록|수정|발행|일시|날짜|발행일)\s*[:]?\s*(\d{4})[./-]([01]?\d)[./-]([0-3]?\d)",
        text,
    )
    if ko_match:
        try:
            return datetime(int(ko_match.group(1)), int(ko_match.group(2)), int(ko_match.group(3)))
        except Exception:
            pass

    # 4. 영문 발행일 패턴
    months = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December"
    mon_dict = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
    
    en_match_a = re.search(fr"(?:Published|Updated|Posted|Date).*?(\d{{1,2}})\s+({months})\.?\s+(\d{{4}})", text, re.IGNORECASE | re.DOTALL)
    if en_match_a:
        try:
            mon_str = en_match_a.group(2)[:3].capitalize()
            return datetime(int(en_match_a.group(3)), mon_dict[mon_str], int(en_match_a.group(1)))
        except Exception:
            pass

    en_match_b = re.search(fr"(?:Published|Updated|Posted|Date).*?({months})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})", text, re.IGNORECASE | re.DOTALL)
    if en_match_b:
        try:
            mon_str = en_match_b.group(1)[:3].capitalize()
            return datetime(int(en_match_b.group(3)), mon_dict[mon_str], int(en_match_b.group(2)))
        except Exception:
            pass

    # 5. 단순 날짜
    lines = text.split("\n")
    check_text = "\n".join(lines[:10] + lines[-10:])
    simple_match = re.search(r"(\d{4})[./-]([01]?\d)[./-]([0-3]?\d)", check_text)
    if simple_match:
        try:
            return datetime(int(simple_match.group(1)), int(simple_match.group(2)), int(simple_match.group(3)))
        except Exception:
            pass

    return None

def update_null_dates():
    conn = sqlite3.connect('k_enter_news.db')
    c = conn.cursor()
    c.execute('SELECT id, content, url FROM raw_news WHERE published_at IS NULL')
    rows = c.fetchall()
    print(f"Checking {len(rows)} articles with NULL published_at...")
    updated_count = 0
    for row_id, content, url in rows:
        dt = extract_date_from_text(content, url)
        if dt:
            dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            c.execute('UPDATE raw_news SET published_at = ? WHERE id = ?', (dt_str, row_id))
            c.execute('UPDATE processed_news SET published_at = ? WHERE raw_news_id = ?', (dt_str, row_id))
            updated_count += 1
    conn.commit()
    print(f"Successfully updated {updated_count} records.")
    conn.close()

if __name__ == "__main__":
    update_null_dates()
