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
from tools import publish_layout, wcb_series_source  # noqa: E402

DEFAULT_ASSET = "xauusd"


def _clear_stale(folder: Path, asset: str) -> bool:
    """ลบบท+ภาพของหัวข้อที่ตกด่าน — ของรอบก่อนต้องไม่นอนปนหน้าตาเหมือนของสด"""
    removed = False
    names = [f"{asset}.md", *chart_story_writer.image_names(asset)]
    for name in names:
        path = folder / name
        if path.exists():
            path.unlink()
            removed = True
    return removed


def run(*, asset: str = DEFAULT_ASSET, publish_root: Path = Path("../output"),
        cutoff_at: str | None = None, fetcher=wcb_series_source.fetch_asset_rows) -> dict:
    cutoff = cutoff_at or datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    day = publish_root / publish_layout.day_folder(cutoff)
    folder = day / chart_story_writer.FOLDER

    meta, rows, label = fetcher(asset)
    story = chart_story.build_story(rows, asset=asset)
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
    }
    if validation["status"] != "pass":
        result["removed_stale"] = _clear_stale(folder, asset)
        return result

    folder.mkdir(parents=True, exist_ok=True)
    first_name, second_name = chart_story_writer.image_names(asset)
    try:
        overview = chart_story_renderer.render_overview(story, rows, folder / first_name)
        zoom = chart_story_renderer.render_zoom(story, rows, folder / second_name)
        (folder / f"{asset}.md").write_text(markdown, encoding="utf-8")
    except Exception:
        # วาดล้มกลางคัน = ห้ามเหลือชุดครึ่ง ๆ กลาง ๆ ให้คนหยิบไปใช้
        _clear_stale(folder, asset)
        raise
    result.update({
        "article": str(folder / f"{asset}.md"),
        "images": [overview["path"], zoom["path"]],
        "overview": overview,
        "zoom": zoom,
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
        print(f"สไตล์ D ({args.asset}): ✅ บท {result['char_count']} อักขระ + ภาพ 2 ใบ "
              f"→ {result['directory']}")
        return 0
    print(f"สไตล์ D ({args.asset}): ❌ ตกด่าน {len(result['findings'])} ข้อ — ไม่วางไฟล์")
    for finding in result["findings"]:
        print(f"   [{finding['rule']}] บรรทัด {finding['line']}: {finding['message']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
