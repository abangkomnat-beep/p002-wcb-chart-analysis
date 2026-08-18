from __future__ import annotations

import copy
import sys
import unittest
import json
import tempfile
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import event_evidence, style_c_event  # noqa: E402

AS_OF = datetime(2026, 8, 17, 14, 45, tzinfo=timezone.utc)
PRICE_META = {"timezone_check": {"asset": "xauusd", "expected_offset_minutes": 0,
                                  "measured_offset_minutes": 0, "verified": True,
                                  "reason": "ค่าที่วัดสดตรงกับทะเบียน"}}


def value(raw):
    return {"raw": str(raw), "value": float(raw), "unit": None, "kind": "index",
            "unit_source": "dict", "scale_unknown": False}


def empire(**updates):
    row = {"id": "398376", "title_en": "NY Empire State Manufacturing Index",
           "title_th": "ภาคการผลิตนิวยอร์ก", "country": "USD", "impact": "Medium",
           "at_th": "2026-08-17 19:30:00", "at_utc": "2026-08-17T12:30:00Z",
           "actual": value(20.6), "forecast": value(11), "previous": value(15.6)}
    row.update(updates)
    return row


def raw(*events):
    return {"ok": True, "retrieved_at": "2026-08-17T14:30:00Z", "events": list(events)}


def bar(at, o, h, l, c, forming=False):
    return {"at": at, "open": o, "high": h, "low": l, "close": c, "forming": forming}


ROWS = [
    bar("2026-08-17 19:00:00", 4387, 4390, 4386, 4389.28067),
    bar("2026-08-17 19:30:00", 4388.52074, 4389.04494, 4377.70871, 4386.04328),
    bar("2026-08-17 20:00:00", 4385.67094, 4388.97733, 4382.50504, 4386.62875),
    bar("2026-08-17 20:30:00", 4386.73842, 4414.62123, 4385.38379, 4408.32887),
    bar("2026-08-17 21:00:00", 4409.25569, 4427.32545, 4404.18399, 4417.80215),
]


def _synthetic_test_only_m5_fixture():
    """Independent provider-shaped M5 fixture; production never resamples M30."""
    start = datetime(2026, 8, 17, 19, 15)
    anchor_at = {2: 4389.28067, 8: 4386.04328, 14: 4386.62875,
                 20: 4408.32887, 26: 4417.80215}
    closes = []
    for index in range(27):
        left = max((point for point in anchor_at if point <= index), default=2)
        right = min((point for point in anchor_at if point >= index), default=26)
        if index < 2:
            close = 4388.4 + index * .44
        elif left == right:
            close = anchor_at[left]
        else:
            close = anchor_at[left] + ((anchor_at[right]-anchor_at[left])
                                      * (index-left)/(right-left))
        closes.append(round(close, 5))
    rows = []
    previous = 4388.05
    for index, close in enumerate(closes):
        opened = previous
        rows.append(bar((start+timedelta(minutes=5*index)).strftime("%Y-%m-%d %H:%M:%S"),
                        opened, max(opened, close)+.72+(index % 3)*.08,
                        min(opened, close)-.66-(index % 2)*.07, close))
        previous = close
    return rows


SYNTHETIC_TEST_ONLY_M5_ROWS = _synthetic_test_only_m5_fixture()


class EventValueTests(unittest.TestCase):
    def test_parse_index(self):
        self.assertEqual(event_evidence.parse_value(value(20.6))["value"], 20.6)

    def test_comparison_above(self):
        self.assertEqual(event_evidence.compare(event_evidence.parse_value(value(20.6)),
                                                event_evidence.parse_value(value(11))), "above")

    def test_unit_mismatch_fails_closed(self):
        left = event_evidence.parse_value(value(20.6))
        right = event_evidence.parse_value({**value(11), "kind": "percent", "unit": "%"})
        self.assertEqual(event_evidence.compare(left, right), "unknown")


class SelectorTests(unittest.TestCase):
    def test_empire_medium_is_direct(self):
        selected = style_c_event.select_event(raw(empire()), AS_OF)
        self.assertEqual(selected["event"]["id"], "398376")

    def test_provider_cased_value_fields_are_accepted(self):
        row = empire()
        for lower, upper in (("actual", "Actual"), ("forecast", "Forecast"),
                             ("previous", "Previous"), ("country", "Country"),
                             ("impact", "Impact")):
            row[upper] = row.pop(lower)
        selected = style_c_event.select_event(raw(row), AS_OF)
        self.assertEqual(selected["event"]["id"], "398376")

    def test_cad_is_rejected(self):
        selected = style_c_event.select_event(raw(empire(id="cad", country="CAD")), AS_OF)
        reasons = selected["rejected_candidates"][0]["reasons"]
        self.assertIn("country_not_directly_approved_for_xauusd", reasons)

    def test_actual_missing_is_rejected(self):
        selected = style_c_event.select_event(raw(empire(actual=None)), AS_OF)
        self.assertIn("actual_missing", selected["rejected_candidates"][0]["reasons"])

    def test_future_event_is_rejected(self):
        selected = style_c_event.select_event(raw(empire(at_utc="2026-08-17T15:30:00Z")), AS_OF)
        self.assertIn("event_in_future", selected["rejected_candidates"][0]["reasons"])

    def test_older_than_24h_is_rejected(self):
        selected = style_c_event.select_event(raw(empire(at_utc="2026-08-16T12:30:00Z")), AS_OF)
        self.assertIn("event_outside_24h", selected["rejected_candidates"][0]["reasons"])

    def test_unknown_family_is_rejected(self):
        selected = style_c_event.select_event(raw(empire(id="x", title_en="Unknown")), AS_OF)
        self.assertIn("family_not_allowlisted", selected["rejected_candidates"][0]["reasons"])


