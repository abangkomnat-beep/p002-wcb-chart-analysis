"""Isolated Style M v6 shadow runner.

This module deliberately has no production-write path.  It is the integration
checkpoint for validating the new oracle, writer and renderer together.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from tools import (intraday_bars, style_m_v6_contract, style_m_v6_renderer,
                   style_m_v6_story, style_m_v6_writer)


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


__all__ = ["run_shadow"]
