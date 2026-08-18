"""ภาพกราฟแนบของสายเว็บ A/B/C — ทางเลือกแทนหมุด `[[chart:]]` (ผู้ใช้สั่ง 08-10 ค่ำ)

ที่มา: กราฟที่เว็บวาดจากหมุดเป็นมุมกว้างเกินไป และหมุดไม่มีพารามิเตอร์คุมซูม
(คู่มือหัวหน้าระบุแค่ TF/s/r) ⇒ ผู้ใช้เลือกทาง "สร้างภาพซูมแนบเอง เราคุมซูม 100%"

สองภาพต่อใบ ตรงกับหมุดสองตัวในบท:
1. `render_daily_zoom` — D1 ~120 แท่ง (แทนหมุด `[[chart:1day|...]]`)
2. `render_h4`         — 4h 24 แท่งจาก snapshot (แทนหมุด `[[chart:4h|...]]`)

กติกาความสอดคล้อง (D-4.5):
- เส้น s/r ใช้ **เลขชุดเดียวกับหมุดเป๊ะ** — อ่านจาก `wcb_writers._sorted_levels`
  + `_distinct_lines` ตัวเดียวกับที่ประกอบหมุด แก้ที่เดียวเปลี่ยนพร้อมกันทั้งบทและภาพ
- ทุกป้ายผ่าน `checked_label` ก่อนวาด (ห้ามปี ค.ศ. บนภาพ)
- เซฟผ่าน `image_output.save_figure` — .webp ≤200 KB ตามสเปกเว็บ วัดไฟล์จริงทุกใบ

⚠️ ภาพชุดนี้เป็น**ของแนบทางเลือก** — ใบหมุดยังเป็นใบหลักจนกว่าจะยืนยันว่า
หน้านำเข้ามือของหลังบ้านแนบรูปได้จริง (ดูใบ `อ่านก่อน.md` ของโฟลเดอร์ขึ้นเว็บ)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import headline_format, image_output, wcb_writers  # noqa: E402
from tools.chart_story_renderer import (  # noqa: E402
    COLORS, _thai_font, checked_label, month_tick_labels)

FIGURE_SIZE = (19.2, 10.8)
DPI = 100
DAILY_BARS = 60           # ~3 เดือน — ผู้ใช้ขอซูมเพิ่ม 08-10 ดึก (120 แท่งช่วงราคากว้าง
                          # จนเส้น s/r สี่เส้นในแถบ 27 ดอลลาร์กองรวมอ่านไม่ออก)
H4_BARS = 24              # snapshot ให้ 24 แท่ง = ~4 วันทำการ

SUPPORT_COLOR = "#1e9e83"     # เขียว — ฝั่ง s ของหมุด
RESISTANCE_COLOR = "#f23645"  # แดง — ฝั่ง r ของหมุด

SIGNAL_COLORS = {
    "buy": "#0f9488",
    "sell": "#e24b5b",
    "neutral": "#7a8494",
}
SIGNAL_THAI = {"buy": "ซื้อ", "sell": "ขาย", "neutral": "กลาง"}
STYLE_A_FOCUS_INDICATORS = (
    "EMA10", "EMA20", "SMA50", "SMA200", "RSI(14)", "MACD(12,26)",
)


def image_names(asset: str, date_text: str) -> tuple[str, str]:
    """ชื่อไฟล์เป็น ค.ศ. ตามสเปกชื่อไฟล์ภาพเดิมของระบบ"""
    return (f"{asset}-web-d1-{date_text}.webp", f"{asset}-web-4h-{date_text}.webp")


def pin_levels(markdown: str) -> tuple[list[float], list[float]] | None:
    """อ่านเลขเส้นจากหมุดในบทจริง — ใช้ตอนสร้างภาพย้อนหลังให้ใบที่ผลิตไปแล้ว

    บทที่ผลิตไปแล้วต้องได้เส้นตามหมุดของมันเป๊ะ ไม่ใช่คำนวณใหม่จากข้อมูลปัจจุบัน
    (ค่า pivot ขยับระหว่างวันได้ — ภาพเส้นคนละชุดกับบทคือ D-4.5)
    """
    import re
    match = re.search(r"\[\[chart:[^|\]]+\|s=([\d.,]+)\|r=([\d.,]+)\]\]", markdown)
    if not match:
        return None
    lower = [float(x) for x in match.group(1).split(",")]
    upper = [float(x) for x in match.group(2).split(",")]
    return lower, upper


def sr_lines(evidence: dict, *, supports: int = 3, resistances: int = 3
             ) -> tuple[list[float], list[float]]:
    # 3/3 ตาม `chart_marker` (ผู้ใช้ทัก 08-11 ค่ำ: ภาพตีเส้นไม่ครบ 3 ด่านของบท)
    # — ทางหลักภาพอ่านเลขจากหมุดในบทจริง (`pin_levels`) ตัวนี้เป็นทางถอยตอนไม่มีหมุด
    # ต้องตรงกันไม่งั้นภาพย้อนหลังกับภาพรอบสดได้เส้นคนละชุด
    """เลขเส้นชุดเดียวกับหมุด — ผ่านตัวยุบเส้นซ้ำตัวเดียวกับ `chart_marker`"""
    below, above = wcb_writers._sorted_levels(evidence)
    lower = [float(text.replace(",", ""))
             for text in wcb_writers._distinct_lines(below, supports, evidence)]
    upper = [float(text.replace(",", ""))
             for text in wcb_writers._distinct_lines(above, resistances, evidence)]
    return lower, upper


def _draw_candles(axes, view: list[dict], Rectangle,
                  *, o="open", h="high", l="low", c="close") -> None:  # noqa: E741
    width = 0.62
    for index, row in enumerate(view):
        rising = row[c] >= row[o]
        color = COLORS["up"] if rising else COLORS["down"]
        axes.plot([index, index], [row[l], row[h]], color=color, linewidth=1.0, zorder=3)
        body_low = min(row[o], row[c])
        height = abs(row[c] - row[o]) or (row[h] - row[l]) * 0.02 or 1e-9
        axes.add_patch(Rectangle((index - width / 2, body_low), width, height,
                                 facecolor=color, edgecolor=color, linewidth=0.5, zorder=3))


def _style_axes(axes) -> None:
    axes.set_facecolor(COLORS["bg"])
    for spine in axes.spines.values():
        spine.set_color("#d1d4dc")
    axes.tick_params(colors=COLORS["axis"], labelsize=12)
    axes.grid(True, color=COLORS["grid"], linewidth=0.8)
    axes.yaxis.tick_right()
    axes.set_axisbelow(True)


def spread_label_positions(values: list[float], y_range: tuple[float, float],
                           *, gap_fraction: float = 0.035) -> dict[float, float]:
    """ตำแหน่งป้ายที่ดันหนีกันแล้ว — เส้นอยู่ที่ค่าจริงเสมอ ขยับเฉพาะป้าย

    ผู้ใช้เจอจริง 08-10 ดึก: แนวรับ 4,315/4,324 กับแนวต้าน 4,341/4,342 อยู่ในแถบ
    27 ดอลลาร์ ป้ายสี่ใบกองทับกันตรงเส้นประจนอ่านไม่ออก — ดันหนีกันด้วยระยะขั้นต่ำ
    ตามสัดส่วนช่วงแกน (วิธีเดียวกับป้ายราคาฝั่งขวาของสไตล์ E)
    """
    minimum_gap = (y_range[1] - y_range[0]) * gap_fraction
    placed: list[list[float]] = []   # [ค่าจริง, ตำแหน่งป้าย]
    for value in sorted(values):
        target = value
        while any(abs(target - other[1]) < minimum_gap for other in placed):
            target += minimum_gap * 0.25
        placed.append([value, target])
    return {value: label_y for value, label_y in placed}


def _draw_levels(axes, evidence: dict, lower: list[float], upper: list[float],
                 n: int) -> None:
    """เส้น s/r พร้อมป้ายราคา — สีตามธรรมเนียมหมุด (s เขียว · r แดง)

    เส้นวาดที่ค่าจริงเป๊ะ · ป้ายดันหนีกันเมื่อระดับชิดกัน (เส้นชิด = เรื่องปกติ
    ของ pivot คนละกรอบ) · ป้ายเรียงคอลัมน์ซ้าย อ่านบน-ลงล่างได้ทันที
    """
    money = wcb_writers.price
    y_low, y_high = axes.get_ylim()
    label_at = spread_label_positions(lower + upper, (y_low, y_high))
    for value in lower:
        axes.hlines(value, -1, n + 1, color=SUPPORT_COLOR, linewidth=1.4,
                    linestyle=(0, (6, 3)), zorder=2)
        axes.text(1, label_at[value], checked_label(f"แนวรับ {money(value, evidence)}"),
                  color=SUPPORT_COLOR, fontsize=12, va="center", zorder=6,
                  bbox=dict(boxstyle="round,pad=0.25", facecolor="#ffffff",
                            edgecolor=SUPPORT_COLOR, linewidth=0.6, alpha=0.92))
    for value in upper:
        axes.hlines(value, -1, n + 1, color=RESISTANCE_COLOR, linewidth=1.4,
                    linestyle=(0, (6, 3)), zorder=2)
        axes.text(1, label_at[value], checked_label(f"แนวต้าน {money(value, evidence)}"),
                  color=RESISTANCE_COLOR, fontsize=12, va="center", zorder=6,
                  bbox=dict(boxstyle="round,pad=0.25", facecolor="#ffffff",
                            edgecolor=RESISTANCE_COLOR, linewidth=0.6, alpha=0.92))


def _fit_y(axes, view: list[dict], lower: list[float], upper: list[float],
           *, h="high", l="low") -> None:  # noqa: E741
    """แกนราคาครอบทั้งแท่งและเส้นทุกเส้น — เส้นหลุดขอบ = ภาพโกหกว่าไม่มีด่านนั้น"""
    values = ([row[h] for row in view] + [row[l] for row in view] + lower + upper)
    top, bottom = max(values), min(values)
    pad = (top - bottom) * 0.06 or 1.0
    axes.set_ylim(bottom - pad, top + pad)


def render_daily_zoom(rows: list[dict], evidence: dict, output_path: Path,
                      *, bars: int = DAILY_BARS,
                      levels: tuple[list[float], list[float]] | None = None) -> dict:
    """ภาพ D1 ซูม — แทนหมุด `[[chart:1day|...]]` ด้วยมุมมองที่เห็นแท่งชัด"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    font_used = _thai_font()
    view = rows[-bars:]
    n = len(view)
    lower, upper = levels if levels is not None else sr_lines(evidence)

    figure, axes = plt.subplots(figsize=FIGURE_SIZE, dpi=DPI)
    figure.patch.set_facecolor(COLORS["bg"])
    _style_axes(axes)
    _draw_candles(axes, view, Rectangle)
    _fit_y(axes, view, lower, upper)          # ตั้งแกนก่อน — ระยะดันป้ายคิดจากช่วงแกนจริง
    _draw_levels(axes, evidence, lower, upper, n)
    axes.set_xlim(-1, n + max(2, int(n * 0.04)))
    ticks, labels = month_tick_labels(view)
    axes.set_xticks(ticks[1:])
    axes.set_xticklabels(labels[1:])
    axes.text(0.01, 0.985, checked_label(
        f"{evidence['quote']['symbol']} · รายวัน (D1) · {n} แท่งล่าสุด"),
        transform=axes.transAxes, color=COLORS["text"], fontsize=17,
        fontweight="bold", va="top", zorder=8)
    axes.text(0.01, 0.952, checked_label(
        f"ข้อมูลถึง {headline_format.thai_date(view[-1]['date'])} · "
        "แนวรับแนวต้านชุดเดียวกับในบท (กรอบรายวัน)"),
        transform=axes.transAxes, color=COLORS["axis"], fontsize=12.5,
        va="top", zorder=8)
    figure.tight_layout()
    try:
        size_bytes = image_output.save_figure(figure, output_path,
                                              facecolor=COLORS["bg"])
    finally:
        plt.close(figure)
    return {"path": str(output_path), "bars": n, "font": font_used,
            "bytes": size_bytes, "kb": image_output.kb(size_bytes),
            "levels": {"s": lower, "r": upper}}


