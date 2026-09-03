from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tools import style_m_v7_contract as contract
from tools import style_m_v7_risk as risk
from tools import style_m_v7_story as story
from tools import style_m_v7_writer as writer


def rows_fixture(days=20):
    start = datetime(2026, 8, 10, tzinfo=story.BANGKOK)
    rows = []
    for i in range(days * 24):
        stamp = start + timedelta(hours=i)
        base = 1000 + (i % 11) * 3
        rows.append({"at": stamp.strftime("%Y-%m-%d %H:%M:%S"),
                     "open": base, "high": base + 100,
                     "low": base - 100, "close": base + 20})
    return rows


def cutoff():
    return datetime(2026, 8, 30, 11, tzinfo=story.BANGKOK)


def test_adr14_uses_fourteen_completed_bangkok_days_and_ignores_forming_day():
    rows = rows_fixture()
    forming = rows + [{"at": "2026-08-30 10:00:00", "open": 1,
                       "high": 999999, "low": 1, "close": 2}]
    first = risk.adr14(rows, cutoff=cutoff())
    second = risk.adr14(forming, cutoff=cutoff())
    assert first["metric"] == "ADR14"
    assert first["length"] == 14
    assert first["last_closed_date"] == "2026-08-29"
    assert first["basis"] == "completed_bangkok_calendar_days_before_cutoff"
    assert second == first


def test_invalid_daily_input_fails_closed_with_reason_code():
    rows = rows_fixture()
    rows.pop(24)
    with pytest.raises(risk.RiskUnavailable) as exc:
        risk.adr14(rows, cutoff=cutoff())
    assert exc.value.reason_code == "ADR14_INVALID_DAILY_INPUT"


def test_missing_or_h1_volatility_cannot_enter_production_policy():
    h1 = story.build(rows_fixture(), cutoff=cutoff(), source_label="fixture")
    with pytest.raises(risk.RiskUnavailable) as exc:
        risk.apply_policy(h1["story"], volatility={"metric": "H1_ATR14", "value": 424.31, "length": 14,
                                                      "basis": "legacy"})
    assert exc.value.reason_code == "ADR14_UNAVAILABLE"


def test_forming_day_bad_ohlc_is_excluded_before_validation():
    rows = rows_fixture() + [{"at": "2026-08-30 10:00:00", "open": "bad",
                              "high": None, "low": None, "close": None}]
    result = risk.adr14(rows, cutoff=cutoff())
    assert result["last_closed_date"] == "2026-08-29"


def test_fixed_policy_builds_adr14_geometry_for_both_legs():
    h1 = story.build(rows_fixture(), cutoff=cutoff(), source_label="fixture")
    vol = risk.adr14(rows_fixture(), cutoff=cutoff())
    # Keep the focused policy test inside the cap with explicit structural
    # anchors; cap behavior is covered independently below.
    h1["story"]["pivots"] = {"lows": [{"price": 1100}], "highs": [{"price": 930}]}
    result = risk.apply_policy(h1["story"], volatility=vol)
    assert result["risk_geometry"]["policy_id"] == "ADR14_F0.50_C1.00_E0.10_R1.50_R2.00"
    assert result["risk_geometry"]["volatility"]["metric"] == "ADR14"
    assert result["risk_geometry"]["volatility"]["length"] == 14
    for plan in result["scenarios"].values():
        assert plan["state"] == "WAIT_TRIGGER"
        assert plan["risk_geometry"]["final_risk"] >= vol["value"] * 0.50
        assert plan["risk_geometry"]["final_risk"] <= vol["value"]
        assert plan["rr1"] >= 1.5 and plan["rr2"] >= 2.0


def test_cap_breach_is_no_plan_without_public_geometry():
    h1 = story.build(rows_fixture(), cutoff=cutoff(), source_label="fixture")
    tiny = {"metric": "ADR14", "value": 0.01, "length": 14,
            "last_closed_date": "2026-08-29",
            "basis": "completed_bangkok_calendar_days_before_cutoff"}
    result = risk.apply_policy(h1["story"], volatility=tiny)
    assert all(plan["state"] == "NO_PLAN" for plan in result["scenarios"].values())
    assert all(plan.get("entry_low") is None and plan.get("sl") is None
               and plan.get("tp1") is None for plan in result["scenarios"].values())
    assert all(plan["no_plan_reason"] == "FINAL_RISK_EXCEEDS_ADR14_CAP"
               for plan in result["scenarios"].values())


def test_v7_story_rejects_legacy_geometry_fields_and_v6_payloads():
    h1 = story.build(rows_fixture(), cutoff=cutoff(), source_label="fixture")
    assert h1["story"]["contract_version"] == "M-PROD/v7"
    assert "entry_zone_atr" not in h1["story"]["scenarios"]["long"]
    with pytest.raises(story.StoryUnavailable):
        story.validate({"schema": "style-m-story/v2", "contract_version": "M-PROD/v6"})


def test_canonical_facts_and_public_copy_are_adr14_only():
    h1 = story.build(rows_fixture(), cutoff=cutoff(), source_label="fixture")
    h1["story"]["pivots"] = {"lows": [{"price": 1100}], "highs": [{"price": 930}]}
    migrated = risk.apply_policy(h1["story"], volatility=risk.adr14(rows_fixture(), cutoff=cutoff()))
    facts = contract.build(migrated, h1["rows"])
    contract.validate(facts, story=migrated)
    article = writer.compose({"story": migrated, "facts": facts})
    assert contract.parity_report(facts, markdown=article)["status"] == "PASS"
    assert "M-PROD/v6" not in article and "H1 ATR" not in article
    assert facts["facts"]["risk_geometry"]["policy_id"] == risk.POLICY_ID


def test_v7_production_call_graph_has_no_legacy_geometry_dependency():
    root = Path(story.__file__).parents[0]
    production = [root / name for name in
                  ("style_m_v7_story.py", "style_m_v7_risk.py", "style_m_v7_daily.py",
                   "style_m_v7_contract.py", "style_m_v7_writer.py", "style_m_v7_renderer.py")]
    source = "\n".join(path.read_text(encoding="utf-8") for path in production)
    assert "style_m_v6" not in source
    assert "ENTRY_ZONE_ATR" not in source
    assert "STOP_BUFFER_ATR" not in source
    assert "B0_H1_ATR14_LEGACY" not in source
