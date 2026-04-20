import sqlite3
import re
from datetime import datetime, timezone
import collections

# crawler1.py에서 최신 로직 복사
_KO_STOPWORDS = {
    "기자", "뉴스", "연예", "기사", "오늘", "내일", "이번", "지난", "어제", "내용",
    "이후", "과거", "현재", "사실", "관련", "대해", "통해", "위해", "대한", "때문",
    "가운데", "지난해", "올해", "내년", "오전", "오후", "최근", "하루", "이날", "이후",
    "스타", "연예인", "가수", "배우", "아이돌", "그룹", "팬덤", "무대", "공연", "콘서트",
    "앨범", "차트", "컴백", "데뷔", "활동", "소식", "작품", "드라마", "영화", "예능",
    "장면", "사람", "하나", "모습", "생각", "이야기", "정도", "부분", "상태", "경우",
    "시작", "진행", "예정", "준비", "확인", "발표", "공개", "참여", "함께", "진심",
    "사랑", "응원", "기대", "감동", "화제", "눈길", "인기", "관심", "매력", "분위기",
    "세계", "글로벌", "해외", "국내", "한국", "문화", "산업", "시장", "현장", "지역"
}

def extract_person_hint(title: str, content: str) -> str:
    combined = f"{title} {content[:1500]}"
    en_names = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", combined)
    ko_names = re.findall(r"[가-힣]{2,4}", combined)
    filtered_ko = [n for n in ko_names if n not in _KO_STOPWORDS]
    counts = collections.Counter(en_names + filtered_ko)
    top_hints = [item[0] for item in counts.most_common(10)]
    return ", ".join(top_hints) if top_hints else ""

def extract_date_from_text(text: str, url: str) -> datetime | None:
    # URL 패턴
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

    # 메타 태그
    meta_match = re.search(r'property="(?:article:published_time|published_date|og:pubdate)"\s+content="(\d{4}-\d{2}-\d{2})', text)
    if not meta_match:
        meta_match = re.search(r'content="(\d{4}-\d{2}-\d{2}).*?property="(?:article:published_time|published_date|og:pubdate)"', text)
    if meta_match:
        try:
            return datetime.strptime(meta_match.group(1), "%Y-%m-%d")
        except Exception:
            pass

    # 본문 전체 검색
    ko_match = re.search(
        r"(?:입력|기사입력|등록|수정|발행|일시|날짜|발행일)\s*[:]?\s*(\d{4})[./-]([01]?\d)[./-]([0-3]?\d)",
        text,
    )
    if ko_match:
        try:
            return datetime(int(ko_match.group(1)), int(ko_match.group(2)), int(ko_match.group(3)))
        except Exception:
            pass
    
    # 영문 발행일 패턴 생략 (중앙일보 등 한국 사이트 위주 보강 목적)
    return None

def update_all_existing_data():
    conn = sqlite3.connect('k_enter_news.db')
    c = conn.cursor()
    c.execute('SELECT id, title, content, url FROM raw_news')
    rows = c.fetchall()
    print(f"Updating {len(rows)} records with latest logic...")
    
    update_count = 0
    for row_id, title, content, url in rows:
        # 1. 기존 힌트 제거하고 순수 본문만 추출
        pure_content = content
        if content.startswith("[ARTIST_HINT]"):
            parts = content.split("\n", 1)
            if len(parts) > 1:
                pure_content = parts[1]
        
        # 2. 날짜 재추출
        dt = extract_date_from_text(pure_content, url)
        dt_str = dt.strftime('%Y-%m-%d %H:%M:%S') if dt else None
        
        # 3. 아티스트 힌트 재추출
        hint = extract_person_hint(title, pure_content)
        final_content = f"[ARTIST_HINT]{hint}\n{pure_content}"
        
        # 4. 업데이트
        if dt_str:
            c.execute('UPDATE raw_news SET published_at = ?, content = ? WHERE id = ?', (dt_str, final_content, row_id))
            c.execute('UPDATE processed_news SET published_at = ? WHERE raw_news_id = ?', (dt_str, row_id))
        else:
            c.execute('UPDATE raw_news SET content = ? WHERE id = ?', (final_content, row_id))
            
        update_count += 1
        if update_count % 50 == 0:
            print(f"Progress: {update_count}/{len(rows)}...")
            
    conn.commit()
    print(f"Successfully updated total {update_count} records.")
    conn.close()

if __name__ == "__main__":
    update_all_existing_data()