def calculate_daily_indicator_series(rows: list[dict]):
    """คำนวณเส้นย้อนหลังของอินดิเคเตอร์ 16 ตัวจาก OHLC ก้อนเดียวกัน

    ใช้สูตรเดียวกับชุด public (RSI rolling, ADX Wilder) และคำนวณบนประวัติทั้งหมดก่อนตัดช่วงแสดงผล
    เพื่อไม่ให้ต้นเส้นของภาพเปลี่ยนตามจำนวนแท่งที่เลือกซูม
    """
    import numpy as np
    import pandas as pd

    frame = pd.DataFrame(rows).copy()
    if len(frame) < 200:
        raise ValueError("ต้องมีอย่างน้อย 200 แท่งเพื่อวาดอินดิเคเตอร์ครบ 16 ตัว")
    for key in ("open", "high", "low", "close"):
        frame[key] = pd.to_numeric(frame[key], errors="raise")
    close, high, low = frame["close"], frame["high"], frame["low"]

    for period in (10, 20, 50, 100, 200):
        frame[f"SMA{period}"] = close.rolling(period).mean()
        frame[f"EMA{period}"] = close.ewm(span=period, adjust=False,
                                            min_periods=period).mean()

    delta = close.diff()
    # ผู้ให้ข้อมูลนิยาม RSI ชุด public ด้วยค่าเฉลี่ย 14 แท่งแบบ rolling
    # (ตรวจปลายเส้นกับค่า RSI ใน snapshot) ไม่ใช่ Wilder recursive average
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    frame["RSI(14)"] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    frame["MACD(12,26)"] = (close.ewm(span=12, adjust=False, min_periods=26).mean()
                             - close.ewm(span=26, adjust=False, min_periods=26).mean())
    frame["MACD signal"] = frame["MACD(12,26)"].ewm(
        span=9, adjust=False, min_periods=9).mean()
    frame["MACD histogram"] = frame["MACD(12,26)"] - frame["MACD signal"]
    low14, high14 = low.rolling(14).min(), high.rolling(14).max()
    frame["Stochastic(14)"] = 100 * (close - low14) / (high14 - low14)
    typical = (high + low + close) / 3
    mean_deviation = typical.rolling(20).apply(
        lambda values: np.mean(np.abs(values - np.mean(values))), raw=True)
    frame["CCI(20)"] = (typical - typical.rolling(20).mean()) / (0.015 * mean_deviation)
    frame["Momentum(10)"] = close - close.shift(10)

    previous_close = close.shift(1)
    true_range = pd.concat((high - low, (high - previous_close).abs(),
                            (low - previous_close).abs()), axis=1).max(axis=1)
    up_move, down_move = high.diff(), -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
                        index=frame.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
                         index=frame.index)
    atr = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False,
                                min_periods=14).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False,
                                  min_periods=14).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    frame["ADX(14)"] = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    return frame


