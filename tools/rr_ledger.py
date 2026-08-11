"""สมุดสถิติ RR ของบทสไตล์ E — หลักฐานสำหรับตัดสินใจตามข้อ 3ก

## ทำไมต้องมี

หัวหน้าเคาะข้อ **3ก** เมื่อ 2026-08-11: *"เก็บสถิติ 7–10 วันก่อนตัดสิน"* ว่าโครง
Golden Zone + TP ที่ระดับ Fibonacci ถัดไป ให้แผนที่ "เข้าไม่ได้" เป็นค่าปกติหรือไม่
— และ **ห้ามดันตัวเลขให้ผ่าน** (ทางเลือก ข ที่เขาไม่เอา)

คำถามที่สมุดนี้ต้องตอบได้เมื่อครบรอบ: *ใน N วันที่ผ่านมา มีกี่วันที่ RR แตะเกณฑ์
`RR_FLOOR` อย่างน้อยหนึ่งฝั่ง* ถ้าเป็นศูนย์ = โครงมีปัญหาเชิงโครงสร้างจริง ค่อยรื้อ

⚠️ **สมุดนี้ไม่ใช่ด่าน** — ไม่ตีตกบท ไม่เปลี่ยนเกณฑ์ ไม่แตะ `RR_FLOOR`
มันบันทึกอย่างเดียว การตัดสินเป็นของคนหลังเห็นตัวเลขครบ

## กันนับซ้ำ

รอบผลิตวันเดียวกันรันซ้ำได้บ่อย (รันมือทับรอบตาราง · แก้บั๊กแล้วรันใหม่) ⇒ ถ้า
append ตรง ๆ วันที่รัน 3 รอบจะกลายเป็น 3 วันในสถิติ **แล้วข้อสรุปจะผิด**
⇒ เก็บเป็น "หนึ่งแถวต่อหนึ่งวันของแท่งราคา" แบบ upsert — รอบหลังทับรอบแรกของวันนั้น
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import chart_indicator_writer  # noqa: E402

# วางไว้นอกโฟลเดอร์รายวัน เพราะเป็นของสะสมข้ามวัน ไม่ใช่ผลผลิตของวันใดวันหนึ่ง
LEDGER_NAME = "_สถิติ-RR-สไตล์E.jsonl"


def ledger_path(publish_root: Path) -> Path:
    return Path(publish_root) / LEDGER_NAME


def row_for(story: dict, *, asset: str) -> dict:
    """แถวเดียวของหนึ่งวัน — เก็บ RR ดิบทั้งสองฝั่ง ไม่ปัด ไม่ตัดสิน

    เก็บค่าดิบเพราะการปัดทำให้เคสขอบ (1.19 vs 1.2) หายไป ซึ่งเป็นเคสที่น่าสนใจที่สุด
    ตอนสรุปว่าโครงนี้ "เกือบผ่าน" หรือ "ไม่ใกล้เลย"
    """
    scenarios = story.get("scenarios") or {}

    def side_of(key: str) -> dict | None:
        scenario = scenarios.get(key)
        if not scenario or scenario.get("rr1") is None:
            return None
        return {"side": scenario.get("side"), "rr1": float(scenario["rr1"]),
                "daily_entry": bool(scenario.get("daily_entry", True))}

    primary, counter = side_of("primary"), side_of("counter")
    rrs = [item["rr1"] for item in (primary, counter) if item]
    return {
        "date": story["current"]["date"],
        "asset": asset,
        "floor": chart_indicator_writer.RR_FLOOR,
        "primary": primary,
        "counter": counter,
        # "วันนี้มีแผนที่เข้าได้ไหม" = อย่างน้อยหนึ่งฝั่งแตะเกณฑ์
        "any_pass": any(value >= chart_indicator_writer.RR_FLOOR for value in rrs),
        "best_rr": max(rrs) if rrs else None,
    }


def record(story: dict, *, asset: str, publish_root: Path) -> dict:
    """เขียนแถวของวันนี้ลงสมุด (upsert ตามวันของแท่งราคา) แล้วคืนแถวที่เขียน"""
    path = ledger_path(publish_root)
    row = row_for(story, asset=asset)
    rows = [item for item in read(path)
            if not (item.get("date") == row["date"] and item.get("asset") == row["asset"])]
    rows.append(row)
    rows.sort(key=lambda item: (item.get("date") or "", item.get("asset") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows),
                    encoding="utf-8")
    return row


def read(path: Path) -> list[dict]:
    """อ่านสมุด — ไฟล์ยังไม่มี = ยังไม่เคยเก็บ ไม่ใช่ข้อผิดพลาด

    บรรทัดเสียถูกข้ามเงียบ ๆ ไม่ได้ **ต้องระเบิด** — สมุดนี้เป็นหลักฐานที่จะเอาไป
    ตัดสินใจ ถ้ายอมให้บรรทัดหายเงียบ สถิติจะบอกว่า "เก็บมา 8 วัน" ทั้งที่จริง 6
    """
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"สมุดสถิติ RR บรรทัดที่ {number} เสีย: {exc}") from exc
    return rows


def summarize(publish_root: Path, *, asset: str | None = None) -> dict:
    """สรุปพอที่จะตอบข้อ 3ก ได้ — จำนวนวัน กี่วันผ่าน และค่าที่ดีที่สุดที่เคยเห็น"""
    rows = read(ledger_path(publish_root))
    if asset:
        rows = [row for row in rows if row.get("asset") == asset]
    best = [row["best_rr"] for row in rows if row.get("best_rr") is not None]
    passed = [row for row in rows if row.get("any_pass")]
    return {
        "days": len(rows),
        "days_passed": len(passed),
        "pass_dates": [row["date"] for row in passed],
        "best_rr_seen": max(best) if best else None,
        "median_best_rr": sorted(best)[len(best) // 2] if best else None,
        "floor": chart_indicator_writer.RR_FLOOR,
        "first_date": rows[0]["date"] if rows else None,
        "last_date": rows[-1]["date"] if rows else None,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        description="สรุปสถิติ RR ของบทสไตล์ E (ข้อ 3ก — เก็บ 7–10 วันก่อนตัดสิน)")
    parser.add_argument("--publish-root", type=Path, default=Path("../output"))
    parser.add_argument("--asset", default=None)
    args = parser.parse_args(argv)

    report = summarize(args.publish_root, asset=args.asset)
    if not report["days"]:
        print("ยังไม่มีข้อมูลในสมุด — รอบผลิตสไตล์ E ยังไม่เคยเดินหลังเปิดสมุดนี้")
        return 0
    print(f"เก็บมา {report['days']} วัน ({report['first_date']} → {report['last_date']}) "
          f"· เกณฑ์ {report['floor']}")
    print(f"วันที่มีอย่างน้อยหนึ่งฝั่งแตะเกณฑ์: {report['days_passed']}/{report['days']} วัน")
    if report["pass_dates"]:
        print("   " + " · ".join(report["pass_dates"]))
    print(f"RR ดีที่สุดที่เคยเห็น: {report['best_rr_seen']:.2f}" if report["best_rr_seen"]
          else "ยังไม่เคยมีฝั่งไหนคำนวณ RR ได้เลย")
    if report["days"] < 7:
        print(f"⏳ ยังไม่ครบรอบที่หัวหน้าเคาะ (7–10 วัน) — เหลืออีกอย่างน้อย "
              f"{7 - report['days']} วันจึงจะสรุปได้")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