class ReactionTests(unittest.TestCase):
    def test_acceptance_chronology_and_metrics(self):
        reaction = style_c_event.build_reaction(ROWS, datetime(2026, 8, 17, 12, 30,
                                                               tzinfo=timezone.utc), AS_OF)
        self.assertEqual([b["ohlc"]["close"] for b in reaction["bars"]],
                         [4389.28067, 4386.04328, 4386.62875, 4408.32887, 4417.80215])
        expected = {"delta_30": -3.23739, "pct_30": -0.07375,
                    "range_30": 11.33623, "range_pct_30": 0.25827,
                    "delta_60": -2.65192, "pct_60": -0.06042,
                    "delta_90": 19.0482, "pct_90": 0.434,
                    "range_90": 36.91252, "range_pct_90": 0.841,
                    "delta_120": 28.52148, "pct_120": 0.6498,
                    "range_120": 49.61674, "range_pct_120": 1.1304}
        for key, wanted in expected.items():
            # แผนระบุ pct_30=-0.07375 แต่สูตรจากค่าฐานเต็มได้ -0.0737567
            # (ปัดมาตรฐาน = -0.07376) จึงตรวจ tolerance 0.00002 และเก็บ unrounded
            # ไว้ใน artifact แทนการบิดสูตรให้ตรงเลขตัวอย่างหนึ่งตัว
            self.assertAlmostEqual(reaction["metrics"][key]["value_rounded"], wanted, places=4)


