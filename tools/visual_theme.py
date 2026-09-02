"""Versioned WCB visual tokens shared by the D, E and L render paths.

The theme owns visual treatment only.  It deliberately has no market values,
labels, routes or rendering decisions, so changing it cannot alter the factual
layer.  Renderers import this module instead of copying brand colours.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = REPO_ROOT / "config" / "visual_theme.json"
SCHEMA = "wcb-visual-theme-v1"
VERSION = "1.0.0"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
REQUIRED = {
    "brand": {"deep_green", "header_green", "gold"},
    "surface": {"canvas", "plot", "panel", "grid", "axis", "text", "muted", "border"},
    "semantic": {"buy", "sell", "stop_loss", "take_profit", "warning", "info", "neutral", "indicator"},
}
PREMIUM_REQUIRED = {
    "surface": {"canvas", "plot", "panel", "panel_alt", "grid", "axis", "text", "muted", "border"},
    "semantic": {"buy", "sell", "stop_loss", "take_profit", "warning", "info", "neutral", "indicator"},
    "component": {"gold", "ivory", "header_start", "header_mid", "header_end",
                  "callout", "callout_strong", "danger_panel"},
}


class ThemeContractError(ValueError):
    """Theme is missing, malformed or fails its accessibility contract."""


def _luminance(color: str) -> float:
    rgb = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
              for value in rgb]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    """Return WCAG contrast ratio for two six-digit hex colours."""
    if not _HEX.fullmatch(foreground) or not _HEX.fullmatch(background):
        raise ThemeContractError("สีต้องเป็นรูปแบบ #RRGGBB")
    light, dark = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def validate_theme(theme: Mapping[str, object]) -> dict:
    if not isinstance(theme, Mapping) or theme.get("schema") != SCHEMA:
        raise ThemeContractError(f"schema ต้องเป็น {SCHEMA}")
    if theme.get("version") != VERSION:
        raise ThemeContractError(f"version ต้องเป็น {VERSION}")
    for group, keys in REQUIRED.items():
        values = theme.get(group)
        if not isinstance(values, Mapping) or not keys.issubset(values):
            missing = sorted(keys - set(values or {}))
            raise ThemeContractError(f"theme.{group} ขาด token: {missing}")
        for key in keys:
            value = values[key]
            if not isinstance(value, str) or not _HEX.fullmatch(value):
                raise ThemeContractError(f"theme.{group}.{key} ต้องเป็น #RRGGBB")
    premium = theme.get("premium")
    if not isinstance(premium, Mapping):
        raise ThemeContractError("theme.premium ต้องเป็น object")
    for group, keys in PREMIUM_REQUIRED.items():
        values = premium.get(group)
        if not isinstance(values, Mapping) or not keys.issubset(values):
            missing = sorted(keys - set(values or {}))
            raise ThemeContractError(f"theme.premium.{group} ขาด token: {missing}")
        for key in keys:
            value = values[key]
            if not isinstance(value, str) or not _HEX.fullmatch(value):
                raise ThemeContractError(
                    f"theme.premium.{group}.{key} ต้องเป็น #RRGGBB")
    accessibility = theme.get("accessibility")
    if not isinstance(accessibility, Mapping):
        raise ThemeContractError("theme.accessibility ต้องเป็น object")
    normal_min = float(accessibility.get("normal_text_min", 4.5))
    large_min = float(accessibility.get("large_text_min", 3.0))
    if normal_min < 4.5 or large_min < 3:
        raise ThemeContractError("เกณฑ์ contrast ต่ำกว่าขั้นต่ำ WCAG")
    surface = theme["surface"]
    for key in ("text", "muted", "axis"):
        if contrast_ratio(surface[key], surface["plot"]) < normal_min:
            raise ThemeContractError(f"contrast ของ surface.{key} ต่ำกว่าเกณฑ์")
    for key in ("buy", "sell", "stop_loss", "take_profit", "warning", "info", "neutral", "indicator"):
        if contrast_ratio(theme["semantic"][key], surface["plot"]) < normal_min:
            raise ThemeContractError(f"contrast ของ semantic.{key} ต่ำกว่าเกณฑ์")
    # Semantic colours must not silently alias brand chrome; shape/text still
    # carries meaning, but a duplicate token would make the palette ambiguous.
    brand_values = set(theme["brand"].values())
    if brand_values.intersection(theme["semantic"].values()):
        raise ThemeContractError("semantic colors ต้องแยกจาก brand chrome")
    premium_surface = premium["surface"]
    for key in ("text", "muted", "axis"):
        if contrast_ratio(premium_surface[key], premium_surface["plot"]) < normal_min:
            raise ThemeContractError(
                f"contrast ของ premium.surface.{key} ต่ำกว่าเกณฑ์")
    for key, value in premium["semantic"].items():
        if contrast_ratio(value, premium_surface["plot"]) < normal_min:
            raise ThemeContractError(
                f"contrast ของ premium.semantic.{key} ต่ำกว่าเกณฑ์")
    if contrast_ratio(premium["component"]["ivory"],
                      premium["component"]["callout"]) < 7.0:
        raise ThemeContractError("premium central callout contrast ต้องไม่น้อยกว่า 7:1")
    return dict(theme)


def load_theme(path: Path | None = None) -> dict:
    source = path or DEFAULT_PATH
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ThemeContractError(f"อ่าน visual theme ไม่ได้: {exc}") from None
    return validate_theme(payload)


THEME = load_theme()
BRAND = THEME["brand"]
SURFACE = THEME["surface"]
SEMANTIC = THEME["semantic"]
PREMIUM = THEME["premium"]


def for_chart(*, include_indicators: bool = True) -> dict[str, str]:
    """Return renderer-friendly aliases without exposing mutable config."""
    values = {
        "bg": SURFACE["plot"], "plot": SURFACE["plot"],
        "canvas": SURFACE["canvas"], "panel": SURFACE["panel"],
        "grid": SURFACE["grid"], "axis": SURFACE["axis"], "text": SURFACE["text"],
        "muted": SURFACE["muted"], "border": SURFACE["border"],
        "up": SEMANTIC["buy"], "down": SEMANTIC["sell"], "buy": SEMANTIC["buy"],
        "sell": SEMANTIC["sell"], "sl": SEMANTIC["stop_loss"],
        "stop_loss": SEMANTIC["stop_loss"], "tp": SEMANTIC["take_profit"],
        "take_profit": SEMANTIC["take_profit"], "warning": SEMANTIC["warning"],
        "info": SEMANTIC["info"], "neutral": SEMANTIC["neutral"],
    }
    if include_indicators:
        values["indicator"] = SEMANTIC["indicator"]
    return values


def for_premium_chart(*, include_indicators: bool = True) -> dict[str, str]:
    """Return dark WCB chart aliases without changing the shared light theme.

    Style D/L opt in explicitly.  Keeping this separate prevents a visual
    redesign from silently changing the E/M render paths that still use
    :func:`for_chart`.
    """
    surface = PREMIUM["surface"]
    semantic = PREMIUM["semantic"]
    component = PREMIUM["component"]
    values = {
        "bg": surface["plot"], "plot": surface["plot"],
        "canvas": surface["canvas"], "panel": surface["panel"],
        "panel_alt": surface["panel_alt"], "grid": surface["grid"],
        "axis": surface["axis"], "text": surface["text"],
        "muted": surface["muted"], "border": surface["border"],
        "up": semantic["buy"], "down": semantic["sell"],
        "buy": semantic["buy"], "sell": semantic["sell"],
        "sl": semantic["stop_loss"], "stop_loss": semantic["stop_loss"],
        "tp": semantic["take_profit"], "take_profit": semantic["take_profit"],
        "warning": semantic["warning"], "info": semantic["info"],
        "neutral": semantic["neutral"], "gold": component["gold"],
        "ivory": component["ivory"], "callout": component["callout"],
        "callout_strong": component["callout_strong"],
        "header_start": component["header_start"],
        "header_mid": component["header_mid"],
        "header_end": component["header_end"],
        "danger_panel": component["danger_panel"],
    }
    if include_indicators:
        values["indicator"] = semantic["indicator"]
    return values


def premium_text_patch_overlap_report(figure, *, gap_pixels: float = 0.0) -> dict:
    """Measure premium text boxes only, excluding annotation leader arrows.

    Matplotlib ``Annotation.get_window_extent`` includes the arrow patch, which
    creates false overlaps when a leader intentionally crosses a factual line.
    This gate measures the visible rounded text patch when present and expands
    each patch by half ``gap_pixels`` before pairwise intersection testing.
    """
    from matplotlib.transforms import Bbox

    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    artists = [artist for artist in figure.findobj()
               if str(artist.get_gid() or "").startswith("premium-label:")]
    boxes = []
    half_gap = float(gap_pixels) / 2.0
    for artist in artists:
        patch = getattr(artist, "get_bbox_patch", lambda: None)()
        bbox = (patch.get_window_extent(renderer)
                if patch is not None else artist.get_window_extent(renderer))
        expanded = Bbox.from_extents(
            bbox.x0 - half_gap, bbox.y0 - half_gap,
            bbox.x1 + half_gap, bbox.y1 + half_gap,
        )
        boxes.append({"role": artist.get_gid(), "bbox": bbox, "expanded": expanded})
    overlaps = []
    for index, left in enumerate(boxes):
        for right in boxes[index + 1:]:
            x_overlap = min(left["expanded"].x1, right["expanded"].x1) - max(
                left["expanded"].x0, right["expanded"].x0)
            y_overlap = min(left["expanded"].y1, right["expanded"].y1) - max(
                left["expanded"].y0, right["expanded"].y0)
            if x_overlap > 0 and y_overlap > 0:
                overlaps.append({
                    "left": left["role"], "right": right["role"],
                    "width_px": round(x_overlap, 2),
                    "height_px": round(y_overlap, 2),
                })
    return {
        "checked": True, "gap_pixels": float(gap_pixels),
        "box_count": len(boxes), "overlap_count": len(overlaps),
        "overlaps": overlaps,
        "boxes": [{"role": item["role"],
                   "bbox_px": [round(item["bbox"].x0, 2), round(item["bbox"].y0, 2),
                               round(item["bbox"].x1, 2), round(item["bbox"].y1, 2)]}
                  for item in boxes],
    }
