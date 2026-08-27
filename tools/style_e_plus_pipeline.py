"""Standalone manual Style E+ pipeline: BTCUSD H1 context + M15 execution."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib
import inspect
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

from tools import intraday_bars, style_e_plus_story, style_e_plus_writer, wcb_source
from tools import style_e_plus_adaptive_stop as adaptive_stop

ASSET = "btcusd"
H1_TIMEFRAME = "1h"
M15_TIMEFRAME = "15min"
TIMEFRAMES = (H1_TIMEFRAME, M15_TIMEFRAME)
OUTPUTSIZE = 500
MAX_CLOSED_BAR_AGE = {H1_TIMEFRAME: timedelta(hours=2),
                      M15_TIMEFRAME: timedelta(minutes=45)}
SNAPSHOT_SCHEMA = "style-e-plus-source-snapshot/v2"
MANIFEST_SCHEMA = "style-e-plus-manifest/v4"
SNAPSHOT_SCHEMA_V3 = "style-e-plus-source-snapshot/v3"
MANIFEST_SCHEMA_V5 = "style-e-plus-manifest/v5"
REPRODUCE_COMMAND = (
    "python -m tools.style_e_plus_pipeline --reproduce-package . "
    "--output-root ./reproduced --confirm-write")
ROW_FIELDS = ("at", "open", "high", "low", "close")


class PipelineError(RuntimeError):
    """A manual E+ run failed before a complete package could be placed."""


def _json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_name(value: str, *, label: str) -> str:
    """Return a safe POSIX package-relative artifact name."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise PipelineError(f"{label}: พาธต้องเป็น POSIX package-relative")
    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) != 1 or path.name in (".", ".."):
        raise PipelineError(f"{label}: พาธต้องอยู่ใน package เท่านั้น")
    if ".style-e-plus-" in value:
        raise PipelineError(f"{label}: ห้ามอ้างโฟลเดอร์ชั่วคราว")
    return path.as_posix()


