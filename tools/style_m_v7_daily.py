"""Paired H1/M15 local-only Style M R6 package boundary."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from shutil import copyfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools import intraday_bars, style_m_v7_contract, style_m_v7_renderer, style_m_v7_risk, style_m_v7_story, style_m_v7_writer, style_m_v7_web_upload
from tools import article_continuity
from tools.delivery_file_naming import article_name, image_name

STYLE_ID = "m_btcusd_h1_visual"; STYLE_LETTER = "M"; ASSET = "btcusd"; ASSETS = (ASSET,)
STYLE_NAME = "Style M v7 — BTCUSD H1 + ADR14"; TIMEFRAMES = ("1h", "15min")
FOLDER = "TH-Thailand/M/BTCUSD"; LANE_FOLDER = "05-BTCUSD-Style-M"; INTERNAL_FOLDER = "style-m-v7"; CONTRACT_VERSION = "M-PROD/v7"; PUBLIC_STYLE_ID = "m_btcusd_h1_visual_daily"
RENDERER_REVISION = style_m_v7_renderer.RENDERER_REVISION


class DailyStyleMError(RuntimeError):
    pass


def _cutoff(value):
    if isinstance(value, datetime): result = value
    elif value is None: result = datetime.now(tz=timezone.utc)
    else:
        try: result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc: raise DailyStyleMError("cutoff_at ต้องเป็น ISO-8601") from exc
    if result.tzinfo is None: raise DailyStyleMError("cutoff_at ต้องมี timezone")
    return result.astimezone(style_m_v7_story.BANGKOK).replace(minute=0, second=0, microsecond=0)


def _visual_source(raw_rows, meta, label, cutoff):
    try:
        closed, basis = intraday_bars.evaluate(raw_rows, asset=ASSET, timeframe="15min", now=cutoff)
        if not closed: raise ValueError("ไม่มีแท่ง M15 ปิด")
        finding = intraday_bars.verify(basis, asset=ASSET, bar_at=closed[-1]["at"], now=cutoff)
        if finding or len(closed) < 96: raise ValueError(finding or f"ต้องมีอย่างน้อย 96 แท่ง (ได้ {len(closed)})")
        closed = closed[-96:]; stamps = [row["at"] for row in closed]; parsed = [intraday_bars.parse_at(stamp) for stamp in stamps]
        if stamps != sorted(set(stamps)): raise ValueError("เวลา M15 ซ้ำหรือไม่เรียง")
        if any(right - left != timedelta(minutes=15) for left, right in zip(parsed, parsed[1:])): raise ValueError("ช่วงเวลา M15 ไม่ต่อเนื่อง")
        for row in closed:
            if not (float(row["low"]) <= float(row["open"]) <= float(row["high"]) and float(row["low"]) <= float(row["close"]) <= float(row["high"])): raise ValueError("OHLC M15 ไม่อยู่ใน envelope")
        projection = {"asset": ASSET, "timeframe": "15min", "cutoff": cutoff.isoformat(), "basis": basis, "rows": closed}
        source_sha = hashlib.sha256(json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {"schema": "style-m-visual-source/v1", "asset": ASSET, "display_timeframe": "M15", "decision_timeframe": "H1", "cutoff": cutoff.isoformat(), "source_label": label, "source_meta": meta or {}, "basis": basis, "row_count": len(closed), "first_bar_at": closed[0]["at"], "latest_bar_at": closed[-1]["at"], "rows": closed, "source_sha256": source_sha}
    except Exception as exc:
        raise DailyStyleMError(f"M15_VISUAL_SOURCE_UNAVAILABLE: {exc}") from exc


def _complete_daily_source(rows, cutoff):
    """Keep only complete pre-cutoff Bangkok calendar days for ADR14.

    Live intraday APIs commonly include a partial first history day.  It is
    excluded from the volatility input; no values are synthesized and the H1
    story source remains the full closed stream.
    """
    groups = {}
    for row in rows:
        stamp = intraday_bars.parse_at(row["at"]).astimezone(style_m_v7_story.BANGKOK)
        if stamp.date() >= cutoff.date():
            continue
        groups.setdefault(stamp.date(), []).append((stamp, row))
    kept = []
    for day in sorted(groups):
        items = sorted(groups[day], key=lambda item: item[0])
        if len(items) == 24 and [item[0].hour for item in items] == list(range(24)):
            kept.extend(row for _, row in items)
    return kept


def _compat_visual_source(raw_rows, meta, label, cutoff):
    """Test-only adapter for pre-R6 fixtures that contain hourly rows.

    It is deliberately reachable only for an explicit fixed/fixture label;
    the live route always takes the strict M15 validator above.
    """
    source = []
    base = list(raw_rows)[-96:]
    start = cutoff - timedelta(minutes=15 * (len(base) - 1))
    for index, row in enumerate(base):
        item = dict(row); item["at"] = (start + timedelta(minutes=15 * index)).strftime("%Y-%m-%d %H:%M:%S")
        item["index"] = index; item.pop("forming", None); source.append(item)
    projection = {"asset": ASSET, "timeframe": "15min", "cutoff": cutoff.isoformat(), "basis": "test_fixture_projection", "rows": source}
    digest = hashlib.sha256(json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"schema": "style-m-visual-source/v1", "asset": ASSET, "display_timeframe": "M15", "decision_timeframe": "H1", "cutoff": cutoff.isoformat(), "source_label": label, "source_meta": {**(meta or {}), "compatibility_projection": True}, "basis": "test_fixture_projection", "row_count": len(source), "first_bar_at": source[0]["at"], "latest_bar_at": source[-1]["at"], "rows": source, "source_sha256": digest}


def prepare(*, cutoff_at=None, fetcher=intraday_bars.fetch_rows, visual_fetcher=None):
    cutoff = _cutoff(cutoff_at)
    meta, raw_rows, label = fetcher(ASSET, timeframe="1h", outputsize=2000)
    try:
        closed_rows, basis = intraday_bars.evaluate(raw_rows, asset=ASSET, timeframe="1h", now=cutoff)
        finding = intraday_bars.verify(basis, asset=ASSET, bar_at=closed_rows[-1]["at"], now=cutoff)
        if finding: raise DailyStyleMError(f"closed H1 gate: {finding}")
    except (IndexError, KeyError, ValueError) as exc: raise DailyStyleMError("closed H1 evidence invalid") from exc
    built = style_m_v7_story.build(closed_rows, cutoff=cutoff, source_label=label, source_meta=meta)
    try:
        risk_rows = _complete_daily_source(closed_rows, cutoff)
        story = style_m_v7_risk.apply_policy(built["story"], volatility=style_m_v7_risk.adr14(risk_rows, cutoff=cutoff))
    except style_m_v7_risk.RiskUnavailable as exc:
        story = dict(built["story"]); story["state"] = "NO_PLAN"; story["risk_geometry"] = {"policy_id": style_m_v7_risk.POLICY_ID, "volatility": {"metric": "ADR14", "value": None, "length": 14}, "no_plan_reason": exc.reason_code}
        for plan in story["scenarios"].values(): plan.update({"state": "NO_PLAN", "entry_low": None, "entry_high": None, "sl": None, "tp1": None, "tp2": None, "risk": None, "rr1": None, "rr2": None, "no_plan_reason": exc.reason_code})
    visual_meta, raw_visual, visual_label = (visual_fetcher or fetcher)(ASSET, timeframe="15min", outputsize=120)
    try:
        visual_source = _visual_source(raw_visual, visual_meta, visual_label, cutoff)
    except DailyStyleMError:
        if visual_fetcher is None and str(visual_label).lower().startswith(("fixed", "fixture")):
            visual_source = _compat_visual_source(raw_visual, visual_meta, visual_label, cutoff)
        else:
            raise
    facts = style_m_v7_contract.build(story, built["rows"])
    names = {role: template.format(date=cutoff.strftime("%Y-%m-%d")) for role, template in style_m_v7_writer.IMAGE_NAMES.items()}
    prepared = {**built, "story": story, "cutoff": cutoff, "basis": basis, "facts": facts, "visual_source": visual_source, "image_names": names, "renderer_revision": RENDERER_REVISION}
    prepared["markdown"] = style_m_v7_writer.compose(prepared); style_m_v7_writer.validate(prepared["markdown"], story, facts)
    prepared["parity"] = style_m_v7_contract.parity_report(facts, markdown=prepared["markdown"])
    prepared["idempotency_key"] = hashlib.sha256(json.dumps({"contract": CONTRACT_VERSION, "policy": style_m_v7_risk.POLICY_ID, "cutoff": cutoff.isoformat(), "source": story["source_sha256"], "visual_source": visual_source["source_sha256"], "renderer_revision": RENDERER_REVISION, "images": names}, sort_keys=True).encode()).hexdigest()
    return prepared


def _write_web_upload(target: Path, prepared: dict, render: dict) -> dict:
    """Create a clean three-file handoff without changing internal btc.md."""
    date_iso = prepared["cutoff"].strftime("%Y-%m-%d")
    upload_dir = target / "web-upload"
    upload_dir.mkdir(parents=True, exist_ok=True)
    image_paths = {role: Path(meta["path"]) for role, meta in render["images"].items()}
    image_names = {role: path.name for role, path in image_paths.items()}
    web_markdown = prepared.get("continuity_web_markdown") or style_m_v7_web_upload.build(
        prepared["markdown"], image_names=image_names, date_iso=date_iso)
    article_path = upload_dir / f"btc-daily-{date_iso}.md"
    article_path.write_text(web_markdown, encoding="utf-8", newline="\n")
    copied = {}
    for role, source in image_paths.items():
        destination = upload_dir / source.name
        copyfile(source, destination)
        copied[role] = destination
    validation = style_m_v7_web_upload.validate(
        web_markdown, filename=article_path.name, image_paths=copied, date_iso=date_iso)
    files = {article_path.name: hashlib.sha256(article_path.read_bytes()).hexdigest()}
    files.update({path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in copied.values()})
    return {"path": str(upload_dir), "article": article_path.name,
            "images": image_names, "files": files, "validation": validation}


def _write_country_source(source: Path, destination: Path, date_iso: str) -> dict[str, str]:
    """Materialize the Thai source at its final country/style/asset path."""
    article = source / f"btc-daily-{date_iso}.md"
    images = sorted(source.glob("*.webp"))
    if not article.is_file() or len(images) != 2:
        raise DailyStyleMError("Style M web-upload ต้องมีบทและภาพ WebP สองใบ")
    names = {image.name: image_name(date_iso, "TH", "M", "BTCUSD", ordinal, image.name)
             for ordinal, image in enumerate(images, start=1)}
    markdown = article.read_text(encoding="utf-8")
    for old, new in names.items():
        markdown = markdown.replace(old, new)
    if any(old in markdown for old in names):
        raise DailyStyleMError("Style M ไม่สามารถแทนชื่อภาพเป็นชื่อ final ได้ครบ")
    files = {article_name(date_iso, "TH", "M", "BTCUSD"): markdown.encode("utf-8")}
    files.update({names[image.name]: image.read_bytes() for image in images})
    if destination.exists():
        existing = {path.relative_to(destination).as_posix(): path.read_bytes()
                    for path in destination.rglob("*") if path.is_file()}
        if existing == files:
            return {"status": "idempotent", "article": article_name(date_iso, "TH", "M", "BTCUSD")}
        raise DailyStyleMError("Style M country output มีอยู่แล้วและ hash ต่าง — HOLD ห้ามเขียนทับ")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".M-BTCUSD-country-", dir=destination.parent))
    try:
        for name, data in files.items():
            (stage / name).write_bytes(data)
        os.replace(stage, destination)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return {"status": "created", "article": article_name(date_iso, "TH", "M", "BTCUSD")}


def run_shadow(*, root: Path, cutoff_at=None, fetcher=intraday_bars.fetch_rows, visual_fetcher=None,
               continuity_root: Path | None = None):
    prepared = prepare(cutoff_at=cutoff_at, fetcher=fetcher, visual_fetcher=visual_fetcher)
    continuity_store = continuity_root or Path(root).parent / "continuity"
    web_markdown = style_m_v7_web_upload.build(
        prepared["markdown"], image_names=prepared["image_names"],
        date_iso=prepared["cutoff"].strftime("%Y-%m-%d"))
    prepared["continuity_web_markdown"], continuity_record = article_continuity.enrich(
        web_markdown, asset=ASSET, style="M", contract=CONTRACT_VERSION,
        cutoff=prepared["cutoff"].isoformat(),
        evidence={"story": prepared["story"], "facts": prepared["facts"], "rows": prepared["rows"]},
        store_root=continuity_store, contexts=["structure", "confirmation", "risk"])
    prepared["idempotency_key"] = hashlib.sha256(
        (prepared["idempotency_key"] + prepared["continuity_web_markdown"]).encode("utf-8")).hexdigest()
    target = Path(root) / prepared["cutoff"].strftime("%d-%m-%Y") / ASSET / "internal" / f"{INTERNAL_FOLDER}-{prepared['idempotency_key'][:12]}"
    if target.exists():
        manifest = target / "manifest.json"
        if manifest.is_file():
            existing = json.loads(manifest.read_text(encoding="utf-8")); expected = existing.get("files") or {}
            actual = {name: hashlib.sha256((target / "public" / name).read_bytes()).hexdigest() for name in expected if (target / "public" / name).is_file()}
            if existing.get("idempotency_key") == prepared["idempotency_key"] and actual == expected: return {"status": "pass", "published": False, "shadow": str(target), "idempotent": True, "image_names": prepared["image_names"]}
        raise DailyStyleMError(f"v7 shadow collision: {target}")
    public = target / "public"; public.mkdir(parents=True); article = public / "btc.md"; article.write_text(prepared["markdown"], encoding="utf-8")
    render = style_m_v7_renderer.render_pair(prepared["story"], prepared["rows"], prepared["visual_source"]["rows"], public, facts=prepared["facts"], visual_source=prepared["visual_source"], names=prepared["image_names"])
    # Compatibility projections are metadata-only; the R6 role map remains the
    # source of truth for both image assets.
    render["label_overlap_count"] = render["images"]["m15_entry_plan"]["label_overlap_count"]
    render["plan_cards"] = render["images"]["m15_entry_plan"]["plan_cards"]
    web_upload = _write_web_upload(target, prepared, render)
    article_continuity.save_candidate(
        continuity_store, continuity_record, prepared["continuity_web_markdown"], qc_pass=True)
    files = {"btc.md": hashlib.sha256(article.read_bytes()).hexdigest()}; files.update({meta["path"].split("\\")[-1]: hashlib.sha256(Path(meta["path"]).read_bytes()).hexdigest() for meta in render["images"].values()})
    manifest_render = json.loads(json.dumps(render))
    for meta in manifest_render["images"].values():
        meta["path"] = Path(meta["path"]).name
    manifest_web_upload = json.loads(json.dumps(web_upload)); manifest_web_upload["path"] = "web-upload"
    evidence = {"schema": "style-m-v7-daily-manifest/v4", "contract_version": CONTRACT_VERSION, "policy_id": style_m_v7_risk.POLICY_ID, "production_write": False, "external_publish": False, "fixture": False, "story": prepared["story"], "facts": prepared["facts"], "visual_source": {key: value for key, value in prepared["visual_source"].items() if key != "rows"}, "renderer_revision": RENDERER_REVISION, "claim_parity": prepared["parity"], "renderer": manifest_render, "images": {role: {"path": Path(meta["path"]).name, "sha256": files[Path(meta["path"]).name]} for role, meta in render["images"].items()}, "image_names": list(prepared["image_names"].values()), "web_upload": manifest_web_upload, "idempotency_key": prepared["idempotency_key"], "files": files}
    (target / "manifest.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "pass", "published": False, "shadow": str(target), "article": str(article), "images": {role: meta["path"] for role, meta in render["images"].items()}, "image": render["images"]["m15_entry_plan"]["path"], "image_names": prepared["image_names"], "web_upload": web_upload, "idempotent": False, "state": prepared["story"]["state"]}


def run_round(*, asset: str = ASSET, publish_root: Path = Path("../output"), work_root: Path = Path("../work/build"), cutoff_at=None, fetcher=intraday_bars.fetch_rows, publish: bool = True, **kwargs):
    if asset != ASSET: raise DailyStyleMError("Style M v7 รองรับเฉพาะ btcusd")
    result = run_shadow(root=work_root, cutoff_at=cutoff_at, fetcher=fetcher,
                        visual_fetcher=kwargs.pop("visual_fetcher", None),
                        continuity_root=kwargs.pop("continuity_root", None))
    if publish and result.get("status") == "pass":
        source = Path(result["shadow"]) / "web-upload"
        if not source.is_dir():
            raise DailyStyleMError("Style M v7 web-upload หายหลังผ่าน shadow gate")
        day = Path(result["shadow"]).parents[2].name
        destination = Path(publish_root) / day / FOLDER
        date_iso = datetime.strptime(day, "%d-%m-%Y").strftime("%Y-%m-%d")
        delivery = _write_country_source(source, destination, date_iso)
        result.update({"published": True, "directory": str(destination),
                       "article": str(destination / delivery["article"]),
                       "idempotent": delivery["status"] == "idempotent"})
    return result


__all__ = ["STYLE_ID", "STYLE_LETTER", "ASSET", "ASSETS", "TIMEFRAMES", "FOLDER", "LANE_FOLDER", "INTERNAL_FOLDER", "CONTRACT_VERSION", "prepare", "run_shadow", "run_round", "DailyStyleMError"]
