"""สายผลิตสไตล์ E — ดึงแท่งจริง → คำนวณ → ตรวจ → วางบท+ภาพสองใบเป็นชุด

หลัก fail-closed เดียวกับสายสไตล์ D: สร้าง candidate ใน temp และคงชุดเดิมไว้
จนกว่าบท ภาพ Fibonacci ภาพแผน และ internal contract จะผ่านครบ.

ขอบเขตควบคุมด้วย allowlist ของ Style E ใน `article_styles.json` — เปิด xauusd เดิม
และ usdjpy ตามคำสั่งผู้ใช้ 2026-08-21 · การขึ้นเว็บยังเป็นไปตาม
`publishing_policy.json` แยกจากสิทธิ์ผลิตบทภายใน
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import chart_indicator, chart_indicator_renderer, chart_indicator_writer  # noqa: E402
from tools import intraday_bars  # noqa: E402
from tools import (data_fetch_retry, image_output, public_number_policy,
                   trade_plan_public_adapters,
                   trade_plan_public_contract, wcb_source)  # noqa: E402
from tools import publish_layout, wcb_series_source  # noqa: E402

DEFAULT_ASSET = "xauusd"


def _publicize_style_e(markdown: str) -> str:
    """ใช้ whole-number policy กับราคา แต่คง Fibonacci ratios ซึ่งไม่ใช่ราคา."""
    ratios = [f"{value:g}" for value in
              [*chart_indicator.FIB_RATIOS, chart_indicator.EXTENSION_RATIO]
              if "." in f"{value:g}"]
    protected: dict[str, str] = {}
    for index, ratio in enumerate(ratios):
        marker = f"__P002_FIB_RATIO_{chr(65 + index)}__"
        markdown = re.sub(
            rf"(?<![\w.]){re.escape(ratio)}(?![\w.])", marker, markdown)
        protected[marker] = ratio
    markdown = public_number_policy.publicize(markdown)
    for marker, ratio in protected.items():
        markdown = markdown.replace(marker, ratio)
    return markdown


def _clear_stale(folder: Path, asset: str) -> bool:
    """ลบบท+ภาพทุกใบของหัวข้อ — ของรอบก่อนต้องไม่นอนปนหน้าตาเหมือนของสด

    ภาพกวาดด้วย glob เพราะชื่อไฟล์มีวันที่ (`xauusd-d1-indicators-<วัน>.webp`)
    และครอบชื่อยุคสองภาพ (`xauusd-1.png`/`-2.png`) ไปในตัว

    กวาด**ทุกนามสกุลที่ไม่ใช่ `.md`** โดยตั้งใจ — ตั้งแต่ย้ายไป `.webp` (08-09)
    โฟลเดอร์ของวันเดียวกันอาจมี `.png` ของรอบก่อนค้าง ถ้ากวาดเฉพาะนามสกุลใหม่
    รูปเก่าจะนอนอยู่คู่รูปใหม่โดยหน้าตาเหมือนของสด และเป็นรูปที่เว็บตีกลับ
    """
    removed = False
    targets = [folder / f"{asset}.md"] + [
        path for path in folder.glob(f"{asset}*") if path.suffix.lower() != ".md"]
    for path in targets:
        if path.exists():
            path.unlink()
            removed = True
    return removed


def _promote_set(folder: Path, candidates: dict[str, Path], *,
                 remove_after: list[Path], backup_root: Path) -> None:
    """Promote a complete Style E set with rollback if any replace fails."""
    folder.mkdir(parents=True, exist_ok=True)
    backup_root.mkdir(parents=True, exist_ok=True)
    backups: dict[Path, Path] = {}
    installed: list[Path] = []
    staged: list[Path] = []
    try:
        for name, source in candidates.items():
            destination = folder / name
            if destination.exists():
                backup = backup_root / name
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup)
                backups[destination] = backup
            local_stage = folder / f".{name}.p002-stage"
            shutil.copy2(source, local_stage)
            staged.append(local_stage)
        for name in candidates:
            local_stage = folder / f".{name}.p002-stage"
            destination = folder / name
            os.replace(local_stage, destination)
            installed.append(destination)
        for legacy in remove_after:
            if legacy.exists():
                backup = backup_root / legacy.name
                shutil.copy2(legacy, backup)
                backups[legacy] = backup
                legacy.unlink()
    except Exception:
        for path in staged:
            if path.exists():
                path.unlink()
        for destination in installed:
            if destination not in backups and destination.exists():
                destination.unlink()
        for destination, backup in backups.items():
            shutil.copy2(backup, destination)
        raise


def run(*, asset: str = DEFAULT_ASSET, publish_root: Path = Path("../output"),
        work_root: Path | None = None, cutoff_at: str | None = None,
        fetcher=intraday_bars.fetch_rows) -> dict:
    cutoff = cutoff_at or datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    day = publish_root / publish_layout.day_folder(cutoff)
    folder = day / chart_indicator_writer.FOLDER

    def fetch_closed() -> tuple[dict, list[dict], dict, str]:
        meta, raw_rows, label = fetcher(asset, timeframe=chart_indicator.TIMEFRAME)
        # H1: ตัดแท่งที่ยังก่อตัวทิ้งก่อนส่งชุดเดียวกันให้ RSI/MACD/Fib และภาพ
        rows, basis = intraday_bars.evaluate(
            raw_rows, asset=asset, timeframe=chart_indicator.TIMEFRAME)
        return meta, rows, basis, label

    try:
        meta, rows, basis, label = data_fetch_retry.run_with_one_retry(
            fetch_closed, asset=asset, timeframe=chart_indicator.TIMEFRAME)
    except data_fetch_retry.DataFetchUnavailable:
        raise
    # วันเผยแพร่ = วันที่รอบผลิตนี้ออก (เหตุผลเดียวกับสไตล์ D · มติผู้ใช้ 08-14)
    story = chart_indicator.build_indicators(
        rows, asset=asset, candle_basis=basis,
        timeframe=chart_indicator.TIMEFRAME,
        publish_date=datetime.now(tz=wcb_source.BANGKOK).strftime("%Y-%m-%d"))

    # รายวันต้องมีแผนเสมอเมื่อข้อมูลสุขภาพดี: ถ้า Fib ไม่มี swing หรือทั้งสอง
    # ฉากทัศน์ไกล/ไม่ผ่าน RR ให้ใช้ contingency ที่อิงราคาปิด H1 ล่าสุด + ATR
    # และส่ง key เดียวกันให้ writer, renderer และ public adapter
    if not story.get("fib") or trade_plan_public_adapters.select_e_candidate(story) is None:
        story.setdefault("scenarios", {})["contingency"] = chart_indicator.contingency_scenario(story)
    selected_key = trade_plan_public_adapters.select_e_candidate(story)
    if selected_key is None:
        raise RuntimeError("Style E ไม่พบแผนประจำวันที่ผ่าน geometry/RR/reachability")
    story["public_plan_key"] = selected_key

    markdown = chart_indicator_writer.render_article(story)
    validation = chart_indicator_writer.validate(markdown, story)

    result = {
        "asset": asset,
        "style": chart_indicator_writer.STYLE_NAME,
        "day": publish_layout.day_folder(cutoff),
        "directory": str(folder),
        "status": validation["status"],
        "char_count": validation["char_count"],
        "findings": validation["findings"],
        "source_label": label,
        "rows": len(rows),
        "candle_basis": basis,
        # Title tag ต้องออกจากระบบ ไม่ใช่ให้ใครพิมพ์มือ (บทเรียน B-3.3 · สเปก 08-10)
        "seo_title": chart_indicator_writer.seo_title(story),
    }
    if validation["status"] != "pass":
        result["removed_stale"] = False
        return result

    markdown = _publicize_style_e(markdown)
    reprotected = _publicize_style_e(markdown)
    number_findings = ([] if reprotected == markdown else
                       ["Style E public number policy ไม่ idempotent"])
    if number_findings:
        raise RuntimeError("; ".join(number_findings))
    result["number_policy"] = public_number_policy.POLICY_VERSION

    fib_name = chart_indicator_writer.fibonacci_image_name(
        asset, story["current"]["date"])
    plan_name = chart_indicator_writer.trade_plan_image_name(
        asset, story["current"]["date"])
    legacy_name = chart_indicator_writer.image_name(
        asset, story["current"]["date"], story.get("timeframe", "1day"))
    with tempfile.TemporaryDirectory(prefix="p002-style-e-") as tmp:
        stage = Path(tmp)
        fib = chart_indicator_renderer.render_fibonacci(
            story, rows, stage / fib_name)
        plan = chart_indicator_renderer.render_trade_plan(
            story, rows, stage / plan_name)
        article_stage = stage / f"{asset}.md"
        article_stage.write_text(markdown.rstrip() + "\n", encoding="utf-8")
        diagnostic = trade_plan_public_adapters.style_e(
            story=story, cutoff_at=cutoff, article_name=article_stage.name,
            article_bytes=article_stage.read_bytes())
        diagnostic = trade_plan_public_adapters.bind_article(
            diagnostic, article_stage.read_bytes())
        contract_report = trade_plan_public_contract.validate(
            diagnostic, article_name=article_stage.name,
            article_bytes=article_stage.read_bytes(), style_id="e_indicator",
            asset=asset,
            expected_evidence_hash=trade_plan_public_adapters.canonical_hash(story))
        if contract_report["status"] != "PASS":
            raise RuntimeError(
                "internal trade-plan contract ไม่ผ่าน: "
                + "; ".join(item["code"] for item in contract_report["findings"]))
        internal_root = (Path(work_root) if work_root is not None else
                         Path(publish_root).parent / "work" / "build")
        contract_path = (internal_root / result["day"] / asset / "internal" /
                         "style-e" / f"{asset}.trade-plan-public.json")
        contract_path.parent.mkdir(parents=True, exist_ok=True)
        contract_path.write_text(
            json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stale_public = [
            path for path in folder.glob(f"{asset}*")
            if path.name not in {article_stage.name, fib_name, plan_name}
        ]
        _promote_set(
            folder,
            {article_stage.name: article_stage, fib_name: stage / fib_name,
             plan_name: stage / plan_name},
            remove_after=[folder / legacy_name, *stale_public,
                          *folder.glob("*.trade-plan-public.json")],
            backup_root=stage / "backup")
    result.update({
        "article": str(folder / f"{asset}.md"),
        "images": [str(folder / fib_name), str(folder / plan_name)],
        "image_kb": {fib_name: fib["kb"], plan_name: plan["kb"]},
        "fibonacci": fib,
        "trade_plan": plan,
        "trade_plan_contract": diagnostic.get("qa_status"),
        "internal_trade_plan_contract": str(contract_path),
    })
    return result


def main(argv: list[str] | None = None) -> int:
    # คอนโซลไทย (cp874) พังเมื่อเจอ ✅/⚠️ — ตั้งก่อนพิมพ์ (บทเรียนเดียวกับ chart_story_pipeline)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description="สร้างบทสไตล์ E (อ่านอินดิเคเตอร์) หนึ่งหัวข้อ")
    parser.add_argument("--asset", default=DEFAULT_ASSET)
    parser.add_argument("--publish-root", type=Path, default=Path("../output"))
    parser.add_argument("--cutoff-at", default=None)
    args = parser.parse_args(argv)
    try:
        result = run(asset=args.asset, publish_root=args.publish_root,
                     cutoff_at=args.cutoff_at)
    except (data_fetch_retry.DataFetchUnavailable,
            chart_indicator.IndicatorUnavailable,
            intraday_bars.IntradayUnavailable,
            intraday_bars.FeedTimezoneDrift,
            intraday_bars.NoClosedBar,
            wcb_series_source.SeriesUnavailable,
            wcb_series_source.SeriesStaleData) as exc:
        print(f"⚠️ สไตล์ E ({args.asset}): {exc}")
        return 1
    if result["status"] == "pass":
        sizes = " · ".join(f"{name} {size} KB" for name, size in result["image_kb"].items())
        print(f"สไตล์ E ({args.asset}): ✅ บท {result['char_count']} อักขระ + ภาพ 2 ใบ "
              f"→ {result['directory']}")
        print(f"   ภาพ: {sizes} (เพดานเว็บ {image_output.kb(image_output.MAX_IMAGE_BYTES)} KB/ใบ)")
        return 0
    print(f"สไตล์ E ({args.asset}): ❌ ตกด่าน {len(result['findings'])} ข้อ — ไม่วางไฟล์")
    for finding in result["findings"]:
        print(f"   [{finding['rule']}] บรรทัด {finding['line']}: {finding['message']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
