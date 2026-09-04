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

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def _find_project_root(path: Path) -> Path:
    """Resolve P002 correctly from both the checkout and nested worktrees."""
    for candidate in (path, *path.parents):
        if candidate.name.startswith("P002-"):
            return candidate
    return path.parent


P002 = _find_project_root(REPO)
ROOT = P002.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools import (  # noqa: E402
    calendar_feed,
    candle_close,
    chart_indicator,
    data_fetch_retry,
    forex_daily_calendar_renderer,
    headline_format,
    image_output,
    intraday_bars,
    intraday_breakout_story,
    intraday_indicators,
    intraday_pullback_story,
    intraday_story,
    intraday_trend_story,
    publish_layout,
    public_number_policy,
    trade_plan_public_contract,
    voice_rules,
    visual_theme,
    wcb_series_source,
    wcb_source,
    web_frontmatter_contract,
)
from tools.chart_story_renderer import _thai_font, checked_label  # noqa: E402

L_COLORS = visual_theme.for_premium_chart()


STYLE_ID = "l_forex_daily_plan"
STYLE_LETTER = "L"
STYLE_NAME = "Style L — Forex Daily Trade Plan"
ASSETS = ("eurusd", "gbpusd", "usdjpy", "audusd", "usdcad")
TIMEFRAMES = ("4h", "1h", "30min", "15min")
PRODUCER = f"P002 {STYLE_NAME} production"
STYLE_FOLDER = "L-Forex-Daily"
STYLE_NUMBER_POLICY = "style-l-forex-number-policy/v1"
PUBLIC_TRADE_PLAN_SCHEMA = "p002-public-trade-plan/v1"
STYLE_L_PLAN_SCHEMA = "style-l-trade-plan/v1"
CONTINUITY_SCHEMA = "style-l-continuity-snapshot/v2"
RR_POLICY_VERSION = "TPR-RR/v1"
RR_BASIS = "gross_pre_cost"
MINIMUM_RR = 1.0
PLAN_EXPIRY_HOURS = 24
MAX_ENTRY_DISTANCE_ATR = 2.0
STATE = REPO / "state" / "forex-daily-plan"
SCHEDULE_PATH = REPO / "config" / "forex_daily_schedule.json"
DECISION_POLICY_PATH = REPO / "config" / "forex_daily_decision_policy.json"
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
    "แผนที่ราคาและระยะของวัน",
    "พักแผนเมื่อ",
    "ติดตามราคา ",
    "คลังบทวิเคราะห์",
    "บทวิเคราะห์นี้จัดทำจากข้อมูลแท่งปิดเพื่อการศึกษา",
    "หลักฐาน: P002 Style L",
)

DIRECT_CHART_ASSETS = frozenset({"eurusd", "gbpusd", "usdjpy", "audusd", "usdcad"})
WEB_IMPORT_ASSETS = DIRECT_CHART_ASSETS
WEB_IMPORT_HOLD_REASON = "WCB asset registry has no usdcad tag"
ASSET_HUB_PATH = "/thailand/asset-hub"
ANALYSIS_ARCHIVE_PATH = "/thailand/analysis"

STYLE_IDS = (
    intraday_trend_story.STYLE_ID,
    intraday_breakout_story.STYLE_ID,
    intraday_pullback_story.STYLE_ID,
)


class DataHold(RuntimeError):
    """Closed-bar evidence cannot support a complete publishable plan."""


def web_import_eligible(asset: str) -> bool:
    """Return whether WCB currently has a registered article asset tag."""
    return asset in WEB_IMPORT_ASSETS


def web_import_sources(staged_files: list[Path]) -> list[Path]:
    """Return web payload only; diagnostic JSON stays in internal evidence."""
    return [path for path in staged_files
            if web_import_eligible(path.parent.name)
            and path.suffix.lower() in {".md", ".webp"}]


def clear_output_sidecars(folder: Path) -> int:
    """Remove legacy diagnostic sidecars from a public Style L lane."""
    removed = 0
    if folder.exists():
        for path in folder.glob("*.trade-plan-public.json"):
            path.unlink()
            removed += 1
    return removed


def clear_output_calendar_images(folder: Path, asset: str) -> int:
    """Remove only this asset's prior Style L calendar pages before promotion."""
    removed = 0
    if folder.exists():
        for path in folder.glob(f"{asset}-forex-daily-calendar-*.webp"):
            path.unlink()
            removed += 1
    return removed


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
    def fetch_closed() -> tuple[list[dict], dict, dict]:
        meta, rows, source = intraday_bars.fetch_rows(
            asset, timeframe=timeframe, outputsize=500, now=cutoff)
        closed, basis = intraday_bars.evaluate(
            rows, asset=asset, timeframe=timeframe, now=cutoff)
        return closed, basis, {**meta, "source": source, "closed_count": len(closed),
                               "last_closed_at": closed[-1]["at"]}

    return data_fetch_retry.run_with_one_retry(
        fetch_closed, asset=asset, timeframe=timeframe)


def closed_daily(asset: str, cutoff: datetime) -> tuple[list[dict], dict, dict]:
    def fetch_closed() -> tuple[list[dict], dict, dict]:
        meta, rows, source = wcb_series_source.fetch_asset_rows(
            asset, count=120, interval="1day", now=cutoff, max_age_days=3)
        closed, basis = candle_close.evaluate(rows, asset=asset, now=cutoff)
        return closed, basis, {**meta, "source": source, "closed_count": len(closed),
                               "last_closed_date": closed[-1]["date"]}

    return data_fetch_retry.run_with_one_retry(
        fetch_closed, asset=asset, timeframe="D1")


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


def load_decision_policy(path: Path = DECISION_POLICY_PATH) -> dict:
    """Load the fail-closed, versioned Style L H4/M30 decision contract."""
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(f"Forex decision policy ใช้งานไม่ได้: {exc}") from exc
    expected_keys = {"schema_version", "policy_version", "h4_bias", "m30_readiness"}
    if not isinstance(policy, dict) or set(policy) != expected_keys:
        raise RuntimeError("Forex decision policy มี key ไม่ครบหรือเกิน schema v1")
    if isinstance(policy["schema_version"], bool) or policy["schema_version"] != 1:
        raise RuntimeError("Forex decision policy ต้องใช้ schema_version 1")
    if policy["policy_version"] != "style-l-decision-policy/v2":
        raise RuntimeError("Forex decision policy version ไม่ตรง contract L2")
    h4_policy = policy.get("h4_bias")
    if not isinstance(h4_policy, dict) or set(h4_policy) != {
            "neutral_on_conflict", "neutral_label"}:
        raise RuntimeError("Forex decision policy H4 มี key ไม่ครบหรือเกิน schema v2")
    if h4_policy != {"neutral_on_conflict": True, "neutral_label": "NEUTRAL"}:
        raise RuntimeError("Forex decision policy H4 ต้อง fail conflict เป็น NEUTRAL")
    m30_policy = policy.get("m30_readiness")
    if not isinstance(m30_policy, dict) or set(m30_policy) != {
            "core", "adx_threshold", "supporting"}:
        raise RuntimeError("Forex decision policy M30 มี key ไม่ครบหรือเกิน schema v2")
    if (m30_policy.get("core") != ["dmi_direction", "adx_threshold"]
            or m30_policy.get("supporting") != ["supertrend"]):
        raise RuntimeError("Forex decision policy M30 core/supporting ไม่ตรง contract L2")
    threshold = m30_policy.get("adx_threshold")
    if type(threshold) is not int or threshold != 20:
        raise RuntimeError("Forex decision policy v2 กำหนด ADX threshold เป็น integer 20 เท่านั้น")
    return policy


def choose_model(bias: str | None, states: dict,
                 decision_policy: dict | None = None) -> tuple[str, str]:
    if bias is None:
        return "NO_SETUP", "H4 เป็น NEUTRAL เพราะ EMA และโครงสร้างยังไม่ยืนยันทิศเดียวกัน"
    h = states.get("H") or {}
    if not m30_gate_pass(h, bias, decision_policy):
        return "WAIT", "M30 ยังไม่ยืนยันทิศ H4 ด้วย DMI direction และ ADX"
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


def preferred_direction(h4: dict) -> tuple[str | None, str]:
    """Return only a confirmed H4 side; conflict stays explicitly neutral."""
    if h4.get("bias") in {"up", "down"}:
        direction = str(h4["bias"])
        return direction, "EMA และโครงสร้าง H4 ยืนยันไปทางเดียวกัน"
    return None, "EMA และโครงสร้าง H4 ขัดกันหรือยังไม่ชัด จึงคงสถานะ NEUTRAL"


def _round_price(asset: str, value: float) -> float:
    return round(float(value), int(wcb_source.profile_for(asset)["decimals"]))


def _plan_leg(asset: str, side: str, trigger: float, atr: float,
              invalidation: float, source: str) -> dict:
    """Build one deterministic leg from a closed-bar level and H1 ATR."""
    sign = 1 if side == "BUY" else -1
    entry = _round_price(asset, trigger)
    stop = _round_price(asset, entry - sign * atr)
    target1 = _round_price(asset, entry + sign * atr)
    target2 = _round_price(asset, entry + sign * atr * 2)
    risk = abs(entry - stop)
    if risk <= 0:
        raise DataHold(f"{side} risk ต้องมากกว่า 0")
    rr1 = abs(target1 - entry) / risk
    rr2 = abs(target2 - entry) / risk
    return {
        "side": side,
        "trigger": {
            "condition": "M15_CLOSE_ABOVE" if side == "BUY" else "M15_CLOSE_BELOW",
            "value": entry,
        },
        "entry_zone": {"low": entry, "high": entry},
        "stop_loss": stop,
        "take_profit": [target1, target2],
        "risk_reward": [round(rr1, 4), round(rr2, 4)],
        "rr_basis": RR_BASIS,
        "invalidation": {
            "condition": "H1_CLOSE_BELOW" if side == "BUY" else "H1_CLOSE_ABOVE",
            "value": _round_price(asset, invalidation),
        },
        "evidence_source": source,
    }


