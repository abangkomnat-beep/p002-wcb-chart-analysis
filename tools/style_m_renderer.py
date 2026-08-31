"""Deterministic one-image renderer for BTCUSD Style M."""

from __future__ import annotations

import math
import hashlib
import json
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tools import (image_output, style_m_article_contract as contract, style_m_semantics,
                   style_m_story)


WIDTH, HEIGHT = contract.CANVAS_WIDTH, contract.CANVAS_HEIGHT
ROOT = Path(__file__).resolve().parents[1]
FONT_REGULAR = ROOT / "assets/fonts/NotoSansThai/NotoSansThai-Regular.ttf"
FONT_BOLD = ROOT / "assets/fonts/NotoSansThai/NotoSansThai-Bold.ttf"


class RendererContractError(RuntimeError):
    """The Style M visual cannot be rendered truthfully."""


STATE_LABELS = {
    "NO_PLAN": "รอเงื่อนไข",
    "INVALIDATED": "ทบทวนโครงสร้าง",
    "WAIT_H1_CONFIRM": "รอแท่งยืนยัน",
    "PLAN_VALID": "แผนพร้อมประเมิน",
}


def cutoff_caption(story: dict) -> str:
    """Build the visible cutoff label from the actual closed-H1 timestamp."""
    cutoff = str(story["cutoff"])
    return (f"ข้อมูลถึงแท่งปิด H1 {cutoff[8:10]}/{cutoff[5:7]}/{cutoff[:4]} "
            f"{cutoff[11:16]} น.")


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


