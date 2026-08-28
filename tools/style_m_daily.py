"""Daily production route for BTCUSD Style M (one H1 article + one image)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from tools import (image_output, intraday_bars, news_source, publish_layout,
                   style_m_renderer, style_m_story, style_m_writer)


STYLE_ID = "m_btcusd_h1_visual"
STYLE_LETTER = "M"
STYLE_NAME = "Style M — แผนภาพรายวัน H1"
ASSET = "btcusd"
ASSETS = (ASSET,)
TIMEFRAMES = ("1h",)
FOLDER = "M-BTCUSD-H1-Visual-Daily"
LANE_FOLDER = "05-BTCUSD-Style-M"
INTERNAL_FOLDER = "style-m"
CONTRACT_VERSION = "M-PROD/v2"


class DailyStyleMError(RuntimeError):
    """Style M cannot produce one verified, atomic daily set."""


class DailyStyleMNotDue(DailyStyleMError):
    """The Bangkok 11:00 cutoff has not occurred yet."""


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
    cutoff = moment.replace(hour=11, minute=0, second=0, microsecond=0)
    if moment < cutoff:
        raise DailyStyleMNotDue("Style M รอแท่ง H1 เวลา 11:00 น. ไทยปิดก่อน")
    return cutoff


def _fetch_h1(fetcher, cutoff: datetime) -> tuple[dict, list[dict], str, dict]:
    # Fetch using the provider's real current clock, then deterministically trim
    # the series to the approved 11:00 Bangkok cutoff below. Passing a historical
    # cutoff as the provider clock can make valid same-day data look shifted.
    meta, raw_rows, label = fetcher(ASSET, timeframe="1h", outputsize=500)
    closed_rows, basis = intraday_bars.evaluate(raw_rows, asset=ASSET, timeframe="1h", now=cutoff)
    finding = intraday_bars.verify(basis, asset=ASSET, bar_at=closed_rows[-1]["at"], now=cutoff)
    if finding:
        raise DailyStyleMError(f"closed H1 gate: {finding}")
    if basis.get("basis_close_at") != cutoff.isoformat():
        raise DailyStyleMError(
            f"latest closed H1 ไม่ตรง cutoff 11:00 ไทย: {basis.get('basis_close_at')}")
    return meta, closed_rows, label, basis


def normalize_news(report: dict) -> list[dict]:
    events: list[dict] = []
    for item in (report.get("items") or [])[:3]:
        url = str(item.get("link") or "").strip()
        published = news_source.parse_published(item.get("published_at"))
        tier = int(item.get("source_tier", news_source.UNKNOWN_SOURCE_TIER))
        if not url or published is None or tier > 2:
            continue
        local = published.astimezone(style_m_story.BANGKOK)
        events.append({
            "event_id": hashlib.sha256(f"{item.get('title')}|{url}".encode("utf-8")).hexdigest()[:16],
            "time_thai": local.strftime("%d/%m %H:%M น."),
            "title": str(item.get("title") or item.get("event") or "เหตุการณ์สำคัญ"),
            "source": str(item.get("source") or "Official source"),
            "url": url,
            "source_tier": tier,
            "retrieved_at": report.get("collected_at"),
            "risk_level": "สูง" if str(item.get("signal") or "").strip() else "เฝ้าระวัง",
            "impact": "อาจเพิ่มความผันผวนของ USD และสินทรัพย์เสี่ยง แต่ไม่กำหนดทิศทาง BTCUSD ล่วงหน้า",
            "plan_action": "ตรวจแท่ง H1 ที่ปิดแล้วอีกครั้ง และไม่เปลี่ยนแผนเทคนิคโดยอัตโนมัติ",
        })
    return events


def prepare(*, cutoff_at: str | datetime | None = None,
            fetcher=intraday_bars.fetch_rows,
            news_collector=news_source.collect_official) -> dict:
    cutoff = daily_cutoff(cutoff_at)
    meta, rows, label, basis = _fetch_h1(fetcher, cutoff)
    built = style_m_story.build(rows, cutoff=cutoff, source_label=label, source_meta=meta)
    try:
        news_report = news_collector(ASSET, now=cutoff.astimezone(timezone.utc))
    except Exception as exc:  # noqa: BLE001 — news source failure must fail closed
        raise DailyStyleMError(f"news evidence gate ใช้งานไม่ได้: {exc}") from exc
    events = normalize_news(news_report)
    markdown = style_m_writer.render(built["story"], events)
    article_qa = style_m_writer.validate(markdown, built["story"], events=events)
    idempotency = {
        "style": STYLE_LETTER, "asset": ASSET,
        "local_date": cutoff.strftime("%Y-%m-%d"), "cutoff": cutoff.isoformat(),
        "source_sha256": built["story"]["source_sha256"],
        "contract_version": CONTRACT_VERSION,
    }
    key = hashlib.sha256(json.dumps(idempotency, sort_keys=True).encode("utf-8")).hexdigest()
    return {**built, "basis": basis, "news_report": news_report, "events": events,
            "markdown": markdown, "article_qa": article_qa,
            "idempotency": {**idempotency, "key": key}, "cutoff": cutoff}


def _render_package(prepared: dict, folder: Path, renderer=None) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    article = folder / "btcusd.md"
    date_iso = prepared["cutoff"].strftime("%Y-%m-%d")
    image_name = style_m_writer.IMAGE_NAME.format(date=date_iso)
    image = folder / image_name
    article.write_text(prepared["markdown"], encoding="utf-8")
    render_result = (renderer or style_m_renderer).render(prepared["story"], prepared["rows"], image)
    image_output.verify(image)
    files = {path.name: {"sha256": _sha256(path), "bytes": path.stat().st_size}
             for path in (article, image)}
    return {"article": article.name, "image": image.name, "files": files,
            "render": render_result}


def _same_package(target: Path, files: dict) -> bool:
    if not target.is_dir():
        return False
    actual = {path.name: _sha256(path) for path in target.iterdir() if path.is_file()}
    expected = {name: record["sha256"] for name, record in files.items()}
    return actual == expected


def _write_internal(prepared: dict, target: Path, package: dict) -> None:
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
                    "qa-report.json": {"article": prepared["article_qa"], "image": package["render"],
                                       "production_write": True, "external_publish": False},
                    "manifest.json": {"schema": "style-m-daily-manifest/v1",
                                      "style": STYLE_LETTER, "asset": ASSET,
                                      "state": prepared["story"]["state"],
                                      "idempotency": prepared["idempotency"],
                                      "files": package["files"],
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
              renderer=None, publish: bool = True) -> dict:
    if asset != ASSET:
        raise DailyStyleMError("Style M รองรับเฉพาะ btcusd")
    prepared = prepare(cutoff_at=cutoff_at, fetcher=fetcher, news_collector=news_collector)
    cutoff = prepared["cutoff"]
    day = publish_layout.day_folder(cutoff.isoformat())
    day_dir = Path(publish_root) / day
    internal = Path(work_root) / day / ASSET / "internal" / INTERNAL_FOLDER
    shadow_parent = internal.parent
    shadow_parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".style-m-package-", dir=shadow_parent))
    try:
        package = _render_package(prepared, stage, renderer=renderer)
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
            _write_internal(prepared, shadow / "evidence", package)
            return {"status": "pass", "published": False, "shadow": str(shadow),
                    "state": prepared["story"]["state"], "idempotent": False}

        primary = day_dir / FOLDER
        lane = day_dir / "0-ขึ้นเว็บวันนี้" / LANE_FOLDER
        existing = [target for target in (primary, lane) if target.exists()]
        if existing:
            if len(existing) == 2 and all(_same_package(target, package["files"])
                                          for target in (primary, lane)):
                _write_internal(prepared, internal, package)
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
            _write_internal(prepared, internal, package)
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
           "daily_cutoff", "normalize_news", "prepare", "run_round"]
