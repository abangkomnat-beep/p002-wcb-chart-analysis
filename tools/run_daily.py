"""คำสั่งเดียวจบรอบวัน — แทนที่การพิมพ์ 3 คำสั่งเดิมด้วยคำสั่งเดียว

    python -m tools.run_daily

**ตั้งแต่ 2026-08-05 ดึก (คำสั่งผู้ใช้): นักเขียน A/B/C เป็นชุดเดียวที่วางลง `output/`**
แทนที่ ①②③ (ณธาร/กฤช/ปุณณ์) — ค่าตั้งต้นของคำสั่งนี้จึงเป็น:

    1. สายภายใน ①②③ รันครบทุกด่าน **แต่ไม่วางไฟล์ลง output/** —
       ยังต้องรันเพราะเป็นเจ้าของหลักฐาน D1 + สาขาแผนการเทรด + ด่านความเสี่ยง
       (ของทั้งหมดอยู่ใน work/build/<batch>/ เหมือนเดิมทุกไฟล์ เพื่อ audit)
    2. สายสาธารณะ A/B/C รันครบทุกด่าน แล้ววางลง output/<วัน>/ ตามปกติ
       ⚠️ สายนี้ต้องมีรหัส (`WCB_SNAPSHOT_KEY` / `WCB_SNAPSHOT_KEY_FILE`)
       ⇒ ตั้งแต่การสลับนี้ รหัสกลายเป็นของจำเป็นต่อการได้บทประจำวัน
    3. 🆕 วางสำเนา **ใบเดียว** ที่ต้องเอาขึ้นเว็บไว้ใน `output/<วัน>/0-ขึ้นเว็บวันนี้/`
       ตามนโยบายใน `config/publishing_policy.json` — หัวหน้าตอบใบคำถาม P002 ข้อ 3
       เมื่อ 2026-08-06 ว่า **วันละ 1 บท เฉพาะทองคำ สไตล์เดียว** ส่วนหัวข้ออื่น
       ผลิตเก็บได้แต่ยังไม่ขึ้นเว็บ ⇒ **กำลังผลิตไม่ลด** เปลี่ยนแค่ว่าหยิบใบไหนไปวาง
    4. ยาม frontmatter ตรวจตัวรีโป + ../output ปิดท้าย

ย้อนกลับพฤติกรรมเดิม (①②③ ลง output ด้วย) ได้สองทาง ไม่ต้องแก้โค้ด:

    python -m tools.run_daily --publish-internal      # วางทั้งหกนักเขียนเหมือนก่อน
    python -m tools.run_daily --line internal          # รันเฉพาะสายเดิม (วางไฟล์ปกติ)

**ตัวนี้เป็นแค่ตัวห่อ ไม่มีตรรกะของตัวเอง** — เรียก `run_internal_line()` /
`run_public_line()` / `dispatch()` ของ build_daily_package กับ `frontmatter_guard.main()`
ตรง ๆ ⇒ ด่านตรวจทุกชั้น (ข้อมูล/ความสด/ความละเอียด/สิทธิ์/ตัวเลขบทความ/ความยาว
รายสไตล์) ยังทำงานครบตามเดิม เพราะมันอยู่ข้างในสายท่อ ไม่ได้อยู่ที่ตัวสั่งงาน

exit code: 0 = ทุกหัวข้อสร้างสำเร็จและไม่มี frontmatter แปลกปลอม · ไม่เป็นศูนย์ = มีอย่างน้อย
หนึ่งอย่างสะดุด (ดูบรรทัดสรุปท้ายรอบว่าตัวไหน)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import brief_pipeline, build_daily_package, calendar_feed, chart_indicator_pipeline, chart_story_pipeline, frontmatter_guard  # noqa: E402
from tools import publish_layout, publish_selection  # noqa: E402

DEFAULT_ASSETS = sorted(build_daily_package.ASSETS)


def default_batch_id(cutoff: datetime) -> str:
    """ชื่อ batch จากเวลาตัดข้อมูล — ห้ามมี `:` เพราะใช้เป็นชื่อโฟลเดอร์"""
    return cutoff.strftime("%Y-%m-%dT%H-%MZ-daily")


def main(argv: list[str] | None = None) -> int:
    # คอนโซลไทย (cp874) พังเมื่อเจออักขระอย่าง `·` — ตั้งก่อนพิมพ์อะไรทั้งนั้น
    # (เหตุผลเดียวกับใน build_daily_package.main)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="รันรอบวันของ P002 ครบทุกขั้นด้วยคำสั่งเดียว")
    parser.add_argument("--asset", action="append", choices=DEFAULT_ASSETS,
                        help="ไม่ระบุ = ครบทั้งสี่หัวข้อ")
    parser.add_argument("--line", choices=[build_daily_package.LINE_INTERNAL,
                                           build_daily_package.LINE_PUBLIC,
                                           build_daily_package.LINE_BOTH],
                        default=build_daily_package.LINE_BOTH,
                        help="ไม่ระบุ = both (สายภายใน ①②③ + สายสาธารณะ A/B/C)")
    parser.add_argument("--batch-id", help="ไม่ระบุ = สร้างจากเวลาปัจจุบัน (UTC)")
    parser.add_argument("--publish-internal", action="store_true",
                        help="วางบทสายภายใน ①②③ ลง output/ ด้วย "
                             "(พฤติกรรมก่อนคำสั่ง 2026-08-05 ดึก ที่ให้ A/B/C แทนที่)")
    parser.add_argument("--skip-guard", action="store_true",
                        help="ข้ามยาม frontmatter — ใช้เฉพาะตอนรันทดลองที่ไม่ได้จะส่งของ")
    parser.add_argument("--skip-selection", action="store_true",
                        help="ไม่ต้องวางโฟลเดอร์ใบขึ้นเว็บ (config/publishing_policy.json)")
    parser.add_argument("--skip-style-d", action="store_true",
                        help="ข้ามบทสไตล์ D (อ่านโครงสร้างกราฟ + ภาพ 2 ใบ)")
    parser.add_argument("--skip-style-e", action="store_true",
                        help="ข้ามบทสไตล์ E (อ่านอินดิเคเตอร์ RSI/MACD/Fibonacci "
                             "+ ภาพรวมใบเดียว)")
    parser.add_argument("--skip-style-fg", action="store_true",
                        help="ข้ามบทเช้าสไตล์ F/G (ระบบเลือก F หรือ G เองตามเงื่อนไขวัน)")
    # เปิดเป็นค่าตั้งต้นตั้งแต่ 2026-08-10 — ดูเหตุผลเดียวกับใน build_daily_package.main
    parser.add_argument("--calendar-feed", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="ใช้ /api/calendar/feed แทนช่อง calendar เดิมใน snapshot "
                             "ทั้ง A/B/C และ D — เปิดเป็นค่าตั้งต้น "
                             "· --no-calendar-feed = สายเก่าแบบตัดตัวเลขทั้งหมด")
    args = parser.parse_args(argv)

    cutoff_dt = datetime.now(tz=timezone.utc)
    cutoff = cutoff_dt.isoformat(timespec="seconds")
    batch_id = args.batch_id or default_batch_id(cutoff_dt)

    # ประกอบชุดธงให้เหมือนพิมพ์คำสั่งเต็มเป๊ะ — ค่าตั้งต้นทุกตัวคัดลอกจาก parser ของ
    # build_daily_package ห้ามคิดค่าใหม่ตรงนี้ ไม่งั้นสองทางเข้าให้ผลต่างกัน
    def line_args(line: str, *, no_publish: bool) -> argparse.Namespace:
        return argparse.Namespace(
            asset=args.asset or DEFAULT_ASSETS,
            line=line,
            batch_id=batch_id,
            output_root=Path("../work/build"),
            publish_root=Path("../output"),
            no_publish=no_publish,
            snapshot=None,
            cutoff_at=cutoff,
            source=None,
            max_bar_age_days=build_daily_package.wcb_series_source.MAX_BAR_AGE_DAYS,
            no_news=False,
            no_trade_plan=False,
            calendar_feed=args.calendar_feed,
        )

    assets = args.asset or DEFAULT_ASSETS
    print(f"รอบวัน P002 · batch {batch_id} · สาย {args.line} · หัวข้อ {', '.join(assets)}")

    if args.line == build_daily_package.LINE_BOTH:
        # ค่าตั้งต้นใหม่ (คำสั่งผู้ใช้ 2026-08-05 ดึก): A/B/C คือชุดเดียวที่ลง output/
        # สายภายในยังรันเต็มทุกด่านเพื่อหลักฐาน+แผนเทรด แต่ไม่วางไฟล์ เว้นแต่สั่ง
        # --publish-internal · สั่ง --line internal ตรง ๆ ยังวางไฟล์ปกติ (คำสั่งชัดเจน
        # ของผู้ใช้ย่อมชนะค่าตั้งต้น)
        if not args.publish_internal:
            print("สายภายใน ①②③: รันเพื่อหลักฐาน+แผนเทรดเท่านั้น ไม่วางลง output/ "
                  "(A/B/C แทนที่ตามคำสั่ง 2026-08-05 · ใส่ --publish-internal ถ้าต้องการของเดิม)")
        build_code = build_daily_package.run_internal_line(
            line_args(build_daily_package.LINE_INTERNAL,
                      no_publish=not args.publish_internal), cutoff)
        print()
        build_code = build_code | build_daily_package.run_public_line(
            line_args(build_daily_package.LINE_PUBLIC, no_publish=False), cutoff)
    else:
        build_code = build_daily_package.dispatch(
            line_args(args.line, no_publish=False), cutoff)

    # สไตล์ D/E/F/G — เข้าสายหลัก**ครบทุกหัวข้อ** ตามคำสั่งผู้ใช้ 2026-08-11
    # (เดิม D/E จำกัดเฉพาะทอง และ F/G ยังไม่เข้ารอบเลย — นโยบาย "วันละ 1 บทเฉพาะทอง"
    #  เป็นเรื่องใบขึ้นเว็บใน publishing_policy.json ไม่ใช่เรื่องการผลิต)
    # ล้มรายหัวข้อ = รายงานหัวข้อนั้นสะดุด ไม่ดึงสายอื่นล้มตาม (หลักเดิมของสายเสริม)
    if not args.skip_style_d and args.line != build_daily_package.LINE_INTERNAL:
        for asset in assets:
            print()
            try:
                style_d = chart_story_pipeline.run(
                    asset=asset, publish_root=Path("../output"), cutoff_at=cutoff,
                    calendar_source=(chart_story_pipeline.calendar_block_from_feed
                                     if args.calendar_feed else chart_story_pipeline._calendar_block))
            except Exception as exc:  # noqa: BLE001 — สายเสริมห้ามพาทั้งรอบล้ม
                print(f"⚠️ สไตล์ D ({asset}): {exc}")
                build_code |= 1
            else:
                if style_d["status"] == "pass":
                    print(f"สไตล์ D ({asset}): ✅ บท + ภาพ 2 ใบ → {style_d['directory']}")
                else:
                    print(f"⚠️ สไตล์ D ({asset}): ตกด่าน {len(style_d['findings'])} ข้อ — ไม่วางไฟล์")
                    build_code |= 1

    if not args.skip_style_e and args.line != build_daily_package.LINE_INTERNAL:
        for asset in assets:
            print()
            try:
                style_e = chart_indicator_pipeline.run(asset=asset,
                                                       publish_root=Path("../output"),
                                                       cutoff_at=cutoff)
            except Exception as exc:  # noqa: BLE001 — สายเสริมห้ามพาทั้งรอบล้ม
                print(f"⚠️ สไตล์ E ({asset}): {exc}")
                build_code |= 1
            else:
                if style_e["status"] == "pass":
                    print(f"สไตล์ E ({asset}): ✅ บท {style_e['char_count']} อักขระ "
                          f"+ ภาพรวมใบเดียว → {style_e['directory']}")
                else:
                    print(f"⚠️ สไตล์ E ({asset}): ตกด่าน {len(style_e['findings'])} ข้อ — ไม่วางไฟล์")
                    build_code |= 1

    # สไตล์ F/G (บทเช้า) — ระบบเลือก F↔G เองตามเงื่อนไขวัน (เหตุการณ์แรงรอ + แนวโน้ม
    # พิสูจน์ได้ ⇒ G) · หนึ่งหัวข้อได้สไตล์เดียวต่อวัน อีกสไตล์ถูกกวาดทิ้งใน pipeline
    if not args.skip_style_fg and args.line != build_daily_package.LINE_INTERNAL:
        for asset in assets:
            print()
            try:
                style_fg = brief_pipeline.run(asset=asset,
                                              publish_root=Path("../output"),
                                              cutoff_at=cutoff)
            except Exception as exc:  # noqa: BLE001 — สายเสริมห้ามพาทั้งรอบล้ม
                print(f"⚠️ สไตล์ F/G ({asset}): {exc}")
                build_code |= 1
            else:
                if style_fg["ok"]:
                    print(f"สไตล์ {style_fg['style_name']} ({asset}): ✅ บท + ภาพกรอบราคา "
                          f"→ {style_fg['folder']}")
                else:
                    print(f"⚠️ สไตล์ {style_fg['style_name']} ({asset}): "
                          f"ตกด่าน {len(style_fg['findings'])} ข้อ — ไม่วางไฟล์")
                    build_code |= 1

    # เลือกใบขึ้นเว็บ **ก่อน** ยาม frontmatter เสมอ เพราะสำเนาที่วางไว้ต้องโดนกวาดด้วย
    # (basic-memory แทรก `permalink:` ให้ไฟล์ .md ใต้ Desktop\Claude โดยอัตโนมัติ —
    #  ใบที่ก๊อปทีหลังจะรอดยามไปขึ้นเว็บพร้อม frontmatter แปลกปลอม)
    if not args.skip_selection and args.line != build_daily_package.LINE_INTERNAL:
        day_dir = Path("../output") / publish_layout.day_folder(cutoff)
        selected = publish_selection.select(day_dir)
        if selected["status"] == "ready":
            print(f"\nใบขึ้นเว็บรอบนี้ (วันละ 1 บทตามคำสั่งหัวหน้า 2026-08-06): "
                  f"{selected['article']}")
        else:
            print(f"\n⚠️ ยังไม่มีใบขึ้นเว็บ — คาดว่าจะเจอที่ {selected['expected']} "
                  f"· เหตุผลอยู่ใน {selected['directory']}")

    guard_code = 0
    if not args.skip_guard:
        print("\nยาม frontmatter — ตัวรีโป:")
        guard_code |= frontmatter_guard.main(["."])
        print("ยาม frontmatter — บทความรอบที่จะส่ง (../output):")
        guard_code |= frontmatter_guard.main(["../output"])

    print("\nสรุปรอบ: สายท่อ "
          + ("✅ ทุกหัวข้อสำเร็จ" if build_code == 0 else "⚠️ มีหัวข้อที่สะดุด (ดูบรรทัดของหัวข้อนั้นข้างบน)")
          + " · frontmatter "
          + ("— ข้ามตามธง" if args.skip_guard else
             ("✅ สะอาด" if guard_code == 0 else "⚠️ เจอของแปลก — ล้างด้วย python -m tools.frontmatter_guard <ที่> --fix")))
    return build_code or guard_code


if __name__ == "__main__":
    raise SystemExit(main())
