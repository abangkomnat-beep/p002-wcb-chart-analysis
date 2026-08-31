from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import style_m_v6_daily as style_m_daily
from tools.m_unified_adapter import MProductionRoute
from tools.unified_registry import RegistryError


REGISTRY = Path(__file__).resolve().parents[1] / "config" / "article_styles.json"


class MRegistryContract(unittest.TestCase):
    def test_registration_matches_production_implementation(self):
        route = MProductionRoute.load()
        self.assertEqual(route.assets, ("btcusd",))
        self.assertTrue(route.production)

    def test_invalid_member_fails_closed(self):
        raw = json.loads(REGISTRY.read_text(encoding="utf-8"))
        raw["execution_units"]["M_BTCUSD_H1_VISUAL"]["members"] = ["e_indicator"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(RegistryError):
                MProductionRoute.load(path)

    def test_route_delegates_to_style_m_only(self):
        route = MProductionRoute.load()
        with mock.patch.object(style_m_daily, "run_round", return_value={"status": "pass"}) as runner:
            result = route.run_round(asset="btcusd", publish_root=Path("out"),
                                     cutoff_at="2026-08-29T12:00:00+07:00")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(runner.call_args.kwargs["asset"], "btcusd")

    def test_duplicate_hold_is_success_boundary_without_public_directory(self):
        held = {"status": "hold", "published": False, "shadow": "shadow",
                "index_policy": {"recommendation": "HOLD_DUPLICATE_NO_PLAN"},
                "state": "NO_PLAN"}
        route = MProductionRoute.load()
        with mock.patch.object(style_m_daily, "run_round", return_value=held) as runner:
            result = route.run_round(asset="btcusd", publish_root=Path("out"),
                                     work_root=Path("work"), cutoff_at="2026-08-29T12:00:00+07:00")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["outcome"], "HOLD_DUPLICATE_NO_PLAN")
        self.assertIsNone(result.get("directory"))
        self.assertNotIn("prior_fingerprint", runner.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
