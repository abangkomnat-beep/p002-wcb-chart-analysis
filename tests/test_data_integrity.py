"""เทสด่านตรวจข้อมูล — ปฏิทิน แท่งเทียน วันหาย indicator ขั้นต่ำ pivot และด่านเผยแพร่"""

import json
import sys
import unittest
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import candles as candles_module  # noqa: E402
from tools import gap_detector, indicators, integrity, market_calendar, pivots, publication_gate  # noqa: E402


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class MarketCalendarTests(unittest.TestCase):
    def test_forex_excludes_weekend_and_holiday(self):
        calendar = market_calendar.for_asset("eurusd")
        self.assertTrue(calendar.is_expected_session("2026-08-03"))   # จันทร์
        self.assertFalse(calendar.is_expected_session("2026-08-01"))  # เสาร์
        self.assertFalse(calendar.is_expected_session("2026-08-02"))  # อาทิตย์
        self.assertEqual(calendar.classify("2026-01-01"), "holiday")

    def test_crypto_expects_every_calendar_day(self):
        calendar = market_calendar.for_asset("btcusd")
        self.assertTrue(calendar.is_continuous)
        for day in ("2026-08-01", "2026-08-02", "2026-08-03"):
            self.assertTrue(calendar.is_expected_session(day))

    def test_previous_expected_session_skips_weekend(self):
        calendar = market_calendar.for_asset("xauusd")
        self.assertEqual(calendar.previous_expected_session("2026-08-03"), date(2026, 7, 31))

    def test_spot_metal_shares_the_forex_style_calendar(self):
        calendar = market_calendar.for_asset("xauusd")
        self.assertFalse(calendar.is_expected_session("2026-08-02"))


class CandleStateTests(unittest.TestCase):
    def setUp(self):
        self.calendar = market_calendar.for_asset("xauusd")
        self.rows = load_fixture("xau_5_points_with_weekend.json")["rows"]

    def test_weekend_candles_are_flagged_not_deleted(self):
        result = candles_module.normalize_candles(self.rows, self.calendar, asset="xauusd")

        self.assertEqual(len(result["candles"]), 5)
        flagged = [c["session_date"] for c in result["candles"] if not c["is_expected_session"]]
        self.assertEqual(flagged, ["2026-08-01", "2026-08-02"])
        self.assertTrue(all(a["severity"] == "fatal_for_publication" for a in result["anomalies"]))

    def test_last_candle_is_forming_by_default(self):
        result = candles_module.normalize_candles(self.rows, self.calendar, asset="xauusd")
        states = [c["candle_state"] for c in result["candles"]]
        self.assertEqual(states[-1], "forming")
        self.assertTrue(all(state == "closed" for state in states[:-1]))

    def test_valid_completed_candles_drops_weekend_and_forming(self):
        result = candles_module.normalize_candles(self.rows, self.calendar, asset="xauusd")
        valid = candles_module.valid_completed_candles(result["candles"])
        self.assertEqual([c["session_date"] for c in valid], ["2026-07-30", "2026-07-31"])

    def test_ohlc_bounds_are_expanded_and_noted(self):
        rows = [{"date": "2026-07-30", "open": 10.0, "high": 9.0, "low": 11.0, "close": 12.0}]
        result = candles_module.normalize_candles(rows, self.calendar, asset="xauusd")
        candle = result["candles"][0]
        self.assertEqual(candle["high"], 12.0)   # close สูงกว่า high ที่ provider ส่งมา
        self.assertEqual(candle["low"], 10.0)    # open ต่ำกว่า low ที่ provider ส่งมา
        self.assertTrue(candle["normalization_notes"])


class GapDetectorTests(unittest.TestCase):
    def _candles(self, fixture, asset):
        calendar = market_calendar.for_asset(asset)
        rows = load_fixture(fixture)["rows"]
        return calendar, candles_module.normalize_candles(rows, calendar, asset=asset)["candles"]

    def test_crypto_missing_day_blocks_publication(self):
        calendar, candle_list = self._candles("btc_missing_one_day.json", "btcusd")
        result = gap_detector.detect_gaps(candle_list, calendar)

        self.assertEqual(result["status"], "fail")
        self.assertIn("2026-07-20", result["missing_sessions"])
        self.assertTrue(result["publication_blocked"])

    def test_forex_weekend_is_not_a_gap(self):
        calendar, candle_list = self._candles("eurusd_valid_sessions.json", "eurusd")
        result = gap_detector.detect_gaps(candle_list, calendar)

        self.assertEqual(result["missing_sessions"], [])
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["publication_blocked"])

    def test_weekend_candles_are_reported_as_unexpected(self):
        calendar, candle_list = self._candles("xau_5_points_with_weekend.json", "xauusd")
        result = gap_detector.detect_gaps(candle_list, calendar)
        self.assertEqual(result["unexpected_sessions"], ["2026-08-01", "2026-08-02"])


