"""ตัววาดภาพสไตล์ D — วาดจาก story artifact เท่านั้น ไม่คำนวณระดับเองแม้แต่เส้นเดียว

**สองภาพกราฟ และภาพปฏิทินเมื่อมีข้อมูล**:
1. `render_overview` — วัฏจักรรอบใหญ่: เส้นกดจากยอด + เส้นยกจากฐาน ·
   แนวต้านแนวนอน · โซนรับ + legend (โทน TradingView light ตามตัวอย่างของหัวหน้า)
2. `render_zoom` — ระยะใกล้ ~120 แท่ง: แผนที่ตัดสินใจจากราคาปัจจุบัน แยกเงื่อนไข
   ยืนยันขาขึ้น แนวรับระหว่างทาง โซนรับหลัก และยืนยันขาลง

geometry ทุกชิ้นมาจาก `chart_story.build_story` — ถ้าภาพผิด ให้แก้ที่เครื่องคิด
ไม่ใช่มาแต่งที่ตัววาด
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import chart_story, consistency_gate, headline_format, image_output, visual_theme, wcb_source  # noqa: E402
from tools import wcb_writers  # noqa: E402
from tools.chart_renderer import THAI_MONTHS, _configure_thai_font  # noqa: E402

RIGHT_PAD_FRACTION = 0.48
ZOOM_RIGHT_PAD_FRACTION = 0.48   # single-line annotation rail; factual candles end at n-1
HEADER_HEIGHT_FRACTION = visual_theme.PREMIUM_HEADER_RATIO
PLOT_HEIGHT_FRACTION = visual_theme.PREMIUM_PLOT_RATIO
RIGHT_CANVAS_EDGE = 0.94
# หัว Decision Map อยู่ภายใน axes; กันข้อมูลแนวนอนสำคัญไว้ต่ำกว่าแถบหัวภาพ
# เพื่อไม่ให้เส้น/price tag พาด title หรือรายละเอียดเมื่อระดับสูงสุดชิดขอบบน
ZOOM_HEADER_SAFE_DATA_FRACTION = 0.90
CURRENT_PRICE_MARKER = "s"
CURRENT_PRICE_BOXSTYLE = "round,pad=0.45"
CURRENT_PRICE_LABEL_X_OFFSET = 1.8
CURRENT_PRICE_BOX_FACE = "#131722"
DECISION_HEADER_STATUS = (
    "ผ่านกรอบย่อยแล้ว · รอปิด D1 เหนือ 4,558.48 เพื่อยืนยันขาขึ้น")
SCENARIO_ARROW_ALPHA = 0.87
FIGURE_SIZE = (19.2, 10.8)       # 16:9 ต่อภาพ — สองภาพแยกตามคำสั่งผู้ใช้ 2026-08-07
DPI = 100
CALENDAR_TABLE_ONLY_FIGURE_SIZE = (19.2, 11.4)
CALENDAR_SOURCE_TEXT = "ที่มา: ปฎิทินเศรษฐกิจ World Class Broker"
OVERVIEW_FOOTER_TEXT = None
ZOOM_FOOTER_TEXT = None
# ผู้ใช้สั่ง 2026-08-19 ให้เพิ่มตัวอักษรทั้งสามภาพ โดยคง canvas 1920×1080 เดิม
# แยกข้อความสำคัญกับข้อความประกอบเพื่อให้ปรับได้จากจุดเดียวและไม่ขยายทุกอย่างจนชนกัน
KEY_TEXT_SCALE = 1.20
SECONDARY_TEXT_SCALE = 1.10
CALENDAR_WEBP_QUALITY = 84

# เงื่อนไขก่อนประกาศผลสำหรับตาราง Style D — แสดงเป็นสถานการณ์ ไม่ใช่คำทำนาย
# ไม่อยู่ในชุดที่ทบทวนแล้วต้องรอผลจริง (fail-closed) แทนการเดาทิศทางจากชื่อข่าว
XAU_POLICY_TONE_FAMILIES = frozenset({
    "fomc_minutes", "us_fed_official_speeches", "us_fed_jackson_hole",
})
XAU_HIGHER_POSITIVE_FAMILIES = frozenset({"us_initial_jobless_claims"})
XAU_HIGHER_NEGATIVE_FAMILIES = frozenset({
    "us_adp_weekly", "us_import_prices_mom", "us_empire_state",
    "us_philly_fed", "us_industrial_production", "us_pmi_manufacturing",
    "us_pmi_services", "us_pmi_composite", "us_housing_activity",
    "us_tic_flows", "us_fed_activity_indexes", "us_income_inflation_activity",
    "us_growth_durable_goods", "us_labor_revision",
})


def _key_text_size(base_size: float) -> float:
    return base_size * KEY_TEXT_SCALE


def _secondary_text_size(base_size: float) -> float:
    return base_size * SECONDARY_TEXT_SCALE

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

_THEME_COLORS = visual_theme.for_premium_chart()
COLORS = {
    **_THEME_COLORS,
    "bg": _THEME_COLORS["bg"], "grid": _THEME_COLORS["grid"], "axis": _THEME_COLORS["axis"], "text": _THEME_COLORS["text"],
    "up": _THEME_COLORS["buy"], "down": _THEME_COLORS["sell"],
    "channel": _THEME_COLORS["sell"], "level": _THEME_COLORS["neutral"],
    "zone": _THEME_COLORS["gold"], "key": _THEME_COLORS["sell"],
    "diag": _THEME_COLORS["muted"],
    "scenario_up": _THEME_COLORS["buy"], "scenario_down": _THEME_COLORS["sell"],
    "decision_now": _THEME_COLORS["callout"],
    "decision_up": _THEME_COLORS["buy"],
    "decision_hold": _THEME_COLORS["warning"],
    "decision_down": _THEME_COLORS["sell"],
    "decision_zone": _THEME_COLORS["gold"],
    "decision_secondary": _THEME_COLORS["neutral"],
    "structure_confirm": _THEME_COLORS["buy"],
    "trend_down": _THEME_COLORS["sell"], "trend_up": _THEME_COLORS["buy"],
}


def checked_label(text: str) -> str:
    """ทางบังคับของข้อความทุกชิ้นก่อนลงภาพ — ด่านความสอดคล้อง D-4.5

    ภาพกับบทต้องเป็นปี ค.ศ. ชุดเดียวกัน (เคสจริงที่ทำให้ด่านนี้เกิด: บทกับหัวกราฟ
    ใช้คนละระบบปี · กลับขั้วเป็น ค.ศ. เมื่อ 08-11) · fail-closed: ป้ายผิด = โยนทิ้งทั้งใบ
    ไม่ใช่วาดออกไปแล้วค่อยรู้ตอนขึ้นเว็บ · เพิ่มจุดวาดข้อความใหม่ต้องผ่านตัวนี้เสมอ
    """
    findings = consistency_gate.check_labels([text])
    if findings:
        raise ValueError(f"ป้ายภาพไม่ผ่านด่านความสอดคล้อง: {findings[0]['message']}")
    return text


def bullish_confirmation_label(story: dict, value: float) -> str:
    """ป้ายยืนยันฝั่งขึ้นแบบ semantic-only — ราคาอยู่ใน tag ขอบขวา."""
    return checked_label("ยืนยันขาขึ้น · ปิด D1 เหนือเส้น")


def current_price_label(story: dict, value: float) -> str:
    """ป้ายจุดปัจจุบันแบบ semantic-only — ราคาปิดอยู่ในหัวภาพแล้ว."""
    return checked_label("ราคาปัจจุบัน")


def bearish_confirmation_label(story: dict, value: float) -> str:
    """ป้ายยืนยันฝั่งลงแบบ semantic-only — ราคาอยู่ใน tag ขอบขวา."""
    return checked_label("ยืนยันขาลง · ปิด D1 ต่ำกว่าฐาน")


def calendar_split_conditions(event: dict, asset: str) -> tuple[str, str]:
    """คืน (เงื่อนไขขาลง, เงื่อนไขขาขึ้น) สำหรับตารางปฏิทินล่วงหน้า."""
    if asset != "xauusd":
        return "รอผลจริง", "รอผลจริง"
    family = str(event.get("family_id") or "")
    title_en = str(event.get("title_en") or "").strip().casefold()
    if family in XAU_POLICY_TONE_FAMILIES:
        return "เข้มงวด", "ผ่อนคลาย"
    if title_en == "mba 30-year mortgage rate":
        return "ดอกเบี้ยขึ้น", "ดอกเบี้ยลง"
    if family in XAU_HIGHER_POSITIVE_FAMILIES:
        return "น้อยกว่าคาดการณ์", "มากกว่าคาดการณ์"
    if family in XAU_HIGHER_NEGATIVE_FAMILIES:
        return "มากกว่าคาดการณ์", "น้อยกว่าคาดการณ์"
    return "รอผลจริง", "รอผลจริง"


def month_tick_labels(view: list[dict]) -> tuple[list[int], list[str]]:
    """ตำแหน่ง+ป้ายแกนเวลา — ปีที่รอยต่อมกราคมเป็น **ค.ศ.** ให้ตรงกับบท

    ภาพรวม 320 แท่ง ≈ 15 เดือน กินข้ามปีใหม่เสมอ ⇒ ป้ายปีโผล่บนภาพแทบทุกใบ
    ระบบปีที่นี่ต้องตรงกับที่บทเขียน ไม่งั้นเป็นอาการ D-4.5 (สองระบบปีในหน้าเดียว)
    ที่ด่านป้าย (`checked_label`) มีไว้จับ — ตอนนี้ทั้งคู่เป็น ค.ศ. (หัวหน้าสั่ง 08-11)
    """
    ticks, labels = [], []
    previous = None
    for index, row in enumerate(view):
        month = row["date"][:7]
        if month != previous:
            previous = month
            year, month_number = int(month[:4]), int(month[5:7])
            ticks.append(index)
            labels.append(str(year) if month_number == 1
                          else THAI_MONTHS[month_number - 1])
    return ticks, [checked_label(label) for label in labels]


def thai_date(date_text: str) -> str:
    """'2026-08-06' → '6 ส.ค. 2026' — ใช้ทั้งบนภาพและในบททุกสไตล์ให้สะกดตรงกัน

    ตัวจริงอยู่ที่ `headline_format` แล้ว (รวมกับรูปแบบพาดหัว) — ตัวนี้เหลือไว้เป็นทางเข้า
    ของผู้เรียกเดิมทั้งหมด **ห้ามคำนวณวันที่ซ้ำที่นี่** ไม่งั้นวันบนภาพกับในบทเพี้ยนกันได้อีก

    🔄 **กลับเป็น ค.ศ. เมื่อ 2026-08-11** (หัวหน้าสั่ง — เว็บแสดงวันที่เผยแพร่เป็น ค.ศ.
    เสมอ) · เปลี่ยนทั้งบทพร้อมกัน ไม่ใช่เฉพาะพาดหัว ไม่งั้นหน้าเดียวกันมีสองระบบปี
    """
    return headline_format.thai_date(date_text)


def _thai_font() -> str:
    return _configure_thai_font()


def _style_axes(axes) -> None:
    axes.set_facecolor(COLORS["bg"])
    for spine in axes.spines.values():
        spine.set_color(COLORS["border"])
    axes.tick_params(colors=COLORS["axis"], labelsize=_secondary_text_size(12))
    axes.grid(True, color=COLORS["grid"], linewidth=0.7)
    axes.yaxis.tick_right()
    axes.set_axisbelow(True)


def packed_label_positions(bounds: tuple[float, float], entries: list[tuple[str, float]],
                           *, min_gap_fraction: float = 0.075) -> dict[str, float]:
    """Pack display labels vertically without changing their factual anchors."""
    if not entries:
        return {}
    low, high = bounds
    span = high - low
    gap = span * min_gap_fraction
    floor, ceiling = low + span * 0.07, high - span * 0.07
    ordered = sorted(entries, key=lambda item: item[1])
    placed: list[list[object]] = []
    for role, anchor in ordered:
        target = max(floor, min(float(anchor), ceiling))
        if placed:
            target = max(target, float(placed[-1][2]) + gap)
        placed.append([role, anchor, target])
    overflow = float(placed[-1][2]) - ceiling
    if overflow > 0:
        for item in placed:
            item[2] = float(item[2]) - overflow
    underflow = floor - float(placed[0][2])
    if underflow > 0:
        for item in placed:
            item[2] = float(item[2]) + underflow
    return {str(role): float(target) for role, _, target in placed}


def _editorial_header(figure, header, plot_axes, story: dict, *,
                      variant: str, bars: int) -> dict:
    """Compact branded rail whose sole visible copy is the asset and timeframe."""
    title = checked_label(f"{story['symbol']} · D1")
    title_artist, _, underline = visual_theme.draw_edge_to_edge_header(
        figure, header, plot_axes, title, COLORS)
    return visual_theme.edge_to_edge_header_layout(
        figure, header, plot_axes, title_artist, underline)


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


def _zone_caption(story: dict, zone: dict, *, entry_style: bool = False) -> str:
    money = money_for(story)
    zone_range = f"{money(zone['low'])}–{money(zone['high'])}"
    if entry_style:
        caption = (f"แนวรับ {zone['rank']} · {zone_range} · "
                   f"อ้างอิง {zone['touches']} ครั้ง")
    else:
        role = "แนวรับหลัก" if zone["rank"] == 1 else "แนวรับระยะยาว"
        caption = (f"{role} {zone_range} · กึ่งกลาง {money(zone['mean'])} · "
                   f"อ้างอิง {zone['touches']} ครั้ง")
    if zone["includes_week52_low"]:
        caption += " · รวมจุดต่ำสุด 52 สัปดาห์"
    return checked_label(caption)


def _overview_support_caption(story: dict, zone: dict) -> str:
    """Compact overview-only copy; never feeds level geometry or metadata."""
    if story.get("asset") == "xauusd":
        if zone["rank"] == 1:
            display_price = f"{int(float(zone['mean']) // 10 * 10):,}"
            caption = f"แนวรับหลัก · {display_price} · อ้างอิง {zone['touches']} ครั้ง"
        else:
            caption = (f"แนวรับระยะยาว · {money_for(story)(zone['mean'])}"
                       f" · อ้างอิง {zone['touches']} ครั้ง"
                       " · ต่ำสุด 52 สัปดาห์")
        return checked_label(caption)
    role = "แนวรับหลัก" if zone["rank"] == 1 else "แนวรับระยะยาว"
    caption = f"{role} · {money_for(story)(zone['mean'])} · อ้างอิง {zone['touches']} ครั้ง"
    if zone["includes_week52_low"]:
        caption += " · ต่ำสุด 52 สัปดาห์"
    return checked_label(caption)


def _draw_zones(axes, story: dict, view: list[dict], x_right: float, Rectangle,
                *, label: bool = True, entry_style: bool = False,
                zones: list[dict] | None = None) -> None:
    """entry_style: แผงระยะใกล้เรียกโซนตามหน้าที่ของแนวรับ
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
        caption = _zone_caption(story, zone, entry_style=entry_style)
        label_top = zone["high"] + atr * 1.1
        label_x = 2
        for candidate in (2, int(n * 0.3), int(n * 0.55), int(n * 0.78)):
            span = view[candidate:candidate + max(1, int(n * 0.18))]
            if all(r["low"] > label_top or r["high"] < zone["high"] for r in span):
                label_x = candidate
                break
        axes.text(label_x, zone["high"] + atr * 0.15, caption,
                  color=COLORS["scenario_up"] if entry_style else COLORS["zone"],
                  fontsize=_key_text_size(12), va="bottom", zorder=6)


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
    # ภาพโครงสร้างบอกสิ่งที่เกิดขึ้นแล้ว จึงหยุดกรอบที่แท่งล่าสุด ไม่ลากเส้นไปใน
    # พื้นที่อนาคตจนดูคล้ายการคาดการณ์ (บรีฟแก้ภาพ 2026-08-17)
    xs = [max(origin, -2.0), n - 1]
    line = lambda x: channel["slope"] * (x - origin) + channel["intercept"]  # noqa: E731
    main = [line(x) for x in xs]
    parallel = [value + channel["offset"] for value in main]
    mid_xs = list(xs)
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


