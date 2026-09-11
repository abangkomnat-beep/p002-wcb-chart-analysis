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

from tools import article_continuity, publish_selection, trade_plan_public_adapters  # noqa: E402


class MultiLaneSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.day = Path(self.tmp.name) / "output" / "31-08-2026"
        self.policy = publish_selection.load_policy()
        # These fixtures exercise the retired copy-mode contract.  Production
        # now uses country_references and has dedicated no-copy tests.
        self.policy["delivery_layout"] = "selection_copy"
        self.policy["selection_folder"] = "0-ขึ้นเว็บวันนี้"
        self._article("D-โครงสร้างกราฟ", "xauusd.md", "xauusd-levels-2026-08-31",
                      ["xauusd-d1-structure-2026-08-28.webp",
                       "xauusd-d1-levels-2026-08-28.webp",
                       "xauusd-weekly-calendar-2026-08-31.webp"])
        self._article("D-โครงสร้างกราฟ", "wtiusd.md", "wtiusd-levels-2026-08-31",
                      ["wtiusd-d1-structure-2026-08-28.webp",
                       "wtiusd-d1-levels-2026-08-28.webp",
                       "wtiusd-weekly-calendar-2026-08-31.webp"])
        self._article("E-อินดิเคเตอร์", "xauusd.md", "xauusd-signals-2026-08-31",
                      ["xauusd-h1-fibonacci-2026-08-31.webp",
                       "xauusd-h1-trade-plan-2026-08-31.webp"])
        self._article("TH-Thailand/M/BTCUSD", "P002-20260831-TH-M-BTCUSD-article.md",
                      "btcusd-donchian-adx-2026-08-31",
                      ["P002-20260831-TH-M-BTCUSD-img01-market.webp",
                       "P002-20260831-TH-M-BTCUSD-img02-plan.webp"])
        for asset in ("eurusd", "usdjpy"):
            self._article("L-Forex-Daily", f"{asset}.md",
                          f"{asset}-forex-daily-plan-2026-08-31",
                          [f"{asset}-forex-daily-h1-plan.webp",
                           f"{asset}-forex-daily-m15-trigger.webp",
                           f"{asset}-forex-daily-calendar-2026-08-31.webp"])

    def test_gold_e_policy_requires_split_pair_and_forbids_legacy_pattern(self):
        lane = next(item for item in self.policy["upload_lanes"]
                    if item["id"] == "gold_e")
        self.assertEqual(lane["images"], [
            "xauusd-h1-fibonacci-*.webp",
            "xauusd-h1-trade-plan-*.webp",
        ])
        self.assertNotIn("xauusd-h1-indicators-*.webp", lane["images"])

    def _article(self, folder: str, name: str, slug: str, images: list[str]) -> None:
        target = self.day / folder
        target.mkdir(parents=True, exist_ok=True)
        refs = "\n".join(f"![chart]({image})" for image in images)
        if folder == "E-อินดิเคเตอร์":
            refs = "\n".join([
                f"![กราฟ Fibonacci H1 120 แท่งของ XAU/USD]({images[0]})",
                f"![กราฟแผน BUY H1 50 แท่งของ XAU/USD Entry 100–101 Current 99 SL 99 TP1 103]({images[1]})",
            ])
        extra_meta = ""
        # Style L freshness must come from its validated internal contract, not
        # from the removed public evidence footer.
        footer = ""
        article = target / name
        if folder == "TH-Thailand/M/BTCUSD":
            frontmatter = "asset: btc\ntitle: BTC test\nexcerpt: test\nauthor_slug: worldclassbroker-team"
        elif folder == "L-Forex-Daily":
            public_asset = "wti" if Path(name).stem == "wtiusd" else Path(name).stem
            frontmatter = (
                f"asset: {public_asset}\nslug: {slug}\n"
                "author_slug: worldclassbroker-team\ntrend: up")
        else:
            public_asset = "wti" if Path(name).stem == "wtiusd" else Path(name).stem
            frontmatter = (f"asset: {public_asset}\nslug: {slug}\n"
                           "author_slug: natthaphon-s")
        article.write_text(
            f"---\n{frontmatter}\n{extra_meta}---\n\n# test\n\n{refs}\n\n"
            f"{'' if folder == 'E-อินดิเคเตอร์' else 'RR ยังไม่หัก spread/slippage'}\n{footer}",
            encoding="utf-8")
        style = {
            "D-โครงสร้างกราฟ": "d_chart_story",
            "E-อินดิเคเตอร์": "e_indicator",
            "TH-Thailand/M/BTCUSD": "m_btcusd_h1_visual_daily",
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
        elif folder == "TH-Thailand/M/BTCUSD":
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
        elif folder == "E-อินดิเคเตอร์":
            visible_plan = ""
        else:
            visible_plan = trade_plan_public_adapters.public_plan_block(contract)
        article.write_text(
            article.read_text(encoding="utf-8").rstrip()
            + (("\n\n" + visible_plan) if visible_plan else "") + "\n",
            encoding="utf-8")
        contract["article_sha256"] = hashlib.sha256(article.read_bytes()).hexdigest()
        contract_target = target / f"{asset}.trade-plan-public.json"
        internal_styles = {
            "E-อินดิเคเตอร์": (asset, "style-e"),
            "L-Forex-Daily": (asset, "style-l"),
            "TH-Thailand/M/BTCUSD": ("btcusd", "style-m-v6"),
        }
        if folder in internal_styles:
            internal_asset, internal_style = internal_styles[folder]
            contract_target = (self.day.parent.parent / "work" / "build" /
                               self.day.name / internal_asset / "internal" /
                               internal_style / f"{asset}.trade-plan-public.json")
            contract_target.parent.mkdir(parents=True, exist_ok=True)
        contract_target.write_text(json.dumps(contract), encoding="utf-8")
        for image in images:
            Image.new("RGB", (120, 80), "white").save(target / image, format="WEBP")

    def _replace_d_calendar_with_pages(self, asset: str,
                                       page_count: int = 3) -> list[str]:
        """Turn one frozen D calendar ref into deterministic synthetic pages."""
        folder = self.day / "D-โครงสร้างกราฟ"
        article = folder / f"{asset}.md"
        single = f"{asset}-weekly-calendar-2026-08-31.webp"
        pages = [
            f"{asset}-weekly-calendar-2026-08-31-p{page:02d}-of-{page_count:02d}.webp"
            for page in range(1, page_count + 1)
        ]
        page_refs = "\n".join(f"![calendar page {page}]({name})"
                              for page, name in enumerate(pages, start=1))
        text = article.read_text(encoding="utf-8")
        article.write_text(
            text.replace(f"![chart]({single})", page_refs), encoding="utf-8")
        (folder / single).unlink()
        for index, name in enumerate(pages, start=1):
            Image.new("RGB", (120, 80), (245 - index, 245, 245)).save(
                folder / name, format="WEBP")
        return pages

    def _save_selection_candidates(self) -> None:
        style_letters = {
            "d_chart_story": "D", "e_indicator": "E",
            "l_forex_daily_plan": "L", "m_btcusd_h1_visual_daily": "M",
        }
        contracts = {"D": "d_chart_story/v1", "E": "e_indicator/v1",
                     "L": "L-PROD/v1", "M": "M-PROD/v7"}
        for lane in self.policy["upload_lanes"]:
            if not lane.get("enabled", True) or 0 not in lane["schedule"]["weekdays"]:
                continue
            assets = publish_selection._lane_assets(lane, "2026-08-31")
            for raw_asset in assets:
                article_name = (lane["article"].replace("{asset}", raw_asset)
                                .replace("{date}", "2026-08-31")
                                .replace("{datecompact}", "20260831"))
                markdown = (self.day / lane["source_folder"] / article_name).read_text(
                    encoding="utf-8")
                asset = "btcusd" if raw_asset == "btc" else raw_asset
                style = style_letters[lane["style"]]
                evidence = {"fixture": True, "asset": asset, "style": style}
                seed = {
                    "schema": article_continuity.SCHEMA, "asset": asset,
                    "style": style, "contract": contracts[style], "locale": "th",
                    "cutoff": "2026-08-31T11:00:00+07:00",
                    "evidence_hash": article_continuity.digest(evidence),
                    "source_article_hash": article_continuity.digest(markdown),
                }
                record = {**seed, "revision": article_continuity.digest(seed),
                          "evidence": evidence, "markdown": markdown,
                          "article_hash": article_continuity.digest(markdown),
                          "question": "fixture?", "question_family": "reading",
                          "semantic_key": "fixture", "baseline_revision": None,
                          "update": None, "baseline_article_hash": None,
                          "continuity_reason": "fixture", "qc_pass": True}
                record["record_hash"] = article_continuity.digest(record)
                article_continuity.save_candidate(
                    self.day.parent.parent / "work" / "continuity", record, markdown)

    def _assert_missing_calendar_page_is_atomic(self, asset: str,
                                                lane_id: str,
                                                destination: str) -> None:
        pages = self._replace_d_calendar_with_pages(asset)
        initial = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(initial["status"], "ready")
        initial_lane = Path(initial["directory"]) / destination
        self.assertEqual(
            sorted(path.name for path in initial_lane.glob(
                f"{asset}-weekly-calendar-*.webp")), pages)

        missing = pages[1]
        (self.day / "D-โครงสร้างกราฟ" / missing).unlink()
        rerun = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(rerun["status"], "partial")
        failed = next(item for item in rerun["lanes"] if item["id"] == lane_id)
        self.assertEqual(failed["status"], "failed")
        self.assertIn(f"ภาพที่บทอ้างหาย: {missing}", failed["reason"])

        # The selector replaces the complete handoff tree.  No page from the
        # previous successful lane, and no partial current lane, may survive.
        root = Path(rerun["directory"])
        self.assertFalse((root / destination).exists())
        self.assertFalse(any(root.rglob(f"{asset}-weekly-calendar-*.webp")))
        self.assertFalse(any(self.day.glob(f".{self.policy['selection_folder']}.staging-*")))

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
        self.assertFalse(any(root.rglob("*.trade-plan-public.json")))
        report = json.loads((root / "selection-report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(all(item["trade_plan_contract"]["status"] == "PASS"
                            for item in report["lanes"]
                            if item["trade_plan_contract"] is not None))
        d_report = next(item for item in report["lanes"] if item["lane_id"] == "gold_d")
        self.assertIsNone(d_report["trade_plan_contract"])
        self.assertTrue(all(
            item.get("contract_storage") == "internal_work"
            for item in report["lanes"]
            if item["trade_plan_contract"] is not None))
        self.assertFalse(any(path.name == "อ่านก่อน.md" for path in root.rglob("*")))

    def test_complete_handoff_records_baseline_automatically_and_idempotently(self):
        self._save_selection_candidates()
        first = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(first["continuity"]["status"], "recorded")
        self.assertFalse(first["continuity"]["idempotent"])
        self.assertEqual(len(first["continuity"]["revisions"]), 6)
        second = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(second["continuity"]["status"], "recorded")
        self.assertTrue(second["continuity"]["idempotent"])
        store = self.day.parent.parent / "work" / "continuity"
        self.assertEqual(len(list((store / "delivery_batches").glob("*.json"))), 1)
        self.assertFalse(any(Path(first["directory"]).rglob("*.trade-plan-public.json")))
        self.assertFalse(any(Path(first["directory"]).rglob("*delivery*.json")))

    def test_daily_route_defers_baseline_until_final_guard(self):
        self._save_selection_candidates()
        with publish_selection.defer_continuity_until_final_guard():
            selected = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(selected["continuity"]["status"], "awaiting_final_guard")
        store = self.day.parent.parent / "work" / "continuity"
        self.assertFalse((store / "delivery_batches").exists())
        report = json.loads(Path(selected["selection_report"]).read_text(encoding="utf-8"))
        finalized = publish_selection.finalize_continuity(
            self.day, inventories=selected["lanes"], selection_report=report,
            target=Path(selected["directory"]))
        self.assertEqual(finalized["status"], "recorded")

    def test_monday_copies_every_referenced_calendar_page_for_xau_and_wti(self):
        expected = {
            asset: self._replace_d_calendar_with_pages(asset)
            for asset in ("xauusd", "wtiusd")
        }
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "ready")
        root = Path(result["directory"])
        destinations = {
            "xauusd": "01-XAUUSD-Style-D",
            "wtiusd": "03-WTIUSD-Style-D",
        }
        report = json.loads((root / "selection-report.json").read_text(encoding="utf-8"))
        for asset, pages in expected.items():
            with self.subTest(asset=asset):
                copied = sorted(path.name for path in
                                (root / destinations[asset]).glob(
                                    f"{asset}-weekly-calendar-*.webp"))
                self.assertEqual(copied, pages)
                lane_id = "gold_d" if asset == "xauusd" else "oil_d"
                lane = next(item for item in report["lanes"]
                            if item["lane_id"] == lane_id)
                self.assertTrue(set(pages) <= set(lane["images"]))

    def test_xau_missing_one_calendar_page_fails_lane_without_half_set(self):
        self._assert_missing_calendar_page_is_atomic(
            "xauusd", "gold_d", "01-XAUUSD-Style-D")

    def test_wti_missing_one_calendar_page_fails_lane_without_half_set(self):
        self._assert_missing_calendar_page_is_atomic(
            "wtiusd", "oil_d", "03-WTIUSD-Style-D")

    def test_missing_one_forex_article_is_partial_and_stale_root_is_removed(self):
        stale = self.day / self.policy["selection_folder"] / "stale.txt"
        stale.parent.mkdir(parents=True)
        stale.write_text("old", encoding="utf-8")
        (self.day / "L-Forex-Daily" / "eurusd.md").unlink()
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "partial")
        self.assertEqual((result["ready_count"], result["expected_count"]), (5, 6))
        self.assertFalse(stale.exists())

    def test_style_l_invalid_web_trend_is_fail_closed_before_copy(self):
        first = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(first["status"], "ready")
        article = self.day / "L-Forex-Daily" / "eurusd.md"
        article.write_text(article.read_text(encoding="utf-8").replace(
            "trend: up", "trend: neutral"), encoding="utf-8")

        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "partial")
        failed = next(item for item in result["lanes"]
                      if item["id"] == "forex_l" and item["asset"] == "eurusd")
        self.assertEqual(failed["status"], "failed")
        self.assertIn("trend ต้องเป็น up | dn | fl", failed["reason"])
        root = Path(result["directory"])
        self.assertFalse((root / "04-Forex-Style-L" / "eurusd.md").exists())
        self.assertTrue((root / "04-Forex-Style-L" / "usdjpy.md").is_file())

    def test_wti_internal_asset_tag_is_rejected_before_copy(self):
        article = self.day / "D-โครงสร้างกราฟ" / "wtiusd.md"
        article.write_text(article.read_text(encoding="utf-8").replace(
            "asset: wti", "asset: wtiusd", 1), encoding="utf-8")
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "partial")
        failed = next(item for item in result["lanes"]
                      if item["id"] == "oil_d" and item["asset"] == "wtiusd")
        self.assertEqual(failed["status"], "failed")
        self.assertIn("public asset ต้องเป็น wti", failed["reason"])
        self.assertFalse((Path(result["directory"]) / "03-WTIUSD-Style-D" /
                          "wtiusd.md").exists())

    def test_style_l_unknown_author_slug_is_fail_closed_before_copy(self):
        article = self.day / "L-Forex-Daily" / "eurusd.md"
        article.write_text(article.read_text(encoding="utf-8").replace(
            "author_slug: worldclassbroker-team",
            "author_slug: world-class-broker-team"), encoding="utf-8")

        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "partial")
        failed = next(item for item in result["lanes"]
                      if item["id"] == "forex_l" and item["asset"] == "eurusd")
        self.assertEqual(failed["status"], "failed")
        self.assertIn(
            "author_slug ต้องเป็น worldclassbroker-team", failed["reason"])
        self.assertFalse((Path(result["directory"]) / "04-Forex-Style-L" /
                          "eurusd.md").exists())

    def test_every_lane_rejects_author_slug_for_wrong_asset(self):
        btc_article = self.day / "TH-Thailand/M/BTCUSD/P002-20260831-TH-M-BTCUSD-article.md"
        btc_article.write_text(btc_article.read_text(encoding="utf-8").replace(
            "author_slug: worldclassbroker-team", "author_slug: natthaphon-s"),
            encoding="utf-8")
        gold_article = self.day / "E-อินดิเคเตอร์" / "xauusd.md"
        gold_article.write_text(gold_article.read_text(encoding="utf-8").replace(
            "author_slug: natthaphon-s", "author_slug: worldclassbroker-team"),
            encoding="utf-8")

        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "partial")
        failed = {(item["id"], item["asset"]): item["reason"]
                  for item in result["lanes"] if item["status"] == "failed"}
        self.assertIn(("btc_m", "btc"), failed)
        self.assertIn(("gold_e", "xauusd"), failed)
        self.assertIn("worldclassbroker-team", failed[("btc_m", "btc")])
        self.assertIn("natthaphon-s", failed[("gold_e", "xauusd")])

    def test_style_l_web_trend_must_match_internal_public_plan(self):
        article = self.day / "L-Forex-Daily" / "eurusd.md"
        article.write_text(article.read_text(encoding="utf-8").replace(
            "trend: up", "trend: fl"), encoding="utf-8")
        contract_path = (self.day.parent.parent / "work" / "build" / self.day.name /
                         "eurusd" / "internal" / "style-l" /
                         "eurusd.trade-plan-public.json")
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["article_sha256"] = hashlib.sha256(article.read_bytes()).hexdigest()
        contract_path.write_text(json.dumps(contract), encoding="utf-8")

        result = publish_selection.select(self.day, policy=self.policy)
        failed = next(item for item in result["lanes"]
                      if item["id"] == "forex_l" and item["asset"] == "eurusd")
        self.assertEqual(failed["status"], "failed")
        self.assertIn("trend ไม่ตรง public plan: คาด up แต่ได้ fl", failed["reason"])

    def test_policy_is_local_only(self):
        self.assertEqual(self.policy["schema_version"], 2)
        self.assertTrue(self.policy["manual_only"])
        self.assertFalse(self.policy["external_publish"])
        self.assertEqual(self.policy["network_authority"], "none")
        forex = next(lane for lane in self.policy["upload_lanes"] if lane["id"] == "forex_l")
        self.assertEqual(forex["max_articles"], 2)
        self.assertEqual(forex["images"], [
            "{asset}-forex-daily-h1-plan.webp",
            "{asset}-forex-daily-m15-trigger.webp",
            "{asset}-forex-daily-calendar-*.webp",
        ])
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
        self.assertNotIn("internal_trade_plan_contract", btc_lane)
        for lane_id in ("gold_e", "forex_l"):
            lane = next(item for item in self.policy["upload_lanes"]
                        if item["id"] == lane_id)
            self.assertIsNone(lane["trade_plan_contract"])
            self.assertEqual(lane["internal_trade_plan_contract"],
                             "{asset}.trade-plan-public.json")

    def test_any_future_lane_is_forbidden_from_copying_contract_to_output(self):
        policy = json.loads(json.dumps(self.policy))
        lane = next(item for item in policy["upload_lanes"]
                    if item["id"] == "gold_e")
        lane.pop("internal_trade_plan_contract")
        lane["trade_plan_contract"] = "{asset}.trade-plan-public.json"
        with self.assertRaisesRegex(
                publish_selection.SelectionUnavailable,
                "ห้ามส่ง trade-plan contract ลง output"):
            publish_selection.select(self.day, policy=policy)

    def test_global_output_purge_covers_unknown_assets_and_styles(self):
        keep = self.day / "Future-Style-Z" / "newasset.md"
        forbidden = keep.with_name("newasset.trade-plan-public.json")
        keep.parent.mkdir(parents=True, exist_ok=True)
        keep.write_text("keep", encoding="utf-8")
        forbidden.write_text("{}", encoding="utf-8")
        removed = publish_selection.purge_forbidden_output_files(self.day)
        self.assertIn(str(forbidden), removed)
        self.assertTrue(keep.is_file())
        self.assertFalse(forbidden.exists())

    def test_btc_lane_requires_v7_two_image_web_upload(self):
        btc = next(lane for lane in self.policy["upload_lanes"] if lane["id"] == "btc_m")
        self.assertEqual(btc["article"], "P002-{datecompact}-TH-M-BTCUSD-article.md")
        self.assertEqual(btc["images"], [
            "P002-{datecompact}-TH-M-BTCUSD-img01-*.webp",
            "P002-{datecompact}-TH-M-BTCUSD-img02-*.webp",
        ])
        self.assertEqual(btc["slug_template"], "btcusd-donchian-adx-{date}")
        result = publish_selection.select(self.day, policy=self.policy)
        lane = next(item for item in result["lanes"] if item["id"] == "btc_m")
        self.assertEqual(lane["status"], "ready")
        self.assertEqual(lane["images"], [
            "P002-20260831-TH-M-BTCUSD-img01-market.webp",
            "P002-20260831-TH-M-BTCUSD-img02-plan.webp",
        ])

    def test_stale_chart_fails_only_its_lane(self):
        folder = self.day / "E-อินดิเคเตอร์"
        current = folder / "xauusd-h1-fibonacci-2026-08-31.webp"
        stale = folder / "xauusd-h1-fibonacci-2026-08-20.webp"
        current.rename(stale)
        article = folder / "xauusd.md"
        article.write_text(article.read_text(encoding="utf-8").replace(current.name, stale.name),
                           encoding="utf-8")
        contract_path = (self.day.parent.parent / "work" / "build" / self.day.name /
                         "xauusd" / "internal" / "style-e" /
                         "xauusd.trade-plan-public.json")
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["article_sha256"] = hashlib.sha256(article.read_bytes()).hexdigest()
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "partial")
        self.assertEqual((result["ready_count"], result["expected_count"]), (5, 6))
        failed = next(item for item in result["lanes"] if item["id"] == "gold_e")
        self.assertIn("date", failed["reason"])

    def test_block_qa_contract_fails_only_its_lane_and_is_not_copied(self):
        contract_path = (self.day.parent.parent / "work" / "build" / self.day.name /
                         "xauusd" / "internal" / "style-e" /
                         "xauusd.trade-plan-public.json")
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

    def test_malformed_m_web_frontmatter_is_fail_closed_before_copy(self):
        article = self.day / "TH-Thailand/M/BTCUSD/P002-20260831-TH-M-BTCUSD-article.md"
        article.write_text(article.read_text(encoding="utf-8").replace(
            "author_slug: worldclassbroker-team", "author_slug: worldclassbroker-team\nslug: forbidden"),
            encoding="utf-8")
        result = publish_selection.select(self.day, policy=self.policy)
        failed = next(item for item in result["lanes"] if item["id"] == "btc_m")
        self.assertEqual(failed["status"], "failed")
        self.assertIn("frontmatter Style M web-upload", failed["reason"])
        self.assertFalse((Path(result["directory"]) / "05-BTCUSD-Style-M" /
                          "P002-20260831-TH-M-BTCUSD-article.md").exists())


if __name__ == "__main__":
    unittest.main()
