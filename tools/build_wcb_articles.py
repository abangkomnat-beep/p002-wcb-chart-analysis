"""สายท่อสายสาธารณะ — ดึงสดจาก snapshot API แล้วเขียนบทความสามสไตล์

    python -m tools.build_wcb_articles --out output/wcb/2026-08-05
    python -m tools.build_wcb_articles --snapshot ไฟล์.json --out ที่เก็บ   # โหมดออฟไลน์

**รหัส API ไม่ได้อยู่ในโค้ดและต้องไม่อยู่** — ตั้งค่าในเครื่องก่อนรันครั้งแรก

    PowerShell:  $env:WCB_SNAPSHOT_KEY = "<รหัส>"
    หรือชี้ไปที่ไฟล์:  $env:WCB_SNAPSHOT_KEY_FILE = "C:\\path\\ถึง\\ไฟล์รหัส.txt"

ตัวเลือก `--save-snapshot` เก็บก้อนดิบไว้ตรวจย้อนกลับ — ก้อนดิบ **ไม่มีรหัสอยู่ในนั้น**
(รหัสอยู่ใน query string ไม่ใช่ในคำตอบ) จึงเก็บและส่งต่อให้ QA ได้อย่างปลอดภัย
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import wcb_source, wcb_writers  # noqa: E402


def build(evidence: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for writer in wcb_writers.WCB_WRITERS:
        target = out_dir / f"{writer['id']}.md"
        target.write_text(writer["render"](evidence), encoding="utf-8")
        written.append(target)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="สร้างบทวิเคราะห์สายสาธารณะสามสไตล์")
    parser.add_argument("--asset", default="xauusd")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path,
                        help="อ่านจากไฟล์แทนการดึงสด (โหมดออฟไลน์/ทดสอบ)")
    parser.add_argument("--save-snapshot", type=Path,
                        help="เก็บก้อนดิบที่ดึงมาไว้ตรวจย้อนกลับ")
    parser.add_argument("--max-age-minutes", type=int, default=wcb_source.MAX_AGE_MINUTES)
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    try:
        if args.snapshot:
            payload = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
            origin = f"ไฟล์ {args.snapshot.name}"
            evidence = wcb_source.normalize(payload)
        else:
            # **ต้องแปลงชื่อหัวข้อเป็น tag ก่อนเสมอ** เหมือนที่ `build_daily_package` ทำ
            # ปลายทางรับทั้ง `btcusd` และ `btc` ตอบ 200 เหมือนกันและคืน symbol BTC/USD
            # เหมือนกัน แต่เป็นคนละชุดข้อมูล — `btcusd` ยังเป็นชุดเก่าจันทร์-ศุกร์
            # ⇒ ทางนี้เคยดึงชุดที่ขาดเสาร์อาทิตย์มาเขียนบทโดยไม่มีอะไรฟ้อง
            payload = wcb_source.fetch_payload(wcb_source.tag_for(args.asset))
            origin = "ดึงสดจาก API"
            evidence = wcb_source.ensure_fresh(
                wcb_source.normalize(payload), args.max_age_minutes)
        # ด่านความละเอียดใช้กับทั้งโหมดสดและโหมดไฟล์ — ก้อนที่หยาบเกินไปก็หยาบเท่ากัน
        # ไม่ว่าจะอ่านจากไหน (ต่างจากด่านความสดที่โหมดไฟล์ข้ามได้โดยตั้งใจ)
        evidence = wcb_source.ensure_resolution(evidence)
        if evidence.get("coarse_prices"):
            print(f"⚠️ {evidence['coarse_note']}")
    except wcb_source.KeyMissing as error:
        print(f"หยุด — {error}")
        return 2
    except (wcb_source.SnapshotUnusable, wcb_source.SnapshotStale,
            wcb_source.SnapshotTooCoarse) as error:
        print(f"หยุด — {error}")
        return 1

    age = wcb_source.age_minutes(evidence)
    print(f"{origin} | {evidence['asset']} | ราคา {evidence['quote']['price']} "
          f"| ก้อนอายุ {int(age) if age is not None else '?'} นาที "
          f"| ข่าว {len(evidence['news'])} ชิ้น | ปฏิทิน {len(evidence['calendar'])} รายการ")

    if args.save_snapshot and not args.snapshot:
        # เก็บ **ก้อนดิบ** เท่านั้น เพื่อให้เอากลับมารันซ้ำและให้ด่านตรวจบทความอ่านได้
        args.save_snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.save_snapshot.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"เก็บก้อนดิบไว้ที่ {args.save_snapshot}")

    for path in build(evidence, args.out):
        print(f"เขียน {path}")
    print("ขั้นถัดไป: ตรวจทุกฉบับด้วย 01-CC/Repo/wcb-analysis/validate_article.py ก่อนส่งมอบ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
