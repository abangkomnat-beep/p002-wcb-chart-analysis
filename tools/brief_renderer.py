"""ตัววาดการ์ดภาพของบทเช้า สไตล์ F/G — วาดจาก brief artifact เท่านั้น

รูปทรงลอกจากบทจริงของ InterGold (สเปกข้อ 2.4 / 3.4) — **การ์ด** ไม่ใช่กราฟเปล่า:

    ┌──────────────────────────────────────────────┐
    │  [ชิปวันที่] [ชิปแนวรับ] [ชิปแนวต้าน]  หัวเรื่องใหญ่ │
    │  ┌────────────────────────────────────────┐  │
    │  │  แท่งเทียน + SMA50 + สิ่งที่ลากทับตามสไตล์   │  │
    │  └────────────────────────────────────────┘  │
    │  แถบท้าย: ชื่อสินทรัพย์ · กรอบเวลา · วันที่ข้อมูล   │
    └──────────────────────────────────────────────┘

สิ่งที่ลากทับต่างกันตามสไตล์ — นี่คือทั้งหมดที่ต่างกันในฝั่งภาพ:

    F  เส้นแนวนอนทึบ 2 เส้น (แนวรับ/แนวต้าน) + กล่องกรอบล่าสุด + ป้าย 2 ป้าย + ลูกศรตัว V
    G  เส้นประคู่ขนาน 2 เส้น (ช่องแนวโน้ม) + วงรีจุดแตะ + ป้าย 2 ป้าย + ลูกศรตัว J

**สิ่งที่จงใจไม่ลอก:** สีแบรนด์ โลโก้ และแถบติดต่อของ InterGold — ใช้โทนกลางของเรา
ส่วนกราฟข้างในเป็นแท่ง **รายวัน** ที่เราวาดเอง ไม่ใช่ภาพถ่ายจอ TradingView ราย 1 ชั่วโมง
⇒ แถบท้ายการ์ดจึงเขียนกรอบเวลากำกับเสมอ ห้ามให้คนเข้าใจผิดว่าเป็นกราฟรายชั่วโมง

ข้อความทุกชิ้นต้องผ่าน `consistency_gate.check_labels` ก่อนลงภาพ (ด่าน D-4.5) —
ป้ายผิดปี = โยนทั้งใบ ไม่ใช่วาดออกไปแล้วค่อยรู้ตอนขึ้นเว็บ
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import brief_story, brief_writer, chart_story, consistency_gate  # noqa: E402
from tools import image_output, wcb_source  # noqa: E402
from tools.chart_story_renderer import _thai_font, month_tick_labels, thai_date  # noqa: E402

# 1040×700 — สัดส่วนเดียวกับต้นแบบเป๊ะ (คนอ่านคุ้นกับกล่องรูปทรงนี้ในหน้าเว็บอยู่แล้ว)
FIGURE_SIZE = (10.40, 7.00)
DPI = 100

# ที่ว่างฝั่งขวาสำหรับป้ายราคาและลูกศรคาดการณ์ คิดเป็นสัดส่วนของจำนวนแท่ง
RIGHT_PAD_FRACTION = 0.26

COLORS = {
    "card": "#12233b",        # พื้นการ์ด — โทนกลางของเรา ไม่ใช่แดงของต้นแบบ
    "panel": "#ffffff",
    "grid": "#eef1f5",
    "axis": "#787b86",
    "text": "#131722",
    "card_text": "#ffffff",
    "up": "#26a69a",
    "down": "#ef5350",
    "sma": "#3949ab",
    "level": "#101418",       # เส้นแนวนอนของ F — ทึบดำแบบต้นแบบ
    "box": "#1e9e83",         # กล่องกรอบของ F — เขียวแบบต้นแบบ
    "channel": "#e5484d",     # ช่องแนวโน้มของ G — แดงเส้นประแบบต้นแบบ
    "touch": "#101418",       # วงรีจุดแตะของ G
    "arrow": "#101418",
    "chip_date": "#d5202f",
    "chip_support": "#1e9e83",
    "chip_resistance": "#f0a02a",
}


def checked(text: str) -> str:
    """ทางบังคับของข้อความทุกชิ้นก่อนลงภาพ — ด่านความสอดคล้อง D-4.5"""
    findings = consistency_gate.check_labels([text])
    if findings:
        raise ValueError(f"ป้ายภาพไม่ผ่านด่านความสอดคล้อง: {findings[0]['message']}")
    return text


def _card(figure, Rectangle) -> None:
    figure.patch.set_facecolor(COLORS["card"])
    figure.add_artist(Rectangle((0.022, 0.030), 0.956, 0.940, transform=figure.transFigure,
                                facecolor=COLORS["panel"], edgecolor="none", zorder=0))


def _chip(figure, x: float, width: float, color: str, caption: str, value: str) -> None:
    """ชิปหัวการ์ดหนึ่งใบ — คำกำกับตัวเล็กบน ค่าตัวใหญ่ล่าง (รูปแบบเดียวกับต้นแบบ)"""
    from matplotlib.patches import FancyBboxPatch

    figure.add_artist(FancyBboxPatch((x, 0.845), width, 0.052,
                                     boxstyle="round,pad=0.006,rounding_size=0.012",
                                     transform=figure.transFigure, facecolor=color,
                                     edgecolor="none", zorder=3))
    figure.text(x + width / 2, 0.871, checked(caption), transform=figure.transFigure,
                ha="center", va="center", color="#ffffff", fontsize=12, fontweight="bold",
                zorder=4)
    figure.text(x + width / 2, 0.806, checked(value), transform=figure.transFigure,
                ha="center", va="center", color=COLORS["text"], fontsize=17,
                fontweight="bold", zorder=4)


def header_title(asset: str) -> str:
    """หัวเรื่องใหญ่บนการ์ด — **สัญลักษณ์คู่เงิน ไม่ใช่ชื่อไทย** (ผู้ใช้สั่ง 2026-08-10)

    "แนวโน้มราคาโซลานา" อ่านแล้วไม่รู้ว่าคู่ไหน ส่วน "SOL/USD" ตรงกับที่คนดูกราฟใช้จริง
    เว้นวรรคก่อนสัญลักษณ์เสมอเพราะเป็นอักษรละตินต่อท้ายคำไทย (เหตุผลเดียวกับ
    `headline_format._pad`) · ชื่อไทยยังใช้ในเนื้อบทตามเดิม คนละช่องคนละหน้าที่
    """
    return f"แนวโน้มราคา {wcb_source.profile_for(asset)['symbol']}"


def _header(figure, brief: dict) -> None:
    money = brief_writer.money_for(brief)
    _chip(figure, 0.052, 0.128, COLORS["chip_date"], "ข้อมูล ณ",
          thai_date(brief["current"]["date"]))
    _chip(figure, 0.196, 0.150, COLORS["chip_support"], "แนวรับ", money(brief["support"]))
    _chip(figure, 0.360, 0.150, COLORS["chip_resistance"], "แนวต้าน", money(brief["resistance"]))
    figure.text(0.960, 0.848, checked(header_title(brief["asset"])),
                transform=figure.transFigure, ha="right", va="center",
                color=COLORS["text"], fontsize=27, fontweight="bold", zorder=4)


def _footer(figure, brief: dict) -> None:
    profile = wcb_source.profile_for(brief["asset"])
    box = brief["range_box"]
    text = (f"{profile['symbol']} · แท่งรายวัน · ช่วงที่แสดง "
            f"{thai_date(brief['display']['start_date'])} ถึง {thai_date(box['end_date'])}"
            f" · {brief_writer.STYLE_NAMES[brief['style']]}")
    figure.text(0.5, 0.062, checked(text), transform=figure.transFigure, ha="center",
                va="center", color=COLORS["axis"], fontsize=11, zorder=4)


def _style_axes(axes) -> None:
    axes.set_facecolor(COLORS["panel"])
    for spine in axes.spines.values():
        spine.set_color("#d1d4dc")
    axes.tick_params(colors=COLORS["axis"], labelsize=10)
    axes.grid(True, color=COLORS["grid"], linewidth=0.8)
    axes.yaxis.tick_right()
    axes.set_axisbelow(True)


def _draw_candles(axes, view: list[dict], Rectangle) -> None:
    width = 0.60
    for index, row in enumerate(view):
        rising = row["close"] >= row["open"]
        color = COLORS["up"] if rising else COLORS["down"]
        axes.plot([index, index], [row["low"], row["high"]], color=color,
                  linewidth=0.9, zorder=3)
        body_low = min(row["open"], row["close"])
        height = abs(row["close"] - row["open"]) or (row["high"] - row["low"]) * 0.02 or 1e-9
        axes.add_patch(Rectangle((index - width / 2, body_low), width, height,
                                 facecolor=color, edgecolor=color, linewidth=0.5, zorder=3))


def _draw_sma(axes, rows: list[dict], view_len: int) -> None:
    values = chart_story.sma([row["close"] for row in rows], 50)
    offset = len(rows) - view_len
    xs = [index for index in range(view_len) if values[offset + index] is not None]
    if len(xs) < 2:
        return
    axes.plot(xs, [values[offset + index] for index in xs], color=COLORS["sma"],
              linewidth=1.8, alpha=0.9, zorder=4)


def _level_label(axes, x: float, y: float, text: str, *, above: bool) -> None:
    axes.text(x, y, checked(text), ha="right", va="bottom" if above else "top",
              fontsize=13, fontweight="bold", color=COLORS["text"], zorder=7,
              bbox={"facecolor": "#ffffff", "edgecolor": "none", "alpha": 0.82,
                    "pad": 2.0})


def _path_arrow(axes, points: list[tuple[float, float]]) -> None:
    """ลูกศรคาดการณ์ — ลากเป็นเส้นหักแล้วติดหัวลูกศรที่ปลายช่วงสุดท้าย

    ต้นแบบวาดด้วยมือเป็นตัว V (สไตล์ F) และตัว J (สไตล์ G) · ที่นี่ใช้จุดหักชุดเดียวกัน
    ต่างกันแค่พิกัดที่ผู้เรียกส่งมา ตัววาดไม่ตัดสินรูปทรงเอง
    """
    for start, end in zip(points, points[1:-1]):
        axes.plot([start[0], end[0]], [start[1], end[1]], color=COLORS["arrow"],
                  linewidth=2.4, solid_capstyle="round", zorder=6)
    axes.annotate("", xy=points[-1], xytext=points[-2],
                  arrowprops={"arrowstyle": "-|>", "color": COLORS["arrow"],
                              "linewidth": 2.4, "mutation_scale": 22},
                  zorder=6)


def _draw_range(axes, brief: dict, view: list[dict], x_right: float, Rectangle) -> None:
    """สิ่งที่ลากทับของสไตล์ F — เส้นแนวนอน 2 เส้น + กล่องกรอบ + ป้าย + ลูกศรตัว V"""
    money = brief_writer.money_for(brief)
    box = brief["range_box"]
    support, resistance = brief["support"], brief["resistance"]
    left = -0.5

    for value in (support, resistance):
        axes.plot([left, x_right], [value, value], color=COLORS["level"],
                  linewidth=1.8, zorder=5)
    axes.add_patch(Rectangle((box["start_index"] - 0.5, box["low"]),
                             len(view) - box["start_index"], box["high"] - box["low"],
                             facecolor=COLORS["box"], edgecolor=COLORS["box"],
                             alpha=0.12, linewidth=2.0, zorder=2))
    axes.add_patch(Rectangle((box["start_index"] - 0.5, box["low"]),
                             len(view) - box["start_index"], box["high"] - box["low"],
                             facecolor="none", edgecolor=COLORS["box"],
                             linewidth=2.0, zorder=5))
    label_x = x_right - (x_right - left) * 0.015
    _level_label(axes, label_x, resistance, f"แนวต้าน {money(resistance)}", above=True)
    _level_label(axes, label_x, support, f"แนวรับ {money(support)}", above=False)

    last_x, last_y = len(view) - 1, view[-1]["close"]
    span = x_right - last_x
    _path_arrow(axes, [(last_x, last_y),
                       (last_x + span * 0.42, box["low"]),
                       (last_x + span * 0.86, resistance)])


def _draw_channel(axes, brief: dict, view: list[dict], x_right: float) -> None:
    """สิ่งที่ลากทับของสไตล์ G — เส้นประคู่ขนาน + วงรีจุดแตะ + ป้าย + ลูกศรตัว J"""
    from matplotlib.patches import Ellipse

    money = brief_writer.money_for(brief)
    channel = brief["channel"]
    touches = brief["channel_touches"]
    origin = channel["start"]

    def line_at(x: float) -> float:
        return channel["slope"] * (x - origin) + channel["intercept"]

    xs = [origin, x_right]
    main = [line_at(x) for x in xs]
    parallel = [value + channel["offset"] for value in main]
    for line in (main, parallel):
        axes.plot(xs, line, color=COLORS["channel"], linewidth=2.0,
                  linestyle=(0, (7, 5)), zorder=5)

    radius_x = max(2.5, len(view) * 0.035)
    radius_y = brief["atr14"] * 1.5
    # วงที่ทับกันต้องยุบเป็นวงเดียว — จุดแตะขอบบนกับขอบล่างมาใกล้กันได้เมื่อช่องแคบ
    # แล้ววงสองวงซ้อนกันอ่านเหมือนวาดพลาด ไม่ใช่หลักฐานสองชิ้น
    drawn: list[tuple[float, float]] = []
    for point in sorted(touches["upper"] + touches["lower"], key=lambda p: p["index"]):
        spot = (point["index"], point["price"])
        if any(abs(spot[0] - x) < radius_x and abs(spot[1] - y) < radius_y / 2
               for x, y in drawn):
            continue
        drawn.append(spot)
        axes.add_patch(Ellipse(spot, radius_x * 2, radius_y, facecolor="none",
                               edgecolor=COLORS["touch"], linewidth=1.7, zorder=6))

    # เส้นนำแนวนอนสั้น ๆ จากแท่งสุดท้ายถึงขอบขวา — ป้ายราคาต้องมีอะไรให้เกาะ
    # (ขอบช่องเอียง ค่าที่ป้ายบอกคือค่า ณ แท่งล่าสุด ไม่ใช่ค่าที่ขอบขวาของภาพ)
    support, resistance = brief["support"], brief["resistance"]
    last_bar = len(view) - 1
    for value in (support, resistance):
        axes.plot([last_bar, x_right], [value, value], color=COLORS["level"],
                  linewidth=1.1, linestyle=(0, (2, 3)), alpha=0.75, zorder=5)
    label_x = x_right - (x_right - origin) * 0.015
    _level_label(axes, label_x, resistance, f"แนวต้าน {money(resistance)}", above=True)
    _level_label(axes, label_x, support, f"แนวรับ {money(support)}", above=False)

    last_x, last_y = last_bar, view[-1]["close"]
    span = x_right - last_x
    # ตัว J: ย่อสั้น ๆ ก่อนแล้วพุ่งยาวขึ้น — ตรงกับประโยค "รอจังหวะย่อตัวเข้าซื้อ" ในบท
    dip = max(support, last_y - brief["atr14"] * 1.2)
    _path_arrow(axes, [(last_x, last_y),
                       (last_x + span * 0.30, dip),
                       (last_x + span * 0.88, resistance)])


def render(brief: dict, rows: list[dict], output_path: Path) -> dict:
    """วาดการ์ดหนึ่งใบแล้วเซฟเป็น .webp ผ่านด่านขนาดไฟล์ — คืนสรุปสั้น"""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot
    from matplotlib.patches import Rectangle

    _thai_font()
    view = rows[-brief["display"]["bars"]:]
    figure = pyplot.figure(figsize=FIGURE_SIZE, dpi=DPI)
    try:
        _card(figure, Rectangle)
        axes = figure.add_axes((0.055, 0.135, 0.845, 0.640))
        _style_axes(axes)
        _draw_candles(axes, view, Rectangle)
        _draw_sma(axes, rows, len(view))

        x_right = len(view) - 1 + len(view) * RIGHT_PAD_FRACTION
        if brief["style"] == brief_story.STYLE_G:
            _draw_channel(axes, brief, view, x_right)
        else:
            _draw_range(axes, brief, view, x_right, Rectangle)

        lows = [row["low"] for row in view] + [brief["support"]]
        highs = [row["high"] for row in view] + [brief["resistance"]]
        pad = (max(highs) - min(lows)) * 0.09
        axes.set_xlim(-0.5, x_right)
        axes.set_ylim(min(lows) - pad, max(highs) + pad)
        positions, labels = month_tick_labels(view)
        axes.set_xticks(positions)
        axes.set_xticklabels([checked(label) for label in labels])

        _header(figure, brief)
        _footer(figure, brief)
        size = image_output.save_figure(figure, Path(output_path),
                                        facecolor=figure.get_facecolor())
    finally:
        pyplot.close(figure)
    return {"path": str(output_path), "bytes": size, "kb": image_output.kb(size),
            "style": brief["style"], "bars": len(view)}
