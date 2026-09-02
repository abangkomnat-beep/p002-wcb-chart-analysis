import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import publish_selection, trade_plan_public_adapters  # noqa: E402


class MultiLaneSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.day = Path(self.tmp.name) / "output" / "31-08-2026"
        self.policy = publish_selection.load_policy()
        self._article("D-โครงสร้างกราฟ", "xauusd.md", "xauusd-levels-2026-08-31",
                      ["xauusd-d1-structure-2026-08-28.webp",
                       "xauusd-d1-levels-2026-08-28.webp",
                       "xauusd-weekly-calendar-2026-08-31.webp"])
        self._article("D-โครงสร้างกราฟ", "wtiusd.md", "wtiusd-levels-2026-08-31",
                      ["wtiusd-d1-structure-2026-08-28.webp",
                       "wtiusd-d1-levels-2026-08-28.webp",
                       "wtiusd-weekly-calendar-2026-08-31.webp"])
        self._article("E-อินดิเคเตอร์", "xauusd.md", "xauusd-signals-2026-08-31",
                      ["xauusd-h1-indicators-2026-08-31.webp"])
        self._article("M-BTCUSD-H1-Visual-Daily", "btc.md",
                      "btcusd-donchian-adx-2026-08-31",
                      ["btcusd-style-m-v6-h1-2026-08-31.webp"])
        for asset in ("eurusd", "usdjpy"):
            self._article("L-Forex-Daily", f"{asset}.md",
                          f"{asset}-forex-daily-plan-2026-08-31",
                          [f"{asset}-forex-daily-h1-plan.webp",
                           f"{asset}-forex-daily-m15-trigger.webp"])

    def _article(self, folder: str, name: str, slug: str, images: list[str]) -> None:
        target = self.day / folder
        target.mkdir(parents=True, exist_ok=True)
        refs = "\n".join(f"![chart]({image})" for image in images)
        extra_meta = ("cutoff: 2026-08-31T11:00:00+07:00\n"
                      if folder == "M-BTCUSD-H1-Visual-Daily" else "")
        footer = ("\n*หลักฐาน: ตัดข้อมูลเมื่อ 31/08/2026 11:34 น. เวลาไทย*\n"
                  if folder == "L-Forex-Daily" else "")
        article = target / name
        article.write_text(
            f"---\nslug: {slug}\n{extra_meta}---\n\n# test\n\n{refs}\n\n"
            f"RR ยังไม่หัก spread/slippage\n{footer}",
            encoding="utf-8")
        style = {
            "D-โครงสร้างกราฟ": "d_chart_story",
            "E-อินดิเคเตอร์": "e_indicator",
            "M-BTCUSD-H1-Visual-Daily": "m_btcusd_h1_visual_daily",
            "L-Forex-Daily": "l_forex_daily_plan",
        }[folder]
        asset = Path(name).stem
        contract = {
            "schema": "p002-public-trade-plan/v1",
            "style_id": style,
            "asset": asset,
            "article": name,
            "article_sha256": hashlib.sha256(article.read_bytes()).hexdigest(),
            "qa_status": "PASS_QA",
            "publishable": True,
            "plan_status": "WAIT_TRIGGER",
            "side": "BUY",
            "current_close": 99.0,
            "cutoff_at": "2026-08-31T11:00:00+07:00",
            "valid_until": "2026-09-01T11:00:00+07:00",
            "evidence_hash": "a" * 64,
            "rr_policy_version": "TPR-RR/v1",
            "plans": [{
                "side": "BUY",
                "trigger": {"condition": "closed bar above level", "value": 100.0},
                "entry_zone": {"low": 100.0, "high": 101.0},
                "stop_loss": 99.0,
                "take_profit": [103.0],
                "risk_reward": [1.0],
                "rr_basis": "gross_pre_cost",
                "invalidation": {"condition": "closed bar below structure", "value": 99.0},
            }],
        }
        if folder == "L-Forex-Daily":
            visible_plan = "\n".join([
                "| แผนสาธารณะ | **BUY** |",
                "| สถานะตอนนี้ | **WAIT_TRIGGER** |",
                "**แผนตามสถานการณ์**",
                "| Side | Trigger | Entry zone | Stop loss | Take profit | RR | Invalidation |",
                "| --- | --- | --- | --- | --- | --- | --- |",
                "| BUY | M15 ปิดเหนือ `100` | `100`–`101` | `99` | `103` | 1.00R | H1 ปิดต่ำกว่า `99` |",
                "- Cutoff at: `2026-08-31T11:00:00+07:00`",
                "- Valid until: `2026-09-01T11:00:00+07:00`",
                "- Evidence hash: `" + "a" * 64 + "`",
                "- RR ยังไม่หัก spread/slippage",
            ])
        elif folder == "M-BTCUSD-H1-Visual-Daily":
            # M7 requires the two-sided scenario table before its OCO block.
            contract.update({
                "side": "OCO",
                "plans": [
                    {
                        "side": "BUY",
                        "trigger": {"condition": "closed_h1_strict_cross", "value": 100.0},
                        "entry_zone": {"low": 100.0, "high": 101.0},
                        "stop_loss": 99.0, "take_profit": [103.0, 105.0],
                        "risk_reward": [1.0, 2.0], "rr_basis": "gross_pre_cost",
                        "invalidation": {"condition": "closed H1 reaches stop after trigger", "value": 99.0},
                    },
                    {
                        "side": "SELL",
                        "trigger": {"condition": "closed_h1_strict_cross", "value": 98.0},
                        "entry_zone": {"low": 97.0, "high": 98.0},
                        "stop_loss": 99.0, "take_profit": [93.0, 91.0],
                        "risk_reward": [2.0, 3.0], "rr_basis": "gross_pre_cost",
                        "invalidation": {"condition": "closed H1 reaches stop after trigger", "value": 99.0},
                    },
                ],
            })
            visible_plan = (
                "## 2. แผนการเทรดรายวัน (Trade Scenarios)\n\n"
                "| รายละเอียด | แผน Long (ฝั่งซื้อ) | แผน Short (ฝั่งขาย) |\n"
                "| :--- | :--- | :--- |\n"
                "| **เงื่อนไข Trigger** | แท่ง H1 ปิดเหนือ **100** | แท่ง H1 ปิดต่ำกว่า **98** |\n"
                "| **โซน Entry (หลัง Retest)** | **100 – 101** | **97 – 98** |\n"
                "| **Stop Loss (SL)** | **99** | **99** |\n"
                "| **Target Price (TP1 / TP2)** | **103 / 105** | **93 / 91** |\n"
                "## 3. จุดสร้างสภาพคล่องและโซนกับดักราคา (Liquidity Pools & Trap Zones)\n\n"
                "RR ยังไม่หัก spread/slippage\n"
            )
        else:
            visible_plan = trade_plan_public_adapters.public_plan_block(contract)
        article.write_text(
            article.read_text(encoding="utf-8").rstrip() + "\n\n"
            + visible_plan + "\n",
            encoding="utf-8")
        contract["article_sha256"] = hashlib.sha256(article.read_bytes()).hexdigest()
        contract_target = target / f"{asset}.trade-plan-public.json"
        if folder == "M-BTCUSD-H1-Visual-Daily":
            contract_target = (self.day.parent.parent / "work" / "build" /
                               self.day.name / "btcusd" / "internal" /
                               "style-m-v6" / f"{asset}.trade-plan-public.json")
            contract_target.parent.mkdir(parents=True, exist_ok=True)
        contract_target.write_text(json.dumps(contract), encoding="utf-8")
        for image in images:
            Image.new("RGB", (120, 80), "white").save(target / image, format="WEBP")

    def test_monday_has_six_articles_and_both_d_calendars(self):
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "ready")
        self.assertEqual((result["ready_count"], result["expected_count"]), (6, 6))
        root = Path(result["directory"])
        self.assertEqual(len(list(root.rglob("*.md"))), 6)
        self.assertEqual(len(list((root / "04-Forex-Style-L").glob("*.md"))), 2)
        self.assertTrue((root / "01-XAUUSD-Style-D" /
                         "xauusd-weekly-calendar-2026-08-31.webp").is_file())
        self.assertTrue((root / "03-WTIUSD-Style-D" /
                         "wtiusd-weekly-calendar-2026-08-31.webp").is_file())
        self.assertEqual(len(list(root.rglob("*.trade-plan-public.json"))), 3)
        report = json.loads((root / "selection-report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(all(item["trade_plan_contract"]["status"] == "PASS"
                            for item in report["lanes"]
                            if item["trade_plan_contract"] is not None))
        d_report = next(item for item in report["lanes"] if item["lane_id"] == "gold_d")
        self.assertIsNone(d_report["trade_plan_contract"])
        for contract_path in root.rglob("*.trade-plan-public.json"):
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            article = contract_path.with_name(contract["article"])
            self.assertEqual(
                contract["article_sha256"], hashlib.sha256(article.read_bytes()).hexdigest())
        self.assertFalse(any(path.name == "อ่านก่อน.md" for path in root.rglob("*")))

    def test_missing_one_forex_article_is_partial_and_stale_root_is_removed(self):
        stale = self.day / self.policy["selection_folder"] / "stale.txt"
        stale.parent.mkdir(parents=True)
        stale.write_text("old", encoding="utf-8")
        (self.day / "L-Forex-Daily" / "eurusd.md").unlink()
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "partial")
        self.assertEqual((result["ready_count"], result["expected_count"]), (5, 6))
        self.assertFalse(stale.exists())

    def test_policy_is_local_only(self):
        self.assertEqual(self.policy["schema_version"], 2)
        self.assertTrue(self.policy["manual_only"])
        self.assertFalse(self.policy["external_publish"])
        self.assertEqual(self.policy["network_authority"], "none")
        forex = next(lane for lane in self.policy["upload_lanes"] if lane["id"] == "forex_l")
        self.assertEqual(forex["max_articles"], 2)
        d_lane = next(lane for lane in self.policy["upload_lanes"] if lane["id"] == "gold_d")
        self.assertIsNone(d_lane["trade_plan_contract"])
        self.assertEqual(d_lane["images"], [
            "xauusd-d1-structure-*.webp", "xauusd-d1-levels-*.webp",
            "xauusd-weekly-calendar-*.webp",
        ])
        oil_lane = next(lane for lane in self.policy["upload_lanes"] if lane["id"] == "oil_d")
        self.assertEqual(oil_lane["destination_folder"], "03-WTIUSD-Style-D")
        self.assertEqual(oil_lane["assets"], ["wtiusd"])
        self.assertIsNone(oil_lane["trade_plan_contract"])
        btc_lane = next(lane for lane in self.policy["upload_lanes"] if lane["id"] == "btc_m")
        self.assertIsNone(btc_lane["trade_plan_contract"])
        self.assertEqual(btc_lane["internal_trade_plan_contract"],
                         "{asset}.trade-plan-public.json")
        self.assertTrue(all(lane["trade_plan_contract"] ==
                            "{asset}.trade-plan-public.json"
                            for lane in self.policy["upload_lanes"]
                            if lane["id"] not in {"gold_d", "oil_d", "btc_m"}))

    def test_btc_lane_requires_v6_image_name(self):
        btc = next(lane for lane in self.policy["upload_lanes"] if lane["id"] == "btc_m")
        self.assertEqual(btc["images"], ["btcusd-style-m-v6-h1-*.webp"])
        self.assertEqual(btc["slug_template"], "btcusd-donchian-adx-{date}")
        result = publish_selection.select(self.day, policy=self.policy)
        lane = next(item for item in result["lanes"] if item["id"] == "btc_m")
        self.assertEqual(lane["status"], "ready")
        self.assertEqual(lane["images"], ["btcusd-style-m-v6-h1-2026-08-31.webp"])

    def test_stale_chart_fails_only_its_lane(self):
        folder = self.day / "E-อินดิเคเตอร์"
        current = folder / "xauusd-h1-indicators-2026-08-31.webp"
        stale = folder / "xauusd-h1-indicators-2026-08-20.webp"
        current.rename(stale)
        article = folder / "xauusd.md"
        article.write_text(article.read_text(encoding="utf-8").replace(current.name, stale.name),
                           encoding="utf-8")
        contract_path = folder / "xauusd.trade-plan-public.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["article_sha256"] = hashlib.sha256(article.read_bytes()).hexdigest()
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "partial")
        self.assertEqual((result["ready_count"], result["expected_count"]), (5, 6))
        failed = next(item for item in result["lanes"] if item["id"] == "gold_e")
        self.assertIn("stale", failed["reason"])

    def test_block_qa_contract_fails_only_its_lane_and_is_not_copied(self):
        contract_path = self.day / "E-อินดิเคเตอร์" / "xauusd.trade-plan-public.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["qa_status"] = "BLOCK_QA"
        contract["publishable"] = False
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "partial")
        failed = next(item for item in result["lanes"] if item["id"] == "gold_e")
        self.assertEqual(failed["trade_plan_contract"]["status"], "FAIL")
        self.assertIn("HOLD_STATUS_PRESENT",
                      {item["code"] for item in
                       failed["trade_plan_contract"]["findings"]})
        root = Path(result["directory"])
        self.assertFalse((root / "02-XAUUSD-Style-E" / "xauusd.md").exists())

    def test_missing_contract_is_fail_closed_before_copy(self):
        (self.day.parent.parent / "work" / "build" / self.day.name / "btcusd" /
         "internal" / "style-m-v6" / "btc.trade-plan-public.json").unlink()
        result = publish_selection.select(self.day, policy=self.policy)
        failed = next(item for item in result["lanes"] if item["id"] == "btc_m")
        self.assertEqual(failed["status"], "failed")
        self.assertIn("ไม่มี trade-plan contract ใน internal_work", failed["reason"])
        self.assertFalse((Path(result["directory"]) / "05-BTCUSD-Style-M" / "btc.md").exists())


if __name__ == "__main__":
    unittest.main()
