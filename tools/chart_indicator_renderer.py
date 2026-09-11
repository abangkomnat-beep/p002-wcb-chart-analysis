"""ตัววาดกราฟสไตล์ E — วาดจาก artifact ของ `chart_indicator` เท่านั้น

สองภาพต่อบท: Fibonacci 120 แท่งแบบ price-only และแผนเทรด 50 แท่ง
พร้อม RSI/MACD. ภาพแรกยึด swing canonical ด้วยเส้นทองและวงกลม exact anchor;
ภาพหลังยึด Entry/Current/SL/TP ที่ราคา exact และไม่มี diagonal leader.

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

ENGLISH_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

FOREIGN_LABELS = {
    "es-419": {"plan": "Plan", "entry": "Entrada", "current": "Actual", "sellers": "Predominio vendedor", "buyers": "Predominio comprador", "balanced": "Compra y venta equilibradas", "rebound": "Rebote de corto plazo", "selling": "Presión vendedora de corto plazo", "steady": "Momentum de corto plazo estable", "high": "Máximo", "low": "Mínimo", "time": "Hora", "price": "Precio"},
    "ru-RU": {"plan": "План", "entry": "Вход", "current": "Текущая", "sellers": "Преобладают продавцы", "buyers": "Преобладают покупатели", "balanced": "Покупатели и продавцы сбалансированы", "rebound": "Краткосрочный отскок", "selling": "Краткосрочное давление продавцов", "steady": "Краткосрочный импульс стабилен", "high": "Максимум", "low": "Минимум", "time": "Время", "price": "Цена"},
    "ms-MY": {"plan": "Pelan", "entry": "Kemasukan", "current": "Semasa", "sellers": "Penjual menguasai", "buyers": "Pembeli menguasai", "balanced": "Beli dan jual seimbang", "rebound": "Lantunan jangka pendek", "selling": "Tekanan jualan jangka pendek", "steady": "Momentum jangka pendek stabil", "high": "Tinggi", "low": "Rendah", "time": "Masa", "price": "Harga"},
    "pt-BR": {"plan": "Plano", "entry": "Entrada", "current": "Atual", "sellers": "Vendedores dominam", "buyers": "Compradores dominam", "balanced": "Compra e venda equilibradas", "rebound": "Repique de curto prazo", "selling": "Pressão vendedora de curto prazo", "steady": "Momentum de curto prazo estável", "high": "Máxima", "low": "Mínima", "time": "Hora", "price": "Preço"},
}
FOREIGN_MONTHS = {
    "es-419": ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"),
    "ru-RU": ("янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"),
    "ms-MY": ("Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ogos", "Sep", "Okt", "Nov", "Dis"),
    "pt-BR": ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"),
}
ENGLISH_LOCALES = frozenset({"en-ZA", "en-NG", "en-SG"})


def _validate_display_locale(locale, source_timezone=None):
    if locale not in {"th-TH", *ENGLISH_LOCALES, "ms-MY", "pt-BR", "es-419", "ru-RU"}:
        raise ValueError("unsupported Style E display locale")
    if locale != "th-TH" and source_timezone != "+07:00":
        raise ValueError("foreign display requires verified source timezone +07:00")

FIGURE_SIZE = (19.2, 12.6)       # ภาพแผนเทรดสามแผง
FIB_FIGURE_SIZE = (19.2, 10.8)   # ภาพ Fibonacci ราคาอย่างเดียว
DPI = 100
RIGHT_PAD_FRACTION = 0.20        # พื้นที่ป้าย Current/SL/TP หลังแท่งล่าสุด
FIB_BARS = 120
TRADE_PLAN_BARS = 50
# บทความยังเก็บ Fibonacci ครบชุดเพื่ออธิบายที่มาของแผน แต่ภาพแสดงเฉพาะ
# ระดับที่มีหน้าที่ต่อการตัดสินใจ ไม่วาด 0.382/0.5 ทับแท่งเทียนอีก
VISIBLE_FIB_RATIOS = frozenset({0.236, 0.618, 0.786})
FIB_RATIO_LABEL_X = 2
FIB_PRICE_LABEL_X_AXES = 0.995

_THEME_COLORS = visual_theme.for_chart()
PREMIUM_COLORS = visual_theme.for_premium_chart()
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
    """วางอัตราส่วนซ้ายและราคาขวาบน y เดียวกับเส้น Fibonacci."""
    ratio_artist = axes.text(FIB_RATIO_LABEL_X, y, checked_label(ratio),
              color=color, fontsize=12.5, fontweight="bold", va="center", zorder=6,
              bbox=_LABEL_BOX)
    price_artist = axes.text(FIB_PRICE_LABEL_X_AXES, y, checked_label(price),
              transform=axes.get_yaxis_transform(), color=color,
              fontsize=11.5, fontweight="bold", ha="right", va="center",
              zorder=6, bbox=_FIB_PRICE_LABEL_BOX)
    ratio_artist.set_gid(f"premium-label:fib-ratio:{ratio}")
    price_artist.set_gid(f"premium-label:fib-price:{ratio}")
    if artifact_artists is not None:
        artifact_artists.extend([
            (f"fib_ratio_{ratio}", ratio_artist),
            (f"fib_price_{ratio}", price_artist),
        ])
    return ratio_artist, price_artist


def _price_integer(value: float) -> str:
    """ราคาทั่วไปบนแผงราคาใช้จำนวนเต็ม แต่ค่าจริงยังคงอยู่ใน geometry."""
    return f"{value:,.0f}"


def _price_viewport(story: dict, view: list[dict], *, include_fib: bool = True,
                    include_plan: bool = True) -> dict:
    """คำนวณช่วงแกน Y โดยไม่ให้ Fibonacci extension ที่ไกลลาก viewport."""
    anchors: list[tuple[str, float]] = []
    anchors += [("candle_low", row["low"]) for row in view]
    anchors += [("candle_high", row["high"]) for row in view]
    anchors.append(("current", story["current"]["close"]))
    scenario = chart_indicator.public_scenario(story) if include_plan else None
    if scenario:
        anchors += [
            ("entry_low", min(scenario["entry_low"], scenario["entry_high"])),
            ("entry_high", max(scenario["entry_low"], scenario["entry_high"])),
            ("stop_loss", scenario["sl"]),
        ]
        anchors += [(f"take_profit_{index}", target)
                    for index, target in enumerate(scenario.get("tps") or [], start=1)]
    fib = story.get("fib") if include_fib else None
    if fib:
        anchors += [
            (f"fib_{level['ratio']:g}", level["price"])
            for level in fib["levels"]
            if level["ratio"] in VISIBLE_FIB_RATIOS
        ]
    values = [value for _, value in anchors]
    raw_low, raw_high = min(values), max(values)
    padding = max((raw_high - raw_low) * 0.06, 1e-9)
    return {
        "low": raw_low - padding,
        "high": raw_high + padding,
        "raw_low": raw_low,
        "raw_high": raw_high,
        "padding": padding,
        "anchor_roles": sorted({role for role, _ in anchors}),
        "extension_included_in_anchors": False,
    }


def _fib_visibility(story: dict, viewport: dict) -> dict:
    """รายงานระดับ Fib ที่อยู่ใน viewport; ระดับนอกช่วงซ่อนทั้งเส้นและป้าย."""
    fib = story.get("fib")
    if not fib:
        return {"visible": [], "hidden": []}
    candidates = [
        {"ratio": level["ratio"], "price": level["price"]}
        for level in fib["levels"]
        if level["ratio"] in VISIBLE_FIB_RATIOS
    ]
    candidates.append({"ratio": chart_indicator.EXTENSION_RATIO,
                       "price": fib["extension"]})
    visible = []
    hidden = []
    for item in candidates:
        if viewport["low"] <= item["price"] <= viewport["high"]:
            visible.append(item)
        else:
            hidden.append({**item, "reason": "outside_price_viewport"})
    return {"visible": visible, "hidden": hidden}


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


def _time_ticks(axes, view: list[dict], timeframe: str, *, locale="th-TH") -> None:
    if timeframe == chart_indicator.TIMEFRAME and view and view[0].get("at"):
        count = min(7, len(view))
        ticks = sorted({round(index * (len(view) - 1) / max(count - 1, 1))
                        for index in range(count)})
        labels = []
        for index in ticks:
            at = view[index]["at"]
            months = FOREIGN_MONTHS.get(locale, ENGLISH_MONTHS) if locale != "th-TH" else THAI_MONTHS
            suffix = "" if locale != "th-TH" else " น."
            labels.append(f"{int(at[8:10])} {months[int(at[5:7]) - 1]} {at[11:16]}{suffix}")
        axes.set_xticks(ticks)
        axes.set_xticklabels(labels)
        if locale != "th-TH":
            labels = FOREIGN_LABELS.get(locale, {})
            axes.set_xlabel(f"{labels.get('time', 'Time')}: UTC+07:00 | {labels.get('price', 'Price')}: USD", fontsize=8, labelpad=3)
        return
    ticks, labels = month_tick_labels(view)
    if locale != "th-TH":
        labels = [label for label in labels]
        for index, label in enumerate(labels):
            for thai, english in zip(THAI_MONTHS, ENGLISH_MONTHS):
                label = label.replace(thai, english)
            labels[index] = label
    axes.set_xticks(ticks[1:])
    axes.set_xticklabels(labels[1:])


def _right_tags(axes, entries: list[dict], x_right: float, y_range: tuple[float, float]) -> dict:
    """วาดป้ายค่าที่ระดับจริงโดยไม่มี leader line และคืนหลักฐาน bbox.

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
        if not entry.get("exact_anchor"):
            for _ in range(50):
                conflict = next(
                    (p for p in placed
                     if not p.get("exact_anchor")
                     and abs(p["label_y"] - target) < minimum_gap),
                    None)
                if conflict is None:
                    break
                target = (conflict["label_y"] + minimum_gap
                          if target >= conflict["label_y"]
                          else conflict["label_y"] - minimum_gap)
        entry["label_y"] = target
        placed.append(entry)
    artists = []
    for entry in placed:
        artist = axes.text(
            entry.get("x", x_right), entry["label_y"], checked_label(entry["text"]),
            color="#ffffff", fontsize=entry.get("font_size", 12.5), fontweight="bold",
            ha=entry.get("ha", "right"), va="center", zorder=7, clip_on=True,
            bbox=dict(boxstyle=f"round,pad={entry.get('padding', 0.28)}",
                      facecolor=entry["face"], edgecolor="none"))
        artist.set_gid(f"premium-label:{entry.get('role') or 'value'}")
        artists.append(artist)
    # The value-space gap above is only a first pass.  Resolve the actual
    # painted boxes as font metrics differ between local Thai font installs.
    # This keeps output deterministic for a given renderer/font and fail-closed
    # metadata can prove that no rail labels overlap.
    movable_artists = [artist for entry, artist in zip(placed, artists)
                       if not entry.get("exact_anchor")]
    _resolve_rail_collisions(axes, movable_artists)
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


