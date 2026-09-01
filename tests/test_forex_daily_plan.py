from __future__ import annotations

import copy
import json
import tempfile
import unittest
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tools import forex_daily_plan
from tools.unified_registry import RegistryLoader


class ForexDailyPlanContract(unittest.TestCase):

    GBPUSD_2026_09_01_H4 = {
        "bias": "down",
        "close": 1.35532,
        "ema20": 1.35670780341694,
        "ema50": 1.35792588447875,
    }
    GBPUSD_2026_09_01_H1 = {
        "close": 1.35454,
        "pdh": 1.35652,
        "pdl": 1.35342,
        "current_high": 1.35597,
        "current_low": 1.35422,
        "current_range": 0.00175,
        "atr14": 0.000989919911447963,
        "adr14": 0.00531714285714283,
        "adr_used_pct": 32.9124126813527,
    }
    GBPUSD_2026_09_01_PLAN = {
        "active": False,
        "direction": "down",
        "watch_low": 1.35415,
        "watch_high": 1.35597,
    }

    def test_style_identity_is_l(self):
        self.assertEqual(forex_daily_plan.STYLE_ID, "l_forex_daily_plan")
        self.assertEqual(forex_daily_plan.STYLE_LETTER, "L")
        self.assertEqual(forex_daily_plan.STYLE_NAME,
                         "Style L — Forex Daily Trade Plan")
        self.assertEqual(forex_daily_plan.STYLE_FOLDER, "L-Forex-Daily")

    def test_l2_decision_policy_is_versioned_and_strict(self):
        policy = forex_daily_plan.load_decision_policy()
        self.assertEqual(policy["policy_version"], "style-l-decision-policy/v2")
        self.assertEqual(policy["m30_readiness"]["core"],
                         ["dmi_direction", "adx_threshold"])
        self.assertEqual(policy["m30_readiness"]["supporting"], ["supertrend"])
        self.assertEqual(policy["m30_readiness"]["adx_threshold"], 20)

        invalid = []
        broken = copy.deepcopy(policy)
        broken["m30_readiness"]["core"].append("supertrend")
        invalid.append(("core/supporting", broken))
        broken = copy.deepcopy(policy)
        broken["h4_bias"]["unknown"] = True
        invalid.append(("H4 มี key", broken))
        broken = copy.deepcopy(policy)
        broken["m30_readiness"]["unknown"] = True
        invalid.append(("M30 มี key", broken))
        broken = copy.deepcopy(policy)
        broken["m30_readiness"]["adx_threshold"] = 20.5
        invalid.append(("integer 20", broken))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "decision-policy.json"
            for message, candidate in invalid:
                with self.subTest(message=message):
                    path.write_text(json.dumps(candidate), encoding="utf-8")
                    with self.assertRaisesRegex(RuntimeError, message):
                        forex_daily_plan.load_decision_policy(path)

    def test_h4_conflict_stays_neutral_instead_of_forcing_a_side(self):
        h4 = dict(self.GBPUSD_2026_09_01_H4,
                  bias=None, structure="higher_high_low")
        preferred, reason = forex_daily_plan.preferred_direction(h4)
        self.assertIsNone(preferred)
        self.assertIn("NEUTRAL", reason)
        model, model_reason = forex_daily_plan.choose_model(None, {})
        self.assertEqual(model, "NO_SETUP")
        self.assertIn("NEUTRAL", model_reason)

    def test_m30_core_is_dmi_plus_adx_and_supertrend_is_supporting_only(self):
        policy = forex_daily_plan.load_decision_policy()
        h = {
            "dmi": {"plus_di": 30, "minus_di": 10, "adx": 21},
            "supertrend": {"direction": "down"},
        }
        self.assertTrue(forex_daily_plan.m30_gate_pass(h, "up", policy))
        read = forex_daily_plan.m30_read(h, "up", policy)
        self.assertIn("ไม่ใช่เงื่อนไข gate", read)
        model, reason = forex_daily_plan.choose_model(
            "up", {"H": h, "I": {"state": "NORMAL"}}, policy)
        self.assertEqual(model, "WAIT")
        self.assertIn("M15", reason)

        low_adx = copy.deepcopy(h)
        low_adx["dmi"]["adx"] = 19
        low_adx["supertrend"]["direction"] = "up"
        self.assertFalse(forex_daily_plan.m30_gate_pass(low_adx, "up", policy))

        trace = forex_daily_plan.decision_policy_trace(
            policy, self.GBPUSD_2026_09_01_H4, {"H": h}, "up")
        self.assertEqual(trace["policy_version"], "style-l-decision-policy/v2")
        self.assertEqual(trace["m30"]["core"], ["dmi_direction", "adx_threshold"])
        self.assertEqual(trace["m30"]["supporting"], ["supertrend"])
        self.assertTrue(trace["m30"]["core_ready"])
        self.assertFalse(trace["m30"]["supertrend_aligned"])

    def test_neutral_final_article_has_no_forced_side_or_trigger(self):
        policy = forex_daily_plan.load_decision_policy()
        h4 = dict(self.GBPUSD_2026_09_01_H4,
                  bias=None, structure="higher_high_low")
        h1 = self.GBPUSD_2026_09_01_H1
        states = {
            "H": {
                "dmi": {"plus_di": 30, "minus_di": 10, "adx": 21},
                "supertrend": {"direction": "down"},
            },
            "I": {}, "J": {},
        }
        preferred, preferred_reason = forex_daily_plan.preferred_direction(h4)
        model, reason = forex_daily_plan.choose_model(h4["bias"], states, policy)
        plan = forex_daily_plan.scenario(model, h4["bias"], preferred, h1, states)
        bases = {key: {"basis_close_at": "2026-09-01T09:00:00+07:00"}
                 for key in forex_daily_plan.TIMEFRAMES}
        article = forex_daily_plan.render_article(
            "gbpusd", datetime(2026, 9, 1, 2, 32, 46, tzinfo=timezone.utc),
            h4, h1, states, model, reason, plan, preferred, preferred_reason, [],
            "a" * 64, ("gbpusd-forex-daily-h1-plan.webp",
                       "gbpusd-forex-daily-m15-trigger.webp"),
            bases, {"previous": "fixture", "change": "fixture"}, policy)
        final = forex_daily_plan.publicize_style_l(article, "gbpusd")
        self.assertIn("**ฝั่งที่ให้น้ำหนัก: NEUTRAL**", final)
        self.assertNotIn("**ฝั่งที่ให้น้ำหนัก: BUY**", final)
        self.assertNotIn("**ฝั่งที่ให้น้ำหนัก: SELL**", final)
        self.assertIn("| Trigger | — ไม่มี trigger จนกว่า H4 จะชัด |", final)
        self.assertNotIn("Pre-trigger plan ฝั่ง", final)
        findings = (
            forex_daily_plan.validate_article(final, "gbpusd", plan)
            + forex_daily_plan.validate_data_domain("gbpusd", h4, h1, plan)
            + forex_daily_plan.validate_markdown_snapshot_parity(
                final, "gbpusd", h4, h1, plan, preferred)
        )
        self.assertEqual(findings, [])

    def test_neutral_m15_chart_has_no_directional_lines_arrow_or_text(self):
        rows = [{
            "at": "2026-09-01 09:00:00",
            "high": 1.35597,
            "low": 1.35415,
        }]
        plan = self.GBPUSD_2026_09_01_PLAN
        basis = {"basis_close_at": "2026-09-01T09:15:00+07:00"}
        with mock.patch.object(forex_daily_plan, "_thai_font"), \
                mock.patch.object(forex_daily_plan, "candle_plot"), \
                mock.patch.object(forex_daily_plan, "add_price_line") as price_line, \
                mock.patch("matplotlib.axes.Axes.annotate") as annotate, \
                mock.patch("matplotlib.figure.Figure.tight_layout"), \
                mock.patch.object(
                    forex_daily_plan.image_output, "save_figure", return_value=123) as save:
            size = forex_daily_plan.save_m15_chart(
                "gbpusd", rows, "NO_SETUP", {"H": {}, "I": {}},
                plan, None, basis, forex_daily_plan.load_decision_policy(),
                Path("unused.webp"))

        self.assertEqual(size, 123)
        price_line.assert_not_called()
        annotate.assert_not_called()
        figure = save.call_args.args[0]
        axis = figure.axes[0]
        visible_text = " ".join(
            [axis.get_title(), *(text.get_text() for text in axis.texts)])
        self.assertIn("NEUTRAL", visible_text)
        self.assertIn("M30: ไม่ประเมินเมื่อ H4 NEUTRAL", visible_text)
        self.assertNotIn("BUY", visible_text)
        self.assertNotIn("SELL", visible_text)
        self.assertNotIn("ปิดเหนือ", visible_text)
        self.assertNotIn("ปิดต่ำกว่า", visible_text)

    def test_weekday_schedule_is_exactly_five_two_asset_batches(self):
        self.assertEqual(forex_daily_plan.ASSETS,
                         ("eurusd", "gbpusd", "usdjpy", "audusd", "usdcad"))
        batches = [
            forex_daily_plan.scheduled_assets(
                datetime(2026, 8, day, 5, 0, tzinfo=timezone.utc))
            for day in range(24, 29)
        ]
        self.assertEqual(batches, [
            ["eurusd", "usdjpy"],
            ["gbpusd", "audusd"],
            ["eurusd", "usdjpy"],
            ["gbpusd", "usdcad"],
            ["eurusd", "usdjpy"],
        ])
        self.assertEqual(sum(map(len, batches)), 10)
        self.assertEqual(Counter(asset for batch in batches for asset in batch), {
            "eurusd": 3, "usdjpy": 3, "gbpusd": 2,
            "audusd": 1, "usdcad": 1,
        })

    def test_weekend_schedule_skips(self):
        self.assertEqual(forex_daily_plan.scheduled_assets(
            datetime(2026, 8, 29, 5, 0, tzinfo=timezone.utc)), [])
        self.assertEqual(forex_daily_plan.scheduled_assets(
            datetime(2026, 8, 30, 5, 0, tzinfo=timezone.utc)), [])

    def test_schedule_loader_returns_schema_v2_tuple_batches(self):
        self.assertEqual(forex_daily_plan.load_schedule(), {
            0: ("eurusd", "usdjpy"),
            1: ("gbpusd", "audusd"),
            2: ("eurusd", "usdjpy"),
            3: ("gbpusd", "usdcad"),
            4: ("eurusd", "usdjpy"),
        })

    def test_schedule_loader_rejects_every_contract_deviation(self):
        valid = {
            "schema_version": 2,
            "timezone": "Asia/Bangkok",
            "description": "fixture",
            "weekday_asset_batches": {
                "0": ["eurusd", "usdjpy"],
                "1": ["gbpusd", "audusd"],
                "2": ["eurusd", "usdjpy"],
                "3": ["gbpusd", "usdcad"],
                "4": ["eurusd", "usdjpy"],
            },
            "weekend_policy": "skip",
            "swap_policy": "never",
            "publish_lane": "forex",
            "gold_lane_unchanged": True,
        }
        invalid: list[tuple[str, dict]] = []

        def changed(name: str, *path_and_value: object) -> None:
            candidate = copy.deepcopy(valid)
            *path, value = path_and_value
            target = candidate
            for key in path[:-1]:
                target = target[key]  # type: ignore[index]
            target[path[-1]] = value  # type: ignore[index]
            invalid.append((name, candidate))

        changed("schema version", "schema_version", 1)
        changed("timezone", "timezone", "UTC")
        changed("schedule type", "weekday_asset_batches", [])
        changed("missing weekday", "weekday_asset_batches", {
            key: value for key, value in valid["weekday_asset_batches"].items()
            if key != "4"
        })
        changed("batch type", "weekday_asset_batches", "0", "eurusd")
        changed("batch count", "weekday_asset_batches", "0", ["eurusd"])
        changed("duplicate", "weekday_asset_batches", "0", ["eurusd", "eurusd"])
        changed("unsupported", "weekday_asset_batches", "0", ["eurusd", "xauusd"])
        changed("not exact", "weekday_asset_batches", "3", ["usdcad", "gbpusd"])
        changed("weekend policy", "weekend_policy", "run")
        changed("swap policy", "swap_policy", "allowed")
        changed("publish lane", "publish_lane", "other")
        changed("gold lane", "gold_lane_unchanged", False)
        invalid.append(("missing key", {
            key: value for key, value in valid.items()
            if key != "weekday_asset_batches"
        }))

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "schedule.json"
            for name, payload in invalid:
                with self.subTest(name=name):
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(RuntimeError, "Forex schedule"):
                        forex_daily_plan.load_schedule(path)

    def test_relevant_events_include_aud_and_cad(self):
        events = [
            {"country": "AUD", "title": "RBA", "impact": "High",
             "at": "2026-08-28 08:00"},
            {"country": "CAD", "title": "BoC", "impact": "High",
             "at": "2026-08-28 09:00"},
            {"country": "USD", "title": "CPI", "impact": "High",
             "at": "2026-08-28 10:00"},
            {"country": "JPY", "title": "BoJ", "impact": "High",
             "at": "2026-08-28 11:00"},
        ]
        cutoff = datetime(2026, 8, 28, 5, 0, tzinfo=timezone.utc)
        self.assertEqual([row["title"] for row in forex_daily_plan.relevant_events(
            "audusd", events, cutoff)], ["RBA", "CPI"])
        self.assertEqual([row["title"] for row in forex_daily_plan.relevant_events(
            "usdcad", events, cutoff)], ["BoC", "CPI"])

    def test_style_l_is_registered_for_production(self):
        registry = RegistryLoader().load(
            Path(__file__).resolve().parents[1] / "config" / "article_styles.json")
        entry = registry.styles[forex_daily_plan.STYLE_ID]
        unit = registry.execution_units[entry.execution_unit]

        self.assertEqual(entry.letter, forex_daily_plan.STYLE_LETTER)
        self.assertEqual(entry.adapter, "forex_daily_plan")
        self.assertEqual(entry.assets, forex_daily_plan.ASSETS)
        self.assertEqual(entry.timeframes, forex_daily_plan.TIMEFRAMES)
        self.assertTrue(entry.production)
        self.assertEqual(unit.members, (forex_daily_plan.STYLE_ID,))
        self.assertFalse(unit.execute_once_per_asset)

    def test_h4_inset_is_removed_only_from_usdjpy(self):
        self.assertFalse(forex_daily_plan.h4_inset_enabled("usdjpy"))
        self.assertTrue(forex_daily_plan.h4_inset_enabled("eurusd"))
        self.assertTrue(forex_daily_plan.h4_inset_enabled("gbpusd"))

    def test_style_l_preserves_asset_precision_without_changing_shared_policy(self):
        article = "ราคา 1.35415 · ATR 0.00099 · ADX 18.1 · ใช้ระยะ 32.9%"
        final = forex_daily_plan.publicize_style_l(article, "gbpusd")
        self.assertEqual(final,
                         "ราคา 1.35415 · ATR 0.00099 · ADX 18 · ใช้ระยะ 33%")
        for asset in forex_daily_plan.ASSETS:
            decimals = forex_daily_plan.wcb_source.profile_for(asset)["decimals"]
            token = "159.123" if decimals == 3 else "1.23456"
            with self.subTest(asset=asset):
                self.assertEqual(
                    forex_daily_plan.publicize_style_l(
                        f"ราคา {token} · ADX 18.1", asset),
                    f"ราคา {token} · ADX 18")
        self.assertEqual(
            forex_daily_plan.validate_style_l_number_policy(final, "gbpusd"), [])
        self.assertEqual(
            forex_daily_plan.public_number_policy.publicize(article),
            "ราคา 1 · ATR 0 · ADX 18 · ใช้ระยะ 33%")

    def test_gbpusd_2026_09_01_bad_public_markdown_is_blocked_by_parity(self):
        broken = """| Trigger | M15 ปิดต่ำกว่า `1` |
ราคาอยู่ใต้ EMA โดยปิดที่ 1 เทียบกับ EMA20 1 และ EMA50 1
ราคาปิด H1 ล่าสุดอยู่ที่ 1
- High/Low วันก่อน: `1` / `1`
- ช่วงจากแท่ง H1 ที่ปิดแล้ววันนี้: `1`–`1`
- ATR14 H1: `0`
- ADR14 จากแท่ง D1 ปิด: `0`
- ช่วงที่ใช้แล้ว: `33%` ของ ADR14
- กรอบเฝ้าดู: `1`–`1`
"""
        findings = forex_daily_plan.validate_markdown_snapshot_parity(
            broken, "gbpusd", self.GBPUSD_2026_09_01_H4,
            self.GBPUSD_2026_09_01_H1, self.GBPUSD_2026_09_01_PLAN, "down")
        self.assertTrue(findings)
        self.assertTrue(any("trigger" in finding for finding in findings))
        self.assertTrue(any("ATR14" in finding for finding in findings))

    def test_gbpusd_2026_09_01_final_markdown_passes_snapshot_parity(self):
        h4 = self.GBPUSD_2026_09_01_H4
        h1 = self.GBPUSD_2026_09_01_H1
        plan = self.GBPUSD_2026_09_01_PLAN
        final = "\n".join((
            "| Trigger | M15 ปิดต่ำกว่า `1.35415` |",
            "M15 ยังต้องปิดต่ำกว่า 1.35415 ดังนั้นแผนปัจจุบันคือรอ",
            "โดยปิดที่ 1.35532 เทียบกับ EMA20 1.35671 และ EMA50 1.35793",
            "ราคาปิด H1 ล่าสุดอยู่ที่ 1.35454",
            "- High/Low วันก่อน: `1.35652` / `1.35342`",
            "- ช่วงจากแท่ง H1 ที่ปิดแล้ววันนี้: `1.35422`–`1.35597`",
            "- ATR14 H1: `0.00099`",
            "- ADR14 จากแท่ง D1 ปิด: `0.00532`",
            "- ช่วงที่ใช้แล้ว: `33%` ของ ADR14",
            "- กรอบเฝ้าดู: `1.35415`–`1.35597`",
            "- จากนั้น M15 ต้องปิดต่ำกว่า `1.35415`; การแตะระดับยังไม่นับ",
            "ยกเลิกแผนเฝ้ารอหาก H4 ปิดเหนือ EMA ทั้งคู่บริเวณ 1.35793 และโครงสร้างไม่ทำ Lower High/Lower Low ต่อ",
            "- ยกเลิกแผนเฝ้ารอหาก H4 ปิดเหนือ EMA ทั้งคู่บริเวณ 1.35793 และโครงสร้างไม่ทำ Lower High/Lower Low ต่อ",
        ))
        self.assertEqual(forex_daily_plan.validate_markdown_snapshot_parity(
            final, "gbpusd", h4, h1, plan, "down"), [])

    def test_zero_atr_or_invalid_price_order_is_blocked(self):
        h1 = dict(self.GBPUSD_2026_09_01_H1, atr14=0, pdh=1.35342, pdl=1.35652)
        findings = forex_daily_plan.validate_data_domain(
            "gbpusd", self.GBPUSD_2026_09_01_H4, h1,
            self.GBPUSD_2026_09_01_PLAN)
        self.assertTrue(any("ATR14" in finding for finding in findings))
        self.assertTrue(any("PDH" in finding for finding in findings))

    def test_unreasonable_scenario_and_inconsistent_adr_used_are_blocked(self):
        plan = dict(self.GBPUSD_2026_09_01_PLAN,
                    watch_low=9.0, watch_high=10.0)
        h1 = dict(self.GBPUSD_2026_09_01_H1, adr_used_pct=9999)
        findings = forex_daily_plan.validate_data_domain(
            "gbpusd", self.GBPUSD_2026_09_01_H4, h1, plan)
        self.assertTrue(any("reasonable domain" in finding for finding in findings))
        self.assertTrue(any("ADR used percent" in finding for finding in findings))

    def test_parity_rejects_duplicate_trigger_cancel_invalidation_and_target2(self):
        h4 = self.GBPUSD_2026_09_01_H4
        h1 = self.GBPUSD_2026_09_01_H1
        wait = self.GBPUSD_2026_09_01_PLAN
        wait_article = self._critical_article(h4, h1, wait, "down")
        cancel = forex_daily_plan.watch_cancel_rule("gbpusd", h4, "down")
        broken_wait = wait_article.replace(cancel, cancel.replace("1.35793", "9.00000"), 1)
        wait_findings = forex_daily_plan.validate_markdown_snapshot_parity(
            broken_wait, "gbpusd", h4, h1, wait, "down")
        self.assertTrue(any("cancel rule" in finding for finding in wait_findings))

        active = {
            "active": True, "direction": "down",
            "entry": 1.35400, "stop": 1.35500,
            "target1": 1.35300, "target2": 1.35200,
            "invalidation_h1": 1.35600,
        }
        active_article = self._critical_article(h4, h1, active, "down")
        duplicate = active_article + "\n| Trigger | M15 ปิดต่ำกว่า `9.00000` |"
        duplicate_findings = forex_daily_plan.validate_markdown_snapshot_parity(
            duplicate, "gbpusd", h4, h1, active, "down")
        self.assertTrue(any("trigger" in finding for finding in duplicate_findings))

        broken_active = active_article.replace(
            "- Target 1 / Target 2: `1.35300` / `1.35200`",
            "- Target 1 / Target 2: `1.35300` / `9.00000`").replace(
            "- หาก H1 ปิดสวนผ่าน `1.35600`",
            "- หาก H1 ปิดสวนผ่าน `9.00000`")
        active_findings = forex_daily_plan.validate_markdown_snapshot_parity(
            broken_active, "gbpusd", h4, h1, active, "down")
        self.assertTrue(any("targets" in finding for finding in active_findings))
        self.assertTrue(any("invalidation" in finding for finding in active_findings))

    def _critical_article(self, h4: dict, h1: dict, plan: dict,
                          preferred: str) -> str:
        asset = "gbpusd"
        price = lambda value: forex_daily_plan.fmt(asset, value)
        trigger = plan.get("entry") or (
            plan["watch_high"] if preferred == "up" else plan["watch_low"])
        trigger_word = "เหนือ" if preferred == "up" else "ต่ำกว่า"
        lines = [
            f"| Trigger | M15 ปิด{trigger_word} `{price(trigger)}` |",
            (f"โดยปิดที่ {price(h4['close'])} เทียบกับ EMA20 {price(h4['ema20'])} "
             f"และ EMA50 {price(h4['ema50'])}"),
            f"ราคาปิด H1 ล่าสุดอยู่ที่ {price(h1['close'])}",
            f"- High/Low วันก่อน: `{price(h1['pdh'])}` / `{price(h1['pdl'])}`",
            (f"- ช่วงจากแท่ง H1 ที่ปิดแล้ววันนี้: `{price(h1['current_low'])}`–"
             f"`{price(h1['current_high'])}`"),
            f"- ATR14 H1: `{price(h1['atr14'])}`",
            f"- ADR14 จากแท่ง D1 ปิด: `{price(h1['adr14'])}`",
            (f"- ช่วงที่ใช้แล้ว: "
             f"`{forex_daily_plan.public_number_policy.percent(h1['adr_used_pct'])}` "
             "ของ ADR14"),
        ]
        if plan.get("active"):
            cancel = (f"ยกเลิก setup หากแตะจุดยกเลิก {price(plan['stop'])}; "
                      f"หาก H1 ปิดสวนผ่าน {price(plan['invalidation_h1'])} "
                      "ให้ประเมินใหม่")
            lines += [
                cancel,
                (f"แผนจึงอยู่สถานะ ACTIVE โดยใช้ {price(plan['entry'])} เป็น trigger "
                 f"และ {price(plan['stop'])} เป็นจุดยกเลิก"),
                f"- Entry trigger: `{price(plan['entry'])}`",
                f"- จุดยกเลิก: `{price(plan['stop'])}`",
                (f"- Target 1 / Target 2: `{price(plan['target1'])}` / "
                 f"`{price(plan['target2'])}`"),
                (f"- หาก H1 ปิดสวนผ่าน `{price(plan['invalidation_h1'])}` "
                 "ให้ยกเลิก bias และประเมินใหม่ ไม่กลับฝั่งอัตโนมัติ"),
            ]
        else:
            cancel = forex_daily_plan.watch_cancel_rule(asset, h4, preferred)
            lines += [
                f"M15 ยังต้องปิด{trigger_word} {price(trigger)} ดังนั้นแผนปัจจุบันคือรอ",
                (f"- กรอบเฝ้าดู: `{price(plan['watch_low'])}`–"
                 f"`{price(plan['watch_high'])}`"),
                f"- จากนั้น M15 ต้องปิด{trigger_word} `{price(trigger)}`; การแตะยังไม่นับ",
                cancel,
                f"- {cancel}",
            ]
        return "\n".join(lines)

    def _run_round_fixture(self, plan: dict, article: str) -> tuple:
        h4 = self.GBPUSD_2026_09_01_H4
        h1 = self.GBPUSD_2026_09_01_H1
        cutoff = datetime(2026, 9, 1, 2, 32, 46, tzinfo=timezone.utc)
        frozen_policy = forex_daily_plan.load_decision_policy()

        def save_image(*args):
            path = args[-1]
            path.write_bytes(b"fixture-image")
            return path.stat().st_size

        basis = {"basis_close_at": "2026-09-01T09:00:00+07:00"}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(forex_daily_plan, "REPO", root))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "STATE", root / "state"))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "load_decision_policy",
                    return_value=frozen_policy))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "fetch_events",
                    return_value=([], {"status": "ok", "provider": "fixture"})))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "closed_intraday",
                    return_value=([{"close": h1["close"]}], basis,
                                  {"source": "fixture"})))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "closed_daily",
                    return_value=([{"close": h1["close"]}], basis,
                                  {"source": "fixture"})))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "h4_context", return_value=h4))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "h1_map", return_value=h1))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "intraday_state", return_value={}))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "preferred_direction",
                    return_value=(plan["direction"], "fixture")))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "choose_model",
                    return_value=("I" if plan["active"] else "WAIT", "fixture")))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "scenario", return_value=plan))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "continuity_snapshot",
                    return_value=({}, {"previous": "fixture", "change": "fixture"})))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "save_h1_chart", side_effect=save_image))
                m15_chart = stack.enter_context(mock.patch.object(
                    forex_daily_plan, "save_m15_chart", side_effect=save_image))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan.image_output, "verify"))
                render = stack.enter_context(mock.patch.object(
                    forex_daily_plan, "render_article", return_value=article))
                trace = stack.enter_context(mock.patch.object(
                    forex_daily_plan, "decision_policy_trace",
                    wraps=forex_daily_plan.decision_policy_trace))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "validate_article", return_value=[]))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "overlap",
                    return_value={"max_jaccard": 0.0,
                                  "comparison_count": 0, "top": []}))
                copy_file = stack.enter_context(mock.patch.object(
                    forex_daily_plan.shutil, "copy2"))
                result = forex_daily_plan.run_round(
                    assets=["gbpusd"], publish_root=root / "output",
                    cutoff_at=cutoff, publish=True)
                return (result, copy_file, frozen_policy,
                        m15_chart, render, trace)

    def test_run_round_corrupted_final_wait_markdown_blocks_promotion(self):
        plan = self.GBPUSD_2026_09_01_PLAN
        article = self._critical_article(
            self.GBPUSD_2026_09_01_H4, self.GBPUSD_2026_09_01_H1, plan, "down")
        article = article.replace(
            "| Trigger | M15 ปิดต่ำกว่า `1.35415` |",
            "| Trigger | M15 ปิดต่ำกว่า `9.00000` |")
        result, copy_file, *_ = self._run_round_fixture(plan, article)
        self.assertFalse(result["ok"])
        self.assertTrue(any("trigger" in error for error in result["errors"]))
        copy_file.assert_not_called()

    def test_run_round_valid_wait_and_active_final_markdown_pass(self):
        active = {
            "active": True, "direction": "down",
            "entry": 1.35400, "stop": 1.35500,
            "target1": 1.35300, "target2": 1.35200,
            "invalidation_h1": 1.35600,
        }
        for name, plan in (("wait", self.GBPUSD_2026_09_01_PLAN),
                           ("active", active)):
            with self.subTest(state=name):
                article = self._critical_article(
                    self.GBPUSD_2026_09_01_H4,
                    self.GBPUSD_2026_09_01_H1, plan, "down")
                (result, copy_file, frozen_policy,
                 m15_chart, render, trace) = self._run_round_fixture(plan, article)
                self.assertTrue(result["ok"], result["errors"])
                self.assertEqual(result["assets"]["gbpusd"]["status"], "PASS_QA")
                self.assertEqual(
                    result["assets"]["gbpusd"]["decision_policy_version"],
                    "style-l-decision-policy/v2")
                self.assertIs(m15_chart.call_args.args[-2], frozen_policy)
                self.assertIs(render.call_args.args[-1], frozen_policy)
                self.assertIs(trace.call_args.args[0], frozen_policy)
                self.assertEqual(copy_file.call_count, 3)

    def test_news_is_combined_in_one_table(self):
        cutoff = datetime(2026, 8, 21, 5, 0, tzinfo=timezone.utc)
        events = [
            {"country": "JPY", "at": "2026-08-21 07:30", "title": "ข่าวเช้า",
             "actual": "52.0", "previous": "51.0"},
            {"country": "USD", "at": "2026-08-21 21:00", "title": "ข่าวค่ำ",
             "forecast": "1.0", "previous": "0.8"},
        ]
        rows, next_event = forex_daily_plan.event_sections(events, cutoff)
        self.assertEqual(len(rows), 2)
        self.assertIn("ประกาศแล้ว", rows[0])
        self.assertIn("รอติดตาม", rows[1])
        self.assertIn("ข่าวค่ำ", next_event)

    def test_removed_copy_is_detected(self):
        for phrase in forex_daily_plan.DEPRECATED_COPY:
            with self.subTest(phrase=phrase):
                self.assertEqual(forex_daily_plan.deprecated_copy_in(phrase), [phrase])
        self.assertEqual(forex_daily_plan.deprecated_copy_in("เนื้อหาใหม่"), [])

    def test_paragraph_indent_uses_em_space_entity(self):
        self.assertEqual(forex_daily_plan.indent_paragraph("ย่อหน้า"),
                         "&emsp;ย่อหน้า")
        self.assertEqual(forex_daily_plan.indent_paragraph("&emsp;ย่อหน้า"),
                         "&emsp;ย่อหน้า")

    def test_internal_chart_links_use_live_relative_routes(self):
        expected = {
            "usdjpy": "/thailand/asset-usdjpy",
            "eurusd": "/thailand/asset-eurusd",
            "gbpusd": "/thailand/asset-gbpusd",
            "audusd": "/thailand/asset-audusd",
            "usdcad": "/thailand/asset-hub",
        }
        for asset, path in expected.items():
            with self.subTest(asset=asset):
                text = forex_daily_plan.internal_chart_links(asset)
                ticker = forex_daily_plan.wcb_source.profile_for(
                    asset)["symbol"].replace("/", "")
                self.assertTrue(text.startswith("&emsp;"))
                self.assertIn(f"ติดตามราคา {ticker} แบบเรียลไทม์", text)
                self.assertIn(f"]({path})", text)
                if path != forex_daily_plan.ASSET_HUB_PATH:
                    self.assertIn(f"[หน้าราคา {ticker}]({path})", text)
                self.assertIn("](/thailand/analysis)", text)
                self.assertNotIn("http://", text)
                self.assertNotIn("https://", text)

    def test_closed_bar_contract_accepts_wait_and_active_wording(self):
        self.assertTrue(forex_daily_plan.has_closed_bar_confirmation(
            "M30 ต้องผ่านครบก่อน และ M15 ต้องปิดเหนือ trigger"))
        self.assertTrue(forex_daily_plan.has_closed_bar_confirmation(
            "M30 ผ่านกฎฝั่ง BUY แล้ว และ M15 ปิดเบรกกรอบแล้ว"))
        self.assertFalse(forex_daily_plan.has_closed_bar_confirmation(
            "M30 ผ่านกฎฝั่ง BUY แล้ว แต่ M15 แตะ trigger ระหว่างแท่ง"))

    def test_friday_expiry_does_not_carry_to_monday(self):
        friday = datetime(2026, 8, 28, 3, 0, tzinfo=timezone.utc)
        monday = datetime(2026, 8, 31, 3, 0, tzinfo=timezone.utc)
        notice = forex_daily_plan.friday_expiry_notice(friday)
        self.assertIn("ไม่ถือสถานะหรือเงื่อนไขเดิมข้ามไปวันจันทร์", notice)
        self.assertIsNone(forex_daily_plan.friday_expiry_notice(monday))

    def test_frontmatter_contract_has_exact_ten_fields(self):
        article = """---
asset: usdjpy
title: t
slug: s
excerpt: e
author_slug: a
timeframe: Daily
trend: down
status: draft
country: thailand
language: th
---
"""
        self.assertEqual(forex_daily_plan.frontmatter_keys(article), [
            "asset", "title", "slug", "excerpt", "author_slug", "timeframe", "trend",
            "status", "country", "language"])

    def test_usdcad_is_held_out_of_web_import_until_registered(self):
        self.assertFalse(forex_daily_plan.web_import_eligible("usdcad"))
        for asset in ("eurusd", "gbpusd", "usdjpy", "audusd"):
            with self.subTest(asset=asset):
                self.assertTrue(forex_daily_plan.web_import_eligible(asset))

        files = [Path("staging/usdjpy/usdjpy.md"), Path("staging/usdcad/usdcad.md")]
        self.assertEqual(forex_daily_plan.web_import_sources(files), [files[0]])

    def test_calendar_failure_is_fail_closed_before_market_fetch(self):
        cutoff = datetime(2026, 8, 21, 5, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with mock.patch.object(forex_daily_plan, "REPO", root), \
                    mock.patch.object(forex_daily_plan, "STATE", root / "state"), \
                    mock.patch.object(
                        forex_daily_plan, "fetch_events",
                        return_value=([], {"status": "unavailable", "reason": "fixture"})), \
                    mock.patch.object(forex_daily_plan, "closed_intraday") as market:
                result = forex_daily_plan.run_round(
                    assets=["usdjpy"], publish_root=root / "output", cutoff_at=cutoff)
        self.assertFalse(result["ok"])
        self.assertIn("calendar feed unavailable", result["errors"][0])
        market.assert_not_called()

    def test_decision_policy_failure_is_fail_closed_before_calendar_or_market(self):
        cutoff = datetime(2026, 9, 1, 2, 32, 46, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with mock.patch.object(forex_daily_plan, "REPO", root), \
                    mock.patch.object(forex_daily_plan, "STATE", root / "state"), \
                    mock.patch.object(
                        forex_daily_plan, "load_decision_policy",
                        side_effect=RuntimeError("fixture policy invalid")), \
                    mock.patch.object(forex_daily_plan, "fetch_events") as calendar, \
                    mock.patch.object(forex_daily_plan, "closed_intraday") as market:
                result = forex_daily_plan.run_round(
                    assets=["gbpusd"], publish_root=root / "output",
                    cutoff_at=cutoff)
        self.assertFalse(result["ok"])
        self.assertIn("fixture policy invalid", result["errors"])
        calendar.assert_not_called()
        market.assert_not_called()

    def test_asset_failure_blocks_the_whole_batch_before_promotion(self):
        cutoff = datetime(2026, 8, 27, 5, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with mock.patch.object(forex_daily_plan, "REPO", root), \
                    mock.patch.object(forex_daily_plan, "STATE", root / "state"), \
                    mock.patch.object(
                        forex_daily_plan, "fetch_events",
                        return_value=([], {"status": "ok", "provider": "fixture"})) as calendar, \
                    mock.patch.object(
                        forex_daily_plan, "closed_intraday",
                        side_effect=RuntimeError("fixture market failure")), \
                    mock.patch.object(forex_daily_plan.shutil, "copy2") as copy_file:
                result = forex_daily_plan.run_round(
                    assets=["gbpusd", "usdcad"],
                    publish_root=root / "output", cutoff_at=cutoff)
        self.assertFalse(result["ok"])
        self.assertEqual(calendar.call_count, 1)
        self.assertEqual(result["destination"] if "destination" in result else None, None)
        copy_file.assert_not_called()

    def test_naive_cutoff_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            forex_daily_plan.parse_cutoff("2026-08-21T12:00:00")


if __name__ == "__main__":
    unittest.main()
