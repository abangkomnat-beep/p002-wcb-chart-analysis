from __future__ import annotations

import copy
import hashlib
import tempfile
from pathlib import Path

import pytest

from tools import style_m_article_contract, style_m_renderer, style_m_writer
from test_style_m_semantics import conflict_story, projection_hash, rows_fixture
from test_style_m_writer_states import state_story


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


def test_swapped_ema_values_block_even_after_markdown_and_fragments_are_rehashed():
    _, _, facts, composed, rendered, _ = valid_package()
    ema20 = f"{facts['facts']['market.ema20']['value']:,.2f}"
    ema50 = f"{facts['facts']['market.ema50']['value']:,.2f}"
    original = next(line for line in composed["markdown"].splitlines()
                    if "EMA20" in line and "EMA50" in line)
    swapped = original.replace(f"EMA20 {ema20}", "EMA20 __SWAP__").replace(
        f"EMA50 {ema50}", f"EMA50 {ema20}").replace("EMA20 __SWAP__", f"EMA20 {ema50}")
    markdown = composed["markdown"].replace(original, swapped)
    report = copy.deepcopy(composed["claim_report"])
    report["markdown_sha256"] = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    for binding in report["bindings"]:
        if binding.get("fragment") == original:
            binding["fragment"] = swapped
            binding["fragment_sha256"] = hashlib.sha256(swapped.encode("utf-8")).hexdigest()
    parity = style_m_article_contract.parity_report(
        facts, markdown=markdown, writer_report=report, render_report=rendered)
    assert parity["status"] == "BLOCK"
    assert "CLAIM_FRAGMENT_MISMATCH" in finding_codes(parity)


def test_duplicate_writer_claim_id_blocks_even_with_unique_binding_and_valid_fragment():
    _, _, facts, composed, rendered, _ = valid_package()
    value = f"{facts['facts']['market.ema20']['value']:,.2f}"
    extra_fragment = f"EMA20 {value} ดอลลาร์ตามค่ามาตรฐานเดียวกัน"
    markdown = composed["markdown"] + f"\n{extra_fragment}\n"
    report = copy.deepcopy(composed["claim_report"])
    original = next(item for item in report["bindings"]
                    if item["claim_id"] == "claim.market.ema20")
    duplicate = copy.deepcopy(original)
    duplicate["binding_id"] = "writer.structure.duplicate-ema20"
    duplicate["fragment"] = extra_fragment
    duplicate["fragment_sha256"] = hashlib.sha256(extra_fragment.encode("utf-8")).hexdigest()
    report["bindings"].append(duplicate)
    report["markdown_sha256"] = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    parity = style_m_article_contract.parity_report(
        facts, markdown=markdown, writer_report=report, render_report=rendered)
    assert parity["status"] == "BLOCK"
    assert "CLAIM_BINDING_DUPLICATE" in finding_codes(parity)


def test_trigger_and_entry_threshold_cross_swap_blocks_after_coherent_rehash():
    rows = rows_fixture()
    story = state_story("WAIT_H1_CONFIRM", "BUY")
    facts = style_m_article_contract.build(story, rows)
    composed = style_m_writer.compose(story, [], facts)
    with tempfile.TemporaryDirectory() as tmp:
        rendered = style_m_renderer.render(story, rows, Path(tmp) / "chart.webp", facts)
    trigger = next(line for line in composed["markdown"].splitlines()
                   if line.startswith("- **Trigger:**"))
    entry = next(line for line in composed["markdown"].splitlines()
                 if line.startswith("- **Entry:**"))
    changed_trigger = trigger.replace("93.00", "92.00")
    changed_entry = entry.replace("92.00–93.00", "93.00–92.00")
    markdown = composed["markdown"].replace(trigger, changed_trigger).replace(entry, changed_entry)
    report = copy.deepcopy(composed["claim_report"])
    report["markdown_sha256"] = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    for binding in report["bindings"]:
        if binding.get("fragment") == trigger:
            binding["fragment"] = changed_trigger
        elif binding.get("fragment") == entry:
            binding["fragment"] = changed_entry
        else:
            continue
        binding["fragment_sha256"] = hashlib.sha256(
            binding["fragment"].encode("utf-8")).hexdigest()
    parity = style_m_article_contract.parity_report(
        facts, markdown=markdown, writer_report=report, render_report=rendered)
    assert parity["status"] == "BLOCK"
    assert "CLAIM_FRAGMENT_MISMATCH" in finding_codes(parity)


