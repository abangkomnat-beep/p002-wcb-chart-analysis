"""สายผลิตสไตล์ D — ดึงแท่งจริง → สร้าง story → ตรวจบท → วางบท+ภาพคู่กัน

ลำดับที่จงใจ: **ตรวจบทให้ผ่านก่อน แล้วค่อยวาดภาพและวางไฟล์** — ถ้าบทตกด่าน
โฟลเดอร์ D ของหัวข้อนั้นต้องว่าง (ล้างของรอบก่อนทิ้งด้วย) ตามหลัก fail-closed
เดียวกับ `publish_layout`: ไฟล์ที่วางอยู่ = หยิบไปใช้ได้เลย

ขอบเขต: **ทุกหัวข้อในทะเบียน** ตั้งแต่ 2026-08-11 (ผู้ใช้สั่งรัน A–G เข้าสายหลัก
ครบทุกหัวข้อ) — นโยบาย "วันละ 1 บทเฉพาะทอง" เป็นเรื่องใบขึ้นเว็บใน
`publishing_policy.json` ไม่ใช่เรื่องการผลิต · สไตล์ D ยังไม่เข้าโฟลเดอร์
`0-ขึ้นเว็บวันนี้` เพราะนโยบายยังชี้สไตล์ A · การเปลี่ยนใบขึ้นเว็บเป็นการตัดสินใจ
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

from tools import calendar_feed, candle_close  # noqa: E402
from tools import chart_story, chart_story_renderer, chart_story_writer, zone_memory  # noqa: E402
from tools import image_output  # noqa: E402
from tools import publish_layout, wcb_series_source, wcb_source, wcb_writers  # noqa: E402

DEFAULT_ASSET = "xauusd"
CALENDAR_LIMIT = 3


def _clear_stale(folder: Path, asset: str) -> bool:
    """ลบบท+ภาพทุกใบของหัวข้อ — ของรอบก่อนต้องไม่นอนปนหน้าตาเหมือนของสด

    ภาพกวาดด้วย glob เพราะชื่อไฟล์มีวันที่ (`xauusd-d1-structure-<วัน>.webp`)
    และครอบชื่อยุคเก่าทุกแบบ (`xauusd-1.png`/`-2.png`) ไปในตัว

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


def _calendar_block(asset: str) -> tuple[dict | None, str]:
    """ก้อนปฏิทินสำหรับหัวข้อปัจจัยพื้นฐาน (ฟีดแบ็กหัวหน้าข้อ 3 · มติผู้ใช้ 08-06 ดึก)

    ใช้ตัวคัดเดิม `wcb_writers._calendar_sentences` (กติกา "คัดด้วยความสำคัญ
    นำเสนอด้วยเวลา" ล็อกไว้ที่นั่น — ห้ามเขียนตัวคัดใหม่) · snapshot ล่ม/ไม่มีรหัส
    = บทออกโดยไม่มีหัวข้อนี้ ไม่พาสายทั้งเส้นล้ม (ปฏิทินเป็นส่วนเสริม ราคาเป็นแกน)

    **กลายเป็นสายสำรองตั้งแต่ 2026-08-10** — ค่าตั้งต้นของ `run_daily` คือ
    `calendar_block_from_feed()` (มีหน่วย + ปิด D-2) · สายนี้เหลือไว้สำหรับ
    `--no-calendar-feed` และต้อง**ตัดตัวเลขทั้งหมด**ก่อนเขียนประโยค เพราะช่อง
    `calendar` เดิมไม่มีข้อมูลหน่วย (ทีมเว็บรอบสี่ข้อ A-3: เลขเปล่า "4.09" หลุดขึ้นบทจริง)
    """
    try:
        evidence = wcb_source.fetch(asset)
        calendar_feed.strip_snapshot_values(evidence)
        sentences = wcb_writers._calendar_sentences(evidence, limit=CALENDAR_LIMIT)
        # รายการต้นทางของประโยค (ตัวคัด/ลำดับเดียวกัน) — ใช้จัดกลุ่ม bullet ตามวัน
        selected = wcb_writers._calendar_events(evidence, CALENDAR_LIMIT)
    except Exception as exc:  # noqa: BLE001 — ส่วนเสริมห้ามพาบทล้ม เหตุถูกบันทึกใน result
        return None, f"unavailable: {exc}"
    if not sentences:
        return None, "empty"
    return {"sentences": sentences, "events": selected}, "ok"


