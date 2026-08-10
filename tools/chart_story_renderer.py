"""ตัววาดกราฟสไตล์ D — วาดจาก story artifact เท่านั้น ไม่คำนวณระดับเองแม้แต่เส้นเดียว

**สองภาพแยกต่อบท** (ผู้ใช้ยืนยัน 2026-08-07: D ไม่รวมภาพ — ที่รวมคือสไตล์ E):
1. `render_overview` — วัฏจักรรอบใหญ่ ~320 แท่ง: ribbon โหมดตลาด · กรอบแนวโน้ม ·
   แนวต้านแนวนอน · โซนรับ + legend (โทน TradingView light ตามตัวอย่างของหัวหน้า)
2. `render_zoom` — ระยะใกล้ ~120 แท่ง: ระดับตัดสินใจ จุดเข้าซื้อ และป้ายฉากทัศน์
   (ป้ายฉากทัศน์ต้องดูออกทันทีว่าเป็นสมมุติ — ไม่มีเส้นโยงจากแท่งสุดท้าย ตามคำสั่งผู้ใช้)

geometry ทุกชิ้นมาจาก `chart_story.build_story` — ถ้าภาพผิด ให้แก้ที่เครื่องคิด
ไม่ใช่มาแต่งที่ตัววาด
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import chart_story, consistency_gate, headline_format, image_output, wcb_source  # noqa: E402
from tools.chart_renderer import THAI_MONTHS  # noqa: E402

RIGHT_PAD_FRACTION = 0.14
ZOOM_RIGHT_PAD_FRACTION = 0.22   # เผื่อที่ให้ป้ายฉากทัศน์และป้ายจุดเข้าซื้อ
FIGURE_SIZE = (19.2, 10.8)       # 16:9 ต่อภาพ — สองภาพแยกตามคำสั่งผู้ใช้ 2026-08-07
DPI = 100

# เพดานการขยายแกนราคาเพื่อให้เห็นกรอบแนวโน้มเต็มเส้น (ผู้ใช้แจ้ง 2026-08-10:
# "เส้นกราฟที่ตีมันขาดไป") — วัดของจริงวันนั้น: แกนตั้งจากแท่ง+ระดับได้ 3,853–5,506
# แต่กรอบแนวโน้มกินถึง 3,510–5,554 ⇒ ขาดบน 47.86 ล่าง 343.50 เส้นเลยถูกตัดที่ขอบภาพ
#
# ⚠️ **ขยายไม่จำกัดไม่ได้** — ฟีดแบ็กหัวหน้าข้อ 6 (08-06) ตีกลับเรื่อง "แกนราคาจม
# จนแท่งถูกบีบ" มาแล้ว · กรอบแนวโน้มลาดลงเร็วกว่าราคาจริง ปลายขวาของขอบล่างจึงหลุด
# ต่ำกว่าแท่งที่ต่ำสุดได้หลายร้อยจุด = พื้นที่ว่างล้วนที่ไม่มีแท่งสักแท่ง
# ⇒ ขยายได้ถึงเพดานนี้ ส่วนที่ยังเกินให้ **ตัดความยาวเส้นในแนวนอน** แทนการยืดแกนต่อ
# (เส้นจบก่อนถึงขอบ = อ่านออกว่าจงใจ ต่างจากเส้นที่ถูกขอบภาพตัด)
CHANNEL_FIT_MAX_EXPANSION = 0.35

COLORS = {
    "bg": "#ffffff", "grid": "#edf0f4", "axis": "#787b86", "text": "#131722",
    "up": "#26a69a", "down": "#ef5350",
    "ribbon_up": "#1e9e83", "ribbon_down": "#f23645",
    "channel": "#f23645", "level": "#555b66", "zone": "#7e57c2",
    "key": "#e91e2c", "diag": "#9aa0a6",
    "scenario_up": "#1e9e83", "scenario_down": "#f23645",
}


def checked_label(text: str) -> str:
    """ทางบังคับของข้อความทุกชิ้นก่อนลงภาพ — ด่านความสอดคล้อง D-4.5

    ภาพกับบทต้องเป็นปี พ.ศ. ชุดเดียวกัน (เคสจริง: บทเป็น พ.ศ. แต่หัวกราฟ ค.ศ.
    — รายงานหัวหน้าไว้ในจดหมายรอบห้า) · fail-closed: ป้ายผิด = โยนทิ้งทั้งใบ
    ไม่ใช่วาดออกไปแล้วค่อยรู้ตอนขึ้นเว็บ · เพิ่มจุดวาดข้อความใหม่ต้องผ่านตัวนี้เสมอ
    """
    findings = consistency_gate.check_labels([text])
    if findings:
        raise ValueError(f"ป้ายภาพไม่ผ่านด่านความสอดคล้อง: {findings[0]['message']}")
    return text


def month_tick_labels(view: list[dict]) -> tuple[list[int], list[str]]:
    """ตำแหน่ง+ป้ายแกนเวลา — ปีที่รอยต่อมกราคมเป็น **พ.ศ.** เสมอ

    🐞 เดิมพิมพ์ `str(year)` ตรง ๆ = ค.ศ. โผล่บนภาพทุกใบที่กินข้ามปีใหม่
    (ภาพรวม 320 แท่ง ≈ 15 เดือน กินข้ามปีเสมอ) ขณะบทเป็น พ.ศ. ทั้งใบ —
    อาการ D-4.5 แท้ ๆ ที่ด่านป้าย (`checked_label`) มีไว้จับ
    """
    ticks, labels = [], []
    previous = None
    for index, row in enumerate(view):
        month = row["date"][:7]
        if month != previous:
            previous = month
            year, month_number = int(month[:4]), int(month[5:7])
            ticks.append(index)
            labels.append(str(headline_format.buddhist_year(year)) if month_number == 1
                          else THAI_MONTHS[month_number - 1])
    return ticks, [checked_label(label) for label in labels]


def thai_date(date_text: str) -> str:
    """'2026-08-06' → '6 ส.ค. 2569' — ใช้ทั้งบนภาพและในบททุกสไตล์ให้สะกดตรงกัน

    ตัวจริงอยู่ที่ `headline_format` แล้ว (รวมกับรูปแบบพาดหัว) — ตัวนี้เหลือไว้เป็นทางเข้า
    ของผู้เรียกเดิมทั้งหมด **ห้ามคำนวณวันที่ซ้ำที่นี่** ไม่งั้นวันบนภาพกับในบทเพี้ยนกันได้อีก

    🆕 **เป็น พ.ศ. ตั้งแต่ 2026-08-10** (ผู้ใช้ตัดสินคู่กับสเปกพาดหัวของหัวหน้า) —
    เปลี่ยนทั้งบทพร้อมกัน ไม่ใช่เฉพาะพาดหัว ไม่งั้นหน้าเดียวกันมีสองระบบปี
    """
    return headline_format.thai_date(date_text)


def _thai_font() -> str:
    from matplotlib import font_manager, rcParams

    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in ("Tahoma", "Leelawadee UI", "Segoe UI"):
        if name in available:
            rcParams["font.family"] = name
            return name
    return rcParams["font.family"]


def _style_axes(axes) -> None:
    axes.set_facecolor(COLORS["bg"])
    for spine in axes.spines.values():
        spine.set_color("#d1d4dc")
    axes.tick_params(colors=COLORS["axis"], labelsize=12)
    axes.grid(True, color=COLORS["grid"], linewidth=0.8)
    axes.yaxis.tick_right()
    axes.set_axisbelow(True)


def _draw_candles(axes, view: list[dict], Rectangle) -> None:
    width = 0.62
    for index, row in enumerate(view):
        rising = row["close"] >= row["open"]
        color = COLORS["up"] if rising else COLORS["down"]
        axes.plot([index, index], [row["low"], row["high"]],
                  color=color, linewidth=0.9, zorder=3)
        body_low = min(row["open"], row["close"])
        height = abs(row["close"] - row["open"]) or (row["high"] - row["low"]) * 0.02 or 1e-9
        axes.add_patch(Rectangle((index - width / 2, body_low), width, height,
                                 facecolor=color, edgecolor=color, linewidth=0.5, zorder=3))


def _draw_ribbon(axes, rows: list[dict], view_len: int) -> None:
    """SMA50 สีตามความชันของตัวเอง — เขียวช่วงยกตัว แดงช่วงหัวลง"""
    sma50_all = chart_story.sma([row["close"] for row in rows], 50)
    offset = len(rows) - view_len
    segment_x, segment_y, segment_up = [], [], None

    def flush():
        if len(segment_x) > 1:
            axes.plot(segment_x, segment_y,
                      color=COLORS["ribbon_up"] if segment_up else COLORS["ribbon_down"],
                      linewidth=5.5, alpha=0.78, zorder=4, solid_capstyle="round")

    for index in range(view_len):
        direction = chart_story.ribbon_direction(sma50_all, offset + index)
        value = sma50_all[offset + index]
        if direction is None or value is None:
            continue
        if segment_up is not None and direction != segment_up:
            segment_x.append(index)
            segment_y.append(value)
            flush()
            segment_x, segment_y = [], []
        segment_x.append(index)
        segment_y.append(value)
        segment_up = direction
    flush()


def _draw_zones(axes, story: dict, view: list[dict], x_right: float, Rectangle,
                *, label: bool = True, entry_style: bool = False,
                zones: list[dict] | None = None) -> None:
    """entry_style: แผงระยะใกล้เรียกโซนเป็น "จุดเข้าซื้อ (SMC POI)" ตามหัวข้อในบท
    zones: จำกัดชุดโซนที่วาด (แผงล่างวาดเฉพาะโซนใกล้ — ฟีดแบ็กหัวหน้าข้อ 6)"""
    money = money_for(story)
    atr = story["atr14"]
    n = len(view)
    for zone in (story["zones"] if zones is None else zones):
        axes.add_patch(Rectangle((-2, zone["low"]), x_right + 2, zone["high"] - zone["low"],
                                 facecolor=COLORS["zone"], alpha=0.16, edgecolor="none", zorder=1))
        axes.hlines(zone["mean"], -2, x_right, color=COLORS["zone"], alpha=0.55,
                    linewidth=1.0, linestyle=(0, (5, 3)), zorder=1)
        if not label:
            continue
        # ป้ายบอกช่วงขอบโซนเสมอ — ฟีดแบ็กหัวหน้าข้อ 1: เลขขอบโซนในบทต้องหาเจอบนภาพ
        zone_range = f"{money(zone['low'])}–{money(zone['high'])}"
        if entry_style:
            caption = (f"จุดเข้าซื้อ {zone['rank']} (SMC POI) · {zone_range} · "
                       f"อ้างอิง {zone['touches']} ครั้ง")
        else:
            caption = f"POI {zone['rank']} · โซนรับ {zone_range} · อ้างอิง {zone['touches']} ครั้ง"
        if zone["includes_week52_low"]:
            caption += " · รวมจุดต่ำสุด 52 สัปดาห์"
        label_top = zone["high"] + atr * 1.1
        label_x = 2
        for candidate in (2, int(n * 0.3), int(n * 0.55), int(n * 0.78)):
            span = view[candidate:candidate + max(1, int(n * 0.18))]
            if all(r["low"] > label_top or r["high"] < zone["high"] for r in span):
                label_x = candidate
                break
        axes.text(label_x, zone["high"] + atr * 0.15, checked_label(caption),
                  color=COLORS["scenario_up"] if entry_style else COLORS["zone"],
                  fontsize=12, va="bottom", zorder=6)


def _channel_geometry(story: dict, *, n: int, x_right: float,
                      view_offset: int = 0) -> dict | None:
    """พิกัดของกรอบแนวโน้มในหน้าต่างที่กำลังวาด — **จุดเดียวที่คำนวณเส้นนี้**

    เดิมสองแผงคำนวณเองคนละที่ ทำให้ตอนตั้งแกนราคายังไม่มีใครรู้ว่าเส้นจะกินถึงไหน
    (ต้นเหตุที่เส้นถูกขอบภาพตัด — ผู้ใช้แจ้ง 08-10) · แยกออกมาเพื่อให้ **ตั้งแกนก่อน
    แล้วค่อยวาด** ด้วยตัวเลขชุดเดียวกัน

    `view_offset` = จำนวนแท่งที่หน้าต่างนี้สั้นกว่าหน้าต่างภาพรวม (แผงภาพรวม = 0)
    """
    channel = story["channel"]
    if not channel:
        return None
    origin = channel["start"] - view_offset      # ดัชนีจุดตั้งต้นในหน้าต่างนี้
    if origin >= n:
        return None
    xs = [max(origin, -2.0), n - 1 + n * 0.02]
    line = lambda x: channel["slope"] * (x - origin) + channel["intercept"]  # noqa: E731
    main = [line(x) for x in xs]
    parallel = [value + channel["offset"] for value in main]
    mid_xs = [max(origin, -2.0), x_right]
    mid = [line(x) + channel["offset"] / 2 for x in mid_xs]
    return {"xs": xs, "main": main, "parallel": parallel,
            "mid_xs": mid_xs, "mid": mid, "band": 0.55 * story["atr14"]}


def _channel_extents(geometry: dict | None, *, with_mid: bool) -> list[float]:
    """ค่า y สุดขอบที่กรอบแนวโน้มกินจริง — ป้อนให้ `_fit_range` ตอนตั้งแกน"""
    if not geometry:
        return []
    band = geometry["band"]
    values = geometry["main"] + geometry["parallel"]
    edges = [v - band for v in values] + [v + band for v in values]
    return edges + (geometry["mid"] if with_mid else [])


def _fit_range(low: float, high: float, pad: float,
               extras: list[float]) -> tuple[float, float]:
    """ขยายกรอบราคาให้รวม `extras` — แต่ไม่เกิน `CHANNEL_FIT_MAX_EXPANSION`

    เพดานมีไว้กันอาการที่หัวหน้าตีกลับไว้แล้ว (ข้อ 6 · 08-06): ยืดแกนตามของที่อยู่
    ไกลราคาจนแท่งเทียนถูกบีบจนอ่านไม่ออก · ส่วนที่ยังเกินเพดานให้ตัดความยาวเส้น
    ในแนวนอนแทน (ดู `_segment_within`) ไม่ใช่ยืดแกนต่อ
    """
    bottom, top = low - pad, high + pad
    if not extras:
        return bottom, top
    room = (top - bottom) * CHANNEL_FIT_MAX_EXPANSION
    return (max(min([bottom, *extras]), bottom - room),
            min(max([top, *extras]), top + room))


def _segment_within(y0: float, y1: float, band: float,
                    bounds: tuple[float, float]) -> tuple[float, float] | None:
    """ช่วง t ∈ [0,1] ของเส้นตรงที่ **ทั้งแถบ** ยังอยู่ในกรอบราคา (None = ไม่โผล่เลย)

    ใช้ตัดความยาวเส้นแทนการปล่อยให้ขอบภาพตัด — เส้นที่จบเองกลางภาพอ่านออกว่าจงใจ
    ส่วนเส้นที่ถูกขอบตัดอ่านเหมือนภาพเสีย (ซึ่งคือสิ่งที่ผู้ใช้เห็นและแจ้งมา 08-10)
    """
    lower, upper = bounds[0] + band, bounds[1] - band
    if upper < lower:                     # กรอบแคบกว่าความหนาแถบ — วาดไม่ได้เลย
        return None
    delta = y1 - y0
    if abs(delta) < 1e-9:
        return (0.0, 1.0) if lower <= y0 <= upper else None
    edges = sorted(((lower - y0) / delta, (upper - y0) / delta))
    start, end = max(edges[0], 0.0), min(edges[1], 1.0)
    return (start, end) if end > start else None


def _draw_band_line(axes, xs: list[float], ys: list[float], band: float,
                    bounds: tuple[float, float]) -> None:
    """วาดเส้นกรอบแนวโน้มหนึ่งเส้นพร้อมแถบ โดยตัดส่วนที่หลุดกรอบราคาทิ้ง"""
    span = _segment_within(ys[0], ys[1], band, bounds)
    if span is None:
        return
    at = lambda values, t: values[0] + t * (values[1] - values[0])  # noqa: E731
    clipped_x = [at(xs, span[0]), at(xs, span[1])]
    clipped_y = [at(ys, span[0]), at(ys, span[1])]
    axes.fill_between(clipped_x, [v - band for v in clipped_y], [v + band for v in clipped_y],
                      color=COLORS["channel"], alpha=0.20, zorder=2)
    axes.plot(clipped_x, clipped_y, color=COLORS["channel"], alpha=0.35,
              linewidth=1.2, zorder=2)


def _draw_channel(axes, geometry: dict | None, bounds: tuple[float, float], *,
                  with_mid: bool) -> None:
    if not geometry:
        return
    for line in (geometry["main"], geometry["parallel"]):
        _draw_band_line(axes, geometry["xs"], line, geometry["band"], bounds)
    if not with_mid:
        return
    span = _segment_within(geometry["mid"][0], geometry["mid"][1], 0.0, bounds)
    if span is None:
        return
    at = lambda values, t: values[0] + t * (values[1] - values[0])  # noqa: E731
    axes.plot([at(geometry["mid_xs"], span[0]), at(geometry["mid_xs"], span[1])],
              [at(geometry["mid"], span[0]), at(geometry["mid"], span[1])],
              color=COLORS["diag"], linewidth=1.1, linestyle=(0, (6, 4)), zorder=2)


def _right_tags(axes, entries: list[dict], x_right: float, y_range: tuple[float, float]) -> None:
    """ป้ายราคาฝั่งขวา จัดไม่ให้ทับกัน — rank ต่ำกว่า = สำคัญกว่า = อยู่ตำแหน่งจริง"""
    minimum_gap = (y_range[1] - y_range[0]) * 0.032
    placed: list[dict] = []
    seen_texts: set[str] = set()
    for entry in sorted(entries, key=lambda item: item["rank"]):
        # ระดับเดียวกันอาจถูกส่งมาจากสองบทบาท (เช่น โซนรับที่เป็นเป้าฉากทัศน์ด้วย)
        # ป้ายซ้ำไม่ได้ให้ข้อมูลเพิ่ม — เก็บใบของบทบาทที่สำคัญกว่าใบเดียว
        if entry["text"] in seen_texts:
            continue
        seen_texts.add(entry["text"])
        target = entry["y"]
        for _ in range(50):
            conflict = next((p for p in placed if abs(p["label_y"] - target) < minimum_gap), None)
            if conflict is None:
                break
            target = (conflict["label_y"] + minimum_gap if target >= conflict["label_y"]
                      else conflict["label_y"] - minimum_gap)
        entry["label_y"] = target
        placed.append(entry)
    for entry in placed:
        axes.text(x_right, entry["label_y"], checked_label(entry["text"]), color="#ffffff", fontsize=11.5,
                  ha="right", va="center", zorder=7,
                  bbox=dict(boxstyle="round,pad=0.28", facecolor=entry["face"], edgecolor="none"))


def _month_ticks(axes, view: list[dict]) -> None:
    ticks, labels = month_tick_labels(view)
    axes.set_xticks(ticks[1:])
    axes.set_xticklabels(labels[1:])


def _header(axes, story: dict, subtitle: str) -> None:
    axes.text(0.01, 0.985, checked_label(f"{story['symbol']} · รายวัน (D1)"),
              transform=axes.transAxes, color=COLORS["text"], fontsize=17,
              fontweight="bold", va="top", zorder=8)
    axes.text(0.01, 0.952, checked_label(subtitle), transform=axes.transAxes,
              color=COLORS["axis"], fontsize=12.5, va="top", zorder=8)


def _footer(axes, text: str) -> None:
    axes.text(0.01, 0.015, checked_label(text), transform=axes.transAxes,
              color=COLORS["axis"], fontsize=10.5, va="bottom", zorder=8)


def price_text(value: float, decimals: int = 2) -> str:
    """รูปแบบราคาที่ภาพและบทความใช้ร่วมกัน — เปลี่ยนที่นี่ต้องเปลี่ยนด่านตรวจด้วย

    🐞 **เคยตรึงไว้ 2 ตำแหน่งตายตัวเพราะสไตล์ D/E เขียนกับทองอย่างเดียว** (พบ 2026-08-07
    ตอนสั่งผลิต EUR/USD ครั้งแรก) — ผลคือระดับราคาทั้งบทถูกปัดเหลือ `1.15` `1.17` `1.18`
    ทั้งที่คู่เงินเดินทีละ 0.00001 ⇒ ทั้งบทเป็นตัวเลขที่ใช้เทรดไม่ได้
    **เป็นบั๊กตัวเดียวกับที่เคยเกิดกับ `wcb_writers.price()` เมื่อ 08-05 และกับ E7
    ฝั่งปลายทาง** — ของแบบนี้กลับมาซ้ำทุกครั้งที่มีตัวเขียนใหม่เกิดในโลกของทอง

    ⇒ ห้ามเรียกตัวนี้ตรง ๆ ในตัวเขียน/ตัววาด ให้ผูกผ่าน `money_for(story)` เสมอ
    ค่าตั้งต้น 2 คงไว้เพื่อไม่ให้ผู้เรียกเก่านอกสายนี้พัง ไม่ใช่เพราะ 2 ถูกต้อง
    """
    return f"{value:,.{decimals}f}"


def decimals_for(story: dict) -> int:
    return wcb_source.profile_for(story["asset"])["decimals"]


def money_for(story: dict):
    """ตัวจัดรูปราคาประจำสินทรัพย์ของ story — ทะเบียนทศนิยมอยู่ที่ `wcb_source` ที่เดียว

    เหมือน `wcb_writers.price(value, evidence)` ของสาย A/B/C ทุกประการ: เพิ่ม
    สินทรัพย์ใหม่แล้วแก้ทะเบียนที่เดียว ไม่ต้องไล่แก้ทุกจุดที่พิมพ์ราคา
    """
    places = decimals_for(story)
    return lambda value: price_text(value, places)


def macd_for(story: dict):
    """MACD เป็น**สเกลราคา** ไม่ใช่ 0-100 จึงต้องใช้ทศนิยมของสินทรัพย์เหมือนราคา

    (เหตุผลเดียวกับที่ทีมเว็บต้องแก้ E7: MACD ของ EUR/USD ที่ถูกปัดเป็น `0.00`
    ค่าจริงคือ `0.00314`)
    """
    places = decimals_for(story)
    return lambda value: price_text(value, places)


def _draw_overview(axes, story: dict, rows: list[dict], Rectangle) -> dict:
    """แผงบน — วัฏจักรรอบใหญ่เต็มหน้าต่างแสดงผล"""
    money = money_for(story)
    view = rows[-story["display"]["bars"]:]
    n = len(view)

    x_right = n - 1 + n * RIGHT_PAD_FRACTION
    low = min(r["low"] for r in view)
    high = max(r["high"] for r in view)
    pad = (high - low) * 0.06
    geometry = _channel_geometry(story, n=n, x_right=x_right)
    bounds = _fit_range(low, high, pad, _channel_extents(geometry, with_mid=True))
    axes.set_xlim(-2, x_right)
    axes.set_ylim(*bounds)

    _draw_zones(axes, story, view, x_right, Rectangle)
    for level in story["resistance"]:
        axes.hlines(level["mean"], -2, n - 1 + n * 0.02, color=COLORS["level"],
                    alpha=0.75, linewidth=0.9, zorder=1)
    if not any(zone["includes_week52_low"] for zone in story["zones"]):
        axes.hlines(story["week52_low"], -2, x_right, color=COLORS["key"],
                    linewidth=1.4, zorder=2)
        axes.text(2, story["week52_low"] - story["atr14"] * 0.35, checked_label("ต่ำสุด 52 สัปดาห์"),
                  color=COLORS["key"], fontsize=12, va="top", zorder=6)
    _draw_channel(axes, geometry, bounds, with_mid=True)
    _draw_candles(axes, view, Rectangle)
    _draw_ribbon(axes, rows, n)

    # ป้ายราคาครบทุกเส้นที่บทพูดถึง — ฟีดแบ็กหัวหน้า 08-06 ข้อ 1: "คนอ่านต้องชี้ได้
    # ว่าเส้นนี้เอง" (เดิมแนวต้าน/SMA50/จุดสูงสุดมีเส้นแต่ไม่มีป้าย)
    tags = [{"y": story["current"]["close"], "text": money(story["current"]["close"]),
             "face": "#131722", "rank": 0}]
    if story["sma50_last"] is not None:
        ribbon_face = COLORS["ribbon_down"] if story["regime"]["down"] else COLORS["ribbon_up"]
        tags.append({"y": story["sma50_last"],
                     "text": f"SMA50 {money(story['sma50_last'])}",
                     "face": ribbon_face, "rank": 1})
    tags.append({"y": story["peak"]["high"],
                 "text": f"จุดสูงสุด {money(story['peak']['high'])}",
                 "face": "#555b66", "rank": 2})
    for level in story["resistance"]:
        tags.append({"y": level["mean"], "text": money(level["mean"]),
                     "face": COLORS["level"], "rank": 3})
    for zone in story["zones"]:
        tags.append({"y": zone["mean"], "text": money(zone["mean"]),
                     "face": COLORS["zone"], "rank": 2})
    if not any(zone["includes_week52_low"] for zone in story["zones"]):
        tags.append({"y": story["week52_low"], "text": money(story["week52_low"]),
                     "face": COLORS["key"], "rank": 1})
    _right_tags(axes, tags, x_right, bounds)
    _month_ticks(axes, view)
    _overview_legend(axes, story)

    mode = "ขาลง" if story["regime"]["down"] else "ขาขึ้น"
    _header(axes, story,
            f"ภาพรวมโครงสร้าง {n} แท่ง · ข้อมูลถึง {thai_date(story['current']['date'])} · "
            f"ปิด {money(story['current']['close'])} · โหมดเส้นค่าเฉลี่ย 50 วัน: {mode}")
    return {"bars": n,
            "elements": {"zones": len(story["zones"]),
                         "resistance": len(story["resistance"]),
                         "channel": bool(story["channel"])}}


def _overview_legend(axes, story: dict) -> None:
    """legend อธิบายทุกองค์ประกอบ — ฟีดแบ็กหัวหน้า: แถบชมพู/เส้นประ/สีเส้น MA ไม่มีคำอธิบาย"""
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    handles = [
        Line2D([], [], color=COLORS["ribbon_up"], linewidth=4,
               label="เส้นค่าเฉลี่ย 50 วัน ช่วงยกตัว"),
        Line2D([], [], color=COLORS["ribbon_down"], linewidth=4,
               label="เส้นค่าเฉลี่ย 50 วัน ช่วงหัวลง"),
    ]
    if story["channel"]:
        handles.append(Patch(facecolor=COLORS["channel"], alpha=0.25,
                             label="กรอบแนวโน้ม (ขอบบน–ล่าง)"))
        handles.append(Line2D([], [], color=COLORS["diag"], linewidth=1.2,
                              linestyle=(0, (6, 4)), label="กึ่งกลางกรอบแนวโน้ม"))
    if story["zones"]:
        handles.append(Patch(facecolor=COLORS["zone"], alpha=0.3, label="โซนรับ (Demand Zone)"))
    if story["resistance"]:
        handles.append(Line2D([], [], color=COLORS["level"], linewidth=1.2, label="แนวต้าน"))
    legend = axes.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, 0.905),
                         fontsize=10.5, framealpha=0.92, edgecolor="#d1d4dc")
    legend.set_zorder(9)


def _draw_zoom(axes, story: dict, rows: list[dict], Rectangle) -> dict:
    """แผงล่าง — ระยะใกล้ ระดับตัดสินใจ จุดเข้าซื้อ และป้ายฉากทัศน์"""
    money = money_for(story)
    zoom_bars = story["display"]["zoom_bars"]
    view = rows[-zoom_bars:]
    n = len(view)
    x_right = n - 1 + n * ZOOM_RIGHT_PAD_FRACTION

    # แผงล่างแสดงเฉพาะของใกล้ราคา — ฟีดแบ็กหัวหน้าข้อ 6: โซนไกล (POI หลายเดือน)
    # ลากแกนราคาจมจนแท่งถูกบีบ และป้าย "อ้างอิง 7 ครั้ง" ขัดกับตาที่ไม่เห็นการแตะเลย
    close = story["current"]["close"]
    near = lambda value: abs(value - close) <= 8 * story["atr14"]  # noqa: E731
    daily_zones = [zone for zone in story["zones"] if zone["daily_entry"]]

    # ช่วงราคา: แท่งในหน้าต่าง + ระดับฉากทัศน์/โซนใกล้ที่บทพูดถึง
    anchors = [r["low"] for r in view] + [r["high"] for r in view]
    for zone in daily_zones[:1]:
        anchors += [zone["low"], zone["high"]]
    for side in ("up", "down"):
        scenario = story["scenarios"][side]
        if scenario:
            anchors += [scenario["trigger"]] + [t for t in scenario["targets"] if near(t)]
            # ป้ายเงื่อนไขลอยห่างเส้น trigger ไป 0.9×ATR — ไม่นับเข้าไปด้วยแล้วป้าย
            # ฝั่งล่างจะไปนั่งคาบขอบภาพ (วัดจริง 08-10: ห่างขอบแค่ 1.06 หน่วย)
            anchors.append(scenario["trigger"]
                           + (story["atr14"] * 0.9 if side == "up" else -story["atr14"] * 0.9))
    low, high = min(anchors), max(anchors)
    pad = (high - low) * 0.06
    view_offset = story["display"]["bars"] - n
    geometry = _channel_geometry(story, n=n, x_right=x_right, view_offset=view_offset)
    bounds = _fit_range(low, high, pad, _channel_extents(geometry, with_mid=False))
    axes.set_xlim(-2, x_right)
    axes.set_ylim(*bounds)

    _draw_zones(axes, story, view, x_right, Rectangle, entry_style=True, zones=daily_zones)
    visible = [level for level in story["resistance"]
               if bounds[0] <= level["mean"] <= bounds[1]]
    for level in visible:
        axes.hlines(level["mean"], -2, x_right, color=COLORS["level"],
                    alpha=0.75, linewidth=0.9, zorder=1)

    # กรอบแนวโน้มเฉพาะส่วนที่อยู่ในหน้าต่างซูม (ไม่มีเส้นกึ่งกลาง — แผงนี้แน่นอยู่แล้ว)
    _draw_channel(axes, geometry, bounds, with_mid=False)

    _draw_candles(axes, view, Rectangle)
    _draw_ribbon(axes, rows, n)

    # ระดับฉากทัศน์ — ป้ายราคา + ป้ายเงื่อนไขเท่านั้น **ไม่มีเส้นโยงจากแท่งสุดท้าย**
    # (ผู้ใช้สั่งเอาเส้นประออก 2026-08-06: เส้นพัดจากแท่งล่าสุดทำให้ภาพดูเป็นคำทำนายทิศทาง)
    tags = [{"y": story["current"]["close"], "text": money(story["current"]["close"]),
             "face": "#131722", "rank": 0}]
    for side, color in (("up", COLORS["scenario_up"]), ("down", COLORS["scenario_down"])):
        scenario = story["scenarios"][side]
        if not scenario:
            continue
        points = [scenario["trigger"]] + [t for t in scenario["targets"] if near(t)]
        span = x_right - (n - 1)
        for target in points:
            tags.append({"y": target, "text": money(target), "face": color, "rank": 3})
        # ป้ายมีตัวเลขในตัวและวางชิดเส้น trigger — ฟีดแบ็กหัวหน้าข้อ 7: ป้ายเดิม
        # วางชิดเส้นอื่นจนคนอ่านเข้าใจผิดว่าเงื่อนไขคือระดับนั้น
        direction_word = "เหนือ" if side == "up" else "ต่ำกว่า"
        label = (("ฉากทัศน์ขึ้น" if side == "up" else "ฉากทัศน์ลง")
                 + f" · ปิดวัน (D1) {direction_word} {money(scenario['trigger'])}")
        label_y = scenario["trigger"] + (story["atr14"] * 0.9 if side == "up"
                                         else -story["atr14"] * 0.9)
        axes.text((n - 1) + span * 0.5, label_y, checked_label(label), color=color, fontsize=11.5,
                  ha="center", va="center", alpha=0.9, zorder=6)

    # ราคาจุดเข้าซื้อเป็นป้ายเขียว rank ต่ำกว่าป้ายโซน — ระดับเดียวกันป้ายเขียวชนะ
    for entry in story["entries"]:
        if bounds[0] <= entry["price"] <= bounds[1]:
            tags.append({"y": entry["price"], "text": money(entry["price"]),
                         "face": COLORS["scenario_up"], "rank": 1})
    for zone in daily_zones:
        if bounds[0] <= zone["mean"] <= bounds[1]:
            tags.append({"y": zone["mean"], "text": money(zone["mean"]),
                         "face": COLORS["zone"], "rank": 2})
    _right_tags(axes, tags, x_right, bounds)
    _month_ticks(axes, view)

    axes.text(0.01, 0.985, checked_label(
                  f"ระยะใกล้ {n} แท่ง · ระดับตัดสินใจ จุดเข้าซื้อ และฉากทัศน์ · "
                  f"ข้อมูลถึง {thai_date(story['current']['date'])}"),
              transform=axes.transAxes, color=COLORS["text"], fontsize=14.5,
              fontweight="bold", va="top", zorder=8)
    return {"bars": n,
            "elements": {"scenario_up": bool(story["scenarios"]["up"]),
                         "scenario_down": bool(story["scenarios"]["down"]),
                         "resistance_visible": len(visible)}}


def _single_figure(draw, story: dict, rows: list[dict], output_path: Path,
                   footer_text: str) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    font_used = _thai_font()
    figure, axes = plt.subplots(figsize=FIGURE_SIZE, dpi=DPI)
    figure.patch.set_facecolor(COLORS["bg"])
    _style_axes(axes)
    info = draw(axes, story, rows, Rectangle)
    _footer(axes, footer_text)
    figure.tight_layout(pad=1.4)
    try:
        size_bytes = image_output.save_figure(figure, output_path, facecolor=COLORS["bg"])
    finally:
        plt.close(figure)   # ตกด่านขนาดก็ต้องคืน figure ไม่งั้นรอบถัดไปกินหน่วยความจำสะสม
    return {"path": str(output_path), "font": font_used,
            "bytes": size_bytes, "kb": image_output.kb(size_bytes), **info}


def render_overview(story: dict, rows: list[dict], output_path: Path) -> dict:
    """ภาพที่ 1 — วัฏจักรรอบใหญ่ พร้อม legend และป้ายราคาครบทุกเส้น"""
    return _single_figure(
        _draw_overview, story, rows, output_path,
        f"ข้อมูล: WCB series API · {story['display']['bars']} แท่ง D1 · "
        "ทุกเส้นและโซนคำนวณจากข้อมูลจริง · สไตล์ D — อ่านโครงสร้างกราฟ (P002)")


def render_zoom(story: dict, rows: list[dict], output_path: Path) -> dict:
    """ภาพที่ 2 — ระยะใกล้ ระดับตัดสินใจ จุดเข้าซื้อ และฉากทัศน์"""
    return _single_figure(
        _draw_zoom, story, rows, output_path,
        "ป้าย \"ฉากทัศน์\" เป็นเงื่อนไขสมมุติจากระดับที่คำนวณได้ ไม่ใช่คำทำนายทิศทาง "
        "· ข้อมูล: WCB series API · สไตล์ D (P002)")