def test_invalidation_level_substitution_blocks_after_coherent_rehash():
    rows = rows_fixture()
    story = state_story("WAIT_H1_CONFIRM", "BUY")
    facts = style_m_article_contract.build(story, rows)
    composed = style_m_writer.compose(story, [], facts)
    with tempfile.TemporaryDirectory() as tmp:
        rendered = style_m_renderer.render(story, rows, Path(tmp) / "chart.webp", facts)
    original = next(line for line in composed["markdown"].splitlines()
                    if line.startswith("- **ยกเลิกแผน:**"))
    changed_fragment = original.replace("90.00", "100.00")
    markdown = composed["markdown"].replace(original, changed_fragment)
    report = copy.deepcopy(composed["claim_report"])
    report["markdown_sha256"] = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    target = next(item for item in report["bindings"]
                  if item["claim_id"] == "claim.plan.invalidation")
    target["fragment"] = changed_fragment
    target["fragment_sha256"] = hashlib.sha256(changed_fragment.encode("utf-8")).hexdigest()
    parity = style_m_article_contract.parity_report(
        facts, markdown=markdown, writer_report=report, render_report=rendered)
    assert parity["status"] == "BLOCK"
    assert "CLAIM_FRAGMENT_MISMATCH" in finding_codes(parity)


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


def test_fake_renderer_geometry_ids_block_even_with_valid_claim_values():
    _, _, facts, composed, rendered, _ = valid_package()
    changed = copy.deepcopy(rendered)
    for index, binding in enumerate(changed["bindings"]):
        binding["binding_id"] = f"renderer.fake.{index}"
        binding["geometry_id"] = f"fake.{index}"
    parity = style_m_article_contract.parity_report(
        facts, markdown=composed["markdown"], writer_report=composed["claim_report"],
        render_report=changed)
    assert parity["status"] == "BLOCK"
    assert "RENDER_TRACE_MISMATCH" in finding_codes(parity)


def test_missing_renderer_geometry_ids_block():
    _, _, facts, composed, rendered, _ = valid_package()
    changed = copy.deepcopy(rendered)
    for binding in changed["bindings"]:
        binding.pop("geometry_id", None)
    parity = style_m_article_contract.parity_report(
        facts, markdown=composed["markdown"], writer_report=composed["claim_report"],
        render_report=changed)
    assert parity["status"] == "BLOCK"
    assert "RENDER_TRACE_MISMATCH" in finding_codes(parity)


def test_trendline_draw_trace_contains_actual_pixel_geometry():
    _, _, _, _, rendered, _ = valid_package()
    trace = next(item for item in rendered["draw_trace"]
                 if item["claim_id"] == "claim.analysis.trendline")
    assert trace["draw_geometry"]["kind"] == "line"
    assert len(trace["draw_geometry"]["coordinates"]) == 4


def test_breakout_draw_trace_contains_marker_connector_and_label_geometry():
    rows = rows_fixture()
    story = conflict_story(rows)
    rows[-1]["close"] = 80_000.0
    story["latest"]["close"] = 80_000.0
    story["source_sha256"] = projection_hash(story, rows)
    facts = style_m_article_contract.build(story, rows)
    assert facts["semantic_decision"]["breakout"]["status"] == "CONFIRMED_UP_BREAK"
    with tempfile.TemporaryDirectory() as tmp:
        rendered = style_m_renderer.render(story, rows, Path(tmp) / "chart.webp", facts)
    trace = next(item for item in rendered["draw_trace"]
                 if item["claim_id"] == "claim.analysis.breakout")
    assert set(trace["draw_geometry"]) == {
        "kind", "marker_bounds", "connector", "label_bounds", "canonical"}


