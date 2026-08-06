"""ชั้นเลือกว่า "รอบนี้บทไหนขึ้นเว็บ" — คนละคำถามกับ "บทไหนผลิตได้"

ตั้งแต่ 2026-08-06 หัวหน้าตอบใบคำถาม P002 ข้อ 3 ว่า **วันละ 1 บท เฉพาะทองคำ
สไตล์เดียว** ส่วนหัวข้ออื่นให้ผลิตเก็บไว้ได้แต่ยังไม่ขึ้นเว็บ

สายท่อจึงยังผลิตครบเหมือนเดิมทุกหัวข้อทุกสไตล์ (ห้ามลดกำลังผลิตเพราะนโยบายเผยแพร่
เปลี่ยน — วันที่นโยบายเปลี่ยนกลับจะไม่มีของเทียบ และงานที่หายไปจะเงียบ) แล้วชั้นนี้
วาง**สำเนาใบเดียว**ไว้ในโฟลเดอร์ที่ชี้ชัดว่าใบนี้คือใบที่ต้องเอาไปวาง

**ทำไมต้องมีโฟลเดอร์นี้ ทั้งที่คนเปิดหาไฟล์เองก็ได้:** ปลายทางตั้งชื่อบทจาก
สินทรัพย์ + วันที่ ⇒ ถ้าเผลอวางสองสไตล์ของวันเดียวกัน **ไฟล์ทับกันเอง** โดยไม่มี
อะไรฟ้อง (ทีมเว็บยืนยัน 2026-08-06) · โฟลเดอร์ที่มีไฟล์เดียวเสมอทำให้พลาดแบบนั้นยาก

**โฟลเดอร์นี้สะท้อนรอบล่าสุดเสมอ** — ล้างก่อนเขียนทุกครั้ง เหตุผลเดียวกับ
`publish_layout._clear_stale`: ใบของเมื่อวานที่ค้างอยู่ในโฟลเดอร์ชื่อ "ขึ้นเว็บวันนี้"
คือกับดักที่แพงที่สุดของโฟลเดอร์แบบนี้

รันเดี่ยว ๆ ได้ (ปกติ `run_daily` เรียกให้เองท้ายรอบ):

    python -m tools.publish_selection ../output/06-082026
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import wcb_writers  # noqa: E402

POLICY_PATH = _REPO_ROOT / "config" / "publishing_policy.json"
READ_ME = "อ่านก่อน.md"


class SelectionUnavailable(RuntimeError):
    """เลือกใบขึ้นเว็บไม่ได้ — ต้องบอกว่าเพราะอะไร ห้ามวางโฟลเดอร์ว่างไว้เฉย ๆ

    โฟลเดอร์ว่างกับ "วันนี้ไม่มีบทให้ขึ้น" หน้าตาเหมือนกันเป๊ะ ⇒ ต้องมีใบอธิบาย
    วางแทนเสมอ ไม่งั้นคนเปิดจะคิดว่าระบบยังไม่ได้รัน
    """


def load_policy(path: Path | None = None) -> dict:
    return json.loads((path or POLICY_PATH).read_text(encoding="utf-8"))


def style_folder(writer_id: str) -> str:
    for writer in wcb_writers.WCB_WRITERS:
        if writer["id"] == writer_id:
            return writer["folder"]
    raise SelectionUnavailable(
        f"นโยบายชี้สไตล์ '{writer_id}' ซึ่งไม่มีในทะเบียนนักเขียนสายเว็บ "
        f"(มีอยู่: {', '.join(w['id'] for w in wcb_writers.WCB_WRITERS)})")


def select(day_dir: Path, *, policy: dict | None = None) -> dict:
    """วางใบที่ต้องเอาขึ้นเว็บไว้ในโฟลเดอร์ของมัน แล้วคืนสรุปว่าเลือกใบไหนเพราะอะไร

    ไม่โยนเมื่อหาไฟล์ไม่เจอ — คืน `status: "missing"` พร้อมเหตุผล แล้ววางใบอธิบายไว้
    เพราะวันที่หัวข้อนั้นตกด่านเป็นเรื่องที่เกิดได้ตามปกติ (fail-closed ของด่านตรวจ)
    ไม่ใช่ระบบพัง ⇒ ไม่ควรทำให้ทั้งรอบ exit ไม่เป็นศูนย์
    """
    policy = policy or load_policy()
    asset = policy["web_asset"]
    folder = style_folder(policy["web_style"])
    target = day_dir / policy.get("selection_folder", "0-ขึ้นเว็บวันนี้")
    source = day_dir / folder / f"{asset}.md"

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    if not source.is_file():
        (target / READ_ME).write_text(_missing_note(policy, folder, asset), encoding="utf-8")
        return {"status": "missing", "asset": asset, "style_folder": folder,
                "expected": str(source), "directory": str(target)}

    placed = target / source.name
    shutil.copyfile(source, placed)
    (target / READ_ME).write_text(_ready_note(policy, folder, asset, source.name),
                                  encoding="utf-8")
    return {"status": "ready", "asset": asset, "style_folder": folder,
            "article": str(placed), "directory": str(target)}


def _ready_note(policy: dict, folder: str, asset: str, filename: str) -> str:
    others = ", ".join(policy.get("produced_but_not_published") or []) or "— ไม่มี"
    return "\n".join([
        "# ใบที่ต้องเอาขึ้นเว็บรอบนี้",
        "",
        f"เปิดไฟล์ **`{filename}`** ในโฟลเดอร์นี้ คัดลอกทั้งไฟล์ไปวางในหน้าหลังบ้าน",
        "ระบบเว็บอ่านส่วนหัวเองและวาดกราฟจากหมุด `[[chart:...]]` ให้ (ใช้เวลา 5–15 วินาที)",
        "",
        "> ⚠️ **กดแล้วขึ้นเว็บทันที ไม่มีคิวรอตรวจ** — คนอ่านเห็นเลย",
        "> ลบออกได้ที่หน้าเดียวกันถ้าพลาด",
        "",
        "## ทำไมมีใบเดียว",
        "",
        f"- นโยบายรอบนี้: **วันละ {policy.get('articles_per_day', 1)} บท** · หัวข้อ **{asset}** · สไตล์ **{folder}**",
        f"- ผู้ตัดสิน: {policy.get('decided_by', '—')}",
        f"- เหตุผล: {policy.get('reason', '—')}",
        "",
        "## หัวข้ออื่นของวันนี้",
        "",
        f"ผลิตครบและผ่านด่านแล้วเหมือนเดิม ({others}) แต่**ยังไม่ขึ้นเว็บ**",
        "อยู่ในโฟลเดอร์สไตล์ข้าง ๆ ตามปกติ ใช้อ่านภายในและเก็บเป็นของเทียบได้",
        "",
        "> 🪤 **ห้ามวางสองสไตล์ของวันเดียวกัน** — เว็บตั้งชื่อบทจากสินทรัพย์+วันที่",
        "> ใบที่วางทีหลังจะทับใบแรกโดยไม่มีอะไรฟ้อง",
        "",
    ])


def _missing_note(policy: dict, folder: str, asset: str) -> str:
    return "\n".join([
        "# รอบนี้ยังไม่มีใบให้ขึ้นเว็บ",
        "",
        f"นโยบายชี้ให้ใช้ **{asset}** สไตล์ **{folder}** แต่รอบนี้ไม่มีไฟล์นั้นในโฟลเดอร์วัน",
        "",
        "แปลว่าอย่างใดอย่างหนึ่ง — เปิดบรรทัดสรุปของรอบเพื่อดูว่าอันไหน:",
        "",
        "1. หัวข้อนั้น**ตกด่านตรวจ** ⇒ ไม่มีไฟล์ตามกติกา fail-closed (พฤติกรรมถูก)",
        "2. สายท่อสะดุดก่อนถึงหัวข้อนั้น เช่นดึงข้อมูลไม่ได้หรือก้อนไม่สด",
        "",
        "**ห้ามหยิบสไตล์อื่นหรือหัวข้ออื่นขึ้นแทนเอง** — นโยบายเผยแพร่ผ่านผู้ใช้มา",
        "การสลับเองทำให้วันที่มีปัญหากับวันปกติแยกไม่ออกบนหน้าเว็บ",
        "",
    ])


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        print("ใช้: python -m tools.publish_selection <โฟลเดอร์วัน เช่น ../output/06-082026>")
        return 2
    result = select(Path(args[0]))
    if result["status"] == "ready":
        print(f"ใบขึ้นเว็บรอบนี้: {result['article']}")
        return 0
    print(f"⚠️ ยังไม่มีใบให้ขึ้นเว็บ — คาดว่าจะเจอที่ {result['expected']} "
          f"(ดูคำอธิบายใน {result['directory']}/{READ_ME})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
