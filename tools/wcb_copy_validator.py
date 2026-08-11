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

from tools import consistency_gate, headline_format, wcb_source, web_features  # noqa: E402


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


def _line_tolerance(pivot: float, levels: int | None = None) -> float:
    """เพดานความคลาดเคลื่อนของเส้นในหมุดกราฟ — ต้องผูกกับขนาดราคา ไม่ใช่ค่าคงที่

    เดิมเป็น `<= 1` ตายตัว ซึ่งพอดีกับทองที่ระดับสี่พัน (คลาด 1 ดอลลาร์ = 0.02%)
    แต่กับ EUR/USD ที่ระดับ 1.15 มันแปลว่า **ทุกค่าระหว่าง 0.15 ถึง 2.15 ผ่านหมด**
    ⇒ ด่านนี้ปล่อยหมุดกราฟที่พังของ EUR/USD ผ่านไปได้โดยไม่ฟ้องอะไรเลย (2026-08-05)

    0.05% ของค่า pivot เผื่อไว้พอสำหรับการปัดเศษที่ชั้นนักเขียนทำจริง
    (ทองปัดเป็นจำนวนเต็ม = คลาดไม่เกิน 0.5 ดอลลาร์ จาก 4,150 คือ 0.012%)
    และมีพื้นขั้นต่ำกันกรณีราคาต่ำมากจนเปอร์เซ็นต์เล็กกว่าทศนิยมที่พิมพ์ออกมา

    `levels` = จำนวนทศนิยมที่ **ชั้นนักเขียนใช้ปั้นค่าในหมุดจริง** (ทะเบียนช่อง
    `levels` ของ `wcb_source.ASSET_PROFILES` ตัวเดียวกับที่ `_distinct_lines()` อ่าน)
    ส่งมาเมื่อไหร่ เพดานจะไม่แคบกว่า **ครึ่งหนึ่งของหลักที่ปัด** เพราะการปัดเศษ
    คลาดได้เท่านั้นเป็นอย่างมากอยู่แล้วโดยนิยาม

    **เหตุที่ต้องมีพื้นนี้ (บั๊กจริง รอบผลิต 2026-08-11):** SOL ตกด่านทั้งสามสไตล์
    ⇒ ไม่ได้วางลง `output/` ทั้งวัน · pivot S2 = 74.66 ถูกปั้นเป็น `74.7` (ทะเบียน
    ตั้ง `levels` 1) คลาด 0.04 แต่เพดานเปอร์เซ็นต์ที่ราคานั้นให้แค่ 0.0373
    ⇒ **ระบบตีตกค่าที่ตัวเองปั้นออกมา** · เงื่อนไขทั่วไปคือ `10^-levels ÷ 2 >
    ราคา × 0.0005` ⇒ ทุกสินทรัพย์ที่ตั้ง 1 ตำแหน่งและราคาต่ำกว่า ~100 จะสุ่มตก
    ทุกครั้งที่ pivot ปัดขึ้น

    ⚠️ **นี่ไม่ใช่การผ่อนด่าน** (ข้อห้ามที่ผู้ใช้ล็อกไว้ยังอยู่ครบ) — เป็นการทำให้
    เพดานของผู้ตรวจกับความละเอียดของผู้เขียนเป็นเลขตัวเดียวกัน ค่าที่คลาด
    **เกิน**การปัดเศษยังตกเหมือนเดิมทุกตัว · ผู้ใช้เคาะทางนี้ 2026-08-11
    (รายการ #20) และมีเทส `เพดานคลาดเคลื่อนของหมุดกราฟ` ล็อกทั้งสองด้านไว้แล้ว

    ไม่ส่ง `levels` มา = เพดานเดิมทุกประการ ⇒ จุดเรียกเก่าไม่เปลี่ยนพฤติกรรม
    """
    span = max(abs(float(pivot)) * 0.0005, 5e-5)
    if levels is None:
        return span
    return max(span, 0.5 * 10 ** -int(levels))