def _pack_exact_y_tags_horizontally(axes, artists: list[object],
                                    fixed_artists: list[object], *,
                                    minimum_x: float, gap_px: float = 7.0) -> None:
    """หลบกล่องที่ชนกันด้วยแกน X เท่านั้น โดยไม่เปลี่ยนราคา anchor."""
    figure = axes.figure
    placed: list[object] = []
    for artist in artists:
        for _ in range(12):
            figure.canvas.draw()
            renderer = figure.canvas.get_renderer()
            box = _painted_bbox(artist, renderer)
            conflict = next(
                (other for other in [*fixed_artists, *placed]
                 if (min(box.x1, _painted_bbox(other, renderer).x1)
                     > max(box.x0, _painted_bbox(other, renderer).x0)
                     and min(box.y1, _painted_bbox(other, renderer).y1)
                     > max(box.y0, _painted_bbox(other, renderer).y0))),
                None)
            if conflict is None:
                break
            other_box = _painted_bbox(conflict, renderer)
            shift_px = box.x1 - other_box.x0 + gap_px
            x, y = artist.get_position()
            x0_px = axes.transData.transform((x, y))[0]
            shifted_x = axes.transData.inverted().transform((x0_px - shift_px, 0))[0]
            if shifted_x < minimum_x:
                raise RuntimeError("Style E exact-y labels ไม่มีพื้นที่แนวนอนพอ")
            artist.set_position((shifted_x, y))
        placed.append(artist)