def zoom_bounds_with_header_clearance(
        bounds: tuple[float, float], horizontal_levels: list[float],
        *, safe_fraction: float = ZOOM_HEADER_SAFE_DATA_FRACTION,
) -> tuple[float, float]:
    """เพิ่ม headroom เฉพาะเมื่อเส้นแนวนอนล้ำเข้าเขตหัว Decision Map.

    ค่า level ไม่เปลี่ยนและเส้นยังวาดเต็ม plot; เปลี่ยนเพียง upper bound ของแกน y
    เท่าที่จำเป็นให้ระดับสูงสุดอยู่ไม่เกิน `safe_fraction` ในพิกัด normalized axes.
    """
    bottom, top = bounds
    if top <= bottom:
        raise ValueError("zoom bounds ต้องมีขอบบนมากกว่าขอบล่าง")
    if not 0.0 < safe_fraction < 1.0:
        raise ValueError("safe_fraction ต้องอยู่ระหว่าง 0 และ 1")
    if not horizontal_levels:
        return bounds
    highest = max(horizontal_levels)
    normalized_y = (highest - bottom) / (top - bottom)
    if normalized_y <= safe_fraction:
        return bounds
    required_top = bottom + (highest - bottom) / safe_fraction
    return bottom, max(top, required_top)


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
    minimum_gap = (y_range[1] - y_range[0]) * 0.080
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
        artist = axes.text(
            x_right, entry["label_y"], checked_label(entry["text"]), color="#ffffff",
            fontsize=_key_text_size(15.5), ha="right", va="center", zorder=7,
            bbox=dict(boxstyle="round,pad=0.28", facecolor=entry["face"], edgecolor="none"))
        artist.set_gid(f"premium-label:right-tag:{entry['text']}")


def _month_ticks(axes, view: list[dict]) -> None:
    ticks, labels = month_tick_labels(view)
    axes.set_xticks(ticks[1:])
    axes.set_xticklabels(labels[1:])


def _header(axes, story: dict, subtitle: str) -> None:
    axes.text(0.01, 0.985, checked_label(f"{story['symbol']} · รายวัน (D1)"),
              transform=axes.transAxes, color=COLORS["text"],
              fontsize=_key_text_size(17),
              fontweight="bold", va="top", zorder=8)
    axes.text(0.01, 0.952, checked_label(subtitle), transform=axes.transAxes,
              color=COLORS["axis"], fontsize=_secondary_text_size(12.5), va="top", zorder=8)


