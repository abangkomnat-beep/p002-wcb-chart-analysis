"""ด่านตรวจความเสี่ยงและตรรกะของแผนการเทรด (Agent 07 Risk & Logic Auditor)

**ผู้ตรวจสั่งแก้อย่างเดียว ห้ามแก้แผนเอง** (มติผู้ใช้ 2026-08-04)
โมดูลนี้จึงไม่แตะและไม่คืนแผนที่แก้แล้ว — คืนเฉพาะ *ใบสั่งแก้* ที่ทุกข้อบอก
**ค่าที่ควรเป็น** (`should_be`) และ **เกณฑ์ที่ถือว่าแก้แล้วผ่าน** (`pass_criterion`)
เพราะเมื่อผู้ตรวจแก้เองไม่ได้ ใบสั่งที่บอกแค่ "ผิดตรงไหน" จะทำให้วนหลายรอบโดยเปล่าประโยชน์

ชั้นนี้เป็น**ด่านตัดสินครั้งเดียว ไม่ใช่ลูป** — กฎ deterministic กับข้อมูลเดิมให้ผลเดิมเสมอ
การวนแก้อยู่ที่ชั้นวิจารณญาณ (สกิล `audit-trade-logic`) ซึ่งคนหรือโมเดลเป็นผู้เดิน
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import levels as level_engine  # noqa: E402
from tools import risk_thresholds  # noqa: E402
from tools import trade_plan  # noqa: E402


AUDITOR_VERSION = "1.0.0"

VERDICT_PASS = "pass"
VERDICT_REVISE = "revise"
VERDICT_BLOCK = "block"

BLOCKING = "blocking"
REQUIRED = "required"
SUGGESTION = "suggestion"

MAX_ROUNDS = 2

# ค่าเกณฑ์อยู่ที่ `config/risk_thresholds.json` — ที่นี่แค่อ่านมาใช้
#
# **RL-003 กับ RL-004 จะไม่ยิงอีกแล้วในทางปฏิบัติ และนั่นคือสิ่งที่ตั้งใจ**
# ตั้งแต่ 2026-08-05 `trade_plan.select_stop()` กับ `select_targets()` เลือกเฉพาะระดับ
# ที่ผ่านสองเกณฑ์นี้อยู่แล้ว หาไม่เจอก็ตอบ `no_trade` ไปตั้งแต่ต้นทาง
# ⇒ แผนที่เดินมาถึงด่านนี้จึงผ่านสองข้อนั้นเสมอ
#
# **"ไม่ยิง" ไม่ได้แปลว่า "พัง"** — กฎสองข้อนี้เปลี่ยนบทบาทจากตัวคัดกรอง
# เป็นตัวกันบั๊ก: ถ้าวันไหนมันยิงขึ้นมา แปลว่าตัวสร้างแผนทำผิดสัญญาของตัวเอง
# ซึ่งเป็นสัญญาณที่มีค่ากว่าเดิม · ห้ามลบกฎทิ้งเพราะเห็นว่าไม่เคยยิง
#
# ที่มาของการเปลี่ยน: วัดย้อนหลัง 484 วัน (121 วัน × 4 สินทรัพย์ ด้วยข้อมูล MT5 จริง)
# เมื่อ 2026-08-05 พบว่าโค้ดเดิมหยิบระดับ**ใกล้สุด**เป็นจุดตัดขาดทุนเสมอ ทำให้ระยะ
# ติดอยู่ที่ 0.35–0.40 ATR ทุกวันและไม่มีแผนไหนผ่านด่านนี้เลยสักวัน
# ผลวัดเต็ม: `01-CC/Output/2026-08-05_ผลวัดระยะ4-เกณฑ์ความเสี่ยง-P002.md`
# บทเรียน 2026-08-04: เกณฑ์ของ forex ที่ยกไปใช้กับทองทำให้คำว่า "แรง" ยิง 59.1% ของวัน
DEFAULT_THRESHOLDS = risk_thresholds.load()


def _finding(*, identifier: str, severity: str, field: str, problem: str,
             should_be: str, pass_criterion: str, target: str = "trade_plan") -> dict:
    return {
        "id": identifier,
        "severity": severity,
        "target": target,
        "field": field,
        "problem": problem,
        "should_be": should_be,
        "pass_criterion": pass_criterion,
        "resolution": None,
    }


def _verdict(findings: list[dict]) -> str:
    severities = {item["severity"] for item in findings}
    if BLOCKING in severities:
        return VERDICT_BLOCK
    if REQUIRED in severities:
        return VERDICT_REVISE
    return VERDICT_PASS


def _score(plan: dict, findings: list[dict]) -> int:
    """คะแนนความน่าเชื่อถือ 1–10 — เริ่มจากคะแนนของแผนแล้วหักตามสิ่งที่ตรวจเจอ"""
    penalty = {BLOCKING: 5, REQUIRED: 2, SUGGESTION: 1}
    score = int(plan.get("confidence") or 1)
    for item in findings:
        score -= penalty[item["severity"]]
    return max(1, min(10, score))


def _better_stop(plan: dict, level_map: dict, atr: float, minimum: float) -> dict | None:
    """หาระดับฝั่งตรงข้ามตัวแรกที่ทำให้ระยะจุดตัดขาดทุนถึงเกณฑ์ — ใช้เสนอค่าที่ควรเป็น"""
    reference = float(level_map["reference_price"])
    supports, resistances = trade_plan.split_sides(level_map.get("zones") or [], reference)
    opposite = resistances if plan["bias"] == trade_plan.BIAS_DOWN else supports
    entry = float(plan["entry"]["edge"])
    for zone in opposite:
        if abs(zone["edge"] - entry) / atr >= minimum:
            return zone
    return None


def _target_reaching_rr(plan: dict, minimum_rr: float) -> dict | None:
    """เป้าหมายชั้นถัดไปที่ให้ RR ถึงเกณฑ์ ถ้ามี"""
    for target in plan.get("targets") or []:
        if target["rr"] >= minimum_rr:
            return target
    return None


def audit(plan: dict, *, level_map: dict, news: dict | None = None,
          thresholds: dict | None = None, round_number: int = 1) -> dict:
    """ตรวจแผนหนึ่งชุดแล้วออกใบสั่งแก้

    ไม่แก้แผน ไม่คืนแผน — คืนผลตรวจอย่างเดียวตามหลักผู้ตรวจอิสระ
    """
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    findings: list[dict] = []
    checked: list[str] = []
    unavailable: list[dict] = []

    # กฎที่ยังตรวจไม่ได้ในรุ่นนี้ — ประกาศไว้ให้เห็น ดีกว่าเงียบแล้วให้คนเข้าใจว่าตรวจครบ
    unavailable.append({
        "rule": "RL-006",
        "name": "news_direction_conflict",
        "reason": ("ข้อมูลข่าวมีเฉพาะ 'ประเด็น' (theme) ไม่มีทิศบวก/ลบของผลกระทบ "
                   "จึงเทียบกับทิศของแผนไม่ได้ — การเดาทิศเองจะทำให้ระบบตัดสินจากสิ่งที่ไม่มีหลักฐาน"),
        "unblocked_by": "ระยะ 3b — เมื่อมีปฏิทินเศรษฐกิจที่ให้ค่าคาดการณ์เป็น evidence",
    })

    if plan.get("classification") == trade_plan.NO_TRADE:
        return {
            "auditor_version": AUDITOR_VERSION,
            "verdict": VERDICT_PASS,
            "confidence_score": 1,
            "round": round_number,
            "max_rounds": MAX_ROUNDS,
            "thresholds_used": limits,
            "note": ("แผนรายงานว่าไม่มีจังหวะพร้อมเหตุผล — เป็นผลลัพธ์ที่ถูกต้อง ไม่ใช่ข้อบกพร่อง "
                     f"(เหตุผล: {plan.get('reason')})"),
            "findings": [],
            "checked": ["RL-000 แผนไม่มีจังหวะ จึงไม่มีค่าให้ตรวจ"],
            "unavailable_checks": unavailable,
        }

    zones = level_map.get("zones") or []
    entry = float(plan["entry"]["edge"])
    stop = float(plan["stop"]["value"])
    atr_distance = float(plan["stop"]["atr_distance"])
    atr = abs(stop - entry) / atr_distance if atr_distance else None

    # RL-001 · ทุกค่าต้องอ้างระดับที่อนุมัติแล้ว — กติกาแกนของโปรเจกต์
    # `invalidation.value` เข้ามาอยู่ในรายการนี้ตั้งแต่ 2026-08-05 ตอนที่มันเลิกเป็นสำเนา
    # ของ `stop.value` — ก่อนหน้านั้นไม่ต้องตรวจเพราะ stop ถูกตรวจอยู่แล้วในบรรทัดเดียวกัน
    invalidation = (plan.get("invalidation") or {}).get("value")
    for field, value in (("entry.edge", entry), ("stop.value", stop),
                         *([("invalidation.value", float(invalidation))]
                           if invalidation is not None else []),
                         *[(f"targets[{i}].value", t["value"])
                           for i, t in enumerate(plan.get("targets") or [])]):
        result = level_engine.validate_target(value, zones)
        if not result["valid"]:
            findings.append(_finding(
                identifier="RL-001", severity=BLOCKING, field=field,
                problem=f"{field} = {value} ไม่ตรงกับระดับที่อนุมัติแล้ว ({result['reason']})",
                should_be="ใช้ค่าจาก level-map.zones ที่ approved_for_publication เท่านั้น",
                pass_criterion="levels.validate_target(ค่านั้น, zones) คืน valid = true"))
    if not findings:
        checked.append("RL-001 ทุกค่าอ้างระดับที่อนุมัติแล้ว")

    # RL-002 · ต้องมีเป้าหมายและจุดยกเลิกครบ (classify_scenario ตัดสินให้แล้ว)
    if plan.get("classification") == level_engine.WATCHLIST:
        findings.append(_finding(
            identifier="RL-002", severity=BLOCKING, field="classification",
            problem=f"แผนถูกจำแนกเป็น watchlist ({plan.get('reason')}) จึงยังไม่ใช่แผน",
            should_be="เติมเป้าหมายที่อ้างระดับจริงและจุดยกเลิกให้ครบ หรือรายงานเป็น no_trade",
            pass_criterion="levels.classify_scenario คืน daily_scenario ขึ้นไป"))
    else:
        checked.append("RL-002 มีเป้าหมายและจุดยกเลิกครบ")

    # RL-003 · อัตราส่วนผลตอบแทนต่อความเสี่ยง
    rr = float(plan["rr"])
    if rr < limits["minimum_rr"]:
        better = _target_reaching_rr(plan, limits["minimum_rr"])
        if better:
            should_be = (f"ใช้เป้าหมายชั้นถัดไปที่ {better['value']} "
                         f"({better['label']}) ซึ่งได้อัตราส่วน {better['rr']:.2f}")
        else:
            should_be = ("ไม่มีเป้าหมายใดในชุดระดับที่อนุมัติแล้วทำให้ถึงเกณฑ์ "
                         "⇒ รายงานแผนนี้เป็น no_trade แทนการฝืนเข้า")
        findings.append(_finding(
            identifier="RL-003", severity=REQUIRED, field="rr",
            problem=f"อัตราส่วนผลตอบแทนต่อความเสี่ยง {rr:.2f} ต่ำกว่าเกณฑ์ {limits['minimum_rr']}",
            should_be=should_be,
            pass_criterion=f"rr >= {limits['minimum_rr']}"))
    else:
        checked.append(f"RL-003 อัตราส่วนผลตอบแทนต่อความเสี่ยง {rr:.2f} ผ่านเกณฑ์")

    # RL-004 · จุดตัดขาดทุนต้องกว้างกว่าความผันผวนปกติ ไม่งั้นโดนกวาดด้วย noise ของวันเดียว
    if atr_distance < limits["minimum_stop_atr"]:
        candidate = _better_stop(plan, level_map, atr, limits["minimum_stop_atr"]) if atr else None
        if candidate:
            should_be = (f"ขยับจุดตัดขาดทุนไปที่ {candidate['edge']} ({candidate['label']}) "
                         f"ซึ่งห่าง {abs(candidate['edge'] - entry) / atr:.2f} เท่าของ ATR14")
        else:
            should_be = ("ไม่มีระดับฝั่งตรงข้ามที่ห่างพอในชุดที่อนุมัติแล้ว "
                         "⇒ รายงานเป็น no_trade แทนการวางจุดตัดขาดทุนที่แคบเกินจริง")
        findings.append(_finding(
            identifier="RL-004", severity=REQUIRED, field="stop.value",
            problem=(f"จุดตัดขาดทุนห่างจากจุดเข้าเพียง {atr_distance:.2f} เท่าของ ATR14 "
                     f"(เกณฑ์ {limits['minimum_stop_atr']}) — แคบกว่าการแกว่งปกติของวันเดียว"),
            should_be=should_be,
            pass_criterion=f"stop.atr_distance >= {limits['minimum_stop_atr']} "
                           f"และ stop.value ยังผ่าน validate_target"))
    else:
        checked.append(f"RL-004 ระยะจุดตัดขาดทุน {atr_distance:.2f} เท่าของ ATR14 ผ่านเกณฑ์")

    # RL-005 · จุดเข้าที่ไกลเกินไปยังไม่ใช่เรื่องของวันนี้
    if atr is not None:
        entry_distance = abs(entry - float(plan["reference_price"])) / atr
        if entry_distance > limits["maximum_entry_atr"]:
            findings.append(_finding(
                identifier="RL-005", severity=REQUIRED, field="entry.edge",
                problem=(f"จุดเข้าอยู่ห่างจากราคาปัจจุบัน {entry_distance:.2f} เท่าของ ATR14 "
                         f"(เกณฑ์ {limits['maximum_entry_atr']})"),
                should_be=("รายงานเป็น no_trade สำหรับรอบนี้ แล้วกลับมาประเมินใหม่"
                           "เมื่อราคาเข้าใกล้ระดับ — ไม่ต้องขยับระดับหนีเข้าหาราคา"),
                pass_criterion=f"|entry.edge - reference_price| / atr14 <= {limits['maximum_entry_atr']}"))
        else:
            checked.append(f"RL-005 จุดเข้าห่างราคาปัจจุบัน {entry_distance:.2f} เท่าของ ATR14")

    # RL-007 · ทิศแผนต้องตรง regime หรือมีเหตุผลกำกับ
    if plan.get("bias") == trade_plan.BIAS_NEUTRAL:
        findings.append(_finding(
            identifier="RL-007", severity=BLOCKING, field="bias",
            problem="แผนไม่มีทิศแต่ยังเสนอจุดเข้า",
            should_be="รายงานเป็น no_trade เมื่อทิศยังไม่ชัด",
            pass_criterion="bias เป็น up หรือ down"))
    elif plan.get("bias_reason") not in ("price_above_rising_stack", "price_below_falling_stack") \
            and not plan.get("counter_trend_reason"):
        findings.append(_finding(
            identifier="RL-007", severity=REQUIRED, field="counter_trend_reason",
            problem="ทิศของแผนไม่ได้มาจาก regime ของเส้นค่าเฉลี่ย แต่ไม่มีเหตุผลกำกับ",
            should_be="เติม counter_trend_reason ที่อ้าง evidence ว่าทำไมจึงสวนทิศ",
            pass_criterion="counter_trend_reason ไม่ว่าง และอ้าง field ใน evidence ได้"))
    else:
        checked.append("RL-007 ทิศของแผนตรงกับ regime ของเส้นค่าเฉลี่ย")

    # RL-008 · ทุกตัวเลขต้องชี้กลับหลักฐานได้
    refs = plan.get("evidence_refs") or {}
    missing = [field for field in ("entry.edge", "stop.value", "targets[0].value", "rr")
               if not refs.get(field)]
    if missing:
        findings.append(_finding(
            identifier="RL-008", severity=BLOCKING, field="evidence_refs",
            problem=f"ไม่มีที่มาของค่า: {', '.join(missing)}",
            should_be="เติม evidence_refs ให้ครบทุก field ที่เป็นตัวเลข",
            pass_criterion="ทุก field ตัวเลขมี key ใน evidence_refs และค่าไม่ว่าง"))
    else:
        checked.append("RL-008 ทุกตัวเลขมีที่มากำกับ")

    # RL-009 · มีข่าวในรอบแต่แผนไม่ได้บันทึกความเสี่ยงเหตุการณ์
    # (แทนที่ RL-006 ที่ตรวจทิศข่าวไม่ได้ — ข้อนี้ตรวจได้จริงโดยไม่ต้องรู้ทิศ)
    news_items = (news or {}).get("items") or []
    if news_items:
        has_event_note = any("ข่าว" in line or "เหตุการณ์" in line
                             for line in plan.get("no_trade") or [])
        if not has_event_note:
            events = ", ".join(sorted({item.get("event", "") for item in news_items})[:2])
            findings.append(_finding(
                identifier="RL-009", severity=SUGGESTION, field="no_trade",
                problem=f"รอบนี้มีข่าวผ่านชั้นคัดกรอง {len(news_items)} ชิ้น แต่แผนไม่ได้ระบุความเสี่ยงเหตุการณ์",
                should_be=f"เพิ่มเงื่อนไขงดเข้าเมื่อใกล้เวลาประกาศ: {events}",
                pass_criterion="no_trade มีข้อที่กล่าวถึงความเสี่ยงจากข่าวหรือเหตุการณ์"))
        else:
            checked.append("RL-009 แผนบันทึกความเสี่ยงเหตุการณ์ไว้แล้ว")
    else:
        checked.append("RL-009 ไม่มีข่าวในรอบนี้ จึงไม่มีความเสี่ยงเหตุการณ์ให้บันทึก")

    return {
        "auditor_version": AUDITOR_VERSION,
        "verdict": _verdict(findings),
        "confidence_score": _score(plan, findings),
        "round": round_number,
        "max_rounds": MAX_ROUNDS,
        "thresholds_used": limits,
        "note": None,
        "findings": findings,
        "checked": checked,
        "unavailable_checks": unavailable,
    }
