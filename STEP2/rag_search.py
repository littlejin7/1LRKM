import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from STEP2.tts import text_to_speech, TTS_OUTPUT_PATH
import ollama
import json

from database import SessionLocal, ProcessedNews
from STEP2.vectorstore import get_stores

# ===================== CONFIG =====================
OLLAMA_MODEL = "gemma3:latest"

# ==================================================

# ── 아티스트 이름 정규화 매핑 ──────────────────────────────────────────────────
ARTIST_MAP = {
    "babymonster": "베이비몬스터",
    "baby monster": "베이비몬스터",
    "베이비 몬스터": "베이비몬스터",
    "baemon": "베이비몬스터",
    "blackpink": "블랙핑크",
    "black pink": "블랙핑크",
    "블랙 핑크": "블랙핑크",
    "newjeans": "뉴진스",
    "new jeans": "뉴진스",
    "뉴 진스": "뉴진스",
    "bts": "방탄소년단",
    "bangtan": "방탄소년단",
    "방탄": "방탄소년단",
    "aespa": "에스파",
    "ive": "아이브",
    "lesserafim": "르세라핌",
    "le sserafim": "르세라핌",
    "straykids": "스트레이 키즈",
    "stray kids": "스트레이 키즈",
    "seventeen": "세븐틴",
    "twice": "트와이스",
}


def normalize_artist(name: str) -> str:
    if not name or not isinstance(name, str):
        return ""
    clean_name = name.lower().replace(" ", "").strip()
    for k, v in ARTIST_MAP.items():
        if k.replace(" ", "") == clean_name:
            return v
    return name.strip()


def _parse(val):
    if not val:
        return []
    if isinstance(val, list):
        return val
    current = val
    for _ in range(3):
        if not isinstance(current, str):
            break
        try:
            cleaned = current.strip()
            if cleaned.startswith("'") or "[ '" in cleaned:
                cleaned = cleaned.replace("'", '"')
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return parsed
            current = parsed
        except:
            break
    if isinstance(current, str) and current.startswith("[") and current.endswith("]"):
        try:
            items = current[1:-1].split(",")
            return [i.strip().strip("'").strip('"') for i in items if i.strip()]
        except:
            pass
    return [current] if current and isinstance(current, str) else []


# ===================== STATE =====================
class NewsState(TypedDict):
    top_news_list: List[Dict[str, Any]]
    related_news_map: Dict[int, List[Dict]]
    summaries_map: Dict[int, str]
    report_text: str
    tts_output_path: str


# ===================== 노드 함수 =====================


def fetch_top_news(state: NewsState) -> NewsState:
    print(" [노드 1] 뉴스 추출 중...")

    import sqlite3 as _sqlite3

    _ROOT = Path(__file__).resolve().parent.parent
    conn = _sqlite3.connect(str(_ROOT / "k_enter_news.db"))
    conn.row_factory = _sqlite3.Row
    cursor = conn.cursor()

    category_limits = {
        "컨텐츠 & 작품": 30,
        "인물 & 아티스트": 30,
        "비즈니스 & 행사": 30,
    }

    raw_rows = []
    for category, limit in category_limits.items():
        cursor.execute(
            "SELECT p.id, p.category, p.sub_category, p.summary, p.keywords, p.artist_tags,"
            " p.importance, p.importance_reason, p.trend_insight, p.source_name,"
            " p.published_at, p.timeline, p.ko_title"
            " FROM processed_news p"
            " WHERE p.importance IS NOT NULL AND p.category = ?"
            " ORDER BY p.importance DESC, p.id DESC LIMIT ?",
            (category, limit),
        )
        raw_rows.extend(cursor.fetchall())
    conn.close()

    seen_artists = set()
    final_news_list = []
    remained_pool = []

    for category in category_limits.keys():
        cat_count = 0
        cat_rows = [r for r in raw_rows if r["category"] == category]

        for row in cat_rows:
            tags = _parse(row["artist_tags"])
            norm_tags = [normalize_artist(t) for t in tags if isinstance(t, str)]

            primary_artist = None
            if norm_tags:
                for t in norm_tags:
                    if t and t.strip():
                        primary_artist = t.strip()
                        break

            is_dup = False
            if primary_artist and primary_artist in seen_artists:
                is_dup = True

            news_obj = {
                "id": row["id"],
                "title": row["ko_title"] or "",
                "summary": _parse(row["summary"]),
                "keywords": _parse(row["keywords"]),
                "artist_tags": norm_tags,
                "importance": row["importance"],
                "importance_reason": row["importance_reason"] or "",
                "sub_category": row["sub_category"] or "",
                "category": row["category"] or "",
                "trend_insight": row["trend_insight"] or "",
                "source_name": row["source_name"] or "",
                "published_at": str(row["published_at"]) if row["published_at"] else "",
                "timeline": _parse(row["timeline"]),
            }

            if not is_dup and cat_count < 4:
                if primary_artist:
                    seen_artists.add(primary_artist)
                final_news_list.append(news_obj)
                cat_count += 1
            else:
                remained_pool.append(news_obj)

    # 10개가 안 채워지면 백업 풀에서 보충
    if len(final_news_list) < 10:
        remained_pool = sorted(
            remained_pool, key=lambda x: x["importance"], reverse=True
        )
        for news in remained_pool:
            tags = news.get("artist_tags", [])
            primary_artist = tags[0] if tags else None
            if primary_artist and primary_artist in seen_artists:
                continue
            if primary_artist:
                seen_artists.add(primary_artist)
            final_news_list.append(news)
            if len(final_news_list) >= 10:
                break

    final_news_list = sorted(
        final_news_list, key=lambda x: (x["importance"], x["id"]), reverse=True
    )

    for i, news in enumerate(final_news_list):
        print(
            f"  {i+1}위. [{news['sub_category']}][중요도:{news['importance']}] {news['title']}"
        )

    return {**state, "top_news_list": final_news_list}


