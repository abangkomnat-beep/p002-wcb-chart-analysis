"""กองบรรณาธิการเชิงกฎสำหรับข้อความสาธารณะของ P002

ไม่ได้แต่งเนื้อหาใหม่และไม่เรียกโมเดลภาษา หน้าที่มีเพียงตัดร่องรอยภาษาจากแม่แบบ
ที่คนเขียนไทยปกติไม่ใช้ เช่น ชื่ออังกฤษซ้ำในวงเล็บ รหัสสถานะภายใน และคำบรรยาย
ว่าระบบกำลังทำอะไร ข้อมูล ตัวเลข เงื่อนไข และชื่อไฟล์ภาพต้องไม่เปลี่ยน
"""
from __future__ import annotations

import re


_INTERNAL_STATES = {
    "EXPANSION": "ช่วงแกว่งกว้างกว่าปกติ",
    "COMPRESSION": "ช่วงแกว่งแคบกว่าปกติ",
    "NORMAL": "ช่วงแกว่งอยู่ในระดับปกติ",
    "ARMED": "ราคาเข้าใกล้ขอบกรอบ",
    "BREAKOUT_UP": "ราคาทะลุกรอบด้านบน",
    "BREAKOUT_DOWN": "ราคาหลุดกรอบด้านล่าง",
    "FAILED_BREAKOUT_UP": "การทะลุด้านบนไม่สำเร็จ",
    "FAILED_BREAKOUT_DOWN": "การหลุดด้านล่างไม่สำเร็จ",
}

# วงเล็บที่เป็นค่าพารามิเตอร์/สัญลักษณ์ ไม่ใช่คำแปล จึงต้องคงไว้
_INDICATOR_PARAMETER = re.compile(
    r"\b(?:RSI|MACD|CCI|ADX|ATR|SMA|EMA|DMI|Stochastic|Momentum)\([^ก-๙)]*\)",
    re.IGNORECASE,
)
_MARKDOWN_IMAGE_OR_LINK = re.compile(r"!?\[[^\]]*\]\([^)]*\)")
_PAREN = re.compile(r"\(([^()]+)\)")
_LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
_SYMBOL_ONLY = re.compile(r"[A-Z0-9./+-]{2,}")
_BACKTICK_STATE = re.compile(r"`([A-Z][A-Z0-9_]+)`")


def _protect(text: str) -> tuple[str, list[str]]:
    held: list[str] = []

    def keep(match: re.Match[str]) -> str:
        held.append(match.group(0))
        return f"\x00H{len(held) - 1}\x00"

    for pattern in (_MARKDOWN_IMAGE_OR_LINK, _INDICATOR_PARAMETER):
        text = pattern.sub(keep, text)
    return text, held


def _restore(text: str, held: list[str]) -> str:
    for index, value in enumerate(held):
        text = text.replace(f"\x00H{index}\x00", value)
    return text


def _drop_translation(match: re.Match[str]) -> str:
    content = match.group(1).strip()
    if content.startswith("ที่มา:") or not _LATIN_WORD.search(content):
        return match.group(0)
    if _SYMBOL_ONLY.fullmatch(content):
        return match.group(0)
    return ""


def naturalize(markdown: str) -> str:
    """ทำให้รูปประโยคเป็นภาษาไทยธรรมชาติ โดยไม่แตะข้อเท็จจริงในบท"""
    text, held = _protect(markdown)

    def state_name(match: re.Match[str]) -> str:
        return _INTERNAL_STATES.get(match.group(1), match.group(1).replace("_", " ").lower())

    text = _BACKTICK_STATE.sub(state_name, text)
    text = _PAREN.sub(_drop_translation, text)
    text = _restore(text, held)

    replacements = (
        ("สถานะที่ระบบจัดให้:", "ภาพตลาดรอบนี้:"),
        ("ระบบจัดสถานะรอบนี้เป็น", "ภาพตลาดรอบนี้เป็น"),
        ("ระบบจัดสถานะเป็น", "ภาพตลาดรอบนี้เป็น"),
        ("ระบบจัดให้อยู่ในกลุ่ม", "อยู่ในภาวะ"),
        ("ระบบจัดให้อยู่ในสถานะ", "อยู่ในภาวะ"),
        ("ระบบจะเปลี่ยนสถานะเป็น", "ภาพจะเปลี่ยนเป็น"),
        ("ระบบจะไม่นับเป็น", "จึงยังไม่นับเป็น"),
        ("ระบบใช้ตัดสิน", "ใช้ตัดสิน"),
        ("ระบบใช้แยก", "ใช้แยก"),
        ("ระบบใช้คือ", "เกณฑ์อยู่ที่"),
        (" & ", " และ "),
    )
    for before, after in replacements:
        text = text.replace(before, after)

    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text


def findings(markdown: str) -> list[dict]:
    """รายงานร่องรอยภาษาแม่แบบที่หลุดหลังผ่าน copy desk"""
    issues: list[dict] = []
    protected, _held = _protect(markdown)
    for line_no, line in enumerate(protected.splitlines(), 1):
        if _BACKTICK_STATE.search(line):
            issues.append({"rule": "internal_state_exposed", "severity": "fatal", "line": line_no,
                           "message": "พบรหัสสถานะภายในในบทสาธารณะ"})
        if any(term in line for term in ("สถานะที่ระบบจัดให้", "ระบบจัดสถานะ", "ระบบจัดให้")):
            issues.append({"rule": "system_voice", "severity": "fatal", "line": line_no,
                           "message": "ประโยคพูดในนามระบบ แทนที่จะเล่าภาพตลาด"})
        for match in _PAREN.finditer(line):
            content = match.group(1).strip()
            if (_LATIN_WORD.search(content) and not content.startswith("ที่มา:")
                    and not _SYMBOL_ONLY.fullmatch(content)):
                issues.append({"rule": "bilingual_parenthetical", "severity": "fatal", "line": line_no,
                               "message": f"พบคำอังกฤษซ้ำในวงเล็บ: ({content})"})
    return issues
