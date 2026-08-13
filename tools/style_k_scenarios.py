"""สถานการณ์ A/B ของ Style K — เขียนเงื่อนไขให้เครื่องตรวจได้ ก่อนเปิดผลจริง

หัวใจของไฟล์นี้: **เงื่อนไขต้องวัดได้ด้วยแท่งราคาอย่างเดียว** ไม่ใช่ถ้อยคำอย่าง
"ถ้าแรงซื้อกลับมา" · ทุกเงื่อนไขจึงเป็นรูป `close/high/low เทียบกับระดับที่มี evidence_id`

สองข้อที่จงใจไม่ทำ:

- **ไม่มี entry / stop / target ที่แต่งขึ้นเพื่อให้คำนวณ MFE/MAE ได้** — ถ้าหลักฐาน
  ไม่พอจะบอกเป้าหมาย ก็ปล่อย `target_zone` เป็น null แล้วรายงาน `not_defined`
  การเติมตัวเลขเพื่อให้ตารางสวยคือการปลอมหลักฐาน
- **Scenario B ไม่ใช่ "ทางที่ผิด"** — เป็นทางสำรองที่เงื่อนไขยังมาไม่ถึง ตอนวัดผลจึงไม่นับ
  ว่าผิดเพียงเพราะไม่เกิด

ตั้งแต่ 2026-08-14 (ใบสั่ง Agent 07 · JL-203): B เลือกระดับยืนยันของตัวเอง —
ระดับถัดไปที่พ้นระดับหักล้างของ A ไม่ใช่กระจกอัตโนมัติ · ใช้กระจกได้เฉพาะเมื่อ
หลักฐานไม่มีระดับอื่นจริง และต้องมี `selection_note` กำกับ (มีด่านตรวจ)
"""

from __future__ import annotations

from tools import style_k_selector as sel

NO_TRADE_DECISIONS = {sel.DECISION_WATCH, sel.DECISION_INSUFFICIENT}


def _levels_from(units: list[dict]) -> list[dict]:
    levels: list[dict] = []
    for unit in units:
        for ref in unit.get("level_refs") or []:
            price = ref.get("price")
            if price is None:
                continue
            levels.append({"price": float(price), "label": ref.get("label", ""),
                           "evidence_id": unit["evidence_id"]})
    return levels


def _nearest(levels: list[dict], reference: float, *, above: bool) -> dict | None:
    """ระดับที่ใกล้ราคาที่สุดในฝั่งที่ต้องการ · tie-break ด้วย evidence_id ให้ผลคงที่"""
    side = [item for item in levels
            if (item["price"] > reference if above else item["price"] < reference)]
    if not side:
        return None
    return sorted(side, key=lambda item: (abs(item["price"] - reference), item["evidence_id"]))[0]


def _next_beyond(levels: list[dict], reference: float, boundary: float,
                 *, above: bool) -> dict | None:
    """ระดับถัดไปที่อยู่พ้น boundary ออกไปในฝั่งเดียวกัน (JL-203)

    ใช้เลือกระดับยืนยันของ Scenario B ให้พ้นระดับหักล้างของ A ออกไปอีกชั้น —
    การปิดข้ามระดับหักล้างของ A บอกแค่ว่า "มุมมอง A ผิด" การยืนยัน B เป็นคำกล่าว
    ที่หนักกว่านั้น จึงต้องใช้ระดับที่ไกลกว่า · ช่องว่างระหว่างสองระดับ = สถานะ
    "A ผิดแต่ B ยังไม่ยืนยัน" ซึ่งของเดิม (B เป็นกระจกของ A) แสดงไม่ได้
    """
    side = [item for item in levels
            if (item["price"] > boundary if above else item["price"] < boundary)]
    if not side:
        return None
    return sorted(side, key=lambda item: (abs(item["price"] - reference), item["evidence_id"]))[0]


def _distance_atr(level: float, reference: float, atr: float | None) -> float | None:
    """ระยะจากราคาปิดถึงระดับ เป็นสัดส่วนของ ATR (JL-202) — เปิดเผยว่า trigger ไกลแค่ไหน"""
    if not atr:
        return None
    return round(abs(level - reference) / atr, 2)