class ChartContractTests(unittest.TestCase):
    def test_true_five_candles_close_markers_and_deterministic_metadata(self):
        from tools import style_c_event_chart
        evidence = style_c_event.build_evidence(raw(empire()), ROWS, asset="xauusd",
                                                as_of=AS_OF, batch_id="chart-test",
                                                price_meta=PRICE_META)
        evidence["chart_reaction"] = style_c_event.build_chart_reaction(
            SYNTHETIC_TEST_ONLY_M5_ROWS, datetime(2026, 8, 17, 12, 30, tzinfo=timezone.utc), AS_OF,
            PRICE_META, evidence["reaction"])
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            meta_a = style_c_event_chart.render(evidence, Path(first))
            meta_b = style_c_event_chart.render(evidence, Path(second))
            self.assertEqual(meta_a, meta_b)
            self.assertEqual(meta_a["candle_count"], 27)
            self.assertEqual(meta_a["body_count"], 27)
            self.assertEqual(meta_a["wick_count"], 27)
            self.assertEqual(meta_a["close_marker_count"], 5)
            self.assertEqual(meta_a["m30_anchor_count"], 5)
            self.assertEqual(meta_a["series"], ["m5_ohlc_candles", "m30_close_anchors"])
            self.assertNotIn("generated_at", meta_a)
            self.assertIn("ภาคการผลิตนิวยอร์ก", meta_a["event_marker_label"])
            self.assertIn("19:30", meta_a["event_marker_label"])
            # Geometry/label collision guards: narrow bodies, unique x labels,
            # and a legend explicitly outside the price plotting area.
            self.assertLess(meta_a["body_width"], .8)
            self.assertEqual(len(set(meta_a["close_labels_th"])), 27)
            self.assertEqual(meta_a["legend_placement"], "outside_plot_top")

    def test_m5_window_has_exact_cadence_and_coverage(self):
        chart = style_c_event.build_chart_reaction(
            SYNTHETIC_TEST_ONLY_M5_ROWS, datetime(2026, 8, 17, 12, 30, tzinfo=timezone.utc), AS_OF,
            PRICE_META, style_c_event.build_reaction(
                ROWS, datetime(2026, 8, 17, 12, 30, tzinfo=timezone.utc), AS_OF))
        self.assertEqual(chart["status"], "complete")
        self.assertEqual(chart["expected_count"], 27)
        self.assertEqual(len(chart["bars"]), 27)
        self.assertEqual(chart["window"], ["2026-08-17T19:15:00+07:00",
                                           "2026-08-17T21:30:00+07:00"])
        opens = [datetime.fromisoformat(item["open_at_th"]) for item in chart["bars"]]
        self.assertEqual({(b-a).total_seconds() for a, b in zip(opens, opens[1:])}, {300})
        self.assertEqual(len(chart["anchor_checks"]), 5)
        self.assertTrue(all(item["match"] for item in chart["anchor_checks"]))
        self.assertEqual([item["slot"] for item in chart["anchor_checks"]],
                         ["pre", "+30", "+60", "+90", "+120"])

    def test_each_m5_m30_anchor_mismatch_fails_gate0_and_renderer(self):
        from tools import style_c_event_chart
        event_at = datetime(2026, 8, 17, 12, 30, tzinfo=timezone.utc)
        m30 = style_c_event.build_reaction(ROWS, event_at, AS_OF)
        base = style_c_event.build_evidence(raw(empire()), ROWS, asset="xauusd",
                                            as_of=AS_OF, batch_id="anchor-mismatch",
                                            price_meta=PRICE_META)
        for anchor_index in (2, 8, 14, 20, 26):
            with self.subTest(anchor_index=anchor_index), tempfile.TemporaryDirectory() as folder:
                rows = copy.deepcopy(SYNTHETIC_TEST_ONLY_M5_ROWS)
                rows[anchor_index]["close"] += .02
                chart_reaction = style_c_event.build_chart_reaction(
                    rows, event_at, AS_OF, PRICE_META, m30)
                self.assertEqual(chart_reaction["status"], "insufficient_bars")
                self.assertIn("m5_m30_anchor_mismatch", chart_reaction["violations"])
                self.assertEqual(sum(not item["match"]
                                     for item in chart_reaction["anchor_checks"]), 1)
                evidence = copy.deepcopy(base)
                evidence["chart_reaction"] = chart_reaction
                with self.assertRaisesRegex(ValueError, "27 closed canonical M5"):
                    style_c_event_chart.render(evidence, Path(folder))
                self.assertFalse(list(Path(folder).glob("*.webp")))

    def test_m5_timezone_gate_requires_explicit_true(self):
        event_at = datetime(2026, 8, 17, 12, 30, tzinfo=timezone.utc)
        m30 = style_c_event.build_reaction(ROWS, event_at, AS_OF)
        false_meta = copy.deepcopy(PRICE_META)
        false_meta["timezone_check"]["verified"] = False
        for meta, expected in ((PRICE_META, "complete"),
                               (false_meta, "insufficient_bars"),
                               ({}, "insufficient_bars")):
            with self.subTest(expected=expected, has_check=bool(meta)):
                chart = style_c_event.build_chart_reaction(
                    SYNTHETIC_TEST_ONLY_M5_ROWS, event_at, AS_OF, meta, m30)
                self.assertEqual(chart["status"], expected)
                if expected != "complete":
                    self.assertIn("m5_timezone_unverified", chart["violations"])

    def test_missing_or_off_cadence_m5_is_incomplete(self):
        for rows in (SYNTHETIC_TEST_ONLY_M5_ROWS[:-1],
                     SYNTHETIC_TEST_ONLY_M5_ROWS[:10] + SYNTHETIC_TEST_ONLY_M5_ROWS[11:]):
            with self.subTest(count=len(rows)):
                chart = style_c_event.build_chart_reaction(
                    rows, datetime(2026, 8, 17, 12, 30, tzinfo=timezone.utc), AS_OF,
                    PRICE_META, style_c_event.build_reaction(
                        ROWS, datetime(2026, 8, 17, 12, 30, tzinfo=timezone.utc), AS_OF))
                self.assertEqual(chart["status"], "insufficient_bars")
                self.assertTrue(chart["missing_open_at_th"])

    def test_m5_window_does_not_use_bars_closed_after_as_of(self):
        early = datetime(2026, 8, 17, 14, 15, tzinfo=timezone.utc)
        chart = style_c_event.build_chart_reaction(
            SYNTHETIC_TEST_ONLY_M5_ROWS,
            datetime(2026, 8, 17, 12, 30, tzinfo=timezone.utc), early,
            PRICE_META, style_c_event.build_reaction(
                ROWS, datetime(2026, 8, 17, 12, 30, tzinfo=timezone.utc), AS_OF))
        self.assertEqual(chart["status"], "insufficient_bars")
        self.assertIn("m5_bar_after_as_of_rejected", chart["violations"])
        self.assertTrue(chart["missing_open_at_th"])
        self.assertEqual(chart["bars"], [])

    def test_partial_three_and_four_bar_evidence_is_factual_and_chart_rejects(self):
        from tools import style_c_event_chart
        expected = ((ROWS[:3], "missing_post_90_bar", "missing_post_120_bar"),
                    (ROWS[:4], None, "missing_post_120_bar"))
        for rows, missing_90, missing_120 in expected:
            with self.subTest(bar_count=len(rows)), tempfile.TemporaryDirectory() as folder:
                evidence = style_c_event.build_evidence(
                    raw(empire()), rows, asset="xauusd", as_of=AS_OF,
                    batch_id="partial-chart", price_meta=PRICE_META)
                self.assertEqual(evidence["identity"]["analysis_mode"],
                                 "post_event_factual_only")
                if missing_90:
                    self.assertIn(missing_90, evidence["skip_reasons"])
                self.assertIn(missing_120, evidence["skip_reasons"])
                with self.assertRaisesRegex(ValueError, "complete|five ordered"):
                    style_c_event_chart.render(evidence, Path(folder))
                self.assertFalse(list(Path(folder).glob("*.webp")))

    def test_as_of_before_plus_120_never_looks_ahead(self):
        early = datetime(2026, 8, 17, 14, 15, tzinfo=timezone.utc)
        reaction = style_c_event.build_reaction(ROWS, datetime(2026, 8, 17, 12, 30,
                                                               tzinfo=timezone.utc), early)
        self.assertEqual(reaction["status"], "insufficient_bars")
        self.assertIn("missing_post_120_bar", reaction["missing_slots"])
        self.assertIn("bar_after_as_of_rejected", reaction["missing_slots"])
        self.assertNotIn("+120", [bar["slot"] for bar in reaction["bars"]])


