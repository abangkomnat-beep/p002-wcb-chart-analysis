"""Compact deterministic Style M v6 chart renderer."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1920, 1080
BG = "#ffffff"


def _font(size: int):
    for name in ("C:/Windows/Fonts/LeelawUI.ttf", "C:/Windows/Fonts/tahoma.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(story: dict, rows: list[dict], output: Path) -> dict:
    if not rows or story.get("state") != "SCENARIOS_READY":
        raise ValueError("v6 renderer ต้องมี story และ rows ที่ valid")
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    title_font, body_font, small_font = _font(36), _font(24), _font(20)
    draw.text((60, 38), "BTCUSD H1 · Donchian 24H + ATR14 + ADX14", fill="#111827", font=title_font)
    draw.text((60, 88), "ADX วัดความแรงของการเคลื่อนไหว ไม่บอกทิศราคา", fill="#475569", font=body_font)

    plot = (80, 150, 1450, 900)
    adx_box = (1510, 150, 1840, 900)
    visible = rows[-120:]
    levels = [float(r["low"]) for r in visible] + [float(r["high"]) for r in visible]
    levels += [float(story["donchian"]["upper"]), float(story["donchian"]["lower"])]
    for plan in story["scenarios"].values():
        levels += [float(plan[k]) for k in ("trigger", "entry_low", "entry_high", "sl", "tp1", "tp2")]
    lo, hi = min(levels), max(levels)
    pad = max((hi - lo) * 0.08, float(story["indicators"]["atr14"]) * 0.5)
    lo, hi = lo - pad, hi + pad
    x0, y0, x1, y1 = plot

    def xy(index: int, price: float):
        x = x0 + (index - visible[0]["index"]) / max(1, len(visible) - 1) * (x1 - x0)
        y = y1 - (price - lo) / (hi - lo) * (y1 - y0)
        return int(x), int(y)

    draw.rectangle(plot, outline="#cbd5e1", width=2)
    upper_y = xy(visible[-1]["index"], story["donchian"]["upper"])[1]
    lower_y = xy(visible[-1]["index"], story["donchian"]["lower"])[1]
    draw.rectangle((x0, upper_y, x1, lower_y), fill="#eff6ff", outline=None)
    draw.line((x0, upper_y, x1, upper_y), fill="#2563eb", width=4)
    draw.line((x0, lower_y, x1, lower_y), fill="#2563eb", width=4)
    draw.text((x0 + 12, upper_y - 32), f"Donchian upper {story['donchian']['upper']:,.2f}", fill="#1d4ed8", font=small_font)
    draw.text((x0 + 12, lower_y + 8), f"Donchian lower {story['donchian']['lower']:,.2f}", fill="#1d4ed8", font=small_font)

    slot = (x1 - x0) / max(1, len(visible))
    candle_w = max(3, int(slot * 0.55))
    for row in visible:
        index = int(row["index"])
        xc = int(x0 + (index - visible[0]["index"]) * slot + slot / 2)
        yo = xy(index, float(row["open"]))[1]
        yc = xy(index, float(row["close"]))[1]
        yh = xy(index, float(row["high"]))[1]
        yl = xy(index, float(row["low"]))[1]
        color = "#15803d" if row["close"] >= row["open"] else "#b91c1c"
        draw.line((xc, yh, xc, yl), fill=color, width=2)
        draw.rectangle((xc - candle_w // 2, min(yo, yc), xc + candle_w // 2, max(yo, yc)), fill=color)

    colors = {"LONG": "#166534", "SHORT": "#b91c1c"}
    for key, plan in story["scenarios"].items():
        color = colors[plan["side"]]
        for field, label, width in (("trigger", "Trigger", 3), ("sl", "SL", 2), ("tp1", "TP1", 2), ("tp2", "TP2", 2)):
            yy = xy(visible[-1]["index"], float(plan[field]))[1]
            draw.line((x0, yy, x1, yy), fill=color, width=width)
            draw.text((x1 - 190, yy - 26), f"{label} {float(plan[field]):,.2f}", fill=color, font=small_font)
        ey0 = xy(visible[-1]["index"], float(plan["entry_high"]))[1]
        ey1 = xy(visible[-1]["index"], float(plan["entry_low"]))[1]
        draw.rectangle((x0, min(ey0, ey1), x1, max(ey0, ey1)), outline=color, width=2)

    draw.rectangle(adx_box, fill="#f8fafc", outline="#cbd5e1", width=2)
    adx = float(story["indicators"]["adx14"])
    draw.text((1540, 185), "ADX14", fill="#111827", font=title_font)
    draw.text((1540, 240), f"{adx:.1f}", fill="#7c3aed", font=_font(48))
    draw.text((1540, 305), str(story["indicators"]["adx_regime"]), fill="#475569", font=body_font)
    draw.text((1540, 355), "ความแรงเท่านั้น", fill="#475569", font=body_font)
    draw.text((1540, 390), "ไม่บอกทิศ", fill="#475569", font=body_font)
    draw.line((1540, 520, 1810, 520), fill="#94a3b8", width=2)
    draw.text((1540, 530), "20  ตลาดแกว่ง", fill="#64748b", font=small_font)
    draw.line((1540, 640, 1810, 640), fill="#94a3b8", width=2)
    draw.text((1540, 650), "25  เทรนด์แข็งแรง", fill="#64748b", font=small_font)
    draw.text((60, 950), f"Close {float(story['latest']['close']):,.2f} · ATR14 {float(story['indicators']['atr14']):,.2f} · cutoff {story['cutoff']}", fill="#475569", font=body_font)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="WEBP", lossless=True, quality=100)
    return {"path": str(output), "width": WIDTH, "height": HEIGHT, "format": "webp"}


__all__ = ["WIDTH", "HEIGHT", "render"]
