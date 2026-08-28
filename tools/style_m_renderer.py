"""Deterministic one-image renderer for BTCUSD Style M."""

from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tools import image_output, style_m_story


WIDTH, HEIGHT = 1920, 1080
ROOT = Path(__file__).resolve().parents[1]
FONT_REGULAR = ROOT / "assets/fonts/NotoSansThai/NotoSansThai-Regular.ttf"
FONT_BOLD = ROOT / "assets/fonts/NotoSansThai/NotoSansThai-Bold.ttf"


class RendererContractError(RuntimeError):
    """The Style M visual cannot be rendered truthfully."""


def _font(size: int, bold: bool = False):
    path = FONT_BOLD if bold else FONT_REGULAR
    if not path.is_file():
        raise RendererContractError(f"ไม่พบ font: {path}")
    return ImageFont.truetype(str(path), size=size)


def _rgba(color: str, alpha: int = 255):
    value = color.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4)) + (alpha,)


def _dashed(draw, points, *, fill, width=4, dash=13):
    for start, end in zip(points, points[1:]):
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        if length <= 0:
            continue
        for index in range(0, int(length // dash) + 1, 2):
            left = min(1.0, index * dash / length)
            right = min(1.0, (index + 1) * dash / length)
            draw.line((start[0] + (end[0] - start[0]) * left,
                       start[1] + (end[1] - start[1]) * left,
                       start[0] + (end[0] - start[0]) * right,
                       start[1] + (end[1] - start[1]) * right), fill=fill, width=width)


def _arrow_head(draw, start, end, *, fill, size=18):
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    left = (end[0] - size * math.cos(angle - math.pi / 6),
            end[1] - size * math.sin(angle - math.pi / 6))
    right = (end[0] - size * math.cos(angle + math.pi / 6),
             end[1] - size * math.sin(angle + math.pi / 6))
    draw.polygon((end, left, right), fill=fill)


def _curve_points(start, control1, control2, end, steps=72):
    result = []
    for index in range(steps + 1):
        t = index / steps
        mt = 1 - t
        result.append((mt ** 3 * start[0] + 3 * mt ** 2 * t * control1[0]
                       + 3 * mt * t ** 2 * control2[0] + t ** 3 * end[0],
                       mt ** 3 * start[1] + 3 * mt ** 2 * t * control1[1]
                       + 3 * mt * t ** 2 * control2[1] + t ** 3 * end[1]))
    return result


def _trendline(story: dict, rows: list[dict], *, px, py, visible_start: int):
    highs = [item for item in story["pivots"]["highs"] if item["index"] >= visible_start]
    best = None
    for left in highs:
        for right in highs:
            gap = right["index"] - left["index"]
            if gap >= 12 and left["price"] > right["price"]:
                if best is None or gap > best[0]:
                    best = (gap, left, right)
    if not best:
        return None
    _, left, right = best
    ax, ay = px(left["index"]), py(left["price"])
    bx, by = px(right["index"]), py(right["price"])
    return {"a": (ax, ay), "b": (bx, by), "left": left, "right": right,
            "slope": (by - ay) / max(1.0, bx - ax)}


def render(story: dict, rows: list[dict], output_path: Path) -> dict:
    style_m_story.validate(story)
    output = Path(output_path)
    if output.suffix.lower() != ".webp":
        raise RendererContractError("Style M image ต้องเป็น .webp")
    indexed_rows = []
    for index, row in enumerate(rows):
        item = dict(row)
        item.setdefault("index", index)
        indexed_rows.append(item)
    visible = indexed_rows[-120:]
    if len(visible) < 60:
        raise RendererContractError("แท่ง H1 สำหรับภาพไม่พอ")
    plan = story.get("plan")
    levels = [row[key] for row in visible for key in ("low", "high")]
    if plan:
        levels.extend(plan[key] for key in ("sl", "entry_low", "entry_high", "tp1", "tp2"))
    span = max(levels) - min(levels)
    if span <= 0:
        raise RendererContractError("ช่วงราคาเป็นศูนย์")
    padding = max(span * 0.08, story["indicators"]["atr14"] * 0.5)
    price_min, price_max = min(levels) - padding, max(levels) + padding
    # The header is intentionally a single compact row.  With the old bottom
    # summary and disclaimer removed, the chart can use almost the full canvas.
    plot = (72, 96, 1596, 1040)
    x0, y0, x1, y1 = plot
    future_slots = 24
    slot = (x1 - x0) / (len(visible) + future_slots)
    visible_start = len(indexed_rows) - len(visible)

    def px(global_index):
        return x0 + (global_index - visible_start + 0.5) * slot

    def py(price):
        return y1 - (float(price) - price_min) / (price_max - price_min) * (y1 - y0)

    # Draw RGBA overlays onto an RGB canvas so alpha is actually blended with
    # white.  Converting an RGBA canvas at the end merely dropped alpha and made
    # every intended pastel zone render as a dark, fully saturated block.
    image = Image.new("RGB", (WIDTH, HEIGHT), "#FFFFFF")
    draw = ImageDraw.Draw(image, "RGBA")
    title = "BTCUSD · H1 VISUAL DAILY PLAN"
    title_font = _font(36, True)
    draw.text((72, 28), title, font=title_font, fill="#111827")
    title_box = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_box[2] - title_box[0]
    badge_color = ("#166534" if story["state"] == "PLAN_VALID" else
                   "#1D4ED8" if story["state"] == "WAIT_H1_CONFIRM" else "#9F1239")
    badge_left = 72 + title_width + 26
    badge = (badge_left, 27, badge_left + 318, 71)
    draw.rounded_rectangle(badge, radius=11, fill="#F8FAFC", outline=badge_color, width=2)
    draw.text((badge_left + 19, 36), story["state"].replace("_", " "),
              font=_font(18, True), fill=badge_color)
    cutoff = f"ข้อมูลถึงแท่งปิด H1 {story['cutoff'][8:10]}/{story['cutoff'][5:7]}/{story['cutoff'][:4]} 11:00 น."
    box = draw.textbbox((0, 0), cutoff, font=_font(18))
    draw.text((1848 - (box[2] - box[0]), 39), cutoff, font=_font(18), fill="#475569")
    draw.rounded_rectangle((x0, y0, 1872, y1), radius=18, fill="#FFFFFF", outline="#CBD5E1", width=2)
    for index in range(7):
        yy = y0 + index * (y1 - y0) / 6
        draw.line((x0, yy, x1, yy), fill="#E5E7EB", width=1)
        draw.text((1618, yy - 12), f"{price_max - index * (price_max - price_min) / 6:,.0f}",
                  font=_font(17), fill="#64748B")
    for index in range(0, len(visible) + future_slots + 1, 12):
        xx = x0 + index * slot
        draw.line((xx, y0, xx, y1), fill="#F1F5F9", width=1)

    # Price-occupancy proxy: count closes per price bin. Source volume is unavailable.
    bins = 72
    counts = [0] * bins
    for row in visible:
        bin_index = max(0, min(bins - 1, int((row["close"] - price_min)
                                             / (price_max - price_min) * bins)))
        counts[bin_index] += 1
    maximum = max(counts) or 1
    bin_height = (y1 - y0) / bins
    for index, count in enumerate(counts):
        if not count:
            continue
        yy = y1 - (index + 1) * bin_height
        # Return to the original light green/grey treatment while using more,
        # thinner bins. This is price occupancy, not exchange-reported volume.
        bar_color = "#16A34A" if index % 3 else "#64748B"
        bar_alpha = 55
        draw.rectangle((x0 + 2, yy + 1, x0 + 18 + 170 * count / maximum,
                        yy + bin_height - 1), fill=_rgba(bar_color, bar_alpha))

    # Light structural zones from latest confirmed pivots.
    for pivot in (story["pivots"]["highs"][-2:] + story["pivots"]["lows"][-2:]):
        yy = py(pivot["price"])
        draw.rectangle((300, yy - 12, x1, yy + 12), fill=_rgba("#C084B4", 35),
                       outline=_rgba("#A855A0", 90), width=1)

    # Plan zones are conditional; NO PLAN and INVALIDATED never receive them.
    last_x = px(visible[-1]["index"])
    rail_left, rail_right = last_x + slot * 2, x1 - slot
    if plan:
        entry_low_y, entry_high_y = py(plan["entry_low"]), py(plan["entry_high"])
        sl_y, tp1_y, tp2_y = py(plan["sl"]), py(plan["tp1"]), py(plan["tp2"])
        if story["side"] == "BUY":
            draw.rectangle((rail_left, tp2_y, rail_right, entry_high_y), fill=_rgba("#22C55E", 38),
                           outline="#86D9A1", width=2)
            draw.rectangle((rail_left, entry_low_y, rail_right, sl_y), fill=_rgba("#EF4444", 36),
                           outline="#F2A3A3", width=2)
        else:
            draw.rectangle((rail_left, entry_low_y, rail_right, tp2_y), fill=_rgba("#22C55E", 38),
                           outline="#86D9A1", width=2)
            draw.rectangle((rail_left, sl_y, rail_right, entry_high_y), fill=_rgba("#EF4444", 36),
                           outline="#F2A3A3", width=2)
        draw.rectangle((rail_left, min(entry_low_y, entry_high_y), rail_right,
                        max(entry_low_y, entry_high_y)), fill=_rgba("#64748B", 28),
                       outline="#94A3B8", width=2)

    for row in visible:
        cx = px(row["index"])
        color = "#16A34A" if row["close"] >= row["open"] else "#DC2626"
        draw.line((cx, py(row["high"]), cx, py(row["low"])), fill=color, width=2)
        top, bottom = sorted((py(row["open"]), py(row["close"])))
        bottom = max(bottom, top + 2)
        draw.rectangle((cx - slot * 0.24, top, cx + slot * 0.24, bottom), fill=color, outline=color)

    trend = _trendline(story, indexed_rows, px=px, py=py, visible_start=visible_start)
    breakout = None
    if trend:
        end_x = min(last_x + slot * 1.2, x1 - slot * 2)
        end_y = trend["a"][1] + trend["slope"] * (end_x - trend["a"][0])
        draw.line((*trend["a"], end_x, end_y), fill="#111827", width=3)
        for row in visible:
            if row["index"] <= trend["right"]["index"]:
                continue
            candle_x = px(row["index"])
            trend_y = trend["a"][1] + trend["slope"] * (candle_x - trend["a"][0])
            if py(row["close"]) < trend_y:
                breakout = (candle_x, trend_y)
                break
    if breakout:
        bx, by = breakout
        draw.ellipse((bx - 46, by - 46, bx + 46, by + 46), fill=_rgba("#F59E0B", 45),
                     outline="#D97706", width=3)
        text = "ทำลายเส้นแนวโน้ม"
        font = _font(18, True)
        text_box = draw.textbbox((0, 0), text, font=font)
        width = text_box[2] - text_box[0] + 30
        tx, ty = min(x1 - width, bx + 60), min(y1 - 50, by + 70)
        draw.line((bx + 28, by + 28, tx, ty + 12), fill="#D97706", width=3)
        draw.rounded_rectangle((tx, ty, tx + width, ty + 42), radius=9,
                               fill="#FFF7D6", outline="#D97706", width=2)
        draw.text((tx + 15, ty + 8), text, font=font, fill="#6B3B00")

    if plan:
        labels = (("TP2", plan["tp2"], "#16A34A"), ("TP1", plan["tp1"], "#16A34A"),
                  ("ENTRY", (plan["entry_low"] + plan["entry_high"]) / 2, "#475569"),
                  ("SL", plan["sl"], "#DC2626"))
        font = _font(18, True)
        label_height = 39
        label_gap = 8
        label_items = []
        for name, price, color in labels:
            label = (f"ENTRY {plan['entry_low']:,.0f}–{plan['entry_high']:,.0f}"
                     if name == "ENTRY" else f"{name} {price:,.0f}")
            text_box = draw.textbbox((0, 0), label, font=font)
            ideal = max(y0 + 8, min(y1 - label_height - 8,
                                    py(price) - label_height / 2))
            label_items.append({"name": name, "price": price, "color": color,
                                "label": label, "width": text_box[2] - text_box[0] + 24,
                                "ideal": ideal})

        # Resolve labels from top to bottom, then pull the stack back inside the
        # plot.  Entry and SL can be only a few pixels apart in price; the elbow
        # connector keeps each displaced box tied to its exact level.
        ordered = sorted(label_items, key=lambda item: item["ideal"])
        cursor = y0 + 8
        for item in ordered:
            item["top"] = max(item["ideal"], cursor)
            cursor = item["top"] + label_height + label_gap
        cursor = y1 - label_height - 8
        for item in reversed(ordered):
            item["top"] = min(item["top"], cursor)
            cursor = item["top"] - label_gap - label_height

        label_boxes = {}
        for item in label_items:
            yy = py(item["price"])
            ly = item["top"]
            center_y = ly + label_height / 2
            draw.line((rail_left, yy, 1598, yy), fill=item["color"], width=2)
            draw.line((1598, yy, 1612, center_y, 1620, center_y),
                      fill=item["color"], width=2)
            draw.rounded_rectangle((1620, ly, 1620 + item["width"], ly + label_height),
                                   radius=8, fill=item["color"])
            draw.text((1632, ly + 6), item["label"], font=font, fill="#FFFFFF")
            label_boxes[item["name"]] = [1620, round(ly, 2),
                                          round(1620 + item["width"], 2),
                                          round(ly + label_height, 2)]

        # No blue projection arrow and no numbered target badges in Style M.
        chart_height = y1 - y0
        curve = _curve_points((420, y0 + chart_height * 0.55),
                              (600, y0 + chart_height * 0.88),
                              (900, y0 + chart_height * 0.89),
                              (max(1050, breakout[0] - 20) if breakout else 1120,
                               min(y0 + chart_height * 0.70,
                                   breakout[1] + 40) if breakout
                               else y0 + chart_height * 0.62))
        draw.line(curve, fill=_rgba("#DC2626", 180), width=4, joint="curve")
        _arrow_head(draw, curve[-2], curve[-1], fill=_rgba("#DC2626", 200), size=18)
    else:
        notice_top = y0 + (y1 - y0) * 0.70
        draw.rounded_rectangle((1060, notice_top, 1545, notice_top + 90),
                               radius=18, fill="#FFF1F2",
                               outline="#FB7185", width=2)
        draw.text((1092, notice_top + 20), "NO PLAN — รอโครงสร้าง H1 รอบใหม่",
                  font=_font(23, True), fill="#9F1239")
    output.parent.mkdir(parents=True, exist_ok=True)
    rgb = image.convert("RGB")
    for quality in (88, 84, 80, 76, 72, 68):
        buffer = BytesIO()
        rgb.save(buffer, format="WEBP", quality=quality, method=6)
        if len(buffer.getvalue()) <= image_output.MAX_IMAGE_BYTES:
            output.write_bytes(buffer.getvalue())
            image_output.verify(output)
            return {"path": output.name, "bytes": output.stat().st_size,
                    "width": WIDTH, "height": HEIGHT, "format": "webp",
                    "state": story["state"], "price_occupancy": True,
                    "occupancy_palette": "green_gray_light",
                    "occupancy_bins": bins,
                    "candle_body_ratio": 0.48,
                    "header_layout": "inline",
                    "bottom_summary": False,
                    "footer_disclaimer": False,
                    "plot_bounds": list(plot),
                    "blue_projection_arrow": False,
                    "target_number_badges": False,
                    "label_boxes": label_boxes if plan else {},
                    "source_volume_available": False}
    raise RendererContractError("Style M WebP เกินเพดาน 200 KB")


__all__ = ["HEIGHT", "RendererContractError", "WIDTH", "render"]
