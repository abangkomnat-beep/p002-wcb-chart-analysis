"""ด่านตรวจบทความสายสาธารณะ — คู่ขนานกับ `public_copy_validator` ของสายภายใน

สองตัวนี้บังคับ **สัญญาส่งออกคนละฉบับ** จึงแยกกันโดยตั้งใจ ไม่ใช่ของซ้ำ:

    public_copy_validator  สายภายใน  `# H1` เดียว · หัวข้อเทคนิคหัวเดียว · ห้ามหัวข้อย่อย
    wcb_copy_validator     สายเว็บ    ห้าม `#` · ต้องมี `##` สามหัว · หมุดกราฟ `[[chart:..]]`

**แกนร่วมที่ต้องเหมือนกันเสมอ** คือกฎ "เลขทุกตัวต้องชี้กลับหลักฐานได้"
ตัวนี้พอร์ตมาจากตัวนั้นแล้วปรับสองจุดให้เข้ากับข้อมูลของ WCB:

1. เก็บจำนวนเต็มเปล่าจากสตริงเข้ากองหลักฐานด้วย — ปฏิทินส่ง `"previous": "98"` มาเป็น
   ข้อความ ถ้าไม่เก็บ ตัวเลขที่บทความอ้างจากปฏิทินจะถูกตีตกทั้งหมด
2. เก็บค่าสัมบูรณ์ — บทความเขียน MACD -3.7 เป็น "3.7 ติดลบ" ตามภาษาคน

**สิ่งที่ด่านนี้ทำไม่ได้** — ตรวจว่าเนื้อความที่ไม่ใช่ตัวเลขตรงข่าวจริงไหม
กฎ `citation_source` กับ `news_note` ช่วยได้แค่ชี้เป้าให้คนไปดู ไม่ได้ตัดสินแทน
(บทเรียน 2026-08-05: บทที่เล่าว่า "น้ำมันร่วง" ขณะที่พาดหัวบอกว่าน้ำมันขึ้น ผ่านด่านเลขได้สบาย)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import wcb_source  # noqa: E402


VALIDATOR_VERSION = "1.1.0"

ALLOWED_TF = ("1h", "4h", "1day", "1week")
ALLOWED_TREND = ("up", "dn", "fl")
FORBIDDEN_FRONTMATTER = ("slug", "status")
REQUIRED_HEADINGS = (
    ("หัวข้อเทคนิค", re.compile(r"##\s*เทคนิค")),
    ("หัวข้อปัจจัยพื้นฐาน", re.compile(r"##\s*ปัจจัย")),
    ("หัวข้อกลยุทธ์", re.compile(r"##\s*กลยุทธ")),
)

THAI_CHAR = re.compile(r"[฀-๿]")
THAI_CHARS_PER_WORD = 3.5
WORD_MIN = 600
TITLE_MAX = 90
EXCERPT_MIN, EXCERPT_MAX = 120, 160

CHART_MARKER = re.compile(r"\[\[chart:([^\]\|]+)((?:\|[^\]]*)?)\]\]")
LINE_VALUE = re.compile(r"[sr]=([\d,\.]+)")
CITATION = re.compile(r"ที่มา:\s*([^,)฀-๿]*[A-Za-z][A-Za-z .&'-]*)")
NUMBER = re.compile(r"\d[\d,]*\.\d+|\d{1,3}(?:,\d{3})+|\d+")

# เลขเชิงโครงสร้างที่ไม่ใช่ข้อมูลตลาด — ลอกออกก่อนตรวจ ไม่งั้นเวลา คาบอินดิเคเตอร์
# และชื่อกรอบเวลาจะถูกนับเป็นตัวเลขที่หาหลักฐานไม่เจอทั้งหมด
STRUCTURAL = (
    re.compile(r"\[\[chart:[^\]]*\]\]"),
    re.compile(r"\d{1,2}:\d{2}"),
    re.compile(r"\(\s*\d+\s*(?:,\s*\d+\s*)*\)"),
    re.compile(r"\d+\s*(?:วัน|ชั่วโมง|นาที|ปี|เดือน|สัปดาห์)(?:ทำการ)?"),
    re.compile(r"ราย\s*\d+"),
    re.compile(r"\b(?:19|20)\d{2}\b"),
)


def split_frontmatter(article: str) -> tuple[str, str, int]:
    match = re.match(r"^---\r?\n(.*?)\r?\n---", article, re.S)
    if not match:
        return "", article, 1
    offset = article[: match.end()].count("\n") + 1
    return match.group(1), article[match.end():], offset


def field(frontmatter: str, name: str) -> str:
    found = re.search(rf"(?m)^{name}:\s*(.+)$", frontmatter)
    return found.group(1).strip() if found else ""


def collect_evidence(payload) -> set[float]:
    numbers: set[float] = set()

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, bool):
            return
        elif isinstance(node, (int, float)):
            numbers.add(abs(float(node)))
        elif isinstance(node, str):
            for token in re.findall(r"\d[\d,]*\.?\d*", node):
                try:
                    numbers.add(abs(float(token.replace(",", ""))))
                except ValueError:
                    pass

    walk(payload)
    return numbers


def strip_structural(line: str) -> str:
    for pattern in STRUCTURAL:
        line = pattern.sub(lambda m: " " * len(m.group(0)), line)
    return line


def match_kind(token: str, evidence: set[float]) -> str | None:
    """ยอมให้ปัดสองระดับตามที่บทความเขียนให้คนอ่าน — นอกนั้นคือเลขที่ไม่มีต้นทาง"""
    try:
        value = abs(float(token.replace(",", "")))
    except ValueError:
        return None
    if any(abs(item - value) < 0.005 for item in evidence):
        return "ตรงเป๊ะ"
    if any(abs(item - value) <= 0.05 for item in evidence):
        return "ปัดทศนิยม"
    if "." not in token and value >= 100 and any(abs(item - value) < 1.0 for item in evidence):
        return "ปัดจำนวนเต็ม"
    return None


def _finding(rule: str, severity: str, line: int, detail: str) -> dict:
    return {"rule": rule, "severity": severity, "line": line, "detail": detail}


def validate(article: str, snapshot: dict, *, allow: set[str] | None = None) -> dict:
    """`snapshot` ต้องเป็น **ก้อนดิบ** จาก API ไม่ใช่ evidence pack ที่แปลงแล้ว"""
    allow = allow or set()
    findings: list[dict] = []

    def add(rule, severity, line, detail):
        findings.append(_finding(rule, severity, line, detail))

    frontmatter, body, offset = split_frontmatter(article)

    if not frontmatter:
        add("frontmatter_missing", "fatal", 1, "ไม่มีบล็อก frontmatter")
    else:
        if not re.search(r"(?m)^asset:\s*\S+\s*$", frontmatter):
            add("asset_missing", "fatal", 1, "ไม่มีฟิลด์ asset")
        title = field(frontmatter, "title")
        if not title:
            add("title_missing", "fatal", 1, "ไม่มี title")
        elif len(title) > TITLE_MAX:
            add("title_length", "fatal", 1, f"title ยาว {len(title)} ตัวอักษร (เพดาน {TITLE_MAX})")
        excerpt = field(frontmatter, "excerpt")
        if not excerpt:
            add("excerpt_missing", "fatal", 1, "ไม่มี excerpt")
        elif not EXCERPT_MIN <= len(excerpt) <= EXCERPT_MAX:
            add("excerpt_length", "fatal", 1,
                f"excerpt ยาว {len(excerpt)} ตัวอักษร (ต้อง {EXCERPT_MIN}-{EXCERPT_MAX})")
        if not field(frontmatter, "author_slug"):
            add("author_missing", "fatal", 1, "ไม่มี author_slug")
        trend = field(frontmatter, "trend")
        if trend and trend not in ALLOWED_TREND:
            add("trend_invalid", "fatal", 1,
                f"trend '{trend}' ใช้ไม่ได้ — ระบบนำเข้ารับแค่ {'/'.join(ALLOWED_TREND)}")
        for key in FORBIDDEN_FRONTMATTER:
            if re.search(rf"(?m)^{key}:", frontmatter):
                add("frontmatter_forbidden", "fatal", 1, f"ห้ามมีฟิลด์ `{key}` ในหัวบทความ")

    if "<<" in article or ">>" in article:
        add("placeholder", "fatal", 1, "ยังมีเครื่องหมาย << หรือ >> ค้างอยู่")
    words = round(len(THAI_CHAR.findall(article)) / THAI_CHARS_PER_WORD)
    if words < WORD_MIN:
        add("word_count", "fatal", 1, f"ยาวประมาณ {words} คำ (ขั้นต่ำ {WORD_MIN})")
    for name, pattern in REQUIRED_HEADINGS:
        if not pattern.search(article):
            add("heading_missing", "fatal", 1, f"ขาด{name}")

    for index, line in enumerate(body.splitlines(), start=offset):
        stripped = line.strip()
        if stripped.startswith("# "):
            add("heading_h1", "fatal", index, "ห้ามใช้หัวข้อ # ในเนื้อบทความ ใช้ ## เท่านั้น")
        if re.match(r"^\s*[-*]\s", line):
            add("bullet_forbidden", "fatal", index, "ห้ามใช้ bullet ในเนื้อบทความ")
        if "|" in re.sub(r"\[\[chart:[^\]]*\]\]", "", line):
            add("table_forbidden", "fatal", index, "พบอักขระ | — บทความร้อยแก้วห้ามมีตาราง")

    pivots = wcb_source.pivot_values(wcb_source.normalize(snapshot))
    charts = list(CHART_MARKER.finditer(article))
    if not charts:
        add("chart_missing", "fatal", 1, "ไม่มีมาร์กเกอร์กราฟในบทความ")
    for chart in charts:
        line_no = article[: chart.start()].count("\n") + 1
        timeframe = chart.group(1)
        if timeframe not in ALLOWED_TF:
            add("chart_timeframe", "fatal", line_no,
                f"กรอบเวลา '{timeframe}' ไม่อยู่ใน {'/'.join(ALLOWED_TF)}")
        for group in LINE_VALUE.finditer(chart.group(2)):
            for raw in group.group(1).split(","):
                try:
                    value = float(raw)
                except ValueError:
                    continue
                if not any(abs(p - value) <= 1 for p in pivots):
                    add("chart_line", "fatal", line_no,
                        f"เส้น {raw} ไม่ตรงกับ pivot ตัวใดใน snapshot")

    evidence = collect_evidence(snapshot)
    kinds: dict[str, int] = {}
    for index, line in enumerate(body.splitlines(), start=offset):
        for match in NUMBER.finditer(strip_structural(line)):
            token = match.group(0)
            if token in allow:
                kinds["ยกเว้นด้วยมือ"] = kinds.get("ยกเว้นด้วยมือ", 0) + 1
                continue
            kind = match_kind(token, evidence)
            if kind:
                kinds[kind] = kinds.get(kind, 0) + 1
            else:
                add("number_unsupported", "fatal", index,
                    f"\"{token}\" ไม่มีอยู่ใน snapshot — ถ้าเป็นเลขที่คำนวณเองต้องตัดออก")

    haystack = json.dumps(snapshot, ensure_ascii=False).lower()
    for match in CITATION.finditer(body):
        name = match.group(1).strip()
        if len(name) < 3:
            continue
        line_no = body[: match.start()].count("\n") + offset
        if name.lower() not in haystack:
            add("citation_source", "warning", line_no,
                f"อ้างที่มา \"{name}\" แต่ไม่พบชื่อนี้ใน snapshot — ต้องยืนยันว่าเอามาจากไหน")

    news = snapshot.get("news") or []
    if not news:
        add("news_note", "warning", 1, "snapshot ไม่มีข่าวเลย — หัวข้อปัจจัยพื้นฐานต้องระวังเป็นพิเศษ")
    else:
        latest = max(str(item.get("published_at") or "") for item in news)
        add("news_note", "warning", 1,
            f"snapshot มีข่าว {len(news)} ชิ้น ชิ้นล่าสุดลงวันที่ {latest} "
            f"(ดึงเมื่อ {str(snapshot.get('generatedAt') or '')[:10]}) — "
            "ตรวจว่าเนื้อหาปัจจัยพื้นฐานตรงกับข่าวชุดนี้จริง")
        for item in news:
            add("news_note", "warning", 1,
                "  พาดหัว: " + wcb_source._mend(str(item.get("title") or "")))

    fatal = [item for item in findings if item["severity"] == "fatal"]
    return {
        "status": "fail" if fatal else "pass",
        "findings": findings,
        "fatal_count": len(fatal),
        "word_count": words,
        "chart_markers": len(charts),
        "number_matches": kinds,
        "evidence_size": len(evidence),
        "validator_version": VALIDATOR_VERSION,
    }


def format_report(result: dict, name: str) -> str:
    lines = [f"{name}: {result['status'].upper()} ({result['fatal_count']} ข้อร้ายแรง) "
             f"| ~{result['word_count']} คำ | กราฟ {result['chart_markers']} จุด "
             f"| หลักฐาน {result['evidence_size']} ค่า"]
    if result["number_matches"]:
        detail = " · ".join(f"{k} {v}" for k, v in sorted(result["number_matches"].items()))
        lines.append(f"  ตัวเลขที่ตรวจผ่าน: {detail}")
    for item in result["findings"]:
        mark = "✗" if item["severity"] == "fatal" else "!"
        lines.append(f"  {mark} บรรทัด {item['line']} [{item['rule']}] {item['detail']}")
    return "\n".join(lines)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="ตรวจบทวิเคราะห์สายสาธารณะ WCB")
    parser.add_argument("article", type=Path)
    parser.add_argument("--snapshot", type=Path, required=True, help="ก้อนดิบจาก API")
    parser.add_argument("--allow", nargs="*", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
    result = validate(args.article.read_text(encoding="utf-8"),
                      snapshot, allow=set(args.allow))
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json
          else format_report(result, args.article.name))
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
