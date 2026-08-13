"""ตัวเลือกหลักฐานของ Style K — จำแนกสภาวะตลาดแล้วเลือก primary/support/conflict

เหตุผลที่ต้องมีตัวเลือกแยกจากตัวคำนวณ: ถ้าปล่อยให้ตัวเขียนบทหยิบหลักฐานเอง
มันจะหยิบอันที่เขียนแล้วสวย ไม่ใช่อันที่เกี่ยวกับสภาวะตลาดจริง ๆ · ที่นี่จึงตัดสิน
ด้วยคะแนนที่มี weight เก็บใน config และถูก hash ตอน freeze

**สิ่งที่ห้ามเป็น feature ของคะแนนโดยเด็ดขาด:** outcome, target hit, MFE/MAE
— ตัวเลือกไม่มีทางเห็นค่าเหล่านั้นอยู่แล้วเพราะอยู่คนละ bundle แต่เขียนไว้ให้ชัด
เผื่อมีคนคิดจะ "ปรับให้ผลย้อนหลังดูดีขึ้น" ในอนาคต

Tie-break เป็น quality → freshness → evidence_id ตามลำดับอักษร เพื่อให้รันกี่ครั้ง
ก็ได้ผลเดิม — ไม่มี dict ordering หรือ set มาทำให้ผลแกว่ง
"""

from __future__ import annotations

from tools import style_k_techniques as tk

REGIME_TREND = "trend"
REGIME_RANGE = "range"
REGIME_COMPRESSION = "compression"
REGIME_EXPANSION = "expansion"
REGIME_TRANSITION = "transition"

DECISION_ARTICLE = "article"
DECISION_WATCH = "watch"
DECISION_INSUFFICIENT = "insufficient_evidence"

CERTAINTY_SCORE = {"confirmed": 1.0, "provisional": 0.6, "conditional": 0.3}


def _usable(units: list[dict]) -> list[dict]:
    return [unit for unit in units if unit["quality"] != tk.QUALITY_UNAVAILABLE]


def _find(units: list[dict], observation_type: str) -> dict | None:
    for unit in units:
        if unit["observation"].get("type") == observation_type:
            return unit
    return None


def classify_regime(record: dict) -> tuple[str, list[str]]:
    """จำแนกสภาวะตลาดจากหลักฐานที่มี — คืน (regime, reason_codes)

    ลำดับการตัดสินตายตัว ไม่ขึ้นกับลำดับที่หลักฐานถูกสร้าง
    """
    units = _usable(record["evidence"])
    reasons: list[str] = []

    volatility = _find(units, "atr_percentile")
    state = volatility["observation"]["state"] if volatility else "normal"

    structure = next((unit for unit in units if unit["technique_group"] == 1
                      and unit["observation"].get("type") in
                      {"higher_high_higher_low", "lower_high_lower_low", "mixed_structure"}), None)
    pattern = structure["observation"]["type"] if structure else None
    has_break = _find(units, "break_of_structure") is not None

    if state == "compression":
        reasons.append("ช่วงแกว่งอยู่ในกลุ่มแคบสุดของประวัติ")
        return REGIME_COMPRESSION, reasons
    if pattern in {"higher_high_higher_low", "lower_high_lower_low"}:
        reasons.append("ยอดและฐานเดินทางเดียวกัน")
        if state == "expansion":
            reasons.append("ช่วงแกว่งขยายตัวพร้อมกับโครงสร้างที่มีทิศ")
            return REGIME_EXPANSION, reasons
        return REGIME_TREND, reasons
    if has_break:
        reasons.append("ราคาทะลุระดับโครงสร้างเดิมขณะที่ยอด/ฐานยังไม่ไปทางเดียวกัน")
        return REGIME_TRANSITION, reasons
    reasons.append("ยอดกับฐานยังเดินคนละทางและช่วงแกว่งอยู่ระดับปกติ")
    return REGIME_RANGE, reasons