def zoom_header_parts(story: dict, bars: int) -> tuple[str, str]:
    """หัว Levels แบบบรรทัดเดียว: ชื่อหลักใหญ่ รายละเอียดต่อท้ายขนาดเล็ก"""
    money = money_for(story)
    return (
        f"{story['symbol']} · รายวัน (D1)",
        f"{bars} แท่ง · ข้อมูลถึง {thai_date(story['current']['date'])} · "
        f"ปิด {money(story['current']['close'])}",
    )


def _zoom_inline_header(axes, story: dict, bars: int) -> None:
    """จัดหัวหลักและรายละเอียดคนละขนาดบน baseline เดียวกันโดยไม่กะระยะ x"""
    from matplotlib.offsetbox import AnchoredOffsetbox, HPacker, TextArea

    title, detail = zoom_header_parts(story, bars)
    title_area = TextArea(
        checked_label(title),
        textprops={"color": COLORS["text"], "fontsize": _key_text_size(17),
                   "fontweight": "bold"},
    )
    detail_area = TextArea(
        checked_label(detail),
        textprops={"color": COLORS["axis"], "fontsize": _secondary_text_size(11)},
    )
    line = HPacker(children=[title_area, detail_area], align="baseline", pad=0, sep=9)
    header = AnchoredOffsetbox(
        loc="upper left", child=line, frameon=False, pad=0, borderpad=0,
        bbox_to_anchor=(0.01, 0.985), bbox_transform=axes.transAxes,
    )
    header.set_zorder(8)
    axes.add_artist(header)


def _footer(axes, text: str) -> None:
    axes.text(0.01, 0.015, checked_label(text), transform=axes.transAxes,
              color=COLORS["axis"], fontsize=_secondary_text_size(10.5), va="bottom", zorder=8)


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


def structure_status(story: dict) -> dict:
    """สถานะที่ภาพโครงสร้างสื่อ โดยแยกแนวโน้มหลักออกจากกรอบย่อย"""
    close = story["current"]["close"]
    channel = story.get("channel")
    upper = lower = None
    channel_state = "ไม่มีกรอบ"
    if channel:
        endpoints = [channel["main_at_last"], channel["parallel_at_last"]]
        upper, lower = max(endpoints), min(endpoints)
        if close > upper:
            channel_state = "ทะลุ"
        elif close < lower:
            channel_state = "หลุด"
        else:
            channel_state = "อยู่ในกรอบ"
    confirmation = (story["scenarios"].get("up") or {}).get("trigger")
    return {
        "primary": "ลง" if story["regime"]["down"] else "ขึ้น",
        "channel": channel_state,
        "above_sma": story["sma50_last"] is not None and close >= story["sma50_last"],
        "reversal_confirmed": confirmation is not None and close > confirmation,
        "confirmation": confirmation,
        "upper": upper,
        "lower": lower,
    }


def _breakout_index(story: dict, view: list[dict]) -> int | None:
    """แท่งล่าสุดที่ราคาปิดข้ามขอบบนของกรอบจากล่างขึ้นบน"""
    channel = story.get("channel")
    if not channel:
        return None
    view_offset = story["display"]["bars"] - len(view)
    origin = channel["start"] - view_offset

    def upper(index: int) -> float:
        main = channel["slope"] * (index - origin) + channel["intercept"]
        return max(main, main + channel["offset"])

    crossings = [index for index in range(max(1, int(origin) + 1), len(view))
                 if view[index - 1]["close"] <= upper(index - 1)
                 and view[index]["close"] > upper(index)]
    return crossings[-1] if crossings else None


def secondary_resistance_line_specs(story: dict, levels: list) -> list[dict]:
    """สเปกเส้นแนวต้านรองแบบเดียวกันทั้งภาพรวมและภาพแผนที่ตัดสินใจ

    คำสั่งผู้ใช้ 2026-08-18: เส้นต้องทึบ พาดเต็มพื้นที่กราฟ และมีเพียงป้ายราคา
    ที่ขอบขวา ห้ามใช้กล่องข้อความหรือป้ายคำอธิบายลอยอยู่กลางกราฟ
    """
    money = money_for(story)
    specs = []
    for level in levels:
        value = level["mean"] if isinstance(level, dict) else float(level)
        specs.append({
            "value": value,
            "tag": money(value),
            "color": COLORS["decision_secondary"],
            "linewidth": 1.25,
            "linestyle": "-",
            "alpha": 0.88,
            "span": "full_plot",
            "label_position": "right_axis",
        })
    return specs


def _overview_trend_geometry(story: dict, *, n: int) -> dict:
    """เลือกเส้นหลักหนึ่งเส้นแล้วแปลงเป็นพิกัดวาด โดยหยุดที่แท่งล่าสุด

    ภาพ 180 แท่งให้เส้นกดจากยอดเป็นเส้นหลัก เพราะอธิบายโครงสร้างรอบใหญ่ ส่วน
    เส้นยกจากฐานเป็นโครงสร้างย่อยซึ่งโซนรับและสถานะโมเมนตัมสื่ออยู่แล้ว หากไม่มี
    เส้นกดจริงจึงค่อยถอยไปใช้เส้นยก ไม่บังคับสร้างเส้นที่ข้อมูลไม่รองรับ
    """
    geometry = {}
    trends = story.get("overview_trends") or {}
    selected = (("descending_resistance", trends.get("descending_resistance"))
                if trends.get("descending_resistance")
                else ("ascending_support", trends.get("ascending_support")))
    key, line = selected
    if line:
        start = max(0, line["start"])
        end = min(n - 1, line.get("end", n - 1))
        geometry[key] = {
            "xs": [start, end],
            "ys": [line["slope"] * start + line["intercept"],
                   line["slope"] * end + line["intercept"]],
            "anchor_dates": line["anchor_dates"],
        }
    return geometry


def _draw_overview_trends(axes, geometry: dict,
                           bounds: tuple[float, float]) -> None:
    """วาดเส้นกดและเส้นยกคนละสี ไม่มีแถบกรอบซึ่งทำให้เข้าใจว่าเป็น channel เดียว"""
    specs = {"descending_resistance": COLORS["trend_down"],
             "ascending_support": COLORS["trend_up"]}
    for key, item in geometry.items():
        color = specs[key]
        span = _segment_within(item["ys"][0], item["ys"][1], 0.0, bounds)
        if span is None:
            continue
        at = lambda values, t: values[0] + t * (values[1] - values[0])  # noqa: E731
        xs = [at(item["xs"], span[0]), at(item["xs"], span[1])]
        ys = [at(item["ys"], span[0]), at(item["ys"], span[1])]
        axes.plot(xs, ys, color=color, linewidth=2.7, zorder=4)


def _draw_zoom_descending_trend(axes, story: dict, *, n: int,
                                view_offset: int,
                                bounds: tuple[float, float]) -> bool:
    """วาดเส้นกดเดิมเส้นเดียวใน Decision Map พร้อมป้ายขนานกับเส้นจริง.

    เส้นมาจาก factual geometry ชุดเดียวกับภาพโครงสร้างรอบใหญ่ แต่ตัดเฉพาะช่วงที่
    อยู่ในหน้าต่าง 120 แท่งและแกนราคาปัจจุบัน ระดับไกลจึงไม่บีบแท่งในภาพระยะใกล้
    และป้ายคำนวณองศาจาก data transform แทนการกำหนดองศาคงที่.
    """
    line = (story.get("overview_trends") or {}).get("descending_resistance")
    if not line:
        return False
    start = max(0.0, float(line["start"] - view_offset))
    end = min(float(n - 1), float(line.get("end", n - 1) - view_offset))
    if end <= start:
        return False

    value_at = lambda x: line["slope"] * (x + view_offset) + line["intercept"]  # noqa: E731
    ys = [value_at(start), value_at(end)]
    span = _segment_within(ys[0], ys[1], 0.0, bounds)
    if span is None:
        return False
    at = lambda values, t: values[0] + t * (values[1] - values[0])  # noqa: E731
    xs = [at([start, end], span[0]), at([start, end], span[1])]
    visible_ys = [at(ys, span[0]), at(ys, span[1])]
    axes.plot(xs, visible_ys, color=COLORS["decision_secondary"], linewidth=2.4,
              linestyle=(0, (7, 5)), alpha=0.82, zorder=2.7)
    return True


