from datetime import date

import pytest

from tools.publication_schedule import ScheduleError, eligible_styles, is_no_run, validate_bundle


def test_monday_allows_d_and_e():
    assert eligible_styles(date(2026, 8, 24)) == ("D", "E")
    assert validate_bundle(date(2026, 8, 24), ("D", "E")) == ("D", "E")


def test_weekdays_tuesday_to_friday_allow_e_only():
    for day in (date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27), date(2026, 8, 28)):
        assert eligible_styles(day) == ("E",)
        assert validate_bundle(day, ("E",)) == ("E",)


def test_weekend_is_no_run():
    for day in (date(2026, 8, 22), date(2026, 8, 23)):
        assert is_no_run(day)
        assert eligible_styles(day) == ()
        with pytest.raises(ScheduleError, match="style_not_allowed_for_day"):
            validate_bundle(day, ("E",))


def test_cap_and_duplicate_are_fail_closed():
    monday = date(2026, 8, 24)
    with pytest.raises(ScheduleError, match="daily_public_cap_exceeded"):
        validate_bundle(monday, ("D", "E", "E"))
    with pytest.raises(ScheduleError, match="duplicate_style_slot"):
        validate_bundle(monday, ("D", "D"))

