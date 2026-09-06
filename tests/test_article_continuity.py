import json
import pytest
from tools import article_continuity as c


def render(root, day=1, **kwargs):
    return c.enrich("# กราฟ\n\nบทนำ\n\n## ภาพวันนี้\n\nกรอบราคา\n", asset="xauusd", style="D", contract="v1", cutoff=f"2026-09-{day:02}T10:00:00+07:00", evidence={"story": {"zones": [100]}}, store_root=root, **kwargs)


def publish(root, record):
    c.save_candidate(root, record, record["markdown"])
    c.confirm_publication(root, record["revision"], article_hash=record["article_hash"], evidence_hash=record["evidence_hash"], published_at=record["cutoff"], receipt="manual:test-record", confirmed_by="fixture-user")


def test_output_and_draft_do_not_prove_publication(tmp_path):
    article, record = render(tmp_path)
    c.save_candidate(tmp_path, record, article)
    next_article, next_record = render(tmp_path, 2)
    assert c.UPDATE not in next_article
    assert next_record["baseline_revision"] is None
    assert list((tmp_path / "published").glob("*")) == []


def test_verified_prior_and_immutable_rerun(tmp_path):
    article, record = render(tmp_path)
    publish(tmp_path, record)
    current, candidate = render(tmp_path, 2)
    assert "01/09/2026" in current
    assert "ยังตรงกับรอบก่อน" in current
    assert current.index(c.UPDATE) < current.index("## ภาพวันนี้")
    assert current.index(c.QUESTION) > current.index("## ภาพวันนี้")
    c.save_candidate(tmp_path, candidate, current)
    assert render(tmp_path, 2) == (current, candidate)


def test_reject_confirmation_mismatch_and_qc_failure(tmp_path):
    article, record = render(tmp_path)
    with pytest.raises(ValueError):
        c.save_candidate(tmp_path, record, article, qc_pass=False)
    c.save_candidate(tmp_path, record, article)
    with pytest.raises(ValueError):
        c.confirm_publication(tmp_path, record["revision"], article_hash="wrong", evidence_hash=record["evidence_hash"], published_at=record["cutoff"], receipt="test", confirmed_by="user")


def test_failed_preview_does_not_consume_history(tmp_path):
    first, record = render(tmp_path)
    assert render(tmp_path) == (first, record)
    assert not tmp_path.joinpath("published").exists()


def test_question_semantics_and_family_rotation(tmp_path):
    records = []
    for day in range(1, 22):
        _, record = render(tmp_path, day)
        assert record["semantic_key"] not in {r["semantic_key"] for r in records[-10:]}
        assert record["question_family"] not in {r["question_family"] for r in records[-3:]}
        publish(tmp_path, record)
        records.append(record)


def test_tampered_baseline_is_ignored(tmp_path):
    _, record = render(tmp_path)
    publish(tmp_path, record)
    path = tmp_path / "published" / (record["revision"] + ".json")
    entry = json.loads(path.read_text(encoding="utf-8"))
    entry["record"]["evidence"]["story"]["zones"] = [999]
    path.write_text(json.dumps(entry))
    assert render(tmp_path, 2)[1]["baseline_revision"] is None


def test_confirm_does_not_allow_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        c.confirm_publication(tmp_path, "../x", article_hash="", evidence_hash="", published_at="2026-09-01T00:00:00Z", receipt="yes", confirmed_by="user")


def prior_plan():
    return {"plan": {"cutoff_at": "2026-09-01T10:00:00Z", "valid_until": "2026-09-01T13:00:00Z", "current_close": 99,
        "plans": [{"side": "BUY", "trigger": {"condition": "closed H1 strict cross from latest closed close", "value": 100}, "invalidation": {"condition": "closed H1 reaches canonical SL", "value": 95}, "stop_loss": 95, "take_profit": [110]}]}}


def candles():
    return [{"at": f"2026-09-01T{hour}:00:00Z", "open": close, "close": close, "high": high, "low": low}
            for hour, close, high, low in [(10, 101, 112, 93), (11, 102, 105, 98), (12, 105, 108, 101)]]


def test_strict_cross_ignores_pre_confirmation_candle_extremes():
    assert "ครบกำหนดอายุ" in c.evaluate_outcome(prior_plan(), {"rows": candles()}, "2026-09-01T13:00:00Z")


def test_ambiguous_stop_target_is_not_success():
    rows = candles()
    rows[1].update(high=112, low=93)
    assert "ลำดับ" in c.evaluate_outcome(prior_plan(), {"rows": rows}, "2026-09-01T13:00:00Z")


def test_gap_and_retest_are_not_untriggered():
    assert c.evaluate_outcome(prior_plan(), {"rows": candles()[1:]}, "2026-09-01T13:00:00Z") is None
    plan = prior_plan()
    plan["plan"]["plans"][0]["trigger"]["condition"] += " retest"
    assert c.evaluate_outcome(plan, {"rows": candles()}, "2026-09-01T13:00:00Z") is None


def test_future_and_post_expiry_candles_do_not_resolve_outcome():
    rows = candles() + [{"at": "2026-09-01T13:00:00Z", "close": 115, "high": 116, "low": 105}]
    assert "ครบกำหนดอายุ" in c.evaluate_outcome(prior_plan(), {"rows": rows}, "2026-09-01T14:00:00Z")
