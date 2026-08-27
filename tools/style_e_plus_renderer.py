"""Two-image renderer for manual BTCUSD Style E+ H1/M15 previews."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

from tools import image_output, intraday_indicators, style_e_plus_story
from tools import style_e_plus_adaptive_stop as adaptive_stop
from tools.chart_story_renderer import _thai_font


ASSET = "btcusd"
STORY_TIMEFRAME = "1h/15min"
H1_TIMEFRAME = "1h"
M15_TIMEFRAME = "15min"
H1_DISPLAY_BARS = 120
M15_DISPLAY_BARS = 60
M15_FUTURE_SPACE_BARS = 24
M15_LABEL_RAIL_START_BARS = 4.0
MIN_SOURCE_BARS = 240
DONCHIAN_LENGTH = 20
EMA_LENGTH = 20
ATR_LENGTH = 14
KELTNER_ATR_MULTIPLIER = 1.5
PERCENTILE_LOOKBACK = 200
FIGURE_SIZE = (16, 10)
DPI = 120

COLORS = {
    "bg": "#ffffff",
    "grid": "#e6e9ef",
    "axis": "#5f6773",
    "text": "#111827",
    "up": "#0f8f83",
    "down": "#e23d36",
    "donchian": "#1769e0",
    "keltner": "#f07818",
    "bbw": "#1769e0",
    "atr": "#f07818",
    "plus_di": "#169b62",
    "minus_di": "#d9363e",
    "adx": "#142b70",
    "price": "#ffd84d",
}


class RendererContractError(ValueError):
    """story/rows ไม่ตรงกันหรือไม่พอสำหรับภาพ Gate A"""


def _validate_story_for_render(story: dict) -> None:
    """Recompute the v4/B100 story before either image renderer can write.

    Keeping this guard at the renderer boundary makes the two image entrypoints
    fail closed on an A-shaped plan, stale adaptive metadata, or any other
    tampered story—even when the caller bypasses the article/pipeline layer.
    """
    if not isinstance(story, dict):
        raise RendererContractError("story ต้องเป็น dict")
    try:
        style_e_plus_story.validate_story(story)
    except style_e_plus_story.StoryUnavailable as exc:
        detail = str(exc)
        # Preserve stable, human-readable anchors for callers/tests while
        # retaining the validator's precise Thai diagnostic.
        anchor = ""
        if "protective_stop" in detail:
            anchor = "protective stop: "
        elif "trigger_confirmed" in detail:
            anchor = "trigger_confirmed: "
        elif "NO_PLAN/NO_CHASE" in detail:
            anchor = "plan=None: "
        elif "plan" in detail:
            anchor = "story.plan: "
        raise RendererContractError(
            f"story validator ไม่ผ่าน: {anchor}{detail}") from exc


def context_metadata_contract() -> dict:
    """Machine-readable contract for image 1: H1 market context."""
    return {
        "schema": "style-e-plus-renderer-v3",
        "role": "h1_context",
        "layout": {
            "panel_count": 3,
            "panels": ["price", "volatility", "dmi_adx"],
            "figure_size_inches": list(FIGURE_SIZE),
            "background": COLORS["bg"],
            "title": True,
            "header": True,
            "status_box": False,
            "footer": False,
        },
        "elements": {
            "candlesticks": True,
            "donchian_20": True,
            "keltner_ema20_atr14_1_5": True,
            "trade_plan_overlay": False,
            "entry_zone": False,
            "stop_loss": False,
            "take_profit": False,
            "bbw_percentile": True,
            "atr14_percentile": True,
            "dmi_adx14": True,
            "right_price_tags": True,
            "volume": False,
        },
    }


def execution_metadata_contract() -> dict:
    """Machine-readable contract for image 2: M15 execution map."""
    return {
        "schema": "style-e-plus-renderer-v3",
        "role": "m15_execution",
        "layout": {
            "panel_count": 1,
            "panels": ["price_execution"],
            "figure_size_inches": [16, 9],
            "background": COLORS["bg"],
            "title": True,
            "header": True,
            "status_box": True,
            "footer": False,
        },
        "elements": {
            "candlesticks": True,
            "ema20": True,
            "donchian_20": True,
            "trade_plan_overlay": True,
            "entry_zone": True,
            "stop_loss": False,
            "protective_stop_plan": True,
            "protective_stop_active": False,
            "take_profit": True,
            "conditional_projection": False,
            "right_price_tags": True,
            "close_right_tag": True,
            "ema20_right_tag": False,
            "state_badge": True,
            "execution_level_labels": True,
            "volume": False,
        },
    }


def metadata_contract() -> dict:
    """Backward-compatible name for the first-image metadata contract."""
    return context_metadata_contract()


def _number(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise RendererContractError(f"{label} ต้องเป็นตัวเลข") from exc
    if not math.isfinite(result):
        raise RendererContractError(f"{label} ต้องเป็นตัวเลขจำกัด")
    return result


def _money(value: float) -> str:
    return f"{float(value):,.2f}"


def _normal_timeframe(value: Any) -> str:
    text = str(value).strip().lower()
    if text in {"1h", "h1"}:
        return H1_TIMEFRAME
    if text in {"15min", "m15", "15m"}:
        return M15_TIMEFRAME
    return text


def _execution_state_presentation(story: dict) -> dict:
    """Map the persisted state to visible M15 semantics; fail closed on mismatch."""
    presentations = {
        "NO_PLAN": {
            "badge": "NO_PLAN · ยังไม่มี Execution Map M15",
            "badge_color": "#475569", "overlay": False,
        },
        "NO_CHASE": {
            "badge": "NO_CHASE · งดไล่ราคา",
            "badge_color": "#b45309", "overlay": False,
        },
        "WAIT_TRIGGER": {
            "badge": "WAIT_TRIGGER · รอยืนยัน Trigger M15",
            "badge_color": "#1d4ed8", "overlay": True,
        },
        "ENTRY_READY": {
            "badge": "ENTRY_READY · Trigger พร้อม · ยังไม่มี Fill",
            "badge_color": "#047857", "overlay": True,
        },
    }
    state = story.get("state")
    if state not in presentations:
        raise RendererContractError("story.state ไม่อยู่ในสัญญา Style E+")
    result = copy.deepcopy(presentations[state])
    plan = story.get("plan")
    if result["overlay"] and not isinstance(plan, dict):
        raise RendererContractError(f"{state} ต้องมี story.plan")
    if not result["overlay"] and plan is not None:
        raise RendererContractError(f"{state} ต้องมี plan=None")
    if not result["overlay"]:
        return result

    side = story.get("side")
    if side not in {"buy", "sell"} or plan.get("side") != side:
        raise RendererContractError("plan.side ต้องตรง story.side BUY/SELL")
    if _normal_timeframe(plan.get("timeframe")) != M15_TIMEFRAME:
        raise RendererContractError("plan.timeframe ต้องเป็น M15")
    if plan.get("trigger_confirmed") is not (state == "ENTRY_READY"):
        raise RendererContractError("state กับ trigger_confirmed ไม่ตรงกัน")
    protective_stop = plan.get("protective_stop")
    if (not isinstance(protective_stop, dict)
            or protective_stop.get("active") is not False
            or protective_stop.get("status") != "inactive_until_external_fill"
            or protective_stop.get("activation_event") != "external_entry_fill"
            or protective_stop.get("effective_from") is not None):
        raise RendererContractError(
            "protective stop ต้อง inactive จนกว่าจะมี external fill")
    levels = {
        key: _number(plan.get(key), f"plan.{key}")
        for key in ("entry_zone_low", "entry_zone_high",
                    "pre_entry_invalidation_close", "tp1", "tp2")
    }
    levels["protective_stop"] = _number(
        protective_stop.get("price"), "plan.protective_stop.price")
    if levels["entry_zone_low"] > levels["entry_zone_high"]:
        raise RendererContractError("Entry Zone เรียงราคาไม่ถูกต้อง")
    if not _same(levels["protective_stop"], levels["pre_entry_invalidation_close"]):
        raise RendererContractError(
            "protective stop ต้องตรง pre-entry invalidation ตาม story.plan")
    result["levels"] = levels
    return result


def _validate_contract(story: dict, rows: list[dict], output_path: Path, *, role: str) -> None:
    if not isinstance(story, dict):
        raise RendererContractError("story ต้องเป็น dict")
    if str(story.get("asset", "")).lower() != ASSET:
        raise RendererContractError("renderer Style E+ รับเฉพาะ asset=btcusd")
    if str(story.get("timeframe", "")).lower() != STORY_TIMEFRAME:
        raise RendererContractError("renderer Style E+ รับเฉพาะ timeframe=1h/15min")
    if len(rows) < MIN_SOURCE_BARS:
        raise RendererContractError(
            f"ต้องมีแท่ง H1 ที่ปิดแล้วอย่างน้อย {MIN_SOURCE_BARS} แท่ง (ได้ {len(rows)})")
    if output_path.suffix.lower() != image_output.IMAGE_SUFFIX:
        raise RendererContractError(f"ภาพต้องเป็น {image_output.IMAGE_SUFFIX}")

    previous_at = ""
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise RendererContractError(f"rows[{index}] ต้องเป็น dict")
        at = str(row.get("at", ""))
        if not at:
            raise RendererContractError(f"rows[{index}] ขาด at")
        if previous_at and at <= previous_at:
            raise RendererContractError("แท่งต้องเรียงตามเวลาและห้ามซ้ำ")
        previous_at = at
        open_, high, low, close = (_number(row.get(key), f"rows[{index}].{key}")
                                   for key in ("open", "high", "low", "close"))
        if high < max(open_, close) or low > min(open_, close) or high < low:
            raise RendererContractError(f"rows[{index}] OHLC เรียงลำดับไม่ถูกต้อง")
        # WCB provider uses `forming`; fixtures/pipeline evidence may additionally
        # carry `candle_state`.  Either signal must fail closed on a direct render.
        if bool(row.get("forming")):
            raise RendererContractError(f"rows[{index}] ยังเป็นแท่ง forming")
        if row.get("candle_state") not in {None, "closed"}:
            raise RendererContractError(f"rows[{index}] ไม่ใช่แท่งปิด")

    if role == "h1":
        expected_timeframe = H1_TIMEFRAME
        bar_at = str(story.get("bar_at", ""))
        current = story.get("current")
        indicators = story.get("indicators")
    elif role == "m15":
        expected_timeframe = M15_TIMEFRAME
        bar_at = str(story.get("m15_bar_at", ""))
        current = (story.get("m15") or {}).get("current")
        indicators = (story.get("m15") or {}).get("indicators")
    else:
        raise RendererContractError(f"ไม่รู้จัก image role: {role}")
    if not bar_at:
        raise RendererContractError("story.bar_at ต้องตรงกับแท่งล่าสุด")
    try:
        same_latest_bar = (adaptive_stop.canonical_timestamp(bar_at)
                           == adaptive_stop.canonical_timestamp(rows[-1]["at"]))
    except adaptive_stop.AdaptiveStopError as exc:
        raise RendererContractError("story.bar_at ต้องตรงกับแท่งล่าสุด") from exc
    if not same_latest_bar:
        raise RendererContractError("story.bar_at ต้องตรงกับแท่งล่าสุด")
    basis = (story.get("candle_basis") or {}).get(role)
    if not isinstance(basis, dict) or basis.get("candle_state") != "closed":
        raise RendererContractError("story.candle_basis ไม่ยืนยันแท่งปิด")
    if (basis.get("asset") != ASSET
            or _normal_timeframe(basis.get("timeframe")) != expected_timeframe
            or adaptive_stop.canonical_timestamp(basis.get("basis_bar_at"))
               != adaptive_stop.canonical_timestamp(bar_at)):
        raise RendererContractError("story.candle_basis ไม่ตรง asset/timeframe/bar_at")
    if not isinstance(indicators, dict):
        raise RendererContractError("story ขาด indicators")
    if not isinstance(current, dict):
        raise RendererContractError("story ขาด current")
    if story.get("state") not in {"WAIT_TRIGGER", "ENTRY_READY", "NO_PLAN", "NO_CHASE"}:
        raise RendererContractError("story.state ไม่อยู่ในสัญญา Style E+")
    lifecycle = story.get("lifecycle") or {}
    if (lifecycle.get("mode") != "manual_analysis_only"
            or lifecycle.get("external_fill_evidence_accepted") is not False
            or lifecycle.get("position_confirmed") is not False
            or lifecycle.get("protective_stop_active") is not False):
        raise RendererContractError("renderer ไม่รับ story ที่อ้าง position/protective stop active")
    plan = story.get("plan")
    if plan:
        protective_stop = plan.get("protective_stop") or {}
        if (not isinstance(protective_stop, dict)
                or protective_stop.get("active") is not False
                or protective_stop.get("status") != "inactive_until_external_fill"
                or protective_stop.get("effective_from") is not None):
            raise RendererContractError("protective stop ต้อง inactive จนกว่าจะมี external fill")
    if role == "m15":
        _execution_state_presentation(story)


def _ema(values: list[float], length: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) < length:
        return output
    current = sum(values[:length]) / length
    output[length - 1] = current
    alpha = 2.0 / (length + 1)
    for index in range(length, len(values)):
        current += alpha * (values[index] - current)
        output[index] = current
    return output


def _atr_series(rows: list[dict], length: int) -> list[float | None]:
    return [None] + intraday_indicators.rma(intraday_indicators.true_ranges(rows), length)


def _percentile_series(values: list[float | None], lookback: int) -> list[float | None]:
    output: list[float | None] = []
    valid: list[float] = []
    for value in values:
        if value is None:
            output.append(None)
            continue
        valid.append(float(value))
        history = valid[-lookback:]
        output.append(sum(item <= value for item in history) / len(history) * 100.0)
    return output


def _tail_indicator(rows: list[dict], bars: int, compute, key: str) -> list[float | None]:
    output: list[float | None] = []
    for end in range(len(rows) - bars + 1, len(rows) + 1):
        result = compute(rows[:end])
        output.append(float(result[key]) if intraday_indicators.available(result) else None)
    return output


def _plot_data(rows: list[dict]) -> dict:
    closes = [float(row["close"]) for row in rows]
    ema_all = _ema(closes, EMA_LENGTH)
    atr_all = _atr_series(rows, ATR_LENGTH)
    atr_percentile_all = _percentile_series(atr_all, PERCENTILE_LOOKBACK)
    keltner_middle = ema_all[-H1_DISPLAY_BARS:]
    atr_view = atr_all[-H1_DISPLAY_BARS:]
    keltner_upper = [None if middle is None or atr is None
                     else middle + KELTNER_ATR_MULTIPLIER * atr
                     for middle, atr in zip(keltner_middle, atr_view)]
    keltner_lower = [None if middle is None or atr is None
                     else middle - KELTNER_ATR_MULTIPLIER * atr
                     for middle, atr in zip(keltner_middle, atr_view)]
    return {
        "donchian_upper": _tail_indicator(
            rows, H1_DISPLAY_BARS,
            lambda prefix: intraday_indicators.donchian(prefix, DONCHIAN_LENGTH), "upper"),
        "donchian_lower": _tail_indicator(
            rows, H1_DISPLAY_BARS,
            lambda prefix: intraday_indicators.donchian(prefix, DONCHIAN_LENGTH), "lower"),
        "keltner_middle": keltner_middle,
        "keltner_upper": keltner_upper,
        "keltner_lower": keltner_lower,
        "bbw_percentile": _tail_indicator(
            rows, H1_DISPLAY_BARS,
            lambda prefix: intraday_indicators.bollinger_bandwidth(
                prefix, length=20, stdev=2.0, percentile_lookback=PERCENTILE_LOOKBACK),
            "percentile"),
        "atr_percentile": atr_percentile_all[-H1_DISPLAY_BARS:],
        "plus_di": _tail_indicator(
            rows, H1_DISPLAY_BARS,
            lambda prefix: intraday_indicators.dmi_adx(prefix, ATR_LENGTH), "plus_di"),
        "minus_di": _tail_indicator(
            rows, H1_DISPLAY_BARS,
            lambda prefix: intraday_indicators.dmi_adx(prefix, ATR_LENGTH), "minus_di"),
        "adx": _tail_indicator(
            rows, H1_DISPLAY_BARS,
            lambda prefix: intraday_indicators.dmi_adx(prefix, ATR_LENGTH), "adx"),
        "atr": atr_view,
    }


def _lookup(payload: dict, *names: str) -> float | None:
    for name in names:
        if name in payload and payload[name] is not None:
            return _number(payload[name], name)
    return None


def _same(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-7, abs_tol=1e-7)


def _validate_story_numbers(story: dict, series: dict, rows: list[dict]) -> None:
    indicators = story["indicators"]
    expected_groups = {
        "donchian": {
            "upper": series["donchian_upper"][-1],
            "lower": series["donchian_lower"][-1],
        },
        "keltner": {
            "middle": series["keltner_middle"][-1],
            "upper": series["keltner_upper"][-1],
            "lower": series["keltner_lower"][-1],
        },
        "bbw": {"percentile": series["bbw_percentile"][-1]},
        "dmi_adx": {
            "plus_di": series["plus_di"][-1],
            "minus_di": series["minus_di"][-1],
            "adx": series["adx"][-1],
        },
        "atr": {"value": series["atr"][-1]},
    }
    for group, expected in expected_groups.items():
        supplied = indicators.get(group)
        if not isinstance(supplied, dict):
            raise RendererContractError(f"story.indicators ขาด {group}")
        for field, actual in expected.items():
            if actual is None:
                raise RendererContractError(f"indicator {group}.{field} ไม่ available")
            aliases = ("middle", "mid") if field == "middle" else (field,)
            wanted = _lookup(supplied, *aliases)
            if wanted is None or not _same(float(actual), wanted):
                raise RendererContractError(
                    f"story.indicators.{group}.{field} ไม่ตรงค่าที่คำนวณจาก rows")

    atr_payload = indicators["atr"]
    supplied_percentile = _lookup(atr_payload, "percentile")
    if supplied_percentile is None:
        extra = indicators.get("atr_percentile")
        supplied_percentile = (_number(extra, "atr_percentile") if extra is not None else None)
    actual_percentile = series["atr_percentile"][-1]
    if (actual_percentile is None or supplied_percentile is None
            or not _same(float(actual_percentile), supplied_percentile)):
        raise RendererContractError("story ไม่มี ATR percentile ที่ตรงกับ rows")

    close = _number(story["current"].get("close"), "story.current.close")
    if not _same(close, float(rows[-1]["close"])):
        raise RendererContractError("story.current.close ไม่ตรงกับแท่งล่าสุด")


def _m15_plot_data(rows: list[dict]) -> dict:
    closes = [float(row["close"]) for row in rows]
    return {
        "ema20": _ema(closes, EMA_LENGTH)[-M15_DISPLAY_BARS:],
        "atr": _atr_series(rows, ATR_LENGTH)[-M15_DISPLAY_BARS:],
        "donchian_upper": _tail_indicator(
            rows, M15_DISPLAY_BARS,
            lambda prefix: intraday_indicators.donchian(prefix, DONCHIAN_LENGTH), "upper"),
        "donchian_lower": _tail_indicator(
            rows, M15_DISPLAY_BARS,
            lambda prefix: intraday_indicators.donchian(prefix, DONCHIAN_LENGTH), "lower"),
    }


def _validate_m15_numbers(story: dict, series: dict, rows: list[dict]) -> None:
    payload = (story.get("m15") or {}).get("indicators") or {}
    expected = {
        "ema20": series["ema20"][-1],
        "atr": series["atr"][-1],
        "donchian_upper": series["donchian_upper"][-1],
        "donchian_lower": series["donchian_lower"][-1],
    }
    supplied = {
        "ema20": payload.get("ema20"),
        "atr": (payload.get("atr") or {}).get("value"),
        "donchian_upper": (payload.get("donchian") or {}).get("upper"),
        "donchian_lower": (payload.get("donchian") or {}).get("lower"),
    }
    for key, actual in expected.items():
        if actual is None or supplied[key] is None or not _same(float(actual), _number(supplied[key], key)):
            raise RendererContractError(f"story M15 {key} ไม่ตรงค่าที่คำนวณจาก rows")
    close = _number((story.get("m15") or {}).get("current", {}).get("close"), "M15.close")
    if not _same(close, float(rows[-1]["close"])):
        raise RendererContractError("story.m15.current.close ไม่ตรงกับแท่งล่าสุด")


def _style_axes(axes) -> None:
    axes.set_facecolor(COLORS["bg"])
    axes.grid(True, color=COLORS["grid"], linewidth=0.8)
    axes.set_axisbelow(True)
    axes.yaxis.tick_right()
    axes.tick_params(colors=COLORS["axis"], labelsize=9.5)
    for spine in axes.spines.values():
        spine.set_color("#d5d9e2")


def _plot_optional(axes, values: list[float | None], **kwargs) -> None:
    xs = [index for index, value in enumerate(values) if value is not None]
    ys = [value for value in values if value is not None]
    if len(xs) > 1:
        axes.plot(xs, ys, **kwargs)


def _draw_candles(axes, view: list[dict], Rectangle) -> None:
    width = 0.62
    for index, row in enumerate(view):
        open_, close = float(row["open"]), float(row["close"])
        color = COLORS["up"] if close >= open_ else COLORS["down"]
        axes.plot([index, index], [float(row["low"]), float(row["high"])],
                  color=color, linewidth=0.85, zorder=4)
        bottom = min(open_, close)
        height = abs(close - open_) or 1e-9
        axes.add_patch(Rectangle(
            (index - width / 2, bottom), width, height,
            facecolor=color, edgecolor=color, linewidth=0.45, zorder=4))


def _right_tag(axes, y: float, text: str, color: str, *, text_color: str = "#ffffff",
               y_offset: float = 0.0):
    """Draw a rounded right-rail tag inside the figure with a value leader."""
    return axes.annotate(
        text, xy=(1, y), xycoords=("axes fraction", "data"),
        xytext=(-12, y_offset), textcoords="offset points", ha="right", va="center",
        fontsize=11.0, fontweight="bold", color=text_color, clip_on=True,
        annotation_clip=True, zorder=10,
        arrowprops={"arrowstyle": "-", "color": color, "linewidth": 0.7,
                    "shrinkA": 0, "shrinkB": 0},
        bbox={"boxstyle": "round,pad=0.30", "facecolor": color,
              "edgecolor": "none", "alpha": 0.98})


def _centered_offsets(count: int, spacing_points: float = 14.0) -> list[float]:
    """Return deterministic, collision-resistant offsets for a right rail."""
    if count <= 0:
        return []
    center = (count - 1) / 2.0
    return [(center - index) * spacing_points for index in range(count)]


def _sorted_tag_offsets(entries: list[dict], spacing_points: float = 28.0) -> dict[str, float]:
    ordered = sorted(entries, key=lambda item: (-float(item["y"]), str(item["role"])))
    offsets = _centered_offsets(len(ordered), spacing_points)
    return {item["role"]: offset for item, offset in zip(ordered, offsets)}


def _right_label(axes, y: float, text: str, *, color: str, facecolor: str = "#ffffff",
                 edgecolor: str = "none", fontsize: float = 10.5,
                 y_offset: float = 0.0, zorder: int = 8):
    """Draw a future-space label anchored to its real price level."""
    return axes.annotate(
        text, xy=(1, y), xycoords=("axes fraction", "data"),
        xytext=(-12, y_offset), textcoords="offset points", ha="right", va="center",
        fontsize=fontsize, fontweight="bold", color=color, clip_on=True,
        annotation_clip=True, zorder=zorder,
        arrowprops={"arrowstyle": "-", "color": edgecolor if edgecolor != "none" else color,
                    "linewidth": 0.55, "shrinkA": 0, "shrinkB": 0},
        bbox={"boxstyle": "round,pad=0.22", "facecolor": facecolor,
              "edgecolor": edgecolor, "alpha": 0.92})


def _painted_bbox(artist, renderer):
    """Return the visible text/box bbox, excluding an annotation leader."""
    get_bbox_patch = getattr(artist, "get_bbox_patch", None)
    if callable(get_bbox_patch):
        patch = get_bbox_patch()
        if patch is not None:
            return patch.get_window_extent(renderer=renderer)
    return artist.get_window_extent(renderer=renderer)


def _edge_aware_right_rail(figure, axes, artists: list[tuple[str, Any]], *,
                           edge_px: float = 12.0) -> None:
    """Resolve right-rail labels against axes edges and one another.

    Offsets are in display points, but the constraints are measured after a
    real canvas draw.  This keeps the result deterministic across text widths
    and ensures watch labels cannot sit on the top/bottom axes boundary.
    """
    if not artists:
        return
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    axes_bbox = axes.bbox
    dpi_scale = float(figure.dpi) / 72.0

    def shift(artist, delta_px: float) -> None:
        x_offset, y_offset = artist.get_position()
        artist.set_position((x_offset, y_offset + delta_px / dpi_scale))

    # First satisfy the edge clearance.  A bounded pass is deterministic and
    # avoids accumulating rounding drift when matplotlib redraws text.
    for _ in range(max(2, len(artists))):
        changed = False
        figure.canvas.draw()
        for _name, artist in artists:
            bbox = _painted_bbox(artist, renderer)
            delta = 0.0
            if bbox.y0 < axes_bbox.y0 + edge_px:
                delta = axes_bbox.y0 + edge_px - bbox.y0
            elif bbox.y1 > axes_bbox.y1 - edge_px:
                delta = axes_bbox.y1 - edge_px - bbox.y1
            if delta:
                shift(artist, delta)
                changed = True
        if not changed:
            break

    # Then separate true painted-box collisions.  Prefer moving the later
    # rail item down; if the bottom edge is occupied, move the earlier item up.
    for _ in range(max(2, len(artists) * 2)):
        figure.canvas.draw()
        boxes = [(_name, artist, _painted_bbox(artist, renderer))
                 for _name, artist in artists]
        collision = False
        for index, (_left_name, left_artist, left_box) in enumerate(boxes):
            for _right_name, right_artist, right_box in boxes[index + 1:]:
                overlap = min(left_box.y1, right_box.y1) - max(left_box.y0, right_box.y0)
                x_overlap = min(left_box.x1, right_box.x1) - max(left_box.x0, right_box.x0)
                if overlap <= 0 or x_overlap <= 0:
                    continue
                collision = True
                down_room = right_box.y0 - (axes_bbox.y0 + edge_px)
                if down_room >= overlap + 2.0:
                    shift(right_artist, -(overlap + 2.0))
                else:
                    shift(left_artist, overlap + 2.0)
                break
            if collision:
                break
        if not collision:
            break


def _layout_guard(figure, artists: list[tuple[str, Any]], *, edge_px: float = 12.0) -> None:
    """Fail closed when required text/label bboxes leave the figure or collide."""
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    figure_bbox = figure.bbox
    boxes: list[tuple[str, Any]] = []
    for name, artist in artists:
        if artist is None:
            continue
        bbox = artist.get_window_extent(renderer=renderer)
        if (bbox.x0 < figure_bbox.x0 + edge_px
                or bbox.y0 < figure_bbox.y0 + edge_px
                or bbox.x1 > figure_bbox.x1 - edge_px
                or bbox.y1 > figure_bbox.y1 - edge_px):
            raise RendererContractError(f"layout guard: {name} อยู่นอก figure")
        # Annotation extents include the leader line from the real price level
        # to the offset label.  That line is intentionally allowed to cross a
        # neighboring rail region; collision must be measured on the painted
        # text/box itself.  Keep the full extent for the edge check above so a
        # clipped leader still fails closed.
        collision_bbox = _painted_bbox(artist, renderer)
        boxes.append((name, collision_bbox))
    for index, (left_name, left_box) in enumerate(boxes):
        for right_name, right_box in boxes[index + 1:]:
            overlap_width = min(left_box.x1, right_box.x1) - max(left_box.x0, right_box.x0)
            overlap_height = min(left_box.y1, right_box.y1) - max(left_box.y0, right_box.y0)
            if overlap_width > 0 and overlap_height > 0:
                raise RendererContractError(
                    f"layout guard: {left_name} ชน {right_name}")


def _summary_rail(axes, text: str, *, legend=None):
    """Place compact panel summary and legend in a rail above data axes."""
    summary = axes.text(
        0.012, 1.13, text, transform=axes.transAxes, ha="left", va="bottom",
        fontsize=9.5, fontweight="bold", color=COLORS["text"], clip_on=False,
        zorder=9)
    if legend is not None:
        # Keep the compact legend in the rail, away from the right value tags.
        # The anchor is fixed in axes coordinates for deterministic output.
        legend.set_bbox_to_anchor((0.42, 1.10), transform=axes.transAxes)
        legend.set_loc("lower left")
    return summary


def render_context(story: dict, rows: list[dict], output_path: Path) -> dict:
    """Render image 1: H1 context without execution levels."""
    output_path = Path(output_path)
    _validate_story_for_render(story)
    _validate_contract(story, rows, output_path, role="h1")
    series = _plot_data(rows)
    _validate_story_numbers(story, series, rows)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter

    _thai_font()
    view = rows[-H1_DISPLAY_BARS:]
    xs = list(range(H1_DISPLAY_BARS))
    figure, (price_axes, volatility_axes, dmi_axes) = plt.subplots(
        3, 1, figsize=FIGURE_SIZE, dpi=DPI, sharex=True,
        # ให้ Price Action กินพื้นที่หลัก; สอง dashboard ด้านล่างกระชับลงราว 32%
        gridspec_kw={"height_ratios": [4.75, 0.75, 0.75], "hspace": 0.07})
    figure.patch.set_facecolor(COLORS["bg"])
    for axes in (price_axes, volatility_axes, dmi_axes):
        _style_axes(axes)

    # แผงราคา: เฉพาะระดับที่ล็อกใน Gate A ไม่วาดแผนหรือสถานะทับกราฟ
    title = price_axes.set_title(
        "BTC/USD · H1 CONTEXT", loc="left", pad=-10,
        fontsize=17, fontweight="bold", color=COLORS["text"])
    _draw_candles(price_axes, view, Rectangle)
    _plot_optional(price_axes, series["donchian_upper"], color=COLORS["donchian"],
                   linewidth=1.6, label="Donchian 20 — ขอบบน")
    _plot_optional(price_axes, series["donchian_lower"], color=COLORS["donchian"],
                   linewidth=1.6, label="Donchian 20 — ขอบล่าง")
    valid_donchian = [(x, low, high) for x, low, high in
                      zip(xs, series["donchian_lower"], series["donchian_upper"])
                      if low is not None and high is not None]
    if valid_donchian:
        price_axes.fill_between(
            [item[0] for item in valid_donchian],
            [item[1] for item in valid_donchian],
            [item[2] for item in valid_donchian],
            color=COLORS["donchian"], alpha=0.055, zorder=1)
    _plot_optional(price_axes, series["keltner_upper"], color=COLORS["keltner"],
                   linewidth=1.35, label="Keltner EMA20 บวก/ลบ 1.5 ATR")
    _plot_optional(price_axes, series["keltner_lower"], color=COLORS["keltner"],
                   linewidth=1.35)
    valid_keltner = [(x, low, high) for x, low, high in
                     zip(xs, series["keltner_lower"], series["keltner_upper"])
                     if low is not None and high is not None]
    if valid_keltner:
        price_axes.fill_between(
            [item[0] for item in valid_keltner],
            [item[1] for item in valid_keltner],
            [item[2] for item in valid_keltner],
            color=COLORS["keltner"], alpha=0.045, zorder=1)

    # H1 owns market context only. Execution-plan levels belong to image 2 (M15).

    price_legend = price_axes.legend(
        loc="upper left", fontsize=10.0, framealpha=0.94, ncol=2)
    price_axes.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))

    close = float(rows[-1]["close"])
    upper = float(series["donchian_upper"][-1])
    lower = float(series["donchian_lower"][-1])
    anchors = ([float(row["low"]) for row in view] + [float(row["high"]) for row in view]
               + [float(value) for key in ("donchian_lower", "donchian_upper",
                                            "keltner_lower", "keltner_upper")
                  for value in series[key] if value is not None])
    price_range = max(anchors) - min(anchors)
    pad = (price_range * 0.06) or max(abs(close) * 0.01, 1.0)
    price_axes.set_ylim(min(anchors) - pad, max(anchors) + pad)

    price_tags = [
        {"role": "close", "y": close, "text": f"ราคาปิด H1 {close:,.2f}",
         "color": "#f5e6a6", "text_color": "#111827"},
        {"role": "upper", "y": upper, "text": f"ขอบบน H1 {upper:,.2f}",
         "color": "#ffd000", "text_color": "#111827"},
        {"role": "lower", "y": lower, "text": f"ขอบล่าง H1 {lower:,.2f}",
         "color": COLORS["donchian"], "text_color": "#ffffff"},
    ]
    price_tag_artists = [
        (item["role"], _right_tag(
            price_axes, item["y"], item["text"], item["color"],
            text_color=item["text_color"],
            y_offset=offset))
        for item, offset in ((item, _sorted_tag_offsets(price_tags)[item["role"]])
                             for item in price_tags)
    ]

    # แผงความผันผวน: percentile อยู่ในช่วง 0–100 เท่านั้น
    _plot_optional(volatility_axes, series["bbw_percentile"], color=COLORS["bbw"],
                   linewidth=1.8, label="อันดับ BBW")
    _plot_optional(volatility_axes, series["atr_percentile"], color=COLORS["atr"],
                   linewidth=1.8, label="อันดับ ATR")
    volatility_axes.set_ylim(0, 100)
    for level in (25, 75):
        volatility_axes.axhline(level, color="#9aa2ad", linewidth=0.9,
                                linestyle=(0, (4, 3)), alpha=0.75)
    bbw = float(series["bbw_percentile"][-1])
    atr_percentile = float(series["atr_percentile"][-1])
    rising = bool(story["indicators"]["bbw"].get("rising", False))
    volatility_legend = volatility_axes.legend(
        loc="lower left", fontsize=10, framealpha=0.94, ncol=2)
    volatility_summary = _summary_rail(
        volatility_axes,
        f"ความผันผวน · BBW อันดับ {bbw:.0f} "
        f"{'ขึ้น' if rising else 'ลง'} · ATR อันดับ {atr_percentile:.0f}",
        legend=volatility_legend)
    volatility_tags = [
        {"role": "bbw", "y": bbw, "text": f"BBW {bbw:.0f}", "color": COLORS["bbw"]},
        {"role": "atr", "y": atr_percentile, "text": f"ATR {atr_percentile:.0f}",
         "color": COLORS["atr"]},
    ]
    volatility_tag_artists = [
        (item["role"], _right_tag(
            volatility_axes, item["y"], item["text"], item["color"],
            y_offset=offset))
        for item, offset in ((item, _sorted_tag_offsets(volatility_tags)[item["role"]])
                             for item in volatility_tags)
    ]

    # แผง DMI/ADX: DI บอกทิศ ADX บอกแรง ไม่ใช้ volume
    _plot_optional(dmi_axes, series["plus_di"], color=COLORS["plus_di"],
                   linewidth=1.7, label="+DI")
    _plot_optional(dmi_axes, series["minus_di"], color=COLORS["minus_di"],
                   linewidth=1.7, label="-DI")
    _plot_optional(dmi_axes, series["adx"], color=COLORS["adx"], linewidth=1.9, label="ADX")
    dmi_axes.axhline(20, color="#111827", linewidth=0.9,
                     linestyle=(0, (5, 4)), alpha=0.7)
    plus_di = float(series["plus_di"][-1])
    minus_di = float(series["minus_di"][-1])
    adx = float(series["adx"][-1])
    dmi_legend = dmi_axes.legend(
        loc="upper right", fontsize=10, framealpha=0.94, ncol=3)
    dmi_summary = _summary_rail(
        dmi_axes,
        f"ทิศและแรง · +DI {plus_di:.1f} · -DI {minus_di:.1f} · ADX {adx:.1f} "
        f"{'ผ่านขั้นต่ำ 20' if adx >= 20 else 'ยังไม่ผ่านขั้นต่ำ 20'}",
        legend=dmi_legend)
    valid_dmi = [float(value) for key in ("plus_di", "minus_di", "adx")
                 for value in series[key] if value is not None]
    dmi_axes.set_ylim(0, max(50, max(valid_dmi, default=40) * 1.15))

    ticks = sorted({round(index * (H1_DISPLAY_BARS - 1) / 6) for index in range(7)})
    dmi_axes.set_xticks(ticks)
    dmi_axes.set_xticklabels([
        f"{view[index]['at'][8:10]}/{view[index]['at'][5:7]} {view[index]['at'][11:16]} น."
        for index in ticks], fontsize=9.5)
    dmi_axes.set_xlim(-1, H1_DISPLAY_BARS - 1 + H1_DISPLAY_BARS * 0.075)
    # Keep enough horizontal content for the image gate after tight-bbox save;
    # the 12 px layout guard still protects every required label from clipping.
    figure.subplots_adjust(left=0.018, right=0.94, top=0.94, bottom=0.055, hspace=0.19)
    _edge_aware_right_rail(figure, volatility_axes, volatility_tag_artists)

    _layout_guard(
        figure,
        [("h1-title", title), ("h1-price-legend", price_legend),
         ("h1-vol-summary", volatility_summary),
         ("h1-vol-legend", volatility_legend), ("h1-dmi-summary", dmi_summary),
         ("h1-dmi-legend", dmi_legend), *price_tag_artists,
         *volatility_tag_artists])

    try:
        size_bytes = image_output.save_figure(
            figure, output_path, dpi=DPI, bbox_inches="tight", facecolor=COLORS["bg"])
    finally:
        plt.close(figure)

    metadata = context_metadata_contract()
    metadata.update({
        "asset": ASSET,
        "timeframe": "H1",
        "bar_at": story["bar_at"],
        "bars": {"source": len(rows), "displayed": H1_DISPLAY_BARS, "closed_only": True},
        "output": {"format": "webp", "size_bytes": size_bytes,
                   "max_size_bytes": image_output.MAX_IMAGE_BYTES},
    })
    return {"path": str(output_path), "size_bytes": size_bytes,
            "metadata": copy.deepcopy(metadata)}


def render_execution(story: dict, rows: list[dict], output_path: Path) -> dict:
    """Render image 2: M15 entry zone, stop and risk-based targets."""
    output_path = Path(output_path)
    _validate_story_for_render(story)
    _validate_contract(story, rows, output_path, role="m15")
    presentation = _execution_state_presentation(story)
    series = _m15_plot_data(rows)
    _validate_m15_numbers(story, series, rows)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter

    _thai_font()
    view = rows[-M15_DISPLAY_BARS:]
    figure, price_axes = plt.subplots(1, 1, figsize=(17, 9), dpi=DPI)
    figure.patch.set_facecolor(COLORS["bg"])
    _style_axes(price_axes)
    title = price_axes.set_title(
        "BTC/USD · M15 EXECUTION", loc="left", pad=38,
        fontsize=17, fontweight="bold", color=COLORS["text"])
    state_badge = price_axes.text(
        0.012, 0.985, presentation["badge"], transform=price_axes.transAxes,
        ha="left", va="top", fontsize=10.5, fontweight="bold", color="#ffffff",
        bbox={"boxstyle": "round,pad=0.38", "facecolor": presentation["badge_color"],
              "edgecolor": presentation["badge_color"], "alpha": 0.96},
        clip_on=True, zorder=9)
    _draw_candles(price_axes, view, Rectangle)
    _plot_optional(price_axes, series["ema20"], color=COLORS["keltner"],
                   linewidth=1.7, label="EMA20 สำหรับจังหวะ M15")
    _plot_optional(price_axes, series["donchian_upper"], color=COLORS["donchian"],
                   linewidth=1.15, alpha=0.72, label="กรอบ Donchian20 M15")
    _plot_optional(price_axes, series["donchian_lower"], color=COLORS["donchian"],
                   linewidth=1.15, alpha=0.72)

    plan = story.get("plan") if presentation["overlay"] else None
    level_labels = []
    right_rail_specs = []
    conditional_labels = []
    if plan:
        levels = presentation["levels"]
        entry_low = levels["entry_zone_low"]
        entry_high = levels["entry_zone_high"]
        protective_stop = levels["protective_stop"]
        tp1 = levels["tp1"]
        tp2 = levels["tp2"]
        price_axes.axhspan(entry_low, entry_high, color="#16a34a", alpha=0.14, zorder=2)
        for level in (entry_low, entry_high):
            price_axes.axhline(level, color="#15803d", linewidth=1.3,
                               linestyle=(0, (4, 3)), zorder=3)
        price_axes.axhline(protective_stop, color="#dc2626", linewidth=1.75,
                           linestyle=(0, (6, 3)), zorder=3)
        price_axes.axhline(tp1, color="#16a34a", linewidth=1.55,
                           linestyle=(0, (6, 3)), zorder=3)
        price_axes.axhline(tp2, color="#16a34a", linewidth=1.55,
                           linestyle=(0, (2, 3)), zorder=3)
        right_rail_specs += [
            {"role": "entry_zone", "y": (entry_low + entry_high) / 2,
             "text": f"Entry Zone M15 {_money(entry_low)}–{_money(entry_high)}",
             "color": "#166534", "edgecolor": "#86efac", "fontsize": 11.0},
            {"role": "protective_stop_plan", "y": protective_stop,
             "text": f"SL/Protective Stop หลัง Fill {_money(protective_stop)} · ยังไม่ active",
             "color": "#b91c1c", "edgecolor": "none", "fontsize": 9.6},
            {"role": "tp1", "y": tp1, "text": f"TP1 {_money(tp1)} · 1.5R",
             "color": "#15803d", "edgecolor": "none", "fontsize": 10.5},
            {"role": "tp2", "y": tp2, "text": f"TP2 {_money(tp2)} · 2.0R",
             "color": "#15803d", "edgecolor": "none", "fontsize": 10.5},
        ]
        level_labels = [
            {"role": "entry_zone", "text": "Entry Zone M15",
             "low": entry_low, "high": entry_high},
            {"role": "protective_stop_plan",
             "text": "SL/Protective Stop หลัง Fill · ยังไม่ active",
             "price": protective_stop, "active": False},
            {"role": "tp1", "text": "TP1 · 1.5R", "price": tp1},
            {"role": "tp2", "text": "TP2 · 2.0R", "price": tp2},
        ]

    conditional = story.get("daily_conditional") if isinstance(story, dict) else None
    geometry = conditional.get("watch_geometry") if isinstance(conditional, dict) else None
    if (isinstance(geometry, dict) and conditional.get("status") != "STALE_DATA"):
        try:
            buy_watch = _number(geometry["buy_watch"], "daily_conditional.buy_watch")
            sell_watch = _number(geometry["sell_watch"], "daily_conditional.sell_watch")
        except (KeyError, TypeError, ValueError) as exc:
            raise RendererContractError("DC-T watch geometry ไม่ถูกต้อง") from exc
        if not buy_watch > sell_watch:
            raise RendererContractError("DC-T buy watch ต้องสูงกว่า sell watch")
        price_axes.axhline(buy_watch, color="#7c3aed", linewidth=1.65,
                           linestyle=(0, (2, 3)), zorder=3)
        price_axes.axhline(sell_watch, color="#7c3aed", linewidth=1.65,
                           linestyle=(0, (2, 3)), zorder=3)
        right_rail_specs += [
            {"role": "buy_watch", "y": buy_watch,
             "text": f"DC-T Buy watch {_money(buy_watch)} · NOT ENTRY",
             "color": "#4c1d95", "edgecolor": "#6d28d9", "fontsize": 11.5,
             "watch": True},
            {"role": "sell_watch", "y": sell_watch,
             "text": f"DC-T Sell watch {_money(sell_watch)} · NOT ENTRY",
             "color": "#4c1d95", "edgecolor": "#6d28d9", "fontsize": 11.5,
             "watch": True},
        ]
        conditional_labels = [
            {"role": "buy_watch", "text": "DC-T Buy watch · NOT ENTRY", "price": buy_watch},
            {"role": "sell_watch", "text": "DC-T Sell watch · NOT ENTRY", "price": sell_watch},
        ]

    close = float(rows[-1]["close"])
    close_tag_offset = 0
    anchors = ([float(row["low"]) for row in view] + [float(row["high"]) for row in view]
               + [float(value) for key in ("ema20", "donchian_lower", "donchian_upper")
                  for value in series[key] if value is not None])
    if plan:
        anchors += [float(plan[key]) for key in
                    ("entry_zone_low", "entry_zone_high", "tp1", "tp2")]
        anchors.append(float(plan["protective_stop"]["price"]))
    if conditional_labels:
        anchors += [item["price"] for item in conditional_labels]
    price_range = max(anchors) - min(anchors)
    pad = (price_range * 0.07) or max(abs(close) * 0.01, 1.0)
    price_axes.set_ylim(min(anchors) - pad, max(anchors) + pad)
    price_axes.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
    price_axes.legend(loc="lower left", fontsize=10.5, framealpha=0.94, ncol=2)

    ticks = sorted({round(index * (M15_DISPLAY_BARS - 1) / 6) for index in range(7)})
    price_axes.set_xticks(ticks)
    price_axes.set_xticklabels([
        f"{view[index]['at'][8:10]}/{view[index]['at'][5:7]} {view[index]['at'][11:16]} น."
        for index in ticks], fontsize=10)
    price_axes.set_xlim(-1, M15_DISPLAY_BARS - 1 + M15_FUTURE_SPACE_BARS)
    figure.subplots_adjust(left=0.04, right=0.92, top=0.88, bottom=0.075)

    right_rail_specs.insert(
        0, {"role": "close", "y": close, "text": f"ราคาปิด M15 {close:,.2f}",
            "color": "#f5e6a6", "text_color": "#111827", "tag": True})
    tag_offsets = _sorted_tag_offsets(right_rail_specs)
    right_rail_artists = []
    for spec in right_rail_specs:
        if spec.get("tag"):
            artist = _right_tag(
                price_axes, spec["y"], spec["text"], spec["color"],
                text_color=spec.get("text_color", "#ffffff"),
                # Reserve a little less upward displacement for the close tag;
                # this keeps it clear of a nearby Entry Zone in SELL layouts.
                y_offset=tag_offsets[spec["role"]] + 8.0)
        else:
            artist = _right_label(
                price_axes, spec["y"], spec["text"], color=spec["color"],
                edgecolor=spec.get("edgecolor", "none"),
                facecolor="#f5f3ff" if spec.get("watch") else "#ffffff",
                fontsize=spec.get("fontsize", 10.5),
                y_offset=tag_offsets[spec["role"]], zorder=9 if spec.get("watch") else 8)
        right_rail_artists.append((f"m15-{spec['role']}", artist))

    _edge_aware_right_rail(figure, price_axes, right_rail_artists)

    _layout_guard(
        figure,
        [("m15-title", title), ("m15-state", state_badge),
         ("m15-legend", price_axes.get_legend()), *right_rail_artists])

    try:
        size_bytes = image_output.save_figure(
            figure, output_path, dpi=DPI, bbox_inches="tight", facecolor=COLORS["bg"])
    finally:
        plt.close(figure)

    metadata = execution_metadata_contract()
    if not plan:
        for key in ("trade_plan_overlay", "entry_zone", "protective_stop_plan",
                    "take_profit", "conditional_projection", "execution_level_labels"):
            metadata["elements"][key] = False
    metadata.update({
        "asset": ASSET,
        "timeframe": "M15",
        "bar_at": story["m15_bar_at"],
        "bars": {"source": len(rows), "displayed": M15_DISPLAY_BARS,
                 "future_space": M15_FUTURE_SPACE_BARS, "closed_only": True},
        "projection": {"mode": "none", "guaranteed": False,
                       "historical_data": False, "visible": False},
        "lifecycle": {
            "state": story["state"],
            "position_confirmed": False,
            "protective_stop_active": False,
            "protective_stop_activation": "external_fill_required",
            "protective_stop_status": (
                plan["protective_stop"]["status"] if plan else None),
            "protective_stop_activation_event": (
                plan["protective_stop"]["activation_event"] if plan else None),
            "plan_created_at": (plan.get("plan_created_at") if plan else None),
            "effective_from": (plan.get("effective_from") if plan else None),
        },
        "labels": {
            "close": "ราคาปิด M15",
            "close_right_tag": {"visible": True, "text": "ราคาปิด M15"},
            "ema20": "EMA20 สำหรับจังหวะ M15",
            "ema20_role": "legend_only",
            "ema20_right_tag": {"visible": False, "text": None},
            "state_badge": {"visible": True, "text": presentation["badge"],
                            "color": presentation["badge_color"]},
            "execution_levels": level_labels,
            "conditional_watch_levels": conditional_labels,
            "tag_offsets_points": {"close": close_tag_offset},
        },
        "output": {"format": "webp", "size_bytes": size_bytes,
                   "max_size_bytes": image_output.MAX_IMAGE_BYTES},
    })
    if conditional_labels:
        metadata["elements"]["conditional_projection"] = True
        metadata["labels"]["conditional_watch_levels"] = conditional_labels
    return {"path": str(output_path), "size_bytes": size_bytes,
            "metadata": copy.deepcopy(metadata)}


render = render_context


__all__ = [
    "RendererContractError", "metadata_contract", "context_metadata_contract",
    "execution_metadata_contract", "render_context", "render_execution", "render",
]
