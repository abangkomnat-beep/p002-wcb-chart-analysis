"""ชั้นข่าวสำรองของสายเว็บ A/B/C — **ปิดสวิตช์ไว้ตั้งแต่วันแรก (2026-08-07)**

## เรื่องนี้มีไว้ทำไม

สายเว็บอ่านข่าวจากก้อน snapshot ของ WCB ตรง ๆ สองช่อง (`news` + `macroNews`)
แต่ทีมเว็บแจ้งเองว่า **โรงงานข่าวยังไม่ได้ต่อเข้าเว็บ** ⇒ วัดจริง 2026-08-07:
ทุกหัวข้อได้พาดหัวชิ้นเดียวลงวันที่ 2026-07-23 (เก่า 15 วัน) บททุกใบจึงเขียนว่า
"ฝั่งข่าวเงียบผิดปกติ" ทุกวัน

ขณะเดียวกัน ชั้นฟีดตรง 21 ตัว (`news_source`) ที่เราสร้างไว้แล้วให้ข่าวสดตรงหัวข้อ
ครบทั้งห้าตัวในวันเดียวกัน — **แต่มันป้อนสายภายใน ①②③ ซึ่งเลิกเผยแพร่ไปแล้ว**
โมดูลนี้คือสะพานที่ขาดอยู่

## ⛔ ทำไมถึงปิดสวิตช์ไว้

การเอา**ชื่อสำนักข่าวภายนอกขึ้นบทที่ลงเว็บของ WCB** ไม่ใช่เรื่องที่เราตัดสินเองได้ —
เป็นข้อ **E11** ใน `EXTERNAL.md` ส่งถามหัวหน้าไปแล้ว 2026-08-06 ยังไม่ได้คำตอบ
⇒ ผู้ใช้สั่ง 2026-08-07 ว่า **"เดินทาง ก แบบปิดสวิตช์ไว้ก่อน"**

**เปิดใช้ได้เมื่อหัวหน้าตอบ E11 ว่าใช้ได้เท่านั้น** — เปิดโดยแก้ `config/news_sources.json`
ช่อง `web_line_fallback.enabled` เป็น `true` ไม่ต้องแก้โค้ด · **ห้ามเปิดเองโดยไม่มีคำตอบ**

## ลำดับความสำคัญที่ห้ามสลับ

มติผู้ใช้ข้อ 10: **ข่าวของเว็บ WCB เป็นลำดับ 1 เสมอ** ⇒ ชั้นนี้ทำงานเฉพาะตอนที่
ลำดับ 1 **ไม่มีของหรือของเก่าเกินวันข้อมูล** เท่านั้น มีของสดเมื่อไหร่ชั้นนี้ไม่แตะเลย

## 🪤 กับดักตัวเลขในพาดหัว (เหตุผลที่ต้องกรองทิ้ง)

ด่าน `wcb_copy_validator` บังคับว่า **เลขทุกตัวในบทต้องชี้กลับก้อน snapshot ได้**
บทยกพาดหัวขึ้นมาทั้งบรรทัด ("พาดหัวล่าสุดคือ …") ⇒ พาดหัวอย่าง
*"Nvidia … Are Up Over 1,000% Since the AI Boom"* จะพาเลข `1,000` เข้าบท
ซึ่ง**ไม่มีวันอยู่ในก้อน snapshot** ⇒ บททั้งใบตกด่าน `number_unsupported`

**ทางที่เลือก (จงใจลัด · รู้เพดาน):** ทิ้งพาดหัวที่มีตัวเลขไปเลย
- วัดแล้วเสียประมาณ 2 ใน 8 ชิ้นของวันที่วัด (2026-08-07) — ยอมรับได้
- **ไม่แตะด่านตัวเลขแม้แต่นิดเดียว** ซึ่งเป็นด่านที่แพงที่สุดถ้าพัง (YMYL)
- **ทางอัปเกรดถ้าวันหน้าอยากได้พาดหัวที่มีเลข:** ส่งเลขจากพาดหัวที่ใช้จริงเข้า
  พารามิเตอร์ `allow` ของ `wcb_copy_validator.validate()` (รูปแบบเดียวกับ
  `plan_numbers` ของหัวข้อแผน) **ห้ามผ่อนด่านเป็นการทั่วไป**
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "news_sources.json"
CHANNEL = "fallback_direct"
# พาดหัวที่มีเลขอารบิกแม้ตัวเดียวถูกทิ้ง — ดูเหตุผลในหัวข้อ "กับดักตัวเลขในพาดหัว"
HAS_DIGIT = re.compile(r"\d")


def load_settings(config_path: Path | None = None) -> dict:
    """อ่านสวิตช์จากทะเบียน — ไฟล์หายหรือไม่มีช่องนี้ = ถือว่าปิด (fail-closed)"""
    path = config_path or CONFIG_PATH
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False, "reason": "อ่านทะเบียนไม่ได้"}
    settings = dict(config.get("web_line_fallback") or {})
    settings.setdefault("enabled", False)
    return settings


def _date_part(stamp) -> str:
    return str(stamp or "")[:10]


def snapshot_news_usable(evidence: dict) -> tuple[bool, str]:
    """ข่าวจากลำดับ 1 ใช้ได้ไหม — คืน (ใช้ได้, เหตุผล)

    เกณฑ์เดียวกับที่ `wcb_writers._news_paragraph` ใช้ตัดสินว่าจะยกพาดหัวขึ้นบทไหม
    **ต้องตรงกันเสมอ** ไม่งั้นจะเกิดสภาพที่ชั้นนี้คิดว่าลำดับ 1 พอแล้ว
    แต่ตัวเขียนกลับเขียนว่า "ฝั่งข่าวเงียบ"
    """
    headlines = evidence.get("headlines") or []
    if not headlines:
        return False, "ก้อน snapshot ไม่มีข่าวเลย"
    newest = _date_part(headlines[0].get("published_at"))
    data_date = _date_part(evidence.get("local_date"))
    if newest and data_date and newest < data_date:
        return False, f"ข่าวในก้อนเก่ากว่าวันข้อมูล (ข่าว {newest} · ข้อมูล {data_date})"
    return True, "ก้อน snapshot มีข่าวที่ใช้ได้"


def to_headline(item: dict) -> dict:
    """แปลงข่าวจากชั้นฟีดตรงให้เป็นรูปเดียวกับพาดหัวของก้อน snapshot

    เก็บ `source` / `source_tier` ต่อท้ายไว้ด้วย เพราะบทฝั่งสายภายในอ้างชื่อสำนักข่าว
    และวันที่เปิดใช้จริงสายเว็บน่าจะต้องอ้างเหมือนกัน — เก็บไว้ตอนนี้ดีกว่าต้องรื้อทีหลัง
    """
    return {
        "title": item.get("title"),
        "published_at": _date_part(item.get("published_at")),
        "slug": None,
        "url": item.get("link"),
        "category": item.get("theme_id"),
        "subcat": None,
        "channel": CHANNEL,
        "source": item.get("source"),
        "source_tier": item.get("source_tier"),
    }


def apply(evidence: dict, *, asset: str, collector=None, now: datetime | None = None,
          config_path: Path | None = None) -> dict:
    """เติมข่าวสำรองลง `evidence["headlines"]` เมื่อเข้าเงื่อนไข — คืน log ไว้เขียนไฟล์

    **แก้ `evidence` ที่ส่งเข้ามาโดยตรงเมื่อเติมจริงเท่านั้น** · ทุกเส้นทางคืน log
    ที่บอกได้ว่าทำอะไรและเพราะอะไร เพื่อให้ตรวจย้อนได้ว่าวันไหนบทใช้ข่าวจากชั้นไหน
    """
    settings = load_settings(config_path)
    log = {
        "asset": asset,
        "enabled": bool(settings.get("enabled")),
        "used": False,
        "added": 0,
        "dropped_with_digits": 0,
        "checked_at": (now or datetime.now(tz=timezone.utc)).isoformat(timespec="seconds"),
    }

    usable, reason = snapshot_news_usable(evidence)
    log["snapshot_news"] = reason

    if not log["enabled"]:
        # ปิดอยู่ = ไม่เรียกฟีดเลย ไม่ใช่เรียกแล้วทิ้ง — ปิดสวิตช์ต้องไม่มีการยิงเครือข่าย
        log["reason"] = ("สวิตช์ปิดอยู่ — รอคำตอบ E11 จากหัวหน้าว่าใช้ข่าวสำนักภายนอก"
                         "ในบทที่ขึ้นเว็บได้ไหม")
        return log
    if usable:
        log["reason"] = "ลำดับ 1 (ข่าวเว็บ WCB) มีของใช้ได้ — ชั้นสำรองไม่ทำงาน"
        return log

    if collector is None:
        from tools import news_source  # นำเข้าตอนใช้จริง — ปิดสวิตช์แล้วไม่ต้องโหลด
        collector = news_source.collect
    try:
        collected = collector(asset, now=now or datetime.now(tz=timezone.utc))
    except Exception as exc:  # noqa: BLE001 — ข่าวล้มไม่หยุดสายท่อ (ต่างจากราคา)
        log["reason"] = f"ชั้นสำรองล้ม: {type(exc).__name__}: {exc}"
        return log

    items = collected.get("items") or []
    kept = [to_headline(item) for item in items
            if item.get("title") and not HAS_DIGIT.search(item["title"])]
    log["dropped_with_digits"] = len(
        [i for i in items if i.get("title") and HAS_DIGIT.search(i["title"])])
    log["provider_used"] = collected.get("provider_used")

    if not kept:
        log["reason"] = ("ชั้นสำรองไม่มีข่าวที่ใช้ได้"
                         + (f" (ทิ้งเพราะมีตัวเลขในพาดหัว {log['dropped_with_digits']} ชิ้น)"
                            if log["dropped_with_digits"] else ""))
        return log

    evidence["headlines"] = kept
    log.update({"used": True, "added": len(kept),
                "reason": f"ใช้ข่าวจากชั้นสำรอง {len(kept)} ชิ้น เพราะ{reason}",
                "titles": [item["title"] for item in kept]})
    return log
