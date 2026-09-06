from __future__ import annotations

import copy
import json
import re
import tempfile
import unittest
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tools import forex_daily_plan, visual_theme
from tools.unified_registry import RegistryLoader


FIXED_CUTOFF = datetime(2026, 9, 1, 2, 32, 46, tzinfo=timezone.utc)
FIXED_EVIDENCE_HASH = "a" * 64


def _canonical_plan(*, direction: str | None = "down", current_close: float = 1.35454) -> dict:
    h1 = {
        "close": 1.35454, "pdh": 1.35652, "pdl": 1.35342,
        "atr14": 0.000989919911447963,
    }
    states = {"I": {"donchian": {"lower": 1.35415, "upper": 1.35597}}}
    crossed = ((direction == "down" and current_close < 1.35415)
               or (direction == "up" and current_close > 1.35597))
    return forex_daily_plan.scenario(
        "I" if crossed else "WAIT" if direction is not None else "NO_SETUP",
        direction, direction,
        h1, states, asset="gbpusd", cutoff=FIXED_CUTOFF,
        evidence_hash=FIXED_EVIDENCE_HASH, current_close=current_close)


def _usdcad_oco_plan() -> dict:
    """Fixed neutral OCO plan matching the 2026-09-03 review snapshot."""
    plan = copy.deepcopy(_canonical_plan(direction=None))
    plan.update({"current_close": 1.38349, "watch_low": 1.38320,
                 "watch_high": 1.38473})
    plan["plans"] = [
        {"side": "BUY", "trigger": {"condition": "M15_CLOSE_ABOVE", "value": 1.38473},
         "entry_zone": {"low": 1.38473, "high": 1.38473},
         "stop_loss": 1.38366, "take_profit": [1.38580, 1.38686],
         "risk_reward": [1.0, 1.9907], "rr_basis": "gross_pre_cost",
         "invalidation": {"condition": "H1_CLOSE_BELOW", "value": 1.38373}},
        {"side": "SELL", "trigger": {"condition": "M15_CLOSE_BELOW", "value": 1.38320},
         "entry_zone": {"low": 1.38320, "high": 1.38320},
         "stop_loss": 1.38427, "take_profit": [1.38213, 1.38107],
         "risk_reward": [1.0, 1.9907], "rr_basis": "gross_pre_cost",
         "invalidation": {"condition": "H1_CLOSE_ABOVE", "value": 1.39400}},
    ]
    return plan


