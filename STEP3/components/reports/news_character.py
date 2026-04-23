import re
import sqlite3
import ollama
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph

from STEP3.components.reports.db import load_all_processed_news

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
OLLAMA_MODEL = "gemma3:latest"


def get_haeryang_data():
    all_news = load_all_processed_news()
    mapping = {
        "컨텐츠 & 작품": ["음악/차트", "앨범/신곡", "콘서트/투어", "드라마/방송", "예능/방송", "공연/전시", "영화/OTT"],
        "인물 & 아티스트": ["팬덤/SNS", "스캔들/논란", "인사/동정", "미담/기부", "연애/결혼", "입대/군복무"],
        "비즈니스 & 행사": ["산업/기획사", "해외반응", "마케팅/브랜드", "행사/이벤트", "기타"]
    }
    tree_data = {key: {"count": 0, "subs": {}} for key in mapping.keys()}
    for news in all_news:
        sub_cat = news.get('sub_category', '기타')
        title = news.get('title', '제목 없음')
        found = False
        for big_cat, sub_list in mapping.items():
            if sub_cat in sub_list:
                tree_data[big_cat]["count"] += 1
                if sub_cat not in tree_data[big_cat]["subs"]:
                    tree_data[big_cat]["subs"][sub_cat] = {"count": 0, "titles": []}
                tree_data[big_cat]["subs"][sub_cat]["count"] += 1
                tree_data[big_cat]["subs"][sub_cat]["titles"].append(title)
                found = True
                break
        if not found:
            big_cat = "비즈니스 & 행사"
            tree_data[big_cat]["count"] += 1
            if "기타" not in tree_data[big_cat]["subs"]:
                tree_data[big_cat]["subs"]["기타"] = {"count": 0, "titles": []}
            tree_data[big_cat]["subs"]["기타"]["count"] += 1
            tree_data[big_cat]["subs"]["기타"]["titles"].append(title)
    total = sum(v["count"] for v in tree_data.values()) or 1
    return all_news, tree_data, total