def test_coherently_rehashed_draw_domain_mutation_blocks_against_canonical_geometry():
    _, _, facts, composed, rendered, _ = valid_package()
    changed = copy.deepcopy(rendered)
    trace = next(item for item in changed["draw_trace"]
                 if item["claim_id"] == "claim.analysis.trendline")
    binding = next(item for item in changed["bindings"]
                   if item["claim_id"] == "claim.analysis.trendline")
    trace["draw_geometry"]["canonical"]["slope_per_bar"] += 1.0
    binding["draw_geometry"] = copy.deepcopy(trace["draw_geometry"])
    changed["visual_trace_sha256"] = style_m_article_contract._json_hash(changed["draw_trace"])
    parity = style_m_article_contract.parity_report(
        facts, markdown=composed["markdown"], writer_report=composed["claim_report"],
        render_report=changed)
    assert parity["status"] == "BLOCK"
    assert "RENDER_TRACE_MISMATCH" in finding_codes(parity)


def _coherently_update_trace(changed, claim_id, mutate):
    trace = next(item for item in changed["draw_trace"] if item["claim_id"] == claim_id)
    binding = next(item for item in changed["bindings"] if item["claim_id"] == claim_id)
    mutate(trace["draw_geometry"])
    binding["draw_geometry"] = copy.deepcopy(trace["draw_geometry"])
    trace_sha = style_m_article_contract._json_hash(changed["draw_trace"])
    changed["visual_trace_sha256"] = trace_sha
    changed["artifact"]["visual_trace_sha256"] = trace_sha
    changed["artifact"]["artifact_trace_sha256"] = hashlib.sha256(
        f"{changed['artifact']['sha256']}:{trace_sha}".encode("utf-8")).hexdigest()


@pytest.mark.parametrize("coordinates", ["shift", "tiny"])
def test_coherent_trendline_pixel_coordinate_forgery_blocks(coordinates):
    _, _, facts, composed, rendered, _ = valid_package()
    changed = copy.deepcopy(rendered)

    def mutate(geometry):
        geometry["coordinates"] = ([value + 100.0 for value in geometry["coordinates"]]
                                   if coordinates == "shift" else [0.0, 0.0, 1.0, 1.0])

    _coherently_update_trace(changed, "claim.analysis.trendline", mutate)
    parity = style_m_article_contract.parity_report(
        facts, markdown=composed["markdown"], writer_report=composed["claim_report"],
        render_report=changed)
    assert parity["status"] == "BLOCK"
    assert "RENDER_GEOMETRY_MISMATCH" in finding_codes(parity)


def test_coherent_breakout_pixel_geometry_shift_blocks():
    rows = rows_fixture()
    story = conflict_story(rows)
    rows[-1]["close"] = 80_000.0
    story["latest"]["close"] = 80_000.0
    story["source_sha256"] = projection_hash(story, rows)
    facts = style_m_article_contract.build(story, rows)
    composed = style_m_writer.compose(story, [], facts)
    with tempfile.TemporaryDirectory() as tmp:
        rendered = style_m_renderer.render(story, rows, Path(tmp) / "chart.webp", facts)
    changed = copy.deepcopy(rendered)

    def mutate(geometry):
        for key in ("marker_bounds", "connector", "label_bounds"):
            geometry[key] = [value + 200.0 for value in geometry[key]]

    _coherently_update_trace(changed, "claim.analysis.breakout", mutate)
    parity = style_m_article_contract.parity_report(
        facts, markdown=composed["markdown"], writer_report=composed["claim_report"],
        render_report=changed)
    assert parity["status"] == "BLOCK"
    assert "RENDER_GEOMETRY_MISMATCH" in finding_codes(parity)


