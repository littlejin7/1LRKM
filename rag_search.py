from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from tts import text_to_speech, TTS_OUTPUT_PATH
import ollama
import json

from database import SessionLocal, ProcessedNews
from vectorstore import get_stores

# ===================== CONFIG =====================
OLLAMA_MODEL = "gemma3:latest"
TOP_N = 10
RELATED_NEWS_COUNT = 3
# ==================================================


# ===================== STATE =====================
class NewsState(TypedDict):
    top_news_list: List[Dict[str, Any]]
    related_news_map: Dict[int, List[Dict]]
    summaries_map: Dict[int, str]
    report_text: str
    tts_output_path: str
    # en_tts_output_path: str  # 영어 tts 들어오면


# ==================================================


# ===================== 노드 함수 =====================


def fetch_top_news(state: NewsState) -> NewsState:
    print(" [노드 1] Top 10 뉴스 추출 중...")

    import sqlite3 as _sqlite3

    category_limits = {
        "컨텐츠 & 작품": 5,
        "인물 & 아티스트": 3,
        "비즈니스 & 행사": 2,
    }

    conn = _sqlite3.connect("k_enter_news.db")
    conn.row_factory = _sqlite3.Row
    cursor = conn.cursor()

    rows = []
    for category, limit in category_limits.items():
        cursor.execute(
            "SELECT p.id, p.category, p.sub_category, p.summary, p.keywords, p.artist_tags,"
            " p.importance, p.importance_reason, p.trend_insight, p.source_name,"
            " p.published_at, p.timeline, p.ko_title"
            " FROM processed_news p"
            " WHERE p.importance IS NOT NULL AND p.category = ?"
            " ORDER BY p.importance DESC, p.id DESC LIMIT ?",
            (category, limit)
        )
        rows.extend(cursor.fetchall())

    conn.close()

    # importance 높은 순, 같으면 id 높은 순으로 최종 정렬
    rows = sorted(rows, key=lambda x: (x["importance"], x["id"]), reverse=True)

    def _parse(v):
        if not v:
            return []
        if isinstance(v, (list, dict)):
            return v
        try:
            return json.loads(v)
        except Exception:
            return []

    top_news_list = []
    for row in rows:
        top_news_list.append({
            "id": row["id"],
            "title": row["ko_title"] or "",
            "summary": _parse(row["summary"]),
            "keywords": _parse(row["keywords"]),
            "artist_tags": _parse(row["artist_tags"]),
            "importance": row["importance"],
            "importance_reason": row["importance_reason"] or "",
            "sub_category": row["sub_category"] or "",
            "category": row["category"] or "",
            "trend_insight": row["trend_insight"] or "",
            "source_name": row["source_name"] or "",
            "published_at": str(row["published_at"]) if row["published_at"] else "",
            "timeline": _parse(row["timeline"]),
        })

    for i, news in enumerate(top_news_list):
        print(f"  {i+1}위. [{news['sub_category']}][중요도:{news['importance']}] {news['title']}")

    return {**state, "top_news_list": top_news_list}


