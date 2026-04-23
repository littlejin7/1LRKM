"""
report.py — K-ENT 뉴스 브리핑 PDF 보고서 생성
위치: STEP3/pages/report/report.py
실행: python STEP3/pages/report/report.py
"""

import sys
import os
import re
from pathlib import Path
import sqlite3 as _sqlite3
import json
from collections import Counter

# 루트 경로 설정
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

import ollama
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from STEP3.components.news.news_pip import load_from_db, ARTIST_MAP

# ===================== CONFIG =====================
OLLAMA_MODEL = "gemma3:latest"
FONT_PATH = str(Path(__file__).resolve().parent / "malgun.ttf")
OUTPUT_PATH = str(ROOT_DIR / "k_ent_report.pdf")
# ==================================================

def register_font():
    """말간고딕 폰트 등록"""
    pdfmetrics.registerFont(TTFont('Malgun', FONT_PATH))

def get_top10():
    """news_pip.py에서 Top 10 뉴스 가져오기"""
    state = load_from_db()
    return state["top_news_list"]


def generate_summary(top10: list) -> str:
    """Top 10 trend_insight 종합 요약 생성"""
    print("종합 인사이트 생성 중...")

    insights = "\n".join([
        f"{i+1}. {news['trend_insight']}"
        for i, news in enumerate(top10)
        if news.get('trend_insight')
    ])

    prompt = f"""당신은 방대한 데이터를 관통하는 통찰을 한 줄로 요약하는 '수석 전략가'입니다.

아래는 오늘의 Top 10 뉴스에서 뽑은 트렌드 인사이트입니다.
이를 종합하여 오늘 K-엔터테인먼트 산업의 전반적인 흐름과 비즈니스 시사점을 3~4문장으로 요약해주세요.

[Top 10 트렌드 인사이트]
{insights}

분석 및 작성 가이드:
1. 핵심 관통: 단순히 정보를 나열하지 말고, 과거의 패턴이 현재 어떻게 '결실'을 맺었거나 '새로운 국면'으로 전환되었는지 그 본질을 짚으십시오.
2. 구체성 유지: 무의미한 추상적 표현 대신, 구체적인 산업 현상이나 가치를 담으십시오.

종합 요약:"""

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    result = response["message"]["content"].strip()
    result = re.sub(r'^\*\*.*?\*\*\s*', '', result).strip()

    return result

def draw_header(c, page_num, total_pages):
    """헤더/푸터 그리기"""
    W, H = A4
    today = datetime.now().strftime('%Y년 %m월 %d일')

    # 헤더 배경
    c.setFillColor(colors.HexColor('#1a1a2e'))
    c.rect(0, H - 40*mm, W, 40*mm, fill=True, stroke=False)

    # 제목
    c.setFillColor(colors.white)
    c.setFont('Malgun', 16)
    c.drawString(15*mm, H - 16*mm, '덜읽더알  |  K-ENT 뉴스 브리핑 보고서')

    # 날짜
    c.setFont('Malgun', 9)
    c.drawString(15*mm, H - 26*mm, today)

    # 구분선
    c.setStrokeColor(colors.HexColor('#e74c3c'))
    c.setLineWidth(2)
    c.line(15*mm, H - 32*mm, W - 15*mm, H - 32*mm)

    # 푸터
    c.setFillColor(colors.HexColor('#888888'))
    c.setFont('Malgun', 8)
    c.drawString(15*mm, 10*mm, f'K-ENT 뉴스 브리핑  |  {today}')
    c.drawRightString(W - 15*mm, 10*mm, f'{page_num} / {total_pages}')


def get_top_keywords(top_n: int = 3) -> list:
    """processed_news 전체 keywords에서 인물 제외 TOP N 키워드 집계"""

    _ROOT = Path(__file__).resolve().parent.parent.parent.parent
    conn = _sqlite3.connect(str(_ROOT / "k_enter_news.db"))
    conn.row_factory = _sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT keywords FROM processed_news WHERE keywords IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()

    # ARTIST_MAP 인물 이름 목록
    exclude = set(ARTIST_MAP.values())

    counter = Counter()
    for row in rows:
        keywords = row["keywords"]
        if isinstance(keywords, str):
            try:
                keywords = json.loads(keywords)
            except:
                continue
        if not isinstance(keywords, list):
            continue
        for kw in keywords:
            if not isinstance(kw, str):
                continue
            kw = kw.strip()
            if kw and kw not in exclude:
                counter[kw] += 1

    return counter.most_common(top_n)

