from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from mpl_toolkits.axes_grid1.inset_locator import inset_axes


HERE = Path(__file__).resolve().parent
REPO = HERE.parent
P002 = REPO.parent
ROOT = P002.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools import (  # noqa: E402
    calendar_feed,
    candle_close,
    chart_indicator,
    headline_format,
    image_output,
    intraday_bars,
    intraday_breakout_story,
    intraday_indicators,
    intraday_pullback_story,
    intraday_story,
    intraday_trend_story,
    publish_layout,
    voice_rules,
    wcb_series_source,
    wcb_source,
)
from tools.chart_story_renderer import _thai_font, checked_label  # noqa: E402


STYLE_ID = "l_forex_daily_plan"
STYLE_LETTER = "L"
STYLE_NAME = "Style L — Forex Daily Trade Plan"
ASSETS = ("eurusd", "gbpusd", "usdjpy", "audusd", "usdcad")
TIMEFRAMES = ("4h", "1h", "30min", "15min")
PRODUCER = f"P002 {STYLE_NAME} production"
STYLE_FOLDER = "L-Forex-Daily"
STATE = REPO / "state" / "forex-daily-plan"
SCHEDULE_PATH = REPO / "config" / "forex_daily_schedule.json"
SCHEDULE_SCHEMA_VERSION = 2
SCHEDULE_TIMEZONE = "Asia/Bangkok"
EXPECTED_WEEKDAY_ASSET_BATCHES = {
    0: ("eurusd", "usdjpy"),
    1: ("gbpusd", "audusd"),
    2: ("eurusd", "usdjpy"),
    3: ("gbpusd", "usdcad"),
    4: ("eurusd", "usdjpy"),
}
SCHEDULE_KEYS = frozenset({
    "schema_version", "timezone", "description", "weekday_asset_batches",
    "weekend_policy", "swap_policy", "publish_lane", "gold_lane_unchanged",
})
DEPRECATED_COPY = (
    "สรุปใน 20 วินาที",
    "ข่าวที่ประกาศแล้วใช้เป็นบริบท",
    "ข้อมูลปฏิทินมีหน้าที่กำหนดช่วงหลีกเลี่ยง",
    "รอบอัปเดตถัดไป:",
    "เวลาจัดทำบทความ:",
)

DIRECT_CHART_ASSETS = frozenset({"eurusd", "gbpusd", "usdjpy", "audusd"})
WEB_IMPORT_ASSETS = DIRECT_CHART_ASSETS
WEB_IMPORT_HOLD_REASON = "WCB asset registry has no usdcad tag"
ASSET_HUB_PATH = "/thailand/asset-hub"
ANALYSIS_ARCHIVE_PATH = "/thailand/analysis"

STYLE_IDS = (
    intraday_trend_story.STYLE_ID,
    intraday_breakout_story.STYLE_ID,
    intraday_pullback_story.STYLE_ID,
)


def web_import_eligible(asset: str) -> bool:
    """Return whether WCB currently has a registered article asset tag."""
    return asset in WEB_IMPORT_ASSETS


def web_import_sources(staged_files: list[Path]) -> list[Path]:
    """Keep unregistered assets in evidence/staging, never in the web-import lane."""
    return [path for path in staged_files if web_import_eligible(path.parent.name)]


THAI_MONTHS = {
    1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.", 5: "พ.ค.", 6: "มิ.ย.",
    7: "ก.ค.", 8: "ส.ค.", 9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค.",
}


