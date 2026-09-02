from datetime import datetime, timedelta

import pytest

from tools import style_m_v6_risk as risk
from tools import style_m_v6_story as story


def _rows(days=20):
    start = datetime(2026, 1, 1, 0, tzinfo=story.BANGKOK)
    out = []
    for i in range(days * 24):
        p = 100 + (i % 9) * 0.1
        out.append({"at": (start + timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S"),
                    "open": p, "high": p + 2, "low": p - 1, "close": p + .5})
    return out


def test_daily_metrics_exclude_forming_day_and_use_closed_days_only():
    rows = _rows()
    cutoff = datetime(2026, 1, 20, 11, tzinfo=story.BANGKOK)
    bars = risk.completed_daily_bars(rows, cutoff=cutoff)
    assert bars[-1]["date"] == "2026-01-19"
    for metric in risk.DAILY_METRICS:
        result = risk.daily_volatility(rows, cutoff=cutoff, metric=metric)
        assert result["last_closed_date"] == "2026-01-19"


def test_insufficient_daily_bars_fails_closed():
    with pytest.raises(risk.RiskUnavailable):
        risk.daily_volatility(_rows(10), cutoff=datetime(2026, 1, 10, 11, tzinfo=story.BANGKOK), metric="ADR14")


def test_candidate_grid_and_policy_have_metadata_and_tick_rr():
    built = story.build(_rows(8), cutoff=datetime(2026, 1, 8, 11, tzinfo=story.BANGKOK), source_label="fixture")
    volatility = {"metric": "ADR14", "value": 30.0, "length": 14,
                  "last_closed_date": "2026-01-07"}
    chosen = risk.apply_policy(built["story"], volatility=volatility,
                               floor_coefficient=.35, max_cap_coefficient=1.25,
                               candidate_id="ADR14_F0.35_C1.25")
    assert chosen["risk_contract"]["candidate_id"] == "ADR14_F0.35_C1.25"
    for plan in chosen["scenarios"].values():
        if plan["state"] != "NO_PLAN":
            assert plan["rr1"] >= 1.5 and plan["rr2"] >= 2.0
            assert plan["risk_policy"] == "ADR14_F0.35_C1.25"


def test_cap_breach_is_oco_fail_closed():
    built = story.build(_rows(8), cutoff=datetime(2026, 1, 8, 11, tzinfo=story.BANGKOK), source_label="fixture")
    chosen = risk.apply_policy(built["story"], volatility={"metric": "ADR14", "value": .01},
                               floor_coefficient=.65, max_cap_coefficient=.85,
                               candidate_id="ADR14_F0.65_C0.85")
    assert all(plan["state"] == "NO_PLAN" for plan in chosen["scenarios"].values())
