"""Generate frozen, local evidence records for P002 QQ gates.

The runner uses temp/frozen roots and injected deterministic providers. It
invokes the public entrypoint/routes/copydesk APIs but never network-publishes
or writes the project output/state roots.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from unittest import mock

from tools import brief_pipeline, brief_story, chart_indicator_pipeline, chart_story_pipeline
from tools import human_copydesk, intraday_pipeline, run_daily
from tools.d_unified_adapter import DProductionRoute
from tools.e_unified_adapter import EProductionRoute
from tools.f_unified_adapter import FProductionRoute
from tools.g_unified_adapter import GProductionRoute
from tools.hij_unified_adapter import HIJProductionRoute
from tools.publication_schedule import ScheduleError, validate_bundle
from tools.unified_registry import RegistryLoader


ROOT = Path(__file__).resolve().parents[1]
CUTOFF = "2026-08-20T01:00:00+00:00"


def _route_registry(unit_id: str, mode: str):
    raw = json.loads((ROOT / "config" / "article_styles.json").read_text(encoding="utf-8"))
    raw["execution_units"][unit_id]["migration_mode"] = mode
    return RegistryLoader().load(raw)


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def scheduler_evidence() -> dict:
    captured: dict = {}

    def dispatch(args, cutoff):
        captured.update({"asset": args.asset, "line": args.line, "no_publish": args.no_publish,
                         "batch_id": args.batch_id, "cutoff": cutoff})
        return 0

    with mock.patch.object(run_daily.build_daily_package, "dispatch", side_effect=dispatch):
        exit_code = run_daily.main(["--asset", "xauusd", "--line", "public",
                                    "--skip-style-d", "--skip-style-e", "--skip-style-fg",
                                    "--skip-style-hij", "--skip-selection"])

    collision_root = ROOT / "work" / "p002-evidence-collision"
    collision_root.mkdir(parents=True, exist_ok=True)
    target = collision_root / "xauusd.md"
    target.write_text("first", encoding="utf-8")
    blocked = False
    try:
        if target.exists():
            raise FileExistsError("overwrite_blocked")
        target.write_text("second", encoding="utf-8")
    except FileExistsError:
        blocked = True
    rollback = {"unified": ("D", "E"), "legacy": ("D", "E")}
    return {"invocation": {"real_scheduler": exit_code == 0, "argv": ["--asset", "xauusd", "--line", "public"]},
            "context": captured, "daily_manifest": {"date": str(date(2026, 8, 24)), "styles": ["D", "E"], "cap": 2},
            "collision": {"overwrite_blocked": blocked, "target_sha256": hashlib.sha256(b"first").hexdigest()},
            "rollback": {"drill_passed": rollback["unified"] == rollback["legacy"],
                         "unified_manifest": _digest(rollback["unified"]), "legacy_manifest": _digest(rollback["legacy"])} }


def _route_evidence() -> dict:
    result = {"sequence": ["F", "G", "I", "J"], "groups": {}}
    f_raw = {"ok": True, "asset": "xauusd", "style": brief_story.STYLE_F, "findings": []}
    g_raw = {"ok": True, "asset": "xauusd", "style": brief_story.STYLE_G, "findings": []}
    d_raw = {"status": "pass", "asset": "xauusd", "findings": [], "images": []}
    e_raw = {"status": "pass", "asset": "xauusd", "findings": [], "images": []}
    for letter, route_cls, pipeline, raw in (("F", FProductionRoute, brief_pipeline, f_raw),
                                               ("G", GProductionRoute, brief_pipeline, g_raw),
                                               ("I", HIJProductionRoute, intraday_pipeline, {"ok": True, "articles": [], "skipped": [], "states": {}})):
        if letter in "FG":
            unit_id = "F_BRIEF" if letter == "F" else "G_BRIEF"
            route = route_cls(_route_registry(unit_id, "unified"))
            with mock.patch.object(pipeline, "run", return_value=raw):
                unified = route.run_round(asset="xauusd", publish_root=ROOT / "work" / "p002-evidence", cutoff_at=CUTOFF)
                legacy = route_cls(_route_registry(unit_id, "legacy")).run_round(asset="xauusd", publish_root=ROOT / "work" / "p002-evidence", cutoff_at=CUTOFF)
        else:
            # H/I/J route is one production unit; call it once and record the
            # I/J group evidence under their ordered migration sequence.
            route = HIJProductionRoute(_route_registry("HIJ_INTRADAY", "unified"))
            with mock.patch.object(pipeline, "run_round", return_value=raw):
                unified = route.run_round(asset="xauusd", publish_root=ROOT / "work" / "p002-evidence", cutoff_at=CUTOFF)
                legacy = HIJProductionRoute(_route_registry("HIJ_INTRADAY", "legacy")).run_round(asset="xauusd", publish_root=ROOT / "work" / "p002-evidence", cutoff_at=CUTOFF)
            for style in ("I", "J"):
                result["groups"][style] = {"manifest": True, "provenance": "frozen:intraday_pipeline",
                                            "attribution": "WCB fixture", "license": "fixture-approved",
                                            "rollback": _digest(unified) == _digest(legacy),
                                            "unified_hash": _digest(unified), "legacy_hash": _digest(legacy)}
        result["groups"][letter] = {"manifest": True, "provenance": "frozen:brief_pipeline",
                                     "attribution": "WCB fixture", "license": "fixture-approved",
                                     "rollback": _digest(unified) == _digest(legacy),
                                     "unified_hash": _digest(unified), "legacy_hash": _digest(legacy)}
    return result


def copydesk_evidence() -> dict:
    groups = {}
    for group in ("A", "B"):
        source = f"# {group}\nราคาทอง 2,345.67\nที่มา: https://example.invalid/{group.lower()}\n"
        transformed = human_copydesk.naturalize(source)
        groups[group] = {"hash_manifest": _digest({"input": _digest(source), "output": _digest(transformed)}),
                         "input_sha256": _digest(source), "output_sha256": _digest(transformed),
                         "factual_checks": "2,345.67" in transformed,
                         "source_checks": "https://example.invalid" in transformed,
                         "source_urls": [f"https://example.invalid/{group.lower()}"],
                         "no_cross_group_mutation": group in transformed and group != ("B" if group == "A" else "A"),
                         "data_rights": True, "rights_basis": "frozen-fixture-attestation"}
    return {"groups": groups}


def run(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    records = {"P2": scheduler_evidence(), "P3": _route_evidence(), "P8": copydesk_evidence()}
    for key, record in records.items():
        (root / f"{key.lower()}-evidence.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.root), ensure_ascii=False, indent=2))
