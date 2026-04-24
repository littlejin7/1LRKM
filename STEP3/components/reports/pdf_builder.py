import io
import os
import re
import ollama
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

from STEP3.components.reports.news_character import (
    parse_insight, draw_section_title, draw_insight_box,
    draw_distribution_chart, draw_haeryang_detail
)
from STEP3.components.reports.top3 import draw_page4
from STEP3.components.reports.db import get_top_artists, get_top_source

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
OLLAMA_MODEL = "gemma3:latest"
FONT_PATH = str(ROOT_DIR / "STEP3" / "pages" / "malgun.ttf")
OUTPUT_PATH = str(ROOT_DIR / "k_ent_report.pdf")


def register_font():
    """말간고딕 폰트 등록"""
    pdfmetrics.registerFont(TTFont('Malgun', FONT_PATH))


def draw_header(c, page_num, total_pages=None):
    """헤더/푸터 그리기"""
    W, H = A4
    today = datetime.now().strftime('%Y년 %m월 %d일')

    # 헤더 배경
    c.setFillColor(colors.HexColor('#1a1a2e'))
    c.rect(0, H - 20*mm, W, 20*mm, fill=True, stroke=False)

    # 제목
    c.setFillColor(colors.white)
    c.setFont('Malgun', 16)
    c.drawString(15*mm, H - 16*mm, '덜읽더알  |  K-ENT 뉴스 브리핑 보고서')

    # 날짜
    c.setFont('Malgun', 9)
    c.drawString(15*mm, H - 26*mm, today)


    # 푸터
    c.setFillColor(colors.HexColor('#888888'))
    c.setFont('Malgun', 8)
    if total_pages:
        c.drawRightString(W - 15*mm, 10*mm, f'{page_num} / {total_pages}')
    else:
        c.drawRightString(W - 15*mm, 10*mm, f'{page_num}')


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


