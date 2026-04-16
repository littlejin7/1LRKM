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
    # en_tts_output_path: str  # 🚨🚨영어 tts 들어오면


# ==================================================


# ===================== 노드 함수 =====================

# ✔️✔️04-16 23:37분 fetch_top_news 함수전체 수정


def fetch_top_news(state: NewsState) -> NewsState:
    print("📰 [노드 1] Top 10 뉴스 추출 중...")

    session = SessionLocal()
    try:
        # 카테고리별 뉴스 추출
        category_limits = {
            "컨텐츠 & 작품": 5,
            "인물 & 아티스트": 3,
            "비즈니스 & 행사": 2,
        }

        candidates = []
        for category, limit in category_limits.items():
            rows = (
                session.query(ProcessedNews)
                .filter(ProcessedNews.importance.isnot(None))
                .filter(ProcessedNews.category == category)
                .order_by(ProcessedNews.importance.desc())
                .limit(limit)
                .all()
            )
            candidates.extend(rows)

        # importance 높은 순으로 최종 정렬
        candidates.sort(key=lambda x: x.importance, reverse=True)

        top_news_list = []
        for news in candidates:
            top_news_list.append(
                {
                    "id": news.id,
                    "title": news.ko_title or "",
                    "summary": news.summary or [],
                    "keywords": news.keywords or [],
                    "artist_tags": news.artist_tags or [],
                    "importance": news.importance,
                    "importance_reason": news.importance_reason or "",
                    "sub_category": news.sub_category or "",
                    "category": news.category or "",
                    "trend_insight": news.trend_insight or "",
                    "source_name": news.source_name or "",
                    "published_at": str(news.published_at) if news.published_at else "",
                    "timeline": news.timeline or [],
                }
            )
    finally:
        session.close()

    for i, news in enumerate(top_news_list):
        print(
            f"  {i+1}위. [{news['sub_category']}][중요도:{news['importance']}] {news['title']}"
        )

    return {**state, "top_news_list": top_news_list}


def fetch_related_news(state: NewsState) -> NewsState:
    """[노드 2] 각 Top 10 뉴스별 관련 past_news 3개 검색 + 1~10위 한줄평 생성 + trend_insight DB 저장"""
    print("\n🔍 [노드 2] 관련 과거뉴스 검색 및 한줄평 생성 중...")

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
        ]
        related_news_map[i] = related

        # 한줄평 생성
        related_text = "\n".join(
            [f"- 과거 뉴스 {j+1}: {r['content'][:500]}" for j, r in enumerate(related)]
        )
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

        ### ⭐⭐⭐⭐ 한줄평 프롬프트 ⭐⭐⭐⭐

        prompt = f"""다음은 현재 주요 뉴스 1건과 관련된 과거 뉴스입니다.  
이 내용을 바탕으로 비즈니스 시사점을 담은 한줄 요약을 한국어로 작성해주세요.

[현재 뉴스]
제목: {news['title']}
요약: {summary_text}

[관련 과거 뉴스]
{related_text}

한줄 요약:"""

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
        print("\n  ✅ trend_insight DB 저장 완료")
    except Exception as e:
        session.rollback()
        print(f"\n  ❌ trend_insight DB 저장 실패: {e}")
    finally:
        session.close()

    return {"related_news_map": related_news_map, "summaries_map": summaries_map}


def generate_report(state: NewsState) -> NewsState:
    """[노드 3] Top 10 뉴스 TTS 보고서 생성"""
    print("\n📝 [노드 3] 요약 보고서 생성 중...")

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
    print("\n🔊 [노드 4] TTS 변환 중...")
    ko_path = text_to_speech(state["report_text"], TTS_OUTPUT_PATH)
    return {"tts_output_path": ko_path}

    # 🚨🚨영어 tts 추가하면 바꿔야함.
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
        # 🚨🚨tts영어
        # "en_tts_output_path": "",
    }

    final_state = app.invoke(initial_state)

    print("\n" + "=" * 50)
    print("✅ 파이프라인 완료!")
    print(f"  🎙️  TTS 파일: {final_state['tts_output_path']}")
    for i, summary in final_state["summaries_map"].items():
        print(f"  💬 {i+1}위 한줄평: {summary}")
