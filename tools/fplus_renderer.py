"""One deterministic composite WebP renderer for BTCUSD F+."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont
from tools.chart_renderer import NOTO_SANS_THAI_BOLD, NOTO_SANS_THAI_REGULAR


WIDTH, HEIGHT = 1200, 675


def describe_render(selected_plan: Mapping[str, Any]) -> dict[str, Any]:
    plan = dict(selected_plan)
    if plan.get("selection") == "NO_TRADE":
        levels: list[dict[str, Any]] = []
    else:
        levels = [
            {"kind": "entry", "value": deepcopy(plan.get("entry_zone"))},
            {"kind": "stop", "value": plan.get("stop_loss")},
            {"kind": "target", "value": plan.get("take_profit_1")},
        ]
    return {
        "selection": plan.get("selection"),
        "direction": plan.get("direction"),
        "entry_zone": deepcopy(plan.get("entry_zone")),
        "stop_loss": plan.get("stop_loss"),
        "take_profit_1": plan.get("take_profit_1"),
        "trade_levels": levels,
    }


@lru_cache(maxsize=16)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load the Repo-bundled Thai font; never fall back to a tofu-producing font."""
    path = NOTO_SANS_THAI_BOLD if bold else NOTO_SANS_THAI_REGULAR
    if not path.is_file():
        raise FileNotFoundError(f"ไม่พบฟอนต์ไทยบังคับสำหรับ F+: {path}")
    try:
        font = ImageFont.truetype(str(path), size=size)
    except OSError as exc:
        raise RuntimeError(f"เปิดฟอนต์ไทยบังคับสำหรับ F+ ไม่ได้: {path}") from exc
    family, _style = font.getname()
    if family != "Noto Sans Thai":
        raise RuntimeError(f"ไฟล์ฟอนต์ F+ ไม่ใช่ Noto Sans Thai: {family}")
    return font


def _fmt(value: Any) -> str:
    return f"{float(value):,.2f}".rstrip("0").rstrip(".")


def render_webp(
    selected_plan: Mapping[str, Any], snapshot: Mapping[str, Any], target: str | Path,
) -> str:
    del snapshot  # Snapshot is provenance only; all displayed decisions come from SelectedPlan.
    plan = dict(selected_plan)
    target_path = Path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (WIDTH, HEIGHT), "#0d1420")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 92), fill="#172538")
    draw.text((54, 24), "BTCUSD F+ DAILY PLAN", font=_font(38, True), fill="#f5f7fb")
    draw.text((900, 33), str(plan.get("trade_date_bangkok", "")), font=_font(22), fill="#a9bdd3")
    draw.rounded_rectangle((50, 125, 1150, 615), radius=24, fill="#121d2b", outline="#2a3c50", width=2)
    selection = str(plan.get("selection", "NO_TRADE"))
    accent = "#f0b44c" if selection == "NO_TRADE" else "#50d6a0"
    draw.text((85, 155), f"Selected: {selection}", font=_font(34, True), fill=accent)
    if selection == "NO_TRADE":
        draw.text((85, 235), "NO-TRADE / WAIT FOR CLOSED-BAR CONFIRMATION", font=_font(26, True), fill="#f3d18a")
        draw.text((85, 292), str(plan.get("bias_h4", "")), font=_font(22), fill="#d7e1ec")
        draw.text((85, 337), str(plan.get("trigger_m15", "")), font=_font(22), fill="#d7e1ec")
        draw.text((85, 405), str(plan.get("news_notice", "")), font=_font(20), fill="#9fb2c7")
    else:
        zone = plan["entry_zone"]
        cards = [
            ("ENTRY ZONE", f"{_fmt(zone['low'])} - {_fmt(zone['high'])}", "#5cb8ff"),
            ("STOP", _fmt(plan["stop_loss"]), "#ff6b75"),
            ("TARGET 1", _fmt(plan["take_profit_1"]), "#50d6a0"),
            ("RR", _fmt(plan["rr"]), "#f0b44c"),
        ]
        for index, (label, value, color) in enumerate(cards):
            left = 85 + (index % 2) * 515
            top = 230 + (index // 2) * 145
            draw.rounded_rectangle((left, top, left + 470, top + 105), radius=16, fill="#192839")
            draw.text((left + 24, top + 15), label, font=_font(18, True), fill="#94a8bd")
            draw.text((left + 24, top + 48), value, font=_font(30, True), fill=color)
    draw.text((85, 560), "H4 bias  |  H1 setup  |  M30 evidence  |  M15 trigger", font=_font(20), fill="#8198af")
    image.save(target_path, "WEBP", quality=82, method=6)
    if target_path.stat().st_size > 204_800:
        image.save(target_path, "WEBP", quality=65, method=6)
    return str(target_path)