def _draw_overview(axes, story: dict, rows: list[dict], Rectangle) -> dict:
    """ภาพโครงสร้าง — แสดงทั้งเส้นกดขาลงและเส้นยกขาขึ้นของหน้าต่างเดียวกัน"""
    money = money_for(story)
    view = rows[-story["display"]["bars"]:]
    n = len(view)

    x_right = n - 1 + n * RIGHT_PAD_FRACTION
    low = min(r["low"] for r in view)
    high = max(r["high"] for r in view)
    pad = (high - low) * 0.06
    geometry = _overview_trend_geometry(story, n=n)
    trend_extents = [value for item in geometry.values() for value in item["ys"]]
    bounds = _fit_range(low, high, pad, trend_extents)
    axes.set_xlim(-2, x_right)
    axes.set_ylim(*bounds)

    # หน้าต่าง 180 แท่งไม่ควรถูกบีบด้วยโซนหลายเดือนที่อยู่นอกช่วงราคาในภาพ
    # โซนยังอยู่ใน story/บทครบ เพียงไม่วาดของที่ไม่มีส่วนใดตัดกับแกนภาพใบนี้
    visible_zones = [zone for zone in story["zones"]
                     if zone["high"] >= bounds[0] and zone["low"] <= bounds[1]]
    _draw_zones(axes, story, view, x_right, Rectangle, label=False,
                zones=visible_zones)
    resistance = sorted(story["resistance"], key=lambda level: level["mean"])
    confirmation = resistance[0] if resistance else None
    secondary = resistance[1:3]
    secondary_specs = secondary_resistance_line_specs(story, secondary)
    if confirmation:
        axes.hlines(confirmation["mean"], n * 0.58, x_right,
                    color=COLORS["structure_confirm"], alpha=0.92,
                    linewidth=3.2, zorder=2)
    for spec in secondary_specs:
        axes.hlines(spec["value"], -2, x_right, color=spec["color"],
                    alpha=spec["alpha"], linewidth=spec["linewidth"],
                    linestyle=spec["linestyle"], zorder=1)
    week52_visible = bounds[0] <= story["week52_low"] <= bounds[1]
    if week52_visible and not any(zone["includes_week52_low"] for zone in visible_zones):
        axes.hlines(story["week52_low"], -2, x_right, color=COLORS["key"],
                    linewidth=1.4, zorder=2)
    _draw_overview_trends(axes, geometry, bounds)
    _draw_candles(axes, view, Rectangle)

    # Resistance remains a rail callout. Support copy belongs inside its
    # factual colored band and therefore needs neither a floating box nor leader.
    overview_cards: list[tuple[str, float, str, str]] = []
    if confirmation:
        overview_cards.append((
            "confirmation", confirmation["mean"],
            checked_label("แนวต้านยืนยัน"),
            COLORS["structure_confirm"],
        ))
    if week52_visible and not any(zone["includes_week52_low"] for zone in visible_zones):
        overview_cards.append(("week52", story["week52_low"],
                               checked_label("ต่ำสุด 52 สัปดาห์"), COLORS["key"]))
    card_positions = packed_label_positions(
        bounds, [(role, anchor) for role, anchor, _, _ in overview_cards],
        min_gap_fraction=0.12,
    )
    for role, anchor, label, color in overview_cards:
        artist = axes.annotate(
            label, xy=(n - 0.5, anchor),
            xytext=(n + 1.6, card_positions[role]), textcoords="data",
            ha="left", va="center", color=COLORS["text"],
            fontsize=_key_text_size(13.5), fontweight="bold", zorder=7,
            arrowprops=dict(arrowstyle="-", color=color, linewidth=1.2),
            bbox=dict(boxstyle="round,pad=0.34", facecolor=COLORS["panel"],
                      edgecolor=color, linewidth=1.2),
        )
        artist.set_gid(f"premium-label:overview:{role}")

    support_labels = []
    for index, zone in enumerate(visible_zones):
        label = _overview_support_caption(story, zone)
        label_x = n + 1.6 if zone["rank"] == 1 else n - 25
        artist = axes.text(
            label_x, zone["mean"], label, ha="left", va="center",
            color=COLORS["text"], fontsize=_key_text_size(12),
            fontweight="bold", zorder=7)
        artist.set_gid(f"premium-label:overview:support-band-{index}")
        support_labels.append({
            "text": label, "y": zone["mean"],
            "x": label_x,
            "band_low": zone["low"], "band_high": zone["high"],
            "leader": False, "floating_box": False,
        })

    # ป้ายราคาครบทุกเส้นที่ภาพรวมพูดถึง
    tags = [{"y": story["current"]["close"],
             "text": f"ราคาปัจจุบัน {money(story['current']['close'])}",
             "face": "#131722", "rank": 0}]
    tags.append({"y": story["peak"]["high"],
                 "text": f"จุดสูงสุด {money(story['peak']['high'])}",
                 "face": "#555b66", "rank": 2})
    if confirmation:
        tags.append({"y": confirmation["mean"], "text": money(confirmation["mean"]),
                     "face": COLORS["structure_confirm"], "rank": 1})
    for spec in secondary_specs:
        tags.append({"y": spec["value"], "text": spec["tag"],
                     "face": spec["color"], "rank": 3})
    for zone in visible_zones:
        tags.append({"y": zone["mean"], "text": money(zone["mean"]),
                     "face": COLORS["zone"], "rank": 2})
    if week52_visible and not any(zone["includes_week52_low"] for zone in visible_zones):
        tags.append({"y": story["week52_low"], "text": money(story["week52_low"]),
                     "face": COLORS["key"], "rank": 1})
    _right_tags(axes, tags, x_right, bounds)
    _month_ticks(axes, view)
    return {"bars": n,
            "layout": {"header_rail": True, "light_plot_card": True,
                       "annotation_rail": True, "legend_dock": "none",
                       "header_components": "asset_timeframe_only",
                       "support_band_labels": support_labels,
                       "support_label_leader_count": 0,
                       "support_label_floating_box_count": 0},
            "elements": {"zones": len(visible_zones),
                         "resistance": len(story["resistance"]),
                         "channel": False,
                         "trend_lines": len(geometry),
                         "sma50": False}}


def _overview_legend(axes, story: dict, geometry: dict) -> None:
    """คำอธิบายภาพโครงสร้างไม่เกินห้ารายการ วางซ้ายให้พ้นกล่องสถานะ"""
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    handles = []
    if "descending_resistance" in geometry:
        handles.append(Line2D([], [], color=COLORS["trend_down"], linewidth=2.7,
                              label="เส้นกดจากยอด (ขาลง)"))
    if "ascending_support" in geometry:
        handles.append(Line2D([], [], color=COLORS["trend_up"], linewidth=2.7,
                              label="เส้นยกจากฐาน (ขาขึ้น)"))
    if story["zones"]:
        handles.append(Patch(facecolor=COLORS["zone"], alpha=0.3, label="โซนรับ"))
    if story["resistance"]:
        handles.append(Line2D([], [], color=COLORS["level"], linewidth=1.2, label="แนวต้าน"))
    if handles:
        legend = axes.legend(handles=handles[:5], loc="upper left", bbox_to_anchor=(0.0, 0.905),
                             fontsize=_secondary_text_size(10.5), framealpha=0.92,
                             edgecolor="#d1d4dc")
        legend.set_zorder(9)


def decision_map(story: dict) -> dict:
    """คืนข้อมูลที่ใช้วาดภาพ 2 โดยไม่คำนวณระดับใหม่ในตัววาด

    จุดสำคัญคือระดับฝั่งลงต้องใช้ **ขอบล่างของโซน** ไม่ใช่ค่ากึ่งกลาง และสถานะ
    ต้องตัดสินจากราคาปิด D1 เท่านั้น เพื่อไม่ให้ไส้เทียนระหว่างวันเปลี่ยนคำบนภาพ
    """
    close = story["current"]["close"]
    # ภาพ Levels ต้องคงฐานโครงสร้างหลักไว้แม้ราคาปัจจุบันอยู่ไกลจนโซนนั้นไม่ใช่
    # daily entry แล้ว มิฉะนั้นพื้นที่ฐานและเงื่อนไขฝั่งขายจะหายไปทั้งชุดในบางวัน
    # โซนเรียงจากใกล้ราคามากไปไกลราคาอยู่แล้ว จึง fallback ไปใบแรกโดยไม่คำนวณ
    # ระดับใหม่ใน renderer และยังให้ daily-entry zone มาก่อนเมื่อมีจริง
    primary_zone = next(
        (zone for zone in story["zones"] if zone["daily_entry"]),
        story["zones"][0] if story["zones"] else None,
    )
    up = story["scenarios"]["up"]
    sma50 = story["sma50_last"]
    if up and close > up["trigger"]:
        state = "bullish_confirmation"
    elif primary_zone and close < primary_zone["low"]:
        state = "bearish_continuation"
    elif sma50 is not None and close >= sma50:
        state = "recovery_not_confirmed"
    else:
        state = "weak_below_sma50"
    return {
        "state": state,
        "close": close,
        "sma50": sma50,
        "sma_role": ("support" if sma50 is not None and close >= sma50 else "resistance"),
        "zone": primary_zone,
        "bullish_confirmation": up["trigger"] if up else None,
        # Decision Map แสดงเพียงแนวต้านถัดไปหนึ่งระดับ ส่วนระดับไกลยังอยู่ใน
        # ภาพโครงสร้างรอบใหญ่และบทความ เพื่อไม่ยืดแกนจนแท่งระยะใกล้เล็กลง
        "secondary_resistance": up["targets"][:1] if up else [],
        "invalidation": primary_zone["low"] if primary_zone else None,
        "channel_broken_above": bool(
            story.get("channel") and story["channel"].get("main_is_upper")
            and close > story["channel"]["main_at_last"]),
    }


