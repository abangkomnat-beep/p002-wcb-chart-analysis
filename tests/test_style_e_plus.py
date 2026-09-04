from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import intraday_bars
from tools import style_e_plus_pipeline as pipeline
from tools import style_e_plus_story as story_module
from tools import style_e_plus_writer as writer


NOW = datetime(2026, 1, 11, 13, 30, tzinfo=timezone.utc)


def h1_rows(count: int = 260) -> list[dict]:
    rows, price = [], 70_000.0
    start = datetime(2026, 1, 1)
    for index in range(count):
        delta = (20 + index * 0.9) * (1 if index % 3 else -0.25)
        opened, closed = price, price + delta
        spread = 60 + index * 1.2
        at = start + timedelta(hours=index)
        rows.append({
            "date": at.strftime("%Y-%m-%d"), "at": at.strftime("%Y-%m-%d %H:%M:%S"),
            "open": opened, "high": max(opened, closed) + spread,
            "low": min(opened, closed) - spread, "close": closed, "forming": False,
        })
        price = closed
    return rows


def m15_rows(count: int = 260) -> list[dict]:
    rows, price = [], 80_000.0
    start = datetime(2026, 1, 8)
    for index in range(count):
        delta = ((index % 8) - 3.5) * 8.0
        opened, closed = price, price + delta
        spread = 55.0 + index % 9
        at = start + timedelta(minutes=15 * index)
        rows.append({
            "date": at.strftime("%Y-%m-%d"), "at": at.strftime("%Y-%m-%d %H:%M:%S"),
            "open": opened, "high": max(opened, closed) + spread,
            "low": min(opened, closed) - spread, "close": closed, "forming": False,
        })
        price = closed
    # B100 acceptance fixture: a confirmed swing plus enough opposing
    # Donchian space in decision-22..decision-1 for the normal story path.
    base = count - 23
    for index, low in zip((base + 12, base + 13, base + 14,
                           base + 15, base + 16),
                          (79_900.0, 79_850.0, 79_800.0,
                           79_850.0, 79_900.0)):
        rows[index]["low"] = low
    rows[base + 5]["high"] = 80_550.0
    return rows


def make_story(h1=None, m15=None):
    h1, m15 = h1 or h1_rows(), m15 or m15_rows()
    return story_module.build(
        h1, m15,
        candle_basis=intraday_bars.basis_for(
            "btcusd", h1[-1]["at"], timeframe="1h", now=NOW),
        m15_candle_basis=intraday_bars.basis_for(
            "btcusd", m15[-1]["at"], timeframe="15min", now=NOW),
        publish_date="2026-08-25", now=NOW)


def test_story_uses_h1_bias_but_m15_owns_every_trade_level():
    story = make_story()
    assert story["schema"] == "style-e-plus-story/v4"
    assert story["side"] == "buy"
    assert story["timeframes"] == {"context": "1h", "execution": "15min"}
    plan = story["plan"]
    assert plan and plan["timeframe"] == "15min"
    atr = story["m15"]["indicators"]["atr"]["value"]
    ema20 = story["m15"]["indicators"]["ema20"]
    assert plan["trigger"] == pytest.approx(ema20)
    assert plan["entry_zone_low"] == pytest.approx(ema20 - 0.25 * atr)
    assert plan["entry_zone_high"] == pytest.approx(ema20 + 0.25 * atr)
    assert plan["variant"] == "B"
    assert 2.0 <= plan["risk_atr"] <= 3.0
    assert plan["risk"] == pytest.approx(plan["risk_atr"] * atr)
    assert plan["sizing_basis"] == "baseline_reference_size"
    assert 0.50 <= plan["sizing_multiplier"] <= 0.75
    assert plan["normalized_risk_ratio"] <= 1.0 + 1e-12
    assert plan["pre_entry_invalidation_close"] == pytest.approx(
        plan["protective_stop"]["price"])
    assert plan["protective_stop"]["price"] == pytest.approx(
        plan["pre_entry_invalidation_close"])
    assert plan["protective_stop"]["active"] is False
    assert (plan["tp1"] - plan["disadvantaged_entry"]) / plan["risk"] == pytest.approx(1.5)
    assert (plan["tp2"] - plan["disadvantaged_entry"]) / plan["risk"] == pytest.approx(2.0)
    assert story["adaptive_context"]["count"] == 23
    assert set(story["images"]) == {"h1", "m15"}


