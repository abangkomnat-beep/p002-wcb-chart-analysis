import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import data_fetch_retry  # noqa: E402


class DataFetchRetryTests(unittest.TestCase):
    def test_second_attempt_success_returns_value_and_stops(self):
        attempts = []

        def operation():
            attempts.append(len(attempts) + 1)
            if len(attempts) == 1:
                raise RuntimeError("provider timeout")
            return {"closed": 42}

        self.assertEqual(
            data_fetch_retry.run_with_one_retry(
                operation, asset="xauusd", timeframe="H1"),
            {"closed": 42})
        self.assertEqual(attempts, [1, 2])

    def test_two_failures_report_asset_timeframe_and_both_errors(self):
        attempts = []

        def operation():
            attempts.append(1)
            raise ValueError(f"bad payload {len(attempts)}")

        with self.assertRaises(data_fetch_retry.DataFetchUnavailable) as raised:
            data_fetch_retry.run_with_one_retry(
                operation, asset="gbpusd", timeframe="15min")
        error = raised.exception
        self.assertEqual(attempts, [1, 1])
        self.assertEqual((error.asset, error.timeframe), ("gbpusd", "15min"))
        self.assertEqual(len(error.failures), 2)
        self.assertIn("attempt 1", str(error))
        self.assertIn("attempt 2", str(error))
        self.assertIn("bad payload 2", str(error))


if __name__ == "__main__":
    unittest.main()
