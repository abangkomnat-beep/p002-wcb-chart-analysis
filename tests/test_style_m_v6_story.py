from datetime import datetime, timedelta

import pytest

from tools import style_m_v6_story as story


def rows_fixture(*, close=100.0, count=96):
    start = datetime(2026, 8, 27, 11, 0, 0, tzinfo=story.BANGKOK)
    rows = []
    for index in range(count):
        price = close + (index % 7) * 0.15
        rows.append({"at": (start + timedelta(hours=index)).strftime("%Y-%m-%d %H:%M:%S"),
                     "open": price, "high": price + 1.0 + (index % 3) * 0.2,
                     "low": price - 1.0, "close": price + 0.2})
    return rows


def built():
    cutoff = datetime(2026, 8, 31, 11, tzinfo=story.BANGKOK)
    return story.build(rows_fixture(), cutoff=cutoff, source_label="fixture")


def test_valid_data_always_has_both_scenarios_and_no_ema_field():
    result = built()["story"]
    assert result["state"] == "SCENARIOS_READY"
    assert set(result["scenarios"]) == {"long", "short"}
    assert "ema20" not in result["indicators"]
    assert "ema50" not in result["indicators"]


def test_donchian_and_geometry_are_deterministic():
    result = built()["story"]
    assert result["donchian"]["length"] == 24
    assert result["scenarios"]["long"]["trigger"] > result["scenarios"]["short"]["trigger"]
    assert result["scenarios"]["long"]["rr1"] >= 1.5
    assert result["scenarios"]["long"]["rr2"] >= 2.0
    assert result["scenarios"]["short"]["rr1"] >= 1.5
    assert result["scenarios"]["short"]["rr2"] >= 2.0


@pytest.mark.parametrize(("value", "expected"),
                         [(19.99, "QUIET_RANGE"), (20.0, "TRANSITION"),
                          (24.99, "TRANSITION"), (25.0, "TRENDING")])
def test_adx_regime_boundaries(value, expected):
    assert story.adx_regime(value) == expected


def test_exact_trigger_does_not_confirm():
    result = built()
    current = result["story"]
    latest = dict(current["latest"])
    latest["close"] = current["scenarios"]["long"]["trigger"]
    scenario = story._scenario("LONG", upper=current["donchian"]["upper"],
                                lower=current["donchian"]["lower"],
                                atr=current["indicators"]["atr14"], latest=latest,
                                cutoff=datetime.fromisoformat(current["cutoff"]))
    assert scenario["state"] == "WAIT_TRIGGER"


def test_malformed_source_fails_closed():
    cutoff = datetime(2026, 8, 31, 11, tzinfo=story.BANGKOK)
    with pytest.raises(story.StoryUnavailable):
        story.build(rows_fixture()[:-40], cutoff=cutoff, source_label="fixture")
