"""ระยะ 1 — จับคู่ "ตัวเลขที่เพิ่งประกาศ" เข้ากับ "สินทรัพย์ที่ควรเขียนถึง"

โมดูลนี้ **ไม่แตะสายผลิตรายวัน** ตัวคัดปฏิทินของบท A/B/C/D คือ
`wcb_writers._calendar_events` ซึ่งกรองเฉพาะสหรัฐและถูกล็อกด้วยเทสไว้แล้ว
(ย่อหน้าสายส่งมหภาคของแต่ละสินทรัพย์เขียนไว้ว่าอ่านได้เฉพาะฝั่งสหรัฐ)
บทรายเหตุการณ์เป็นคนละชนิดกัน จึงมีตัวคัดของตัวเองที่นี่ **ห้ามยุบสองตัวนี้เข้าด้วยกัน**

ที่มาของตัวเลข: ช่อง `actual` ในปฏิทินของก้อน snapshot — วัดเอง 2026-08-07
ว่าค่ามาถึงเราภายใน 30 วินาทีหลังเวลาประกาศ (ดุลการค้ายูโรโซน 13:00:00 น. →
เห็นค่า 13:00:30 น. · รอบก่อนหน้า 12:59:29 น. ยังว่าง · 14 รอบไม่มีรอบไหนพลาด)

⚠️ **ค่า `previous` ถูกทบทวนย้อนหลังได้ภายในวันเดียวกัน** — เห็นจริงวันเดียวกัน
ดุลการค้ายูโรโซนให้ `€19.1` ตลอด 11:18–13:02 แล้วเปลี่ยนเป็น `€19.3` ตอน 14:36
⇒ บทหนึ่งใบต้องอ่านจากก้อนเดียวทั้งใบ **ห้ามหยิบคนละช่องจากคนละรอบยิงมาปนกัน**
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "event_impact.json"


def load(config_path: Path | None = None) -> dict:
    """อ่านทะเบียน — **ห้ามใส่ค่าตั้งต้นเวลาอ่านไม่ได้**

    ทะเบียนหายหรือพัง = เราไม่รู้ว่ารายการไหนกระทบอะไร การเดาต่อคือการเขียนบท
    ถึงสินทรัพย์ที่อาจไม่เกี่ยวกับตัวเลขนั้นเลย ⇒ ให้ระเบิดตรงนี้ ไม่ใช่เงียบแล้วเขียนผิด
    """
    return json.loads((config_path or CONFIG_PATH).read_text(encoding="utf-8"))


def has_actual(event: dict) -> bool:
    return event.get("actual") not in (None, "")


def released_events(calendar: list[dict], settings: dict) -> list[dict]:
    """รายการที่ **ประกาศแล้ว** และสำคัญพอจะเขียนถึง เรียงตามเวลา

    ไม่กรองประเทศตรงนี้ — ประเทศที่ยังไม่ลงทะเบียนจะได้สินทรัพย์ว่างจาก
    `assets_for()` แล้วหลุดออกเองในขั้นวางแผน ทำให้ผู้เรียกยังนับได้ว่า
    "รอบนี้มีตัวเลขออกกี่รายการ และตกไปกี่รายการเพราะยังไม่ลงทะเบียน"
    """
    allowed = set(settings.get("minimum_impact") or [])
    events = [e for e in calendar if has_actual(e) and (not allowed or e.get("impact") in allowed)]
    return sorted(events, key=lambda e: str(e.get("at") or ""))


def assets_for(event: dict, settings: dict) -> list[str]:
    """สินทรัพย์ที่ควรเขียนถึงเมื่อรายการนี้ประกาศ — ตัดด้วยตัวที่เปิดผลิตอยู่จริง

    คืนลิสต์ว่างเมื่อสกุลเงินยังไม่ลงทะเบียน ซึ่งแปลว่า **ยังไม่ตัดสิน**
    ไม่ใช่ "ไม่มีผล" (ดูช่อง `ยังไม่ลงทะเบียนโดยตั้งใจ` ในทะเบียน)
    """
    related = settings.get("currency_assets", {}).get(event.get("country")) or []
    enabled = settings.get("assets_enabled_now")
    if enabled is None:            # ไม่ระบุ = ผลิตทุกตัวที่เกี่ยวข้อง
        return list(related)
    order = {asset: i for i, asset in enumerate(enabled)}
    return sorted((a for a in related if a in order), key=lambda a: order[a])


def plan(calendar: list[dict], settings: dict | None = None) -> list[dict]:
    """ใบสั่งงานของรอบนี้ — รายการไหนประกาศแล้ว ต้องเขียนถึงสินทรัพย์ใดบ้าง

    รายการที่ไม่มีสินทรัพย์เลยยังถูกคืนกลับไปพร้อม `assets: []` โดยตั้งใจ
    เพื่อให้ผู้เรียก **รายงานได้ว่าตกไปเพราะอะไร** แทนที่จะหายเงียบ
    (กติกา "no silent caps" — ของที่ถูกตัดต้องเห็น)
    """
    settings = settings if settings is not None else load()
    return [{"event": event, "assets": assets_for(event, settings)}
            for event in released_events(calendar, settings)]
