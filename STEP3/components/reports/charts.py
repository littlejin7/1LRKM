import io
import textwrap
from collections import Counter
from pathlib import Path
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle

from STEP3.components.reports.db import (
    _fetch_recent_distinct_dates, _fetch_processed_in_dates,
    _fetch_past_in_dates
)

FONT_PATH = str(Path(__file__).resolve().parent.parent.parent.parent / "STEP3" / "pages" / "malgun.ttf")


def _mpl_setup_korean() -> None:
    from matplotlib import font_manager as fm
    plt.rcParams["axes.unicode_minus"] = False
    try:
        fm.fontManager.addfont(FONT_PATH)
        family = fm.FontProperties(fname=FONT_PATH).get_name()
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = [family]
    except Exception:
        plt.rcParams["font.family"] = "sans-serif"


def _plt_to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="white", pad_inches=0.06)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _sentiment_pcts(counts: dict[str, int]) -> tuple[float, float, float]:
    labels = ["긍정", "부정", "중립"]
    sizes = [int(counts.get(k, 0)) for k in labels]
    total = sum(sizes) or 1
    return tuple(round(100 * sizes[i] / total, 1) for i in range(3))


def _norm_sent_ko(item: dict) -> str:
    s = str(item.get("sentiment") or "").strip()
    sl = s.lower()
    if s in ("긍정", "positive", "pos", "Positive") or sl == "positive":
        return "긍정"
    if s in ("부정", "negative", "neg", "Negative") or sl == "negative":
        return "부정"
    return "중립"


def _counts_from_rows(rows: list[dict]) -> dict[str, int]:
    counts = {"긍정": 0, "부정": 0, "중립": 0}
    for r in rows:
        counts[_norm_sent_ko(r)] += 1
    return counts


def _aggregate_keywords(rows: list[dict]) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    pos = Counter()
    neg = Counter()
    for r in rows:
        s = _norm_sent_ko(r)
        for kw in (r.get("keywords") or []):
            if not isinstance(kw, str):
                continue
            kw = kw.strip()
            if not kw:
                continue
            if s == "긍정":
                pos[kw] += 1
            elif s == "부정":
                neg[kw] += 1
    return (pos.most_common(8), neg.most_common(8))


def _mmdd(d: date) -> str:
    return f"{d.month}/{d.day}"


def _range_mmdd(days: list[date]) -> str:
    if not days:
        return ""
    days = sorted(days)
    if len(days) == 1:
        return _mmdd(days[0])
    start, end = days[0], days[-1]
    if start.month == end.month:
        return f"{_mmdd(start)}~{end.day}"
    return f"{_mmdd(start)}~{_mmdd(end)}"


