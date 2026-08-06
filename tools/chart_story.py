"""เครื่องอ่านโครงสร้างกราฟของสไตล์ D — คำนวณทุกอย่างจากแท่งราคา ไม่มีการเดา

หลักการ (จากแผน chart storytelling ที่หัวหน้าอนุมัติ 2026-08-06):
- โค้ดคำนวณ geometry ทั้งหมด · ไม่มีชั้นไหนสร้างราคาใหม่ขึ้นเอง
- บทความและกราฟอ่านจาก artifact เดียวกัน (`build_story`) — เลขบนภาพกับเลขในบท
  จึงตรงกันโดยโครงสร้าง ไม่ใช่โดยวินัย
- หนามราคาแหลมครั้งเดียวห้ามกำหนด geometry ทั้งเส้น — ใช้ค่า "อันดับสอง"
  (หลักเดียวกับ provider_step ที่ปิด E7: ค่าประหลาดตัวเดียวต้องไม่ยกทั้งก้อน)
- ฉากทัศน์เป็น "เงื่อนไข ไม่ใช่คำทำนาย" และต้องชี้กลับระดับที่คำนวณได้เสมอ

สไตล์ D แยกขาดจาก A/B/C ตามคำสั่งหัวหน้า 2026-08-06 — ทะเบียน `WCB_WRITERS`
และด่านของสายนั้นไม่รู้จักสไตล์นี้ และต้องไม่รู้จักต่อไป
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import wcb_source  # noqa: E402

SCHEMA = "chart-story-v1"

DISPLAY_BARS = 320          # ภาพรวมรอบใหญ่ ~15 เดือน ตามภาพตัวอย่างที่หัวหน้าส่งมา
ZOOM_BARS = 120             # ภาพระยะใกล้สำหรับระดับตัดสินใจ
SWING_WINDOW = 5            # แท่งซ้าย/ขวาที่ต้องต่ำ/สูงกว่าจึงนับเป็น swing
MAJOR_WINDOW = 10           # หน้าต่างยอด major (แตะครั้งเดียวก็มีความหมาย)
RIBBON_SLOPE_BARS = 5       # ระยะวัดความชันของ SMA50 สำหรับสีโหมดตลาด
CLUSTER_TOUCHES_MIN = 2     # ระดับแนวนอนต้องถูกแตะอย่างน้อยกี่ครั้งจึงเป็น cluster
MAX_RESISTANCE_LINES = 6
MAX_DEMAND_ZONES = 2
# ครึ่งความสูงโซน คิดเป็นเท่าของ ATR14 — 0.5 ให้ช่วง POI แคบพอจะใช้งานจริง
# ตามรูปแบบบทอ้างอิงที่หัวหน้าเลือก (investing.com 200458003: POI กว้าง ~20-40 จุด)
ZONE_HALF_ATR = 0.5
WEEK52_SESSIONS = 252


class StoryUnavailable(RuntimeError):
    """ข้อมูลไม่พอสร้างโครงสร้าง — หยุดสายสไตล์ D ห้ามเดาต่อ"""


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for index, value in enumerate(values):
        total += value
        if index >= period:
            total -= values[index - period]
        if index >= period - 1:
            out[index] = total / period
    return out


def atr14(rows: list[dict]) -> float:
    if len(rows) < 15:
        raise StoryUnavailable(f"แท่งมีแค่ {len(rows)} ตัว ไม่พอคำนวณ ATR14")
    ranges = []
    for prev, cur in zip(rows[-15:-1], rows[-14:]):
        ranges.append(max(cur["high"] - cur["low"],
                          abs(cur["high"] - prev["close"]),
                          abs(cur["low"] - prev["close"])))
    return sum(ranges) / len(ranges)


def swing_points(rows: list[dict], window: int) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """คืน (swing_highs, swing_lows) เป็น (index, ราคา) เทียบกับ rows ที่ส่งเข้า"""
    highs, lows = [], []
    for index in range(window, len(rows) - window):
        segment = rows[index - window:index + window + 1]
        if rows[index]["high"] == max(r["high"] for r in segment):
            highs.append((index, rows[index]["high"]))
        if rows[index]["low"] == min(r["low"] for r in segment):
            lows.append((index, rows[index]["low"]))
    return highs, lows


def cluster_levels(points: list[tuple[int, float]], tolerance: float) -> list[dict]:
    """รวมระดับที่ห่างกันไม่เกิน tolerance — คืน mean/touches/last_index ต่อกลุ่ม"""
    clusters: list[dict] = []
    for index, value in sorted(points, key=lambda p: p[1]):
        if clusters and abs(value - clusters[-1]["values"][-1]) <= tolerance:
            clusters[-1]["values"].append(value)
            clusters[-1]["last_index"] = max(clusters[-1]["last_index"], index)
        else:
            clusters.append({"values": [value], "last_index": index})
    for cluster in clusters:
        cluster["mean"] = sum(cluster["values"]) / len(cluster["values"])
        cluster["touches"] = len(cluster["values"])
        del cluster["values"]
    return clusters


def fit_line(points: list[tuple[int, float]]) -> tuple[float, float]:
    """least squares — คืน (slope, intercept)"""
    n = len(points)
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sxx = sum(p[0] * p[0] for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    denominator = n * sxx - sx * sx
    slope = (n * sxy - sx * sy) / denominator if denominator else 0.0
    return slope, (sy - slope * sx) / n


def second_rank_offset(residuals: list[float], *, downtrend: bool) -> float:
    """ระยะเส้นขนาน — ใช้จุดไกล "อันดับสอง" เพื่อไม่ให้หนามแหลมครั้งเดียวกำหนดกรอบ"""
    ordered = sorted(residuals)
    if downtrend:
        return ordered[1] if len(ordered) >= 2 else ordered[0]
    return ordered[-2] if len(ordered) >= 2 else ordered[-1]


def build_channel(view: list[dict], regime_down: bool, *,
                  swing_window: int = SWING_WINDOW) -> dict | None:
    """กรอบแนวโน้มจากจุดสุดขั้วล่าสุด — ไม่มี swing พอ = ไม่วาด (ไม่เดา)

    จุดสุดขั้ว (ยอด/ก้น) ไม่ถูกใช้ fit เพราะมักเป็น wick แหลมที่ลากความชันทั้งเส้น
    ให้ผิดรูป — เกิดจริงกับ wick ทอง 5,600 ตอนพัฒนาต้นแบบ 2026-08-06
    """
    if regime_down:
        anchor = max(range(len(view)), key=lambda i: view[i]["high"])
    else:
        anchor = min(range(len(view)), key=lambda i: view[i]["low"])
    tail = view[anchor:]
    if len(tail) < swing_window * 4:
        return None
    highs, lows = swing_points(tail, swing_window)
    primary = highs if regime_down else lows
    opposite = lows if regime_down else highs
    if len(primary) < 2 or not opposite:
        return None
    slope, intercept = fit_line(primary)
    if regime_down:
        intercept += max(p[1] - (slope * p[0] + intercept) for p in primary)
    else:
        intercept += min(p[1] - (slope * p[0] + intercept) for p in primary)
    offset = second_rank_offset(
        [p[1] - (slope * p[0] + intercept) for p in opposite], downtrend=regime_down)
    last = len(tail) - 1
    main_at_last = slope * last + intercept
    return {
        "start": anchor,
        "start_date": view[anchor]["date"],
        "slope": slope,
        "intercept": intercept,
        "offset": offset,
        "touch_count": len(primary) + len(opposite),
        "main_at_last": main_at_last,
        "parallel_at_last": main_at_last + offset,
        # ฝั่งแนวโน้มคือเส้นหลัก: ขาลง = ขอบบน · ขาขึ้น = ขอบล่าง
        "main_is_upper": regime_down,
    }


def ribbon_direction(sma50_all: list[float | None], index: int,
                     *, slope_bars: int = RIBBON_SLOPE_BARS) -> bool | None:
    """ทิศของ ribbon ณ แท่ง index (เทียบ sma ทั้งชุด) — True=ขึ้น · None=ข้อมูลไม่พอ"""
    if index < slope_bars:
        return None
    now, past = sma50_all[index], sma50_all[index - slope_bars]
    if now is None or past is None:
        return None
    return now >= past


def build_story(rows: list[dict], *, asset: str,
                display_bars: int = DISPLAY_BARS,
                zoom_bars: int = ZOOM_BARS) -> dict:
    """artifact กลางของสไตล์ D — ตัววาดและนักเขียนอ่านจากก้อนนี้ก้อนเดียว"""
    profile = wcb_source.profile_for(asset)
    if len(rows) < 200 + RIBBON_SLOPE_BARS:
        raise StoryUnavailable(
            f"{asset}: มีแท่ง {len(rows)} ตัว ไม่พอคำนวณ SMA200 กับโหมดตลาด")

    closes = [row["close"] for row in rows]
    sma50_all = sma(closes, 50)
    sma200_all = sma(closes, 200)
    view = rows[-display_bars:]
    offset = len(rows) - len(view)
    atr = atr14(rows)
    current = view[-1]

    direction = ribbon_direction(sma50_all, len(rows) - 1)
    if direction is None:
        raise StoryUnavailable(f"{asset}: SMA50 ยังคำนวณไม่ได้ที่แท่งล่าสุด")
    regime_down = not direction

    # วันที่โหมดพลิกมาเป็นทิศปัจจุบัน — ไล่ถอยหลังหาแท่งแรกของ run ปัจจุบัน
    flip_index = None
    for index in range(len(rows) - 1, offset - 1, -1):
        past_direction = ribbon_direction(sma50_all, index)
        if past_direction is None or past_direction != direction:
            flip_index = index + 1
            break
    flip_date = rows[flip_index]["date"] if flip_index is not None and flip_index < len(rows) else None

    highs, lows = swing_points(view, SWING_WINDOW)
    tolerance = 0.9 * atr

    resistance = [c for c in cluster_levels(highs, tolerance)
                  if c["touches"] >= CLUSTER_TOUCHES_MIN and c["mean"] > current["close"]]
    major_highs, _ = swing_points(view, MAJOR_WINDOW)
    for index, value in major_highs:
        if value > current["close"] and all(abs(value - c["mean"]) > tolerance for c in resistance):
            resistance.append({"mean": value, "touches": 1, "last_index": index})
    resistance = sorted(resistance, key=lambda c: (-c["touches"], -c["mean"]))[:MAX_RESISTANCE_LINES]
    for cluster in resistance:
        cluster["last_date"] = view[cluster["last_index"]]["date"]

    week52_low = min(row["low"] for row in rows[-WEEK52_SESSIONS:])
    zone_half = ZONE_HALF_ATR * atr
    zones = [c for c in cluster_levels(lows, tolerance)
             if c["touches"] >= CLUSTER_TOUCHES_MIN and c["mean"] < current["close"]]
    zones = sorted(zones, key=lambda c: c["mean"], reverse=True)[:MAX_DEMAND_ZONES]
    for rank, zone in enumerate(zones, start=1):
        zone["rank"] = rank
        zone["low"] = zone["mean"] - zone_half
        zone["high"] = zone["mean"] + zone_half
        zone["last_date"] = view[zone["last_index"]]["date"]
        zone["includes_week52_low"] = abs(week52_low - zone["mean"]) <= 1.2 * atr

    peak_index = max(range(len(view)), key=lambda i: view[i]["high"])
    trough_index = min(range(len(view)), key=lambda i: view[i]["low"])
    channel = build_channel(view, regime_down)

    return {
        "schema": SCHEMA,
        "asset": asset,
        "symbol": profile["symbol"],
        "display": {
            "bars": len(view),
            "zoom_bars": min(zoom_bars, len(view)),
            "start_date": view[0]["date"],
            "end_date": view[-1]["date"],
        },
        "current": {"date": current["date"], "close": current["close"]},
        # ค่าเส้นค่าเฉลี่ยล่าสุด — ให้บทพูดถึง "แนวต้าน/แนวรับพลวัต" ด้วยตัวเลขจริงได้
        "sma50_last": sma50_all[-1],
        "sma200_last": sma200_all[-1],
        "atr14": atr,
        "regime": {
            "down": regime_down,
            "rule": f"ความชัน SMA50 เทียบ {RIBBON_SLOPE_BARS} แท่งก่อนหน้า",
            "flip_date": flip_date,
        },
        "peak": {"date": view[peak_index]["date"], "high": view[peak_index]["high"]},
        "trough": {"date": view[trough_index]["date"], "low": view[trough_index]["low"]},
        "resistance": resistance,
        "zones": zones,
        "week52_low": week52_low,
        "channel": channel,
        "scenarios": _scenarios(current["close"], resistance, zones, week52_low, atr),
        "entries": _entries(zones),
    }


def _entries(zones: list[dict]) -> list[dict]:
    """จุดเข้าซื้อที่ได้เปรียบ (SMC POI) — ผู้ใช้สั่ง 2026-08-06 ให้แนะนำเป็นราคา

    ราคาเข้า = กลางโซนรับ (จุดที่ราคาเคยเด้งจริง) · จุดยกเลิก = ขอบล่างโซน
    ไม่มีโซนผ่านเกณฑ์ = ไม่มีจุดเข้า — ห้ามสร้างราคาแนะนำจากความรู้สึกแทน
    """
    return [{
        "rank": zone["rank"],
        "price": zone["mean"],
        "zone_low": zone["low"],
        "zone_high": zone["high"],
        "invalidation": zone["low"],
        "touches": zone["touches"],
    } for zone in zones]


def _scenarios(current: float, resistance: list[dict], zones: list[dict],
               week52_low: float, atr: float) -> dict:
    """ฉากทัศน์สองทางจากระดับที่คำนวณแล้วเท่านั้น — ไม่มีระดับ = ไม่มีฉากทัศน์ฝั่งนั้น"""
    up = None
    above = sorted(c["mean"] for c in resistance)
    if above:
        up = {
            "trigger": above[0],
            "targets": above[1:3],
            "condition": "ราคาปิดวัน (D1) เหนือแนวต้านแรก",
            "invalidation": "ปิดกลับต่ำกว่าแนวต้านแรกหลังทะลุ",
        }
    down = None
    if zones:
        first = zones[0]
        targets = [zone["mean"] for zone in zones[1:]]
        if all(abs(week52_low - t) > atr for t in targets) and week52_low < first["low"]:
            targets.append(week52_low)
        down = {
            "trigger": first["low"],
            "targets": targets,
            "condition": "ราคาปิดวัน (D1) ต่ำกว่าขอบล่างโซนรับ 1",
            "invalidation": "ปิดกลับเข้าโซนรับ 1 ได้อีกครั้ง",
        }
    return {"up": up, "down": down}
