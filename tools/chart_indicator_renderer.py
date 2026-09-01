"""ตัววาดกราฟสไตล์ E — วาดจาก artifact ของ `chart_indicator` เท่านั้น

**ภาพเดียวต่อบท** (ผู้ใช้สั่งรวม 2026-08-07 — สไตล์ E รวม · สไตล์ D ไม่รวม):
สามแผงซ้อนในผืนเดียวบนพื้นขาว โดยไม่มีหัวเรื่องเหนือกราฟ:
1. แผงราคา — แท่งเทียน + EMA12/26 + SMA50 + Fibonacci คงป้ายอัตราส่วนไว้ซ้าย
   และแยกป้ายราคาไปชิดขวาสุด
   สีรายขั้น + โซนเข้า/SL/TP ของฉากทัศน์หลัก (กำกับชัดว่าเป็นเงื่อนไข ไม่ใช่คำทำนาย)
2. แผง RSI (14)
3. แผง MACD (12, 26, 9)

geometry ทุกชิ้นมาจาก `build_indicators` — ภาพผิดให้แก้ที่เครื่องคิด ไม่ใช่แต่งที่ตัววาด
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import chart_indicator, chart_story, image_output  # noqa: E402
from tools.chart_renderer import THAI_MONTHS  # noqa: E402
from tools.chart_story_renderer import (  # noqa: E402
    _thai_font, checked_label, money_for, month_tick_labels)

FIGURE_SIZE = (19.2, 12.6)       # สามแผงซ้อน — สูงกว่า 16:9 ให้แผงราคาอ่านแท่งออก
DPI = 100
RIGHT_PAD_FRACTION = 0.20        # เผื่อที่ให้กล่องโซนเข้าและป้าย SL/TP
# บทความยังเก็บ Fibonacci ครบชุดเพื่ออธิบายที่มาของแผน แต่ภาพแสดงเฉพาะ
# ระดับที่มีหน้าที่ต่อการตัดสินใจ ไม่วาด 0.382/0.5 ทับแท่งเทียนอีก
VISIBLE_FIB_RATIOS = frozenset({0.236, 0.618, 0.786})
FIB_RATIO_LABEL_X = 2
FIB_PRICE_LABEL_X_AXES = 0.995

COLORS = {
    "bg": "#ffffff", "grid": "#e5e7eb", "axis": "#4b5563", "text": "#111827",
    "up": "#0f766e", "down": "#dc2626",
    "ema_fast": "#ea580c", "ema_slow": "#0284c7", "sma": "#111827",
    "rsi": "#7e22ce", "rsi_band": "#6b7280",
    "macd": "#1d4ed8", "signal": "#ea580c", "hist": "#60a5fa",
    "fib": "#4b5563", "fib_anchor": "#a16207", "golden": "#c2410c",
    "order_zone_fill": "#ffedd5", "order_zone_edge": "#c2410c",
    "extension": "#dc2626", "swing": "#6b7280",
    "entry": "#0f766e", "sl": "#dc2626", "tp": "#15803d",
    # E-3 (ฟีดแบ็กหัวหน้า 08-07): Scenario B (สวนเทรนด์) ไม่เคยถูกวาดเลย — เพิ่มสีชุดที่สอง
    # ให้แยกจาก Scenario A ด้วยตา ส่วน SL/TP คงโทนแดง/เขียวเดิม (มาตรฐานอ่านกราฟสากล)
}

# สีประจำขั้น Fibonacci — ผู้ใช้ขอ 2026-08-06: แยกสีรายขั้นและให้เข้มขึ้น (เดิมเทาจางหมด)
# โทนตามต้นแบบ TradingView: จุดตั้งต้น/ปลาย swing เหลือง · ขั้นกลางไล่โทนแดง→ส้ม→เขียว→ฟ้า→ม่วง
FIB_LEVEL_COLORS = {
    0.0: "#a16207", 0.236: "#c62828", 0.382: "#d97706", 0.5: "#15803d",
    0.618: "#0f766e", 0.705: "#0369a1", 0.786: "#1d4ed8", 0.886: "#7e22ce",
    1.0: "#a16207",
}

_LABEL_BOX = dict(boxstyle="round,pad=0.28", facecolor="#ffffff", alpha=0.97,
                  edgecolor="#d1d5db", linewidth=0.6)
_FIB_PRICE_LABEL_BOX = dict(boxstyle="round,pad=0.20", facecolor="#ffffff", alpha=0.97,
                            edgecolor="#d1d5db", linewidth=0.6)


def _draw_fib_label(axes, *, y: float, ratio: str, price: str, color: str) -> None:
    """คงอัตราส่วนไว้ที่ anchor เดิม และวางราคาแยกชิดขอบขวาของกราฟ."""
    axes.text(FIB_RATIO_LABEL_X, y, checked_label(ratio),
              color=color, fontsize=12.5, fontweight="bold", va="bottom", zorder=6,
              bbox=_LABEL_BOX)
    axes.text(FIB_PRICE_LABEL_X_AXES, y, checked_label(price),
              transform=axes.get_yaxis_transform(), color=color,
              fontsize=11.5, fontweight="bold", ha="right", va="bottom",
              zorder=6, bbox=_FIB_PRICE_LABEL_BOX)


def _style_axes(axes) -> None:
    axes.set_facecolor(COLORS["bg"])
    for spine in axes.spines.values():
        spine.set_color("#d1d5db")
    axes.tick_params(colors=COLORS["axis"], labelsize=11)
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


def _series_view(values: list[float | None], total: int, view_len: int) -> list[float | None]:
    return values[total - view_len:]


def _plot_line(axes, values: list[float | None], color: str, *,
               linewidth: float = 1.6, linestyle: str = "-", alpha: float = 1.0,
               zorder: int = 4) -> None:
    xs = [i for i, v in enumerate(values) if v is not None]
    ys = [v for v in values if v is not None]
    if len(xs) > 1:
        axes.plot(xs, ys, color=color, linewidth=linewidth, linestyle=linestyle,
                  alpha=alpha, zorder=zorder)


def _time_ticks(axes, view: list[dict], timeframe: str) -> None:
    if timeframe == chart_indicator.TIMEFRAME and view and view[0].get("at"):
        count = min(7, len(view))
        ticks = sorted({round(index * (len(view) - 1) / max(count - 1, 1))
                        for index in range(count)})
        labels = []
        for index in ticks:
            at = view[index]["at"]
            labels.append(f"{int(at[8:10])} {THAI_MONTHS[int(at[5:7]) - 1]}\n{at[11:16]} น.")
        axes.set_xticks(ticks)
        axes.set_xticklabels(labels)
        return
    ticks, labels = month_tick_labels(view)
    axes.set_xticks(ticks[1:])
    axes.set_xticklabels(labels[1:])


def _right_tags(axes, entries: list[dict], x_right: float, y_range: tuple[float, float]) -> None:
    """ป้ายราคาฝั่งขวา จัดไม่ให้ทับกัน — rank ต่ำกว่า = สำคัญกว่า = อยู่ตำแหน่งจริง"""
    minimum_gap = (y_range[1] - y_range[0]) * 0.034
    placed: list[dict] = []
    seen_texts: set[str] = set()
    for entry in sorted(entries, key=lambda item: item["rank"]):
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
        axes.text(x_right, entry["label_y"], checked_label(entry["text"]), color="#ffffff", fontsize=12.5,
                  fontweight="bold",
                  ha="right", va="center", zorder=7,
                  bbox=dict(boxstyle="round,pad=0.28", facecolor=entry["face"], edgecolor="none"))


def _panel_label(axes, text: str) -> None:
    axes.text(0.005, 0.94, checked_label(text), transform=axes.transAxes, color=COLORS["text"],
              fontsize=14, fontweight="bold", va="top", zorder=8, bbox=_LABEL_BOX)


def _rsi_status(value: float) -> str:
    if value < 50:
        return "ฝั่งขายครองตลาด"
    if value > 50:
        return "ฝั่งซื้อครองตลาด"
    return "แรงซื้อกับแรงขายสมดุล"


def _macd_status(histogram: float) -> str:
    if histogram > 0:
        return "รีบาวด์ระยะสั้น"
    if histogram < 0:
        return "แรงขายระยะสั้น"
    return "แรงส่งระยะสั้นทรงตัว"


def _entry_zone_label(scenario: dict, money) -> str:
    side = scenario["side"].upper()
    role = "แนวต้าน" if side == "SELL" else "แนวรับ"
    entry_bottom = min(scenario["entry_low"], scenario["entry_high"])
    entry_top = max(scenario["entry_low"], scenario["entry_high"])
    status = ("พื้นที่เฝ้าระวัง — โซนยังไกลจากราคาปัจจุบัน"
              if not scenario.get("daily_entry", True) else "โฟกัสวันนี้")
    basis = ("ระดับจากแท่ง H1 ปิดล่าสุด + ATR14"
             if scenario.get("source") else f"{role}สำคัญ (61.8%–78.6%)")
    return (f"{status} · โซนรอ {side} (ตามเทรนด์หลัก)\n"
            f"โซนรอเข้าออเดอร์ · {basis}\n"
            f"{money(entry_bottom)}–{money(entry_top)}")


def _tp_label(order: int, target: float, money) -> str:
    """ป้ายเป้าหมายแบบสั้น ลดโอกาสชนกับป้ายราคาปัจจุบัน"""
    return f"TP{order} {money(target)}"


def entry_zone_visible(story: dict) -> bool:
    """มีแผนหลักต้องวาดโซน/SL/TP แม้ราคายังอยู่ไกล โดยป้ายบอกสถานะให้ชัด"""
    scenario = story.get("scenarios", {}).get("primary")
    return bool(scenario)


def _entry_zone_label_position(story: dict, bar_count: int,
                               x_right: float) -> tuple[float, str]:
    """XAUUSD ยึดขอบขวาของป้ายกับขอบกราฟ; สินทรัพย์อื่นยังใช้กึ่งกลางเดิม"""
    if story.get("asset") == "xauusd":
        return x_right - 1.5, "right"
    return int(bar_count * 0.56), "center"


def _current_price_label_layout(story: dict) -> tuple[tuple[int, int], str]:
    """รักษาป้ายไว้ที่ระดับราคาจริง; เมื่อราคาอยู่ในโซนให้หลบกล่องไปทางซ้าย"""
    scenario = story.get("scenarios", {}).get("primary")
    if entry_zone_visible(story) and scenario.get("active", False):
        return (-10, 0), "right"
    return (9, 0), "left"


def _draw_current_price(axes, story: dict, bar_count: int, money) -> bool:
    """วางป้ายราคาปัจจุบันข้างแท่งล่าสุดเฉพาะ XAUUSD; คืน True เมื่อวาดแล้ว"""
    if story.get("asset") != "xauusd":
        return False
    current = story["current"]["close"]
    label_offset, label_alignment = _current_price_label_layout(story)
    axes.scatter([bar_count - 1], [current], s=30, color="#2962ff",
                 edgecolor="#ffffff", linewidth=0.8, zorder=8)
    axes.annotate(checked_label(f"ราคาปัจจุบัน {money(current)}"),
                  xy=(bar_count - 1, current), xytext=label_offset,
                  textcoords="offset points",
                  color="#111827", fontsize=12, fontweight="bold",
                  ha=label_alignment, va="center", zorder=9,
                  bbox=dict(boxstyle="round,pad=0.30", facecolor="#facc15",
                            edgecolor="#111827", linewidth=0.8, alpha=0.98))
    return True


def _draw_fib_content(axes, story: dict, view: list[dict], x_right: float,
                      Rectangle) -> list[dict]:
    """เส้น Fibonacci + โซนเข้า/SL/TP บนแผงราคา — คืนรายการป้ายฝั่งขวาที่ต้องติด"""
    money = money_for(story)
    fib = story["fib"]
    n = len(view)
    tags: list[dict] = []
    if not fib:
        scenario = chart_indicator.public_scenario(story)
        if not scenario:
            return tags
        entry_bottom = min(scenario["entry_low"], scenario["entry_high"])
        entry_top = max(scenario["entry_low"], scenario["entry_high"])
        axes.add_patch(Rectangle((-2, entry_bottom), x_right + 2,
                                 entry_top - entry_bottom,
                                 facecolor=COLORS["order_zone_fill"], alpha=0.46,
                                 edgecolor=COLORS["order_zone_edge"], linewidth=1.2, zorder=1))
        zone_label = ("พื้นที่เฝ้าระวัง — แผนสำรองจากแท่ง H1 ปิดล่าสุด\n"
                      f"โซนรอเข้า {scenario['side'].upper()}\n"
                      f"{money(entry_bottom)}–{money(entry_top)}")
        axes.text(_entry_zone_label_position(story, n, x_right)[0],
                  (entry_bottom + entry_top) / 2, checked_label(zone_label),
                  color=COLORS["order_zone_edge"], fontsize=13.0, fontweight="bold",
                  ha=_entry_zone_label_position(story, n, x_right)[1], va="center", zorder=6,
                  bbox=dict(boxstyle="round,pad=0.38", facecolor="#fff7ed", alpha=0.98,
                            edgecolor=COLORS["order_zone_edge"], linewidth=1.0))
        axes.hlines(scenario["sl"], n - 1, x_right, color=COLORS["sl"],
                    linewidth=1.6, linestyle=(0, (4, 3)), zorder=4)
        tags.append({"y": scenario["sl"], "text": f"ตัดขาดทุน (SL) {money(scenario['sl'])}",
                     "face": COLORS["sl"], "rank": 1})
        for order, target in enumerate(scenario["tps"], start=1):
            axes.hlines(target, n - 1, x_right, color=COLORS["tp"], linewidth=1.3,
                        linestyle=(0, (4, 3)), alpha=0.9, zorder=4)
            tags.append({"y": target, "text": _tp_label(order, target, money),
                         "face": "#2e7d32", "rank": order + 1})
        return tags

    golden_low, golden_high = fib["golden"]
    for level in fib["levels"]:
        if level["ratio"] not in VISIBLE_FIB_RATIOS:
            continue
        color = FIB_LEVEL_COLORS.get(level["ratio"], COLORS["fib"])
        axes.hlines(level["price"], -2, x_right, color=color,
                    alpha=0.85, linewidth=1.2, zorder=2)
        _draw_fib_label(
            axes, y=level["price"] + story["atr14"] * 0.08,
            ratio=f"{level['ratio']:g}", price=money(level["price"]), color=color)
    axes.hlines(fib["extension"], -2, x_right, color=COLORS["extension"],
                alpha=0.95, linewidth=1.3, zorder=2)
    _draw_fib_label(
        axes, y=fib["extension"] + story["atr14"] * 0.08,
        ratio=f"{chart_indicator.EXTENSION_RATIO:g}",
        price=money(fib["extension"]), color=COLORS["extension"])
    # เส้น swing ที่ใช้วัด — ให้คนอ่านเห็นว่า Fibonacci ผูกกับขาไหน
    def _bar_index(anchor: dict) -> int | None:
        for index, row in enumerate(view):
            if anchor.get("at") and row.get("at") == anchor["at"]:
                return index
            if not anchor.get("at") and row["date"] == anchor["date"]:
                return index
        return None

    start_key = "swing_high" if fib["direction"] == "down" else "swing_low"
    end_key = "swing_low" if fib["direction"] == "down" else "swing_high"
    start_x = _bar_index(fib[start_key])
    end_x = _bar_index(fib[end_key])
    if start_x is not None and end_x is not None:
        axes.plot([start_x, end_x], [fib[start_key]["price"], fib[end_key]["price"]],
                  color=COLORS["swing"], linewidth=1.2, linestyle=(0, (6, 4)),
                  alpha=0.8, zorder=2)

    # ผู้ใช้สั่ง 2026-08-19 ให้ Style E แสดงฝั่งที่หลักฐานสนับสนุนมากที่สุดเพียงฝั่งเดียว
    # ภาพจึงวาดเฉพาะ primary ให้ตรงกับบท และไม่สร้างแผนสวนขึ้นมาทดแทน
    for scenario, entry_color, rank_base in (
        (chart_indicator.public_scenario(story), COLORS["order_zone_edge"], 1),
    ):
        if not scenario or not entry_zone_visible(story):
            continue
        entry_bottom = min(scenario["entry_low"], scenario["entry_high"])
        entry_top = max(scenario["entry_low"], scenario["entry_high"])
        # Golden Zone กับ Entry คือช่วงเดียวกันในแผนหลัก จึงใช้กล่องเดียวครอบทั้งกราฟ
        # แทนกล่องส้ม+เทาซ้อนกัน และบอกทิศแผนด้วยภาษาไทยในจุดเดียว
        axes.add_patch(Rectangle((-2, entry_bottom), x_right + 2,
                                 entry_top - entry_bottom,
                                 facecolor=COLORS["order_zone_fill"], alpha=0.46,
                                 edgecolor=entry_color, linewidth=1.2, zorder=1))
        zone_label = _entry_zone_label(scenario, money)
        zone_x, zone_alignment = _entry_zone_label_position(story, n, x_right)
        axes.text(zone_x, (entry_bottom + entry_top) / 2,
                  checked_label(zone_label), color=entry_color, fontsize=13.0,
                  fontweight="bold", ha=zone_alignment, va="center", zorder=6,
                  bbox=dict(boxstyle="round,pad=0.38", facecolor="#fff7ed", alpha=0.98,
                            edgecolor=entry_color, linewidth=1.0))
        axes.hlines(scenario["sl"], n - 1, x_right, color=COLORS["sl"], linewidth=1.6,
                    linestyle=(0, (4, 3)), zorder=4)
        tags.append({"y": scenario["sl"],
                     "text": f"ตัดขาดทุน (SL) {money(scenario['sl'])}",
                     "face": COLORS["sl"], "rank": rank_base})
        for order, target in enumerate(scenario["tps"], start=1):
            axes.hlines(target, n - 1, x_right, color=COLORS["tp"], linewidth=1.3,
                        linestyle=(0, (4, 3)), alpha=0.9, zorder=4)
            tags.append({"y": target, "text": _tp_label(order, target, money),
                         "face": "#2e7d32", "rank": rank_base + 1})
    return tags


def render_combined(story: dict, rows: list[dict], output_path: Path) -> dict:
    """ภาพเดียวของสไตล์ E — ราคา+Fibonacci+แผนเทรด / RSI / MACD สามแผงซ้อน"""
    money = money_for(story)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    font_used = _thai_font()
    bars = story["display"]["bars"]
    view = rows[-bars:]
    n = len(view)
    closes = [row["close"] for row in rows]
    fib = story["fib"]
    x_right = n - 1 + n * RIGHT_PAD_FRACTION

    figure, (ax_price, ax_rsi, ax_macd) = plt.subplots(
        3, 1, figsize=FIGURE_SIZE, dpi=DPI, sharex=True,
        gridspec_kw={"height_ratios": [3.6, 1.0, 1.0], "hspace": 0.06})
    figure.patch.set_facecolor(COLORS["bg"])
    for axes in (ax_price, ax_rsi, ax_macd):
        _style_axes(axes)

    # ---- แผงราคา + Fibonacci + แผนเทรด ----
    anchors = [r["low"] for r in view] + [r["high"] for r in view]
    if fib:
        anchors += [level["price"] for level in fib["levels"]]
        anchors.append(fib["extension"])
        for key in ("primary",):
            scenario = story["scenarios"][key]
            # แผนหลักต้องคงโซน/SL/TP บนภาพแม้ยังไกลจากราคาปัจจุบัน เพื่อให้ภาพตรงกับบท
            # โดย _entry_zone_label จะระบุว่าเป็นพื้นที่เฝ้าระวัง ไม่ใช่จุดเข้าทันที
            if scenario and entry_zone_visible(story):
                anchors += [scenario["sl"], *scenario["tps"]]
    low, high = min(anchors), max(anchors)
    pad = (high - low) * 0.06
    ax_price.set_xlim(-2, x_right)
    ax_price.set_ylim(low - pad, high + pad)

    tags = _draw_fib_content(ax_price, story, view, x_right, Rectangle)
    _draw_candles(ax_price, view, Rectangle)
    _plot_line(ax_price, _series_view(chart_indicator.ema(closes, chart_indicator.MACD_FAST),
                                      len(rows), n), COLORS["ema_fast"], linewidth=1.5)
    _plot_line(ax_price, _series_view(chart_indicator.ema(closes, chart_indicator.MACD_SLOW),
                                      len(rows), n), COLORS["ema_slow"], linewidth=1.5)
    _plot_line(ax_price, _series_view(chart_story.sma(closes, 50), len(rows), n),
               COLORS["sma"], linewidth=1.4, linestyle=(0, (5, 3)), alpha=0.85)
    current_at_latest_candle = _draw_current_price(ax_price, story, n, money)
    if not current_at_latest_candle:
        tags.append({"y": story["current"]["close"],
                     "text": money(story["current"]["close"]),
                     "face": "#2962ff", "rank": 0})
    _right_tags(ax_price, tags, x_right, (low - pad, high + pad))

    # ---- แผง RSI ----
    rsi_view = _series_view(chart_indicator.rsi(closes), len(rows), n)
    ax_rsi.set_ylim(0, 100)
    for level, style in ((chart_indicator.RSI_OVERBOUGHT, (0, (5, 3))),
                         (50.0, (0, (2, 3))),
                         (chart_indicator.RSI_OVERSOLD, (0, (5, 3)))):
        ax_rsi.hlines(level, -2, x_right, color=COLORS["rsi_band"], alpha=0.6,
                      linewidth=0.9, linestyle=style, zorder=2)
    ax_rsi.fill_between([-2, x_right], chart_indicator.RSI_OVERSOLD,
                        chart_indicator.RSI_OVERBOUGHT,
                        color=COLORS["rsi"], alpha=0.05, zorder=1)
    _plot_line(ax_rsi, rsi_view, COLORS["rsi"], linewidth=1.7)
    _right_tags(ax_rsi, [{"y": story["rsi"]["value"], "text": f"{story['rsi']['value']:.1f}",
                          "face": "#7e57c2", "rank": 0}], x_right, (0, 100))
    _panel_label(ax_rsi, checked_label(
        f"RSI (14): {story['rsi']['value']:.1f} ({_rsi_status(story['rsi']['value'])})"))

    # ---- แผง MACD ----
    macd_line, macd_signal, macd_hist = chart_indicator.macd(closes)
    line_view = _series_view(macd_line, len(rows), n)
    signal_view = _series_view(macd_signal, len(rows), n)
    hist_view = _series_view(macd_hist, len(rows), n)
    hist_xs = [i for i, v in enumerate(hist_view) if v is not None]
    hist_ys = [v for v in hist_view if v is not None]
    if hist_xs:
        ax_macd.bar(hist_xs, hist_ys, width=0.7, color=COLORS["hist"], alpha=0.75, zorder=2)
    ax_macd.axhline(0, color=COLORS["rsi_band"], linewidth=0.9, alpha=0.6, zorder=2)
    _plot_line(ax_macd, line_view, COLORS["macd"], linewidth=1.5)
    _plot_line(ax_macd, signal_view, COLORS["signal"], linewidth=1.5)
    macd_values = ([v for v in line_view + signal_view + hist_ys if v is not None] or [0.0])
    macd_low, macd_high = min(macd_values), max(macd_values)
    macd_pad = (macd_high - macd_low) * 0.15 or 1.0
    ax_macd.set_ylim(macd_low - macd_pad, macd_high + macd_pad)
    ax_macd.set_xlim(-2, x_right)
    _right_tags(ax_macd, [{"y": story["macd"]["histogram"],
                           "text": f"{story['macd']['histogram']:,.2f}",
                           "face": "#1e53ba", "rank": 0}],
                x_right, (macd_low - macd_pad, macd_high + macd_pad))
    _panel_label(ax_macd, checked_label(
        f"MACD: {story['macd']['histogram']:,.2f} "
        f"({_macd_status(story['macd']['histogram'])})"))

    timeframe = story.get("timeframe", "1day")
    _time_ticks(ax_macd, view, timeframe)

    # ผู้ใช้สั่ง 2026-08-19 ให้ตัดหัวเรื่องและคำบรรยายเหนือภาพออกทั้งหมด แล้วคืนพื้นที่
    # ให้กราฟ และสั่ง 2026-08-25 ให้ถอด footer ใต้ MACD ออกทั้งแถว โดยคงชื่อแผง
    # RSI/MACD และแกนเวลาไว้ตามเดิม
    figure.subplots_adjust(left=0.015, right=0.955, top=0.988, bottom=0.045, hspace=0.06)
    try:
        size_bytes = image_output.save_figure(figure, output_path, facecolor=COLORS["bg"])
    finally:
        plt.close(figure)   # ตกด่านขนาดก็ต้องคืน figure ไม่งั้นรอบถัดไปกินหน่วยความจำสะสม
    return {"path": str(output_path), "bars": n, "font": font_used,
            "bytes": size_bytes, "kb": image_output.kb(size_bytes),
            "background": COLORS["bg"],
            "elements": {"rsi": True, "macd": True, "footer": False,
                         "fib": bool(fib),
                         "primary": bool(chart_indicator.public_scenario(story)),
                         "entry_zone": entry_zone_visible(story),
                         "counter": False,
                         "header": False},
            "layout": {
                "entry_zone_label": "right" if story.get("asset") == "xauusd" else "center",
                "current_price": ("latest_candle" if current_at_latest_candle
                                  else "right_edge"),
            }}
