"""ตัวรัน Style K รายวัน — ผลผลิตภายในที่ `run_daily` เรียกอัตโนมัติ

สถานะหลังคำสั่งผู้ใช้ 2026-08-18:

- `run_daily` เรียกตัวรันนี้เป็นค่าตั้งต้นเฉพาะหัวข้อที่เปิดใน
  `config/style_k_pilot.json`; สั่งข้ามได้ด้วย `--skip-style-k`
- Style K ยังเป็น pilot ภายใน (`published: false` ทุกใบ) และไม่เข้า
  `0-ขึ้นเว็บวันนี้/`
- ความล้มเหลวถูกรายงานแยกและไม่ทำให้บทเว็บประจำวันหาย
- ไฟล์นี้ยังเรียกตรงได้ เพื่อรัน/ตรวจ Style K โดยไม่ต้องสร้างสไตล์อื่น

สายในไฟล์นี้ต่อท่อจากของที่มีอยู่ล้วน ๆ: ดึงแท่งผ่าน `wcb_series_source` (มีด่านความสด
ในตัว — ข้อมูลค้างคือหยุด ไม่ใช่เขียนบทจากของเก่า) → เดินชั้นวิเคราะห์/เขียนของ Style K
ที่ผ่านด่าน pilot มาแล้วทุกตัว → วางบทให้อ่านที่ `output/style-k-daily/<วัน>/`

กติกาที่คงจาก pilot ทุกข้อ: แท่งท้ายถือว่ายังไม่ปิด · freeze ก่อนเปิดผล ·
no_trade คือคำตอบที่ถูกต้อง · ไม่แตะ production/publishing ใด ๆ
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import style_k_dataset as ds          # noqa: E402
from tools import style_k_renderer as rd         # noqa: E402
from tools import style_k_scenarios as sc        # noqa: E402
from tools import style_k_selector as sel        # noqa: E402
from tools import style_k_techniques as tk       # noqa: E402
from tools import style_k_writer as wr           # noqa: E402
from tools import wcb_series_source as series    # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DAILY = PROJECT_ROOT / "work" / "style-k-daily"
READER_OUT = PROJECT_ROOT / "output" / "style-k-daily"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load_config() -> dict:
    """จุดเชื่อมสาธารณะสำหรับตัวห่อรอบวัน — ไม่ให้ผู้เรียกพึ่ง `ds` ภายในโมดูล."""
    return ds.load_config()


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _tier(session_date: str, captured: date, config: dict) -> str:
    lag = (captured - date.fromisoformat(session_date)).days
    return ds.TIER_A if lag <= config["tier_rule"]["a_max_capture_lag_days"] else ds.TIER_B


def run_asset(asset: str, config: dict, *, now: datetime | None = None,
              fetch=series.fetch_asset_rows) -> dict:
    """ดึงข้อมูล → วิเคราะห์ → freeze → เขียนบท ของหนึ่งหัวข้อ · คืน dict สรุปผล

    โยนข้อยกเว้นของชั้นดึงข้อมูล (`SeriesStaleData`/`SeriesUnavailable`) ออกไปตรง ๆ —
    ผู้เรียกตัดสินใจว่ารายงานยังไง ห้ามกลืนแล้วเขียนบทจากของค้าง
    """
    now = now or _now()
    stamp = now.strftime("%Y-%m-%dT%H-%MZ")
    meta, rows, source = fetch(asset)

    closed = ds.closed_rows(rows)
    if not closed:
        raise series.SeriesUnavailable(f"{asset}: ไม่มีแท่งที่ปิดแล้วเลยหลังตัดแท่งท้าย")
    session_date = closed[-1]["date"]

    # snapshot เก็บเสมอ — เป็นหลักฐาน point-in-time ให้ตรวจย้อน/ทำ evaluation ทีหลัง
    snapshot_rel = Path("work") / "style-k-daily" / "snapshots" / stamp / f"{asset}.snapshot.json"
    snapshot_path = PROJECT_ROOT / snapshot_rel
    _write(snapshot_path, {
        "captured_at": now.isoformat(timespec="seconds"),
        "cutoff_at": now.isoformat(timespec="seconds"),
        "asset": asset, "source": source, "meta": meta, "rows": rows,
    })

    tier = _tier(session_date, now.date(), config)
    bundle = {
        "asset": asset,
        "session_date": session_date,
        "cutoff": f"{session_date}T23:59:59+00:00",
        "confidence_tier": tier,
        "rows": ds.rows_upto(closed, session_date),
        "source_files": [snapshot_rel.as_posix()],
        "source_hashes": {snapshot_rel.as_posix(): ds.sha256_of(snapshot_path)},
        "limitations": ([] if tier == ds.TIER_A
                        else [f"เก็บช้ากว่าวันปิด {(now.date() - date.fromisoformat(session_date)).days} วัน"]),
    }

    record = tk.build_evidence(bundle, config=config)
    selection = sel.select(record, config=config)
    manifest = sc.build_scenarios(record, selection)
    problems = sel.selection_problems(selection, record)
    problems += sc.scenario_problems(manifest, record)

    target = DAILY / session_date / asset
    if (target / "analysis_freeze.json").exists():
        old = json.loads((target / "analysis_freeze.json").read_text(encoding="utf-8"))
        if old["output_hashes"]["evidence.json"] != ds.hash_payload(record):
            # แท่งของ session เดิมเปลี่ยนค่า = provider แก้ย้อนหลัง — ห้ามเขียนทับเงียบ
            raise RuntimeError(
                f"{asset} {session_date}: หลักฐานไม่ตรงกับ freeze ที่มีอยู่ "
                f"(ค่าอาจถูกแก้ย้อนหลัง) — หยุดให้คนดู ไม่เขียนทับ")

    entry = {"asset": asset, "session_date": session_date, "cutoff": bundle["cutoff"],
             "limitations": bundle["limitations"]}
    _write(target / "input-manifest.json", {
        "asset": asset, "session_date": session_date, "cutoff": bundle["cutoff"],
        "confidence_tier": tier, "source_files": bundle["source_files"],
        "source_hashes": bundle["source_hashes"], "bar_count": len(bundle["rows"]),
        "last_bar": bundle["rows"][-1]["date"], "limitations": bundle["limitations"],
    })
    _write(target / "evidence.json", record)
    _write(target / "selection.json", selection)
    _write(target / "scenarios.json", manifest)
    _write(target / "analysis_freeze.json", {
        "asset": asset, "session_date": session_date, "cutoff": bundle["cutoff"],
        "created_at": now.isoformat(timespec="seconds"),
        "input_hashes": bundle["source_hashes"], "config_hash": ds.hash_payload(config),
        "output_hashes": {
            "evidence.json": ds.hash_payload(record),
            "selection.json": ds.hash_payload(selection),
            "scenarios.json": ds.hash_payload(manifest),
        },
        "evaluation_opened": False,
    })

    result = {"asset": asset, "session_date": session_date, "tier": tier,
              "decision": selection["decision"], "problems": problems,
              "article": None, "no_trade_reason": manifest.get("no_trade_reason")}

    reader_dir = READER_OUT / session_date
    try:
        markdown, sidecar = wr.build_article(record=record, selection=selection,
                                             manifest=manifest, config=config, entry=entry)
    except wr.ArticleUnbuildable as exc:
        # ไม่มี setup = คำตอบที่ถูกต้อง — บันทึกให้คนอ่านเห็น ไม่ใช่เงียบหาย
        note = (f"# Style K — {asset} {session_date}\n\n"
                f"วันนี้ไม่มีบท: {exc}\n\nการไม่แต่งระดับขึ้นเองคือพฤติกรรมที่ถูกต้องของสไตล์นี้\n")
        (reader_dir).mkdir(parents=True, exist_ok=True)
        (reader_dir / f"{asset}-no-trade.md").write_text(note, encoding="utf-8")
        return result

    images = [
        rd.render_overview(bundle=bundle, record=record, selection=selection,
                           output=target / "overview.webp",
                           display=config["assets"][asset]["display"]),
        rd.render_scenarios(bundle=bundle, record=record, manifest=manifest,
                            output=target / "evidence-scenarios.webp",
                            display=config["assets"][asset]["display"]),
    ]
    for image_meta in images:
        problems += rd.image_problems(image_meta, record=record,
                                      session_date=session_date, config=config)
    sidecar["images"] = images
    problems += wr.article_problems(markdown, sidecar, config=config, record=record)

    (target / "article.md").write_text(markdown, encoding="utf-8")
    _write(target / "article.json", sidecar)

    # สำเนาฉบับอ่านสำหรับผู้ใช้ — บท + ภาพ อยู่ที่เดียวเปิดง่าย
    reader_dir.mkdir(parents=True, exist_ok=True)
    (reader_dir / f"{asset}.md").write_text(markdown, encoding="utf-8")
    for name in ("overview.webp", "evidence-scenarios.webp"):
        (reader_dir / f"{asset}-{name}").write_bytes((target / name).read_bytes())

    result["article"] = str(reader_dir / f"{asset}.md")
    result["problems"] = problems
    result["word_count"] = sidecar["word_count"]
    return result


def main(argv: list[str] | None = None) -> int:
    # Windows ภาษาไทยมักเปิด stdout เป็น cp874 ซึ่งพิมพ์ ✓/✗ ไม่ได้ — ตั้งก่อน log
    # (ใช้หลักเดียวกับ run_daily/build_daily_package)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="Style K รายวัน (ผลผลิตภายในเท่านั้น)")
    parser.add_argument("--asset", action="append",
                        help="จำกัดหัวข้อ (ค่าตั้งต้น: ทุกหัวข้อใน config)")
    args = parser.parse_args(argv)

    config = load_config()
    assets = args.asset or list(config["assets"])
    failures: list[str] = []

    for asset in assets:
        try:
            result = run_asset(asset, config)
        except (series.SeriesStaleData, series.SeriesUnavailable, RuntimeError) as exc:
            failures.append(f"{asset}: {exc}")
            print(f"✗ {asset}: {exc}")
            continue
        if result["article"]:
            print(f"✓ {asset} {result['session_date']} tier {result['tier']} "
                  f"คำ {result['word_count']} → {result['article']}")
        else:
            print(f"✓ {asset} {result['session_date']} tier {result['tier']} "
                  f"no_trade: {result['no_trade_reason'] or result['decision']}")
        for problem in result["problems"]:
            failures.append(f"{asset}: {problem}")
            print(f"  ✗ {problem}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