def _header_plan_text(story: dict, money, *, locale="th-TH") -> str | None:
    """คืน direction, entry และ current ในบรรทัดเดียวจาก canonical story."""
    scenario = chart_indicator.public_scenario(story)
    if not scenario:
        return None
    low = min(scenario["entry_low"], scenario["entry_high"])
    high = max(scenario["entry_low"], scenario["entry_high"])
    text = (f"แผน {str(scenario['side']).upper()} · "
            f"โซนเข้า {money(low)}–{money(high)} · "
            f"ปัจจุบัน {money(story['current']['close'])}")
    if locale != "th-TH":
        labels = FOREIGN_LABELS.get(locale, {"plan": "Plan", "entry": "Entry", "current": "Current"})
        text = (f"{labels['plan']} {str(scenario['side']).upper()} · "
                f"{labels['entry']} {money(low)}–{money(high)} · "
                f"{labels['current']} {money(story['current']['close'])}")
    if "\n" in text or "…" in text or "..." in text:
        raise RuntimeError("Style E header ต้องเป็นข้อความเต็มหนึ่งบรรทัด")
    return text


def _draw_adaptive_header_plan(figure, header, title_artist, underline,
                               text: str) -> tuple[object, dict]:
    """ลด font แบบ deterministic จน card ผ่าน geometry; ไม่ wrap/truncate."""
    if "\n" in text or "…" in text or "..." in text:
        raise RuntimeError("Style E header ห้าม wrap/truncate/ellipsis")
    last_error: RuntimeError | None = None
    for font_size in (17.0, 16.0, 15.0, 14.0):
        before = len(header.texts)
        try:
            artist, layout = visual_theme.draw_header_accessory_card(
                figure, header, title_artist, underline,
                checked_label(text), PREMIUM_COLORS,
                role="style-e-plan", font_size=font_size)
            layout["adaptive_font_size"] = font_size
            layout["adaptive_candidates"] = [17.0, 16.0, 15.0, 14.0]
            layout["one_line"] = layout["line_count"] == 1
            layout["truncated"] = artist.get_text() != text
            if not layout["one_line"] or layout["truncated"]:
                artist.remove()
                raise RuntimeError("Style E header ต้องเต็มหนึ่งบรรทัด")
            artist._premium_header_card_layout = layout
            return artist, layout
        except RuntimeError as exc:
            last_error = exc
            for artist in list(header.texts)[before:]:
                artist.remove()
    raise RuntimeError(f"Style E header ไม่มีพื้นที่พอที่ font ขั้นต่ำ: {last_error}")


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


def _rsi_status(value: float, *, locale="th-TH") -> str:
    labels = FOREIGN_LABELS.get(locale)
    if labels:
        return labels["sellers"] if value < 50 else labels["buyers"] if value > 50 else labels["balanced"]
    if locale in ENGLISH_LOCALES:
        return "Sellers dominate" if value < 50 else "Buyers dominate" if value > 50 else "Buying and selling balanced"
    if value < 50:
        return "ฝั่งขายครองตลาด"
    if value > 50:
        return "ฝั่งซื้อครองตลาด"
    return "แรงซื้อกับแรงขายสมดุล"