def fetch_related_news(state: NewsState) -> NewsState:
    """[노드 2] 관련 과거뉴스 검색 및 한줄평 생성"""
    print("\n [노드 2] 관련 과거뉴스 검색 및 한줄평 생성 중...")
    _, past_store = get_stores()
    top_news_list = state["top_news_list"]
    related_news_map = {}
    summaries_map = {}

    for i, news in enumerate(top_news_list):
        query_text = news["title"] + " " + " ".join(news["keywords"])
        results = past_store.similarity_search_with_score(query_text, k=10)
        related = [
            {"content": doc.page_content, "metadata": doc.metadata, "score": score}
            for doc, score in results
            if 30 <= int((1 - score) * 100) <= 75
        ][:3]
        related_news_map[i] = related

        summary_text = (
            " ".join(
                [
                    item.get("content", "") if isinstance(item, dict) else str(item)
                    for item in news["summary"]
                ]
            )
            if news["summary"]
            else ""
        )
        related_text = (
            "\n".join(
                [
                    f"- 과거 뉴스 {j+1}: {r['content'][:500]}"
                    for j, r in enumerate(related)
                ]
            )
            if related
            else "관련 과거 뉴스 없음"
        )

        prompt = f"""당신은 방대한 데이터를 관통하는 통찰을 한 줄로 요약하는 '수석 전략가'입니다.
과거의 기록들과 현재의 사건을 연결하여, 지금 이 현상이 산업 전체에 던지는 핵심 메시지를 단 한 문장으로 정의하십시오.

[현재 뉴스]
- 제목: {news['title']}
- 요약: {summary_text}

[과거 관련 기록]
{related_text}

분석 및 작성 가이드:
1. 핵심 관통: 단순히 정보를 나열하지 말고, 과거의 패턴이 현재 어떻게 '결실'을 맺었거나 '새로운 국면'으로 전환되었는지 그 본질을 짚으십시오.
2. 구체성 유지: 무의미한 추상적 표현 대신, 구체적인 산업 현상이나 가치를 담으십시오.
3. 문장 스타일: 통찰을 담은 한 문장으로 작성하십시오.
4. 엄격한 규칙: 오직 한 문장만 출력하십시오.

핵심 인사이트:"""

        response = ollama.chat(
            model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}]
        )
        summary = response["message"]["content"].strip()
        summaries_map[i] = summary
        print(f"  {i+1}위 '{news['title'][:30]}' 한줄평 완료")

    import sqlite3 as _sqlite3

    _ROOT = Path(__file__).resolve().parent.parent
    conn = _sqlite3.connect(str(_ROOT / "k_enter_news.db"))
    try:
        for i, news in enumerate(top_news_list):
            conn.execute(
                "UPDATE processed_news SET trend_insight = ? WHERE id = ?",
                (summaries_map[i], news["id"]),
            )
        conn.commit()
        print("\n   trend_insight DB 저장 완료")
    except Exception as e:
        print(f"\n   trend_insight DB 저장 실패: {e}")
    finally:
        conn.close()

    return {"related_news_map": related_news_map, "summaries_map": summaries_map}


def generate_report(state: NewsState) -> NewsState:
    """[노드 3] 보고서 TTS 보고서 생성"""
    print("\n [노드 3] 요약 보고서 생성 중...")
    top_news_list = state["top_news_list"]
    summaries_map = state["summaries_map"]
    report_lines = ["안녕하세요. 오늘의 주요 뉴스 브리핑을 전해드립니다."]
    for i, news in enumerate(top_news_list):
        summary = summaries_map.get(i, "")
        report_lines.append(f"{i+1}위 뉴스는, {summary}")
    report_lines.append("이상으로 오늘의 주요 뉴스 브리핑이었습니다.")
    report_text = " ".join(report_lines)
    with open("./news_report.txt", "w", encoding="utf-8") as f:
        f.write(report_text)
    return {"report_text": report_text}


def run_tts(state: NewsState) -> NewsState:
    """[노드 4] 보고서 텍스트를 TTS로 변환"""
    print("\n [노드 4] TTS 변환 중...")
    ko_path = text_to_speech(state["report_text"], TTS_OUTPUT_PATH)
    return {"tts_output_path": ko_path}


def build_graph() -> StateGraph:
    graph = StateGraph(NewsState)
    graph.add_node("fetch_top_news", fetch_top_news)
    graph.add_node("fetch_related_news", fetch_related_news)
    graph.add_node("generate_report", generate_report)
    graph.add_node("run_tts", run_tts)
    graph.set_entry_point("fetch_top_news")
    graph.add_edge("fetch_top_news", "fetch_related_news")
    graph.add_edge("fetch_related_news", "generate_report")
    graph.add_edge("generate_report", "run_tts")
    graph.add_edge("run_tts", END)
    return graph.compile()


if __name__ == "__main__":
    app = build_graph()
    initial_state: NewsState = {
        "top_news_list": [],
        "related_news_map": {},
        "summaries_map": {},
        "report_text": "",
        "tts_output_path": "",
    }
    final_state = app.invoke(initial_state)
    print("✅ 파이프라인 완료!")