def get_top_artists(top_n: int = 3) -> list:
    """processed_news 전체 artist_tags에서 TOP N 아티스트 집계"""

    _ROOT = Path(__file__).resolve().parent.parent.parent.parent
    conn = _sqlite3.connect(str(_ROOT / "k_enter_news.db"))
    conn.row_factory = _sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT artist_tags FROM processed_news WHERE artist_tags IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()

    counter = Counter()
    for row in rows:
        tags = row["artist_tags"]
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except:
                continue
        if not isinstance(tags, list):
            continue
        for tag in tags:
            if not isinstance(tag, str):
                continue
            tag = tag.strip()
            if not tag:
                continue
            # ARTIST_MAP에 있으면 정규화된 이름으로, 없으면 원래 이름으로
            norm = ARTIST_MAP.get(tag.lower().replace(" ", ""), tag)
            counter[norm] += 1

    return counter.most_common(top_n)















def get_top_source(top_n: int = 3) -> list:
    """processed_news 전체 source_name에서 TOP N 언론사 집계"""
    _ROOT = Path(__file__).resolve().parent.parent.parent.parent
    conn = _sqlite3.connect(str(_ROOT / "k_enter_news.db"))
    conn.row_factory = _sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT source_name FROM processed_news WHERE source_name IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()

    counter = Counter()
    for row in rows:
        source = row["source_name"]
        if source and isinstance(source, str):
            counter[source.strip()] += 1

    return counter.most_common(top_n)