def _macd_status(histogram: float, *, locale="th-TH") -> str:
    labels = FOREIGN_LABELS.get(locale)
    if labels:
        return labels["rebound"] if histogram > 0 else labels["selling"] if histogram < 0 else labels["steady"]
    if locale in ENGLISH_LOCALES:
        return "Short-term rebound" if histogram > 0 else "Short-term selling pressure" if histogram < 0 else "Short-term momentum steady"
    if histogram > 0:
        return "รีบาวด์ระยะสั้น"
    if histogram < 0:
        return "แรงขายระยะสั้น"
    return "แรงส่งระยะสั้นทรงตัว"


def _tp_label(order: int, target: float, money) -> str:
    """ป้ายเป้าหมายแบบสั้น ลดโอกาสชนกับป้ายราคาปัจจุบัน"""
    return f"TP{order} {money(target)}"


def entry_zone_visible(story: dict) -> bool:
    """มีแผนหลักต้องวาดโซน/SL/TP แม้ราคายังอยู่ไกล โดยป้ายบอกสถานะให้ชัด"""
    scenario = story.get("scenarios", {}).get("primary")
    return bool(scenario)


def _draw_current_price(axes, story: dict, bar_count: int, money=None) -> object | None:
    """วางเฉพาะ marker ที่แท่งล่าสุดและราคา exact; ข้อความอยู่ใน header."""
    if story.get("asset") != "xauusd":
        return None
    current = story["current"]["close"]
    marker = axes.scatter([bar_count - 1], [current], s=30, color=COLORS["info"],
                          edgecolor=COLORS["bg"], linewidth=0.8, zorder=8)
    marker.set_gid("premium-artist:current-price-marker")
    return marker


def _draw_fib_content(axes, story: dict, view: list[dict], x_right: float,
                      Rectangle, *, artifact_artists: list | None = None,
                      fib_visibility: dict | None = None) -> list[dict]:
    """เส้น Fibonacci + โซนเข้า/SL/TP บนแผงราคา — คืนรายการป้ายฝั่งขวาที่ต้องติด"""
    fib_money = money_for(story)
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
        tags.append({"role": "stop_loss", "y": scenario["sl"],
                     "text": f"SL {_price_integer(scenario['sl'])}",
                     "face": COLORS["sl"], "rank": 1, "exact_anchor": True,
                     "font_size": 10.5, "padding": 0.16})
        for order, target in enumerate(scenario["tps"], start=1):
            axes.hlines(target, n - 1, x_right, color=COLORS["tp"], linewidth=1.3,
                        linestyle=(0, (4, 3)), alpha=0.9, zorder=4)
            tags.append({"role": f"take_profit_{order}", "y": target,
                         "text": _tp_label(order, target, _price_integer),
                         "face": COLORS["tp"], "rank": order + 1,
                         "exact_anchor": True, "font_size": 10.5,
                         "padding": 0.16})
        return tags

    visible_ratios = {
        item["ratio"] for item in (fib_visibility or {"visible": []})["visible"]
    }
    for level in fib["levels"]:
        if level["ratio"] not in visible_ratios:
            continue
        color = FIB_LEVEL_COLORS.get(level["ratio"], COLORS["fib"])
        axes.hlines(level["price"], -2, x_right, color=color,
                    alpha=0.85, linewidth=1.2, zorder=2)
        _draw_fib_label(
            axes, y=level["price"], ratio=f"{level['ratio']:g}",
            price=fib_money(level["price"]), color=color,
            artifact_artists=artifact_artists)
    if chart_indicator.EXTENSION_RATIO in visible_ratios:
        axes.hlines(fib["extension"], -2, x_right, color=COLORS["extension"],
                    alpha=0.95, linewidth=1.3, zorder=2)
        _draw_fib_label(
            axes, y=fib["extension"], ratio=f"{chart_indicator.EXTENSION_RATIO:g}",
            price=fib_money(fib["extension"]), color=COLORS["extension"],
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
                     "text": f"SL {_price_integer(scenario['sl'])}",
                     "face": COLORS["sl"], "rank": rank_base,
                     "exact_anchor": True, "font_size": 10.5,
                     "padding": 0.16})
        for order, target in enumerate(scenario["tps"], start=1):
            axes.hlines(target, n - 1, x_right, color=COLORS["tp"], linewidth=1.3,
                        linestyle=(0, (4, 3)), alpha=0.9, zorder=4)
            tags.append({"role": f"take_profit_{order}", "y": target,
                         "text": _tp_label(order, target, _price_integer),
                         "face": COLORS["tp"], "rank": rank_base + order,
                         "exact_anchor": True, "font_size": 10.5,
                         "padding": 0.16})
    return tags


def _anchor_index(view: list[dict], anchor: dict) -> int:
    """หาแท่ง canonical ของ swing แบบ fail-closed; ห้ามขยับ anchor เพื่อความสวย."""
    for index, row in enumerate(view):
        if anchor.get("at") and row.get("at") == anchor["at"]:
            return index
        if not anchor.get("at") and row.get("date") == anchor.get("date"):
            return index
    raise RuntimeError("Style E Fibonacci anchor อยู่นอกหน้าต่าง 120 แท่ง")


