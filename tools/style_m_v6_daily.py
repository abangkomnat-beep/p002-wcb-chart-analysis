"""Style M v6 daily route with shadow-first, collision-safe production output."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from tools import (image_output, intraday_bars, news_source, publish_layout,
                   public_number_policy,
                   style_m_daily as legacy_style_m_daily, style_m_v6_contract,
                   style_m_v6_renderer, style_m_v6_story, style_m_v6_writer,
                   trade_plan_public_adapters, trade_plan_public_contract)


STYLE_ID = legacy_style_m_daily.STYLE_ID
STYLE_LETTER = legacy_style_m_daily.STYLE_LETTER
STYLE_NAME = "Style M v6 — Donchian 24H + ADX14"
ASSET = style_m_v6_story.ASSET
ASSETS = (ASSET,)
TIMEFRAMES = (style_m_v6_story.TIMEFRAME,)
FOLDER = legacy_style_m_daily.FOLDER
LANE_FOLDER = legacy_style_m_daily.LANE_FOLDER
INTERNAL_FOLDER = "style-m-v6"
PUBLIC_STYLE_ID = "m_btcusd_h1_visual_daily"
CONTRACT_VERSION = style_m_v6_contract.CONTRACT_VERSION
DailyStyleMError = legacy_style_m_daily.DailyStyleMError
DailyStyleMNotDue = legacy_style_m_daily.DailyStyleMNotDue
daily_cutoff = legacy_style_m_daily.daily_cutoff


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _same_package(target: Path, files: dict) -> bool:
    if not target.is_dir():
        return False
    actual = {path.name: _sha256(path) for path in target.iterdir() if path.is_file()}
    return actual == {name: record["sha256"] for name, record in files.items()}


def _events(report: dict) -> list[dict]:
    try:
        return legacy_style_m_daily.normalize_news(report)[:1]
    except Exception:  # news is advisory and must not weaken the price-data gate
        return []


def _validate_visual_plan(prepared: dict, render: dict) -> None:
    if render.get("label_overlap_count") != 0:
        raise DailyStyleMError("visual QA: plan/reference labels overlap")
    facts = prepared["facts"]["facts"]
    expected = {
        side.upper(): {
            "trigger": facts[f"plan.{side}.trigger"],
            "entry_low": facts[f"plan.{side}.entry_low"],
            "entry_high": facts[f"plan.{side}.entry_high"],
            "sl": facts[f"plan.{side}.sl"],
            "tp1": facts[f"plan.{side}.tp1"],
            "tp2": facts[f"plan.{side}.tp2"],
        }
        for side in ("long", "short")
    }
    cards = render.get("plan_cards", [])
    actual = {item.get("side"): {field: item.get(field) for field in
                                  ("trigger", "entry_low", "entry_high",
                                   "sl", "tp1", "tp2")}
              for item in cards}
    if len(cards) != 2 or len(actual) != 2 or actual != expected:
        raise DailyStyleMError("visual QA: BUY/SELL cards ไม่ตรง canonical facts")
    expected_display_entry = {
        "LONG": expected["LONG"]["entry_high"],
        "SHORT": expected["SHORT"]["entry_low"],
    }
    if {item.get("side"): item.get("display_entry") for item in cards} != expected_display_entry:
        raise DailyStyleMError("visual QA: จุดเข้า Retest ในการ์ดไม่ตรงขอบแรกของ canonical zone")
    if any(text_box[0] < item["bbox"][0]
           or text_box[1] < item["bbox"][1]
           or text_box[2] > item["bbox"][2]
           or text_box[3] > item["bbox"][3]
           for item in cards for text_box in item["text_bboxes"]):
        raise DailyStyleMError("visual QA: plan card text ล้นกรอบ")
    references = render.get("reference_labels") or {}
    if references != {
            "buy_side": facts["zone.liquidity.buy_side_reference"],
            "sell_side": facts["zone.liquidity.sell_side_reference"]}:
        raise DailyStyleMError("visual QA: liquidity reference ไม่ตรง canonical facts")
    trap = render.get("trap_zone") or {}
    if trap != {"low": facts["zone.trap.low"], "high": facts["zone.trap.high"]}:
        raise DailyStyleMError("visual QA: trap zone ไม่ตรง canonical facts")
    layout = render.get("layout") or {}
    if (layout.get("visible_bars") != style_m_v6_renderer.VISIBLE_BARS
            or layout.get("plan_label_rail") is not None
            or len(render.get("price_axis", [])) != style_m_v6_renderer.PRICE_TICKS
            or len(render.get("time_axis", [])) != style_m_v6_renderer.TIME_TICKS):
        raise DailyStyleMError("visual QA: H1 axes/48-bar layout ไม่ตรง contract")


def prepare(*, cutoff_at: str | datetime | None = None,
            fetcher=intraday_bars.fetch_rows,
            news_collector=news_source.collect_official) -> dict:
    cutoff = daily_cutoff(cutoff_at)
    meta, raw_rows, label = fetcher(ASSET, timeframe="1h", outputsize=500)
    closed_rows, basis = intraday_bars.evaluate(raw_rows, asset=ASSET,
                                                 timeframe="1h", now=cutoff)
    finding = intraday_bars.verify(basis, asset=ASSET,
                                   bar_at=closed_rows[-1]["at"], now=cutoff)
    if finding or basis.get("basis_close_at") != cutoff.isoformat():
        raise DailyStyleMError(f"closed H1 gate: {finding or basis.get('basis_close_at')}")
    built = style_m_v6_story.build(closed_rows, cutoff=cutoff, source_label=label,
                                   source_meta=meta)
    try:
        news_report = news_collector(ASSET, now=cutoff.astimezone(timezone.utc))
    except Exception as exc:  # news remains a non-fatal advisory
        news_report = {"asset": ASSET, "items": [], "provider_status": "unavailable",
                       "error_class": type(exc).__name__}
    events = _events(news_report)
    image_name = f"btcusd-style-m-v6-h1-{cutoff:%Y-%m-%d}.webp"
    markdown = style_m_v6_writer.compose(built, events=events, image_name=image_name)
    facts = style_m_v6_contract.build(built["story"], built["rows"])
    style_m_v6_contract.validate(facts, story=built["story"])
    parity = style_m_v6_contract.parity_report(facts, markdown=markdown)
    if parity["status"] != "PASS":
        raise DailyStyleMError(f"v6 claim parity {parity['status']}: {parity['findings']}")
    key = hashlib.sha256(json.dumps({
        "contract": CONTRACT_VERSION, "asset": ASSET, "cutoff": cutoff.isoformat(),
        "source_sha256": built["story"]["source_sha256"], "events": events,
    }, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {**built, "cutoff": cutoff, "basis": basis, "news_report": news_report,
            "events": events, "markdown": markdown, "facts": facts, "parity": parity,
            "image_name": image_name, "idempotency_key": key}


def _render_package(prepared: dict, folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    article = folder / "btc.md"
    image = folder / prepared["image_name"]
    article.write_text(prepared["markdown"], encoding="utf-8")
    public_contract = trade_plan_public_adapters.style_m_v6(
        story=prepared["story"], article_name=article.name,
        article_bytes=article.read_bytes())
    if public_contract.get("publishable") is True:
        public_contract = trade_plan_public_adapters.bind_article(
            public_contract, article.read_bytes())
    contract_report = trade_plan_public_contract.validate(
        public_contract, article_name=article.name, article_bytes=article.read_bytes(),
        style_id=PUBLIC_STYLE_ID, asset="btc", publish_date=prepared["cutoff"].date(),
        expected_evidence_hash=prepared["story"]["source_sha256"])
    if contract_report["status"] != "PASS":
        raise DailyStyleMError(
            "public trade-plan contract: "
            + ", ".join(item["code"] for item in contract_report["findings"]))
    render = style_m_v6_renderer.render(prepared["story"], prepared["rows"], image)
    _validate_visual_plan(prepared, render)
    image_output.verify(image)
    files = {path.name: {"sha256": _sha256(path), "bytes": path.stat().st_size}
             for path in (article, image)}
    return {"article": article.name, "image": image.name, "render": render,
            "contract_payload": public_contract,
            "contract_report": contract_report, "files": files}


def _write_evidence(prepared: dict, target: Path, package: dict, *,
                    production_write: bool,
                    replace_existing: bool = False) -> None:
    repair_existing = False
    if target.exists():
        manifest = target / "manifest.json"
        if manifest.is_file():
            existing = json.loads(manifest.read_text(encoding="utf-8"))
            internal_contract_files = (
                target / "btc.trade-plan-public.json",
                target / "trade-plan-public-qa.json",
            )
            if existing.get("idempotency_key") == prepared["idempotency_key"]:
                if all(path.is_file() for path in internal_contract_files):
                    return
                repair_existing = True
        if not (replace_existing or repair_existing):
            raise DailyStyleMError(f"v6 evidence ชื่อชนและ hash ต่าง: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".style-m-v6-evidence-", dir=target.parent))
    backup_root: Path | None = None
    try:
        payloads = {
            "story.json": prepared["story"], "source-evidence.json": prepared["source_projection"],
            "candle-basis.json": prepared["basis"], "news-evidence.json": prepared["news_report"],
            "article-visual-facts.json": prepared["facts"],
            "claim-parity-report.json": prepared["parity"],
            "btc.trade-plan-public.json": package["contract_payload"],
            "trade-plan-public-qa.json": package["contract_report"],
            "qa-report.json": {"production_write": production_write,
                               "external_publish": False,
                               "number_policy": public_number_policy.POLICY_VERSION,
                               "renderer": package["render"]},
            "manifest.json": {"schema": "style-m-v6-daily-manifest/v1",
                              "contract_version": CONTRACT_VERSION,
                              "style": STYLE_LETTER, "asset": ASSET,
                              "cutoff": prepared["cutoff"].isoformat(),
                              "idempotency_key": prepared["idempotency_key"],
                              "files": package["files"],
                              "number_policy": public_number_policy.POLICY_VERSION,
                              "production_write": production_write,
                              "external_publish": False},
        }
        for name, payload in payloads.items():
            (stage / name).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if target.exists():
            backup_root = Path(tempfile.mkdtemp(
                prefix=".style-m-v6-evidence-replace-", dir=target.parent))
            os.replace(target, backup_root / "old")
        try:
            os.replace(stage, target)
        except Exception:
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            if backup_root is not None and (backup_root / "old").exists():
                os.replace(backup_root / "old", target)
            raise
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    finally:
        if backup_root is not None:
            shutil.rmtree(backup_root, ignore_errors=True)


def run_shadow(*, root: Path, cutoff_at: str | datetime | None = None,
               fetcher=intraday_bars.fetch_rows) -> dict:
    cutoff = (datetime.fromisoformat(str(cutoff_at).replace("Z", "+00:00"))
              if cutoff_at is not None else datetime.now(tz=timezone.utc))
    if cutoff.tzinfo is None:
        raise ValueError("cutoff_at ต้องมี timezone")
    cutoff = cutoff.astimezone(style_m_v6_story.BANGKOK)
    meta, raw_rows, label = fetcher(style_m_v6_story.ASSET, timeframe="1h", outputsize=500)
    closed_rows, basis = intraday_bars.evaluate(raw_rows, asset=style_m_v6_story.ASSET,
                                                 timeframe="1h", now=cutoff)
    finding = intraday_bars.verify(basis, asset=style_m_v6_story.ASSET,
                                   bar_at=closed_rows[-1]["at"], now=cutoff)
    if finding:
        raise RuntimeError(f"closed H1 gate: {finding}")
    prepared = style_m_v6_story.build(closed_rows, cutoff=cutoff, source_label=label,
                                      source_meta=meta)
    story = prepared["story"]
    markdown = style_m_v6_writer.compose(prepared, image_name="btcusd-style-m-v6-h1.webp")
    facts = style_m_v6_contract.build(story, prepared["rows"])
    style_m_v6_contract.validate(facts, story=story)
    parity = style_m_v6_contract.parity_report(facts, markdown=markdown)
    if parity["status"] != "PASS":
        raise RuntimeError(f"v6 claim parity {parity['status']}: {parity['findings']}")
    idempotency_key = hashlib.sha256(json.dumps({
        "contract": "M-PROD/v6", "asset": style_m_v6_story.ASSET,
        "cutoff": cutoff.isoformat(), "source_sha256": prepared["story"]["source_sha256"],
    }, sort_keys=True).encode("utf-8")).hexdigest()
    target = (Path(root) / cutoff.strftime("%d-%m-%Y") / style_m_v6_story.ASSET /
              "internal" / f"style-m-v6-shadow-{idempotency_key[:12]}")
    public = target / "public"
    if target.exists():
        manifest = target / "manifest.json"
        if manifest.is_file():
            existing = json.loads(manifest.read_text(encoding="utf-8"))
            if existing.get("idempotency_key") == idempotency_key:
                return {"status": "pass", "published": False, "shadow": str(target),
                        "article": str(public / "btc.md"),
                        "image": str(public / "btcusd-style-m-v6-h1.webp"),
                        "state": story["state"],
                        "scenario_states": {key: value["state"] for key, value in story["scenarios"].items()},
                        "adx14": story["indicators"]["adx14"], "idempotent": True}
        raise RuntimeError(f"v6 shadow collision: {target}")
    public.mkdir(parents=True, exist_ok=True)
    article = public / "btc.md"
    image = public / "btcusd-style-m-v6-h1.webp"
    article.write_text(markdown, encoding="utf-8")
    render = style_m_v6_renderer.render(story, prepared["rows"], image)
    evidence = {
        "schema": "style-m-v6-shadow-manifest/v1", "contract_version": "M-PROD/v6",
        "style": "M", "asset": style_m_v6_story.ASSET, "cutoff": story["cutoff"],
        "source_sha256": story["source_sha256"], "idempotency_key": idempotency_key,
        "production_write": False,
        "external_publish": False, "story": story, "candle_basis": basis,
        "facts": facts, "claim_parity": parity, "renderer": render,
        "files": {name: hashlib.sha256(path.read_bytes()).hexdigest()
                  for name, path in (("btc.md", article), (image.name, image))},
    }
    (target / "manifest.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "pass", "published": False, "shadow": str(target),
            "article": str(article), "image": str(image), "state": story["state"],
            "scenario_states": {key: value["state"] for key, value in story["scenarios"].items()},
            "adx14": story["indicators"]["adx14"], "idempotent": False}


def load_prior_fingerprint(_work_root: Path, _cutoff: datetime) -> None:
    """v6 has two daily scenarios and does not suppress duplicate no-plan copy."""
    return None


def run_round(*, asset: str = ASSET, publish_root: Path = Path("../output"),
              work_root: Path = Path("../work/build"),
              cutoff_at: str | datetime | None = None,
              fetcher=intraday_bars.fetch_rows,
              news_collector=news_source.collect_official,
              renderer=None, publish: bool = True,
              prior_fingerprint: dict | str | None = None) -> dict:
    del prior_fingerprint
    if asset != ASSET:
        raise DailyStyleMError("Style M v6 รองรับเฉพาะ btcusd")
    if renderer is not None:
        raise DailyStyleMError("production อนุญาตเฉพาะ canonical v6 renderer")
    prepared = prepare(cutoff_at=cutoff_at, fetcher=fetcher,
                       news_collector=news_collector)
    day = publish_layout.day_folder(prepared["cutoff"].isoformat())
    day_dir = Path(publish_root) / day
    internal = Path(work_root) / day / ASSET / "internal" / INTERNAL_FOLDER
    internal.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".style-m-v6-package-", dir=internal.parent))
    try:
        package = _render_package(prepared, stage)
        if not publish:
            shadow = internal.with_name(
                f"{INTERNAL_FOLDER}-shadow-{prepared['idempotency_key'][:12]}")
            if shadow.exists():
                if _same_package(shadow / "public", package["files"]):
                    shutil.rmtree(stage, ignore_errors=True)
                    return {"status": "pass", "published": False,
                            "shadow": str(shadow), "state": prepared["story"]["state"],
                            "idempotent": True}
                raise DailyStyleMError(f"v6 shadow ชื่อชนและ hash ต่าง: {shadow}")
            shadow.mkdir(parents=True)
            os.replace(stage, shadow / "public")
            _write_evidence(prepared, shadow / "evidence", package,
                            production_write=False)
            return {"status": "pass", "published": False,
                    "shadow": str(shadow),
                    "article": str(shadow / "public" / package["article"]),
                    "image": str(shadow / "public" / package["image"]),
                    "state": prepared["story"]["state"], "idempotent": False}

        primary = day_dir / FOLDER
        lane = day_dir / "0-ขึ้นเว็บวันนี้" / LANE_FOLDER
        existing = [target for target in (primary, lane) if target.exists()]
        if existing:
            if len(existing) == 2 and all(
                    _same_package(target, package["files"]) for target in (primary, lane)):
                _write_evidence(prepared, internal, package, production_write=True)
                shutil.rmtree(stage, ignore_errors=True)
                return {"status": "pass", "published": True, "idempotent": True,
                        "directory": str(primary), "lane": str(lane),
                        "state": prepared["story"]["state"], "files": package["files"]}
        # A user-requested rerun for the same publishing day is allowed to
        # replace stale output.  Move the old directories to a temporary
        # backup first so a failed write can restore both lanes atomically.
        backup_root: Path | None = None
        backups: list[tuple[Path, Path]] = []
        try:
            if existing:
                backup_root = Path(tempfile.mkdtemp(
                    prefix=".style-m-v6-replace-", dir=day_dir))
                try:
                    for index, target in enumerate(existing):
                        backup = backup_root / f"target-{index}"
                        os.replace(target, backup)
                        backups.append((target, backup))
                except Exception:
                    for target, backup in reversed(backups):
                        if backup.exists():
                            os.replace(backup, target)
                    raise
            day_dir.mkdir(parents=True, exist_ok=True)
            lane.parent.mkdir(parents=True, exist_ok=True)
            lane_stage: Path | None = None
            primary_created = False
            try:
                lane_stage = Path(tempfile.mkdtemp(prefix=".style-m-v6-lane-", dir=day_dir))
                shutil.copy2(stage / package["article"], lane_stage / package["article"])
                shutil.copy2(stage / package["image"], lane_stage / package["image"])
                os.replace(stage, primary)
                primary_created = True
                os.replace(lane_stage, lane)
                _write_evidence(prepared, internal, package, production_write=True,
                                replace_existing=bool(existing))
            except Exception:
                if primary_created:
                    shutil.rmtree(primary, ignore_errors=True)
                shutil.rmtree(lane, ignore_errors=True)
                if lane_stage is not None:
                    shutil.rmtree(lane_stage, ignore_errors=True)
                for target, backup in reversed(backups):
                    if backup.exists():
                        os.replace(backup, target)
                raise
            replaced_existing = bool(existing)
        finally:
            if backup_root is not None:
                shutil.rmtree(backup_root, ignore_errors=True)
        return {"status": "pass", "published": True, "idempotent": False,
                "directory": str(primary), "lane": str(lane),
                "article": str(primary / package["article"]),
                "image": str(primary / package["image"]),
                "state": prepared["story"]["state"], "files": package["files"],
                "replaced_existing": replaced_existing}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


__all__ = ["ASSET", "ASSETS", "CONTRACT_VERSION", "DailyStyleMError",
           "DailyStyleMNotDue", "FOLDER", "INTERNAL_FOLDER", "LANE_FOLDER",
           "STYLE_ID", "STYLE_LETTER", "STYLE_NAME", "TIMEFRAMES",
           "daily_cutoff", "load_prior_fingerprint", "prepare", "run_round",
           "run_shadow"]
