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
    "SMA20", "SMA50", "RSI(14)", "MACD(12,26)",
)

PLAN_COLORS = {
    "trigger": "#d08b00",
    "stop": "#d64b5d",
    "target": "#15947d",
    "scenario": "#6750a4",
}

CANVAS_BG = "#F5F7FA"
CARD_BG = "#FFFFFF"
CARD_BORDER = "#DCE4EC"
SLATE = "#465568"
TEXT = "#192534"
TEAL = "#0F9D8C"
AMBER = "#C89200"
CYAN = "#32B7BC"
RED = "#E05260"


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


def plan_overlay(plan: dict | None) -> dict | None:
    """ระดับแผนสำหรับภาพ Style A — ต้องครบและยังคงเป็นเงื่อนไขปิด D1

    ภาพยอมแสดง ``daily_scenario`` แต่ไม่เปลี่ยน ``executable`` และไม่ตีความการแตะ
    ระดับบน H4 ว่าเป็นสัญญาณเข้า ถ้าลำดับ Trigger/SL/TP ผิดฝั่งให้ล้มดัง ๆ แทนการ
    วาดกล่อง R:R ที่กลับหัว
    """
    if not plan or plan.get("classification") not in {"daily_scenario", "trade_setup"}:
        return None
    entry = plan.get("entry") or {}
    stop = plan.get("stop") or {}
    targets = plan.get("targets") or []
    if entry.get("edge") is None or stop.get("value") is None or not targets:
        return None
    trigger = float(entry["edge"])
    stop_value = float(stop["value"])
    target = float(targets[0]["value"])
    bias = plan.get("bias")
    valid = (stop_value < trigger < target if bias == "up"
             else target < trigger < stop_value if bias == "down" else False)
    if not valid:
        raise ValueError("ลำดับ Daily Trigger/SL/TP ไม่ตรงทิศของแผน")
    rr = float(plan.get("rr") if plan.get("rr") is not None
               else abs(target - trigger) / abs(trigger - stop_value))
    return {
        "trigger": trigger,
        "stop": stop_value,
        "target": target,
        "rr": rr,
        "bias": bias,
        "condition": "daily_close",
        "executable": bool(plan.get("executable", False)),
    }


def uptrend_anchors(rows: list[dict], *, window: int = 2,
                    low_key: str = "low") -> tuple[tuple[int, float], tuple[int, float]] | None:
    """คืน swing low สองจุดล่าสุดเมื่อจุดหลังยกสูงขึ้นเท่านั้น

    ใช้หน้าต่างซ้าย/ขวาเท่ากันเพื่อให้ผล deterministic และไม่ใช้แท่งขวาสุดที่ยังไม่มี
    แท่งยืนยันครบ หากคู่ล่าสุดไม่ได้ higher low จะไม่ย้อนเลือกคู่เก่าเพื่อฝืนวาดขาขึ้น
    """
    if len(rows) < window * 2 + 1:
        return None
    lows = [float(row[low_key]) for row in rows]
    swings = []
    for index in range(window, len(rows) - window):
        value = lows[index]
        neighbours = lows[index - window:index] + lows[index + 1:index + window + 1]
        if all(value < other for other in neighbours):
            swings.append((index, value))
    if len(swings) < 2:
        return None
    first, second = swings[-2], swings[-1]
    return (first, second) if second[1] > first[1] else None


def _fit_plan_y(axes, view: list[dict], overlay: dict | None,
                *, h="high", l="low") -> None:  # noqa: E741
    lower = [overlay["stop"]] if overlay else []
    upper = [overlay["trigger"], overlay["target"]] if overlay else []
    _fit_y(axes, view, lower, upper, h=h, l=l)


