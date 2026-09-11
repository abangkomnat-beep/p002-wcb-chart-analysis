"""Versioned WCB visual tokens shared by the D, E and L render paths.

The theme owns visual treatment only.  It deliberately has no market values,
labels, routes or rendering decisions, so changing it cannot alter the factual
layer.  Renderers import this module instead of copying brand colours.
"""

from __future__ import annotations

import hashlib
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
PREMIUM_HEADER_RATIO = 0.09
PREMIUM_PLOT_RATIO = 0.91
PREMIUM_HEADER_HSPACE = 0.018
PREMIUM_HEADER_FONT_SIZE = 20
PREMIUM_HEADER_UNDERLINE_FRACTION = 0.052
WATERMARK_TEXT = "WorldClassBroker"
WATERMARK_WIDTH_TARGET = 0.32
WATERMARK_WIDTH_RANGE = (0.30, 0.35)
WATERMARK_CENTER_X_RANGE = (0.49, 0.51)
WATERMARK_CENTER_Y_RANGE = (0.42, 0.58)
WATERMARK_CHART_COLOR = "#F4F1E7"
WATERMARK_CHART_ALPHA = 0.08
WATERMARK_CALENDAR_COLOR = "#0E2A1D"
WATERMARK_CALENDAR_ALPHA = 0.05
WATERMARK_LIGHT_PLOT_ALPHA = 0.12
MATPLOTLIB_WATERMARK_TRACKING_PX = 2.0


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


def _watermark_contract(*, width: float, height: float, bbox: tuple[float, float,
                              float, float], surface: str,
                        vertical_nudge: float, layer: str,
                        resolved_color: str | None = None,
                        resolved_alpha: float | None = None,
                        palette_role: str | None = None) -> dict:
    if surface not in {"chart", "calendar"}:
        raise ThemeContractError("watermark surface ต้องเป็น chart หรือ calendar")
    if not -0.08 <= vertical_nudge <= 0.08:
        raise ThemeContractError("watermark vertical_nudge ต้องไม่เกิน ±0.08")
    x0, y0, x1, y1 = bbox
    width_ratio = (x1 - x0) / width
    center_x = (x0 + x1) / 2 / width
    center_y = (y0 + y1) / 2 / height
    color = resolved_color or (WATERMARK_CHART_COLOR if surface == "chart"
                               else WATERMARK_CALENDAR_COLOR)
    alpha = (float(resolved_alpha) if resolved_alpha is not None
             else (WATERMARK_CHART_ALPHA if surface == "chart"
                   else WATERMARK_CALENDAR_ALPHA))
    layout = {
        "role": "premium-decoration:watermark",
        "text": WATERMARK_TEXT,
        "count": 1,
        "bbox_px": [round(value, 2) for value in bbox],
        "bbox_width_ratio": round(width_ratio, 4),
        "center_x_ratio": round(center_x, 4),
        "center_y_ratio": round(center_y, 4),
        "color": color,
        "alpha": alpha,
        "rotation": 0,
        "box": False,
        "border": False,
        "shadow": False,
        "path_effect": False,
        "layer": layer,
        "vertical_nudge": vertical_nudge,
        "target_width_ratio": WATERMARK_WIDTH_TARGET,
        "palette_role": palette_role or surface,
    }
    failures = []
    if not WATERMARK_WIDTH_RANGE[0] <= width_ratio <= WATERMARK_WIDTH_RANGE[1]:
        failures.append("width ratio")
    if not WATERMARK_CENTER_X_RANGE[0] <= center_x <= WATERMARK_CENTER_X_RANGE[1]:
        failures.append("center x")
    if not WATERMARK_CENTER_Y_RANGE[0] <= center_y <= WATERMARK_CENTER_Y_RANGE[1]:
        failures.append("center y")
    if surface == "chart":
        if palette_role == "light_plot":
            if not 0.10 <= alpha <= 0.14:
                failures.append("light plot alpha")
        elif not 0.07 <= alpha <= 0.09:
            failures.append("chart alpha")
    if surface == "calendar":
        if palette_role == "dark_calendar":
            if not 0.07 <= alpha <= 0.09:
                failures.append("dark calendar alpha")
        elif not 0.04 <= alpha <= 0.06:
            failures.append("calendar alpha")
    if failures:
        raise ThemeContractError(f"watermark contract failed {failures}: {layout}")
    return layout


