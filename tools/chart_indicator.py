"""เครื่องอ่านอินดิเคเตอร์ของสไตล์ E — RSI/MACD/Fibonacci คำนวณจากแท่ง H1 เท่านั้น

ต้นแบบที่หัวหน้าเลือก (th.tradingview.com/chart/XAUUSD/vxcu4F8w): แผนเทรดที่วาง
Fibonacci Retracement บนกราฟจริง ป้ายทุกเส้นเป็น "อัตราส่วน (ราคา)" มีแผง MACD
ด้านล่าง และท้ายบทเป็น Trading Scenario สองฝั่งพร้อม Entry/SL/TP/RR

หลักเดียวกับสไตล์ D (chart_story):
- โค้ดคำนวณทุกระดับ · ไม่มีชั้นไหนสร้างราคาใหม่ขึ้นเอง
- บทความและภาพอ่านจาก artifact เดียวกัน (`build_indicators`)
- swing ที่เล็กกว่า 2×ATR ไม่วาง Fibonacci — สัญญาณรบกวนห้ามกลายเป็นระดับ
- ฉากทัศน์เป็น "เงื่อนไข ไม่ใช่คำทำนาย" และชี้กลับระดับที่คำนวณได้เสมอ

สไตล์ E แยกขาดจาก A/B/C และ D — ทะเบียน `WCB_WRITERS` ต้องไม่รู้จักสไตล์นี้
"""

from __future__ import annotations

import sys
import math
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import candle_close, chart_story, intraday_bars, wcb_source  # noqa: E402

SCHEMA = "chart-indicator-v1"

TIMEFRAME = "1h"
PANEL_BARS = 120            # ภาพเดียวสามแผง — ลดความแน่นให้แท่ง H1 และ RSI/MACD อ่านง่ายขึ้น
# 🐞 **E-4 (ฟีดแบ็กหัวหน้า 2026-08-07):** เดิม FIB_BARS=120 แคบกว่า PANEL_BARS=160
# ที่ใช้วาดภาพจริง ⇒ จุดสูงสุดตัวจริงอาจอยู่ในช่วง 121–160 (มองเห็นบนภาพ) แต่ตัวหา
# swing ไม่เห็นเพราะค้นแค่ 120 แท่งหลังสุด — เกิดจริง: D บอกจุดสูงสุด 5,597.23 (29 ม.ค.)
# แต่ E ลาก Fib จาก 5,417.76 (2 มี.ค.) ทั้งที่แท่งปลาย ม.ค. สูงกว่าเห็นชัดอยู่ในภาพเดียวกัน
# แก้ที่ราก: ให้หน้าต่างหา swing เท่ากับหน้าต่างที่วาดภาพเป๊ะ แม้ปรับจำนวนแท่งในภายหลัง
FIB_BARS = PANEL_BARS
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
RSI_OVERBOUGHT, RSI_OVERSOLD = 70.0, 30.0
RSI_SLOPE_BARS = 5          # ระยะวัดทิศของ RSI เอง (แนวเดียวกับ ribbon ของ D)
# 🐞 **B-3.2 (ทีมเว็บ 2026-08-09):** ภาพของสไตล์ E วาดเส้น 0.705 และ 0.886 ที่บท
# ไม่ได้พูดถึงเลย — ขัดกติกาเดิมของระบบ (ขีดเฉพาะระดับที่พูดถึงจริงในบท ไม่ใช่ยัดทุกค่า
# ที่มี · กราฟรกแล้วอ่านไม่รู้เรื่อง) และเป็นอาการเดียวกับ "เส้นกำพร้า" ที่หัวหน้าเคยติ
# สไตล์ D จนต้องลด MAX_RESISTANCE_LINES จาก 6 เหลือ 3
# ⇒ **แก้ที่ราก:** ตัดสองอัตราส่วนนั้นออกจากชุดข้อมูลเลย ไม่ใช่ไปกรองตอนวาด — ตัววาด
#   กับตัวเขียนอ่านจาก artifact ก้อนเดียวกัน ชุดนี้จึงเป็น "ทะเบียนเส้นที่บทต้องพูดถึง"
#   และมีด่าน `fib_level_not_in_article` คอยยันไว้ว่าทุกเส้นในชุดนี้ต้องโผล่ในบทจริง
FIB_RATIOS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)
GOLDEN_LOW_RATIO, GOLDEN_HIGH_RATIO = 0.618, 0.786   # OTE ตามต้นแบบ
EXTENSION_RATIO = 1.272     # ป้ายตามธรรมเนียมเทรดเดอร์ — สูตรใช้ level(-(1.272-1))
SL_BUFFER_ATR = 0.5         # ระยะเผื่อ SL เลยจุดตั้งต้น swing (Buffer ตามต้นแบบ)
MIN_SWING_ATR = 2.0         # swing ต้องกว้างอย่างน้อยกี่ ATR จึงคู่ควรกับ Fibonacci
MIN_TAIL_BARS = 8           # จุดตั้งต้น swing ต้องไม่ชิดขอบขวาจนไม่มีขาอีกฝั่ง