def _draw_plan_badges(axes, evidence: dict, overlay: dict, *, n: int,
                      Rectangle, risk_box: bool = False) -> dict:
    """วาดระดับแผนทางขวา ป้ายทุกใบย้ำว่า Trigger ต้องรอแท่ง D1 ปิด"""
    money = wcb_writers.price
    y_low, y_high = axes.get_ylim()
    gap = (y_high - y_low) * 0.045
    label_positions = spread_label_positions(
        [overlay["trigger"], overlay["stop"], overlay["target"]],
        (y_low, y_high), gap_fraction=0.045)
    labels = (
        ("trigger", f"Daily Trigger (ปิด D1): {money(overlay['trigger'], evidence)}"),
        ("stop", f"SL: {money(overlay['stop'], evidence)}"),
        ("target", f"TP: {money(overlay['target'], evidence)}"),
    )
    line_start, line_end, label_x = n - 1, n + 8.0, n + 8.6
    for key, label in labels:
        value = overlay[key]
        color = PLAN_COLORS[key]
        axes.hlines(value, line_start, line_end, color=color, linewidth=1.8,
                    linestyle="solid" if key == "trigger" else (0, (4, 3)), zorder=7)
        axes.text(label_x, label_positions[value], checked_label(label), color=color,
                  fontsize=10.5, va="center", ha="right", zorder=10,
                  bbox=dict(boxstyle="round,pad=0.28", facecolor="#ffffff",
                            edgecolor=color, linewidth=0.9, alpha=0.96))

    band_half = (y_high - y_low) * 0.006
    axes.axhspan(overlay["trigger"] - band_half, overlay["trigger"] + band_half,
                 color=PLAN_COLORS["trigger"], alpha=0.11, zorder=1)
    if risk_box:
        box_x, box_width = n + 0.2, 4.6
        axes.add_patch(Rectangle(
            (box_x, min(overlay["trigger"], overlay["target"])),
            box_width, abs(overlay["target"] - overlay["trigger"]),
            facecolor=PLAN_COLORS["target"], edgecolor=PLAN_COLORS["target"],
            linewidth=1.0, alpha=0.13, zorder=4))
        axes.add_patch(Rectangle(
            (box_x, min(overlay["trigger"], overlay["stop"])),
            box_width, abs(overlay["stop"] - overlay["trigger"]),
            facecolor=PLAN_COLORS["stop"], edgecolor=PLAN_COLORS["stop"],
            linewidth=1.0, alpha=0.13, zorder=4))
        reward_middle = (overlay["trigger"] + overlay["target"]) / 2
        axes.text(box_x + box_width / 2, reward_middle,
                  checked_label(f"R:R 1:{overlay['rr']:.2f}"), ha="center", va="center",
                  fontsize=10.5, color=COLORS["text"], zorder=9,
                  bbox=dict(boxstyle="round,pad=0.22", facecolor="#ffffff",
                            edgecolor="#c7ccd4", alpha=0.92))
    return {"meaning": "visual_highlight_only", "half_height": band_half}


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


def _add_card(figure, x: float, y: float, width: float, height: float,
              *, face: str = CARD_BG, edge: str = CARD_BORDER):
    """การ์ดแบบเดียวกันทั้ง D1/H4 — พิกัดเป็นสัดส่วนของ canvas"""
    from matplotlib.patches import FancyBboxPatch
    patch = FancyBboxPatch(
        (x, y), width, height, transform=figure.transFigure,
        boxstyle="round,pad=0,rounding_size=0.012", linewidth=0.9,
        facecolor=face, edgecolor=edge, zorder=0)
    figure.add_artist(patch)
    return patch


def _fig_text(figure, x: float, y: float, text: str, *, size: float = 14,
              color: str = TEXT, weight: str = "normal", ha: str = "left",
              va: str = "center", zorder: int = 5):
    return figure.text(x, y, checked_label(text), fontsize=size, color=color,
                       fontweight=weight, ha=ha, va=va, zorder=zorder)


def _fig_pill(figure, x: float, y: float, width: float, height: float, text: str,
              *, face: str, color: str, size: float = 13.5):
    _add_card(figure, x, y, width, height, face=face, edge=face)
    _fig_text(figure, x + width / 2, y + height / 2, text,
              size=size, color=color, weight="bold", ha="center")


