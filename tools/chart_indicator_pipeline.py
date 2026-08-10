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

from tools import candle_close  # noqa: E402
from tools import chart_indicator, chart_indicator_renderer, chart_indicator_writer  # noqa: E402
from tools import image_output  # noqa: E402
from tools import publish_layout, wcb_series_source  # noqa: E402

DEFAULT_ASSET = "xauusd"


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


def run(*, asset: str = DEFAULT_ASSET, publish_root: Path = Path("../output"),
        cutoff_at: str | None = None, fetcher=wcb_series_source.fetch_asset_rows) -> dict:
    cutoff = cutoff_at or datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    day = publish_root / publish_layout.day_folder(cutoff)
    folder = day / chart_indicator_writer.FOLDER

    meta, rows, label = fetcher(asset)
    # A-1: ตัดแท่งที่ยังไม่ปิดทิ้งที่นี่ที่เดียว แล้วส่งชุดเดียวกันให้ทั้งตัวคำนวณและตัววาด
    rows, basis = candle_close.evaluate(rows, asset=asset)
    story = chart_indicator.build_indicators(rows, asset=asset, candle_basis=basis)
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
        result["removed_stale"] = _clear_stale(folder, asset)
        return result

    folder.mkdir(parents=True, exist_ok=True)
    _clear_stale(folder, asset)  # กวาดชุดเก่าก่อนวางใหม่ — ชื่อภาพผูกวันที่ เก่าค้างไม่ได้
    try:
        combined = chart_indicator_renderer.render_combined(
            story, rows,
            folder / chart_indicator_writer.image_name(asset, story["current"]["date"]))
        (folder / f"{asset}.md").write_text(markdown, encoding="utf-8")
    except Exception:
        # วาดล้มกลางคัน = ห้ามเหลือชุดครึ่ง ๆ กลาง ๆ ให้คนหยิบไปใช้
        _clear_stale(folder, asset)
        raise
    result.update({
        "article": str(folder / f"{asset}.md"),
        "images": [combined["path"]],
        "image_kb": {Path(combined["path"]).name: combined["kb"]},
        "combined": combined,
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
        sizes = " · ".join(f"{name} {size} KB" for name, size in result["image_kb"].items())
        print(f"สไตล์ E ({args.asset}): ✅ บท {result['char_count']} อักขระ + ภาพรวมใบเดียว "
              f"→ {result['directory']}")
        print(f"   ภาพ: {sizes} (เพดานเว็บ {image_output.kb(image_output.MAX_IMAGE_BYTES)} KB/ใบ)")
        return 0
    print(f"สไตล์ E ({args.asset}): ❌ ตกด่าน {len(result['findings'])} ข้อ — ไม่วางไฟล์")
    for finding in result["findings"]:
        print(f"   [{finding['rule']}] บรรทัด {finding['line']}: {finding['message']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