def _indicator_endpoint_checks(frame, evidence: dict, names=None) -> list[dict]:
    checks = []
    published = evidence.get("daily", {}).get("indicators") or {}
    selected = names or published.keys()
    for name in selected:
        item = published.get(name) or {}
        if name not in frame or item.get("value") is None:
            continue
        calculated = float(frame[name].iloc[-1])
        reference = float(item["value"])
        checks.append({"name": name, "calculated": calculated, "reference": reference,
                       "difference": calculated - reference})
    return checks


def validate_indicator_endpoints(checks: list[dict], expected_names=None) -> None:
    """ด่านก่อนส่งภาพ: ปลายเส้นทุกตัวต้องปัด 2 ตำแหน่งตรงกับ snapshot"""
    expected = list(expected_names or STYLE_A_FOCUS_INDICATORS)
    seen = [item["name"] for item in checks]
    if seen != expected:
        raise ValueError(f"อินดิเคเตอร์ปลายเส้นไม่ครบ: ต้องมี {expected} แต่ได้ {seen}")
    mismatches = [item for item in checks
                  if round(item["calculated"], 2) != round(item["reference"], 2)]
    if mismatches:
        detail = ", ".join(
            f"{item['name']}={item['calculated']:.4f}/{item['reference']:.4f}"
            for item in mismatches)
        raise ValueError(f"ค่าปลายเส้นไม่ตรง snapshot หลังปัด 2 ตำแหน่ง: {detail}")