def _anchor_label(role: str, anchor: dict, *, locale="th-TH") -> str:
    raw_date = str(anchor.get("date") or anchor.get("at") or "")[:10]
    year, month, day = raw_date.split("-")
    del year
    months = ENGLISH_MONTHS if locale != "th-TH" else THAI_MONTHS
    role = FOREIGN_LABELS.get(locale, {}).get("high" if role == "High" else "low", role)
    return checked_label(
        f"Fib {role} {_price_integer(anchor['price'])} · "
        f"{int(day)} {months[int(month) - 1]}")


def _draw_trade_content(axes, story: dict, view: list[dict], x_right: float,
                        Rectangle) -> list[dict]:
    """วาดเฉพาะ execution geometry สำหรับภาพแผน; ไม่วาด Fibonacci/swing."""
    scenario = chart_indicator.public_scenario(story)
    if not scenario:
        return []
    n = len(view)
    entry_bottom = min(scenario["entry_low"], scenario["entry_high"])
    entry_top = max(scenario["entry_low"], scenario["entry_high"])
    axes.add_patch(Rectangle(
        (-2, entry_bottom), x_right + 2, entry_top - entry_bottom,
        facecolor=COLORS["order_zone_fill"], alpha=0.46,
        edgecolor=COLORS["order_zone_edge"], linewidth=1.2, zorder=1))
    axes.hlines(scenario["sl"], n - 1, x_right, color=COLORS["sl"],
                linewidth=1.6, linestyle=(0, (4, 3)), zorder=4)
    tags = [{"role": "stop_loss", "y": scenario["sl"],
             "text": f"SL {_price_integer(scenario['sl'])}",
             "face": COLORS["sl"], "rank": 1, "exact_anchor": True,
             "font_size": 10.5, "padding": 0.16}]
    for order, target in enumerate(scenario.get("tps") or [], start=1):
        axes.hlines(target, n - 1, x_right, color=COLORS["tp"], linewidth=1.3,
                    linestyle=(0, (4, 3)), alpha=0.9, zorder=4)
        tags.append({"role": f"take_profit_{order}", "y": target,
                     "text": _tp_label(order, target, _price_integer),
                     "face": COLORS["tp"], "rank": order + 1,
                     "exact_anchor": True, "font_size": 10.5,
                     "padding": 0.16})
    return tags