def calendar_block_from_feed(asset: str, *, fetcher=calendar_feed.fetch_raw) -> tuple[dict | None, str]:
    """เหมือน `_calendar_block` แต่ดึงจาก `/api/calendar/feed` แทน (ปิด D-2 ถาวร)

    D ไม่มีด่านตรวจแบบ `wcb_copy_validator` ที่เทียบเลขกับก้อน snapshot ดิบ —
    `chart_story_writer.allowed_numbers()` ไล่เก็บตัวเลขจากประโยคปฏิทินที่
    `_calendar_sentences()` สร้างออกมาโดยตรง (เชื่อว่าฟังก์ชันนั้นพูดจาก
    หลักฐานจริงอยู่แล้ว) ⇒ **ไม่ต้องพ่วงก้อนดิบเข้าด่านตรวจเหมือนฝั่ง A/B/C**
    เปลี่ยนแค่แหล่งข้อมูลที่ป้อนเข้า `_calendar_sentences` ก็พอ

    `fetcher` รับได้เพื่อทดสอบโดยไม่ต้องยิงเครือข่ายจริง (แนวเดียวกับ `fetcher`
    ของ `run()` และ `calendar_source` ของโมดูลนี้)
    """
    try:
        raw = fetcher()
        today = datetime.now(tz=wcb_source.BANGKOK).strftime("%Y-%m-%d")
        pseudo_evidence = {"calendar": calendar_feed.to_calendar_events(raw),
                           "local_date": today}
        sentences = wcb_writers._calendar_sentences(pseudo_evidence, limit=CALENDAR_LIMIT)
        # รายการต้นทางของประโยค (ตัวคัด/ลำดับเดียวกัน) — ใช้จัดกลุ่ม bullet ตามวัน
        selected = wcb_writers._calendar_events(pseudo_evidence, CALENDAR_LIMIT)
    except Exception as exc:  # noqa: BLE001 — ส่วนเสริมห้ามพาบทล้ม เหตุถูกบันทึกใน result
        return None, f"unavailable: {exc}"
    if not sentences:
        return None, "empty"
    return {"sentences": sentences, "events": selected}, "ok"


