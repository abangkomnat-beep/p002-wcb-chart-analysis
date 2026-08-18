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

    F  เส้นแนวนอนทึบ 2 เส้น (แนวรับ/แนวต้าน) + กล่องกรอบล่าสุด + ทางเลือกแบบมีเงื่อนไข
    G  เส้นประคู่ขนาน 2 เส้น (ช่องแนวโน้ม) + จุดแตะสำคัญไม่เกิน 4 จุด + ทางเลือกแบบมีเงื่อนไข

**สิ่งที่จงใจไม่ลอก:** สีแบรนด์ โลโก้ และแถบติดต่อของ InterGold — ใช้โทนกลางของเรา
ส่วนกราฟข้างในวาดจากแท่งตามกรอบเวลาที่ระบุใน brief ไม่ใช่ภาพถ่ายจอ TradingView
⇒ แถบท้ายการ์ดเขียนกรอบเวลากำกับเสมอ เพื่อให้วันที่และช่วงข้อมูลตรวจสอบได้

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
from tools.chart_renderer import THAI_MONTHS  # noqa: E402

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
    "path_up": "#1e9e83",
    "path_down": "#d94b57",
}


def checked(text: str) -> str:
    """ทางบังคับของข้อความทุกชิ้นก่อนลงภาพ — ด่านความสอดคล้อง D-4.5"""
    findings = consistency_gate.check_labels([text])
    if findings:
        raise ValueError(f"ป้ายภาพไม่ผ่านด่านความสอดคล้อง: {findings[0]['message']}")
    return text


def _tick_labels(brief: dict, view: list[dict]) -> tuple[list[int], list[str]]:
    """ป้ายแกนเวลา — รายวันเดินทีละเดือน · intraday เดินทีละวัน

    ใช้ตัวเดิม (`month_tick_labels`) กับแท่งรายวันไม่ได้กับ intraday เพราะหน้าต่าง
    ทั้งหน้าต่างอยู่ในเดือนเดียว ⇒ จะได้ป้ายเดียวทั้งภาพ อ่านไม่ออกว่าตรงไหนคือวันไหน
    """
    if brief.get("timeframe") is None:
        return month_tick_labels(view)
    positions, labels, seen = [], [], None
    # เลือกตามระยะบนแกนจริง ไม่เลือกตามจำนวนวัน เพราะตลาดแต่ละชนิดมีจำนวนแท่ง
    # ต่อวันไม่เท่ากันและมีวันหยุด ทำให้ป้ายสองวันท้ายเคยเบียดกันแม้มีเพียง 7 ป้าย
    sampled = sorted({round(index * (len(view) - 1) / 5) for index in range(6)})
    for index in sampled:
        row = view[index]
        if row["date"] == seen:
            continue
        seen = row["date"]
        day, month = int(row["date"][8:10]), int(row["date"][5:7])
        positions.append(index)
        labels.append(f"{day} {THAI_MONTHS[month - 1]}")
    return positions, labels


def _card(figure, Rectangle) -> None:
    """พื้นภาพเต็มใบ ไม่มีกรอบตกแต่งรอบนอก"""
    figure.patch.set_facecolor(COLORS["panel"])


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


def _event_header(figure, brief: dict) -> None:
    """หัวภาพ G: เห็นเหตุการณ์และระดับยืนยันทั้งสองฝั่งได้ภายในไม่กี่วินาที"""
    money = brief_writer.money_for(brief)
    profile = wcb_source.profile_for(brief["asset"])
    timeframe = brief_writer.tf_words(brief)["front"]
    at = str(brief["current"].get("at") or "")
    clock = at[11:16] if len(at) >= 16 else ""

    figure.text(0.050, 0.885,
                checked(f"กรอบประเมินหลังประกาศ · {profile['symbol']} {timeframe}"),
                transform=figure.transFigure, ha="left", va="center",
                color="#111827", fontsize=20.5, zorder=10)
    detail = f"ข้อมูลถึง {thai_date(brief['current']['date'])}"
    if clock:
        detail += f" เวลา {clock} น."
    detail += f" · รอแท่ง {timeframe} ปิดยืนยัน"
    figure.text(0.050, 0.838, checked(detail), transform=figure.transFigure,
                ha="left", va="center", color="#64748B", fontsize=11.5, zorder=10)

    _trade_chip(figure, (0.520, 0.835, 0.126, 0.064),
                f"ปิด {money(brief['current']['close'])}",
                face="#0F172A", edge="#0F172A", color="#FFFFFF")
    _trade_chip(figure, (0.657, 0.835, 0.139, 0.064),
                f"ยืนยัน > {money(brief['resistance'])}",
                face="#EAFBF7", edge="#1F9D86", color="#127865")
    _trade_chip(figure, (0.807, 0.835, 0.142, 0.064),
                f"ยืนยัน < {money(brief['support'])}",
                face="#FFF1F2", edge="#E14957", color="#B42336")


