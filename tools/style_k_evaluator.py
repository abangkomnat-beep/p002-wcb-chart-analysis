"""ชั้นวัดผลของ Style K — เปิดได้ต่อเมื่อ analysis freeze ผ่านแล้วเท่านั้น

ไฟล์นี้เป็นที่เดียวที่ได้เห็นแท่งหลังวัน D · ตัวเขียนบท ตัววาดภาพ และ Agent ภาษา
ไม่ import ไฟล์นี้เลย ถ้าวันหนึ่งมีใคร import เข้าไป จะเห็นในหัวไฟล์นั้นทันทีว่าผิด

**กฎความซื่อสัตย์ที่โค้ดบังคับ ไม่ใช่แค่เขียนไว้ในเอกสาร:**

1. เงื่อนไขวัดที่ราคาปิดรายวัน เพราะบทเขียนเป็นเงื่อนไข "ปิดเหนือ/ปิดใต้"
2. **แท่งเดียวที่ปิดยืนยันฝั่งหนึ่ง แต่ระหว่างวันเคยแตะระดับที่หักล้างอีกฝั่ง =
   `ambiguous_same_bar`** — เรามีแค่แท่งรายวัน ไม่มีทางรู้ว่าอะไรเกิดก่อน
   การเลือกเชียร์ฝั่งที่ปิดคือการเดาลำดับ ซึ่งห้ามทำ
3. MFE/MAE เริ่มนับจากแท่งที่ trigger เท่านั้น ไม่ trigger คืน `not_applicable`
   ไม่ใช่ 0 — ศูนย์แปลว่า "วัดแล้วได้ศูนย์" ซึ่งคนละความหมายกับ "ไม่มีอะไรให้วัด"
4. XAUUSD กับ BTCUSD ห้ามรวมหน่วยราคาดิบ จึงมีค่า normalize ด้วย ATR ณ วัน D คู่มาเสมอ
"""

from __future__ import annotations

STATUS_CONFIRMED_HELD = "confirmed_then_held"
STATUS_CONFIRMED_INVALIDATED = "confirmed_then_invalidated"
STATUS_INVALIDATED_FIRST = "invalidated_first"
STATUS_UNRESOLVED = "unresolved"
STATUS_AMBIGUOUS = "ambiguous"

NOT_APPLICABLE = "not_applicable"


def _close_beyond(row: dict, rule: dict) -> bool:
    return row["close"] > rule["level"] if rule["comparison"] == "gt" else row["close"] < rule["level"]


def _range_reached(row: dict, rule: dict) -> bool:
    """แท่งนี้เคยแตะระดับตามเงื่อนไขระหว่างวันหรือไม่ (ไม่สนว่าปิดตรงไหน)"""
    return row["high"] >= rule["level"] if rule["comparison"] == "gt" else row["low"] <= rule["level"]


def _excursions(rows: list[dict], *, reference: float, bias: str) -> tuple[float, float]:
    """คืน (MFE, MAE) — ทั้งคู่ไม่ติดลบตามนิยาม

    ค่าติดลบเกิดได้เมื่อราคาไม่เคยเคลื่อนไปฝั่งนั้นเลยหลัง trigger (เช่นฝั่งลงถูก trigger
    แต่ราคาไม่เคยลงต่ำกว่าราคาอ้างอิงเลยสักครั้ง) · ความหมายที่ถูกต้องของกรณีนั้นคือ
    "ระยะที่วิ่งเข้าทาง = 0" ไม่ใช่ระยะติดลบ — ปล่อยค่าติดลบไว้จะอ่านผิดเป็นขาดทุน
    """
    highest = max(row["high"] for row in rows)
    lowest = min(row["low"] for row in rows)
    if bias == "bullish":
        favorable, adverse = highest - reference, reference - lowest
    else:
        favorable, adverse = reference - lowest, highest - reference
    return max(favorable, 0.0), max(adverse, 0.0)