def fetch_related_news(state: NewsState) -> NewsState:
    """[노드 2] 각 Top 10 뉴스별 관련 past_news 3개 검색 + 1~10위 한줄평 생성 + trend_insight DB 저장"""
    print("\n [노드 2] 관련 과거뉴스 검색 및 한줄평 생성 중...")

    _, past_store = get_stores()
    top_news_list = state["top_news_list"]
    related_news_map = {}
    summaries_map = {}

    for i, news in enumerate(top_news_list):
        # 관련 과거뉴스 검색
        query_text = news["title"] + " " + " ".join(news["keywords"])
        results = past_store.similarity_search_with_score(
            query_text, k=RELATED_NEWS_COUNT
        )
        related = [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": score,
            }
            for doc, score in results
            if int((1 - score) * 100) >= 85
        ]
        related_news_map[i] = related

        # 한줄평 생성
        related_text = "\n".join(
            [f"- 과거 뉴스 {j+1}: {r['content'][:500]}" for j, r in enumerate(related)]
        ) if related else "관련 과거 뉴스 없음"
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


        prompt = f"""당신은 방대한 데이터를 관통하는 통찰을 한 줄로 요약하는 '수석 전략가'입니다.
과거의 기록들과 현재의 사건을 연결하여, 지금 이 현상이 산업 전체에 던지는 핵심 메시지를 단 한 문장으로 정의하십시오.

[현재 뉴스]
- 제목: {news['title']}
- 요약: {summary_text}

[과거 관련 기록]
{related_text}

분석 및 작성 가이드:
1. 핵심 관통: 단순히 정보를 나열하지 말고, 과거의 패턴이 현재 어떻게 '결실'을 맺었거나 '새로운 국면'으로 전환되었는지 그 본질을 짚으십시오.
2. 구체성 유지: 무의미한 추상적 표현(예: "글로벌 경쟁력 강화") 대신, 구체적인 산업 현상이나 가치를 담으십시오. (필요하다면 핵심 아티스트나 곡명을 문맥에 맞게 포함해도 좋으나, 단순 나열은 금지합니다.)
3. 문장 스타일: "현상은 ~를 넘어 ~로 진화하고 있다", "~의 반복은 결국 ~라는 필연적 흐름을 완성하고 있다", "~가 단순 유행을 넘어 하나의 견고한 산업 규범으로 자리 잡는 과정이다" 등 깊이 있는 통찰을 담은 한 문장으로 작성하십시오.
4. 엄격한 규칙: 오직 한 문장만 출력하십시오. 부연 설명, 따옴표, "트렌드 인사이트:" 같은 머리말은 절대 금지합니다.

핵심 인사이트:"""

        response = ollama.chat(
            model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}]
        )
        summary = response["message"]["content"].strip()
        summaries_map[i] = summary
        print(f"  {i+1}위 '{news['title'][:30]}' 한줄평 완료")

    # trend_insight 컬럼에 한줄평 저장
    session = SessionLocal()
    try:
        for i, news in enumerate(top_news_list):
            row = (
                session.query(ProcessedNews)
                .filter(ProcessedNews.id == news["id"])
                .first()
            )
            if row:
                row.trend_insight = summaries_map[i]
        session.commit()
        print("\n   trend_insight DB 저장 완료")
    except Exception as e:
        session.rollback()
        print(f"\n   trend_insight DB 저장 실패: {e}")
    finally:
        session.close()

    return {"related_news_map": related_news_map, "summaries_map": summaries_map}


def generate_report(state: NewsState) -> NewsState:
    """[노드 3] Top 10 뉴스 TTS 보고서 생성"""
    print("\n [노드 3] 요약 보고서 생성 중...")

    top_news_list = state["top_news_list"]
    summaries_map = state["summaries_map"]

    report_lines = ["안녕하세요. 오늘의 주요 뉴스 top 10을 전해드립니다."]
    for i, news in enumerate(top_news_list):
        summary = summaries_map.get(i, "")
        report_lines.append(f"{i+1}위 뉴스는, {summary}")  # {news['title']}.
    report_lines.append("이상으로 오늘의 주요 뉴스 top 10이었습니다.")

    report_text = " ".join(report_lines)
    print(f"\n  📄 보고서 생성 완료 ({len(report_text)}자)")

    # 보고서 텍스트 파일 저장
    with open("./news_report.txt", "w", encoding="utf-8") as f:
        f.write(report_text)
    print("  📄 보고서 텍스트 파일 저장 완료: ./news_report.txt")

    return {"report_text": report_text}


def run_tts(state: NewsState) -> NewsState:
    """[노드 4] 보고서 텍스트를 TTS로 변환"""
    print("\n [노드 4] TTS 변환 중...")
    ko_path = text_to_speech(state["report_text"], TTS_OUTPUT_PATH)
    return {"tts_output_path": ko_path}

    # 영어 tts 추가하면 바꿔야함.
    # ko_path, en_path = text_to_speech(state["report_text"], TTS_OUTPUT_PATH)
    # return {"tts_output_path": ko_path, "en_tts_output_path": en_path}


# ===================== 그래프 구성 =====================
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
    print("🚀 뉴스 파이프라인 시작\n" + "=" * 50)

    app = build_graph()
    initial_state: NewsState = {
        "top_news_list": [],
        "related_news_map": {},
        "summaries_map": {},
        "report_text": "",
        "tts_output_path": "",
        # tts영어
        # "en_tts_output_path": "",
    }

    final_state = app.invoke(initial_state)

    print("\n" + "=" * 50)
    print("✅ 파이프라인 완료!")
    print(f"  🎙️  TTS 파일: {final_state['tts_output_path']}")
    for i, summary in final_state["summaries_map"].items():
        print(f"  💬 {i+1}위 한줄평: {summary}")
