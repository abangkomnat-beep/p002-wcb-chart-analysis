from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools import style_e_plus_daily, style_e_plus_pipeline, style_e_plus_renderer


UTC = timezone.utc
BANGKOK = timezone(timedelta(hours=7))
CUTOFF = datetime(2026, 8, 27, 8, 0, tzinfo=BANGKOK)


def _rows(timeframe: str) -> list[dict]:
    step = timedelta(hours=1) if timeframe == "1h" else timedelta(minutes=15)
    end = CUTOFF.replace(tzinfo=None) - step
    start = end - step * 240
    return [
        {
            "at": (start + step * index).strftime("%Y-%m-%d %H:%M:%S"),
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
            "forming": False,
        }
        for index in range(241)
    ]


def _fetch(asset: str, *, timeframe: str, outputsize: int):
    return {"provider": "offline-fixture"}, _rows(timeframe), "offline-fixture"


def test_phase6_prepare_is_additive_v5_and_has_no_write_side_effect(tmp_path):
    result = style_e_plus_pipeline.prepare_daily_conditional(
        asset="btcusd", session_cutoff=CUTOFF, fetcher=_fetch, now=CUTOFF)
    story = result["story"]
    assert story["schema"] == "style-e-plus-story/v5"
    assert story["daily_conditional"]["status"] == "ARMED"
    assert result["source_snapshot"]["schema"] == "style-e-plus-source-snapshot/v3"
    assert story["manifest"]["schema"] == "style-e-plus-manifest/v5"
    assert result["qa"]["ok"] is True
    assert list(tmp_path.iterdir()) == []


def test_phase6_daily_seam_is_in_memory_only_and_renderer_marks_watch(tmp_path):
    result = style_e_plus_daily.prepare_isolated(
        asset="btcusd", session_cutoff=CUTOFF,
        cutoff_at=CUTOFF.isoformat(), fetcher=_fetch)
    story = result["story"]
    m15 = style_e_plus_renderer.render_execution(
        story, result["m15_rows"], tmp_path / "m15.webp")
    assert result["qa"]["ok"] is True
    assert m15["metadata"]["elements"]["conditional_projection"] is True
    assert len(m15["metadata"]["labels"]["conditional_watch_levels"]) == 2
    assert not (tmp_path / "0-ขึ้นเว็บวันนี้").exists()


def test_phase6_keeps_existing_prepare_on_v4_path():
    result = style_e_plus_pipeline.prepare(
        asset="btcusd", fetcher=_fetch, now=CUTOFF,
        publish_date="2026-08-27")
    assert result["story"]["schema"] == "style-e-plus-story/v4"
    assert "daily_conditional" not in result["story"]


def test_versioned_writer_is_atomic_offline_and_refuses_overwrite(tmp_path):
    prepared = style_e_plus_daily.prepare_isolated(
        asset="btcusd", session_cutoff=CUTOFF,
        cutoff_at=CUTOFF.isoformat(), fetcher=_fetch)

    class FakeRenderer:
        @staticmethod
        def _write(output_path: Path, role: str):
            output_path.write_bytes((role + "-offline").encode("ascii"))
            return {"path": str(output_path), "size_bytes": output_path.stat().st_size,
                    "metadata": {"role": role}}

        @classmethod
        def render_context(cls, story, rows, output_path):
            return cls._write(output_path, "h1_context")

        @classmethod
        def render_execution(cls, story, rows, output_path):
            return cls._write(output_path, "m15_execution")

    target = tmp_path / "dc-t-v1-run1"
    result = style_e_plus_daily.write_versioned_package(
        prepared=prepared, output_folder=target, renderer=FakeRenderer)
    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert result["network_used"] is False
    assert manifest["schema"] == "style-e-plus-daily/v3"
    assert manifest["network_authority"] == "none"
    assert manifest["policies"] == ["adaptive-stop-b100-no-fallback",
                                     "daily-conditional-dc-t-v1"]
    assert (target / "btcusd.md").is_file()
    assert (target / "internal" / "conditional-artifact.json").is_file()
    with pytest.raises(style_e_plus_daily.DailyEPlusError, match="overwrite"):
        style_e_plus_daily.write_versioned_package(
            prepared=prepared, output_folder=target, renderer=FakeRenderer)
