"""Local/production boundary for Style M M-PROD/v7."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from tools import intraday_bars, style_m_v7_contract, style_m_v7_renderer, style_m_v7_risk, style_m_v7_story, style_m_v7_writer

STYLE_ID = "m_btcusd_h1_visual"
STYLE_LETTER = "M"
STYLE_NAME = "Style M v7 — BTCUSD H1 + ADR14"
ASSET = "btcusd"
ASSETS = (ASSET,)
TIMEFRAMES = ("1h",)
FOLDER = "M-BTCUSD-H1-Visual-Daily"
LANE_FOLDER = "05-BTCUSD-Style-M"
INTERNAL_FOLDER = "style-m-v7"
CONTRACT_VERSION = "M-PROD/v7"
PUBLIC_STYLE_ID = "m_btcusd_h1_visual_daily"


class DailyStyleMError(RuntimeError):
    pass


def _cutoff(value):
    if isinstance(value, datetime):
        result = value
    elif value is None:
        result = datetime.now(tz=timezone.utc)
    else:
        try: result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc: raise DailyStyleMError("cutoff_at ต้องเป็น ISO-8601") from exc
    if result.tzinfo is None: raise DailyStyleMError("cutoff_at ต้องมี timezone")
    return result.astimezone(style_m_v7_story.BANGKOK).replace(minute=0, second=0, microsecond=0)


def prepare(*, cutoff_at=None, fetcher=intraday_bars.fetch_rows) -> dict:
    cutoff = _cutoff(cutoff_at)
    meta, raw_rows, label = fetcher(ASSET, timeframe="1h", outputsize=1000)
    # canonical story trims forming bars and validates closed-H1 ordering;
    # intraday gate is retained as a separate evidence record.
    try:
        closed_rows, basis = intraday_bars.evaluate(raw_rows, asset=ASSET, timeframe="1h", now=cutoff)
        finding = intraday_bars.verify(basis, asset=ASSET, bar_at=closed_rows[-1]["at"], now=cutoff)
        if finding: raise DailyStyleMError(f"closed H1 gate: {finding}")
    except (IndexError, KeyError, ValueError) as exc:
        raise DailyStyleMError("closed H1 evidence invalid") from exc
    built = style_m_v7_story.build(closed_rows, cutoff=cutoff, source_label=label, source_meta=meta)
    try:
        vol = style_m_v7_risk.adr14(closed_rows, cutoff=cutoff)
        story = style_m_v7_risk.apply_policy(built["story"], volatility=vol)
    except style_m_v7_risk.RiskUnavailable as exc:
        story = dict(built["story"])
        story["state"] = "NO_PLAN"
        story["risk_geometry"] = {"policy_id": style_m_v7_risk.POLICY_ID,
                                   "volatility": {"metric": "ADR14", "value": None, "length": 14},
                                   "no_plan_reason": exc.reason_code}
        for plan in story["scenarios"].values():
            plan.update({"state": "NO_PLAN", "entry_low": None, "entry_high": None,
                         "sl": None, "tp1": None, "tp2": None, "risk": None,
                         "rr1": None, "rr2": None, "no_plan_reason": exc.reason_code})
    prepared = {**built, "story": story, "cutoff": cutoff, "basis": basis}
    facts = style_m_v7_contract.build(story, built["rows"])
    markdown = style_m_v7_writer.compose({"story": story, "facts": facts})
    style_m_v7_writer.validate(markdown, story, facts)
    prepared.update({"facts": facts, "markdown": markdown,
                     "parity": style_m_v7_contract.parity_report(facts, markdown=markdown),
                     "image_name": style_m_v7_writer.IMAGE_NAME.format(date=cutoff.strftime("%Y-%m-%d"))})
    prepared["idempotency_key"] = hashlib.sha256(json.dumps(
        {"contract": CONTRACT_VERSION, "policy": style_m_v7_risk.POLICY_ID,
         "cutoff": cutoff.isoformat(), "source": story["source_sha256"]}, sort_keys=True).encode()).hexdigest()
    return prepared


def run_shadow(*, root: Path, cutoff_at=None, fetcher=intraday_bars.fetch_rows) -> dict:
    prepared = prepare(cutoff_at=cutoff_at, fetcher=fetcher)
    target = Path(root) / prepared["cutoff"].strftime("%d-%m-%Y") / ASSET / "internal" / (INTERNAL_FOLDER + "-" + prepared["idempotency_key"][:12])
    if target.exists():
        manifest = target / "manifest.json"
        if manifest.is_file():
            existing = json.loads(manifest.read_text(encoding="utf-8"))
            if existing.get("idempotency_key") == prepared["idempotency_key"]:
                expected = existing.get("files") or {}
                actual = {name: hashlib.sha256((target / "public" / name).read_bytes()).hexdigest()
                          for name in expected if (target / "public" / name).is_file()}
                if actual == expected:
                    return {"status": "pass", "published": False, "shadow": str(target), "idempotent": True}
        raise DailyStyleMError(f"v7 shadow collision: {target}")
    public = target / "public"; public.mkdir(parents=True)
    article = public / "btc.md"; image = public / prepared["image_name"]
    article.write_text(prepared["markdown"], encoding="utf-8")
    render = style_m_v7_renderer.render(prepared["story"], prepared["rows"], image)
    evidence = {"schema": "style-m-v7-daily-manifest/v1", "contract_version": CONTRACT_VERSION,
                "policy_id": style_m_v7_risk.POLICY_ID, "production_write": False,
                "external_publish": False, "story": prepared["story"], "facts": prepared["facts"],
                "claim_parity": prepared["parity"], "renderer": render,
                "idempotency_key": prepared["idempotency_key"],
                "files": {"btc.md": hashlib.sha256(article.read_bytes()).hexdigest(),
                          image.name: hashlib.sha256(image.read_bytes()).hexdigest()}}
    (target / "manifest.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "pass", "published": False, "shadow": str(target), "article": str(article),
            "image": str(image), "idempotent": False, "state": prepared["story"]["state"]}


def run_round(*, asset: str = ASSET, publish_root: Path = Path("../output"),
              work_root: Path = Path("../work/build"), cutoff_at=None,
              fetcher=intraday_bars.fetch_rows, publish: bool = True, **_kwargs) -> dict:
    """Run the v7 package boundary; callers must perform promotion separately.

    The implementation always records a local evidence package first.  This
    task intentionally keeps the route local-only, so ``publish`` is retained
    as an API compatibility flag but never creates an external side effect.
    """
    del publish_root, publish
    if asset != ASSET:
        raise DailyStyleMError("Style M v7 รองรับเฉพาะ btcusd")
    return run_shadow(root=work_root, cutoff_at=cutoff_at, fetcher=fetcher)


__all__ = ["STYLE_ID", "STYLE_LETTER", "ASSET", "ASSETS", "TIMEFRAMES", "FOLDER", "LANE_FOLDER",
           "INTERNAL_FOLDER", "CONTRACT_VERSION", "prepare", "run_shadow", "run_round", "DailyStyleMError"]