def test_package_readme_describes_plan_and_no_plan_images_truthfully():
    planned = make_story()
    planned_readme = pipeline._readme(planned)
    assert "ภาพ M15 แสดง Entry Zone" in planned_readme

    no_plan = dict(planned, state="NO_PLAN", side=None, plan=None)
    no_plan_readme = pipeline._readme(no_plan)
    assert "ภาพ M15 แสดงราคาปิดและ EMA20 โดยไม่มีระดับแผนเทรด" in no_plan_readme
    assert "ภาพ M15 แสดง Entry Zone" not in no_plan_readme


def test_story_fails_closed_for_short_or_forming_data_on_either_timeframe():
    h1, m15 = h1_rows(), m15_rows()
    with pytest.raises(story_module.StoryUnavailable, match="240"):
        make_story(h1=h1[:239], m15=m15)
    m15[-1]["forming"] = True
    with pytest.raises(story_module.StoryUnavailable, match="forming"):
        make_story(h1=h1, m15=m15)


def test_writer_is_deterministic_uses_m15_plan_and_two_images():
    story = make_story()
    markdown = writer.render_article(story)
    result = writer.validate(markdown, story, now=NOW)
    assert result["ok"] and result["char_count"] >= 1000
    assert 'author_slug: "worldclassbroker-team"' in markdown
    excerpt_line = next(line for line in markdown.splitlines() if line.startswith("excerpt: "))
    assert 120 <= len(excerpt_line.removeprefix('excerpt: "').removesuffix('"')) <= 160
    assert "## แผน M15 วันนี้: รอยืนยันจุดเข้า (WAIT_TRIGGER)" in markdown
    assert "## ภาพรวมตลาดและกรอบ H1 (H1 Framework)" in markdown
    assert "M15 Trigger" in markdown
    assert "เส้นทางตามเงื่อนไข" not in markdown
    assert "ไม่ใช่ราคาจริง" not in markdown
    assert markdown.count("![ภาพที่ ") == 2
    assert all(markdown.count(f"]({name})") == 1 for name in story["images"].values())
    assert not any(token in markdown for token in ("📌", "📈", "📉"))
    changed = markdown.replace(f"{story['plan']['trigger']:,.2f}", "90,999.99", 1)
    result = writer.validate(changed, story, now=NOW)
    assert not result["ok"]
    assert any(item["rule"] == "deterministic_copy" for item in result["findings"])


def dual_fetcher(h1, m15, *, live=False):
    def fetcher(asset, *, timeframe, outputsize):
        assert asset == "btcusd" and outputsize == 500
        meta = {"asset": asset, "timeframe": timeframe}
        if live:
            meta["timezone_check"] = {"status": "match"}
        return meta, (h1 if timeframe == "1h" else m15), f"fixture:{timeframe}"
    return fetcher


def test_pipeline_without_confirmation_fetches_both_and_writes_nothing(tmp_path):
    called = {"context": False, "execution": False}
    renderer = SimpleNamespace(
        render_context=lambda *_: called.__setitem__("context", True),
        render_execution=lambda *_: called.__setitem__("execution", True),
    )
    output_root = tmp_path / "not-created"
    result = pipeline.run(
        asset="btcusd", output_root=output_root, confirm_write=False,
        fetcher=dual_fetcher(h1_rows(), m15_rows()), now=NOW,
        publish_date="2026-08-25", renderer=renderer)
    assert result["status"] == "pass" and result["written"] is False
    assert not output_root.exists()
    assert called == {"context": False, "execution": False}
    assert set(result["image_names"]) == {"h1", "m15"}


def test_pipeline_confirmed_places_complete_atomic_two_image_package(tmp_path):
    h1, m15 = h1_rows(), m15_rows()

    def render_context(_story, source_rows, output_path):
        assert source_rows == h1
        output_path.write_bytes(b"RIFF-h1-test-webp")
        return {"path": str(output_path), "size_bytes": output_path.stat().st_size,
                "metadata": {"role": "h1_context"}}

    def render_execution(_story, source_rows, output_path):
        assert source_rows == m15
        output_path.write_bytes(b"RIFF-m15-test-webp")
        return {"path": str(output_path), "size_bytes": output_path.stat().st_size,
                "metadata": {"role": "m15_execution"}}

    result = pipeline.run(
        asset="btcusd", output_root=tmp_path / "preview", confirm_write=True,
        fetcher=dual_fetcher(h1, m15), now=NOW, publish_date="2026-08-25",
        renderer=SimpleNamespace(render_context=render_context,
                                 render_execution=render_execution))
    folder = Path(result["directory"])
    assert result["written"] is True
    assert {path.name for path in folder.iterdir()} == {
        "btcusd.md", "btcusd-eplus-h1-context-2026-08-25.webp",
        "btcusd-eplus-m15-execution-2026-08-25.webp", "story.json",
        "source-evidence.json", "source-snapshot.json", "qa-report.json",
        "README.md", "manifest.json",
    }
    assert not list((tmp_path / "preview").glob(".style-e-plus-*"))


