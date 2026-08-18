"""เทสทะเบียนเทคนิค 1–8 — ตรวจ "ความซื่อสัตย์ของแต่ละกลุ่ม" ไม่ใช่ตรวจค่าตรงกับแพลตฟอร์มไหน

สิ่งที่ต้องคงที่คือคุณสมบัติที่บทกับด่านตรวจพึ่งพา: กลุ่มที่ไม่มีข้อมูลต้องบอกว่าไม่มี
ความผันผวนต้องไม่กลายเป็นทิศทาง และเสียงที่ไม่อิสระต้องไม่ถูกนับเป็นหลายเสียง
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools import style_k_dataset as ds  # noqa: E402
from tools import style_k_techniques as tk  # noqa: E402
from tests.test_style_k_no_lookahead import bars, make_bundle  # noqa: E402


@pytest.fixture
def config() -> dict:
    return ds.load_config()


def build(rows, config, session_date=None):
    session_date = session_date or rows[-1]["date"]
    return tk.build_evidence(make_bundle(rows, session_date), config=config)


def test_all_eight_groups_report_readiness(config):
    record = build(bars(300), config)
    assert sorted(int(key) for key in record["readiness"]) == [1, 2, 3, 4, 5, 6, 7, 8]


def test_volume_group_is_unavailable_without_provenance(config):
    record = build(bars(300), config)
    volume = [unit for unit in record["evidence"] if unit["technique_group"] == 6]
    assert volume and all(unit["quality"] == tk.QUALITY_UNAVAILABLE for unit in volume)
    assert 6 in record["unavailable_groups"]


def test_multi_timeframe_is_unavailable_with_single_timeframe(config):
    record = build(bars(300), config)
    assert 8 in record["unavailable_groups"]


def test_volatility_never_claims_a_direction(config):
    record = build(bars(300), config)
    for unit in record["evidence"]:
        if unit["observation"].get("type") == "atr_percentile":
            assert unit["direction"] == "neutral"


def test_volatility_percentile_is_normalized_by_price(config):
    """ราคาที่สูงขึ้นทั้งชุดโดยความผันผวนสัมพัทธ์เท่าเดิม ต้องไม่ทำให้เปอร์เซ็นไทล์เพี้ยน

    นี่คือบั๊กที่วัดเจอจริงกับ BTCUSD: เทียบช่วงจริงเป็นหน่วยราคาดิบทำให้ทุกวัน
    ขึ้นว่า "ผันผวนต่ำสุดในประวัติ" เพราะอดีตราคาสูงกว่า
    """
    base = bars(200, start=100.0, step=0.0)
    scaled = [{**row, **{key: row[key] * 1000 for key in ("open", "high", "low", "close")}}
              for row in base]
    raw = tk.true_ranges(scaled)
    normalized = tk.true_ranges(scaled, normalized=True)
    assert max(raw) > 100 * max(normalized)
    assert pytest.approx(tk.true_ranges(base, normalized=True), rel=1e-9) == normalized


def test_momentum_and_trend_are_separate_families(config):
    record = build(bars(300), config)
    group4 = [unit for unit in record["evidence"] if unit["technique_group"] == 4
              and unit["quality"] != tk.QUALITY_UNAVAILABLE]
    families = {unit["independence_family"] for unit in group4}
    assert tk.FAMILY_TREND in families and tk.FAMILY_MOMENTUM in families


def test_short_history_makes_techniques_unavailable_not_wrong(config):
    """ประวัติสั้นต้องออกมาเป็น unavailable พร้อมเหตุผล ไม่ใช่ค่าที่เดาเอา"""
    record = build(bars(20), config)
    structure = [unit for unit in record["evidence"] if unit["technique_group"] == 1]
    assert all(unit["quality"] == tk.QUALITY_UNAVAILABLE for unit in structure)
    assert all(unit["limitations"] for unit in structure)


def test_every_unit_carries_traceable_identity(config):
    record = build(bars(300), config)
    seen = set()
    for unit in record["evidence"]:
        assert unit["evidence_id"] not in seen
        seen.add(unit["evidence_id"])
        assert unit["technique_group"] in tk.GROUP_NAMES
        assert unit["certainty"] in {"confirmed", "provisional", "conditional"}
        assert unit["direction"] in {"bullish", "bearish", "neutral"}


def test_supply_zone_checks_whole_zone_not_only_pivot_price(config):
    """Regression จาก BTC 2026-08-17: pivot high ถูกฝั่ง แต่ body อยู่ใต้ราคาปัจจุบัน.

    โซนดังกล่าวต้องถูกข้าม มิฉะนั้นบทจะบอกว่า "อยู่เหนือราคา" ทั้งที่ตัวเลขต่ำกว่า
    ทั้งช่วง ระบบควรเลือกผู้สมัครถัดไปที่ขอบโซนทั้งก้อนอยู่เหนือราคาจริง
    """
    rows = bars(60, start=99.0, step=0.0)
    for row in rows:
        row.update({"open": 99.0, "high": 100.0, "low": 97.0, "close": 99.0})
    # ผู้สมัครไกลกว่าแต่ใช้ได้: body ทั้งก้อนอยู่เหนือราคาปัจจุบัน
    rows[30].update({"open": 106.0, "high": 110.0, "low": 104.0, "close": 108.0})
    # ผู้สมัครใกล้กว่าแต่ใช้ไม่ได้: มีเพียงไส้เทียนที่เหนือราคา ส่วน body อยู่ใต้ราคา
    rows[40].update({"open": 95.0, "high": 105.0, "low": 94.0, "close": 96.0})

    evidence = tk.group3_supply_demand(
        rows, asset="btcusd", session_date=rows[-1]["date"],
        cutoff=f"{rows[-1]['date']}T23:59:59+00:00", config=config,
    )[0]

    assert evidence["quality"] != tk.QUALITY_UNAVAILABLE
    assert evidence["observation"]["type"] == "supply_zone"
    assert evidence["observation"]["origin_bar"] == rows[30]["date"]
    assert evidence["observation"]["lower"] > rows[-1]["close"]


def test_equal_level_labels_are_reader_facing_thai_in_evidence(config):
    rows = bars(60, start=99.0, step=0.0)
    for row in rows:
        row.update({"open": 99.0, "high": 100.0, "low": 97.0, "close": 99.0})
    rows[20]["high"] = 105.0
    rows[40]["high"] = 105.0
    evidence = tk.group2_liquidity(
        rows, asset="xauusd", session_date=rows[-1]["date"],
        cutoff=f"{rows[-1]['date']}T23:59:59+00:00", config=config,
    )
    equal_units = [unit for unit in evidence
                   if unit["observation"].get("type") in {"equal_highs", "equal_lows"}]
    assert equal_units
    labels = [ref["label"] for unit in equal_units for ref in unit["level_refs"]]
    assert all("equal" not in label.lower() for label in labels)
    assert set(labels) <= {"ยอดราคาใกล้เคียงกัน", "ฐานราคาใกล้เคียงกัน"}


def test_fib_levels_reference_their_anchor_bars(config):
    record = build(bars(300), config)
    fib = [unit for unit in record["evidence"] if unit["technique_group"] == 7
           and unit["quality"] != tk.QUALITY_UNAVAILABLE]
    for unit in fib:
        assert len(unit["source_refs"]) == 2, "ระดับฟีโบต้องอ้างจุดยึดสองจุดเสมอ"
        assert unit["observation"]["anchor_high"]["date"] in unit["source_refs"]
        assert unit["observation"]["anchor_low"]["date"] in unit["source_refs"]