def evaluate_scenario(scenario: dict, rows: list[dict], *, horizon: str,
                      atr14: float | None) -> dict:
    """วัดผลหนึ่ง scenario บนแท่งของ horizon ที่กำหนด — `rows` ต้องเรียงตามเวลา"""
    result = {
        "scenario_id": scenario["scenario_id"],
        "bias": scenario["bias"],
        "horizon": horizon,
        "confirmation_triggered": False,
        "invalidation_triggered": False,
        "first_event": "neither",
        "first_event_date": None,
        "target_reached": "not_defined" if scenario.get("target_zone") is None else "no",
        "mfe": None,
        "mae": None,
        "mfe_atr": None,
        "mae_atr": None,
        "close_direction_match": None,
        "scenario_status": STATUS_UNRESOLVED,
        "bars_evaluated": [row["date"] for row in rows],
        "limitations": [],
    }
    if not rows:
        result["limitations"].append("not_available: ไม่มีแท่งที่ปิดแล้วใน horizon นี้")
        return result

    confirm = scenario["confirmation_rule"]
    invalidate = scenario["invalidation_rule"]
    reference = scenario["evaluation_reference_price"]

    trigger_index = None
    for index, row in enumerate(rows):
        closed_confirm = _close_beyond(row, confirm)
        closed_invalid = _close_beyond(row, invalidate)
        if not (closed_confirm or closed_invalid):
            continue

        other = invalidate if closed_confirm else confirm
        if _range_reached(row, other):
            # ปิดฝั่งหนึ่งแต่ระหว่างวันเคยแตะอีกฝั่ง — ลำดับที่แท้จริงไม่มีทางรู้จากแท่งรายวัน
            result.update({
                "confirmation_triggered": True,
                "invalidation_triggered": True,
                "first_event": "ambiguous_same_bar",
                "first_event_date": row["date"],
                "scenario_status": STATUS_AMBIGUOUS,
            })
            result["limitations"].append(
                f"แท่ง {row['date']} ปิด{'ยืนยัน' if closed_confirm else 'หักล้าง'}ฝั่งหนึ่ง "
                "แต่ช่วงระหว่างวันเคยแตะระดับของอีกฝั่ง — ไม่มีแท่งย่อยบอกลำดับ จึงไม่ตัดสิน"
            )
            trigger_index = index
            break

        if closed_confirm:
            result.update({"confirmation_triggered": True, "first_event": "confirmation",
                           "first_event_date": row["date"]})
            remaining = rows[index + 1:]
            later_invalid = next((item for item in remaining if _close_beyond(item, invalidate)), None)
            result["invalidation_triggered"] = later_invalid is not None
            result["scenario_status"] = (STATUS_CONFIRMED_INVALIDATED if later_invalid
                                         else STATUS_CONFIRMED_HELD)
        else:
            result.update({"invalidation_triggered": True, "first_event": "invalidation",
                           "first_event_date": row["date"],
                           "scenario_status": STATUS_INVALIDATED_FIRST})
        trigger_index = index
        break

    last_close = rows[-1]["close"]
    result["close_direction_match"] = (last_close > reference if scenario["bias"] == "bullish"
                                       else last_close < reference)

    if trigger_index is None:
        result["mfe"] = NOT_APPLICABLE
        result["mae"] = NOT_APPLICABLE
        result["limitations"].append("ไม่มีเงื่อนไขใดถูก trigger จึงไม่มีจุดเริ่มนับ MFE/MAE")
        return result

    mfe, mae = _excursions(rows[trigger_index:], reference=reference, bias=scenario["bias"])
    result["mfe"] = mfe
    result["mae"] = mae
    if atr14:
        result["mfe_atr"] = mfe / atr14
        result["mae_atr"] = mae / atr14
    else:
        result["limitations"].append("ไม่มี ATR ณ วัน D จึง normalize ไม่ได้")

    target = scenario.get("target_zone")
    if target is not None:
        reached = any(row["high"] >= target["price"] if scenario["bias"] == "bullish"
                      else row["low"] <= target["price"] for row in rows[trigger_index:])
        result["target_reached"] = "yes" if reached else "no"
    return result


def evaluate_record(manifest: dict, outcome: dict) -> dict:
    """วัดผลทุก scenario ของ session เดียว ทั้ง H+1 และ H+3"""
    horizons = outcome["horizons"]
    rows_by_date = {row["date"]: row for row in outcome["rows"]}
    atr14 = manifest.get("atr14")

    results: list[dict] = []
    for name, steps in (("H+1", 1), ("H+3", 3)):
        wanted = horizons.get(name) or []
        rows = [rows_by_date[day] for day in wanted if day in rows_by_date]
        available = len(rows) == steps and len(wanted) == steps
        for scenario in manifest["scenarios"]:
            if not available:
                results.append({
                    "scenario_id": scenario["scenario_id"], "bias": scenario["bias"],
                    "horizon": name, "scenario_status": "not_available",
                    "confirmation_triggered": None, "invalidation_triggered": None,
                    "first_event": "not_available", "target_reached": "not_defined",
                    "mfe": None, "mae": None, "mfe_atr": None, "mae_atr": None,
                    "close_direction_match": None, "bars_evaluated": [row["date"] for row in rows],
                    "limitations": [f"not_available: session ร่วมที่ปิดแล้วหลังวัน D "
                                    f"ไม่ครบ {steps} ตัว — ไม่ประมาณค่าแทน"],
                })
                continue
            results.append(evaluate_scenario(scenario, rows, horizon=name, atr14=atr14))

    return {
        "asset": manifest["asset"],
        "session_date": manifest["session_date"],
        "evaluation_reference_price": manifest["evaluation_reference_price"],
        "atr14": atr14,
        "horizons": horizons,
        "no_trade_reason": manifest.get("no_trade_reason"),
        "outcome_source": outcome["source_file"],
        "outcome_source_hash": outcome["source_hash"],
        "results": results,
    }


def evaluation_problems(evaluation: dict) -> list[str]:
    problems: list[str] = []
    horizons = {item["horizon"] for item in evaluation["results"]}
    if evaluation["no_trade_reason"] is None and "H+1" not in horizons:
        problems.append(f"{evaluation['asset']} {evaluation['session_date']}: ไม่มีผล H+1")
    for item in evaluation["results"]:
        if item["scenario_status"] == "not_available":
            continue
        if item["first_event"] == "neither" and item["mfe"] != NOT_APPLICABLE:
            problems.append("ไม่ trigger แต่ MFE ไม่ใช่ not_applicable")
        if item["first_event"] == "ambiguous_same_bar" and \
                item["scenario_status"] != STATUS_AMBIGUOUS:
            problems.append("first_event กำกวมแต่สถานะไม่ใช่ ambiguous")
    return problems