def _relevance(unit: dict, regime: str) -> float:
    """ความเกี่ยวข้องของกลุ่มเทคนิคกับสภาวะตลาด — ตารางตายตัว ไม่ใช่ค่าที่จูนตามผล"""
    table = {
        REGIME_TREND: {1: 1.0, 4: 0.9, 3: 0.6, 7: 0.6, 2: 0.4, 5: 0.3},
        REGIME_EXPANSION: {5: 1.0, 1: 0.9, 2: 0.6, 4: 0.6, 3: 0.4, 7: 0.3},
        REGIME_COMPRESSION: {5: 1.0, 2: 0.8, 3: 0.7, 1: 0.5, 7: 0.4, 4: 0.3},
        REGIME_RANGE: {3: 1.0, 2: 0.9, 7: 0.7, 1: 0.5, 5: 0.4, 4: 0.4},
        REGIME_TRANSITION: {1: 1.0, 2: 0.8, 5: 0.7, 4: 0.6, 3: 0.5, 7: 0.4},
    }
    return table[regime].get(unit["technique_group"], 0.2)


def _freshness(unit: dict) -> float:
    """หลักฐานที่อ้างแท่งล่าสุดสดกว่าหลักฐานที่อ้างแท่งเมื่อหลายสัปดาห์ก่อน"""
    refs = unit.get("source_refs") or []
    if not refs:
        return 0.3
    return 1.0 if max(refs) == unit["session_date"] else 0.5


def score_unit(unit: dict, *, regime: str, weights: dict) -> float:
    quality = 1.0 if unit["quality"] == tk.QUALITY_PASS else 0.5
    score = (
        weights["relevance_to_regime"] * _relevance(unit, regime)
        + weights["evidence_quality"] * quality * CERTAINTY_SCORE.get(unit["certainty"], 0.3)
        + weights["freshness"] * _freshness(unit)
        + weights["explainability"] * unit.get("explainability", 1.0)
        + weights["timeframe_fit"] * 1.0
    )
    score -= weights["limitation_penalty"] * min(len(unit.get("limitations") or []), 2) * 0.5
    if _freshness(unit) < 0.5:
        score -= weights["staleness_penalty"]
    return score


def _sort_key(unit: dict, scores: dict) -> tuple:
    """เรียงจากคะแนนมากไปน้อย แล้ว tie-break ตามกติกาข้อ 25 ของแผน"""
    return (
        -scores[unit["evidence_id"]],
        0 if unit["quality"] == tk.QUALITY_PASS else 1,
        -_freshness(unit),
        unit["evidence_id"],
    )