def draw_matplotlib_watermark(figure, axes, *, surface: str = "chart",
                              vertical_nudge: float = 0.0,
                              zorder: float = 2.25,
                              surface_aware: bool = False) -> dict:
    """Draw one deterministic tracked watermark below factual artists.

    Matplotlib ``Text`` has no letter-spacing control.  The exact semantic
    string therefore remains as one hidden gid marker while the visible layer
    draws its glyphs individually at a measured two-pixel gap.  This keeps one
    public watermark, avoids inserting whitespace into its text, and exposes
    real (not inferred) tracking metadata.
    """
    from matplotlib.colors import to_hex
    from matplotlib.transforms import Bbox

    background = to_hex(axes.get_facecolor(), keep_alpha=False).upper()
    background_luminance = _luminance(background)
    light_plot_detected = bool(surface == "chart" and background_luminance >= 0.75)
    dark_calendar_detected = bool(
        surface == "calendar" and background_luminance <= 0.20)
    use_light_plot_palette = bool(surface_aware and light_plot_detected)
    use_dark_calendar_palette = bool(surface_aware and dark_calendar_detected)
    color = (WATERMARK_CALENDAR_COLOR if use_light_plot_palette
             else (WATERMARK_CHART_COLOR if use_dark_calendar_palette
                   else (WATERMARK_CHART_COLOR if surface == "chart"
                         else WATERMARK_CALENDAR_COLOR)))
    alpha = (WATERMARK_LIGHT_PLOT_ALPHA if use_light_plot_palette
             else (WATERMARK_CHART_ALPHA if use_dark_calendar_palette
                   else (WATERMARK_CHART_ALPHA if surface == "chart"
                         else WATERMARK_CALENDAR_ALPHA)))
    palette_role = ("light_plot" if use_light_plot_palette
                    else ("dark_calendar" if use_dark_calendar_palette
                          else surface))
    canvas_width = float(figure.bbox.width)
    canvas_height = float(figure.bbox.height)
    artist = axes.text(
        0.5, 0.5 + vertical_nudge, WATERMARK_TEXT,
        transform=figure.transFigure, ha="center", va="center",
        color=color, alpha=alpha, fontsize=48, fontweight="medium",
        rotation=0, zorder=zorder, clip_on=False, visible=False,
    )
    artist.set_gid("premium-decoration:watermark")
    glyphs = []
    for index, character in enumerate(WATERMARK_TEXT):
        glyph = axes.text(
            0.0, 0.5 + vertical_nudge, character,
            transform=figure.transFigure, ha="left", va="center",
            color=color, alpha=alpha, fontsize=48, fontweight="medium",
            rotation=0, zorder=zorder, clip_on=False,
        )
        glyph.set_gid(f"premium-decoration:watermark-glyph:{index:02d}")
        glyphs.append(glyph)

    tracking = float(MATPLOTLIB_WATERMARK_TRACKING_PX)
    font_size = 48.0
    target_width = WATERMARK_WIDTH_TARGET * canvas_width
    renderer = None
    glyph_boxes = []
    for _ in range(3):
        for glyph in glyphs:
            glyph.set_fontsize(font_size)
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        glyph_boxes = [glyph.get_window_extent(renderer) for glyph in glyphs]
        measured_width = (sum(box.width for box in glyph_boxes)
                          + tracking * max(0, len(glyphs) - 1))
        if measured_width <= 0:
            raise ThemeContractError("วัด watermark ไม่ได้")
        font_size *= target_width / measured_width

    for glyph in glyphs:
        glyph.set_fontsize(font_size)
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    glyph_boxes = [glyph.get_window_extent(renderer) for glyph in glyphs]
    total_width = (sum(box.width for box in glyph_boxes)
                   + tracking * max(0, len(glyphs) - 1))
    cursor = figure.bbox.x0 + (canvas_width - total_width) / 2.0
    y_position = 0.5 + vertical_nudge
    inverse = figure.transFigure.inverted()
    for glyph, box in zip(glyphs, glyph_boxes):
        glyph_x = inverse.transform((cursor, figure.bbox.y0))[0]
        glyph.set_position((glyph_x, y_position))
        cursor += box.width + tracking

    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    glyph_boxes = [glyph.get_window_extent(renderer) for glyph in glyphs]
    bbox_obj = Bbox.union(glyph_boxes)
    desired_center = figure.bbox.x0 + canvas_width / 2.0
    center_delta = desired_center - (bbox_obj.x0 + bbox_obj.x1) / 2.0
    if abs(center_delta) > 0.01:
        shift = center_delta / canvas_width
        for glyph in glyphs:
            x, y = glyph.get_position()
            glyph.set_position((x + shift, y))
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        glyph_boxes = [glyph.get_window_extent(renderer) for glyph in glyphs]
        bbox_obj = Bbox.union(glyph_boxes)

    measured_gaps = [
        right.x0 - left.x1
        for left, right in zip(glyph_boxes, glyph_boxes[1:])
    ]
    measured_tracking = (sum(measured_gaps) / len(measured_gaps)
                         if measured_gaps else 0.0)
    if measured_tracking < 1.0:
        raise ThemeContractError(
            f"watermark tracking ต้อง >=1px แต่วัดได้ {measured_tracking:.3f}")
    artist.set_fontsize(font_size)
    layout = _watermark_contract(
        width=canvas_width, height=canvas_height,
        bbox=(bbox_obj.x0, bbox_obj.y0, bbox_obj.x1, bbox_obj.y1),
        surface=surface, vertical_nudge=vertical_nudge,
        layer="above_background_and_zones_below_factual",
        resolved_color=color, resolved_alpha=alpha,
        palette_role=palette_role,
    )
    foreground_rgb = [int(color[index:index + 2], 16) for index in (1, 3, 5)]
    background_rgb = [int(background[index:index + 2], 16) for index in (1, 3, 5)]
    composite_rgb = [round(foreground * alpha + base * (1.0 - alpha))
                     for foreground, base in zip(foreground_rgb, background_rgb)]
    composite = "#" + "".join(f"{value:02X}" for value in composite_rgb)
    effective_contrast = contrast_ratio(composite, background)
    layout.update({
        "backend": "matplotlib",
        "zorder": zorder,
        "font_size_pt": round(font_size, 3),
        "font_weight": "medium",
        "tracking_px": round(measured_tracking, 3),
        "tracking_target_px": tracking,
        "glyph_count": len(glyphs),
        "rendered_color": to_hex(glyphs[0].get_color(), keep_alpha=False).upper(),
        "surface_contrast": {
            "mode": "surface-aware" if surface_aware else "fixed",
            "background_color": background,
            "background_luminance": round(background_luminance, 4),
            "light_plot_detected": light_plot_detected,
            "dark_calendar_detected": dark_calendar_detected,
            "palette_role": palette_role,
            "composited_color": composite,
            "effective_contrast_ratio": round(effective_contrast, 4),
            "visibility_threshold": (
                1.20 if use_light_plot_palette or use_dark_calendar_palette
                else None),
            "visibility_pass": (effective_contrast >= 1.20
                                if use_light_plot_palette
                                or use_dark_calendar_palette else None),
        },
    })
    if ((use_light_plot_palette or use_dark_calendar_palette)
            and effective_contrast < 1.20):
        raise ThemeContractError(
            f"surface-aware watermark contrast ต่ำเกินไป: {effective_contrast:.3f}")
    if (artist.get_bbox_patch() is not None or artist.get_path_effects()
            or any(glyph.get_bbox_patch() is not None or glyph.get_path_effects()
                   for glyph in glyphs)):
        raise ThemeContractError("watermark ต้องไม่มี box/path effect")
    figure._premium_watermark_layout = layout
    return layout


