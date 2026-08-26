from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import style_e_plus_daily


def _prepared() -> dict:
    story = {
        "asset": "btcusd", "style": "e_plus_h1_m15", "state": "WAIT_TRIGGER",
        "publish_date": "2026-08-25",
        "images": {
            "h1": "btcusd-eplus-h1-context-2026-08-25.webp",
            "m15": "btcusd-eplus-m15-execution-2026-08-25.webp",
        },
    }
    return {
        "story": story, "markdown": "---\nauthor_slug: world-class-broker-team\n---\n",
        "qa": {"ok": True, "status": "pass", "char_count": 1800},
        "source_evidence": {"schema": "evidence"},
        "source_snapshot": {"schema": "snapshot"},
        "h1_rows": [{"close": 1}], "m15_rows": [{"close": 1}],
    }


def _renderer(*, fail_m15: bool = False):
    def context(_story, _rows, path):
        path.write_bytes(b"RIFF-h1")
        return {"path": str(path), "size_bytes": path.stat().st_size}

    def execution(_story, _rows, path):
        if fail_m15:
            raise RuntimeError("m15 fixture failed")
        path.write_bytes(b"RIFF-m15")
        return {"path": str(path), "size_bytes": path.stat().st_size}

    return SimpleNamespace(render_context=context, render_execution=execution)


def test_daily_places_three_public_files_and_internal_evidence_atomically(tmp_path, monkeypatch):
    monkeypatch.setattr(style_e_plus_daily.style_e_plus_pipeline, "prepare",
                        lambda **_kwargs: _prepared())
    result = style_e_plus_daily.run(
        asset="btcusd", publish_root=tmp_path / "output",
        work_root=tmp_path / "work", cutoff_at="2026-08-25T03:00:00+00:00",
        renderer=_renderer())

    public = Path(result["directory"])
    assert {path.name for path in public.iterdir()} == {
        "btcusd.md", "btcusd-eplus-h1-context-2026-08-25.webp",
        "btcusd-eplus-m15-execution-2026-08-25.webp",
    }
    internal = Path(result["internal_directory"])
    assert {path.name for path in internal.iterdir()} == {
        "story.json", "qa.json", "source-evidence.json",
        "source-snapshot.json", "manifest.json",
    }
    manifest = json.loads((internal / "manifest.json").read_text(encoding="utf-8"))
    assert {record["path"] for record in manifest["images"].values()} == {
        "btcusd-eplus-h1-context-2026-08-25.webp",
        "btcusd-eplus-m15-execution-2026-08-25.webp",
    }


def test_daily_renderer_failure_leaves_previous_public_set_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(style_e_plus_daily.style_e_plus_pipeline, "prepare",
                        lambda **_kwargs: _prepared())
    public = tmp_path / "output" / "25-08-2026" / style_e_plus_daily.FOLDER
    public.mkdir(parents=True)
    (public / "btcusd.md").write_text("previous", encoding="utf-8")

    with pytest.raises(RuntimeError, match="m15 fixture failed"):
        style_e_plus_daily.run(
            asset="btcusd", publish_root=tmp_path / "output",
            work_root=tmp_path / "work", cutoff_at="2026-08-25T03:00:00+00:00",
            renderer=_renderer(fail_m15=True))
    assert (public / "btcusd.md").read_text(encoding="utf-8") == "previous"
    assert not list(public.glob("*.webp"))