def generate_pdf(top10: list, summary: str, top_keywords: list, top_artists: list, top_source: list):
    """PDF 생성"""
    W, H = A4
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    c = canvas.Canvas(OUTPUT_PATH, pagesize=A4)

    # ─────────────────────────────────────
    # 페이지 1: Top 10 뉴스
    # ─────────────────────────────────────
    draw_header(c, 1, 5)
    y = H - 48*mm

    # 섹션 제목
    c.setFillColor(colors.HexColor('#1a1a2e'))
    c.setFont('Malgun', 13)
    c.drawString(15*mm, y, '■ Top 10 뉴스 요약')
    y -= 7*mm

    c.setStrokeColor(colors.HexColor('#1a1a2e'))
    c.setLineWidth(1.5)
    c.line(15*mm, y, W - 15*mm, y)
    y -= 5*mm

    for i, news in enumerate(top10):
        if y < 20*mm:
            c.showPage()
            draw_header(c, 2, 5)
            y = H - 48*mm

        # 순위 배지
        badge_color = colors.HexColor('#e74c3c') if i < 3 else colors.HexColor('#3498db')
        c.setFillColor(badge_color)
        c.roundRect(15*mm, y - 3.5*mm, 10*mm, 6*mm, 1.5, fill=True, stroke=False)
        c.setFillColor(colors.white)
        c.setFont('Malgun', 7)
        c.drawCentredString(20*mm, y - 0.5*mm, f'{i+1}위')

        # 제목
        c.setFillColor(colors.HexColor('#1a1a2e'))
        c.setFont('Malgun', 9)
        title = news['title'][:38] + ('...' if len(news['title']) > 38 else '')
        c.drawString(28*mm, y - 0.5*mm, title)

        # 카테고리
        c.setFillColor(colors.HexColor('#888888'))
        c.setFont('Malgun', 7)
        c.drawRightString(W - 15*mm, y - 0.5*mm, news.get('category', ''))
        y -= 6*mm

        # tts_text
        tts = news.get('tts_text', '')
        if tts:
            # 줄바꿈 처리
            max_width = W - 45*mm
            line = ''
            lines = []
            for ch in tts:
                test = line + ch
                if c.stringWidth(test, 'Malgun', 8) > max_width:
                    lines.append(line)
                    line = ch
                else:
                    line = test
            if line:
                lines.append(line)

            c.setFillColor(colors.HexColor('#444444'))
            c.setFont('Malgun', 8)
            for ln in lines[:3]:  # 최대 3줄
                c.drawString(28*mm, y, ln)
                y -= 5*mm

        # 구분선
        c.setStrokeColor(colors.HexColor('#eeeeee'))
        c.setLineWidth(0.3)
        c.line(15*mm, y, W - 15*mm, y)
        y -= 4*mm

    # ─────────────────────────────────────
    # 페이지 2: 종합 인사이트
    # ─────────────────────────────────────
    c.showPage()
    draw_header(c, 2, 5)
    y = H - 48*mm

    # 섹션 제목
    c.setFillColor(colors.HexColor('#1a1a2e'))
    c.setFont('Malgun', 13)
    c.drawString(15*mm, y, '■  TOP 10 종합 인사이트')
    y -= 4*mm

    c.setStrokeColor(colors.HexColor('#1a1a2e'))
    c.setLineWidth(1.5)
    c.line(15*mm, y, W - 15*mm, y)
    y -= 8*mm

    # 종합 요약 박스
    box_height = 42*mm
    c.setFillColor(colors.HexColor('#f8f9fb'))
    c.setStrokeColor(colors.HexColor('#3498db'))
    c.setLineWidth(1)
    c.roundRect(15*mm, y - box_height, W - 30*mm, box_height, 3, fill=True, stroke=True)

    # 박스 안 텍스트
    text_y = y - 8*mm
    max_width = W - 40*mm
    c.setFillColor(colors.HexColor('#333333'))
    c.setFont('Malgun', 9)

    line = ''
    for ch in summary:
        test = line + ch
        if c.stringWidth(test, 'Malgun', 9) > max_width:
            c.drawString(20*mm, text_y, line)
            text_y -= 6*mm
            line = ch
        else:
            line = test
    if line:
        c.drawString(20*mm, text_y, line)

    y -= box_height + 10*mm

    # 분리선
    c.setStrokeColor(colors.HexColor('#1a1a2e'))
    c.setLineWidth(1.5)
    c.line(15*mm, y, W - 15*mm, y)
    y -= 8*mm




    # ─────────────────────────────────────
    # 페이지 3: 조원 작업 공간
    # ─────────────────────────────────────
    c.showPage()
    draw_header(c, 3, 5)
    y = H - 48*mm




    # ─────────────────────────────────────
    # 페이지 4: 아티스트 & 타임라인
    # ─────────────────────────────────────
    c.showPage()
    draw_header(c, 4, 5)
    y = H - 48*mm

    y -= 10*mm

    c.setFillColor(colors.HexColor('#1a1a2e'))
    c.setFont('Malgun', 13)
    c.drawString(15*mm, y, '■  최신 뉴스 TOP 3 분석')
    y -= 4*mm
    c.setStrokeColor(colors.HexColor('#1a1a2e'))
    c.setLineWidth(1.5)
    c.line(15*mm, y, W - 15*mm, y)
    y -= 8*mm

    # 3열 컴팩트 레이아웃
    col_w = (W - 30*mm) / 3
    col1_x = 15*mm
    col2_x = 15*mm + col_w
    col3_x = 15*mm + col_w * 2

    # 헤더 배경
    c.setFillColor(colors.HexColor('#f8f9fb'))
    c.rect(15*mm, y - 8*mm, W - 30*mm, 8*mm, fill=True, stroke=False)

    # 열 헤더
    c.setFillColor(colors.HexColor('#1a1a2e'))
    c.setFont('Malgun', 9)
    c.drawString(col1_x + 3*mm, y - 5*mm, '아티스트 TOP 3')
    c.drawString(col2_x + 3*mm, y - 5*mm, '키워드 TOP 3')
    c.drawString(col3_x + 3*mm, y - 5*mm, '언론사 TOP 3')
    y -= 14*mm

    # 세로 구분선
    c.setStrokeColor(colors.HexColor('#dddddd'))
    c.setLineWidth(0.5)
    c.line(col2_x, y + 2*mm, col2_x, y - 3 * 9*mm)
    c.line(col3_x, y + 2*mm, col3_x, y - 3 * 9*mm)

    # 아티스트 출력
    for i, (artist, cnt) in enumerate(top_artists):
        c.setFillColor(colors.HexColor('#1a1a2e'))
        c.setFont('Malgun', 9)
        c.drawString(col1_x + 3*mm, y - (i * 9*mm), f'{i+1}위  {artist}  ({cnt}건)')

    # 키워드 출력
    for i, (kw, cnt) in enumerate(top_keywords):
        c.setFillColor(colors.HexColor('#1a1a2e'))
        c.setFont('Malgun', 9)
        c.drawString(col2_x + 3*mm, y - (i * 9*mm), f'{i+1}위  #{kw}  ({cnt}건)')

    # 언론사 출력
    for i, (source, cnt) in enumerate(top_source):
        c.setFillColor(colors.HexColor('#1a1a2e'))
        c.setFont('Malgun', 9)
        c.drawString(col3_x + 3*mm, y - (i * 9*mm), f'{i+1}위  {source}  ({cnt}건)')

    c.save()
    print(f"PDF 저장 완료: {OUTPUT_PATH}")





def main():
    print("K-ENT 뉴스 브리핑 보고서 생성 시작\n" + "="*50)

    register_font()

    print("Top 10 뉴스 불러오는 중...")
    top10 = get_top10()[:10]
    print(f"  {len(top10)}개 뉴스 로드 완료")

    summary = generate_summary(top10)
    print(f"  종합 요약 완료: {summary[:50]}...")

    top_keywords = get_top_keywords()
    top_artists = get_top_artists()
    top_source = get_top_source()
    generate_pdf(top10, summary, top_keywords, top_artists, top_source)

    print(top10[0].keys())  # tts_text 있는지 확인
    print(top10[0].get('tts_text', '없음'))

if __name__ == "__main__":
    main()
