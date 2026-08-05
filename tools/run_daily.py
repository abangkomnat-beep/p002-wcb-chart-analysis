"""คำสั่งเดียวจบรอบวัน — แทนที่การพิมพ์ 3 คำสั่งเดิมด้วยคำสั่งเดียว

    python -m tools.run_daily

เท่ากับการรันตามลำดับ (ของเดิมทุกอย่าง ไม่มีขั้นไหนถูกตัดหรือย่อ):

    1. python -m tools.build_daily_package --line both \
           --asset xauusd --asset eurusd --asset btcusd --asset nvda \
           --batch-id <สร้างจากเวลาปัจจุบันให้อัตโนมัติ>
    2. python -m tools.frontmatter_guard .            (ตัวรีโป)
    3. python -m tools.frontmatter_guard ../output    (บทความรอบที่จะส่ง)

**ตัวนี้เป็นแค่ตัวห่อ ไม่มีตรรกะของตัวเอง** — เรียก `build_daily_package.dispatch()`
กับ `frontmatter_guard.main()` ตรง ๆ ⇒ ผลลัพธ์เหมือนพิมพ์เองทุกไฟล์ทุกด่าน
ด่านตรวจทุกชั้น (ข้อมูล/ความสด/ความละเอียด/สิทธิ์/ตัวเลขบทความ/ความยาวรายสไตล์)
ยังทำงานครบตามเดิม เพราะมันอยู่ข้างในสายท่อ ไม่ได้อยู่ที่ตัวสั่งงาน

ปรับแต่งได้เท่าที่จำเป็นจริง — อยากได้มากกว่านี้ให้กลับไปใช้ `build_daily_package` ตรง ๆ:

    python -m tools.run_daily --asset xauusd          # รันหัวข้อเดียว
    python -m tools.run_daily --line internal          # รันสายเดียว
    python -m tools.run_daily --batch-id 2026-08-06T07-00Z-daily   # ตั้งชื่อ batch เอง

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

from tools import build_daily_package, frontmatter_guard  # noqa: E402

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
    parser.add_argument("--skip-guard", action="store_true",
                        help="ข้ามยาม frontmatter — ใช้เฉพาะตอนรันทดลองที่ไม่ได้จะส่งของ")
    args = parser.parse_args(argv)

    cutoff_dt = datetime.now(tz=timezone.utc)
    cutoff = cutoff_dt.isoformat(timespec="seconds")
    batch_id = args.batch_id or default_batch_id(cutoff_dt)

    # ประกอบชุดธงให้เหมือนพิมพ์คำสั่งเต็มเป๊ะ — ค่าตั้งต้นทุกตัวคัดลอกจาก parser ของ
    # build_daily_package ห้ามคิดค่าใหม่ตรงนี้ ไม่งั้นสองทางเข้าให้ผลต่างกัน
    build_args = argparse.Namespace(
        asset=args.asset or DEFAULT_ASSETS,
        line=args.line,
        batch_id=batch_id,
        output_root=Path("../work/build"),
        publish_root=Path("../output"),
        no_publish=False,
        snapshot=None,
        cutoff_at=cutoff,
        source=None,
        max_bar_age_days=build_daily_package.wcb_series_source.MAX_BAR_AGE_DAYS,
        no_news=False,
        no_trade_plan=False,
    )

    print(f"รอบวัน P002 · batch {batch_id} · สาย {args.line} "
          f"· หัวข้อ {', '.join(build_args.asset)}")
    build_code = build_daily_package.dispatch(build_args, cutoff)

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