class IndicatorUnavailable(RuntimeError):
    """ข้อมูลไม่พอคำนวณอินดิเคเตอร์ — หยุดสายสไตล์ E ห้ามเดาต่อ"""


# ---------------------------------------------------------------- อินดิเคเตอร์

def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    out[period - 1] = sum(values[:period]) / period
    k = 2.0 / (period + 1)
    for index in range(period, len(values)):
        out[index] = values[index] * k + out[index - 1] * (1 - k)
    return out


def rsi(closes: list[float], period: int = RSI_PERIOD) -> list[float | None]:
    """RSI แบบ Wilder — seed ด้วยค่าเฉลี่ยธรรมดาแล้ว smooth ต่อ"""
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = losses = 0.0
    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    average_gain, average_loss = gains / period, losses / period

    def to_rsi(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + gain / loss)

    out[period] = to_rsi(average_gain, average_loss)
    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        average_gain = (average_gain * (period - 1) + max(change, 0.0)) / period
        average_loss = (average_loss * (period - 1) + max(-change, 0.0)) / period
        out[index] = to_rsi(average_gain, average_loss)
    return out


def macd(closes: list[float]) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """คืน (เส้น MACD, เส้น Signal, Histogram) ยาวเท่า closes เสมอ"""
    fast = ema(closes, MACD_FAST)
    slow = ema(closes, MACD_SLOW)
    line = [None if f is None or s is None else f - s for f, s in zip(fast, slow)]
    valid = [value for value in line if value is not None]
    signal_tail = ema(valid, MACD_SIGNAL)
    signal = [None] * (len(line) - len(valid)) + signal_tail
    histogram = [None if l is None or s is None else l - s for l, s in zip(line, signal)]
    return line, signal, histogram


# ---------------------------------------------------------------- Fibonacci

def fib_level(fib: dict, ratio: float) -> float:
    """ราคา ณ อัตราส่วน — ธรรมเนียมป้ายตามต้นแบบ: 0 = ปลาย swing ล่าสุด · 1 = จุดตั้งต้น"""
    span = fib["swing_high"]["price"] - fib["swing_low"]["price"]
    if fib["direction"] == "down":
        return fib["swing_low"]["price"] + ratio * span
    return fib["swing_high"]["price"] - ratio * span


