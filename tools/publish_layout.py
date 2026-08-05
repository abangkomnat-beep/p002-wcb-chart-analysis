"""ชั้นจัดวางไฟล์ที่ผู้ใช้เอาไปอัปจริง — แยกขาดจากกองไฟล์ทำงานของสายท่อ

ก่อนหน้านี้โฟลเดอร์ผลผลิตปนกันสามอย่างในที่เดียว: ไฟล์ที่เอาไปอัป · ไฟล์หลักฐาน
ฝั่ง internal · และรหัส batch ที่คนอ่านไม่รู้ว่าแปลว่าอะไร ผู้ใช้เปิดแล้วหาไม่เจอว่า
ต้องหยิบไฟล์ไหน (คำสั่งผู้ใช้ 2026-08-04 — "ไฟล์ output ดูแล้วงงมาก ตัดเรื่อง internal ออก")

โครงที่ผู้ใช้สั่ง — มีแค่นี้ ไม่มีอย่างอื่นปนในโฟลเดอร์ที่ผู้ใช้เปิด:

    output/04-082026/1-ณธาร-รายงานตลาด/xauusd.md
                                       /xauusd.png
                    /2-กฤช-โครงสร้างราคา/xauusd.md
                                       /xauusd.png
                    /3-ปุณณ์-จังหวะตลาด/ ...

ชื่อไฟล์ .md กับ .png ตรงกันทุกคู่ เพื่อให้จับคู่ตอนอัปขึ้นเว็บได้โดยไม่ต้องเปิดดู
ไฟล์หลักฐาน ผลด่าน และของฝั่ง internal ทั้งหมดไปอยู่ใต้ `work/build/` แทน
— ยังครบเหมือนเดิมทุกไฟล์ ไม่ได้ตัดทิ้ง แค่ย้ายออกจากสายตา
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import public_copy_validator, voice_rules, writers  # noqa: E402


def day_folder(cutoff_at: str) -> str:
    """ชื่อโฟลเดอร์รายวันตามที่ผู้ใช้สั่ง — วันเวลาไทย รูปแบบ DD-MMYYYY เช่น 04-082026"""
    key = voice_rules.thai_day_key(cutoff_at)
    if key is None:
        raise ValueError(f"อ่านเวลา '{cutoff_at}' ไม่ออก จึงตั้งชื่อโฟลเดอร์วันไม่ได้")
    return key


def publish_asset(*, asset: str, article_data: dict, technical_evidence: dict,
                  chart_source: Path, publish_root: Path, cutoff_at: str,
                  instrument_type: str, trade_branch: dict | None = None) -> dict:
    """เขียนบทความสามสไตล์ของสินทรัพย์หนึ่งตัวลงโครงที่ผู้ใช้เปิดใช้จริง

    แต่ละสไตล์ผ่านด่านตรวจของตัวเองก่อนเสมอ — **ไม่ผ่าน = ไม่มีไฟล์ในโฟลเดอร์นั้น**
    เหมือนกติกาเดิมของสไตล์ ① ทุกประการ (fail-closed) เพราะไฟล์ที่วางอยู่ในโฟลเดอร์นี้
    แปลว่า "หยิบไปอัปได้เลย" ถ้าปล่อยของที่ยังไม่ผ่านลงมาปน ความหมายนั้นจะหายไปทันที

    `trade_branch` คือผลของสาขาแผนการเทรดฝั่ง internal — ชั้นนี้ไม่ตัดสินเองว่าแผนไหน
    พูดได้ ปล่อยให้ `writers.plan_for_public` เป็นคนตัดสินที่เดียว แล้วส่งต่อเฉพาะ
    นักเขียนที่ประกาศว่าใช้แผน (`uses_trade_plan`) — คนอื่นไม่ได้รับแม้แต่ค่าเดียว
    """
    day = publish_root / day_folder(cutoff_at)
    plan = writers.plan_for_public(trade_branch)
    results = []
    for writer in writers.WRITERS:
        writer_plan = plan if writer.get("uses_trade_plan") else None
        markdown = writer["render"](article_data, chart_name=f"{asset}.png", plan=writer_plan)
        evidence = {"article": article_data, "technical": technical_evidence}
        ratio_values = None
        if writer_plan:
            # หลักฐานของหัวข้อแผนเข้ากองเฉพาะสไตล์ที่เขียนหัวข้อนั้นจริง
            # ไม่งั้นสไตล์อื่นจะได้เลขชุดใหญ่ขึ้นฟรี ๆ ทั้งที่ไม่ได้ใช้
            evidence["trade_plan"] = writers.plan_evidence(writer_plan)
            ratio_values = writers.plan_ratio_values(writer_plan)
        validation = public_copy_validator.validate(
            markdown,
            evidence=evidence,
            instrument_type=instrument_type,
            profile=writer["profile"],
            ratio_values=ratio_values,
        )
        entry = {
            "writer_id": writer["id"],
            "pen_name": writer["pen_name"],
            "style": writer["style"],
            "folder": writer["folder"],
            "status": validation["status"],
            "word_count": validation["word_count"],
            "fatal_count": validation["fatal_count"],
            "trade_plan_included": bool(writer_plan),
            "findings": validation["findings"],
        }
        if validation["status"] == "pass":
            target = day / writer["folder"]
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{asset}.md").write_text(markdown, encoding="utf-8")
            shutil.copyfile(chart_source, target / f"{asset}.png")
            entry["article"] = str(target / f"{asset}.md")
            entry["chart"] = str(target / f"{asset}.png")
        results.append(entry)
    return {"asset": asset, "day": day_folder(cutoff_at), "directory": str(day),
            "trade_plan_public": _plan_note(trade_branch, plan),
            "writers": results}


def _plan_note(trade_branch: dict | None, plan: dict | None) -> dict:
    """บันทึกว่าหัวข้อแผนขึ้นบทความหรือไม่ **และเพราะอะไร**

    วันที่ไม่มีหัวข้อแผนต้องแยกออกได้ว่าเป็น "วันนี้ไม่มีจังหวะจริง" หรือ "ระบบพัง"
    ถ้าไม่บันทึกเหตุผลไว้ ทั้งสองกรณีจะหน้าตาเหมือนกันเป๊ะคือหัวข้อหายไปเฉย ๆ
    """
    if plan:
        return {"included": True, "reason": None,
                "classification": plan["classification"], "bias": plan["bias"],
                "rr_first_target": plan["targets"][0]["rr"]}
    branch = trade_branch or {}
    status = branch.get("status")
    if status != "built":
        return {"included": False, "reason": f"trade_branch_status:{status or 'missing'}"}
    inner = branch.get("plan") or {}
    if inner.get("classification") == "no_trade":
        return {"included": False, "reason": "no_trade",
                "detail": inner.get("detail") or inner.get("reason")}
    return {"included": False, "reason": "risk_audit_blocking_finding",
            "detail": [item["id"] for item in (branch.get("audit") or {}).get("findings") or []
                       if item["severity"] == "blocking"]}
