"""
processor.py — LLM 가공 + 지능형 이미지 수집
"""

import os
import sys
import io
import json
import time
import requests
import re
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import quote
from contextlib import contextmanager

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 윈도우 터미널 인코딩 에러 방지
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from playwright.sync_api import sync_playwright
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from openai import OpenAI
from pydantic import ValidationError
from database import RawNews, ProcessedNews, PastNews, get_session
from schemas import KpopNewsSummary, summary_to_processed_payload

from prompts.processingprompt import get_summary_prompts

# 프롬프트 불러오기
SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT_TEMPLATE = get_summary_prompts()

# ═══════════════════════════════════════════════════
# Part 0: 불량 데이터 필터링 (Junk Filter)
# ═══════════════════════════════════════════════════

def is_junk_raw_news(raw: RawNews) -> tuple[bool, str]:
    title = (raw.title or "").strip()
    content = (raw.content or "").strip()

    if len(content) < 200:
        return True, "본문 내용이 너무 짧음 (추출 실패 가능성)"

    junk_titles = ["KBS", "SBS", "SBS연예", "Daum", "MBC", "JTBC", "네이버", "Naver", "Daum | 문화"]
    if title in junk_titles:
        return True, f"포털/방송사 메인 페이지 추정 (제목: {title})"

    links = re.findall(r"\[.*?\]\(.*?\)", content)
    if len(content) > 0:
        link_ratio = (len(links) * 40) / len(content)
        if link_ratio > 0.6:
            return True, "링크 밀도가 높은 메뉴판/네비게이션 데이터"

    nav_keywords = ["바로가기", "GNB", "LNB", "검색창", "로그인", "About KBS"]
    match_count = sum(1 for kw in nav_keywords if kw in content)
    if match_count >= 3:
        return True, "네비게이션 키워드 다수 발견"

    return False, ""

# ═══════════════════════════════════════════════════
# Part 1: LLM 가공 (raw_news → processed_news)
# ═══════════════════════════════════════════════════

client = OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
LLM_MODEL = "gemma3:latest"
LLM_DELAY = 0.5

def repair_json(raw: str) -> str:
    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"\s*```", "", raw).strip()
    return raw

def extract_names_from_title(title: str) -> list[str]:
    if not title: return []
    en_names = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", title)
    ko_names = re.findall(r'[\'"](.+?)[\'"]', title)
    ko_candidates = re.findall(r"\b[가-힣]{2,10}\b", title)
    return list(set(en_names + ko_names + ko_candidates))

