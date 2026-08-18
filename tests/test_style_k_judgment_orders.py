"""เทสใบสั่ง Agent 07 (JL-201…204 · 2026-08-14) — ตรึงพฤติกรรมที่เคาะจาก judgment order

- JL-201 ระดับจากหลักฐานนอกชุดที่บทเล่า ต้องถูกบอกผู้อ่านในตัวบท ไม่ใช่แค่ manifest
- JL-202 ทุก rule มี distance_atr และบทแสดงระยะ + คำเตือนเมื่ออยู่ในระยะ noise (<0.25 ATR)
- JL-203 Scenario B เลือกระดับเอง ไม่ใช่กระจกของ A · ใช้กระจกได้เฉพาะเมื่อจำเป็น + มี note
- JL-204 confluence ต่าง family ภายใน 0.1 ATR ต้องถูกเล่าพร้อมอ้างหลักฐานทั้งสองตัว
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools import style_k_dataset as ds  # noqa: E402
from tools import style_k_scenarios as sc  # noqa: E402
from tools import style_k_selector as sel  # noqa: E402
from tools import style_k_techniques as tk  # noqa: E402
from tools import style_k_writer as wr  # noqa: E402
from tests.test_style_k_no_lookahead import bars, make_bundle  # noqa: E402


@pytest.fixture
def config() -> dict:
    return ds.load_config()


@pytest.fixture
def built(config):
    """ชุดเดียวกับ fixture ของ test_style_k_writer — สร้างบทจริงจากสายเต็ม"""
    import datetime as dt
    rows = bars(300)
    last = rows[-1]
    day = dt.date.fromisoformat(last["date"])
    for step in range(1, 6):
        close = last["close"] - 4.0 * step
        rows.append({"date": (day + dt.timedelta(days=step)).isoformat(),
                     "open": close + 1.5, "high": close + 2.5,
                     "low": close - 2.5, "close": close})
    session_date = rows[-1]["date"]
    bundle = make_bundle(rows, session_date)
    record = tk.build_evidence(bundle, config=config)
    selection = sel.select(record, config=config)
    manifest = sc.build_scenarios(record, selection)
    entry = {"asset": "xauusd", "session_date": session_date,
             "cutoff": bundle["cutoff"], "limitations": []}
    markdown, sidecar = wr.build_article(record=record, selection=selection,
                                         manifest=manifest, config=config, entry=entry)
    return {"record": record, "selection": selection, "manifest": manifest,
            "markdown": markdown, "sidecar": sidecar, "config": config}


# ---------------------------------------------------------------- JL-202

def test_every_rule_carries_distance_atr(built):
    for scenario in built["manifest"]["scenarios"]:
        for key in ("confirmation_rule", "invalidation_rule"):
            distance = scenario[key]["distance_atr"]
            assert distance is not None and distance >= 0


def test_article_shows_distance_for_both_scenarios(built):
    assert built["markdown"].count("เท่าของช่วงแกว่งเฉลี่ย") >= 2


def test_noise_distance_gets_a_warning_and_far_does_not():
    """ระดับใกล้กว่า 0.25 ATR ต้องมีคำเตือน — ระดับไกลต้องไม่มี (คำเตือนพร่ำเพรื่อ = ไม่มีใครอ่าน)"""
    record = {
        "reference_price": 100.0,
        "evidence": [
            {"evidence_id": "ATR", "quality": "pass", "independence_family": "volatility",
             "observation": {"type": "atr_percentile", "atr14": 10.0},
             "interpretation": "", "level_refs": []},
        ],
    }
    atr_unit = record["evidence"][0]
    near = wr._rule_extras({"level": 101.0, "level_evidence_id": "X"}, record=record,
                           narrated={"X"}, atr_unit=atr_unit, instrument="spot_metal",
                           refs=[], scenario_label="ทดสอบ")
    far = wr._rule_extras({"level": 108.0, "level_evidence_id": "X"}, record=record,
                          narrated={"X"}, atr_unit=atr_unit, instrument="spot_metal",
                          refs=[], scenario_label="ทดสอบ")
    assert "การแกว่งปกติวันเดียวก็ปิดข้ามได้" in near
    assert "ปิดข้ามได้" not in far


# ---------------------------------------------------------------- JL-203

def _record_with_levels(levels_below, levels_above, atr=10.0):
    """record สังเคราะห์: หลักฐานคนละ family ต่อระดับ เพื่อคุมพูลระดับตรง ๆ"""
    evidence = [{"evidence_id": "ATR", "quality": "pass",
                 "independence_family": "volatility",
                 "observation": {"type": "atr_percentile", "atr14": atr},
                 "certainty": "confirmed", "interpretation": "", "level_refs": []}]
    for index, price in enumerate([*levels_below, *levels_above]):
        evidence.append({
            "evidence_id": f"E{index}", "quality": "pass",
            "independence_family": f"family{index}",
            "observation": {"type": "test"}, "certainty": "confirmed",
            "interpretation": "ระดับทดสอบ",
            "level_refs": [{"label": f"ระดับทดสอบ {index}", "price": price}],
        })
    return {"asset": "xauusd", "session_date": "2026-01-02",
            "cutoff": "2026-01-02T23:59:59+00:00", "reference_price": 100.0,
            "atr14": atr, "evidence": evidence}


def _selection_for(record, bias="bullish"):
    ids = [unit["evidence_id"] for unit in record["evidence"] if unit["evidence_id"] != "ATR"]
    return {"decision": sel.DECISION_ARTICLE, "bias": bias, "regime": "range",
            "primary_evidence_id": ids[0], "supporting_evidence_ids": ids[1:3],
            "conflicting_evidence_ids": [], "reason_codes": []}


def test_scenario_b_picks_its_own_level_when_one_exists():
    record = _record_with_levels(levels_below=[95.0, 90.0], levels_above=[105.0])
    manifest = sc.build_scenarios(record, _selection_for(record))
    scenario_a, scenario_b = manifest["scenarios"]
    assert scenario_a["confirmation_rule"]["level"] == 105.0
    assert scenario_a["invalidation_rule"]["level"] == 95.0
    # B ต้องพ้นระดับหักล้างของ A ออกไปอีกชั้น — ไม่ใช่กระจก 95
    assert scenario_b["confirmation_rule"]["level"] == 90.0
    assert scenario_b["selection_note"] is None
    assert sc.scenario_problems(manifest, record) == []


def test_scenario_b_mirrors_only_with_a_recorded_reason():
    record = _record_with_levels(levels_below=[95.0], levels_above=[105.0])
    manifest = sc.build_scenarios(record, _selection_for(record))
    scenario_b = manifest["scenarios"][1]
    assert scenario_b["confirmation_rule"]["level"] == 95.0
    assert scenario_b["selection_note"]
    assert sc.scenario_problems(manifest, record) == []


def test_mirror_without_note_is_rejected_by_the_gate():
    record = _record_with_levels(levels_below=[95.0], levels_above=[105.0])
    manifest = sc.build_scenarios(record, _selection_for(record))
    manifest["scenarios"][1]["selection_note"] = None
    problems = sc.scenario_problems(manifest, record)
    assert any("กระจก" in problem for problem in problems)


# ---------------------------------------------------------------- JL-201 + JL-204

def test_unnarrated_level_source_is_told_to_the_reader():
    """จำลองเคส 08-10 XAU: ระดับยืนยันมาจากหลักฐานที่ไม่ได้อยู่ในชุดที่บทเล่า"""
    record = {
        "reference_price": 100.0,
        "evidence": [
            {"evidence_id": "ATR", "quality": "pass", "independence_family": "volatility",
             "observation": {"type": "atr_percentile", "atr14": 10.0},
             "interpretation": "", "level_refs": []},
            {"evidence_id": "ZONE", "quality": "pass", "independence_family": "zone",
             "observation": {"type": "supply_zone", "lower": 110.0, "upper": 114.0},
             "interpretation": "โซนที่เคยมีแรงขายกดราคาลงมา ซึ่งยังอยู่เหนือราคาปัจจุบัน",
             "level_refs": [{"label": "ขอบล่างโซนอุปทาน", "price": 110.0}]},
        ],
    }
    refs: list = []
    extras = wr._rule_extras({"level": 110.0, "level_evidence_id": "ZONE"}, record=record,
                             narrated={"OTHER"}, atr_unit=record["evidence"][0],
                             instrument="spot_metal", refs=refs, scenario_label="ทดสอบ")
    assert "ซึ่งยังไม่ได้กล่าวถึงในส่วนก่อนหน้า" in extras
    assert "110" in extras and "114" in extras
    assert any(ref["evidence_id"] == "ZONE" for ref in refs)


def test_cross_family_confluence_is_disclosed_with_both_evidence_ids():
    """จำลองเคส 08-03 XAU: เส้นค่าเฉลี่ยทับระดับย่อฟีโบต่าง family ภายใน 0.1 ATR"""
    record = {
        "reference_price": 100.0,
        "evidence": [
            {"evidence_id": "ATR", "quality": "pass", "independence_family": "volatility",
             "observation": {"type": "atr_percentile", "atr14": 10.0},
             "interpretation": "", "level_refs": []},
            {"evidence_id": "TREND", "quality": "pass", "independence_family": "trend",
             "observation": {"type": "test"}, "interpretation": "",
             "level_refs": [{"label": "เส้นค่าเฉลี่ย 20 วัน", "price": 105.0}]},
            {"evidence_id": "FIB", "quality": "pass", "independence_family": "fibonacci",
             "observation": {"type": "test"}, "interpretation": "",
             "level_refs": [{"label": "ระดับย่อ 0.382", "price": 105.4}]},
        ],
    }
    refs: list = []
    extras = wr._rule_extras({"level": 105.0, "level_evidence_id": "TREND"}, record=record,
                             narrated={"TREND"}, atr_unit=record["evidence"][0],
                             instrument="spot_metal", refs=refs, scenario_label="ทดสอบ")
    assert "ทับกับระดับย่อ 0.382" in extras
    assert any(ref["evidence_id"] == "FIB" for ref in refs)
    # ตัวเลขในชื่อระดับ (0.382) ต้องมี ref ของตัวเอง ไม่ใช่ลอยอยู่ในบท
    assert any(ref["value"] == "0.382" for ref in refs)


def test_far_levels_are_not_called_confluence():
    record = {
        "reference_price": 100.0,
        "evidence": [
            {"evidence_id": "ATR", "quality": "pass", "independence_family": "volatility",
             "observation": {"type": "atr_percentile", "atr14": 10.0},
             "interpretation": "", "level_refs": []},
            {"evidence_id": "TREND", "quality": "pass", "independence_family": "trend",
             "observation": {"type": "test"}, "interpretation": "",
             "level_refs": [{"label": "เส้นค่าเฉลี่ย 20 วัน", "price": 105.0}]},
            {"evidence_id": "FIB", "quality": "pass", "independence_family": "fibonacci",
             "observation": {"type": "test"}, "interpretation": "",
             "level_refs": [{"label": "ระดับย่อ 0.382", "price": 108.0}]},
        ],
    }
    extras = wr._rule_extras({"level": 105.0, "level_evidence_id": "TREND"}, record=record,
                             narrated={"TREND"}, atr_unit=record["evidence"][0],
                             instrument="spot_metal", refs=[], scenario_label="ทดสอบ")
    assert "ทับกับ" not in extras


# ---------------------------------------------------------------- บันไดลดทอนงบคำ

def _extras_record():
    return {
        "reference_price": 100.0,
        "evidence": [
            {"evidence_id": "ATR", "quality": "pass", "independence_family": "volatility",
             "observation": {"type": "atr_percentile", "atr14": 10.0},
             "interpretation": "", "level_refs": []},
            {"evidence_id": "ZONE", "quality": "pass", "independence_family": "zone",
             "observation": {"type": "supply_zone", "lower": 108.0, "upper": 112.0},
             "interpretation": "โซนทดสอบ",
             "level_refs": [{"label": "ขอบล่างโซนอุปทาน", "price": 108.0}]},
            {"evidence_id": "FIB", "quality": "pass", "independence_family": "fibonacci",
             "observation": {"type": "test"}, "interpretation": "",
             "level_refs": [{"label": "ระดับย่อ 0.382", "price": 108.5}]},
        ],
    }


def test_compact_mode_drops_plain_distance_but_keeps_noise_warning():
    record = _extras_record()
    atr_unit = record["evidence"][0]
    far_rule = {"level": 108.0, "level_evidence_id": "ZONE"}
    near_rule = {"level": 101.0, "level_evidence_id": "ZONE"}
    far = wr._rule_extras(far_rule, record=record, narrated={"ZONE"}, atr_unit=atr_unit,
                          instrument="spot_metal", refs=[], scenario_label="t", mode="compact")
    near = wr._rule_extras(near_rule, record=record, narrated={"ZONE"}, atr_unit=atr_unit,
                           instrument="spot_metal", refs=[], scenario_label="t", mode="compact")
    assert "ห่างราว" not in far
    assert "การแกว่งปกติวันเดียวก็ปิดข้ามได้" in near


def test_minimal_mode_drops_confluence_but_never_provenance():
    record = _extras_record()
    atr_unit = record["evidence"][0]
    rule = {"level": 108.0, "level_evidence_id": "ZONE"}
    minimal = wr._rule_extras(rule, record=record, narrated={"OTHER"}, atr_unit=atr_unit,
                              instrument="spot_metal", refs=[], scenario_label="t",
                              mode="minimal")
    assert "ทับกับ" not in minimal
    assert "ซึ่งยังไม่ได้กล่าวถึงในส่วนก่อนหน้า" in minimal


def test_build_article_degrades_mode_to_fit_word_budget(built):
    """บีบเพดานคำให้ต่ำกว่าฉบับ full — ladder ต้องถอยโหมดเอง ไม่ใช่ปล่อยบทเกิน"""
    import copy
    config = copy.deepcopy(built["config"])
    full_count = built["sidecar"]["word_count"]
    config["article"]["word_max"] = full_count - 1
    markdown, sidecar = wr.build_article(record=built["record"], selection=built["selection"],
                                         manifest=built["manifest"], config=config,
                                         entry={"asset": "xauusd",
                                                "session_date": built["record"]["session_date"],
                                                "cutoff": built["record"]["cutoff"],
                                                "limitations": []})
    assert sidecar["extras_mode"] in ("compact", "minimal")
    assert sidecar["word_count"] < full_count


# ---------------------------------------------------------------- บทเต็มยังผ่านด่านเดิม

def test_full_article_still_passes_all_gates(built):
    assert built["sidecar"]["extras_mode"] == "full"
    assert wr.article_problems(built["markdown"], built["sidecar"],
                               config=built["config"], record=built["record"]) == []
