"""
report.cy.py — K-ENT 뉴스 브리핑 PDF 보고서 실행 파일
위치: STEP3/pages/report.cy.py
실행: python STEP3/pages/report.py
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from STEP3.components.reports.db import get_top10, get_top_keywords
from STEP3.components.reports.news_character import get_haeryang_data, generate_haeryang_insight
from STEP3.components.reports.pdf_builder import register_font, generate_summary, generate_pdf




def main():
    print("K-ENT 뉴스 브리핑 보고서 생성 시작\n" + "="*50)

    register_font()

    print("Top 10 뉴스 불러오는 중...")
    top10 = get_top10()[:10]
    print(f"  {len(top10)}개 뉴스 로드 완료")

    summary = generate_summary(top10)
    print(f"  종합 요약 완료: {summary[:50]}...")

    top_keywords = get_top_keywords()

    print("전체 뉴스 카테고리 분석 중...")
    all_news, tree_data, h_total = get_haeryang_data()
    print(f"  전체 뉴스 {h_total}건 로드 완료")

    insight_raw = generate_haeryang_insight(tree_data, h_total)

    generate_pdf(top10, summary, top_keywords, all_news, tree_data, h_total, insight_raw)


if __name__ == "__main__":
    main()
