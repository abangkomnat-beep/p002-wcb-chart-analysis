import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from tools import article_continuity as c


def render(root, day=1, **kwargs):
    return c.enrich("## ภาพวันนี้\n\nบทนำ\n\nกรอบราคา\n", asset="xauusd", style="D", contract="v1", cutoff=f"2026-09-{day:02}T10:00:00+07:00", evidence={"story": {"zones": [100]}}, store_root=root, **kwargs)


def publish(root, record):
    c.save_candidate(root, record, record["markdown"])
    c.confirm_publication(root, record["revision"], article_hash=record["article_hash"], evidence_hash=record["evidence_hash"], published_at=record["cutoff"], receipt="manual:test-record", confirmed_by="fixture-user")


def deliver(root, records, day, selected_at=None):
    target = root / "handoff"
    inventories = []
    style_ids = {"D": "d_chart_story", "E": "e_indicator",
                 "L": "l_forex_daily_plan", "M": "m_btcusd_h1_visual_daily"}
    for index, record in enumerate(records):
        folder = f"lane-{index}"
        name = f"{record['asset']}.md"
        destination = target / folder
        destination.mkdir(parents=True, exist_ok=True)
        destination.joinpath(name).write_text(record["markdown"], encoding="utf-8")
        c.save_candidate(root, record, record["markdown"])
        inventories.append({"id": folder, "asset": "btc" if record["asset"] == "btcusd" else record["asset"],
                            "style": style_ids[record["style"]], "status": "ready",
                            "destination_folder": folder, "article_name": name})
    report = {"status": "PASS", "article_date": day,
              "lanes": [{"id": i["id"], "asset": i["asset"]} for i in inventories]}
    return c.record_selected_delivery(root, target_root=target, inventories=inventories,
                                      selection_report=report, article_date=day,
                                      selected_at=selected_at or f"{day}T12:00:00+07:00")


def test_output_and_draft_do_not_prove_publication(tmp_path):
    article, record = render(tmp_path)
    c.save_candidate(tmp_path, record, article)
    next_article, next_record = render(tmp_path, 2)
    assert c.UPDATE not in next_article
    assert next_record["baseline_revision"] is None
    assert list((tmp_path / "published").glob("*")) == []


def test_layout_representation_binds_canonical_bytes_to_immutable_parent(tmp_path):
    legacy = "## ภาพวันนี้\n\n![แผน](legacy-plan.webp)\n\nบทนำ\n"
    article, parent = c.enrich(
        legacy, asset="xauusd", style="E", contract="v1",
        cutoff="2026-09-08T10:00:00+07:00", evidence={"story": {"zones": [100]}},
        store_root=tmp_path)
    c.save_candidate(tmp_path, parent, article)
    canonical = article.replace("legacy-plan.webp", "P002-20260908-TH-E-XAUUSD-img02-h1-trade-plan.webp")
    bound = c.bind_layout_representation(
        tmp_path, parent, canonical,
        article_name="P002-20260908-TH-E-XAUUSD-article.md")
    assert c._verified(parent)
    assert c._verified(bound)
    assert bound["article_hash"] == c.digest(canonical)
    assert bound["representation"]["parent_revision"] == parent["revision"]
    assert bound["revision"] != parent["revision"]
    assert c.layout_equivalent(article, canonical)


def test_verified_prior_and_immutable_rerun(tmp_path):
    article, record = render(tmp_path)
    publish(tmp_path, record)
    current, candidate = render(tmp_path, 2)
    assert "01/09/2026" in current
    assert "ยังตรงกับรอบก่อน" in current
    assert current.index(c.UPDATE) > current.index("## ภาพวันนี้")
    assert current.index(c.QUESTION) > current.index("## ภาพวันนี้")
    c.save_candidate(tmp_path, candidate, current)
    assert render(tmp_path, 2) == (current, candidate)