def render_fibonacci(story: dict, rows: list[dict], output_path: Path, *,
                     locale="th-TH", source_timezone=None,
                     fontfamily=None, fontsize=None) -> dict:
    """ภาพ Fibonacci ราคาอย่างเดียว 120 แท่ง พร้อม swing/anchors canonical."""
    _validate_display_locale(locale, source_timezone)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter

    if not story.get("fib"):
        raise RuntimeError("Style E Fibonacci image ต้องมี canonical Fibonacci")
    font_used = _thai_font()
    view = rows[-FIB_BARS:]
    if len(view) != FIB_BARS:
        raise RuntimeError("Style E Fibonacci image ต้องมีแท่งปิดครบ 120 แท่ง")
    n = len(view)
    fib = story["fib"]
    closes = [row["close"] for row in rows]
    x_right = n - 1 + n * 0.10
    figure, ax_price = plt.subplots(1, 1, figsize=FIB_FIGURE_SIZE, dpi=DPI)
    figure.patch.set_facecolor(COLORS["bg"])
    _style_axes(ax_price)
    viewport = _price_viewport(story, view, include_fib=True, include_plan=False)
    candidates = [
        {"ratio": level["ratio"], "price": level["price"]}
        for level in fib["levels"] if level["ratio"] not in {0.0, 1.0}
    ] + [{"ratio": chart_indicator.EXTENSION_RATIO,
          "price": fib["extension"]}]
    visibility = {"visible": [], "hidden": []}
    for item in candidates:
        if viewport["low"] <= item["price"] <= viewport["high"]:
            visibility["visible"].append(item)
        else:
            visibility["hidden"].append(
                {**item, "reason": "outside_price_viewport"})
    ax_price.set_xlim(-2, x_right)
    ax_price.set_ylim(viewport["low"], viewport["high"])
    ax_price.yaxis.set_major_formatter(
        FuncFormatter(lambda value, _position: _price_integer(value)))

    artists: list[tuple[str, object]] = []
    visible_ratios = {item["ratio"] for item in visibility["visible"]}
    for level in fib["levels"]:
        if level["ratio"] not in visible_ratios:
            continue
        ratio = f"{level['ratio']:g}"
        color = FIB_LEVEL_COLORS.get(level["ratio"], COLORS["fib"])
        ax_price.hlines(level["price"], -2, x_right, color=color,
                        alpha=0.85, linewidth=1.2, zorder=2)
        _draw_fib_label(ax_price, y=level["price"], ratio=ratio,
                        price=_price_integer(level["price"]), color=color,
                        artifact_artists=artists)
    if chart_indicator.EXTENSION_RATIO in visible_ratios:
        ratio = f"{chart_indicator.EXTENSION_RATIO:g}"
        ax_price.hlines(fib["extension"], -2, x_right, color=COLORS["extension"],
                        alpha=0.95, linewidth=1.3, zorder=2)
        _draw_fib_label(ax_price, y=fib["extension"], ratio=ratio,
                        price=_price_integer(fib["extension"]),
                        color=COLORS["extension"], artifact_artists=artists)

    start_key = "swing_high" if fib["direction"] == "down" else "swing_low"
    end_key = "swing_low" if fib["direction"] == "down" else "swing_high"
    start_x, end_x = (_anchor_index(view, fib[start_key]),
                      _anchor_index(view, fib[end_key]))
    start_y, end_y = fib[start_key]["price"], fib[end_key]["price"]
    ax_price.plot([start_x, end_x], [start_y, end_y], color=COLORS["fib_anchor"],
                  linewidth=2.2, alpha=0.95, zorder=5)
    anchor_records = {}
    for key, x, y in ((start_key, start_x, start_y), (end_key, end_x, end_y)):
        role = "High" if key == "swing_high" else "Low"
        marker = ax_price.scatter([x], [y], s=72, facecolor=COLORS["bg"],
                                  edgecolor=COLORS["fib_anchor"], linewidth=2.2,
                                  zorder=7)
        marker.set_gid(f"premium-artist:fib-{role.lower()}-anchor")
        right_side = x > n * 0.70
        label = ax_price.annotate(
            _anchor_label(role, fib[key], locale=locale), xy=(x, y),
            xytext=((-10 if right_side else 10), (13 if role == "High" else -13)),
            textcoords="offset points", ha=("right" if right_side else "left"),
            va=("bottom" if role == "High" else "top"), color=COLORS["fib_anchor"],
            fontsize=12, fontweight="bold", zorder=8,
            bbox=dict(boxstyle="round,pad=0.24", facecolor=COLORS["bg"],
                      edgecolor=COLORS["fib_anchor"], linewidth=0.8, alpha=0.97))
        label.set_gid(f"premium-label:fib-{role.lower()}-anchor")
        artists.append((f"fib_{role.lower()}_anchor_label", label))
        anchor_records[key] = {"x": x, "y": y, "date": fib[key]["date"],
                               "label": label.get_text(), "exact": True}

    _draw_candles(ax_price, view, Rectangle)
    _plot_line(ax_price, _series_view(chart_indicator.ema(closes, chart_indicator.MACD_FAST),
                                      len(rows), n), COLORS["ema_fast"], linewidth=1.5)
    _plot_line(ax_price, _series_view(chart_indicator.ema(closes, chart_indicator.MACD_SLOW),
                                      len(rows), n), COLORS["ema_slow"], linewidth=1.5)
    _plot_line(ax_price, _series_view(chart_story.sma(closes, 50), len(rows), n),
               COLORS["sma"], linewidth=1.4, linestyle=(0, (5, 3)), alpha=0.85)
    _time_ticks(ax_price, view, story.get("timeframe", "1day"), locale=locale)
    figure.subplots_adjust(left=0.015, right=0.955, top=0.87, bottom=0.08)
    header = figure.add_axes([0.0, 0.89, 1.0, 0.08])
    title, _, underline = visual_theme.draw_edge_to_edge_header(
        figure, header, ax_price, checked_label(f"{story['symbol']} · H1 · Fibonacci"),
        PREMIUM_COLORS, fontfamily=fontfamily, fontsize=fontsize)
    header_layout = visual_theme.edge_to_edge_header_layout(
        figure, header, ax_price, title, underline)
    watermark = visual_theme.draw_matplotlib_watermark(
        figure, ax_price, surface="chart", surface_aware=True)
    _layout_guard(figure, artists)
    boxes = _bbox_record(artists, figure)
    try:
        size_bytes = image_output.save_figure(figure, output_path, facecolor=COLORS["bg"])
    finally:
        plt.close(figure)
    return {"path": str(output_path), "bars": n, "font": font_used,
            "bytes": size_bytes, "kb": image_output.kb(size_bytes),
            "background": COLORS["bg"],
            "elements": {"fib": True, "swing": True, "anchors": True,
                         "rsi": False, "macd": False, "trade_plan": False},
            "layout": {"header_visible_text": [f"{story['symbol']} · H1 · Fibonacci"],
                       "edge_to_edge_header": header_layout, "watermark": watermark,
                       "leader_lines": False, "anchor_records": anchor_records,
                       "fib_visibility": visibility, "price_viewport": viewport,
                       "bbox_assertions": {"checked": True, "overlap_count": 0,
                                           "roles": [item["role"] for item in boxes]}},
            "metadata": {"schema": "style-e-fibonacci-renderer-v1",
                         "layout": {"anchor_records": anchor_records,
                                    "fib_visibility": visibility,
                                    "bbox_assertions": {"checked": True,
                                                        "overlap_count": 0,
                                                        "boxes": boxes}}}}


