"""Daily delivery layer for BTCUSD Style E+ (H1 context + M15 execution)."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from tools import (intraday_bars, publish_layout, style_e_plus_pipeline,
                   style_e_plus_renderer, wcb_source)

ASSET = style_e_plus_pipeline.ASSET
FOLDER = "E+-แผนเทรด-H1-M15"
INTERNAL_FOLDER = "style-e-plus"


class DailyEPlusError(RuntimeError):
    """The E+ daily set could not be delivered as one verified unit."""


def prepare_isolated(*, asset: str, session_cutoff: datetime,
                     cutoff_at: str | None = None,
                     fetcher=intraday_bars.fetch_rows) -> dict:
    """Prepare the v5/DC-T daily package in memory for Gate V/Q only.

    This seam deliberately has no filesystem, network, scheduler or publish
    side effect.  The existing ``run`` path remains the production B100 path
    until a separate Promote/Production-output Gate is approved.
    """
    moment = _moment(cutoff_at)
    return style_e_plus_pipeline.prepare_daily_conditional(
        asset=asset, session_cutoff=session_cutoff, fetcher=fetcher, now=moment)


def write_versioned_package(*, prepared: dict, output_folder: Path,
                            renderer=None) -> dict:
    """Atomically write one self-contained DC-T package without overwrite.

    ``prepared`` must come from ``prepare_daily_conditional``.  This function
    performs no fetch and never replaces an existing path.
    """
    target = Path(output_folder).resolve()
    if target.exists():
        raise DailyEPlusError(f"versioned output มีอยู่แล้ว ห้าม overwrite: {target}")
    story = prepared.get("story") or {}
    if story.get("schema") != "style-e-plus-story/v5":
        raise DailyEPlusError("versioned package รับเฉพาะ DC-T story v5")
    conditional = story.get("daily_conditional") or {}
    if conditional.get("contract") != "DC-T/v1":
        raise DailyEPlusError("versioned package ขาด DC-T/v1 contract")
    if not (prepared.get("qa") or {}).get("ok"):
        raise DailyEPlusError("versioned package รับเฉพาะ prepared QA PASS")

    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".style-e-plus-dct-", dir=target.parent))
    try:
        (stage / "btcusd.md").write_text(prepared["markdown"], encoding="utf-8")
        image_results = _render(prepared, stage, renderer=renderer)
        internal = stage / "internal"
        internal.mkdir()
        internal_files = {
            "story.json": story,
            "qa.json": prepared["qa"],
            "source-evidence.json": prepared["source_evidence"],
            "source-snapshot.json": prepared["source_snapshot"],
            "conditional-artifact.json": prepared["conditional_artifact"],
        }
        for name, payload in internal_files.items():
            (internal / name).write_text(_json_text(payload), encoding="utf-8")
        public_names = {"btcusd.md", *story["images"].values()}
        manifest = {
            "schema": "style-e-plus-daily/v3",
            "asset": ASSET,
            "style": "E+",
            "story_schema": story["schema"],
            "source_snapshot_schema": prepared["source_snapshot"]["schema"],
            "session_id": story["session_id"],
            "state": story["state"],
            "conditional_status": conditional["status"],
            "strict_projection_sha256": conditional["strict_projection_hash"],
            "conditional_sha256": conditional["sha256"],
            "policies": ["adaptive-stop-b100-no-fallback",
                         "daily-conditional-dc-t-v1"],
            "manual_only": True,
            "network_authority": "none",
            "files": {
                name: {"sha256": _sha256(stage / name),
                       "bytes": (stage / name).stat().st_size}
                for name in sorted(public_names)
            } | {
                f"internal/{name}": {"sha256": _sha256(internal / name),
                                      "bytes": (internal / name).stat().st_size}
                for name in sorted(internal_files)
            },
            "images": deepcopy(image_results),
        }
        (internal / "manifest.json").write_text(_json_text(manifest), encoding="utf-8")
        os.replace(stage, target)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return {
        "status": "pass", "written": True, "network_used": False,
        "directory": str(target), "article": str(target / "btcusd.md"),
        "images": [str(target / story["images"][role]) for role in ("h1", "m15")],
        "manifest": str(target / "internal" / "manifest.json"),
        "conditional_status": conditional["status"],
    }


def _json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _moment(cutoff_at: str | None) -> datetime:
    if cutoff_at is None:
        return datetime.now(tz=timezone.utc)
    try:
        value = datetime.fromisoformat(str(cutoff_at).replace("Z", "+00:00"))
    except ValueError as exc:
        raise DailyEPlusError("cutoff_at ต้องเป็น ISO-8601") from exc
    if value.tzinfo is None:
        raise DailyEPlusError("cutoff_at ต้องมี timezone")
    return value


def _clear_stale(folder: Path, names: set[str]) -> list[str]:
    """Remove only BTCUSD E+ artifacts for the selected output day."""
    removed: list[str] = []
    if not folder.exists():
        return removed
    patterns = ("btcusd.md", "btcusd-eplus-h1-context-*",
                "btcusd-eplus-m15-execution-*")
    targets = {path for pattern in patterns for path in folder.glob(pattern)}
    for path in sorted(targets):
        if path.is_file() and path.name not in names:
            path.unlink()
            removed.append(path.name)
    return removed


def _render(prepared: dict, stage: Path, renderer=None) -> dict[str, dict]:
    story = prepared["story"]
    module = renderer or style_e_plus_renderer
    paths = {role: stage / name for role, name in story["images"].items()}
    raw_results = {
        "h1": module.render_context(story, prepared["h1_rows"], paths["h1"]),
        "m15": module.render_execution(story, prepared["m15_rows"], paths["m15"]),
    }
    results: dict[str, dict] = {}
    for role, path in paths.items():
        if not path.is_file() or path.stat().st_size <= 0:
            raise DailyEPlusError(f"renderer ไม่ได้สร้างภาพ {role.upper()} ที่สมบูรณ์")
        if not isinstance(raw_results[role], dict):
            raise DailyEPlusError("renderer result ต้องเป็น object")
        results[role] = deepcopy(raw_results[role])
        results[role]["path"] = story["images"][role]
    return results


def run(*, asset: str, publish_root: Path = Path("../output"),
        cutoff_at: str | None = None, fetcher=intraday_bars.fetch_rows,
        renderer=None, work_root: Path = Path("work/build")) -> dict:
    """Build then atomically place the public set and its internal evidence."""
    if asset != ASSET:
        raise DailyEPlusError("Style E+ Daily รองรับเฉพาะ btcusd")
    moment = _moment(cutoff_at)
    publish_date = moment.astimezone(wcb_source.BANGKOK).strftime("%Y-%m-%d")
    day_name = publish_layout.day_folder(moment.isoformat())
    output_folder = Path(publish_root) / day_name / FOLDER
    internal_folder = (Path(work_root) / day_name / asset / "internal" /
                       INTERNAL_FOLDER)

    prepared = style_e_plus_pipeline.prepare(
        asset=asset, fetcher=fetcher, now=moment, publish_date=publish_date)
    story = prepared["story"]
    names = {"btcusd.md", story["images"]["h1"], story["images"]["m15"]}

    output_parent = output_folder.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".style-e-plus-daily-", dir=output_parent))
    try:
        (stage / "btcusd.md").write_text(prepared["markdown"], encoding="utf-8")
        image_results = _render(prepared, stage, renderer=renderer)
        file_records = {
            name: {"sha256": _sha256(stage / name), "bytes": (stage / name).stat().st_size}
            for name in sorted(names)
        }
        internal_stage = stage / "internal"
        internal_stage.mkdir()
        internal_files = {
            "story.json": story,
            "qa.json": prepared["qa"],
            "source-evidence.json": prepared["source_evidence"],
            "source-snapshot.json": prepared["source_snapshot"],
        }
        for name, payload in internal_files.items():
            (internal_stage / name).write_text(_json_text(payload), encoding="utf-8")
        manifest = {
            "schema": "style-e-plus-daily/v2", "asset": asset,
            "style": "E+", "day": day_name, "publish_date": publish_date,
            "state": story["state"], "files": file_records,
            "story_schema": story["schema"],
            "source_snapshot_schema": style_e_plus_pipeline.SNAPSHOT_SCHEMA,
            "adaptive_context_sha256": story["adaptive_context"]["sha256"],
            "policy": "adaptive-stop-b100-no-fallback",
            "manual_only": True,
            "images": deepcopy(image_results),
        }
        (internal_stage / "manifest.json").write_text(
            _json_text(manifest), encoding="utf-8")

        output_folder.mkdir(parents=True, exist_ok=True)
        removed = _clear_stale(output_folder, names)
        for name in sorted(names):
            os.replace(stage / name, output_folder / name)

        internal_folder.parent.mkdir(parents=True, exist_ok=True)
        old_internal = internal_folder.with_name(f".{INTERNAL_FOLDER}-old")
        if old_internal.exists():
            shutil.rmtree(old_internal)
        if internal_folder.exists():
            os.replace(internal_folder, old_internal)
        os.replace(internal_stage, internal_folder)
        if old_internal.exists():
            shutil.rmtree(old_internal)
    except Exception:
        # Public files are staged before placement; a rendering/QA failure leaves
        # the previous daily set untouched.
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    return {
        "asset": asset, "style": "E+", "variant": "e_plus_h1_m15",
        "status": "pass", "day": day_name, "directory": str(output_folder),
        "article": str(output_folder / "btcusd.md"),
        "images": [str(output_folder / story["images"][role]) for role in ("h1", "m15")],
        "char_count": prepared["qa"]["char_count"], "findings": [],
        "state": story["state"], "internal_directory": str(internal_folder),
        "removed_stale": removed,
    }


__all__ = ["ASSET", "DailyEPlusError", "FOLDER", "prepare_isolated",
           "write_versioned_package", "run"]
