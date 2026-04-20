import sqlite3
import re
import collections

# crawler1.py에서 최신 로직 복사 (10글자 지원)
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
    combined = f"{title} {content[:1000]}"
    en_names = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", combined)
    ko_keywords = re.findall(r"[가-힣]{2,10}", combined) # 10글자로 확장
    filtered_ko = [k for k in ko_keywords if k not in _KO_STOPWORDS]
    counts = collections.Counter(en_names + filtered_ko)
    top_hints = [item[0] for item in counts.most_common(10)]
    return ", ".join(top_hints) if top_hints else ""

def update_hints_v10():
    conn = sqlite3.connect('k_enter_news.db')
    c = conn.cursor()
    c.execute('SELECT id, title, content FROM raw_news')
    rows = c.fetchall()
    print(f"Updating hints for {len(rows)} records with 10-char logic...")
    
    count = 0
    for rid, title, content in rows:
        pure_content = content
        if content.startswith("[ARTIST_HINT]"):
            parts = content.split("\n", 1)
            if len(parts) > 1:
                pure_content = parts[1]
        
        new_hint = extract_person_hint(title, pure_content)
        final_content = f"[ARTIST_HINT]{new_hint}\n{pure_content}"
        
        c.execute('UPDATE raw_news SET content = ? WHERE id = ?', (final_content, rid))
        count += 1
    
    conn.commit()
    print(f"Successfully updated hints for {count} records.")
    conn.close()

if __name__ == "__main__":
    update_hints_v10()
