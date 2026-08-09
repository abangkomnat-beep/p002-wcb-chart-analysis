"""กราฟรายวันรุ่นใหม่ — แสดงเฉพาะสิ่งที่ข้อมูลรองรับ และบอกผู้อ่านตรง ๆ ว่าอะไรที่ไม่แสดง

ต่างจากตัวเดิมที่วาดด้วย PIL ทีละเส้น:
- แสดง 90 แท่งตามมาตรฐาน พร้อมช่องว่างขวา 12%
- indicator ที่ข้อมูลไม่พอจะไม่ถูกพล็อต และมีข้อความบอกเหตุผล
- แท่งที่กำลังก่อตัวต่างจากแท่งปิดด้วยลายและกรอบประ ไม่ใช่แค่สี (เรื่อง accessibility)
- ระดับที่ชิดกันแสดงเป็นโซน · ป้ายชื่อไม่ทับกันและจำกัดจำนวนตามลำดับความสำคัญ
- คำบรรยายใต้หัวเรื่องเป็นเวลาไทยที่คนอ่านเข้าใจ ไม่ใช่ ISO timestamp
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from tools import image_output


BANGKOK = timezone(timedelta(hours=7))
THAI_MONTHS = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
               "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")

DISPLAY_BARS = 90
RIGHT_PADDING_PERCENT = 12
MAX_VISIBLE_LABELS = 5

# ลำดับความสำคัญของป้าย ตาม §17
ROLE_PRIORITY = {"current_price": 0, "trigger": 1, "invalidation": 2, "target": 3}
TYPE_PRIORITY = {"previous_day": 4, "moving_average": 5, "swing": 6, "zone": 6,
                 "previous_week": 7, "pivot": 8, "atr_projection": 9}

COLORS = {
    "background": "#0f172a", "panel": "#111827", "grid": "#334155",
    "muted": "#94a3b8", "foreground": "#f8fafc",
    "up": "#38bdf8", "down": "#fb7185",
    "support": "#34d399", "resistance": "#f87171", "bias_divider": "#60a5fa",
    "ma": ("#fbbf24", "#a78bfa", "#f472b6"),
}

# key ใน metadata ที่ใช้ในหน่วยความจำ/ฝั่ง internal เท่านั้น — ห้ามเขียนลงไฟล์สาธารณะ
# (article_builder ใช้ชุดนี้กรองก่อนใส่ visuals ใน public/article.json)
PRIVATE_METADATA_KEYS = frozenset({
    "metadata_path", "absolute_path",
    "plotted_indicator_codes", "hidden_indicator_codes",
})

_MA_CODE = re.compile(r"(?:sma|ema)\s*_?(\d+)", re.IGNORECASE)


def indicator_public_name(code: str) -> str:
    """ชื่อเครื่องมือแบบที่ผู้อ่านเห็น — sma20 → 'เส้นค่าเฉลี่ย 20 วัน' (denylist #15)

    RSI เป็นคำที่ spec อนุญาต · โค้ดที่ไม่รู้จักคงชื่อเดิมไว้ให้เทส hygiene จับเอง
    """
    match = _MA_CODE.fullmatch(code.strip())
    if match:
        return f"เส้นค่าเฉลี่ย {match.group(1)} วัน"
    if code.lower().startswith("rsi"):
        return "RSI"
    return code


def thai_datetime_text(moment: str | datetime) -> str:
    """แปลงเวลาเป็นข้อความไทยที่คนอ่านเข้าใจ เช่น '3 ส.ค. 2026 13:33 น. เวลาไทย'"""
    if isinstance(moment, str):
        text = moment.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return moment
    else:
        parsed = moment
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    local = parsed.astimezone(BANGKOK)
    return (f"{local.day} {THAI_MONTHS[local.month - 1]} {local.year} "
            f"{local.hour:02d}:{local.minute:02d} น. เวลาไทย")


def _configure_thai_font():
    from matplotlib import font_manager, rcParams

    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ("Tahoma", "Leelawadee UI", "Leelawadee", "Angsana New", "Segoe UI"):
        if candidate in available:
            rcParams["font.family"] = candidate
            return candidate
    return rcParams["font.family"]


def _label_priority(level: dict) -> int:
    return ROLE_PRIORITY.get(level.get("role"), TYPE_PRIORITY.get(level.get("type"), 10))


def place_labels(entries: list[dict], *, minimum_gap: float) -> list[dict]:
    """เลื่อนป้ายในแนวตั้งไม่ให้ทับกัน โดยให้ป้ายสำคัญกว่าอยู่ตำแหน่งจริง

    entries: [{"y": float, "priority": int, ...}] — คืนรายการเดิมพร้อม key "label_y"
    """
    ordered = sorted(entries, key=lambda item: (item["priority"], -item["y"]))
    placed: list[dict] = []
    for entry in ordered:
        target = entry["y"]
        for _ in range(200):
            conflict = next((item for item in placed if abs(item["label_y"] - target) < minimum_gap), None)
            if conflict is None:
                break
            target = (conflict["label_y"] + minimum_gap if target >= conflict["label_y"]
                      else conflict["label_y"] - minimum_gap)
        entry["label_y"] = target
        placed.append(entry)
    return sorted(placed, key=lambda item: entries.index(item))


def render_daily_chart(
    *,
    candles: list[dict],
    output_path: Path,
    symbol: str,
    cutoff_at: str,
    levels: list[dict] | None = None,
    indicator_series: dict | None = None,
    hidden_indicators: list[dict] | None = None,
    decimals: int = 2,
    display_bars: int = DISPLAY_BARS,
    timeframe_label: str = "Daily",
    figure_size: tuple[float, float] = (14.4, 10.8),
    dpi: int = 100,
    price_text: Callable[[float], str] | None = None,
) -> dict:
    """วาดกราฟรายวันและคืน metadata ที่ใช้อ้างอิงในบทความ

    price_text: ตัวแปลงราคาเป็นข้อความ — สายท่อจริงส่ง voice_rules.format_price เข้ามา
    เพื่อให้เลขบนภาพปัดกติกาเดียวกับบทความ (forex 4 ตำแหน่ง / BTC หลักร้อย+comma)
    ไม่ส่ง = ใช้ทศนิยมตาม decimals แบบเดิม
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter

    def fmt(value: float) -> str:
        return price_text(value) if price_text else f"{value:,.{decimals}f}"

    font_used = _configure_thai_font()
    visible = candles[-display_bars:]
    if not visible:
        raise ValueError("ไม่มีแท่งเทียนให้วาด")

    levels = levels or []
    indicator_series = indicator_series or {}
    hidden_indicators = hidden_indicators or []

    figure, axes = plt.subplots(figsize=figure_size, dpi=dpi)
    figure.patch.set_facecolor(COLORS["background"])
    axes.set_facecolor(COLORS["panel"])
    for spine in axes.spines.values():
        spine.set_color(COLORS["grid"])
    axes.tick_params(colors=COLORS["muted"], labelsize=11)
    axes.grid(True, color=COLORS["grid"], linewidth=0.6, alpha=0.5)
    axes.yaxis.tick_right()
    axes.yaxis.set_label_position("right")

    forming_count = 0
    for index, candle in enumerate(visible):
        open_value, close_value = float(candle["open"]), float(candle["close"])
        high_value, low_value = float(candle["high"]), float(candle["low"])
        rising = close_value >= open_value
        color = COLORS["up"] if rising else COLORS["down"]
        forming = candle.get("candle_state") == "forming"
        if forming:
            forming_count += 1

        axes.plot([index, index], [low_value, high_value], color=color,
                  linewidth=1.4, alpha=0.6 if forming else 1.0,
                  linestyle="--" if forming else "-", zorder=2)
        height = abs(close_value - open_value) or (high_value - low_value) * 0.02 or 1e-9
        axes.add_patch(Rectangle(
            (index - 0.32, min(open_value, close_value)), 0.64, height,
            facecolor="none" if forming else color,
            edgecolor=color, linewidth=1.6 if forming else 0.8,
            linestyle="--" if forming else "-",
            hatch="///" if forming else None,
            alpha=0.9, zorder=3,
        ))
        if forming:
            axes.plot([index], [high_value], marker="v", color=COLORS["foreground"],
                      markersize=9, zorder=5)

    for order, (name, series) in enumerate(sorted(indicator_series.items())):
        values = series[-display_bars:]
        points = [(index, value) for index, value in enumerate(values) if value is not None]
        if len(points) < 2:
            continue
        axes.plot([item[0] for item in points], [item[1] for item in points],
                  color=COLORS["ma"][order % len(COLORS["ma"])], linewidth=2.0,
                  label=indicator_public_name(name), zorder=4)

    limit = len(visible) - 1 + max(len(visible) * RIGHT_PADDING_PERCENT / 100.0, 3)
    axes.set_xlim(-1, limit)

    prices = [float(candle[key]) for candle in visible for key in ("high", "low")]
    low_bound, high_bound = min(prices), max(prices)
    for level in levels:
        for value in (level.get("value"), level.get("zone_low"), level.get("zone_high")):
            if value is not None:
                low_bound, high_bound = min(low_bound, float(value)), max(high_bound, float(value))
    padding = (high_bound - low_bound) * 0.08 or abs(high_bound) * 0.01
    axes.set_ylim(low_bound - padding, high_bound + padding)
    if price_text:
        # แกนราคาใช้กติกาปัดเดียวกับบทความ — เลขทุกตัวบนภาพมาตรฐานเดียว
        axes.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: price_text(value)))

    # เตรียมรายการป้ายก่อน แล้วค่อยวาด เพื่อให้รู้ว่าระดับไหนจะได้ป้าย
    # ระดับที่ไม่ได้ป้ายให้วาดจาง ๆ จะได้อ่านออกว่าเป็นข้อมูลรอง ไม่ใช่เส้นลอยไร้ที่มา
    label_entries = []
    for index, level in enumerate(levels):
        if not level.get("approved_for_publication"):
            continue
        color = COLORS.get(level.get("role"), COLORS["muted"])
        if level.get("zone_low") is not None:
            anchor = (float(level["zone_low"]) + float(level["zone_high"])) / 2
            low_text, high_text = fmt(float(level["zone_low"])), fmt(float(level["zone_high"]))
            # ขอบโซนที่ปัดแล้วกลายเป็นข้อความเดียวกัน แสดงค่าเดียวพอ ไม่เขียน "X-X"
            range_text = low_text if low_text == high_text else f"{low_text}-{high_text}"
            text = f"{level['label']} {range_text}"
        else:
            anchor = float(level["value"])
            text = f"{level['label']} {fmt(anchor)}"
        label_entries.append({"y": anchor, "priority": _label_priority(level),
                              "text": text, "color": color, "level": level, "order": index})

    last_close = float(visible[-1]["close"])
    label_entries.append({"y": last_close, "priority": 0, "color": COLORS["foreground"],
                          "text": f"ล่าสุด {fmt(last_close)}", "level": None, "order": -1})

    shown = sorted(label_entries, key=lambda item: item["priority"])[:MAX_VISIBLE_LABELS]
    labelled_orders = {entry["order"] for entry in shown}

    for entry in label_entries:
        level = entry["level"]
        if level is None:
            continue
        prominent = entry["order"] in labelled_orders
        if level.get("zone_low") is not None:
            axes.axhspan(float(level["zone_low"]), float(level["zone_high"]),
                         color=entry["color"], alpha=0.16 if prominent else 0.06, zorder=1)
        else:
            axes.axhline(entry["y"], color=entry["color"], zorder=1,
                         linewidth=1.3 if prominent else 0.9,
                         linestyle=(0, (6, 4)), alpha=1.0 if prominent else 0.35)

    axes.plot([len(visible) - 1], [last_close], marker="o", color=COLORS["foreground"],
              markersize=8, zorder=6)
    span = axes.get_ylim()[1] - axes.get_ylim()[0]
    for entry in place_labels(shown, minimum_gap=span * 0.045):
        axes.annotate(
            entry["text"], xy=(limit, entry["label_y"]), xytext=(-6, 0),
            textcoords="offset points", ha="right", va="center",
            color=entry["color"], fontsize=12, fontweight="bold", zorder=7,
            bbox={"facecolor": COLORS["panel"], "edgecolor": entry["color"],
                  "boxstyle": "round,pad=0.35", "alpha": 0.95},
        )

    step = max(1, len(visible) // 8)
    ticks = list(range(0, len(visible), step))
    axes.set_xticks(ticks)
    axes.set_xticklabels([_short_date(visible[index]["session_date"]) for index in ticks])

    # "กำลังก่อตัว" เป็นคำ denylist #11 — บนภาพใช้ภาษาคน "ยังไม่ปิด" แทน
    candle_state_text = "แท่งล่าสุดยังไม่ปิด" if forming_count else "แท่งล่าสุดปิดแล้ว"
    subtitle = f"ข้อมูล ณ {thai_datetime_text(cutoff_at)} | กรอบ {timeframe_label} | {candle_state_text}"
    if hidden_indicators:
        names = ", ".join(indicator_public_name(item["indicator"]) for item in hidden_indicators)
        subtitle += f" | {names} ไม่แสดงเพราะข้อมูลย้อนหลังไม่พอ"

    # "แผนที่" แปลว่า map — ผิดความหมาย หัวภาพคือกราฟเทคนิค
    axes.set_title(f"{symbol} | กราฟเทคนิครายวัน", color=COLORS["foreground"],
                   fontsize=22, fontweight="bold", loc="left", pad=34)
    axes.text(0, 1.015, subtitle, transform=axes.transAxes, color=COLORS["muted"], fontsize=12)

    if indicator_series:
        legend = axes.legend(loc="upper left", facecolor=COLORS["panel"],
                             edgecolor=COLORS["grid"], labelcolor=COLORS["foreground"], fontsize=11)
        legend.get_frame().set_alpha(0.9)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    try:
        image_bytes = image_output.save_figure(
            figure, output_path, facecolor=figure.get_facecolor())
    finally:
        plt.close(figure)   # ตกด่านขนาดก็ต้องคืน figure ไม่งั้นรอบถัดไปกินหน่วยความจำสะสม

    approved_labels = [entry["text"] for entry in shown]
    level_labels = [entry["text"] for entry in shown if entry["level"] is not None]
    alt_text = (
        f"กราฟแท่งเทียนรายวันของ {symbol} จำนวน {len(visible)} แท่ง ราคาล่าสุดที่ "
        f"{fmt(last_close)} {candle_state_text}"
    )
    if level_labels:
        alt_text += f" พร้อมระดับสำคัญ {', '.join(level_labels[:3])}"

    plotted_codes = sorted(indicator_series)
    average_line_days = [int(match.group(1)) for code in plotted_codes
                         if (match := _MA_CODE.fullmatch(code))]
    metadata = {
        # เก็บเฉพาะชื่อไฟล์ เพราะ metadata ชุดนี้ไปอยู่ในโฟลเดอร์สาธารณะ
        # พาธเต็มในเครื่องถือเป็นข้อมูลภายในและห้ามหลุดออกไป
        "static_path": output_path.name,
        "external_interactive_url": None,
        "public_caption": subtitle,
        "alt_text": alt_text,
        "timestamp": cutoff_at,
        "timestamp_public": thai_datetime_text(cutoff_at),
        "timeframe": timeframe_label,
        "candle_state": "forming" if forming_count else "closed",
        "displayed_bars": len(visible),
        "font": font_used,
        # ฝั่ง public เห็นเฉพาะชื่อภาษาคน — โค้ดเทคนิค (sma20 ฯลฯ) อยู่ key ภายในด้านล่าง
        "plotted_indicators": [indicator_public_name(code) for code in plotted_codes],
        "average_line_days": average_line_days,
        "hidden_indicators": [
            {**item, "indicator": indicator_public_name(item["indicator"])}
            for item in hidden_indicators
        ],
        "labels_shown": approved_labels,
        "levels_used": [level["id"] for level in levels if level.get("approved_for_publication")],
    }
    metadata_path = output_path.with_suffix(".chart.json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    # key ใน PRIVATE_METADATA_KEYS ใช้ในหน่วยความจำ/ฝั่ง internal เท่านั้น
    # ไม่ถูกเขียนลงไฟล์สาธารณะ และ article_builder จะกรองออกก่อนใส่ visuals
    metadata["plotted_indicator_codes"] = plotted_codes
    metadata["hidden_indicator_codes"] = hidden_indicators
    metadata["metadata_path"] = str(metadata_path)
    metadata["absolute_path"] = str(output_path)
    metadata["image_bytes"] = image_bytes   # ผ่านด่าน `image_output` มาแล้ว — เก็บไว้ให้รายงานรอบ
    return metadata


def _short_date(session_date: str) -> str:
    day = date.fromisoformat(session_date)
    return f"{day.day} {THAI_MONTHS[day.month - 1]}"


def rolling_mean_series(candles: list[dict], period: int) -> list[float | None]:
    """ค่าเฉลี่ยเคลื่อนที่แบบพล็อตได้ — ช่วงที่แท่งไม่พอจะเป็น None ไม่ใช่เส้นแบน"""
    closes = [float(candle["close"]) for candle in candles]
    series: list[float | None] = []
    for index in range(len(closes)):
        if index + 1 < period:
            series.append(None)
        else:
            window = closes[index + 1 - period:index + 1]
            series.append(sum(window) / period)
    return series
