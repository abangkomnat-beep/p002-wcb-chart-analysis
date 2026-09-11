import json
from datetime import datetime, timezone

import pytest

from tools.daily_source_selector import (TIMEZONE, SourceSelectorError, _forex_keys,
                                          bangkok_business_date, expected_count,
                                          is_weekend, source_keys_for_date)


def test_monday_has_six_lanes_including_both_daily_structure_articles():
    assert TIMEZONE == "Asia/Bangkok"
    assert source_keys_for_date("2026-09-07") == (
        ("D", "XAUUSD"), ("D", "WTIUSD"), ("E", "XAUUSD"),
        ("M", "BTCUSD"), ("L", "EURUSD"), ("L", "USDJPY"))
    assert expected_count("2026-09-07") == 6


def test_tuesday_to_friday_have_four_lanes_and_weekends_skip():
    assert expected_count("2026-09-08") == 4
    assert source_keys_for_date("2026-09-09")[2:] == (("L", "EURUSD"), ("L", "USDJPY"))
    assert source_keys_for_date("2026-09-10")[2:] == (("L", "GBPUSD"), ("L", "USDCAD"))
    assert expected_count("2026-09-11") == 4
    assert is_weekend("2026-09-12") and source_keys_for_date("2026-09-12") == ()


@pytest.mark.parametrize("assets", [[], ["eurusd"], ["eurusd", "usdjpy", "gbpusd"], ["eurusd", 1], ["eurusd", "xagusd"]])
def test_forex_schedule_rejects_wrong_pair_shape_and_unknown_assets(tmp_path, assets):
    schedule = {"timezone": TIMEZONE, "weekend_policy": "skip",
                "weekday_asset_batches": {str(day): list(assets) for day in range(5)}}
    path = tmp_path / "schedule.json"
    path.write_text(json.dumps(schedule), encoding="utf-8")
    with pytest.raises(SourceSelectorError):
        _forex_keys(path)


def test_bangkok_business_day_rolls_over_at_its_own_timezone_boundary():
    assert bangkok_business_date(datetime(2026, 9, 7, 16, 59, tzinfo=timezone.utc)) == "2026-09-07"
    assert bangkok_business_date(datetime(2026, 9, 7, 17, 0, tzinfo=timezone.utc)) == "2026-09-08"
    with pytest.raises(SourceSelectorError):
        bangkok_business_date(datetime(2026, 9, 7, 17, 0))