def _scenario(scenario_id, *, bias, reference, confirm, invalidate, evidence_refs,
              certainty, atr=None, target=None, selection_note=None) -> dict:
    direction_word = "ขึ้นไปปิดเหนือ" if bias == "bullish" else "ลงไปปิดใต้"
    invalid_word = "ปิดใต้" if bias == "bullish" else "ปิดเหนือ"
    return {
        "scenario_id": scenario_id,
        "bias": bias,
        "if_condition": {
            "type": "daily_close_beyond",
            "side": "above" if bias == "bullish" else "below",
            "level": confirm["price"],
            "text": f"ถ้าราคาปิดรายวัน{direction_word} {confirm['price']:.2f}",
        },
        "confirmation_rule": {
            "measure": "close",
            "comparison": "gt" if bias == "bullish" else "lt",
            "level": confirm["price"],
            "level_label": confirm["label"],
            "level_evidence_id": confirm["evidence_id"],
            "distance_atr": _distance_atr(confirm["price"], reference, atr),
        },
        "selection_note": selection_note,
        "confirmation_level_or_zone": {"price": confirm["price"], "label": confirm["label"]},
        "expected_path": [],
        "target_zone": target,
        "invalidation_rule": {
            "measure": "close",
            "comparison": "lt" if bias == "bullish" else "gt",
            "level": invalidate["price"],
            "level_label": invalidate["label"],
            "level_evidence_id": invalidate["evidence_id"],
            "text": f"ถ้าราคา{invalid_word} {invalidate['price']:.2f}",
            "distance_atr": _distance_atr(invalidate["price"], reference, atr),
        },
        "evaluation_reference_price": reference,
        "evidence_refs": evidence_refs,
        "certainty": certainty,
    }


def build_scenarios(record: dict, selection: dict) -> dict:
    """สร้าง Scenario A/B หรือบันทึกเหตุผลที่ไม่มี setup"""
    reference = record["reference_price"]
    by_id = {unit["evidence_id"]: unit for unit in record["evidence"]}

    if selection["decision"] in NO_TRADE_DECISIONS:
        return {
            "asset": record["asset"],
            "session_date": record["session_date"],
            "cutoff": record["cutoff"],
            "evaluation_reference_price": reference,
            "scenarios": [],
            "no_trade_reason": " · ".join(selection["reason_codes"]),
        }

    chosen_ids = [selection["primary_evidence_id"], *selection["supporting_evidence_ids"],
                  *selection["conflicting_evidence_ids"]]
    levels = _levels_from([by_id[evidence_id] for evidence_id in chosen_ids if evidence_id in by_id])
    above = _nearest(levels, reference, above=True)
    below = _nearest(levels, reference, above=False)

    # ถ้าฝั่งใดว่าง ให้ขยายไปหาระดับจากหลักฐานที่ใช้ได้ทั้งชุด **แล้วบันทึกว่าขยาย**
    #
    # ทำไมต้องมีชั้นนี้: เมื่อราคาเพิ่งทะลุขึ้น ระดับที่หลักฐานชุดที่เลือกอ้างถึงมัก
    # อยู่ใต้ราคาทั้งหมด ทำให้เขียนเงื่อนไขยืนยันฝั่งบนไม่ได้ทั้งที่ยังมีระดับจริงอยู่
    # ในหลักฐานชิ้นอื่น · การขยายพูลไม่ใช่การแต่งระดับ — ยังเป็นระดับที่มี evidence_id
    # แต่ต้องโปร่งใสว่าไม่ได้มาจากสามชิ้นที่บทเล่า จึงติดธง `level_pool` ไว้
    pool_note: list[str] = []
    if above is None or below is None:
        wide = _levels_from([unit for unit in record["evidence"]
                             if unit["quality"] != "unavailable"])
        if above is None:
            above = _nearest(wide, reference, above=True)
            if above is not None:
                pool_note.append("ระดับยืนยันฝั่งบนมาจากหลักฐานนอกชุดที่บทเล่า")
        if below is None:
            below = _nearest(wide, reference, above=False)
            if below is not None:
                pool_note.append("ระดับยืนยันฝั่งล่างมาจากหลักฐานนอกชุดที่บทเล่า")

    if above is None or below is None:
        missing = "เหนือราคา" if above is None else "ใต้ราคา"
        return {
            "asset": record["asset"],
            "session_date": record["session_date"],
            "cutoff": record["cutoff"],
            "evaluation_reference_price": reference,
            "scenarios": [],
            "no_trade_reason": (f"หลักฐานทั้งชุดไม่มีระดับราคา{missing}ให้ใช้เป็นเงื่อนไข "
                                "จึงเขียนเงื่อนไขที่วัดได้ไม่ได้ — ไม่แต่งระดับขึ้นเอง"),
        }

    bias = selection["bias"]
    primary_certainty = by_id[selection["primary_evidence_id"]]["certainty"]
    atr = record.get("atr14")
    wide = _levels_from([unit for unit in record["evidence"]
                         if unit["quality"] != "unavailable"])

    # JL-203 (มติ 08-14): B เลือกระดับยืนยันของตัวเอง — ระดับถัดไปที่พ้นระดับหักล้าง
    # ของ A ออกไปอีกชั้น (หาในชุดที่บทเล่าก่อน แล้วค่อยขยายทั้งชุด) · หาไม่ได้จริง
    # จึงยอมใช้กระจกของ A พร้อมบันทึกเหตุผล — ห้ามเงียบ
    def _b_confirm(mirror: dict, *, above_side: bool) -> tuple[dict, str | None]:
        for pool in (levels, wide):
            candidate = _next_beyond(pool, reference, mirror["price"], above=above_side)
            if candidate is not None:
                return candidate, None
        return mirror, ("หลักฐานทั้งชุดไม่มีระดับที่พ้นระดับหักล้างของ A "
                        "จึงใช้ระดับเดียวกันโดยจำเป็น")

    if bias == "bullish":
        scenario_a = _scenario("A", bias="bullish", reference=reference, confirm=above,
                               invalidate=below, evidence_refs=chosen_ids,
                               certainty=primary_certainty, atr=atr)
        b_confirm, b_note = _b_confirm(below, above_side=False)
        scenario_b = _scenario("B", bias="bearish", reference=reference, confirm=b_confirm,
                               invalidate=above, evidence_refs=chosen_ids,
                               certainty="conditional", atr=atr, selection_note=b_note)
    else:
        scenario_a = _scenario("A", bias="bearish", reference=reference, confirm=below,
                               invalidate=above, evidence_refs=chosen_ids,
                               certainty=primary_certainty, atr=atr)
        b_confirm, b_note = _b_confirm(above, above_side=True)
        scenario_b = _scenario("B", bias="bullish", reference=reference, confirm=b_confirm,
                               invalidate=below, evidence_refs=chosen_ids,
                               certainty="conditional", atr=atr, selection_note=b_note)

    return {
        "asset": record["asset"],
        "session_date": record["session_date"],
        "cutoff": record["cutoff"],
        "evaluation_reference_price": reference,
        "atr14": record["atr14"],
        "scenarios": [scenario_a, scenario_b],
        "level_pool_notes": pool_note,
        "no_trade_reason": None,
    }


