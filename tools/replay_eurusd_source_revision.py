"""Prepare, verify, and install the recoverable 2026-09-07 EUR/USD source revision.

The recovery is deliberately narrow: it only accepts the preserved historical
EUR/USD staging tree and its decision trace.  ``--apply`` is idempotence-hostile
on purpose: it refuses to replace a source tree whose prepared precondition no
longer matches, and retains the replaced tree plus source-layout manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


DATE = "2026-09-07"
WORK_DAY = "07-09-2026"
ARTICLE = "L/EURUSD/article.md"
IMAGES = (
    "eurusd-forex-daily-calendar-2026-09-07.webp",
    "eurusd-forex-daily-h1-plan.webp",
    "eurusd-forex-daily-m15-trigger.webp",
)


class RevisionError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _revision_root(project: Path) -> Path:
    return project / "work" / "source-revisions" / WORK_DAY / "eurusd-recovered-calendar-r1"


def _historical_paths(historical_run: Path) -> tuple[Path, Path]:
    staging = historical_run / "staging" / "eurusd"
    trace = historical_run / "evidence" / "eurusd-decision-trace.json"
    if not staging.is_dir() or not trace.is_file():
        raise RevisionError("historical run must contain staging/eurusd and the EURUSD decision trace")
    return staging, trace


def _revised_article(historical_article: Path) -> bytes:
    text = historical_article.read_text(encoding="utf-8")
    old = "![แผนที่ราคา H1 พร้อมกรอบย่อ H4 ของ EUR/USD](eurusd-forex-daily-h1-plan.webp)"
    new = "![แผนที่ราคา H1 ของ EUR/USD](images/eurusd-forex-daily-h1-plan.webp)"
    if old not in text:
        raise RevisionError("historical article lacks the expected obsolete H4 caption")
    text = text.replace(old, new, 1)
    for name in (IMAGES[0], IMAGES[2]):
        text = text.replace(f"]({name})", f"](images/{name})")
    if "กรอบย่อ H4" in text:
        raise RevisionError("obsolete H4 inset caption remains after revision")
    return text.encode("utf-8")


def _expected_event(trace: dict) -> dict:
    events = trace.get("events")
    if not isinstance(events, list) or len(events) != 1:
        raise RevisionError("decision trace must contain exactly one recovered calendar event")
    event = events[0]
    expected = {
        "source_id": "400922", "title_en": "Industrial Production MoM",
        "title_th": "ผลผลิตภาคอุตสาหกรรม (รายเดือน)", "at": "2026-09-07 13:00",
        "country": "EUR", "impact": "Medium", "previous": "0.2%", "forecast": "0.3%",
    }
    if not isinstance(event, dict) or any(event.get(k) != v for k, v in expected.items()):
        raise RevisionError("decision trace event does not match the approved recovered evidence")
    return event


def prepare(project: Path, historical_run: Path) -> Path:
    staging, trace_path = _historical_paths(historical_run)
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    event = _expected_event(trace)
    prepared = _revision_root(project) / "prepared" / "L" / "EURUSD"
    if prepared.exists():
        raise RevisionError("prepared revision already exists; verify it or remove it through an approved recovery")
    prepared.mkdir(parents=True)
    article = _revised_article(staging / "eurusd.md")
    (prepared / "article.md").write_bytes(article)
    image_dir = prepared / "images"
    image_dir.mkdir()
    for name in IMAGES:
        source = staging / name
        if not source.is_file():
            raise RevisionError(f"historical image missing: {name}")
        shutil.copyfile(source, image_dir / name)
    current = project / "output" / WORK_DAY / "TH-Thailand" / "L" / "EURUSD"
    if not (current / "article.md").is_file():
        raise RevisionError("current TH EURUSD source tree is missing")
    manifest = {
        "schema": "p002-source-revision/v1", "revision_id": "eurusd-recovered-calendar-r1",
        "source_business_date": DATE, "status": "PREPARED", "article_path": ARTICLE,
        "reason": "Replay preserved same-day evidence because current calendar evidence is incomplete.",
        "historical_run": str(historical_run), "historical_article_sha256": _sha(staging / "eurusd.md"),
        "decision_trace_sha256": _sha(trace_path), "recovered_event": event,
        "prepared": {"article_sha256": _sha(prepared / "article.md"),
                     "images": {name: _sha(image_dir / name) for name in IMAGES}},
        "replaced_precondition": {"article_sha256": _sha(current / "article.md"),
                                 "images": {name: _sha(current / "images" / name) for name in IMAGES}},
    }
    _write_json(_revision_root(project) / "manifest.json", manifest)
    return prepared


def verify(project: Path) -> dict:
    root = _revision_root(project)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise RevisionError("revision manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    prepared = root / "prepared" / "L" / "EURUSD"
    article = prepared / "article.md"
    text = article.read_text(encoding="utf-8")
    required = ["EUR · 07-09-2026 13:00 · ผลผลิตภาคอุตสาหกรรม (รายเดือน)",
                "![แผนที่ราคา H1 ของ EUR/USD](images/eurusd-forex-daily-h1-plan.webp)",
                "![ข่าวสำคัญประจำวันที่เกี่ยวข้องกับ EUR/USD](images/eurusd-forex-daily-calendar-2026-09-07.webp)"]
    if any(value not in text for value in required) or "กรอบย่อ H4" in text:
        raise RevisionError("prepared article does not meet recovered-calendar/caption contract")
    if _sha(article) != manifest["prepared"]["article_sha256"]:
        raise RevisionError("prepared article hash mismatch")
    for name in IMAGES:
        path = prepared / "images" / name
        if not path.is_file() or _sha(path) != manifest["prepared"]["images"][name]:
            raise RevisionError(f"prepared image hash mismatch: {name}")
    event = manifest.get("recovered_event", {})
    if event.get("source_id") != "400922" or event.get("actual") is not None:
        raise RevisionError("recovered event custody is invalid")
    return {"status": "PASS", "revision_id": manifest["revision_id"], "prepared": str(prepared)}


def apply(project: Path) -> dict:
    verify(project)
    root = _revision_root(project)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    current = project / "output" / WORK_DAY / "TH-Thailand" / "L" / "EURUSD"
    for name, expected in manifest["replaced_precondition"]["images"].items():
        if _sha(current / "images" / name) != expected:
            raise RevisionError(f"current source changed since prepare: {name}")
    if _sha(current / "article.md") != manifest["replaced_precondition"]["article_sha256"]:
        raise RevisionError("current source article changed since prepare")
    layout_path = project / "output" / WORK_DAY / "TH-Thailand" / "source-layout-manifest.json"
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    target = root / "prepared" / "L" / "EURUSD"
    with tempfile.TemporaryDirectory(dir=str(current.parent), prefix=".eurusd-revision-") as temp:
        temporary = Path(temp) / "EURUSD"
        shutil.copytree(target, temporary)
        backup = root / "backup" / "TH-Thailand-L-EURUSD"
        if backup.exists():
            raise RevisionError("backup already exists")
        (root / "backup").mkdir(exist_ok=True)
        shutil.move(str(current), str(backup))
        try:
            shutil.move(str(temporary), str(current))
            for entry in layout.get("articles", []):
                if entry.get("article_id") == "L-EURUSD":
                    entry["source_sha256"] = _sha(current / "article.md")
                    entry["source_bytes"] = (current / "article.md").stat().st_size
                    for image in entry.get("images", []):
                        image["sha256"] = _sha(current / "images" / image["name"])
                        image["bytes"] = (current / "images" / image["name"]).stat().st_size
            for rel in [ARTICLE, *(f"L/EURUSD/images/{name}" for name in IMAGES)]:
                layout["files"][rel] = _sha(project / "output" / WORK_DAY / "TH-Thailand" / rel)
            _write_json(layout_path, layout)
        except Exception:
            if current.exists():
                shutil.rmtree(current)
            shutil.move(str(backup), str(current))
            raise
    manifest["status"] = "APPLIED"
    manifest["applied"] = {"article_sha256": _sha(current / "article.md"),
                           "images": {name: _sha(current / "images" / name) for name in IMAGES}}
    _write_json(root / "manifest.json", manifest)
    return {"status": "APPLIED", "revision_id": manifest["revision_id"], "output": str(current)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--historical-run")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    project = Path(args.project_root).resolve()
    if args.prepare:
        if not args.historical_run:
            parser.error("--prepare requires --historical-run")
        result = {"status": "PREPARED", "prepared": str(prepare(project, Path(args.historical_run).resolve()))}
    elif args.verify:
        result = verify(project)
    else:
        result = apply(project)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