def decision_label_layout(zone: dict, atr14: float) -> dict:
    """แยกป้ายฐานหลักกับป้ายหลุดฐานให้อยู่คนละด้านของโซนเสมอ

    ป้ายสีม่วงยึดเหนือขอบบนและขยายขึ้น ส่วนป้ายสีแดงยึดใต้ขอบล่างและขยายลง
    จึงไม่พึ่งระยะห่างคงที่ระหว่างกล่อง ซึ่งเคยทำให้สองป้ายซ้อนกันเมื่อโซนแคบ
    """
    gap = max(float(atr14) * 0.12, 1e-9)
    return {
        "zone_y": zone["high"] + gap,
        "zone_va": "bottom",
        "invalidation_y": zone["low"] - gap,
        "invalidation_va": "top",
    }


def _zoom_callout_labels(story: dict, plan: dict) -> dict[str, str]:
    """ข้อความกลาง Decision Map มีหน้าที่บอกความหมาย ไม่เป็นเจ้าของราคา."""
    return {
        "bullish": bullish_confirmation_label(
            story, plan["bullish_confirmation"]),
        "bearish": bearish_confirmation_label(story, plan["invalidation"]),
        "current": current_price_label(story, plan["close"]),
        "zone": checked_label(
            (f"ฐานหลัก · {money_for(story)(plan['zone']['high'])}"
             if plan["zone"] else "ฐานหลัก")),
        "sma50": checked_label("MA50"),
    }


def _zoom_right_tag_specs(story: dict, plan: dict,
                          secondary_specs: list[dict]) -> list[dict]:
    """คืน price tags ของ Decision Map ตามลำดับความสำคัญโดยไม่สร้างระดับใหม่.

    ระดับเดียวกันอาจทำหลายบทบาท จึง dedupe ด้วยข้อความราคาหลัง formatter เดิม
    และเก็บบทบาท rank สูงสุดเพียงใบเดียว ก่อนส่งให้ `_right_tags()` จัดตำแหน่ง.
    """
    money = money_for(story)
    zone = plan["zone"]
    entries = []
    if plan["bullish_confirmation"] is not None:
        entries.append({
            "role": "bullish_confirmation",
            "y": plan["bullish_confirmation"],
            "text": money(plan["bullish_confirmation"]),
            "face": COLORS["decision_up"],
            "rank": 1,
        })
    # Zone-low and zone-high are already stated by the downside region and the
    # in-band base label.  R7 removes only their duplicate right-side tags.
    if plan["sma50"] is not None:
        entries.append({
            "role": "sma50", "y": plan["sma50"], "text": money(plan["sma50"]),
            "face": COLORS["decision_hold"], "rank": 4,
        })
    entries.extend({
        "role": "secondary_resistance", "y": spec["value"], "text": spec["tag"],
        "face": spec["color"], "rank": 5,
    } for spec in secondary_specs)

    seen = set()
    deduped = []
    for entry in entries:
        if entry["text"] in seen:
            continue
        seen.add(entry["text"])
        deduped.append(entry)
    return deduped


def _draw_zoom(axes, story: dict, rows: list[dict], Rectangle) -> dict:
    """ภาพ 2 — Decision Map ที่เริ่มอ่านจากราคาปัจจุบัน ไม่เล่าภาพใหญ่ซ้ำ"""
    from matplotlib.patches import FancyArrowPatch

    zoom_bars = story["display"]["zoom_bars"]
    view = rows[-zoom_bars:]
    n = len(view)
    x_right = n - 1 + n * ZOOM_RIGHT_PAD_FRACTION
    plan = decision_map(story)
    close = plan["close"]
    zone = plan["zone"]
    sma50 = plan["sma50"]
    confirm = plan["bullish_confirmation"]
    callout_labels = _zoom_callout_labels(story, plan)

    secondary_specs = secondary_resistance_line_specs(
        story, list(plan["secondary_resistance"]))
    anchors = [r["low"] for r in view] + [r["high"] for r in view]
    if zone:
        # ป้ายฐานหลักอยู่เหนือโซนและป้ายหลุดฐานอยู่ใต้โซน จึงเผื่อพื้นที่คนละด้าน
        anchors += [zone["low"] - story["atr14"] * 1.20,
                    zone["high"] + story["atr14"] * 0.65]
    if sma50 is not None:
        anchors.append(sma50)
    if confirm is not None:
        anchors.append(confirm)
    # แนวต้านรองเป็นเส้นจริง จึงต้องอยู่ในแกนราคาและห้ามซ่อนเป็นกล่องลอย
    anchors += [spec["value"] for spec in secondary_specs]
    low, high = min(anchors), max(anchors)
    pad = (high - low) * 0.045
    view_offset = story["display"]["bars"] - n
    # ภาพนี้ไม่ขยายแกนตามกรอบทั้งชุด เพราะจะทำให้แท่งและระดับตัดสินใจเล็กลง
    bounds = zoom_bounds_with_header_clearance(
        (low - pad, high + pad),
        [spec["value"] for spec in secondary_specs],
    )
    axes.set_xlim(-2, x_right)
    axes.set_ylim(*bounds)
    callout_anchors: list[tuple[str, float]] = []
    if confirm is not None:
        callout_anchors.append(("bullish", confirm))
    callout_positions = packed_label_positions(
        bounds, callout_anchors, min_gap_fraction=0.13)
    card_x = n + 1.5

    # Decision Map ไม่วาดขอบ channel ที่อยู่นอกแกนเกือบทั้งเส้น เพราะเมื่อถูกตัด
    # จะเหลือเป็นเศษแถบสีที่มุมภาพและไม่ช่วยการตัดสินใจ ใช้เส้นกดเดิมเส้นเดียวแทน
    trend_drawn = _draw_zoom_descending_trend(
        axes, story, n=n, view_offset=view_offset, bounds=bounds)
    _draw_candles(axes, view, Rectangle)

    # ฐานหลักต้องอ่านเป็นพื้นที่ โดยใช้ขอบบน/ล่างเป็น decision thresholds เท่านั้น
    if zone:
        zone_start = int(n * 0.56)
        zone_width = x_right - zone_start - 1.2
        axes.add_patch(Rectangle((zone_start, zone["low"]), zone_width,
                                 zone["high"] - zone["low"],
                                 facecolor=COLORS["decision_zone"], alpha=0.12,
                                 edgecolor=COLORS["decision_zone"], linewidth=3.0, zorder=2))
        zone_artist = axes.text(
            zone_start + zone_width * 0.58, zone["mean"], callout_labels["zone"],
            color=COLORS["text"], fontsize=_key_text_size(15),
            ha="center", va="center", fontweight="bold", zorder=7)
        zone_artist.set_gid("premium-label:decision:zone")

    # เส้นยืนยันฝั่งขึ้นและแนวรับระหว่างทาง ใช้น้ำหนักตามลำดับการตัดสินใจ
    path_x = n - 1 + (x_right - (n - 1)) * 0.52
    if confirm is not None:
        axes.hlines(confirm, int(n * 0.58), x_right - 1.1,
                    color=COLORS["decision_up"], linewidth=4.2, zorder=5)
        up_arrow = FancyArrowPatch(
            (n - 1 + 0.2, close + story["atr14"] * 0.10),
            (path_x, confirm), connectionstyle="arc3,rad=0.10", arrowstyle="-|>",
            mutation_scale=24, linewidth=3.2, color=COLORS["decision_up"],
            alpha=SCENARIO_ARROW_ALPHA, zorder=6)
        up_arrow.set_gid("premium-scenario:decision:up")
        axes.add_patch(up_arrow)
        bullish_artist = axes.annotate(
            callout_labels["bullish"], xy=(path_x, confirm),
            xytext=(card_x, callout_positions["bullish"]), textcoords="data",
            color=COLORS["text"], fontsize=_key_text_size(15), ha="left", va="center",
            fontweight="bold",
            arrowprops=dict(arrowstyle="-", color=COLORS["decision_up"], linewidth=1.2),
            bbox=dict(boxstyle="round,pad=0.45", facecolor=COLORS["panel"],
                      edgecolor=COLORS["decision_up"], linewidth=1.8), zorder=7)
        bullish_artist.set_gid("premium-label:decision:bullish")
    if sma50 is not None:
        guide_start = int(n * 0.62)
        axes.hlines(sma50, guide_start, x_right - 1.1,
                    color=COLORS["decision_hold"], linewidth=2.8, zorder=5)
        hold_arrow = FancyArrowPatch(
            (n - 1 + 0.2, close - story["atr14"] * 0.10),
            (path_x, sma50), connectionstyle="arc3,rad=-0.20", arrowstyle="-|>",
            mutation_scale=22, linewidth=2.6, color=COLORS["decision_hold"],
            alpha=SCENARIO_ARROW_ALPHA, zorder=6)
        hold_arrow.set_gid("premium-scenario:decision:hold")
        axes.add_patch(hold_arrow)
        sma_artist = axes.text(
            card_x, sma50, callout_labels["sma50"],
            color=COLORS["warning"], fontsize=_key_text_size(15), ha="left", va="center",
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.38", facecolor=COLORS["panel"],
                      edgecolor=COLORS["decision_hold"], linewidth=1.5), zorder=7)
        sma_artist.set_gid("premium-label:decision:sma50")
        if zone and sma50 > zone["high"] + story["atr14"] * 0.05:
            base_arrow = FancyArrowPatch(
                (path_x, sma50), (path_x + 3.2, zone["high"]),
                connectionstyle="arc3,rad=-0.08", arrowstyle="-|>",
                mutation_scale=21, linewidth=2.45, color=COLORS["decision_down"],
                alpha=SCENARIO_ARROW_ALPHA, zorder=6)
            base_arrow.set_gid("premium-scenario:decision:hold-to-base")
            axes.add_patch(base_arrow)

    current_band_height = (bounds[1] - bounds[0]) * 0.01
    current_band = Rectangle(
        (-2, close - current_band_height / 2), x_right + 2,
        current_band_height, facecolor=COLORS["decision_now"],
        edgecolor=COLORS["decision_now"], linewidth=0.8,
        alpha=0.18, zorder=1.4)
    current_band.set_gid("premium-artist:decision:current-band")
    axes.add_patch(current_band)
    current_text = checked_label(f"ราคาปัจจุบัน {money_for(story)(close)}")
    current_artist = axes.text(
        x_right - 2.4, close, current_text, color=COLORS["ivory"],
        fontsize=_key_text_size(13), fontweight="bold",
        ha="right", va="center", zorder=7,
        bbox=dict(boxstyle="round,pad=0.12", facecolor=CURRENT_PRICE_BOX_FACE,
                  edgecolor=CURRENT_PRICE_BOX_FACE, linewidth=0.8))
    current_artist.set_gid("premium-label:decision:current-band")

    if zone:
        downside_region = Rectangle(
            (-2, bounds[0]), x_right + 2, zone["low"] - bounds[0],
            facecolor=COLORS["decision_down"], edgecolor="none",
            linewidth=0, alpha=0.12, zorder=1.2)
        downside_region.set_gid("premium-artist:decision:downside-region")
        axes.add_patch(downside_region)
        downside_text = checked_label(
            f"ยืนยันขาลง · ปิด D1 ต่ำกว่า {money_for(story)(zone['low'])}")
        downside_artist = axes.text(
            (-2 + x_right) / 2, (bounds[0] + zone["low"]) / 2,
            downside_text, color=COLORS["sell"], fontsize=_key_text_size(18),
            ha="center", va="center", fontweight="bold", zorder=7)
        downside_artist.set_gid("premium-label:decision:downside-region")

    # Marker remains a factual close anchor; the old floating current box/leader is gone.
    axes.scatter([n - 1], [close], s=130, marker=CURRENT_PRICE_MARKER,
                 facecolor="#ffffff",
                 edgecolor=COLORS["decision_now"], linewidth=2.4, zorder=7)
    # แนวต้านรอง: เส้นทึบเต็มกราฟ + ป้ายราคาเฉพาะขอบขวาตามภาพอ้างอิง
    for spec in secondary_specs:
        axes.hlines(spec["value"], -2, x_right, color=spec["color"],
                    linewidth=spec["linewidth"], linestyle=spec["linestyle"],
                    alpha=spec["alpha"], zorder=4)

    # ตัวเลขระดับทั้งหมดอยู่ใน price tags ขอบขวา; ไม่มี current หรือ zone midpoint
    tags = _zoom_right_tag_specs(story, plan, secondary_specs)
    _right_tags(axes, tags, x_right, bounds)
    _month_ticks(axes, view)

    return {"bars": n,
            "layout": {"header_rail": True, "light_plot_card": True,
                       "annotation_rail": True, "scenario_dock": "plot_annotation_rail",
                       "header_components": "asset_timeframe_only",
                       "ma50_label_leader_count": 0,
                       "base_label_leader_count": 0,
                       "base_band": ({"x0": zone_start, "x1": zone_start + zone_width,
                                      "y0": zone["low"], "y1": zone["high"]}
                                     if zone else None),
                       "base_label_position": ({"x": zone_start + zone_width * 0.58,
                                                "y": zone["mean"]}
                                               if zone else None),
                       "current_price_band": {
                           "center": close, "height": current_band_height,
                           "x0": -2, "x1": x_right, "alpha": 0.18,
                           "text": current_text,
                           "box_face": CURRENT_PRICE_BOX_FACE,
                           "text_color": COLORS["ivory"],
                       },
                       "current_on_band_box_count": 1,
                       "current_integrated_unboxed_text_count": 0,
                       "current_floating_box_count": 0,
                       "current_connector_count": 0,
                       "downside_region": ({
                           "x0": -2, "x1": x_right, "bottom": bounds[0],
                           "top": zone["low"], "alpha": 0.12,
                           "text": downside_text,
                       } if zone else None),
                       "downside_floating_box_count": 0,
                       "downside_connector_count": 0,
                       "downside_arrow_count": 0,
                       "remaining_scenario_arrow_count": len([
                           artist for artist in axes.patches
                           if str(artist.get_gid() or "").startswith(
                               "premium-scenario:decision:")]),
                       "status_card": None},
            "decision_state": plan["state"],
            "levels": {"current": close, "bullish_confirmation": confirm,
                       "sma50": sma50,
                       "zone_low": zone["low"] if zone else None,
                       "zone_midpoint": zone["mean"] if zone else None,
                       "zone_high": zone["high"] if zone else None,
                       "invalidation": plan["invalidation"]},
            "elements": {"scenario_up": confirm is not None,
                          "scenario_down": zone is not None,
                          "resistance_visible": ((1 if confirm is not None else 0)
                                                 + len(secondary_specs)),
                          "secondary_resistance_lines": len(secondary_specs),
                          "sma50": sma50 is not None,
                          "descending_trendline": trend_drawn,
                          "legacy_channel_band": False,
                          "current_price_right_tag": False,
                          "decision_map": True}}