class WordBoundaryTests(unittest.TestCase):
    def test_inclusive_350_to_600_contract(self):
        from tools import build_daily_package
        for count, passes, expected_rule in ((349, False, "style_word_floor"),
                                              (350, True, None),
                                              (600, True, None),
                                              (601, False, "style_word_ceiling")):
            with self.subTest(count=count):
                result = {"word_count": count, "findings": [], "status": "pass",
                          "fatal_count": 0}
                checked = build_daily_package.enforce_post_event_word_contract(
                    result, floor=350, ceiling=600)
                self.assertEqual(checked["status"] == "pass", passes)
                self.assertEqual(checked["fatal_count"], 0 if passes else 1)
                if expected_rule:
                    self.assertEqual(checked["findings"][0]["rule"], expected_rule)

    def test_forming_required_bar_is_rejected(self):
        rows = copy.deepcopy(ROWS)
        rows[1]["forming"] = True
        reaction = style_c_event.build_reaction(rows, datetime(2026, 8, 17, 12, 30,
                                                               tzinfo=timezone.utc), AS_OF)
        self.assertEqual(reaction["status"], "insufficient_bars")
        self.assertIn("forming_bar_rejected", reaction["missing_slots"])

    def test_bar_after_as_of_is_rejected(self):
        reaction = style_c_event.build_reaction(ROWS, datetime(2026, 8, 17, 12, 30,
                                                               tzinfo=timezone.utc),
                                                datetime(2026, 8, 17, 12, 45,
                                                         tzinfo=timezone.utc))
        self.assertIn("bar_after_as_of_rejected", reaction["missing_slots"])


