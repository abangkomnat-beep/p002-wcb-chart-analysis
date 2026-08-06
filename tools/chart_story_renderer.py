"""ตัววาดกราฟสไตล์ D — วาดจาก story artifact เท่านั้น ไม่คำนวณระดับเองแม้แต่เส้นเดียว

ภาพ 2 ใบต่อบท (หัวหน้าอนุมัติหน้าตาจากต้นแบบ 2026-08-06):
1. `render_overview` — วัฏจักรรอบใหญ่ ~320 แท่ง: ribbon โหมดตลาด · กรอบแนวโน้ม ·
   แนวต้านแนวนอน · โซนรับ (โทน TradingView light 16:9 ตามภาพตัวอย่างของหัวหน้า)
2. `render_zoom` — ระยะใกล้ ~120 แท่ง: ระดับตัดสินใจ + เส้นประ "ฉากทัศน์" สองทาง
   (เส้นฉากทัศน์ต้องดูออกทันทีว่าเป็นสมมุติ: เส้นประ โปร่ง และมีป้ายกำกับ)

geometry ทุกชิ้นมาจาก `chart_story.build_story` — ถ้าภาพผิด ให้แก้ที่เครื่องคิด
ไม่ใช่มาแต่งที่ตัววาด
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import chart_story  # noqa: E402
from tools.chart_renderer import THAI_MONTHS  # noqa: E402

RIGHT_PAD_FRACTION = 0.14
ZOOM_RIGHT_PAD_FRACTION = 0.22   # เผื่อที่ให้เส้นและป้ายฉากทัศน์
FIGURE_SIZE = (19.2, 10.8)
DPI = 100

COLORS = {
    "bg": "#ffffff", "grid": "#edf0f4", "axis": "#787b86", "text": "#131722",
    "up": "#26a69a", "down": "#ef5350",
    "ribbon_up": "#1e9e83", "ribbon_down": "#f23645",
    "channel": "#f23645", "level": "#555b66", "zone": "#7e57c2",
    "key": "#e91e2c", "diag": "#9aa0a6",
    "scenario_up": "#1e9e83", "scenario_down": "#f23645",
}


def thai_date(date_text: str) -> str:
    """'2026-08-06' → '6 ส.ค. 2026' — ใช้ทั้งบนภาพและในบทความให้สะกดตรงกัน"""
    year, month, day = date_text.split("-")
    return f"{int(day)} {THAI_MONTHS[int(month) - 1]} {year}"


def _thai_font() -> str:
    from matplotlib import font_manager, rcParams

    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in ("Tahoma", "Leelawadee UI", "Segoe UI"):
        if name in available:
            rcParams["font.family"] = name
            return name
    return rcParams["font.family"]


def _base_axes(plt):
    figure, axes = plt.subplots(figsize=FIGURE_SIZE, dpi=DPI)
    figure.patch.set_facecolor(COLORS["bg"])
    axes.set_facecolor(COLORS["bg"])
    for spine in axes.spines.values():
        spine.set_color("#d1d4dc")
    axes.tick_params(colors=COLORS["axis"], labelsize=12)
    axes.grid(True, color=COLORS["grid"], linewidth=0.8)
    axes.yaxis.tick_right()
    axes.set_axisbelow(True)
    return figure, axes


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
                *, label: bool = True) -> None:
    atr = story["atr14"]
    n = len(view)
    for zone in story["zones"]:
        axes.add_patch(Rectangle((-2, zone["low"]), x_right + 2, zone["high"] - zone["low"],
                                 facecolor=COLORS["zone"], alpha=0.16, edgecolor="none", zorder=1))
        axes.hlines(zone["mean"], -2, x_right, color=COLORS["zone"], alpha=0.55,
                    linewidth=1.0, linestyle=(0, (5, 3)), zorder=1)
        if not label:
            continue
        caption = f"POI {zone['rank']} · โซนรับ · แตะ {zone['touches']} ครั้ง"
        if zone["includes_week52_low"]:
            caption += " · รวมจุดต่ำสุด 52 สัปดาห์"
        label_top = zone["high"] + atr * 1.1
        label_x = 2
        for candidate in (2, int(n * 0.3), int(n * 0.55), int(n * 0.78)):
            span = view[candidate:candidate + max(1, int(n * 0.18))]
            if all(r["low"] > label_top or r["high"] < zone["high"] for r in span):
                label_x = candidate
                break
        axes.text(label_x, zone["high"] + atr * 0.15, caption,
                  color=COLORS["zone"], fontsize=12, va="bottom", zorder=6)


def _draw_channel(axes, story: dict, n: int, x_right: float) -> None:
    channel = story["channel"]
    if not channel:
        return
    start = channel["start"]
    xs = [start, n - 1 + n * 0.02]
    main = [channel["slope"] * (x - start) + channel["intercept"] for x in xs]
    parallel = [value + channel["offset"] for value in main]
    band = 0.55 * story["atr14"]
    for line in (main, parallel):
        axes.fill_between(xs, [v - band for v in line], [v + band for v in line],
                          color=COLORS["channel"], alpha=0.20, zorder=2)
        axes.plot(xs, line, color=COLORS["channel"], alpha=0.35, linewidth=1.2, zorder=2)
    mid_xs = [start, x_right]
    mid = [channel["slope"] * (x - start) + channel["intercept"] + channel["offset"] / 2
           for x in mid_xs]
    axes.plot(mid_xs, mid, color=COLORS["diag"], linewidth=1.1,
              linestyle=(0, (6, 4)), zorder=2)


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
        axes.text(x_right, entry["label_y"], entry["text"], color="#ffffff", fontsize=11.5,
                  ha="right", va="center", zorder=7,
                  bbox=dict(boxstyle="round,pad=0.28", facecolor=entry["face"], edgecolor="none"))


def _month_ticks(axes, view: list[dict]) -> None:
    ticks, labels = [], []
    previous = None
    for index, row in enumerate(view):
        month = row["date"][:7]
        if month != previous:
            previous = month
            year, month_number = int(month[:4]), int(month[5:7])
            ticks.append(index)
            labels.append(str(year) if month_number == 1 else THAI_MONTHS[month_number - 1])
    axes.set_xticks(ticks[1:])
    axes.set_xticklabels(labels[1:])


def _header(axes, story: dict, subtitle: str) -> None:
    axes.text(0.01, 0.985, f"{story['symbol']} · รายวัน (D1)",
              transform=axes.transAxes, color=COLORS["text"], fontsize=17,
              fontweight="bold", va="top", zorder=8)
    axes.text(0.01, 0.952, subtitle, transform=axes.transAxes,
              color=COLORS["axis"], fontsize=12.5, va="top", zorder=8)


def _footer(axes, text: str) -> None:
    axes.text(0.01, 0.015, text, transform=axes.transAxes,
              color=COLORS["axis"], fontsize=10.5, va="bottom", zorder=8)


def price_text(value: float) -> str:
    """รูปแบบราคาที่ภาพและบทความใช้ร่วมกัน — เปลี่ยนที่นี่ต้องเปลี่ยนด่านตรวจด้วย"""
    return f"{value:,.2f}"


def render_overview(story: dict, rows: list[dict], output_path: Path) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    font_used = _thai_font()
    view = rows[-story["display"]["bars"]:]
    n = len(view)
    figure, axes = _base_axes(plt)

    x_right = n - 1 + n * RIGHT_PAD_FRACTION
    low = min(r["low"] for r in view)
    high = max(r["high"] for r in view)
    pad = (high - low) * 0.06
    axes.set_xlim(-2, x_right)
    axes.set_ylim(low - pad, high + pad)

    _draw_zones(axes, story, view, x_right, Rectangle)
    for level in story["resistance"]:
        axes.hlines(level["mean"], -2, n - 1 + n * 0.02, color=COLORS["level"],
                    alpha=0.75, linewidth=0.9, zorder=1)
    if not any(zone["includes_week52_low"] for zone in story["zones"]):
        axes.hlines(story["week52_low"], -2, x_right, color=COLORS["key"],
                    linewidth=1.4, zorder=2)
        axes.text(2, story["week52_low"] - story["atr14"] * 0.35, "ต่ำสุด 52 สัปดาห์",
                  color=COLORS["key"], fontsize=12, va="top", zorder=6)
    _draw_channel(axes, story, n, x_right)
    _draw_candles(axes, view, Rectangle)
    _draw_ribbon(axes, rows, n)

    tags = [{"y": story["current"]["close"], "text": price_text(story["current"]["close"]),
             "face": "#131722", "rank": 0}]
    for zone in story["zones"]:
        tags.append({"y": zone["mean"], "text": price_text(zone["mean"]),
                     "face": COLORS["zone"], "rank": 2})
    if not any(zone["includes_week52_low"] for zone in story["zones"]):
        tags.append({"y": story["week52_low"], "text": price_text(story["week52_low"]),
                     "face": COLORS["key"], "rank": 1})
    _right_tags(axes, tags, x_right, (low - pad, high + pad))
    _month_ticks(axes, view)

    mode = "ขาลง" if story["regime"]["down"] else "ขาขึ้น"
    _header(axes, story,
            f"ภาพรวมโครงสร้าง {n} แท่ง · ข้อมูลถึง {thai_date(story['current']['date'])} · "
            f"ปิด {price_text(story['current']['close'])} · โหมดเส้นค่าเฉลี่ย 50 วัน: {mode}")
    _footer(axes, f"ข้อมูล: WCB series API · {n} แท่ง D1 · "
                  "ทุกเส้นและโซนคำนวณจากข้อมูลจริง · สไตล์ D — อ่านโครงสร้างกราฟ (P002)")

    figure.tight_layout(pad=1.4)
    figure.savefig(output_path, facecolor=COLORS["bg"])
    plt.close(figure)
    return {"path": str(output_path), "bars": n, "font": font_used,
            "elements": {"zones": len(story["zones"]),
                         "resistance": len(story["resistance"]),
                         "channel": bool(story["channel"])}}


def render_zoom(story: dict, rows: list[dict], output_path: Path) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    font_used = _thai_font()
    zoom_bars = story["display"]["zoom_bars"]
    view = rows[-zoom_bars:]
    n = len(view)
    figure, axes = _base_axes(plt)
    x_right = n - 1 + n * ZOOM_RIGHT_PAD_FRACTION

    # ช่วงราคา: แท่งในหน้าต่าง + ระดับฉากทัศน์/โซนที่บทพูดถึง ต้องเห็นครบ
    anchors = [r["low"] for r in view] + [r["high"] for r in view]
    for zone in story["zones"][:1]:
        anchors += [zone["low"], zone["high"]]
    for side in ("up", "down"):
        scenario = story["scenarios"][side]
        if scenario:
            anchors += [scenario["trigger"], *scenario["targets"]]
    low, high = min(anchors), max(anchors)
    pad = (high - low) * 0.06
    axes.set_xlim(-2, x_right)
    axes.set_ylim(low - pad, high + pad)

    _draw_zones(axes, story, view, x_right, Rectangle)
    visible = [level for level in story["resistance"]
               if low - pad <= level["mean"] <= high + pad]
    for level in visible:
        axes.hlines(level["mean"], -2, x_right, color=COLORS["level"],
                    alpha=0.75, linewidth=0.9, zorder=1)

    # กรอบแนวโน้มเฉพาะส่วนที่อยู่ในหน้าต่างซูม — แปลง index จากหน้าต่างภาพรวม
    channel = story["channel"]
    view_offset = story["display"]["bars"] - n
    if channel and channel["start"] < story["display"]["bars"]:
        start_zoom = channel["start"] - view_offset
        xs = [max(start_zoom, -2), n - 1 + n * 0.02]
        main = [channel["slope"] * (x + view_offset - channel["start"]) + channel["intercept"]
                for x in xs]
        parallel = [value + channel["offset"] for value in main]
        band = 0.55 * story["atr14"]
        for line in (main, parallel):
            axes.fill_between(xs, [v - band for v in line], [v + band for v in line],
                              color=COLORS["channel"], alpha=0.20, zorder=2)
            axes.plot(xs, line, color=COLORS["channel"], alpha=0.35, linewidth=1.2, zorder=2)

    _draw_candles(axes, view, Rectangle)
    _draw_ribbon(axes, rows, n)

    # เส้นประฉากทัศน์ — ลากจากแท่งล่าสุดไปยังระดับเป้า พร้อมป้ายบอกชัดว่าเป็นสมมุติ
    tags = [{"y": story["current"]["close"], "text": price_text(story["current"]["close"]),
             "face": "#131722", "rank": 0}]
    for side, color in (("up", COLORS["scenario_up"]), ("down", COLORS["scenario_down"])):
        scenario = story["scenarios"][side]
        if not scenario:
            continue
        points = [scenario["trigger"], *scenario["targets"]]
        span = x_right - (n - 1)
        for step, target in enumerate(points, start=1):
            end_x = (n - 1) + span * (0.35 + 0.2 * step)
            axes.plot([n - 1, end_x], [story["current"]["close"], target],
                      color=color, alpha=0.45, linewidth=1.6,
                      linestyle=(0, (5, 4)), zorder=5)
            tags.append({"y": target, "text": price_text(target), "face": color, "rank": 3})
        label = ("ฉากทัศน์ขึ้น" if side == "up" else "ฉากทัศน์ลง") + f" · {scenario['condition']}"
        label_y = points[-1] + (story["atr14"] * 0.8 if side == "up" else -story["atr14"] * 0.8)
        axes.text((n - 1) + span * 0.5, label_y, label, color=color, fontsize=11.5,
                  ha="center", va="center", alpha=0.9, zorder=6)

    for zone in story["zones"]:
        if low - pad <= zone["mean"] <= high + pad:
            tags.append({"y": zone["mean"], "text": price_text(zone["mean"]),
                         "face": COLORS["zone"], "rank": 2})
    _right_tags(axes, tags, x_right, (low - pad, high + pad))
    _month_ticks(axes, view)

    _header(axes, story,
            f"ระยะใกล้ {n} แท่ง · ระดับตัดสินใจและฉากทัศน์ · "
            f"ข้อมูลถึง {thai_date(story['current']['date'])}")
    _footer(axes, "เส้นประ \"ฉากทัศน์\" เป็นเงื่อนไขสมมุติจากระดับที่คำนวณได้ ไม่ใช่ข้อมูลย้อนหลัง "
                  "และไม่ใช่คำทำนาย · ข้อมูล: WCB series API · สไตล์ D (P002)")

    figure.tight_layout(pad=1.4)
    figure.savefig(output_path, facecolor=COLORS["bg"])
    plt.close(figure)
    return {"path": str(output_path), "bars": n, "font": font_used,
            "elements": {"scenario_up": bool(story["scenarios"]["up"]),
                         "scenario_down": bool(story["scenarios"]["down"]),
                         "resistance_visible": len(visible)}}
