"""สายผลิตสไตล์ D — ดึงแท่งจริง → สร้าง story → ตรวจบท → วางบท+ภาพคู่กัน

ลำดับที่จงใจ: **ตรวจบทให้ผ่านก่อน แล้วค่อยวาดภาพและวางไฟล์** — ถ้าบทตกด่าน
โฟลเดอร์ D ของหัวข้อนั้นต้องว่าง (ล้างของรอบก่อนทิ้งด้วย) ตามหลัก fail-closed
เดียวกับ `publish_layout`: ไฟล์ที่วางอยู่ = หยิบไปใช้ได้เลย

ขอบเขตปัจจุบัน: ทองคำ (xauusd) ตัวเดียว ตามนโยบายวันละ 1 บทเฉพาะทอง
(หัวหน้าสั่ง 2026-08-06) — สไตล์ D ยังไม่เข้าโฟลเดอร์ `0-ขึ้นเว็บวันนี้` เพราะ
`publishing_policy.json` ยังชี้สไตล์ A · การเปลี่ยนใบขึ้นเว็บเป็นการตัดสินใจ
ของหัวหน้าผ่านผู้ใช้ ไม่ใช่ของสายท่อ
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import chart_story, chart_story_renderer, chart_story_writer  # noqa: E402
from tools import publish_layout, wcb_series_source, wcb_source, wcb_writers  # noqa: E402

DEFAULT_ASSET = "xauusd"
CALENDAR_LIMIT = 3


def _clear_stale(folder: Path, asset: str) -> bool:
    """ลบบท+ภาพทุกใบของหัวข้อ — ของรอบก่อนต้องไม่นอนปนหน้าตาเหมือนของสด

    ภาพกวาดด้วย glob เพราะชื่อไฟล์มีวันที่ (`xauusd-d1-structure-<วัน>.png`)
    และครอบชื่อยุคเก่าทุกแบบ (`xauusd-1.png`/`-2.png`) ไปในตัว
    """
    removed = False
    targets = [folder / f"{asset}.md"] + list(folder.glob(f"{asset}*.png"))
    for path in targets:
        if path.exists():
            path.unlink()
            removed = True
    return removed


def _calendar_block(asset: str) -> tuple[dict | None, str]:
    """ก้อนปฏิทินสำหรับหัวข้อปัจจัยพื้นฐาน (ฟีดแบ็กหัวหน้าข้อ 3 · มติผู้ใช้ 08-06 ดึก)

    ใช้ตัวคัดเดิม `wcb_writers._calendar_sentences` (กติกา "คัดด้วยความสำคัญ
    นำเสนอด้วยเวลา" ล็อกไว้ที่นั่น — ห้ามเขียนตัวคัดใหม่) · snapshot ล่ม/ไม่มีรหัส
    = บทออกโดยไม่มีหัวข้อนี้ ไม่พาสายทั้งเส้นล้ม (ปฏิทินเป็นส่วนเสริม ราคาเป็นแกน)
    """
    try:
        evidence = wcb_source.fetch(asset)
        sentences = wcb_writers._calendar_sentences(evidence, limit=CALENDAR_LIMIT)
    except Exception as exc:  # noqa: BLE001 — ส่วนเสริมห้ามพาบทล้ม เหตุถูกบันทึกใน result
        return None, f"unavailable: {exc}"
    if not sentences:
        return None, "empty"
    return {"sentences": sentences}, "ok"


def run(*, asset: str = DEFAULT_ASSET, publish_root: Path = Path("../output"),
        cutoff_at: str | None = None, fetcher=wcb_series_source.fetch_asset_rows,
        calendar_source=_calendar_block) -> dict:
    cutoff = cutoff_at or datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    day = publish_root / publish_layout.day_folder(cutoff)
    folder = day / chart_story_writer.FOLDER

    meta, rows, label = fetcher(asset)
    calendar, calendar_status = calendar_source(asset)
    story = chart_story.build_story(rows, asset=asset, calendar=calendar)
    markdown = chart_story_writer.render_article(story)
    validation = chart_story_writer.validate(markdown, story)

    result = {
        "asset": asset,
        "style": chart_story_writer.STYLE_NAME,
        "day": publish_layout.day_folder(cutoff),
        "directory": str(folder),
        "status": validation["status"],
        "char_count": validation["char_count"],
        "findings": validation["findings"],
        "source_label": label,
        "rows": len(rows),
        "calendar": calendar_status,
    }
    if validation["status"] != "pass":
        result["removed_stale"] = _clear_stale(folder, asset)
        return result

    folder.mkdir(parents=True, exist_ok=True)
    _clear_stale(folder, asset)  # กวาดชุดเก่าก่อนวางใหม่ — ชื่อภาพผูกวันที่ เก่าค้างไม่ได้
    try:
        combined = chart_story_renderer.render_combined(
            story, rows,
            folder / chart_story_writer.image_name(asset, story["current"]["date"]))
        (folder / f"{asset}.md").write_text(markdown, encoding="utf-8")
    except Exception:
        # วาดล้มกลางคัน = ห้ามเหลือชุดครึ่ง ๆ กลาง ๆ ให้คนหยิบไปใช้
        _clear_stale(folder, asset)
        raise
    result.update({
        "article": str(folder / f"{asset}.md"),
        "images": [combined["path"]],
        "combined": combined,
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="สร้างบทสไตล์ D (อ่านโครงสร้างกราฟ) หนึ่งหัวข้อ")
    parser.add_argument("--asset", default=DEFAULT_ASSET)
    parser.add_argument("--publish-root", type=Path, default=Path("../output"))
    parser.add_argument("--cutoff-at", default=None)
    args = parser.parse_args(argv)
    try:
        result = run(asset=args.asset, publish_root=args.publish_root,
                     cutoff_at=args.cutoff_at)
    except (chart_story.StoryUnavailable,
            wcb_series_source.SeriesUnavailable,
            wcb_series_source.SeriesStaleData) as exc:
        print(f"⚠️ สไตล์ D ({args.asset}): {exc}")
        return 1
    if result["status"] == "pass":
        print(f"สไตล์ D ({args.asset}): ✅ บท {result['char_count']} อักขระ + ภาพรวมใบเดียว "
              f"→ {result['directory']}")
        return 0
    print(f"สไตล์ D ({args.asset}): ❌ ตกด่าน {len(result['findings'])} ข้อ — ไม่วางไฟล์")
    for finding in result["findings"]:
        print(f"   [{finding['rule']}] บรรทัด {finding['line']}: {finding['message']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
