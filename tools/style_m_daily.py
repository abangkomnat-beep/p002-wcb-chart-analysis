"""Daily production route for BTCUSD Style M (one H1 article + one image)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from tools import (image_output, intraday_bars, news_source, publish_layout,
                   style_m_article_contract, style_m_renderer, style_m_semantics,
                   style_m_story, style_m_writer)


STYLE_ID = "m_btcusd_h1_visual"
STYLE_LETTER = "M"
STYLE_NAME = "Style M — แผนภาพรายวัน H1"
ASSET = "btcusd"
ASSETS = (ASSET,)
TIMEFRAMES = ("1h",)
FOLDER = "M-BTCUSD-H1-Visual-Daily"
LANE_FOLDER = "05-BTCUSD-Style-M"
INTERNAL_FOLDER = "style-m"
CONTRACT_VERSION = style_m_article_contract.CONTRACT_VERSION


class DailyStyleMError(RuntimeError):
    """Style M cannot produce one verified, atomic daily set."""


class DailyStyleMNotDue(DailyStyleMError):
    """The Bangkok 05:00 cutoff has not occurred yet."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _moment(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now(tz=timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise DailyStyleMError("cutoff_at ต้องเป็น ISO-8601") from exc
    if parsed.tzinfo is None:
        raise DailyStyleMError("cutoff_at ต้องมี timezone")
    return parsed


def daily_cutoff(value: str | datetime | None) -> datetime:
    moment = _moment(value).astimezone(style_m_story.BANGKOK)
    cutoff = moment.replace(hour=5, minute=0, second=0, microsecond=0)
    if moment < cutoff:
        raise DailyStyleMNotDue("Style M รอแท่ง H1 เวลา 05:00 น. ไทยปิดก่อน")
    return cutoff