def build_fib(view: list[dict], regime_down: bool, atr: float) -> dict | None:
    """เลือก swing ล่าสุดที่มีนัย แล้ววางชุดระดับ — ไม่มี swing ผ่านเกณฑ์ = ไม่วาง (ไม่เดา)"""
    n = len(view)
    if regime_down:
        anchor = max(range(n), key=lambda i: view[i]["high"])
        if anchor > n - MIN_TAIL_BARS:
            return None
        tail = min(range(anchor, n), key=lambda i: view[i]["low"])
        swing_high = {"date": view[anchor]["date"], "price": view[anchor]["high"]}
        swing_low = {"date": view[tail]["date"], "price": view[tail]["low"]}
    else:
        anchor = min(range(n), key=lambda i: view[i]["low"])
        if anchor > n - MIN_TAIL_BARS:
            return None
        tail = max(range(anchor, n), key=lambda i: view[i]["high"])
        swing_low = {"date": view[anchor]["date"], "price": view[anchor]["low"]}
        swing_high = {"date": view[tail]["date"], "price": view[tail]["high"]}
    if view[anchor].get("at"):
        (swing_high if regime_down else swing_low)["at"] = view[anchor]["at"]
    if view[tail].get("at"):
        (swing_low if regime_down else swing_high)["at"] = view[tail]["at"]
    span = swing_high["price"] - swing_low["price"]
    if span < MIN_SWING_ATR * atr:
        return None
    fib = {
        "direction": "down" if regime_down else "up",
        "swing_high": swing_high,
        "swing_low": swing_low,
        "span": span,
    }
    fib["levels"] = [{"ratio": ratio, "price": fib_level(fib, ratio)} for ratio in FIB_RATIOS]
    fib["golden"] = sorted([fib_level(fib, GOLDEN_LOW_RATIO), fib_level(fib, GOLDEN_HIGH_RATIO)])
    # เป้าขยายฝั่งต่อเนื่องของ swing — เลย 0 ออกไปอีก 0.272 ของช่วง (เรียก 1.272 ตามธรรมเนียม)
    fib["extension"] = fib_level(fib, -(EXTENSION_RATIO - 1.0))
    return fib


# ---------------------------------------------------------------- ฉากทัศน์

# ป้ายอัตราส่วน Fibonacci ที่ผูกกับแต่ละราคาในฉากทัศน์ — โครงสร้างระดับ (ไม่ใช่ตัวราคา)
# เหมือนกันทุกทิศเทรนด์ เห็นได้จาก _scenarios() ด้านล่าง: primary ใช้ entry ที่ Golden
# Zone (0.618–0.786) เสมอ tps ที่ [0.236, 0, ส่วนขยาย] เสมอ · counter ใช้ entry ที่
# (0–0.236) เสมอ tps ที่ [0.5, 0.618] เสมอ — ผูกไว้ที่นี่ที่เดียวให้ตัวเขียนอ้างได้ตรง ๆ
# แทนที่จะรู้จำนวนวิเศษ (E-3: TP1 ของทั้งสองฉากทัศน์เคยเป็น "4,295.97" ลอย ๆ ไม่มีใครบอกว่า
# มันคือ Fib 0.236 มาจากไหน)
PRIMARY_ENTRY_LABEL = f"Golden Zone ({GOLDEN_LOW_RATIO:g}–{GOLDEN_HIGH_RATIO:g})"
PRIMARY_TP_LABELS = ("0.236", "0", f"{EXTENSION_RATIO:g} (ส่วนขยาย)")
COUNTER_ENTRY_LABEL = f"0–{0.236:g}"
COUNTER_TP_LABELS = ("0.5", f"{GOLDEN_LOW_RATIO:g}")


def _disadvantaged_entry(scenario: dict) -> float:
    """ขอบของโซนเข้าที่เสียเปรียบที่สุดของฝั่งนั้น — ใช้คำนวณ RR แทนกลางโซน

    🐞 **E-2 (ฟีดแบ็กหัวหน้า 2026-08-07):** RR เดิมคำนวณจากกลางโซน แต่โซนเข้ากว้าง
    5% ถ้าเข้าคนละขอบตัวเลขคนละเรื่องเลย — ตัวอย่างจริงที่หัวหน้าวัด: Scenario A (SELL)
    บทบอก RR 1:1.4 แต่เข้าที่ขอบเสียเปรียบได้แค่ 0.93 (ตกเกณฑ์ 1.2) ด่านตรวจ RR วัดจุดเดียว
    (กลางโซน) จึงจับไม่ได้

    กฎ: **SELL** อยากขายแพง ⇒ ขอบเสียเปรียบ = ราคาต่ำกว่า (`entry_low`)
        **BUY**  อยากซื้อถูก ⇒ ขอบเสียเปรียบ = ราคาสูงกว่า (`entry_high`)
    """
    return scenario["entry_low"] if scenario["side"] == "sell" else scenario["entry_high"]