def generate_pdf(top10: list, summary: str, top_keywords: list, all_news, tree_data, h_total, insight_raw):
    """PDF 생성"""
    W, H = A4
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    c = canvas.Canvas(OUTPUT_PATH, pagesize=A4)

    def _draw_png_sections(png_parts: list[bytes], *, start_y: float, page_num: int) -> tuple[float, int]:
        """PNG 섹션을 배치. 안 들어가면 다음 페이지로 넘겨 계속 그립니다."""
        margin_x = 15 * mm
        bottom_y = 16 * mm
        max_w = W - 2 * margin_x
        gap = 6
        y_top = start_y

        for png in png_parts:
            img = ImageReader(io.BytesIO(png))
            iw, ih = img.getSize()
            if iw <= 0 or ih <= 0:
                continue
            avail_h = max(y_top - bottom_y, 80)
            scale = min(max_w / iw, avail_h / ih, 1.0)
            dw, dh = iw * scale, ih * scale
            if y_top - dh < bottom_y:
                c.showPage()
                page_num += 1
                draw_header(c, page_num, None)
                y_top = H -38 * mm
                avail_h = max(y_top - bottom_y, 80)
                scale = min(max_w / iw, avail_h / ih, 1.0)
                dw, dh = iw * scale, ih * scale
            y_bottom = y_top - dh
            c.drawImage(img, margin_x, y_bottom, width=dw, height=dh, mask="auto")
            y_top = y_bottom - gap
        return (y_top, page_num)

    # ─────────────────────────────────────
    # 페이지 1: 서론 및 Top 10 뉴스 tts_text
    # ─────────────────────────────────────
    page_num = 1
    draw_header(c, page_num, None)
    y = H - 28*mm

    # 서론 섹션
    c.setFillColor(colors.HexColor('#1a1a2e'))
    c.setFont('Malgun', 13)
    c.drawString(15*mm, y, '■ 서론')
    y -= 7*mm

    c.setStrokeColor(colors.HexColor('#dddddd'))
    c.setLineWidth(0.5)
    c.line(15*mm, y, W - 15*mm, y)
    y -= 5*mm

    introduction_text = "오늘의 K-ENT 시장은 정체된 패러다임을 깨는 새로운 시도와 글로벌 성과가 교차하는 지점에 있습니다. 인공지능이 분석한 오늘의 트렌드 차트에는 [주요 아티스트]를 중심으로 한 팬덤 경제의 확장과 [핵심 키워드]라는 새로운 화두가 선명하게 드러나고 있습니다. 지금 바로 오늘의 변화를 확인할 수 있습니다."

    max_width = W - 30*mm
    c.setFillColor(colors.HexColor('#333333'))
    c.setFont('Malgun', 9)

    line = ''
    lines = []
    for ch in introduction_text:
        test = line + ch
        if c.stringWidth(test, 'Malgun', 9) > max_width:
            lines.append(line)
            line = ch
        else:
            line = test
    if line:
        lines.append(line)

    for ln in lines:
        if y < 20*mm:
            c.showPage()
            page_num += 1
            draw_header(c, page_num, None)
            y = H - 28*mm
        c.drawString(15*mm, y, ln)
        y -= 6*mm

    y -= 10*mm  # 섹션 간 간격

    c.setFillColor(colors.HexColor('#1a1a2e'))
    c.setFont('Malgun', 13)
    c.drawString(15*mm, y, '■ Top 10 뉴스 요약')
    y -= 7*mm

    c.setStrokeColor(colors.HexColor('#dddddd'))
    c.setLineWidth(0.5)
    c.line(15*mm, y, W - 15*mm, y)
    y -= 5*mm

    for i, news in enumerate(top10):
        if y < 20*mm:
            c.showPage()
            page_num += 1
            draw_header(c, page_num, None)
            y = H - 28*mm

        badge_color = colors.HexColor('#e74c3c') if i < 3 else colors.HexColor('#3498db')
        c.setFillColor(badge_color)
        c.roundRect(15*mm, y - 3.5*mm, 10*mm, 6*mm, 1.5, fill=True, stroke=False)
        c.setFillColor(colors.white)
        c.setFont('Malgun', 7)
        c.drawCentredString(20*mm, y - 0.5*mm, f'{i+1}위')

        c.setFillColor(colors.HexColor('#1a1a2e'))
        c.setFont('Malgun', 9)
        title = news['title'][:38] + ('...' if len(news['title']) > 38 else '')
        c.drawString(28*mm, y - 0.5*mm, title)

        c.setFillColor(colors.HexColor('#888888'))
        c.setFont('Malgun', 7)
        c.drawRightString(W - 15*mm, y - 0.5*mm, news.get('category', ''))
        y -= 6*mm

        tts = news.get('tts_text', '')
        if tts:
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
            for ln in lines[:3]:
                c.drawString(28*mm, y, ln)
                y -= 5*mm

        c.setStrokeColor(colors.HexColor('#eeeeee'))
        c.setLineWidth(0.3)
        c.line(15*mm, y, W - 15*mm, y)
        y -= 10*mm

    c.setFillColor(colors.HexColor('#1a1a2e'))
    c.setFont('Malgun', 13)
    c.drawString(15*mm, y, '■  TOP 10 종합 인사이트')
    y -= 4*mm

    c.setStrokeColor(colors.HexColor('#dddddd'))
    c.setLineWidth(0.5)
    c.line(15*mm, y, W - 15*mm, y)
    y -= 8*mm

    box_height = 42*mm
    c.setFillColor(colors.HexColor('#f8f9fb'))
    c.setStrokeColor(colors.HexColor('#3498db'))
    c.setLineWidth(1)
    c.roundRect(15*mm, y - box_height, W - 30*mm, box_height, 3, fill=True, stroke=True)

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

    # ─────────────────────────────────────
    # 해량 섹션: 최신 연예계 뉴스 성격
    # ─────────────────────────────────────
    c.showPage()
    page_num += 1
    draw_header(c, page_num, None)
    y = H - 28*mm
    y = draw_section_title(c, y, '■  최신 연예계 뉴스 분석')
    headline, body = parse_insight(insight_raw)
    y = draw_insight_box(c, y, headline, body)
    y = draw_distribution_chart(c, tree_data, h_total, y)
    y, page_num = draw_haeryang_detail(c, tree_data, h_total, y, page_num, draw_header)

    top_artists = get_top_artists()
    top_source = get_top_source()
    draw_page4(c, W, H, draw_header, top_artists, top_keywords, top_source, page_num=3, total_pages=3)

    c.save()
    print(f"PDF 저장 완료: {OUTPUT_PATH}")