def scenario_problems(manifest: dict, record: dict) -> list[str]:
    problems: list[str] = []
    scenarios = manifest["scenarios"]
    if not scenarios:
        if not manifest.get("no_trade_reason"):
            problems.append("ไม่มี scenario แต่ก็ไม่มีเหตุผลกำกับ")
        return problems
    if len(scenarios) != 2:
        problems.append(f"ต้องมี Scenario A และ B ได้ {len(scenarios)}")

    ids = {unit["evidence_id"] for unit in record["evidence"]}
    for scenario in scenarios:
        confirm = scenario["confirmation_rule"]["level"]
        invalidate = scenario["invalidation_rule"]["level"]
        if confirm == invalidate:
            problems.append(f"{scenario['scenario_id']}: ระดับยืนยันกับระดับที่หักล้างเป็นค่าเดียวกัน")
        if scenario["bias"] == "bullish" and not confirm > invalidate:
            problems.append(f"{scenario['scenario_id']}: ฝั่งขึ้นแต่ระดับยืนยันไม่ได้อยู่เหนือระดับหักล้าง")
        if scenario["bias"] == "bearish" and not confirm < invalidate:
            problems.append(f"{scenario['scenario_id']}: ฝั่งลงแต่ระดับยืนยันไม่ได้อยู่ใต้ระดับหักล้าง")
        for key in ("confirmation_rule", "invalidation_rule"):
            evidence_id = scenario[key]["level_evidence_id"]
            if evidence_id not in ids:
                problems.append(f"{scenario['scenario_id']}: {key} อ้าง evidence_id ที่ไม่มี")
        if scenario.get("target_zone") is None and scenario.get("expected_path"):
            problems.append(f"{scenario['scenario_id']}: มีเส้นทางคาดหวังแต่ไม่มีเป้าหมาย")
    biases = {scenario["bias"] for scenario in scenarios}
    if len(biases) != 2:
        problems.append("Scenario A และ B ต้องเป็นคนละทิศ ไม่ใช่ทางเดียวกันสองใบ")

    # JL-203: B ที่เป็นกระจกของ A (confirm B == invalidate A) ต้องมีเหตุผลกำกับเสมอ
    if len(scenarios) == 2:
        first, second = scenarios
        mirror = second["confirmation_rule"]["level"] == first["invalidation_rule"]["level"]
        if mirror and not second.get("selection_note"):
            problems.append("B: ระดับยืนยันเป็นกระจกของระดับหักล้าง A โดยไม่มีเหตุผลกำกับ")
    return problems