def _scenarios(fib: dict | None, regime_down: bool, atr: float,
              current_price: float | None = None) -> dict:
    """แผนสองฝั่งจากระดับ Fibonacci เท่านั้น — ไม่มี fib = ไม่มีแผน ห้ามตั้งราคาเอง

    ตามเทรนด์ = รอราคาย้อนเข้า Golden Zone (0.618–0.786) · สวนเทรนด์ = เล่นเด้ง
    ที่ปลาย swing — โครงเดียวกับ Scenario A/B ของบทต้นแบบ

    `current_price` ใช้คำนวณสองอย่างที่เพิ่ม 2026-08-07 ตามฟีดแบ็กหัวหน้า:
    - `daily_entry` (E-1) — โซนห่างราคาปัจจุบันเกิน `chart_story.ENTRY_MAX_DISTANCE_ATR`
      เท่าของ ATR ไม่นับเป็นแผนรายวัน กติกาเดียวกับสไตล์ D ที่หัวหน้าสั่งให้บังคับ
      "ทุกสไตล์ ไม่ใช่เฉพาะ D" — ตัวอย่างจริงที่ทำให้ต้องมีกฎนี้: Golden Zone เคยห่างราคา
      14.8–20.6% (13.8–19.2×ATR) แล้วยังถูกเสนอเป็นแผนหลักของบทรายวัน
    - `active` (E-3) — ราคาปัจจุบันอยู่ในโซนเข้าแล้วหรือยัง ป้องกันบทเขียนขัดกับราคาจริง
      (เคยเกิด: บทเขียนว่า "รอราคาย่อกลับลงมา" ทั้งที่ราคาอยู่ในโซนนั้นแล้ว)
    """
    if not fib:
        return {"primary": None, "counter": None}
    level = lambda ratio: fib_level(fib, ratio)  # noqa: E731
    buffer = SL_BUFFER_ATR * atr
    if regime_down:
        primary = {
            "side": "sell",
            "name": "SELL (Follow Trend)",
            "entry_low": level(GOLDEN_LOW_RATIO), "entry_high": level(GOLDEN_HIGH_RATIO),
            "sl": level(1.0) + buffer,
            "tps": [level(0.236), level(0.0), fib["extension"]],
            "entry_label": PRIMARY_ENTRY_LABEL, "tp_labels": PRIMARY_TP_LABELS,
            "condition": "รอราคาดีดกลับขึ้นเข้าโซน Golden Zone (0.618–0.786) โดยไม่ปิดแท่ง H1 เหนือจุดเริ่มต้นของคลื่น",
        }
        counter = {
            "side": "buy",
            "name": "BUY (Counter Trend)",
            "entry_low": level(0.0), "entry_high": level(0.236),
            "sl": level(0.0) - buffer,
            "tps": [level(0.5), level(GOLDEN_LOW_RATIO)],
            "entry_label": COUNTER_ENTRY_LABEL, "tp_labels": COUNTER_TP_LABELS,
            "condition": "รอราคาย่อกลับลงมาบริเวณปลาย swing เดิมแล้วมีแรงรับชัดเจน",
        }
    else:
        primary = {
            "side": "buy",
            "name": "BUY (Follow Trend)",
            "entry_low": level(GOLDEN_HIGH_RATIO), "entry_high": level(GOLDEN_LOW_RATIO),
            "sl": level(1.0) - buffer,
            "tps": [level(0.236), level(0.0), fib["extension"]],
            "entry_label": PRIMARY_ENTRY_LABEL, "tp_labels": PRIMARY_TP_LABELS,
            "condition": "รอราคาย่อลงเข้าโซน Golden Zone (0.618–0.786) โดยไม่ปิดแท่ง H1 ต่ำกว่าจุดเริ่มต้นของคลื่น",
        }
        counter = {
            "side": "sell",
            "name": "SELL (Counter Trend)",
            "entry_low": level(0.236), "entry_high": level(0.0),
            "sl": level(0.0) + buffer,
            "tps": [level(0.5), level(GOLDEN_LOW_RATIO)],
            "entry_label": COUNTER_ENTRY_LABEL, "tp_labels": COUNTER_TP_LABELS,
            "condition": "รอราคาดันขึ้นไปบริเวณปลาย swing เดิมแล้วถูกปฏิเสธชัดเจน",
        }
    for scenario in (primary, counter):
        # 🐞 **B-1 (ทีมเว็บ 2026-08-09):** SL เดิมวางเลยจุดตั้งต้น swing ด้วยระยะเผื่อ
        # 0.5×ATR เท่านั้น ⇒ ฝั่งสวนเทรนด์ (counter) ได้ SL ห่างขอบโซนเข้าแค่ 0.5×ATR
        # ซึ่งต่ำกว่าเกณฑ์ 1×ATR ที่ใช้กับสไตล์ D — เกณฑ์เดียวต้องบังคับทุกสไตล์ทุกคู่
        # ไม่ใช่เฉพาะคู่ที่เคยถูกฟ้อง · `safe_invalidation` ไม่ดึง SL ที่ห่างพออยู่แล้ว
        # ให้แคบลง จึงไม่กระทบฉากทัศน์ตามเทรนด์ที่ SL อยู่เลย swing ไปไกลกว่านั้น
        zone_low = min(scenario["entry_low"], scenario["entry_high"])
        zone_high = max(scenario["entry_low"], scenario["entry_high"])
        scenario["sl"] = chart_story.safe_invalidation(
            zone_low, zone_high, scenario["sl"], atr,
            below=scenario["side"] == "buy")
        scenario["entry_mid"] = (scenario["entry_low"] + scenario["entry_high"]) / 2
        disadvantaged = _disadvantaged_entry(scenario)
        scenario["disadvantaged_entry"] = disadvantaged
        # Canonical closed-bar trigger for the public TPR adapter.  The level
        # is already an entry-zone edge from the Fibonacci snapshot; exposing
        # it here prevents downstream code from inventing a trigger or
        # silently switching to the counter scenario.
        scenario["trigger"] = (max(scenario["entry_low"], scenario["entry_high"])
                                if scenario["side"] == "buy" else
                                min(scenario["entry_low"], scenario["entry_high"]))
        scenario["trigger_condition"] = (
            "closed H1 above entry-zone high after confirmation"
            if scenario["side"] == "buy" else
            "closed H1 below entry-zone low after confirmation")
        risk = abs(scenario["sl"] - disadvantaged)
        scenario["rr1"] = (abs(scenario["tps"][0] - disadvantaged) / risk
                           if risk > 0 else None)
        if current_price is not None:
            scenario["daily_entry"] = chart_story.within_daily_entry_range(
                current_price, scenario["entry_mid"], atr)
            zone_low = min(scenario["entry_low"], scenario["entry_high"])
            zone_high = max(scenario["entry_low"], scenario["entry_high"])
            scenario["active"] = zone_low <= current_price <= zone_high
        else:
            scenario["daily_entry"] = True
            scenario["active"] = False
    return {"primary": primary, "counter": counter}