def test_pipeline_integrates_both_real_renderers_and_records_contracts(tmp_path):
    result = pipeline.run(
        asset="btcusd", output_root=tmp_path / "integrated", confirm_write=True,
        fetcher=dual_fetcher(h1_rows(), m15_rows()), now=NOW,
        publish_date="2026-08-25")
    folder = Path(result["directory"])
    qa = json.loads((folder / "qa-report.json").read_text(encoding="utf-8"))
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert qa["images"]["h1"]["metadata"]["role"] == "h1_context"
    assert qa["images"]["m15"]["metadata"]["role"] == "m15_execution"
    assert qa["images"]["h1"]["metadata"]["elements"]["trade_plan_overlay"] is False
    assert qa["images"]["m15"]["metadata"]["elements"]["trade_plan_overlay"] is True
    assert manifest["manual_only"] is True
    assert set(manifest["timeframes"].values()) == {"1h", "15min"}
    for image in result["images"].values():
        assert manifest["files"][Path(image).name]["bytes"] <= 200 * 1024


def test_pipeline_cleans_partial_package_when_second_renderer_fails(tmp_path):
    def render_context(_story, _rows, output_path):
        output_path.write_bytes(b"h1")
        return {"path": str(output_path), "size_bytes": 2, "metadata": {}}

    def render_execution(_story, _rows, output_path):
        output_path.write_bytes(b"partial")
        raise RuntimeError("renderer failed after partial write")

    root = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="partial write"):
        pipeline.run(
            asset="btcusd", output_root=root, confirm_write=True,
            fetcher=dual_fetcher(h1_rows(), m15_rows()), now=NOW,
            publish_date="2026-08-25",
            renderer=SimpleNamespace(render_context=render_context,
                                     render_execution=render_execution))
    assert root.is_dir() and list(root.iterdir()) == []


def test_invalid_asset_fails_before_fetch_or_write(tmp_path):
    called = False

    def fetcher(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("must not fetch")

    with pytest.raises(pipeline.PipelineError, match="btcusd"):
        pipeline.run(asset="xauusd", output_root=tmp_path / "x", fetcher=fetcher)
    assert called is False and not (tmp_path / "x").exists()


def test_runtime_rejects_external_fill_evidence_before_fetch_or_write(tmp_path):
    called = False

    def fetcher(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("must not fetch")

    with pytest.raises(pipeline.PipelineError, match="ยังไม่รับ fill/exit"):
        pipeline.run(
            asset="btcusd", output_root=tmp_path / "x", fetcher=fetcher,
            lifecycle_input={"event": "entry_filled", "plan_id": "untrusted"})
    assert called is False and not (tmp_path / "x").exists()


def test_pipeline_rejects_stale_m15_bar_without_writing(tmp_path):
    output_root = tmp_path / "stale"
    with pytest.raises(pipeline.PipelineError, match="15min.*stale|stale"):
        pipeline.run(
            asset="btcusd", output_root=output_root, confirm_write=True,
            fetcher=dual_fetcher(h1_rows(), m15_rows(), live=True),
            now=NOW + timedelta(hours=3), publish_date="2026-08-25")
    assert not output_root.exists()


def _byte_renderer(h1_bytes=b"RIFF-h1-reproduce", m15_bytes=b"RIFF-m15-reproduce"):
    def render_context(_story, _rows, output_path):
        output_path.write_bytes(h1_bytes)
        return {"path": str(output_path), "size_bytes": len(h1_bytes),
                "metadata": {"role": "h1_context"}}

    def render_execution(_story, _rows, output_path):
        output_path.write_bytes(m15_bytes)
        return {"path": str(output_path), "size_bytes": len(m15_bytes),
                "metadata": {"role": "m15_execution"}}

    return SimpleNamespace(render_context=render_context, render_execution=render_execution)


def test_package_paths_snapshot_and_manifest_are_self_contained(tmp_path):
    result = pipeline.run(
        asset="btcusd", output_root=tmp_path / "source", confirm_write=True,
        fetcher=dual_fetcher(h1_rows(), m15_rows()), now=NOW,
        publish_date="2026-08-25", renderer=_byte_renderer())
    folder = Path(result["directory"])
    qa = json.loads((folder / "qa-report.json").read_text(encoding="utf-8"))
    snapshot = json.loads((folder / "source-snapshot.json").read_text(encoding="utf-8"))
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

    assert qa["images"]["h1"]["path"] == "btcusd-eplus-h1-context-2026-08-25.webp"
    assert qa["images"]["m15"]["path"] == "btcusd-eplus-m15-execution-2026-08-25.webp"
    assert snapshot["schema"] == pipeline.SNAPSHOT_SCHEMA
    assert snapshot["analysis_at"] == NOW.isoformat()
    assert snapshot["volume_policy"] == "unavailable-and-forbidden"
    assert set(snapshot["timeframes"]) == {"1h", "15min"}
    for timeframe in ("1h", "15min"):
        source = snapshot["timeframes"][timeframe]
        assert source["row_count"] == len(source["rows"]) == 260
        assert all(set(row) == {"at", "open", "high", "low", "close"}
                   for row in source["rows"])
        assert not any("volume" in key.lower() for row in source["rows"] for key in row)
    assert manifest["schema"] == pipeline.MANIFEST_SCHEMA
    assert manifest["reproduce"] == pipeline.REPRODUCE_COMMAND
    assert str(tmp_path) not in manifest["reproduce"]
    assert set(manifest["files"]) == {path.name for path in folder.iterdir()
                                      if path.name != "manifest.json"}
    assert all(".style-e-plus-" not in path.read_text(encoding="utf-8", errors="ignore")
               for path in folder.glob("*.json"))
    for name, record in manifest["files"].items():
        path = folder / name
        assert record == {"sha256": pipeline._sha256(path), "bytes": path.stat().st_size}


def test_offline_reproduce_is_byte_identical_and_never_fetches(tmp_path, monkeypatch):
    renderer = _byte_renderer()
    original = pipeline.run(
        asset="btcusd", output_root=tmp_path / "original", confirm_write=True,
        fetcher=dual_fetcher(h1_rows(), m15_rows()), now=NOW,
        publish_date="2026-08-25", renderer=renderer)
    original_folder = Path(original["directory"])
    monkeypatch.setattr(
        intraday_bars, "fetch_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network forbidden")))

    replay = pipeline.reproduce(
        package=original_folder, output_root=tmp_path / "replayed",
        confirm_write=True, renderer=renderer)
    replay_folder = Path(replay["directory"])
    assert replay["network_used"] is False
    assert {path.name: path.read_bytes() for path in original_folder.iterdir()} == {
        path.name: path.read_bytes() for path in replay_folder.iterdir()}
    assert not list((tmp_path / "replayed").glob(".style-e-plus-*"))


