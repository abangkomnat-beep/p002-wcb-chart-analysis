from __future__ import annotations

import unittest
import hashlib
from copy import deepcopy

from tools import style_m_article_contract as contract
from tools import style_m_semantics, style_m_story
from test_style_m_semantics import conflict_story, rows_fixture


class StyleMArticleContract(unittest.TestCase):
    def story(self, state="NO_PLAN"):
        return {
            "schema": style_m_story.SCHEMA, "asset": "btcusd", "timeframe": "1h",
            "cutoff": "2026-08-29T11:00:00+07:00",
            "latest": {"at": "2026-08-29 10:00:00", "close": 100.0},
            "indicators": {"ema20": 101.0, "ema50": 100.0, "atr14": 2.0},
            "pivots": {"highs": [{"index": 70, "at": "2026-08-28 12:00:00", "price": 110.0},
                                  {"index": 90, "at": "2026-08-29 08:00:00", "price": 108.0}],
                       "lows": [{"index": 60, "at": "2026-08-28 02:00:00", "price": 90.0},
                                {"index": 85, "at": "2026-08-29 03:00:00", "price": 92.0}]},
            "source_sha256": "a" * 64, "state": state, "side": None,
            "reason_code": "STRUCTURE_CONFLICT", "reason": "conflict",
            "show_plan_geometry": False, "plan": None,
        }

    def test_manifest_has_stable_schema_and_occupancy_meaning(self):
        facts = contract.build(self.story(), [])
        self.assertEqual(facts["schema"], "style-m-article-visual-facts/v2")
        self.assertEqual(facts["contract_version"], "M-PROD/v5")
        self.assertEqual(facts["semantic_decision"]["schema"],
                         "style-m-semantic-decision/v1")
        self.assertTrue(facts["claims"])
        self.assertFalse(facts["facts"]["occupancy.price_bins"]["source_volume_available"])
        self.assertEqual(facts["facts"]["occupancy.price_bins"]["count"], 72)
        self.assertEqual(facts["web_routes"], {"primary": "/thailand/asset-btc",
                                                "secondary": "/thailand/analysis"})

    def test_no_plan_forbids_trade_geometry(self):
        facts = contract.build(self.story(), [])
        self.assertEqual(facts["facts"]["plan.entry"]["permission"], "FORBIDDEN")
        self.assertEqual(facts["facts"]["plan.sl_tp_rr"]["permission"], "FORBIDDEN")
        self.assertFalse(any(key.startswith("claim.plan.entry") for key in facts["claims"]))

    def test_four_state_permission_matrix(self):
        for state in ("NO_PLAN", "INVALIDATED", "WAIT_H1_CONFIRM", "PLAN_VALID"):
            with self.subTest(state=state):
                story = self.story(state)
                if state == "INVALIDATED":
                    story.update({"side": "BUY", "reason_code": "STOP_INVALIDATED"})
                if state in ("WAIT_H1_CONFIRM", "PLAN_VALID"):
                    story.update({"side": "BUY", "show_plan_geometry": True,
                                  "reason_code": "PLAN_VALID",
                                  "plan": {"entry_low": 92.0, "entry_high": 92.5,
                                            "sl": 90.0, "tp1": 100.0, "tp2": 108.0,
                                            "rr1": 2.0, "rr2": 4.0,
                                            "min_rr1": 1.5, "min_rr2": 2.0,
                                            "dynamic_entry_limit": 94.0,
                                            "entry_zone_atr": 0.25,
                                            "stop_buffer_atr": 0.75,
                                            "worst_entry_risk_atr": 1.0}})
                facts = contract.build(story, [])
                self.assertEqual(facts["facts"]["plan.state"]["value"], state)
                if state in ("NO_PLAN", "INVALIDATED"):
                    self.assertEqual(facts["facts"]["plan.sl_tp_rr"]["permission"], "FORBIDDEN")
                    self.assertEqual(facts["facts"]["plan.side"]["permission"], "FORBIDDEN")
                else:
                    self.assertIn("plan.entry_low", facts["facts"])
                    self.assertIn("plan.tp2", facts["facts"])
                    self.assertEqual(facts["facts"]["plan.side"]["value"], "BUY")
                    self.assertEqual(facts["facts"]["plan.side"]["permission"],
                                     "CONDITIONAL" if state == "WAIT_H1_CONFIRM" else "ALLOWED")

    def test_duplicate_no_plan_is_hold(self):
        facts = contract.build(self.story(), [])
        result = contract.index_recommendation(facts, facts["semantic_fingerprint"])
        self.assertEqual(result["recommendation"], "HOLD_DUPLICATE_NO_PLAN")
        self.assertFalse(result["index"])

    def test_duplicate_tolerance_is_atr_normalized(self):
        facts = contract.build(self.story(), [])
        inside = deepcopy(facts)
        inside["fingerprint_basis"]["support"]["low"] += 0.20  # exactly 0.10 ATR14
        self.assertEqual(contract.index_recommendation(facts, inside)["recommendation"],
                         "HOLD_DUPLICATE_NO_PLAN")
        outside = deepcopy(facts)
        outside["fingerprint_basis"]["support"]["low"] += 0.21
        self.assertEqual(contract.index_recommendation(facts, outside)["recommendation"], "NEW_DRAFT")

    def test_v1_prior_migrates_read_only_and_never_holds_as_v2_equal(self):
        facts = contract.build(self.story(), [])
        legacy = {"schema": contract.LEGACY_SCHEMA,
                  "semantic_fingerprint": facts["semantic_fingerprint"],
                  "fingerprint_basis": facts["fingerprint_basis"]}
        migrated = contract.migrate_prior_v1(legacy)
        self.assertEqual(migrated["migration_version"], "style-m-v1-prior-adapter/v1")
        self.assertEqual(migrated["migrated_from"], contract.LEGACY_SCHEMA)
        self.assertFalse(migrated["comparable_to_v2"])
        self.assertEqual(contract.index_recommendation(facts, legacy)["recommendation"],
                         "NEW_DRAFT")

    def test_parity_label_mutation_blocks_typed_claim(self):
        facts = contract.build(self.story(), [])
        markdown = "canonical fragment"
        reports = {}
        for consumer, schema in (("writer", "style-m-writer-claim-report/v1"),
                                 ("renderer", "style-m-renderer-claim-report/v1")):
            bindings = []
            for claim_id, claim in facts["claims"].items():
                if consumer not in claim["consumers"]:
                    continue
                binding = {"binding_id": f"{consumer}.{len(bindings)}", "claim_id": claim_id,
                           "consumer": consumer, "rendered_value": claim["value"],
                           "unit": claim["unit"], "timeframe": claim["timeframe"],
                           "source_fact_ids": claim["source_fact_ids"], "label": claim["label"],
                           "anchor_fact_ids": (claim["value"].get("anchor_fact_ids", [])
                                               if isinstance(claim["value"], dict) else [])}
                if consumer == "writer":
                    binding.update({"fragment": markdown,
                                    "fragment_sha256": hashlib.sha256(
                                        markdown.encode("utf-8")).hexdigest()})
                bindings.append(binding)
            reports[consumer] = {"schema": schema, "facts_sha256": facts["facts_sha256"],
                                 "bindings": bindings, "unbound_numeric_tokens": []}
        reports["writer"]["bindings"][0]["label"] = "wrong label"
        report = contract.parity_report(facts, markdown=markdown,
                                        writer_report=reports["writer"],
                                        render_report=reports["renderer"])
        self.assertEqual(report["status"], "BLOCK")
        self.assertIn("CLAIM_LABEL_MISMATCH", {item["code"] for item in report["findings"]})

    def test_verified_news_is_one_public_advisory(self):
        event = {"event_id": "e1", "title": "Fed", "url": "https://example.test/fed",
                 "time_thai": "29/08 20:00 น."}
        facts = contract.build(self.story(), [], events=[event, dict(event, event_id="e2")])
        self.assertTrue(facts["news"]["public_advisory"])
        self.assertEqual(facts["news"]["selected_event_id"], "e1")

    def test_permission_enum_and_no_plan_matrix_are_strict(self):
        facts = contract.build(self.story(), [])
        allowed = {"FORBIDDEN", "CONTEXT_ONLY", "DIAGNOSTIC_ONLY", "CONDITIONAL", "ALLOWED"}
        permissions = [item["permission"] for item in facts["facts"].values()
                       if isinstance(item, dict) and "permission" in item]
        permissions += [item["permission"] for item in facts["claims"].values()]
        permissions += list(facts["semantic_decision"]["decision"]["permissions"].values())
        self.assertTrue(set(permissions) <= allowed)
        self.assertNotIn("CONDITIONAL_ONLY", permissions)
        self.assertFalse(any(key.startswith("claim.plan.") and key != "claim.plan.state"
                             for key in facts["claims"]))

    def test_reason_fact_is_causal_source_of_implication_and_reassessment(self):
        facts = contract.build(self.story(), [])
        self.assertEqual(facts["facts"]["decision.reason_code"]["value"], "STRUCTURE_CONFLICT")
        implication = facts["claims"]["claim.analysis.decision_implication"]
        self.assertEqual(implication["source_fact_ids"],
                         ["plan.state", "decision.reason_code"])
        self.assertIn("decision.reason_code",
                      facts["facts"]["analysis.decision_implication"]["derived_from"])

    def test_rehashed_invalid_claim_permission_still_fails_closed(self):
        facts = contract.build(self.story(), [])
        facts["claims"]["claim.market.ema20"]["permission"] = "MAYBE"
        facts["facts_sha256"] = contract._facts_hash(facts)
        with self.assertRaises(contract.ArticleContractError) as caught:
            contract.validate(facts, story=self.story())
        self.assertEqual(caught.exception.code, "CLAIM_PERMISSION_INVALID")

    def test_rehashed_valid_but_escalated_claim_permission_fails_derivation(self):
        story = self.story()
        facts = contract.build(story, [])
        facts["claims"]["claim.market.ema20"]["permission"] = "ALLOWED"
        facts["facts_sha256"] = contract._facts_hash(facts)
        with self.assertRaises(contract.ArticleContractError) as caught:
            contract.validate(facts, story=story)
        self.assertEqual(caught.exception.code, "CLAIM_PERMISSION_DERIVATION_MISMATCH")

    def test_rehashed_claim_projection_mutations_fail_exact_canonical_comparison(self):
        story = self.story()
        cases = {
            "role": lambda claim, facts: claim.update(role="PLAN_LEVEL"),
            "value": lambda claim, facts: claim.update(
                value=facts["facts"]["market.ema50"]["value"]),
            "consumers": lambda claim, facts: claim.update(consumers=["writer"]),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                facts = contract.build(story, [])
                mutate(facts["claims"]["claim.market.ema20"], facts)
                facts["facts_sha256"] = contract._facts_hash(facts)
                with self.assertRaises(contract.ArticleContractError) as caught:
                    contract.validate(facts, story=story)
                self.assertEqual(caught.exception.code, "CLAIM_PROJECTION_MISMATCH")

    def test_rehashed_viewport_field_mutations_fail_full_registry_projection(self):
        rows = rows_fixture()
        story = conflict_story(rows)
        mutations = {
            "policy": lambda viewport: viewport.update(policy="forged/v9"),
            "canvas": lambda viewport: viewport["canvas"].__setitem__(0, 1820),
            "plot_bounds": lambda viewport: viewport["plot_bounds"].__setitem__(
                0, viewport["plot_bounds"][0] + 100),
            "future_slots": lambda viewport: viewport.update(
                future_slots=viewport["future_slots"] + 1),
            "visible_start_index": lambda viewport: viewport.update(
                visible_start_index=viewport["visible_start_index"] + 1),
            "visible_end_index": lambda viewport: viewport.update(
                visible_end_index=viewport["visible_end_index"] - 1),
            "visible_count": lambda viewport: viewport.update(
                visible_count=viewport["visible_count"] - 1),
            "slot": lambda viewport: viewport.update(slot=viewport["slot"] + 1.0),
            "price_min": lambda viewport: viewport.update(
                price_min=viewport["price_min"] - 5_000.0),
            "price_max": lambda viewport: viewport.update(
                price_max=viewport["price_max"] + 5_000.0),
        }
        for field, mutate in mutations.items():
            with self.subTest(field=field):
                facts = contract.build(story, rows)
                mutate(facts["facts"]["visual.viewport"])
                facts["facts_sha256"] = contract._facts_hash(facts)
                with self.assertRaises(contract.ArticleContractError) as caught:
                    contract.validate(facts, story=story, rows=rows)
                self.assertEqual(caught.exception.code,
                                 "FACT_REGISTRY_PROJECTION_MISMATCH")

    def test_rehashed_authoritative_registry_mutation_fails_full_projection(self):
        rows = rows_fixture()
        story = conflict_story(rows)
        facts = contract.build(story, rows)
        facts["facts"]["occupancy.price_bins"]["count"] = 71
        facts["facts_sha256"] = contract._facts_hash(facts)
        with self.assertRaises(contract.ArticleContractError) as caught:
            contract.validate(facts, story=story, rows=rows)
        self.assertEqual(caught.exception.code, "FACT_REGISTRY_PROJECTION_MISMATCH")

    def test_rehashed_authoritative_envelope_mutations_fail_full_projection(self):
        rows = rows_fixture()
        story = conflict_story(rows)
        event = {"event_id": "e1", "title": "Fed", "url": "https://example.test/fed",
                 "time_thai": "29/08 20:00 น."}
        legacy = {"schema": contract.LEGACY_SCHEMA,
                  "semantic_fingerprint": "legacy-fingerprint",
                  "fingerprint_basis": {"state": "NO_PLAN"}}
        mutations = {
            "asset": lambda payload: payload.update(asset="xauusd"),
            "timeframe": lambda payload: payload.update(timeframe="4h"),
            "cutoff": lambda payload: payload.update(cutoff="2026-08-30T11:00:00+07:00"),
            "source_sha256": lambda payload: payload["source"].update(sha256="0" * 64),
            "source_closed_h1": lambda payload: payload["source"].update(closed_h1=False),
            "web_route": lambda payload: payload["web_routes"].update(primary="/forged"),
            "semantic_fingerprint": lambda payload: payload.update(
                semantic_fingerprint="0" * 64),
            "fingerprint_basis": lambda payload: payload["fingerprint_basis"].update(
                reason_bucket="FORGED"),
            "news": lambda payload: payload["news"].update(public_advisory=False),
            "migration": lambda payload: payload["migration"].update(
                migration_version="forged/v9"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                facts = contract.build(story, rows, events=[event],
                                       news_report={"provider_status": "ok"},
                                       prior_fingerprint=legacy)
                mutate(facts)
                facts["facts_sha256"] = contract._facts_hash(facts)
                with self.assertRaises(contract.ArticleContractError) as caught:
                    contract.validate(facts, story=story, rows=rows, events=[event])
                self.assertEqual(caught.exception.code,
                                 "FACT_DOCUMENT_PROJECTION_MISMATCH")

    def test_news_projection_never_trusts_registry_as_expected_input(self):
        rows = rows_fixture()
        story = conflict_story(rows)
        official = {"event_id": "official-1", "title": "Federal Reserve remarks",
                    "url": "https://www.federalreserve.gov/official",
                    "time_thai": "29/08 20:00 น."}
        forged = {"event_id": "evil-1", "title": "Forged signal",
                  "url": "https://evil.example/forge", "time_thai": "29/08 20:00 น."}

        canonical = contract.build(story, rows, events=[official])
        with self.assertRaises(contract.ArticleContractError) as omitted:
            contract.validate(canonical, story=story, rows=rows)
        self.assertEqual(omitted.exception.code, "FACT_REGISTRY_PROJECTION_MISMATCH")

        forged_news = contract.build(story, rows, events=[forged])
        for name, source in (("official_forged", canonical),
                             ("zero_news_injected", contract.build(story, rows))):
            with self.subTest(name=name):
                facts = deepcopy(source)
                facts["facts"]["news.risk_context"] = deepcopy(
                    forged_news["facts"]["news.risk_context"])
                facts["claims"]["claim.news.risk_context"] = deepcopy(
                    forged_news["claims"]["claim.news.risk_context"])
                facts["news"] = deepcopy(forged_news["news"])
                facts["facts_sha256"] = contract._facts_hash(facts)
                trusted_events = [official] if name == "official_forged" else []
                with self.assertRaises(contract.ArticleContractError) as caught:
                    contract.validate(facts, story=story, rows=rows,
                                      events=trusted_events)
                self.assertEqual(caught.exception.code,
                                 "FACT_REGISTRY_PROJECTION_MISMATCH")

    def test_coherent_facts_semantic_and_claim_rehash_still_fails_canonical_registry(self):
        rows = rows_fixture()
        story = conflict_story(rows)
        facts = contract.build(story, rows)
        registry = facts["facts"]
        registry["market.ema20"]["value"] = registry["market.ema50"]["value"]
        semantic = style_m_semantics.build(story, registry, rows)
        facts["semantic_decision"] = semantic
        for key, item in semantic["relations"].items():
            registry[f"analysis.{key}"] = contract._derived_fact(
                item["value"], item["derived_from"])
        registry["analysis.decision_alignment"] = contract._derived_fact(
            semantic["decision"]["alignment"], ["plan.state", "decision.reason_code"])
        registry["analysis.decision_implication"] = contract._derived_fact(
            semantic["decision"]["implication"], ["plan.state", "decision.reason_code"])
        registry["analysis.reassessment_observations"] = contract._derived_fact(
            semantic["decision"]["reassessment_observation_codes"],
            ["analysis.decision_implication"])
        registry["analysis.trendline"] = {
            **semantic["trendline"],
            "derived_from": semantic["trendline"].get("anchor_fact_ids", []),
            "rule": style_m_semantics.RULE_VERSION,
        }
        breakout_sources = list(semantic["breakout"].get("trendline_anchor_fact_ids", []))
        if semantic["breakout"].get("evaluated_candle_fact_id"):
            breakout_sources.append(semantic["breakout"]["evaluated_candle_fact_id"])
        registry["analysis.breakout"] = {
            **semantic["breakout"], "derived_from": breakout_sources,
            "rule": style_m_semantics.RULE_VERSION,
        }
        facts["claims"] = contract._claims(story, registry, semantic, [])
        facts["facts_sha256"] = contract._facts_hash(facts)
        with self.assertRaises(contract.ArticleContractError) as caught:
            contract.validate(facts, story=story, rows=rows)
        self.assertEqual(caught.exception.code, "FACT_REGISTRY_PROJECTION_MISMATCH")

    def test_semantic_mutation_and_rehash_still_fails_derivation_validation(self):
        facts = contract.build(self.story(), [])
        facts["semantic_decision"]["decision"]["implication"] = "WAIT_FOR_RETEST"
        semantic_payload = dict(facts["semantic_decision"])
        semantic_payload.pop("semantic_sha256", None)
        facts["semantic_decision"]["semantic_sha256"] = contract._json_hash(semantic_payload)
        facts["facts_sha256"] = contract._facts_hash(facts)
        with self.assertRaises(contract.ArticleContractError) as caught:
            contract.validate(facts, story=self.story(), rows=[])
        self.assertEqual(caught.exception.code, "SEMANTIC_DERIVATION_MISMATCH")


if __name__ == "__main__":
    unittest.main()