class IndicatorMinimumBarTests(unittest.TestCase):
    def _valid(self, fixture, asset):
        calendar = market_calendar.for_asset(asset)
        rows = load_fixture(fixture)["rows"]
        normalized = candles_module.normalize_candles(rows, calendar, asset=asset)
        return candles_module.valid_completed_candles(normalized["candles"])

    def test_five_bars_make_every_indicator_unavailable(self):
        valid = self._valid("xau_5_points_with_weekend.json", "xauusd")
        result = indicators.compute_indicator_set(valid)

        for name in ("sma20", "sma50", "rsi14", "atr14"):
            with self.subTest(indicator=name):
                self.assertEqual(result[name]["status"], "insufficient_data")
                self.assertIsNone(result[name]["value"])
                self.assertFalse(result[name]["approved_for_publication"])
        self.assertEqual(indicators.published_values(result), {})

    def test_long_history_enables_sma50_but_not_sma200(self):
        valid = self._valid("xau_valid_120_sessions.json", "xauusd")
        result = indicators.compute_indicator_set(valid)

        self.assertEqual(result["sma20"]["status"], "available")
        self.assertEqual(result["sma50"]["status"], "available")
        self.assertEqual(result["sma50"]["calculation_owner"], "P002")
        self.assertEqual(result["sma200"]["status"], "insufficient_data")
        self.assertGreater(result["atr14"]["value"], 0)

    def test_provider_value_is_recorded_but_not_approved(self):
        item = indicators.provider_value("sma50", 4093.86, required=50, available=2)
        self.assertEqual(item["status"], "provider_only")
        self.assertEqual(item["calculation_owner"], "provider")
        self.assertFalse(item["approved_for_publication"])


