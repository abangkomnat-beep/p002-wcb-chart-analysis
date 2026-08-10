"""ความจำโซนข้ามวันของสไตล์ D — "ล็อกโซนจนกว่าราคาทะลุ" (ผู้ใช้เคาะ 08-10 ข้อ #18ข)

ทำไมต้องมี: โซน/แนวต้าน/กรอบเดิมคำนวณสดทุกวัน คนอ่านประจำเห็นระดับกระโดด
ไปมาทั้งที่ราคาไม่ได้ทะลุอะไร — ความต่อเนื่องข้ามวันคือความน่าเชื่อถือของบท

ขอบเขตที่ผู้ใช้เคาะตอนอนุมัติแผน (08-10 ค่ำ):
- ล็อก 3 อย่าง: โซนรับ + แนวต้าน + กรอบแนวโน้ม (เฉพาะสไตล์ D)
- "ทะลุ" = แท่งรายวัน**ปิด**นอกระดับ — intraday แทงแล้วเด้งกลับไม่นับ
  (กติกาเดียวกับกฎแท่งปิด A-1 และภาษาที่บทใช้อยู่แล้ว "ยืนใต้...แบบปิดแท่งได้")
- โซนล็อกไกลราคาเกิน 2 วันติด → CC ยกไปทบทวนกับผู้ใช้ (ตัวเฝ้าอยู่ฝั่งรายงาน)

การไหลของข้อมูล (ตัดสินใจในแผน — I/O อยู่ที่ pipeline เท่านั้น):
    pipeline: locked = zone_memory.load(asset)
              story  = chart_story.build_story(rows, asset=..., locked=locked)
              zone_memory.save(asset, zone_memory.build_state(story))
`build_story` ไม่แตะดิสก์เอง — เทส/สคริปต์ที่เรียกตรงไม่มีทางเขียน state ปนของจริง

state หาย/พัง = คำนวณสดต่อ ไม่ตกทั้งบท — ความจำเป็นเรื่อง**ความต่อเนื่อง**
ไม่ใช่ความจริงของตัวเลข ค่าที่คำนวณสดยังถูกต้องเสมอ (ต่างจากด่านตัวเลขที่ fail-closed)
"""

import json
import os
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

SCHEMA = "zone-memory-v1"
# tracked ใน git (ระดับราคาไม่ใช่ความลับ) — ได้ประวัติตรวจย้อนฟรีตามแผน
STATE_DIR = _REPO_ROOT / "state"


def state_path(asset: str, state_dir: Path | None = None) -> Path:
    return (state_dir or STATE_DIR) / f"zones-{asset}.json"


def load(asset: str, state_dir: Path | None = None) -> dict | None:
    """อ่าน state — ไม่มี/พัง/schema ไม่ตรง = None (ผู้เรียกคำนวณสดต่อ)"""
    path = state_path(asset, state_dir)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(state, dict) or state.get("schema") != SCHEMA:
        return None
    return state


def save(asset: str, state: dict, state_dir: Path | None = None) -> Path:
    """เขียนแบบ atomic (temp + replace) — หลายเซสชันใช้รีโปเดียวกันจริง (เกิด 08-05/06)"""
    path = state_path(asset, state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=1)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    # ให้เทสยืนยันได้ว่าไม่มีไฟล์ .tmp ค้าง — นามสกุลสุดท้ายเป็น .json เสมอ
    return path


def build_state(story: dict, previous: dict | None = None) -> dict:
    """สร้าง state จาก story ที่เพิ่งผลิต — `locked_since` ไหลมากับระดับที่ล็อกอยู่แล้ว

    ระดับที่มาจากความจำมี `locked_since` เดิมติดตัว · ระดับใหม่ (คำนวณสดรอบนี้)
    เริ่มนับวันล็อกที่วันนี้ · `previous` รับไว้เพื่อความชัดของ call-site เท่านั้น
    """
    del previous  # ข้อมูลที่ต้องส่งต่ออยู่ใน story ครบแล้ว
    today = story["current"]["date"]
    channel = story.get("channel")
    return {
        "schema": SCHEMA,
        "asset": story["asset"],
        "as_of": today,
        "zones": [{"mean": z["mean"], "low": z["low"], "high": z["high"],
                   "locked_since": z.get("locked_since", today)}
                  for z in story["zones"]],
        "resistance": [{"mean": r["mean"],
                        "locked_since": r.get("locked_since", today)}
                       for r in story["resistance"]],
        "channel": None if not channel else {
            "start_date": channel["start_date"],
            "slope": channel["slope"],
            "intercept": channel["intercept"],
            "offset": channel["offset"],
            "main_is_upper": channel["main_is_upper"],
            "touch_count": channel["touch_count"],
            "locked_since": channel.get("locked_since", today),
        },
    }


def closes_after(rows: list[dict], date_text: str) -> list[dict]:
    """แท่งปิดที่อยู่หลังวันที่กำหนด — ใช้ตัดสิน "ทะลุ" (idempotent: เช็คซ้ำได้ผลเดิม)"""
    return [row for row in rows if row["date"] > date_text]


def zone_broken(zone: dict, rows: list[dict]) -> bool:
    """โซนรับแตกเมื่อมีแท่ง**ปิด**ใต้ขอบล่าง หลังวันที่ล็อก"""
    return any(row["close"] < zone["low"]
               for row in closes_after(rows, zone["locked_since"]))


def level_broken(level: dict, rows: list[dict]) -> bool:
    """แนวต้านแตกเมื่อมีแท่ง**ปิด**เหนือเส้น หลังวันที่ล็อก"""
    return any(row["close"] > level["mean"]
               for row in closes_after(rows, level["locked_since"]))
