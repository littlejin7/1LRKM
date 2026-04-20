import sqlite3
import re
import sys

# 인코딩 설정
sys.stdout.reconfigure(encoding='utf-8')

def is_junk_news_check(title: str, content: str, url: str) -> tuple[bool, str]:
    t = (title or "").strip().lower()
    c = (content or "").strip()
    u = (url or "").strip().lower()

    # 1. URL 패턴
    junk_url_patterns = ["/search/", "query=", "list.do", "newslist", "page=", "/archive/", "category/"]
    for p in junk_url_patterns:
        if p in u:
            return True, f"URL pattern: {p}"

    # 2. 제목 키워드
    junk_titles = ["search results", "검색결과", "목록", "index of", "highlights", "preview", "roundup"]
    if any(jt in t for jt in junk_titles):
        return True, "Junk title keyword"

    # 3. 링크 밀도
    links = re.findall(r"\[.*?\]\(.*?\)", c)
    if len(c) > 0:
        links_len = sum(len(m) for m in links)
        if (links_len / len(c)) > 0.45 or len(links) > 30: # 기준을 약간 더 보수적으로 조정
            return True, f"High link density ({len(links)} links)"

    # 4. 헤더 밀도
    headers = re.findall(r"^#{1,3} .*$", c, re.MULTILINE)
    if len(headers) >= 5:
        if len(c) / len(headers) < 350:
            return True, f"High header density ({len(headers)} headers)"

    return False, ""

def find_remaining_junk():
    conn = sqlite3.connect('k_enter_news.db')
    c = conn.cursor()
    c.execute('SELECT id, title, content, url FROM raw_news')
    rows = c.fetchall()
    
    junk_items = []
    for row_id, title, content, url in rows:
        is_junk, reason = is_junk_news_check(title, content, url)
        if is_junk:
            junk_items.append((row_id, title[:60], reason))
    
    print(f"Found {len(junk_items)} potential junk/navigation items:")
    for item in junk_items:
        print(f"ID: {item[0]} | Title: {item[1]} | Reason: {item[2]}")
    
    conn.close()

if __name__ == "__main__":
    find_remaining_junk()
