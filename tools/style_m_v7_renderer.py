"""Deterministic local Style M v7 chart renderer."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from tools import visual_theme

WIDTH, HEIGHT = 1920, 1080
VISIBLE_BARS, PRICE_TICKS, TIME_TICKS = 48, 7, 6
PUBLIC_TITLE = "BTCUSD · H1"


def _font(size):
    for name in ("C:/Windows/Fonts/LeelawUI.ttf", "C:/Windows/Fonts/tahoma.ttf", "arial.ttf"):
        try: return ImageFont.truetype(name, size=size)
        except OSError: pass
    return ImageFont.load_default()


def _overlap(boxes):
    return sum(1 for i, a in enumerate(boxes) for b in boxes[i+1:]
               if not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]))


def render(story: dict, rows: list[dict], output: Path) -> dict:
    if story.get("contract_version") != "M-PROD/v7" or not rows:
        raise ValueError("v7 renderer ต้องมี story/rows valid")
    colors = visual_theme.for_chart()
    image = Image.new("RGB", (WIDTH, HEIGHT), colors["bg"])
    draw = ImageDraw.Draw(image)
    header = visual_theme.draw_pil_edge_to_edge_header(image, PUBLIC_TITLE, plot_left=80,
                                                       font_factory=_font, header_height=108,
                                                       underline_height=5)
    plot = (80, 170, 1760, 810)
    visible = rows[-VISIBLE_BARS:]
    values = [float(x[k]) for x in visible for k in ("low", "high")]
    values += [float(story["donchian"][k]) for k in ("lower", "upper")]
    for p in story["scenarios"].values():
        values.append(float(p["trigger"]))
        values += [float(p[k]) for k in ("entry_low", "entry_high") if p.get(k) is not None]
    lo, hi = min(values), max(values)
    pad = max((hi - lo) * .08, 1)
    lo, hi = lo - pad, hi + pad
    x0, y0, x1, y1 = plot
    def px(i): return int(x0 + (i - visible[0]["index"] + 1) / (len(visible) + 1) * (x1-x0))
    def py(v): return int(y1 - (float(v)-lo)/(hi-lo)*(y1-y0))
    draw.rectangle(plot, fill=colors["bg"], outline=colors["border"], width=2)
    upper_y, lower_y = py(story["donchian"]["upper"]), py(story["donchian"]["lower"])
    draw.rectangle((x0, upper_y, x1, lower_y), fill="#eff6ff")
    for i, row in enumerate(visible):
        xc = px(row["index"]); yo, yc = py(row["open"]), py(row["close"])
        yh, yl = py(row["high"]), py(row["low"])
        color = colors["buy"] if row["close"] >= row["open"] else colors["sell"]
        draw.line((xc, yh, xc, yl), fill=color, width=2)
        draw.rectangle((xc-5, min(yo,yc), xc+5, max(yo,yc)), fill=color)
    draw.line((x0, upper_y, x1, upper_y), fill=colors["info"], width=3)
    draw.line((x0, lower_y, x1, lower_y), fill=colors["info"], width=3)
    labels, boxes = [], []
    for p in story["scenarios"].values():
        color = colors["buy"] if p["side"] == "LONG" else colors["sell"]
        yy = py(p["trigger"])
        draw.line((x0, yy, x1, yy), fill=color, width=3)
        side = "BUY" if p["side"] == "LONG" else "SELL"
        text = f"{side} Trigger {float(p['trigger']):,.0f}"
        box = (x1-300, max(y0+8, min(y1-40, yy-16)), x1-12, max(y0+40, min(y1-8, yy+16)))
        draw.rounded_rectangle(box, radius=5, fill=colors["bg"], outline=color, width=2)
        draw.text((box[0]+10, box[1]+5), text, fill=color, font=_font(18))
        labels.append({"side": p["side"], "value": p["trigger"], "anchor_y": yy,
                       "label_y": (box[1]+box[3])//2, "bbox": list(box)})
        boxes.append(box)
    cards = []
    for index, p in enumerate(story["scenarios"].values()):
        side = "BUY" if p["side"] == "LONG" else "SELL"
        box = (80 + index*880, 850, 920 + index*880, 1015)
        color = colors["buy"] if p["side"] == "LONG" else colors["sell"]
        draw.rounded_rectangle(box, radius=12, fill=colors["bg"], outline=color, width=3)
        if p["state"] == "NO_PLAN":
            text = f"{side} · NO PLAN · {p['no_plan_reason']}"
            visible_text = [text]
            draw.text(((box[0]+box[2])//2, box[1]+48), text, fill=color, font=_font(21), anchor="mm")
        else:
            text = f"{side} · Entry {p['entry_low']:,.0f}–{p['entry_high']:,.0f} · SL {p['sl']:,.0f}"
            targets = f"TP1 {p['tp1']:,.0f} · TP2 {p['tp2']:,.0f}"
            visible_text = [text, targets]
            draw.text(((box[0]+box[2])//2, box[1]+38), text, fill=color, font=_font(19), anchor="mm")
            draw.text(((box[0]+box[2])//2, box[1]+82), targets, fill=color, font=_font(19), anchor="mm")
        cards.append({"side": p["side"], "state": p["state"], "trigger": p["trigger"],
                      "entry_low": p.get("entry_low"), "entry_high": p.get("entry_high"),
                      "sl": p.get("sl"), "tp1": p.get("tp1"), "tp2": p.get("tp2"),
                      "bbox": list(box), "visible_text": visible_text})
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="WEBP", lossless=True, quality=100)
    return {"path": str(output), "width": WIDTH, "height": HEIGHT, "format": "webp",
            "header_title": PUBLIC_TITLE,
            "label_overlap_count": _overlap(boxes), "plan_cards": cards,
            "trigger_labels": labels, "reference_labels": {"buy_side": story["donchian"]["upper"],
                                                               "sell_side": story["donchian"]["lower"]},
            "layout": {"plot": list(plot), "visible_bars": len(visible),
                       "internal_state_visible_count": 0, "plan_label_rail": None}}


__all__ = ["WIDTH", "HEIGHT", "VISIBLE_BARS", "PRICE_TICKS", "TIME_TICKS", "render"]