def _assert_no_unsafe_paths(value, *, label: str = "artifact") -> None:
    """Reject temporary or absolute paths in persisted JSON metadata."""
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_no_unsafe_paths(item, label=f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_unsafe_paths(item, label=f"{label}[{index}]")
    elif isinstance(value, str):
        if ".style-e-plus-" in value:
            raise PipelineError(f"{label}: พบพาธโฟลเดอร์ชั่วคราว")
        if Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
            raise PipelineError(f"{label}: พบ absolute path ใน metadata")


def _without_volume(value):
    """Copy provenance/lifecycle metadata while removing forbidden volume data."""
    if isinstance(value, dict):
        return {
            str(key): _without_volume(item)
            for key, item in value.items()
            if "volume" not in str(key).lower()
        }
    if isinstance(value, list):
        return [_without_volume(item) for item in value]
    return deepcopy(value)


def _normal_rows(rows: list[dict], *, timeframe: str) -> list[dict]:
    normalized = []
    for index, row in enumerate(rows):
        if row.get("forming"):
            raise PipelineError(f"{timeframe}: snapshot เก็บได้เฉพาะแท่งปิด")
        try:
            item = {"at": str(row["at"])}
            for field in ROW_FIELDS[1:]:
                item[field] = float(row[field])
        except (KeyError, TypeError, ValueError) as exc:
            raise PipelineError(
                f"{timeframe}: OHLC row {index} ไม่สมบูรณ์") from exc
        if not item["at"] or item["high"] < max(item["open"], item["close"]):
            raise PipelineError(f"{timeframe}: OHLC row {index} ไม่สมเหตุผล")
        if item["low"] > min(item["open"], item["close"]):
            raise PipelineError(f"{timeframe}: OHLC row {index} ไม่สมเหตุผล")
        normalized.append(item)
    return normalized


def _story_parameters() -> dict:
    names = (
        "MIN_CLOSED_BARS", "PERCENTILE_LOOKBACK", "ENTRY_HALF_WIDTH_ATR",
        )
    values = {name.lower(): getattr(style_e_plus_story, name)
              for name in names if hasattr(style_e_plus_story, name)}
    values.update({
        "source_outputsize": OUTPUTSIZE,
        "h1_freshness_max_seconds": int(MAX_CLOSED_BAR_AGE[H1_TIMEFRAME].total_seconds()),
        "m15_freshness_max_seconds": int(MAX_CLOSED_BAR_AGE[M15_TIMEFRAME].total_seconds()),
        "adaptive_policy": "adaptive-stop-b100-no-fallback",
        "adaptive_context_count": adaptive_stop.CONTEXT_COUNT,
        "pivot_left": adaptive_stop.PIVOT_LEFT,
        "pivot_right": adaptive_stop.PIVOT_RIGHT,
        "pivot_lookback_bars": adaptive_stop.PIVOT_LOOKBACK_BARS,
        "structure_buffer_atr": adaptive_stop.STRUCTURE_BUFFER_ATR,
        "risk_floor_atr": adaptive_stop.RISK_FLOOR_ATR,
        "risk_cap_atr": adaptive_stop.RISK_CAP_ATR,
        "donchian_length": adaptive_stop.DONCHIAN_LENGTH,
        "target_space_min_r": adaptive_stop.TARGET_SPACE_MIN_R,
        "tp1_r": 1.5, "tp2_r": 2.0,
        "baseline_max_risk_atr": adaptive_stop.BASELINE_MAX_RISK_ATR,
        "tolerance": adaptive_stop.TOLERANCE,
    })
    return values


def _runtime_commit() -> str:
    """Record the exact checked-out runtime revision in every v4 manifest."""
    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.STDOUT,
            text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PipelineError("ไม่สามารถระบุ runtime commit จาก git ได้") from exc
    if len(value) != 40 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise PipelineError("runtime commit ไม่ใช่ SHA-1 ที่ถูกต้อง")
    return value


def _run_id(story: dict) -> str:
    h1 = str(story["bar_at"])[11:19].replace(":", "")
    m15 = str(story["m15_bar_at"])[11:19].replace(":", "")
    return f"{story['publish_date']}-h1-{h1}-m15-{m15}"


def _validate_arguments(asset: str, output_root: Path) -> Path:
    if asset != ASSET:
        raise PipelineError("Style E+ manual รองรับเฉพาะ --asset btcusd")
    if output_root is None or not str(output_root).strip():
        raise PipelineError("ต้องระบุ --output-root ทุกครั้ง")
    resolved = Path(output_root).expanduser().resolve()
    if resolved.exists() and not resolved.is_dir():
        raise PipelineError(f"output root ไม่ใช่โฟลเดอร์: {resolved}")
    return resolved


def _validate_lifecycle_input(value: dict | None) -> None:
    if value is None or value == {}:
        return
    raise PipelineError(
        "Style E+ รุ่นนี้เป็น manual analysis และยังไม่รับ fill/exit lifecycle evidence")


def _renderer(renderer=None):
    return renderer or importlib.import_module("tools.style_e_plus_renderer")


def _closed_source(*, asset: str, timeframe: str, fetcher,
                   now: datetime | None) -> dict:
    meta, rows, source_label = fetcher(
        asset, timeframe=timeframe, outputsize=OUTPUTSIZE)
    closed_rows, basis = intraday_bars.evaluate(
        rows, asset=asset, timeframe=timeframe, now=now)
    try:
        close_at = datetime.fromisoformat(str(basis["basis_close_at"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PipelineError(f"{timeframe}: candle basis ไม่มี basis_close_at") from exc
    if close_at.tzinfo is None:
        raise PipelineError(f"{timeframe}: basis_close_at ต้องมี timezone")
    moment = now or datetime.now(tz=timezone.utc)
    if moment.tzinfo is None:
        raise PipelineError("now ต้องมี timezone เพื่อป้องกันการตัดสินแท่งผิดเขตเวลา")
    age = moment.astimezone(timezone.utc) - close_at.astimezone(timezone.utc)
    if age < timedelta(0):
        raise PipelineError(f"{timeframe}: basis_close_at อยู่ในอนาคต")
    live_source = fetcher is intraday_bars.fetch_rows or "timezone_check" in (meta or {})
    if live_source and age > MAX_CLOSED_BAR_AGE[timeframe]:
        raise PipelineError(
            f"แท่ง {timeframe} ล่าสุดเก่า {age} เกินเพดาน {MAX_CLOSED_BAR_AGE[timeframe]} — stale")
    return {"meta": meta, "rows": closed_rows, "basis": basis,
            "source_label": source_label, "age": age, "live": live_source}


def _build_story(h1_rows: list[dict], m15_rows: list[dict], *, h1_basis: dict,
                 m15_basis: dict, publish_date: str, now: datetime,
                 lifecycle_input: dict | None) -> dict:
    kwargs = {
        "asset": ASSET, "candle_basis": h1_basis,
        "m15_candle_basis": m15_basis, "publish_date": publish_date, "now": now,
    }
    parameters = inspect.signature(style_e_plus_story.build).parameters
    if "lifecycle_input" in parameters:
        kwargs["lifecycle_input"] = deepcopy(lifecycle_input)
    elif lifecycle_input:
        raise PipelineError("story contract รุ่นนี้ยังไม่รองรับ lifecycle_input")
    return style_e_plus_story.build(h1_rows, m15_rows, **kwargs)


def _snapshot(*, h1: dict, m15: dict, story: dict, analysis_at: datetime,
              lifecycle_input: dict | None) -> dict:
    snapshot = {
        "schema": SNAPSHOT_SCHEMA,
        "asset": ASSET,
        "analysis_at": analysis_at.isoformat(),
        "publish_date": story["publish_date"],
        "candle_state": "closed",
        "volume_policy": "unavailable-and-forbidden",
        "parameters": _story_parameters(),
        "lifecycle_input": _without_volume(lifecycle_input or {}),
        "timeframes": {},
        "adaptive_context": deepcopy(story["adaptive_context"]),
        "adaptive_context_sha256": story["adaptive_context"]["sha256"],
        "adaptive_policy": "adaptive-stop-b100-no-fallback",
    }
    for timeframe, source in ((H1_TIMEFRAME, h1), (M15_TIMEFRAME, m15)):
        snapshot["timeframes"][timeframe] = {
            "source_label": str(source["source_label"]),
            "source_meta": _without_volume(source["meta"] or {}),
            "candle_basis": deepcopy(source["basis"]),
            "dropped_forming_bars": _without_volume(
                list(source["basis"].get("dropped_forming_bars") or [])),
            "closed_bar_age_seconds": int(source["age"].total_seconds()),
            "freshness_max_age_seconds": int(MAX_CLOSED_BAR_AGE[timeframe].total_seconds()),
            "freshness_enforced": bool(source["live"]),
            "row_count": len(source["rows"]),
            "rows": _normal_rows(source["rows"], timeframe=timeframe),
        }
    return snapshot


def _source_evidence(snapshot: dict) -> dict:
    evidence = {
        "schema": "style-e-plus-source/v4",
        "asset": snapshot["asset"], "wcb_tag": "btc",
        "analysis_at": snapshot["analysis_at"],
        "adaptive_context_sha256": snapshot["adaptive_context_sha256"],
        "adaptive_policy": snapshot["adaptive_policy"],
        "timeframes": {}, "volume": "unavailable-and-forbidden",
    }
    for timeframe in TIMEFRAMES:
        source = snapshot["timeframes"][timeframe]
        evidence["timeframes"][timeframe] = {
            "source_label": source["source_label"],
            "source_meta": deepcopy(source["source_meta"]),
            "closed_rows": len(source["rows"]),
            "basis_bar_at": source["candle_basis"]["basis_bar_at"],
            "candle_basis": deepcopy(source["candle_basis"]),
            "dropped_forming_bars": deepcopy(source["dropped_forming_bars"]),
            "closed_bar_age_seconds": source["closed_bar_age_seconds"],
            "freshness_max_age_seconds": source["freshness_max_age_seconds"],
            "freshness_enforced": source["freshness_enforced"],
        }
    return evidence


def prepare(*, asset: str, fetcher=intraday_bars.fetch_rows,
            now: datetime | None = None, publish_date: str | None = None,
            lifecycle_input: dict | None = None) -> dict:
    """Prepare and validate E+ artifacts without writing any files.

    The manual preview pipeline and the daily delivery layer intentionally
    share this function so candle selection, story decisions and copy QA
    cannot drift between the two entry points.
    """
    _validate_arguments(asset, Path("."))
    _validate_lifecycle_input(lifecycle_input)
    if wcb_source.tag_for(asset) != "btc":
        raise PipelineError("WCB tag ของ BTCUSD ต้องเป็น btc")
    analysis_at = now or datetime.now(tz=timezone.utc)
    if analysis_at.tzinfo is None:
        raise PipelineError("now ต้องมี timezone")
    date_text = publish_date or analysis_at.astimezone(wcb_source.BANGKOK).strftime("%Y-%m-%d")
    h1 = _closed_source(
        asset=asset, timeframe=H1_TIMEFRAME, fetcher=fetcher, now=analysis_at)
    m15 = _closed_source(
        asset=asset, timeframe=M15_TIMEFRAME, fetcher=fetcher, now=analysis_at)
    story = _build_story(
        h1["rows"], m15["rows"], h1_basis=h1["basis"], m15_basis=m15["basis"],
        publish_date=date_text, now=analysis_at, lifecycle_input=lifecycle_input)
    markdown = style_e_plus_writer.render_article(story)
    qa = style_e_plus_writer.validate(markdown, story, now=analysis_at)
    if not qa["ok"]:
        raise PipelineError(
            "บท Style E+ ตก validator: " + "; ".join(item["message"] for item in qa["findings"]))
    snapshot = _snapshot(
        h1=h1, m15=m15, story=story, analysis_at=analysis_at,
        lifecycle_input=lifecycle_input)
    return {"story": story, "markdown": markdown, "qa": qa,
            "source_snapshot": snapshot, "source_evidence": _source_evidence(snapshot),
            "h1_rows": h1["rows"], "m15_rows": m15["rows"]}


def prepare_daily_conditional(*, asset: str, session_cutoff: datetime,
                              fetcher=intraday_bars.fetch_rows,
                              now: datetime | None = None,
                              publish_date: str | None = None) -> dict:
    """Prepare a v5/DC-T package in memory; never writes or publishes output."""
    base = prepare(asset=asset, fetcher=fetcher, now=now,
                   publish_date=publish_date)
    moment = now or datetime.now(tz=timezone.utc)
    if moment.tzinfo is None or session_cutoff.tzinfo is None:
        raise PipelineError("session_cutoff และ now ต้องมี timezone")
    story = style_e_plus_story.build_daily_conditional(
        base["h1_rows"], base["m15_rows"], asset=asset,
        session_cutoff=session_cutoff,
        candle_basis=base["source_snapshot"]["timeframes"][H1_TIMEFRAME]["candle_basis"],
        m15_candle_basis=base["source_snapshot"]["timeframes"][M15_TIMEFRAME]["candle_basis"],
        publish_date=publish_date or moment.astimezone(wcb_source.BANGKOK).strftime("%Y-%m-%d"),
        now=moment)
    markdown = style_e_plus_writer.render_article(story)
    qa = style_e_plus_writer.validate(markdown, story, now=moment)
    if not qa["ok"]:
        raise PipelineError("บท DC-T ตก validator: " +
                            "; ".join(item["message"] for item in qa["findings"]))
    snapshot = deepcopy(base["source_snapshot"])
    snapshot["schema"] = SNAPSHOT_SCHEMA_V3
    snapshot["daily_conditional"] = deepcopy(story["daily_conditional"])
    snapshot["strict_projection_sha256"] = story["strict_projection_oracle"]["sha256"]
    snapshot["conditional_sha256"] = story["daily_conditional"]["sha256"]
    evidence = deepcopy(base["source_evidence"])
    evidence["schema"] = "style-e-plus-source/v5"
    evidence["daily_conditional"] = deepcopy(story["daily_conditional"])
    return {"story": story, "markdown": markdown, "qa": qa,
            "source_snapshot": snapshot, "source_evidence": evidence,
            "conditional_artifact": {
                key: deepcopy(story[key]) for key in (
                    "session_id", "daily_conditional", "strict_projection_oracle",
                    "watch_geometry_oracle", "source_snapshot", "manifest")
            },
            "h1_rows": base["h1_rows"], "m15_rows": base["m15_rows"]}


# Private alias kept for offline-reproduce and older tests that deliberately
# exercise the preparation seam.  New callers should use ``prepare``.
_prepare = prepare


def _readme(story: dict) -> str:
    side = (story.get("side") or "none").upper()
    m15_check = (
        "2. ภาพ M15 แสดง Entry Zone, จุดยกเลิกก่อนเข้า, protective stop, TP1 และ TP2"
        if story.get("plan") else
        "2. ภาพ M15 แสดงราคาปิดและ EMA20 โดยไม่มีระดับแผนเทรด"
    )
    lines = [
        "# Preview — Style E+ BTCUSD H1/M15", "",
        f"- State: `{story['state']}`", f"- H1 Bias: `{side}`",
        f"- H1 closed basis: `{story['bar_at']}` (Asia/Bangkok)",
        f"- M15 closed basis: `{story['m15_bar_at']}` (Asia/Bangkok)",
        "- Manual only: package นี้เกิดจากคำสั่งตรง ไม่มี schedule/automation", "",
        "## รายการตรวจ", "",
        "1. ภาพ H1 แสดงบริบทเทรนด์และความผันผวนโดยไม่มีจุดเข้า",
        m15_check,
        "3. บทใช้ H1 เป็น Bias และใช้ M15 เป็น Execution เท่านั้น",
        "4. บทและภาพไม่มีข้อมูล volume",
    ]
    if story.get("plan"):
        plan = story["plan"]
        lines += ["", "## ระดับ M15 ที่ต้องตรวจ", "",
                  f"- Trigger: `{plan['trigger']:.2f}`",
                  f"- Entry: `{plan['entry_zone_low']:.2f}–{plan['entry_zone_high']:.2f}`",
                  f"- Pre-entry invalidation (close): `{plan['pre_entry_invalidation_close']:.2f}`",
                  f"- Protective stop after external fill: `{plan['protective_stop']['price']:.2f}`",
                  f"- TP1 / TP2: `{plan['tp1']:.2f}` / `{plan['tp2']:.2f}`"]
    else:
        lines += ["", "รอบนี้ไม่มี Entry/SL/TP ตามกฎของสถานะดังกล่าว"]
    return "\n".join(lines) + "\n"


def _relative_image_result(result: dict, image_name: str) -> dict:
    if not isinstance(result, dict):
        raise PipelineError("renderer result ต้องเป็น object")
    normalized = deepcopy(result)
    normalized["path"] = _package_name(image_name, label="renderer.path")
    _assert_no_unsafe_paths(normalized, label="renderer")
    return normalized


def _write_package(prepared: dict, *, output_root: Path, renderer=None,
                   expected_manifest: dict | None = None) -> dict:
    story = prepared["story"]
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / _run_id(story)
    if target.exists():
        raise PipelineError(f"Preview run นี้มีอยู่แล้ว ห้ามเขียนทับ: {target}")
    temporary = Path(tempfile.mkdtemp(prefix=".style-e-plus-", dir=str(output_root)))
    try:
        article_path = temporary / "btcusd.md"
        image_paths = {role: temporary / name for role, name in story["images"].items()}
        article_path.write_text(prepared["markdown"], encoding="utf-8")
        (temporary / "story.json").write_text(_json_text(story), encoding="utf-8")
        (temporary / "source-evidence.json").write_text(
            _json_text(prepared["source_evidence"]), encoding="utf-8")
        (temporary / "source-snapshot.json").write_text(
            _json_text(prepared["source_snapshot"]), encoding="utf-8")

        renderer_module = _renderer(renderer)
        image_results = {
            "h1": _relative_image_result(renderer_module.render_context(
                story, prepared["h1_rows"], image_paths["h1"]),
                story["images"]["h1"]),
            "m15": _relative_image_result(renderer_module.render_execution(
                story, prepared["m15_rows"], image_paths["m15"]),
                story["images"]["m15"]),
        }
        for role, path in image_paths.items():
            if not path.is_file():
                raise PipelineError(f"renderer ไม่สร้างภาพ {role}")
        qa = dict(prepared["qa"])
        qa["images"] = image_results
        _assert_no_unsafe_paths(qa, label="qa-report")
        (temporary / "qa-report.json").write_text(_json_text(qa), encoding="utf-8")
        (temporary / "README.md").write_text(_readme(story), encoding="utf-8")

        artifact_names = [
            "btcusd.md", story["images"]["h1"], story["images"]["m15"],
            "story.json", "source-evidence.json", "source-snapshot.json",
            "qa-report.json", "README.md",
        ]
        runtime_commit = _runtime_commit()
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "manual_only": True, "asset": ASSET,
            "runtime_commit": runtime_commit,
            "runtime_base_commit": runtime_commit,
            "story_schema": story["schema"],
            "snapshot_schema": SNAPSHOT_SCHEMA,
            "adaptive_context_schema": adaptive_stop.CONTEXT_SCHEMA,
            "adaptive_context_sha256": story["adaptive_context"]["sha256"],
            "policy": "adaptive-stop-b100-no-fallback",
            "timeframes": {"context": H1_TIMEFRAME, "execution": M15_TIMEFRAME},
            "state": story["state"], "run_id": target.name,
            "reproduce": REPRODUCE_COMMAND,
            "files": {name: {"sha256": _sha256(temporary / name),
                              "bytes": (temporary / name).stat().st_size}
                      for name in artifact_names},
        }
        _assert_no_unsafe_paths(manifest, label="manifest")
        if expected_manifest is not None and manifest != expected_manifest:
            raise PipelineError("offline reproduce ให้ manifest/artifact hash ไม่ตรงต้นฉบับ")
        (temporary / "manifest.json").write_text(_json_text(manifest), encoding="utf-8")
        temporary.replace(target)
        return {
            "status": "pass", "written": True, "asset": ASSET,
            "state": story["state"], "side": story.get("side"),
            "directory": str(target), "article": str(target / "btcusd.md"),
            "images": {role: str(target / name) for role, name in story["images"].items()},
            "manifest": str(target / "manifest.json"),
            "manifest_sha256": _sha256(target / "manifest.json"),
            "char_count": prepared["qa"]["char_count"],
        }
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def _read_json(path: Path, *, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label}: อ่าน JSON ไม่ได้") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{label}: ต้องเป็น JSON object")
    return value


def _verify_manifest(package: Path) -> dict:
    if not package.is_dir():
        raise PipelineError(f"reproduce package ไม่ใช่โฟลเดอร์: {package}")
    manifest = _read_json(package / "manifest.json", label="manifest")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise PipelineError("manifest schema ไม่รองรับ")
    if manifest.get("asset") != ASSET or manifest.get("manual_only") is not True:
        raise PipelineError("manifest contract ของ Style E+ ไม่ตรง")
    if (manifest.get("story_schema") != "style-e-plus-story/v4"
            or manifest.get("snapshot_schema") != SNAPSHOT_SCHEMA
            or manifest.get("adaptive_context_schema") != adaptive_stop.CONTEXT_SCHEMA
            or manifest.get("policy") != "adaptive-stop-b100-no-fallback"
            or not isinstance(manifest.get("adaptive_context_sha256"), str)):
        raise PipelineError("manifest B100/context contract ไม่ตรง")
    for key in ("runtime_commit", "runtime_base_commit"):
        value = manifest.get(key)
        if (not isinstance(value, str) or len(value) != 40
                or any(char not in "0123456789abcdef" for char in value.lower())):
            raise PipelineError(f"manifest ไม่มี {key} ที่เป็น SHA-1")
    if manifest.get("reproduce") != REPRODUCE_COMMAND:
        raise PipelineError("manifest reproduce command ไม่เป็น generic offline command")
    files = manifest.get("files")
    if not isinstance(files, dict) or "source-snapshot.json" not in files:
        raise PipelineError("manifest ไม่มี source snapshot")
    names = {_package_name(name, label="manifest.files") for name in files}
    actual = {path.name for path in package.iterdir() if path.is_file()}
    expected = names | {"manifest.json"}
    if actual != expected or any(path.is_dir() for path in package.iterdir()):
        raise PipelineError("package มี artifact ขาด/เกินจาก manifest")
    for name in sorted(names):
        record = files.get(name)
        if not isinstance(record, dict) or set(record) != {"sha256", "bytes"}:
            raise PipelineError(f"manifest record ไม่ถูกต้อง: {name}")
        path = package / name
        if record["bytes"] != path.stat().st_size or record["sha256"] != _sha256(path):
            raise PipelineError(f"manifest hash/bytes ไม่ตรง: {name}")
    _assert_no_unsafe_paths(manifest, label="manifest")
    return manifest


def _validated_snapshot(snapshot: dict) -> tuple[datetime, dict[str, list[dict]]]:
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise PipelineError("source snapshot schema ไม่รองรับ")
    if snapshot.get("asset") != ASSET or snapshot.get("candle_state") != "closed":
        raise PipelineError("source snapshot asset/candle state ไม่ตรง")
    if snapshot.get("volume_policy") != "unavailable-and-forbidden":
        raise PipelineError("source snapshot volume policy ไม่ตรง")
    if snapshot.get("adaptive_policy") != "adaptive-stop-b100-no-fallback":
        raise PipelineError("source snapshot adaptive policy ไม่ตรง")
    if not isinstance(snapshot.get("adaptive_context"), dict):
        raise PipelineError("source snapshot ไม่มี adaptive context")
    if snapshot.get("parameters") != _story_parameters():
        raise PipelineError("source snapshot parameters ไม่ตรง runtime")
    try:
        analysis_at = datetime.fromisoformat(str(snapshot["analysis_at"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PipelineError("source snapshot ไม่มี analysis_at ที่ถูกต้อง") from exc
    if analysis_at.tzinfo is None:
        raise PipelineError("source snapshot analysis_at ต้องมี timezone")
    timeframes = snapshot.get("timeframes")
    if not isinstance(timeframes, dict) or set(timeframes) != set(TIMEFRAMES):
        raise PipelineError("source snapshot ต้องมี H1/M15 ครบ")
    restored = {}
    for timeframe in TIMEFRAMES:
        source = timeframes[timeframe]
        if not isinstance(source, dict) or not isinstance(source.get("rows"), list):
            raise PipelineError(f"source snapshot {timeframe} rows ไม่ถูกต้อง")
        rows = _normal_rows(source["rows"], timeframe=timeframe)
        if rows != source["rows"]:
            raise PipelineError(f"source snapshot {timeframe} rows ไม่ normalized")
        if source.get("row_count") != len(rows):
            raise PipelineError(f"source snapshot {timeframe} row count ไม่ตรง")
        if len(rows) < int(getattr(style_e_plus_story, "MIN_CLOSED_BARS", 240)):
            raise PipelineError(f"source snapshot {timeframe} rows ไม่ครบ")
        basis = source.get("candle_basis")
        if not isinstance(basis, dict) or basis.get("timeframe") != timeframe:
            raise PipelineError(f"source snapshot {timeframe} candle basis ไม่ตรง")
        detail = intraday_bars.verify(
            basis, asset=ASSET, bar_at=rows[-1]["at"], now=analysis_at)
        if detail:
            raise PipelineError(f"source snapshot {timeframe} basis: {detail}")
        restored[timeframe] = [
            {**row, "date": row["at"][:10], "forming": False} for row in rows]
    if not isinstance(snapshot.get("lifecycle_input"), dict):
        raise PipelineError("source snapshot lifecycle_input ต้องเป็น object")
    try:
        context = adaptive_stop.build_context(restored[M15_TIMEFRAME])
        adaptive_stop.validate_context(snapshot["adaptive_context"])
    except adaptive_stop.AdaptiveStopError as exc:
        raise PipelineError(f"source snapshot adaptive context ไม่ถูกต้อง: {exc}") from exc
    if context != snapshot["adaptive_context"] or context["sha256"] != snapshot.get("adaptive_context_sha256"):
        raise PipelineError("source snapshot adaptive context/hash ไม่ตรง rows")
    return analysis_at, restored


def _prepare_reproduce(package: Path, manifest: dict) -> dict:
    snapshot = _read_json(package / "source-snapshot.json", label="source snapshot")
    analysis_at, rows = _validated_snapshot(snapshot)
    story = _build_story(
        rows[H1_TIMEFRAME], rows[M15_TIMEFRAME],
        h1_basis=snapshot["timeframes"][H1_TIMEFRAME]["candle_basis"],
        m15_basis=snapshot["timeframes"][M15_TIMEFRAME]["candle_basis"],
        publish_date=str(snapshot["publish_date"]), now=analysis_at,
        lifecycle_input=snapshot["lifecycle_input"])
    original_story = _read_json(package / "story.json", label="story")
    if story != original_story or _run_id(story) != manifest.get("run_id"):
        raise PipelineError("snapshot สร้าง story ไม่ตรง package")
    markdown = style_e_plus_writer.render_article(story)
    if markdown != (package / "btcusd.md").read_text(encoding="utf-8"):
        raise PipelineError("snapshot สร้างบทไม่ตรง package")
    qa = style_e_plus_writer.validate(markdown, story, now=analysis_at)
    if not qa["ok"]:
        raise PipelineError("offline reproduce ตก writer validator")
    evidence = _source_evidence(snapshot)
    if evidence != _read_json(package / "source-evidence.json", label="source evidence"):
        raise PipelineError("snapshot สร้าง source evidence ไม่ตรง package")
    return {
        "story": story, "markdown": markdown, "qa": qa,
        "source_snapshot": snapshot, "source_evidence": evidence,
        "h1_rows": rows[H1_TIMEFRAME], "m15_rows": rows[M15_TIMEFRAME],
    }


def reproduce(*, package: Path, output_root: Path, confirm_write: bool = False,
              renderer=None) -> dict:
    """Rebuild a verified package from its snapshot without any network access."""
    resolved_root = _validate_arguments(ASSET, output_root)
    package = Path(package).expanduser().resolve()
    manifest = _verify_manifest(package)
    prepared = _prepare_reproduce(package, manifest)
    if not confirm_write:
        return {
            "status": "pass", "written": False, "mode": "offline-reproduce-preview",
            "asset": ASSET, "state": prepared["story"]["state"],
            "output_root": str(resolved_root), "run_id": manifest["run_id"],
            "network_used": False,
        }
    result = _write_package(
        prepared, output_root=resolved_root, renderer=renderer,
        expected_manifest=manifest)
    result["network_used"] = False
    result["reproduced_from"] = str(package)
    return result


def run(*, asset: str, output_root: Path, confirm_write: bool = False,
        fetcher=intraday_bars.fetch_rows, now: datetime | None = None,
        publish_date: str | None = None, renderer=None,
        lifecycle_input: dict | None = None) -> dict:
    """Calculate one dual-timeframe package; write atomically only when confirmed."""
    resolved_root = _validate_arguments(asset, output_root)
    _validate_lifecycle_input(lifecycle_input)
    prepared = prepare(
        asset=asset, fetcher=fetcher, now=now, publish_date=publish_date,
        lifecycle_input=lifecycle_input)
    story = prepared["story"]
    if not confirm_write:
        return {
            "status": "pass", "written": False, "mode": "preview",
            "asset": asset, "state": story["state"], "side": story.get("side"),
            "bar_at": story["bar_at"], "m15_bar_at": story["m15_bar_at"],
            "output_root": str(resolved_root), "run_id": _run_id(story),
            "char_count": prepared["qa"]["char_count"],
            "image_names": dict(story["images"]), "plan": story.get("plan"),
            "note": "ไม่มี --confirm-write: คำนวณและตรวจแล้ว แต่ไม่สร้างไฟล์",
        }
    return _write_package(prepared, output_root=resolved_root, renderer=renderer)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(
        description="ผลิต Style E+ BTCUSD แบบ H1 context + M15 execution ตามคำสั่งเท่านั้น")
    parser.add_argument("--asset", choices=[ASSET])
    parser.add_argument("--reproduce-package", type=Path,
                        help="replay แพ็กเกจจาก source snapshot แบบ offline")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--confirm-write", action="store_true",
                        help="ยืนยันการวาง preview package; ไม่ใส่ธงนี้จะไม่เขียนไฟล์")
    args = parser.parse_args(argv)
    try:
        if args.reproduce_package is not None:
            if args.asset is not None:
                raise PipelineError("ห้ามใช้ --asset ร่วมกับ --reproduce-package")
            result = reproduce(
                package=args.reproduce_package, output_root=args.output_root,
                confirm_write=args.confirm_write)
        else:
            if args.asset is None:
                raise PipelineError("ต้องระบุ --asset btcusd สำหรับ live/manual run")
            result = run(asset=args.asset, output_root=args.output_root,
                         confirm_write=args.confirm_write)
    except Exception as exc:
        print(f"Style E+ BTCUSD: FAIL — {exc}")
        return 1
    print(_json_text(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
