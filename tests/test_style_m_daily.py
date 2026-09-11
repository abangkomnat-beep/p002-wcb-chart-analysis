from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from PIL import Image

from tools import (style_m_article_contract, style_m_daily, style_m_renderer,
                   style_m_story, style_m_writer)


BKK = style_m_story.BANGKOK


def rows_for(cutoff: datetime, count: int = 121) -> list[dict]:
    start = cutoff - timedelta(hours=count - 1)
    rows = []
    for index in range(count):
        at = start + timedelta(hours=index)
        wave = ((index % 20) - 10) * 18
        base = 78_000 + index * 11 + wave
        close = base + (35 if index % 2 == 0 else -25)
        rows.append({"at": at.strftime("%Y-%m-%d %H:%M:%S"),
                     "open": base, "high": max(base, close) + 90,
                     "low": min(base, close) - 90, "close": close,
                     "forming": index == count - 1})
    return rows


def fetcher_for(rows):
    def fetcher(asset, *, timeframe, outputsize):
        return ({"asset": asset, "timeframe": timeframe, "count": len(rows),
                 "timezone_check": {"verified": True}}, list(rows), "fixture H1")
    return fetcher


def empty_news(asset, *, now):
    return {"asset": asset, "items": [], "provider_used": "official",
            "attempts": [], "cut_reason": "no_usable_news", "collected_at": now.isoformat()}


def official_news(asset, *, now):
    return {"asset": asset, "provider_status": "ok", "collected_at": now.isoformat(),
            "items": [{"title": "Federal Reserve remarks",
                       "link": "https://www.federalreserve.gov/official",
                       "published_at": "2026-08-29T13:00:00+00:00",
                       "source_tier": 1, "source": "Federal Reserve"}]}