def load_schedule(path: Path = SCHEDULE_PATH) -> dict[int, tuple[str, str]]:
    """โหลด schema v2 และหยุดทันทีเมื่อคิวต่างจาก contract 5×2 ที่อนุมัติ."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(f"Forex schedule ใช้งานไม่ได้: {exc}") from exc

    if not isinstance(raw, dict):
        raise RuntimeError("Forex schedule ต้องเป็น object")
    if set(raw) != SCHEDULE_KEYS:
        raise RuntimeError("Forex schedule มี key ไม่ครบหรือเกินจาก schema v2")
    if (isinstance(raw["schema_version"], bool)
            or raw["schema_version"] != SCHEDULE_SCHEMA_VERSION):
        raise RuntimeError("Forex schedule ต้องใช้ schema_version 2")
    if raw["timezone"] != SCHEDULE_TIMEZONE:
        raise RuntimeError("Forex schedule ต้องใช้ timezone Asia/Bangkok")
    if not isinstance(raw["description"], str) or not raw["description"].strip():
        raise RuntimeError("Forex schedule ต้องมี description")
    if raw["weekend_policy"] != "skip":
        raise RuntimeError("Forex schedule ต้องข้ามเสาร์–อาทิตย์")
    if raw["swap_policy"] != "never":
        raise RuntimeError("Forex schedule ห้ามสลับคู่เงินอัตโนมัติ")
    if raw["publish_lane"] != "forex":
        raise RuntimeError("Forex schedule ต้องใช้ publish lane forex")
    if raw["gold_lane_unchanged"] is not True:
        raise RuntimeError("Forex schedule ต้องคง gold lane เดิม")

    schedule = raw["weekday_asset_batches"]
    if not isinstance(schedule, dict):
        raise RuntimeError("Forex schedule weekday_asset_batches ต้องเป็น object")
    if set(schedule) != {str(day) for day in range(5)}:
        raise RuntimeError("Forex schedule ต้องมีวันจันทร์ถึงศุกร์ครบ 0–4")

    parsed: dict[int, tuple[str, str]] = {}
    for day in range(5):
        batch = schedule[str(day)]
        if not isinstance(batch, list):
            raise RuntimeError(f"Forex schedule วันที่ {day} ต้องเป็น list")
        if len(batch) != 2:
            raise RuntimeError(f"Forex schedule วันที่ {day} ต้องมี 2 คู่")
        if any(not isinstance(asset, str) for asset in batch):
            raise RuntimeError(f"Forex schedule วันที่ {day} มีชนิด asset ไม่ถูกต้อง")
        if len(set(batch)) != 2:
            raise RuntimeError(f"Forex schedule วันที่ {day} ห้ามมีคู่ซ้ำ")
        unsupported = [asset for asset in batch if asset not in ASSETS]
        if unsupported:
            raise RuntimeError(
                f"Forex schedule วันที่ {day} มีคู่ที่ไม่รองรับ: {', '.join(unsupported)}")
        parsed[day] = (batch[0], batch[1])

    if parsed != EXPECTED_WEEKDAY_ASSET_BATCHES:
        raise RuntimeError("Forex schedule ไม่ตรงตาราง 10 บทต่อสัปดาห์ที่อนุมัติ")
    return parsed


def scheduled_assets(cutoff_at: str | datetime | None = None) -> list[str]:
    """คืนสองคู่ประจำวันตามเวลาไทย; เสาร์–อาทิตย์คืน list ว่าง."""
    cutoff = parse_cutoff(cutoff_at)
    local_date = cutoff.astimezone(wcb_source.BANGKOK).date()
    return list(load_schedule().get(local_date.weekday(), ()))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def closed_intraday(asset: str, timeframe: str, cutoff: datetime) -> tuple[list[dict], dict, dict]:
    meta, rows, source = intraday_bars.fetch_rows(
        asset, timeframe=timeframe, outputsize=500, now=cutoff)
    closed, basis = intraday_bars.evaluate(
        rows, asset=asset, timeframe=timeframe, now=cutoff)
    return closed, basis, {**meta, "source": source, "closed_count": len(closed),
                           "last_closed_at": closed[-1]["at"]}


def closed_daily(asset: str, cutoff: datetime) -> tuple[list[dict], dict, dict]:
    meta, rows, source = wcb_series_source.fetch_asset_rows(
        asset, count=120, interval="1day", now=cutoff, max_age_days=3)
    closed, basis = candle_close.evaluate(rows, asset=asset, now=cutoff)
    return closed, basis, {**meta, "source": source, "closed_count": len(closed),
                           "last_closed_date": closed[-1]["date"]}


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def h4_context(rows: list[dict]) -> dict:
    closes = [float(row["close"]) for row in rows]
    ema20 = chart_indicator.ema(closes, 20)
    ema50 = chart_indicator.ema(closes, 50)
    current = closes[-1]
    recent, prior = rows[-10:], rows[-20:-10]
    higher = (max(r["high"] for r in recent) > max(r["high"] for r in prior)
              and min(r["low"] for r in recent) > min(r["low"] for r in prior))
    lower = (max(r["high"] for r in recent) < max(r["high"] for r in prior)
             and min(r["low"] for r in recent) < min(r["low"] for r in prior))
    ema_up = current > ema20[-1] > ema50[-1]
    ema_down = current < ema20[-1] < ema50[-1]
    bias = "up" if ema_up and higher else "down" if ema_down and lower else None
    return {
        "bias": bias,
        "close": current,
        "ema20": ema20[-1], "ema50": ema50[-1],
        "structure": "higher_high_low" if higher else "lower_high_low" if lower else "mixed",
        "ema20_series": ema20, "ema50_series": ema50,
    }


def h1_map(rows: list[dict], daily: list[dict]) -> dict:
    volatility = intraday_indicators.atr(rows, 14)
    dates = sorted({row["date"] for row in rows})
    current_date = dates[-1]
    previous_date = dates[-2]
    today = [row for row in rows if row["date"] == current_date]
    previous = [row for row in rows if row["date"] == previous_date]
    adr14 = mean([float(row["high"]) - float(row["low"]) for row in daily[-14:]])
    current_range = max(r["high"] for r in today) - min(r["low"] for r in today)
    return {
        "date": current_date,
        "previous_date": previous_date,
        "close": float(rows[-1]["close"]),
        "pdh": max(r["high"] for r in previous),
        "pdl": min(r["low"] for r in previous),
        "current_high": max(r["high"] for r in today),
        "current_low": min(r["low"] for r in today),
        "current_range": current_range,
        "adr14": adr14,
        "adr_used_pct": current_range / adr14 * 100 if adr14 else None,
        "atr14": volatility["value"],
        "range_basis": f"แท่ง H1 ที่ปิดแล้วถึงเวลา {rows[-1]['at'][11:16]} น. (เวลาไทย)",
    }


def preview_styles(asset: str) -> dict:
    styles = copy.deepcopy(intraday_story.load_styles())
    for style_id in STYLE_IDS:
        if asset not in styles[style_id]["assets"]:
            styles[style_id]["assets"].append(asset)
        styles[style_id]["production"] = False
    return styles


def intraday_state(asset: str, rows: dict, bases: dict) -> dict:
    styles = preview_styles(asset)
    params = intraday_story.load_params()
    result: dict[str, object] = {"skipped": []}
    builders = (
        ("H", lambda: intraday_trend_story.build(
            rows["30min"], asset=asset, timeframe="30min",
            candle_basis=bases["30min"], previous_state=None,
            params=params, styles=styles)),
        ("I", lambda: intraday_breakout_story.build(
            rows["15min"], asset=asset, timeframe="15min",
            candle_basis=bases["15min"], previous_state=None,
            params=params, styles=styles)),
        ("J", lambda: intraday_pullback_story.build(
            rows["30min"], rows["15min"], asset=asset,
            context_timeframe="30min", trigger_timeframe="15min",
            candle_basis=bases["15min"], context_basis=bases["30min"],
            previous_state=None, params=params, styles=styles)),
    )
    for letter, build in builders:
        try:
            result[letter] = build()
        except intraday_story.StoryUnavailable as exc:
            result["skipped"].append({"style": letter, "reason": str(exc)})
    return result


def choose_model(bias: str | None, states: dict) -> tuple[str, str]:
    if bias is None:
        return "NO_SETUP", "H4 ยังไม่ให้ bias ที่ EMA และโครงสร้างยืนยันพร้อมกัน"
    h = states.get("H") or {}
    if h.get("direction") != bias or float((h.get("dmi") or {}).get("adx", 0)) < 20:
        return "WAIT", "M30 ยังไม่ยืนยันทิศ H4 ด้วย DMI/ADX และ Supertrend"
    i = states.get("I") or {}
    j = states.get("J") or {}
    j_states = {"PULLBACK_FORMING", "PULLBACK_CONFIRMED", "TREND_RESUMED"}
    if j.get("direction") == bias and j.get("state") in j_states:
        return "J", f"J อยู่ในสถานะ {j['state']} ตาม bias {bias}"
    breakout = "BREAKOUT_UP" if bias == "up" else "BREAKOUT_DOWN"
    if i.get("state") == breakout:
        return "I", f"I ยืนยัน {breakout} ตาม bias {bias}"
    if i.get("state") in {"COMPRESSION", "ARMED"}:
        return "I_WATCH", f"I อยู่ในสถานะ {i['state']} รอปิดพ้นกรอบตาม bias"
    return "WAIT", "M15 ยังไม่เข้าเงื่อนไข breakout หรือ pullback ที่สอดคล้องกับภาพใหญ่"


def preferred_direction(h4: dict) -> tuple[str, str]:
    """เลือกฝั่งเดียวแบบลำดับชั้น โดยไม่เปลี่ยน readiness ของ setup."""
    if h4.get("bias") in {"up", "down"}:
        direction = str(h4["bias"])
        return direction, "EMA และโครงสร้าง H4 ยืนยันไปทางเดียวกัน"
    if h4.get("structure") == "higher_high_low":
        return "up", "โครงสร้าง H4 ยกทั้งจุดสูงและจุดต่ำ แม้ EMA ยังไม่เรียงตัวครบ"
    if h4.get("structure") == "lower_high_low":
        return "down", "โครงสร้าง H4 ลดทั้งจุดสูงและจุดต่ำ แม้ EMA ยังไม่เรียงตัวครบ"
    midpoint = (float(h4["ema20"]) + float(h4["ema50"])) / 2
    if float(h4["close"]) >= midpoint:
        return "up", "โครงสร้าง H4 ยังผสม จึงให้น้ำหนักจากราคาที่อยู่เหนือกึ่งกลาง EMA20/50"
    return "down", "โครงสร้าง H4 ยังผสม จึงให้น้ำหนักจากราคาที่อยู่ใต้กึ่งกลาง EMA20/50"


def scenario(model: str, bias: str | None, preferred: str,
             h1: dict, states: dict) -> dict:
    if model not in {"I", "J"}:
        i = states.get("I") or {}
        return {"active": False, "direction": preferred,
                "watch_low": (i.get("donchian") or {}).get("lower", h1["pdl"]),
                "watch_high": (i.get("donchian") or {}).get("upper", h1["pdh"])}
    atr = float(h1["atr14"])
    if model.startswith("I") and states.get("I"):
        channel = states["I"]["donchian"]
        entry = float(channel["upper"] if bias == "up" else channel["lower"])
    elif model == "J" and states.get("J"):
        zone = states["J"]["pullback_zone"]
        entry = (float(zone["low"]) + float(zone["high"])) / 2
    else:
        entry = float(h1["pdh"] if bias == "up" else h1["pdl"])
    sign = 1 if bias == "up" else -1
    stop = entry - sign * atr
    target1 = entry + sign * atr
    target2 = entry + sign * atr * 2
    valid = stop < entry < target1 < target2 if bias == "up" else target2 < target1 < entry < stop
    if not valid:
        raise RuntimeError(f"scenario ordering invalid for {bias}")
    return {"active": model in {"I", "J"}, "direction": bias,
            "entry": entry, "stop": stop, "target1": target1, "target2": target2,
            "invalidation_h1": h1["pdl"] if bias == "up" else h1["pdh"]}


def fetch_events(cutoff: datetime) -> tuple[list[dict], dict]:
    start = cutoff.date().isoformat()
    end = (cutoff.date() + timedelta(days=2)).isoformat()
    try:
        raw = calendar_feed.fetch_raw(from_date=start, to_date=end)
        events = calendar_feed.to_calendar_events(raw)
        return events, {"status": "ok", "count": len(events),
                        "sha256": sha(raw), "retrieved_at": raw.get("retrieved_at")}
    except calendar_feed.CalendarFeedUnusable as exc:
        return [], {"status": "unavailable", "reason": str(exc)}


def event_datetime(event: dict) -> datetime | None:
    raw = event.get("at")
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw), "%Y-%m-%d %H:%M").replace(
            tzinfo=wcb_source.BANGKOK)
    except ValueError:
        return None


def relevant_events(asset: str, events: list[dict], cutoff: datetime) -> list[dict]:
    countries = {
        "eurusd": {"EUR", "USD"}, "gbpusd": {"GBP", "USD"},
        "usdjpy": {"USD", "JPY"},
        "audusd": {"AUD", "USD"}, "usdcad": {"CAD", "USD"},
    }[asset]
    selected = [event for event in events
                if str(event.get("country", "")).upper() in countries
                and str(event.get("impact", "")).title() in {"High", "Medium"}]
    cutoff_th = cutoff.astimezone(wcb_source.BANGKOK)
    selected.sort(key=lambda event: event_datetime(event) or cutoff_th)
    announced = [event for event in selected
                 if event_datetime(event) and event_datetime(event) <= cutoff_th]
    upcoming = [event for event in selected
                if event_datetime(event) and event_datetime(event) > cutoff_th]
    # เก็บเรื่องราวล่าสุดและข่าวถัดไป ไม่ปล่อยให้รายการเก่าบัง USD event ที่ยังไม่ประกาศ
    return announced[-4:] + upcoming[:4]


def fmt(asset: str, value: float) -> str:
    return f"{value:,.{wcb_source.profile_for(asset)['decimals']}f}"


def bias_th(bias: str | None) -> str:
    return {"up": "เอนขึ้น", "down": "เอนลง"}.get(bias, "ยังเป็นกลาง")


def side_code(direction: str) -> str:
    return "BUY" if direction == "up" else "SELL"


def structure_th(structure: str) -> str:
    return {
        "higher_high_low": "จุดสูงและจุดต่ำยกขึ้น",
        "lower_high_low": "จุดสูงและจุดต่ำลดลง",
        "mixed": "จุดสูงและจุดต่ำยังสลับกัน",
    }.get(structure, "โครงสร้างยังไม่ชัด")


def ema_position_th(asset: str, h4: dict) -> str:
    close = float(h4["close"])
    ema20 = float(h4["ema20"])
    ema50 = float(h4["ema50"])
    if close > max(ema20, ema50):
        position = "ราคาอยู่เหนือ EMA20 และ EMA50"
    elif close < min(ema20, ema50):
        position = "ราคาอยู่ใต้ EMA20 และ EMA50"
    else:
        position = "ราคาอยู่ระหว่าง EMA20 และ EMA50"
    return (f"{position} โดยปิดที่ {fmt(asset, close)} เทียบกับ EMA20 "
            f"{fmt(asset, ema20)} และ EMA50 {fmt(asset, ema50)}")


def m30_read(h: dict, direction: str) -> str:
    adx = float((h.get("dmi") or {}).get("adx", 0))
    dmi = h.get("dmi") or {}
    plus_di = float(dmi.get("plus_di", 0))
    minus_di = float(dmi.get("minus_di", 0))
    supertrend = str((h.get("supertrend") or {}).get("direction", ""))
    threshold = float((h.get("thresholds") or {}).get("no_trend", 20))
    di_ok = plus_di > minus_di if direction == "up" else minus_di > plus_di
    super_ok = supertrend == direction
    adx_ok = adx >= threshold
    side = side_code(direction)
    if di_ok and super_ok and adx_ok:
        return (f"M30 ผ่านกฎฝั่ง {side}: DMI ชี้ทางเดียวกัน "
                f"(+DI {plus_di:.1f} / -DI {minus_di:.1f}), Supertrend อยู่ฝั่งเดียวกัน "
                f"และ ADX {adx:.1f} สูงกว่าเกณฑ์ {threshold:.0f}")
    missing = []
    if not di_ok:
        missing.append("DMI ยังไม่ชี้ฝั่งเดียวกัน")
    if not super_ok:
        missing.append("ราคายังไม่ยืนฝั่งเดียวกันของ Supertrend")
    if not adx_ok:
        missing.append(f"ADX {adx:.1f} ยังต่ำกว่า {threshold:.0f}")
    return f"M30 ยังไม่ผ่านกฎฝั่ง {side}: " + "; ".join(missing)


def m30_gate_pass(h: dict, direction: str) -> bool:
    dmi = h.get("dmi") or {}
    plus_di = float(dmi.get("plus_di", 0))
    minus_di = float(dmi.get("minus_di", 0))
    di_ok = plus_di > minus_di if direction == "up" else minus_di > plus_di
    super_ok = str((h.get("supertrend") or {}).get("direction", "")) == direction
    threshold = float((h.get("thresholds") or {}).get("no_trend", 20))
    return di_ok and super_ok and float(dmi.get("adx", 0)) >= threshold


def m30_rule(direction: str) -> str:
    if direction == "up":
        return "+DI มากกว่า -DI, ราคาปิดเหนือ Supertrend และ ADX อย่างน้อย 20"
    return "-DI มากกว่า +DI, ราคาปิดใต้ Supertrend และ ADX อย่างน้อย 20"


def watch_cancel_rule(asset: str, h4: dict, direction: str) -> str:
    edge = max(float(h4["ema20"]), float(h4["ema50"])) if direction == "down" else min(
        float(h4["ema20"]), float(h4["ema50"]))
    if direction == "down":
        return (f"ยกเลิกแผนเฝ้ารอหาก H4 ปิดเหนือ EMA ทั้งคู่บริเวณ {fmt(asset, edge)} "
                "และโครงสร้างไม่ทำ Lower High/Lower Low ต่อ")
    return (f"ยกเลิกแผนเฝ้ารอหาก H4 ปิดใต้ EMA ทั้งคู่บริเวณ {fmt(asset, edge)} "
            "และโครงสร้างไม่ทำ Higher High/Higher Low ต่อ")


def basis_close_label(basis: dict) -> str:
    raw = str(basis.get("basis_close_at") or "")
    try:
        when = datetime.fromisoformat(raw).astimezone(wcb_source.BANGKOK)
        return when.strftime("%H:%M น.")
    except ValueError:
        return "ไม่ระบุ"


def thai_tick(raw: str) -> str:
    try:
        when = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        return f"{when.day} {THAI_MONTHS[when.month]}\n{when:%H:%M}"
    except ValueError:
        return raw[5:16]


def m15_read(i: dict, j: dict, model: str, direction: str) -> str:
    wanted = "ขาขึ้น" if direction == "up" else "ขาลง"
    if model == "J":
        return f"M15 อยู่ในช่วงย่อตัวตามบริบท{wanted} รอแท่งปิดยืนยันการกลับไปตามทิศหลัก"
    if model == "I":
        return f"M15 ปิดเบรกกรอบตามบริบท{wanted}แล้ว จึงเลื่อนแผนเป็น ACTIVE"
    if i.get("state") in {"COMPRESSION", "ARMED"}:
        return "M15 กำลังบีบตัวใกล้กรอบตัดสินใจ จึงรอการปิดแท่งเลือกทาง"
    return f"M15 ยังไม่ยืนยันจังหวะ{wanted} จึงคงสถานะรอ"


def technical_context(i: dict, j: dict) -> str:
    bbw = float((i.get("bbw") or {}).get("percentile", 0))
    chop = float((j.get("chop") or {}).get("value", 0))
    if bbw >= 65 and chop <= 45:
        meaning = "ความผันผวนกำลังขยายและตลาดเริ่มเคลื่อนเป็นทิศมากขึ้น"
    elif bbw <= 35 or chop >= 55:
        meaning = "ตลาดยังแกว่งตัวและมีความเสี่ยงเกิดสัญญาณหลอก"
    else:
        meaning = "ตลาดอยู่ช่วงเปลี่ยนผ่าน จึงยังต้องให้น้ำหนักกับแท่งปิดมากกว่าความเร็วระหว่างแท่ง"
    return (f"Bollinger Bands อยู่ใน percentile {bbw:.1f} และ CHOP อยู่ที่ {chop:.1f} "
            f"ภาพรวมสะท้อนว่า{meaning} ตัวเลขนี้ใช้บอกสภาพตลาด ไม่ได้เลือกทิศแทนราคา")


def candle_plot(ax, rows: list[dict]) -> None:
    for index, row in enumerate(rows):
        up = row["close"] >= row["open"]
        color = "#1f9d8a" if up else "#e05252"
        ax.vlines(index, row["low"], row["high"], color=color, linewidth=0.8, zorder=2)
        low = min(row["open"], row["close"])
        height = max(abs(row["close"] - row["open"]), 1e-8)
        ax.add_patch(Rectangle((index - 0.32, low), 0.64, height,
                               facecolor=color, edgecolor=color, linewidth=0.6, zorder=3))
    ax.grid(True, color="#edf0f4", linewidth=0.7)
    for spine in ax.spines.values():
        spine.set_color("#d1d4dc")


def h4_inset_enabled(asset: str) -> bool:
    """USDJPY ใช้ H1 เต็มภาพตามบรีฟ ส่วนอีกสองคู่คงกรอบย่อ H4."""
    return asset != "usdjpy"


def add_price_line(ax, value: float, text: str, color: str, *, style: str = "--",
                   label_offset: int = 0) -> None:
    ax.axhline(value, color=color, linestyle=style, linewidth=1.2, alpha=0.9)
    ax.annotate(checked_label(text), xy=(0.995, value),
                xycoords=("axes fraction", "data"), xytext=(0, label_offset),
                textcoords="offset points", ha="right", va="bottom",
                fontsize=9.5, color="#ffffff",
                bbox={"boxstyle": "round,pad=0.25", "facecolor": color,
                      "edgecolor": color})


def save_h1_chart(asset: str, rows: list[dict], h4_rows: list[dict], h4: dict,
                  h1: dict, plan: dict, preferred: str, basis: dict,
                  path: Path) -> int:
    _thai_font()
    view = rows[-100:]
    closes = [float(row["close"]) for row in view]
    ema20 = chart_indicator.ema(closes, 20)
    ema50 = chart_indicator.ema(closes, 50)
    fig, ax = plt.subplots(figsize=(14, 7.5))
    candle_plot(ax, view)
    if plan.get("active"):
        zone_low = min(plan["entry"], plan["stop"])
        zone_high = max(plan["entry"], plan["stop"])
    else:
        zone_low = plan["watch_low"]
        zone_high = plan["watch_high"]
    zone_name = "โซนแผน" if plan.get("active") else "โซนรอ"
    ax.axhspan(zone_low, zone_high, color="#f4c95d",
               alpha=0.16, zorder=0)
    ax.text(0.012, 0.08, checked_label(
        f"{zone_name} {fmt(asset, zone_low)}–{fmt(asset, zone_high)}"),
        transform=ax.transAxes, fontsize=10.5, color="#7c5b00",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "#fff7d6",
              "edgecolor": "#d6a800"})
    x = list(range(len(view)))
    ax.plot(x, ema20, color="#ef7d00", linewidth=1.5, label="EMA20")
    ax.plot(x, ema50, color="#168aad", linewidth=1.5, label="EMA50")
    add_price_line(ax, h1["pdh"], f"PDH {fmt(asset, h1['pdh'])}", "#2d6cdf",
                   label_offset=5)
    add_price_line(ax, h1["pdl"], f"PDL {fmt(asset, h1['pdl'])}", "#7b61a8")
    add_price_line(ax, h1["close"], f"ปิดล่าสุด {fmt(asset, h1['close'])}", "#111827",
                   style="-", label_offset=-6)
    profile = wcb_source.profile_for(asset)
    ax.set_title(checked_label(
        f"{profile['symbol']} · แผนที่ราคา H1 — ให้น้ำหนัก {side_code(preferred)}"),
                 fontsize=19, fontweight="bold", loc="left")
    ax.text(0.01, 0.97, checked_label(
        f"ATR H1 {fmt(asset, h1['atr14'])} · ADR {fmt(asset, h1['adr14'])} · "
        f"ใช้ระยะแล้ว {h1['adr_used_pct']:.1f}% · ปิดล่าสุด {basis_close_label(basis)}"),
        transform=ax.transAxes, va="top", fontsize=11.5, color="#111827",
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "#ffffff", "edgecolor": "#d1d4dc"})

    # ตามมติผู้ใช้ USDJPY ใช้ H1 เต็มภาพโดยไม่วางกรอบ H4 ซ้อน
    if h4_inset_enabled(asset):
        h4_view = h4_rows[-40:]
        inset = inset_axes(ax, width="34%", height="34%", loc="lower left",
                           bbox_to_anchor=(0.03, 0.14, 1, 1), bbox_transform=ax.transAxes,
                           borderpad=0)
        inset.set_facecolor("#ffffff")
        candle_plot(inset, h4_view)
        recent_start = len(h4_view) - 10
        recent = h4_view[-10:]
        high_idx = recent_start + max(range(len(recent)), key=lambda k: recent[k]["high"])
        low_idx = recent_start + min(range(len(recent)), key=lambda k: recent[k]["low"])
        high_tag = "HH" if h4["structure"] == "higher_high_low" else "LH" if h4["structure"] == "lower_high_low" else "H"
        low_tag = "HL" if h4["structure"] == "higher_high_low" else "LL" if h4["structure"] == "lower_high_low" else "L"
        inset.scatter([high_idx], [h4_view[high_idx]["high"]], color="#7c3aed", s=24, zorder=5)
        inset.scatter([low_idx], [h4_view[low_idx]["low"]], color="#7c3aed", s=24, zorder=5)
        inset.annotate(high_tag, (high_idx, h4_view[high_idx]["high"]), xytext=(0, 7),
                       textcoords="offset points", ha="center", fontsize=8, color="#6d28d9")
        inset.annotate(low_tag, (low_idx, h4_view[low_idx]["low"]), xytext=(0, -12),
                       textcoords="offset points", ha="center", fontsize=8, color="#6d28d9")
        inset.set_title(checked_label(f"H4 · {structure_th(h4['structure'])}"), fontsize=9, loc="left")
        inset.set_xticks([])
        inset.tick_params(axis="y", labelsize=7)
    ticks = list(range(0, len(view), max(1, len(view)//7)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([thai_tick(view[i]["at"]) for i in ticks], fontsize=9)
    ax.set_ylabel(checked_label("ราคา"))
    fig.text(0.01, 0.01, checked_label(
        f"ข้อมูลแท่ง H1 ปิดถึง {basis_close_label(basis)} · ADR ใช้วัดระยะ ไม่ใช้ยืนยันทิศทาง"),
        fontsize=9, color="#6b7280")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    size = image_output.save_figure(fig, path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return size


def save_m15_chart(asset: str, rows: list[dict], model: str, states: dict,
                   plan: dict, preferred: str, basis: dict, path: Path) -> int:
    _thai_font()
    view = rows[-120:]
    fig, ax = plt.subplots(figsize=(14, 7.5))
    candle_plot(ax, view)
    i = states.get("I") or {}
    trigger = plan.get("entry") or (
        plan["watch_high"] if preferred == "up" else plan["watch_low"])
    if not plan.get("active"):
        opposite = plan["watch_low"] if preferred == "up" else plan["watch_high"]
        ax.axhspan(plan["watch_low"], plan["watch_high"], color="#cbd5e1",
                   alpha=0.22, zorder=0)
        ax.text(0.50, 0.50, checked_label("NO TRADE / รอยืนยัน"),
                transform=ax.transAxes, ha="center", va="center", fontsize=18,
                color="#64748b", fontweight="bold", alpha=0.85)
        add_price_line(ax, trigger,
                       f"{side_code(preferred)} Trigger — รอ M15 ปิด"
                       f"{'เหนือ' if preferred == 'up' else 'ต่ำกว่า'} {fmt(asset, trigger)}",
                       "#7c3aed", style="-", label_offset=7 if preferred == "up" else -9)
        add_price_line(ax, opposite, f"ขอบโซนรอ {fmt(asset, opposite)}", "#94a3b8")
        y_span = max(row["high"] for row in view) - min(row["low"] for row in view)
        arrow_y = trigger + (0.11 * y_span if preferred == "up" else -0.11 * y_span)
        ax.annotate(checked_label(f"พื้นที่พิจารณา {side_code(preferred)} หลังแท่งปิด"),
                    xy=(len(view) - 12, trigger), xytext=(len(view) - 42, arrow_y),
                    fontsize=10.5, color="#6d28d9",
                    arrowprops={"arrowstyle": "->", "color": "#7c3aed", "lw": 1.8},
                    bbox={"boxstyle": "round,pad=0.3", "facecolor": "#f5f3ff",
                          "edgecolor": "#7c3aed"})
    elif i:
        add_price_line(ax, i["donchian"]["upper"],
                       f"Donchian บน {fmt(asset, i['donchian']['upper'])}", "#e5a11a",
                       label_offset=6)
        add_price_line(ax, i["donchian"]["lower"],
                       f"Donchian ล่าง {fmt(asset, i['donchian']['lower'])}", "#e5a11a",
                       label_offset=-6)
    if plan.get("active"):
        add_price_line(ax, plan["entry"], f"Entry trigger {fmt(asset, plan['entry'])}", "#2563eb",
                       label_offset=7)
        add_price_line(ax, plan["stop"], f"Invalidation {fmt(asset, plan['stop'])}", "#dc2626")
        add_price_line(ax, plan["target1"], f"Target 1 {fmt(asset, plan['target1'])}", "#15803d",
                       label_offset=-7)
        add_price_line(ax, plan["target2"], f"Target 2 {fmt(asset, plan['target2'])}", "#166534")
    profile = wcb_source.profile_for(asset)
    h = states.get("H") or {}
    readiness = "พร้อมเมื่อแท่งปิดยืนยัน" if plan.get("active") else "รอยืนยัน"
    ax.set_title(checked_label(
        f"{profile['symbol']} · Trigger map M15 — {side_code(preferred)} · {readiness}"),
                 fontsize=18, fontweight="bold", loc="left", x=0.015)
    gate_badge = "M30: สนับสนุนแล้ว" if m30_gate_pass(h, preferred) else "M30: ยังไม่สนับสนุนครบ"
    trigger_badge = "M15: Trigger แล้ว" if plan.get("active") else "M15: ยังไม่ Trigger"
    ax.text(0.01, 0.97, checked_label(
        f"สถานะ: {'ACTIVE' if plan.get('active') else 'WAIT'}  ·  {gate_badge}  ·  {trigger_badge}"),
        transform=ax.transAxes, va="top", fontsize=11.5, color="#111827",
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "#ffffff", "edgecolor": "#d1d4dc"})
    ticks = list(range(0, len(view), max(1, len(view)//7)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([thai_tick(view[i]["at"]) for i in ticks], fontsize=9)
    ax.set_ylabel(checked_label("ราคา"))
    fig.text(0.01, 0.01, checked_label(
        f"ข้อมูลแท่ง M15 ปิดถึง {basis_close_label(basis)} · เข้าเมื่อแท่งปิดยืนยันเท่านั้น"),
        fontsize=9, color="#6b7280")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    size = image_output.save_figure(fig, path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return size


def event_label(event: dict) -> str:
    when = str(event.get("at") or event.get("date") or "ไม่ระบุเวลา")
    iso_date = re.match(r"^(\d{4})-(\d{2})-(\d{2})(.*)$", when)
    if iso_date:
        year, month, day, remainder = iso_date.groups()
        when = f"{day}-{month}-{year}{remainder}"
    title = str(event.get("title") or event.get("title_th")
                or event.get("title_en") or "ไม่ระบุชื่อ")
    return f"`{event.get('country')}` · {when} · {title}"


def event_sections(events: list[dict], cutoff: datetime) -> tuple[list[str], str]:
    cutoff_th = cutoff.astimezone(wcb_source.BANGKOK)
    rows: list[str] = []
    next_label = "ไม่มีรายการถัดไปในช่วงปฏิทินที่ดึงมา"
    for event in events:
        when = event_datetime(event)
        label_parts = [part.strip() for part in event_label(event).split(" · ", 2)]
        country, event_time, title = label_parts
        if when and when <= cutoff_th:
            actual = event.get("actual")
            previous = event.get("previous")
            if actual:
                detail = f"Actual `{actual}`"
                if previous:
                    detail += f" / Previous `{previous}`"
            else:
                detail = "Actual ยังไม่มีค่าที่ตรวจสอบได้ จึงไม่ตีความผล"
            rows.append(
                f"| ประกาศแล้ว | {country} | {event_time} | {title} | {detail} |")
        elif when:
            detail = []
            if event.get("forecast"):
                detail.append(f"Forecast `{event['forecast']}`")
            if event.get("previous"):
                detail.append(f"Previous `{event['previous']}`")
            rows.append(
                f"| รอติดตาม | {country} | {event_time} | {title} | "
                f"{' / '.join(detail) if detail else '—'} |")
            if next_label.startswith("ไม่มี"):
                next_label = event_label(event).replace("`", "")
    if not rows:
        rows = ["| — | — | — | ไม่มีรายการ Medium/High ในช่วงข้อมูลนี้ | — |"]
    return rows, next_label


def continuity_snapshot(asset: str, cutoff: datetime, preferred: str,
                        plan: dict) -> tuple[dict, dict]:
    trigger = plan.get("entry") or (
        plan["watch_high"] if preferred == "up" else plan["watch_low"])
    current = {
        "date": cutoff.astimezone(wcb_source.BANGKOK).date().isoformat(),
        "cutoff_utc": cutoff.isoformat(),
        "side": side_code(preferred),
        "status": "ACTIVE" if plan.get("active") else "WAIT",
        "trigger": trigger,
    }
    path = STATE / f"{asset}-continuity.json"
    previous = None
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous = None
    if not previous or previous.get("date") == current["date"]:
        same_day_change = None
        if previous:
            same_day_change = ("ฝั่งและสถานะยังเหมือนรอบก่อนวันนี้"
                               if (previous.get("side"), previous.get("status")) ==
                               (current["side"], current["status"])
                               else f"เทียบรอบก่อนวันนี้ เปลี่ยนเป็น {current['side']} / {current['status']}")
        summary = {
            "previous": "ยังไม่มี baseline จากวันก่อน จึงไม่สรุปผลย้อนหลัง",
            "change": same_day_change or "วันนี้เป็น baseline วันแรกสำหรับติดตามสถานะแผน",
        }
    else:
        summary = {
            "previous": (f"วันก่อนให้น้ำหนัก {previous.get('side')} และอยู่สถานะ "
                         f"{previous.get('status')} ที่ trigger {fmt(asset, float(previous.get('trigger')))}"),
            "change": ("ฝั่งและสถานะยังเหมือนเดิม"
                       if (previous.get("side"), previous.get("status")) ==
                       (current["side"], current["status"])
                       else f"เปลี่ยนเป็น {current['side']} / {current['status']}"),
        }
    return current, summary


def render_article(asset: str, cutoff: datetime, h4: dict, h1: dict, states: dict,
                   model: str, reason: str, plan: dict, preferred: str,
                   preferred_reason: str, events: list[dict],
                   input_hash: str, images: tuple[str, str], bases: dict,
                   continuity: dict) -> str:
    profile = wcb_source.profile_for(asset)
    h = states.get("H") or {}
    i = states.get("I") or {}
    j = states.get("J") or {}
    cutoff_th = cutoff.astimezone(wcb_source.BANGKOK)
    cutoff_label = cutoff_th.strftime("%d/%m/%Y %H:%M น. เวลาไทย")
    date_text = cutoff_th.date().isoformat()
    is_active = bool(plan.get("active"))
    plan_name = "แผนเทรดรายวัน" if is_active else "แผนเฝ้ารอ"
    title = headline_format.title(asset, date_text, f"{plan_name}จาก H4 ถึง M15")
    slug = f"{asset}-forex-daily-plan-{date_text}"
    side = side_code(preferred)
    status_excerpt = ("มีจังหวะตามเงื่อนไขของแผน"
                      if is_active else "ยังรอกรอบย่อยยืนยันก่อนเข้า")
    excerpt = (f"อัปเดต{plan_name} {profile['symbol']} จาก H4 ถึง M15 "
               f"ให้น้ำหนักฝั่ง {side} และ{status_excerpt} พร้อมระดับราคาและข่าวสำคัญประจำวัน")
    trend = preferred
    trigger = plan.get("entry") or (
        plan["watch_high"] if preferred == "up" else plan["watch_low"])
    trigger_word = "เหนือ" if preferred == "up" else "ต่ำกว่า"
    cancel_rule = (f"ยกเลิก setup หากแตะจุดยกเลิก {fmt(asset, plan['stop'])}; "
                   f"หาก H1 ปิดสวนผ่าน {fmt(asset, plan['invalidation_h1'])} ให้ประเมินใหม่"
                   if is_active else watch_cancel_rule(asset, h4, preferred))
    news_rows, next_event = event_sections(events, cutoff)
    status = "ACTIVE" if is_active else "WAIT — ยังไม่เปิดสถานะ"
    m30_status = "ผ่าน" if m30_gate_pass(h, preferred) else "ยังไม่ผ่าน"
    time_rows = " · ".join(
        f"{name} {basis_close_label(bases[key])}"
        for name, key in (("H4", "4h"), ("H1", "1h"), ("M30", "30min"), ("M15", "15min")))
    if is_active:
        lead = (f"ภาพใหญ่ H4 ให้น้ำหนัก {side} ขณะที่ M30 และ M15 ผ่านด่านของระบบแล้ว "
                f"แผนจึงอยู่สถานะ ACTIVE โดยใช้ {fmt(asset, plan['entry'])} เป็น trigger "
                f"และ {fmt(asset, plan['stop'])} เป็นจุดยกเลิก")
    else:
        lead = (f"ภาพใหญ่ H4 ให้น้ำหนัก {side} แต่ M30 {m30_status}ตามกฎของระบบ "
                f"และ M15 ยังต้องปิด{trigger_word} {fmt(asset, trigger)} "
                "ดังนั้นแผนปัจจุบันคือรอและยังไม่เปิดสถานะ")
    h1_alt = (f"แผนที่ราคา H1 ของ {profile['symbol']}" if asset == "usdjpy"
              else f"แผนที่ราคา H1 พร้อมกรอบย่อ H4 ของ {profile['symbol']}")
    lines = [
        "---", f"asset: {asset}", f"title: {title}", f"slug: {slug}",
        f"excerpt: {excerpt}", "author_slug: world-class-broker-team",
        "timeframe: Daily", f"trend: {trend}", "status: draft",
        "country: thailand", "language: th", "---", "",
        f"# {plan_name} — {profile['symbol']}", "",
        "## ภาพรวมตลาดวันนี้", "",
        "| รายการ | สถานะ |", "| --- | --- |",
        f"| มุมมองหลัก | **{side}** |",
        f"| สถานะตอนนี้ | **{status}** |",
        f"| Trigger | M15 ปิด{trigger_word} `{fmt(asset, trigger)}` |",
        f"| เงื่อนไข M30 | {m30_status} — {m30_rule(preferred)} |",
        f"| จุดยกเลิก | {cancel_rule} |",
        f"| ข่าวถัดไป | {next_event} |",
        f"| อัปเดตล่าสุด | {cutoff_th.strftime('%H:%M น.')} เวลาไทย |", "",
        f"**ฝั่งที่ให้น้ำหนัก: {side}**", "",
        indent_paragraph(lead), "",
        indent_paragraph(
            f"กราฟ H4 มีลักษณะ{structure_th(h4['structure'])} และ{ema_position_th(asset, h4)} "
            f"จึงเลือกติดตามฝั่ง {side} เพียงฝั่งเดียว เหตุผลหลักคือ {preferred_reason}"), "",
        indent_paragraph(
            f"{m30_read(h, preferred)} ราคาปิด H1 ล่าสุดอยู่ที่ {fmt(asset, h1['close'])}"), "",
        f"![{h1_alt}]({images[0]})", "",
        "**แผนที่ราคาและระยะของวัน**", "",
        f"- High/Low วันก่อน: `{fmt(asset, h1['pdh'])}` / `{fmt(asset, h1['pdl'])}`",
        f"- ช่วงจากแท่ง H1 ที่ปิดแล้ววันนี้: `{fmt(asset, h1['current_low'])}`–`{fmt(asset, h1['current_high'])}`",
        f"- ATR14 H1: `{fmt(asset, h1['atr14'])}`",
        f"- ADR14 จากแท่ง D1 ปิด: `{fmt(asset, h1['adr14'])}`",
        f"- ช่วงที่ใช้แล้ว: `{h1['adr_used_pct']:.1f}%` ของ ADR14",
        "- ADR/ATR ใช้ประเมินระยะและความผันผวน ไม่ใช้ยืนยันทิศทาง",
        f"- เวลาแท่งปิดล่าสุด: {time_rows}", "",
        "**ความต่อเนื่องของแผน**", "",
        f"- เมื่อวาน/รอบก่อน: {continuity['previous']}",
        f"- วันนี้เปลี่ยนอะไร: {continuity['change']}",
        f"- เส้นทางสถานะ: `WAIT` → `ACTIVE` → `CANCELLED/COMPLETED` (ปัจจุบัน `{status.split(' —')[0]}`)", "",
        "## จังหวะและแผนการเทรด", "",
        indent_paragraph(m15_read(i, j, model, preferred)), "",
        f"![Trigger map M15 ของ {profile['symbol']}]({images[1]})", "",
        "**แผนตามสถานการณ์**", "",
    ]
    if is_active:
        lines += [
            f"**แผนฝั่ง {side} — สถานะ ACTIVE**",
            f"- Entry trigger: `{fmt(asset, plan['entry'])}`",
            f"- จุดยกเลิก: `{fmt(asset, plan['stop'])}`",
            f"- Target 1 / Target 2: `{fmt(asset, plan['target1'])}` / `{fmt(asset, plan['target2'])}`",
            f"- หาก H1 ปิดสวนผ่าน `{fmt(asset, plan['invalidation_h1'])}` ให้ยกเลิก bias และประเมินใหม่ ไม่กลับฝั่งอัตโนมัติ", "",
        ]
    else:
        lines += [
            f"**Pre-trigger plan ฝั่ง {side} — สถานะ WAIT**",
            f"- กรอบเฝ้าดู: `{fmt(asset, plan['watch_low'])}`–`{fmt(asset, plan['watch_high'])}`",
            f"- M30 ต้องผ่านครบ: {m30_rule(preferred)}",
            f"- จากนั้น M15 ต้องปิด{trigger_word} `{fmt(asset, trigger)}`; การแตะระดับระหว่างแท่งยังไม่นับ",
            f"- {cancel_rule}",
            "- ก่อนเงื่อนไขครบยังไม่มี Entry, Stop Loss หรือ Take Profit; การแตะระดับระหว่างแท่งไม่ใช่สัญญาณ", "",
        ]
    lines += [
        "**ข้อมูลเชิงเทคนิคเพิ่มเติม**", "",
        indent_paragraph(technical_context(i, j)), "",
        "**การควบคุมความเสี่ยง**", "",
        indent_paragraph("อย่าไล่ราคาหากแท่งยืนยันวิ่งเลย trigger มากผิดปกติเมื่อเทียบกับ ATR14 และอย่าขยายจุดยกเลิกเพื่อรองรับการเข้าช้า หาก spread หรือ slippage สูงกว่าปกติ ให้รอประเมินใหม่"), "",
        indent_paragraph("ขนาดความเสี่ยงต้องคำนวณจากระยะ Entry ถึงจุดยกเลิกหลังแผนเปลี่ยนเป็น ACTIVE เท่านั้น"), "",
    ]
    expiry_notice = friday_expiry_notice(cutoff)
    if expiry_notice:
        lines += ["**อายุแผนวันศุกร์**", "", indent_paragraph(expiry_notice), ""]
    lines += [
        "## ข่าวสำคัญและจุดพักแผน", "",
        "**ข่าวที่ควรติดตามวันนี้**", "",
        "| สถานะ | สกุลเงิน | เวลาไทย | ข่าว | ตัวเลข |",
        "| --- | --- | --- | --- | --- |", *news_rows, "",
        "**พักแผนเมื่อ**", "",
        "- H4/H1, M30 และ M15 ขัดกัน หรือไม่สามารถตรวจสอบแหล่งข้อมูลและเวลาแท่งปิดได้",
        "- ราคาวิ่งผ่านระดับก่อนแท่งปิดยืนยัน หรือจำเป็นต้องขยาย stop/target นอกหลักฐานที่คำนวณไว้",
        "- ใกล้รายการเศรษฐกิจ Medium/High ของสกุลเงินสองฝั่งจนความเสี่ยง gap/slippage เปลี่ยนจากสมมติฐานของแผน", "",
        internal_chart_links(asset), "",
        "> บทวิเคราะห์นี้จัดทำจากข้อมูลแท่งปิดเพื่อการศึกษา ไม่ใช่คำแนะนำเฉพาะบุคคลหรือคำรับรองผล", "",
        f"*หลักฐาน: {PRODUCER} · ตัดข้อมูลเมื่อ {cutoff_label} · input `{input_hash[:12]}…`*", "",
    ]
    return "\n".join(lines)


def token_set(text: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"[A-Za-z]{3,}|[ก-๙]{3,}", text)}


def overlap(article: str, asset: str) -> dict:
    source = token_set(article)
    candidates = list((P002 / "output").glob(f"**/{asset}.md"))
    rows = []
    for path in candidates:
        other = token_set(path.read_text(encoding="utf-8"))
        union = source | other
        score = len(source & other) / len(union) if union else 0.0
        rows.append({"path": str(path), "jaccard": round(score, 4)})
    rows.sort(key=lambda row: row["jaccard"], reverse=True)
    return {"max_jaccard": rows[0]["jaccard"] if rows else 0.0,
            "comparison_count": len(rows), "top": rows[:5]}


def parse_cutoff(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now(tz=timezone.utc).replace(microsecond=0)
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("cutoff_at ต้องระบุ timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def frontmatter_keys(article: str) -> list[str]:
    if not article.startswith("---\n"):
        return []
    try:
        block = article.split("---", 2)[1]
    except IndexError:
        return []
    return [line.split(":", 1)[0].strip() for line in block.splitlines()
            if ":" in line]


def has_closed_bar_confirmation(article: str) -> bool:
    """ยอมรับถ้อยคำของทั้ง WAIT และ ACTIVE แต่ต้องยืนยัน M30/M15 ด้วยแท่งปิด."""
    m30_confirmed = ("M30 ต้องผ่านครบ" in article
                     or "M30 ผ่านกฎฝั่ง" in article)
    m15_confirmed = ("M15 ต้องปิด" in article
                     or "M15 ปิด" in article)
    return m30_confirmed and m15_confirmed


def deprecated_copy_in(article: str) -> list[str]:
    """คืนข้อความเก่าที่ผู้ใช้สั่งถอดออกจาก Style L."""
    return [phrase for phrase in DEPRECATED_COPY if phrase in article]


def indent_paragraph(text: str) -> str:
    """เยื้องย่อหน้า Markdown ด้วย entity ที่ผู้ใช้กำหนด."""
    return text if text.startswith("&emsp;") else f"&emsp;{text}"


def chart_page_path(asset: str) -> str:
    """คืนหน้ากราฟที่ตรวจพบจริง; คู่ที่ยังไม่มีหน้าตรงให้ลง Asset Hub."""
    if asset not in ASSETS:
        raise ValueError(f"ไม่รองรับลิงก์หน้ากราฟของ {asset}")
    if asset in DIRECT_CHART_ASSETS:
        return f"/thailand/asset-{wcb_source.tag_for(asset)}"
    return ASSET_HUB_PATH


def internal_chart_links(asset: str) -> str:
    """สร้าง internal links แบบเดียวกับ XAUUSD โดยไม่ใส่โดเมนเต็ม."""
    profile = wcb_source.profile_for(asset)
    ticker = profile["symbol"].replace("/", "")
    chart_path = chart_page_path(asset)
    if chart_path == ASSET_HUB_PATH:
        chart_link = f"[หน้ารวมกราฟสินทรัพย์]({chart_path})"
    else:
        chart_link = f"[หน้าราคา {ticker}]({chart_path})"
    return indent_paragraph(
        f"ติดตามราคา {ticker} แบบเรียลไทม์ได้ที่ {chart_link} "
        f"และดูบทวิเคราะห์ย้อนหลังทั้งหมดได้ที่ "
        f"[คลังบทวิเคราะห์]({ANALYSIS_ARCHIVE_PATH})")


def friday_expiry_notice(cutoff: datetime) -> str | None:
    """คืนข้อความหมดอายุสำหรับบทวันศุกร์ตามเวลาไทย; วันอื่นไม่เพิ่มข้อความ."""
    if cutoff.astimezone(wcb_source.BANGKOK).weekday() != 4:
        return None
    return ("แผนนี้สิ้นสุดก่อนตลาดปิดช่วงสุดสัปดาห์ ไม่ถือสถานะหรือเงื่อนไขเดิม"
            "ข้ามไปวันจันทร์โดยอัตโนมัติ หากจะติดตามต่อ ต้องใช้ข้อมูลแท่งปิดและข่าว"
            "ชุดใหม่เพื่อประเมินแผนอีกครั้ง")


def validate_article(article: str, asset: str, plan: dict) -> list[str]:
    findings: list[str] = []
    expected = ["asset", "title", "slug", "excerpt", "author_slug", "timeframe", "trend",
                "status", "country", "language"]
    if frontmatter_keys(article) != expected:
        findings.append("frontmatter ต้องมี 10 ช่องตามลำดับที่อนุมัติ")
    if article.count("\n## ") != 3:
        findings.append("บทความต้องมีหัวข้อ H2 จำนวน 3 หัวข้อ")
    if len(re.findall(r"!\[[^]]+\]\([^)]+\.webp\)", article)) != 2:
        findings.append("บทความต้องอ้างภาพ WebP 2 ใบ")
    words = voice_rules.count_public_words(article)
    if not 600 <= words <= 1000:
        findings.append(f"ความยาว {words} คำ อยู่นอกช่วง 600–1000")
    if "| สถานะ | สกุลเงิน | เวลาไทย | ข่าว | ตัวเลข |" not in article:
        findings.append("ต้องรวมข่าวในตารางเดียว")
    if deprecated_copy_in(article):
        findings.append("พบข้อความเก่าที่ผู้ใช้สั่งถอดออกจาก Style L")
    if article.count("&emsp;") < 7:
        findings.append("ย่อหน้าเนื้อหาต้องขึ้นต้นด้วย &emsp;")
    expected_chart_path = chart_page_path(asset)
    if f"]({expected_chart_path})" not in article:
        findings.append("ขาดลิงก์หน้ากราฟภายในของสินทรัพย์")
    if f"]({ANALYSIS_ARCHIVE_PATH})" not in article:
        findings.append("ขาดลิงก์คลังบทวิเคราะห์ภายใน")
    if "http://" in article or "https://" in article:
        findings.append("ลิงก์ภายในต้องใช้ relative path และห้ามใส่โดเมนเต็ม")
    if not has_closed_bar_confirmation(article):
        findings.append("ขาดกฎยืนยัน M30/M15 แบบแท่งปิด")
    if plan.get("active"):
        if "- Entry trigger:" not in article or "- Target 1 / Target 2:" not in article:
            findings.append("ACTIVE ต้องมี Entry และ Target")
    elif "- Entry trigger:" in article or "- Target 1 / Target 2:" in article:
        findings.append("WAIT ห้ามสร้าง Entry หรือ Target")
    side = side_code(plan["direction"])
    opposite = "SELL" if side == "BUY" else "BUY"
    if f"**ฝั่งที่ให้น้ำหนัก: {side}**" not in article:
        findings.append("ขาดฝั่งหลักที่เลือก")
    if f"**ฝั่งที่ให้น้ำหนัก: {opposite}**" in article:
        findings.append("พบฝั่งตรงข้ามในช่องฝั่งหลัก")
    return findings


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_round(*, assets: list[str] | tuple[str, ...] = ASSETS,
              publish_root: Path = Path("../output"),
              cutoff_at: str | datetime | None = None,
              publish: bool = True) -> dict:
    """สร้าง Forex Daily Plan จาก snapshot เดียวและปล่อยแบบ all-or-nothing."""
    requested = list(dict.fromkeys(assets))
    unsupported = sorted(set(requested) - set(ASSETS))
    if unsupported:
        raise ValueError(f"Forex Daily Plan ไม่รองรับ: {', '.join(unsupported)}")
    cutoff = parse_cutoff(cutoff_at)
    run_id = f"fx-daily-plan-{cutoff.strftime('%Y%m%dT%H%M%SZ')}"
    work = REPO / "work" / "forex-daily-plan" / run_id
    input_dir = work / "input"
    evidence_dir = work / "evidence"
    staging_dir = work / "staging"
    for path in (input_dir, evidence_dir, staging_dir, STATE):
        path.mkdir(parents=True, exist_ok=True)
    summary = {"run_id": run_id, "style_id": STYLE_ID,
               "style_letter": STYLE_LETTER, "style_name": STYLE_NAME,
               "producer": PRODUCER,
               "cutoff_utc": cutoff.isoformat(), "publish": publish,
               "assets": {}, "errors": []}
    events, calendar_meta = fetch_events(cutoff)
    summary["calendar"] = calendar_meta
    write_json(evidence_dir / "calendar-meta.json", calendar_meta)
    if calendar_meta.get("status") != "ok":
        summary["errors"].append("calendar feed unavailable — fail closed")
        summary["ok"] = False
        write_json(evidence_dir / "run-summary.json", summary)
        return summary

    continuity_updates: dict[str, dict] = {}
    staged_files: list[Path] = []
    for asset in requested:
        try:
            rows: dict[str, list[dict]] = {}
            bases: dict[str, dict] = {}
            source_meta: dict[str, dict] = {}
            for timeframe in TIMEFRAMES:
                rows[timeframe], bases[timeframe], source_meta[timeframe] = closed_intraday(
                    asset, timeframe, cutoff)
            daily, daily_basis, daily_meta = closed_daily(asset, cutoff)
            h4 = h4_context(rows["4h"])
            h1 = h1_map(rows["1h"], daily)
            states = intraday_state(asset, rows, bases)
            preferred, preferred_reason = preferred_direction(h4)
            model, reason = choose_model(h4["bias"], states)
            plan = scenario(model, h4["bias"], preferred, h1, states)
            selected_events = relevant_events(asset, events, cutoff)
            continuity_state, continuity = continuity_snapshot(asset, cutoff, preferred, plan)
            continuity_updates[asset] = continuity_state
            input_payload = {"asset": asset, "cutoff_utc": cutoff.isoformat(),
                             "rows": {**rows, "1day": daily}}
            input_hash = sha(input_payload)
            write_json(input_dir / f"{asset}-closed-bars.json", input_payload)
            evidence_payload = {
                "asset": asset, "cutoff_utc": cutoff.isoformat(),
                "source_meta": source_meta, "daily_meta": daily_meta,
                "bases": bases, "daily_basis": daily_basis,
                "h4": {k: v for k, v in h4.items() if not k.endswith("_series")},
                "h1": h1, "states": states, "model": model,
                "model_reason": reason, "preferred_direction": preferred,
                "preferred_reason": preferred_reason, "scenario": plan,
                "events": selected_events, "continuity": continuity,
                "input_sha256": input_hash,
            }
            write_json(evidence_dir / f"{asset}-decision-trace.json", evidence_payload)
            folder = staging_dir / asset
            folder.mkdir(parents=True, exist_ok=True)
            h1_name = f"{asset}-forex-daily-h1-plan.webp"
            m15_name = f"{asset}-forex-daily-m15-trigger.webp"
            sizes = {
                h1_name: save_h1_chart(asset, rows["1h"], rows["4h"], h4, h1,
                                       plan, preferred, bases["1h"], folder / h1_name),
                m15_name: save_m15_chart(asset, rows["15min"], model, states, plan,
                                          preferred, bases["15min"], folder / m15_name),
            }
            article = render_article(asset, cutoff, h4, h1, states, model, reason,
                                     plan, preferred, preferred_reason, selected_events,
                                     input_hash, (h1_name, m15_name), bases, continuity)
            article_path = folder / f"{asset}.md"
            article_path.write_text(article, encoding="utf-8")
            findings = validate_article(article, asset, plan)
            for image_name in sizes:
                image_output.verify(folder / image_name)
            overlap_report = overlap(article, asset)
            write_json(evidence_dir / f"{asset}-overlap.json", overlap_report)
            if findings:
                summary["errors"].extend(f"{asset}: {item}" for item in findings)
            staged_files.extend([article_path, folder / h1_name, folder / m15_name])
            summary["assets"][asset] = {
                "status": "PASS_QA" if not findings else "BLOCK_QA",
                "model": model, "bias": h4["bias"],
                "preferred_direction": preferred,
                "readiness": "ACTIVE" if plan.get("active") else "WAIT",
                "words": voice_rules.count_public_words(article),
                "input_sha256": input_hash, "images": sizes,
                "max_overlap_jaccard": overlap_report["max_jaccard"],
            }
        except Exception as exc:  # noqa: BLE001 — asset ใดตกต้อง block ทั้งชุด
            summary["errors"].append(f"{asset}: {type(exc).__name__}: {exc}")
            summary["assets"][asset] = {"status": "BLOCK_ERROR"}

    if summary["errors"]:
        summary["ok"] = False
        write_json(evidence_dir / "run-summary.json", summary)
        return summary

    public_sources = web_import_sources(staged_files)
    destination = Path(publish_root) / publish_layout.day_folder(cutoff) / STYLE_FOLDER
    if publish and public_sources:
        destination.mkdir(parents=True, exist_ok=True)
        for source in public_sources:
            shutil.copy2(source, destination / source.name)
    if publish:
        for asset, state in continuity_updates.items():
            write_json(STATE / f"{asset}-continuity.json", state)
    for asset in requested:
        article_path = staging_dir / asset / f"{asset}.md"
        eligible = web_import_eligible(asset)
        summary["assets"][asset]["article"] = str(
            destination / article_path.name if publish and eligible else article_path)
        summary["assets"][asset]["web_import_status"] = (
            "READY_FOR_WEB_IMPORT" if publish and eligible else
            "DRY_RUN" if eligible else "HOLD_UNREGISTERED_ASSET")
        if not eligible:
            summary["assets"][asset]["web_import_hold_reason"] = WEB_IMPORT_HOLD_REASON
        summary["assets"][asset]["artifacts"] = {
            path.name: file_sha256(path) for path in staged_files
            if path.parent.name == asset
        }
    summary["destination"] = str(destination) if publish and public_sources else None
    summary["ok"] = True
    write_json(evidence_dir / "run-summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"ผลิต {STYLE_NAME}")
    parser.add_argument("--asset", action="append", choices=ASSETS)
    parser.add_argument("--publish-root", type=Path, default=Path("../output"))
    parser.add_argument("--cutoff-at")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = run_round(assets=args.asset or list(ASSETS),
                       publish_root=args.publish_root,
                       cutoff_at=args.cutoff_at, publish=not args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