def process_single(raw: RawNews) -> dict:
    full_content = raw.content or ""
    artist_hint_from_db = ""
    clean_content_text = full_content
    
    if full_content.startswith("[ARTIST_HINT]"):
        parts = full_content.split("\n", 1)
        artist_hint_from_db = parts[0].replace("[ARTIST_HINT]", "").strip()
        clean_content_text = parts[1] if len(parts) > 1 else ""

    title_names = extract_names_from_title(raw.title or "")
    combined_hint = artist_hint_from_db
    if title_names:
        combined_hint = (combined_hint + ", " + ", ".join(title_names)).strip(", ")

    user_message = SUMMARY_USER_PROMPT_TEMPLATE.format(
        title=raw.title or "",
        content=clean_content_text[:3000],
        raw_category_hint=f"{raw.category} / {raw.sub_category}",
        raw_artist_hint=combined_hint if combined_hint else "없음",
    )

    response = client.chat.completions.create(
        model=LLM_MODEL,
        temperature=0.3,
        timeout=120,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    raw_text = response.choices[0].message.content or ""
    fixed_text = repair_json(raw_text)
    result_dict = json.loads(fixed_text)

    ai_tags = result_dict.get("artist_tags", [])
    if not isinstance(ai_tags, list): ai_tags = []
    final_tags = [t.strip() for t in ai_tags if len(t.strip()) > 1]
    final_tags = list(dict.fromkeys(final_tags))
    # [FIX] 제거: final_tags if final_tags else ["K-Enter"]
    result_dict["artist_tags"] = final_tags

    # source_name 리스트 변환 (Pydantic 에러 방지)
    s_name = result_dict.get("source_name", "")
    if isinstance(s_name, list):
        result_dict["source_name"] = ", ".join(map(str, s_name))

    validated = KpopNewsSummary(**result_dict)
    payload = summary_to_processed_payload(raw.id, validated)
    
    payload.update({
        "url": raw.url,
        "published_at": raw.published_at,
        "crawled_at": raw.crawled_at,
        "trend_insight": None
    })

    if not payload.get("source_name"):
        if raw.url:
            from urllib.parse import urlparse
            netloc = urlparse(raw.url).netloc.replace("www.", "")
            payload["source_name"] = netloc.split(".")[0].capitalize()
        else:
            payload["source_name"] = "Unknown"

    return payload, validated.image_search_query

def process_and_save(session, batch_size: int = 50) -> int:
    unprocessed = session.query(RawNews).filter(RawNews.is_processed == False).limit(batch_size).all()
    if not unprocessed: return -1

    processed_count = 0
    threshold_date = (datetime.now() - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)

    for raw in unprocessed:
        try:
            # 0. Junk 필터링
            is_junk, junk_reason = is_junk_raw_news(raw)
            if is_junk:
                raw.is_processed = True
                raw.skip_reason = f"JunkFilter: {junk_reason}"
                session.commit()
                continue

            # 1. AI 가공
            print(f"  → 가공 중: {raw.title[:40]}...")
            result_payload, ai_query = process_single(raw)
            time.sleep(LLM_DELAY)

            # 2. K-엔터 체크
            if not result_payload.get("is_k_ent", True):
                raw.is_processed = True
                raw.skip_reason = "NotKEnt: AI judged as non-K-ent news"
                session.commit()
                continue

            # 3. 실시간 이미지 수집
            if not result_payload.get("thumbnail_url"):
                artists = result_payload.get("artist_tags")
                artist_name = artists[0] if artists else None
                img_query = ai_query.strip() if ai_query and ai_query.strip() else build_query_for_processed(result_payload)[0]
                
                print(f"    📸 이미지 검색 중: {img_query}")
                image_url = pick_non_duplicate_bing_image(session, img_query, artist_name=artist_name, headless=True)
                if image_url: result_payload["thumbnail_url"] = image_url

            # 4. 분기 저장
            pub_at = raw.published_at
            if pub_at and pub_at >= threshold_date:
                session.add(ProcessedNews(**result_payload))
            else:
                result_payload.pop("raw_news_id", None)
                session.add(PastNews(**result_payload))

            raw.is_processed = True
            raw.skip_reason = None
            session.commit()
            processed_count += 1

        except ValidationError as e:
            print(f"    [스킵] AI 스키마 파괴 (총 {len(e.errors())}개 오류)")
            reason = f"ValidationError: {e.errors()[0]['msg']}"
            for err in e.errors()[:3]:
                loc = ".".join(str(x) for x in err["loc"])
                print(f"      - 필드 [{loc}]: {err['msg']}")
            
            session.rollback() # 트랜잭션 취소 후
            raw = session.query(RawNews).filter(RawNews.id == raw.id).first() # 객체 다시 로드
            raw.is_processed = True
            raw.skip_reason = reason
            session.commit()
        except Exception as e:
            print(f"    [스킵] 오류: {str(e).splitlines()[0]}")
            reason = f"SystemError: {str(e)[:200]}"
            session.rollback()
            raw = session.query(RawNews).filter(RawNews.id == raw.id).first()
            raw.is_processed = True
            raw.skip_reason = reason
            session.commit()

    return processed_count

# ═══════════════════════════════════════════════════
# Part 2: 이미지 수집 (Bing 이미지 검색)
# ═══════════════════════════════════════════════════

def _loads_maybe(v):
    if v is None: return []
    if isinstance(v, list): return v
    try:
        obj = json.loads(v)
        return obj if isinstance(obj, list) else []
    except: return []

def _clean_query(text: str) -> str:
    return " ".join((text or "").split()).strip()

def _norm_url(url: str | None) -> str:
    return (url or "").strip()

def _is_good_image_url(url: str) -> bool:
    if not url: return False
    low = url.lower()
    bad = ["logo", "sprite", "icon", ".svg", "r.bing.com"]
    return low.startswith("http") and not any(k in low for k in bad)

def get_all_used_thumbnail_urls(session) -> set[str]:
    processed_rows = session.query(ProcessedNews.thumbnail_url).filter(ProcessedNews.thumbnail_url != "").all()
    return {_norm_url(r[0]) for r in processed_rows if r[0]}

def get_used_urls_for_artist(session, artist_name: str) -> set[str]:
    name = (artist_name or "").strip()
    if not name: return set()
    used = set()
    rows = session.query(ProcessedNews.artist_tags, ProcessedNews.thumbnail_url).filter(ProcessedNews.thumbnail_url != "").all()
    for tags, thumb in rows:
        arr = [str(x).strip().lower() for x in _loads_maybe(tags)]
        if name.lower() in arr and thumb:
            used.add(_norm_url(thumb))
    return used

def extract_bing_image_candidates(query: str, headless: bool = True, max_candidates: int = 20) -> list[str]:
    query = _clean_query(query)
    if not query: return []
    search_url = f"https://www.bing.com/images/search?q={quote(query)}&form=HDRSC3"

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=headless, args=["--no-sandbox"])
            context = browser.new_context(user_agent="Mozilla/5.0 ...")
            page = context.new_page()
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            
            cards = page.locator("a.iusc")
            results = []
            seen = set()
            for i in range(min(cards.count(), 60)):
                m_attr = cards.nth(i).get_attribute("m")
                if m_attr:
                    try:
                        m_json = json.loads(m_attr)
                        url = _norm_url(m_json.get("murl"))
                        if _is_good_image_url(url) and url not in seen:
                            seen.add(url); results.append(url)
                    except: pass
                if len(results) >= max_candidates: break
            browser.close()
            return results
        except: return []

