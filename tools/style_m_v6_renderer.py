"""Deterministic reader-first Style M v6 H1 chart renderer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from tools import visual_theme


WIDTH, HEIGHT = 1920, 1080
M_COLORS = visual_theme.for_chart()
BG = M_COLORS["bg"]
VISIBLE_BARS = 48
PRICE_TICKS = 7
TIME_TICKS = 6
LEFT_CANDLE_PADDING = 1.0
RIGHT_CANDLE_PADDING = 2.5
PUBLIC_TITLE = "BTCUSD · H1"


def _font(size: int):
    for name in ("C:/Windows/Fonts/LeelawUI.ttf", "C:/Windows/Fonts/tahoma.ttf",
                 "arial.ttf"):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _time_label(value: object) -> str:
    text = str(value).replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return str(value)[:16]
    return stamp.strftime("%d/%m %H:%M")


def _spread_y(items: list[dict], *, top: int, bottom: int,
              gap: int = 34) -> list[dict]:
    ordered = sorted((dict(item) for item in items), key=lambda item: item["anchor_y"])
    if not ordered:
        return []
    positions = [max(top, min(bottom, int(item["anchor_y"]))) for item in ordered]
    for index in range(1, len(positions)):
        positions[index] = max(positions[index], positions[index - 1] + gap)
    overflow = positions[-1] - bottom
    if overflow > 0:
        positions = [value - overflow for value in positions]
    for index in range(len(positions) - 2, -1, -1):
        positions[index] = min(positions[index], positions[index + 1] - gap)
    for item, label_y in zip(ordered, positions):
        item["label_y"] = int(label_y)
    return ordered


def _overlap_count(boxes: list[tuple[int, int, int, int]]) -> int:
    count = 0
    for index, left in enumerate(boxes):
        for right in boxes[index + 1:]:
            separated = (left[2] <= right[0] or right[2] <= left[0]
                         or left[3] <= right[1] or right[3] <= left[1])
            if not separated:
                count += 1
    return count


def render(story: dict, rows: list[dict], output: Path) -> dict:
    if not rows or story.get("state") != "SCENARIOS_READY":
        raise ValueError("v6 renderer ต้องมี story และ rows ที่ valid")
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    title_font, body_font, small_font = _font(36), _font(21), _font(18)
    # Keep the public heading minimal; scenario semantics remain visible in
    # the BUY/SELL/Trap legend labels below.
    draw.text((60, 36), PUBLIC_TITLE,
              fill=M_COLORS["text"], font=title_font)

    plot = (80, 130, 1760, 790)
    visible = rows[-VISIBLE_BARS:]
    levels = [float(row["low"]) for row in visible]
    levels += [float(row["high"]) for row in visible]
    levels += [float(story["donchian"]["upper"]),
               float(story["donchian"]["lower"])]
    for plan in story["scenarios"].values():
        levels.extend(float(plan[key]) for key in
                      ("trigger", "entry_low", "entry_high"))
    lo, hi = min(levels), max(levels)
    pad = max((hi - lo) * 0.06, float(story["indicators"]["atr14"]) * 0.25)
    lo, hi = lo - pad, hi + pad
    x0, y0, x1, y1 = plot

    candle_span = max(1.0, (len(visible) - 1)
                      + LEFT_CANDLE_PADDING + RIGHT_CANDLE_PADDING)

    def candle_x(index: int) -> int:
        offset = index - visible[0]["index"] + LEFT_CANDLE_PADDING
        return int(x0 + offset / candle_span * (x1 - x0))

    def price_y(price: float) -> int:
        return int(y1 - (price - lo) / (hi - lo) * (y1 - y0))

    draw.rectangle(plot, fill=BG, outline=M_COLORS["border"], width=2)

    upper_y = price_y(float(story["donchian"]["upper"]))
    lower_y = price_y(float(story["donchian"]["lower"]))
    draw.rectangle((x0, upper_y, x1, lower_y), fill="#eff6ff")

    trap_top = price_y(float(story["zones"]["trap_zone_high"]))
    trap_bottom = price_y(float(story["zones"]["trap_zone_low"]))
    draw.rectangle((x0, min(trap_top, trap_bottom), x1, max(trap_top, trap_bottom)),
                   fill="#F4EBC9", outline=M_COLORS["warning"], width=2)

    entry_zones = []
    entry_fills = {"LONG": "#dcfce7", "SHORT": "#fee2e2"}
    entry_outlines = {"LONG": M_COLORS["buy"], "SHORT": M_COLORS["sell"]}
    for plan in story["scenarios"].values():
        top = price_y(float(plan["entry_high"]))
        bottom = price_y(float(plan["entry_low"]))
        box = (x0, min(top, bottom), x1, max(top, bottom))
        draw.rectangle(box, fill=entry_fills[plan["side"]],
                       outline=entry_outlines[plan["side"]], width=2)
        entry_zones.append({"side": plan["side"], "low": float(plan["entry_low"]),
                            "high": float(plan["entry_high"]), "bbox": list(box)})

    price_axis = []
    for tick in range(PRICE_TICKS):
        price = lo + (hi - lo) * tick / (PRICE_TICKS - 1)
        yy = price_y(price)
        draw.line((x0, yy, x1, yy), fill=M_COLORS["grid"], width=1)
        text = f"{price:,.0f}"
        draw.text((x1 + 12, yy - 10), text, fill=M_COLORS["muted"], font=small_font)
        price_axis.append({"price": price, "y": yy, "label": text})

    time_axis = []
    tick_indexes = sorted({round(index * (len(visible) - 1) / (TIME_TICKS - 1))
                           for index in range(TIME_TICKS)})
    for row_index in tick_indexes:
        row = visible[row_index]
        xx = candle_x(int(row["index"]))
        draw.line((xx, y0, xx, y1), fill=M_COLORS["grid"], width=1)
        label = _time_label(row["at"])
        bbox = draw.textbbox((0, 0), label, font=small_font)
        text_width = bbox[2] - bbox[0]
        draw.text((xx - text_width // 2, y1 + 14), label,
                  fill=M_COLORS["muted"], font=small_font)
        time_axis.append({"at": str(row["at"]), "x": xx, "label": label})

    slot = (x1 - x0) / candle_span
    candle_w = max(5, int(slot * 0.56))
    for row in visible:
        xc = candle_x(int(row["index"]))
        yo, yc = price_y(float(row["open"])), price_y(float(row["close"]))
        yh, yl = price_y(float(row["high"])), price_y(float(row["low"]))
        color = M_COLORS["buy"] if row["close"] >= row["open"] else M_COLORS["sell"]
        draw.line((xc, yh, xc, yl), fill=color, width=2)
        draw.rectangle((xc - candle_w // 2, min(yo, yc),
                        xc + candle_w // 2, max(yo, yc)), fill=color)

    draw.line((x0, upper_y, x1, upper_y), fill=M_COLORS["info"], width=3)
    draw.line((x0, lower_y, x1, lower_y), fill=M_COLORS["info"], width=3)

    trigger_items = []
    for plan in story["scenarios"].values():
        color = M_COLORS["buy"] if plan["side"] == "LONG" else M_COLORS["sell"]
        side = "BUY" if plan["side"] == "LONG" else "SELL"
        yy = price_y(float(plan["trigger"]))
        draw.line((x0, yy, x1, yy), fill=color, width=3)
        trigger_items.append({"side": plan["side"], "value": float(plan["trigger"]),
                              "anchor_y": yy,
                              "text": f"{side} Trigger {float(plan['trigger']):,.0f}",
                              "color": color})

    trigger_boxes = []
    laid_out_triggers = _spread_y(trigger_items, top=y0 + 70, bottom=y1 - 30)
    for item in laid_out_triggers:
        label_y = item["label_y"]
        box = (x1 - 270, label_y - 14, x1 - 12, label_y + 14)
        trigger_boxes.append(box)
        draw.rounded_rectangle(box, radius=5, fill=BG,
                               outline=item["color"], width=2)
        draw.text((box[0] + 10, label_y - 10), item["text"],
                  fill=item["color"], font=small_font)

    reference_boxes = [
        (x0 + 10, upper_y - 30, x0 + 420, upper_y - 2),
        (x0 + 10, lower_y + 2, x0 + 425, lower_y + 30),
    ]
    reference_texts = [
        f"Buy-side ref · Donchian upper {story['donchian']['upper']:,.0f}",
        f"Sell-side ref · Donchian lower {story['donchian']['lower']:,.0f}",
    ]
    for box, text in zip(reference_boxes, reference_texts):
        draw.rounded_rectangle(box, radius=5, fill=BG,
                               outline=M_COLORS["info"], width=2)
        draw.text((box[0] + 8, box[1] + 4), text, fill=M_COLORS["info"], font=small_font)

    legend_boxes = []
    legends = [
        ("BUY Entry Zone", "#E3F3EC", M_COLORS["buy"], 210),
        ("SELL Entry Zone", "#FBE7E5", M_COLORS["sell"], 220),
        (f"Trap Zone {story['zones']['trap_zone_low']:,.0f}–"
         f"{story['zones']['trap_zone_high']:,.0f}", "#F4EBC9", M_COLORS["warning"], 300),
    ]
    legend_gap = 10
    legend_total_width = sum(item[3] for item in legends) + legend_gap * (len(legends) - 1)
    legend_x = x1 - legend_total_width
    for text, fill, outline, width in legends:
        box = (legend_x, 42, legend_x + width, 74)
        legend_boxes.append(box)
        draw.rounded_rectangle(box, radius=6, fill=fill, outline=outline, width=2)
        draw.text((box[0] + 10, box[1] + 5), text, fill=outline, font=small_font)
        legend_x = box[2] + legend_gap

    cards = []
    card_specs = [
        (story["scenarios"]["long"], "BUY", (80, 870, 920, 1025),
         "#E3F3EC", M_COLORS["buy"], "เหนือ"),
        (story["scenarios"]["short"], "SELL", (960, 870, 1800, 1025),
         "#FBE7E5", M_COLORS["sell"], "ต่ำกว่า"),
    ]
    for plan, side, box, fill, outline, direction in card_specs:
        draw.rounded_rectangle(box, radius=12, fill=fill, outline=outline, width=3)
        title = f"{side} PLAN · รอแท่ง H1 ปิด{direction} {float(plan['trigger']):,.0f}"
        entry_price = (float(plan["entry_high"]) if plan["side"] == "LONG"
                       else float(plan["entry_low"]))
        row1 = (f"จุดเข้าเมื่อ Retest {entry_price:,.0f}"
                f"   ·   SL {float(plan['sl']):,.0f}")
        row2 = (f"TP1 {float(plan['tp1']):,.0f}"
                f"   ·   TP2 {float(plan['tp2']):,.0f}")
        title_font_card = _font(27)
        card_body_font = _font(25)
        center_x = (box[0] + box[2]) // 2
        text_positions = [
            (center_x, box[1] + 34),
            (center_x, box[1] + 82),
            (center_x, box[1] + 126),
        ]
        draw.text(text_positions[0], title, fill=outline,
                  font=title_font_card, anchor="mm")
        draw.text(text_positions[1], row1, fill=M_COLORS["muted"],
                  font=card_body_font, anchor="mm")
        draw.text(text_positions[2], row2, fill=M_COLORS["muted"],
                  font=card_body_font, anchor="mm")
        text_bboxes = [
            list(draw.textbbox(text_positions[0], title,
                               font=title_font_card, anchor="mm")),
            list(draw.textbbox(text_positions[1], row1,
                               font=card_body_font, anchor="mm")),
            list(draw.textbbox(text_positions[2], row2,
                               font=card_body_font, anchor="mm")),
        ]
        cards.append({"side": plan["side"], "trigger": float(plan["trigger"]),
                      "entry_low": float(plan["entry_low"]),
                      "entry_high": float(plan["entry_high"]),
                      "display_entry": entry_price,
                      "sl": float(plan["sl"]), "tp1": float(plan["tp1"]),
                      "tp2": float(plan["tp2"]), "bbox": list(box),
                      "text_bboxes": text_bboxes})

    visual_boxes = trigger_boxes + reference_boxes + legend_boxes + [
        tuple(card["bbox"]) for card in cards]
    overlap_count = _overlap_count(visual_boxes)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="WEBP", lossless=True, quality=100)
    return {
        "path": str(output), "width": WIDTH, "height": HEIGHT, "format": "webp",
        "theme": {"schema": visual_theme.SCHEMA, "version": visual_theme.VERSION},
        "label_overlap_count": overlap_count,
        "plan_cards": cards,
        "trigger_labels": [{"side": item["side"], "value": item["value"],
                            "anchor_y": item["anchor_y"],
                            "label_y": item["label_y"], "bbox": list(box)}
                           for item, box in zip(laid_out_triggers, trigger_boxes)],
        "reference_labels": {
            "buy_side": story["zones"]["buy_side_liquidity_reference"],
            "sell_side": story["zones"]["sell_side_liquidity_reference"],
        },
        "trap_zone": {"low": story["zones"]["trap_zone_low"],
                      "high": story["zones"]["trap_zone_high"]},
        "entry_zones": entry_zones,
        "price_axis": price_axis,
        "time_axis": time_axis,
        "layout": {
            "plot": list(plot), "visible_bars": len(visible),
            "plan_label_rail": None, "adx_panel": None,
            "legend_boxes": [list(box) for box in legend_boxes],
            "candle_x_range": [candle_x(int(visible[0]["index"])),
                               candle_x(int(visible[-1]["index"]))],
            "candle_padding_slots": {"left": LEFT_CANDLE_PADDING,
                                     "right": RIGHT_CANDLE_PADDING},
        },
    }


__all__ = ["WIDTH", "HEIGHT", "PUBLIC_TITLE", "VISIBLE_BARS", "PRICE_TICKS", "TIME_TICKS",
           "LEFT_CANDLE_PADDING", "RIGHT_CANDLE_PADDING", "render"]
