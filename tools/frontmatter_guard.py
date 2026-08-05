"""ยามเฝ้า frontmatter — กันช่องที่เครื่องมืออื่นแทรกเข้ามาติดไปกับของที่ส่งมอบ

## ปัญหาที่ยามตัวนี้แก้

ไฟล์ `.md` ของเราถูก**เครื่องมือภายนอกเขียนแทรก**หลังจากสายท่อเขียนเสร็จ ตัวที่เจอจริงคือ
basic-memory ซึ่งตั้ง project ชี้ที่รากของระบบทั้งก้อน แล้ว watcher ของมันเติมช่อง
`permalink:` (บางไฟล์เติม `title:` กับ `type: note` มาทั้งบล็อก) กลับเข้าไปในไฟล์ต้นฉบับ

ผลที่เกิดจริงเมื่อ 2026-08-05: บทความที่ส่งมอบ **12 จาก 12 ใบ** มีบรรทัด

    permalink: library/projects/p002-nakekhiiynbthwiekhraaah/output/05-082026/...

ติดไปด้วย และในตัวรีโปเองอีก 27 ไฟล์ รวมถึง `README.md`, `GOVERNANCE.md` และ
**ไฟล์ fixture ของเทส** — ไฟล์กลุ่มหลังอันตรายที่สุด เพราะเทสเทียบผลกับ fixture
ที่ถูกของนอกระบบแก้ไปแล้วโดยไม่มีใครรู้

## ทำไมไม่แก้ที่ปลายทางอย่างเดียว

การตั้งค่าเครื่องมือให้เลิกยุ่งกับโฟลเดอร์เรา (ดู `.bmignore`) เป็นการแก้ที่ต้นเหตุ
แต่มันเป็น**ค่าบนเครื่องคนใดคนหนึ่ง** — คนที่รับรีโปนี้ไปใช้มีชุดเครื่องมือของตัวเอง
ที่เราไม่รู้จัก ยามตัวนี้จึงอยู่ในรีโป เพื่อให้ "ตรวจก่อนส่ง" ทำได้เสมอไม่ว่าเครื่องไหน

## กติกาการลบ — แคบไว้ก่อน

ลบเฉพาะสองรูปที่พิสูจน์ได้ว่าเป็นของเครื่องมือ ไม่ใช่ "ลบทุกช่องที่ไม่รู้จัก":

1. **ช่อง `permalink`** — ไม่มีที่ใดในสเปกของเราใช้ชื่อนี้
2. **ทั้งบล็อกที่มีแค่ `title` + `type` + `permalink`** — ลายเซ็นของบล็อกที่ถูกเติม
   ให้ไฟล์ที่เดิมไม่มี frontmatter เลย เอกสารจริงของเราไม่มีใบไหนหน้าตาแบบนี้

ช่องอื่นที่ไม่รู้จักจะถูก**รายงานว่าเจอ แต่ไม่ลบ** — การลบของที่เราไม่แน่ใจว่าใครใส่
อันตรายกว่าการปล่อยให้มันติดไป เพราะอย่างหลังยังมีคนเห็น
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

INJECTED_KEY = "permalink"
INJECTED_BLOCK_KEYS = {"title", "type", INJECTED_KEY}

# ช่องที่บทความของเราใช้จริง (ดู `writers._frontmatter`) — ใช้ตอนรายงานว่าอะไรเกินมา
ARTICLE_KEYS = ("title", "symbol", "instrument_type", "cutoff_at", "timezone")

_FENCE = "---"


def split_frontmatter(text: str) -> tuple[list[str], list[str]] | None:
    """แยกบรรทัดใน frontmatter ออกจากเนื้อไฟล์ — คืน None ถ้าไฟล์ไม่มีบล็อกนี้"""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _FENCE:
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == _FENCE:
            return lines[1:index], lines[index + 1:]
    return None  # เปิดบล็อกแล้วไม่ปิด — ถือว่าไม่ใช่ frontmatter อย่าไปยุ่ง


def _key_of(line: str) -> str | None:
    """ชื่อช่องของบรรทัดนี้ — คืน None ถ้าเป็นบรรทัดต่อของช่องก่อนหน้า (ย่อหน้าหรือ list)"""
    if not line.strip() or line[:1].isspace() or line.lstrip().startswith("-"):
        return None
    name, separator, _ = line.partition(":")
    return name.strip() if separator else None


def clean(text: str) -> tuple[str, list[str]]:
    """คืน (เนื้อไฟล์ที่เอาของแปลกออกแล้ว, รายชื่อช่องที่ลบ)"""
    parts = split_frontmatter(text)
    if parts is None:
        return text, []
    head, body = parts
    keys = [key for key in (_key_of(line) for line in head) if key]

    if keys and set(keys) == INJECTED_BLOCK_KEYS:
        # ทั้งบล็อกเป็นของเครื่องมือ — ไฟล์นี้เดิมไม่มี frontmatter เลย
        rest = "".join(body).lstrip("\n")
        return rest, sorted(INJECTED_BLOCK_KEYS)

    kept: list[str] = []
    removed: list[str] = []
    dropping = False
    for line in head:
        key = _key_of(line)
        if key is not None:
            dropping = key == INJECTED_KEY
            if dropping:
                removed.append(key)
        if not dropping:
            kept.append(line)
    if not removed:
        return text, []
    return f"{_FENCE}\n" + "".join(kept) + f"{_FENCE}\n" + "".join(body), removed


def foreign_keys(text: str, allowed: tuple[str, ...] = ARTICLE_KEYS) -> list[str]:
    """ช่องที่โผล่มานอกรายการที่อนุญาต — ใช้รายงาน ไม่ใช้ตัดสินใจลบ"""
    parts = split_frontmatter(text)
    if parts is None:
        return []
    keys = [key for key in (_key_of(line) for line in parts[0]) if key]
    return [key for key in keys if key not in allowed]


def scan(root: Path, *, fix: bool = False) -> list[dict]:
    """ไล่ไฟล์ .md ใต้ root — คืนเฉพาะใบที่มีของแปลก"""
    hits = []
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        cleaned, removed = clean(text)
        if not removed:
            continue
        if fix:
            path.write_text(cleaned, encoding="utf-8")
        hits.append({"path": str(path), "removed": removed, "fixed": fix})
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ตรวจ (หรือล้าง) ช่อง frontmatter ที่เครื่องมือภายนอกแทรกเข้ามา")
    parser.add_argument("root", type=Path, nargs="?", default=Path("."),
                        help="โฟลเดอร์ที่จะไล่ตรวจ")
    parser.add_argument("--fix", action="store_true",
                        help="ลบของแปลกออกจริง — ไม่ใส่ = รายงานอย่างเดียว")
    args = parser.parse_args(argv)

    hits = scan(args.root, fix=args.fix)
    if not hits:
        print(f"สะอาด — ไม่พบช่องแปลกปลอมใต้ {args.root}")
        return 0
    verb = "ลบแล้ว" if args.fix else "พบ"
    for hit in hits:
        print(f"{verb}: {hit['path']} · {', '.join(hit['removed'])}")
    print(f"\nรวม {len(hits)} ไฟล์")
    # ยังไม่แก้ = ถือว่าตก เพื่อให้ขั้นตรวจก่อนส่งสะดุดตรงนี้แทนที่จะปล่อยผ่าน
    return 0 if args.fix else 1


if __name__ == "__main__":
    sys.exit(main())