class PivotTests(unittest.TestCase):
    def _candles(self, rows, asset):
        calendar = market_calendar.for_asset(asset)
        return calendar, candles_module.normalize_candles(rows, calendar, asset=asset)["candles"]

    def test_monday_pivot_uses_friday_not_the_weekend(self):
        rows = load_fixture("xau_5_points_with_weekend.json")["rows"]
        calendar, candle_list = self._candles(rows, "xauusd")

        result = pivots.compute_classic_pivots(candle_list, calendar=calendar)

        self.assertEqual(result["basis_session_date"], "2026-07-31")
        self.assertEqual(result["basis_candle_state"], "closed")
        self.assertEqual(result["quality_status"], "valid")

    def test_forming_candle_is_never_the_basis(self):
        rows = load_fixture("eurusd_valid_sessions.json")["rows"]
        calendar, candle_list = self._candles(rows, "eurusd")

        result = pivots.compute_classic_pivots(candle_list, calendar=calendar)

        self.assertNotEqual(result["basis_session_date"], candle_list[-1]["session_date"])
        self.assertEqual(result["basis_candle_state"], "closed")

    def test_classic_formula_is_correct(self):
        rows = [
            {"date": "2026-07-30", "open": 99.0, "high": 110.0, "low": 90.0, "close": 100.0},
            {"date": "2026-07-31", "open": 99.0, "high": 110.0, "low": 90.0, "close": 100.0},
            {"date": "2026-08-03", "open": 101.0, "high": 104.0, "low": 98.0, "close": 102.0},
        ]
        calendar, candle_list = self._candles(rows, "xauusd")
        result = pivots.compute_classic_pivots(candle_list, calendar=calendar)

        self.assertAlmostEqual(result["p"], 100.0)
        self.assertAlmostEqual(result["r1"], 110.0)
        self.assertAlmostEqual(result["s1"], 90.0)
        self.assertAlmostEqual(result["r2"], 120.0)
        self.assertAlmostEqual(result["s2"], 80.0)

    def test_records_full_basis_for_traceability(self):
        rows = load_fixture("xau_valid_120_sessions.json")["rows"]
        calendar, candle_list = self._candles(rows, "xauusd")
        result = pivots.compute_classic_pivots(candle_list, calendar=calendar, calculated_at="2026-08-03T06:30:00Z")

        for field in ("basis_session_date", "basis_open", "basis_high", "basis_low",
                      "basis_close", "basis_candle_state", "basis_timezone", "calculated_at"):
            with self.subTest(field=field):
                self.assertIsNotNone(result[field])

    def test_no_valid_basis_returns_invalid(self):
        rows = [
            {"date": "2026-08-01", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5},
            {"date": "2026-08-02", "open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0},
        ]
        calendar, candle_list = self._candles(rows, "xauusd")
        result = pivots.compute_classic_pivots(candle_list, calendar=calendar)

        self.assertEqual(result["quality_status"], "invalid")
        self.assertIsNone(result["p"])


class ProviderSessionConventionTests(unittest.TestCase):
    """Yahoo ประทับเวลาแท่ง FX ไว้ที่ 23:00 UTC ของวันก่อนหน้า = 00:00 ตามเวลาตลาด"""

    def setUp(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "pilot_generator", REPO_ROOT / "tools" / "pilot_generator.py"
        )
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_london_stamped_bar_maps_to_the_next_calendar_day(self):
        # 1783292400 = 2026-07-05T23:00Z = session วันจันทร์ที่ 6 ก.ค. ตามเวลา Europe/London
        self.assertEqual(self.mod.session_date_from_timestamp(1783292400, 3600), "2026-07-06")

    def test_utc_stamped_bar_is_unchanged(self):
        self.assertEqual(self.mod.session_date_from_timestamp(1783292400, 0), "2026-07-05")

    def test_missing_offset_falls_back_to_utc(self):
        self.assertEqual(self.mod.session_date_from_timestamp(1783292400, None), "2026-07-05")

    def test_corrected_labels_produce_weekday_sessions_only(self):
        calendar = market_calendar.for_asset("eurusd")
        # แท่งจริงจาก Yahoo ห้าแท่งติดกัน ประทับเวลาแบบ 23:00 UTC
        stamps = [1783292400, 1783378800, 1783465200, 1783551600, 1783638000]
        labels = [self.mod.session_date_from_timestamp(stamp, 3600) for stamp in stamps]

        self.assertEqual(labels, ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"])
        self.assertTrue(all(calendar.is_expected_session(label) for label in labels))


class PublicationGateTests(unittest.TestCase):
    def test_old_xau_sample_is_blocked(self):
        fixture = load_fixture("xau_5_points_with_weekend.json")
        report = integrity.assess(
            fixture["rows"], "xauusd",
            provider_indicators=fixture["provider_indicators"],
            calculated_at="2026-08-03T06:30:00Z",
        )
        gate = report["publication_gate"]

        self.assertEqual(gate["status"], "fail")
        codes = {reason["code"] for reason in gate["reasons"]}
        self.assertIn("pivot_uses_invalid_session", codes)
        self.assertIn("indicator_insufficient_bars", codes)
        self.assertEqual(report["published_indicator_values"], {})

    def test_valid_metal_history_passes(self):
        fixture = load_fixture("xau_valid_120_sessions.json")
        report = integrity.assess(fixture["rows"], "xauusd", calculated_at="2026-08-03T06:30:00Z")

        self.assertEqual(report["publication_gate"]["status"], "pass")
        self.assertIn("sma50", report["published_indicator_values"])

    def test_crypto_gap_blocks_even_with_long_history(self):
        fixture = load_fixture("btc_missing_one_day.json")
        report = integrity.assess(fixture["rows"], "btcusd", calculated_at="2026-08-03T06:30:00Z")
        gate = report["publication_gate"]

        self.assertEqual(gate["status"], "fail")
        self.assertIn("crypto_daily_gap", {reason["code"] for reason in gate["reasons"]})

    def test_valid_forex_history_passes(self):
        fixture = load_fixture("eurusd_valid_sessions.json")
        report = integrity.assess(fixture["rows"], "eurusd", calculated_at="2026-08-03T06:30:00Z")

        self.assertEqual(report["publication_gate"]["status"], "pass")

    def test_gate_reports_version_and_checked_at(self):
        gate = publication_gate.evaluate(
            indicators={}, pivots={}, gap_check={}, checked_at="2026-08-03T06:30:00Z"
        )
        self.assertEqual(gate["validator_version"], publication_gate.VALIDATOR_VERSION)
        self.assertEqual(gate["checked_at"], "2026-08-03T06:30:00Z")
        self.assertEqual(gate["status"], "pass")


if __name__ == "__main__":
    unittest.main()