def _levels_digits(snapshot: dict) -> int | None:
    """ความละเอียดที่ชั้นนักเขียนใช้ปั้นหมุด — หาไม่เจอให้คืน None ห้ามโยน

    เหตุผลเดียวกับที่ `wcb_source.normalize()` จงใจไม่เรียก `profile_for()`:
    ด่านตรวจต้อง **คืนคำตัดสินได้เสมอ** ก้อนของหัวข้อที่ยังไม่ลงทะเบียนต้องได้
    ผลว่า "ตกด่าน" ไม่ใช่ exception ที่ทำให้ทั้งรอบผลิตล้มโดยไม่รู้ว่าบทไหนผิด
    ⇒ ที่นี่กลืน error แล้วถอยไปใช้เพดานเปอร์เซ็นต์ล้วน ซึ่งเข้มกว่า ไม่ใช่หลวมกว่า
    """
    try:
        return int(wcb_source.profile_for(snapshot.get("asset", ""))["levels"])
    except (wcb_source.SnapshotUnusable, AttributeError, KeyError, TypeError, ValueError):
        return None


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
    # ปี พ.ศ. — บทเขียนเป็น พ.ศ. ตั้งแต่ 2026-08-10 แต่ก้อน snapshot เก็บวันที่เป็น
    # ค.ศ. ทั้งหมด (โดยเจตนา: ทะเบียนภายในต้องเทียบกับข้อมูลจริงได้) ⇒ ขึ้นทะเบียนคู่ให้
    # **ไม่ใช่การผ่อนด่าน** — เพิ่มเฉพาะปีที่แปลงจากปีที่มีอยู่จริงในก้อนเท่านั้น
    # ปีมั่วที่ไม่มีต้นทางยังตกเหมือนเดิม
    for value in [n for n in numbers if 1900 <= n <= 2200 and float(n).is_integer()]:
        numbers.add(float(headline_format.buddhist_year(int(value))))
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


def plan_numbers(plan: dict) -> set[float]:
    """ค่าจากแผนที่หัวข้อแผนได้รับอนุญาตให้เขียน — **แคบที่สุดเท่าที่พอ**

    แผนเต็มมีทั้งคะแนนความเชื่อมั่น ระยะเทียบความผันผวน และ `invalidation` ปนอยู่
    ยกทั้งแผนเข้ากองหลักฐาน = เปิดช่องให้เลขที่ไม่ได้ตั้งใจให้เขียนผ่านด่านไปได้ฟรี ๆ
    (หลักการเดียวกับ `writers.plan_evidence` ของสายภายใน — คนละสัญญาแต่เหตุผลเดียวกัน)

    **ค่าเหล่านี้ไม่ได้อยู่ใน snapshot และไม่มีวันอยู่** เพราะแผนคำนวณจากแท่ง D1 ของ
    series API คนละ endpoint กัน ⇒ ถ้าไม่เติมเข้ากองนี้ หัวข้อแผนจะถูกตีตกทุกใบ
    ที่กฎ `number_unsupported` · การเติมยังคงกฎแกนไว้ครบ: เลขทุกตัวยังชี้กลับ
    **ไฟล์หลักฐาน** ได้เหมือนเดิม แค่เป็น `internal/trade-plan.json` แทน snapshot
    """
    numbers: set[float] = set()
    entry = plan.get("entry") or {}
    for value in list(entry.get("zone") or []) + [entry.get("edge")]:
        if value is not None:
            numbers.add(abs(float(value)))
    stop = plan.get("stop") or {}
    if stop.get("value") is not None:
        numbers.add(abs(float(stop["value"])))
    for target in plan.get("targets") or []:
        for key in ("value", "rr"):
            if target.get(key) is not None:
                numbers.add(abs(float(target[key])))
    return numbers