def test_every_required_renderer_claim_has_non_null_primitive_geometry_proof():
    _, _, facts, _, rendered, _ = valid_package()
    assert rendered["viewport_policy"] == facts["facts"]["visual.viewport"]
    required = {claim_id for claim_id, claim in facts["claims"].items()
                if claim["required"] and "renderer" in claim["consumers"]}
    traced = {item["claim_id"] for item in rendered["draw_trace"]
              if isinstance(item.get("draw_geometry"), dict)
              and item["draw_geometry"].get("kind")}
    assert traced == required


def test_markdown_numeric_injection_is_scanned_from_output_not_writer_declaration():
    _, _, facts, composed, rendered, _ = valid_package()
    changed = composed["markdown"] + "\n\nระดับที่ไม่มี claim 88,888.00\n"
    parity = style_m_article_contract.parity_report(
        facts, markdown=changed, writer_report=composed["claim_report"], render_report=rendered)
    assert parity["status"] == "BLOCK"
    assert "UNBOUND_NUMERIC_TOKEN" in finding_codes(parity)


def test_writer_binding_must_contain_its_claim_label_and_formatted_value():
    _, _, facts, composed, rendered, _ = valid_package()
    report = copy.deepcopy(composed["claim_report"])
    target = next(item for item in report["bindings"]
                  if item["claim_id"] == "claim.market.ema20")
    target["fragment"] = next(line for line in composed["markdown"].splitlines()
                              if line.startswith("# "))
    import hashlib
    target["fragment_sha256"] = hashlib.sha256(target["fragment"].encode("utf-8")).hexdigest()
    parity = style_m_article_contract.parity_report(
        facts, markdown=composed["markdown"], writer_report=report, render_report=rendered)
    assert parity["status"] == "BLOCK"
    assert "CLAIM_FRAGMENT_MISMATCH" in finding_codes(parity)


def test_markdown_hash_mismatch_is_stale_even_without_numeric_change():
    _, _, facts, composed, rendered, _ = valid_package()
    changed = composed["markdown"] + "\nข้อความเพิ่ม\n"
    parity = style_m_article_contract.parity_report(
        facts, markdown=changed, writer_report=composed["claim_report"], render_report=rendered)
    assert parity["status"] != "PASS"
    assert "STALE_MARKDOWN_HASH" in finding_codes(parity)


def test_renderer_geometry_must_equal_canonical_trendline_trace():
    _, _, facts, composed, rendered, _ = valid_package()
    if facts["semantic_decision"]["trendline"]["status"] != "SHOWN":
        raise AssertionError("fixture must expose canonical trendline")
    changed = copy.deepcopy(rendered)
    changed["trendline_geometry"]["slope_per_bar"] += 1.0
    parity = style_m_article_contract.parity_report(
        facts, markdown=composed["markdown"], writer_report=composed["claim_report"],
        render_report=changed)
    assert parity["status"] == "BLOCK"
    assert "TRENDLINE_PROVENANCE_INCOMPLETE" in finding_codes(parity)


def test_false_breakout_annotation_blocks_against_not_confirmed_canonical_status():
    _, _, facts, composed, rendered, _ = valid_package()
    if facts["semantic_decision"]["breakout"]["status"] == "CONFIRMED_UP_BREAK":
        raise AssertionError("fixture must not confirm breakout")
    changed = copy.deepcopy(rendered)
    changed["breakout_annotation"] = {"status": "CONFIRMED_UP_BREAK"}
    parity = style_m_article_contract.parity_report(
        facts, markdown=composed["markdown"], writer_report=composed["claim_report"],
        render_report=changed)
    assert parity["status"] == "BLOCK"
    assert "BREAKOUT_STATUS_MISMATCH" in finding_codes(parity)