def select(record: dict, *, config: dict) -> dict:
    weights = config["selector_weights"]
    rules = config["selection_rules"]
    regime, reasons = classify_regime(record)
    units = _usable(record["evidence"])
    scores = {unit["evidence_id"]: score_unit(unit, regime=regime, weights=weights)
              for unit in units}
    ranked = sorted(units, key=lambda unit: _sort_key(unit, scores))

    reason_codes = list(reasons)
    primary_pool = [unit for unit in ranked
                    if unit["quality"] == tk.QUALITY_PASS and unit["direction"] != "neutral"]
    if not primary_pool:
        # ไม่มีหลักฐานที่ทั้งคุณภาพผ่านและมีทิศ — บอกไม่ได้ว่าจะเอียงไปทางไหน
        reason_codes.append("ไม่มีหลักฐานคุณภาพผ่านที่ระบุทิศทางได้")
        return _no_article(record, regime, reason_codes, scores, DECISION_INSUFFICIENT)

    primary = primary_pool[0]
    supporting: list[dict] = []
    used_families = {primary["independence_family"]}
    conflicting: list[dict] = []

    for unit in ranked:
        if unit["evidence_id"] == primary["evidence_id"]:
            continue
        same_side = unit["direction"] == primary["direction"]
        opposite = unit["direction"] not in {primary["direction"], "neutral"}
        if opposite:
            if len(conflicting) < rules["conflicting_max"]:
                conflicting.append(unit)
            continue
        if len(supporting) >= rules["supporting_max"]:
            continue
        # เลือกคนละ family ก่อน — RSI กับ MACD เป็นเสียงเดียวกัน ไม่ใช่สองเสียง
        if unit["independence_family"] in used_families:
            continue
        if same_side or unit["direction"] == "neutral":
            supporting.append(unit)
            used_families.add(unit["independence_family"])

    if len(supporting) < rules["supporting_min"]:
        reason_codes.append(
            f"หลักฐานสนับสนุนจากคนละกลุ่มอิสระมีแค่ {len(supporting)} ชิ้น "
            f"ต่ำกว่าเกณฑ์ {rules['supporting_min']} — ไม่ลดเกณฑ์เพื่อให้เขียนบทได้"
        )
        return _no_article(record, regime, reason_codes, scores, DECISION_WATCH,
                           primary=primary, supporting=supporting)

    return {
        "asset": record["asset"],
        "session_date": record["session_date"],
        "cutoff": record["cutoff"],
        "regime": regime,
        "primary_evidence_id": primary["evidence_id"],
        "supporting_evidence_ids": [unit["evidence_id"] for unit in supporting],
        "conflicting_evidence_ids": [unit["evidence_id"] for unit in conflicting],
        "unavailable_groups": record["unavailable_groups"],
        "decision": DECISION_ARTICLE,
        "bias": primary["direction"],
        "reason_codes": reason_codes,
        "scores": {key: round(value, 4) for key, value in sorted(scores.items())},
    }


def _no_article(record, regime, reason_codes, scores, decision, *, primary=None,
                supporting=None) -> dict:
    return {
        "asset": record["asset"],
        "session_date": record["session_date"],
        "cutoff": record["cutoff"],
        "regime": regime,
        "primary_evidence_id": primary["evidence_id"] if primary else None,
        "supporting_evidence_ids": [unit["evidence_id"] for unit in (supporting or [])],
        "conflicting_evidence_ids": [],
        "unavailable_groups": record["unavailable_groups"],
        "decision": decision,
        "bias": "neutral",
        "reason_codes": reason_codes,
        "scores": {key: round(value, 4) for key, value in sorted(scores.items())},
    }


def selection_problems(selection: dict, record: dict) -> list[str]:
    """เกณฑ์รับของขั้นเลือกหลักฐาน — ใช้ทั้งตอนรันจริงและในเทส"""
    problems: list[str] = []
    if selection["decision"] != DECISION_ARTICLE:
        if not selection["reason_codes"]:
            problems.append("ผลที่ไม่ใช่บทความต้องมีเหตุผลกำกับเสมอ")
        return problems

    ids = {unit["evidence_id"] for unit in record["evidence"]}
    chosen = [selection["primary_evidence_id"], *selection["supporting_evidence_ids"],
              *selection["conflicting_evidence_ids"]]
    for evidence_id in chosen:
        if evidence_id not in ids:
            problems.append(f"อ้าง evidence_id ที่ไม่มีในชุด: {evidence_id}")
    if len(set(chosen)) != len(chosen):
        problems.append("หลักฐานชิ้นเดียวถูกใช้ซ้ำหลายบทบาท")
    if not 2 <= len(selection["supporting_evidence_ids"]) <= 3:
        problems.append("จำนวนหลักฐานสนับสนุนต้องอยู่ระหว่าง 2–3 ชิ้น")
    if len(selection["conflicting_evidence_ids"]) > 1:
        problems.append("หลักฐานที่ขัดแย้งเลือกได้ไม่เกิน 1 ชิ้น")

    by_id = {unit["evidence_id"]: unit for unit in record["evidence"]}
    families = [by_id[evidence_id]["independence_family"]
                for evidence_id in [selection["primary_evidence_id"],
                                    *selection["supporting_evidence_ids"]]]
    if len(set(families)) != len(families):
        problems.append("หลักฐานหลักและสนับสนุนมาจากกลุ่มอิสระซ้ำกัน")
    return problems