def run(*, asset: str = DEFAULT_ASSET, publish_root: Path = Path("../output"),
        cutoff_at: str | None = None, fetcher=wcb_series_source.fetch_asset_rows,
        calendar_source=_calendar_block,
        zone_state_dir: Path | None = None) -> dict:
    """`zone_state_dir`: ที่เก็บความจำโซน — เทส**ต้องส่ง tmp เสมอ** ไม่งั้นข้อมูล
    สังเคราะห์จะเขียนทับ state ของจริงแล้วรอบผลิตวันถัดไปโหลดของปลอม
    (เกิดจริงตอนพัฒนา 08-10: เทส pipeline ทิ้ง state ลงวันที่ 2026-02-24 ไว้)"""
    cutoff = cutoff_at or datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    day = publish_root / publish_layout.day_folder(cutoff)
    folder = day / chart_story_writer.FOLDER

    meta, rows, label = fetcher(asset)
    # 🐞 **A-1 (08-09):** ตัดแท่งที่ยังไม่ปิดทิ้ง **ก่อนทั้งการคำนวณและการวาดภาพ**
    # ตัดที่นี่ที่เดียวแล้วส่งชุดเดียวกันต่อทั้งสองทาง — ถ้าปล่อยให้ `build_story`
    # ตัดเองแล้วยังส่ง `rows` ชุดเดิมไปให้ตัววาด ภาพจะมีแท่งที่บทไม่นับอยู่ที่ขอบขวา
    rows, basis = candle_close.evaluate(rows, asset=asset)
    calendar, calendar_status = calendar_source(asset)
    # ความจำโซนข้ามวัน (ผู้ใช้เคาะ 08-10 #18ข) — pipeline คือจุดเดียวที่แตะ state
    # บนดิสก์ · state หาย/พัง load คืน None = คำนวณสดต่อ ไม่ตกทั้งบท
    locked = zone_memory.load(asset, state_dir=zone_state_dir)
    # วันเผยแพร่ = วันที่รอบผลิตนี้ออก (เขตเวลากรุงเทพ) — พาดหัวใช้ค่านี้ ไม่ใช่วันแท่งฐาน
    # (มติผู้ใช้ 08-14: ทุกสไตล์ต้องลงวันเดียวกันในรอบเดียวกัน)
    story = chart_story.build_story(
        rows, asset=asset, calendar=calendar, candle_basis=basis, locked=locked,
        publish_date=datetime.now(tz=wcb_source.BANGKOK).strftime("%Y-%m-%d"))
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
        "candle_basis": basis,
        # B-3.3: Title tag ออกมาจากระบบ ไม่ต้องมีใครพิมพ์เอง จึงเพี้ยนจาก H1 ไม่ได้
        "seo_title": chart_story_writer.seo_title(story),
    }
    if validation["status"] != "pass":
        result["removed_stale"] = _clear_stale(folder, asset)
        return result

    folder.mkdir(parents=True, exist_ok=True)
    _clear_stale(folder, asset)  # กวาดชุดเก่าก่อนวางใหม่ — ชื่อภาพผูกวันที่ เก่าค้างไม่ได้
    first_name, second_name = chart_story_writer.image_names(asset, story["current"]["date"])
    try:
        overview = chart_story_renderer.render_overview(story, rows, folder / first_name)
        zoom = chart_story_renderer.render_zoom(story, rows, folder / second_name)
        (folder / f"{asset}.md").write_text(markdown, encoding="utf-8")
    except Exception:
        # วาดล้มกลางคัน = ห้ามเหลือชุดครึ่ง ๆ กลาง ๆ ให้คนหยิบไปใช้
        _clear_stale(folder, asset)
        raise
    # อัปเดต state เฉพาะรอบที่ผ่านด่านและวางไฟล์แล้วจริง — รอบที่ตกด่านห้ามล็อก
    # ระดับชุดใหม่ (คนอ่านยังไม่เคยเห็นมัน จะเรียกว่า "โซนเดิม" ไม่ได้)
    result["zone_state"] = str(zone_memory.save(
        asset, zone_memory.build_state(story, previous=locked),
        state_dir=zone_state_dir))
    result["zone_memory"] = story.get("zone_memory")
    result.update({
        "article": str(folder / f"{asset}.md"),
        "images": [overview["path"], zoom["path"]],
        "image_kb": {Path(overview["path"]).name: overview["kb"],
                     Path(zoom["path"]).name: zoom["kb"]},
        "overview": overview,
        "zoom": zoom,
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="สร้างบทสไตล์ D (อ่านโครงสร้างกราฟ) หนึ่งหัวข้อ")
    # คอนโซลไทย (cp874) พังเมื่อเจอ ✅/⚠️ — ตั้งก่อนพิมพ์อะไรทั้งนั้น (เหตุผลเดียวกับ
    # run_daily/brief_pipeline · เพิ่งกัดจริง 08-11: บทเขียนเสร็จแล้วแต่บรรทัดสรุปพังแทน)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
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
        sizes = " · ".join(f"{name} {size} KB" for name, size in result["image_kb"].items())
        print(f"สไตล์ D ({args.asset}): ✅ บท {result['char_count']} อักขระ + ภาพ 2 ใบ "
              f"→ {result['directory']}")
        print(f"   Title tag: {result['seo_title']}")
        print(f"   ฐานแท่ง: {result['candle_basis']['basis_session_date']} (ปิดแล้ว) · "
              f"{result['candle_basis']['rule']}")
        print(f"   ภาพ: {sizes} (เพดานเว็บ {image_output.kb(image_output.MAX_IMAGE_BYTES)} KB/ใบ)")
        return 0
    print(f"สไตล์ D ({args.asset}): ❌ ตกด่าน {len(result['findings'])} ข้อ — ไม่วางไฟล์")
    for finding in result["findings"]:
        print(f"   [{finding['rule']}] บรรทัด {finding['line']}: {finding['message']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