def render(story: dict, rows: list[dict], output_path: Path, facts: dict | None = None, *,
           events: list[dict] | None = None, news_report: dict | None = None,
           prior_fingerprint: dict | None = None) -> dict:
    style_m_story.validate(story)
    output = Path(output_path)
    if output.suffix.lower() != ".webp":
        raise RendererContractError("Style M image ต้องเป็น .webp")
    indexed_rows = style_m_semantics.canonicalize_rows(rows)
    visible = indexed_rows[-120:]
    if len(visible) < 60:
        raise RendererContractError("แท่ง H1 สำหรับภาพไม่พอ")
    facts = facts or contract.build(story, indexed_rows)
    contract.validate(facts, story=story, rows=indexed_rows, events=events,
                      news_report=news_report, prior_fingerprint=prior_fingerprint)
    plan = story.get("plan")
    fact_map = facts["facts"]
    semantic = facts["semantic_decision"]
    bindings: list[dict] = []
    draw_trace: list[dict] = []
    bound_claim_ids: set[str] = set()

    def bind(claim_id: str, *, geometry_id: str, rendered_value,
             label_id: str | None = None, anchor_fact_ids: list[str] | None = None,
             draw_geometry: dict | None = None):
        claim = facts["claims"].get(claim_id)
        if not claim or "renderer" not in claim["consumers"] or claim_id in bound_claim_ids:
            return
        bound_claim_ids.add(claim_id)
        trace = {"claim_id": claim_id, "geometry_id": geometry_id,
                 "label_id": label_id, "rendered_value": rendered_value,
                 "draw_geometry": draw_geometry}
        draw_trace.append(trace)
        bindings.append({"binding_id": f"renderer.{geometry_id}", "claim_id": claim_id,
                         "consumer": "renderer", "geometry_id": geometry_id,
                         "label_id": label_id, "rendered_value": rendered_value,
                         "unit": claim["unit"], "timeframe": claim["timeframe"],
                         "at": claim.get("at"),
                         "source_fact_ids": list(claim["source_fact_ids"]),
                         "label": claim["label"],
                         "anchor_fact_ids": list(anchor_fact_ids or []),
                         "draw_geometry": draw_geometry})
    latest_value = float(fact_map.get("market.latest.close", {}).get("value", visible[-1]["close"]))
    if facts is not None and abs(latest_value - float(visible[-1]["close"])) > 1e-6:
        raise RendererContractError("canonical latest close ไม่ตรงแท่ง H1 ที่แสดง")
    visual_state = fact_map.get("plan.state", {}).get("value", story["state"])
    visual_side = fact_map.get("plan.side", {}).get("value", story.get("side"))
    if visual_state not in ("WAIT_H1_CONFIRM", "PLAN_VALID"):
        plan = None
    if plan and facts:
        plan = dict(plan)
        for key in ("entry_low", "entry_high", "sl", "tp1", "tp2"):
            item = fact_map.get(f"plan.{key}")
            if isinstance(item, dict) and item.get("value") is not None:
                plan[key] = item["value"]
    atr_value = float(fact_map.get("market.atr14", {}).get("value", story["indicators"]["atr14"]))
    viewport = fact_map.get("visual.viewport")
    if not isinstance(viewport, dict):
        raise RendererContractError("canonical viewport หาย")
    price_min, price_max = float(viewport["price_min"]), float(viewport["price_max"])
    # The header is intentionally a single compact row.  With the old bottom
    # summary and disclaimer removed, the chart can use almost the full canvas.
    plot = tuple(viewport["plot_bounds"])
    x0, y0, x1, y1 = plot
    future_slots = int(viewport["future_slots"])
    slot = float(viewport["slot"])
    visible_start = int(viewport["visible_start_index"])

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
    badge_color = ("#166534" if visual_state == "PLAN_VALID" else
                   "#1D4ED8" if visual_state == "WAIT_H1_CONFIRM" else "#9F1239")
    badge = contract.STATE_BADGE_BOUNDS
    badge_left = badge[0]
    draw.rounded_rectangle(badge, radius=11, fill="#F8FAFC", outline=badge_color, width=2)
    draw.text((badge_left + 19, 36), STATE_LABELS.get(visual_state, "ตรวจสอบ"),
              font=_font(18, True), fill=badge_color)
    bind("claim.plan.state", geometry_id="badge.plan.state", label_id="label.plan.state",
         rendered_value=visual_state,
         draw_geometry={"kind": "badge", "bounds": list(badge)})
    cutoff = cutoff_caption(story)
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

    # Draw moving-average and latest-close facts from the shared manifest.
    ema20_value = float(fact_map.get("market.ema20", {}).get("value", story["indicators"]["ema20"]))
    ema50_value = float(fact_map.get("market.ema50", {}).get("value", story["indicators"]["ema50"]))
    for value, color, label in ((ema20_value, "#2563EB", "EMA20"), (ema50_value, "#7C3AED", "EMA50")):
        yy = py(value)
        draw.line((x0, yy, x1, yy), fill=color, width=2)
        draw.text((x0 + 24, max(y0 + 4, yy - 24)), label, font=_font(16, True), fill=color)
        bind(f"claim.market.{label.lower()}", geometry_id=f"line.{label.lower()}",
             label_id=f"label.{label.lower()}", rendered_value=value,
             draw_geometry={"kind": "horizontal_line",
                            "coordinates": [x0, yy, x1, yy]})
    latest_y = py(latest_value)
    _dashed(draw, ((x0, latest_y), (x1, latest_y)), fill="#0F172A", width=2, dash=10)
    draw.text((x0 + 24, max(y0 + 4, latest_y - 22)), "ปิดล่าสุด", font=_font(16, True), fill="#0F172A")
    bind("claim.market.latest_close", geometry_id="line.latest_close",
         label_id="label.latest_close", rendered_value=latest_value,
         draw_geometry={"kind": "dashed_horizontal_line",
                        "coordinates": [x0, latest_y, x1, latest_y]})
    draw.text((72, 73), f"ปิด {latest_value:,.2f} · ATR14 {atr_value:,.2f}",
              font=_font(15), fill="#475569")
    bind("claim.market.atr14", geometry_id="label.atr14", label_id="label.atr14",
         rendered_value=atr_value,
         draw_geometry={"kind": "text", "position": [72.0, 73.0]})

    # Price-occupancy proxy: count closes per price bin. Source volume is unavailable.
    bins = 72
    counts = [0] * bins
    for row in visible:
        bin_index = max(0, min(bins - 1, int((row["close"] - price_min)
                                             / (price_max - price_min) * bins)))
        counts[bin_index] += 1
    maximum = max(counts) or 1
    bin_height = (y1 - y0) / bins
    occupancy_rectangles = []
    for index, count in enumerate(counts):
        if not count:
            continue
        yy = y1 - (index + 1) * bin_height
        # Return to the original light green/grey treatment while using more,
        # thinner bins. This is price occupancy, not exchange-reported volume.
        bar_color = "#16A34A" if index % 3 else "#64748B"
        bar_alpha = 55
        rectangle = [x0 + 2, yy + 1, x0 + 18 + 170 * count / maximum,
                     yy + bin_height - 1]
        draw.rectangle(tuple(rectangle), fill=_rgba(bar_color, bar_alpha))
        occupancy_rectangles.append(rectangle)
    bind("claim.occupancy.disclosure", geometry_id="histogram.price_occupancy",
         label_id=None, rendered_value="closed_h1_price_occupancy_not_volume",
         draw_geometry={"kind": "rectangles", "rectangles": occupancy_rectangles})

    # Light structural zones from latest confirmed pivots.
    for pivot_kind, pivots in (("high", story["pivots"]["highs"][-2:]),
                               ("low", story["pivots"]["lows"][-2:])):
        for pivot in pivots:
            pivot_id = f"structure.pivot.{pivot_kind}.{pivot['index']}"
            if facts is not None and pivot_id not in fact_map:
                raise RendererContractError(f"canonical fact หาย: {pivot_id}")
            pivot_value = fact_map.get(pivot_id, {}).get("value", pivot["price"])
            yy = py(pivot_value)
            rectangle = [300.0, yy - 12, x1, yy + 12]
            draw.rectangle(tuple(rectangle), fill=_rgba("#C084B4", 35),
                           outline=_rgba("#A855A0", 90), width=1)
            bind(f"claim.{pivot_id}", geometry_id=f"zone.{pivot_id}",
                 rendered_value=pivot_value,
                 draw_geometry={"kind": "rectangle", "bounds": rectangle})

    # Primary support/resistance are semantic facts used by the article too;
    # draw their canonical levels explicitly so the parity report describes
    # values that are genuinely present in the image.
    for fact_id, color, label in (("zone.support.primary", "#0F766E", "แนวรับ"),
                                  ("zone.resistance.primary", "#B45309", "แนวต้าน")):
        zone = fact_map.get(fact_id)
        if not isinstance(zone, dict):
            continue
        zone_lines = []
        for bound in ("low", "high"):
            if zone.get(bound) is None:
                continue
            yy = py(zone[bound])
            _dashed(draw, ((300, yy), (x1, yy)), fill=color, width=2, dash=12)
            zone_lines.append([300.0, yy, x1, yy])
        if zone.get("high") is not None:
            draw.text((x0 + 24, max(y0 + 4, py(zone["high"]) - 20)), label,
                      font=_font(16, True), fill=color)
        bind(f"claim.{fact_id}", geometry_id=fact_id, label_id=f"label.{fact_id}",
             rendered_value={"low": zone["low"], "high": zone["high"]},
             draw_geometry={"kind": "dashed_horizontal_lines",
                            "coordinates": zone_lines})

    # Plan zones are conditional; NO PLAN and INVALIDATED never receive them.
    last_x = px(visible[-1]["index"])
    rail_left, rail_right = last_x + slot * 2, x1 - slot
    if plan:
        plan_rectangles = []
        entry_low_y, entry_high_y = py(plan["entry_low"]), py(plan["entry_high"])
        sl_y, tp1_y, tp2_y = py(plan["sl"]), py(plan["tp1"]), py(plan["tp2"])
        if visual_side == "BUY":
            reward_rectangle = [rail_left, tp2_y, rail_right, entry_high_y]
            risk_rectangle = [rail_left, entry_low_y, rail_right, sl_y]
            draw.rectangle(tuple(reward_rectangle), fill=_rgba("#22C55E", 38),
                           outline="#86D9A1", width=2)
            draw.rectangle(tuple(risk_rectangle), fill=_rgba("#EF4444", 36),
                           outline="#F2A3A3", width=2)
        else:
            reward_rectangle = [rail_left, entry_low_y, rail_right, tp2_y]
            risk_rectangle = [rail_left, sl_y, rail_right, entry_high_y]
            draw.rectangle(tuple(reward_rectangle), fill=_rgba("#22C55E", 38),
                           outline="#86D9A1", width=2)
            draw.rectangle(tuple(risk_rectangle), fill=_rgba("#EF4444", 36),
                           outline="#F2A3A3", width=2)
        entry_rectangle = [rail_left, min(entry_low_y, entry_high_y), rail_right,
                           max(entry_low_y, entry_high_y)]
        draw.rectangle(tuple(entry_rectangle), fill=_rgba("#64748B", 28),
                       outline="#94A3B8", width=2)
        plan_rectangles.extend([reward_rectangle, risk_rectangle, entry_rectangle])
        bind("claim.plan.side", geometry_id="zone.plan.side", rendered_value=visual_side,
             draw_geometry={"kind": "rectangles", "rectangles": plan_rectangles})

    for row in visible:
        cx = px(row["index"])
        color = "#16A34A" if row["close"] >= row["open"] else "#DC2626"
        draw.line((cx, py(row["high"]), cx, py(row["low"])), fill=color, width=2)
        top, bottom = sorted((py(row["open"]), py(row["close"])))
        bottom = max(bottom, top + 2)
        draw.rectangle((cx - slot * 0.24, top, cx + slot * 0.24, bottom), fill=color, outline=color)

    canonical_trend = semantic["trendline"]
    trend = None
    breakout = None
    if canonical_trend["status"] == "SHOWN":
        anchor_ids = canonical_trend["anchor_fact_ids"]
        anchor_indices = [int(item.rsplit(".", 1)[-1]) for item in anchor_ids]
        anchor_prices = [float(fact_map[item]["value"]) for item in anchor_ids]
        trend = {
            "a": (px(anchor_indices[0]), py(anchor_prices[0])),
            "b": (px(anchor_indices[1]), py(anchor_prices[1])),
            "left_index": anchor_indices[0], "right_index": anchor_indices[1],
            "slope": ((py(anchor_prices[1]) - py(anchor_prices[0])) /
                      max(1.0, px(anchor_indices[1]) - px(anchor_indices[0]))),
        }
        end_x = min(last_x + slot * 1.2, x1 - slot * 2)
        end_y = trend["a"][1] + trend["slope"] * (end_x - trend["a"][0])
        trend_coordinates = [trend["a"][0], trend["a"][1], end_x, end_y]
        draw.line(tuple(trend_coordinates), fill="#111827", width=3)
        bind("claim.analysis.trendline", geometry_id="trendline.primary",
             label_id="label.trendline.primary",
             rendered_value={"anchor_fact_ids": list(anchor_ids),
                             "slope_per_bar": canonical_trend["slope_per_bar"],
                             "intercept": canonical_trend["intercept"]},
             anchor_fact_ids=list(anchor_ids),
             draw_geometry={"kind": "line", "coordinates": trend_coordinates,
                            "canonical": {
                                "anchor_fact_ids": list(anchor_ids),
                                "slope_per_bar": canonical_trend["slope_per_bar"],
                                "intercept": canonical_trend["intercept"],
                            }})
        canonical_breakout = semantic["breakout"]
        if canonical_breakout["status"] == "CONFIRMED_UP_BREAK":
            candle_index = int(canonical_breakout["evaluated_candle_fact_id"].rsplit(".", 1)[-1])
            candle_x = px(candle_index)
            trend_y = trend["a"][1] + trend["slope"] * (candle_x - trend["a"][0])
            breakout = (candle_x, trend_y)
    if breakout:
        bx, by = breakout
        marker_bounds = [bx - 46, by - 46, bx + 46, by + 46]
        draw.ellipse(tuple(marker_bounds), fill=_rgba("#F59E0B", 45),
                     outline="#D97706", width=3)
        text = "ทำลายเส้นแนวโน้ม"
        font = _font(18, True)
        width = contract.BREAKOUT_LABEL_WIDTH
        tx, ty = min(x1 - width, bx + 60), min(y1 - 50, by + 70)
        connector = [bx + 28, by + 28, tx, ty + 12]
        label_bounds = [tx, ty, tx + width, ty + 42]
        draw.line(tuple(connector), fill="#D97706", width=3)
        draw.rounded_rectangle(tuple(label_bounds), radius=9,
                               fill="#FFF7D6", outline="#D97706", width=2)
        draw.text((tx + 15, ty + 8), text, font=font, fill="#6B3B00")
        bind("claim.analysis.breakout", geometry_id="annotation.breakout.primary",
             label_id="label.breakout.primary", rendered_value="CONFIRMED_UP_BREAK",
             draw_geometry={"kind": "annotation", "marker_bounds": marker_bounds,
                            "connector": connector, "label_bounds": label_bounds,
                            "canonical": {
                                "status": canonical_breakout["status"],
                                "evaluated_candle_fact_id": canonical_breakout[
                                    "evaluated_candle_fact_id"],
                                "evaluated_close": canonical_breakout["evaluated_close"],
                                "line_value_at_candle": canonical_breakout[
                                    "line_value_at_candle"],
                            }})

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
            claim_key = {"ENTRY": None, "SL": "claim.plan.sl",
                         "TP1": "claim.plan.tp1", "TP2": "claim.plan.tp2"}[item["name"]]
            if claim_key:
                bind(claim_key, geometry_id=f"line.plan.{item['name'].lower()}",
                     label_id=f"label.plan.{item['name'].lower()}",
                     rendered_value=item["price"],
                     draw_geometry={"kind": "horizontal_line",
                                    "coordinates": [rail_left, yy, 1598.0, yy]})
        bind("claim.plan.entry_low", geometry_id="zone.plan.entry.low",
             label_id="label.plan.entry", rendered_value=plan["entry_low"],
             draw_geometry={"kind": "zone_boundary",
                            "coordinates": [rail_left, entry_low_y, rail_right, entry_low_y]})
        bind("claim.plan.entry_high", geometry_id="zone.plan.entry.high",
             label_id="label.plan.entry", rendered_value=plan["entry_high"],
             draw_geometry={"kind": "zone_boundary",
                            "coordinates": [rail_left, entry_high_y, rail_right, entry_high_y]})

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
        draw.text((1092, notice_top + 20), "รอเงื่อนไข — รอโครงสร้าง H1 รอบใหม่",
                  font=_font(23, True), fill="#9F1239")
    output.parent.mkdir(parents=True, exist_ok=True)
    rgb = image.convert("RGB")
    for quality in (88, 84, 80, 76, 72, 68):
        buffer = BytesIO()
        rgb.save(buffer, format="WEBP", quality=quality, method=6)
        if len(buffer.getvalue()) <= image_output.MAX_IMAGE_BYTES:
            output.write_bytes(buffer.getvalue())
            image_output.verify(output)
            image_sha256 = hashlib.sha256(output.read_bytes()).hexdigest()
            visual_trace_sha256 = hashlib.sha256(json.dumps(
                draw_trace, sort_keys=True, ensure_ascii=False,
                separators=(",", ":")).encode("utf-8")).hexdigest()
            artifact_trace_sha256 = hashlib.sha256(
                f"{image_sha256}:{visual_trace_sha256}".encode("utf-8")).hexdigest()
            displayed_fact_ids = ["market.latest.close", "market.ema20", "market.ema50",
                                  "market.atr14", "occupancy.price_bins", "plan.state"]
            displayed_fact_ids += [f"structure.pivot.high.{pivot['index']}"
                                   for pivot in story["pivots"]["highs"][-2:]]
            displayed_fact_ids += [f"structure.pivot.low.{pivot['index']}"
                                   for pivot in story["pivots"]["lows"][-2:]]
            if canonical_trend["status"] == "SHOWN" and trend:
                displayed_fact_ids.append("analysis.trendline")
            displayed_fact_ids += [key for key in ("zone.support.primary", "zone.resistance.primary")
                                   if key in fact_map]
            if plan:
                displayed_fact_ids += [f"plan.{key}" for key in
                                       ("side", "entry_low", "entry_high", "sl", "tp1", "tp2")
                                       if f"plan.{key}" in fact_map]
            rendered_fact_values = {key: fact_map[key] for key in displayed_fact_ids if key in fact_map}
            required_renderer = {claim_id for claim_id, claim in facts["claims"].items()
                                 if claim.get("required") and "renderer" in claim.get("consumers", [])}
            missing_renderer = sorted(required_renderer - bound_claim_ids)
            if missing_renderer:
                raise RendererContractError(f"renderer binding ไม่ครบ: {missing_renderer}")
            return {"path": output.name, "bytes": output.stat().st_size,
                    "width": WIDTH, "height": HEIGHT, "format": "webp",
                    "schema": "style-m-renderer-claim-report/v1",
                    "claim_report_schema": "style-m-renderer-claim-report/v1",
                    "facts_sha256": facts["facts_sha256"],
                    "bindings": bindings,
                    "draw_trace": draw_trace,
                    "visual_trace_sha256": visual_trace_sha256,
                    "artifact": {"sha256": image_sha256, "bytes": output.stat().st_size,
                                 "width": WIDTH, "height": HEIGHT, "format": "webp",
                                 "visual_trace_sha256": visual_trace_sha256,
                                 "artifact_trace_sha256": artifact_trace_sha256},
                    "trendline_geometry": (canonical_trend if trend else None),
                    "breakout_annotation": (semantic["breakout"] if breakout else None),
                    "state_label": STATE_LABELS.get(visual_state, "ตรวจสอบ"), "price_occupancy": True,
                    "occupancy_palette": "green_gray_light",
                    "occupancy_bins": bins,
                    "candle_body_ratio": 0.48,
                    "header_layout": "inline",
                    "bottom_summary": False,
                    "footer_disclaimer": False,
                    "plot_bounds": list(plot),
                    "viewport_policy": dict(viewport),
                    "blue_projection_arrow": False,
                    "target_number_badges": False,
                    "label_boxes": label_boxes if plan else {},
                    "source_volume_available": False,
                    "displayed_fact_ids": sorted(set(displayed_fact_ids)),
                    "annotation_ids": (["trendline.breakout"] if breakout else []),
                    "rendered_fact_values": rendered_fact_values,
                    "displayed_levels": ({key: fact_map[key] for key in fact_map
                                          if key.startswith(("zone.", "plan."))} if facts else {})}
    raise RendererContractError("Style M WebP เกินเพดาน 200 KB")


__all__ = ["HEIGHT", "RendererContractError", "STATE_LABELS", "WIDTH", "render"]