def planned_story(cutoff: datetime, rows: list[dict]) -> dict:
    latest = rows[-2]
    anchors = {
        "hprev": {"index": 70, "at": rows[70]["at"], "price": 80_850.0},
        "hlast": {"index": 92, "at": rows[92]["at"], "price": 81_480.0},
        "lprev": {"index": 55, "at": rows[55]["at"], "price": 79_200.0},
        "llast": {"index": 82, "at": rows[82]["at"], "price": 79_750.0},
    }
    story = {
        "schema": style_m_story.SCHEMA, "asset": "btcusd", "timeframe": "1h",
        "cutoff": cutoff.isoformat(),
        "latest": {key: latest[key] for key in ("at", "open", "high", "low", "close")},
        "indicators": {"ema20": 79_930.0, "ema50": 79_450.0, "atr14": 522.87},
        "pivots": {"highs": [anchors["hprev"], anchors["hlast"]],
                   "lows": [anchors["lprev"], anchors["llast"]]},
        "source_label": "fixture", "source_meta": {}, "source_sha256": "a" * 64,
        "volume_policy": "unavailable-and-forbidden", "state": "WAIT_H1_CONFIRM",
        "side": "BUY", "reason_code": "PLAN_VALID", "reason": "รอแท่ง H1",
        "show_plan_geometry": True,
        "plan": {"entry_low": 79_750.0, "entry_high": 79_880.72, "sl": 79_357.85,
                 "tp1": 80_850.0, "tp2": 81_480.0, "rr1": 1.8538, "rr2": 3.0587,
                 "atr14": 522.87, "entry_zone_atr": 0.25,
                 "min_rr1": 1.5, "min_rr2": 2.0, "dynamic_entry_limit": 79_954.71,
                 "stop_buffer_atr": 0.75, "worst_entry_risk_atr": 1.0,
                 "anchors": anchors},
    }
    projection = {"cutoff": story["cutoff"], "source_label": story["source_label"],
                  "source_meta": story["source_meta"],
                  "rows": [{key: row[key] for key in ("at", "open", "high", "low", "close")}
                           for row in rows[:-1]]}
    story["source_sha256"] = hashlib.sha256(json.dumps(
        projection, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    style_m_story.validate(story)
    return story


class StyleMContracts(unittest.TestCase):
    def setUp(self):
        self.moment = datetime(2026, 8, 29, 9, 10, tzinfo=BKK)
        self.cutoff = self.moment.replace(minute=0, second=0, microsecond=0)
        self.rows = rows_for(self.cutoff)

    def test_cutoff_uses_latest_closed_h1_boundary_at_any_hour(self):
        self.assertEqual(style_m_daily.daily_cutoff(self.moment), self.cutoff)
        self.assertEqual(
            style_m_daily.daily_cutoff(self.moment.replace(hour=4, minute=37)),
            self.moment.replace(hour=4, minute=0, second=0, microsecond=0))
        self.assertEqual(
            style_m_daily.daily_cutoff(self.moment.replace(hour=10, minute=0)),
            self.moment.replace(hour=10, minute=0, second=0, microsecond=0))

    def test_prepare_uses_closed_h1_and_zero_news_branch(self):
        prepared = style_m_daily.prepare(
            cutoff_at=self.moment, fetcher=fetcher_for(self.rows), news_collector=empty_news)
        self.assertEqual(prepared["basis"]["basis_close_at"], self.cutoff.isoformat())
        self.assertIn(prepared["story"]["state"], style_m_story.STATES)
        self.assertEqual(prepared["events"], [])
        self.assertNotIn("ไม่พบเหตุการณ์สำคัญ", prepared["markdown"])
        self.assertEqual(prepared["article_qa"]["headings"], list(style_m_writer.H2))
        self.assertEqual(style_m_writer.H2, (
            "BTCUSD H1 บอกอะไรจากโครงสร้างล่าสุด",
            "แนวรับ แนวต้าน และแผน BTCUSD วันนี้"))
        self.assertIn('contract_version": "M-PROD/v5"', prepared["article_visual_facts"] and
                      __import__("json").dumps(prepared["article_visual_facts"], ensure_ascii=False))
        self.assertEqual(prepared["semantic_decision"]["schema"],
                         "style-m-semantic-decision/v1")
        self.assertEqual(prepared["writer_claim_report"]["schema"],
                         "style-m-writer-claim-report/v1")

    def test_blind_editorial_rubric_no_plan_conflict_has_thesis_evidence_synthesis_action(self):
        from test_style_m_semantics import conflict_story, rows_fixture
        rows = rows_fixture()
        story = conflict_story(rows)
        facts = style_m_article_contract.build(story, rows)
        article = style_m_writer.compose(story, [], facts)["markdown"]
        body = article.split("---", 2)[-1].replace("&emsp;", "")
        lead, structure, decision = body.split("## ", 2)
        self.assertIn("ยังไม่มีแผนเข้าเทรด", lead)
        self.assertIn("ยังเลือกฝั่งไม่ได้", lead + decision)
        self.assertIn("ราคาปิดล่าสุด", structure)
        self.assertIn("EMA20", structure)
        self.assertIn("EMA50", structure)
        self.assertIn("จุดสูง", structure)
        self.assertIn("จุดต่ำ", structure)
        self.assertIn("ยอดยกสูงขึ้น", structure)
        self.assertIn("ฐานลดต่ำลง", structure)
        self.assertIn("จึงทำให้กรอบขยายออกสองด้าน", structure)
        self.assertIn("สวนทางกับภาพเส้นเฉลี่ย", structure)
        self.assertNotIn("(จุดสูงสูงขึ้น)", structure)
        self.assertNotIn("(จุดต่ำต่ำลง)", structure)
        self.assertNotIn("(กรอบราคาขยายออกสองด้าน)", structure)
        self.assertIn("ขณะที่ EMA20", structure)
        self.assertNotIn("ขณะที่EMA20", structure)
        self.assertNotIn("กรอบราคาจึงกรอบราคา", structure)
        self.assertIn("ขอบเขตสังเกต", structure)
        self.assertIn("ยังไม่ใช่สัญญาณเข้า", structure)
        self.assertIn("เงื่อนไขที่ต้องเห็น", decision)
        self.assertIn("ราคาปิดยืนยัน", decision)
        self.assertIn("ยอดที่ยกสูงขึ้นสวนทางกับภาพ EMA ที่เป็นขาลง", decision)
        self.assertIn("ฐานที่ลดต่ำลงและราคาปิดใต้เส้นเฉลี่ยยิ่งย้ำให้ระวัง", decision)
        self.assertNotIn(";", body)
        self.assertFalse(any(line.rstrip().endswith(".") for line in body.splitlines()))

    def test_no_plan_never_writes_trade_labels(self):
        prepared = style_m_daily.prepare(
            cutoff_at=self.moment, fetcher=fetcher_for(self.rows), news_collector=empty_news)
        story = dict(prepared["story"], state="NO_PLAN", side=None, plan=None,
                     show_plan_geometry=False, reason_code="STRUCTURE_CONFLICT",
                     reason="โครงสร้างไม่ครบ")
        markdown = style_m_writer.render(story, [])
        for label in ("**Entry:**", "**Stop Loss:**", "**TP1 / TP2:**", "**RR โดยประมาณ:**"):
            self.assertNotIn(label, markdown)
        self.assertNotIn("ข่าว เหตุการณ์ และความเสี่ยงวันนี้", markdown)

    def test_writer_uses_registered_web_identity_and_safe_draft_metadata(self):
        story = dict(planned_story(self.cutoff, self.rows), state="NO_PLAN", side=None,
                     plan=None, show_plan_geometry=False, reason_code="STRUCTURE_CONFLICT",
                     reason="โครงสร้างไม่ครบ")
        markdown = style_m_writer.render(story, [])
        frontmatter = markdown.split("---", 2)[1]
        self.assertIn('asset: "btc"', frontmatter)
        self.assertIn('slug: "btcusd-levels-2026-08-29"', frontmatter)
        self.assertIn('excerpt: "', frontmatter)
        self.assertIn('author_slug: "worldclassbroker-team"', frontmatter)
        self.assertIn('trend: "', frontmatter)
        self.assertIn('status: "draft"', frontmatter)
        self.assertIn("country: thailand", frontmatter)
        self.assertIn("language: th", frontmatter)
        self.assertNotIn("NO_PLAN", frontmatter)

    def test_writer_news_advisory_and_wait_is_not_order(self):
        story = planned_story(self.cutoff, self.rows)
        event = {"time_thai": "29/08 20:00 น.", "title": "Official remarks",
                 "source": "Federal Reserve", "url": "https://www.federalreserve.gov/test",
                 "risk_level": "สูง", "impact": "อาจผันผวน", "plan_action": "รอ H1 ปิด"}
        markdown = style_m_writer.render(story, [event])
        self.assertIn("**ความเสี่ยงตามเวลา:**", markdown)
        self.assertNotIn("| เวลาไทย | เหตุการณ์ |", markdown)
        self.assertIn(event["url"], markdown)
        self.assertIn("ยังไม่ใช่ออเดอร์ที่เปิดแล้ว", markdown)
        self.assertIn("0.75 ATR", markdown)
        self.assertIn("slippage", markdown)
        self.assertIn("&emsp;BTCUSD", markdown)
        self.assertNotIn("สถานะแผน", markdown)
        self.assertIn("- **Trigger:**", markdown)
        self.assertIn("- **ยกเลิกแผน:**", markdown)
        self.assertIn("- **กรอบความเสี่ยง:**", markdown)
        self.assertIn("- **เกณฑ์ก่อนเข้า:** RR ขั้นต่ำ TP1 1.50", markdown)
        self.assertNotIn("ปิดเขียว", markdown)
        self.assertIn("- **Entry:**", markdown)
        self.assertIn("[ดูกราฟ BTCUSD](/thailand/asset-btc)", markdown)
        self.assertIn("[อ่านบทวิเคราะห์ล่าสุด](/thailand/analysis)", markdown)
        self.assertNotIn("](/thailand/asset-btc)", markdown.replace(
            "[ดูกราฟ BTCUSD](/thailand/asset-btc)", ""))
        self.assertIn("# วิเคราะห์ BTCUSD H1 วันนี้ 29/08/2026:", markdown)
        self.assertNotIn("# [BTCUSD]", markdown)
        self.assertNotIn("ข่าวเป็นเพียงตัวเพิ่มความเสี่ยงและความผันผวน", markdown)
        self.assertNotIn("บทวิเคราะห์นี้เป็นฉากทัศน์แบบมีเงื่อนไข", markdown)

    def test_stop_uses_0_75_atr_beyond_structure_and_one_atr_worst_entry_risk(self):
        def pivot(index, hours_ago, price):
            return {"index": index,
                    "at": (self.cutoff - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S"),
                    "price": price}

        pivots = {
            "highs": [pivot(70, 48, 80_850.0), pivot(92, 4, 81_480.0)],
            "lows": [pivot(55, 60, 79_200.0), pivot(82, 12, 79_750.0)],
        }
        latest = {"at": self.cutoff.strftime("%Y-%m-%d %H:%M:%S"), "open": 79_780.0,
                  "high": 79_850.0, "low": 79_700.0, "close": 79_810.0}
        result = style_m_story.decide([latest], ema20=79_930.0, ema50=79_450.0,
                                      atr14=522.87, pivots=pivots)
        plan = result["plan"]
        self.assertEqual(plan["sl"], 79_357.85)
        self.assertEqual(plan["stop_buffer_atr"], 0.75)
        self.assertEqual(plan["worst_entry_risk_atr"], 1.0)
        self.assertAlmostEqual(plan["rr1"], 1.8538, places=3)
        self.assertAlmostEqual(plan["rr2"], 3.0587, places=3)
        self.assertEqual(plan["min_rr1"], 1.5)
        self.assertEqual(plan["min_rr2"], 2.0)
        self.assertEqual(plan["dynamic_entry_limit"], 79_954.71)

    def test_h1_close_confirms_without_requiring_green_candle(self):
        def pivot(index, hours_ago, price):
            return {"index": index,
                    "at": (self.cutoff - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S"),
                    "price": price}

        pivots = {
            "highs": [pivot(70, 48, 80_850.0), pivot(92, 4, 81_480.0)],
            "lows": [pivot(55, 60, 79_200.0), pivot(82, 12, 79_750.0)],
        }
        red_close_above_trigger = {
            "at": self.cutoff.strftime("%Y-%m-%d %H:%M:%S"),
            "open": 80_050.0, "high": 80_100.0, "low": 79_820.0, "close": 79_900.0,
        }
        result = style_m_story.decide(
            [red_close_above_trigger], ema20=79_930.0, ema50=79_450.0,
            atr14=522.87, pivots=pivots)
        self.assertEqual(result["state"], "PLAN_VALID")

    def test_renderer_is_white_webp_and_conditional_geometry(self):
        story = planned_story(self.cutoff, self.rows)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chart.webp"
            result = style_m_renderer.render(story, self.rows[:-1], path)
            self.assertLessEqual(path.stat().st_size, 200 * 1024)
            with Image.open(path) as image:
                self.assertEqual(image.size, (1920, 1080))
                self.assertEqual(image.format, "WEBP")
            self.assertFalse(result["source_volume_available"])
            self.assertEqual(result["state_label"], "รอแท่งยืนยัน")
            self.assertNotIn("state", result)
            self.assertEqual(result["occupancy_palette"], "green_gray_light")
            self.assertEqual(result["occupancy_bins"], 72)
            self.assertEqual(result["candle_body_ratio"], 0.48)
            self.assertEqual(result["header_layout"], "inline")
            self.assertFalse(result["bottom_summary"])
            self.assertFalse(result["footer_disclaimer"])
            self.assertEqual(result["plot_bounds"], [72, 96, 1596, 1040])
            self.assertFalse(result["blue_projection_arrow"])
            self.assertFalse(result["target_number_badges"])
            entry = result["label_boxes"]["ENTRY"]
            sl = result["label_boxes"]["SL"]
            self.assertLessEqual(entry[3] + 8, sl[1],
                                 "กล่อง Entry และ SL ต้องมีช่องว่างอย่างน้อย 8 px")

    def test_renderer_cutoff_caption_uses_actual_story_time(self):
        story = planned_story(self.cutoff.replace(hour=8), self.rows)
        self.assertEqual(
            style_m_renderer.cutoff_caption(story),
            "ข้อมูลถึงแท่งปิด H1 29/08/2026 08:00 น.",
        )

    def test_renderer_fact_mutation_blocks_against_original_article(self):
        story = planned_story(self.cutoff, self.rows)
        facts = style_m_article_contract.build(story, self.rows[:-1])
        facts["facts"]["zone.support.primary"]["low"] += 25.0
        with self.assertRaises(style_m_article_contract.ArticleContractError) as caught:
            with tempfile.TemporaryDirectory() as tmp:
                style_m_renderer.render(story, self.rows[:-1], Path(tmp) / "chart.webp", facts)
        self.assertEqual(caught.exception.code, "STALE_FACTS_HASH")

    def test_story_mutation_after_facts_is_rejected_by_oracle_binding(self):
        story = planned_story(self.cutoff, self.rows)
        facts = style_m_article_contract.build(story, self.rows[:-1])
        mutated_plan = dict(story["plan"])
        mutated_plan["dynamic_entry_limit"] = max(
            (mutated_plan["tp1"] + mutated_plan["min_rr1"] * mutated_plan["sl"])
            / (1.0 + mutated_plan["min_rr1"]),
            (mutated_plan["tp2"] + mutated_plan["min_rr2"] * mutated_plan["sl"])
            / (1.0 + mutated_plan["min_rr2"]),
        )
        mutated_story = dict(story, side="SELL", plan=mutated_plan)
        with self.assertRaises(style_m_article_contract.ArticleContractError) as caught:
            style_m_writer.render(mutated_story, [], facts)
        self.assertEqual(caught.exception.code, "ORACLE_BINDING_MISMATCH")

    def test_renderer_uses_reader_state_labels_for_all_states(self):
        expected = {"NO_PLAN": "รอเงื่อนไข", "INVALIDATED": "ทบทวนโครงสร้าง",
                    "WAIT_H1_CONFIRM": "รอแท่งยืนยัน", "PLAN_VALID": "แผนพร้อมประเมิน"}
        with tempfile.TemporaryDirectory() as tmp:
            for state, label in expected.items():
                story = planned_story(self.cutoff, self.rows)
                if state == "NO_PLAN":
                    story.update({"state": state, "side": None, "plan": None,
                                  "reason_code": "STRUCTURE_CONFLICT", "show_plan_geometry": False})
                elif state == "INVALIDATED":
                    story.update({"state": state, "side": "BUY", "plan": None,
                                  "reason_code": "STOP_INVALIDATED", "show_plan_geometry": False})
                else:
                    story["state"] = state
                facts = style_m_article_contract.build(story, self.rows[:-1])
                report = style_m_renderer.render(story, self.rows[:-1],
                                                  Path(tmp) / f"{state}.webp", facts)
                self.assertEqual(report["state_label"], label)
                self.assertNotIn(state, report)
                composed = style_m_writer.compose(story, [], facts)
                article = composed["markdown"]
                self.assertNotIn(state, article)
                parity = style_m_article_contract.parity_report(
                    facts, markdown=article, writer_report=composed["claim_report"],
                    render_report=report)
                self.assertEqual(parity["status"], "PASS")
                self.assertEqual(parity["missing_bindings"], [])
                self.assertEqual(parity["unbound_numeric_tokens"], [])
                if state in ("NO_PLAN", "INVALIDATED"):
                    self.assertEqual(report["label_boxes"], {})
                    self.assertNotIn("**Entry:**", article)
                else:
                    self.assertTrue(report["label_boxes"])
                    self.assertIn("**Entry:**", article)

    def test_atomic_two_lane_release_preserves_siblings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as publish_tmp, tempfile.TemporaryDirectory() as work_tmp:
            publish_root, work_root = Path(publish_tmp), Path(work_tmp)
            day = publish_root / "29-08-2026"
            sentinels = {}
            for lane in ("02-XAUUSD-Style-E", "04-Forex-Style-L"):
                folder = day / lane
                folder.mkdir(parents=True)
                file = folder / "sentinel.txt"
                file.write_text(lane, encoding="utf-8")
                sentinels[file] = hashlib.sha256(file.read_bytes()).hexdigest()
            kwargs = {"asset": "btcusd", "publish_root": publish_root,
                      "work_root": work_root, "cutoff_at": self.moment,
                      "fetcher": fetcher_for(self.rows), "news_collector": empty_news}
            first = style_m_daily.run_round(**kwargs)
            second = style_m_daily.run_round(**kwargs)
            self.assertTrue(first["published"])
            self.assertTrue(second["idempotent"])
            self.assertTrue(Path(first["article"]).is_file())
            evidence = work_root / "29-08-2026" / "btcusd" / "internal" / "style-m"
            self.assertEqual(json_names := {path.name for path in evidence.glob("*.json")},
                             {"story.json", "source-evidence.json", "candle-basis.json",
                              "news-evidence.json", "semantic-decision.json",
                              "article-visual-facts.json", "writer-claim-report.json",
                              "renderer-claim-report.json", "claim-parity-report.json",
                              "index-policy.json", "qa-report.json", "manifest.json"})
            self.assertNotIn("parity-report.json", json_names)
            manifest = __import__("json").loads((evidence / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "style-m-daily-manifest/v3")
            qa = __import__("json").loads((evidence / "qa-report.json").read_text(encoding="utf-8"))
            for report in (manifest, qa):
                self.assertTrue(report["production_write"])
                self.assertFalse(report["external_publish"])
            for file, digest in sentinels.items():
                self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), digest)

    def test_publish_false_records_shadow_safety_flags_in_manifest_and_qa(self):
        with tempfile.TemporaryDirectory() as publish_tmp, tempfile.TemporaryDirectory() as work_tmp:
            result = style_m_daily.run_round(
                asset="btcusd", publish_root=Path(publish_tmp), work_root=Path(work_tmp),
                cutoff_at=self.moment, fetcher=fetcher_for(self.rows),
                news_collector=empty_news, publish=False)
            self.assertFalse(result["published"])
            self.assertFalse((Path(publish_tmp) / "29-08-2026" / style_m_daily.FOLDER).exists())
            evidence = Path(result["shadow"]) / "evidence"
            for name in ("manifest.json", "qa-report.json"):
                report = __import__("json").loads((evidence / name).read_text(encoding="utf-8"))
                self.assertFalse(report["production_write"])
                self.assertFalse(report["external_publish"])

    def test_different_hash_collision_holds(self):
        with tempfile.TemporaryDirectory() as publish_tmp, tempfile.TemporaryDirectory() as work_tmp:
            kwargs = {"asset": "btcusd", "publish_root": Path(publish_tmp),
                      "work_root": Path(work_tmp), "cutoff_at": self.moment,
                      "fetcher": fetcher_for(self.rows), "news_collector": empty_news}
            result = style_m_daily.run_round(**kwargs)
            Path(result["article"]).write_text("changed", encoding="utf-8")
            with self.assertRaises(style_m_daily.DailyStyleMError):
                style_m_daily.run_round(**kwargs)

    def test_duplicate_no_plan_is_held_in_shadow_without_web_lane(self):
        first = style_m_daily.prepare(
            cutoff_at=self.moment, fetcher=fetcher_for(self.rows), news_collector=empty_news)
        with tempfile.TemporaryDirectory() as publish_tmp, tempfile.TemporaryDirectory() as work_tmp:
            result = style_m_daily.run_round(
                asset="btcusd", publish_root=Path(publish_tmp), work_root=Path(work_tmp),
                cutoff_at=self.moment, fetcher=fetcher_for(self.rows), news_collector=empty_news,
                prior_fingerprint=first["article_visual_facts"])
            self.assertEqual(result["status"], "hold")
            self.assertFalse(result["published"])
            self.assertEqual(result["index_policy"]["recommendation"], "HOLD_DUPLICATE_NO_PLAN")
            self.assertFalse((Path(publish_tmp) / "29-08-2026" / style_m_daily.FOLDER).exists())
            self.assertFalse((Path(publish_tmp) / "29-08-2026" / "0-ขึ้นเว็บวันนี้" /
                              style_m_daily.LANE_FOLDER).exists())
            self.assertTrue(Path(result["shadow"]).is_dir())
            manifest = __import__("json").loads(
                (Path(result["shadow"]) / "evidence" / "manifest.json").read_text(encoding="utf-8"))
            qa = __import__("json").loads(
                (Path(result["shadow"]) / "evidence" / "qa-report.json").read_text(encoding="utf-8"))
            for report in (manifest, qa):
                self.assertFalse(report["production_write"])
                self.assertFalse(report["external_publish"])

    def test_evidence_failure_rolls_back_both_new_public_lanes(self):
        with tempfile.TemporaryDirectory() as publish_tmp, tempfile.TemporaryDirectory() as work_tmp:
            publish_root = Path(publish_tmp)
            kwargs = {"asset": "btcusd", "publish_root": publish_root,
                      "work_root": Path(work_tmp), "cutoff_at": self.moment,
                      "fetcher": fetcher_for(self.rows), "news_collector": empty_news}
            with mock.patch.object(style_m_daily, "_write_internal",
                                   side_effect=OSError("fixture evidence failure")):
                with self.assertRaises(OSError):
                    style_m_daily.run_round(**kwargs)
            day = publish_root / "29-08-2026"
            self.assertFalse((day / style_m_daily.FOLDER).exists())
            self.assertFalse((day / "0-ขึ้นเว็บวันนี้" /
                              style_m_daily.LANE_FOLDER).exists())

    def _assert_stale_consumer_leaves_no_partial_output(self, consumer):
        prepared = style_m_daily.prepare(
            cutoff_at=self.moment, fetcher=fetcher_for(self.rows), news_collector=empty_news)
        renderer = None
        if consumer == "writer":
            prepared["writer_claim_report"]["facts_sha256"] = "0" * 64
        else:
            class StaleRenderer:
                @staticmethod
                def render(story, rows, output, facts):
                    report = style_m_renderer.render(story, rows, output, facts)
                    report["facts_sha256"] = "0" * 64
                    return report
            renderer = StaleRenderer
        with tempfile.TemporaryDirectory() as publish_tmp, tempfile.TemporaryDirectory() as work_tmp:
            publish_root, work_root = Path(publish_tmp), Path(work_tmp)
            with mock.patch.object(style_m_daily, "prepare", return_value=prepared):
                with self.assertRaises(style_m_daily.DailyStyleMError):
                    style_m_daily.run_round(
                        asset="btcusd", publish_root=publish_root, work_root=work_root,
                        cutoff_at=self.moment, fetcher=fetcher_for(self.rows),
                        news_collector=empty_news, renderer=renderer)
            day = publish_root / "29-08-2026"
            self.assertFalse((day / style_m_daily.FOLDER).exists())
            self.assertFalse((day / "0-ขึ้นเว็บวันนี้" / style_m_daily.LANE_FOLDER).exists())
            self.assertFalse((work_root / "29-08-2026" / "btcusd" / "internal" /
                              style_m_daily.INTERNAL_FOLDER).exists())

    def test_stale_writer_report_blocks_without_partial_output(self):
        self._assert_stale_consumer_leaves_no_partial_output("writer")

    def test_stale_renderer_report_blocks_without_partial_output(self):
        self._assert_stale_consumer_leaves_no_partial_output("renderer")

    def test_rehashed_canonical_registry_mutation_blocks_before_package_output(self):
        legacy = {"schema": style_m_article_contract.LEGACY_SCHEMA,
                  "semantic_fingerprint": "legacy-fingerprint",
                  "fingerprint_basis": {"state": "NO_PLAN"}}
        prepared_base = style_m_daily.prepare(
            cutoff_at=self.moment, fetcher=fetcher_for(self.rows), news_collector=empty_news,
            prior_fingerprint=legacy)
        mutations = {
            "viewport": lambda registry: registry["visual.viewport"].update(
                price_min=registry["visual.viewport"]["price_min"] - 5_000.0),
            "full_registry": lambda registry: registry["occupancy.price_bins"].update(
                count=registry["occupancy.price_bins"]["count"] - 1),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                prepared = copy.deepcopy(prepared_base)
                facts = prepared["article_visual_facts"]
                mutate(facts["facts"])
                facts["facts_sha256"] = style_m_article_contract._facts_hash(facts)
                prepared["writer_claim_report"]["facts_sha256"] = facts["facts_sha256"]
                folder = Path(tmp) / "package"
                with self.assertRaises(style_m_article_contract.ArticleContractError) as caught:
                    style_m_daily._render_package(prepared, folder)
                self.assertEqual(caught.exception.code,
                                 "FACT_REGISTRY_PROJECTION_MISMATCH")
                self.assertFalse(folder.exists())
                self.assertFalse((folder / "btc.md").exists())

        envelope_mutations = {
            "asset": lambda payload: payload.update(asset="xauusd"),
            "timeframe": lambda payload: payload.update(timeframe="4h"),
            "cutoff": lambda payload: payload.update(cutoff="2026-08-30T05:00:00+07:00"),
            "source_sha256": lambda payload: payload["source"].update(sha256="0" * 64),
            "source_closed_h1": lambda payload: payload["source"].update(closed_h1=False),
            "web_route": lambda payload: payload["web_routes"].update(primary="/forged"),
            "semantic_fingerprint": lambda payload: payload.update(
                semantic_fingerprint="0" * 64),
            "fingerprint_basis": lambda payload: payload["fingerprint_basis"].update(
                reason_bucket="FORGED"),
            "news": lambda payload: payload["news"].update(public_advisory=True),
            "migration": lambda payload: payload["migration"].update(
                migration_version="forged/v9"),
        }
        for name, mutate in envelope_mutations.items():
            with self.subTest(name=f"envelope_{name}"), tempfile.TemporaryDirectory() as tmp:
                prepared = copy.deepcopy(prepared_base)
                facts = prepared["article_visual_facts"]
                mutate(facts)
                facts["facts_sha256"] = style_m_article_contract._facts_hash(facts)
                prepared["writer_claim_report"]["facts_sha256"] = facts["facts_sha256"]
                folder = Path(tmp) / "package"
                with self.assertRaises(style_m_article_contract.ArticleContractError):
                    style_m_daily._render_package(prepared, folder)
                self.assertFalse(folder.exists())
                self.assertFalse((folder / "btc.md").exists())

    def test_forged_news_projection_blocks_before_package_output(self):
        official_prepared = style_m_daily.prepare(
            cutoff_at=self.moment, fetcher=fetcher_for(self.rows),
            news_collector=official_news)
        zero_prepared = style_m_daily.prepare(
            cutoff_at=self.moment, fetcher=fetcher_for(self.rows),
            news_collector=empty_news)
        forged_event = {"event_id": "evil-1", "title": "Forged signal",
                        "url": "https://evil.example/forge",
                        "time_thai": "29/08 20:00 น."}
        for name, prepared_base in (("official_forged", official_prepared),
                                    ("zero_news_injected", zero_prepared)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                prepared = copy.deepcopy(prepared_base)
                facts = prepared["article_visual_facts"]
                forged_facts = style_m_article_contract.build(
                    prepared["story"], prepared["rows"], events=[forged_event],
                    news_report=prepared["news_report"],
                    prior_fingerprint=prepared["prior_fingerprint"])
                facts["facts"]["news.risk_context"] = copy.deepcopy(
                    forged_facts["facts"]["news.risk_context"])
                facts["claims"]["claim.news.risk_context"] = copy.deepcopy(
                    forged_facts["claims"]["claim.news.risk_context"])
                facts["news"] = copy.deepcopy(forged_facts["news"])
                facts["facts_sha256"] = style_m_article_contract._facts_hash(facts)
                prepared["writer_claim_report"]["facts_sha256"] = facts["facts_sha256"]
                folder = Path(tmp) / "package"
                with self.assertRaises(style_m_article_contract.ArticleContractError):
                    style_m_daily._render_package(prepared, folder)
                self.assertFalse(folder.exists())
                self.assertFalse((folder / "btc.md").exists())

    def test_coherent_events_envelope_attack_blocks_against_raw_news(self):
        official_prepared = style_m_daily.prepare(
            cutoff_at=self.moment, fetcher=fetcher_for(self.rows),
            news_collector=official_news)
        empty_prepared = style_m_daily.prepare(
            cutoff_at=self.moment, fetcher=fetcher_for(self.rows),
            news_collector=empty_news)
        forged = {"event_id": "evil-1", "title": "Forged signal",
                  "url": "https://evil.example/forge", "time_thai": "29/08 20:00 น."}
        attacks = (("official_to_forged", official_prepared, [forged]),
                   ("official_to_zero", official_prepared, []),
                   ("empty_to_forged", empty_prepared, [forged]))
        for name, prepared_base, forged_events in attacks:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                prepared = copy.deepcopy(prepared_base)
                prepared["events"] = copy.deepcopy(forged_events)
                facts = style_m_article_contract.build(
                    prepared["story"], prepared["rows"], events=prepared["events"],
                    news_report=prepared["news_report"],
                    prior_fingerprint=prepared["prior_fingerprint"])
                composed = style_m_writer.compose(
                    prepared["story"], prepared["events"], facts)
                prepared["article_visual_facts"] = facts
                prepared["semantic_decision"] = facts["semantic_decision"]
                prepared["markdown"] = composed["markdown"]
                prepared["writer_claim_report"] = composed["claim_report"]
                folder = Path(tmp) / "package"
                with self.assertRaises(style_m_article_contract.ArticleContractError):
                    style_m_daily._render_package(prepared, folder)
                self.assertFalse(folder.exists())
                self.assertFalse((folder / "btc.md").exists())

    def test_blank_image_replacement_blocks_even_with_real_renderer_report(self):
        class BlankRenderer:
            @staticmethod
            def render(story, rows, output, facts):
                report = style_m_renderer.render(story, rows, output, facts)
                Image.new("RGB", (1920, 1080), "white").save(output, format="WEBP")
                return report

        with tempfile.TemporaryDirectory() as publish_tmp, tempfile.TemporaryDirectory() as work_tmp:
            with self.assertRaises(style_m_daily.DailyStyleMError):
                style_m_daily.run_round(
                    asset="btcusd", publish_root=Path(publish_tmp), work_root=Path(work_tmp),
                    cutoff_at=self.moment, fetcher=fetcher_for(self.rows),
                    news_collector=empty_news, renderer=BlankRenderer, publish=False)
            self.assertFalse((Path(work_tmp) / "29-08-2026" / "btcusd" / "internal" /
                              style_m_daily.INTERNAL_FOLDER).exists())

    def test_coherently_rehashed_blank_custom_renderer_is_not_a_trusted_production_renderer(self):
        class CoherentBlankRenderer:
            @staticmethod
            def render(story, rows, output, facts):
                report = style_m_renderer.render(story, rows, output, facts)
                Image.new("RGB", (1920, 1080), "white").save(output, format="WEBP")
                image_sha = hashlib.sha256(Path(output).read_bytes()).hexdigest()
                trace_sha = hashlib.sha256(json.dumps(
                    report["draw_trace"], ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode("utf-8")).hexdigest()
                report["visual_trace_sha256"] = trace_sha
                report["artifact"] = {
                    "sha256": image_sha, "bytes": Path(output).stat().st_size,
                    "width": 1920, "height": 1080, "format": "webp",
                    "visual_trace_sha256": trace_sha,
                    "artifact_trace_sha256": hashlib.sha256(
                        f"{image_sha}:{trace_sha}".encode("utf-8")).hexdigest(),
                }
                return report

        with tempfile.TemporaryDirectory() as publish_tmp, tempfile.TemporaryDirectory() as work_tmp:
            with self.assertRaises(style_m_daily.DailyStyleMError):
                style_m_daily.run_round(
                    asset="btcusd", publish_root=Path(publish_tmp), work_root=Path(work_tmp),
                    cutoff_at=self.moment, fetcher=fetcher_for(self.rows),
                    news_collector=empty_news, renderer=CoherentBlankRenderer, publish=False)


if __name__ == "__main__":
    unittest.main()