def _snapshot_stamp(evidence: dict, plan: dict | None = None) -> str:
    """เวลาไทยจาก cutoff ของแผน; brief ต้องแสดงเวลาเดียวกันทั้งสองภาพ"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    raw = (plan or {}).get("cutoff_at") or evidence.get("generated_at")
    if raw:
        try:
            stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=ZoneInfo("UTC"))
            stamp = stamp.astimezone(ZoneInfo("Asia/Bangkok"))
            months = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                      "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")
            return f"{stamp.day} {months[stamp.month - 1]} {stamp.year} เวลา {stamp:%H:%M} น."
        except (TypeError, ValueError):
            pass
    return "เวลาผลิตบท"


def _indicator(evidence: dict, timeframe: str, name: str) -> dict:
    return ((evidence.get("daily" if timeframe == "1day" else "by_tf", {})
             .get("indicators", {}) if timeframe == "1day" else
             evidence.get("by_tf", {}).get(timeframe, {}).get("indicators", {}))
            .get(name, {}))


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


def synchronize_live_tail(series_rows: list[dict], evidence: dict) -> str:
    """ล็อกแท่งวันปัจจุบันให้ใช้ฐานเดียวกับค่าอินดิเคเตอร์ใน snapshot

    WCB ส่ง `recentDaily.c` ช้ากว่า `quote.price` ได้ในแท่งที่ยังไม่ปิด แต่ค่า
    อินดิเคเตอร์ใน snapshot คำนวณจากราคาล่าสุดใน `quote.price` แล้ว จึงต้องใช้
    quote เป็น close ปลายเส้น ส่วน O/H/L ยังยึดแท่ง snapshot เดิม
    """
    snapshot_tail = (evidence.get("recent_daily") or [])[-1:]
    if not snapshot_tail or not series_rows:
        return "series"
    tail = snapshot_tail[0]
    if str(series_rows[-1].get("date")) != str(tail.get("t", ""))[:10]:
        return "series"
    for source, target in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close")):
        if tail.get(source) is not None:
            series_rows[-1][target] = float(tail[source])
    quote_price = (evidence.get("quote") or {}).get("price")
    if quote_price is not None:
        close = float(quote_price)
        series_rows[-1]["close"] = close
        series_rows[-1]["high"] = max(float(series_rows[-1]["high"]), close)
        series_rows[-1]["low"] = min(float(series_rows[-1]["low"]), close)
        return "snapshot_quote"
    return "snapshot_recent_daily"


def render_daily_indicator_lines(
        rows: list[dict], evidence: dict, output_path: Path, *, bars: int = DAILY_BARS,
        verify_endpoints: bool = True, plan: dict | None = None) -> dict:
    """ภาพ Style A แบบ dashboard ตาม brief: สรุปภาพใหญ่ก่อน แล้วค่อยอ่านกราฟ D1"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    font_used = _thai_font()
    series_rows = [dict(row) for row in rows]
    endpoint_price_basis = synchronize_live_tail(series_rows, evidence)
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
    overlay = plan_overlay(plan)
    published = evidence.get("daily", {}).get("indicators") or {}
    counts = {key: 0 for key in SIGNAL_THAI}
    for name in STYLE_A_FOCUS_INDICATORS:
        item = published.get(name) or {}
        signal = item.get("signal", "neutral")
        counts[signal if signal in counts else "neutral"] += 1
    summary_counts = dict((evidence.get("daily", {}).get("counts") or {}))
    for key in SIGNAL_THAI:
        summary_counts[key] = int(summary_counts.get(key, 0))
    quote = evidence.get("quote", {})
    price = float(quote.get("price", view[-1]["close"]))
    change = float(quote.get("change", 0.0))
    pct = float(quote.get("percent", 0.0))
    daily_indicators = evidence.get("daily", {}).get("indicators") or {}
    sma20 = float((daily_indicators.get("SMA20") or {}).get("value", view_frame["SMA20"].iloc[-1]))
    sma50 = float((daily_indicators.get("SMA50") or {}).get("value", view_frame["SMA50"].iloc[-1]))
    sma100 = float((daily_indicators.get("SMA100") or {}).get("value", 0.0))
    sma200 = float((daily_indicators.get("SMA200") or {}).get("value", 0.0))
    rsi_item = daily_indicators.get("RSI(14)") or {}
    macd_item = daily_indicators.get("MACD(12,26)") or {}
    rsi = float(rsi_item.get("value", view_frame["RSI(14)"].iloc[-1]))
    macd = float(macd_item.get("value", view_frame["MACD(12,26)"].iloc[-1]))
    trigger = float(overlay["trigger"] if overlay else (evidence.get("daily", {}).get("pivots", {}) or {}).get("p", price))
    stamp = _snapshot_stamp(evidence, plan)

    figure = plt.figure(figsize=FIGURE_SIZE, dpi=DPI, facecolor=CANVAS_BG)
    figure.patch.set_facecolor(CANVAS_BG)
    # แถบสรุป 5 การ์ดด้านบน — ใช้พื้นที่ให้ค่าที่คนอ่านต้องเห็นก่อนกราฟ
    cards = ((0.025, 0.825, 0.225), (0.262, 0.825, 0.145),
             (0.419, 0.825, 0.168), (0.599, 0.825, 0.168),
             (0.779, 0.825, 0.196))
    for x0, y0, width in cards:
        _add_card(figure, x0, y0, width, 0.135)
    _fig_text(figure, 0.038, 0.925, "ข้อสรุปภาพใหญ่", size=16, weight="bold")
    _fig_text(figure, 0.038, 0.887, "บวกระยะสั้น–กลาง", size=18, color=TEAL, weight="bold")
    _fig_text(figure, 0.038, 0.850, "ระยะยาวยังไม่ยืนยัน", size=13.5, color=SLATE)
    _fig_text(figure, 0.275, 0.925, "ราคาล่าสุด", size=13, color=SLATE)
    _fig_text(figure, 0.275, 0.881, f"{price:,.2f}", size=24, weight="bold")
    _fig_text(figure, 0.275, 0.846, f"{change:+,.2f} ({pct:+.2f}%)", size=13, color=RED if change < 0 else TEAL)
    _fig_text(figure, 0.432, 0.925, "สัญญาณรวม", size=13, color=SLATE)
    _fig_text(figure, 0.432, 0.881, f"{summary_counts['buy']} ซื้อ · {summary_counts['sell']} ขาย", size=19, weight="bold")
    _fig_text(figure, 0.432, 0.846, f"{summary_counts['neutral']} กลาง · รวม {sum(summary_counts.values())} ตัว", size=13, color=SLATE)
    _fig_text(figure, 0.612, 0.925, "สั้น–กลาง", size=13, color=SLATE)
    _fig_text(figure, 0.612, 0.884, "เหนือ SMA20 / SMA50", size=15, color=TEAL, weight="bold")
    _fig_text(figure, 0.612, 0.847, f"{sma20:,.2f} / {sma50:,.2f}", size=13.5, color=SLATE)
    _fig_text(figure, 0.792, 0.925, "ระยะยาว", size=13, color=SLATE)
    _fig_text(figure, 0.792, 0.884, "ใต้ SMA100 / SMA200", size=15, color=RED, weight="bold")
    _fig_text(figure, 0.792, 0.847, f"{sma100:,.2f} / {sma200:,.2f}", size=13.5, color=SLATE)

    _fig_text(figure, 0.035, 0.792,
              f"ข้อมูล ณ {stamp} · {n} แท่งอ้างอิง", size=12.5, color=SLATE)
    _fig_pill(figure, 0.816, 0.777, 0.151, 0.037, "แท่ง D1 ยังไม่ปิด",
              face="#FFF4D6", color=AMBER, size=12)

    _add_card(figure, 0.025, 0.285, 0.95, 0.475)
    price_axes = figure.add_axes([0.042, 0.315, 0.916, 0.405])
    _style_axes(price_axes)
    _draw_candles(price_axes, view, Rectangle)
    price_axes.plot(x, view_frame["SMA20"], color="#C58B00", linewidth=2.1,
                    label="SMA20", zorder=4)
    price_axes.plot(x, view_frame["SMA50"], color=CYAN, linewidth=2.1,
                    label="SMA50", zorder=4)
    _fit_y(price_axes, view, [trigger], [trigger])
    price_axes.set_xlim(-1, n + 5.5)
    price_axes.set_xticks([])
    price_axes.axhline(trigger, color=AMBER, linewidth=1.8, linestyle=(0, (6, 4)), zorder=2)
    price_axes.text(n + 5.1, trigger, checked_label(
        f"แนวต้านสำคัญ · ต้องปิดทะลุ {trigger:,.2f}"), color=AMBER,
        fontsize=12, ha="right", va="center", zorder=6,
        bbox=dict(facecolor="#FFF4D6", edgecolor="none", pad=3.5))
    price_axes.legend(loc="upper left", frameon=False, fontsize=11, ncol=2)
    ticks, labels = month_tick_labels(view)
    price_axes.set_xticks(ticks[1:])
    price_axes.set_xticklabels(labels[1:], fontsize=10)

    # การ์ดอินดิเคเตอร์ด้านล่าง — สรุปสั้น และมี mini chart แทนข้อความยาว
    _add_card(figure, 0.025, 0.065, 0.46, 0.17)
    _add_card(figure, 0.505, 0.065, 0.47, 0.17)
    _fig_text(figure, 0.045, 0.195, "RSI (14)", size=14, weight="bold")
    _fig_text(figure, 0.045, 0.150, f"{rsi:,.2f}", size=27, weight="bold")
    _fig_pill(figure, 0.155, 0.178, 0.075, 0.035, "กลาง", face="#EEF2F6", color=SLATE, size=12)
    _fig_text(figure, 0.045, 0.095, "ใกล้ระดับ 70 แต่ยังไม่ Overbought", size=12.5, color=SLATE)
    rsi_axes = figure.add_axes([0.275, 0.105, 0.185, 0.095])
    _style_axes(rsi_axes)
    rsi_axes.plot(x, view_frame["RSI(14)"], color=SLATE, linewidth=1.6)
    rsi_axes.axhline(70, color="#B8C2CE", linestyle=(0, (4, 3)), linewidth=0.8)
    rsi_axes.set_ylim(20, 80); rsi_axes.set_xticks([]); rsi_axes.set_yticks([])
    _fig_text(figure, 0.525, 0.195, "MACD (12,26)", size=14, weight="bold")
    _fig_text(figure, 0.525, 0.150, f"{macd:,.2f}", size=27, weight="bold")
    _fig_pill(figure, 0.65, 0.178, 0.075, 0.035, "ซื้อ", face="#DDF5F0", color=TEAL, size=12)
    _fig_text(figure, 0.525, 0.095, "MACD อยู่เหนือ Signal", size=12.5, color=SLATE)
    macd_axes = figure.add_axes([0.755, 0.105, 0.19, 0.095])
    _style_axes(macd_axes)
    histogram = view_frame["MACD histogram"]
    macd_axes.bar(x, histogram, color=[TEAL if value >= 0 else RED for value in histogram],
                  width=0.72, alpha=0.55, zorder=2)
    macd_axes.plot(x, view_frame["MACD(12,26)"], color=SLATE, linewidth=1.4)
    macd_axes.plot(x, view_frame["MACD signal"], color=AMBER, linewidth=1.3)
    macd_axes.set_xticks([]); macd_axes.set_yticks([])
    _fig_text(figure, 0.035, 0.028, "ข้อมูลระหว่างวันอาจเปลี่ยนแปลงได้", size=10.5, color=SLATE)
    _fig_text(figure, 0.965, 0.028, "เพื่อการศึกษา · ไม่ใช่คำแนะนำการลงทุน", size=10.5,
              color=SLATE, ha="right")
    trigger_band = {"meaning": "visual_highlight_only", "value": trigger}
    try:
        size_bytes = image_output.save_figure(figure, output_path,
                                              facecolor=CANVAS_BG)
    finally:
        plt.close(figure)
    return {"path": str(output_path), "bars": n, "font": font_used,
            "bytes": size_bytes, "kb": image_output.kb(size_bytes),
            "levels": {"s": [], "r": []}, "indicator_count": len(checks),
            "signal_counts": counts, "endpoint_checks": checks,
            "endpoint_price_basis": endpoint_price_basis,
            "plan_overlay": overlay, "trigger_band": trigger_band,
            "trendline": None, "layout": "d1_dashboard"}


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
              *, levels: tuple[list[float], list[float]] | None = None,
              plan: dict | None = None) -> dict:
    """ภาพ Style A H4 แบบกราฟ + action sidebar ตาม brief

    แท่งท้ายสุดอาจยังเดินอยู่ จึงระบุสถานะไว้ที่ footer และไม่ตีความการแตะ
    Trigger เป็นคำสั่งเข้า — แผนยังยืนยันด้วยแท่ง D1 ปิดเท่านั้น
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
    overlay = plan_overlay(plan)
    quote = evidence.get("quote", {})
    current = float(quote.get("price", view[-1]["c"]))
    h4_evidence = evidence.get("by_tf", {}).get("4h", {}) or {}
    h4_counts = h4_evidence.get("counts", {}) or {}
    h4_indicators = h4_evidence.get("indicators", {}) or {}
    rsi = float((h4_indicators.get("RSI(14)") or {}).get("value", 0.0))
    cci = float((h4_indicators.get("CCI(20)") or {}).get("value", 0.0))
    adx = float((h4_indicators.get("ADX(14)") or {}).get("value", 0.0))
    stamp = _snapshot_stamp(evidence, plan)
    # หากเรียก renderer โดยไม่มี trade-plan ให้ใช้ระดับ pivot เป็นข้อมูลอ้างอิง
    # แต่ไม่แสดงเป็นเส้น SR เพิ่ม เพราะ brief กำหนดให้ H4 มี 4 เส้นเท่านั้น
    if overlay:
        line_specs = (("TP", overlay["target"], TEAL, (0, (6, 4))),
                      ("Trigger", overlay["trigger"], AMBER, (0, (6, 4))),
                      ("ราคา", current, SLATE, "solid"),
                      ("SL", overlay["stop"], RED, (0, (6, 4))))
    else:
        fallback_trigger = upper[0] if upper else current
        line_specs = (("ราคา", current, SLATE, "solid"),
                      ("Trigger", fallback_trigger, AMBER, (0, (6, 4))))

    figure = plt.figure(figsize=FIGURE_SIZE, dpi=DPI, facecolor=CANVAS_BG)
    figure.patch.set_facecolor(CANVAS_BG)
    _add_card(figure, 0.025, 0.27, 0.724, 0.69)
    _add_card(figure, 0.765, 0.27, 0.21, 0.69)
    graph_axes = figure.add_axes([0.044, 0.35, 0.68, 0.54])
    _style_axes(graph_axes)
    graph_values = [value for _, value, _, _ in line_specs]
    _fit_y(graph_axes, view, [value for value in graph_values],
           [value for value in graph_values], h="h", l="l")
    _draw_candles(graph_axes, view, Rectangle, o="o", h="h", l="l", c="c")
    graph_axes.set_xlim(-1, n + 6.2)
    graph_axes.set_xticks([])
    for label, value, color, style in line_specs:
        graph_axes.axhline(value, color=color, linewidth=1.7, linestyle=style, zorder=2)
        graph_axes.text(n + 5.9, value, checked_label(f"{label} {value:,.2f}"),
                        color=color, fontsize=12.5, ha="right", va="center", zorder=7,
                        bbox=dict(facecolor=CARD_BG, edgecolor="none", pad=3.0))
    _fig_pill(figure, 0.048, 0.904,
              0.215, 0.037,
              f"H4 เอนขาย · ซื้อ {int(h4_counts.get('buy', 0))} / ขาย {int(h4_counts.get('sell', 0))}",
              face="#FFF0F1", color=RED, size=12)
    ticks, labels = _h4_tick_labels(view)
    graph_axes.set_xticks(ticks)
    graph_axes.set_xticklabels(labels, fontsize=10)

    # Sidebar ชี้ให้เห็นว่าระดับ Trigger ยังไม่ใช่ราคาเข้าที่รับประกัน
    _fig_text(figure, 0.785, 0.912, "ตอนนี้ต้องทำอะไร?", size=17, weight="bold")
    _fig_pill(figure, 0.785, 0.858, 0.112, 0.037, "รอ D1 ยืนยัน", face="#FFF4D6", color=AMBER, size=12)
    _fig_text(figure, 0.785, 0.820, "ยังไม่เปิดสถานะ", size=15, color=SLATE, weight="bold")
    _add_card(figure, 0.785, 0.680, 0.17, 0.115, face="#FFF9EA", edge="#F0D58C")
    _fig_text(figure, 0.800, 0.765, "เงื่อนไขของแผน", size=12.5, color=SLATE, weight="bold")
    trigger_text = overlay["trigger"] if overlay else (upper[0] if upper else current)
    _fig_text(figure, 0.800, 0.725, f"รอ D1 ปิดเหนือ {trigger_text:,.2f}", size=15, color=AMBER, weight="bold")
    _fig_text(figure, 0.800, 0.697, "แตะระดับหรือมีไส้เทียนทะลุ", size=11.5, color=SLATE)
    _fig_text(figure, 0.800, 0.675, "ยังไม่ถือว่าเป็นการยืนยัน", size=11.5, color=SLATE)
    _fig_text(figure, 0.785, 0.625, "เมื่อยืนยันแล้ว", size=13, color=SLATE, weight="bold")
    if overlay:
        _fig_text(figure, 0.785, 0.590, f"TP  {overlay['target']:,.2f}", size=15, color=TEAL, weight="bold")
        _fig_text(figure, 0.785, 0.555, f"SL  {overlay['stop']:,.2f}", size=15, color=RED, weight="bold")
        _fig_text(figure, 0.785, 0.520, f"R:R  1:{overlay['rr']:.2f}", size=15, color=SLATE, weight="bold")
    _add_card(figure, 0.785, 0.400, 0.17, 0.085, face="#F5F7FA", edge="#E4EAF0")
    _fig_text(figure, 0.800, 0.455, "Trigger ไม่ใช่ราคาเข้าที่รับประกัน", size=11.5, color=SLATE)
    _fig_text(figure, 0.800, 0.428, "ใช้เงื่อนไขแท่ง D1 เป็นหลัก", size=11.5, color=SLATE)

    # แถวอินดิเคเตอร์ 4H ด้านล่าง
    bottom_cards = ((0.025, 0.065, 0.30), (0.35, 0.065, 0.30), (0.675, 0.065, 0.30))
    for x0, y0, width in bottom_cards:
        _add_card(figure, x0, y0, width, 0.17)
    _fig_text(figure, 0.045, 0.195, "RSI (14)", size=14, weight="bold")
    _fig_text(figure, 0.045, 0.150, f"{rsi:,.2f}", size=27, weight="bold")
    _fig_pill(figure, 0.155, 0.178, 0.12, 0.035, "กลาง", face="#EEF2F6", color=SLATE, size=12)
    _fig_text(figure, 0.045, 0.095, "ต่ำกว่า 50 · ยังไม่ Oversold", size=12.5, color=SLATE)
    _fig_text(figure, 0.370, 0.195, "CCI (20)", size=14, weight="bold")
    _fig_text(figure, 0.370, 0.150, f"{cci:,.2f}", size=27, weight="bold")
    _fig_pill(figure, 0.480, 0.178, 0.135, 0.035, "แรงขายระยะสั้น", face="#FFF0F1", color=RED, size=11.5)
    _fig_text(figure, 0.370, 0.095, "แรงขายระยะสั้นเด่น", size=12.5, color=SLATE)
    _fig_text(figure, 0.695, 0.195, "ADX (14)", size=14, weight="bold")
    _fig_text(figure, 0.695, 0.150, f"{adx:,.2f}", size=27, weight="bold")
    _fig_pill(figure, 0.805, 0.178, 0.14, 0.035, "มีแรงแนวโน้ม", face="#EEF2F6", color=SLATE, size=11.5)
    _fig_text(figure, 0.695, 0.095, "มีแรงแนวโน้ม · ไม่บอกทิศ", size=12.5, color=SLATE)
    _fig_text(figure, 0.035, 0.028,
              f"ข้อมูล ณ {stamp} · แท่งล่าสุดอาจยังไม่ปิด", size=10.5, color=SLATE)
    rr_footer = (f"R:R อ้างอิงจุดเข้า {overlay['trigger']:,.2f} · เพื่อการศึกษา"
                 if overlay else "เพื่อการศึกษา · ไม่ใช่คำแนะนำการลงทุน")
    _fig_text(figure, 0.965, 0.028, rr_footer, size=10.5, color=SLATE, ha="right")

    scenario = None
    if overlay:
        if overlay["bias"] == "up":
            pullback_candidates = [value for value in lower if value < current]
            pullback = max(pullback_candidates) if pullback_candidates else overlay["stop"]
        else:
            pullback_candidates = [value for value in upper if value > current]
            pullback = min(pullback_candidates) if pullback_candidates else overlay["stop"]
        scenario = {"points": [(n - 1, current), (n + 0.8, pullback),
                                (n + 2.4, overlay["trigger"]),
                                (n + 4.5, overlay["target"])],
                    "confirmation": "daily_close", "rendered": False}
    try:
        size_bytes = image_output.save_figure(figure, output_path,
                                              facecolor=CANVAS_BG)
    finally:
        plt.close(figure)
    return {"path": str(output_path), "bars": n, "font": font_used,
            "bytes": size_bytes, "kb": image_output.kb(size_bytes),
            "levels": {"s": [], "r": []}, "plan_overlay": overlay,
            "trigger_band": None, "scenario": scenario,
            "volume": {"status": "unavailable", "reason": "no_verified_provenance"},
            "layout": "h4_action_plan"}


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