def _event_banner(figure, brief: dict) -> None:
    event = brief.get("event") or {}
    at = str(event.get("at") or "")
    when = ""
    if len(at) >= 16:
        when = f"{thai_date(at[:10])} เวลา {at[11:16]} น. · "
    box = (0.520, 0.704, 0.370, 0.052)
    _figure_box(figure, box, face="#FFF7E8", edge="#E5A11A", linewidth=1.0,
                radius=0.010)
    x, y, width, height = box
    figure.text(x + width / 2, y + height / 2,
                checked(f"{when}รอการยืนยันทิศทาง"),
                transform=figure.transFigure, ha="center", va="center",
                color="#9A6700", fontsize=10.8, zorder=10)


def _event_card(figure, brief: dict, side: str) -> None:
    money = brief_writer.money_for(brief)
    timeframe = brief_writer.tf_words(brief)["front"]
    if side == "up":
        box, title, value, face, edge, color = (
            (0.744, 0.488, 0.146, 0.132), "แนวโน้มเชิงบวก", brief["resistance"],
            "#EAFBF7", "#1F9D86", "#127865")
        detail = f"ปิด {timeframe} เหนือระดับนี้"
    else:
        box, title, value, face, edge, color = (
            (0.744, 0.180, 0.146, 0.132), "แนวโน้มเชิงลบ", brief["support"],
            "#FFF1F2", "#E14957", "#B42336")
        detail = f"ปิด {timeframe} ต่ำกว่าระดับนี้"
    _figure_box(figure, box, face=face, edge=edge, linewidth=1.8, radius=0.012)
    x, y, width, height = box
    figure.text(x + width / 2, y + height - 0.030, checked(title),
                transform=figure.transFigure, ha="center", va="center",
                color=color, fontsize=11.8, zorder=10)
    figure.text(x + width / 2, y + height - 0.069, checked(money(value)),
                transform=figure.transFigure, ha="center", va="center",
                color="#111827", fontsize=15, fontweight="bold", zorder=10)
    figure.text(x + width / 2, y + 0.023, checked(detail),
                transform=figure.transFigure, ha="center", va="center",
                color="#475569", fontsize=9.2, zorder=10)


def _figure_box(figure, box: tuple[float, float, float, float], *, face: str,
                edge: str, linewidth: float = 1.2, radius: float = 0.012):
    """กล่องพิกัดระดับ figure — ใช้กับ header/banner/card เพื่อไม่เลื่อนตามแกนราคา"""
    from matplotlib.patches import FancyBboxPatch

    x, y, width, height = box
    patch = FancyBboxPatch((x, y), width, height,
                           boxstyle=f"round,pad=0.004,rounding_size={radius}",
                           transform=figure.transFigure, facecolor=face,
                           edgecolor=edge, linewidth=linewidth, zorder=9)
    figure.add_artist(patch)
    return patch


def _trade_chip(figure, box, text: str, *, face: str, edge: str, color: str) -> None:
    _figure_box(figure, box, face=face, edge=edge, linewidth=1.0)
    x, y, width, height = box
    figure.text(x + width / 2, y + height / 2, checked(text),
                transform=figure.transFigure, ha="center", va="center",
                color=color, fontsize=12.5, zorder=10)