def render_daily_indicator_lines(
        rows: list[dict], evidence: dict, output_path: Path, *, bars: int = 120,
        verify_endpoints: bool = True) -> dict:
    """ภาพทดลอง Style A: อินดิเคเตอร์เป็นเส้นจริง ไม่มีแนวรับแนวต้าน/กล่องข้อมูล"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    font_used = _thai_font()
    series_rows = [dict(row) for row in rows]
    # แท่งวันปัจจุบันขยับระหว่างวัน: ล็อกปลายเส้นให้ตรง snapshot ที่สร้างบท
    # ไม่เช่นนั้นการดึง series ภายหลังจะได้ close ใหม่และเทียบกับค่าที่อ้างในบทไม่ได้
    snapshot_tail = (evidence.get("recent_daily") or [])[-1:]
    if snapshot_tail and series_rows and str(series_rows[-1].get("date")) == str(
            snapshot_tail[0].get("t", ""))[:10]:
        tail = snapshot_tail[0]
        for source, target in (("o", "open"), ("h", "high"),
                               ("l", "low"), ("c", "close")):
            series_rows[-1][target] = float(tail[source])
    frame = calculate_daily_indicator_series(series_rows)
    checks = _indicator_endpoint_checks(frame, evidence, STYLE_A_FOCUS_INDICATORS)
    if verify_endpoints:
        validate_indicator_endpoints(checks)
    view_frame = frame.iloc[-bars:].copy()
    view = view_frame.to_dict("records")
    if not view:
        raise ValueError("ไม่มีแท่งรายวันให้วาดภาพ Style A")
    n = len(view)
    x = list(range(n))
    price_lines = (
        ("EMA10", "#e05260", "solid"),
        ("EMA20", "#e69f00", "solid"),
        ("SMA50", "#38bfc3", "solid"),
        ("SMA200", "#485bc7", "solid"),
    )
    oscillators = [
        ("RSI(14)", (30, 70)), ("MACD(12,26)", (0,)),
    ]

    figure = plt.figure(figsize=FIGURE_SIZE, dpi=DPI, facecolor=COLORS["bg"])
    grid = figure.add_gridspec(2, 2, height_ratios=(2.25, 1.1),
                               hspace=0.10, wspace=0.08)
    price_axes = figure.add_subplot(grid[0, :])
    _style_axes(price_axes)
    _draw_candles(price_axes, view, Rectangle)
    for name, color, line_style in price_lines:
        price_axes.plot(x, view_frame[name], color=color, linewidth=1.9,
                        linestyle=line_style, label=name, zorder=4)
    _fit_y(price_axes, view, [], [])
    price_axes.set_xlim(-1, n)
    price_axes.set_xticks([])
    legend_handles, legend_labels = price_axes.get_legend_handles_labels()
    figure.legend(legend_handles, legend_labels, loc="upper left", ncol=4,
                  fontsize=10, frameon=False, bbox_to_anchor=(0.035, 0.925),
                  handlelength=3.2, columnspacing=1.5, borderaxespad=0)

    published = evidence.get("daily", {}).get("indicators") or {}
    for index, (name, guides) in enumerate(oscillators):
        axes = figure.add_subplot(grid[1, index])
        _style_axes(axes)
        if name == "MACD(12,26)":
            histogram = view_frame["MACD histogram"]
            bar_colors = ["#2aa79b" if value >= 0 else "#df5964" for value in histogram]
            axes.bar(x, histogram, color=bar_colors, width=0.72, alpha=0.55, zorder=2)
            axes.plot(x, view_frame[name], color="#2878b5", linewidth=1.7,
                      label="MACD", zorder=3)
            axes.plot(x, view_frame["MACD signal"], color="#e69f00", linewidth=1.55,
                      label="Signal", zorder=3)
            axes.legend(loc="lower left", ncol=2, fontsize=8.5, frameon=False,
                        handlelength=2.4)
        else:
            axes.plot(x, view_frame[name], color="#334155", linewidth=1.65)
        for guide in guides:
            axes.axhline(guide, color="#a8b0bd", linewidth=0.9,
                         linestyle=(0, (4, 3)), zorder=1)
        axes.set_xlim(-1, n)
        item = published.get(name, {})
        signal = item.get("signal", "neutral")
        latest = float(view_frame[name].iloc[-1])
        axes.text(0.015, 0.94, name, transform=axes.transAxes, va="top",
                  color=COLORS["text"], fontsize=10.2, fontweight="bold")
        axes.text(0.985, 0.94,
                  checked_label(f"ล่าสุด {latest:,.2f} · {SIGNAL_THAI.get(signal, 'กลาง')}"),
                  transform=axes.transAxes, ha="right", va="top", fontsize=9.2,
                  color=SIGNAL_COLORS.get(signal, SIGNAL_COLORS["neutral"]))
        ticks, labels = month_tick_labels(view)
        axes.set_xticks(ticks[1:])
        axes.set_xticklabels(labels[1:], fontsize=8.5)

    counts = {key: 0 for key in SIGNAL_THAI}
    for name in STYLE_A_FOCUS_INDICATORS:
        item = published.get(name) or {}
        signal = item.get("signal", "neutral")
        counts[signal if signal in counts else "neutral"] += 1
    figure.suptitle(checked_label(
        f"{evidence['quote']['symbol']} · รายวัน (D1) · {n} แท่ง · 6 อินดิเคเตอร์หลัก"),
        x=0.035, y=0.99, ha="left", fontsize=17, fontweight="bold",
        color=COLORS["text"])
    figure.text(0.035, 0.946, checked_label(
        f"ข้อมูลถึง {headline_format.thai_date(view[-1]['date'])} · "
        f"ซื้อ {counts['buy']} · ขาย {counts['sell']} · กลาง {counts['neutral']} · "
        "เส้นราคา: EMA10 · EMA20 · SMA50 · SMA200 | ด้านล่าง: RSI · MACD"),
        fontsize=10.8, color=COLORS["axis"])
    figure.subplots_adjust(left=0.025, right=0.965, top=0.882, bottom=0.035)
    try:
        size_bytes = image_output.save_figure(figure, output_path,
                                              facecolor=COLORS["bg"])
    finally:
        plt.close(figure)
    return {"path": str(output_path), "bars": n, "font": font_used,
            "bytes": size_bytes, "kb": image_output.kb(size_bytes),
            "levels": {"s": [], "r": []}, "indicator_count": len(checks),
            "signal_counts": counts, "endpoint_checks": checks}


def _h4_tick_labels(view: list[dict]) -> tuple[list[int], list[str]]:
    """แกนเวลาแบบ 4 ชม. — เวลา HH:MM ทุกแท่งเว้นแท่ง · ขึ้นวันใหม่กำกับวันที่ไทย

    จงใจไม่มีปีบนแกน (ช่วง 4 วันไม่มีทางคร่อมปี) — เลี่ยงเรื่องระบบปีทั้งชุด
    """
    ticks, labels = [], []
    previous_day = None
    for index, row in enumerate(view):
        stamp = str(row["t"]).replace("T", " ")
        day_text, clock = stamp.split(" ")[0], stamp.split(" ")[1][:5]
        if day_text != previous_day:
            previous_day = day_text
            year, month, day = day_text.split("-")
            labels.append(f"{int(day)} {headline_format.MONTH_ABBR[int(month) - 1]}")
            ticks.append(index)
        elif index % 2 == 0:
            labels.append(clock)
            ticks.append(index)
    return ticks, [checked_label(label) for label in labels]


def render_h4(evidence: dict, output_path: Path,
              *, levels: tuple[list[float], list[float]] | None = None) -> dict:
    """ภาพราย 4 ชั่วโมง — แทนหมุด `[[chart:4h|...]]` · ใช้ 24 แท่งจาก snapshot

    ⚠️ แท่งท้ายสุดของ 4h อาจยังเดินอยู่ (สไตล์ A เป็นบทสภาพสด ตลาดยังไม่ปิด
    โดยประกาศในบทเองอยู่แล้ว) — ห้ามใส่คำว่า "ปิด" บนภาพนี้
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    font_used = _thai_font()
    view = list(evidence.get("recent_by_tf", {}).get("4h") or [])
    if len(view) < 8:
        raise ValueError(f"แท่ง 4h มี {len(view)} ตัว ไม่พอวาดภาพที่อ่านรู้เรื่อง")
    view = view[-H4_BARS:]
    n = len(view)
    lower, upper = levels if levels is not None else sr_lines(evidence)

    figure, axes = plt.subplots(figsize=FIGURE_SIZE, dpi=DPI)
    figure.patch.set_facecolor(COLORS["bg"])
    _style_axes(axes)
    _draw_candles(axes, view, Rectangle, o="o", h="h", l="l", c="c")
    _fit_y(axes, view, lower, upper, h="h", l="l")
    _draw_levels(axes, evidence, lower, upper, n)
    axes.set_xlim(-1, n + max(2, int(n * 0.06)))
    ticks, labels = _h4_tick_labels(view)
    axes.set_xticks(ticks)
    axes.set_xticklabels(labels)
    axes.text(0.01, 0.985, checked_label(
        f"{evidence['quote']['symbol']} · ราย 4 ชั่วโมง · {n} แท่งล่าสุด"),
        transform=axes.transAxes, color=COLORS["text"], fontsize=17,
        fontweight="bold", va="top", zorder=8)
    axes.text(0.01, 0.952, checked_label(
        "กรอบจับจังหวะ · แนวรับแนวต้านชุดเดียวกับในบท (กรอบรายวัน) · "
        "ข้อมูล ณ เวลาผลิตบท แท่งขวาสุดอาจยังเดินอยู่"),
        transform=axes.transAxes, color=COLORS["axis"], fontsize=12.5,
        va="top", zorder=8)
    figure.tight_layout()
    try:
        size_bytes = image_output.save_figure(figure, output_path,
                                              facecolor=COLORS["bg"])
    finally:
        plt.close(figure)
    return {"path": str(output_path), "bars": n, "font": font_used,
            "bytes": size_bytes, "kb": image_output.kb(size_bytes),
            "levels": {"s": lower, "r": upper}}


def swap_pins_for_images(markdown: str, daily_name: str, h4_name: str) -> str:
    """ฉบับแนบภาพ — แทนบรรทัดหมุดด้วยการอ้างภาพ (ห้ามเหลือหมุดปนภาพ = กราฟซ้ำ)

    alt text จงใจไม่มีตัวเลข — เลขบนภาพมีทะเบียนของมันแล้ว ไม่เพิ่มเลขให้ด่านตรวจนับ
    """
    lines = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("[[chart:1day"):
            lines.append(f"![กราฟรายวันระยะซูม เห็นแท่งเทียนและแนวรับแนวต้านชัดเจน]({daily_name})")
        elif stripped.startswith("[[chart:4h"):
            lines.append(f"![กราฟรายสี่ชั่วโมง กรอบจับจังหวะพร้อมแนวรับแนวต้าน]({h4_name})")
        else:
            lines.append(line)
    return "\n".join(lines) + ("\n" if markdown.endswith("\n") else "")
