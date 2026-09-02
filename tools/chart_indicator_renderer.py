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

from tools import chart_indicator, chart_story, image_output, visual_theme  # noqa: E402
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

_THEME_COLORS = visual_theme.for_chart()
COLORS = {
    **_THEME_COLORS,
    "bg": _THEME_COLORS["bg"], "grid": _THEME_COLORS["grid"], "axis": _THEME_COLORS["axis"], "text": _THEME_COLORS["text"],
    "up": _THEME_COLORS["buy"], "down": _THEME_COLORS["sell"],
    "ema_fast": _THEME_COLORS["warning"], "ema_slow": _THEME_COLORS["info"], "sma": _THEME_COLORS["neutral"],
    "rsi": _THEME_COLORS["indicator"], "rsi_band": _THEME_COLORS["muted"],
    "macd": _THEME_COLORS["info"], "signal": _THEME_COLORS["warning"], "hist": "#60a5fa",
    "fib": "#4b5563", "fib_anchor": "#a16207", "golden": "#c2410c",
    "order_zone_fill": "#F4EBC9", "order_zone_edge": _THEME_COLORS["warning"],
    "extension": _THEME_COLORS["sell"], "swing": _THEME_COLORS["muted"],
    "entry": _THEME_COLORS["buy"], "sl": _THEME_COLORS["stop_loss"], "tp": _THEME_COLORS["take_profit"],
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

_LABEL_BOX = dict(boxstyle="round,pad=0.28", facecolor=visual_theme.SURFACE["plot"], alpha=0.97,
                  edgecolor=visual_theme.SURFACE["border"], linewidth=0.6)
_FIB_PRICE_LABEL_BOX = dict(boxstyle="round,pad=0.20", facecolor=visual_theme.SURFACE["plot"], alpha=0.97,
                            edgecolor=visual_theme.SURFACE["border"], linewidth=0.6)


def _draw_fib_label(axes, *, y: float, ratio: str, price: str, color: str,
                    artifact_artists: list | None = None) -> tuple[object, object]:
    """คงอัตราส่วนไว้ที่ anchor เดิม และวางราคาแยกชิดขอบขวาของกราฟ."""
    ratio_artist = axes.text(FIB_RATIO_LABEL_X, y, checked_label(ratio),
              color=color, fontsize=12.5, fontweight="bold", va="bottom", zorder=6,
              bbox=_LABEL_BOX)
    price_artist = axes.text(FIB_PRICE_LABEL_X_AXES, y, checked_label(price),
              transform=axes.get_yaxis_transform(), color=color,
              fontsize=11.5, fontweight="bold", ha="right", va="bottom",
              zorder=6, bbox=_FIB_PRICE_LABEL_BOX)
    if artifact_artists is not None:
        artifact_artists.extend([("fib_ratio", ratio_artist), ("fib_price", price_artist)])
    return ratio_artist, price_artist


def _style_axes(axes) -> None:
    axes.set_facecolor(COLORS["bg"])
    for spine in axes.spines.values():
        spine.set_color(COLORS["border"])
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


def _right_tags(axes, entries: list[dict], x_right: float, y_range: tuple[float, float]) -> dict:
    """วาด annotation rail นอกช่วงแท่ง พร้อม leader line และคืนหลักฐาน bbox.

    ``x_right`` คือขอบรางด้านขวา (หลังแท่งล่าสุด) ไม่ใช่ตำแหน่งในแท่งเทียน
    จึงไม่มีป้ายข้อความยาวนั่งทับข้อมูลราคาอีกต่อไป.  การจัด y เป็น deterministic
    จาก rank และค่าเงินจริง ส่วนการตรวจ bbox ทำหลัง Matplotlib วาดจริง.
    """
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
    artists = []
    for entry in placed:
        artist = axes.annotate(
            checked_label(entry["text"]),
            xy=(0.985, entry["y"]), xycoords=("axes fraction", "data"),
            xytext=(x_right, entry["label_y"]), textcoords=("data", "data"),
            color="#ffffff", fontsize=12.5, fontweight="bold",
            ha="right", va="center", zorder=7, clip_on=True,
            arrowprops={"arrowstyle": "-", "color": entry["face"],
                        "linewidth": 0.7, "shrinkA": 0, "shrinkB": 0},
            bbox=dict(boxstyle="round,pad=0.28", facecolor=entry["face"], edgecolor="none"))
        artists.append(artist)
    # The value-space gap above is only a first pass.  Resolve the actual
    # painted boxes as font metrics differ between local Thai font installs.
    # This keeps output deterministic for a given renderer/font and fail-closed
    # metadata can prove that no rail labels overlap.
    _resolve_rail_collisions(axes, artists)
    return {"placed": placed, "artists": artists,
            "roles": [str(item.get("role") or item["text"]) for item in placed]}


def _resolve_rail_collisions(axes, artists: list[object], *, edge_px: float = 8.0) -> None:
    """Separate painted annotation boxes in display space, bounded by axes."""
    if len(artists) < 2:
        return
    figure = axes.figure
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    for _ in range(max(4, len(artists) * 3)):
        boxes = [_painted_bbox(artist, renderer) for artist in artists]
        collision = False
        for index, left in enumerate(boxes):
            for right_index in range(index + 1, len(boxes)):
                right = boxes[right_index]
                overlap = min(left.y1, right.y1) - max(left.y0, right.y0)
                x_overlap = min(left.x1, right.x1) - max(left.x0, right.x0)
                if overlap <= 0 or x_overlap <= 0:
                    continue
                collision = True
                # Prefer moving the later item down; if that would leave the
                # rail, move the earlier item up.  Both are in data coordinates.
                current_x, current_y = artists[right_index].get_position()
                _, y0 = axes.transData.transform((0, 0))
                _, y1 = axes.transData.transform((0, 1))
                pixels_per_data = max(abs(y1 - y0), 1e-6)
                next_y = current_y - (overlap + 3.0) / pixels_per_data
                ymin, ymax = axes.get_ylim()
                if next_y > ymin:
                    artists[right_index].set_position((current_x, next_y))
                else:
                    current_x, current_y = artists[index].get_position()
                    artists[index].set_position((current_x, current_y + (overlap + 3.0) / pixels_per_data))
                break
            if collision:
                break
        if not collision:
            break
        figure.canvas.draw()


def _summary_strip_text(story: dict, money) -> str | None:
    """คืนข้อความสรุปของโซนสำหรับแถบเหนือ plot (ไม่วาดทับแท่ง)."""
    scenario = chart_indicator.public_scenario(story)
    if not scenario:
        return None
    low = min(scenario["entry_low"], scenario["entry_high"])
    high = max(scenario["entry_low"], scenario["entry_high"])
    state = "โฟกัสวันนี้" if scenario.get("daily_entry", True) else "พื้นที่เฝ้าระวัง"
    return (f"{state} · โซนรอ {str(scenario['side']).upper()} · "
            f"Entry {money(low)}–{money(high)} · "
            f"SL {money(scenario['sl'])} · "
            f"TP {', '.join(money(value) for value in scenario['tps'])}")


def _bbox_record(artists: list[tuple[str, object]], figure) -> list[dict]:
    """Serialize visible artist bboxes for QA metadata without market values."""
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    records = []
    for role, artist in artists:
        bbox = _painted_bbox(artist, renderer)
        records.append({"role": role, "x0": round(float(bbox.x0), 2),
                        "y0": round(float(bbox.y0), 2), "x1": round(float(bbox.x1), 2),
                        "y1": round(float(bbox.y1), 2)})
    return records


def _painted_bbox(artist, renderer):
    """Return the painted label box, excluding its intentional leader line."""
    patch = getattr(artist, "get_bbox_patch", lambda: None)()
    return patch.get_window_extent(renderer=renderer) if patch is not None else artist.get_window_extent(renderer=renderer)


def _layout_guard(figure, artists: list[tuple[str, object]], *, edge_px: float = 10.0) -> None:
    """Fail closed on clipped or overlapping summary/rail labels."""
    if not artists:
        return
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    figure_bbox = figure.bbox
    boxes = []
    for role, artist in artists:
        bbox = _painted_bbox(artist, renderer)
        if (bbox.x0 < figure_bbox.x0 + edge_px or bbox.y0 < figure_bbox.y0 + edge_px
                or bbox.x1 > figure_bbox.x1 - edge_px or bbox.y1 > figure_bbox.y1 - edge_px):
            raise RuntimeError(f"Style E layout guard: {role} อยู่นอก figure")
        boxes.append((role, bbox))
    for index, (left_role, left_box) in enumerate(boxes):
        for right_role, right_box in boxes[index + 1:]:
            if (min(left_box.x1, right_box.x1) > max(left_box.x0, right_box.x0)
                    and min(left_box.y1, right_box.y1) > max(left_box.y0, right_box.y0)):
                raise RuntimeError(f"Style E layout guard: {left_role} ชน {right_role}")


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
    axes.scatter([bar_count - 1], [current], s=30, color=COLORS["info"],
                 edgecolor=COLORS["bg"], linewidth=0.8, zorder=8)
    axes.annotate(checked_label(f"ราคาปัจจุบัน {money(current)}"),
                  xy=(bar_count - 1, current), xytext=label_offset,
                  textcoords="offset points",
                  color=COLORS["text"], fontsize=12, fontweight="bold",
                  ha=label_alignment, va="center", zorder=9,
                  bbox=dict(boxstyle="round,pad=0.30", facecolor="#F4EBC9",
                            edgecolor=COLORS["text"], linewidth=0.8, alpha=0.98))
    return True


def _draw_fib_content(axes, story: dict, view: list[dict], x_right: float,
                      Rectangle, *, artifact_artists: list | None = None) -> list[dict]:
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
        axes.hlines(scenario["sl"], n - 1, x_right, color=COLORS["sl"],
                    linewidth=1.6, linestyle=(0, (4, 3)), zorder=4)
        tags.append({"role": "stop_loss", "y": scenario["sl"], "text": f"ตัดขาดทุน (SL) {money(scenario['sl'])}",
                     "face": COLORS["sl"], "rank": 1})
        for order, target in enumerate(scenario["tps"], start=1):
            axes.hlines(target, n - 1, x_right, color=COLORS["tp"], linewidth=1.3,
                        linestyle=(0, (4, 3)), alpha=0.9, zorder=4)
            tags.append({"role": f"take_profit_{order}", "y": target, "text": _tp_label(order, target, money),
                         "face": COLORS["tp"], "rank": order + 1})
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
            ratio=f"{level['ratio']:g}", price=money(level["price"]), color=color,
            artifact_artists=artifact_artists)
    axes.hlines(fib["extension"], -2, x_right, color=COLORS["extension"],
                alpha=0.95, linewidth=1.3, zorder=2)
    _draw_fib_label(
        axes, y=fib["extension"] + story["atr14"] * 0.08,
        ratio=f"{chart_indicator.EXTENSION_RATIO:g}",
        price=money(fib["extension"]), color=COLORS["extension"],
        artifact_artists=artifact_artists)
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
        axes.hlines(scenario["sl"], n - 1, x_right, color=COLORS["sl"], linewidth=1.6,
                    linestyle=(0, (4, 3)), zorder=4)
        tags.append({"role": "stop_loss", "y": scenario["sl"],
                     "text": f"ตัดขาดทุน (SL) {money(scenario['sl'])}",
                     "face": COLORS["sl"], "rank": rank_base})
        for order, target in enumerate(scenario["tps"], start=1):
            axes.hlines(target, n - 1, x_right, color=COLORS["tp"], linewidth=1.3,
                        linestyle=(0, (4, 3)), alpha=0.9, zorder=4)
            tags.append({"role": f"take_profit_{order}", "y": target, "text": _tp_label(order, target, money),
                         "face": COLORS["tp"], "rank": rank_base + 1})
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
    # Reserve a second, explicit rail after the price-data area.  The extra
    # breathing room keeps Fibonacci price tags at the plot edge from touching
    # execution labels, even when several levels share nearly the same price.
    x_limit_right = x_right + n * 0.20

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
    ax_price.set_xlim(-2, x_limit_right)
    ax_price.set_ylim(low - pad, high + pad)

    fib_artists = []
    tags = _draw_fib_content(ax_price, story, view, x_right, Rectangle,
                             artifact_artists=fib_artists)
    _draw_candles(ax_price, view, Rectangle)
    _plot_line(ax_price, _series_view(chart_indicator.ema(closes, chart_indicator.MACD_FAST),
                                      len(rows), n), COLORS["ema_fast"], linewidth=1.5)
    _plot_line(ax_price, _series_view(chart_indicator.ema(closes, chart_indicator.MACD_SLOW),
                                      len(rows), n), COLORS["ema_slow"], linewidth=1.5)
    _plot_line(ax_price, _series_view(chart_story.sma(closes, 50), len(rows), n),
               COLORS["sma"], linewidth=1.4, linestyle=(0, (5, 3)), alpha=0.85)
    # Keep the marker at the factual latest candle, but put its text in the
    # same dedicated rail as SL/TP so a near-entry price cannot cover candles.
    current_at_latest_candle = story.get("asset") == "xauusd"
    if current_at_latest_candle:
        ax_price.scatter([n - 1], [story["current"]["close"]], s=30,
                         color=visual_theme.SEMANTIC["info"], edgecolor="#ffffff",
                         linewidth=0.8, zorder=8)
    tags.insert(0, {"role": "current_price", "y": story["current"]["close"],
                    "text": f"ราคาปัจจุบัน {money(story['current']['close'])}",
                    "face": visual_theme.SEMANTIC["info"], "rank": 0})
    price_rail = _right_tags(ax_price, tags, x_right, (low - pad, high + pad))
    summary_text = _summary_strip_text(story, money)
    summary_artist = None
    if summary_text:
        summary_artist = figure.text(
            0.018, 0.985, checked_label(summary_text),
            ha="left", va="top", fontsize=11.5, fontweight="bold",
            color=COLORS["text"], clip_on=False,
            bbox={"boxstyle": "round,pad=0.38", "facecolor": "#F4EBC9",
                  "edgecolor": visual_theme.BRAND["gold"], "linewidth": 0.9}, zorder=9)

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
    rsi_rail = _right_tags(ax_rsi, [{"role": "rsi", "y": story["rsi"]["value"], "text": f"{story['rsi']['value']:.1f}",
                          "face": COLORS["indicator"], "rank": 0}], x_right, (0, 100))
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
    ax_macd.set_xlim(-2, x_limit_right)
    macd_rail = _right_tags(ax_macd, [{"role": "macd", "y": story["macd"]["histogram"],
                           "text": f"{story['macd']['histogram']:,.2f}",
                           "face": visual_theme.SEMANTIC["info"], "rank": 0}],
                x_right, (macd_low - macd_pad, macd_high + macd_pad))
    _panel_label(ax_macd, checked_label(
        f"MACD: {story['macd']['histogram']:,.2f} "
        f"({_macd_status(story['macd']['histogram'])})"))

    timeframe = story.get("timeframe", "1day")
    _time_ticks(ax_macd, view, timeframe)

    # ผู้ใช้สั่ง 2026-08-19 ให้ตัดหัวเรื่องและคำบรรยายเหนือภาพออกทั้งหมด แล้วคืนพื้นที่
    # ให้กราฟ และสั่ง 2026-08-25 ให้ถอด footer ใต้ MACD ออกทั้งแถว โดยคงชื่อแผง
    # RSI/MACD และแกนเวลาไว้ตามเดิม
    figure.subplots_adjust(left=0.015, right=0.955, top=0.955, bottom=0.045, hspace=0.06)
    required_artists = []
    if summary_artist is not None:
        required_artists.append(("entry_zone_summary", summary_artist))
    required_artists += [(f"{role}-{index}", artist)
                         for index, (role, artist) in enumerate(fib_artists)]
    required_artists += [(f"price-{role}", artist)
                         for role, artist in zip(price_rail["roles"], price_rail["artists"])]
    required_artists += [(f"rsi-{role}", artist)
                         for role, artist in zip(rsi_rail["roles"], rsi_rail["artists"])]
    required_artists += [(f"macd-{role}", artist)
                         for role, artist in zip(macd_rail["roles"], macd_rail["artists"])]
    _layout_guard(figure, required_artists)
    bbox_records = _bbox_record(required_artists, figure)
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
                "summary_strip": bool(summary_artist),
                "annotation_rail": "right_outside_candle_area",
                "leader_lines": True,
                "bbox_assertions": {"checked": True, "overlap_count": 0,
                                    "roles": [item["role"] for item in bbox_records]},
            },
            "metadata": {
                "schema": "style-e-renderer-v4",
                "theme": {"schema": visual_theme.SCHEMA, "version": visual_theme.VERSION},
                "layout": {"summary_strip": "above_price_plot",
                           "annotation_rail": "right_outside_candle_area",
                           "bbox_assertions": {"checked": True, "overlap_count": 0,
                                               "boxes": bbox_records}},
            }}
