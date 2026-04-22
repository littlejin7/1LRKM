import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def generate_report_pdf(filtered: list) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 60, "K-ENT Today News Report")
    c.setFont("Helvetica", 11)
    c.drawString(50, height - 85, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    c.line(50, height - 100, width - 50, height - 100)

    y = height - 130
    for i, item in enumerate(filtered[:10], 1):
        if y < 100:
            c.showPage()
            y = height - 60

        title = item.get("title", "")[:50]
        category = item.get("sub_category", item.get("category", ""))
        sentiment = item.get("sentiment", "")

        summary = item.get("summary", "")
        if isinstance(summary, list) and summary:
            first = summary[0]
            summary_text = (
                first.get("content", str(first))
                if isinstance(first, dict)
                else str(first)
            )
        else:
            summary_text = str(summary or "")

        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, f"{i}. {title}")
        y -= 18
        c.setFont("Helvetica", 10)
        c.drawString(60, y, f"Category: {category}  |  Sentiment: {sentiment}")
        y -= 15
        c.setFont("Helvetica", 9)
        c.drawString(60, y, summary_text[:80])
        y -= 25
        c.line(50, y, width - 50, y)
        y -= 15

    c.save()
    buffer.seek(0)
    return buffer.read()