class EvidenceTests(unittest.TestCase):
    def test_no_event_is_explicit_skip(self):
        evidence = style_c_event.build_evidence(raw(), ROWS, asset="xauusd", as_of=AS_OF,
                                                batch_id="test")
        self.assertEqual(evidence["identity"]["analysis_mode"], "not_applicable")
        self.assertEqual(evidence["skip_reasons"], ["no_eligible_released_event"])

    def test_non_xau_not_enabled(self):
        evidence = style_c_event.build_evidence(raw(empire()), ROWS, asset="eurusd",
                                                as_of=AS_OF, batch_id="test")
        self.assertEqual(evidence["skip_reasons"], ["rollout_asset_not_enabled"])

    def test_full_evidence_disables_causation(self):
        evidence = style_c_event.build_evidence(raw(empire()), ROWS, asset="xauusd",
                                                as_of=AS_OF, batch_id="test", price_meta=PRICE_META)
        self.assertEqual(evidence["identity"]["analysis_mode"], "post_event")
        self.assertEqual(evidence["event"]["event_at_utc"], "2026-08-17T12:30:00+00:00")
        self.assertEqual(evidence["surprise"]["actual_vs_forecast"], "above")
        self.assertEqual(evidence["interpretation"]["causal_status"], "disabled")

    def test_missing_calendar_provenance_is_not_applicable(self):
        payload = raw(empire())
        payload.pop("retrieved_at")
        evidence = style_c_event.build_evidence(payload, ROWS, asset="xauusd",
                                                as_of=AS_OF, batch_id="test",
                                                price_meta=PRICE_META)
        self.assertEqual(evidence["identity"]["analysis_mode"], "not_applicable")
        self.assertEqual(evidence["skip_reasons"], ["calendar_provenance_missing"])

    def test_source_after_asof_is_not_applicable(self):
        payload = raw(empire())
        payload["retrieved_at"] = "2026-08-17T15:00:00Z"
        evidence = style_c_event.build_evidence(payload, ROWS, asset="xauusd",
                                                as_of=AS_OF, batch_id="test",
                                                price_meta=PRICE_META)
        self.assertEqual(evidence["skip_reasons"], ["source_after_as_of"])

    def test_missing_forecast_is_factual_only(self):
        evidence = style_c_event.build_evidence(raw(empire(forecast=None)), ROWS,
                                                asset="xauusd", as_of=AS_OF, batch_id="test",
                                                price_meta=PRICE_META)
        self.assertEqual(evidence["identity"]["analysis_mode"], "post_event_factual_only")
        self.assertIn("forecast_missing", evidence["skip_reasons"])
        self.assertEqual(evidence["surprise"]["actual_vs_forecast"], "unknown")

    def test_missing_previous_is_factual_only_and_unknown(self):
        evidence = style_c_event.build_evidence(raw(empire(previous=None)), ROWS,
                                                asset="xauusd", as_of=AS_OF, batch_id="test",
                                                price_meta=PRICE_META)
        self.assertEqual(evidence["identity"]["analysis_mode"], "post_event_factual_only")
        self.assertIn("previous_missing", evidence["skip_reasons"])
        self.assertEqual(evidence["surprise"]["actual_vs_previous"], "unknown")

    def test_unit_mismatch_is_factual_only(self):
        mismatch = {**value(11), "kind": "percent", "unit": "%"}
        evidence = style_c_event.build_evidence(raw(empire(forecast=mismatch)), ROWS,
                                                asset="xauusd", as_of=AS_OF, batch_id="test",
                                                price_meta=PRICE_META)
        self.assertEqual(evidence["identity"]["analysis_mode"], "post_event_factual_only")
        self.assertIn("unit_mismatch", evidence["skip_reasons"])

    def test_unknown_semantics_is_factual_only(self):
        registry = copy.deepcopy(style_c_event.load_registry())
        registry["families"][0].pop("higher_means")
        evidence = style_c_event.build_evidence(raw(empire()), ROWS, asset="xauusd",
                                                as_of=AS_OF, batch_id="test",
                                                price_meta=PRICE_META, registry=registry)
        self.assertEqual(evidence["identity"]["analysis_mode"], "post_event_factual_only")
        self.assertIn("semantics_unknown", evidence["skip_reasons"])

    def test_missing_timezone_metadata_is_factual_only(self):
        evidence = style_c_event.build_evidence(raw(empire()), ROWS, asset="xauusd",
                                                as_of=AS_OF, batch_id="test", price_meta={})
        self.assertEqual(evidence["identity"]["analysis_mode"], "post_event_factual_only")
        self.assertFalse(evidence["reaction"]["timezone_normalized"])
        self.assertIn("timezone_unverified", evidence["skip_reasons"])

    def test_registry_based_unverified_timezone_check_is_accepted(self):
        meta = copy.deepcopy(PRICE_META)
        meta["timezone_check"].update({"verified": False, "measured_offset_minutes": None,
                                       "reason": "วัดไม่ได้ในรอบนี้ — ใช้ค่าในทะเบียน"})
        evidence = style_c_event.build_evidence(raw(empire()), ROWS, asset="xauusd",
                                                as_of=AS_OF, batch_id="test", price_meta=meta)
        self.assertEqual(evidence["identity"]["analysis_mode"], "post_event")
        self.assertTrue(evidence["reaction"]["timezone_normalized"])

    def test_runtime_contract_detects_missing_nested_provenance(self):
        evidence = style_c_event.build_evidence(raw(empire()), ROWS, asset="xauusd",
                                                as_of=AS_OF, batch_id="test",
                                                price_meta=PRICE_META)
        del evidence["provenance"]["calendar"]["payload_sha256"]
        self.assertIn("provenance.calendar.payload_sha256",
                      style_c_event.validate_contract(evidence))

    def test_json_schema_declares_nested_contract(self):
        schema = json.loads((ROOT / "schemas" / "style-c-event-evidence-v1.schema.json")
                            .read_text(encoding="utf-8"))
        self.assertIn("provenance", schema["allOf"][0]["then"]["required"])
        self.assertIn("event", schema["$defs"])
        self.assertIn("reaction", schema["$defs"])
        self.assertIn("payload_sha256", schema["$defs"]["source"]["required"])


