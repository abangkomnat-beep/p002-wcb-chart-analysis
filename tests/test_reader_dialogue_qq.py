"""Independent QQ regressions: unsupported facts must not become prose claims."""
from copy import deepcopy
import json

import pytest

from tools import article_continuity as ac


def prior_plan():
    return {"plan": {"cutoff_at": "2026-09-01T00:00:00Z",
        "valid_until": "2026-09-01T02:00:00Z", "current_close": 99,
        "plans": [{"side": "BUY", "trigger": {
            "condition": "closed H1 strict cross from latest closed close", "value": 100},
            "stop_loss": 90, "take_profit": [110],
            "invalidation": {"condition": "closed H1 reaches canonical SL", "value": 90}}]}}


def rows():
    return [{"at": "2026-09-01T00:00:00Z", "open": 99, "high": 102,
             "low": 98, "close": 101},
            {"at": "2026-09-01T01:00:00Z", "open": 101, "high": 111,
             "low": 100, "close": 110}]


def test_valid_control_reaches_target_before_mutation():
    result = ac.evaluate_outcome(prior_plan(), {"rows": rows()}, "2026-09-01T02:00:00Z")
    assert result is not None and "ถึงระดับเป้าหมายแรก" in result


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_ohlc_cannot_assert_verified_outcome(value):
    candles = rows()
    candles[0]["close"] = value
    assert ac.evaluate_outcome(prior_plan(), {"rows": candles}, "2026-09-01T02:00:00Z") is None


def test_invalid_ohlc_envelope_cannot_assert_outcome():
    candles = rows()
    candles[0]["high"] = 95
    assert ac.evaluate_outcome(prior_plan(), {"rows": candles}, "2026-09-01T02:00:00Z") is None


def test_unsupported_invalidation_cannot_inherit_close_stop_rule():
    previous = prior_plan()
    previous["plan"]["plans"][0]["invalidation"]["condition"] = "custom unsupported trailing rule"
    assert ac.evaluate_outcome(previous, {"rows": rows()}, "2026-09-01T02:00:00Z") is None


def test_off_grid_h1_candles_are_not_complete_native_h1_evidence():
    previous = prior_plan()
    previous["plan"]["cutoff_at"] = "2026-09-01T00:35:00Z"
    previous["plan"]["valid_until"] = "2026-09-01T02:15:00Z"
    candles = rows()
    candles[0]["at"] = "2026-09-01T00:15:00Z"
    candles[1]["at"] = "2026-09-01T01:15:00Z"
    assert ac.evaluate_outcome(previous, {"rows": candles}, "2026-09-01T02:15:00Z") is None


def test_m_next_bar_rule_is_not_reinterpreted_as_any_later_bar():
    from tests.test_article_continuity_outcomes import m, candle
    previous = m()
    previous["story"]["scenarios"]["long"]["sl"] = 70
    candles = [candle(0, 111, 110, 112), candle(1, 112, 111, 113),
               candle(2, 89, 88, 90)]
    result = ac.evaluate_outcome(previous, {"rows": candles}, "2026-09-01T03:00:00+07:00")
    assert result is None or "ยกเลิก" not in result.replace("อีกฝั่งถูกยกเลิก", "")


def render(root, asset="xauusd", *, contract="test/v1", cutoff="2026-09-02T08:00:00+07:00"):
    return ac.enrich("# บททดสอบ\n\nบทนำ\n\n## กราฟ\n\nกราฟและระดับราคา\n",
        asset=asset, style="D", contract=contract, cutoff=cutoff,
        evidence={"story": {"zones": [100]}}, store_root=root)


def test_final_section_cannot_contain_unrecorded_factual_claim(tmp_path):
    markdown, record = render(tmp_path)
    changed = markdown.replace(ac.QUESTION, ac.QUESTION + "\n\nราคาครั้งก่อนทำกำไรแน่นอน 999999 บาท")
    with pytest.raises(ValueError):
        ac.validate_sections(changed, record)


def test_cached_record_must_match_requested_candidate_identity(tmp_path):
    markdown, expected = render(tmp_path)
    other_markdown, other = render(tmp_path, asset="wtiusd")
    ac.save_candidate(tmp_path, expected, markdown)
    # A valid different record copied into the requested cache slot must not replay.
    slot = tmp_path / "candidates" / (expected["revision"] + ".json")
    slot.write_text(json.dumps(other, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        render(tmp_path)


def test_record_integrity_binds_revision_to_identity(tmp_path):
    markdown, record = render(tmp_path)
    forged = deepcopy(record)
    forged["asset"] = "wtiusd"
    forged["record_hash"] = ac.digest({k: v for k, v in forged.items() if k != "record_hash"})
    with pytest.raises(ValueError):
        ac.save_candidate(tmp_path, forged, markdown)


def test_contract_reset_keeps_reader_question_history(tmp_path):
    # Repeated compatibility changes reset factual baseline, but readers still
    # saw each previous question in this asset/style/locale stream.
    records = []
    for day in range(1, 14):
        cutoff = f"2026-09-{day:02}T08:00:00+07:00"
        markdown, record = render(tmp_path, contract=f"test/v{day}", cutoff=cutoff)
        assert record["baseline_revision"] is None
        assert record["semantic_key"] not in {r["semantic_key"] for r in records[-10:]}
        assert record["question_family"] not in {r["question_family"] for r in records[-3:]}
        ac.save_candidate(tmp_path, record, markdown)
        ac.confirm_publication(tmp_path, record["revision"], article_hash=record["article_hash"],
            evidence_hash=record["evidence_hash"], published_at=cutoff,
            receipt="SYNTHETIC TEST ONLY", confirmed_by="qq-test")
        records.append(record)