def validate(article: str, snapshot: dict, *, allow: set[str] | None = None,
             plan: dict | None = None, calendar_feed: dict | None = None) -> dict:
    """`snapshot` ต้องเป็น **ก้อนดิบ** จาก API ไม่ใช่ evidence pack ที่แปลงแล้ว

    `plan` ส่งมาเฉพาะรอบที่บทความมีหัวข้อแผนจริง (ผู้ใช้สั่งเปิด 2026-08-05) —
    **ส่งมาทุกรอบไม่ได้** เพราะกองหลักฐานที่กว้างขึ้นแปลว่าด่านตัวเลขหลวมลงตามไปด้วย
    ผู้ตัดสินว่าแผนไหนขึ้นบทได้อยู่ที่ `writers.plan_for_public` + `wcb_writers.plan_rejection`
    ที่เดียว ชั้นนี้แค่ยอมรับผลนั้น

    `calendar_feed` (เพิ่ม 2026-08-07): ก้อนดิบจาก `calendar_feed.fetch_raw()` —
    ส่งมาเมื่อบทความอ้างปฏิทินจากฟีดใหม่แทนช่อง `calendar` เดิมใน snapshot
    เหตุผลเดียวกับ `plan`: ฟีดปฏิทินเป็นคนละ endpoint จาก snapshot เลขของมัน
    จึงไม่อยู่ในกองหลักฐานที่ `collect_evidence(snapshot)` เดินอยู่ ไม่ส่งมา =
    รายการปฏิทินที่ snapshot ไม่เคยมี (ช่วงกว้างกว่า/สกุลเงินอื่น) จะตกด่าน
    `number_unsupported` ทั้งที่มีต้นทางจริง
    """
    allow = allow or set()
    findings: list[dict] = []

    def add(rule, severity, line, detail):
        findings.append(_finding(rule, severity, line, detail))

    # ด่านความสอดคล้อง D-4.5 ส่วนที่ครอบทุกสไตล์ (ผู้ใช้เคาะ 08-10):
    # ปีทั้งใบเป็น พ.ศ. + วันที่ Title ต้องตรง H1 — สไตล์ A/B/C ไม่มี story
    # จึงส่ง None (กฎทิศ trend↔regime ข้ามไป มีเฉพาะ D/E ที่มี artifact)
    for gate_finding in consistency_gate.check(article, None):
        add(gate_finding["rule"], gate_finding["severity"],
            gate_finding["line"], gate_finding["message"])

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

    # H1 — เดิมห้ามทั้งหมด เพราะทีมเว็บสร้าง H1 จากช่อง `title` ให้เอง
    # 🆕 **2026-08-10 ผู้ใช้สั่งให้ทุกสไตล์มีทั้ง title และ H1** ⇒ อนุญาต **ตัวเดียว
    # และต้องเป็นบรรทัดแรกของเนื้อบท** · เกินหนึ่งตัวหรืออยู่กลางบท = ตกเหมือนเดิม
    # (H1 กลางบทไม่มีทางถูกในเชิงโครงสร้างเอกสาร ไม่ว่าเว็บจะรองรับช่องแยกหรือไม่)
    h1_lines = [index for index, line in enumerate(body.splitlines(), start=offset)
                if line.strip().startswith("# ")]
    body_lines = body.splitlines()
    first_content = next((i for i, line in enumerate(body_lines) if line.strip()), None)
    if len(h1_lines) > 1:
        add("heading_h1", "fatal", h1_lines[1],
            f"มีหัวข้อ # {len(h1_lines)} ตัว — ได้ตัวเดียวเท่านั้น ที่เหลือใช้ ##")
    elif h1_lines and first_content is not None \
            and not body_lines[first_content].strip().startswith("# "):
        add("heading_h1", "fatal", h1_lines[0],
            "หัวข้อ # ต้องเป็นบรรทัดแรกของเนื้อบทความเท่านั้น")
    # H1 ที่ซ้ำกับ title = ส่งข้อความเดียวกันสองที่ ไม่ได้บอกอะไรเพิ่มให้คนอ่าน
    # (สเปก SEO ของหัวหน้า 2026-08-10 บังคับให้ต่างกัน — กฎเดียวกับสไตล์ D/E)
    if h1_lines and frontmatter:
        h1_text = next(line.strip()[2:] for line in body_lines if line.strip().startswith("# "))
        if headline_format.same_headline(field(frontmatter, "title") or "", h1_text):
            add("title_equals_h1", "fatal", h1_lines[0],
                "title กับ H1 เหมือนกัน — สเปก SEO บังคับให้หางต่างกัน")

    # bullet ผูกกับ **ความสามารถของหน้าเว็บ ไม่ใช่รสนิยม** — ห้ามเมื่อ `.an-body` ยังไม่มี
    # CSS ให้ `ul` (ฟีดแบ็กหัวหน้า 2026-08-07) · สวิตช์อยู่ที่ `config/publishing_policy.json`
    # ที่เดียว ชั้นนักเขียนอ่านช่องเดียวกัน ⇒ เปิด/ปิดแล้วสองฝั่งขยับพร้อมกันเสมอ
    # **ตารางยังห้ามอยู่ทุกกรณี** — CSS ของ `table/th/td` เป็นคนละเรื่องและยังไม่มีใครสั่ง
    bullets_ok = web_features.bullets_enabled()
    for index, line in enumerate(body.splitlines(), start=offset):
        if not bullets_ok and re.match(r"^\s*[-*]\s", line):
            add("bullet_forbidden", "fatal", index,
                "ห้ามใช้ bullet ในเนื้อบทความ — `.an-body` ของเว็บยังไม่มี CSS ให้ `ul` "
                "(เปิดได้ที่ `web_bullets_enabled` ใน config/publishing_policy.json)")
        if "|" in re.sub(r"\[\[chart:[^\]]*\]\]", "", line):
            add("table_forbidden", "fatal", index, "พบอักขระ | — บทความร้อยแก้วห้ามมีตาราง")

    pivots = wcb_source.pivot_values(wcb_source.normalize(snapshot))
    levels = _levels_digits(snapshot)
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
                if not any(abs(p - value) <= _line_tolerance(p, levels) for p in pivots):
                    add("chart_line", "fatal", line_no,
                        f"เส้น {raw} ไม่ตรงกับ pivot ตัวใดใน snapshot")

    evidence = collect_evidence(snapshot)
    if plan:
        evidence |= plan_numbers(plan)
    if calendar_feed:
        evidence |= collect_evidence(calendar_feed)
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

    # ตั้งแต่ 2026-08-06 ก้อนมีสองช่อง: `news` ติดป้ายสินทรัพย์ตรง ๆ · `macroNews`
    # คัดมาจากตัวขับระดับมหภาค · ต้องรายงานทั้งคู่ ไม่งั้นบทที่ยกพาดหัวจาก macroNews
    # จะดูเหมือนอ้างข่าวที่ไม่มีอยู่ในก้อน
    news = list(snapshot.get("news") or [])
    macro = list(snapshot.get("macroNews") or [])
    both = news + macro
    if not both:
        add("news_note", "warning", 1, "snapshot ไม่มีข่าวเลย — หัวข้อปัจจัยพื้นฐานต้องระวังเป็นพิเศษ")
    else:
        latest = max(str(item.get("published_at") or "") for item in both)
        add("news_note", "warning", 1,
            f"snapshot มีข่าว {len(news)} ชิ้น + ข่าวมหภาค {len(macro)} ชิ้น "
            f"ชิ้นล่าสุดลงวันที่ {latest} "
            f"(ดึงเมื่อ {str(snapshot.get('generatedAt') or '')[:10]}) — "
            "ตรวจว่าเนื้อหาปัจจัยพื้นฐานตรงกับข่าวชุดนี้จริง "
            "· สองช่องนี้ให้แค่พาดหัวกับลิงก์ ไม่มีเนื้อข่าว ห้ามสรุปแทน")
        for item in both:
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
        # ต้องบันทึกว่ารอบนี้กองหลักฐานถูกขยายด้วยแผนหรือไม่ — ไม่งั้นผลตรวจสองรอบ
        # ที่ใช้เกณฑ์คนละชุดจะหน้าตาเหมือนกันเป๊ะเมื่อเปิดย้อนหลัง
        "plan_evidence_used": bool(plan),
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