class IntegrationTests(unittest.TestCase):
    def _build(self, events, rows=ROWS, publish=False, seed_stale_c=False,
               seed_stale_chart=False, m5_rows=SYNTHETIC_TEST_ONLY_M5_ROWS,
               m5_meta=PRICE_META):
        from tools import build_daily_package
        fixture = ROOT / "tests" / "fixtures" / "wcb-snapshot-xauusd.json"
        folder = tempfile.TemporaryDirectory()
        root = Path(folder.name)
        snapshot = root / "snapshot.json"
        snapshot.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
        if seed_stale_chart:
            stale_chart_dir = root / "work" / "style-c-test" / "xauusd" / "internal" / "public-line" / "drafts"
            stale_chart_dir.mkdir(parents=True, exist_ok=True)
            (stale_chart_dir / "xauusd-style-c-old-m5.webp").write_bytes(b"stale")
        if publish and seed_stale_c:
            from tools import publish_layout, wcb_writers
            stale_dir = root / "out" / publish_layout.day_folder(AS_OF.isoformat()) / wcb_writers.by_id("c_event")["folder"]
            stale_dir.mkdir(parents=True, exist_ok=True)
            (stale_dir / "xauusd.md").write_text("stale", encoding="utf-8")

        def event_feed(_asset, _start, _end):
            return raw(*events)

        def price_feed(_asset, **kwargs):
            selected = m5_rows if kwargs.get("timeframe") == "5min" else rows
            selected_meta = m5_meta if kwargs.get("timeframe") == "5min" else PRICE_META
            return (copy.deepcopy(selected_meta), copy.deepcopy(selected),
                    f"fixture {kwargs.get('timeframe')}")

        result = build_daily_package.build_public(
            "xauusd", batch_id="style-c-test", output_root=root / "work",
            publish_root=(root / "out") if publish else None, snapshot_path=snapshot,
            cutoff_at=AS_OF.isoformat(), max_age_minutes=10**9,
            event_calendar_fetcher=event_feed, event_intraday_fetcher=price_feed)
        return folder, root, result

    def test_no_event_skips_only_c_and_ab_pass(self):
        folder, root, result = self._build([], seed_stale_chart=True)
        try:
            self.assertEqual(result["drafts"]["c_event"]["status"], "skipped")
            self.assertEqual(result["drafts"]["a_standard"]["status"], "pass")
            self.assertEqual(result["drafts"]["b_technical"]["status"], "pass")
            self.assertTrue(result["content_ok"])
            draft_dir = root / "work" / "style-c-test" / "xauusd" / "internal" / "public-line" / "drafts"
            self.assertFalse((draft_dir / "c_event.md").exists())
            self.assertFalse(list(draft_dir.glob("xauusd-style-c-*.webp")))
            artifact = json.loads((draft_dir.parent / "style-c-event-evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(artifact["skip_reasons"], ["no_eligible_released_event"])
        finally:
            folder.cleanup()

    def test_post_event_draft_is_internal_and_not_published(self):
        folder, root, result = self._build([empire()], publish=True, seed_stale_c=True)
        try:
            self.assertEqual(result["drafts"]["c_event"]["status"], "pass",
                             msg=str(result["drafts"]["c_event"].get("validation")))
            article = (root / "work" / "style-c-test" / "xauusd" / "internal" /
                       "public-line" / "drafts" / "c_event.md").read_text(encoding="utf-8")
            from tools import headline_format, wcb_source, wcb_writers
            snapshot = json.loads((root / "snapshot.json").read_text(encoding="utf-8"))
            daily = wcb_source.normalize(snapshot)
            self.assertIn(headline_format.prefix("xauusd", "2026-08-17", full_month=True), article)
            self.assertNotIn(headline_format.prefix("xauusd", "2026-08-05", full_month=True), article)
            self.assertNotIn("[[chart:", article)
            self.assertNotIn("สัญญาณรายวันเป็นบริบท", article)
            self.assertNotIn("snapshot", article.lower())
            self.assertNotIn("ระบบ", article)
            self.assertNotIn("ทะเบียน", article)
            self.assertIn("ปฏิทินเศรษฐกิจ WorldClassBroker", article)
            for internal_token in ("factual-only", "post_event", "not_applicable"):
                self.assertNotIn(internal_token, article)
            count = result["drafts"]["c_event"]["validation"]["word_count"]
            self.assertGreaterEqual(count, wcb_writers.by_id("c_event")["post_event_min_words"])
            self.assertLessEqual(count, wcb_writers.by_id("c_event")["post_event_max_words"])
            self.assertEqual(len([line for line in article.splitlines() if line.startswith("## ")]), 3)
            stale_numbers = [wcb_writers.price(daily["quote"]["price"], daily)]
            stale_numbers += [wcb_writers.price(item, daily)
                              for item in wcb_source.pivot_values(daily)]
            for stale in stale_numbers:
                self.assertNotIn(stale, article, f"เลข daily snapshot คนละวันหลุดเข้า Style C: {stale}")
            self.assertIn("ต่ำกว่าฐานเล็กน้อย", article)
            self.assertIn("กลับเหนือฐาน", article)
            for phrase in style_c_event.load_registry()["causal_banned_phrases"]:
                self.assertNotIn(phrase, article)
            c_publish = next(item for item in result["published"]["writers"]
                             if item["writer_id"] == "c_event")
            self.assertEqual(c_publish["status"], "skipped")
            self.assertEqual(c_publish["reason_codes"], ["internal_only"])
            self.assertTrue(c_publish["removed_stale"])
            self.assertEqual(result["published"]["silent_drops"], [])
            self.assertFalse(list((root / "out").rglob("C-อิงเหตุการณ์/xauusd.md")))
            artifact_path = root / "work" / "style-c-test" / "xauusd" / "internal" / "public-line" / "style-c-event-evidence.json"
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            chart = artifact["chart"]
            chart_source = artifact["provenance"]["chart_price"]
            self.assertEqual(chart_source["timeframe"], "5min")
            self.assertEqual(chart_source["cadence_minutes"], 5)
            self.assertEqual(len(chart_source["payload_sha256"]), 64)
            self.assertTrue(chart_source["timezone_check"]["verified"])
            self.assertEqual(artifact["reaction"]["timeframe"], "30min")
            chart_path = artifact_path.parent / "drafts" / chart["filename"]
            self.assertTrue(chart_path.is_file())
            self.assertEqual(chart["candle_count"], 27)
            self.assertEqual(chart["body_count"], 27)
            self.assertEqual(chart["wick_count"], 27)
            self.assertEqual(chart["close_marker_count"], 5)
            self.assertEqual(chart["m30_anchor_count"], 5)
            self.assertEqual(chart["window"], ["2026-08-17T19:15:00+07:00",
                                               "2026-08-17T21:30:00+07:00"])
            self.assertEqual(len(chart["close_labels_th"]), 27)
            self.assertNotIn("12:30", chart["close_labels_th"])
            import hashlib
            self.assertEqual(hashlib.sha256(chart_path.read_bytes()).hexdigest(), chart["sha256"])
            self.assertIn(f"]({chart['filename']})", article)
            self.assertIn("*กราฟ M5 วันที่ 17 ส.ค. 2026 เวลาไทย 19:15–21:30 น.;", article)
            self.assertIn("ตัวเลขในบทคำนวณจากแท่ง M30", article)
            self.assertNotIn("แหล่งราคาจาก WorldClassBroker", article)
            self.assertIn("เส้นประคือเวลาตามกำหนดที่ประกาศข่าว", article)
            self.assertIn("ไม่ได้ยืนยันว่าข่าวเป็นสาเหตุของราคา", article)
        finally:
            folder.cleanup()

    def test_long_parenthetical_event_title_is_complete_and_spaced(self):
        from tools import wcb_writers
        long_title = "ดัชนีภาคการผลิตรัฐนิวยอร์ก (Empire State)"
        folder, _root, result = self._build([empire(title_th=long_title)])
        try:
            article = result["drafts"]["c_event"]["markdown"]
            title = next(line.removeprefix("title: ") for line in article.splitlines()
                         if line.startswith("title: "))
            excerpt = next(line.removeprefix("excerpt: ") for line in article.splitlines()
                           if line.startswith("excerpt: "))
            self.assertLessEqual(len(title), wcb_writers.TITLE_MAX)
            self.assertEqual(title.count("("), title.count(")"))
            self.assertNotIn("(Empire", title)
            self.assertNotIn(")ประกาศ", article)
            self.assertIn("ดัชนีภาคการผลิตรัฐนิวยอร์ก ประกาศที่", excerpt)
            self.assertIn("ดัชนีภาคการผลิตรัฐนิวยอร์ก ของสหรัฐประกาศแล้ว", article)
            clipped = wcb_writers.fit_title("ก" * 70 + " (Empire State alias long enough)")
            self.assertEqual(clipped.count("("), clipped.count(")"))
            self.assertLessEqual(len(clipped), wcb_writers.TITLE_MAX)
        finally:
            folder.cleanup()

    def test_factual_only_omits_reaction_direction_mechanism_and_missing_previous(self):
        from tools import wcb_writers
        folder, _root, result = self._build([empire(previous=None)])
        try:
            c = result["drafts"]["c_event"]
            self.assertEqual(c["status"], "pass", msg=str(c.get("validation")))
            article = c["markdown"]
            for internal_token in ("factual-only", "post_event", "not_applicable"):
                self.assertNotIn(internal_token, article)
            self.assertNotIn("4389.28067", article)
            self.assertNotIn("กลไกที่เป็นไปได้", article)
            self.assertNotIn("ครั้งก่อน 15.6", article)
            self.assertIn("ปฏิทินเศรษฐกิจ WorldClassBroker", article)
            self.assertGreaterEqual(c["validation"]["word_count"],
                                    wcb_writers.by_id("c_event")["post_event_min_words"])
            self.assertLessEqual(c["validation"]["word_count"],
                                 wcb_writers.by_id("c_event")["post_event_max_words"])
            self.assertNotIn("xauusd-style-c-398376-m5.webp", article)
            self.assertNotIn("![กราฟ", article)
            artifact_path = (_root / "work" / "style-c-test" / "xauusd" / "internal" /
                             "public-line" / "style-c-event-evidence.json")
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertIsNone(artifact.get("chart"))
            self.assertFalse(list((artifact_path.parent / "drafts").glob(
                "xauusd-style-c-*.webp")))
        finally:
            folder.cleanup()

    def test_partial_three_and_four_bars_create_no_chart_or_embed(self):
        for rows in (ROWS[:3], ROWS[:4]):
            folder, root, result = self._build([empire()], rows=rows)
            try:
                c = result["drafts"]["c_event"]
                self.assertEqual(c["status"], "pass", msg=str(c.get("validation")))
                self.assertNotIn("![กราฟ", c["markdown"])
                artifact_path = (root / "work" / "style-c-test" / "xauusd" / "internal" /
                                 "public-line" / "style-c-event-evidence.json")
                artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
                self.assertEqual(artifact["identity"]["analysis_mode"],
                                 "post_event_factual_only")
                self.assertIsNone(artifact.get("chart"))
                self.assertFalse(list((artifact_path.parent / "drafts").glob(
                    "xauusd-style-c-*.webp")))
            finally:
                folder.cleanup()

    def test_missing_or_gapped_m5_keeps_m30_article_without_chart(self):
        cases = (SYNTHETIC_TEST_ONLY_M5_ROWS[:-1],
                 SYNTHETIC_TEST_ONLY_M5_ROWS[:10] + SYNTHETIC_TEST_ONLY_M5_ROWS[11:])
        for m5_rows in cases:
            folder, root, result = self._build([empire()], m5_rows=m5_rows)
            try:
                c = result["drafts"]["c_event"]
                self.assertEqual(c["status"], "pass")
                self.assertTrue(result["content_ok"])
                self.assertNotIn("![กราฟ", c["markdown"])
                artifact = json.loads((root / "work" / "style-c-test" / "xauusd" /
                                       "internal" / "public-line" /
                                       "style-c-event-evidence.json").read_text(
                                           encoding="utf-8"))
                self.assertEqual(artifact["identity"]["analysis_mode"], "post_event")
                self.assertEqual(artifact["chart_reaction"]["status"],
                                 "insufficient_bars")
                self.assertEqual(artifact["chart_status"]["status"], "unavailable")
                self.assertIn("m5_window_incomplete",
                              artifact["chart_status"]["reason_codes"])
                self.assertIsNone(artifact.get("chart"))
            finally:
                folder.cleanup()

    def test_unverified_m5_timezone_keeps_m30_article_without_chart(self):
        meta = copy.deepcopy(PRICE_META)
        meta["timezone_check"]["verified"] = False
        folder, root, result = self._build([empire()], m5_meta=meta)
        try:
            c = result["drafts"]["c_event"]
            self.assertEqual(c["status"], "pass")
            self.assertTrue(result["content_ok"])
            self.assertNotIn("![กราฟ", c["markdown"])
            artifact_path = (root / "work" / "style-c-test" / "xauusd" / "internal" /
                             "public-line" / "style-c-event-evidence.json")
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertIn("m5_timezone_unverified",
                          artifact["chart_reaction"]["violations"])
            self.assertIn("m5_timezone_unverified",
                          artifact["chart_status"]["reason_codes"])
            self.assertIsNone(artifact.get("chart"))
            self.assertFalse(list((artifact_path.parent / "drafts").glob("*.webp")))
        finally:
            folder.cleanup()

    def test_each_anchor_mismatch_keeps_m30_article_without_chart(self):
        for anchor_index in (2, 8, 14, 20, 26):
            rows = copy.deepcopy(SYNTHETIC_TEST_ONLY_M5_ROWS)
            rows[anchor_index]["close"] += .02
            folder, root, result = self._build([empire()], m5_rows=rows)
            try:
                c = result["drafts"]["c_event"]
                self.assertEqual(c["status"], "pass")
                self.assertTrue(result["content_ok"])
                self.assertNotIn("![กราฟ", c["markdown"])
                artifact_path = (root / "work" / "style-c-test" / "xauusd" / "internal" /
                                 "public-line" / "style-c-event-evidence.json")
                artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
                self.assertIn("m5_m30_anchor_mismatch",
                              artifact["chart_reaction"]["violations"])
                self.assertIn("m5_m30_anchor_mismatch",
                              artifact["chart_status"]["reason_codes"])
                self.assertEqual(sum(not item["match"] for item in
                                     artifact["chart_reaction"]["anchor_checks"]), 1)
                self.assertIsNone(artifact.get("chart"))
                self.assertFalse(list((artifact_path.parent / "drafts").glob("*.webp")))
            finally:
                folder.cleanup()

    def test_build_rejects_rendered_c_below_style_minimum(self):
        from tools import wcb_writers
        writer = wcb_writers.by_id("c_event")
        with mock.patch.dict(writer, {"post_event_min_words": 10**6}):
            folder, _root, result = self._build([empire()])
        try:
            c = result["drafts"]["c_event"]
            self.assertEqual(c["status"], "fail")
            self.assertFalse(result["content_ok"])
            self.assertTrue(any(item["rule"] == "style_word_floor"
                                for item in c["validation"]["findings"]))
        finally:
            folder.cleanup()

    def test_chart_renderer_unavailable_keeps_m30_article_without_broken_embed(self):
        from tools import style_c_event_chart
        with mock.patch.object(style_c_event_chart, "render", side_effect=ValueError("boom")):
            folder, _root, result = self._build([empire()])
        try:
            c = result["drafts"]["c_event"]
            self.assertEqual(c["status"], "pass")
            self.assertTrue(result["content_ok"])
            self.assertNotIn(".webp)", c["markdown"])
        finally:
            folder.cleanup()

    def test_causal_phrase_is_fatal(self):
        from tools import wcb_copy_validator
        folder, root, result = self._build([empire()])
        try:
            article = result["drafts"]["c_event"]["markdown"] + "\nทองขึ้นเพราะข่าว\n"
            snapshot = json.loads((root / "snapshot.json").read_text(encoding="utf-8"))
            artifact = json.loads((root / "work" / "style-c-test" / "xauusd" / "internal" /
                                   "public-line" / "style-c-event-evidence.json").read_text(encoding="utf-8"))
            checked = wcb_copy_validator.validate(article, snapshot, event_evidence=artifact)
            self.assertTrue(any(item["rule"] == "causal_phrase_forbidden"
                                for item in checked["findings"]))
        finally:
            folder.cleanup()


if __name__ == "__main__":
    unittest.main()
