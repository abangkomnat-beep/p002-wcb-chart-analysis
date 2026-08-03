import importlib.util
import inspect
import json
import math
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "pilot_generator.py"


def load_module():
    spec = importlib.util.spec_from_file_location("pilot_generator", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PilotGeneratorTests(unittest.TestCase):
    def test_enrich_snapshot_contract_adds_required_provenance(self):
        mod = load_module()
        snapshot = {
            "asset": "xauusd",
            "generated_at": "2026-08-03T01:44:28.873Z",
            "source_path": "input.json",
            "quote": {"price": 4048.39},
            "technicals": {"pivots": {"p": 4042.82}},
        }

        self.assertTrue(hasattr(mod, "enrich_snapshot_contract"))
        result = mod.enrich_snapshot_contract(snapshot, "xauusd")

        self.assertEqual(result["instrument"]["instrument_type"], "spot")
        self.assertEqual(result["instrument"]["unit"], "USD/oz")
        self.assertEqual(result["instrument"]["timezone"], "Asia/Bangkok")
        self.assertEqual(result["instrument"]["data_status"], "locked_snapshot")
        self.assertIn("technicals.pivots", result["approved_level_sources"])
        self.assertGreaterEqual(len(result["source_log"]), 3)
        for entry in result["source_log"]:
            self.assertIn("field", entry)
            self.assertIn("value", entry)
            self.assertIn("source", entry)
            self.assertIn("published_at", entry)
            self.assertIn("retrieved_at", entry)
            self.assertIn("reviewer", entry)

    def test_compute_classic_pivots_uses_previous_completed_candle(self):
        mod = load_module()
        rows = [
            {"date": "2026-08-01", "open": 99.0, "high": 110.0, "low": 90.0, "close": 100.0},
            {"date": "2026-08-03", "open": 101.0, "high": 104.0, "low": 98.0, "close": 102.0},
        ]

        pivots = mod.compute_classic_pivots(rows)

        self.assertAlmostEqual(pivots["p"], 100.0)
        self.assertAlmostEqual(pivots["r1"], 110.0)
        self.assertAlmostEqual(pivots["s1"], 90.0)
        self.assertAlmostEqual(pivots["r2"], 120.0)
        self.assertAlmostEqual(pivots["s2"], 80.0)

    def test_format_volatility_metric_does_not_mislabel_five_day_range_as_atr14(self):
        mod = load_module()

        self.assertEqual(
            mod.format_volatility_metric({"atr14": 2.5}, decimals=2),
            "ATR 14: 2.50",
        )
        self.assertEqual(
            mod.format_volatility_metric({"atr14": None, "range5_max": 90.94}, decimals=2),
            "5D max range: 90.94",
        )

    def test_normalize_ohlc_expands_bounds_to_include_open_and_close(self):
        mod = load_module()

        row = mod.normalize_ohlc({
            "date": "2026-08-03",
            "open": 63497.25,
            "high": 63497.25,
            "low": 62988.29,
            "close": 62972.08,
        })

        self.assertEqual(row["high"], 63497.25)
        self.assertEqual(row["low"], 62972.08)
        self.assertLessEqual(row["low"], row["close"])
        self.assertGreaterEqual(row["high"], row["open"])

    def test_compute_indicators_returns_traceable_values(self):
        mod = load_module()
        rows = []
        for i in range(60):
            close = 100 + i * 0.5 + math.sin(i / 3)
            rows.append({
                "date": f"2026-06-{(i % 28) + 1:02d}",
                "open": close - 0.2,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
            })

        result = mod.compute_indicators(rows)

        self.assertEqual(result["points"], 60)
        self.assertIsInstance(result["sma20"], float)
        self.assertIsInstance(result["sma50"], float)
        self.assertGreaterEqual(result["rsi14"], 0)
        self.assertLessEqual(result["rsi14"], 100)
        self.assertGreater(result["atr14"], 0)
        self.assertGreater(result["resistance"], result["support"])

    def test_write_chart_uses_same_basename_and_writes_metadata(self):
        mod = load_module()
        self.assertIn("contract_metadata", inspect.signature(mod.write_chart).parameters)
        rows = []
        for i in range(60):
            close = 100 + i * 0.3
            rows.append({
                "date": f"2026-07-{(i % 28) + 1:02d}",
                "open": close - 0.1,
                "high": close + 0.8,
                "low": close - 0.8,
                "close": close,
            })
        analysis = mod.compute_indicators(rows)

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            result = mod.write_chart(
                rows=rows,
                analysis=analysis,
                output_dir=out_dir,
                basename="2026-08-03_forex-eurusd",
                title="EUR/USD test",
                source="Test source",
                decimals=4,
                contract_metadata={
                    "symbol": "EUR/USD",
                    "instrument_type": "forex_spot",
                    "cutoff_at": "2026-08-03T00:00:00Z",
                    "timezone": "Asia/Bangkok",
                    "data_status": "locked_snapshot",
                    "unit": "USD per EUR",
                },
            )

            self.assertEqual(result["image"].name, "2026-08-03_forex-eurusd.png")
            self.assertEqual(result["metadata"].name, "2026-08-03_forex-eurusd.chart.json")
            self.assertTrue(result["image"].is_file())
            meta = json.loads(result["metadata"].read_text(encoding="utf-8"))
            self.assertEqual(meta["basename"], "2026-08-03_forex-eurusd")
            self.assertEqual(meta["source"], "Test source")
            self.assertEqual(meta["instrument_type"], "forex_spot")
            self.assertEqual(meta["data_status"], "locked_snapshot")
            self.assertIn("caption", meta)
            self.assertIn("alt_text", meta)
            self.assertEqual(meta["annotations"]["s1"], analysis["pivots"]["s1"])
            self.assertEqual(meta["annotations"]["r1"], analysis["pivots"]["r1"])
            self.assertEqual(meta["annotations"]["p"], analysis["pivots"]["p"])
            self.assertEqual(meta["annotations"]["r3"], analysis["pivots"]["r3"])
            self.assertEqual(meta["annotations"]["s3"], analysis["pivots"]["s3"])


if __name__ == "__main__":
    unittest.main()
