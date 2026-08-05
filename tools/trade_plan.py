"""ชั้นแผนการเทรดฝั่ง internal — ประกอบแผนผู้สมัครจากระดับที่อนุมัติแล้วเท่านั้น

มติผู้ใช้ 2026-08-04 ที่ผูกกับโมดูลนี้โดยตรง:

1. **ไฟล์แผนอยู่ฝั่ง internal ทั้งหมด** — ส่วนตัวเลขจุดเข้า จุดตัดขาดทุน เป้าหมาย
   และอัตราส่วน **เล่าในบทความสไตล์ ② ได้แล้ว** (ผู้ใช้ปลดมติข้อ 14ก เมื่อ 2026-08-04)
   ผู้ตัดสินว่าแผนไหนพูดได้คือ `writers.plan_for_public()` ที่เดียว ไม่ใช่โมดูลนี้ —
   โมดูลนี้ยังทำหน้าที่เดิมคือ **เสนอแผน** โดยไม่รู้ว่าปลายทางจะเอาไปเล่าหรือไม่
2. **ระบบมีข้อมูลรายวัน (D1) เท่านั้น** ⇒ `levels.classify_scenario` จะคืน `daily_scenario`
   เสมอ ไม่ใช่ `trade_setup` — แผนที่ได้จึงเป็นเงื่อนไขระดับวัน ("หากปิดใต้ X…")
   ไม่ใช่จุดเข้าแบบ intraday · ห้ามใช้ภาษาชี้จังหวะเข้าตาม `forbidden_language`

โมดูลนี้ **เสนอ** อย่างเดียว ไม่ตัดสินว่าแผนผ่านเกณฑ์ความเสี่ยงหรือไม่ —
การตัดสินอยู่ที่ `tools/risk_auditor.py` ซึ่งเป็นด่านแยกตามหลักผู้ตรวจอิสระ

ทุกตัวเลขในแผนต้องเป็นค่าที่มีอยู่แล้วใน level map หรือ evidence — ห้ามสร้างเลขใหม่
(Contract ข้อ 5: ระดับหรือ Target ที่ถูกสร้างเอง = BLOCK)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import levels as level_engine  # noqa: E402
from tools import risk_thresholds  # noqa: E402
from tools import voice_rules  # noqa: E402


PLAN_VERSION = "1.0.0"

BIAS_UP = "up"
BIAS_DOWN = "down"
BIAS_NEUTRAL = "neutral"

NO_TRADE = "no_trade"

# จำนวนระดับขั้นต่ำที่ต้องมีในทิศที่จะเล่น: 1 จุดเข้า + อย่างน้อย 1 เป้าหมาย
#
# เดิมเป็น 3 เพราะเป้าถูกหยิบแบบตายตัวเป็นสองตัวถัดจากจุดเข้า · ตั้งแต่ 2026-08-05
# เป้าถูก*ค้น*ตามเกณฑ์อัตราส่วนแทน เกณฑ์ 3 จึงกลายเป็นตัวคัดกรองที่ตอบผิดเหตุผล:
# วันที่มีสองระดับแต่ระดับที่สองไกลพอจนอัตราส่วนถึงเกณฑ์ ควรได้แผน ไม่ใช่ถูกตัดทิ้ง
# ⇒ ลดเหลือ 2 แล้วให้ `select_targets()` เป็นคนตอบว่ามีเป้าที่ใช้ได้จริงไหม
MINIMUM_LEVELS_IN_DIRECTION = 2


def _near_edge(zone: dict, reference_price: float) -> float | None:
    """ขอบด้านที่ใกล้ราคาที่สุดของโซน — กติกาเดียวกับ Contract ข้อ 2

    ค่าเดี่ยวคืนค่าตัวเอง · โซนใต้ราคาคืนขอบบน · โซนเหนือราคาคืนขอบล่าง
    """
    if zone.get("value") is not None:
        return float(zone["value"])
    low, high = zone.get("zone_low"), zone.get("zone_high")
    if low is None or high is None:
        return None
    return float(high) if float(high) <= reference_price else float(low)


def _zone_bounds(zone: dict) -> list[float]:
    """ช่วงราคาของโซนสำหรับใช้เป็นเขตเข้า — ค่าเดี่ยวได้ช่วงที่ขอบชนกัน"""
    if zone.get("value") is not None:
        value = float(zone["value"])
        return [value, value]
    return [float(zone["zone_low"]), float(zone["zone_high"])]


def split_sides(zones: list[dict], reference_price: float) -> tuple[list[dict], list[dict]]:
    """แยกโซนที่อนุมัติแล้วเป็นฝั่งแนวรับและแนวต้าน เรียงจากใกล้ราคาไปไกล

    ใช้ `voice_rules.public_level_side` ตัดสินฝั่งเพื่อให้ตรงกับที่บทความและกราฟใช้
    ระดับที่ไม่ผ่าน `approved_for_publication` ถูกตัดทิ้งตั้งแต่ต้น
    """
    supports, resistances = [], []
    for zone in zones:
        if not zone.get("approved_for_publication"):
            continue
        edge = _near_edge(zone, reference_price)
        if edge is None:
            continue
        side = voice_rules.public_level_side(zone, reference_price)
        entry = {**zone, "edge": edge, "distance": abs(edge - reference_price)}
        if side == level_engine.SUPPORT:
            supports.append(entry)
        elif side == level_engine.RESISTANCE:
            resistances.append(entry)
    supports.sort(key=lambda item: item["distance"])
    resistances.sort(key=lambda item: item["distance"])
    return supports, resistances


def select_stop(opposite: list[dict], entry_edge: float, *, atr: float,
                minimum_stop_atr: float) -> dict | None:
    """ระดับฝั่งตรงข้าม **ตัวแรกที่ห่างจากจุดเข้าอย่างน้อยตามเกณฑ์ความผันผวน**

    เดิมโมดูลนี้หยิบ `opposite[0]` เสมอ ซึ่งเป็นต้นเหตุที่วัดเจอเมื่อ 2026-08-05:
    ระยะห่างระหว่างระดับที่อนุมัติบนกรอบรายวันอยู่ราว 0.2 ATR จุดตัดขาดทุนจึงติดอยู่ที่
    0.35–0.40 ATR ทุกวันทั้งสี่สินทรัพย์ — แคบกว่าการแกว่งปกติของวันเดียวเกือบสามเท่า
    ทั้งที่ฝั่งตรงข้ามมีระดับที่อนุมัติเฉลี่ยห้าตัว กระจายไปถึง 2.6–3.9 ATR โดยไม่เคยถูกใช้

    **เลือก "ตัวแรกที่ผ่าน" ไม่ใช่ "ตัวที่ไกลที่สุด"** — ตัวแรกที่ผ่านคือความเสี่ยงน้อย
    ที่สุดที่ยังนับว่าปลอดภัยตามเกณฑ์ ซึ่งให้อัตราส่วนสูงสุดไปพร้อมกัน

    `opposite` เรียงจากใกล้ราคาไปไกลมาแล้ว และจุดเข้าอยู่คนละฝั่งของราคากับระดับ
    เหล่านี้ ระยะจากจุดเข้าจึงเพิ่มตามลำดับเดียวกัน — วนจากต้นแล้วหยุดตัวแรกที่ผ่านได้เลย
    """
    for zone in opposite:
        if abs(float(zone["edge"]) - entry_edge) / atr >= minimum_stop_atr:
            return zone
    return None


def _far_edge(zone: dict, bias: str) -> float | None:
    """ขอบที่ราคาต้อง**ปิดเลยไปจริง ๆ** จึงจะถือว่าเหตุผลของแผนตาย

    ต่างจาก `_near_edge` ที่ใช้กับจุดเข้าและจุดตัดขาดทุน — ตรงนั้นถามว่า "แตะเมื่อไหร่"
    ตรงนี้ถามว่า "พ้นเมื่อไหร่" · แผนขาลงตายเมื่อปิดเหนือขอบบน แผนขาขึ้นตายเมื่อปิดใต้ขอบล่าง
    """
    if zone.get("value") is not None:
        return float(zone["value"])
    low, high = zone.get("zone_low"), zone.get("zone_high")
    if low is None or high is None:
        return None
    return float(high) if bias == BIAS_DOWN else float(low)


def select_invalidation(opposite: list[dict], *, sma20: float | None, bias: str,
                        stop_zone: dict, stop_value: float) -> dict:
    """จุดที่**เหตุผล**ของแผนตาย — คนละเรื่องกับจุดที่ยอมขาดทุน

    ก่อน 2026-08-05 ช่องนี้ถูกตั้งให้เท่ากับ `stop.value` เสมอทุกแผน ⇒ ไม่ให้ข้อมูลอะไรเลย
    เคสที่ทำให้เห็นปัญหา (XAU 2026-07-02): แผนยืนบนเหตุผล "ราคาอยู่ใต้เส้นค่าเฉลี่ยที่เรียงตัวลง"
    ซึ่งตายตั้งแต่ปิดเหนือโซน SMA20 ที่ 4190.89 แต่จุดตัดขาดทุนอยู่ที่ 4266.26
    — มีช่วง 0.67 ATR ที่แผนยังมีชีวิตทั้งที่เหตุผลของมันหายไปแล้ว

    **ทำไมผูกกับ SMA20:** `infer_bias()` ตัดสินทิศจากราคาเทียบ SMA20/SMA50 เท่านั้น
    จุดที่เหตุผลตายจึงต้องเป็นจุดที่ราคากลับข้าม SMA20 ตามนิยาม ไม่ใช่เกณฑ์ที่เราคิดขึ้นใหม่

    ไล่สามชั้น — **ห้ามใช้ค่า SMA20 ดิบเป็นคำตอบ** เพราะถ้าวันนั้นมันไม่ตกในโซนที่อนุมัติ
    ค่าจะไม่ผ่าน RL-001 แล้วแผนทั้งใบพังจากช่องที่เป็นแค่ข้อมูลประกอบ:

    1. `sma20_zone` — โซนที่ครอบ SMA20 (ตรงนิยามที่สุด และเป็นระดับที่อนุมัติแล้วอยู่แล้ว)
    2. `first_level_beyond_sma20` — ระดับที่อนุมัติตัวแรกที่เลย SMA20 ไป (กันวันที่ SMA20 ลอยนอกโซน)
    3. `fallback_stop` — เท่ากับจุดตัดขาดทุนเหมือนเดิม **แต่ต้องบอกว่าเพราะอะไร ไม่ใช่เงียบ**
    """
    if sma20 is not None:
        for zone in opposite:
            low, high = zone.get("zone_low"), zone.get("zone_high")
            if low is not None and high is not None and float(low) <= sma20 <= float(high):
                edge = _far_edge(zone, bias)
                if edge is not None:
                    return {"zone": zone, "value": edge, "source": "sma20_zone"}

        for zone in opposite:
            edge = _far_edge(zone, bias)
            if edge is None:
                continue
            beyond = edge >= sma20 if bias == BIAS_DOWN else edge <= sma20
            if beyond:
                return {"zone": zone, "value": edge,
                        "source": "first_level_beyond_sma20"}

    return {"zone": stop_zone, "value": stop_value, "source": "fallback_stop"}


def select_targets(forward: list[dict], entry_edge: float, risk: float, *,
                   minimum_rr: float, limit: int = 2) -> list[dict]:
    """เป้าหมาย **ตัวแรกที่ทำให้อัตราส่วนถึงเกณฑ์** แล้วต่อด้วยระดับถัดไปตามลำดับ

    เดิมหยิบ `forward[1]` กับ `forward[2]` เสมอ ซึ่งเป็นระดับที่ติดกับจุดเข้าที่สุด
    อัตราส่วนจึงออกมา ~1.0 โดยโครงสร้าง ไม่ว่าตลาดจะเป็นอย่างไร

    **ห้ามเปลี่ยนเป็น "เลือกตัวที่ให้อัตราส่วนสูงสุด"** — เป้าที่ไกลกว่าให้ตัวเลขที่สวยกว่า
    โดยที่โอกาสไปถึงน้อยลง คือการแต่งตัวเลขให้ดูดีซึ่งผู้ใช้ปฏิเสธมาแล้วสองครั้ง
    · จำนวนวันที่ผ่านเกณฑ์เท่ากันเป๊ะทั้งสองแบบอยู่แล้ว (ถ้ามีเป้าที่ผ่าน เป้าตัวแรก
    ที่ผ่านก็ผ่าน) ต่างกันแค่ตัวเลขที่รายงานออกไป
    """
    candidates = forward[1:]
    for index, zone in enumerate(candidates):
        if abs(float(zone["edge"]) - entry_edge) / risk >= minimum_rr:
            return candidates[index:index + limit]
    return []


def infer_bias(report: dict, reference_price: float) -> dict:
    """ทิศของแผนต้องมาจาก regime ที่วัดได้ ไม่ใช่ความเห็น

    เกณฑ์: ราคาปิดล่าสุดเทียบเส้นค่าเฉลี่ย 20 วัน และเส้น 20 เทียบเส้น 50
    เรียงตัวครบทางเดียวกันจึงถือว่ามีทิศ — ไม่ครบ = `neutral` ซึ่งเป็นคำตอบที่ถูกต้อง
    ไม่ใช่ความล้มเหลว · เส้นที่ยังไม่ผ่านขั้นต่ำใน minimum_bars ถือว่าไม่มีข้อมูล
    """
    indicators = report.get("indicators") or {}
    sma20 = indicators.get("sma20") or {}
    sma50 = indicators.get("sma50") or {}
    if not (sma20.get("approved_for_publication") and sma50.get("approved_for_publication")):
        return {"bias": BIAS_NEUTRAL, "reason": "moving_average_unavailable",
                "detail": "เส้นค่าเฉลี่ย 20 หรือ 50 วันยังไม่ผ่านจำนวนแท่งขั้นต่ำ"}
    fast, slow = float(sma20["value"]), float(sma50["value"])
    if reference_price > fast > slow:
        return {"bias": BIAS_UP, "reason": "price_above_rising_stack", "detail": None}
    if reference_price < fast < slow:
        return {"bias": BIAS_DOWN, "reason": "price_below_falling_stack", "detail": None}
    return {"bias": BIAS_NEUTRAL, "reason": "stack_not_aligned",
            "detail": "ราคากับเส้นค่าเฉลี่ยยังไม่เรียงตัวไปทางเดียวกัน"}


def _no_trade_plan(*, reason: str, detail: str, bias: dict, reference_price: float,
                   context: dict) -> dict:
    return {
        "plan_version": PLAN_VERSION,
        "classification": NO_TRADE,
        "executable": False,
        "reason": reason,
        "detail": detail,
        "bias": bias["bias"],
        "bias_reason": bias["reason"],
        "counter_trend_reason": None,
        "reference_price": reference_price,
        "entry": None,
        "stop": None,
        "targets": [],
        "rr": None,
        "invalidation": None,
        "no_trade": [detail],
        "confidence": 1,
        "confidence_basis": ["ไม่มีแผนให้ประเมิน"],
        "evidence_refs": {"reference_price": "level-map.reference_price"},
        "forbidden_language": [],
        **context,
    }


def _confidence(*, rr: float, atr_distance: float | None, target_count: int,
                counter_trend: bool) -> tuple[int, list[str]]:
    """คะแนน 1–10 จากปัจจัยที่นับได้เท่านั้น — เกณฑ์เขียนไว้ให้ตรวจย้อนได้

    ห้ามให้คะแนนจากความรู้สึก · ทุกคะแนนที่บวกต้องมีบรรทัดเหตุผลกำกับใน basis

    **ฐานคะแนนสูงขึ้นตั้งแต่ 2026-08-05 และเป็นผลที่ตั้งใจ** — ข้อ "ระยะจุดตัดขาดทุน
    กว้างกว่าความผันผวนเฉลี่ย" เดิมแทบไม่เคยได้เลย (วัด 221 แผนได้ 3 ครั้ง) เพราะโค้ด
    หยิบระดับใกล้สุดเสมอ · ตอนนี้ `select_stop()` การันตีข้อนี้ทุกแผน ⇒ ทุกแผนได้ +2 เสมอ
    คะแนนจึงยังแยกแผนได้จากอัตราส่วนและจำนวนชั้นเป้าหมาย แต่**เทียบข้ามยุคกันไม่ได้**
    คะแนน 6 ของวันนี้ไม่เท่ากับคะแนน 6 ของเมื่อวาน
    """
    score, basis = 3, ["ฐานเริ่มต้นของแผนที่ประกอบได้ครบ"]
    if rr >= 2.0:
        score += 3
        basis.append("อัตราส่วนผลตอบแทนต่อความเสี่ยงตั้งแต่ 2.0 ขึ้นไป")
    elif rr >= 1.5:
        score += 2
        basis.append("อัตราส่วนผลตอบแทนต่อความเสี่ยงตั้งแต่ 1.5 ขึ้นไป")
    if atr_distance is not None and atr_distance >= 1.0:
        score += 2
        basis.append("ระยะจุดตัดขาดทุนกว้างกว่าความผันผวนเฉลี่ย 14 วัน")
    if target_count >= 2:
        score += 1
        basis.append("มีเป้าหมายรองรับสองชั้น")
    if counter_trend:
        score -= 2
        basis.append("แผนสวนทิศของเส้นค่าเฉลี่ย จึงหักคะแนน")
    return max(1, min(10, score)), basis


def build(*, report: dict, level_map: dict, symbol: str, instrument_type: str,
          cutoff_at: str, batch_id: str, asset: str,
          news: dict | None = None, thresholds: dict | None = None) -> dict:
    """ประกอบแผนผู้สมัครหนึ่งชุดจาก snapshot ที่ล็อกแล้ว

    คืน dict เสมอ — ไม่มีกรณีที่โยน exception เพราะไม่มีจังหวะเทรด
    ไม่มีจังหวะ = `classification: no_trade` พร้อมเหตุผลที่ตรวจย้อนได้

    `thresholds` มีไว้ให้**เทสกับสคริปต์วัดผล**ส่งค่าชุดอื่นเข้ามาได้ ไม่ใช่ให้สายท่อจริงใช้
    — `build_daily_package` ไม่ส่งค่านี้ ค่าจึงมาจาก `config/risk_thresholds.json` เสมอ
    มีไว้เพราะการกวาดค่าเกณฑ์หลายค่าเพื่อหาว่าควรล็อกที่เท่าไหร่ (จุด ✋3) ต้องเปลี่ยนค่า
    ระหว่างรัน ถ้าไม่มีช่องนี้จะต้องไปแก้ไฟล์ config ระหว่างวัด ซึ่งพลาดง่ายกว่ามาก
    """
    reference_price = float(level_map["reference_price"])
    zones = level_map.get("zones") or []
    indicators = report.get("indicators") or {}
    atr_item = indicators.get("atr14") or {}
    atr = float(atr_item["value"]) if atr_item.get("approved_for_publication") else None

    context = {
        "asset": asset,
        "symbol": symbol,
        "instrument_type": instrument_type,
        "cutoff_at": cutoff_at,
        "batch_id": batch_id,
        "timeframe": "D1",
        "news_provider": (news or {}).get("provider_used"),
    }
    bias = infer_bias(report, reference_price)
    supports, resistances = split_sides(zones, reference_price)

    if bias["bias"] == BIAS_NEUTRAL:
        return _no_trade_plan(
            reason="no_directional_bias",
            detail=bias["detail"] or "ยังไม่มีทิศที่วัดได้จากเส้นค่าเฉลี่ย",
            bias=bias, reference_price=reference_price, context=context)

    if atr is None:
        return _no_trade_plan(
            reason="volatility_unavailable",
            detail="ยังไม่มีค่าความผันผวนเฉลี่ย 14 วัน จึงวัดระยะจุดตัดขาดทุนไม่ได้",
            bias=bias, reference_price=reference_price, context=context)

    # ทิศลงเล่นฝั่งแนวรับ (รอหลุด) · ทิศขึ้นเล่นฝั่งแนวต้าน (รอทะลุ)
    forward, opposite = (supports, resistances) if bias["bias"] == BIAS_DOWN \
        else (resistances, supports)

    if len(forward) < MINIMUM_LEVELS_IN_DIRECTION:
        return _no_trade_plan(
            reason="insufficient_levels_in_direction",
            detail=(f"ทิศที่จะเล่นมีระดับที่อนุมัติแล้วเพียง {len(forward)} ระดับ "
                    f"ต้องการอย่างน้อย {MINIMUM_LEVELS_IN_DIRECTION}"),
            bias=bias, reference_price=reference_price, context=context)
    if not opposite:
        return _no_trade_plan(
            reason="no_level_for_stop",
            detail="ไม่มีระดับฝั่งตรงข้ามให้วางจุดตัดขาดทุน",
            bias=bias, reference_price=reference_price, context=context)

    thresholds = thresholds or risk_thresholds.load()
    entry_zone = forward[0]
    entry_edge = entry_zone["edge"]

    stop_zone = select_stop(opposite, entry_edge, atr=atr,
                            minimum_stop_atr=thresholds["minimum_stop_atr"])
    if stop_zone is None:
        return _no_trade_plan(
            reason="no_stop_meets_volatility",
            detail=(f"ไม่มีระดับฝั่งตรงข้ามที่ห่างจากจุดเข้าถึง "
                    f"{thresholds['minimum_stop_atr']:.1f} เท่าของความผันผวนเฉลี่ย 14 วัน "
                    f"— วางจุดตัดขาดทุนแล้วจะแคบกว่าการแกว่งปกติของวันเดียว"),
            bias=bias, reference_price=reference_price, context=context)

    stop_value = stop_zone["edge"]
    risk = abs(stop_value - entry_edge)
    if risk == 0:
        return _no_trade_plan(
            reason="zero_risk_distance",
            detail="จุดเข้ากับจุดตัดขาดทุนอยู่ระดับเดียวกันหลังยุบโซน",
            bias=bias, reference_price=reference_price, context=context)

    chosen = select_targets(forward, entry_edge, risk,
                            minimum_rr=thresholds["minimum_rr"])
    if not chosen:
        return _no_trade_plan(
            reason="no_target_meets_ratio",
            detail=(f"ไม่มีระดับในทิศที่เล่นที่ทำให้ผลตอบแทนต่อความเสี่ยงถึง "
                    f"{thresholds['minimum_rr']:.1f} เท่า เมื่อวัดจากจุดตัดขาดทุนที่เลือกไว้"),
            bias=bias, reference_price=reference_price, context=context)

    targets = []
    for zone in chosen:
        reward = abs(zone["edge"] - entry_edge)
        targets.append({
            "value": zone["edge"],
            "matched_level": zone["id"],
            "label": zone["label"],
            "rr": reward / risk,
        })

    direction_word = "ใต้" if bias["bias"] == BIAS_DOWN else "เหนือ"
    invalidation_word = "เหนือ" if bias["bias"] == BIAS_DOWN else "ใต้"
    sma20_item = indicators.get("sma20") or {}
    sma20 = (float(sma20_item["value"])
             if sma20_item.get("approved_for_publication") else None)
    invalidation = select_invalidation(
        opposite, sma20=sma20, bias=bias["bias"],
        stop_zone=stop_zone, stop_value=stop_value)
    invalidation["beyond_stop"] = (
        invalidation["value"] > stop_value if bias["bias"] == BIAS_DOWN
        else invalidation["value"] < stop_value)
    scenario = level_engine.classify_scenario(
        target=targets[0]["value"], invalidation=invalidation["value"],
        levels=zones, has_h4=False, has_intraday=False,
    )
    atr_distance = risk / atr
    counter_trend = False  # ทิศแผนมาจาก regime โดยตรง จึงไม่มีกรณีสวนในรุ่นนี้
    confidence, basis = _confidence(
        rr=targets[0]["rr"], atr_distance=atr_distance,
        target_count=len(targets), counter_trend=counter_trend)

    return {
        "plan_version": PLAN_VERSION,
        "classification": scenario["classification"],
        "executable": scenario["executable"],
        "reason": scenario["reason"],
        "detail": None,
        "bias": bias["bias"],
        "bias_reason": bias["reason"],
        "counter_trend_reason": None,
        "reference_price": reference_price,
        "entry": {
            "zone": _zone_bounds(entry_zone),
            "edge": entry_edge,
            "matched_level": entry_zone["id"],
            "label": entry_zone["label"],
            "condition": f"หากแท่งรายวันปิด{direction_word}ระดับนี้",
        },
        "stop": {
            "value": stop_value,
            "matched_level": stop_zone["id"],
            "label": stop_zone["label"],
            "atr_distance": atr_distance,
        },
        "targets": targets,
        "rr": targets[0]["rr"],
        "invalidation": {
            "value": invalidation["value"],
            "matched_level": invalidation["zone"]["id"],
            "label": invalidation["zone"].get("label"),
            "source": invalidation["source"],
            "beyond_stop": invalidation["beyond_stop"],
            "text": (f"แท่งรายวันปิด{invalidation_word}ระดับจุดตัดขาดทุน"
                     if invalidation["source"] == "fallback_stop"
                     else f"แท่งรายวันปิด{invalidation_word}"
                          f"{invalidation['zone'].get('label') or 'ระดับที่ใช้ตัดสินทิศ'}"),
        },
        "no_trade": [
            "ราคายังไม่ปิดผ่านระดับจุดเข้าตามเงื่อนไข",
            "แท่งล่าสุดยังไม่ปิดรอบ",
        ],
        "confidence": confidence,
        "confidence_basis": basis,
        "evidence_refs": {
            "reference_price": "level-map.reference_price",
            "entry.edge": f"level-map.zones[{entry_zone['id']}]",
            "stop.value": f"level-map.zones[{stop_zone['id']}]",
            "invalidation.value": f"level-map.zones[{invalidation['zone']['id']}]",
            # จำนวนเป้าหมายไม่คงที่แล้ว จึงไล่จากของจริงแทนการเขียนสองบรรทัดตายตัว
            **{f"targets[{index}].value": f"level-map.zones[{target['matched_level']}]"
               for index, target in enumerate(targets)},
            "stop.atr_distance": "technical.evidence.indicators.atr14",
            "bias": "technical.evidence.indicators.sma20 + sma50",
            "rr": "computed",
        },
        "forbidden_language": scenario.get("forbidden_language", []),
        **context,
    }
