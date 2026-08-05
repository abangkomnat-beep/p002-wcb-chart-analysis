"""ค่าเกณฑ์ความเสี่ยงที่ตัวสร้างแผนกับด่านตรวจใช้ร่วมกัน

**ทำไมต้องมีโมดูลนี้แยกออกมา** — `risk_auditor` นำเข้า `trade_plan` อยู่แล้ว
(ผู้ตรวจต้องรู้จักโครงของแผนที่ตรวจ) การให้ `trade_plan` อ่านค่าจาก `risk_auditor`
กลับไปจึงทำให้นำเข้าวนกันและระบบพังตั้งแต่ import (CC พบตอนตรวจแผนทาง ค 2026-08-05)

ค่าจึงอยู่ในไฟล์ config และมีโมดูลบาง ๆ ตัวนี้เป็นทางเข้าเดียว — ทั้งสองฝั่งนำเข้า
ที่นี่ ไม่มีใครนำเข้าใคร · แบบแผนเดียวกับ `indicators.load_minimum_bars()`

**ผลพลอยได้ที่ตั้งใจ:** ค่าที่ผู้ใช้ล็อก (จุด ✋3) จะไปอยู่ในไฟล์ config ที่เปิดอ่าน
ได้โดยไม่ต้องเปิดโค้ด และมีช่อง `locked_at` / `locked_by` บันทึกว่าใครล็อกเมื่อไหร่
"""

from __future__ import annotations

import json
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "risk_thresholds.json"

REQUIRED_KEYS = ("minimum_rr", "minimum_stop_atr", "maximum_entry_atr")


def load(path: Path | None = None) -> dict:
    """อ่านค่าเกณฑ์ — ขาดค่าใดค่าหนึ่ง = โยนทันที ไม่เติมค่าตั้งต้นให้เงียบ ๆ

    เกณฑ์ที่หายไปแล้วถูกแทนด้วยค่าเดาในโค้ด คือเกณฑ์ที่ไม่มีใครรู้ว่าใช้ค่าอะไรอยู่
    ซึ่งอันตรายกว่าระบบที่ไม่ยอมเริ่มทำงาน
    """
    payload = json.loads((path or CONFIG_PATH).read_text(encoding="utf-8"))
    thresholds = payload.get("thresholds") or {}
    missing = [key for key in REQUIRED_KEYS if key not in thresholds]
    if missing:
        raise KeyError(f"ไฟล์เกณฑ์ความเสี่ยงขาดค่า: {', '.join(missing)}")
    return {key: float(thresholds[key]) for key in REQUIRED_KEYS}


def lock_status(path: Path | None = None) -> dict:
    """ค่าถูกผู้ใช้ล็อกแล้วหรือยัง — ใช้รายงาน ไม่ได้ใช้ตัดสินอะไรในสายท่อ"""
    payload = json.loads((path or CONFIG_PATH).read_text(encoding="utf-8"))
    return {
        "locked": bool(payload.get("locked_at")),
        "locked_at": payload.get("locked_at"),
        "locked_by": payload.get("locked_by"),
        "note": payload.get("lock_note"),
    }
