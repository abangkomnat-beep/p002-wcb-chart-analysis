from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from PIL import Image

from tools import style_m_daily, style_m_renderer, style_m_story, style_m_writer


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
    style_m_story.validate(story)
    return story


class StyleMContracts(unittest.TestCase):
    def setUp(self):
        self.moment = datetime(2026, 8, 29, 12, 0, tzinfo=BKK)
        self.cutoff = self.moment.replace(hour=11)
        self.rows = rows_for(self.cutoff)

    def test_cutoff_requires_11_bangkok(self):
        with self.assertRaises(style_m_daily.DailyStyleMNotDue):
            style_m_daily.daily_cutoff(self.moment.replace(hour=10))
        self.assertEqual(style_m_daily.daily_cutoff(self.moment), self.cutoff)

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
        self.assertIn('contract_version": "M-PROD/v4"', prepared["article_visual_facts"] and
                      __import__("json").dumps(prepared["article_visual_facts"], ensure_ascii=False))

    def test_no_plan_never_writes_trade_labels(self):
        prepared = style_m_daily.prepare(
            cutoff_at=self.moment, fetcher=fetcher_for(self.rows), news_collector=empty_news)
        story = dict(prepared["story"], state="NO_PLAN", side=None, plan=None,
                     show_plan_geometry=False, reason="โครงสร้างไม่ครบ")
        markdown = style_m_writer.render(story, [])
        for label in ("**Entry:**", "**Stop Loss:**", "**TP1 / TP2:**", "**RR โดยประมาณ:**"):
            self.assertNotIn(label, markdown)
        self.assertNotIn("ข่าว เหตุการณ์ และความเสี่ยงวันนี้", markdown)

    def test_writer_uses_registered_web_identity_and_safe_draft_metadata(self):
        story = dict(planned_story(self.cutoff, self.rows), state="NO_PLAN", side=None,
                     plan=None, show_plan_geometry=False, reason="โครงสร้างไม่ครบ")
        markdown = style_m_writer.render(story, [])
        frontmatter = markdown.split("---", 2)[1]
        self.assertIn('asset: "btc"', frontmatter)
        self.assertIn('slug: "btcusd-levels-2026-08-29"', frontmatter)
        self.assertIn('excerpt: "', frontmatter)
        self.assertIn('author_slug: "world-class-broker-team"', frontmatter)
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

    def test_atomic_two_lane_release_preserves_siblings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as publish_tmp, tempfile.TemporaryDirectory() as work_tmp:
            publish_root, work_root = Path(publish_tmp), Path(work_tmp)
            day = publish_root / "29-08-2026" / "0-ขึ้นเว็บวันนี้"
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
            self.assertTrue((day / style_m_daily.LANE_FOLDER / "btc.md").is_file())
            for file, digest in sentinels.items():
                self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), digest)

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


if __name__ == "__main__":
    unittest.main()
