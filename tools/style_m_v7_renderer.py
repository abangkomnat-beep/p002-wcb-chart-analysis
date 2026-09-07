"""Deterministic two-role Style M v7 renderer."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from tools import visual_theme

WIDTH, HEIGHT = 1920, 1080
H1_VISIBLE_BARS = 96
M15_VISIBLE_BARS = 72
VISIBLE_BARS = H1_VISIBLE_BARS
PRICE_TICKS = 7
M15_PRICE_TICKS = 11
H1_TIME_TICKS = 7
M15_TIME_TICKS = 8
RENDERER_REVISION = "style-m-visual-r10/v1"
TITLES = {"h1_market_map": "BTCUSD · H1 MARKET MAP",
          "m15_entry_plan": "BTCUSD · M15 ENTRY · H1 PLAN"}
THAI_MONTHS = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
               "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")
ENGLISH_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _font(size: int):
    for name in ("C:/Windows/Fonts/LeelawUI.ttf", "C:/Windows/Fonts/tahoma.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def _overlap(boxes):
    return sum(1 for i, a in enumerate(boxes) for b in boxes[i + 1:]
               if not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]))


def _price(value):
    return float(value)


def _domain(story, rows, include_plans=True, *, pad_fraction=.08):
    values = [_price(row[key]) for row in rows for key in ("low", "high")]
    values.extend(_price(story["donchian"][key]) for key in ("lower", "upper"))
    if include_plans:
        for plan in story.get("scenarios", {}).values():
            values.extend(_price(plan[key]) for key in
                          ("trigger", "entry_low", "entry_high", "sl", "tp1", "tp2")
                          if plan.get(key) is not None)
    lo, hi = min(values), max(values)
    pad = max((hi - lo) * pad_fraction, 1.0)
    return lo - pad, hi + pad


def _draw_header(image, title):
    layout = visual_theme.draw_pil_edge_to_edge_header(
        image, title, plot_left=80, font_factory=_font,
        header_height=108, underline_height=5)
    # Repaint the exact M15 title at the measured header anchor after all
    # header layers. This prevents a downstream card/panel layer from hiding
    # the leading BTCUSD token in raster previews.
    if title == TITLES["m15_entry_plan"]:
        draw = ImageDraw.Draw(image); font = _font(36); box = draw.textbbox((0, 0), title, font=font)
        y = round((108 - 5 - (box[3] - box[1])) / 2 - box[1])
        draw.text((80, y), title, fill=visual_theme.PREMIUM["component"]["ivory"], font=font)
    return layout


def _draw_scale(draw, plot, lo, hi, colors, *, count=PRICE_TICKS):
    x0, y0, x1, y1 = plot
    ticks = []
    for index in range(count):
        value = hi - (hi - lo) * index / max(count - 1, 1)
        y = int(y1 - (value - lo) / (hi - lo) * (y1 - y0))
        draw.line((x0, y, x1, y), fill=colors["grid"], width=1)
        text = f"{value:,.0f}"; origin = (x1 + 12, y - 8)
        draw.text(origin, text, fill=colors["axis"], font=_font(14))
        ticks.append({"value": value, "y": y,
                      "label_bbox": list(draw.textbbox(origin, text, font=_font(14)))})
    return ticks


def _time_text(value, *, locale="th-TH", source_timezone=None) -> str:
    if isinstance(value, datetime):
        moment = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        moment = datetime.fromisoformat(text)
    if locale == "en-ZA":
        if source_timezone != "+07:00":
            raise ValueError("ZA pilot requires an explicit verified source timezone +07:00")
        if moment.utcoffset() is not None and moment.strftime("%z") != "+0700":
            raise ValueError("timestamp offset differs from the displayed source timezone")
        return f"{moment.day} {ENGLISH_MONTHS[moment.month - 1]} {moment:%H:%M}"
    if locale != "th-TH":
        raise ValueError("unsupported Style M display locale")
    return f"{moment.day} {THAI_MONTHS[moment.month - 1]} {moment:%H:%M} น."


def _draw_time_scale(draw, rows, plot, x_end, colors, *, count, visible_bars,
                     x_start=None, locale="th-TH", source_timezone=None):
    """Draw source-backed time ticks below the plot and record painted geometry."""
    visible = list(rows)[-visible_bars:]
    if not visible or any(not row.get("at") for row in visible):
        raise RuntimeError("Style M R8 time axis ต้องมี timestamp ของแท่งปิดครบ")
    indices = sorted({round(index * (len(visible) - 1) / max(count - 1, 1))
                      for index in range(count)})
    if len(indices) != count:
        raise RuntimeError("Style M R8 time axis สร้างจำนวน tick ไม่ครบ")
    font = _font(13); ticks = []; boxes = []; grids = []
    plot_x0, y0, _, y1 = plot
    x0 = plot_x0 if x_start is None else x_start
    for source_index in indices:
        x = int(round(x0 + source_index / max(len(visible) - 1, 1) * (x_end - x0)))
        label = _time_text(visible[source_index]["at"], locale=locale,
                           source_timezone=source_timezone)
        measured = draw.textbbox((0, 0), label, font=font)
        width = measured[2] - measured[0]
        origin_x = max(4, min(int(round(x - width / 2)), WIDTH - width - 4))
        origin_y = y1 + 15
        bbox = draw.textbbox((origin_x, origin_y), label, font=font)
        draw.line((x, y0, x, y1), fill=colors["grid"], width=1)
        draw.line((x, y1, x, y1 + 7), fill=colors["axis"], width=1)
        draw.text((origin_x, origin_y), label, fill=colors["axis"], font=font)
        boxes.append(tuple(bbox))
        ticks.append({"source_index": source_index,
                      "source_at": str(visible[source_index]["at"]),
                      "label": label, "x": x, "bbox": list(bbox),
                      "contained_in_canvas": bool(
                          bbox[0] >= 0 and bbox[1] >= 0
                          and bbox[2] <= WIDTH and bbox[3] <= HEIGHT)})
        grids.append({"x": x, "y_start": y0, "y_end": y1,
                      "layer": "background_grid"})
    if locale == "en-ZA":
        draw.text((x0, y1 + 40), "Time: UTC+07:00 | Price: USD",
                  fill=colors["axis"], font=_font(13))
    return ticks, _overlap(boxes), grids


def _pill_geometry(draw, text, *, right, bottom, max_width):
    for size in (13, 12, 11):
        font = _font(size)
        measured = draw.textbbox((0, 0), text, font=font)
        width = measured[2] - measured[0] + 18
        height = measured[3] - measured[1] + 8
        if width <= max_width:
            return font, (right - width, bottom - height, right, bottom)
    raise RuntimeError(f"Style M R8 price pill ยาวเกิน contract: {text}")


def _draw_header_cards(draw, plans, header, colors):
    face = visual_theme.PREMIUM["component"]["ivory"]
    edge = visual_theme.PREMIUM["component"]["gold"]
    text_color = visual_theme.PREMIUM["component"]["callout"]
    title_right = header["title_bbox_px"][2]
    gap = 16; right = WIDTH - 24; left_min = int(title_right + 24)
    font = _font(14); prepared = []
    for plan in plans:
        side = "BUY" if plan.get("side") == "LONG" else "SELL"
        if plan.get("state") == "NO_PLAN":
            lines = [f"{side} · NO PLAN", str(plan.get("no_plan_reason", "UNAVAILABLE"))]
        else:
            lines = [
                f"{side} · Entry {_price(plan['entry_low']):,.0f}–{_price(plan['entry_high']):,.0f}",
                f"SL {_price(plan['sl']):,.0f} · TP1 {_price(plan['tp1']):,.0f} · TP2 {_price(plan['tp2']):,.0f}",
            ]
        measured = [draw.textbbox((0, 0), line, font=font) for line in lines]
        text_width = max(box[2] - box[0] for box in measured)
        card_width = max(270, min(360, text_width + 44))
        prepared.append((plan, side, lines, card_width))
    total_width = sum(item[3] for item in prepared) + gap * max(0, len(prepared) - 1)
    first_left = right - total_width
    if first_left < left_min:
        raise RuntimeError("Style M R9 header ไม่มีพื้นที่พอสำหรับ BUY/SELL cards")
    cards = []; cursor = first_left
    for plan, side, lines, card_width in prepared:
        card = (cursor, 18, cursor + card_width, 88); cursor = card[2] + gap
        draw.rounded_rectangle(card, radius=7, fill=face, outline=edge, width=2)
        accent = colors["buy"] if side == "BUY" else colors["sell"]
        draw.rounded_rectangle((card[0] + 7, card[1] + 9, card[0] + 12, card[3] - 9),
                               radius=2, fill=accent)
        origins = ((card[0] + 22, card[1] + 10), (card[0] + 22, card[1] + 38))
        text_boxes = [draw.textbbox(origin, line, font=font)
                      for origin, line in zip(origins, lines)]
        if any(box[2] > card[2] - 12 or box[3] > card[3] - 6 for box in text_boxes):
            raise RuntimeError("Style M R8 header card text ล้นกรอบ")
        for origin, line in zip(origins, lines):
            draw.text(origin, line, fill=text_color, font=font)
        contained = bool(card[0] >= 0 and card[2] <= WIDTH
                         and card[1] >= 0
                         and card[3] <= header["header_height_px"] - header["underline_height_px"])
        cards.append({"side": plan.get("side"), "state": plan.get("state"),
                      "entry_low": plan.get("entry_low"), "entry_high": plan.get("entry_high"),
                      "sl": plan.get("sl"), "tp1": plan.get("tp1"), "tp2": plan.get("tp2"),
                      "bbox": list(card), "visible_text": lines,
                      "text_bboxes": [list(box) for box in text_boxes],
                      "line_count": 2, "contained_in_header": contained,
                      "content_sized": True,
                      "text_clipped": False,
                      "position": "top_right_horizontal"})
    return cards


def _draw_candles(draw, rows, plot, lo, hi, colors, x_end, *,
                  visible_bars=VISIBLE_BARS, x_start=None):
    plot_x0, y0, x1, y1 = plot
    x0 = plot_x0 if x_start is None else x_start
    visible = rows[-visible_bars:]
    def px(i): return int(x0 + i / max(len(visible) - 1, 1) * (x_end - x0))
    def py(v): return int(y1 - (_price(v) - lo) / (hi - lo) * (y1 - y0))
    result = []
    for i, row in enumerate(visible):
        xc = px(i); op, cl = py(row["open"]), py(row["close"])
        yh, yl = py(row["high"]), py(row["low"])
        color = colors["buy"] if _price(row["close"]) >= _price(row["open"]) else colors["sell"]
        draw.line((xc, yh, xc, yl), fill=color, width=2)
        body_bbox = (xc - 4, min(op, cl), xc + 4, max(op, cl))
        draw.rectangle(body_bbox, fill=color)
        result.append({"index": row.get("index", i), "x": xc, "open": row["open"],
                       "high": row["high"], "low": row["low"], "close": row["close"],
                       "wick_x": xc, "body_bbox": list(body_bbox)})
    return result


def _render_h1(story, rows, output, *, facts=None, visual_source=None,
               locale="th-TH", source_timezone=None):
    colors = visual_theme.for_chart()
    image = Image.new("RGB", (WIDTH, HEIGHT), colors["canvas"]); draw = ImageDraw.Draw(image)
    header = _draw_header(image, TITLES["h1_market_map"])
    plot = (80, 145, 1750, 950); lo, hi = _domain(story, rows[-H1_VISIBLE_BARS:], False)
    draw.rectangle(plot, fill=colors["plot"], outline=colors["border"], width=2)
    def py(v): return int(plot[3] - (_price(v) - lo) / (hi - lo) * (plot[3] - plot[1]))
    artists = [{"role": "h1_candles", "count": 0}]; boxes = []
    upper, lower = py(story["donchian"]["upper"]), py(story["donchian"]["lower"])
    draw.rectangle((plot[0], min(upper, lower), plot[2], max(upper, lower)), fill="#F2F7FB")
    trigger_values = [plan.get("trigger") for plan in story.get("scenarios", {}).values()
                      if plan.get("trigger") is not None]
    if len(trigger_values) == 2:
        trap_top, trap_bottom = sorted((py(trigger_values[0]), py(trigger_values[1])))
        draw.rectangle((plot[0], trap_top, plot[2], trap_bottom), fill="#FFF7D6")
    ticks = _draw_scale(draw, plot, lo, hi, colors)
    candle_end = 1580
    time_ticks, time_overlap, vertical_grid = _draw_time_scale(
        draw, rows, plot, candle_end, colors,
        count=H1_TIME_TICKS, visible_bars=H1_VISIBLE_BARS,
        locale=locale, source_timezone=source_timezone)
    watermark = visual_theme.draw_pil_watermark(
        image, surface="chart", font_factory=_font, surface_aware=True)
    candles = _draw_candles(
        draw, rows, plot, lo, hi, colors, candle_end,
        visible_bars=H1_VISIBLE_BARS)
    artists[0]["count"] = len(candles)
    for value, role, label in ((story["donchian"]["upper"], "donchian_upper", "Donchian upper"),
                               (story["donchian"]["lower"], "donchian_lower", "Donchian lower")):
        y = py(value); draw.line((plot[0], y, plot[2], y), fill=colors["indicator"], width=3)
        draw.text((plot[2] - 250, max(plot[1] + 6, y - 24)), f"{label} {_price(value):,.0f}", fill=colors["indicator"], font=_font(16))
        artists.append({"role": role, "price": value, "y_anchor": y, "x_start": plot[0], "x_end": plot[2]})
    if len(trigger_values) == 2:
        y_top, y_bottom = sorted((py(trigger_values[0]), py(trigger_values[1])))
        trap_box = (plot[0] + 18, max(plot[1] + 18, y_top + 12), plot[0] + 190, max(plot[1] + 44, y_top + 40))
        draw.rounded_rectangle(trap_box, radius=5, fill="#FFF7D6", outline=colors["warning"], width=1)
        draw.text((trap_box[0] + 10, trap_box[1] + 5), "TRAP ZONE", fill=colors["warning"], font=_font(15)); boxes.append(trap_box)
        artists.append({"role": "trap_band", "lower": min(trigger_values), "upper": max(trigger_values), "y_top": y_top, "y_bottom": y_bottom})
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    image.save(Path(output), format="WEBP", lossless=True, quality=100)
    return {"path": str(output), "width": WIDTH, "height": HEIGHT, "format": "webp", "role": "h1_market_map",
            "header_title": TITLES["h1_market_map"], "display_timeframe": "H1", "decision_timeframe": "H1",
            "displayed_bars": len(candles), "artists": artists, "price_ticks": ticks,
            "time_ticks": time_ticks, "time_tick_overlap_count": time_overlap,
            "vertical_time_grid": vertical_grid,
            "header": header,
            "layout": {"plot": list(plot), "data_span": [plot[0], candle_end]},
            "label_overlap_count": _overlap(boxes), "forbidden_execution_artist_count": 0,
            "watermark": watermark, "watermark_count": 1,
            "canonical_facts_sha256": (facts or {}).get("facts_sha256"), "story_source_sha256": story.get("source_sha256"),
            "visual_source_sha256": (visual_source or {}).get("source_sha256")}


def _render_m15(story, rows, output, *, facts=None, visual_source=None,
                locale="th-TH", source_timezone=None):
    colors = visual_theme.for_chart(); image = Image.new("RGB", (WIDTH, HEIGHT), colors["canvas"]); draw = ImageDraw.Draw(image)
    header = _draw_header(image, TITLES["m15_entry_plan"]); plot = (28, 118, 1810, 1010)
    data_x_start = plot[0] + 5
    latest_x = int(round(plot[0] + (plot[2] - plot[0]) * 0.84))
    domain_padding = .03
    lo, hi = _domain(story, rows[-M15_VISIBLE_BARS:], True,
                     pad_fraction=domain_padding)
    draw.rectangle(plot, fill=colors["plot"], outline=colors["border"], width=2)
    def py(v): return int(plot[3] - (_price(v) - lo) / (hi - lo) * (plot[3] - plot[1]))
    ticks = _draw_scale(draw, plot, lo, hi, colors, count=M15_PRICE_TICKS)
    time_ticks, time_overlap, vertical_grid = _draw_time_scale(
        draw, rows, plot, latest_x, colors,
        count=M15_TIME_TICKS, visible_bars=M15_VISIBLE_BARS,
        x_start=data_x_start, locale=locale, source_timezone=source_timezone)
    bands = []; lines = []; labels = []; cards = []; label_boxes = []
    plans = list(story.get("scenarios", {}).values())
    for plan in plans:
        if plan.get("state") == "NO_PLAN" or plan.get("entry_low") is None: continue
        side = "BUY" if plan.get("side") == "LONG" else "SELL"; color = colors["buy"] if side == "BUY" else colors["sell"]
        ya, yb = py(plan["entry_low"]), py(plan["entry_high"])
        band_fill = "#BFE6D0" if side == "BUY" else "#F3C6C3"
        draw.rectangle((latest_x, min(ya, yb), plot[2], max(ya, yb)), fill=band_fill, outline=color, width=2)
        bands.append({"side": side, "low": plan["entry_low"], "high": plan["entry_high"], "x_start": latest_x, "x_end": plot[2], "y_low": ya, "y_high": yb, "fill_color": band_fill, "bbox": [latest_x, min(ya, yb), plot[2], max(ya, yb)]})
    watermark = visual_theme.draw_pil_watermark(
        image, surface="chart", font_factory=_font, surface_aware=True)
    candles = _draw_candles(
        draw, rows, plot, lo, hi, colors, latest_x,
        visible_bars=M15_VISIBLE_BARS, x_start=data_x_start)
    occupied = []
    for plan in plans:
        side = "BUY" if plan.get("side") == "LONG" else "SELL"; color = colors["buy"] if side == "BUY" else colors["sell"]
        if plan.get("state") == "NO_PLAN" or plan.get("entry_low") is None: continue
        execution = [("SL", (plan["sl"],), py(plan["sl"])), ("TP1", (plan["tp1"],), py(plan["tp1"])), ("TP2", (plan["tp2"],), py(plan["tp2"]))]
        for role, values, y in execution:
            value = values[0]; text = f"{role} {_price(value):,.0f}"
            line_style = "solid" if role == "SL" else "dashed"
            if line_style == "solid": draw.line((latest_x, y, plot[2], y), fill=color, width=3)
            else:
                for start in range(latest_x, plot[2], 18): draw.line((start, y, min(start + 10, plot[2]), y), fill=color, width=3)
            font, initial = _pill_geometry(
                draw, text, right=plot[2] - 8,
                bottom=min(y - 2, plot[3] - 4), max_width=120)
            pill_height = initial[3] - initial[1]; box = None
            for step in range(16):
                candidate_bottom = initial[3] - step * (pill_height + 4)
                candidate = (initial[0], candidate_bottom - pill_height,
                             initial[2], candidate_bottom)
                if candidate[1] < plot[1] + 4 or candidate[3] > plot[3] - 4:
                    continue
                if candidate[3] > y:
                    continue
                if all(candidate[3] <= old[1] or old[3] <= candidate[1] for old in occupied): box = candidate; break
            if box is None: raise RuntimeError("Style M R7 M15 ป้ายระดับไม่มีพื้นที่ไม่ชนกัน")
            occupied.append(box)
            draw.rounded_rectangle(box, radius=4, fill=color, outline=color, width=1)
            text_origin = (box[0] + 9, box[1] + 4)
            draw.text(text_origin, text, fill="#FFFFFF", font=font)
            labels.append({"side": side, "role": role, "price": values[0], "text": text, "bbox": list(box), "text_bbox": list(draw.textbbox(text_origin, text, font=font)), "y_anchor": y, "label_position": "above_line" if box[3] <= y else "near_line", "content_sized": True, "fill_color": color.upper(), "text_color": "#FFFFFF"})
            lines.append({"side": side, "role": role, "price": values[0], "x_start": latest_x, "x_end": plot[2], "y_anchor": y, "line_style": line_style})
    band_font = _font(16)
    for band in bands:
        box = band["bbox"]
        center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        text = (f"{band['side'].title()} {_price(band['low']):,.0f}"
                f" - {_price(band['high']):,.0f}")
        measured = draw.textbbox((0, 0), text, font=band_font)
        text_origin = (center[0] - (measured[0] + measured[2]) / 2,
                       center[1] - (measured[1] + measured[3]) / 2)
        text_bbox = draw.textbbox(text_origin, text, font=band_font)
        text_contained = bool(
            box[0] <= text_bbox[0] <= text_bbox[2] <= box[2]
            and box[1] <= text_bbox[1] <= text_bbox[3] <= box[3])
        draw.text(text_origin, text,
                  fill=(colors["buy"] if band["side"] == "BUY" else colors["sell"]),
                  font=band_font)
        band.update({"text": text, "text_bbox": list(text_bbox),
                     "text_center": list(center), "centered": True,
                     "text_contained": text_contained,
                     "text_layer": "foreground"})
    cards = _draw_header_cards(draw, plans, header, colors)
    occupied.extend(tuple(card["bbox"]) for card in cards)
    Path(output).parent.mkdir(parents=True, exist_ok=True); image.save(Path(output), format="WEBP", lossless=True, quality=100)
    label_left = min((item["bbox"][0] for item in labels), default=plot[2] - 8)
    return {"path": str(output), "width": WIDTH, "height": HEIGHT, "format": "webp", "role": "m15_entry_plan", "header_title": TITLES["m15_entry_plan"], "display_timeframe": "M15", "decision_timeframe": "H1", "displayed_bars": len(candles), "candles": candles, "summary_cards": cards, "plan_cards": cards, "entry_bands": bands, "execution_lines": lines, "right_labels": labels, "price_ticks": ticks, "time_ticks": time_ticks, "time_tick_overlap_count": time_overlap, "vertical_time_grid": vertical_grid, "header": header, "separate_entry_high_low_count": 0, "label_overlap_count": _overlap([tuple(item) for item in occupied]), "forbidden_tokens": [], "watermark": watermark, "watermark_count": 1, "canonical_facts_sha256": (facts or {}).get("facts_sha256"), "story_source_sha256": story.get("source_sha256"), "visual_source_sha256": (visual_source or {}).get("source_sha256"), "layout": {"plot": list(plot), "data_x_start": data_x_start, "plan_lane": [latest_x, plot[2]], "plan_lane_fraction": round((plot[2] - latest_x) / (plot[2] - plot[0]), 4), "latest_candle_fraction": round((latest_x - plot[0]) / (plot[2] - plot[0]), 4), "internal_label_lane": [label_left, plot[2] - 8], "price_axis": [plot[2] + 12, WIDTH - 12], "domain_padding_fraction": domain_padding}}


def render_role(story, rows, output, *, role, facts=None, visual_source=None,
                locale="th-TH", source_timezone=None):
    if role not in TITLES: raise ValueError(f"unknown Style M visual role: {role}")
    if story.get("contract_version") != "M-PROD/v7" or not rows: raise ValueError("v7 renderer ต้องมี story/rows valid")
    _time_text(rows[0]["at"], locale=locale, source_timezone=source_timezone)
    return (_render_h1 if role == "h1_market_map" else _render_m15)(story, list(rows), Path(output), facts=facts, visual_source=visual_source, locale=locale, source_timezone=source_timezone)


def render_pair(story, h1_rows, m15_rows, output_dir, *, facts=None, visual_source=None, names=None,
                locale="th-TH", source_timezone=None):
    output_dir = Path(output_dir); names = names or {"h1_market_map": "btcusd-style-m-v7-h1-market-map.webp", "m15_entry_plan": "btcusd-style-m-v7-m15-entry-h1-plan.webp"}
    images = {role: render_role(story, rows, output_dir / names[role], role=role, facts=facts, visual_source=visual_source, locale=locale, source_timezone=source_timezone) for role, rows in (("h1_market_map", h1_rows), ("m15_entry_plan", m15_rows))}
    return {"schema": "style-m-two-image-render/v1", "revision": RENDERER_REVISION, "images": images, "image_names": {role: Path(meta["path"]).name for role, meta in images.items()}, "canonical_facts_sha256": (facts or {}).get("facts_sha256"), "story_source_sha256": story.get("source_sha256"), "visual_source_sha256": (visual_source or {}).get("source_sha256")}


def localize_rendered_time_axis(source, metadata, output, *, expected_source_sha256,
                                locale="en-ZA", source_timezone=None):
    """Translate only a verified saved chart's time-label strip.

    Uses recorded tick timestamps and x positions, never reconstructs missing
    candle data. Everything at and above the plot bottom stays pixel-identical.
    """
    from copy import deepcopy

    source = Path(source); output = Path(output)
    if source.resolve() == output.resolve() or output.exists():
        raise ValueError("localised chart requires a new output path")
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected_source_sha256:
        raise ValueError("source chart hash mismatch")
    result = deepcopy(metadata)
    if result.get("role") not in TITLES or not result.get("time_ticks"):
        raise ValueError("saved renderer tick metadata required")
    image = Image.open(source).convert("RGB")
    if image.size != (WIDTH, HEIGHT):
        raise ValueError("source chart dimensions differ")
    plot = result["layout"]["plot"]; y0 = plot[3] + 8
    if not 0 < y0 < HEIGHT - 45:
        raise ValueError("time label strip is outside the canvas")
    ticks = result["time_ticks"]
    if len(ticks) != (H1_TIME_TICKS if result["role"] == "h1_market_map" else M15_TIME_TICKS):
        raise ValueError("incomplete source tick metadata")
    if any(not tick.get("contained_in_canvas") or tick["bbox"][1] < y0
           for tick in ticks):
        raise ValueError("source tick boxes are not confined to the label strip")
    colors = visual_theme.for_chart(); draw = ImageDraw.Draw(image); font = _font(13)
    prepared = []
    for tick in ticks:
        label = _time_text(tick["source_at"], locale=locale, source_timezone=source_timezone)
        box = draw.textbbox((0, 0), label, font=font); width = box[2] - box[0]
        origin = (max(4, min(round(tick["x"] - width / 2), WIDTH - width - 4)), plot[3] + 15)
        bbox = draw.textbbox(origin, label, font=font)
        if bbox[1] < y0 or bbox[2] > WIDTH or bbox[3] >= HEIGHT:
            raise ValueError("translated tick exceeds label strip")
        prepared.append((tick, label, origin, bbox))
    if _overlap([item[3] for item in prepared]):
        raise ValueError("translated time ticks overlap")
    draw.rectangle((0, y0, WIDTH, HEIGHT), fill=colors["canvas"])
    for tick, label, origin, bbox in prepared:
        draw.text(origin, label, fill=colors["axis"], font=font)
        tick.update(label=label, bbox=list(bbox), contained_in_canvas=True)
    if locale == "en-ZA":
        draw.text((plot[0], plot[3] + 40), "Time: UTC+07:00 | Price: USD",
                  fill=colors["axis"], font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="WEBP", lossless=True, quality=100)
    result.update(path=str(output), display_locale=locale,
                  time_axis_timezone=source_timezone, price_unit="USD",
                  time_tick_overlap_count=0,
                  source_image_sha256=expected_source_sha256,
                  translation_method="verified_time_label_strip_only",
                  unchanged_pixel_region=[0, 0, WIDTH, y0])
    return result


def render(story, rows, output, *args, role=None, facts=None):
    del args
    if role is not None:
        return render_role(story, rows, output, role=role, facts=facts)
    # Historical callers used the single-image entry point and consumed plan
    # card metadata. Keep that adapter stable while R6 callers use explicit
    # roles and the paired API.
    meta = render_role(story, rows, output, role="m15_entry_plan", facts=facts)
    meta["header_title"] = "BTCUSD · H1"
    return meta


__all__ = ["WIDTH", "HEIGHT", "VISIBLE_BARS", "PRICE_TICKS", "M15_PRICE_TICKS", "RENDERER_REVISION", "TITLES", "render", "render_role", "render_pair"]