def _fig_section1(rows: list[dict], *, period_label: str) -> bytes:
    _mpl_setup_korean()
    counts = _counts_from_rows(rows)
    pos_kw, neg_kw = _aggregate_keywords(rows)
    pos_pct, neg_pct, neu_pct = _sentiment_pcts(counts)
    n_pos, n_neg, n_neu = counts["긍정"], counts["부정"], counts["중립"]
    total = n_pos + n_neg + n_neu

    p_pos, p_neg, p_neu = int(round(pos_pct)), int(round(neg_pct)), int(round(neu_pct))
    if p_pos >= 65:
        headline = f"이번 주 K-엔터는 긍정 기류가 뚜렷했습니다 (긍정 {p_pos}%)"
    elif p_pos >= 50:
        headline = f"긍정 우세 속 일부 부정 이슈가 혼재했습니다 (긍정 {p_pos}%)"
    elif p_neg >= 40:
        headline = f"부정 뉴스 비중이 높아진 흐름입니다 (부정 {p_neg}%)"
    else:
        headline = f"긍정·부정이 비교적 균형을 이룬 흐름입니다 (긍정 {p_pos}%)"

    pos_kw_only = [w for w, _ in pos_kw]
    neg_kw_only = [w for w, _ in neg_kw]
    if pos_kw_only:
        kw_str = "  ".join(f"#{k}" for k in pos_kw_only[:3])
        pos_line = f"{kw_str} 등 키워드를 중심으로 긍정 보도가 이어졌습니다."
    else:
        pos_line = "긍정 키워드 데이터가 충분하지 않습니다."

    if n_neg == 0:
        neg_line = "이번 집계 구간에서 부정 기사는 확인되지 않았습니다."
    elif neg_kw_only:
        kw_str = "  ".join(f"#{k}" for k in neg_kw_only[:3])
        neg_line = f"부정 측에서는 {kw_str} 이슈가 반복 언급됐습니다 ({n_neg}건)."
    else:
        neg_line = f"부정 기사 {n_neg}건이 집계됐으나 키워드 정보가 부족합니다."

    if p_pos >= 65 and p_neg <= 15:
        summary_line = f"전반적으로 밝은 분위기 속에 기사 {total}건이 집계됐습니다."
    elif p_neg >= 30:
        summary_line = f"부정 이슈가 비교적 높은 비중({p_neg}%)을 차지해 모니터링이 필요합니다."
    else:
        summary_line = f"전체 {total}건 중 긍정이 과반을 차지하며 안정적인 흐름을 보였습니다."

    C_POS = "#3498db"
    C_NEG = "#e74c3c"
    C_NEU = "#95a5a6"
    C_DARK = "#1a1a2e"
    C_MUTED = "#666666"
    C_BORDER = "#e0e0e0"

    fig = plt.figure(figsize=(7.6, 5.5))
    fig.patch.set_facecolor("white")
    gs = fig.add_gridspec(
        3, 3, height_ratios=[0.45, 0.03, 2.0], hspace=0.25, wspace=0.22, left=0.04, right=0.97, top=0.88, bottom=0.03
    )

    fig.text(0.04, 0.975, "■  최신 뉴스 감성 분포도", fontsize=13, fontweight="bold", color=C_DARK, va="top")

    card_specs = [
        ("긍정", p_pos, n_pos, C_POS, "#EBF5FB"),
        ("부정", p_neg, n_neg, C_NEG, "#FDEDEC"),
        ("중립", p_neu, n_neu, C_NEU, "#F2F3F4"),
    ]
    for col_idx, (label, pct_i, n_i, accent, bg) in enumerate(card_specs):
        axc = fig.add_subplot(gs[0, col_idx])
        axc.set_xlim(0, 1)
        axc.set_ylim(0, 1)
        axc.axis("off")
        axc.add_patch(FancyBboxPatch((0.04, 0.08), 0.92, 0.84, boxstyle="round,pad=0.04", facecolor=bg, edgecolor="none"))
        axc.text(0.50, 0.66, f"{pct_i}%", ha="center", va="center", fontsize=19, fontweight="bold", color=accent)
        axc.text(0.50, 0.24, f"{label}  {n_i}건", ha="center", va="center", fontsize=9, color=C_MUTED)

    ax_div = fig.add_subplot(gs[1, :])
    ax_div.axis("off")
    ax_div.axhline(0.5, color=C_BORDER, linewidth=0.8, xmin=0.01, xmax=0.99)

    ax_main = fig.add_subplot(gs[2, :])
    ax_main.set_xlim(0, 1)
    ax_main.set_ylim(0, 1)
    ax_main.axis("off")

    ax_main.add_patch(FancyBboxPatch((0.00, 0.85), 1.0, 0.14, boxstyle="round,pad=0.01", facecolor="#EBF5FB", edgecolor="none"))
    ax_main.text(0.50, 0.915, headline, ha="center", va="center", fontsize=11, fontweight="bold", color=C_POS)

    ax_main.text(0.02, 0.724, "긍정 주요 내용", ha="left", va="center", fontsize=9.5, fontweight="bold", color=C_POS)
    ax_main.text(0.52, 0.724, "부정 주요 내용", ha="left", va="center", fontsize=9.5, fontweight="bold", color=C_NEG)
    ax_main.text(0.02, 0.678, textwrap.fill(pos_line, width=35), ha="left", va="top", fontsize=9, color="#333333", linespacing=1.5)
    ax_main.text(0.52, 0.678, textwrap.fill(neg_line, width=35), ha="left", va="top", fontsize=9, color="#333333", linespacing=1.5)
    ax_main.axvline(0.50, ymin=0.02, ymax=0.80, color=C_BORDER, linewidth=0.8, linestyle="--")

    ax_main.add_patch(Rectangle((0.00, 0.00), 1.0, 0.20, facecolor="#F8F9FA", edgecolor="none"))
    ax_main.text(0.50, 0.10, summary_line, ha="center", va="center", fontsize=9.5, color=C_MUTED, style="italic")

    return _plt_to_png(fig)


