"""สายผลิตสไตล์ E — ดึงแท่งจริง → คำนวณอินดิเคเตอร์ → ตรวจบท → วางบท+ภาพคู่กัน

หลัก fail-closed เดียวกับสายสไตล์ D: ตรวจบทให้ผ่านก่อนแล้วค่อยวาดภาพและวางไฟล์
— ถ้าบทตกด่าน โฟลเดอร์ E ของหัวข้อนั้นต้องว่าง (ล้างของรอบก่อนทิ้งด้วย)

ขอบเขต: ทองคำ (xauusd) ตัวเดียว ตามคำสั่งผู้ใช้ 2026-08-06 ("เอาแค่ XAUUSD")
สไตล์ E ยังไม่เข้ารอบผลิตรายวัน (`run_daily`) — รอหัวหน้าพรูฟก่อน เหมือนขั้นตอน
ที่สไตล์ D เคยผ่าน · การขึ้นเว็บยังเป็นสไตล์ A ตาม `publishing_policy.json`
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import chart_indicator, chart_indicator_renderer, chart_indicator_writer  # noqa: E402
from tools import publish_layout, wcb_series_source  # noqa: E402

DEFAULT_ASSET = "xauusd"


def _clear_stale(folder: Path, asset: str) -> bool:
    """ลบบท+ภาพของหัวข้อที่ตกด่าน — ของรอบก่อนต้องไม่นอนปนหน้าตาเหมือนของสด"""
    removed = False
    names = [f"{asset}.md", *chart_indicator_writer.image_names(asset)]
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
    folder = day / chart_indicator_writer.FOLDER

    meta, rows, label = fetcher(asset)
    story = chart_indicator.build_indicators(rows, asset=asset)
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
    }
    if validation["status"] != "pass":
        result["removed_stale"] = _clear_stale(folder, asset)
        return result

    folder.mkdir(parents=True, exist_ok=True)
    first_name, second_name = chart_indicator_writer.image_names(asset)
    try:
        panels = chart_indicator_renderer.render_panels(story, rows, folder / first_name)
        fib = chart_indicator_renderer.render_fib(story, rows, folder / second_name)
        (folder / f"{asset}.md").write_text(markdown, encoding="utf-8")
    except Exception:
        # วาดล้มกลางคัน = ห้ามเหลือชุดครึ่ง ๆ กลาง ๆ ให้คนหยิบไปใช้
        _clear_stale(folder, asset)
        raise
    result.update({
        "article": str(folder / f"{asset}.md"),
        "images": [panels["path"], fib["path"]],
        "panels": panels,
        "fib": fib,
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="สร้างบทสไตล์ E (อ่านอินดิเคเตอร์) หนึ่งหัวข้อ")
    parser.add_argument("--asset", default=DEFAULT_ASSET)
    parser.add_argument("--publish-root", type=Path, default=Path("../output"))
    parser.add_argument("--cutoff-at", default=None)
    args = parser.parse_args(argv)
    try:
        result = run(asset=args.asset, publish_root=args.publish_root,
                     cutoff_at=args.cutoff_at)
    except (chart_indicator.IndicatorUnavailable,
            wcb_series_source.SeriesUnavailable,
            wcb_series_source.SeriesStaleData) as exc:
        print(f"⚠️ สไตล์ E ({args.asset}): {exc}")
        return 1
    if result["status"] == "pass":
        print(f"สไตล์ E ({args.asset}): ✅ บท {result['char_count']} อักขระ + ภาพ 2 ใบ "
              f"→ {result['directory']}")
        return 0
    print(f"สไตล์ E ({args.asset}): ❌ ตกด่าน {len(result['findings'])} ข้อ — ไม่วางไฟล์")
    for finding in result["findings"]:
        print(f"   [{finding['rule']}] บรรทัด {finding['line']}: {finding['message']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
