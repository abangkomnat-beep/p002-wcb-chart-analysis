"""ตัววาดกราฟสไตล์ E — วาดจาก artifact ของ `chart_indicator` เท่านั้น

**ภาพเดียวต่อบท** (ผู้ใช้สั่งรวม 2026-08-07 — สไตล์ E รวม · สไตล์ D ไม่รวม):
สามแผงซ้อนในผืนเดียว ตรงกับหน้าตาต้นแบบของหัวหน้า (TradingView dark · vxcu4F8w):
1. แผงราคา — แท่งเทียน + EMA12/26 + SMA50 + Fibonacci ป้าย "อัตราส่วน (ราคา)"
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

from tools import chart_indicator, chart_story  # noqa: E402
from tools.chart_renderer import THAI_MONTHS  # noqa: E402
from tools.chart_story_renderer import _thai_font, money_for, thai_date  # noqa: E402

FIGURE_SIZE = (19.2, 12.6)       # สามแผงซ้อน — สูงกว่า 16:9 ให้แผงราคาอ่านแท่งออก
DPI = 100
RIGHT_PAD_FRACTION = 0.20        # เผื่อที่ให้กล่องโซนเข้าและป้าย SL/TP

COLORS = {
    "bg": "#131722", "grid": "#1e222d", "axis": "#787b86", "text": "#d1d4dc",
    "up": "#26a69a", "down": "#ef5350",
    "ema_fast": "#ff9800", "ema_slow": "#00bcd4", "sma": "#e0e0e0",
    "rsi": "#b39ddb", "rsi_band": "#787b86",
    "macd": "#2962ff", "signal": "#ff9800", "hist": "#5b9cf6",
    "fib": "#787b86", "fib_anchor": "#ffd54f", "golden": "#ffb74d",
    "extension": "#f23645", "swing": "#9aa0a6",
    "entry": "#26a69a", "sl": "#f23645", "tp": "#4caf50",
}

# สีประจำขั้น Fibonacci — ผู้ใช้ขอ 2026-08-06: แยกสีรายขั้นและให้เข้มขึ้น (เดิมเทาจางหมด)
# โทนตามต้นแบบ TradingView: จุดตั้งต้น/ปลาย swing เหลือง · ขั้นกลางไล่โทนแดง→ส้ม→เขียว→ฟ้า→ม่วง
FIB_LEVEL_COLORS = {
    0.0: "#ffd54f", 0.236: "#f23645", 0.382: "#ff9800", 0.5: "#4caf50",
    0.618: "#26a69a", 0.705: "#00bcd4", 0.786: "#2962ff", 0.886: "#b39ddb",
    1.0: "#ffd54f",
}

_LABEL_BOX = dict(boxstyle="round,pad=0.25", facecolor="#131722", alpha=0.75, edgecolor="none")


def _style_axes(axes) -> None:
    axes.set_facecolor(COLORS["bg"])
    for spine in axes.spines.values():
        spine.set_color("#2a2e39")
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
        axes.text(x_right, entry["label_y"], entry["text"], color="#ffffff", fontsize=11,
                  ha="right", va="center", zorder=7,
                  bbox=dict(boxstyle="round,pad=0.28", facecolor=entry["face"], edgecolor="none"))


def _panel_label(axes, text: str) -> None:
    axes.text(0.005, 0.94, text, transform=axes.transAxes, color=COLORS["text"],
              fontsize=12.5, fontweight="bold", va="top", zorder=8, bbox=_LABEL_BOX)


def _draw_fib_content(axes, story: dict, view: list[dict], x_right: float,
                      Rectangle) -> list[dict]:
    """เส้น Fibonacci + โซนเข้า/SL/TP บนแผงราคา — คืนรายการป้ายฝั่งขวาที่ต้องติด"""
    money = money_for(story)
    fib = story["fib"]
    n = len(view)
    tags: list[dict] = []
    if not fib:
        return tags

    golden_low, golden_high = fib["golden"]
    axes.add_patch(Rectangle((-2, golden_low), x_right + 2, golden_high - golden_low,
                             facecolor=COLORS["golden"], alpha=0.13, edgecolor="none", zorder=1))
    for level in fib["levels"]:
        is_anchor = level["ratio"] in (0.0, 1.0)
        color = FIB_LEVEL_COLORS.get(level["ratio"], COLORS["fib"])
        axes.hlines(level["price"], -2, x_right, color=color,
                    alpha=0.95 if is_anchor else 0.85,
                    linewidth=1.4 if is_anchor else 1.2, zorder=2)
        axes.text(2, level["price"] + story["atr14"] * 0.08,
                  f"{level['ratio']:g} ({money(level['price'])})",
                  color=color, fontsize=11.5, va="bottom", zorder=6, bbox=_LABEL_BOX)
    axes.hlines(fib["extension"], -2, x_right, color=COLORS["extension"],
                alpha=0.95, linewidth=1.3, zorder=2)
    axes.text(2, fib["extension"] + story["atr14"] * 0.08,
              f"{chart_indicator.EXTENSION_RATIO} ({money(fib['extension'])})",
              color=COLORS["extension"], fontsize=11.5, va="bottom", zorder=6, bbox=_LABEL_BOX)
    # ป้ายโซนทองวางกลางภาพ — ชิดซ้ายจะชนคอลัมน์ป้ายอัตราส่วน (เจอตอนตรวจภาพจริง)
    axes.text(int(n * 0.45), (golden_low + golden_high) / 2, "Golden Zone (OTE)",
              color=COLORS["golden"], fontsize=11.5, va="center", ha="center",
              zorder=6, alpha=0.95, bbox=_LABEL_BOX)

    # เส้น swing ที่ใช้วัด — ให้คนอ่านเห็นว่า Fibonacci ผูกกับขาไหน
    def _bar_index(date_text: str) -> int | None:
        for index, row in enumerate(view):
            if row["date"] == date_text:
                return index
        return None

    start_key = "swing_high" if fib["direction"] == "down" else "swing_low"
    end_key = "swing_low" if fib["direction"] == "down" else "swing_high"
    start_x = _bar_index(fib[start_key]["date"])
    end_x = _bar_index(fib[end_key]["date"])
    if start_x is not None and end_x is not None:
        axes.plot([start_x, end_x], [fib[start_key]["price"], fib[end_key]["price"]],
                  color=COLORS["swing"], linewidth=1.2, linestyle=(0, (6, 4)),
                  alpha=0.8, zorder=2)

    primary = story["scenarios"]["primary"]
    if primary:
        # กล่องโซนเข้าเฉพาะช่วง right-pad — ป้ายกำกับชัดว่าเป็นเงื่อนไข ไม่ใช่คำทำนาย
        entry_bottom = min(primary["entry_low"], primary["entry_high"])
        entry_top = max(primary["entry_low"], primary["entry_high"])
        axes.add_patch(Rectangle((n - 1, entry_bottom), x_right - (n - 1),
                                 entry_top - entry_bottom,
                                 facecolor=COLORS["entry"], alpha=0.22,
                                 edgecolor=COLORS["entry"], linewidth=1.0, zorder=4))
        axes.text((n - 1 + x_right) / 2, entry_top + story["atr14"] * 0.35,
                  f"Entry Zone · {primary['name']}", color=COLORS["entry"], fontsize=11.5,
                  ha="center", va="bottom", zorder=6, bbox=_LABEL_BOX)
        axes.hlines(primary["sl"], n - 1, x_right, color=COLORS["sl"], linewidth=1.6,
                    linestyle=(0, (4, 3)), zorder=4)
        tags.append({"y": primary["sl"], "text": f"SL {money(primary['sl'])}",
                     "face": COLORS["sl"], "rank": 1})
        for order, target in enumerate(primary["tps"], start=1):
            axes.hlines(target, n - 1, x_right, color=COLORS["tp"], linewidth=1.3,
                        linestyle=(0, (4, 3)), alpha=0.9, zorder=4)
            tags.append({"y": target, "text": f"TP{order} {money(target)}",
                         "face": "#2e7d32", "rank": 2})
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
        for key in ("primary", "counter"):
            scenario = story["scenarios"][key]
            if scenario:
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
    tags.append({"y": story["current"]["close"], "text": money(story["current"]["close"]),
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
    _panel_label(ax_rsi, "RSI (14)")

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
    _panel_label(ax_macd, "MACD (12, 26, 9)")

    _month_ticks(ax_macd, view)
    ax_macd.text(0.005, 0.06,
                 "Entry/SL/TP เป็นเงื่อนไขสมมุติจากระดับ Fibonacci ที่คำนวณได้ ไม่ใช่คำทำนายทิศทาง "
                 f"· ข้อมูล: WCB series API · {n} แท่ง D1 · สไตล์ E — อ่านอินดิเคเตอร์ (P002)",
                 transform=ax_macd.transAxes, color=COLORS["axis"], fontsize=10,
                 va="bottom", zorder=8, bbox=_LABEL_BOX)

    # หัวภาพอยู่ในแถบเหนือแกน — ป้ายระดับ Fibonacci 1.0 มักชิดขอบบนของแผงราคาพอดี
    # วางหัวในแกนแล้วทับกัน (เจอจริงตอนตรวจภาพ) · tight_layout ไม่รองรับ gridspec นี้
    figure.subplots_adjust(left=0.015, right=0.955, top=0.945, bottom=0.045, hspace=0.06)
    figure.text(0.01, 0.988, f"{story['symbol']} · รายวัน (D1) · EMA 12 / EMA 26 / SMA 50 · "
                             "Fibonacci Retracement + แผนเทรด",
                color=COLORS["text"], fontsize=15, fontweight="bold", va="top")
    mode = "ขาลง" if story["regime"]["down"] else "ขาขึ้น"
    subtitle = (f"ข้อมูลถึง {thai_date(story['current']['date'])} · "
                f"ปิด {money(story['current']['close'])} · โหมด SMA50: {mode}")
    if not fib:
        subtitle += " · รอบนี้ไม่มี swing ที่ผ่านเกณฑ์ จึงไม่วาง Fibonacci"
    figure.text(0.01, 0.962, subtitle, color=COLORS["axis"], fontsize=11.5, va="top")
    figure.savefig(output_path, facecolor=COLORS["bg"])
    plt.close(figure)
    return {"path": str(output_path), "bars": n, "font": font_used,
            "elements": {"rsi": True, "macd": True,
                         "fib": bool(fib),
                         "primary": bool(story["scenarios"]["primary"])}}