def load_prior_fingerprint(work_root: Path, cutoff: datetime) -> dict | None:
    """Read the newest prior v4/v5 facts without touching production output.

    The current local-date folder is explicitly excluded so a rerun cannot use
    the immutable 31-08 evidence as its own prior.  Missing/invalid evidence
    is a normal cache miss and returns ``None``.
    """
    root = Path(work_root)
    if not root.is_dir():
        return None
    current_day = publish_layout.day_folder(cutoff.isoformat())
    candidates: list[tuple[datetime, Path]] = []
    for path in root.rglob("article-visual-facts.json"):
        if current_day in path.parts or "style-m-hold-" in str(path.parent.parent):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema") not in (style_m_article_contract.SCHEMA,
                                               style_m_article_contract.LEGACY_SCHEMA):
                continue
            day = next((part for part in path.parts if len(part) == 10 and part[2] == "-" and part[5] == "-"), None)
            stamp = datetime.strptime(day, "%d-%m-%Y") if day else datetime.min
            if stamp.date() < cutoff.date():
                candidates.append((stamp, path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    if not candidates:
        return None
    _, selected = max(candidates, key=lambda item: item[0])
    return json.loads(selected.read_text(encoding="utf-8"))


def _fetch_h1(fetcher, cutoff: datetime) -> tuple[dict, list[dict], str, dict]:
    # Fetch using the provider's real current clock, then deterministically trim
    # the series to the approved 05:00 Bangkok cutoff below. Passing a historical
    # cutoff as the provider clock can make valid same-day data look shifted.
    meta, raw_rows, label = fetcher(ASSET, timeframe="1h", outputsize=500)
    closed_rows, basis = intraday_bars.evaluate(raw_rows, asset=ASSET, timeframe="1h", now=cutoff)
    finding = intraday_bars.verify(basis, asset=ASSET, bar_at=closed_rows[-1]["at"], now=cutoff)
    if finding:
        raise DailyStyleMError(f"closed H1 gate: {finding}")
    if basis.get("basis_close_at") != cutoff.isoformat():
        raise DailyStyleMError(
            f"latest closed H1 ไม่ตรง cutoff 05:00 ไทย: {basis.get('basis_close_at')}")
    return meta, closed_rows, label, basis


def normalize_news(report: dict) -> list[dict]:
    return style_m_article_contract.canonical_event_projection(report)


def prepare(*, cutoff_at: str | datetime | None = None,
            fetcher=intraday_bars.fetch_rows,
            news_collector=news_source.collect_official,
            prior_fingerprint: dict | str | None = None) -> dict:
    cutoff = daily_cutoff(cutoff_at)
    meta, rows, label, basis = _fetch_h1(fetcher, cutoff)
    built = style_m_story.build(rows, cutoff=cutoff, source_label=label, source_meta=meta)
    built["rows"] = style_m_semantics.canonicalize_rows(built["rows"])
    try:
        news_report = news_collector(ASSET, now=cutoff.astimezone(timezone.utc))
    except Exception as exc:  # noqa: BLE001 — news is a non-fatal advisory
        news_report = {"asset": ASSET, "items": [], "provider_status": "unavailable",
                       "error_class": type(exc).__name__, "cut_reason": "provider_unavailable",
                       "collected_at": cutoff.astimezone(timezone.utc).isoformat()}
    events = normalize_news(news_report)
    facts = style_m_article_contract.build(built["story"], built["rows"], events=events,
                                           news_report=news_report,
                                           prior_fingerprint=(prior_fingerprint if isinstance(prior_fingerprint, dict) else None))
    composed = style_m_writer.compose(built["story"], events, facts)
    markdown = composed["markdown"]
    writer_claim_report = composed["claim_report"]
    article_qa = style_m_writer.validate(markdown, built["story"], events=events, facts=facts)
    idempotency = {
        "style": STYLE_LETTER, "asset": ASSET,
        "local_date": cutoff.strftime("%Y-%m-%d"), "cutoff": cutoff.isoformat(),
        "source_sha256": built["story"]["source_sha256"],
        "contract_version": CONTRACT_VERSION,
        "facts_schema": facts["schema"],
        "semantic_schema": facts["semantic_decision"]["schema"],
    }
    key = hashlib.sha256(json.dumps(idempotency, sort_keys=True).encode("utf-8")).hexdigest()
    index_policy = style_m_article_contract.index_recommendation(facts, prior_fingerprint)
    return {**built, "basis": basis, "news_report": news_report, "events": events,
            "prior_fingerprint": (prior_fingerprint
                                  if isinstance(prior_fingerprint, dict) else None),
            "article_visual_facts": facts, "index_policy": index_policy,
            "semantic_decision": facts["semantic_decision"],
            "writer_claim_report": writer_claim_report,
            "markdown": markdown, "article_qa": article_qa,
            "idempotency": {**idempotency, "key": key}, "cutoff": cutoff}


def _render_package(prepared: dict, folder: Path, renderer=None) -> dict:
    if renderer is not None and renderer is not style_m_renderer:
        raise DailyStyleMError("production package อนุญาตเฉพาะ canonical Style M renderer")
    trusted_events = style_m_article_contract.canonical_event_projection(
        prepared["news_report"])
    if prepared.get("events") != trusted_events:
        raise style_m_article_contract.ArticleContractError(
            "TRUSTED_EVENTS_PROJECTION_MISMATCH",
            "prepared.events ไม่ตรงกับ canonical projection ของ raw news_report")
    style_m_article_contract.validate(
        prepared["article_visual_facts"], story=prepared["story"],
        rows=prepared["rows"], events=prepared["events"],
        news_report=prepared["news_report"],
        prior_fingerprint=prepared["prior_fingerprint"])
    folder.mkdir(parents=True, exist_ok=True)
    # WCB's registered web tag is `btc`; `btcusd` remains the internal market-data key.
    article = folder / "btc.md"
    date_iso = prepared["cutoff"].strftime("%Y-%m-%d")
    image_name = style_m_writer.IMAGE_NAME.format(date=date_iso)
    image = folder / image_name
    article.write_text(prepared["markdown"], encoding="utf-8")
    render_result = (renderer or style_m_renderer).render(
        prepared["story"], prepared["rows"], image, prepared.get("article_visual_facts"),
        events=prepared["events"], news_report=prepared["news_report"],
        prior_fingerprint=prepared["prior_fingerprint"])
    image_output.verify(image)
    try:
        with Image.open(image) as rendered_image:
            width, height = rendered_image.size
            image_format = rendered_image.format.lower()
        actual_sha256 = _sha256(image)
        actual_bytes = image.stat().st_size
        trace = render_result.get("draw_trace")
        visual_trace_sha256 = hashlib.sha256(json.dumps(
            trace, sort_keys=True, ensure_ascii=False,
            separators=(",", ":")).encode("utf-8")).hexdigest()
        artifact_trace_sha256 = hashlib.sha256(
            f"{actual_sha256}:{visual_trace_sha256}".encode("utf-8")).hexdigest()
        artifact = render_result.get("artifact", {})
        actual = {"sha256": actual_sha256, "bytes": actual_bytes,
                  "width": width, "height": height, "format": image_format,
                  "visual_trace_sha256": visual_trace_sha256,
                  "artifact_trace_sha256": artifact_trace_sha256}
        if artifact != actual or render_result.get("visual_trace_sha256") != visual_trace_sha256:
            raise DailyStyleMError("renderer report ไม่ตรง image artifact/visual trace จริง")
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise DailyStyleMError("ตรวจ image artifact/visual trace ไม่สำเร็จ") from exc
    files = {path.name: {"sha256": _sha256(path), "bytes": path.stat().st_size}
             for path in (article, image)}
    parity = style_m_article_contract.parity_report(
        prepared["article_visual_facts"], markdown=prepared["markdown"],
        writer_report=prepared["writer_claim_report"],
        render_report=render_result)
    if parity["status"] != "PASS":
        raise DailyStyleMError(f"Style M parity gate {parity['status']}: {parity}")
    return {"article": article.name, "image": image.name, "files": files,
            "render": render_result, "renderer_claim_report": render_result,
            "parity": parity}


def _same_package(target: Path, files: dict) -> bool:
    if not target.is_dir():
        return False
    actual = {path.name: _sha256(path) for path in target.iterdir() if path.is_file()}
    expected = {name: record["sha256"] for name, record in files.items()}
    return actual == expected


def _write_internal(prepared: dict, target: Path, package: dict, *,
                    production_write: bool) -> None:
    if target.exists():
        manifest = target / "manifest.json"
        if manifest.is_file():
            existing = json.loads(manifest.read_text(encoding="utf-8"))
            if existing.get("idempotency", {}).get("key") == prepared["idempotency"]["key"]:
                return
        raise DailyStyleMError(f"internal evidence ชื่อชนและ hash ต่าง: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".style-m-evidence-", dir=target.parent))
    try:
        payloads = {"story.json": prepared["story"], "source-evidence.json": prepared["source_projection"],
                    "candle-basis.json": prepared["basis"], "news-evidence.json": prepared["news_report"],
                    "semantic-decision.json": prepared["semantic_decision"],
                    "article-visual-facts.json": prepared["article_visual_facts"],
                    "writer-claim-report.json": prepared["writer_claim_report"],
                    "renderer-claim-report.json": package["renderer_claim_report"],
                    "index-policy.json": prepared["index_policy"],
                    "claim-parity-report.json": package["parity"],
                    "qa-report.json": {"article": prepared["article_qa"], "image": package["render"],
                                       "production_write": production_write,
                                       "external_publish": False},
                    "manifest.json": {"schema": "style-m-daily-manifest/v3",
                                      "contract_version": CONTRACT_VERSION,
                                      "facts_schema": prepared["article_visual_facts"]["schema"],
                                      "semantic_schema": prepared["semantic_decision"]["schema"],
                                      "style": STYLE_LETTER, "asset": ASSET,
                                      "state": prepared["story"]["state"],
                                      "idempotency": prepared["idempotency"],
                                      "files": package["files"],
                                      "production_write": production_write,
                                      "external_publish": False}}
        for name, value in payloads.items():
            (stage / name).write_text(_json(value), encoding="utf-8")
        os.replace(stage, target)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def run_round(*, asset: str = ASSET, publish_root: Path = Path("../output"),
              work_root: Path = Path("../work/build"), cutoff_at: str | datetime | None = None,
              fetcher=intraday_bars.fetch_rows, news_collector=news_source.collect_official,
              renderer=None, publish: bool = True,
              prior_fingerprint: dict | str | None = None) -> dict:
    if asset != ASSET:
        raise DailyStyleMError("Style M รองรับเฉพาะ btcusd")
    cutoff = daily_cutoff(cutoff_at)
    if prior_fingerprint is None:
        prior_fingerprint = load_prior_fingerprint(work_root, cutoff)
    prepared = prepare(cutoff_at=cutoff_at, fetcher=fetcher, news_collector=news_collector,
                       prior_fingerprint=prior_fingerprint)
    cutoff = prepared["cutoff"]
    day = publish_layout.day_folder(cutoff.isoformat())
    day_dir = Path(publish_root) / day
    internal = Path(work_root) / day / ASSET / "internal" / INTERNAL_FOLDER
    shadow_parent = internal.parent
    shadow_parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".style-m-package-", dir=shadow_parent))
    try:
        package = _render_package(prepared, stage, renderer=renderer)
        if prepared["index_policy"]["recommendation"] == "HOLD_DUPLICATE_NO_PLAN":
            shadow = internal.with_name(f"{INTERNAL_FOLDER}-hold-{prepared['idempotency']['key'][:12]}")
            if shadow.exists():
                if _same_package(shadow / "public", package["files"]):
                    shutil.rmtree(stage, ignore_errors=True)
                    return {"status": "hold", "published": False, "shadow": str(shadow),
                            "state": prepared["story"]["state"], "idempotent": True,
                            "index_policy": prepared["index_policy"]}
                raise DailyStyleMError(f"duplicate hold shadow ชื่อชนและ hash ต่าง: {shadow}")
            public = stage.rename(stage.with_name(stage.name + "-public"))
            shadow.mkdir(parents=True)
            os.replace(public, shadow / "public")
            _write_internal(prepared, shadow / "evidence", package, production_write=False)
            return {"status": "hold", "published": False, "shadow": str(shadow),
                    "state": prepared["story"]["state"], "idempotent": False,
                    "index_policy": prepared["index_policy"]}
        if not publish:
            shadow = internal.with_name(f"{INTERNAL_FOLDER}-shadow-{prepared['idempotency']['key'][:12]}")
            if shadow.exists():
                if _same_package(shadow / "public", package["files"]):
                    shutil.rmtree(stage, ignore_errors=True)
                    return {"status": "pass", "published": False, "shadow": str(shadow),
                            "state": prepared["story"]["state"], "idempotent": True}
                raise DailyStyleMError(f"shadow output ชื่อชนและ hash ต่าง: {shadow}")
            public = stage.rename(stage.with_name(stage.name + "-public"))
            shadow.mkdir(parents=True)
            os.replace(public, shadow / "public")
            _write_internal(prepared, shadow / "evidence", package, production_write=False)
            return {"status": "pass", "published": False, "shadow": str(shadow),
                    "state": prepared["story"]["state"], "idempotent": False}

        primary = day_dir / FOLDER
        lane = day_dir / "0-ขึ้นเว็บวันนี้" / LANE_FOLDER
        existing = [target for target in (primary, lane) if target.exists()]
        if existing:
            if len(existing) == 2 and all(_same_package(target, package["files"])
                                          for target in (primary, lane)):
                _write_internal(prepared, internal, package, production_write=True)
                return {"status": "pass", "published": True, "idempotent": True,
                        "directory": str(primary), "lane": str(lane),
                        "state": prepared["story"]["state"], "files": package["files"]}
            raise DailyStyleMError("Style M output ชื่อชนและ hash ต่าง — HOLD ห้าม overwrite")
        day_dir.mkdir(parents=True, exist_ok=True)
        lane.parent.mkdir(parents=True, exist_ok=True)
        primary_stage = stage
        lane_stage = Path(tempfile.mkdtemp(prefix=".style-m-lane-", dir=day_dir))
        shutil.copy2(primary_stage / package["article"], lane_stage / package["article"])
        shutil.copy2(primary_stage / package["image"], lane_stage / package["image"])
        primary_created = False
        try:
            os.replace(primary_stage, primary)
            primary_created = True
            os.replace(lane_stage, lane)
        except Exception:
            if primary_created and primary.exists():
                shutil.rmtree(primary)
            shutil.rmtree(lane_stage, ignore_errors=True)
            raise
        try:
            _write_internal(prepared, internal, package, production_write=True)
        except Exception:
            # A round is not successful until its evidence is durable.  If that
            # final gate fails, remove only the two M directories created by this
            # invocation so no production package is left behind after FAIL.
            shutil.rmtree(primary, ignore_errors=True)
            shutil.rmtree(lane, ignore_errors=True)
            raise
        return {"status": "pass", "published": True, "idempotent": False,
                "directory": str(primary), "lane": str(lane),
                "article": str(primary / package["article"]),
                "image": str(primary / package["image"]),
                "state": prepared["story"]["state"], "files": package["files"]}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


__all__ = ["ASSET", "ASSETS", "CONTRACT_VERSION", "DailyStyleMError",
           "DailyStyleMNotDue", "FOLDER", "INTERNAL_FOLDER", "LANE_FOLDER",
           "STYLE_ID", "STYLE_LETTER", "STYLE_NAME", "TIMEFRAMES",
           "daily_cutoff", "load_prior_fingerprint", "normalize_news", "prepare", "run_round"]