def render_trade_plan(story: dict, rows: list[dict], output_path: Path, *,
                      locale="th-TH", source_timezone=None,
                      fontfamily=None, fontsize=None) -> dict:
    """ภาพแผนเทรด 50 แท่ง — ราคา/Entry/Current/SL/TP + RSI/MACD."""
    _validate_display_locale(locale, source_timezone)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter

    font_used = _thai_font()
    bars = TRADE_PLAN_BARS
    view = rows[-bars:]
    if len(view) != TRADE_PLAN_BARS:
        raise RuntimeError("Style E trade-plan image ต้องมีแท่งปิดครบ 50 แท่ง")
    n = len(view)
    closes = [row["close"] for row in rows]
    x_right = n - 1 + n * RIGHT_PAD_FRACTION
    x_limit_right = x_right

    figure, (ax_price, ax_rsi, ax_macd) = plt.subplots(
        3, 1, figsize=FIGURE_SIZE, dpi=DPI, sharex=True,
        gridspec_kw={"height_ratios": [3.6, 1.0, 1.0], "hspace": 0.06})
    figure.patch.set_facecolor(COLORS["bg"])
    for axes in (ax_price, ax_rsi, ax_macd):
        _style_axes(axes)

    # ---- แผงราคา + แผนเทรด (ไม่มี Fibonacci/swing) ----
    price_viewport = _price_viewport(
        story, view, include_fib=False, include_plan=True)
    fib_visibility = {"visible": [], "hidden": []}
    low, high = price_viewport["low"], price_viewport["high"]
    ax_price.set_xlim(-2, x_limit_right)
    ax_price.set_ylim(low, high)
    ax_price.yaxis.set_major_formatter(
        FuncFormatter(lambda value, _position: _price_integer(value)))

    price_artists: list[tuple[str, object]] = []
    execution_tags = _draw_trade_content(
        ax_price, story, view, x_right, Rectangle)
    _draw_candles(ax_price, view, Rectangle)
    _plot_line(ax_price, _series_view(chart_indicator.ema(closes, chart_indicator.MACD_FAST),
                                      len(rows), n), COLORS["ema_fast"], linewidth=1.5)
    _plot_line(ax_price, _series_view(chart_indicator.ema(closes, chart_indicator.MACD_SLOW),
                                      len(rows), n), COLORS["ema_slow"], linewidth=1.5)
    _plot_line(ax_price, _series_view(chart_story.sma(closes, 50), len(rows), n),
               COLORS["sma"], linewidth=1.4, linestyle=(0, (5, 3)), alpha=0.85)
    current_marker = _draw_current_price(ax_price, story, n, _price_integer)
    current_at_latest_candle = current_marker is not None
    # เริ่มชิดขอบขวา แล้วหลบเฉพาะแนวนอนเมื่อป้ายราคาใกล้กัน; y ห้ามเปลี่ยน.
    execution_label_x = x_right - n * 0.01
    price_rail = _right_tags(
        ax_price, execution_tags, execution_label_x, (low, high))
    _pack_exact_y_tags_horizontally(
        ax_price, price_rail["artists"],
        [],
        minimum_x=n - 1 + n * 0.02)
    price_artists += [
        (f"price_{role}", artist)
        for role, artist in zip(price_rail["roles"], price_rail["artists"])
    ]

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
        f"RSI (14): {story['rsi']['value']:.1f} ({_rsi_status(story['rsi']['value'], locale=locale)})"))

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
        f"({_macd_status(story['macd']['histogram'], locale=locale)})"))

    timeframe = story.get("timeframe", "1day")
    _time_ticks(ax_macd, view, timeframe, locale=locale)

    # ผู้ใช้สั่ง 2026-08-19 ให้ตัดหัวเรื่องและคำบรรยายเหนือภาพออกทั้งหมด แล้วคืนพื้นที่
    # ให้กราฟ และสั่ง 2026-08-25 ให้ถอด footer ใต้ MACD ออกทั้งแถว โดยคงชื่อแผง
    # RSI/MACD และแกนเวลาไว้ตามเดิม
    figure.subplots_adjust(left=0.015, right=0.955, top=0.87,
                           bottom=0.045, hspace=0.06)
    header = figure.add_axes([0.0, 0.89, 1.0, 0.08])
    header_title, _, header_underline = visual_theme.draw_edge_to_edge_header(
        figure, header, ax_price,
        checked_label(f"{story['symbol']} · H1"), PREMIUM_COLORS,
        fontfamily=fontfamily, fontsize=fontsize)
    header_layout = visual_theme.edge_to_edge_header_layout(
        figure, header, ax_price, header_title, header_underline)
    header_plan_text = _header_plan_text(story, _price_integer, locale=locale)
    header_card_artist = None
    header_card_layout = None
    if header_plan_text:
        header_card_artist, header_card_layout = _draw_adaptive_header_plan(
            figure, header, header_title, header_underline, header_plan_text)
    watermark_layout = visual_theme.draw_matplotlib_watermark(
        figure, ax_price, surface="chart", surface_aware=True)
    required_artists = list(price_artists)
    if header_card_artist is not None:
        required_artists.append(("header_plan", header_card_artist))
    required_artists += [(f"rsi-{role}", artist)
                         for role, artist in zip(rsi_rail["roles"], rsi_rail["artists"])]
    required_artists += [(f"macd-{role}", artist)
                         for role, artist in zip(macd_rail["roles"], macd_rail["artists"])]
    _layout_guard(figure, required_artists)
    bbox_records = _bbox_record(required_artists, figure)
    price_line_label_x_fractions = {
        role: round(
            ax_price.transData.transform(artist.get_position())[0]
            / figure.bbox.width, 4)
        for role, artist in zip(price_rail["roles"], price_rail["artists"])
    }
    fib_label_texts = {
        role: artist.get_text() for role, artist in price_artists
        if role.startswith("fib_ratio_") or role.startswith("fib_price_")
    }
    price_axis_tick_labels = [
        label.get_text() for label in ax_price.get_yticklabels()
        if label.get_visible() and label.get_text()
    ]
    scenario = chart_indicator.public_scenario(story)
    entry_zone_band = ([min(scenario["entry_low"], scenario["entry_high"]),
                        max(scenario["entry_low"], scenario["entry_high"])]
                       if scenario else None)
    try:
        size_bytes = image_output.save_figure(figure, output_path, facecolor=COLORS["bg"])
    finally:
        plt.close(figure)   # ตกด่านขนาดก็ต้องคืน figure ไม่งั้นรอบถัดไปกินหน่วยความจำสะสม
    return {"path": str(output_path), "bars": n, "font": font_used,
            "bytes": size_bytes, "kb": image_output.kb(size_bytes),
            "background": COLORS["bg"],
            "elements": {"rsi": True, "macd": True, "footer": False,
                         "fib": False,
                         "primary": bool(chart_indicator.public_scenario(story)),
                         "entry_zone": entry_zone_visible(story),
                         "counter": False,
                         "header": True},
            "layout": {
                "entry_zone_label": None,
                "entry_zone_band": entry_zone_band,
                "current_price": "header_card" if current_at_latest_candle else None,
                "current_price_location": "header_card" if current_at_latest_candle else None,
                "current_marker": "latest_candle" if current_at_latest_candle else None,
                "current_marker_anchor": ({"x": n - 1,
                                           "y": story["current"]["close"],
                                           "exact": True}
                                          if current_at_latest_candle else None),
                "current_price_label_in_plot": False,
                "summary_strip": False,
                "old_floating_summary_count": 0,
                "header_visible_text": [f"{story['symbol']} · H1"],
                "header_card_visible_text": ([header_plan_text]
                                             if header_plan_text else []),
                "edge_to_edge_header": header_layout,
                "header_accessory_card": header_card_layout,
                "watermark": watermark_layout,
                "watermark_count": sum(
                    artist.get_gid() == "premium-decoration:watermark"
                    for axes in figure.axes for artist in axes.texts),
                "annotation_rail": "price_line_end_labels",
                "leader_lines": False,
                "price_line_anchors": {
                    item["role"]: item["y"] for item in price_rail["placed"]
                },
                "price_line_labels": {
                    item["role"]: item["text"] for item in price_rail["placed"]
                },
                "price_line_label_x_fractions": price_line_label_x_fractions,
                "fib_label_texts": {},
                "current_price_text": None,
                "price_axis_tick_labels": price_axis_tick_labels,
                "price_viewport": price_viewport,
                "fib_visibility": fib_visibility,
                "latest_candle_x_fraction": round(
                    ax_price.transData.transform((n - 1, 0))[0]
                    / figure.bbox.width, 4),
                "bbox_assertions": {"checked": True, "overlap_count": 0,
                                    "roles": [item["role"] for item in bbox_records]},
            },
            "metadata": {
                "schema": "style-e-trade-plan-renderer-v1",
                "theme": {"schema": visual_theme.SCHEMA, "version": visual_theme.VERSION},
                "layout": {"summary_strip": "header_accessory_card",
                           "old_floating_summary_count": 0,
                           "header_visible_text": [f"{story['symbol']} · H1"],
                           "header_accessory_card": header_card_layout,
                           "edge_to_edge_header": header_layout,
                           "watermark": watermark_layout,
                            "watermark_count": 1,
                            "annotation_rail": "price_line_end_labels",
                            "leader_lines": False,
                            "current_price_location": (
                                "header_card" if current_at_latest_candle else None),
                            "current_marker": (
                                "latest_candle" if current_at_latest_candle else None),
                            "current_marker_anchor": (
                                {"x": n - 1, "y": story["current"]["close"],
                                 "exact": True}
                                if current_at_latest_candle else None),
                            "current_price_label_in_plot": False,
                            "price_line_anchors": {
                                item["role"]: item["y"]
                                for item in price_rail["placed"]
                            },
                            "price_line_labels": {
                                item["role"]: item["text"]
                                for item in price_rail["placed"]
                            },
                            "price_line_label_x_fractions":
                                price_line_label_x_fractions,
                            "fib_label_texts": {},
                            "price_axis_tick_labels": price_axis_tick_labels,
                            "price_viewport": price_viewport,
                            "fib_visibility": fib_visibility,
                           "bbox_assertions": {"checked": True, "overlap_count": 0,
                                               "boxes": bbox_records}},
            }}


def render_combined(story: dict, rows: list[dict], output_path: Path) -> dict:
    """Compatibility shim; production Style E uses the two explicit renderers."""
    return render_trade_plan(story, rows, output_path)