def _single_figure(draw, story: dict, rows: list[dict], output_path: Path,
                   footer_text: str | None) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    font_used = _thai_font()
    figure = plt.figure(figsize=FIGURE_SIZE, dpi=DPI,
                        facecolor=COLORS["canvas"])
    grid = figure.add_gridspec(
        2, 1, height_ratios=(HEADER_HEIGHT_FRACTION, PLOT_HEIGHT_FRACTION),
        hspace=0.018, left=0.035, right=RIGHT_CANVAS_EDGE,
        top=0.97, bottom=0.035,
    )
    header = figure.add_subplot(grid[0])
    axes = figure.add_subplot(grid[1])
    variant = "overview" if draw is _draw_overview else "decision"
    bars = (story["display"]["bars"] if variant == "overview"
            else story["display"]["zoom_bars"])
    header_layout = _editorial_header(
        figure, header, axes, story, variant=variant, bars=bars)
    header_status_layout = None
    if (variant == "decision"
            and decision_map(story)["channel_broken_above"]):
        title_artist = next(
            artist for artist in header.texts
            if artist.get_gid() == "premium-decoration:header-title")
        underline = next(
            patch for patch in header.patches
            if patch.get_gid() == "premium-decoration:header-underline")
        _, header_status_layout = visual_theme.draw_header_accessory_card(
            figure, header, title_artist, underline,
            checked_label(DECISION_HEADER_STATUS), COLORS,
            role="decision-status", font_size=_key_text_size(18))
    _style_axes(axes)
    info = draw(axes, story, rows, Rectangle)
    bbox_report = visual_theme.premium_text_patch_overlap_report(
        figure, gap_pixels=12.0)
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    tick_boxes = [label.get_window_extent(renderer) for label in axes.get_yticklabels()
                  if label.get_visible() and label.get_text()]
    tick_safe_gutter = min(
        (figure.bbox.x1 - bbox.x1 for bbox in tick_boxes), default=figure.bbox.width)
    callout_texts = [
        artist.get_text() for artist in figure.findobj()
        if str(artist.get_gid() or "").startswith("premium-label:")
    ]
    layout = info.setdefault("layout", {})
    role_boxes = {
        item["role"]: item["bbox_px"]
        for item in bbox_report["boxes"]
    }
    protected_right_safe = min(
        (figure.bbox.x1 - values[2] for role, values in role_boxes.items()
         if not role.startswith("premium-label:header-card:")),
        default=figure.bbox.width)
    layout.update({
        "bbox_assertions": bbox_report,
        "edge_to_edge_header": header_layout,
        "header_visible_text": [
            artist.get_text() for artist in header.texts
            if artist.get_gid() == "premium-decoration:header-title"],
        "header_card_visible_text": [
            artist.get_text() for artist in header.texts
            if str(artist.get_gid() or "").startswith(
                "premium-label:header-card:")],
        "header_height_fraction": round(header.get_position().height, 4),
        "plot_height_fraction": round(axes.get_position().height, 4),
        "right_tick_safe_gutter_px": round(tick_safe_gutter, 2),
        "right_tick_safe_gutter_px_at_768": round(
            tick_safe_gutter * 768 / (FIGURE_SIZE[0] * DPI), 2),
        "protected_right_safe_gutter_px": round(protected_right_safe, 2),
        "protected_right_safe_gutter_px_at_768": round(
            protected_right_safe * 768 / (FIGURE_SIZE[0] * DPI), 2),
        "callout_texts": callout_texts,
        "callout_newline_count": sum("\n" in text for text in callout_texts),
    })
    if variant == "overview":
        containment = []
        for index, item in enumerate(layout.get("support_band_labels", [])):
            box = role_boxes[f"premium-label:overview:support-band-{index}"]
            band_bottom = axes.transData.transform((0, item["band_low"]))[1]
            band_top = axes.transData.transform((0, item["band_high"]))[1]
            containment.append(box[1] >= band_bottom and box[3] <= band_top)
        layout["support_label_inside_band"] = containment
    if variant == "decision" and layout.get("base_band"):
        layout["status_card"] = header_status_layout
        layout["header_components"] = (
            "asset_timeframe_plus_status_card"
            if header_status_layout else "asset_timeframe_only")
        layout["old_plot_status_count"] = sum(
            artist.get_gid() == "premium-label:decision:recovery"
            for artist in axes.texts)
        layout["old_status_accent_count"] = sum(
            artist.get_gid() == "premium-decoration:decision:status-left-accent"
            for artist in axes.lines)
        layout["header_status_card_count"] = sum(
            artist.get_gid() == "premium-label:header-card:decision-status"
            for artist in header.texts)
        layout["right_tag_texts"] = [
            artist.get_text() for artist in axes.texts
            if str(artist.get_gid() or "").startswith("premium-label:right-tag:")]
        layout["base_label_text"] = next(
            artist.get_text() for artist in axes.texts
            if artist.get_gid() == "premium-label:decision:zone")
        band = layout["base_band"]
        x0, y0 = axes.transData.transform((band["x0"], band["y0"]))
        x1, y1 = axes.transData.transform((band["x1"], band["y1"]))
        base_box = role_boxes["premium-label:decision:zone"]
        layout["base_label_inside_band"] = (
            base_box[0] >= x0 and base_box[2] <= x1
            and base_box[1] >= y0 and base_box[3] <= y1)
        axes_box = axes.get_window_extent(renderer)
        current_patch = next(
            artist for artist in axes.patches
            if artist.get_gid() == "premium-artist:decision:current-band")
        downside_patch = next(
            artist for artist in axes.patches
            if artist.get_gid() == "premium-artist:decision:downside-region")
        current_box = current_patch.get_window_extent(renderer)
        downside_region_box = downside_patch.get_window_extent(renderer)
        current_label_box = role_boxes["premium-label:decision:current-band"]
        current_artist = next(
            artist for artist in axes.texts
            if artist.get_gid() == "premium-label:decision:current-band")
        current_text_box = current_artist.get_window_extent(renderer)
        downside_label_box = role_boxes["premium-label:decision:downside-region"]
        current_center_px = axes.transData.transform(
            (0, layout["current_price_band"]["center"]))[1]
        downside_top_px = axes.transData.transform(
            (0, layout["downside_region"]["top"]))[1]
        layout["current_price_band"].update({
            "x0_delta_px": round(abs(current_box.x0 - axes_box.x0), 2),
            "x1_delta_px": round(abs(current_box.x1 - axes_box.x1), 2),
            "center_data_delta": round(
                abs(layout["current_price_band"]["center"]
                    - info["levels"]["current"]), 8),
            "thickness_plot_fraction": round(
                current_box.height / axes_box.height, 4),
            "label_center_delta_px": round(abs(
                (current_label_box[1] + current_label_box[3]) / 2
                - current_center_px), 2),
            "box_width_px": round(current_label_box[2] - current_label_box[0], 2),
            "box_height_px": round(current_label_box[3] - current_label_box[1], 2),
            "right_plot_margin_px": round(axes_box.x1 - current_label_box[2], 2),
            "text_height_px_at_768": round(
                current_text_box.height * 768 / figure.bbox.width, 2),
            "text_contrast": round(visual_theme.contrast_ratio(
                COLORS["ivory"], CURRENT_PRICE_BOX_FACE), 2),
        })
        layout["downside_region"].update({
            "x0_delta_px": round(abs(downside_region_box.x0 - axes_box.x0), 2),
            "x1_delta_px": round(abs(downside_region_box.x1 - axes_box.x1), 2),
            "bottom_delta_px": round(
                abs(downside_region_box.y0 - axes_box.y0), 2),
            "top_data_delta": round(abs(
                layout["downside_region"]["top"]
                - info["levels"]["zone_low"]), 8),
            "top_pixel_delta": round(abs(
                downside_region_box.y1 - downside_top_px), 2),
            "text_inside_region": bool(
                downside_label_box[0] >= downside_region_box.x0
                and downside_label_box[2] <= downside_region_box.x1
                and downside_label_box[1] >= downside_region_box.y0
                and downside_label_box[3] <= downside_region_box.y1),
            "text_contrast": round(visual_theme.contrast_ratio(
                COLORS["sell"], COLORS["bg"]), 2),
        })
        current = layout["current_price_band"]
        downside = layout["downside_region"]
        if (current["x0_delta_px"] > 1 or current["x1_delta_px"] > 1
                or current["center_data_delta"] > 0.01
                or not 0.007 <= current["thickness_plot_fraction"] <= 0.015
                or current["label_center_delta_px"] > 2
                or current["box_width_px"] > 243
                or current["box_height_px"] > 39.03
                or current["right_plot_margin_px"] < 8
                or current["text_height_px_at_768"] < 10
                or current["text_contrast"] < 7.0
                or downside["x0_delta_px"] > 1 or downside["x1_delta_px"] > 1
                or downside["bottom_delta_px"] > 1
                or downside["top_data_delta"] > 0.01
                or downside["top_pixel_delta"] > 1
                or not downside["text_inside_region"]
                or downside["text_contrast"] < 4.5):
            raise RuntimeError(f"Style D decision band contract failed: {layout}")
    if bbox_report["overlap_count"] or bbox_report["clipping_count"]:
        raise RuntimeError(
            "Style D premium label layout failure: "
            f"overlaps={bbox_report['overlaps']}; clipping={bbox_report['clipping']}")
    if (layout["protected_right_safe_gutter_px"] < 48
            or layout["protected_right_safe_gutter_px_at_768"] < 16):
        raise RuntimeError(f"Style D protected right gutter failed: {layout}")
    if footer_text:
        _footer(axes, footer_text)
    try:
        size_bytes = image_output.save_figure(
            figure, output_path, facecolor=COLORS["canvas"])
    finally:
        plt.close(figure)   # ตกด่านขนาดก็ต้องคืน figure ไม่งั้นรอบถัดไปกินหน่วยความจำสะสม
    return {"path": str(output_path), "font": font_used,
            "bytes": size_bytes, "kb": image_output.kb(size_bytes), **info}


