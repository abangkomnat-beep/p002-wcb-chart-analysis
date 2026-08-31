from __future__ import annotations

import copy
import tempfile
from pathlib import Path

from tools import style_m_article_contract, style_m_renderer, style_m_writer
from test_style_m_semantics import conflict_story, rows_fixture


def valid_package():
    rows = rows_fixture()
    story = conflict_story(rows)
    facts = style_m_article_contract.build(story, rows)
    composed = style_m_writer.compose(story, [], facts)
    with tempfile.TemporaryDirectory() as tmp:
        rendered = style_m_renderer.render(story, rows, Path(tmp) / "chart.webp", facts)
    parity = style_m_article_contract.parity_report(
        facts, markdown=composed["markdown"],
        writer_report=composed["claim_report"], render_report=rendered)
    return story, rows, facts, composed, rendered, parity


def finding_codes(report):
    return {item["code"] for item in report["findings"]}


def test_valid_claim_bound_package_passes():
    *_, parity = valid_package()
    assert parity["schema"] == "style-m-claim-parity-report/v2"
    assert parity["status"] == "PASS"
    assert parity["findings"] == []


def test_wrong_label_ema20_ema50_blocks_even_when_both_numeric_tokens_exist():
    _, _, facts, composed, rendered, _ = valid_package()
    report = copy.deepcopy(composed["claim_report"])
    bindings = {item["claim_id"]: item for item in report["bindings"]}
    left = bindings["claim.market.ema20"]
    right = bindings["claim.market.ema50"]
    left["label"], right["label"] = right["label"], left["label"]
    parity = style_m_article_contract.parity_report(
        facts, markdown=composed["markdown"], writer_report=report, render_report=rendered)
    assert parity["status"] == "BLOCK"
    assert "CLAIM_LABEL_MISMATCH" in finding_codes(parity)


def test_fragment_hash_mismatch_blocks_even_when_visible_text_is_unchanged():
    _, _, facts, composed, rendered, _ = valid_package()
    report = copy.deepcopy(composed["claim_report"])
    report["bindings"][0]["fragment_sha256"] = "0" * 64
    parity = style_m_article_contract.parity_report(
        facts, markdown=composed["markdown"], writer_report=report, render_report=rendered)
    assert parity["status"] == "BLOCK"
    assert "CLAIM_FRAGMENT_MISMATCH" in finding_codes(parity)


def test_unclaimed_public_number_blocks_before_package_write():
    _, _, facts, composed, rendered, _ = valid_package()
    report = copy.deepcopy(composed["claim_report"])
    report["unbound_numeric_tokens"] = ["88,888.00"]
    parity = style_m_article_contract.parity_report(
        facts, markdown=composed["markdown"], writer_report=report, render_report=rendered)
    assert parity["status"] == "BLOCK"
    assert "UNBOUND_NUMERIC_TOKEN" in finding_codes(parity)


def test_renderer_trendline_anchor_mutation_blocks_against_canonical_claim():
    _, _, facts, composed, rendered, _ = valid_package()
    trend_bindings = [item for item in rendered["bindings"]
                      if item["claim_id"] == "claim.analysis.trendline"]
    if not trend_bindings:
        return
    changed = copy.deepcopy(rendered)
    target = next(item for item in changed["bindings"]
                  if item["claim_id"] == "claim.analysis.trendline")
    target["anchor_fact_ids"] = list(reversed(target["anchor_fact_ids"]))
    parity = style_m_article_contract.parity_report(
        facts, markdown=composed["markdown"],
        writer_report=composed["claim_report"], render_report=changed)
    assert parity["status"] == "BLOCK"
    assert "CLAIM_ANCHOR_MISMATCH" in finding_codes(parity)

