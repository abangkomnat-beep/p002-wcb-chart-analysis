"""ตัวเลือกบทของสายระหว่างวัน — "ออกบ่อยขึ้น" โดยไม่กลายเป็นบทซ้ำ

โจทย์จริงของหัวหน้าคือ *อยากมีงานออกบ่อยขึ้น* และคำตอบที่ผิดคือ "ผลิตทุกแท่ง"
เพราะ M15 ปิดวันละเกือบร้อยแท่ง ผลที่ได้จะเป็นบทที่เหมือนกันร้อยใบต่อวัน ซึ่งทำร้าย
ทั้งคนอ่านและหน้าเว็บ (สาระเดียวกันหลายหน้า = แย่งอันดับกันเอง)

คำตอบที่ถูกคือ **ผลิตเมื่อสถานะของตลาดเปลี่ยนจริง** (ข้อเสนอ §36) และเมื่อรอบหนึ่ง
มีหลายสไตล์เปลี่ยนพร้อมกัน ให้ออกใบเดียวที่มีเรื่องเล่าใหญ่สุด ส่วนที่เหลือเก็บเป็น
หลักฐานภายใน (§48) — สองข้อนี้รวมกันคือหน้าที่ทั้งหมดของไฟล์นี้

⚖️ **เกณฑ์เลือกไม่ใช่ "สัญญาณแรงสุด" แต่เป็น "มีเรื่องให้เขียนที่คนอ่านเห็นความต่าง"**
(ข้อเสนอ §83) — สถานะที่นิ่งอยู่กับที่มีค่าทางเทคนิคได้ แต่ไม่มีค่าทางบทความ
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import intraday_breakout_story as breakout  # noqa: E402
from tools import intraday_pullback_story as pullback  # noqa: E402
from tools import intraday_story  # noqa: E402
from tools import intraday_trend_story as trend  # noqa: E402

SCHEMA = "intraday-selection-v1"

# คะแนนความคุ้มค่าที่จะเป็นบท — ยิ่งสูงยิ่งมีเรื่องเล่าที่คนอ่านเห็นความต่างชัด
#
# ค่าพวกนี้ไม่ใช่ "ความแรงของสัญญาณ" แต่เป็น **ความคุ้มค่าที่จะเป็นบทความ**:
# การทะลุกรอบที่ล้มเหลวได้คะแนนสูงพอ ๆ กับการทะลุสำเร็จ เพราะมันเล่าเรื่องได้ดีเท่ากัน
# ส่วนสถานะ "ปกติ/ไม่มีทิศ" ได้ศูนย์ = ไม่ผลิต ไม่ใช่ผลิตแบบสั้น
WORTH = {
    trend.STYLE_ID: {
        trend.BULL_TREND: 8, trend.BEAR_TREND: 8,
        trend.EARLY_BULL: 6, trend.EARLY_BEAR: 6,
        trend.TRANSITION: 4, trend.NO_TREND: 2,
    },
    breakout.STYLE_ID: {
        breakout.BREAKOUT_UP: 10, breakout.BREAKOUT_DOWN: 10,
        breakout.FAILED_BREAKOUT_UP: 9, breakout.FAILED_BREAKOUT_DOWN: 9,
        breakout.ARMED: 7, breakout.COMPRESSION: 5,
        breakout.EXPANSION: 4, breakout.NORMAL: 0,
    },
    pullback.STYLE_ID: {
        pullback.PULLBACK_CONFIRMED: 10, pullback.TREND_RESUMED: 9,
        pullback.PULLBACK_FAILED: 8, pullback.PULLBACK_FORMING: 7,
        pullback.M30_BULL_CONTEXT: 3, pullback.M30_BEAR_CONTEXT: 3,
        pullback.NO_M30_BIAS: 0,
    },
}

# สถานะที่ **ห้ามผลิตเป็นบทเลย** แม้สถานะจะเพิ่งเปลี่ยนมาก็ตาม — บทที่บอกว่า
# "ไม่มีอะไรเกิดขึ้น" ไม่ใช่บทวิเคราะห์ มันคือหน้าเว็บที่เสียเปล่า
NEVER_PUBLISH = {
    breakout.STYLE_ID: {breakout.NORMAL},
    pullback.STYLE_ID: {pullback.NO_M30_BIAS},
    trend.STYLE_ID: set(),
}


def candidate(story: dict) -> dict:
    """แปลง story หนึ่งใบเป็นผู้สมัครหนึ่งราย พร้อมเหตุผลที่อ่านออก"""
    style_id = story["style"]
    state = story["state"]
    worth = WORTH.get(style_id, {}).get(state, 0)
    blocked = state in NEVER_PUBLISH.get(style_id, set())
    changed = bool(story.get("state_changed"))
    first_run = story.get("previous_state") is None
    if blocked:
        reason = f"สถานะ {state} ไม่มีเรื่องให้เขียน"
    elif changed:
        reason = f"สถานะเปลี่ยนจาก {story['previous_state']} เป็น {state}"
    elif first_run:
        reason = f"รอบแรกของหัวข้อนี้ ยังไม่มีสถานะเดิมให้เทียบ (สถานะ {state})"
    else:
        reason = f"สถานะยังเป็น {state} เหมือนรอบก่อน"
    return {
        "style": style_id, "state": state, "worth": worth,
        # **รอบแรกผลิตได้** — ไม่งั้นระบบจะไม่มีวันออกบทใบแรกเลย เพราะไม่มีอะไรให้เทียบ
        "eligible": bool(not blocked and (changed or first_run) and worth > 0),
        "reason": reason,
        "triggers": list(story.get("triggers") or []),
    }


def evaluate(stories: list[dict], *, last_published_state: dict | None = None) -> list[dict]:
    """ตรวจคุณสมบัติของทุกใบ — ขั้นร่วมของทั้ง `select()` และ `select_all()`

    `last_published_state` = {style_id: state ที่เผยแพร่ไปแล้วล่าสุด} ใช้กันการ
    ปล่อยบทที่พูดเรื่องเดิมกับใบที่เพิ่งปล่อยไป แม้ story จะมองว่าสถานะเพิ่งเปลี่ยน
    (เกิดได้เวลาสถานะเด้งไปกลับ A → B → A ภายในไม่กี่แท่ง)
    """
    published = last_published_state or {}
    entries = [candidate(story) for story in stories]
    for entry in entries:
        if entry["eligible"] and published.get(entry["style"]) == entry["state"]:
            entry["eligible"] = False
            entry["reason"] = (f"สถานะ {entry['state']} ตรงกับใบที่เผยแพร่ไปแล้วล่าสุด "
                               "— บทจะซ้ำเรื่องเดิม")
    return entries


def select_all(stories: list[dict], *, last_published_state: dict | None = None) -> dict:
    """คืน **ทุกใบที่มีเรื่องให้เขียน** ไม่ใช่ใบเดียว — สำหรับรอบที่เกิดวันละครั้ง

    กติกา "หนึ่งใบต่อรอบ" ของ `select()` แก้ปัญหาของ *จังหวะปิดแท่ง*: ถ้ายิงทุก 15 นาที
    แล้วปล่อยสามสไตล์พร้อมกัน จะได้สามหน้าที่พูดถึงแท่งเดียวกันในนาทีเดียวกัน
    แต่รอบวัน (`run_daily`) เกิดวันละครั้ง และวางไฟล์คนละโฟลเดอร์เหมือนที่ A–G ออก
    พร้อมกันทุกวันอยู่แล้ว ⇒ ข้อจำกัดนั้นไม่มีเหตุผลรองรับในรอบวัน
    (และใบที่ขึ้นเว็บจริงยังถูกคัดวันละหนึ่งด้วย `publish_selection` อีกชั้นอยู่ดี)

    ⚠️ สิ่งที่ **ไม่** ผ่อนคือเกณฑ์ "มีเรื่องให้เขียน" — สถานะที่ `worth = 0` หรืออยู่ใน
    `NEVER_PUBLISH` ยังไม่ผลิตเหมือนเดิม การเพิ่มจำนวนใบต้องมาจากตลาดมีเรื่องเล่า
    ไม่ใช่จากการลดเกณฑ์
    """
    entries = evaluate(stories, last_published_state=last_published_state)
    eligible = [entry for entry in entries if entry["eligible"]]
    order = {trend.STYLE_ID: 0, breakout.STYLE_ID: 1, pullback.STYLE_ID: 2}
    chosen = sorted(eligible, key=lambda item: (-item["worth"], order[item["style"]]))
    return {
        "schema": SCHEMA,
        "publish": bool(chosen),
        "styles": [entry["style"] for entry in chosen],
        "reason": ("; ".join(f"{entry['style']}: {entry['reason']}" for entry in chosen)
                   or "ไม่มีสไตล์ใดมีเรื่องใหม่ให้เขียนในรอบนี้"),
        "candidates": entries,
    }


def select(stories: list[dict], *, last_published_state: dict | None = None) -> dict:
    """เลือกบท **ใบเดียว** ที่จะผลิตในรอบนี้ — คืนคำตัดสินพร้อมรายชื่อที่ถูกกลั้นไว้"""
    entries = evaluate(stories, last_published_state=last_published_state)
    eligible = [entry for entry in entries if entry["eligible"]]
    if not eligible:
        return {"schema": SCHEMA, "publish": False, "style": None, "reason":
                "ไม่มีสไตล์ใดมีเรื่องใหม่ให้เขียนในรอบนี้",
                "candidates": entries, "suppressed": []}
    # เรียงด้วยคะแนนก่อน แล้วใช้ลำดับสไตล์เป็นตัวตัดสินเสมอเมื่อคะแนนเท่ากัน
    # (ลำดับคงที่ = ผลลัพธ์ทำซ้ำได้ ซึ่งจำเป็นกับเทสและกับการตรวจย้อนหลัง)
    order = {trend.STYLE_ID: 0, breakout.STYLE_ID: 1, pullback.STYLE_ID: 2}
    winner = sorted(eligible, key=lambda item: (-item["worth"], order[item["style"]]))[0]
    return {
        "schema": SCHEMA,
        "publish": True,
        "style": winner["style"],
        "state": winner["state"],
        "reason": winner["reason"],
        "candidates": entries,
        "suppressed": [entry["style"] for entry in eligible if entry is not winner],
    }


def last_published(*, asset: str, state_dir: Path | None = None) -> dict:
    """อ่านสถานะที่ **เผยแพร่แล้ว** ของแต่ละสไตล์จากความจำ

    ต่างจากสถานะรอบก่อนตรงคำว่า "เผยแพร่แล้ว" — รอบที่คำนวณแล้วไม่ได้ปล่อยบท
    ไม่ควรกันบทของรอบถัดไป
    """
    result: dict[str, str] = {}
    for style_id, timeframe in ((trend.STYLE_ID, "30min"), (breakout.STYLE_ID, "15min"),
                                (pullback.STYLE_ID, "15min")):
        memory = intraday_story.read_state(style_id, asset, timeframe,
                                           state_dir=state_dir)
        if memory.get("published") and memory.get("state"):
            result[style_id] = memory["state"]
    return result