def _donut_on_ax(ax, counts: dict[str, int], title: str) -> None:
    labels = ["긍정", "부정", "중립"]
    colors_ = ["#3498db", "#e74c3c", "#95a5a6"]
    sizes = [int(counts.get(k, 0)) for k in labels]
    tot = sum(sizes) or 1
    if sum(sizes) == 0:
        ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center", fontsize=11)
        ax.set_axis_off()
        ax.set_title(title, fontsize=11, fontweight="bold")
        return
    ax.pie(sizes, labels=None, colors=colors_, startangle=90, radius=0.92, wedgeprops=dict(width=0.42, edgecolor="white", linewidth=1.2))
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=11, fontweight="bold", pad=6)
    handles = [
        Patch(facecolor=colors_[i], edgecolor="#ffffff", linewidth=0.8, label=f"{labels[i]} {sizes[i]}건 ({100 * sizes[i] / tot:.1f}%)")
        for i in range(3)
    ]
    ax.legend(handles=handles, title="감성", loc="lower center", bbox_to_anchor=(0.5, -0.22), ncol=3, fontsize=8.5,
              frameon=True, fancybox=False, edgecolor="#bbbbbb", framealpha=1.0, title_fontsize=9)


def _fig_section3_donuts(left_counts: dict[str, int], right_counts: dict[str, int], *, left_title: str, right_title: str) -> bytes:
    _mpl_setup_korean()

    fig = plt.figure(figsize=(7.8, 3.2))
    gs = fig.add_gridspec(
        2, 2,
        height_ratios=[0.20, 0.80],  # 🔥 제목 vs 그래프 비율
        wspace=0.36,  # 🔥 좌우 그래프 간격 (줄이면 더 붙음)
        hspace=0.00,  # 🔥 위아래 간격
        left=0.04,    # 🔥 👈 전체 왼쪽 시작 위치 (섹션1이랑 맞추려면 이거 핵심)
        right=0.96,
        top=0.95,
        bottom=0.18
    )

    ax_title = fig.add_subplot(gs[0, :])
    ax_title.axis("off")
    fig.text(0.00, 0.95, "■ 주간 감성 분포 비교",
         ha="left", va="top", fontsize=13, fontweight="bold")

    ax1 = fig.add_subplot(gs[1, 0])  # 🔥 왼쪽 (최신)
    ax2 = fig.add_subplot(gs[1, 1])  # 🔥 오른쪽 (과거)

    _donut_on_ax(ax1, left_counts, left_title)
    _donut_on_ax(ax2, right_counts, right_title)
    # 👉 "최신", "과거" 텍스트는 여기서 들어감
    # 👉 left_title / right_title 값 수정하면 바뀜

    return _plt_to_png(fig)


def _fig_section3_notes(cur_counts: dict[str, int], prev_counts: dict[str, int], pos_kw: list[tuple[str, int]], neg_kw: list[tuple[str, int]]) -> bytes:
    _mpl_setup_korean()
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    ax.axis("off")
    cp = _sentiment_pcts(cur_counts)
    pp = _sentiment_pcts(prev_counts)
    top_pos = f"#{pos_kw[0][0]}" if pos_kw else "#(키워드 부족)"
    top_neg = f"#{neg_kw[0][0]}" if neg_kw else "#(해당 없음)"
    lines = [
        "[뉴스 분포 변화]",
        f" · 긍정 비율은 이전{pp[0]}%대비 {abs(cp[0]-pp[0]):.1f}%p 변화 수준 입니다.",
        f" · 부정 비율은 {pp[1]}% 대비 {cp[1]}% 변화 수준 입니다.",
        "",
        "[원인 추정]",
        f" · 긍정 쪽 키워드: {top_pos} 등이 이번 구간 보도에 많이 등장했습니다.",
        f" · 부정 쪽 키워드: {top_neg} 등이 분포에 기여했을 수 있습니다.",
    ]
    ax.text(0.03, 0.88, "\n".join(lines), transform=ax.transAxes, ha="left", va="top", fontsize=9.5, linespacing=1.5)
    return _plt_to_png(fig)


def _build_weekly_png_sections(*, period_days: int = 3) -> list[bytes]:
    proc_days = _fetch_recent_distinct_dates("processed_news", n_days=period_days)
    past_days = _fetch_recent_distinct_dates("past_news", n_days=period_days)
    processed = _fetch_processed_in_dates(proc_days)
    past = _fetch_past_in_dates(past_days)

    left_counts = _counts_from_rows(processed)
    right_counts = _counts_from_rows(past)
    pos_kw, neg_kw = _aggregate_keywords(processed)

    proc_range = _range_mmdd(proc_days)
    past_range = _range_mmdd(past_days)

    return [
        _fig_section1(processed, period_label=proc_range),
        _fig_section3_donuts(left_counts, right_counts, left_title=f"최신", right_title=f"과거"),
        _fig_section3_notes(left_counts, right_counts, pos_kw, neg_kw),
    ]