def public_scenario(story: dict) -> dict | None:
    """คืนฉากทัศน์ที่สายผลิตเลือกแสดงต่อสาธารณะ โดยไม่แก้หลักฐานดิบใน scenarios."""
    scenarios = story.get("scenarios") or {}
    key = story.get("public_plan_key", "primary")
    value = scenarios.get(key)
    if isinstance(value, dict):
        return value
    value = scenarios.get("primary")
    return value if isinstance(value, dict) else None


def contingency_scenario(story: dict) -> dict:
    """สร้างแผน E สำรองจากแท่ง H1 ปิดล่าสุดและ ATR เท่านั้นเมื่อ Fib ใช้ไม่ได้/ไกลเกินไป.

    ระดับนี้เป็น breakout buffer ของราคาปิดจริง ไม่ใช่การเดาราคาใหม่จากภายนอก
    และมีไว้ให้บทประจำวันที่ข้อมูลอินดิเคเตอร์ครบยังคงมีแผนที่ตรวจสอบได้.
    """
    current = float(story["current"]["close"])
    atr = float(story["atr14"])
    if not math.isfinite(current) or not math.isfinite(atr) or atr <= 0:
        raise IndicatorUnavailable("E contingency ใช้ current close/ATR ไม่ได้")
    decimals = int(wcb_source.profile_for(story["asset"])["decimals"])
    side = "sell" if (story.get("regime") or {}).get("down") else "buy"
    q = lambda value: round(float(value), decimals)  # noqa: E731
    if side == "buy":
        trigger = q(current + 0.10 * atr)
        entry_low, entry_high = trigger, q(trigger + 0.25 * atr)
        sl = q(trigger - 1.10 * atr)
        tps = [q(entry_high + 1.50 * atr), q(entry_high + 2.50 * atr),
               q(entry_high + 3.50 * atr)]
        condition = "รอแท่ง H1 ปิดเหนือราคาปิดล่าสุดบวก Buffer ATR แล้วรอ retest"
    else:
        trigger = q(current - 0.10 * atr)
        entry_low, entry_high = q(trigger - 0.25 * atr), trigger
        sl = q(trigger + 1.10 * atr)
        tps = [q(entry_low - 1.50 * atr), q(entry_low - 2.50 * atr),
               q(entry_low - 3.50 * atr)]
        condition = "รอแท่ง H1 ปิดต่ำกว่าราคาปิดล่าสุดลบ Buffer ATR แล้วรอ retest"
    return {
        "side": side, "name": f"{side.upper()} (ATR Close Contingency)",
        "entry_low": entry_low, "entry_high": entry_high, "entry_mid": (entry_low + entry_high) / 2,
        "sl": sl, "tps": tps, "trigger": trigger,
        "trigger_condition": "closed H1 strict cross from latest closed close",
        "condition": condition, "daily_entry": True, "active": False,
        "source": "latest closed H1 close + ATR14 contingency",
    }


