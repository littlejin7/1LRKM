import base64
from pathlib import Path
from categories import accent_color_for_row, resolve_row_categories

SENT_LABEL = {
    "positive": "긍정",
    "neutral": "중립",
    "negative": "부정",
    "긍정": "긍정",
    "중립": "중립",
    "부정": "부정",
}
TITLE_IMG = Path(__file__).resolve().parent / "assets" / "title.png"
LOGOS_IMG = Path(__file__).resolve().parent / "assets" / "mag.png"

# ── 유틸 헬퍼 ────────────────────────────────────────────────────────────────
def _safe_tags(val) -> list:
    if not val: return []
    if isinstance(val, list): return val
    if isinstance(val, str):
        try:
            import json
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else [str(parsed)]
        except: return [val]
    return [str(val)]

def _thumb_html(url: str, featured: bool = False) -> str:
    cls = "featured-thumb" if featured else "news-thumb"
    fallback = "https://via.placeholder.com/640x360?text=No+Image"
    src = url.strip() if url else fallback
    return f'<img class="{cls}" src="{src}" alt="thumbnail" referrerpolicy="no-referrer" onerror="this.src=\'{fallback}\'" />'


def _badge(sentiment: str) -> str:
    if sentiment in ["positive", "긍정"]:
        return '<span class="badge-pos">● 긍정</span>'
    if sentiment in ["negative", "부정"]:
        return '<span class="badge-neg">● 부정</span>'
    return '<span class="badge-neu">● 중립</span>'


def _cat_badge(item: dict) -> str:
    _, sub = resolve_row_categories(item)
    color = accent_color_for_row(item)
    return (
        f'<span style="background:{color}18;color:{color};border:1px solid {color}55;'
        f'padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;">{sub}</span>'
    )


def _change_badge(score: float) -> str:
    if score >= 0.8:
        return '<span class="change-up">↑</span>'
    if score <= 0.3:
        return '<span class="change-down">↓</span>'
    return '<span class="change-same">→</span>'

def get_base64_image(image_path):
    with open(image_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