def test_selected_delivery_becomes_automatic_baseline_without_publication_claim(tmp_path):
    first, record = render(tmp_path)
    result = deliver(tmp_path, [record], "2026-09-01")
    assert result["status"] == "recorded"
    current, candidate = render(tmp_path, 2)
    assert "จากแผนครั้งก่อนวันที่ 01/09/2026" in current
    assert candidate["baseline_revision"] == record["revision"]
    entry = json.loads(next((tmp_path / "deliveries").glob("*/*.json")).read_text(encoding="utf-8"))
    assert entry["delivery"]["receipt_type"] == "selected_delivery"
    assert entry["delivery"]["publication_verified"] is False
    assert not (tmp_path / "published").exists()


def test_delivery_batch_supports_all_approved_styles_and_is_idempotent(tmp_path):
    records = []
    for asset, style in [("xauusd", "D"), ("xauusd", "E"), ("usdcad", "L"), ("btcusd", "M")]:
        article, record = c.enrich(
            f"# {asset} {style}\n\n## ภาพวันนี้\n\nระดับราคา\n", asset=asset,
            style=style, contract=f"{style}/v1", cutoff="2026-09-01T10:00:00+07:00",
            evidence={"story": {"zones": [100]}}, store_root=tmp_path)
        records.append(record)
    first = deliver(tmp_path, records, "2026-09-01")
    second = deliver(tmp_path, records, "2026-09-01", "2026-09-01T13:00:00+07:00")
    assert len(first["revisions"]) == 4
    assert second["idempotent"] is True
    assert second["batch_id"] == first["batch_id"]


def test_concurrent_identical_delivery_is_one_safe_batch(tmp_path):
    _, record = render(tmp_path)
    target = tmp_path / "handoff" / "lane"
    target.mkdir(parents=True)
    target.joinpath("xauusd.md").write_text(record["markdown"], encoding="utf-8")
    c.save_candidate(tmp_path, record, record["markdown"])
    inventory = [{"id": "lane", "asset": "xauusd", "style": "d_chart_story",
                  "status": "ready", "destination_folder": "lane",
                  "article_name": "xauusd.md"}]
    def write(index):
        return c.record_selected_delivery(
            tmp_path, target_root=tmp_path / "handoff", inventories=inventory,
            selection_report={"status": "PASS"}, article_date="2026-09-01",
            selected_at=f"2026-09-01T12:00:{index:02}+07:00")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(write, range(8)))
    assert len({item["batch_id"] for item in results}) == 1
    assert len(list((tmp_path / "delivery_batches").glob("*.json"))) == 1


def test_unfinalized_or_mismatched_delivery_never_becomes_baseline(tmp_path):
    _, record = render(tmp_path)
    deliver(tmp_path, [record], "2026-09-01")
    manifest = next((tmp_path / "delivery_batches").glob("*.json"))
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["finalized"] = False
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    assert render(tmp_path, 2)[1]["baseline_revision"] is None


def test_same_day_reruns_do_not_become_same_day_baseline(tmp_path):
    _, first = render(tmp_path)
    deliver(tmp_path, [first], "2026-09-01")
    for hour in range(11, 20):
        article, rerun = c.enrich(
            f"# กราฟใหม่ {hour}\n\n## ภาพวันนี้\n\nกรอบราคา {hour}\n", asset="xauusd", style="D",
            contract="v1", cutoff=f"2026-09-01T{hour}:00:00+07:00",
            evidence={"story": {"zones": [hour]}}, store_root=tmp_path)
        assert rerun["baseline_revision"] is None
        deliver(tmp_path, [rerun], "2026-09-01", f"2026-09-01T{hour}:30:00+07:00")
    next_day = render(tmp_path, 2)[1]
    assert next_day["baseline_revision"] == rerun["revision"]


def test_partial_selection_cannot_finalize_delivery(tmp_path):
    _, record = render(tmp_path)
    c.save_candidate(tmp_path, record, record["markdown"])
    with pytest.raises(ValueError):
        c.record_selected_delivery(
            tmp_path, target_root=tmp_path, article_date="2026-09-01",
            selection_report={"status": "BLOCK_PARTIAL"},
            inventories=[{"status": "failed"}])
    assert not (tmp_path / "delivery_batches").exists()


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