# ---------------------------------------------------------------- artifact กลาง

def build_indicators(rows: list[dict], *, asset: str, publish_date: str | None = None,
                     panel_bars: int = PANEL_BARS,
                     fib_bars: int = FIB_BARS,
                     candle_basis: dict | None = None,
                     timeframe: str | None = None) -> dict:
    """artifact กลางของสไตล์ E — ตัววาดและนักเขียนอ่านจากก้อนนี้ก้อนเดียว

    สายผลิตจริงส่งแท่ง H1 และใช้ `intraday_bars` พิสูจน์สถานะแท่งก่อนคำนวณทุกค่า
    ส่วนการเดากรอบเวลาจากช่อง `at` มีไว้รองรับชุดทดสอบและ artifact รุ่นเก่าเท่านั้น
    """
    timeframe = timeframe or (TIMEFRAME if rows and rows[-1].get("at") else "1day")
    if candle_basis is None:
        if timeframe == TIMEFRAME:
            rows, candle_basis = intraday_bars.evaluate(rows, asset=asset, timeframe=TIMEFRAME)
        else:
            rows, candle_basis = candle_close.evaluate(rows, asset=asset)
    profile = wcb_source.profile_for(asset)
    if len(rows) < 240:
        raise IndicatorUnavailable(
            f"{asset}: มีแท่ง {len(rows)} ตัว ไม่พอคำนวณอินดิเคเตอร์ครบชุด")

    closes = [row["close"] for row in rows]
    atr = chart_story.atr14(rows)
    current = rows[-1]

    sma50_all = chart_story.sma(closes, 50)
    direction = chart_story.ribbon_direction(sma50_all, len(rows) - 1)
    if direction is None:
        raise IndicatorUnavailable(f"{asset}: SMA50 ยังคำนวณไม่ได้ที่แท่งล่าสุด")
    regime_down = not direction
    flip_index = None
    for index in range(len(rows) - 1, len(rows) - panel_bars - 1, -1):
        past = chart_story.ribbon_direction(sma50_all, index)
        if past is None or past != direction:
            flip_index = index + 1
            break
    flip_date = rows[flip_index]["date"] if flip_index is not None and flip_index < len(rows) else None

    rsi_all = rsi(closes)
    rsi_last = rsi_all[-1]
    rsi_past = rsi_all[-1 - RSI_SLOPE_BARS]
    if rsi_last is None or rsi_past is None:
        raise IndicatorUnavailable(f"{asset}: RSI ยังคำนวณไม่ได้ที่แท่งล่าสุด")
    if rsi_last >= RSI_OVERBOUGHT:
        rsi_zone = "overbought"
    elif rsi_last <= RSI_OVERSOLD:
        rsi_zone = "oversold"
    else:
        rsi_zone = "bullish" if rsi_last >= 50.0 else "bearish"

    macd_line, macd_signal, macd_hist = macd(closes)
    if macd_hist[-1] is None:
        raise IndicatorUnavailable(f"{asset}: MACD ยังคำนวณไม่ได้ที่แท่งล่าสุด")
    cross_date = None
    for index in range(len(rows) - 1, 0, -1):
        now, prev = macd_hist[index], macd_hist[index - 1]
        if now is None or prev is None:
            break
        if (now >= 0) != (prev >= 0):
            cross_date = rows[index]["date"]
            break

    view = rows[-fib_bars:]
    fib = build_fib(view, regime_down, atr)

    return {
        "schema": SCHEMA,
        "asset": asset,
        "symbol": profile["symbol"],
        "timeframe": timeframe,
        "display": {
            "timeframe": timeframe,
            "bars": min(panel_bars, len(rows)),
            "fib_bars": len(view),
            "start_date": rows[-min(panel_bars, len(rows))]["date"],
            "end_date": rows[-1]["date"],
        },
        "current": {"date": current["date"], "close": current["close"],
                    "at": current.get("at"),
                    "candle_state": candle_basis["candle_state"]},
        "candle_basis": candle_basis,
        "atr14": atr,
        "sma50_last": sma50_all[-1],
        # วันเผยแพร่ที่พาดหัวพิมพ์ — คนละเรื่องกับวันแท่งฐาน (มติผู้ใช้ 08-14)
        # ไม่ส่งมา = เท่ากับวันแท่งฐาน เหมือนพฤติกรรมก่อน 08-14
        "publish_date": publish_date,
        "regime": {
            "down": regime_down,
            "rule": f"ความชัน SMA50 เทียบ {chart_story.RIBBON_SLOPE_BARS} แท่งก่อนหน้า",
            "flip_date": flip_date,
        },
        "rsi": {
            "value": rsi_last,
            "rising": rsi_last >= rsi_past,
            "zone": rsi_zone,
        },
        "macd": {
            "line": macd_line[-1],
            "signal": macd_signal[-1],
            "histogram": macd_hist[-1],
            "bullish": macd_hist[-1] >= 0,
            "cross_date": cross_date,
            "histogram_shrinking": (macd_hist[-4] is not None
                                    and abs(macd_hist[-1]) < abs(macd_hist[-4])),
        },
        "fib": fib,
        "scenarios": _scenarios(fib, regime_down, atr, current["close"]),
    }