def test_reproduce_rejects_tamper_before_any_output_write(tmp_path):
    original = pipeline.run(
        asset="btcusd", output_root=tmp_path / "original", confirm_write=True,
        fetcher=dual_fetcher(h1_rows(), m15_rows()), now=NOW,
        publish_date="2026-08-25", renderer=_byte_renderer())
    folder = Path(original["directory"])
    snapshot_path = folder / "source-snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["timeframes"]["15min"]["rows"][0]["close"] += 1.0
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    target = tmp_path / "must-not-exist"
    with pytest.raises(pipeline.PipelineError, match="hash/bytes"):
        pipeline.reproduce(
            package=folder, output_root=target, confirm_write=True,
            renderer=_byte_renderer())
    assert not target.exists()


@pytest.mark.parametrize(("mutation", "message"), [
    (lambda value: value.__setitem__("schema", "style-e-plus-source-snapshot/v999"),
     "schema"),
    (lambda value: value["timeframes"]["15min"]["candle_basis"].__setitem__(
        "timeframe", "1h"), "basis"),
    (lambda value: value["timeframes"]["15min"]["rows"].pop(0), "row count"),
])
def test_reproduce_rejects_invalid_snapshot_even_with_refreshed_file_hash(
        tmp_path, mutation, message):
    original = pipeline.run(
        asset="btcusd", output_root=tmp_path / "original", confirm_write=True,
        fetcher=dual_fetcher(h1_rows(), m15_rows()), now=NOW,
        publish_date="2026-08-25", renderer=_byte_renderer())
    folder = Path(original["directory"])
    snapshot_path = folder / "source-snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    mutation(snapshot)
    snapshot_path.write_text(pipeline._json_text(snapshot), encoding="utf-8")
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["source-snapshot.json"] = {
        "sha256": pipeline._sha256(snapshot_path), "bytes": snapshot_path.stat().st_size}
    manifest_path.write_text(pipeline._json_text(manifest), encoding="utf-8")
    target = tmp_path / "must-not-exist"
    with pytest.raises(pipeline.PipelineError, match=message):
        pipeline.reproduce(
            package=folder, output_root=target, confirm_write=True,
            renderer=_byte_renderer())
    assert not target.exists()