def scenario(model: str, bias: str | None, preferred: str | None,
             h1: dict, states: dict, *, asset: str = "gbpusd",
             cutoff: datetime | None = None, evidence_hash: str = "",
             current_close: float | None = None) -> dict:
    """Build a complete public plan; WAIT describes readiness, never plan absence."""
    i = states.get("I") or {}
    channel = i.get("donchian") or {}
    try:
        watch_low = float(channel.get("lower", h1["pdl"]))
        watch_high = float(channel.get("upper", h1["pdh"]))
        atr = float(h1["atr14"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DataHold(f"Style L level/ATR ใช้งานไม่ได้: {exc}") from exc
    if (not all(math.isfinite(value) and value > 0
                for value in (watch_low, watch_high, atr))
            or watch_high <= watch_low):
        raise DataHold("Style L level/ATR ไม่ผ่าน data domain")
    has_channel = "lower" in channel and "upper" in channel
    if cutoff is None:
        cutoff = datetime.now(timezone.utc)
    valid_until = (cutoff.astimezone(wcb_source.BANGKOK)
                   + timedelta(hours=PLAN_EXPIRY_HOURS)).isoformat()
    market_close = _round_price(
        asset, h1["close"] if current_close is None else current_close)
    adr14 = float(h1.get("adr14", 0) or 0)

    def reachable(value: float) -> bool:
        """แผนรายวันต้องไม่ไกลเกิน 2×ATR หรือ 1×ADR จากราคาปิดจริง"""
        distance = abs(float(value) - market_close)
        # ชุดทดสอบ/legacy ที่ไม่มี ADR ไม่ควรถูกตีความเป็นข้อมูลผิดพลาด;
        # สายผลิตจริงดึง ADR14 เสมอและจึงใช้ gate นี้เต็มรูปแบบ
        return adr14 <= 0 or distance <= max(MAX_ENTRY_DISTANCE_ATR * atr, adr14)

    upper_candidates = [
        (watch_high, "M15 Donchian upper" if has_channel else "H1 PDH"),
        (float(h1["pdh"]), "H1 PDH"),
    ]
    lower_candidates = [
        (watch_low, "M15 Donchian lower" if has_channel else "H1 PDL"),
        (float(h1["pdl"]), "H1 PDL"),
    ]
    if h1.get("current_high") is not None:
        upper_candidates.append((float(h1["current_high"]), "current H1 closed-bar high"))
    if h1.get("current_low") is not None:
        lower_candidates.append((float(h1["current_low"]), "current H1 closed-bar low"))

    def next_upper() -> tuple[float, str]:
        candidates = [item for item in upper_candidates
                      if item[0] > market_close and reachable(item[0])]
        if not candidates:
            raise DataHold("ไม่มีแนวต้านจากแท่งปิดที่อยู่เหนือ current close")
        return min(candidates, key=lambda item: item[0])

    def next_lower() -> tuple[float, str]:
        candidates = [item for item in lower_candidates
                      if item[0] < market_close and reachable(item[0])]
        if not candidates:
            raise DataHold("ไม่มีแนวรับจากแท่งปิดที่อยู่ใต้ current close")
        return max(candidates, key=lambda item: item[0])

    if preferred is None:
        buy_trigger, buy_source = next_upper()
        sell_trigger, sell_source = next_lower()
        legs = [
            _plan_leg(asset, "BUY", buy_trigger, atr, h1["pdl"], buy_source),
            _plan_leg(asset, "SELL", sell_trigger, atr, h1["pdh"], sell_source),
        ]
        public_side = "OCO"
    else:
        if model == "J" and states.get("J"):
            zone = states["J"]["pullback_zone"]
            trigger = (float(zone["low"]) + float(zone["high"])) / 2
            source = "M15 pullback zone midpoint"
            if not reachable(trigger):
                trigger, source = next_upper() if preferred == "up" else next_lower()
        else:
            trigger = watch_high if preferred == "up" else watch_low
            source = (("M15 Donchian upper" if has_channel else "H1 PDH")
                      if preferred == "up" else
                      ("M15 Donchian lower" if has_channel else "H1 PDL"))
            if model not in {"I", "J"}:
                trigger, source = next_upper() if preferred == "up" else next_lower()
            elif not reachable(trigger):
                trigger, source = next_upper() if preferred == "up" else next_lower()
        side = "BUY" if preferred == "up" else "SELL"
        legs = [_plan_leg(
            asset, side, trigger, atr,
            h1["pdl"] if preferred == "up" else h1["pdh"], source)]
        public_side = side

    active = False
    if len(legs) == 1:
        leg = legs[0]
        trigger_value = leg["trigger"]["value"]
        crossed = (market_close > trigger_value if leg["side"] == "BUY"
                   else market_close < trigger_value)
        active = crossed and model in {"I", "J"}

    plan = {
        "schema": STYLE_L_PLAN_SCHEMA,
        "status": "ACTIVE" if active else "WAIT_TRIGGER",
        "side": public_side,
        "current_close": market_close,
        "cutoff_at": cutoff.astimezone(wcb_source.BANGKOK).isoformat(),
        "rr_policy_version": RR_POLICY_VERSION,
        "valid_until": valid_until,
        "evidence_hash": evidence_hash,
        "plans": legs,
        "internal_readiness": model,
        "active": active,
        "direction": preferred,
        "watch_low": watch_low,
        "watch_high": watch_high,
        "reachability": {
            "max_distance_atr": MAX_ENTRY_DISTANCE_ATR,
            "adr14": adr14,
            "legs": [
                {"side": leg["side"],
                 "distance_atr": round(abs(leg["trigger"]["value"] - market_close) / atr, 4),
                 "distance_adr": (round(abs(leg["trigger"]["value"] - market_close) / adr14, 4)
                                  if adr14 > 0 else None),
                 "reachable": reachable(leg["trigger"]["value"])}
                for leg in legs
            ],
        },
    }
    # Compatibility projection for the existing chart/continuity code. Public
    # claims are always rendered from plans[], not these aliases.
    if len(legs) == 1:
        leg = legs[0]
        plan.update({
            "entry": leg["trigger"]["value"], "stop": leg["stop_loss"],
            "target1": leg["take_profit"][0], "target2": leg["take_profit"][1],
            "invalidation_h1": leg["invalidation"]["value"],
        })
    return plan


def public_trade_plan_sidecar(asset: str, article_name: str, article: str,
                              plan: dict) -> dict:
    """Project the Style L plan into the selector/release public contract."""
    legs = []
    for source in plan["plans"]:
        legs.append({key: copy.deepcopy(source[key]) for key in (
            "side", "trigger", "entry_zone", "stop_loss", "take_profit",
            "risk_reward", "rr_basis", "invalidation")})
    return {
        "schema": PUBLIC_TRADE_PLAN_SCHEMA,
        "style_id": STYLE_ID,
        "asset": asset,
        "article": article_name,
        "article_sha256": hashlib.sha256(article.encode("utf-8")).hexdigest(),
        "qa_status": "PASS_QA",
        "publishable": True,
        "plan_status": plan["status"],
        "side": plan["side"],
        "current_close": plan["current_close"],
        "cutoff_at": plan["cutoff_at"],
        "rr_policy_version": plan["rr_policy_version"],
        "valid_until": plan["valid_until"],
        "evidence_hash": plan["evidence_hash"],
        "plans": legs,
    }


def validate_public_trade_plan_sidecar(sidecar: dict, article: str) -> list[str]:
    """Fail closed on the exact selector-facing Style L sidecar contract."""
    findings: list[str] = []
    expected = {
        "schema", "style_id", "asset", "article", "article_sha256", "qa_status",
        "publishable", "plan_status", "side", "current_close", "rr_policy_version",
        "cutoff_at", "valid_until", "evidence_hash", "plans",
    }
    if not isinstance(sidecar, dict) or set(sidecar) != expected:
        return ["public trade-plan sidecar key ไม่ครบหรือเกิน"]
    if sidecar["schema"] != PUBLIC_TRADE_PLAN_SCHEMA or sidecar["style_id"] != STYLE_ID:
        findings.append("public trade-plan schema/style ไม่ถูกต้อง")
    if sidecar["qa_status"] != "PASS_QA" or sidecar["publishable"] is not True:
        findings.append("public trade-plan ต้อง PASS_QA และ publishable=true")
    if sidecar["plan_status"] not in {"WAIT_TRIGGER", "ACTIVE"}:
        findings.append("public plan_status ไม่ถูกต้อง")
    if sidecar["side"] not in {"BUY", "SELL", "OCO"}:
        findings.append("public side ไม่ถูกต้อง")
    if sidecar["rr_policy_version"] != RR_POLICY_VERSION:
        findings.append("RR policy version ไม่ถูกต้อง")
    if sidecar["article_sha256"] != hashlib.sha256(article.encode("utf-8")).hexdigest():
        findings.append("article_sha256 ไม่ตรง final Markdown")
    if not re.fullmatch(r"[0-9a-f]{64}", str(sidecar["evidence_hash"])):
        findings.append("evidence_hash ไม่ใช่ SHA-256")
    try:
        if datetime.fromisoformat(str(sidecar["valid_until"])).tzinfo is None:
            raise ValueError
    except (TypeError, ValueError):
        findings.append("valid_until ไม่มี timezone")
    legs = sidecar["plans"]
    expected_count = 2 if sidecar["side"] == "OCO" else 1
    if not isinstance(legs, list) or len(legs) != expected_count:
        findings.append("จำนวน public plan legs ไม่ตรง side")
        return findings
    leg_keys = {"side", "trigger", "entry_zone", "stop_loss", "take_profit",
                "risk_reward", "rr_basis", "invalidation"}
    if any(not isinstance(leg, dict) or set(leg) != leg_keys for leg in legs):
        findings.append("public plan leg key ไม่ครบหรือเกิน")
    if any(leg.get("rr_basis") != RR_BASIS for leg in legs):
        findings.append("Style L RR basis ต้องเป็น gross_pre_cost")
    if sidecar["side"] == "OCO" and {leg.get("side") for leg in legs} != {"BUY", "SELL"}:
        findings.append("public OCO ต้องมี BUY/SELL ครบ")
    central = trade_plan_public_contract.validate(
        sidecar, article_name=str(sidecar.get("article")),
        article_bytes=article.encode("utf-8"), style_id=STYLE_ID,
        asset=str(sidecar.get("asset")))
    findings.extend(
        f"central contract {item['code']}: {item['message']}"
        for item in central["findings"])
    return findings


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


def daily_relevant_events(asset: str, events: list[dict], cutoff: datetime) -> list[dict]:
    """Select all Medium/High events for both currencies on the article day."""
    countries = {
        "eurusd": {"EUR", "USD"}, "gbpusd": {"GBP", "USD"},
        "usdjpy": {"USD", "JPY"}, "audusd": {"AUD", "USD"},
        "usdcad": {"CAD", "USD"},
    }[asset]
    article_day = cutoff.astimezone(wcb_source.BANGKOK).date()
    selected = []
    for event in events:
        when = event_datetime(event)
        if (when is None or when.date() != article_day
                or str(event.get("country") or "").upper() not in countries
                or str(event.get("impact") or "").title() not in {"High", "Medium"}):
            continue
        selected.append(event)
    return sorted(selected, key=lambda event: (
        event_datetime(event), str(event.get("country") or ""),
        str(event.get("title") or event.get("title_th") or event.get("title_en") or "")))


def fmt(asset: str, value: float) -> str:
    return f"{value:,.{wcb_source.profile_for(asset)['decimals']}f}"


def image_price(asset: str, value: float) -> str:
    """Format a Style L chart label without mutating canonical precision."""
    del asset  # Asset-specific precision belongs to canonical/public text only.
    return f"{float(value):.3f}"


def _chart_price(asset: str, value: float) -> str:
    """Return the display policy for the Style L visual remediation targets."""
    return image_price(asset, value) if asset in {"gbpusd", "usdcad"} else fmt(asset, value)


def _chart_label_x_offset(role: str) -> float:
    """Stagger dense target labels horizontally while retaining factual y."""
    if role.startswith("h1-"):
        return 0.0
    if role.startswith("donchian-"):
        return 0.0
    if role.endswith("trigger") or role == "entry-trigger":
        return -120.0
    if role.endswith("tp1") or role == "target-1":
        return -156.0
    if role.endswith("tp2") or role == "target-2":
        return -234.0
    if role == "stop-loss" or role.endswith("sl"):
        return -120.0
    return 0.0


def _protect_style_price_tokens(markdown: str, asset: str) -> tuple[str, dict[str, str]]:
    """Hide Style L price tokens while the shared whole-number policy runs.

    Style L renders prices and volatility distances with the asset profile's
    precision. Other technical decimals (ADX, DMI, percentages, and similar
    measurements) keep using the shared public policy.
    """
    decimals = int(wcb_source.profile_for(asset)["decimals"])
    price_token = re.compile(
        rf"(?<![\w.])\d[\d,]*\.\d{{{decimals}}}(?![\w.])")
    protected: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        placeholder = f"STYLELPRICETOKEN{len(protected)}END"
        protected[placeholder] = match.group(0)
        return placeholder

    return price_token.sub(replace, markdown), protected


def publicize_style_l(article: str, asset: str) -> str:
    """Apply the shared policy without destroying Style L Forex precision."""
    protected_article, protected = _protect_style_price_tokens(article, asset)
    final_article = public_number_policy.publicize(protected_article)
    for placeholder, token in protected.items():
        final_article = final_article.replace(placeholder, token)
    return final_article


def validate_style_l_number_policy(article: str, asset: str) -> list[str]:
    """Reject technical decimals other than asset-profile price tokens."""
    protected_article, _ = _protect_style_price_tokens(article, asset)
    return public_number_policy.validate(protected_article)


def validate_data_domain(asset: str, h4: dict, h1: dict, plan: dict) -> list[str]:
    """Validate critical Style L numbers before any artifact can be promoted."""
    findings: list[str] = []

    def positive(name: str, value: object) -> float | None:
        if isinstance(value, bool):
            findings.append(f"{name} ต้องเป็นเลข finite ที่มากกว่า 0")
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            findings.append(f"{name} ต้องเป็นเลข finite ที่มากกว่า 0")
            return None
        if not math.isfinite(number) or number <= 0:
            findings.append(f"{name} ต้องเป็นเลข finite ที่มากกว่า 0")
            return None
        return number

    values = {
        "H4 close": h4.get("close"),
        "H4 EMA20": h4.get("ema20"),
        "H4 EMA50": h4.get("ema50"),
        "H1 close": h1.get("close"),
        "PDH": h1.get("pdh"),
        "PDL": h1.get("pdl"),
        "H1 current high": h1.get("current_high"),
        "H1 current low": h1.get("current_low"),
        "H1 current range": h1.get("current_range"),
        "H1 ATR14": h1.get("atr14"),
        "D1 ADR14": h1.get("adr14"),
    }
    checked = {name: positive(name, value) for name, value in values.items()}

    try:
        adr_used = float(h1.get("adr_used_pct"))
    except (TypeError, ValueError):
        adr_used = math.nan
    if not math.isfinite(adr_used) or not 0 <= adr_used <= 1000:
        findings.append("ADR used percent ต้องเป็นเลข finite ในช่วง 0–1000")

    pdh, pdl = checked["PDH"], checked["PDL"]
    if pdh is not None and pdl is not None and pdh <= pdl:
        findings.append("PDH ต้องมากกว่า PDL")
    current_high = checked["H1 current high"]
    current_low = checked["H1 current low"]
    if (current_high is not None and current_low is not None
            and current_high < current_low):
        findings.append("H1 current high ต้องไม่น้อยกว่า current low")
    current_range = checked["H1 current range"]
    adr14 = checked["D1 ADR14"]
    if (current_high is not None and current_low is not None
            and current_range is not None
            and not math.isclose(current_range, current_high - current_low,
                                 rel_tol=1e-9, abs_tol=1e-12)):
        findings.append("H1 current range ไม่ตรงกับ current high ลบ current low")
    if current_range is not None and adr14 is not None and math.isfinite(adr_used):
        expected_adr_used = current_range / adr14 * 100
        if not math.isclose(adr_used, expected_adr_used,
                            rel_tol=1e-9, abs_tol=1e-6):
            findings.append("ADR used percent ไม่ตรงกับ current range หาร ADR14")

    public_legs = plan.get("plans")
    if public_legs is not None:
        if (plan.get("schema") != STYLE_L_PLAN_SCHEMA
                or plan.get("side") not in {"BUY", "SELL", "OCO"}
                or plan.get("status") not in {"WAIT_TRIGGER", "ACTIVE"}):
            findings.append("public trade plan schema/side/status ไม่ถูกต้อง")
        if plan.get("rr_policy_version") != RR_POLICY_VERSION:
            findings.append("RR policy version ไม่ถูกต้อง")
        current_close = positive("public plan current close", plan.get("current_close"))
        if not isinstance(plan.get("evidence_hash"), str) or not re.fullmatch(
                r"[0-9a-f]{64}", plan.get("evidence_hash", "")):
            findings.append("evidence hash ต้องเป็น SHA-256 64 ตัว")
        try:
            expires = datetime.fromisoformat(str(plan.get("valid_until")))
            if expires.tzinfo is None:
                raise ValueError
        except (TypeError, ValueError):
            findings.append("valid_until ต้องเป็น ISO datetime ที่มี timezone")
        expected_count = 2 if plan.get("side") == "OCO" else 1
        if not isinstance(public_legs, list) or len(public_legs) != expected_count:
            findings.append("จำนวน plan legs ไม่ตรงกับ side")
            public_legs = []
        elif plan.get("side") == "OCO" and {
                leg.get("side") for leg in public_legs if isinstance(leg, dict)
        } != {"BUY", "SELL"}:
            findings.append("OCO ต้องมี BUY และ SELL อย่างละหนึ่ง leg")

    if plan.get("active") and public_legs is None:
        scenario_names = ("entry", "stop", "target1", "target2", "invalidation_h1")
    else:
        scenario_names = ("watch_low", "watch_high")
    scenario_values = {
        name: positive(f"scenario {name}", plan.get(name)) for name in scenario_names
    }
    if not plan.get("active"):
        watch_low = scenario_values["watch_low"]
        watch_high = scenario_values["watch_high"]
        if watch_low is not None and watch_high is not None and watch_high <= watch_low:
            findings.append("scenario watch_high ต้องมากกว่า watch_low")

    observed = [checked[name] for name in (
        "H1 close", "PDH", "PDL", "H1 current high", "H1 current low")]
    if all(value is not None for value in observed) and adr14 is not None:
        observed_low = min(value for value in observed if value is not None)
        observed_high = max(value for value in observed if value is not None)
        # Ten ADRs is deliberately a broad integrity envelope, not a trade rule.
        # It rejects placeholder/cross-asset levels such as GBPUSD 9–10 without
        # constraining a legitimate plan near the observed market.
        reasonable_low = max(0.0, observed_low - 10 * adr14)
        reasonable_high = observed_high + 10 * adr14
        for name, value in scenario_values.items():
            if value is not None and not reasonable_low <= value <= reasonable_high:
                findings.append(
                    f"scenario {name} อยู่นอก reasonable domain ของราคา H1/PDH/PDL")

    if (plan.get("active") and public_legs is None
            and all(value is not None for value in scenario_values.values())):
        entry = scenario_values["entry"]
        stop = scenario_values["stop"]
        target1 = scenario_values["target1"]
        target2 = scenario_values["target2"]
        ordered = (stop < entry < target1 < target2 if plan.get("direction") == "up"
                   else target2 < target1 < entry < stop)
        if not ordered:
            findings.append("scenario Entry/Stop/Target1/Target2 เรียงลำดับไม่ถูกต้อง")

    for index, leg in enumerate(public_legs or []):
        if not isinstance(leg, dict):
            findings.append(f"plan leg {index} ต้องเป็น object")
            continue
        side = leg.get("side")
        if leg.get("rr_basis") != RR_BASIS:
            findings.append(f"plan leg {index} RR basis ต้องเป็น gross_pre_cost")
        trigger = positive(f"plan leg {index} trigger", (leg.get("trigger") or {}).get("value"))
        entry = leg.get("entry_zone") or {}
        entry_low = positive(f"plan leg {index} entry low", entry.get("low"))
        entry_high = positive(f"plan leg {index} entry high", entry.get("high"))
        stop = positive(f"plan leg {index} stop loss", leg.get("stop_loss"))
        targets = leg.get("take_profit")
        rrs = leg.get("risk_reward")
        invalidation = positive(
            f"plan leg {index} invalidation", (leg.get("invalidation") or {}).get("value"))
        if (not isinstance(targets, list) or not targets
                or not isinstance(rrs, list) or len(rrs) != len(targets)):
            findings.append(f"plan leg {index} TP/RR ต้องเป็น list ที่มีจำนวนตรงกัน")
            continue
        checked_targets = [positive(f"plan leg {index} TP{n + 1}", value)
                           for n, value in enumerate(targets)]
        checked_rrs = [positive(f"plan leg {index} RR{n + 1}", value)
                       for n, value in enumerate(rrs)]
        numeric = [trigger, entry_low, entry_high, stop, invalidation,
                   *checked_targets, *checked_rrs]
        if any(value is None for value in numeric):
            continue
        if entry_low > entry_high or not entry_low <= trigger <= entry_high:
            findings.append(f"plan leg {index} trigger ต้องอยู่ใน entry zone")
            continue
        if current_close is not None:
            crossed = (current_close > trigger if side == "BUY" else current_close < trigger)
            if plan.get("status") == "WAIT_TRIGGER" and crossed:
                findings.append(f"plan leg {index} WAIT_TRIGGER แต่ current close ข้าม trigger แล้ว")
            if plan.get("status") == "ACTIVE" and not crossed:
                findings.append(f"plan leg {index} ACTIVE แต่ current close ยังไม่ข้าม trigger")
        worst_entry = entry_high if side == "BUY" else entry_low
        risk = abs(worst_entry - stop)
        if side == "BUY":
            ordered = stop < entry_low <= entry_high < checked_targets[0]
            rewards = [target - worst_entry for target in checked_targets]
        elif side == "SELL":
            ordered = checked_targets[0] < entry_low <= entry_high < stop
            rewards = [worst_entry - target for target in checked_targets]
        else:
            ordered, rewards = False, []
        if not ordered or risk <= 0:
            findings.append(f"plan leg {index} geometry ไม่ถูกต้อง")
            continue
        for rr_index, (reward, claimed) in enumerate(zip(rewards, checked_rrs), 1):
            actual = reward / risk
            if claimed < MINIMUM_RR or not math.isclose(
                    actual, claimed, rel_tol=1e-4, abs_tol=1e-4):
                findings.append(
                    f"plan leg {index} RR{rr_index} ไม่ผ่านหรือไม่ตรง geometry")

        if all(value is not None for value in observed) and adr14 is not None:
            leg_values = [trigger, entry_low, entry_high, stop, invalidation,
                          *checked_targets]
            for value in leg_values:
                if not reasonable_low <= value <= reasonable_high:
                    findings.append(
                        f"plan leg {index} อยู่นอก reasonable domain ของราคา H1/PDH/PDL")
                    break

    return [f"{asset}: {finding}" for finding in findings]


def validate_markdown_snapshot_parity(article: str, asset: str, h4: dict,
                                      h1: dict, plan: dict,
                                      preferred: str | None) -> list[str]:
    """Compare final Markdown fields with the canonical in-memory snapshot."""
    missing = [key for key in ("side", "valid_until", "evidence_hash", "plans")
               if key not in plan]
    if missing:
        return [f"{asset}: public trade plan ขาด canonical field: {', '.join(missing)}"]
    expected: dict[str, tuple[str, int]] = {
        "H4 close/EMA": ((
            f"โดยปิดที่ {fmt(asset, h4['close'])} เทียบกับ EMA20 "
            f"{fmt(asset, h4['ema20'])} และ EMA50 {fmt(asset, h4['ema50'])}"), 1),
        "H1 close": (f"ราคาปิด H1 ล่าสุดอยู่ที่ {fmt(asset, h1['close'])}", 1),
        "public side": (f"| แผนสาธารณะ | **{plan['side']}** |", 1),
        "cutoff at": (f"- Cutoff at: `{plan['cutoff_at']}`", 1),
        "valid until": (f"- Valid until: `{plan['valid_until']}`", 1),
        "evidence hash": (f"- Evidence hash: `{plan['evidence_hash']}`", 1),
        "cancel rule": (f"- {public_plan_cancel_rule(asset, plan)}", 1),
    }

    for leg in plan.get("plans", []):
        side = leg["side"]
        condition = "M15 ปิดเหนือ" if side == "BUY" else "M15 ปิดต่ำกว่า"
        invalidation = "H1 ปิดต่ำกว่า" if side == "BUY" else "H1 ปิดเหนือ"
        targets = " / ".join(f"`{fmt(asset, value)}`" for value in leg["take_profit"])
        rrs = " / ".join(public_number_policy.publicize(f"{value:.2f}R")
                         for value in leg["risk_reward"])
        row = (
            f"| {side} | {condition} `{fmt(asset, leg['trigger']['value'])}` | "
            f"`{fmt(asset, leg['entry_zone']['low'])}`–"
            f"`{fmt(asset, leg['entry_zone']['high'])}` | "
            f"`{fmt(asset, leg['stop_loss'])}` | {targets} | {rrs} | "
            f"{invalidation} `{fmt(asset, leg['invalidation']['value'])}` |")
        expected[f"{side} complete plan row"] = (row, 1)

    findings = [
        f"{asset}: Markdown ไม่ตรง snapshot ที่ช่อง {name} "
        f"(พบ {article.count(marker)} ครั้ง; ต้องมี {count})"
        for name, (marker, count) in expected.items()
        if article.count(marker) != count
    ]

    return findings


def bias_th(bias: str | None) -> str:
    return {"up": "เอนขึ้น", "down": "เอนลง"}.get(bias, "ยังเป็นกลาง")


def side_code(direction: str | None) -> str:
    return {"up": "BUY", "down": "SELL"}.get(direction, "NEUTRAL")


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


def m30_readiness(h: dict, direction: str | None,
                  decision_policy: dict | None = None) -> dict:
    policy = decision_policy or load_decision_policy()
    threshold = float(policy["m30_readiness"]["adx_threshold"])
    dmi = h.get("dmi") or {}
    plus_di = float(dmi.get("plus_di", 0))
    minus_di = float(dmi.get("minus_di", 0))
    dmi_direction = "up" if plus_di > minus_di else "down" if minus_di > plus_di else None
    adx = float(dmi.get("adx", 0))
    supertrend_direction = str((h.get("supertrend") or {}).get("direction", "")) or None
    return {
        "core_ready": direction in {"up", "down"}
                      and dmi_direction == direction and adx >= threshold,
        "dmi_direction": dmi_direction,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "adx": adx,
        "adx_threshold": threshold,
        "supertrend_direction": supertrend_direction,
        "supertrend_aligned": (direction in {"up", "down"}
                               and supertrend_direction == direction),
        "policy_version": policy["policy_version"],
    }


def m30_read(h: dict, direction: str,
             decision_policy: dict | None = None) -> str:
    readiness = m30_readiness(h, direction, decision_policy)
    adx = readiness["adx"]
    plus_di = readiness["plus_di"]
    minus_di = readiness["minus_di"]
    threshold = readiness["adx_threshold"]
    side = side_code(direction)
    supertrend_context = (
        "Supertrend สนับสนุนทิศเดียวกัน"
        if readiness["supertrend_aligned"]
        else "Supertrend ยังไม่สนับสนุนทิศเดียวกัน แต่ไม่ใช่เงื่อนไข gate")
    if readiness["core_ready"]:
        return (f"M30 ผ่านกฎฝั่ง {side}: DMI ชี้ทางเดียวกัน "
                f"(+DI {plus_di:.1f} / -DI {minus_di:.1f}) และ ADX {adx:.1f} "
                f"สูงกว่าเกณฑ์ {threshold:.0f}; {supertrend_context}")
    missing = []
    if readiness["dmi_direction"] != direction:
        missing.append("DMI ยังไม่ชี้ฝั่งเดียวกัน")
    if adx < threshold:
        missing.append(f"ADX {adx:.1f} ยังต่ำกว่า {threshold:.0f}")
    return (f"M30 ยังไม่ผ่านกฎฝั่ง {side}: " + "; ".join(missing)
            + f"; {supertrend_context}")


def m30_gate_pass(h: dict, direction: str | None,
                  decision_policy: dict | None = None) -> bool:
    return bool(m30_readiness(h, direction, decision_policy)["core_ready"])


def m30_rule(direction: str, decision_policy: dict | None = None) -> str:
    policy = decision_policy or load_decision_policy()
    threshold = float(policy["m30_readiness"]["adx_threshold"])
    dmi_rule = "+DI มากกว่า -DI" if direction == "up" else "-DI มากกว่า +DI"
    return (f"{dmi_rule} และ ADX อย่างน้อย {threshold:.0f}; "
            "Supertrend ใช้เป็นบริบทสนับสนุน ไม่ใช่ gate")


def decision_policy_trace(policy: dict, h4: dict, states: dict,
                          preferred: str | None) -> dict:
    readiness = m30_readiness(states.get("H") or {}, preferred, policy)
    return {
        "policy_version": policy["policy_version"],
        "config_sha256": sha(policy),
        "h4": {
            "bias": h4.get("bias"),
            "state": side_code(preferred),
            "neutral_on_conflict": policy["h4_bias"]["neutral_on_conflict"],
        },
        "m30": {
            "core": list(policy["m30_readiness"]["core"]),
            "core_ready": readiness["core_ready"],
            "dmi_direction": readiness["dmi_direction"],
            "adx": readiness["adx"],
            "adx_threshold": readiness["adx_threshold"],
            "supporting": list(policy["m30_readiness"]["supporting"]),
            "supertrend_direction": readiness["supertrend_direction"],
            "supertrend_aligned": readiness["supertrend_aligned"],
        },
    }


def watch_cancel_rule(asset: str, h4: dict, direction: str) -> str:
    edge = max(float(h4["ema20"]), float(h4["ema50"])) if direction == "down" else min(
        float(h4["ema20"]), float(h4["ema50"]))
    if direction == "down":
        return (f"ยกเลิกแผนเฝ้ารอหาก H4 ปิดเหนือ EMA ทั้งคู่บริเวณ {fmt(asset, edge)} "
                "และโครงสร้างไม่ทำ Lower High/Lower Low ต่อ")
    return (f"ยกเลิกแผนเฝ้ารอหาก H4 ปิดใต้ EMA ทั้งคู่บริเวณ {fmt(asset, edge)} "
            "และโครงสร้างไม่ทำ Higher High/Higher Low ต่อ")


def public_plan_cancel_rule(asset: str, plan: dict) -> str:
    if plan.get("side") == "OCO":
        return "OCO: เมื่อ leg แรก trigger ให้ยกเลิกอีกฝั่งทันที"
    leg = plan["plans"][0]
    relation = "H1 ปิดต่ำกว่า" if leg["side"] == "BUY" else "H1 ปิดเหนือ"
    return (f"ยกเลิก setup หากแตะ stop loss {fmt(asset, leg['stop_loss'])}; "
            f"หาก {relation} {fmt(asset, leg['invalidation']['value'])} ให้ประเมินใหม่")


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
        return f"{when.day} {THAI_MONTHS[when.month]} {when:%H:%M}"
    except ValueError:
        return raw[5:16]


def m15_read(i: dict, j: dict, model: str, direction: str | None) -> str:
    if direction is None:
        return ("H4 ยังเป็น NEUTRAL จึงไม่ใช้ M30/M15 บังคับเลือกทิศเดียว "
                "แผน OCO รอแท่ง M15 ปิดข้ามขอบจริงฝั่งใดฝั่งหนึ่งและยกเลิกอีกฝั่ง")
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
        color = L_COLORS["buy"] if up else L_COLORS["sell"]
        ax.vlines(index, row["low"], row["high"], color=color, linewidth=0.8, zorder=2)
        low = min(row["open"], row["close"])
        height = max(abs(row["close"] - row["open"]), 1e-8)
        ax.add_patch(Rectangle((index - 0.32, low), 0.64, height,
                               facecolor=color, edgecolor=color, linewidth=0.6, zorder=3))
    ax.grid(True, color=L_COLORS["grid"], linewidth=0.7)
    for spine in ax.spines.values():
        spine.set_color(L_COLORS["border"])
    ax.set_facecolor(L_COLORS["plot"])
    ax.tick_params(colors=L_COLORS["axis"])
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")
    ax.yaxis.label.set_color(L_COLORS["axis"])


def h4_inset_enabled(asset: str) -> bool:
    """Style L now uses one full-width factual chart for every asset."""
    return False


def premium_chart_figure(symbol: str, timeframe: str, role: str,
                         *, bottom: float = 0.075,
                         header_accessory_text: str | None = None,
                         header_accessory_role: str | None = None,
                         surface_aware_watermark: bool = False):
    """Create the WCB editorial frame while keeping the factual plot white."""
    figure = plt.figure(figsize=(14, 7.5), facecolor=L_COLORS["canvas"])
    grid = figure.add_gridspec(
        2, 1,
        height_ratios=(visual_theme.PREMIUM_HEADER_RATIO,
                       visual_theme.PREMIUM_PLOT_RATIO),
        hspace=visual_theme.PREMIUM_HEADER_HSPACE,
        left=0.045, right=0.90, top=0.97, bottom=bottom,
    )
    header = figure.add_subplot(grid[0])
    axes = figure.add_subplot(grid[1])
    axes.set_facecolor(L_COLORS["plot"])
    title, _, underline = visual_theme.draw_edge_to_edge_header(
        figure, header, axes, checked_label(f"{symbol} · {timeframe}"), L_COLORS,
        underline_height_px=4.0)
    figure._premium_header_layout = visual_theme.edge_to_edge_header_layout(
        figure, header, axes, title, underline)
    figure._premium_watermark_layout = visual_theme.draw_matplotlib_watermark(
        figure, axes, surface="chart",
        surface_aware=surface_aware_watermark)
    figure._premium_header_card_layout = None
    if header_accessory_text:
        _, figure._premium_header_card_layout = (
            visual_theme.draw_header_accessory_card(
                figure, header, title, underline,
                checked_label(header_accessory_text), L_COLORS,
                role=header_accessory_role or "status", font_size=18.0))
    return figure, axes


def central_callout_position(ax, rows: list[dict]) -> tuple[float, float]:
    """Pick central negative space by counting candle wicks in display space."""
    ax.figure.canvas.draw()
    candidates = ((0.50, 0.52), (0.50, 0.35), (0.50, 0.69),
                  (0.34, 0.52), (0.66, 0.52))
    axis_box = ax.get_window_extent()
    box_width = min(390.0, axis_box.width * 0.32)
    box_height = 68.0
    ranked = []
    for x_fraction, y_fraction in candidates:
        x_center = axis_box.x0 + axis_box.width * x_fraction
        y_center = axis_box.y0 + axis_box.height * y_fraction
        left, right = x_center - box_width / 2, x_center + box_width / 2
        bottom, top = y_center - box_height / 2, y_center + box_height / 2
        collisions = 0
        for index, row in enumerate(rows):
            close = float(row.get("close", (float(row["high"]) + float(row["low"])) / 2))
            x_pixel = ax.transData.transform((index, close))[0]
            low_pixel = ax.transData.transform((index, float(row["low"])))[1]
            high_pixel = ax.transData.transform((index, float(row["high"])))[1]
            if left <= x_pixel <= right and high_pixel >= bottom and low_pixel <= top:
                collisions += 1
        distance = abs(x_fraction - 0.50) + abs(y_fraction - 0.52)
        ranked.append((collisions, distance, x_fraction, y_fraction))
    _, _, x_fraction, y_fraction = min(ranked)
    return x_fraction, y_fraction


def add_resolved_price_lines(ax, specs: list[dict]) -> None:
    """Pack right-rail annotations while preserving every factual y anchor."""
    if not specs:
        return
    offsets = resolved_right_label_offsets(
        ax, [(spec["role"], spec["value"]) for spec in specs],
        min_gap_points=24.0,
    )
    artists = []
    for spec in specs:
        artists.append(add_price_line(
            ax, spec["value"], spec["text"], spec["color"],
            style=spec.get("style", "--"),
            label_offset=(0.0 if spec.get("lock_to_anchor")
                          else offsets[spec["role"]]),
            leader=not spec.get("lock_to_anchor", False),
            role=spec["role"],
            x_offset=spec.get("x_offset", 0.0),
            rail=spec.get("rail", "right"),
            line_start=spec.get("line_start"),
            line_end=spec.get("line_end"),
        ))
    # Remediated target charts must keep every annotation's factual y-anchor;
    # their measured copy is short enough that packing is unnecessary. Legacy
    # assets retain the existing display-space packing behavior.
    if not all(spec.get("lock_to_anchor", False) for spec in specs):
        _pack_rendered_price_annotations(ax, artists, minimum_gap_px=13.0)


def _pack_rendered_price_annotations(ax, artists: list, *, minimum_gap_px: float) -> None:
    """Pack dense OCO labels by measured patches; leave clear rails unchanged."""
    from matplotlib.text import Annotation
    if not all(isinstance(artist, Annotation) for artist in artists):
        # Unit tests may replace add_price_line with a mock to inspect factual
        # calls; layout packing belongs only to concrete rendered annotations.
        return
    if len(artists) < 2:
        return
    figure = ax.figure
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    ordered = sorted(
        artists,
        key=lambda artist: artist.get_bbox_patch().get_window_extent(renderer).y0)
    boxes = [artist.get_bbox_patch().get_window_extent(renderer) for artist in ordered]
    if all(upper.y0 - lower.y1 >= minimum_gap_px
           for lower, upper in zip(boxes, boxes[1:])):
        return
    heights = [box.height for box in boxes]
    span = sum(heights) + minimum_gap_px * (len(heights) - 1)
    axis_box = ax.get_window_extent(renderer)
    if span > axis_box.height:
        raise RuntimeError("Style L price rail has no safe vertical space")
    centers = [(box.y0 + box.y1) / 2 for box in boxes]
    packed = [sum(centers) / len(centers) - span / 2 + heights[0] / 2]
    for index in range(1, len(centers)):
        packed.append(packed[-1] + heights[index - 1] / 2
                      + minimum_gap_px + heights[index] / 2)
    overflow = packed[-1] + heights[-1] / 2 - axis_box.y1
    if overflow > 0:
        packed = [value - overflow for value in packed]
    underflow = axis_box.y0 - (packed[0] - heights[0] / 2)
    if underflow > 0:
        packed = [value + underflow for value in packed]
    pixels_to_points = 72.0 / float(figure.dpi)
    for artist, center in zip(ordered, packed):
        anchor_y = ax.transData.transform((0, float(artist.xy[1])))[1]
        artist.set_position((0, (center - anchor_y) * pixels_to_points))


def add_price_line(ax, value: float, text: str, color: str, *, style: str = "--",
                   label_offset: float = 0, leader: bool = False,
                   role: str | None = None, x_offset: float = 0,
                   rail: str = "right", line_start: float | None = None,
                   line_end: float | None = None):
    if line_start is None and line_end is None:
        line = ax.axhline(value, color=color, linestyle=style, linewidth=1.2,
                          alpha=0.9, zorder=4)
    else:
        if line_start is None:
            line_start = ax.get_xlim()[0]
        if line_end is None:
            line_end = ax.get_xlim()[1]
        line, = ax.plot([line_start, line_end], [value, value], color=color,
                        linestyle=style, linewidth=1.2, alpha=0.9, zorder=4)
    if role:
        line.set_gid(f"premium-line:style-l:{role}")
    arrowprops = ({"arrowstyle": "-", "color": color, "lw": 0.9,
                   "shrinkA": 0, "shrinkB": 3}
                  if leader and abs(label_offset) >= 1 else None)
    left_rail = rail == "left"
    artist = ax.annotate(
        checked_label(text), xy=(0.012 if left_rail else 0.988, value),
        xycoords=("axes fraction", "data"), xytext=(x_offset, label_offset),
        textcoords="offset points", ha="left" if left_rail else "right",
        va="center",
        fontsize=(8.0 if role and (role.startswith("h1-") or
                                   role in {"entry-trigger", "stop-loss",
                                            "target-1", "target-2"} or
                                   role.startswith("oco-")) else 10.5),
        color="#ffffff", arrowprops=arrowprops,
        bbox={"boxstyle": "round,pad=0.25", "facecolor": color,
              "edgecolor": color, "alpha": 1.0})
    artist.set_zorder(9)
    patch = artist.get_bbox_patch()
    if patch is not None:
        patch.set_zorder(8)
        patch.set_alpha(1.0)
    if role:
        artist.set_gid(f"premium-label:style-l:{role}")
    return artist


def assert_premium_label_clearance(figure, context: str) -> dict:
    """Fail closed on visible text-patch overlap; annotation arrows are excluded."""
    report = visual_theme.premium_text_patch_overlap_report(
        figure, gap_pixels=12.0)
    if report["overlap_count"] or report["clipping_count"]:
        raise RuntimeError(
            f"{context} premium label layout failure: "
            f"overlaps={report['overlaps']}; clipping={report['clipping']}")
    return report


def assert_style_l_axis_contract(figure, ax, context: str) -> dict:
    """Fail closed on single-line time ticks and the two-column right rail."""
    report = assert_premium_label_clearance(figure, context)
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    x_labels = [label for label in ax.get_xticklabels()
                if label.get_visible() and label.get_text()]
    left_ticks = [tick.label1 for tick in ax.yaxis.get_major_ticks()
                  if tick.label1.get_visible() and tick.label1.get_text()]
    right_ticks = [tick.label2 for tick in ax.yaxis.get_major_ticks()
                   if tick.label2.get_visible() and tick.label2.get_text()]
    right_boxes = [label.get_window_extent(renderer) for label in right_ticks]
    premium_boxes = []
    for artist in figure.findobj():
        if not str(artist.get_gid() or "").startswith("premium-label:style-l:"):
            continue
        patch = getattr(artist, "get_bbox_patch", lambda: None)()
        premium_boxes.append(
            patch.get_window_extent(renderer) if patch is not None
            else artist.get_window_extent(renderer))
    rail_overlaps = sum(
        left.overlaps(right) for left in premium_boxes for right in right_boxes)
    canvas_safe = min(
        (figure.bbox.x1 - box.x1 for box in right_boxes), default=figure.bbox.width)
    full_safe = canvas_safe * 120.0 / float(figure.dpi)
    result = {
        "x_tick_count": len(x_labels),
        "x_tick_newline_count": sum("\n" in label.get_text() for label in x_labels),
        "left_numeric_tick_count": len(left_ticks),
        "right_numeric_tick_count": len(right_ticks),
        "price_tag_tick_overlap_count": rail_overlaps,
        "right_safe_gutter_px": round(full_safe, 2),
        "right_safe_gutter_px_at_768": round(full_safe * 768 / 1680, 2),
        "bbox_assertions": report,
        "edge_to_edge_header": figure._premium_header_layout,
        "header_accessory_card": figure._premium_header_card_layout,
        "header_accessory_card_count": sum(
            str(artist.get_gid() or "").startswith(
                "premium-label:header-card:")
            for axes in figure.axes for artist in axes.texts),
        "central_decision_card_count": sum(
            artist.get_gid() == "premium-label:style-l:central-decision"
            for axes in figure.axes for artist in axes.texts),
        "watermark": figure._premium_watermark_layout,
        "watermark_count": sum(
            artist.get_gid() == "premium-decoration:watermark"
            for axes in figure.axes for artist in axes.texts),
    }
    if (result["x_tick_newline_count"] or left_ticks or not right_ticks
            or rail_overlaps or result["right_safe_gutter_px"] < 48
            or result["right_safe_gutter_px_at_768"] < 16):
        raise RuntimeError(f"{context} axis/rail contract failed: {result}")
    figure._premium_axis_layout = result
    return result


def style_l_figure_metadata(figure, *, role: str, source_dpi: float = 120.0) -> dict:
    """Return measured per-image header/watermark evidence for Style L."""
    from matplotlib.colors import to_hex

    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    header = next(
        axes for axes in figure.axes
        if any(image.get_gid() == "premium-decoration:header-face"
               for image in axes.images))
    face = next(image for image in header.images
                if image.get_gid() == "premium-decoration:header-face")
    title = next(artist for artist in header.texts
                 if artist.get_gid() == "premium-decoration:header-title")
    underline = next(patch for patch in header.patches
                     if patch.get_gid() == "premium-decoration:header-underline")
    face_array = face.get_array()
    header_box = header.get_window_extent(renderer)
    underline_box = underline.get_window_extent(renderer)
    status_card = copy.deepcopy(getattr(figure, "_premium_header_card_layout", None))
    watermark = copy.deepcopy(getattr(figure, "_premium_watermark_layout", None))
    if watermark is None:
        raise RuntimeError("Style L figure missing watermark metadata")
    source_scale = float(source_dpi) / float(figure.dpi)
    watermark["bbox_px"] = [round(value * source_scale, 2)
                            for value in watermark["bbox_px"]]
    scale_box = lambda box: [round(value * source_scale, 2) for value in box]
    if status_card is not None:
        for key in ("bbox_px", "text_bbox_px", "shadow_offset_px"):
            status_card[key] = scale_box(status_card[key])
        for key in (
                "border_width_px", "right_safe_margin_px", "title_gap_px",
                "top_padding_px", "bottom_padding_px", "underline_clearance_px"):
            status_card[key] = round(float(status_card[key]) * source_scale, 2)
    result = {
        "role": role,
        "exact_title": title.get_text(),
        "source_dimensions_px": [int(round(figure.bbox.width * source_scale)),
                                 int(round(figure.bbox.height * source_scale))],
        "measurement_dpi": float(figure.dpi),
        "source_dpi": float(source_dpi),
        "source_scale": round(source_scale, 4),
        "header": {
            "role": "premium-decoration:header-face",
            "bbox_px": scale_box(
                (header_box.x0, header_box.y0, header_box.x1, header_box.y1)),
            "face_start": to_hex(
                face.cmap(face.norm(face_array[0, 0])), keep_alpha=False).upper(),
            "face_end": to_hex(
                face.cmap(face.norm(face_array[-1, -1])), keep_alpha=False).upper(),
            "underline": {
                "role": "premium-decoration:header-underline",
                "bbox_px": scale_box(
                    (underline_box.x0, underline_box.y0,
                     underline_box.x1, underline_box.y1)),
                "color": to_hex(underline.get_facecolor(), keep_alpha=False).upper(),
            },
            "layout": copy.deepcopy(figure._premium_header_layout),
        },
        "status_card": copy.deepcopy(status_card),
        "watermark": watermark,
    }
    required_watermark = {
        "role", "text", "color", "alpha", "bbox_px", "center_x_ratio",
        "center_y_ratio", "rotation", "layer", "vertical_nudge",
    }
    if required_watermark - set(result["watermark"]):
        raise RuntimeError("Style L watermark evidence incomplete")
    return result


def resolved_right_label_offsets(ax, levels: list[tuple[str, float]],
                                 *, min_gap_points: float = 24.0,
                                 edge_padding_points: float = 12.0) -> dict[str, float]:
    """Separate near price tags in display space without moving price lines.

    Values remain exact data-space anchors.  Only the annotation boxes receive
    point offsets; nearby boxes get a leader line from their factual level.
    """
    if not levels:
        return {}
    ax.figure.canvas.draw()
    dpi = float(ax.figure.dpi)
    pixel_to_point = 72.0 / dpi
    axis_box = ax.get_window_extent()
    low = axis_box.y0 * pixel_to_point + edge_padding_points
    high = axis_box.y1 * pixel_to_point - edge_padding_points
    actual = sorted(
        [(role, float(value), ax.transData.transform((0, float(value)))[1]
          * pixel_to_point) for role, value in levels],
        key=lambda item: item[2],
    )
    offsets = {role: 0.0 for role, _, _ in actual}
    start = 0
    while start < len(actual):
        end = start + 1
        while (end < len(actual)
               and actual[end][2] - actual[end - 1][2] < min_gap_points):
            end += 1
        cluster = actual[start:end]
        if len(cluster) > 1:
            center = sum(item[2] for item in cluster) / len(cluster)
            span = min_gap_points * (len(cluster) - 1)
            first = center - span / 2
            first = max(low, min(first, high - span))
            for index, (role, _, y_point) in enumerate(cluster):
                offsets[role] = first + index * min_gap_points - y_point
        start = end
    return offsets


def save_h1_chart(asset: str, rows: list[dict], h4_rows: list[dict], h4: dict,
                  h1: dict, plan: dict, preferred: str | None, basis: dict,
                  path: Path) -> int:
    _thai_font()
    view = rows[-100:]
    closes = [float(row["close"]) for row in view]
    ema20 = chart_indicator.ema(closes, 20)
    ema50 = chart_indicator.ema(closes, 50)
    profile = wcb_source.profile_for(asset)
    side = plan.get("side", side_code(preferred))
    fig, ax = premium_chart_figure(
        profile["symbol"], "H1", f"DAILY PRICE PLAN · {side}",
        surface_aware_watermark=True)
    candle_plot(ax, view)
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")
    ax.set_xlim(-2, len(view) - 1 + len(view) * 0.14)
    if plan.get("active"):
        zone_low = min(plan["entry"], plan["stop"])
        zone_high = max(plan["entry"], plan["stop"])
    else:
        zone_low = plan["watch_low"]
        zone_high = plan["watch_high"]
    zone_name = "โซนแผน" if plan.get("active") else "โซนรอ"
    ax.axhspan(zone_low, zone_high, color=visual_theme.BRAND["gold"],
               alpha=0.16, zorder=0)
    zone_artist = ax.text(
        0.04, (zone_low + zone_high) / 2,
        checked_label(
            f"{zone_name} {_chart_price(asset, zone_low)}–"
            f"{_chart_price(asset, zone_high)}"),
        transform=ax.get_yaxis_transform(), fontsize=10.5,
        color=L_COLORS["warning"], fontweight="bold", va="center",
        zorder=5)
    zone_artist.set_gid("premium-label:style-l:h1-zone")
    x = list(range(len(view)))
    ax.plot(x, ema20, color=L_COLORS["indicator"], linewidth=1.5, label="EMA20")
    ax.plot(x, ema50, color=L_COLORS["info"], linewidth=1.5, label="EMA50")
    target_visual = asset == "gbpusd"
    label_offsets = (resolved_right_label_offsets(ax, [
        ("pdh", h1["pdh"]), ("pdl", h1["pdl"]), ("close", h1["close"]),
    ], min_gap_points=46.0) if not target_visual else
        {"pdh": 0.0, "pdl": 0.0, "close": 0.0})
    add_price_line(ax, h1["pdh"], f"PDH {_chart_price(asset, h1['pdh'])}", L_COLORS["info"],
                   label_offset=label_offsets["pdh"], leader=not target_visual,
                   role="h1-pdh", x_offset=0, rail="right")
    pdl_artist = add_price_line(
        ax, h1["pdl"], f"PDL {_chart_price(asset, h1['pdl'])}",
        L_COLORS["indicator"], label_offset=label_offsets["pdl"],
        leader=not target_visual, role="h1-pdl", x_offset=0, rail="right")
    close_artist = add_price_line(
        ax, h1["close"], f"ปิดล่าสุด {_chart_price(asset, h1['close'])}",
        L_COLORS["neutral"], style="-", label_offset=label_offsets["close"],
        leader=not target_visual, role="h1-close", x_offset=0, rail="right")
    from matplotlib.text import Annotation
    if target_visual and isinstance(pdl_artist, Annotation) \
            and isinstance(close_artist, Annotation):
        # Both labels start on the same outer-right rail. If measured bbox
        # overlap occurs, move only PDL horizontally to an inner-right lane;
        # the factual y anchors and full-width lines remain untouched.
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        for x_offset in (0.0, -48.0, -72.0, -96.0):
            pdl_artist.set_position((x_offset, 0.0))
            fig.canvas.draw()
            pdl_box = pdl_artist.get_bbox_patch().get_window_extent(renderer)
            close_box = close_artist.get_bbox_patch().get_window_extent(renderer)
            vertical_gap = max(pdl_box.y0 - close_box.y1,
                               close_box.y0 - pdl_box.y1)
            if not pdl_box.overlaps(close_box) and vertical_gap >= 12.0:
                break
    ticks = list(range(0, len(view), max(1, len(view)//7)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([thai_tick(view[i]["at"]) for i in ticks], fontsize=9)
    ax.set_ylabel(checked_label("ราคา"))
    assert_style_l_axis_contract(fig, ax, "Style L H1")
    size = image_output.save_figure(fig, path, dpi=120)
    plt.close(fig)
    return size


def save_m15_chart(asset: str, rows: list[dict], model: str, states: dict,
                   plan: dict, preferred: str | None, basis: dict,
                   decision_policy: dict, path: Path) -> int:
    _thai_font()
    view = rows[-120:]
    profile = wcb_source.profile_for(asset)
    side = plan.get("side", side_code(preferred))
    directional_wait = not plan.get("active") and preferred is not None
    is_neutral = preferred is None
    usdcad_neutral_oco = asset == "usdcad" and is_neutral and not plan.get("active")
    fig, ax = premium_chart_figure(
        profile["symbol"], "M15", f"TRIGGER MAP · {side}", bottom=0.055,
        header_accessory_text=(f"แผน {str(plan['plans'][0].get('side') or side).upper()}"
                               if asset == "gbpusd" and plan.get("active")
                               else "NEUTRAL / โซนสังเกตการณ์"
                               if usdcad_neutral_oco else
                               "NO TRADE / รอยืนยัน" if directional_wait else None),
        header_accessory_role=("style-l-m15-plan-side"
                               if asset == "gbpusd" and plan.get("active") else
                               "style-l-m15-neutral-oco"
                               if usdcad_neutral_oco else
                               "style-l-m15-wait" if directional_wait else None),
        surface_aware_watermark=(
            directional_wait
            or (asset in {"eurusd", "usdjpy"} and is_neutral)))
    candle_plot(ax, view)
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")
    ax.set_xlim(-2, len(view) - 1 + len(view) * 0.20)
    price_specs: list[dict] = []
    target_visual = asset in {"gbpusd", "usdcad"}

    line_start = len(view) - 1 if target_visual else None
    line_end = ax.get_xlim()[1] if target_visual else None

    def queue(role: str, value: float, text: str, color: str,
              style: str = "--", *, lock_to_anchor: bool = False,
              rail: str = "right", line_span: bool = False) -> None:
        price_specs.append({"role": role, "value": value, "text": text,
                            "color": color, "style": style,
                            "lock_to_anchor": lock_to_anchor or target_visual,
                            "rail": rail,
                            "line_start": line_start if line_span else None,
                            "line_end": line_end if line_span else None})
    i = states.get("I") or {}
    trigger = None if is_neutral else plan["plans"][0]["trigger"]["value"]
    if not plan.get("active"):
        ax.axhspan(plan["watch_low"], plan["watch_high"], color=L_COLORS["neutral"],
                   alpha=0.22, zorder=0)
        if is_neutral and not usdcad_neutral_oco:
            callout_x, callout_y = central_callout_position(ax, view)
            central_artist = ax.text(
                callout_x, callout_y,
                checked_label("NEUTRAL / โซนสังเกตการณ์"),
                transform=ax.transAxes, ha="center", va="center", fontsize=18,
                color=L_COLORS["ivory"], fontweight="bold",
                bbox={"boxstyle": "round,pad=0.62",
                      "facecolor": L_COLORS["callout"],
                      "edgecolor": L_COLORS["gold"], "linewidth": 1.8},
                zorder=10)
            central_artist.set_gid("premium-label:style-l:central-decision")
        if is_neutral and plan.get("plans") and usdcad_neutral_oco:
            for leg in plan["plans"]:
                color = L_COLORS["buy"] if leg["side"] == "BUY" else L_COLORS["sell"]
                side_label = leg["side"]
                entry_word = "Entry" if asset == "usdcad" else "Trigger"
                queue(
                    f"oco-{side_label}-trigger", leg["trigger"]["value"],
                    f"{side_label} {entry_word} {_chart_price(asset, leg['trigger']['value'])}",
                    color, style="-", lock_to_anchor=True,
                    line_span=target_visual)
                for index, target in enumerate(leg["take_profit"], 1):
                    queue(
                        f"oco-{side_label}-tp{index}", target,
                        f"TP{index} {_chart_price(asset, target)}",
                        color, style="--", lock_to_anchor=True,
                        line_span=target_visual)
        elif is_neutral and plan.get("plans"):
            for leg in plan["plans"]:
                color = L_COLORS["buy"] if leg["side"] == "BUY" else L_COLORS["sell"]
                queue(
                    f"oco-{leg['side']}-trigger", leg["trigger"]["value"],
                    f"OCO {leg['side']} Trigger {fmt(asset, leg['trigger']['value'])}",
                    color, style="-")
                queue(
                    f"oco-{leg['side']}-sl", leg["stop_loss"],
                    f"OCO {leg['side']} SL {fmt(asset, leg['stop_loss'])}",
                    L_COLORS["stop_loss"], style=":")
                for index, target in enumerate(leg["take_profit"], 1):
                    queue(
                        f"oco-{leg['side']}-tp{index}", target,
                        f"OCO {leg['side']} TP{index} {fmt(asset, target)}",
                        L_COLORS["take_profit"], style="--")
        elif not is_neutral:
            opposite = plan["watch_low"] if preferred == "up" else plan["watch_high"]
            queue("trigger", trigger,
                  f"{side_code(preferred)} Trigger — รอ M15 ปิด"
                  f"{'เหนือ' if preferred == 'up' else 'ต่ำกว่า'} {_chart_price(asset, trigger)}",
                  L_COLORS["indicator"], style="-", lock_to_anchor=True)
            queue("watch-edge", opposite, f"ขอบโซนรอ {_chart_price(asset, opposite)}",
                  L_COLORS["neutral"])
    elif i:
        queue("donchian-upper", i["donchian"]["upper"],
              f"Donchian บน {_chart_price(asset, i['donchian']['upper'])}",
              L_COLORS["warning"], style="-",
              rail="left" if asset == "gbpusd" else "right")
        queue("donchian-lower", i["donchian"]["lower"],
              f"Donchian ล่าง {_chart_price(asset, i['donchian']['lower'])}",
              L_COLORS["warning"], style="-",
              rail="left" if asset == "gbpusd" else "right")
    if plan.get("active"):
        leg = plan["plans"][0]
        leg_side = str(leg.get("side") or side_code(preferred)).upper()
        try:
            entry_zone = leg.get("entry_zone") or {}
            zone_low = float(entry_zone["low"])
            zone_high = float(entry_zone["high"])
        except (KeyError, TypeError, ValueError):
            zone_low = zone_high = math.nan
        if (asset == "gbpusd" and math.isfinite(zone_low)
                and math.isfinite(zone_high) and zone_low < zone_high):
            zone_color = L_COLORS["buy"] if leg_side == "BUY" else L_COLORS["sell"]
            zone = ax.axhspan(zone_low, zone_high, color=zone_color,
                              alpha=0.16, zorder=0)
            zone.set_gid("premium-zone:style-l:entry-zone")
        entry_text = (f"{leg_side} Entry {_chart_price(asset, leg['trigger']['value'])}"
                      if asset == "gbpusd" else
                      f"Entry trigger {_chart_price(asset, leg['trigger']['value'])}")
        stop_text = (f"SL {_chart_price(asset, leg['stop_loss'])}"
                     if asset == "gbpusd" else
                     f"Stop loss {_chart_price(asset, leg['stop_loss'])}")
        queue("entry-trigger", leg["trigger"]["value"],
              entry_text, L_COLORS["info"], line_span=target_visual)
        queue("stop-loss", leg["stop_loss"],
              stop_text, L_COLORS["stop_loss"], line_span=target_visual)
        for index, target in enumerate(leg["take_profit"], 1):
            target_text = (f"TP{index} {_chart_price(asset, target)}"
                           if asset == "gbpusd" else
                           f"Target {index} {_chart_price(asset, target)}")
            queue(f"target-{index}", target,
                  target_text, L_COLORS["take_profit"], line_span=target_visual)
    add_resolved_price_lines(ax, price_specs)
    ticks = list(range(0, len(view), max(1, len(view)//7)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([thai_tick(view[i]["at"]) for i in ticks], fontsize=9)
    ax.set_ylabel(checked_label("ราคา"))
    assert_style_l_axis_contract(fig, ax, "Style L M15")
    size = image_output.save_figure(fig, path, dpi=120)
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


def _plan_projection(plan: dict, field: str, *, nested: str | None = None) -> object:
    values = {}
    for leg in plan.get("plans") or []:
        value = leg.get(field)
        if nested is not None:
            value = (value or {}).get(nested)
        values[str(leg.get("side"))] = copy.deepcopy(value)
    if plan.get("side") == "OCO":
        return values
    return next(iter(values.values()), None)


def build_continuity_snapshot(asset: str, cutoff: datetime, plan: dict) -> dict:
    return {
        "schema": CONTINUITY_SCHEMA,
        "asset": asset,
        "date": cutoff.astimezone(wcb_source.BANGKOK).date().isoformat(),
        "cutoff_utc": cutoff.isoformat(),
        "cutoff_at": plan.get("cutoff_at") or cutoff.astimezone(wcb_source.BANGKOK).isoformat(),
        "side": plan.get("side"),
        "status": plan.get("status"),
        "trigger": _plan_projection(plan, "trigger", nested="value"),
        "entry_zone": _plan_projection(plan, "entry_zone"),
        "stop_loss": _plan_projection(plan, "stop_loss"),
        "take_profit": _plan_projection(plan, "take_profit"),
        "invalidation": _plan_projection(plan, "invalidation", nested="value"),
        "valid_until": plan.get("valid_until"),
        "evidence_hash": plan.get("evidence_hash"),
        "plans": copy.deepcopy(plan.get("plans") or []),
    }


def _row_datetime(row: dict) -> datetime | None:
    raw = str(row.get("at") or row.get("date") or "")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed.replace(tzinfo=wcb_source.BANGKOK) if parsed.tzinfo is None else parsed


def evaluate_prior_plan(previous: dict, closed_rows: list[dict]) -> str:
    """Evaluate a published plan from ordered closed bars; ambiguity fails closed."""
    try:
        start = datetime.fromisoformat(str(previous["cutoff_at"]))
        end = datetime.fromisoformat(str(previous["valid_until"]))
    except (KeyError, TypeError, ValueError):
        return "ประเมินผลไม่ได้จากแท่งปิด"
    rows = sorted(
        (row for row in closed_rows
         if (when := _row_datetime(row)) is not None and start < when <= end),
        key=lambda row: _row_datetime(row))
    any_triggered = False
    any_invalidated = False
    for leg in previous.get("plans") or []:
        side = str(leg.get("side") or "")
        try:
            trigger = float((leg.get("trigger") or {})["value"])
            stop = float(leg["stop_loss"])
            targets = [float(value) for value in leg["take_profit"]]
            invalidation = float((leg.get("invalidation") or {})["value"])
        except (KeyError, TypeError, ValueError):
            return "ประเมินผลไม่ได้จากแท่งปิด"
        triggered = False
        for row in rows:
            try:
                close = float(row["close"])
                low = float(row.get("low", close))
                high = float(row.get("high", close))
            except (KeyError, TypeError, ValueError):
                continue
            crossed_trigger = close > trigger if side == "BUY" else close < trigger
            if not triggered and crossed_trigger:
                triggered = True
                any_triggered = True
            if not triggered:
                continue
            target = targets[-1]
            # Use the first adverse close level.  The more distant invalidation
            # remains part of the contract but cannot make the nearer SL vanish.
            stop_level = max(stop, invalidation) if side == "BUY" else min(stop, invalidation)
            touched_stop = low <= stop_level if side == "BUY" else high >= stop_level
            touched_target = high >= target if side == "BUY" else low <= target
            if touched_stop and touched_target:
                return "ประเมินผลไม่ได้จากแท่งปิด"
            invalidated = close <= stop_level if side == "BUY" else close >= stop_level
            completed = close >= target if side == "BUY" else close <= target
            if invalidated:
                any_invalidated = True
                break
            if completed:
                return "Completed"
    if any_invalidated:
        return "Invalidation"
    return "Trigger แล้ว" if any_triggered else "ยังไม่ Trigger"


def _snapshot_from_sidecar(asset: str, sidecar: dict) -> dict:
    cutoff = datetime.fromisoformat(str(sidecar["cutoff_at"]))
    plan = {
        "side": sidecar.get("side"), "status": sidecar.get("plan_status"),
        "valid_until": sidecar.get("valid_until"),
        "evidence_hash": sidecar.get("evidence_hash"),
        "plans": sidecar.get("plans") or [],
    }
    snapshot = build_continuity_snapshot(asset, cutoff, plan)
    snapshot.update({
        "cutoff_at": sidecar.get("cutoff_at"),
        "article_sha256": sidecar.get("article_sha256"),
        "qa_status": sidecar.get("qa_status"),
        "publishable": sidecar.get("publishable"),
    })
    return snapshot


def _article_supports_snapshot(article: str, asset: str, snapshot: dict) -> bool:
    """Allow editorial-only rewrites while proving every plan datum is unchanged."""
    evidence_hash = str(snapshot.get("evidence_hash") or "")
    if not evidence_hash or evidence_hash not in article:
        return False
    if f"| แผนสาธารณะ | **{snapshot.get('side')}** |" not in article:
        return False
    for leg in snapshot.get("plans") or []:
        values = [
            (leg.get("trigger") or {}).get("value"),
            (leg.get("entry_zone") or {}).get("low"),
            (leg.get("entry_zone") or {}).get("high"),
            leg.get("stop_loss"),
            *((leg.get("take_profit") or [])),
            (leg.get("invalidation") or {}).get("value"),
        ]
        try:
            if any(f"`{fmt(asset, float(value))}`" not in article for value in values):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _verified_prior_snapshot(asset: str, current_date: str, *,
                             published_root: Path, internal_root: Path) -> dict | None:
    candidates: list[dict] = []
    paths = list((STATE / asset).glob("*.json"))
    paths += list(Path(internal_root).glob(
        f"*/{asset}/internal/style-l/{asset}.trade-plan-public.json"))
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            snapshot = (raw if raw.get("schema") == CONTINUITY_SCHEMA
                        else _snapshot_from_sidecar(asset, raw))
            baseline_date = str(snapshot.get("date") or "")
            if not baseline_date or baseline_date >= current_date:
                continue
            if snapshot.get("qa_status") not in {None, "PASS_QA"}:
                continue
            if snapshot.get("publishable") not in {None, True}:
                continue
            article = (Path(published_root)
                       / datetime.fromisoformat(baseline_date).strftime("%d-%m-%Y")
                       / STYLE_FOLDER / f"{asset}.md")
            expected_hash = snapshot.get("article_sha256")
            if not article.is_file() or not expected_hash:
                continue
            if file_sha256(article) != expected_hash:
                article_text = article.read_text(encoding="utf-8")
                if not _article_supports_snapshot(article_text, asset, snapshot):
                    continue
            candidates.append(snapshot)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
    return max(candidates, key=lambda item: (str(item["date"]), str(item.get("cutoff_utc") or "")),
               default=None)


def _continuity_value(asset: str, value: object) -> str:
    if isinstance(value, dict):
        if {"low", "high"} <= set(value):
            return (f"{fmt(asset, float(value['low']))}–"
                    f"{fmt(asset, float(value['high']))}")
        if "value" in value:
            return fmt(asset, float(value["value"]))
        return " / ".join(
            f"{side} {(_continuity_value(asset, item))}" for side, item in value.items())
    if isinstance(value, list):
        return "/".join(fmt(asset, float(item)) for item in value)
    return fmt(asset, float(value)) if isinstance(value, (int, float)) else str(value)


def continuity_snapshot(asset: str, cutoff: datetime, preferred: str | None,
                        plan: dict, closed_rows: list[dict] | None = None, *,
                        published_root: Path | None = None,
                        internal_root: Path | None = None) -> tuple[dict, dict | None]:
    del preferred  # Kept in the call contract; the public plan is canonical.
    current = build_continuity_snapshot(asset, cutoff, plan)
    published_root = Path(published_root or (P002 / "output"))
    internal_root = Path(internal_root or (P002 / "work" / "build"))
    previous = _verified_prior_snapshot(
        asset, current["date"], published_root=published_root, internal_root=internal_root)
    if previous is None:
        return current, None
    trigger_text = _continuity_value(asset, previous.get("trigger"))
    changes = []
    labels = {
        "side": "Side", "status": "Status", "trigger": "Trigger",
        "entry_zone": "Entry zone", "stop_loss": "SL",
        "take_profit": "TP", "invalidation": "Invalidation",
    }
    for key, label in labels.items():
        if previous.get(key) != current.get(key):
            changes.append(
                f"{label} {_continuity_value(asset, previous.get(key))} → "
                f"{_continuity_value(asset, current.get(key))}")
    return current, {
        "baseline_date": previous["date"],
        "previous": (f"{previous.get('side')} · {previous.get('status')} · "
                     f"Trigger {trigger_text}"),
        "changes": changes,
        "result": evaluate_prior_plan(previous, closed_rows or []),
        "baseline_evidence_hash": previous.get("evidence_hash"),
    }


def render_article(asset: str, cutoff: datetime, h4: dict, h1: dict, states: dict,
                   model: str, reason: str, plan: dict, preferred: str | None,
                   preferred_reason: str, events: list[dict],
                   input_hash: str, images: tuple[str, str], bases: dict,
                   continuity: dict | None, decision_policy: dict | None = None,
                   calendar_images: tuple[str, ...] = ()) -> str:
    policy = decision_policy or load_decision_policy()
    profile = wcb_source.profile_for(asset)
    h = states.get("H") or {}
    i = states.get("I") or {}
    j = states.get("J") or {}
    cutoff_th = cutoff.astimezone(wcb_source.BANGKOK)
    date_text = cutoff_th.date().isoformat()
    is_active = bool(plan.get("active"))
    is_neutral = preferred is None
    plan_name = "แผนเทรดรายวัน"
    title = headline_format.title(asset, date_text, f"{plan_name}จาก H4 ถึง M15")
    slug = f"{asset}-forex-daily-plan-{date_text}"
    side = plan["side"]
    status_excerpt = ("มี OCO สองฝั่งจากระดับแท่งปิดจริงและรอ trigger แรก"
                      if is_neutral else "มีจังหวะตามเงื่อนไขของแผน"
                      if is_active else "มีแผนครบและยังรอ trigger")
    excerpt = (f"อัปเดต{plan_name} {profile['symbol']} จาก H4 ถึง M15 "
               f"ให้น้ำหนักฝั่ง {side} และ{status_excerpt} พร้อมระดับราคาและข่าวสำคัญประจำวัน")
    trend = web_frontmatter_contract.trend_from_direction(preferred)
    leg_by_side = {leg["side"]: leg for leg in plan["plans"]}
    trigger = None if is_neutral else plan["plans"][0]["trigger"]["value"]
    trigger_word = "เหนือ" if preferred == "up" else "ต่ำกว่า"
    cancel_rule = public_plan_cancel_rule(asset, plan)
    _, next_event = event_sections(events, cutoff)
    status = plan["status"]
    m30_status = ("ยังไม่ประเมินจนกว่า H4 จะชัด" if is_neutral else
                  "ผ่าน" if m30_gate_pass(h, preferred, policy) else "ยังไม่ผ่าน")
    if is_neutral:
        readiness = m30_readiness(h, None, policy)
        supertrend_context = (readiness["supertrend_direction"] or "ไม่ระบุ")
        lead = ("ภาพใหญ่ H4 ยังเป็น NEUTRAL เพราะ EMA และโครงสร้างไม่ยืนยันไปทางเดียวกัน "
                "จึงใช้แผน OCO จากขอบบนและขอบล่างจริง โดย trigger แรกยกเลิกอีกฝั่ง")
        m30_summary = (f"M30 บันทึก DMI direction={readiness['dmi_direction'] or 'none'} "
                       f"และ ADX {readiness['adx']:.1f} เทียบเกณฑ์ "
                       f"{readiness['adx_threshold']:.0f}; Supertrend={supertrend_context} "
                       "เป็นบริบทสนับสนุนเท่านั้น ยังไม่เปิด readiness gate เมื่อ H4 เป็น NEUTRAL")
    elif is_active:
        lead = (f"ภาพใหญ่ H4 ให้น้ำหนัก {side} ขณะที่ M30 และ M15 ผ่านด่านของระบบแล้ว "
                f"แผนจึงอยู่สถานะ ACTIVE โดยใช้ {fmt(asset, plan['entry'])} เป็น trigger "
                f"และ {fmt(asset, plan['stop'])} เป็นจุดยกเลิก")
        m30_summary = m30_read(h, preferred, policy)
    else:
        lead = (f"ภาพใหญ่ H4 ให้น้ำหนัก {side} แต่ M30 {m30_status}ตามกฎของระบบ "
                f"และ M15 ยังต้องปิด{trigger_word} {fmt(asset, trigger)} "
                "ดังนั้นแผนปัจจุบันคือรอและยังไม่เปิดสถานะ")
        m30_summary = m30_read(h, preferred, policy)
    trigger_cell = ((
        f"BUY: M15 ปิดเหนือ `{fmt(asset, leg_by_side['BUY']['trigger']['value'])}` / "
        f"SELL: M15 ปิดต่ำกว่า `{fmt(asset, leg_by_side['SELL']['trigger']['value'])}`")
        if is_neutral else f"M15 ปิด{trigger_word} `{fmt(asset, trigger)}`")
    m30_cell = ("DMI direction + ADX ใช้หลัง H4 ชัด; Supertrend เป็น supporting context"
                if is_neutral else m30_rule(preferred, policy))
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
        f"| แผนสาธารณะ | **{side}** |",
        f"| สถานะตอนนี้ | **{status}** |",
        f"| Trigger | {trigger_cell} |",
        f"| เงื่อนไข M30 | {m30_status} — {m30_cell} |",
        f"| จุดยกเลิก | {cancel_rule} |",
        f"| ข่าวถัดไป | {next_event} |",
        "",
        f"**ฝั่งแผนสาธารณะ: {side}**", "",
        indent_paragraph(lead), "",
        indent_paragraph(
            f"กราฟ H4 มีลักษณะ{structure_th(h4['structure'])} และ{ema_position_th(asset, h4)} "
            + (f"จึงคงสถานะ NEUTRAL เหตุผลหลักคือ {preferred_reason}" if is_neutral else
               f"จึงเลือกติดตามฝั่ง {side} เพียงฝั่งเดียว เหตุผลหลักคือ {preferred_reason}")), "",
        indent_paragraph(
            f"{m30_summary} ราคาปิด H1 ล่าสุดอยู่ที่ {fmt(asset, h1['close'])}"), "",
        f"![{h1_alt}]({images[0]})", "",
    ]
    if continuity:
        lines += [
            "**ความต่อเนื่องจากแผนครั้งก่อน**", "",
            f"- แผนครั้งก่อน ({continuity['baseline_date']}): {continuity['previous']}",
        ]
        if continuity.get("changes"):
            lines.append("- สิ่งที่เปลี่ยนวันนี้: " + "; ".join(continuity["changes"]))
        lines += [f"- ผลของแผนเดิม: {continuity['result']}", ""]
    lines += [
        "## จังหวะและแผนการเทรด", "",
        indent_paragraph(m15_read(i, j, model, preferred)), "",
        f"![Trigger map M15 ของ {profile['symbol']}]({images[1]})", "",
        "**แผนตามสถานการณ์**", "",
    ]
    lines += [
        f"**แผน {side} — สถานะ {plan['status']}**",
        "| Side | Trigger | Entry zone | Stop loss | Take profit | RR | Invalidation |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for leg in plan["plans"]:
        condition = "M15 ปิดเหนือ" if leg["side"] == "BUY" else "M15 ปิดต่ำกว่า"
        invalidation = "H1 ปิดต่ำกว่า" if leg["side"] == "BUY" else "H1 ปิดเหนือ"
        targets = " / ".join(f"`{fmt(asset, value)}`" for value in leg["take_profit"])
        rrs = " / ".join(f"{value:.2f}R" for value in leg["risk_reward"])
        lines.append(
            f"| {leg['side']} | {condition} `{fmt(asset, leg['trigger']['value'])}` | "
            f"`{fmt(asset, leg['entry_zone']['low'])}`–"
            f"`{fmt(asset, leg['entry_zone']['high'])}` | "
            f"`{fmt(asset, leg['stop_loss'])}` | {targets} | {rrs} | "
            f"{invalidation} `{fmt(asset, leg['invalidation']['value'])}` |")
    lines += [
        "",
        f"- {cancel_rule}",
        f"- Cutoff at: `{plan['cutoff_at']}`",
        f"- Valid until: `{plan['valid_until']}`",
        f"- Evidence hash: `{plan['evidence_hash']}`",
        "- RR ยังไม่หัก spread/slippage; ก่อนใช้งานต้องคำนวณใหม่จากต้นทุนจริงของบัญชี",
        "- WAIT_TRIGGER หมายถึงแผนครบแต่กำลังรอแท่ง M15 ปิดยืนยัน; ไม่ใช่การไม่มีแผน",
        "",
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
    lines += ["## ข่าวสำคัญวันนี้", ""]
    if calendar_images:
        lines += [
            f"![ข่าวสำคัญประจำวันที่เกี่ยวข้องกับ {profile['symbol']}]({name})" for name in calendar_images
        ]
        lines.append("")
    else:
        lines += [
            indent_paragraph(
                "วันนี้ไม่มีข่าวระดับ Medium/High ที่เกี่ยวข้องกับสกุลเงินทั้งสองฝั่ง"),
            "",
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


def frontmatter_value(article: str, key: str) -> str | None:
    """Read one scalar from the first frontmatter block without accepting body text."""
    if not article.startswith("---\n"):
        return None
    try:
        block = article.split("---", 2)[1]
    except IndexError:
        return None
    for line in block.splitlines():
        name, separator, value = line.partition(":")
        if separator and name.strip() == key:
            return value.strip().strip("\"'")
    return None


def has_closed_bar_confirmation(article: str) -> bool:
    """ยอมรับถ้อยคำของทั้ง WAIT และ ACTIVE แต่ต้องยืนยัน M30/M15 ด้วยแท่งปิด."""
    # WAIT articles explicitly say that M30 has *not* passed yet (for
    # example, ``M30 ยังไม่ผ่านกฎฝั่ง SELL``).  The old substring check only
    # accepted the affirmative wording and therefore rejected a valid plan
    # even though the article included the closed-bar rule and its evidence.
    m30_confirmed = bool(re.search(
        r"M30\s+(?:ยังไม่)?ผ่านกฎฝั่ง|M30\s+ต้องผ่านครบ|เงื่อนไข M30",
        article))
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


def validate_article(article: str, asset: str, plan: dict,
                     calendar_images: tuple[str, ...] = ()) -> list[str]:
    findings: list[str] = []
    expected = ["asset", "title", "slug", "excerpt", "author_slug", "timeframe", "trend",
                "status", "country", "language"]
    if frontmatter_keys(article) != expected:
        findings.append("frontmatter ต้องมี 10 ช่องตามลำดับที่อนุมัติ")
    try:
        expected_trend = web_frontmatter_contract.trend_from_direction(
            plan.get("direction"))
    except ValueError as exc:
        findings.append(str(exc))
    else:
        actual_trend = frontmatter_value(article, "trend")
        if actual_trend not in web_frontmatter_contract.WEB_TREND_CODES:
            findings.append("frontmatter trend ต้องเป็น up | dn | fl")
        elif actual_trend != expected_trend:
            findings.append(
                f"frontmatter trend ต้องตรง canonical plan: "
                f"คาด {expected_trend} แต่ได้ {actual_trend}")
    if article.count("\n## ") != 3:
        findings.append("บทความต้องมีหัวข้อ H2 จำนวน 3 หัวข้อ")
    image_refs = re.findall(r"!\[[^]]+\]\(([^)]+\.webp)\)", article)
    expected_images = [
        f"{asset}-forex-daily-h1-plan.webp",
        f"{asset}-forex-daily-m15-trigger.webp",
        *calendar_images,
    ]
    if image_refs != expected_images:
        findings.append("บทความต้องอ้างภาพ H1/M15/ข่าวตาม manifest และลำดับที่อนุมัติ")
    words = voice_rules.count_public_words(article)
    if not 400 <= words <= 900:
        findings.append(f"ความยาว {words} คำ อยู่นอกช่วง 400–900")
    if "| สถานะ | สกุลเงิน | เวลาไทย | ข่าว | ตัวเลข |" in article:
        findings.append("ข่าว Style L ต้องเป็นภาพ ไม่ใช่ตาราง Markdown")
    if calendar_images:
        if "วันนี้ไม่มีข่าวระดับ Medium/High" in article:
            findings.append("มีภาพข่าวแล้วห้ามแสดงข้อความว่าไม่มีข่าว")
    elif "วันนี้ไม่มีข่าวระดับ Medium/High" not in article:
        findings.append("ไม่มีข่าวต้องแสดงข้อความสั้นและไม่สร้างภาพว่าง")
    if deprecated_copy_in(article):
        findings.append("พบข้อความเก่าที่ผู้ใช้สั่งถอดออกจาก Style L")
    if article.count("&emsp;") < 7:
        findings.append("ย่อหน้าเนื้อหาต้องขึ้นต้นด้วย &emsp;")
    if "http://" in article or "https://" in article:
        findings.append("บท Style L ห้ามมีลิงก์ URL ในเนื้อหา")
    is_neutral = plan.get("direction") is None
    if is_neutral:
        if plan.get("side") != "OCO" or len(plan.get("plans", [])) != 2:
            findings.append("H4 NEUTRAL ต้องเผยแพร่ OCO สอง leg")
    elif not has_closed_bar_confirmation(article):
        findings.append("ขาดกฎยืนยัน M30/M15 แบบแท่งปิด")
    required_plan_copy = (
        "| Side | Trigger | Entry zone | Stop loss | Take profit | RR | Invalidation |",
        f"**ฝั่งแผนสาธารณะ: {plan.get('side')}**",
        f"- Valid until: `{plan.get('valid_until')}`",
        f"- Evidence hash: `{plan.get('evidence_hash')}`",
        "RR ยังไม่หัก spread/slippage",
    )
    for marker in required_plan_copy:
        if marker not in article:
            findings.append(f"public trade plan ขาดช่อง: {marker}")
    if any(text in article for text in (
            "ไม่มี Entry, Stop Loss, Take Profit หรือ RR",
            "ไม่มีแผนฝั่งและไม่มี trigger",
            "ยังไม่มี Entry, Stop Loss หรือ Take Profit")):
        findings.append("บท publishable ห้ามประกาศว่าไม่มีแผนครบ")
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
    try:
        decision_policy = load_decision_policy()
    except RuntimeError as exc:
        summary["errors"].append(str(exc))
        summary["ok"] = False
        write_json(evidence_dir / "run-summary.json", summary)
        return summary
    summary["decision_policy"] = {
        "policy_version": decision_policy["policy_version"],
        "config_sha256": sha(decision_policy),
    }
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
            input_payload = {"asset": asset, "cutoff_utc": cutoff.isoformat(),
                             "rows": {**rows, "1day": daily}}
            input_hash = sha(input_payload)
            write_json(input_dir / f"{asset}-closed-bars.json", input_payload)
            preferred, preferred_reason = preferred_direction(h4)
            model, reason = choose_model(h4["bias"], states, decision_policy)
            plan = scenario(
                model, h4["bias"], preferred, h1, states,
                asset=asset, cutoff=cutoff, evidence_hash=input_hash,
                current_close=float(rows["15min"][-1]["close"]))
            selected_events = daily_relevant_events(asset, events, cutoff)
            continuity_state, continuity = continuity_snapshot(
                asset, cutoff, preferred, plan, rows["15min"])
            continuity_updates[asset] = continuity_state
            evidence_payload = {
                "asset": asset, "cutoff_utc": cutoff.isoformat(),
                "source_meta": source_meta, "daily_meta": daily_meta,
                "bases": bases, "daily_basis": daily_basis,
                "h4": {k: v for k, v in h4.items() if not k.endswith("_series")},
                "h1": h1, "states": states, "model": model,
                "model_reason": reason, "preferred_direction": preferred,
                "preferred_reason": preferred_reason, "scenario": plan,
                "decision_policy": decision_policy_trace(
                    decision_policy, h4, states, preferred),
                "events": selected_events, "continuity": continuity,
                "input_sha256": input_hash,
            }
            write_json(evidence_dir / f"{asset}-decision-trace.json", evidence_payload)
            data_findings = validate_data_domain(asset, h4, h1, plan)
            if plan.get("evidence_hash") != input_hash:
                data_findings.append(f"{asset}: evidence hash ไม่ตรง canonical input snapshot")
            expected_close = _round_price(asset, float(rows["15min"][-1]["close"]))
            if plan.get("current_close") != expected_close:
                data_findings.append(f"{asset}: current_close ไม่ตรงแท่ง M15 ปิดล่าสุด")
            if data_findings:
                summary["errors"].extend(data_findings)
                summary["assets"][asset] = {
                    "status": "DATA_HOLD", "model": model,
                    "bias": h4["bias"], "preferred_direction": preferred,
                    "input_sha256": input_hash,
                }
                continue
            folder = staging_dir / asset
            folder.mkdir(parents=True, exist_ok=True)
            h1_name = f"{asset}-forex-daily-h1-plan.webp"
            m15_name = f"{asset}-forex-daily-m15-trigger.webp"
            sizes = {
                h1_name: save_h1_chart(asset, rows["1h"], rows["4h"], h4, h1,
                                       plan, preferred, bases["1h"], folder / h1_name),
                m15_name: save_m15_chart(asset, rows["15min"], model, states, plan,
                                           preferred, bases["15min"], decision_policy,
                                           folder / m15_name),
            }
            calendar_pages = forex_daily_calendar_renderer.paginate_events(selected_events)
            calendar_names = forex_daily_calendar_renderer.filenames(
                asset, cutoff.astimezone(wcb_source.BANGKOK).date().isoformat(),
                len(calendar_pages))
            calendar_rendered = forex_daily_calendar_renderer.render_daily_calendar(
                asset=asset, symbol=wcb_source.profile_for(asset)["symbol"],
                article_date=cutoff.astimezone(wcb_source.BANGKOK).date().isoformat(),
                events=selected_events, output_dir=folder, cutoff=cutoff)
            if tuple(Path(item["path"]).name for item in calendar_rendered) != calendar_names:
                raise RuntimeError(f"{asset}: calendar manifest drift")
            sizes.update({Path(item["path"]).name: item["bytes"] for item in calendar_rendered})
            article = render_article(asset, cutoff, h4, h1, states, model, reason,
                                     plan, preferred, preferred_reason, selected_events,
                                     input_hash, (h1_name, m15_name), bases, continuity,
                                     decision_policy, calendar_names)
            article = publicize_style_l(article, asset)
            findings = validate_article(article, asset, plan, calendar_names)
            findings.extend(validate_style_l_number_policy(article, asset))
            findings.extend(validate_markdown_snapshot_parity(
                article, asset, h4, h1, plan, preferred))
            article_path = folder / f"{asset}.md"
            article_path.write_text(article, encoding="utf-8", newline="\n")
            continuity_state.update({
                "cutoff_at": plan.get("cutoff_at"),
                "article_sha256": file_sha256(article_path),
                "qa_status": "PASS_QA", "publishable": True,
            })
            for image_name in sizes:
                image_output.verify(folder / image_name)
            overlap_report = overlap(article, asset)
            write_json(evidence_dir / f"{asset}-overlap.json", overlap_report)
            if findings:
                summary["errors"].extend(f"{asset}: {item}" for item in findings)
            asset_files = [
                article_path, folder / h1_name, folder / m15_name,
                *(folder / name for name in calendar_names),
            ]
            if not findings:
                sidecar = public_trade_plan_sidecar(
                    asset, article_path.name, article, plan)
                sidecar_findings = validate_public_trade_plan_sidecar(sidecar, article)
                if sidecar_findings:
                    findings.extend(sidecar_findings)
                    summary["errors"].extend(
                        f"{asset}: {item}" for item in sidecar_findings)
                else:
                    sidecar_path = folder / f"{asset}.trade-plan-public.json"
                    write_json(sidecar_path, sidecar)
                    asset_files.append(sidecar_path)
            staged_files.extend(asset_files)
            summary["assets"][asset] = {
                "status": "PASS_QA" if not findings else "BLOCK_QA",
                "model": model, "bias": h4["bias"],
                "preferred_direction": preferred,
                "readiness": ("ACTIVE" if plan.get("active") else
                              "NEUTRAL" if preferred is None else "WAIT"),
                "decision_policy_version": decision_policy["policy_version"],
                "words": voice_rules.count_public_words(article),
                 "input_sha256": input_hash, "images": sizes,
                 "calendar": {
                     "events": len(selected_events),
                     "pages": len(calendar_names),
                     "images": list(calendar_names),
                 },
                "max_overlap_jaccard": overlap_report["max_jaccard"],
                "number_policy": public_number_policy.POLICY_VERSION,
                "style_number_policy": STYLE_NUMBER_POLICY,
                "trade_plan_contract": "PASS" if not findings else "BLOCK_QA",
                "trade_plan_sidecar": (
                    f"{asset}.trade-plan-public.json" if not findings else None),
            }
        except data_fetch_retry.DataFetchUnavailable as exc:
            summary["errors"].append(f"{asset}: DATA_FETCH_FAILED: {exc}")
            summary["assets"][asset] = {
                "status": "DATA_HOLD", "reason": str(exc),
            }
        except DataHold as exc:
            summary["errors"].append(f"{asset}: DATA_HOLD: {exc}")
            summary["assets"][asset] = {"status": "DATA_HOLD"}
        except Exception as exc:  # noqa: BLE001 — asset ใดตกต้อง block ทั้งชุด
            summary["errors"].append(f"{asset}: {type(exc).__name__}: {exc}")
            summary["assets"][asset] = {"status": "BLOCK_ERROR"}

    if summary["errors"]:
        summary["ok"] = False
        write_json(evidence_dir / "run-summary.json", summary)
        return summary

    public_sources = web_import_sources(staged_files)
    day_folder = publish_layout.day_folder(cutoff)
    internal_day = Path(publish_root).parent / "work" / "build" / day_folder
    for asset in requested:
        source = staging_dir / asset / f"{asset}.trade-plan-public.json"
        target = (internal_day / asset / "internal" / "style-l" /
                  f"{asset}.trade-plan-public.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    destination = Path(publish_root) / day_folder / STYLE_FOLDER
    if publish and public_sources:
        destination.mkdir(parents=True, exist_ok=True)
        clear_output_sidecars(destination)
        for asset in requested:
            clear_output_calendar_images(destination, asset)
        for source in public_sources:
            shutil.copy2(source, destination / source.name)
    if publish:
        for asset, state in continuity_updates.items():
            write_json(STATE / asset / f"{state['date']}.json", state)
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
