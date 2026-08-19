import json
import tempfile
import unittest
from pathlib import Path

from tools import calendar_feed, style_d_calendar


def raw_event(source_id: str, title_en: str, *, country: str = "USD",
              impact: str = "High", at: str = "2026-08-19 19:00",
              actual: float | None = None, forecast: float | None = None) -> dict:
    return {
        "id": source_id, "title_en": title_en, "title_th": title_en,
        "country": country, "impact": impact, "at_th": at,
        "actual": ({"raw": str(actual), "value": actual} if actual is not None else None),
        "forecast": ({"raw": str(forecast), "value": forecast}
                     if forecast is not None else None),
        "previous": None,
    }


def build(raw_events: list[dict], asset: str = "xauusd") -> tuple[dict, dict]:
    payload = {"ok": True, "retrieved_at": "2026-08-19T00:00:00Z",
               "events": raw_events}
    return style_d_calendar.build_calendar(
        payload, calendar_feed.to_calendar_events(payload),
        asset=asset, local_date="2026-08-19")


class StyleDCalendarRegistryTests(unittest.TestCase):
    def test_registry_covers_all_assets(self):
        registry = style_d_calendar.load_registry()
        self.assertEqual(set(registry["assets"]), style_d_calendar.EXPECTED_ASSETS)

    def test_missing_asset_is_fatal(self):
        source = json.loads(style_d_calendar.DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))
        source["assets"].remove("wtiusd")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaises(style_d_calendar.StyleDCalendarUnavailable) as caught:
                style_d_calendar.load_registry(path)
        self.assertEqual(caught.exception.reason_code, "calendar_registry_asset_missing")

    def test_id_precedes_alias_and_unknown_is_excluded(self):
        calendar, evidence = build([
            raw_event("390610", "title changed upstream"),
            raw_event("", "FOMC   Minutes", at="2026-08-20 01:00"),
            raw_event("999999", "FOMC Minutes Extra", at="2026-08-20 02:00"),
        ])
        self.assertEqual(calendar["event_count"], 2)
        self.assertEqual([row["matched_by"] for row in calendar["events"]],
                         ["source_id", "title_en_exact"])
        self.assertIn("unknown_family",
                      [row["reason_code"] for row in evidence["decisions"]])

    def test_asset_rules_are_fail_closed(self):
        energy = [raw_event("396574", "EIA Crude Oil Stocks Change")]
        gold, _ = build(energy, "xauusd")
        oil, _ = build(energy, "wtiusd")
        self.assertEqual(gold["event_count"], 0)
        self.assertEqual(oil["event_count"], 1)
        thai = [raw_event("406050", "GDP Growth YoY", country="THB")]
        thb, _ = build(thai, "usdthb")
        eur, _ = build(thai, "eurusd")
        self.assertEqual(thb["event_count"], 1)
        self.assertEqual(eur["event_count"], 0)

    def test_no_total_limit_and_single_page_covers_every_event(self):
        events = [raw_event(
            "", "FOMC Minutes", at=f"2026-08-{17 + index // 8:02d} {index % 8:02d}:00")
            for index in range(24)]
        calendar, evidence = build(events)
        self.assertEqual(calendar["event_count"], 24)
        flattened = [event for page in calendar["pages"] for event in page]
        self.assertEqual(len(flattened), 24)
        self.assertEqual(len(calendar["pages"]), 1)
        self.assertTrue(calendar["table_only"])
        self.assertEqual(evidence["counts"]["included"], 24)

    def test_valid_zero_creates_one_empty_page(self):
        calendar, evidence = build([raw_event("999", "Unknown Event")])
        self.assertTrue(calendar["empty_relevant"])
        self.assertEqual(calendar["pages"], [[]])
        self.assertEqual(evidence["counts"]["pages"], 1)

    def test_direction_uses_actual_vs_forecast_or_waits(self):
        raw_events = [
            raw_event("396587", "Initial Jobless Claims", actual=250, forecast=240),
            raw_event("397842", "ADP Employment Change Weekly", actual=20, forecast=10,
                      at="2026-08-19 20:00"),
            raw_event("390610", "FOMC Minutes", at="2026-08-20 01:00"),
        ]
        payload = {"ok": True, "events": raw_events}
        normalized = calendar_feed.to_calendar_events(payload)
        normalized[0].update({"actual": "250", "forecast": "240"})
        normalized[1].update({"actual": "20", "forecast": "10"})
        calendar, evidence = style_d_calendar.build_calendar(
            payload, normalized, asset="xauusd", local_date="2026-08-19")
        self.assertEqual([event["direction"] for event in calendar["events"]],
                         ["positive", "negative", "undetermined"])
        included = [row for row in evidence["decisions"] if row["decision"] == "included"]
        self.assertIsNotNone(included[0]["direction_basis"])
        self.assertIsNone(included[2]["direction_basis"])


if __name__ == "__main__":
    unittest.main()
