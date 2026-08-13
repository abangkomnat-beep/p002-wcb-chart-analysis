"""ตัวสั่งงานของ Style K pilot — แยกขั้นวิเคราะห์กับขั้นวัดผลออกจากกันด้วยคำสั่งคนละตัว

ที่ต้องเป็นคนละคำสั่ง ไม่ใช่ธงในคำสั่งเดียว: ขั้นวัดผลต้องรันหลัง freeze ผ่านแล้ว
ถ้าอยู่ในคำสั่งเดียวกัน วันหนึ่งจะมีคนเผลอรันรวดเดียวแล้วชั้นวิเคราะห์เห็นผลจริง

    python -m tools.style_k_pilot inventory
    python -m tools.style_k_pilot analyze     # evidence + selector + scenario + freeze
    python -m tools.style_k_pilot golden       # เลือก Golden Sample ก่อนเปิดผล
    python -m tools.style_k_pilot evaluate     # เปิดผลจริง (ต้องมี freeze ครบก่อน)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools import (style_k_dataset as ds, style_k_evaluator as ev,
                   style_k_renderer as rd, style_k_scenarios as sc,
                   style_k_selector as sel, style_k_techniques as tk,
                   style_k_writer as wr)

PILOT = ds.PILOT_ROOT
INVENTORY_PATH = PILOT / "inventory" / "data-inventory.json"
GOLDEN_PATH = PILOT / "inventory" / "golden-selection.json"

BTC_REFRESH = PILOT / "inventory" / "btcusd.evaluation-refresh.snapshot.json"
XAU_OUTCOME = ds.BUILD_ROOT / "2026-08-13T02-53Z-daily" / "xauusd" / "internal" / "raw.snapshot.json"

OUTCOME_SOURCES = {"xauusd": XAU_OUTCOME, "btcusd": BTC_REFRESH}
EXTRA_SOURCES = {"btcusd": [BTC_REFRESH]}

# 2 sessions × 2 assets = 4 บท (ขั้นต่ำที่การันตี) · 4 sessions × 2 assets = 8 บท (เป้าหมาย)
MINIMUM_GOLDEN_SESSIONS = 2
TARGET_GOLDEN_SESSIONS = 4


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _analysis_dir(entry: dict) -> Path:
    return PILOT / "analysis" / entry["session_date"] / entry["asset"]


def _evaluation_dir(entry: dict) -> Path:
    return PILOT / "evaluation" / entry["session_date"] / entry["asset"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- คำสั่ง

def command_inventory(_args) -> int:
    config = ds.load_config()
    inventory = ds.build_inventory(config=config, extra_sources=EXTRA_SOURCES)
    problems = ds.inventory_problems(inventory)
    _write(INVENTORY_PATH, inventory)
    tiers = {}
    for entry in inventory["sessions"]:
        tiers[entry["confidence_tier"]] = tiers.get(entry["confidence_tier"], 0) + 1
    print(f"inventory: {len(inventory['sessions'])} entries → {INVENTORY_PATH}")
    print(f"  tier: {tiers}")
    for problem in problems:
        print(f"  ✗ {problem}")
    return 1 if problems else 0


def command_analyze(_args) -> int:
    config = ds.load_config()
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    config_hash = ds.hash_payload(config)
    failures: list[str] = []

    for entry in inventory["sessions"]:
        if entry["confidence_tier"] == ds.TIER_C:
            failures.append(f"{entry['asset']} {entry['session_date']}: Tier C ข้าม")
            continue
        bundle = ds.analysis_bundle(entry)
        record = tk.build_evidence(bundle, config=config)
        selection = sel.select(record, config=config)
        manifest = sc.build_scenarios(record, selection)

        problems = sel.selection_problems(selection, record)
        problems += sc.scenario_problems(manifest, record)
        for problem in problems:
            failures.append(f"{entry['asset']} {entry['session_date']}: {problem}")

        target = _analysis_dir(entry)
        _write(target / "input-manifest.json", {
            "asset": entry["asset"], "session_date": entry["session_date"],
            "cutoff": entry["cutoff"], "confidence_tier": entry["confidence_tier"],
            "source_files": entry["source_files"], "source_hashes": entry["source_hashes"],
            "bar_count": len(bundle["rows"]), "last_bar": bundle["rows"][-1]["date"],
            "limitations": entry["limitations"], "horizons": entry["horizons"],
        })
        _write(target / "evidence.json", record)
        _write(target / "selection.json", selection)
        _write(target / "scenarios.json", manifest)
        _write(target / "analysis_freeze.json", {
            "asset": entry["asset"], "session_date": entry["session_date"],
            "cutoff": entry["cutoff"], "created_at": _now(),
            "input_hashes": entry["source_hashes"], "config_hash": config_hash,
            "code_revision": "worktree-dirty · ดู inventory/preflight-git-status.txt",
            "output_hashes": {
                "evidence.json": ds.hash_payload(record),
                "selection.json": ds.hash_payload(selection),
                "scenarios.json": ds.hash_payload(manifest),
            },
            "evaluation_opened": False,
        })

    print(f"analyze: เขียน {len(inventory['sessions'])} records ลง {PILOT / 'analysis'}")
    for failure in failures:
        print(f"  ✗ {failure}")
    return 1 if failures else 0


def command_golden(_args) -> int:
    """เลือก Golden Sample ตามลำดับตายตัวในแผนข้อ 14 — ก่อนเปิดผลจริงเสมอ

    เกณฑ์คือ coverage และความต่างของสภาวะตลาด ไม่ใช่ว่าใบไหนทายถูก (ยังไม่มีใครรู้)
    """
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    sessions = sorted({entry["session_date"] for entry in inventory["sessions"]})

    profile: dict[str, dict] = {}
    for session_date in sessions:
        coverage, regimes, ok = 0, [], True
        for entry in inventory["sessions"]:
            if entry["session_date"] != session_date:
                continue
            path = _analysis_dir(entry)
            selection = json.loads((path / "selection.json").read_text(encoding="utf-8"))
            record = json.loads((path / "evidence.json").read_text(encoding="utf-8"))
            manifest = json.loads((path / "scenarios.json").read_text(encoding="utf-8"))
            # ต้องเขียนบทได้จริงทั้งสองหัวข้อ — decision=article อย่างเดียวไม่พอ
            # เพราะยังตกที่ขั้นสร้างเงื่อนไขได้ถ้าไม่มีระดับราคาฝั่งใดฝั่งหนึ่ง
            if selection["decision"] != sel.DECISION_ARTICLE or not manifest["scenarios"]:
                ok = False
            coverage += sum(1 for value in record["readiness"].values() if value == "ready")
            regimes.append(selection["regime"])
        profile[session_date] = {"coverage": coverage, "regimes": regimes, "eligible": ok}

    eligible = [day for day in sessions if profile[day]["eligible"]]
    if len(eligible) < 2:
        print("golden: ✗ session ที่เขียนบทได้ครบสองหัวข้อมีไม่ถึง 2 วัน")
        return 1

    # 1) วันที่ coverage สูงสุด · เท่ากันเลือกวันใหม่กว่า
    first = max(eligible, key=lambda day: (profile[day]["coverage"], day))
    picked = [first]
    reasons = {first: f"coverage รวมสองหัวข้อสูงสุด ({profile[first]['coverage']} กลุ่มพร้อมใช้)"}

    # 2+) วันที่สภาวะตลาดต่างจากชุดที่เลือกไว้แล้วมากที่สุด · เท่ากันเลือกวันเก่ากว่า (ข้อ 14.3)
    def difference(day: str) -> int:
        return max(
            sum(1 for left, right in zip(profile[day]["regimes"], profile[chosen]["regimes"])
                if left != right)
            for chosen in picked
        )

    while len(picked) < min(TARGET_GOLDEN_SESSIONS, len(eligible)):
        rest = [day for day in eligible if day not in picked]
        nxt = max(rest, key=lambda day: (difference(day), profile[day]["coverage"],
                                         -sessions.index(day)))
        reasons[nxt] = (f"สภาวะตลาดต่างจากชุดที่เลือกไว้มากที่สุด ({profile[nxt]['regimes']}) "
                        f"· coverage {profile[nxt]['coverage']}")
        picked.append(nxt)

    payload = {
        "selected_at": _now(),
        "rule": "แผนข้อ 14 — เลือกก่อนเปิดผลจริง ห้ามใช้ผลลัพธ์เป็นเกณฑ์",
        "evaluation_opened": False,
        "sessions": picked,
        "minimum_sessions": picked[:MINIMUM_GOLDEN_SESSIONS],
        "target_sessions": picked,
        "reasons": reasons,
        "profile": profile,
    }
    _write(GOLDEN_PATH, payload)
    print(f"golden: เลือก {len(picked)} sessions → {GOLDEN_PATH}")
    for index, day in enumerate(picked, start=1):
        band = "ขั้นต่ำ" if index <= MINIMUM_GOLDEN_SESSIONS else "เป้าหมาย"
        print(f"  [{band}] {day}: {reasons[day]}")
    return 0


def command_write(_args) -> int:
    """สร้างบทและภาพของ session ที่ถูกเลือกเป็น Golden — ยังไม่แตะชั้นวัดผล"""
    config = ds.load_config()
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    if golden.get("evaluation_opened"):
        print("write: ✗ ชุด Golden ถูกเลือกหลังเปิดผลจริง — ปฏิเสธ")
        return 1

    failures: list[str] = []
    written = 0
    for entry in inventory["sessions"]:
        if entry["session_date"] not in golden["sessions"]:
            continue
        target = _analysis_dir(entry)
        record = json.loads((target / "evidence.json").read_text(encoding="utf-8"))
        selection = json.loads((target / "selection.json").read_text(encoding="utf-8"))
        manifest = json.loads((target / "scenarios.json").read_text(encoding="utf-8"))
        label = f"{entry['asset']} {entry['session_date']}"

        try:
            markdown, sidecar = wr.build_article(record=record, selection=selection,
                                                 manifest=manifest, config=config, entry=entry)
        except wr.ArticleUnbuildable as exc:
            failures.append(f"{label}: เขียนบทไม่ได้ — {exc}")
            continue

        bundle = ds.analysis_bundle(entry)
        display = config["assets"][entry["asset"]]["display"]
        images = [
            rd.render_overview(bundle=bundle, record=record, selection=selection,
                               output=target / "overview.webp", display=display),
            rd.render_scenarios(bundle=bundle, record=record, manifest=manifest,
                                output=target / "evidence-scenarios.webp", display=display),
        ]
        for meta in images:
            failures.extend(f"{label}: {problem}" for problem in rd.image_problems(
                meta, record=record, session_date=entry["session_date"], config=config))

        sidecar["images"] = images
        failures.extend(f"{label}: {problem}" for problem in wr.article_problems(
            markdown, sidecar, config=config, record=record))

        (target / "article.md").write_text(markdown, encoding="utf-8")
        _write(target / "article.json", sidecar)

        # บทกับภาพเกิดหลัง freeze ได้ แต่ห้ามทำให้หลักฐาน/สถานการณ์เปลี่ยน
        freeze_path = target / "analysis_freeze.json"
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        for name, payload in (("evidence.json", record), ("selection.json", selection),
                              ("scenarios.json", manifest)):
            if ds.hash_payload(payload) != freeze["output_hashes"][name]:
                failures.append(f"{label}: {name} เปลี่ยนหลัง freeze")
        freeze["output_hashes"]["article.md"] = ds.hash_payload(markdown)
        freeze["article_written_at"] = _now()
        _write(freeze_path, freeze)
        written += 1

    print(f"write: สร้างบท {written} ใบ + ภาพ {written * 2} ใบ")
    for failure in failures:
        print(f"  ✗ {failure}")
    return 1 if failures else 0


def command_evaluate(_args) -> int:
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    missing = [f"{entry['asset']} {entry['session_date']}"
               for entry in inventory["sessions"]
               if not (_analysis_dir(entry) / "analysis_freeze.json").exists()]
    if missing:
        print("evaluate: ✗ ยังไม่มี freeze ครบ — ห้ามเปิดผลจริง")
        for item in missing:
            print(f"    {item}")
        return 1

    failures: list[str] = []
    for entry in inventory["sessions"]:
        analysis = _analysis_dir(entry)
        freeze = json.loads((analysis / "analysis_freeze.json").read_text(encoding="utf-8"))
        manifest = json.loads((analysis / "scenarios.json").read_text(encoding="utf-8"))

        # ต้องพิสูจน์ว่าชั้นวิเคราะห์ไม่ถูกแก้ระหว่างทางก่อนจะยอมเปิดผล
        if ds.hash_payload(manifest) != freeze["output_hashes"]["scenarios.json"]:
            failures.append(f"{entry['asset']} {entry['session_date']}: scenarios.json ถูกแก้หลัง freeze")
            continue

        outcome = ds.evaluation_bundle(entry, outcome_sources=OUTCOME_SOURCES)
        evaluation = ev.evaluate_record(manifest, outcome)
        failures.extend(ev.evaluation_problems(evaluation))

        target = _evaluation_dir(entry)
        _write(target / "outcome-input.json", outcome)
        _write(target / "evaluation.json", evaluation)

        freeze["evaluation_opened"] = True
        freeze["evaluation_opened_at"] = _now()
        _write(analysis / "analysis_freeze.json", freeze)

    print(f"evaluate: เขียนผล {len(inventory['sessions'])} records ลง {PILOT / 'evaluation'}")
    for failure in failures:
        print(f"  ✗ {failure}")
    return 1 if failures else 0


COMMANDS = {
    "inventory": command_inventory,
    "analyze": command_analyze,
    "golden": command_golden,
    "write": command_write,
    "evaluate": command_evaluate,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Style K walk-forward pilot")
    parser.add_argument("command", choices=sorted(COMMANDS))
    args = parser.parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