class ForexDailyPlanContract(unittest.TestCase):

    def assert_edge_header_contract(self, figure):
        header = figure._premium_header_layout
        expected_width = figure.bbox.width
        self.assertLessEqual(header["header_x0_px"], 1)
        self.assertGreaterEqual(header["header_x1_px"], expected_width - 1)
        self.assertLessEqual(header["header_width_delta_px"], 2)
        self.assertLessEqual(header["header_top_gap_px"], 1)
        self.assertLessEqual(header["underline_x0_px"], 1)
        self.assertGreaterEqual(header["underline_x1_px"], expected_width - 1)
        self.assertLessEqual(header["underline_width_delta_px"], 2)
        self.assertGreaterEqual(header["underline_height_px"], 3)
        self.assertLessEqual(header["underline_height_px"], 6)
        self.assertGreaterEqual(header["underline_height_px_at_768"], 1)
        self.assertLessEqual(header["title_plot_start_delta_px"], 4)
        self.assertLessEqual(header["title_plot_start_delta_px_at_768"], 2)
        self.assertGreaterEqual(header["title_top_padding_px"], 10)
        self.assertGreaterEqual(header["title_bottom_padding_px"], 10)
        self.assertLessEqual(header["title_center_delta_px"], 2)
        self.assertLessEqual(header["title_center_delta_px_at_768"], 1)
        self.assertLessEqual(header["title_padding_imbalance_px"], 4)
        self.assertLessEqual(header["title_padding_imbalance_px_at_768"], 2)
        self.assertGreaterEqual(header["title_height_px_at_768"], 14)
        self.assertFalse(header["title_clipped"])

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
    GBPUSD_2026_09_01_PLAN = _canonical_plan()

    def test_h1_near_price_tags_get_display_offsets_without_moving_levels(self):
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(14, 7.5), dpi=120)
        try:
            ax.set_ylim(1.157, 1.168)
            levels = [("pdh", 1.15888), ("close", 1.15908), ("pdl", 1.15781)]
            offsets = forex_daily_plan.resolved_right_label_offsets(ax, levels)
            point_scale = 72.0 / fig.dpi
            placed = {}
            for role, value in levels:
                actual = ax.transData.transform((0, value))[1] * point_scale
                placed[role] = actual + offsets[role]
            self.assertGreaterEqual(abs(placed["close"] - placed["pdh"]), 24.0)
            self.assertNotEqual(offsets["close"], 0.0)
            self.assertNotEqual(offsets["pdh"], 0.0)
            self.assertEqual([value for _, value in levels],
                             [1.15888, 1.15908, 1.15781])
        finally:
            plt.close(fig)

    def test_thai_tick_is_single_line_date_and_time(self):
        label = forex_daily_plan.thai_tick("2026-08-28 05:30:00")
        self.assertEqual(label, "28 ส.ค. 05:30")
        self.assertNotIn("\n", label)

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

    def test_neutral_final_article_has_complete_oco_without_forced_bias(self):
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
        plan = forex_daily_plan.scenario(
            model, h4["bias"], preferred, h1, states, asset="gbpusd",
            cutoff=FIXED_CUTOFF, evidence_hash=FIXED_EVIDENCE_HASH,
            current_close=h1["close"])
        bases = {key: {"basis_close_at": "2026-09-01T09:00:00+07:00"}
                 for key in forex_daily_plan.TIMEFRAMES}
        article = forex_daily_plan.render_article(
            "gbpusd", datetime(2026, 9, 1, 2, 32, 46, tzinfo=timezone.utc),
            h4, h1, states, model, reason, plan, preferred, preferred_reason, [],
            FIXED_EVIDENCE_HASH, ("gbpusd-forex-daily-h1-plan.webp",
                       "gbpusd-forex-daily-m15-trigger.webp"),
            bases, None, policy)
        final = forex_daily_plan.publicize_style_l(article, "gbpusd")
        self.assertIn("trend: fl", final)
        self.assertIn("author_slug: worldclassbroker-team", final)
        self.assertIn("**ฝั่งแผนสาธารณะ: OCO**", final)
        self.assertIn("| BUY | M15 ปิดเหนือ `1.35597`", final)
        self.assertIn("| SELL | M15 ปิดต่ำกว่า `1.35422`", final)
        self.assertIn("OCO: เมื่อ leg แรก trigger ให้ยกเลิกอีกฝั่งทันที", final)
        self.assertIn(f"- Evidence hash: `{FIXED_EVIDENCE_HASH}`", final)
        self.assertNotIn("| อัปเดตล่าสุด |", final)
        self.assertNotIn("ไม่มี Entry, Stop Loss, Take Profit หรือ RR", final)
        self.assertNotIn("แผนที่ราคาและระยะของวัน", final)
        self.assertNotIn("พักแผนเมื่อ", final)
        self.assertNotIn("หลักฐาน: P002 Style L", final)
        self.assertNotIn("| สถานะ | สกุลเงิน | เวลาไทย | ข่าว | ตัวเลข |", final)
        self.assertNotIn("ความต่อเนื่องจากแผนครั้งก่อน", final)
        self.assertIn("## ข่าวสำคัญวันนี้", final)
        self.assertIn("วันนี้ไม่มีข่าวระดับ Medium/High", final)
        findings = (
            forex_daily_plan.validate_article(final, "gbpusd", plan)
            + forex_daily_plan.validate_data_domain("gbpusd", h4, h1, plan)
            + forex_daily_plan.validate_markdown_snapshot_parity(
                final, "gbpusd", h4, h1, plan, preferred)
        )
        self.assertEqual(findings, [])

        invalid = final.replace("trend: fl", "trend: neutral")
        self.assertIn(
            "frontmatter trend ต้องเป็น up | dn | fl",
            forex_daily_plan.validate_article(invalid, "gbpusd", plan))

        mismatch = final.replace("trend: fl", "trend: up")
        self.assertIn(
            "frontmatter trend ต้องตรง canonical plan: คาด fl แต่ได้ up",
            forex_daily_plan.validate_article(mismatch, "gbpusd", plan))

        missing = final.replace("trend: fl\n", "")
        missing_findings = forex_daily_plan.validate_article(missing, "gbpusd", plan)
        self.assertIn("frontmatter ต้องมี 10 ช่องตามลำดับที่อนุมัติ", missing_findings)
        self.assertIn("frontmatter trend ต้องเป็น up | dn | fl", missing_findings)

        wrong_author = final.replace(
            "author_slug: worldclassbroker-team",
            "author_slug: world-class-broker-team")
        self.assertIn(
            "frontmatter Style L author_slug ต้องเป็น worldclassbroker-team",
            forex_daily_plan.validate_article(wrong_author, "gbpusd", plan))

    def test_neutral_m15_chart_shows_symmetric_oco_without_directional_arrow(self):
        rows = [{
            "at": "2026-09-01 09:00:00",
            "high": 1.35597,
            "low": 1.35415,
        }]
        plan = _canonical_plan(direction=None)
        basis = {"basis_close_at": "2026-09-01T09:15:00+07:00"}
        with mock.patch.object(forex_daily_plan, "_thai_font"), \
                mock.patch.object(forex_daily_plan, "candle_plot"), \
                mock.patch.object(forex_daily_plan, "add_price_line") as price_line, \
                mock.patch("matplotlib.axes.Axes.annotate") as annotate, \
                mock.patch("matplotlib.figure.Figure.tight_layout"), \
                mock.patch.object(
                    forex_daily_plan.image_output, "save_figure", return_value=123) as save:
            size = forex_daily_plan.save_m15_chart(
                "eurusd", rows, "NO_SETUP", {"H": {}, "I": {}},
                plan, None, basis, forex_daily_plan.load_decision_policy(),
                Path("unused.webp"))

        self.assertEqual(size, 123)
        self.assertEqual(price_line.call_count, 8)
        labels = [call.args[2] for call in price_line.call_args_list]
        self.assertTrue(any("OCO BUY Trigger" in label for label in labels))
        self.assertTrue(any("OCO SELL Trigger" in label for label in labels))
        self.assertTrue(any("OCO BUY SL" in label for label in labels))
        self.assertTrue(any("OCO SELL TP2" in label for label in labels))
        annotate.assert_not_called()
        figure = save.call_args.args[0]
        self.assert_edge_header_contract(figure)
        axis = figure.axes[-1]
        visible_text = " ".join(
            text.get_text() for current_axis in figure.axes
            for text in current_axis.texts)
        self.assertIn("NEUTRAL", visible_text)
        self.assertNotIn("WAIT_TRIGGER", visible_text)
        self.assertNotIn("M30:", visible_text)
        self.assertNotIn("M15:", visible_text)
        self.assertNotIn("OCO", visible_text)
        self.assertEqual(
            [text.get_text() for text in figure.axes[0].texts], ["EUR/USD · M15"])
        self.assertEqual(figure.texts, [])
        self.assertEqual(figure._premium_axis_layout["header_accessory_card_count"], 0)
        self.assertEqual(figure._premium_axis_layout["central_decision_card_count"], 1)
        watermark = figure._premium_axis_layout["watermark"]
        self.assertEqual(watermark["color"], "#0E2A1D")
        self.assertEqual(watermark["alpha"], 0.12)
        self.assertEqual(watermark["palette_role"], "light_plot")
        self.assertEqual(watermark["surface_contrast"]["mode"], "surface-aware")
        self.assertGreaterEqual(
            watermark["surface_contrast"]["effective_contrast_ratio"], 1.20)
        self.assertTrue(watermark["surface_contrast"]["visibility_pass"])
        self.assertLessEqual(axis.get_position().y0, 0.06)

    def test_image_price_formatter_is_three_decimals_without_changing_canonical_fmt(self):
        self.assertEqual(forex_daily_plan.image_price("gbpusd", 1.34813), "1.348")
        self.assertEqual(forex_daily_plan.image_price("usdcad", 1.38473), "1.385")
        self.assertEqual(forex_daily_plan.fmt("gbpusd", 1.34813), "1.34813")
        self.assertEqual(forex_daily_plan.fmt("usdcad", 1.38473), "1.38473")

    def test_gbpusd_h1_labels_lock_to_factual_anchors_and_zone_is_inside_band(self):
        import math

        rows = [{
            "at": f"2026-09-{(index % 28) + 1:02d} 09:00:00",
            "open": 1.3544, "high": 1.3550, "low": 1.3540, "close": 1.3545,
        } for index in range(100)]
        h1 = dict(self.GBPUSD_2026_09_01_H1)
        plan = copy.deepcopy(self.GBPUSD_2026_09_01_PLAN)
        captured = []

        def inspect(figure, *_args, **_kwargs):
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            canvas = FigureCanvasAgg(figure)
            canvas.draw()
            axis = figure.axes[-1]
            captured.append((figure, axis, canvas.get_renderer()))
            return 123

        with mock.patch.object(forex_daily_plan, "_thai_font"), \
                mock.patch.object(forex_daily_plan.image_output, "save_figure",
                                  side_effect=inspect):
            forex_daily_plan.save_h1_chart(
                "gbpusd", rows, rows, {"structure": "lower_high_low"}, h1,
                plan, "down", {"basis_close_at": "2026-09-01T09:00:00+07:00"},
                Path("unused.webp"))

        figure, axis, renderer = captured[0]
        for role, value in (("h1-pdh", h1["pdh"]), ("h1-pdl", h1["pdl"]),
                            ("h1-close", h1["close"])):
            artist = next(item for item in axis.texts if item.get_gid() == f"premium-label:style-l:{role}")
            self.assertRegex(artist.get_text(), r"-?\d+\.\d{3}$")
            self.assertEqual(artist.xy[1], value)
            patch = artist.get_bbox_patch().get_window_extent(renderer)
            expected_y = axis.transData.transform((0, value))[1]
            self.assertAlmostEqual((patch.y0 + patch.y1) / 2, expected_y, delta=1.0)
            self.assertIsNone(artist.arrow_patch)

        zone = next(item for item in axis.texts if item.get_gid() == "premium-label:style-l:h1-zone")
        self.assertIsNone(zone.get_bbox_patch())
        self.assertEqual(zone.get_transform(), axis.get_yaxis_transform())
        self.assertGreater(zone.get_position()[1], min(plan["entry"], plan["stop"]))
        self.assertLess(zone.get_position()[1], max(plan["entry"], plan["stop"]))
        for value in (h1["pdh"], h1["pdl"]):
            line = next(line for line in axis.lines
                        if len(line.get_ydata()) == 2 and
                        all(abs(float(y) - value) < 1e-10 for y in line.get_ydata()))
            self.assertAlmostEqual(float(line.get_xdata()[0]), 0.0, delta=1e-9)
            self.assertAlmostEqual(float(line.get_xdata()[-1]), 1.0, delta=1e-9)

    def test_gbpusd_m15_active_labels_use_three_decimals_and_factual_anchors(self):
        rows = [{
            "at": f"2026-09-{(index % 28) + 1:02d} {index % 24:02d}:00:00",
            "open": 1.3540, "high": 1.3550, "low": 1.3520, "close": 1.3535,
        } for index in range(120)]
        plan = _canonical_plan(direction="down", current_close=1.35390)
        captured = []

        def inspect(figure, *_args, **_kwargs):
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            canvas = FigureCanvasAgg(figure)
            canvas.draw()
            captured.append((figure, canvas.get_renderer(),
                             visual_theme.premium_text_patch_overlap_report(
                                 figure, gap_pixels=12.0)))
            return 123

        with mock.patch.object(forex_daily_plan, "_thai_font"), \
                mock.patch.object(forex_daily_plan.image_output, "save_figure",
                                  side_effect=inspect):
            forex_daily_plan.save_m15_chart(
                "gbpusd", rows, "I", {"H": {}, "I": {}}, plan, "down",
                {"basis_close_at": "2026-09-03T16:35:16+07:00"},
                forex_daily_plan.load_decision_policy(), Path("unused.webp"))

        figure, renderer, overlap = captured[0]
        self.assertEqual(overlap["overlap_count"], 0, overlap["overlaps"])
        axis = figure.axes[-1]
        expected = {
            "entry-trigger": plan["plans"][0]["trigger"]["value"],
            "stop-loss": plan["plans"][0]["stop_loss"],
            "target-1": plan["plans"][0]["take_profit"][0],
            "target-2": plan["plans"][0]["take_profit"][1],
        }
        for role, value in expected.items():
            artist = next(item for item in axis.texts
                          if item.get_gid() == f"premium-label:style-l:{role}")
            self.assertRegex(artist.get_text(), r"-?\d+\.\d{3}$")
            self.assertEqual(artist.xy[1], value)
            box = artist.get_bbox_patch().get_window_extent(renderer)
            expected_y = axis.transData.transform((0, value))[1]
            self.assertAlmostEqual((box.y0 + box.y1) / 2, expected_y, delta=1.0)
            self.assertIsNone(artist.arrow_patch)

    def test_usdcad_neutral_oco_has_grouped_three_decimal_labels_and_header_card(self):
        rows = [{
            "at": "2026-09-03 09:00:00", "open": 1.3835,
            "high": 1.3848, "low": 1.3831, "close": 1.38349,
        }] * 120
        plan = _usdcad_oco_plan()
        captured = []

        def inspect(figure, *_args, **_kwargs):
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            FigureCanvasAgg(figure)
            figure.canvas.draw()
            captured.append(figure)
            return 123

        with mock.patch.object(forex_daily_plan, "_thai_font"), \
                mock.patch.object(forex_daily_plan, "candle_plot"), \
                mock.patch.object(forex_daily_plan.image_output, "save_figure",
                                  side_effect=inspect):
            forex_daily_plan.save_m15_chart(
                "usdcad", rows, "NO_SETUP", {"H": {}, "I": {}}, plan, None,
                {"basis_close_at": "2026-09-03T16:35:16+07:00"},
                forex_daily_plan.load_decision_policy(), Path("unused.webp"))

        figure = captured[0]
        axis = figure.axes[-1]
        texts = [artist for artist in axis.texts
                 if str(artist.get_gid() or "").startswith("premium-label:style-l:")]
        visible = " ".join(artist.get_text() for artist in texts)
        self.assertNotIn("OCO", visible)
        self.assertNotIn("SL", visible)
        self.assertEqual(sum("BUY Entry" in artist.get_text() for artist in texts), 1)
        self.assertEqual(sum("SELL Entry" in artist.get_text() for artist in texts), 1)
        self.assertEqual(sum(re.search(r"\bTP[12] \d+\.\d{3}$", artist.get_text()) is not None
                             for artist in texts), 4)
        self.assertEqual(sum(artist.get_text().startswith("TP") and ("BUY" in artist.get_text() or "SELL" in artist.get_text())
                             for artist in texts), 0)
        for artist in texts:
            if artist.get_bbox_patch() is None:
                continue
            self.assertIsNone(artist.arrow_patch)
            self.assertRegex(artist.get_text(), r"\d+\.\d{3}$")
        line_styles = {round(float(line.get_ydata()[0]), 5): line.get_linestyle()
                       for line in axis.lines if len(line.get_ydata()) == 2}
        self.assertEqual(line_styles[1.38473], "-")
        self.assertEqual(line_styles[1.38320], "-")
        self.assertEqual(line_styles[1.38580], "--")
        self.assertEqual(line_styles[1.38213], "--")
        self.assertFalse(any("stop-loss" in str(artist.get_gid()) for artist in axis.lines))
        self.assertEqual(figure._premium_axis_layout["central_decision_card_count"], 0)
        self.assertEqual(figure._premium_axis_layout["header_accessory_card_count"], 1)
        self.assertEqual(figure._premium_header_card_layout["text"],
                         "NEUTRAL / โซนสังเกตการณ์")

    def test_usdjpy_neutral_m15_keeps_oco_geometry_with_visible_watermark(self):
        rows = [{
            "at": "2026-09-01 09:00:00",
            "high": 150.597,
            "low": 150.415,
        }]
        plan = _canonical_plan(direction=None)
        basis = {"basis_close_at": "2026-09-01T09:15:00+07:00"}
        with mock.patch.object(forex_daily_plan, "_thai_font"), \
                mock.patch.object(forex_daily_plan, "candle_plot"), \
                mock.patch.object(forex_daily_plan, "add_price_line") as price_line, \
                mock.patch("matplotlib.axes.Axes.annotate") as annotate, \
                mock.patch.object(
                    forex_daily_plan.image_output, "save_figure",
                    return_value=123) as save:
            size = forex_daily_plan.save_m15_chart(
                "usdjpy", rows, "NO_SETUP", {"H": {}, "I": {}},
                plan, None, basis, forex_daily_plan.load_decision_policy(),
                Path("unused.webp"))

        self.assertEqual(size, 123)
        self.assertEqual(price_line.call_count, 8)
        labels = [call.args[2] for call in price_line.call_args_list]
        self.assertEqual(sum("OCO BUY" in label for label in labels), 4)
        self.assertEqual(sum("OCO SELL" in label for label in labels), 4)
        annotate.assert_not_called()
        figure = save.call_args.args[0]
        layout = figure._premium_axis_layout
        self.assertEqual(layout["header_accessory_card_count"], 0)
        self.assertEqual(layout["central_decision_card_count"], 1)
        self.assertEqual(
            [text.get_text() for text in figure.axes[0].texts], ["USD/JPY · M15"])
        watermark = layout["watermark"]
        self.assertEqual(watermark["color"], "#0E2A1D")
        self.assertEqual(watermark["alpha"], 0.12)
        self.assertEqual(watermark["palette_role"], "light_plot")
        self.assertGreaterEqual(
            watermark["surface_contrast"]["effective_contrast_ratio"], 1.20)
        self.assertTrue(watermark["surface_contrast"]["visibility_pass"])

    def test_h1_editorial_chart_removes_inset_metrics_and_footer_artists(self):
        rows = [{
            "at": "2026-09-01 09:00:00", "open": 1.3544,
            "high": 1.3550, "low": 1.3540, "close": 1.3545,
        }] * 60
        h1 = dict(self.GBPUSD_2026_09_01_H1)
        plan = self.GBPUSD_2026_09_01_PLAN
        basis = {"basis_close_at": "2026-09-01T09:00:00+07:00"}
        raster_reports = []

        def inspect(figure, *_args, **_kwargs):
            raster_reports.append(
                visual_theme.premium_header_raster_report(figure))
            return 123

        with mock.patch.object(forex_daily_plan, "_thai_font"), \
                mock.patch.object(forex_daily_plan, "candle_plot"), \
                mock.patch.object(forex_daily_plan, "add_price_line"), \
                mock.patch.object(
                    forex_daily_plan.image_output, "save_figure",
                    side_effect=inspect) as save:
            size = forex_daily_plan.save_h1_chart(
                "gbpusd", rows, rows, {"structure": "lower_high_low"},
                h1, plan, "down", basis, Path("unused.webp"))

        self.assertEqual(size, 123)
        figure = save.call_args.args[0]
        self.assert_edge_header_contract(figure)
        self.assertEqual(len(figure.axes), 2)
        visible_text = " ".join(
            text.get_text() for axis in figure.axes for text in axis.texts)
        visible_text += " " + figure.axes[-1].get_title(loc="left")
        for forbidden in ("H4", "ATR H1", "ADR", "ใช้ระยะแล้ว", "ข้อมูลแท่ง H1"):
            self.assertNotIn(forbidden, visible_text)
        self.assertNotIn("DAILY PRICE PLAN", visible_text)
        self.assertEqual(
            [text.get_text() for text in figure.axes[0].texts], ["GBP/USD · H1"])
        self.assertEqual(raster_reports[0]["top_row_green_coverage"], 1.0)
        self.assertEqual(raster_reports[0]["top_row_cream_like_pixels"], 0)
        self.assertEqual(
            raster_reports[0]["header_before_underline_cream_like_pixels"], 0)
        self.assertEqual(raster_reports[0]["protected_start_row"], 82)
        self.assertAlmostEqual(
            figure._premium_header_layout["underline_height_px"], 4.00,
            delta=0.05)
        self.assertAlmostEqual(
            figure._premium_header_layout["underline_y0_px"], 667.63,
            delta=0.05)
        watermark = figure._premium_axis_layout["watermark"]
        self.assertEqual(figure._premium_axis_layout["watermark_count"], 1)
        self.assertEqual(watermark["text"], "WorldClassBroker")
        self.assertEqual(watermark["color"], "#0E2A1D")
        self.assertEqual(watermark["alpha"], 0.12)
        self.assertEqual(watermark["palette_role"], "light_plot")
        self.assertEqual(watermark["surface_contrast"]["mode"], "surface-aware")
        self.assertTrue(watermark["surface_contrast"]["light_plot_detected"])
        self.assertGreaterEqual(
            watermark["surface_contrast"]["effective_contrast_ratio"], 1.20)
        self.assertTrue(watermark["surface_contrast"]["visibility_pass"])
        self.assertEqual(watermark["font_weight"], "medium")
        self.assertGreaterEqual(watermark["tracking_px"], 1.0)
        self.assertGreaterEqual(watermark["bbox_width_ratio"], 0.30)
        self.assertLessEqual(watermark["bbox_width_ratio"], 0.35)

    def test_directional_m15_text_patches_keep_twelve_pixel_clearance(self):
        import math

        rows = []
        for index in range(120):
            close = 1.35505 + 0.00034 * math.sin(index / 5)
            rows.append({
                "at": f"2026-09-01 {index % 24:02d}:{(index % 4) * 15:02d}:00",
                "open": close - 0.00005,
                "high": close + 0.00028,
                "low": close - 0.00028,
                "close": close,
            })
        plan = _canonical_plan(direction="down")
        basis = {"basis_close_at": "2026-09-01T09:15:00+07:00"}
        captured = []

        def inspect(figure, *_args, **_kwargs):
            captured.append((
                visual_theme.premium_text_patch_overlap_report(
                    figure, gap_pixels=12.0),
                figure._premium_axis_layout,
                [artist.get_text() for artist in figure.axes[-1].texts],
            ))
            return 123

        with mock.patch.object(
                forex_daily_plan.image_output, "save_figure", side_effect=inspect):
            size = forex_daily_plan.save_m15_chart(
                "gbpusd", rows, "WAIT", {"H": {}, "I": {}}, plan, "down",
                basis, forex_daily_plan.load_decision_policy(), Path("unused.webp"))

        self.assertEqual(size, 123)
        report, layout, plot_texts = captured[0]
        self.assertEqual(report["overlap_count"], 0, report["overlaps"])
        self.assertEqual(report["gap_pixels"], 12.0)
        self.assertEqual(layout["header_accessory_card_count"], 1)
        self.assertEqual(layout["central_decision_card_count"], 0)
        self.assertEqual(layout["watermark_count"], 1)
        self.assertEqual(layout["watermark"]["text"], "WorldClassBroker")
        self.assertEqual(layout["watermark"]["color"], "#0E2A1D")
        self.assertEqual(layout["watermark"]["alpha"], 0.12)
        self.assertEqual(layout["watermark"]["palette_role"], "light_plot")
        self.assertEqual(
            layout["watermark"]["surface_contrast"]["mode"], "surface-aware")
        self.assertGreaterEqual(
            layout["watermark"]["surface_contrast"]["effective_contrast_ratio"],
            1.20)
        self.assertTrue(
            layout["watermark"]["surface_contrast"]["visibility_pass"])
        self.assertGreaterEqual(layout["watermark"]["tracking_px"], 1.0)
        self.assertNotIn("NO TRADE / รอยืนยัน", plot_texts)
        self.assertEqual(layout["header_accessory_card"]["text"],
                         "NO TRADE / รอยืนยัน")

    def test_m15_trigger_is_locked_to_right_price_rail_without_diagonal_leader(self):
        import math

        rows = []
        for index in range(120):
            close = 1.1591 + 0.00030 * math.sin(index / 5)
            rows.append({
                "at": f"2026-08-28 {index % 24:02d}:{(index % 4) * 15:02d}:00",
                "open": close - 0.00004, "high": close + 0.00025,
                "low": close - 0.00025, "close": close,
            })
        plan = _canonical_plan(direction="down")
        plan["plans"][0]["trigger"]["value"] = 1.15856
        plan["watch_low"] = 1.15856
        plan["watch_high"] = 1.15945
        captured = []

        def inspect(figure, *_args, **_kwargs):
            figure.canvas.draw()
            axis = figure.axes[-1]
            trigger = next(artist for artist in axis.texts
                           if artist.get_gid() == "premium-label:style-l:trigger")
            patch = trigger.get_bbox_patch().get_window_extent(
                figure.canvas.get_renderer())
            expected_y = axis.transData.transform((0, 1.15856))[1]
            captured.append((figure, axis, trigger, patch, expected_y,
                             figure._premium_axis_layout,
                             visual_theme.premium_header_raster_report(figure)))
            return 123

        with mock.patch.object(
                forex_daily_plan.image_output, "save_figure", side_effect=inspect):
            forex_daily_plan.save_m15_chart(
                "eurusd", rows, "WAIT", {"H": {}, "I": {}}, plan, "down",
                {"basis_close_at": "2026-08-31T11:30:00+07:00"},
                forex_daily_plan.load_decision_policy(), Path("unused.webp"))

        figure, axis, trigger, patch, expected_y, layout, raster = captured[0]
        self.assertEqual(
            trigger.get_text(),
            "SELL Trigger — รอ M15 ปิดต่ำกว่า 1.15856")
        self.assertEqual(trigger.xy[1], 1.15856)
        self.assertAlmostEqual((patch.y0 + patch.y1) / 2, expected_y, delta=1.0)
        self.assertFalse(any(
            artist.get_gid() == "premium-label:style-l:consideration"
            for artist in axis.texts))
        self.assertTrue(any(
            all(abs(float(value) - 1.15856) < 1e-9 for value in line.get_ydata())
            for line in axis.lines if len(line.get_ydata()) == 2))
        self.assertEqual(layout["x_tick_newline_count"], 0)
        self.assertEqual(layout["left_numeric_tick_count"], 0)
        self.assertGreater(layout["right_numeric_tick_count"], 0)
        self.assertEqual(layout["price_tag_tick_overlap_count"], 0)
        self.assertGreaterEqual(layout["right_safe_gutter_px"], 48)
        self.assertGreaterEqual(layout["right_safe_gutter_px_at_768"], 16)
        self.assert_edge_header_contract(figure)
        self.assertEqual(raster["top_row_green_coverage"], 1.0)
        self.assertEqual(raster["top_row_cream_like_pixels"], 0)
        self.assertEqual(raster["header_background_cream_like_pixels"], 0)
        self.assertEqual(raster["approved_header_card_count"], 1)
        self.assertEqual(raster["protected_start_row"], 84)
        card = layout["header_accessory_card"]
        self.assertEqual(card["role"], "style-l-m15-wait")
        self.assertEqual(card["text"], "NO TRADE / รอยืนยัน")
        self.assertEqual(card["line_count"], 1)
        self.assertEqual(card["face"], "#F4F1E7")
        self.assertEqual(card["text_color"], "#0E2A1D")
        self.assertEqual(card["edge"], "#D6B34A")
        self.assertGreaterEqual(card["contrast"], 7)
        self.assertGreaterEqual(card["font_height_px_at_768"], 12)
        self.assertGreaterEqual(card["right_safe_margin_px_at_768"], 8)
        self.assertGreaterEqual(card["title_gap_px_at_768"], 8)
        self.assertTrue(card["contained_in_header"])
        self.assertFalse(card["overlaps_title"])
        self.assertFalse(card["overlaps_underline"])
        self.assertFalse(card["clipped"])
        self.assertEqual(layout["header_accessory_card_count"], 1)
        self.assertEqual(layout["central_decision_card_count"], 0)
        self.assertAlmostEqual(layout["edge_to_edge_header"]["underline_height_px"],
                               4.00, delta=0.05)
        self.assertAlmostEqual(layout["edge_to_edge_header"]["underline_y0_px"],
                               666.29, delta=0.05)

    def test_h1_latest_close_tag_is_in_reserved_right_gutter(self):
        import math

        rows = []
        for index in range(100):
            close = 1.3547 + 0.00032 * math.sin(index / 7)
            rows.append({
                "at": f"2026-09-{(index % 28) + 1:02d} 09:00:00",
                "open": close - 0.00004,
                "high": close + 0.00025,
                "low": close - 0.00025,
                "close": close,
            })
        captured = []

        def inspect(figure, *_args, **_kwargs):
            figure.canvas.draw()
            axis = figure.axes[-1]
            close_artist = next(
                artist for artist in axis.texts
                if artist.get_gid() == "premium-label:style-l:h1-close")
            patch = close_artist.get_bbox_patch().get_window_extent(
                figure.canvas.get_renderer())
            latest_candle_x = axis.transData.transform((len(rows) - 1, 1.3547))[0]
            captured.append((patch.x0, latest_candle_x, axis.get_xlim()[1]))
            return 123

        with mock.patch.object(
                forex_daily_plan.image_output, "save_figure", side_effect=inspect):
            forex_daily_plan.save_h1_chart(
                "gbpusd", rows, rows, {"structure": "lower_high_low"},
                self.GBPUSD_2026_09_01_H1, self.GBPUSD_2026_09_01_PLAN,
                "down", {"basis_close_at": "2026-09-01T09:00:00+07:00"},
                Path("unused.webp"))

        patch_left, latest_candle_x, x_limit = captured[0]
        self.assertGreater(patch_left, latest_candle_x)
        self.assertGreater(x_limit, len(rows) - 1)

    def test_tpr_v1_neutral_oco_and_directional_plans_are_complete(self):
        neutral = _canonical_plan(direction=None)
        self.assertEqual(neutral["side"], "OCO")
        self.assertEqual(neutral["status"], "WAIT_TRIGGER")
        self.assertEqual({leg["side"] for leg in neutral["plans"]}, {"BUY", "SELL"})
        directional = self.GBPUSD_2026_09_01_PLAN
        self.assertEqual(directional["side"], "SELL")
        self.assertEqual(len(directional["plans"]), 1)
        for plan in (neutral, directional):
            self.assertEqual(plan["schema"], forex_daily_plan.STYLE_L_PLAN_SCHEMA)
            self.assertEqual(plan["rr_policy_version"], "TPR-RR/v1")
            self.assertEqual(plan["evidence_hash"], FIXED_EVIDENCE_HASH)
            for leg in plan["plans"]:
                self.assertEqual(leg["rr_basis"], "gross_pre_cost")
                self.assertTrue(all(rr >= forex_daily_plan.MINIMUM_RR
                                    for rr in leg["risk_reward"]))
                self.assertEqual(len(leg["take_profit"]), len(leg["risk_reward"]))

    def test_tpr_v1_uses_each_asset_precision(self):
        for asset in forex_daily_plan.ASSETS:
            with self.subTest(asset=asset):
                base = 150.0 if asset == "usdjpy" else 1.25
                h1 = {"close": base, "pdh": base + .01, "pdl": base - .01,
                      "atr14": .00123}
                states = {"I": {"donchian": {
                    "lower": base - .00567, "upper": base + .00567}}}
                plan = forex_daily_plan.scenario(
                    "WAIT", "up", "up", h1, states, asset=asset,
                    cutoff=FIXED_CUTOFF, evidence_hash=FIXED_EVIDENCE_HASH,
                    current_close=base)
                decimals = forex_daily_plan.wcb_source.profile_for(asset)["decimals"]
                for value in (plan["current_close"],
                              plan["plans"][0]["trigger"]["value"],
                              plan["plans"][0]["stop_loss"]):
                    self.assertEqual(value, round(value, decimals))

    def test_public_sidecar_hashes_final_markdown_and_rejects_tamper(self):
        plan = self.GBPUSD_2026_09_01_PLAN
        article = self._critical_article(
            self.GBPUSD_2026_09_01_H4, self.GBPUSD_2026_09_01_H1, plan, "down")
        sidecar = forex_daily_plan.public_trade_plan_sidecar(
            "gbpusd", "gbpusd.md", article, plan)
        self.assertEqual(sidecar["schema"], "p002-public-trade-plan/v1")
        self.assertEqual(sidecar["current_close"], plan["current_close"])
        self.assertEqual(sidecar["plans"][0]["rr_basis"], "gross_pre_cost")
        self.assertEqual(
            forex_daily_plan.validate_public_trade_plan_sidecar(sidecar, article), [])
        self.assertTrue(any("article_sha256" in finding for finding in
                            forex_daily_plan.validate_public_trade_plan_sidecar(
                                sidecar, article + "\ntampered")))

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
        self.assertFalse(forex_daily_plan.h4_inset_enabled("eurusd"))
        self.assertFalse(forex_daily_plan.h4_inset_enabled("gbpusd"))

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
        self.assertTrue(any("complete plan row" in finding for finding in findings))
        self.assertTrue(any("public side" in finding for finding in findings))

    def test_gbpusd_2026_09_01_final_markdown_passes_snapshot_parity(self):
        h4 = self.GBPUSD_2026_09_01_H4
        h1 = self.GBPUSD_2026_09_01_H1
        plan = self.GBPUSD_2026_09_01_PLAN
        final = self._critical_article(h4, h1, plan, "down")
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
        cancel = forex_daily_plan.public_plan_cancel_rule("gbpusd", wait)
        broken_wait = wait_article.replace(cancel, cancel.replace("1.35652", "9.00000"), 1)
        wait_findings = forex_daily_plan.validate_markdown_snapshot_parity(
            broken_wait, "gbpusd", h4, h1, wait, "down")
        self.assertTrue(any("cancel rule" in finding for finding in wait_findings))

        active = _canonical_plan(current_close=1.35300)
        active_article = self._critical_article(h4, h1, active, "down")
        plan_row = next(line for line in active_article.splitlines()
                        if line.startswith("| SELL |"))
        duplicate = active_article + "\n" + plan_row
        duplicate_findings = forex_daily_plan.validate_markdown_snapshot_parity(
            duplicate, "gbpusd", h4, h1, active, "down")
        self.assertTrue(any("complete plan row" in finding for finding in duplicate_findings))

        leg = active["plans"][0]
        broken_active = active_article.replace(
            forex_daily_plan.fmt("gbpusd", leg["take_profit"][1]), "9.00000", 1
        ).replace(
            forex_daily_plan.fmt("gbpusd", leg["invalidation"]["value"]),
            "9.00000", 1)
        active_findings = forex_daily_plan.validate_markdown_snapshot_parity(
            broken_active, "gbpusd", h4, h1, active, "down")
        self.assertTrue(any("complete plan row" in finding for finding in active_findings))

    def _critical_article(self, h4: dict, h1: dict, plan: dict,
                          preferred: str) -> str:
        asset = "gbpusd"
        price = lambda value: forex_daily_plan.fmt(asset, value)
        lines = [
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
            f"| แผนสาธารณะ | **{plan['side']}** |",
            f"| สถานะตอนนี้ | **{plan['status']}** |",
            "**แผนตามสถานการณ์**",
            "| Side | Trigger | Entry zone | Stop loss | Take profit | RR | Invalidation |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for leg in plan["plans"]:
            condition = "M15 ปิดเหนือ" if leg["side"] == "BUY" else "M15 ปิดต่ำกว่า"
            invalidation = "H1 ปิดต่ำกว่า" if leg["side"] == "BUY" else "H1 ปิดเหนือ"
            targets = " / ".join(f"`{price(value)}`" for value in leg["take_profit"])
            rrs = " / ".join(
                forex_daily_plan.public_number_policy.publicize(f"{value:.2f}R")
                for value in leg["risk_reward"])
            lines.append(
                f"| {leg['side']} | {condition} `{price(leg['trigger']['value'])}` | "
                f"`{price(leg['entry_zone']['low'])}`–`{price(leg['entry_zone']['high'])}` | "
                f"`{price(leg['stop_loss'])}` | {targets} | {rrs} | "
                f"{invalidation} `{price(leg['invalidation']['value'])}` |")
        lines += [
            f"- {forex_daily_plan.public_plan_cancel_rule(asset, plan)}",
            f"- Cutoff at: `{plan['cutoff_at']}`",
            f"- Valid until: `{plan['valid_until']}`",
            f"- Evidence hash: `{plan['evidence_hash']}`",
            "- RR ยังไม่หัก spread/slippage",
        ]
        return "\n".join(lines)

    def _run_round_fixture(self, plan: dict, article: str) -> tuple:
        h4 = self.GBPUSD_2026_09_01_H4
        h1 = self.GBPUSD_2026_09_01_H1
        cutoff = datetime(2026, 9, 1, 2, 32, 46, tzinfo=timezone.utc)
        frozen_policy = forex_daily_plan.load_decision_policy()
        intraday_rows = [{"close": plan["current_close"]}]
        daily_rows = [{"close": h1["close"]}]
        canonical_hash = forex_daily_plan.sha({
            "asset": "gbpusd", "cutoff_utc": cutoff.isoformat(),
            "rows": {**{timeframe: intraday_rows
                         for timeframe in forex_daily_plan.TIMEFRAMES},
                     "1day": daily_rows},
        })
        plan = copy.deepcopy(plan)
        article = article.replace(plan["evidence_hash"], canonical_hash)
        plan["evidence_hash"] = canonical_hash

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
                    return_value=(intraday_rows, basis,
                                  {"source": "fixture"})))
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "closed_daily",
                    return_value=(daily_rows, basis,
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
                continuity_state = forex_daily_plan.build_continuity_snapshot(
                    "gbpusd", cutoff, plan)
                stack.enter_context(mock.patch.object(
                    forex_daily_plan, "continuity_snapshot",
                    return_value=(continuity_state, None)))
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
                if result["ok"]:
                    candidates = list((root / "work" / "continuity" / "candidates").glob("*.json"))
                    self.assertEqual(len(candidates), 1)
                    record = json.loads(candidates[0].read_text(encoding="utf-8"))
                    self.assertEqual(record["markdown"].count("## คุณมองตลาดอย่างไร?"), 1)
                    staged = next((root / "work" / "forex-daily-plan").glob("*/staging/gbpusd/gbpusd.md"))
                    self.assertEqual(record["markdown"], staged.read_text(encoding="utf-8"))
                    self.assertEqual(record["markdown"].encode("utf-8"), staged.read_bytes())
                return (result, copy_file, frozen_policy,
                        m15_chart, render, trace)

    def test_run_round_corrupted_final_wait_markdown_blocks_promotion(self):
        plan = self.GBPUSD_2026_09_01_PLAN
        article = self._critical_article(
            self.GBPUSD_2026_09_01_H4, self.GBPUSD_2026_09_01_H1, plan, "down")
        article = article.replace("M15 ปิดต่ำกว่า `1.35415`",
                                  "M15 ปิดต่ำกว่า `9.00000`", 1)
        result, copy_file, *_ = self._run_round_fixture(plan, article)
        self.assertFalse(result["ok"])
        self.assertTrue(any("complete plan row" in error for error in result["errors"]))
        copy_file.assert_not_called()

    def test_run_round_bad_rr_becomes_data_hold_without_sidecar_or_promotion(self):
        plan = copy.deepcopy(self.GBPUSD_2026_09_01_PLAN)
        plan["plans"][0]["risk_reward"][0] = 0.5
        article = self._critical_article(
            self.GBPUSD_2026_09_01_H4, self.GBPUSD_2026_09_01_H1, plan, "down")
        result, copy_file, *_ = self._run_round_fixture(plan, article)
        self.assertFalse(result["ok"])
        self.assertEqual(result["assets"]["gbpusd"]["status"], "DATA_HOLD")
        self.assertTrue(any("RR1" in error for error in result["errors"]))
        copy_file.assert_not_called()

    def test_run_round_valid_wait_and_active_final_markdown_pass(self):
        active = _canonical_plan(current_close=1.35300)
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
                self.assertIs(render.call_args.args[-2], frozen_policy)
                self.assertEqual(render.call_args.args[-1], ())
                self.assertIs(trace.call_args.args[0], frozen_policy)
                self.assertEqual(copy_file.call_count, 4)
                self.assertEqual(result["assets"]["gbpusd"]["trade_plan_contract"],
                                 "PASS")
                self.assertIn("gbpusd.trade-plan-public.json",
                              result["assets"]["gbpusd"]["artifacts"])

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
            "usdcad": "/thailand/asset-usdcad",
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

    def test_web_trend_mapping_covers_every_internal_direction_and_fails_closed(self):
        self.assertEqual(forex_daily_plan.web_frontmatter_contract.trend_from_direction(
            "up"), "up")
        self.assertEqual(forex_daily_plan.web_frontmatter_contract.trend_from_direction(
            "down"), "dn")
        self.assertEqual(forex_daily_plan.web_frontmatter_contract.trend_from_direction(
            None), "fl")
        for invalid in ("neutral", "dn", "fl", "", 0):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    forex_daily_plan.web_frontmatter_contract.trend_from_direction(invalid)

    def test_registered_forex_assets_are_eligible_for_web_import(self):
        for asset in ("eurusd", "gbpusd", "usdjpy", "audusd", "usdcad"):
            with self.subTest(asset=asset):
                self.assertTrue(forex_daily_plan.web_import_eligible(asset))

        files = [
            Path("staging/usdjpy/usdjpy.md"),
            Path("staging/usdcad/usdcad.md"),
            Path("staging/usdcad/usdcad-forex-daily-calendar-2026-09-03.webp"),
        ]
        self.assertEqual(forex_daily_plan.web_import_sources(files), files)
        diagnostic = Path("staging/usdcad/usdcad.trade-plan-public.json")
        self.assertEqual(forex_daily_plan.web_import_sources(files + [diagnostic]), files)

    def test_output_lane_removes_legacy_trade_plan_sidecars_only(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            article = folder / "gbpusd.md"
            article.write_text("keep", encoding="utf-8")
            for asset in ("gbpusd", "usdcad"):
                (folder / f"{asset}.trade-plan-public.json").write_text(
                    "{}", encoding="utf-8")
            self.assertEqual(forex_daily_plan.clear_output_sidecars(folder), 2)
            self.assertTrue(article.is_file())
            self.assertFalse(any(folder.glob("*.trade-plan-public.json")))

    def test_calendar_cleanup_is_asset_scoped_and_removes_all_old_pages(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            targets = [
                folder / "gbpusd-forex-daily-calendar-2026-09-03.webp",
                folder / "gbpusd-forex-daily-calendar-2026-09-03-p01-of-02.webp",
            ]
            keep = folder / "usdcad-forex-daily-calendar-2026-09-03.webp"
            for path in [*targets, keep]:
                path.write_bytes(b"fixture")
            self.assertEqual(
                forex_daily_plan.clear_output_calendar_images(folder, "gbpusd"), 2)
            self.assertFalse(any(path.exists() for path in targets))
            self.assertTrue(keep.exists())

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


def test_style_l_r8_matrix_exposes_complete_per_image_metadata():
    cases = (
        ("style-l-eurusd-h1-plan", "EUR/USD", "H1", None, True),
        ("style-l-eurusd-m15-wait", "EUR/USD", "M15",
         "NO TRADE / รอยืนยัน", True),
        ("style-l-eurusd-m15-neutral-oco", "EUR/USD", "M15", None, True),
        ("style-l-usdjpy-m15-neutral-oco", "USD/JPY", "M15", None, True),
    )
    for role, symbol, timeframe, card, surface_aware in cases:
        figure, _ = forex_daily_plan.premium_chart_figure(
            symbol, timeframe, "fixture",
            header_accessory_text=card,
            header_accessory_role=("style-l-m15-wait" if card else None),
            surface_aware_watermark=surface_aware)
        metadata = forex_daily_plan.style_l_figure_metadata(figure, role=role)
        assert metadata["role"] == role
        assert metadata["exact_title"] == f"{symbol} · {timeframe}"
        assert metadata["source_dimensions_px"] == [1680, 900]
        assert metadata["header"]["role"] == "premium-decoration:header-face"
        assert metadata["header"]["bbox_px"][0] == 0
        assert metadata["header"]["bbox_px"][2] == 1680
        assert metadata["header"]["underline"]["role"] == (
            "premium-decoration:header-underline")
        assert metadata["header"]["underline"]["color"] == "#D6B34A"
        assert (metadata["status_card"] is not None) == bool(card)
        watermark = metadata["watermark"]
        assert watermark["role"] == "premium-decoration:watermark"
        assert watermark["text"] == "WorldClassBroker"
        if surface_aware:
            assert watermark["color"] == "#0E2A1D"
            assert watermark["alpha"] == 0.12
            assert watermark["palette_role"] == "light_plot"
            assert watermark["surface_contrast"]["mode"] == "surface-aware"
            assert watermark["surface_contrast"]["effective_contrast_ratio"] >= 1.20
            assert watermark["surface_contrast"]["visibility_pass"] is True
        else:
            assert watermark["color"] == "#F4F1E7"
            assert watermark["alpha"] == 0.08
            assert watermark["palette_role"] == "chart"
            assert watermark["surface_contrast"]["mode"] == "fixed"
        assert watermark["rotation"] == 0
        assert watermark["layer"] == "above_background_and_zones_below_factual"
        assert watermark["vertical_nudge"] == 0.0
        assert watermark["font_weight"] == "medium"
        assert watermark["tracking_px"] >= 1.0
        assert len(watermark["bbox_px"]) == 4
        assert 0.49 <= watermark["center_x_ratio"] <= 0.51
        assert 0.42 <= watermark["center_y_ratio"] <= 0.58
        forex_daily_plan.plt.close(figure)


def _capture_saved_figure(monkeypatch):
    captured = []

    def inspect(figure, *_args, **_kwargs):
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        canvas = FigureCanvasAgg(figure)
        canvas.draw()
        captured.append((figure, canvas.get_renderer()))
        return 123

    monkeypatch.setattr(forex_daily_plan, "_thai_font", lambda: None)
    monkeypatch.setattr(forex_daily_plan.image_output, "save_figure", inspect)
    return captured


def _fixture_rows(price=1.3545, count=120):
    return [{
        "at": f"2026-09-{(index % 28) + 1:02d} {index % 24:02d}:00:00",
        "open": price, "high": price + 0.001, "low": price - 0.001,
        "close": price + 0.0002,
    } for index in range(count)]


def test_r2_annotation_patch_is_opaque_and_above_price_line():
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.colors import to_rgba

    figure, axis = plt.subplots(figsize=(14, 7.5), dpi=120)
    try:
        axis.set_xlim(0, 1)
        axis.set_ylim(0, 2)
        annotation = forex_daily_plan.add_price_line(
            axis, 1.0, "SL 1.000", "#C94C4C", role="stop-loss")
        canvas = FigureCanvasAgg(figure)
        canvas.draw()
        line = next(item for item in axis.lines
                    if item.get_gid() == "premium-line:style-l:stop-loss")
        patch = annotation.get_bbox_patch()
        assert annotation.get_zorder() > line.get_zorder()
        assert patch.get_zorder() > line.get_zorder()
        assert patch.get_facecolor()[3] == 1.0
        assert patch.get_alpha() == 1.0
        # Raster contract: the line's alpha-composited color must not survive
        # inside the opaque patch interior (excluding the 2 px border).
        pixels = np.asarray(canvas.buffer_rgba())[:, :, :3]
        box = patch.get_window_extent(canvas.get_renderer())
        x0, x1 = int(box.x0) + 2, int(box.x1) - 2
        y0, y1 = int(box.y0) + 2, int(box.y1) - 2
        interior = pixels[y0:y1, x0:x1]
        line_rgb = np.array(to_rgba("#C94C4C")[:3]) * 255
        line_rgb = line_rgb * 0.9 + 255 * 0.1
        assert not np.any(np.linalg.norm(interior - line_rgb, axis=2) <= 3.0)
    finally:
        plt.close(figure)


def test_r3_gbpusd_h1_pdl_uses_right_rail(monkeypatch):
    captured = _capture_saved_figure(monkeypatch)
    h1 = dict(ForexDailyPlanContract.GBPUSD_2026_09_01_H1)
    plan = copy.deepcopy(ForexDailyPlanContract.GBPUSD_2026_09_01_PLAN)
    forex_daily_plan.save_h1_chart(
        "gbpusd", _fixture_rows(), _fixture_rows(), {"structure": "lower_high_low"},
        h1, plan, "down", {"basis_close_at": "2026-09-01T09:00:00+07:00"},
        Path("unused.webp"))
    figure, renderer = captured[0]
    axis = figure.axes[-1]
    label = next(item for item in axis.texts
                 if item.get_gid() == "premium-label:style-l:h1-pdl")
    axis_box = axis.get_window_extent(renderer)
    box = label.get_bbox_patch().get_window_extent(renderer)
    gap = axis_box.x1 - box.x1
    assert 8 <= gap <= 20
    assert box.x0 > axis_box.x0 + axis_box.width * 0.75
    assert label.xy[1] == h1["pdl"]


def test_r2_gbpusd_m15_side_copy_rails_zone_policy_and_line_spans(monkeypatch):
    captured = _capture_saved_figure(monkeypatch)
    plan = _canonical_plan(direction="down", current_close=1.35390)
    plan["plans"][0]["side"] = "BUY"
    plan["plans"][0]["entry_zone"] = {"low": 1.34900, "high": 1.34920}
    rows = _fixture_rows()
    forex_daily_plan.save_m15_chart(
        "gbpusd", rows, "I", {"H": {}, "I": {"donchian": {"upper": 1.34950,
        "lower": 1.34850}}}, plan, "up", {"basis_close_at": "2026-09-03T16:35:16+07:00"},
        forex_daily_plan.load_decision_policy(), Path("unused.webp"))
    figure, renderer = captured[0]
    axis = figure.axes[-1]
    labels = {item.get_gid().split(":")[-1]: item for item in axis.texts
              if str(item.get_gid() or "").startswith("premium-label:style-l:")}
    assert labels["entry-trigger"].get_text().startswith("BUY Entry ")
    assert labels["stop-loss"].get_text().startswith("SL ")
    assert labels["target-1"].get_text().startswith("TP1 ")
    assert labels["target-2"].get_text().startswith("TP2 ")
    axis_box = axis.get_window_extent(renderer)
    for role in ("entry-trigger", "stop-loss", "target-1", "target-2"):
        box = labels[role].get_bbox_patch().get_window_extent(renderer)
        assert 8 <= axis_box.x1 - box.x1 <= 20
    for role in ("donchian-upper", "donchian-lower"):
        box = labels[role].get_bbox_patch().get_window_extent(renderer)
        assert 8 <= box.x0 - axis_box.x0 <= 20
        line = next(item for item in axis.lines
                    if item.get_gid() == f"premium-line:style-l:{role}")
        assert line.get_linestyle() == "-"
        assert list(line.get_xdata()) == [0.0, 1.0]
    assert len([patch for patch in axis.patches
                if patch.get_gid() == "premium-zone:style-l:entry-zone"]) == 1
    latest_x = axis.transData.transform((len(rows[-120:]) - 1, 1.349))[0]
    right_x = axis.get_window_extent(renderer).x1
    for role in ("entry-trigger", "stop-loss", "target-1", "target-2"):
        line = next(item for item in axis.lines
                    if item.get_gid() == f"premium-line:style-l:{role}")
        line_x = axis.transData.transform((line.get_xdata()[0], 1.349))[0]
        end_x = axis.transData.transform((line.get_xdata()[-1], 1.349))[0]
        assert abs(line_x - latest_x) <= 1
        assert abs(end_x - right_x) <= 1


def test_r2_gbpusd_m15_equal_or_missing_entry_zone_draws_no_band(monkeypatch):
    for zone in ({"low": 1.34914, "high": 1.34914}, {},
                 {"low": float("nan"), "high": 1.34920}):
        captured = _capture_saved_figure(monkeypatch)
        plan = _canonical_plan(direction="down", current_close=1.35390)
        plan["plans"][0]["entry_zone"] = zone
        forex_daily_plan.save_m15_chart(
            "gbpusd", _fixture_rows(), "I", {"I": {"donchian": {
                "upper": 1.34950, "lower": 1.34850}}}, plan, "down",
            {"basis_close_at": "2026-09-03T16:35:16+07:00"},
            forex_daily_plan.load_decision_policy(), Path("unused.webp"))
        figure, _ = captured[0]
        assert not any(patch.get_gid() == "premium-zone:style-l:entry-zone"
                       for patch in figure.axes[-1].patches)


def test_r2_usdcad_oco_uses_unified_right_rail_and_last_candle_segments(monkeypatch):
    captured = _capture_saved_figure(monkeypatch)
    rows = _fixture_rows(price=1.38349)
    forex_daily_plan.save_m15_chart(
        "usdcad", rows, "NO_SETUP", {"I": {}}, _usdcad_oco_plan(), None,
        {"basis_close_at": "2026-09-03T16:35:16+07:00"},
        forex_daily_plan.load_decision_policy(), Path("unused.webp"))
    figure, renderer = captured[0]
    axis = figure.axes[-1]
    labels = [item for item in axis.texts
              if str(item.get_gid() or "").startswith("premium-label:style-l:oco-")]
    axis_box = axis.get_window_extent(renderer)
    right_edges = [item.get_bbox_patch().get_window_extent(renderer).x1
                   for item in labels]
    assert max(right_edges) - min(right_edges) <= 2
    assert all(8 <= axis_box.x1 - right <= 20 for right in right_edges)
    latest_x = axis.transData.transform((len(rows[-120:]) - 1, 1.3835))[0]
    right_x = axis_box.x1
    for line in axis.lines:
        if str(line.get_gid() or "").startswith("premium-line:style-l:oco-"):
            start_x = axis.transData.transform((line.get_xdata()[0], 1.3835))[0]
            end_x = axis.transData.transform((line.get_xdata()[-1], 1.3835))[0]
            assert abs(start_x - latest_x) <= 1
            assert abs(end_x - right_x) <= 1


def test_r3_gbpusd_h1_pdl_returns_to_right_rail_without_close_collision(monkeypatch):
    captured = _capture_saved_figure(monkeypatch)
    h1 = dict(ForexDailyPlanContract.GBPUSD_2026_09_01_H1)
    plan = copy.deepcopy(ForexDailyPlanContract.GBPUSD_2026_09_01_PLAN)
    forex_daily_plan.save_h1_chart(
        "gbpusd", _fixture_rows(), _fixture_rows(), {"structure": "lower_high_low"},
        h1, plan, "down", {"basis_close_at": "2026-09-01T09:00:00+07:00"},
        Path("unused.webp"))
    figure, renderer = captured[0]
    axis = figure.axes[-1]
    labels = {item.get_gid().split(":")[-1]: item for item in axis.texts
              if str(item.get_gid() or "").startswith("premium-label:style-l:h1-")}
    axis_box = axis.get_window_extent(renderer)
    pdl_box = labels["h1-pdl"].get_bbox_patch().get_window_extent(renderer)
    close_box = labels["h1-close"].get_bbox_patch().get_window_extent(renderer)
    assert pdl_box.x0 > axis_box.x0 + axis_box.width * 0.75
    assert close_box.x0 > axis_box.x0 + axis_box.width * 0.75
    assert not pdl_box.overlaps(close_box)
    assert labels["h1-pdl"].xy[1] == h1["pdl"]
    assert labels["h1-close"].xy[1] == h1["close"]
    assert labels["h1-pdl"].arrow_patch is None
    assert labels["h1-close"].arrow_patch is None


def test_r3_gbpusd_m15_entry_and_header_card_share_canonical_side(monkeypatch):
    for side in ("SELL", "BUY"):
        captured = _capture_saved_figure(monkeypatch)
        plan = _canonical_plan(direction="down", current_close=1.35390)
        plan["plans"][0]["side"] = side
        forex_daily_plan.save_m15_chart(
            "gbpusd", _fixture_rows(), "I", {"I": {"donchian": {
                "upper": 1.34950, "lower": 1.34850}}}, plan, "down",
            {"basis_close_at": "2026-09-03T16:35:16+07:00"},
            forex_daily_plan.load_decision_policy(), Path("unused.webp"))
        figure, _ = captured[0]
        labels = [item.get_text() for item in figure.axes[-1].texts
                  if str(item.get_gid() or "").startswith("premium-label:style-l:")]
        assert sum(text.startswith(f"{side} Entry ") for text in labels) == 1
        assert not any("Entry Trigger" in text for text in labels)
        card = figure._premium_header_card_layout
        assert card["text"] == f"แผน {side}"
        assert card["face"] == "#F4F1E7"
        assert card["edge"] == "#D6B34A"
        assert card["text_color"] == "#0E2A1D"
        assert card["contrast"] >= 7.0


def test_r3_usdcad_neutral_oco_uses_entry_copy_without_trigger_or_oco(monkeypatch):
    captured = _capture_saved_figure(monkeypatch)
    forex_daily_plan.save_m15_chart(
        "usdcad", _fixture_rows(price=1.38349), "NO_SETUP", {"I": {}},
        _usdcad_oco_plan(), None,
        {"basis_close_at": "2026-09-03T16:35:16+07:00"},
        forex_daily_plan.load_decision_policy(), Path("unused.webp"))
    figure, _ = captured[0]
    texts = [item.get_text() for item in figure.axes[-1].texts
             if str(item.get_gid() or "").startswith("premium-label:style-l:oco-")]
    assert sum(text.startswith("BUY Entry ") for text in texts) == 1
    assert sum(text.startswith("SELL Entry ") for text in texts) == 1
    assert not any("Trigger" in text or "OCO" in text for text in texts)