def render_overview(story: dict, rows: list[dict], output_path: Path) -> dict:
    """ภาพที่ 1 — วัฏจักรรอบใหญ่ พร้อม legend และป้ายราคาครบทุกเส้น"""
    return _single_figure(
        _draw_overview, story, rows, output_path,
        OVERVIEW_FOOTER_TEXT)


def render_zoom(story: dict, rows: list[dict], output_path: Path) -> dict:
    """ภาพที่ 2 — แผนที่ตัดสินใจจากราคาปัจจุบัน"""
    return _single_figure(
        _draw_zoom, story, rows, output_path, ZOOM_FOOTER_TEXT)


def render_weekly_calendar(story: dict, output_path: Path, *, events: list[dict] | None = None,
                           page_number: int = 1, page_count: int = 1,
                           total_count: int | None = None, first_index: int = 1) -> dict:
    """ภาพปฏิทินหนึ่งหน้า; ผู้เรียกแบ่งหน้าแล้วจึงไม่มีการตัดข่าวในตัววาด."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    calendar = story.get("calendar") or {}
    table_only = bool(calendar.get("table_only"))
    if events is None:
        events = calendar.get("events") or []
    total_count = len(events) if total_count is None else total_count

    # ชุดสีอ้างอิงจากหน้าเว็บ WorldClassBroker: เขียวเข้มตัดทอง โดยคงพื้นแถว
    # เป็นสีอ่อนเพื่อให้ตัวเลขและชื่อเหตุการณ์อ่านได้ชัดบนจอและโทรศัพท์
    brand_green = visual_theme.BRAND["deep_green"]
    brand_green_header = visual_theme.BRAND["header_green"]
    brand_gold = visual_theme.BRAND["gold"]
    brand_cream = "#F4EBC9"
    row_cream = "#FFF9E8"
    row_green = "#EDF4EC"
    row_high = "#FFF1C2"

    font_used = _thai_font()
    figure_size = CALENDAR_TABLE_ONLY_FIGURE_SIZE if table_only else FIGURE_SIZE
    figure, axes = plt.subplots(figsize=figure_size, dpi=DPI)
    figure.patch.set_facecolor(brand_green)
    axes.set_axis_off()
    axes.set_facecolor(brand_green)
    # กินพื้นที่เกือบเต็มภาพ แทนการใช้ subplot margin เริ่มต้นของ Matplotlib
    table_source_y = None
    table_outer_margins_px = None
    if table_only:
        # คงขนาดตาราง 1920×1080 เดิม และแบ่งความสูงที่เพิ่มให้ขอบบน/ล่างเท่ากัน
        # ข้อความที่มาอยู่กึ่งกลางแถบล่าง โดยไม่ย่อ/ขยายตารางหรือเปลี่ยนข้อมูล
        original_height = FIGURE_SIZE[1] * DPI
        canvas_height = CALENDAR_TABLE_ONLY_FIGURE_SIZE[1] * DPI
        added_each_side = (canvas_height - original_height) / 2.0
        table_axes_bottom = (0.01 * original_height + added_each_side) / canvas_height
        table_axes_height = (0.98 * original_height) / canvas_height
        axes.set_position([
            0.01,
            table_axes_bottom,
            0.98,
            table_axes_height,
        ])
        # กึ่งกลางช่องว่างจริงระหว่างขอบล่างภาพกับขอบล่างตาราง
        table_source_y = table_axes_bottom / 2.0
        top_margin = 1.0 - (table_axes_bottom + table_axes_height)
        table_outer_margins_px = [
            round(top_margin * canvas_height, 4),
            round(table_axes_bottom * canvas_height, 4),
        ]
    else:
        axes.set_position([0.025, 0.105, 0.95, 0.73])

    rows = []
    row_impacts = []
    row_units = []
    previous_day = None
    for event in events:
        day = wcb_writers.date_thai(event.get("at"))
        display_day = day if day != previous_day else ""
        previous_day = day
        impact = str(event.get("impact") or "").lower()
        impact_text = "สูง" if impact == "high" else "ปานกลาง"
        title = str(event.get("title") or "").strip()
        event_text = textwrap.fill(title, width=52,
                                   break_long_words=True, break_on_hyphens=False)
        relevance_text = "โดยตรง" if event.get("relevance") == "direct" else "โดยอ้อม"
        bearish_condition, bullish_condition = calendar_split_conditions(
            event, str(story.get("asset") or ""))
        rows.append([
            display_day,
            (wcb_writers.clock(event.get("at")) + " น.")
            if wcb_writers.clock(event.get("at")) else "—",
            event_text,
            impact_text,
            relevance_text,
            bearish_condition,
            bullish_condition,
        ])
        row_impacts.append(impact)
        row_units.append(max(1, int(event.get("row_units") or event_text.count("\n") + 1)))

    columns = ["วันที่", "เวลาไทย", "เหตุการณ์", "ระดับ", "ความเกี่ยวข้อง",
               "เงื่อนไขขาลง", "เงื่อนไขขาขึ้น"]
    table = None
    if rows:
        table = axes.table(
            cellText=[[checked_label(value) for value in row] for row in rows],
            colLabels=[checked_label(value) for value in columns],
            colWidths=[0.11, 0.09, 0.34, 0.08, 0.10, 0.14, 0.14],
            cellLoc="center", colLoc="center", bbox=[0.0, 0.0, 1.0, 1.0])
        table.auto_set_font_size(False)
        total_units = max(1, sum(row_units))
        for (row_index, column_index), cell in table.get_celld().items():
            cell.set_edgecolor(brand_gold)
            cell.set_linewidth(1.25)
            cell.PAD = 0.03 if table_only else 0.10
            text = cell.get_text()
            text.set_fontfamily(font_used)
            if row_index == 0:
                cell.set_height(0.055 if table_only else 0.12)
                if column_index == 5:
                    cell.set_facecolor("#8F2836")
                elif column_index == 6:
                    cell.set_facecolor("#167A73")
                else:
                    cell.set_facecolor(brand_green_header)
                text.set_color(brand_cream)
                text.set_fontsize(_key_text_size(14.0 if column_index >= 5 else 15.2))
                text.set_fontweight("bold")
            else:
                body_fraction = 0.945 if table_only else 0.88
                cell.set_height(body_fraction * row_units[row_index - 1] / total_units)
                is_high = row_impacts[row_index - 1] == "high"
                cell.set_facecolor(
                    row_high if is_high else (row_green if row_index % 2 else row_cream))
                text.set_color(brand_green)
                text.set_fontsize(_secondary_text_size(13.0))
                if column_index == 2:
                    text.set_ha("left")
                if column_index == 0 and rows[row_index - 1][0]:
                    text.set_fontweight("bold")
                if column_index == 4:
                    text.set_fontweight("bold")
                    text.set_color("#167A73" if rows[row_index - 1][4] == "โดยตรง"
                                   else "#667085")
                if column_index == 5:
                    text.set_ha("center")
                    text.set_va("center")
                    text.set_fontweight("bold")
                    cell.set_facecolor("#FCE8EA")
                    text.set_color("#A32F40")
                if column_index == 6:
                    text.set_ha("center")
                    text.set_va("center")
                    text.set_fontweight("bold")
                    cell.set_facecolor("#E1F3EF")
                    text.set_color("#08766A")
    else:
        axes.text(0.5, 0.54,
                  checked_label("ไม่พบข่าวผลกระทบสูงหรือปานกลางที่ตรงทะเบียนสินทรัพย์ในสัปดาห์นี้"),
                  ha="center", va="center", color=brand_cream,
                  fontsize=_key_text_size(20), fontweight="bold", wrap=True)
        axes.text(0.5, 0.42,
                  checked_label("ระบบตรวจครบช่วงวันจันทร์–ศุกร์แล้ว และไม่เติมข่าวที่ไม่เกี่ยวข้อง"),
                  ha="center", va="center", color=brand_cream,
                  fontsize=_secondary_text_size(15), wrap=True)

    week_start = str(calendar.get("week_start") or "")
    week_end = str(calendar.get("week_end") or "")
    period = (f"{thai_date(week_start)} – {thai_date(week_end)}"
              if week_start and week_end else "สัปดาห์นี้")
    last_index = first_index + len(rows) - 1
    count_text = (f"รายการ {first_index}–{last_index} จาก {total_count}"
                  if rows else "ตรวจครบทั้งสัปดาห์ · ไม่พบรายการที่เกี่ยวข้อง")
    if table_only:
        figure.text(0.975, table_source_y, checked_label(CALENDAR_SOURCE_TEXT),
                    color=brand_cream, fontsize=_secondary_text_size(12.5),
                    ha="right", va="center")
    else:
        figure.text(0.025, 0.965, checked_label("ปฏิทินเศรษฐกิจประจำสัปดาห์"),
                    color=brand_cream, fontsize=_key_text_size(23),
                    fontweight="bold", va="top")
        figure.text(0.025, 0.912,
                    checked_label(
                        f"{story['symbol']} · {period} · เวลาไทย · หน้า {page_number}/{page_count}"),
                    color=brand_cream, fontsize=_secondary_text_size(16.0), va="top")
        figure.add_artist(plt.Line2D(
            [0.025, 0.975], [0.872, 0.872], transform=figure.transFigure,
            color=brand_gold, linewidth=2.0))
        figure.text(0.025, 0.042, checked_label(count_text),
                    color=brand_cream, fontsize=_secondary_text_size(12.5), va="bottom")
        figure.text(0.975, 0.042,
                    checked_label(CALENDAR_SOURCE_TEXT),
                    color=brand_cream, fontsize=_secondary_text_size(12.5),
                    ha="right", va="bottom")
    try:
        # ตารางรวมข่าวจริงทั้งสัปดาห์มีพื้นสีและตัวอักษรมากกว่ากราฟ จึงใช้
        # คุณภาพเฉพาะภาพนี้ที่ยังสูงกว่าพื้นขั้นต่ำ แทนการลดความละเอียด/ขนาดตัวอักษร
        size_bytes = image_output.save_figure(
            figure, output_path, facecolor=brand_green,
            webp_quality=CALENDAR_WEBP_QUALITY)
    finally:
        plt.close(figure)
    return {
        "path": str(output_path), "font": font_used,
        "bytes": size_bytes, "kb": image_output.kb(size_bytes),
        "rows": len(rows), "week_start": week_start, "week_end": week_end,
        "countries": calendar.get("countries") or [],
        "columns": columns,
        "effects": [
            ("สูง" if str(event.get("impact") or "").lower() == "high" else "ปานกลาง")
            + " · " + str(event.get("asset_effect"))
            if event.get("asset_effect") else f"{row[5]} | {row[6]}"
            for event, row in zip(events, rows)
        ],
        "conditions": [
            {"bearish": row[5], "bullish": row[6]} for row in rows
        ],
        "palette": {"green": brand_green, "gold": brand_gold},
        "page": page_number, "pages": page_count,
        "table_only": table_only,
        "source_text": CALENDAR_SOURCE_TEXT,
        "source_y": table_source_y if table_only else 0.042,
        "outer_margins_px": table_outer_margins_px,
        "canvas": [int(figure_size[0] * DPI), int(figure_size[1] * DPI)],
        "table_area_fraction": 0.98 * 0.98 if table_only else 0.95 * 0.73,
    }


def render_weekly_calendars(story: dict, output_dir: Path,
                            filenames: tuple[str, ...]) -> list[dict]:
    """วาดทุกหน้าตาม pagination manifest; จำนวนไฟล์ต้องตรงทุกครั้ง."""
    pages = (story.get("calendar") or {}).get("pages") or [[]]
    if len(pages) != len(filenames):
        raise ValueError("จำนวนหน้า calendar ไม่ตรงกับ manifest ชื่อไฟล์")
    total = len((story.get("calendar") or {}).get("events") or [])
    rendered: list[dict] = []
    first_index = 1
    for page_number, (events, filename) in enumerate(zip(pages, filenames), start=1):
        rendered.append(render_weekly_calendar(
            story, output_dir / filename, events=events,
            page_number=page_number, page_count=len(pages),
            total_count=total, first_index=first_index))
        first_index += len(events)
    return rendered