def _trade_header(figure, brief: dict) -> None:
    """หัวภาพ F แบบ Trade Plan Map — วันที่ เวลา และ OPEN ต้องอ่านได้ใน 5 วินาที"""
    money = brief_writer.money_for(brief)
    profile = wcb_source.profile_for(brief["asset"])
    timeframe = brief_writer.tf_words(brief)["front"]
    at = str(brief["current"].get("at") or "")
    clock = at[11:16] if len(at) >= 16 else ""
    plan = brief["trade_plan"]

    figure.text(0.050, 0.885,
                checked(f"แผนเทรดตามกรอบ · {profile['symbol']} {timeframe}"),
                transform=figure.transFigure, ha="left", va="center",
                color="#111827", fontsize=20.5, zorder=10)
    detail = f"ข้อมูลถึง {thai_date(brief['current']['date'])}"
    if clock:
        detail += f" เวลา {clock} น."
    detail += f" · ยืนยันด้วยแท่ง {timeframe}"
    figure.text(0.050, 0.838, checked(detail), transform=figure.transFigure,
                ha="left", va="center", color="#64748B", fontsize=11.5, zorder=10)

    _trade_chip(figure, (0.520, 0.835, 0.126, 0.064),
                f"ปิด {money(brief['current']['close'])}",
                face="#0F172A", edge="#0F172A", color="#FFFFFF")
    _trade_chip(figure, (0.657, 0.835, 0.139, 0.064),
                f"SELL {money(plan['sell']['open'])}",
                face="#FFF1F2", edge="#E14957", color="#B42336")
    _trade_chip(figure, (0.807, 0.835, 0.142, 0.064),
                f"BUY {money(plan['buy']['open'])}",
                face="#EAFBF7", edge="#1F9D86", color="#127865")


def _risk_clock(brief: dict) -> str | None:
    for event in brief.get("calendar_events") or []:
        at = str(event.get("at") or "")
        if len(at) >= 16:
            return at[11:16]
    return None


def _news_banner(figure, brief: dict) -> None:
    clock = _risk_clock(brief)
    if not clock:
        return
    box = (0.528, 0.704, 0.362, 0.048)
    _figure_box(figure, box, face="#FFF7E8", edge="#E5A11A", linewidth=1.0,
                radius=0.010)
    x, y, width, height = box
    figure.text(x + width / 2, y + height / 2,
                checked(f"ข่าวสหรัฐฯ {clock} น. · ระวังราคาแกว่งแรง"),
                transform=figure.transFigure, ha="center", va="center",
                color="#9A6700", fontsize=11.5, zorder=10)


def _plan_card(figure, brief: dict, side: str) -> None:
    """การ์ด SELL/BUY เรียง OPEN → TP → SL ตายตัวตามบรีฟ"""
    money = brief_writer.money_for(brief)
    item = brief["trade_plan"][side]
    if side == "sell":
        box, title, face, edge, color = ((0.744, 0.497, 0.146, 0.153),
                                         "SELL", "#FFF1F2", "#E14957", "#B42336")
    else:
        box, title, face, edge, color = ((0.744, 0.132, 0.146, 0.145),
                                         "BUY", "#EAFBF7", "#1F9D86", "#127865")
    _figure_box(figure, box, face=face, edge=edge, linewidth=1.8, radius=0.012)
    x, y, width, height = box
    figure.text(x + width / 2, y + height - 0.027, checked(title),
                transform=figure.transFigure, ha="center", va="center",
                color=color, fontsize=15, zorder=10)
    for index, (label, key) in enumerate((("OPEN", "open"), ("TP", "tp"), ("SL", "sl"))):
        figure.text(x + 0.014, y + height - 0.066 - index * 0.035,
                    checked(f"{label} {money(item[key])}"),
                    transform=figure.transFigure, ha="left", va="center",
                    color="#111827", fontsize=11.2, zorder=10)


