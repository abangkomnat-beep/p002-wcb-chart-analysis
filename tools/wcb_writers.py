"""นักเขียนสามสไตล์ของสายสาธารณะ WCB — A มาตรฐาน · B เทคนิคเจาะลึก · C อิงเหตุการณ์

สายนี้ **แยกจาก `tools/writers.py` (① ณธาร ② กฤช ③ ปุณณ์) โดยตั้งใจ** เพราะสองสายนี้
ผูกกับสัญญาส่งออกคนละฉบับและแหล่งข้อมูลคนละเจ้า:

    สายเดิม ①②③   MT5 Raw Trading · D1 อย่างเดียว · `# H1` + bullet + ไฟล์กราฟ PNG
                    → ใช้ภายในเท่านั้น เพราะสิทธิ์ข้อมูลไม่ให้เผยแพร่
    สายนี้ A/B/C     WCB snapshot API · 4 กรอบเวลา · `##` เท่านั้น ห้าม bullet
                    → หมุดกราฟ `[[chart:TF|s=..|r=..]]` ให้เว็บวาดเอง

การยุบสองสายเป็นสายเดียวต้องรอจนสายสาธารณะพิสูจน์ตัวเองและ MT5 ถูกปลดออกจริง
ถ้ายุบตอนนี้จะพังทั้งสายภายในที่ยังทำงานอยู่ แลกกับผลที่ได้เท่าเดิม

**กติกาที่ทั้งสามสไตล์ใช้ร่วมกันและห้ามยกเว้น** (ฉบับเต็ม:
`01-CC/Library/Policies/2026-08-05_สเปกสไตล์บทวิเคราะห์-ABC.md`)

- เลขทุกตัวยกมาจาก evidence ตรง ๆ · **ห้ามคำนวณส่วนต่างเอง** — อยากบอกว่าวิ่งไปเท่าไร
  ให้พิมพ์ค่าต้นทางสองค่า ไม่ใช่ผลลบ · ด่าน `01-CC/Repo/wcb-analysis/validate_article.py`
  จับได้ทันทีถ้าฝืน เพราะเลขที่คิดเองจะไม่ตรงกับค่าใดใน snapshot
- **ห้ามแปลงหน่วย** — ปฏิทินส่ง `"98"` มาก็เขียน 98 พร้อมกำกับหน่วยเป็นข้อความ
- จำนวนนับเขียนเป็น**คำไทย** ("ห้าแท่งติด") ไม่ใช่ตัวเลข — จำนวนที่นับเองไม่มีใน evidence
- evidence ไม่พอ = ตัดประโยคนั้นเงียบ ไม่มีหัวข้อว่าง ไม่มีคำแก้ตัว

**เมื่อฟีดข่าวว่างหรือมีแต่ข่าวเก่า บทความยังต้องเต็มความยาว** โดยหันไปใช้ปฏิทินกับ
ผลตอบแทนย้อนหลังแทน และต้องบอกสภาพฟีดตามจริง — ห้ามเดาสาเหตุมาเติมให้ครบหัวข้อ
(บทเรียน 2026-08-05: ฉบับที่เดาสาเหตุเอง เล่าสวนทางกับข่าวชิ้นเดียวที่มีจริง)
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import wcb_source  # noqa: E402


AUTHOR_SLUG = "natthaphon-s"
TITLE_MAX = 90
EXCERPT_MIN, EXCERPT_MAX = 120, 160

THAI_WEEKDAY = ("จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์")
THAI_COUNT = {2: "สอง", 3: "สาม", 4: "สี่", 5: "ห้า", 6: "หก", 7: "เจ็ด", 8: "แปด"}


# ---------------------------------------------------------------- ตัวช่วยจัดรูปเลข
def price(value) -> str:
    return f"{float(value):,.2f}"


def num(value) -> str:
    """ค่าอินดิเคเตอร์ — ตัดศูนย์ท้ายทิ้งเพื่อให้ตรงกับที่ผู้ให้บริการส่งมา"""
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return text or "0"


def pct(value) -> str:
    return f"{abs(float(value)):.2f}"


def when(event_at: str, today: str) -> str:
    """เรียกเวลาของเหตุการณ์เป็นภาษาคน — จงใจไม่พิมพ์วันที่เป็นตัวเลข

    วันที่แบบ "7 สิงหาคม" ทำให้เลข 7 เข้าไปอยู่ในบทความโดยไม่มีต้นทางใน evidence
    เรียกเป็นชื่อวันแทนได้ความหมายเท่ากันและตรวจสอบย้อนกลับได้จากฟิลด์ `at`
    """
    stamp = str(event_at or "")[:10]
    if not stamp:
        return "ช่วงถัดไป"
    if stamp == today:
        return "คืนนี้"
    try:
        delta = (date.fromisoformat(stamp) - date.fromisoformat(today)).days
    except ValueError:
        return "ช่วงถัดไป"
    if delta == 1:
        return "คืนพรุ่งนี้"
    weekday = THAI_WEEKDAY[date.fromisoformat(stamp).weekday()]
    return f"วัน{weekday}นี้" if delta <= 4 else f"วัน{weekday}ถัดไป"


def clock(event_at: str) -> str:
    return str(event_at or "")[11:16]


def fit_title(core: str) -> str:
    if len(core) <= TITLE_MAX:
        return core
    cut = core[:TITLE_MAX]
    return cut[: cut.rfind(" ")] if " " in cut else cut


def fit_excerpt(clauses: list[str]) -> str:
    """ต่อประโยคจนอยู่ในช่วง 120-160 ตัวอักษรที่ระบบนำเข้าบังคับ"""
    text = ""
    for clause in clauses:
        if len(text) >= EXCERPT_MIN:
            break
        text = clause if not text else f"{text} {clause}"
    if len(text) > EXCERPT_MAX:
        cut = text[:EXCERPT_MAX]
        text = cut[: cut.rfind(" ")] if " " in cut else cut
    return text


# ---------------------------------------------------------------- อ่านภาพจาก evidence
def trend_code(evidence: dict) -> str:
    """up/dn/fl เท่านั้น — ระบบนำเข้าของเว็บปฏิเสธค่าอื่นทุกค่า รวมทั้งคำไทย"""
    indicators = evidence["daily"]["indicators"]
    spot = float(evidence["quote"]["price"])
    fast = (indicators.get("SMA20") or {}).get("value")
    slow = (indicators.get("SMA50") or {}).get("value")
    if fast is None or slow is None:
        return "fl"
    if spot > fast and spot > slow:
        return "up"
    if spot < fast and spot < slow:
        return "dn"
    return "fl"


def _sorted_levels(evidence: dict) -> tuple[list[float], list[float]]:
    """แนวรับ/แนวต้านจาก pivot รายวัน แยกด้วยราคาปัจจุบัน ไม่ใช่ด้วยชื่อ r/s

    pivot ที่ชื่อ r1 อาจอยู่ใต้ราคาไปแล้วเมื่อราคาทะลุขึ้นมา การเรียกมันว่าแนวต้าน
    ต่อไปคือการอ่านผิด · จัดกลุ่มตามตำแหน่งจริงเทียบราคาจึงถูกเสมอ
    """
    spot = float(evidence["quote"]["price"])
    values = sorted({round(float(v), 2) for v in wcb_source.pivot_values(evidence)})
    below = [v for v in values if v < spot]
    above = [v for v in values if v >= spot]
    return list(reversed(below)), above


def _distinct_ints(values: list[float], limit: int) -> list[str]:
    """pivot คนละ TF ที่ปัดแล้วชนกันต้องเหลือเส้นเดียว

    เส้นซ้ำบนกราฟไม่ได้ให้ข้อมูลเพิ่ม แต่ทำให้ผู้อ่านนึกว่ามีสองด่านที่ระดับเดียวกัน
    """
    seen: list[str] = []
    for value in values:
        text = str(int(round(value)))
        if text not in seen:
            seen.append(text)
        if len(seen) == limit:
            break
    return seen


def chart_marker(evidence: dict, timeframe: str, *, supports=2, resistances=2) -> str:
    below, above = _sorted_levels(evidence)
    parts = [f"chart:{timeframe}"]
    lower = _distinct_ints(below, supports)
    upper = _distinct_ints(above, resistances)
    if lower:
        parts.append("s=" + ",".join(lower))
    if upper:
        parts.append("r=" + ",".join(upper))
    return "[[" + "|".join(parts) + "]]"


def _streak(bars: list[dict], key: str) -> int:
    """จำนวนแท่งท้ายสุดที่ค่า key ไล่สูงขึ้นต่อเนื่อง — นับจากแท่งจริงเท่านั้น"""
    count = 1
    for index in range(len(bars) - 1, 0, -1):
        try:
            current = float(bars[index][key])
            previous = float(bars[index - 1][key])
        except (KeyError, TypeError, ValueError):
            break
        if current > previous:
            count += 1
        else:
            break
    return count


def _news_paragraph(evidence: dict) -> str:
    """สภาพฟีดข่าวตามจริง — ย่อหน้านี้บังคับมีทุกสไตล์ ไม่ว่าจะมีข่าวหรือไม่"""
    news = evidence["news"]
    if not news:
        return ("เรื่องที่ต้องบอกไว้ก่อนคือรอบนี้ฟีดข่าวที่มาพร้อมชุดราคาไม่มีรายการใดเลย "
                "แปลว่าวันนี้เราไม่มีตัวจุดชนวนที่ระบุชื่อได้ และการเดาสาเหตุขึ้นมาเองก็ไม่ช่วยใคร "
                "สิ่งที่ใช้วางแผนได้จริงคือปฏิทินเศรษฐกิจซึ่งบอกล่วงหน้าได้ว่าตัวแปรตัวต่อไปจะมาถึงเมื่อไหร่ "
                "และภาพผลตอบแทนย้อนหลังซึ่งบอกว่าราคายืนอยู่ตรงไหนของรอบใหญ่")
    head = news[0]
    stamp = str(head.get("published_at") or "")
    stale = stamp and stamp < (evidence.get("local_date") or "")
    lead = ("เรื่องที่ต้องบอกไว้ก่อนคือรอบนี้ฝั่งข่าวเงียบผิดปกติ "
            if len(news) == 1 else "เริ่มจากสภาพฝั่งข่าวก่อน ")
    body = (f"ฟีดข่าวที่ระบบดึงมาพร้อมชุดราคามีอยู่ {THAI_COUNT.get(len(news), 'หลาย')}รายการ "
            if len(news) > 1 else "ฟีดข่าวที่ระบบดึงมาพร้อมชุดราคามีอยู่รายการเดียว ")
    body += f"พาดหัวล่าสุดคือ {head['title']}"
    if stale:
        body += (" ซึ่งลงวันที่ไว้ก่อนหน้าวันที่ดึงข้อมูลนี้หลายวัน "
                 "เก่าเกินกว่าจะใช้อธิบายการเคลื่อนไหวของวันนี้ได้ "
                 "สิ่งที่ทำได้คือเก็บไว้เป็นฉากหลังแล้วหันไปอ่านสิ่งที่ตรวจสอบได้จริงแทน "
                 "นั่นคือปฏิทินเศรษฐกิจและภาพผลตอบแทนย้อนหลัง")
    else:
        body += " ซึ่งใช้เป็นบริบทประกอบได้ แต่ยังไม่ใช่ตัวชี้ทิศทางของทองโดยตรง"
    return lead + body


def _calendar_sentences(evidence: dict, *, limit: int = 6) -> list[str]:
    today = evidence.get("local_date") or ""
    lines = []
    for event in wcb_source.upcoming(evidence, impacts=("High", "Medium"), limit=limit):
        if event["country"] != "USD":
            continue
        moment = when(event["at"], today)
        text = f"{moment}เวลา {clock(event['at'])} น. {event['title']}"
        if event["impact"] == "High":
            text += " ซึ่งจัดเป็นรายการผลกระทบสูง"
        if event["previous"] not in (None, ""):
            text += f" ครั้งก่อนอยู่ที่ {event['previous']}"
        lines.append(text)
    return lines


def _performance_paragraph(evidence: dict) -> str:
    perf = (evidence["performance"] or {}).get("perf") or {}
    fifty = (evidence["quote"] or {}).get("fiftyTwoWeek") or {}
    pieces = []
    if fifty.get("highChangePercent") is not None and fifty.get("lowChangePercent") is not None:
        pieces.append(f"ราคาปัจจุบันต่ำกว่าจุดสูงสุดรอบหนึ่งปีอยู่ {pct(fifty['highChangePercent'])}% "
                      f"แต่ยังสูงกว่าจุดต่ำสุดรอบหนึ่งปีอยู่ {pct(fifty['lowChangePercent'])}%")
    if fifty.get("low") is not None and fifty.get("high") is not None:
        pieces.append(f"โดยกรอบหนึ่งปีกว้างตั้งแต่ {price(fifty['low'])} ถึง {price(fifty['high'])} ดอลลาร์")
    spans = []
    for key, label in (("1W", "หนึ่งสัปดาห์"), ("1M", "หนึ่งเดือน"),
                       ("3M", "สามเดือน"), ("6M", "หกเดือน"), ("1Y", "หนึ่งปี")):
        if perf.get(key) is not None:
            word = "บวก" if float(perf[key]) >= 0 else "ติดลบ"
            spans.append(f"{label}{word} {pct(perf[key])}%")
    if spans:
        pieces.append("ด้านผลตอบแทนย้อนหลัง " + " · ".join(spans))
    if not pieces:
        return ""
    return (" ".join(pieces) + " ตัวเลขชุดนี้บอกตำแหน่งของราคาในรอบใหญ่ได้ตรงกว่าความรู้สึก "
            "และควรใช้เป็นฐานในการประเมินข่าวที่กำลังจะออก ไม่ใช่ประเมินจากแท่งวันเดียว")


def _levels_paragraph(evidence: dict) -> str:
    below, above = _sorted_levels(evidence)
    parts = []
    if above:
        following = " ถัดขึ้นไปคือ " + " และ ".join(price(v) for v in above[1:3]) if above[1:3] else ""
        parts.append(f"ด่านแรกฝั่งบนอยู่ที่ {price(above[0])} ดอลลาร์{following}")
    if below:
        following = " ถัดลงไปคือ " + " และ ".join(price(v) for v in below[1:3]) if below[1:3] else ""
        parts.append(f"ฝั่งล่างแนวรับด่านแรกอยู่ที่ {price(below[0])} ดอลลาร์{following}")
    if not parts:
        return ""
    return (" ".join(parts) + " ระดับทั้งหมดนี้เป็นจุดหมุนที่คำนวณจากกรอบเวลาต่าง ๆ ในชุดข้อมูลเดียวกัน "
            "จึงเป็นเส้นที่ผู้เล่นจำนวนมากเห็นตรงกัน และมักเป็นจุดที่ราคาตอบสนองจริง")


def _closing() -> str:
    return ("ปิดท้ายด้วยเรื่องที่สำคัญกว่าการอ่านทิศทางถูก คือการบริหารความเสี่ยง "
            "ปรับขนาดสถานะให้เล็กพอที่ไม้เดียวจะไม่ทำลายพอร์ต "
            "และตั้งจุดตัดขาดทุน (Stop Loss) ทุกไม้ก่อนเข้าตลาดเสมอครับ")


def _frontmatter(evidence: dict, title: str, excerpt: str, timeframe: str) -> list[str]:
    return [
        "---",
        f"asset: {evidence['asset']}",
        f"title: {fit_title(title)}",
        f"excerpt: {fit_excerpt(excerpt) if isinstance(excerpt, list) else excerpt}",
        f"author_slug: {AUTHOR_SLUG}",
        f"timeframe: {timeframe}",
        f"trend: {trend_code(evidence)}",
        "---",
        "",
    ]


def _opening(evidence: dict) -> str:
    quote = evidence["quote"]
    stamp = f" (ข้อมูล ณ {evidence['local_time']} น.)" if evidence.get("local_time") else ""
    text = (f"ทองคำโลก{stamp} อยู่ที่ {price(quote['price'])} ดอลลาร์ต่อออนซ์")
    if quote.get("change") is not None and quote.get("percent") is not None:
        word = "บวก" if float(quote["change"]) >= 0 else "ลบ"
        text += f" {word} {price(abs(float(quote['change'])))} ดอลลาร์หรือ {pct(quote['percent'])}%"
    if quote.get("prevClose") is not None:
        text += f" จากราคาปิดก่อนหน้าที่ {price(quote['prevClose'])}"
    if quote.get("high") is not None and quote.get("low") is not None:
        text += f" ระหว่างวันขึ้นไปสูงสุด {price(quote['high'])} และลงต่ำสุด {price(quote['low'])}"
    return text


# ================================================================== A — มาตรฐาน
def render_a(evidence: dict) -> str:
    indicators = evidence["daily"]["indicators"]
    counts = evidence["daily"]["counts"]
    spot = float(evidence["quote"]["price"])
    below, above = _sorted_levels(evidence)

    lines = _frontmatter(
        evidence,
        f"ทองคำโลก (XAU/USD) ยืนที่ {price(spot)} ประเมินโครงสร้างและปฏิทินข้างหน้า",
        [f"ทองอยู่ที่ {price(spot)} ดอลลาร์",
         f"สัญญาณรายวันรวมเป็น {evidence['daily']['summary']}",
         "อ่านโครงสร้างรายวันคู่กับจังหวะราย 4 ชั่วโมง",
         "พร้อมปฏิทินเศรษฐกิจที่รออยู่ข้างหน้า"],
        "Daily")
    lines += [_opening(evidence) +
              " บทนี้ไล่อ่านโครงสร้างรายวันเป็นหลัก แล้วซูมลงราย 4 ชั่วโมงเพื่อดูจังหวะ "
              "ก่อนปิดท้ายด้วยสิ่งที่ปฏิทินเศรษฐกิจกำลังจะพามา ตลาดยังไม่ปิด ตัวเลขทั้งหมดจึงยังขยับได้อีก",
              "", "## เทคนิคและระดับราคาสำคัญ", ""]

    stack = []
    for name in ("SMA20", "SMA50", "SMA100", "SMA200"):
        value = (indicators.get(name) or {}).get("value")
        if value is None:
            continue
        side = "เหนือ" if spot > float(value) else "ใต้"
        stack.append(f"{side}เส้น {name} ที่ {price(value)}")
    if stack:
        lines += ["เริ่มจากตำแหน่งเทียบเส้นค่าเฉลี่ยรายวัน ราคาล่าสุดอยู่" + " · ".join(stack) +
                  " การเรียงตัวแบบนี้บอกว่าภาพระยะสั้นถึงกลางกับภาพระยะยาวยังไม่ได้เล่าเรื่องเดียวกัน "
                  "ซึ่งเป็นสภาพปกติของช่วงที่ราคากำลังพยายามพลิกโครงสร้าง ไม่ใช่ช่วงที่เทรนด์เดินชัดแล้ว", ""]

    if counts:
        lines += [f"ผลรวมสัญญาณอินดิเคเตอร์รายวันออกมาเป็น {evidence['daily']['summary']} "
                  f"ด้วยคะแนนฝั่งซื้อ {counts.get('buy')} ฝั่งขาย {counts.get('sell')} "
                  f"และเป็นกลาง {counts.get('neutral')} ตัวเลขชุดนี้เป็นการนับหัวเท่านั้น "
                  "ยังไม่ได้บอกน้ำหนัก จึงต้องเปิดดูรายตัวต่อว่าใครพูดอะไร", ""]

    tension = []
    for name, note in (("RSI(14)", "วัดน้ำหนักแรงซื้อขายสะสม"),
                       ("Stochastic(14)", "วัดว่าราคาปิดอยู่ตรงไหนของกรอบสั้น"),
                       ("CCI(20)", "วัดระยะห่างจากค่าเฉลี่ย"),
                       ("MACD(12,26)", "วัดการตัดกันของโมเมนตัม")):
        item = indicators.get(name)
        if item and item.get("value") is not None:
            tension.append(f"{name} อยู่ที่ {num(item['value'])} ให้สัญญาณ{item['signal']} ({note})")
    if tension:
        lines += ["ไล่ดูรายตัวจะเห็นเหลี่ยมที่คนอ่านผ่าน ๆ มักพลาด " + " · ".join(tension) +
                  " จุดสำคัญคืออินดิเคเตอร์จับจังหวะเร็วกับอินดิเคเตอร์สะสมน้ำหนักมักไม่ตรงกันในช่วงที่ราคาวิ่งเร็ว "
                  "และนั่นไม่ใช่ความขัดแย้ง แต่เป็นการบอกว่าแรงซื้อกระจุกอยู่ในระยะสั้นมากกว่าระยะกลาง", ""]

    lines += [chart_marker(evidence, "1day"), ""]
    levels = _levels_paragraph(evidence)
    if levels:
        lines += [levels, ""]

    four = evidence["by_tf"].get("4h")
    if four:
        detail = []
        for name in ("RSI(14)", "ADX(14)", "CCI(20)"):
            item = (four["indicators"] or {}).get(name)
            if item and item.get("value") is not None:
                detail.append(f"{name} ที่ {num(item['value'])}")
        lines += [f"ซูมลงมาที่ราย 4 ชั่วโมงซึ่งเป็นกรอบจับจังหวะ สัญญาณรวมของกรอบนี้อยู่ที่ {four['summary']} "
                  f"ด้วยคะแนนฝั่งซื้อ {(four['counts'] or {}).get('buy')} ต่อฝั่งขาย "
                  f"{(four['counts'] or {}).get('sell')}" +
                  (" โดยมี " + " และ " .join(detail) if detail else "") +
                  " ภาพกรอบนี้ใช้ยืนยันจังหวะได้ แต่ห้ามใช้แทนข้อสรุปของรายวัน "
                  "เพราะกรอบเล็กกว่าย่อมตอบสนองเร็วกว่าและกลับทิศบ่อยกว่าเสมอ", "",
                  chart_marker(evidence, "4h"), ""]

    lines += ["## ปัจจัยพื้นฐานที่ต้องดู", "", _news_paragraph(evidence), ""]
    calendar = _calendar_sentences(evidence)
    if calendar:
        lines += ["ไล่ปฏิทินที่รออยู่ตามลำดับเวลา " + " ถัดมาคือ ".join(calendar) +
                  " (ที่มา: ปฏิทินเศรษฐกิจ WorldClassBroker) "
                  "สายส่งจากตัวเลขเหล่านี้ถึงราคาทองเดินผ่านทางเดียวคือความคาดหวังดอกเบี้ย "
                  "ข้อมูลที่อ่อนกว่าเดิมแปลว่าไม่มีเหตุผลต้องขึ้นดอกเบี้ยเพิ่ม ผลตอบแทนพันธบัตรและดอลลาร์อ่อนลง ทองได้ประโยชน์ "
                  "ในทางกลับกันข้อมูลที่แข็งเกินคาดจะพาเรื่องดอกเบี้ยสูงยาวกลับมาและกดทองทันที", ""]
    performance = _performance_paragraph(evidence)
    if performance:
        lines += [performance, ""]

    lines += ["## กลยุทธ์วันนี้", ""]
    if above and below:
        lines += [f"ตำแหน่งราคาปัจจุบันอยู่ระหว่างแนวรับที่ {price(below[0])} กับแนวต้านที่ {price(above[0])} "
                  "ซึ่งไม่ใช่จุดที่ได้เปรียบทั้งสองทาง คนที่รอเข้าฝั่งซื้อ จังหวะที่คุ้มกว่าคือรอให้ราคาย่อกลับไปทดสอบโซนแนวรับ "
                  "แล้วดูว่ามีแรงรับจริงไหม ส่วนคนที่อยากไล่ราคาที่ระดับนี้ต้องยอมรับว่ากำลังซื้อใกล้ด่านที่ยังไม่ผ่าน", "",
                  f"เงื่อนไขที่บอกว่าภาพวันนี้เสียคือราคากลับลงไปยืนใต้ {price(below[0])} แบบปิดแท่งได้ "
                  "เพราะเท่ากับการทะลุขึ้นมาก่อนหน้ากลายเป็นการทะลุหลอก และโซนแนวรับถัดลงไปจะถูกทดสอบต่อทันที "
                  "ส่วนเงื่อนไขที่ยืนยันฝั่งซื้อคือการปิดเหนือแนวต้านด่านแรกได้จริง ไม่ใช่แค่แทงทะลุระหว่างวันแล้วเด้งกลับ", ""]
    lines += [_closing()]
    return "\n".join(lines)


# ============================================================ B — เทคนิคเจาะลึก
def render_b(evidence: dict) -> str:
    indicators = evidence["daily"]["indicators"]
    spot = float(evidence["quote"]["price"])
    below, above = _sorted_levels(evidence)
    daily_bars = evidence["recent_daily"]

    lines = _frontmatter(
        evidence,
        "ทองคำโลก (XAU/USD) อ่านสี่กรอบเวลาให้ครบ ก่อนตัดสินจากสัญญาณตัวเดียว",
        [f"ไล่โครงสร้างทองจากรายวันถึง 30 นาที ราคาล่าสุด {price(spot)} ดอลลาร์",
         "ดูทั้งอินดิเคเตอร์ชุดเต็มและการนับแท่งจริง",
         "พร้อมจุดที่สัญญาณแต่ละกรอบเวลาขัดกัน"],
        "Daily")
    lines += [_opening(evidence) +
              " บทนี้ไล่อ่านทีละกรอบเวลาจากใหญ่ไปเล็ก เพราะสัญญาณของแต่ละกรอบมักไม่ตรงกัน "
              "และคนที่หยิบมาแค่ตัวเดียวมีโอกาสอ่านผิดทางสูง แท่งล่าสุดของทุกกรอบเวลายังวิ่งอยู่ ยังไม่ปิด",
              "", "## เทคนิคและระดับราคาสำคัญ", ""]

    if len(daily_bars) >= 3:
        highs = _streak(daily_bars, "high")
        lows = _streak(daily_bars, "low")
        if highs >= 2 or lows >= 2:
            detail = []
            if highs >= 2:
                detail.append(f"จุดสูงสุดยกขึ้นต่อเนื่อง {THAI_COUNT.get(highs, 'หลาย')}แท่ง")
            if lows >= 2:
                detail.append(f"จุดต่ำสุดยกขึ้นต่อเนื่อง {THAI_COUNT.get(lows, 'หลาย')}แท่ง")
            lines += ["เริ่มจากสิ่งที่นับได้จริงบนแท่งรายวัน " + " และ ".join(detail) +
                      " การยกทั้งจุดสูงและจุดต่ำพร้อมกันคือนิยามพื้นฐานของโครงสร้างขาขึ้นระยะสั้น "
                      "ไม่ใช่การเด้งเทคนิคแท่งเดียว ข้อดีของการนับแบบนี้คือมันตรวจสอบย้อนกลับได้ "
                      "ต่างจากการอ่านรูปทรงกราฟที่แต่ละคนเห็นไม่เหมือนกัน", ""]

    full = []
    for name in ("RSI(14)", "MACD(12,26)", "Stochastic(14)", "CCI(20)", "Momentum(10)", "ADX(14)"):
        item = indicators.get(name)
        if item and item.get("value") is not None:
            full.append(f"{name} อยู่ที่ {num(item['value'])} สัญญาณ{item['signal']}")
    if full:
        lines += ["อินดิเคเตอร์รายวันชุดเต็มให้ภาพแบบนี้ " + " · ".join(full) +
                  " สิ่งที่ต้องอ่านคือความสัมพันธ์ ไม่ใช่ค่าเดี่ยว ๆ ตัวที่วัดโมเมนตัมสะสมกับตัวที่วัดตำแหน่งในกรอบสั้น "
                  "แยกกันได้มากในวันที่ราคาวิ่งเร็ว และช่องว่างระหว่างสองกลุ่มนี้คือสิ่งที่บอกว่ารอบนี้อยู่ช่วงต้นหรือช่วงปลาย", ""]
    lines += [chart_marker(evidence, "1day"), ""]

    four = evidence["by_tf"].get("4h")
    if four:
        detail = []
        for name in ("RSI(14)", "ADX(14)", "CCI(20)", "Stochastic(14)"):
            item = (four["indicators"] or {}).get(name)
            if item and item.get("value") is not None:
                detail.append(f"{name} ที่ {num(item['value'])} สัญญาณ{item['signal']}")
        lines += [f"ลงมาที่ราย 4 ชั่วโมง สัญญาณรวมอยู่ที่ {four['summary']} ด้วยคะแนนฝั่งซื้อ "
                  f"{(four['counts'] or {}).get('buy')} ต่อฝั่งขาย {(four['counts'] or {}).get('sell')} "
                  + (" โดย " + " · ".join(detail) if detail else "") +
                  " จุดที่ต้องหยุดดูเป็นพิเศษคือค่าที่วัดความแรงของเทรนด์ เพราะราคาที่วิ่งขึ้นแรงพร้อมกับเทรนด์ที่ยังไม่ได้รับการยืนยัน "
                  "มักเป็นการวิ่งจากแรงกระตุ้นชั่วคราวมากกว่าเทรนด์ที่ตั้งฐานมั่นคง และโครงแบบนั้นย่อกลับได้เร็วพอ ๆ กับที่ขึ้นมา", "",
                  chart_marker(evidence, "4h"), ""]

    ladder = []
    for name in ("1day", "4h", "1h", "30min"):
        block = evidence["by_tf"].get(name) if name != "1day" else evidence["daily"]
        item = ((block or {}).get("indicators") or {}).get("RSI(14)")
        if item and item.get("value") is not None:
            ladder.append(f"{name} อยู่ที่ {num(item['value'])}")
    if len(ladder) >= 3:
        lines += ["ขอย้ำก่อนว่ากรอบ 1 ชั่วโมงและ 30 นาทีใช้เป็นข้อมูลประกอบเท่านั้น ไม่ใช่ข้อสรุปของบท "
                  "เมื่อเรียง RSI ทุกกรอบเวลาต่อกันจะได้แบบนี้ " + " · ".join(ladder) +
                  " การไล่ระดับแบบนี้อ่านได้ตรงตัวว่าแรงซื้อกระจุกอยู่ในระยะสั้นมากแค่ไหน "
                  "หลักที่ถูกคือยึดกรอบใหญ่เป็นตัวตั้งแล้วเอากรอบเล็กมาเป็นข้อควรระวัง "
                  "ไม่ใช่หยิบค่าที่ตึงที่สุดของกรอบเล็กขึ้นมาแล้วสรุปภาพรวมทั้งหมด นั่นคือการเอาหางไปกระดิกหมา", ""]

    lines += ["## ปัจจัยพื้นฐานที่ต้องดู", "", _news_paragraph(evidence), ""]
    calendar = _calendar_sentences(evidence, limit=4)
    if calendar:
        lines += ["สำหรับบทเชิงเทคนิค ปฏิทินมีค่าในฐานะตัวกำหนดเวลาที่ความผันผวนจะกระโดด มากกว่าจะเป็นตัวชี้ทิศ "
                  "เวลาที่ควรหมายไว้บนกราฟคือ " + " · ".join(calendar) +
                  " (ที่มา: ปฏิทินเศรษฐกิจ WorldClassBroker) "
                  "สิ่งที่ควรทำในช่วงเวลาเหล่านี้คือลดขนาดสถานะและถอยจุดตัดขาดทุนให้พ้นโซนแนวรับที่นับมาได้ "
                  "ไม่ใช่ตั้งชิดยอดแล้วหวังว่าแรงเหวี่ยงช่วงประกาศจะไม่กวาดถึง", ""]

    lines += ["## กลยุทธ์วันนี้", ""]
    levels = _levels_paragraph(evidence)
    if levels:
        lines += [levels, ""]
    if below:
        lines += [f"เงื่อนไขที่บอกว่าภาพเทคนิควันนี้เสียคือแท่งราคาหลุดลงไปปิดใต้ {price(below[0])} ดอลลาร์ "
                  "เพราะเท่ากับทำลายทั้งจุดหมุนที่อ้างถึงและโครงสร้างการยกฐานที่นับมาได้ทั้งชุด "
                  "ตราบที่ยังไม่เกิดเงื่อนไขนั้น การย่อระหว่างทางยังเป็นการย่อในโครงเดิม ไม่ใช่การเปลี่ยนโครง", ""]
    lines += [_closing()]
    return "\n".join(lines)


# ============================================================== C — อิงเหตุการณ์
def render_c(evidence: dict) -> str:
    spot = float(evidence["quote"]["price"])
    below, above = _sorted_levels(evidence)

    lines = _frontmatter(
        evidence,
        "ทองคำโลก (XAU/USD) วางฉากทัศน์ก่อนถึงคิวข้อมูลชุดใหญ่ในปฏิทิน",
        [f"ทองอยู่ที่ {price(spot)} ดอลลาร์ ก่อนเข้าช่วงที่ปฏิทินอัดแน่น",
         "วางฉากทัศน์และระดับราคาที่ต้องดูไว้ล่วงหน้า",
         "ดีกว่ารอให้ข่าวออกแล้วค่อยวิ่งตาม"],
        "Daily")
    lines += [_opening(evidence) +
              " แต่เรื่องที่สำคัญกว่าราคาวันนี้คือปฏิทินที่รออยู่ข้างหน้า "
              "บทนี้จึงวางฉากทัศน์ไว้ล่วงหน้าว่าถ้าตัวเลขออกมาแต่ละแบบ ระดับราคาไหนคือจุดที่ต้องดู "
              "แทนที่จะรอให้ข่าวออกแล้วค่อยวิ่งตาม ตลาดยังไม่ปิด ตัวเลขทั้งหมดจึงยังขยับได้อีก",
              "", "## เทคนิคและระดับราคาสำคัญ", ""]

    lines += ["ก่อนพูดถึงเหตุการณ์ ต้องรู้ก่อนว่าสมรภูมิอยู่ตรงไหน "
              "เพราะฉากทัศน์ที่ไม่มีระดับราคากำกับคือความเห็น ไม่ใช่แผน", ""]
    levels = _levels_paragraph(evidence)
    if levels:
        lines += [levels, ""]
    counts = evidence["daily"]["counts"]
    if counts:
        lines += [f"ด้านสภาพตลาด สัญญาณอินดิเคเตอร์รายวันรวมเป็น {evidence['daily']['summary']} "
                  f"ด้วยคะแนนฝั่งซื้อ {counts.get('buy')} ฝั่งขาย {counts.get('sell')} "
                  f"และเป็นกลาง {counts.get('neutral')} "
                  "ภาพนี้บอกว่าโครงสร้างยังเอนไปทางเดียว แต่ยังไม่ถึงขั้นขาดลอย "
                  "ซึ่งเป็นสภาพที่ข่าวมีอำนาจเปลี่ยนทิศได้มากที่สุด เพราะไม่มีเทรนด์แข็งพอจะดูดซับแรงเหวี่ยง", ""]
    lines += [chart_marker(evidence, "1day"), ""]

    lines += ["## ปัจจัยพื้นฐานที่ต้องดู", "", _news_paragraph(evidence), ""]
    calendar = _calendar_sentences(evidence, limit=8)
    if calendar:
        lines += ["ไล่ไทม์ไลน์ที่รออยู่ตามลำดับ ด่านแรกคือ" + calendar[0], ""]
        if calendar[1:]:
            lines += ["ด่านถัดไปเรียงกันมาแบบนี้ " + " ต่อด้วย ".join(calendar[1:]) +
                      " (ที่มา: ปฏิทินเศรษฐกิจ WorldClassBroker) "
                      "ทุกรายการในชุดนี้ยังไม่มีตัวเลขคาดการณ์ในระบบ จึงอ้างได้แค่ค่าครั้งก่อนกับวันเวลาเท่านั้น "
                      "การเดาตัวเลขคาดการณ์ขึ้นมาเองคือการสร้างข้อมูลที่ไม่มีต้นทาง", ""]
    lines += ["สายส่งจากข้อมูลเศรษฐกิจถึงราคาทองเดินผ่านความคาดหวังดอกเบี้ยเป็นหลัก "
              "เศรษฐกิจที่อ่อนแรงลงแปลว่าไม่มีเหตุผลต้องขึ้นดอกเบี้ยเพิ่ม ต้นทุนค่าเสียโอกาสของการถือทองซึ่งไม่มีดอกผลจึงลดลง "
              "กลับกันถ้าข้อมูลออกมาแข็ง เรื่องดอกเบี้ยสูงยาวจะถูกหยิบขึ้นมาพูดใหม่ทันที "
              "สิ่งที่ต้องระวังเป็นพิเศษคือกรณีที่ตัวเลขคนละตัวออกมาคนละทาง เพราะตลาดจะใช้เวลาเลือกว่าจะให้น้ำหนักตัวไหน "
              "และช่วงที่ตลาดยังไม่เลือก คือช่วงที่ราคาเหวี่ยงสองทางแรงที่สุด", ""]
    performance = _performance_paragraph(evidence)
    if performance:
        lines += [performance, ""]

    lines += ["## กลยุทธ์วันนี้", ""]
    if above and below:
        lines += [f"ฉากทัศน์แรก ถ้าข้อมูลออกมาอ่อนกว่าครั้งก่อน แรงหนุนฝั่งทองจะแข็งขึ้น "
                  f"สิ่งที่ต้องเห็นคือราคายืนเหนือ {price(above[0])} ดอลลาร์ได้จริงหลังข่าวผ่านไปสักพัก "
                  "ไม่ใช่แค่แทงทะลุตอนข่าวออกแล้วเด้งกลับ ซึ่งเป็นภาพที่เกิดบ่อยจนหลอกคนได้ทุกรอบ", "",
                  f"ฉากทัศน์ที่สอง ถ้าข้อมูลออกมาแข็งกว่าครั้งก่อน ให้จับตาว่าราคาจะหลุดกลับลงไปใต้ "
                  f"{price(below[0])} ดอลลาร์หรือไม่ ถ้าหลุดแล้วยืนไม่ได้ โซนแนวรับถัดลงไปจะถูกทดสอบต่อในรอบเดียวกัน", ""]
    lines += ["สิ่งที่ไม่ควรทำในช่วงแบบนี้คือการเข้าไม้ใหญ่ตามแรงกระชากช่วงข่าวออกใหม่ ๆ "
              "เพราะราคามักวิ่งสองทางในไม่กี่นาทีแรกก่อนเลือกทิศจริง คนที่เข้าตอนนั้นมักได้ราคาที่แย่ที่สุดของทั้งวัน "
              "การรอให้ตลาดเลือกทางแล้วค่อยเข้าตามโครงสร้างที่ยืนยันแล้ว เป็นวิธีที่ช้ากว่าแต่รอดกว่า", "",
              _closing()]
    return "\n".join(lines)


# ---------------------------------------------------------------- ทะเบียนนักเขียน
WCB_WRITERS = (
    {
        "id": "a_standard",
        "style": "A — มาตรฐาน",
        "folder": "A-มาตรฐาน",
        "render": render_a,
        "summary": "สมดุลเทคนิค-พื้นฐาน-กลยุทธ์ · โครงสร้างรายวันแล้วซูมราย 4 ชั่วโมง · หมุดกราฟสองจุด",
    },
    {
        "id": "b_technical",
        "style": "B — เทคนิคเจาะลึก",
        "folder": "B-เทคนิคเจาะลึก",
        "render": render_b,
        "summary": "ไล่สี่กรอบเวลาจากใหญ่ไปเล็ก · อินดิเคเตอร์ชุดเต็มและการนับแท่งจริง · ปัจจัยพื้นฐานย่อ",
    },
    {
        "id": "c_event",
        "style": "C — อิงเหตุการณ์",
        "folder": "C-อิงเหตุการณ์",
        "render": render_c,
        "summary": "นำด้วยปฏิทิน · เทคนิคย่อเป็นระดับสมรภูมิ · ปิดด้วยฉากทัศน์สองทางต่อเหตุการณ์",
    },
)


def by_id(writer_id: str) -> dict:
    for writer in WCB_WRITERS:
        if writer["id"] == writer_id:
            return writer
    raise KeyError(f"ไม่รู้จักสไตล์ '{writer_id}' — มีให้เลือก "
                   f"{', '.join(item['id'] for item in WCB_WRITERS)}")