def pick_non_duplicate_bing_image(session, query: str, artist_name: str = None, headless: bool = True) -> str | None:
    candidates = extract_bing_image_candidates(query, headless=headless)
    if not candidates: return None
    all_used = get_all_used_thumbnail_urls(session)
    artist_used = get_used_urls_for_artist(session, artist_name) if artist_name else set()

    for url in candidates:
        if url not in all_used and url not in artist_used: return url
    for url in candidates:
        if url not in artist_used: return url
    return candidates[0]

BAD_QUERY_KEYWORDS = ["teaser", "official", "comeback", "new", "video", "photo"]

def build_query_for_processed(article) -> tuple[str, str]:
    """[개선된 지능형 이미지 검색어 생성 로직]"""
    if isinstance(article, dict):
        artists = article.get("artist_tags", [])
        keywords = article.get("keywords", [])
        cat = article.get("sub_category", "")
        title = article.get("ko_title", "")
    else:
        artists = _loads_maybe(getattr(article, "artist_tags", None))
        keywords = _loads_maybe(getattr(article, "keywords", None))
        cat = getattr(article, "sub_category", "")
        title = getattr(article, "ko_title", "") or getattr(article, "title", "")

    # [개선 1] 유효 아티스트 필터링
    valid_artists = [str(a).strip() for a in artists if str(a).strip().lower() not in ["k-enter", "신인"]]
    
    # [개선 2] 스마트 따옴표 추출
    quotes = re.findall(r"['\"‘“](.*?)['\"’”]", title)
    extra_context = ""
    for q in quotes:
        q_clean = q.strip()
        if q_clean not in valid_artists and len(q_clean) > 1:
            if q_clean.lower() not in BAD_QUERY_KEYWORDS:
                extra_context = q_clean
                break

    # [개선 3] 검색어 조합
    query_base = " ".join(valid_artists[:2]) if valid_artists else (keywords[0] if keywords else title[:20])
    final_query = f"{query_base} {extra_context}".strip()

    # [개선 4] 카테고리별 맞춤 수식어
    suffix = "2026 recent official photo HQ"
    if any(kw in (cat or "") for kw in ["드라마", "배우"]):
        suffix = "2026 drama still cut official"
    
    return f"{final_query} {suffix}".strip(), (valid_artists[0] if valid_artists else "")

def fetch_images_for_processed(session, headless: bool = True, overwrite: bool = False):
    """최신 및 과거 기사 이미지 모두 수집"""
    q_recent = session.query(ProcessedNews)
    if not overwrite: q_recent = q_recent.filter(or_(ProcessedNews.thumbnail_url.is_(None), ProcessedNews.thumbnail_url == ""))
    
    q_past = session.query(PastNews)
    if not overwrite: q_past = q_past.filter(or_(PastNews.thumbnail_url.is_(None), PastNews.thumbnail_url == ""))
    
    articles = q_recent.all() + q_past.all()
    print(f"\n[이미지 수집] 총 {len(articles)}건 처리 시작...")

    for article in articles:
        q, name = build_query_for_processed(article)
        print(f"📸 수집 중 (ID={article.id}): {q}")
        url = pick_non_duplicate_bing_image(session, q, artist_name=name, headless=headless)
        if url:
            article.thumbnail_url = url
            session.commit()
        time.sleep(1.0)

if __name__ == "__main__":
    with get_session() as session:
        print("\n🚀 [뉴스 가공 파이프라인 시작]")
        total_processed = 0
        batch_count = 1
        while True:
            print(f"\n--- [{batch_count}회차 세트] 5개 가공 시작 ---")
            count = process_and_save(session, batch_size=5)
            if count == -1: break
            total_processed += count
            print("📸 현재 세트 이미지 수집 중...")
            fetch_images_for_processed(session, headless=True)
            batch_count += 1
        print(f"\n🏁 최종 완료! 총 {total_processed}건 처리되었습니다.")