def _footer(figure, brief: dict) -> None:
    """แถบท้ายการ์ด — **ต้องบอกกรอบเวลาเสมอ**

    การ์ดของทุกกรอบเวลาหน้าตาเหมือนกันหมด ถ้าไม่เขียนกำกับ คนอ่านจะเดาเอง
    และเดาผิดได้ (ต้นแบบเป็นราย 1 ชั่วโมง) — เหตุผลเดียวกับบรรทัด `stamp_line` ในบท
    """
    profile = wcb_source.profile_for(brief["asset"])
    box = brief["range_box"]
    text = (f"{profile['symbol']} · {brief_writer.tf_words(brief)['bar']} · ช่วงที่แสดง "
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
    """สิ่งที่ลากทับของ F — กรอบจริง แผนสองฝั่ง และราคาปิดล่าสุด"""
    money = brief_writer.money_for(brief)
    box = brief["range_box"]
    plan = brief["trade_plan"]
    support, resistance = brief["support"], brief["resistance"]
    left = -0.5

    axes.plot([left, x_right], [resistance, resistance], color="#E14957",
              linewidth=2.0, zorder=5)
    axes.plot([left, x_right], [support, support], color="#1F9D86",
              linewidth=2.0, zorder=5)
    # กล่องต้องใช้ระดับเดียวกับป้ายและบท ห้ามใช้ขอบดิบคนละค่าจนภาพมีแนวต้านสองชุด
    axes.add_patch(Rectangle((box["start_index"] - 0.5, support),
                             len(view) - box["start_index"], resistance - support,
                             facecolor=COLORS["box"], edgecolor=COLORS["box"],
                             alpha=0.12, linewidth=2.0, zorder=2))
    axes.add_patch(Rectangle((box["start_index"] - 0.5, support),
                             len(view) - box["start_index"], resistance - support,
                             facecolor="none", edgecolor=COLORS["box"],
                             linewidth=2.0, zorder=5))
    last_x, last_y = len(view) - 1, view[-1]["close"]
    span = x_right - last_x
    axes.scatter([last_x], [last_y], s=42, facecolor="#ffffff",
                  edgecolor=COLORS["text"], linewidth=1.4, zorder=7)
    axes.text(last_x - max(1.5, len(view) * 0.012), last_y,
              checked(f"ตอนนี้ {money(last_y)}"), ha="right", va="center",
              fontsize=11.5, color="#FFFFFF", zorder=8,
              bbox={"boxstyle": "round,pad=0.45", "facecolor": "#0F172A",
                    "edgecolor": "#0F172A"})

    # เส้น TP/SL เป็นเส้นสั้นในพื้นที่แผนด้านขวา ไม่พาดทับประวัติราคา
    start = last_x + span * 0.04
    styles = {"open": "-", "tp": (0, (4, 3)), "sl": (0, (2, 3))}
    for side, color in (("sell", "#E14957"), ("buy", "#1F9D86")):
        for key in ("open", "tp", "sl"):
            value = plan[side][key]
            axes.plot([start, x_right], [value, value], color=color,
                      linewidth=1.5 if key == "open" else 1.1,
                      linestyle=styles[key], alpha=1.0 if key == "open" else 0.65,
                      zorder=6)


def _draw_channel(axes, brief: dict, view: list[dict], x_right: float) -> None:
    """สิ่งที่ลากทับของ G — ช่องที่พิสูจน์ได้ จุดแตะสำคัญ และเงื่อนไขสองทาง"""
    from matplotlib.patches import Ellipse

    money = brief_writer.money_for(brief)
    channel = brief["channel"]
    touches = brief["channel_touches"]
    origin = channel["start"]

    def line_at(x: float) -> float:
        return channel["slope"] * (x - origin) + channel["intercept"]

    last_bar = len(view) - 1
    # ช่องแนวโน้มคือหลักฐานจากแท่งที่เกิดขึ้นแล้ว จึงหยุดที่แท่งล่าสุด
    xs = [origin, last_bar]
    main = [line_at(x) for x in xs]
    parallel = [value + channel["offset"] for value in main]
    for line in (main, parallel):
        axes.plot(xs, line, color=COLORS["channel"], linewidth=2.0,
                  linestyle=(0, (7, 5)), zorder=5)
    axes.text(origin + max(2, len(view) * 0.025), min(main[0], parallel[0]),
              checked("กรอบแนวโน้มระยะสั้น"), color=COLORS["channel"],
              fontsize=9.5, va="top", zorder=7,
              bbox={"facecolor": "#ffffff", "edgecolor": "none", "alpha": 0.82})

    radius_x = max(2.5, len(view) * 0.035)
    radius_y = brief["atr14"] * 1.5
    # วงที่ทับกันต้องยุบเป็นวงเดียว — จุดแตะขอบบนกับขอบล่างมาใกล้กันได้เมื่อช่องแคบ
    # แล้ววงสองวงซ้อนกันอ่านเหมือนวาดพลาด ไม่ใช่หลักฐานสองชิ้น
    candidates: list[tuple[float, float]] = []
    for point in sorted(touches["upper"] + touches["lower"], key=lambda p: p["index"]):
        spot = (point["index"], point["price"])
        if any(abs(spot[0] - x) < radius_x and abs(spot[1] - y) < radius_y / 2
               for x, y in candidates):
            continue
        candidates.append(spot)
    if len(candidates) > 4:
        selected = sorted({0, round((len(candidates) - 1) / 3),
                           round((len(candidates) - 1) * 2 / 3), len(candidates) - 1})
        candidates = [candidates[index] for index in selected]
    for spot in candidates:
        axes.add_patch(Ellipse(spot, radius_x * 2, radius_y, facecolor="none",
                               edgecolor=COLORS["touch"], linewidth=1.7, zorder=6))

    # เส้นนำแนวนอนสั้น ๆ จากแท่งสุดท้ายถึงขอบขวา — ป้ายราคาต้องมีอะไรให้เกาะ
    # (ขอบช่องเอียง ค่าที่ป้ายบอกคือค่า ณ แท่งล่าสุด ไม่ใช่ค่าที่ขอบขวาของภาพ)
    support, resistance = brief["support"], brief["resistance"]
    for value in (support, resistance):
        axes.plot([last_bar, x_right], [value, value], color=COLORS["level"],
                  linewidth=1.1, linestyle=(0, (2, 3)), alpha=0.75, zorder=5)
    label_x = x_right - (x_right - origin) * 0.015
    _level_label(axes, label_x, resistance, f"แนวต้าน {money(resistance)}", above=True)
    _level_label(axes, label_x, support, f"แนวรับ {money(support)}", above=False)

    last_x, last_y = last_bar, view[-1]["close"]
    span = x_right - last_x
    axes.scatter([last_x], [last_y], s=42, facecolor="#ffffff",
                 edgecolor=COLORS["text"], linewidth=1.4, zorder=7)
    axes.text(last_x - max(1.5, len(view) * 0.012), last_y,
              checked(f"ตอนนี้ {money(last_y)}"), ha="right", va="center",
              fontsize=11.2, color="#FFFFFF", zorder=8,
              bbox={"boxstyle": "round,pad=0.42", "facecolor": "#0F172A",
                    "edgecolor": "#0F172A"})


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
        if brief["style"] == brief_story.STYLE_F:
            for side in brief["trade_plan"].values():
                if isinstance(side, dict):
                    lows.extend(value for value in side.values()
                                if isinstance(value, (int, float)))
                    highs.extend(value for value in side.values()
                                 if isinstance(value, (int, float)))
        pad = (max(highs) - min(lows)) * 0.09
        axes.set_xlim(-0.5, x_right)
        axes.set_ylim(min(lows) - pad, max(highs) + pad)
        positions, labels = _tick_labels(brief, view)
        axes.set_xticks(positions)
        axes.set_xticklabels([checked(label) for label in labels])

        if brief["style"] == brief_story.STYLE_F:
            _trade_header(figure, brief)
            _news_banner(figure, brief)
            _plan_card(figure, brief, "sell")
            _plan_card(figure, brief, "buy")
        else:
            _event_header(figure, brief)
            _event_banner(figure, brief)
            _event_card(figure, brief, "up")
            _event_card(figure, brief, "down")
        _footer(figure, brief)
        size = image_output.save_figure(figure, Path(output_path),
                                        facecolor=figure.get_facecolor())
    finally:
        pyplot.close(figure)
    return {"path": str(output_path), "bytes": size, "kb": image_output.kb(size),
            "style": brief["style"], "bars": len(view)}