def generate_haeryang_insight(tree_data, total):
    detail_lines = []
    for big_cat, info in tree_data.items():
        pct = info['count'] / total * 100
        subs = ", ".join([f"{s}({v['count']}건)" for s, v in info['subs'].items()]) or "없음"
        detail_lines.append(f"- {big_cat} {pct:.1f}% ({info['count']}건): {subs}")
    stats_text = "\n".join(detail_lines)
    prompt = f"""당신은 K-엔터테인먼트 시장 분석가입니다.
아래 전체 뉴스 분포(총 {total}건)를 분석하여 **극도로 간결하게** 출력하세요.

[분포 데이터]
{stats_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 절대 규칙 (위반 시 실패):
1. 자기소개·서론 금지. 아래 2줄만 출력. 그 외 어떤 문장도 추가 금지.
2. 헤드라인은 반드시 30자 이내 1문장.
3. 주요 내용은 반드시 **정확히 2문장**. 절대 3문장 이상 쓰지 말 것.
4. 각 문장은 40자 이내로 짧게.
5. 구체적 아티스트·작품명 언급 금지. 카테고리와 비율만 언급.
6. 실제 데이터의 숫자(%)를 반드시 인용.

[출력 형식 - 정확히 이 2줄만]
📌 헤드라인: (30자 이내)
🔎 주요 내용: (2문장, 각 40자 이내)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
    response = ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}])
    return response["message"]["content"].strip()


def parse_insight(text):
    headline, body_lines = "", []
    in_body = False
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if "📌" in line or line.startswith("헤드라인"):
            headline = re.sub(r'^.*?헤드라인[:：]?\s*', '', line).strip()
            headline = headline.replace("📌", "").strip()
            in_body = False
        elif "🔎" in line or "주요" in line:
            body_text = re.sub(r'^.*?주요\s*내용[:：]?\s*', '', line).strip()
            body_text = body_text.replace("🔎", "").strip()
            if body_text:
                body_lines.append(body_text)
            in_body = True
        elif in_body and not line.startswith("#") and "🏷" not in line and "━" not in line:
            body_lines.append(line)
    body = " ".join(body_lines)
    if not headline and not body:
        body = text
    if body:
        sentences = re.split(r'(?<=[.!?다])\s+', body.strip())
        sentences = [s for s in sentences if s.strip()]
        body = " ".join(sentences[:2])
    return headline, body


def draw_section_title(c, y, text):
    W, _ = A4
    c.setFillColor(colors.HexColor('#1a1a2e'))
    c.setFont('Malgun', 13)
    c.drawString(15*mm, y, text)
    y -= 7*mm
    c.setStrokeColor(colors.HexColor('#dddddd'))
    c.setLineWidth(0.5)
    c.line(15*mm, y, W - 15*mm, y)
    return y - 6*mm


def draw_insight_box(c, y, headline, body):
    W, H = A4
    box_x = 15*mm
    box_w = W - 30*mm
    pad = 5*mm
    head_style = ParagraphStyle('Head', fontName='Malgun', fontSize=12,
                                textColor=colors.HexColor('#1a1a2e'), leading=16)
    body_style = ParagraphStyle('Body', fontName='Malgun', fontSize=9,
                                textColor=colors.HexColor('#333333'), leading=14)
    head_p = Paragraph(f"<b>📌 {headline}</b>" if headline else "<b>📌 주간 요약</b>", head_style)
    body_p = Paragraph(f"🔎 {body}" if body else "", body_style)
    hw, hh = head_p.wrap(box_w - 2*pad, H)
    bw, bh = body_p.wrap(box_w - 2*pad, H)
    total_h = hh + 3*mm + bh + 2*pad
    c.setFillColor(colors.HexColor('#f8f9fb'))
    c.setStrokeColor(colors.HexColor('#3498db'))
    c.setLineWidth(1)
    c.roundRect(box_x, y - total_h, box_w, total_h, 3, fill=True, stroke=True)
    cy = y - pad - hh
    head_p.drawOn(c, box_x + pad, cy)
    cy -= (3*mm + bh)
    body_p.drawOn(c, box_x + pad, cy)
    return y - total_h - 6*mm


def palette_color(big_cat):
    return {
        "컨텐츠 & 작품": colors.HexColor('#3498db'),
        "인물 & 아티스트": colors.HexColor('#9b59b6'),
        "비즈니스 & 행사": colors.HexColor('#e67e22'),
    }.get(big_cat, colors.HexColor('#95a5a6'))


def draw_distribution_chart(c, tree_data, total, y_top):
    W, _ = A4
    y = draw_section_title(c, y_top, f'  •   카테고리별 기사 분포 (전체 {total}건)')
    label_x = 15*mm
    bar_x = 55*mm
    bar_max_w = W - bar_x - 32*mm
    bar_h = 6*mm
    gap = 11*mm
    max_count = max((v['count'] for v in tree_data.values()), default=1) or 1
    for big_cat, info in tree_data.items():
        cnt = info['count']
        percent = cnt / total * 100
        c.setFillColor(colors.HexColor('#333333'))
        c.setFont('Malgun', 9)
        c.drawString(label_x, y - bar_h + 1.8*mm, big_cat)
        c.setFillColor(colors.HexColor('#ecf0f1'))
        c.roundRect(bar_x, y - bar_h, bar_max_w, bar_h, 1.5, fill=True, stroke=False)
        ratio = cnt / max_count
        actual_w = max(bar_max_w * ratio, 0.1)
        c.setFillColor(palette_color(big_cat))
        c.roundRect(bar_x, y - bar_h, actual_w, bar_h, 1.5, fill=True, stroke=False)
        c.setFillColor(colors.HexColor('#1a1a2e'))
        c.setFont('Malgun', 8.5)
        c.drawString(bar_x + actual_w + 2*mm, y - bar_h + 1.8*mm, f"{cnt}건 ({percent:.1f}%)")
        y -= gap
    return y - 4*mm


def draw_haeryang_detail(c, tree_data, total, y, page_num, draw_header_fn):
    W, H = A4
    y = draw_section_title(c, y, '   •  카테고리별 상세 기사 (소분류별 대표 1건)')
    sub_style = ParagraphStyle('SubStyle', fontName='Malgun', fontSize=8.5,
                               textColor=colors.HexColor('#e67e22'), leading=11)
    news_style = ParagraphStyle('NewsStyle', fontName='Malgun', fontSize=8.5,
                                textColor=colors.HexColor('#444444'), leading=12)
    BIG_X = 15*mm
    SUB_X = 24*mm
    SUB_W = 25*mm
    TITLE_X = SUB_X + SUB_W + 2*mm
    TITLE_W = W - TITLE_X - 15*mm
    TREE_X = 18*mm
    MAX_TITLES_PER_SUB = 1
    for big_cat, info in tree_data.items():
        if y < 35*mm:
            c.showPage()
            page_num += 1
            draw_header_fn(c, page_num)
            y = H - 44*mm
        c.setFillColor(palette_color(big_cat))
        c.circle(BIG_X + 1.5*mm, y + 1.2*mm, 1.5*mm, fill=True, stroke=False)
        c.setFillColor(colors.HexColor('#1a1a2e'))
        c.setFont('Malgun', 11)
        c.drawString(BIG_X + 5*mm, y, big_cat)
        y -= 8*mm
        if info['subs']:
            c.setStrokeColor(colors.HexColor('#cccccc'))
            c.setLineWidth(0.5)
            sorted_subs = sorted(info['subs'].items(), key=lambda x: x[1]['count'], reverse=True)
            for sub_name, sub_info in sorted_subs:
                if y < 25*mm:
                    c.showPage()
                    page_num += 1
                    draw_header_fn(c, page_num)
                    y = H - 44*mm
                shown = sub_info['titles'][:MAX_TITLES_PER_SUB]
                extra = sub_info['count'] - len(shown)
                titles_text = " / ".join(shown)
                if extra > 0:
                    titles_text += f" <font color='#888888'>외 {extra}건</font>"
                title_p = Paragraph(titles_text, news_style)
                tw, th = title_p.wrap(TITLE_W, H)
                row_h = max(th, 5*mm)
                center_y = y - row_h / 2 + 1*mm
                c.line(TREE_X, y + 4*mm, TREE_X, center_y)
                c.line(TREE_X, center_y, SUB_X - 1*mm, center_y)
                sub_p = Paragraph(f"[{sub_name}]", sub_style)
                sw, sh = sub_p.wrap(SUB_W, H)
                sub_p.drawOn(c, SUB_X, center_y - sh/2)
                title_p.drawOn(c, TITLE_X, center_y - th/2)
                y -= (row_h + 3*mm)
            y -= 4*mm
            c.setStrokeColor(colors.HexColor('#eeeeee'))
            c.setLineWidth(0.3)
            c.line(15*mm, y, W - 15*mm, y)
            y -= 5*mm
        else:
            y -= 5*mm
    return y, page_num