def _pil_rgb(color: str) -> tuple[int, int, int]:
    if not _HEX.fullmatch(color):
        raise ThemeContractError("สี PIL ต้องเป็น #RRGGBB")
    return tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))


def _pil_tracked_width(draw, text: str, font, tracking: int) -> int:
    widths = [draw.textlength(character, font=font) for character in text]
    return int(round(sum(widths) + tracking * max(0, len(text) - 1)))


def draw_pil_watermark(image, *, surface: str = "chart", font_factory,
                       vertical_nudge: float = 0.0,
                       tracking_px: int = 2,
                       surface_aware: bool = False) -> dict:
    """Composite one tracked PIL watermark; caller controls factual z-order."""
    from PIL import Image, ImageDraw

    if image.mode not in {"RGB", "RGBA"}:
        raise ThemeContractError("PIL watermark รองรับภาพ RGB/RGBA เท่านั้น")
    width, height = image.size
    probe = ImageDraw.Draw(image)
    target = width * WATERMARK_WIDTH_TARGET
    low, high = 8, max(12, int(width * 0.2))
    while low < high:
        mid = (low + high + 1) // 2
        candidate = font_factory(mid)
        if _pil_tracked_width(probe, WATERMARK_TEXT, candidate, tracking_px) <= target:
            low = mid
        else:
            high = mid - 1
    font = font_factory(low)
    text_width = _pil_tracked_width(probe, WATERMARK_TEXT, font, tracking_px)
    font_box = probe.textbbox((0, 0), WATERMARK_TEXT, font=font)
    text_height = font_box[3] - font_box[1]
    x0 = int(round((width - text_width) / 2))
    y0 = int(round(height * (0.5 + vertical_nudge) - text_height / 2))
    background_rgb = image.convert("RGB").getpixel((width // 2, height // 2))
    background = "#" + "".join(f"{channel:02X}" for channel in background_rgb)
    background_luminance = _luminance(background)
    light_plot_detected = bool(surface == "chart" and background_luminance >= 0.75)
    use_light_plot_palette = bool(surface_aware and light_plot_detected)
    color = (WATERMARK_CALENDAR_COLOR if use_light_plot_palette
             else (WATERMARK_CHART_COLOR if surface == "chart"
                   else WATERMARK_CALENDAR_COLOR))
    alpha = (WATERMARK_LIGHT_PLOT_ALPHA if use_light_plot_palette
             else (WATERMARK_CHART_ALPHA if surface == "chart"
                   else WATERMARK_CALENDAR_ALPHA))
    palette_role = "light_plot" if use_light_plot_palette else surface
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cursor = float(x0)
    rgba = (*_pil_rgb(color), int(round(alpha * 255)))
    for character in WATERMARK_TEXT:
        draw.text((round(cursor), y0 - font_box[1]), character,
                  fill=rgba, font=font)
        cursor += draw.textlength(character, font=font) + tracking_px
    composed = Image.alpha_composite(image.convert("RGBA"), overlay)
    image.paste(composed.convert(image.mode))
    bbox = (x0, y0, x0 + text_width, y0 + text_height)
    layout = _watermark_contract(
        width=float(width), height=float(height), bbox=bbox, surface=surface,
        vertical_nudge=vertical_nudge,
        layer="above_background_and_zones_below_factual",
        resolved_color=color, resolved_alpha=alpha,
        palette_role=palette_role,
    )
    foreground_rgb = _pil_rgb(color)
    composite_rgb = [round(foreground * alpha + base * (1.0 - alpha))
                     for foreground, base in zip(foreground_rgb, background_rgb)]
    composite = "#" + "".join(f"{value:02X}" for value in composite_rgb)
    effective_contrast = contrast_ratio(composite, background)
    layout.update({
        "backend": "PIL",
        "font_size_px": low,
        "font_weight": "medium",
        "tracking_px": tracking_px,
        "zorder": "caller_draw_order_before_factual_foreground",
        "surface_contrast": {
            "mode": "surface-aware" if surface_aware else "fixed",
            "background_color": background,
            "background_luminance": round(background_luminance, 4),
            "light_plot_detected": light_plot_detected,
            "palette_role": palette_role,
            "composited_color": composite,
            "effective_contrast_ratio": round(effective_contrast, 4),
            "visibility_threshold": 1.20 if use_light_plot_palette else None,
            "visibility_pass": (effective_contrast >= 1.20
                                if use_light_plot_palette else None),
        },
    })
    if use_light_plot_palette and effective_contrast < 1.20:
        raise ThemeContractError(
            f"surface-aware PIL watermark contrast ต่ำเกินไป: "
            f"{effective_contrast:.3f}")
    return layout


def draw_pil_edge_to_edge_header(image, title: str, *, plot_left: int,
                                 font_factory, header_height: int | None = None,
                                 underline_height: int | None = None) -> dict:
    """Draw the R7 header language on a PIL canvas without touching plot data."""
    from PIL import ImageDraw

    width, height = image.size
    header_height = header_height or round(height * 0.10)
    underline_height = underline_height or max(3, min(6, round(width / 384)))
    if header_height <= underline_height or not 0 <= plot_left < width:
        raise ThemeContractError("PIL header geometry ไม่ถูกต้อง")
    draw = ImageDraw.Draw(image)
    start = _pil_rgb(PREMIUM["component"]["header_start"])
    end = _pil_rgb(PREMIUM["component"]["header_end"])
    for x in range(width):
        ratio = x / max(1, width - 1)
        color = tuple(round(left + (right - left) * ratio)
                      for left, right in zip(start, end))
        draw.line((x, 0, x, header_height - underline_height - 1), fill=color)
    gold = PREMIUM["component"]["gold"]
    draw.rectangle((0, header_height - underline_height,
                    width - 1, header_height - 1), fill=gold)
    font_size = max(18, round(width * 0.01875))
    font = font_factory(font_size)
    text_box = draw.textbbox((0, 0), title, font=font)
    text_height = text_box[3] - text_box[1]
    title_y = round((header_height - underline_height - text_height) / 2 - text_box[1])
    draw.text((plot_left, title_y), title,
              fill=PREMIUM["component"]["ivory"], font=font)
    title_bbox = draw.textbbox((plot_left, title_y), title, font=font)
    layout = {
        "role": "premium-decoration:header-face",
        "title": title,
        "title_count": 1,
        "title_bbox_px": list(title_bbox),
        "title_x_px": plot_left,
        "x0_px": 0,
        "x1_px": width,
        "top_gap_px": 0,
        "header_height_px": header_height,
        "header_height_ratio": round(header_height / height, 4),
        "underline_height_px": underline_height,
        "underline_color": gold.upper(),
        "title_color": PREMIUM["component"]["ivory"].upper(),
        "header_start": PREMIUM["component"]["header_start"].upper(),
        "header_end": PREMIUM["component"]["header_end"].upper(),
        "font_size_px": font_size,
        "title_wrap_count": title.count("\n"),
        "title_clipped": bool(title_bbox[0] < 0 or title_bbox[2] > width
                              or title_bbox[1] < 0 or title_bbox[3] > header_height),
    }
    if (layout["title_count"] != 1 or layout["title_wrap_count"]
            or layout["title_clipped"] or not 3 <= underline_height <= 6):
        raise ThemeContractError(f"PIL header contract failed: {layout}")
    return layout


def draw_edge_to_edge_header(figure, header, plot_axes, title: str,
                             colors: Mapping[str, str], *,
                             underline_fraction: float = PREMIUM_HEADER_UNDERLINE_FRACTION,
                             underline_height_px: float | None = None,
                             fontfamily: str | None = None,
                             fontsize: float | None = None):
    """Draw one measured WCB header component across the whole canvas.

    The plot keeps its own inset.  Only the header axes expands to the canvas,
    while the title anchor reuses the plot's left edge in figure coordinates.
    """
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import Rectangle
    import re

    original = header.get_position()
    # Gridspec deliberately stops at ``top=0.97`` so ordinary plot axes keep a
    # quiet outer margin.  The premium header is the one exception: extend its
    # face upward into that margin without changing its lower edge (and thus
    # without moving the underline, plot, or any factual artist).
    extended_height = 1.0 - original.y0
    header.set_position([0.0, original.y0, 1.0, extended_height])
    gradient = LinearSegmentedColormap.from_list(
        "wcb-edge-header",
        [colors["header_start"], colors["header_mid"], colors["header_end"]],
    )
    face = header.imshow(
        [list(range(256))], aspect="auto", extent=(0, 1, 0, 1),
        origin="lower", cmap=gradient, zorder=0,
    )
    face.set_gid("premium-decoration:header-face")
    # Express the underline in the enlarged axes while preserving its exact
    # pre-R6 figure-space height.
    if underline_height_px is None:
        underline_fraction = underline_fraction * original.height / extended_height
    else:
        header_height_px = extended_height * figure.bbox.height
        underline_fraction = underline_height_px / header_height_px
    underline = Rectangle(
        (0, 0), 1, underline_fraction,
        transform=header.transAxes, facecolor=colors["gold"],
        edgecolor="none", linewidth=0, zorder=2,
    )
    underline.set_gid("premium-decoration:header-underline")
    header.add_patch(underline)
    title_kwargs = {}
    if fontfamily is not None:
        title_kwargs["fontfamily"] = fontfamily
    elif re.search(r"[\u0400-\u04ff]", title):
        # The default project font is optimized for Thai and may make
        # Cyrillic headings too short for the responsive legibility gate.
        title_kwargs["fontfamily"] = "Arial"
    effective_fontsize = fontsize or (28.0 if re.search(r"[\u0400-\u04ff]", title)
                                      else PREMIUM_HEADER_FONT_SIZE)
    title_artist = header.text(
        plot_axes.get_position().x0, 0.50, title,
        color=colors["ivory"], fontsize=effective_fontsize,
        fontweight="bold", ha="left", va="center", zorder=3,
        **title_kwargs,
    )
    title_artist.set_gid("premium-decoration:header-title")
    header._premium_original_position = original
    header.set_xlim(0, 1)
    header.set_ylim(0, 1)
    header.set_axis_off()
    return title_artist, face, underline


def draw_header_accessory_card(figure, header, title_artist, underline,
                               text: str, colors: Mapping[str, str], *,
                               role: str, font_size: float = 18.0):
    """Draw and measure one premium status card inside the shared header.

    This is decorative chrome only: it uses axes coordinates and never changes
    the header, plot, or any market-data transform.
    """
    from matplotlib import patheffects
    from matplotlib.colors import to_hex

    shadow_offset_points = (2.0, -2.0)
    shadow_alpha = 0.22
    card = header.text(
        0.97, 0.50, text, transform=header.transAxes,
        color=colors["callout"], fontsize=font_size, fontweight="bold",
        ha="right", va="center", zorder=5,
        bbox={"boxstyle": "round,pad=0.30", "facecolor": colors["canvas"],
              "edgecolor": colors["gold"], "linewidth": 0.9},
    )
    card.set_gid(f"premium-label:header-card:{role}")
    patch = card.get_bbox_patch()
    patch.set_path_effects([
        patheffects.withSimplePatchShadow(
            offset=shadow_offset_points, shadow_rgbFace=colors["header_start"],
            alpha=shadow_alpha),
        patheffects.Normal(),
    ])
    patch.set_gid(f"premium-decoration:header-card:{role}")

    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    canvas = figure.bbox
    header_box = header.get_window_extent(renderer)
    title_box = title_artist.get_window_extent(renderer)
    underline_box = underline.get_window_extent(renderer)
    text_box = card.get_window_extent(renderer)
    card_box = patch.get_window_extent(renderer)
    responsive_scale = 768.0 / canvas.width
    shadow_x_px = shadow_offset_points[0] * figure.dpi / 72.0
    shadow_y_px = abs(shadow_offset_points[1]) * figure.dpi / 72.0
    right_safe = header_box.x1 - card_box.x1 - shadow_x_px
    title_gap = card_box.x0 - title_box.x1
    top_padding = header_box.y1 - card_box.y1
    bottom_padding = card_box.y0 - header_box.y0
    underline_clearance = card_box.y0 - underline_box.y1 - shadow_y_px
    layout = {
        "role": role,
        "text": text,
        "line_count": text.count("\n") + 1,
        "face": to_hex(patch.get_facecolor(), keep_alpha=False).upper(),
        "text_color": to_hex(card.get_color(), keep_alpha=False).upper(),
        "edge": to_hex(patch.get_edgecolor(), keep_alpha=False).upper(),
        "border_width_px": round(patch.get_linewidth() * figure.dpi / 72.0, 2),
        "shadow_color": colors["header_start"].upper(),
        "shadow_alpha": shadow_alpha,
        "shadow_offset_px": [round(shadow_x_px, 2), round(shadow_y_px, 2)],
        "shadow_offset_px_at_768": [
            round(shadow_x_px * responsive_scale, 2),
            round(shadow_y_px * responsive_scale, 2),
        ],
        "contrast": round(contrast_ratio(colors["callout"], colors["canvas"]), 2),
        "leader": False,
        "connector": False,
        "accent_to_plot": False,
        "bbox_px": [round(value, 2) for value in
                    (card_box.x0, card_box.y0, card_box.x1, card_box.y1)],
        "text_bbox_px": [round(value, 2) for value in
                         (text_box.x0, text_box.y0, text_box.x1, text_box.y1)],
        "right_safe_margin_px": round(right_safe, 2),
        "right_safe_margin_px_at_768": round(right_safe * responsive_scale, 2),
        "title_gap_px": round(title_gap, 2),
        "title_gap_px_at_768": round(title_gap * responsive_scale, 2),
        "top_padding_px": round(top_padding, 2),
        "bottom_padding_px": round(bottom_padding, 2),
        "underline_clearance_px": round(underline_clearance, 2),
        "top_padding_px_at_768": round(top_padding * responsive_scale, 2),
        "bottom_padding_px_at_768": round(bottom_padding * responsive_scale, 2),
        "underline_clearance_px_at_768": round(
            underline_clearance * responsive_scale, 2),
        "font_height_px_at_768": round(text_box.height * responsive_scale, 2),
        "contained_in_header": bool(
            card_box.x0 >= header_box.x0 and card_box.x1 + shadow_x_px <= header_box.x1
            and card_box.y0 - shadow_y_px >= header_box.y0
            and card_box.y1 <= header_box.y1),
        "overlaps_title": bool(card_box.overlaps(title_box)),
        "overlaps_underline": bool(card_box.overlaps(underline_box)),
        "clipped": bool(
            card_box.x0 < canvas.x0 or card_box.x1 + shadow_x_px > canvas.x1
            or card_box.y0 - shadow_y_px < canvas.y0 or card_box.y1 > canvas.y1),
    }
    failures = []
    if layout["face"] != "#F4F1E7" or layout["text_color"] != "#0E2A1D":
        failures.append("card palette")
    if layout["edge"] != "#D6B34A" or not 1.0 <= layout["border_width_px"] <= 1.5:
        failures.append("card border")
    if layout["contrast"] < 7.0:
        failures.append("card contrast")
    if (layout["right_safe_margin_px"] < 24
            or layout["right_safe_margin_px_at_768"] < 8
            or layout["title_gap_px"] < 24
            or layout["title_gap_px_at_768"] < 8):
        failures.append("card horizontal clearance")
    if (layout["top_padding_px"] < 12 or layout["bottom_padding_px"] < 12
            or layout["top_padding_px_at_768"] < 4
            or layout["bottom_padding_px_at_768"] < 4
            or layout["underline_clearance_px"] < 8
            or layout["underline_clearance_px_at_768"] < 3):
        failures.append("card vertical clearance")
    if (not layout["contained_in_header"] or layout["overlaps_title"]
            or layout["overlaps_underline"] or layout["clipped"]):
        failures.append("card containment")
    # Cyrillic fallback fonts report smaller pixel metrics at the responsive
    # reference width while remaining fully contained and high contrast.
    if layout["font_height_px_at_768"] < 7 or layout["line_count"] > 2:
        failures.append("card typography")
    if failures:
        raise RuntimeError(f"premium header card failed {failures}: {layout}")
    card._premium_header_card_layout = layout
    return card, layout


def edge_to_edge_header_layout(figure, header, plot_axes, title_artist,
                               underline) -> dict:
    """Measure and fail closed on the shared full-canvas header contract."""
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    canvas = figure.bbox
    header_box = header.get_window_extent(renderer)
    plot_box = plot_axes.get_window_extent(renderer)
    title_box = title_artist.get_window_extent(renderer)
    underline_box = underline.get_window_extent(renderer)
    responsive_scale = 768.0 / canvas.width
    layout = {
        "header_x0_px": round(header_box.x0, 2),
        "header_x1_px": round(header_box.x1, 2),
        "header_width_delta_px": round(abs(header_box.width - canvas.width), 2),
        "header_height_fraction": round(header_box.height / canvas.height, 4),
        "header_y0_px": round(header_box.y0, 2),
        "header_y1_px": round(header_box.y1, 2),
        "header_top_gap_px": round(max(0.0, canvas.y1 - header_box.y1), 2),
        "underline_x0_px": round(underline_box.x0, 2),
        "underline_x1_px": round(underline_box.x1, 2),
        "underline_width_delta_px": round(abs(underline_box.width - canvas.width), 2),
        "underline_height_px": round(underline_box.height, 2),
        "underline_y0_px": round(underline_box.y0, 2),
        "underline_y1_px": round(underline_box.y1, 2),
        "underline_height_px_at_768": round(
            underline_box.height * responsive_scale, 2),
        "title_plot_start_delta_px": round(abs(title_box.x0 - plot_box.x0), 2),
        "title_plot_start_delta_px_at_768": round(
            abs(title_box.x0 - plot_box.x0) * responsive_scale, 2),
        "title_top_padding_px": round(header_box.y1 - title_box.y1, 2),
        "title_bottom_padding_px": round(title_box.y0 - header_box.y0, 2),
        "title_top_padding_px_at_768": round(
            (header_box.y1 - title_box.y1) * responsive_scale, 2),
        "title_bottom_padding_px_at_768": round(
            (title_box.y0 - header_box.y0) * responsive_scale, 2),
        "title_height_px_at_768": round(title_box.height * responsive_scale, 2),
        "title_center_delta_px": round(abs(
            (title_box.y0 + title_box.y1) / 2
            - (header_box.y0 + header_box.y1) / 2), 2),
        "title_center_delta_px_at_768": round(abs(
            (title_box.y0 + title_box.y1) / 2
            - (header_box.y0 + header_box.y1) / 2) * responsive_scale, 2),
        "title_padding_imbalance_px": round(abs(
            (header_box.y1 - title_box.y1)
            - (title_box.y0 - header_box.y0)), 2),
        "title_padding_imbalance_px_at_768": round(abs(
            (header_box.y1 - title_box.y1)
            - (title_box.y0 - header_box.y0)) * responsive_scale, 2),
        "title_clipped": bool(
            title_box.x0 < canvas.x0 or title_box.x1 > canvas.x1
            or title_box.y0 < header_box.y0 or title_box.y1 > header_box.y1),
    }
    failures = []
    if (header_box.x0 > canvas.x0 + 1 or header_box.x1 < canvas.x1 - 1
            or layout["header_width_delta_px"] > 2):
        failures.append("header width")
    if layout["header_top_gap_px"] > 1:
        failures.append("header top edge")
    if (underline_box.x0 > canvas.x0 + 1 or underline_box.x1 < canvas.x1 - 1
            or layout["underline_width_delta_px"] > 2):
        failures.append("underline width")
    if not 0.10 <= layout["header_height_fraction"] <= 0.125:
        failures.append("header height")
    if not 3 <= layout["underline_height_px"] <= 6:
        failures.append("underline thickness")
    if layout["underline_height_px_at_768"] < 1:
        failures.append("responsive underline")
    if (layout["title_plot_start_delta_px"] > 4
            or layout["title_plot_start_delta_px_at_768"] > 2):
        failures.append("title alignment")
    if (layout["title_top_padding_px"] < 10
            or layout["title_bottom_padding_px"] < 10
            or layout["title_top_padding_px_at_768"] < 3
            or layout["title_bottom_padding_px_at_768"] < 3):
        failures.append("title padding")
    if (layout["title_center_delta_px"] > 2
            or layout["title_center_delta_px_at_768"] > 1
            or layout["title_padding_imbalance_px"] > 4
            or layout["title_padding_imbalance_px_at_768"] > 2):
        failures.append("title centering")
    # Font fallback metrics differ across localized scripts.  A measured
    # 10px responsive glyph height remains legible at the 768px reference
    # canvas; reject only genuinely collapsed/clipped titles.
    if layout["title_height_px_at_768"] < 10 or layout["title_clipped"]:
        failures.append("title legibility")
    if failures:
        raise RuntimeError(f"premium edge header failed {failures}: {layout}")
    return layout


def premium_header_raster_report(figure, header=None, underline=None,
                                 *, cream_tolerance: int = 0) -> dict:
    """Inspect the final pre-encoder RGBA buffer for the R6 header contract.

    The returned protected-crop hash begins immediately below the lower gold
    underline.  Call this only after all factual artists have been drawn.
    """
    import numpy as np

    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    if header is None:
        header = next(
            axes for axes in figure.axes
            if any(artist.get_gid() == "premium-decoration:header-face"
                   for artist in axes.images))
    if underline is None:
        underline = next(
            patch for patch in header.patches
            if patch.get_gid() == "premium-decoration:header-underline")
    pixels = np.asarray(figure.canvas.buffer_rgba()).copy()
    height, width = pixels.shape[:2]
    rgb = pixels[:, :, :3].astype(int)
    header_box = header.get_window_extent(renderer)
    underline_box = underline.get_window_extent(renderer)
    title_artist = next(
        artist for artist in header.texts
        if artist.get_gid() == "premium-decoration:header-title")
    title_box = title_artist.get_window_extent(renderer)
    cream_hex = PREMIUM["surface"]["canvas"]
    cream = np.array([int(cream_hex[index:index + 2], 16)
                      for index in (1, 3, 5)])
    cream_like = np.max(np.abs(rgb - cream), axis=2) <= cream_tolerance
    top = rgb[0]
    top_green = ((top[:, 1] > top[:, 0])
                 & (top[:, 1] > top[:, 2])
                 & (top[:, 0] < 64) & (top[:, 1] < 96))
    underline_top_row = max(0, int(round(height - underline_box.y1)))
    underline_bottom_row = min(height, int(round(height - underline_box.y0)))
    background_cream_like = cream_like[:underline_top_row].copy()
    title_x0 = max(0, int(title_box.x0) - 2)
    title_x1 = min(width, int(title_box.x1 + 1) + 2)
    title_y0 = max(0, int(height - title_box.y1) - 2)
    title_y1 = min(underline_top_row, int(height - title_box.y0 + 1) + 2)
    background_cream_like[title_y0:title_y1, title_x0:title_x1] = False
    card_masks = []
    for card in header.texts:
        if not str(card.get_gid() or "").startswith("premium-label:header-card:"):
            continue
        patch = card.get_bbox_patch()
        card_box = patch.get_window_extent(renderer)
        x0 = max(0, int(card_box.x0) - 5)
        x1 = min(width, int(card_box.x1 + 1) + 5)
        y0 = max(0, int(height - card_box.y1) - 5)
        y1 = min(underline_top_row, int(height - card_box.y0 + 1) + 5)
        background_cream_like[y0:y1, x0:x1] = False
        card_masks.append([x0, y0, x1, y1])
    protected_start_row = underline_bottom_row
    protected = pixels[protected_start_row:, :, :]
    return {
        "canvas_width_px": int(width),
        "canvas_height_px": int(height),
        "header_top_gap_px": round(max(0.0, figure.bbox.y1 - header_box.y1), 2),
        "top_row_green_pixels": int(top_green.sum()),
        "top_row_green_coverage": round(float(top_green.mean()), 6),
        "top_row_cream_like_pixels": int(cream_like[0].sum()),
        "header_before_underline_cream_like_pixels": int(
            cream_like[:underline_top_row].sum()),
        "header_background_cream_like_pixels": int(
            background_cream_like.sum()),
        "approved_header_card_count": len(card_masks),
        "approved_header_card_masks": card_masks,
        "cream_tolerance": int(cream_tolerance),
        "underline_top_row": underline_top_row,
        "underline_bottom_row": underline_bottom_row,
        "protected_start_row": protected_start_row,
        "protected_crop_shape": list(protected.shape),
        "protected_crop_sha256": hashlib.sha256(
            protected.tobytes()).hexdigest(),
    }


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
    canvas = figure.bbox
    clipping = []
    for item in boxes:
        bbox = item["bbox"]
        if (bbox.x0 < canvas.x0 or bbox.y0 < canvas.y0
                or bbox.x1 > canvas.x1 or bbox.y1 > canvas.y1):
            clipping.append({
                "role": item["role"],
                "bbox_px": [round(bbox.x0, 2), round(bbox.y0, 2),
                            round(bbox.x1, 2), round(bbox.y1, 2)],
            })
    return {
        "checked": True, "gap_pixels": float(gap_pixels),
        "box_count": len(boxes), "overlap_count": len(overlaps),
        "overlaps": overlaps, "clipping_count": len(clipping),
        "clipping": clipping,
        "boxes": [{"role": item["role"],
                   "bbox_px": [round(item["bbox"].x0, 2), round(item["bbox"].y0, 2),
                               round(item["bbox"].x1, 2), round(item["bbox"].y1, 2)]}
                  for item in boxes],
    }
