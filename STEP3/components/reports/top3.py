from reportlab.lib import colors
from reportlab.lib.units import mm

def draw_page4(c, W, H, draw_header, top_artists, top_keywords, top_source, page_num=4, total_pages=4):

    c.showPage()
    draw_header(c, page_num, total_pages)

    y = H - 40 * mm

    # =========================
    # 1. 최신 핵심 키워드 TOP 3
    # =========================
    c.setFillColor(colors.HexColor('#1a1a2e'))
    c.setFont('Malgun', 13)
    c.drawString(15*mm, y, '■ 최신 뉴스 키워드  top3')

    y -= 4*mm
    c.setStrokeColor(colors.HexColor('#dddddd'))
    c.line(15*mm, y, W - 15*mm, y)

    y -= 10*mm

    for i, (kw, cnt) in enumerate(top_keywords):
        c.setFont('Malgun', 11)
        c.drawString(15*mm, y, f'{i+1}위  #{kw} ({cnt}건)')
        y -= 8*mm

    y -= 10*mm


    # =========================
    # 2. 아티스트 TOP 3
    # =========================
    c.setFont('Malgun', 13)
    c.drawString(15*mm, y, '■ 최신 뉴스 아티스트 top3')

    y -= 4*mm
    c.line(15*mm, y, W - 15*mm, y)

    y -= 10*mm

    for i, (artist, cnt) in enumerate(top_artists):
        c.setFont('Malgun', 11)
        c.drawString(15*mm, y, f'{i+1}위  {artist} ({cnt}건)')
        y -= 8*mm

    y -= 10*mm


    # =========================
    # 3. 언론사 TOP 3
    # =========================
    c.setFont('Malgun', 13)
    c.drawString(15*mm, y, '■ 최신 뉴스 보도 언론사 top3 ')

    y -= 4*mm
    c.line(15*mm, y, W - 15*mm, y)

    y -= 10*mm

    for i, (source, cnt) in enumerate(top_source):
        c.setFont('Malgun', 11)
        c.drawString(15*mm, y, f'{i+1}위  {source} ({cnt}건)')
        y -= 8*mm