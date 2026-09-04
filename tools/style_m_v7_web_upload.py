"""Strict three-file web upload projection for Style M."""
from __future__ import annotations

import re
from pathlib import Path

ALLOWED_KEYS = ("asset", "title", "excerpt", "author_slug")
MARKDOWN_NAME = re.compile(r"^btc-daily-\d{4}-\d{2}-\d{2}\.md$")
TITLE = "Bitcoin (BTC) จับตากรอบ Donchian และแผนสองฝั่ง"


def _frontmatter(markdown: str) -> tuple[str, str]:
    if not markdown.startswith("---\n") and not markdown.startswith("---\r\n"):
        raise ValueError("web upload markdown ต้องเริ่มด้วย frontmatter")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", markdown, re.S)
    if not match:
        raise ValueError("web upload frontmatter ปิดไม่ครบ")
    return match.group(1), match.group(2)


def _quote(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def build(markdown: str, *, image_names: dict[str, str], date_iso: str,
          excerpt: str | None = None) -> str:
    """Project canonical article into the exact minimal web-import contract."""
    _old_frontmatter, body = _frontmatter(markdown)
    names = [image_names.get("h1_market_map"), image_names.get("m15_entry_plan")]
    if any(not name for name in names) or len(set(names)) != 2:
        raise ValueError("web upload ต้องมีภาพ H1/M15 สองชื่อที่ distinct")
    refs = re.findall(r"!\[[^]]*\]\(([^)]+)\)", body)
    if set(refs) != set(names):
        raise ValueError("web upload image refs ไม่ตรง image_names")
    if "<<" in body or ">>" in body:
        raise ValueError("web upload ยังมี placeholder")
    lines = ["---", "asset: btc", f"title: {_quote(TITLE)}",
             f"excerpt: {_quote(excerpt or 'วิเคราะห์ BTCUSD จากโครงสร้าง H1, Donchian, ADX และ ADR14 พร้อมแผน Entry สองฝั่งและแนวทางรับมือ False Breakout')}",
             "author_slug: natthaphon-s", "---", body.lstrip("\r\n")]
    return "\n".join(lines)


def validate(markdown: str, *, filename: str, image_paths: dict[str, Path], date_iso: str) -> dict:
    if not MARKDOWN_NAME.fullmatch(filename):
        raise ValueError("ชื่อ web Markdown ต้องเป็น btc-daily-YYYY-MM-DD.md")
    if filename != f"btc-daily-{date_iso}.md":
        raise ValueError("ชื่อวันที่ของ web Markdown ไม่ตรง package")
    front, body = _frontmatter(markdown)
    keys = [match.group(1) for match in re.finditer(r"(?m)^([A-Za-z_][\w-]*):", front)]
    if keys != list(ALLOWED_KEYS):
        raise ValueError(f"web upload frontmatter keys ไม่ตรง: {keys}")
    if not re.search(r"(?m)^asset:\s+btc\s*$", front):
        raise ValueError("web upload asset ต้องเป็น btc")
    title = re.search(r"(?m)^title:\s*[\"']?(.*?)[\"']?\s*$", front)
    if not title or not title.group(1).startswith(TITLE):
        raise ValueError("web upload title ไม่ตรง Bitcoin (BTC) contract")
    if not re.search(r"(?m)^author_slug:\s+natthaphon-s\s*$", front):
        raise ValueError("web upload author_slug ไม่ตรงแม่แบบ")
    refs = set(re.findall(r"!\[[^]]*\]\(([^)]+)\)", body))
    expected = {Path(path).name for path in image_paths.values()}
    if refs != expected or len(refs) != 2:
        raise ValueError("web upload ต้องอ้างภาพสองไฟล์แบบ basename exact")
    for path in image_paths.values():
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError(f"web upload ภาพหายหรือว่าง: {path}")
    return {"ok": True, "filename": filename, "frontmatter_keys": keys,
            "image_refs": sorted(refs), "image_count": len(refs)}


__all__ = ["ALLOWED_KEYS", "MARKDOWN_NAME", "TITLE", "build", "validate"]
