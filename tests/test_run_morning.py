"""P0 contract ของ Morning Editorial Command — ไม่ยิง API และไม่แตะ output จริง."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import run_morning  # noqa: E402


RUN_DATE = date(2026, 8, 14)
NOW = datetime(2026, 8, 14, 1, 0, tzinfo=timezone.utc)
MONDAY = date(2026, 8, 31)


class PlanRules(unittest.TestCase):

    def make(self, **kwargs):
        return run_morning.build_plan(run_date=RUN_DATE, now=NOW, **kwargs)

    def test_no_write_means_gold_only(self):
        plan = self.make()
        self.assertEqual(plan["write_assets"], ["xauusd"])
        self.assertEqual(plan["ownership"]["xauusd"], "natthaphon-s")

    def test_monday_automatically_adds_wti_after_gold(self):
        plan = run_morning.build_plan(run_date=MONDAY, now=NOW)
        self.assertEqual(plan["write_assets"], ["xauusd", "wtiusd"])
        self.assertEqual(plan["ownership"]["wtiusd"], "natthaphon-s")
        self.assertEqual(plan["ownership"]["default"], "world-class-broker-team")

    def test_monday_wti_cannot_be_excluded(self):
        with self.assertRaisesRegex(run_morning.MorningPlanError, "งด wtiusd ไม่ได้"):
            run_morning.build_plan(run_date=MONDAY, now=NOW, exclude=["wtiusd"])

    def test_selected_assets_are_only_gold_plus_user_choices(self):
        plan = self.make(write=["EURUSD", "btcusd", "eurusd"])
        self.assertEqual(plan["write_assets"], ["xauusd", "eurusd", "btcusd"])
        self.assertNotIn("nvda", plan["write_assets"])
        self.assertEqual(plan["ownership"]["default"], "world-class-broker-team")

    def test_watch_does_not_create_articles(self):
        plan = self.make(watch=["USD", "btc"])
        self.assertEqual(plan["write_assets"], ["xauusd"])
        self.assertEqual(plan["watch_topics"], ["usd", "btc"])

    def test_watch_topic_must_be_machine_safe(self):
        with self.assertRaisesRegex(run_morning.MorningPlanError, "watch topic"):
            run_morning.validate_plan(self.make(watch=["ข่าว USD"]))

    def test_write_and_watch_may_overlap_but_exclude_may_not(self):
        plan = self.make(write=["btcusd"], watch=["btcusd"])
        self.assertIn("btcusd", plan["write_assets"])
        with self.assertRaisesRegex(run_morning.MorningPlanError, "ขัดแย้ง"):
            self.make(write=["btcusd"], exclude=["btcusd"])
        with self.assertRaisesRegex(run_morning.MorningPlanError, "ขัดแย้ง"):
            self.make(watch=["nvda"], exclude=["nvda"])

    def test_gold_cannot_be_excluded(self):
        with self.assertRaisesRegex(run_morning.MorningPlanError, "งด xauusd ไม่ได้"):
            self.make(exclude=["xauusd"])

    def test_unknown_asset_fails_with_supported_values(self):
        with self.assertRaisesRegex(run_morning.MorningPlanError, "รองรับ:"):
            self.make(write=["dogeusd"])

    def test_schema_file_matches_runtime_contract(self):
        schema = json.loads((Path(__file__).parents[1] / "schemas" /
                             "morning-editorial-plan-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["timezone"]["const"], "Asia/Bangkok")
        self.assertEqual(schema["properties"]["ownership"]["properties"]["xauusd"]["const"],
                         "natthaphon-s")
        self.assertEqual(schema["properties"]["ownership"]["properties"]["wtiusd"]["const"],
                         "natthaphon-s")
        run_morning.validate_plan(self.make())


class PreviewAndExecution(unittest.TestCase):

    def test_preview_does_not_write_or_call_production(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(run_morning.run_daily, "main") as production:
            code = run_morning.main([
                "--date", RUN_DATE.isoformat(), "--write", "eurusd",
                "--plan-root", folder,
            ])
            self.assertEqual(code, 0)
            production.assert_not_called()
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_confirm_passes_only_planned_assets_and_selects_gold_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plan = run_morning.build_plan(write=["eurusd", "btcusd"],
                                           run_date=RUN_DATE, confirmed=True, now=NOW)
            target = root / "plan.json"
            with mock.patch.object(run_morning.run_daily, "main", return_value=0) as production, \
                    mock.patch.object(run_morning, "verify_author_ownership", return_value=[]), \
                    mock.patch.object(run_morning.publish_selection, "select", return_value={
                        "status": "ready", "article": "gold.md"}) as selection:
                code = run_morning.run_confirmed(plan, target=target, output_root=root / "output")
            self.assertEqual(code, 0)
            self.assertEqual(production.call_args.args[0], [
                "--asset", "xauusd", "--asset", "eurusd", "--asset", "btcusd",
                "--skip-selection",
            ])
            selection.assert_called_once()
            saved = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "completed")
            self.assertEqual(saved["exit_code"], 0)

    def test_second_confirmed_run_is_blocked_before_production(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "plan.json"
            plan = run_morning.build_plan(run_date=RUN_DATE, confirmed=True, now=NOW)
            run_morning.save_plan(target, plan)
            with mock.patch.object(run_morning.run_daily, "main") as production:
                with self.assertRaisesRegex(run_morning.MorningPlanError, "ปฏิเสธการรันซ้ำ"):
                    run_morning.run_confirmed(plan, target=target, output_root=root / "output")
            production.assert_not_called()

    def test_production_failure_is_written_to_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "plan.json"
            plan = run_morning.build_plan(run_date=RUN_DATE, confirmed=True, now=NOW)
            with mock.patch.object(run_morning.run_daily, "main", return_value=1), \
                    mock.patch.object(run_morning, "verify_author_ownership", return_value=[]), \
                    mock.patch.object(run_morning.publish_selection, "select") as selection:
                code = run_morning.run_confirmed(plan, target=target, output_root=root / "output")
            self.assertEqual(code, 1)
            selection.assert_not_called()
            saved = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "failed")

    def test_author_ownership_gate_flags_wrong_slug(self):
        with tempfile.TemporaryDirectory() as folder:
            day = Path(folder)
            (day / "xauusd.md").write_text(
                "---\nauthor_slug: world-class-broker-team\n---\n", encoding="utf-8")
            (day / "eurusd.md").write_text(
                "---\nauthor_slug: world-class-broker-team\n---\n", encoding="utf-8")
            findings = run_morning.verify_author_ownership(day, ["xauusd", "eurusd"])
            self.assertEqual(len(findings), 1)
            self.assertIn("natthaphon-s", findings[0])

    def test_author_ownership_gate_flags_missing_slug(self):
        with tempfile.TemporaryDirectory() as folder:
            day = Path(folder)
            (day / "xauusd.md").write_text("# บทที่ไม่มีผู้เขียน\n", encoding="utf-8")
            findings = run_morning.verify_author_ownership(day, ["xauusd"])
            self.assertEqual(len(findings), 1)
            self.assertIn("ไม่มี author_slug", findings[0])

    def test_author_ownership_gate_requires_personal_author_for_wti(self):
        with tempfile.TemporaryDirectory() as folder:
            day = Path(folder)
            (day / "wtiusd.md").write_text(
                "---\nauthor_slug: world-class-broker-team\n---\n", encoding="utf-8")
            findings = run_morning.verify_author_ownership(day, ["wtiusd"])
            self.assertEqual(len(findings), 1)
            self.assertIn("natthaphon-s", findings[0])


if __name__ == "__main__":
    unittest.main()
