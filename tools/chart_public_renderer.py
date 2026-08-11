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
