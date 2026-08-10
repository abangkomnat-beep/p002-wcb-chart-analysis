"""นักเขียนบทสั้นตอนเช้า สไตล์ F/G + ด่านตรวจของสองสไตล์นี้เอง

โครงมาจากบทจริงของ InterGold สองใบที่ผู้ใช้ส่งมา 2026-08-10 (สเปกฉบับแกะอยู่ที่
`01-CC/Output/2026-08-10_แกะสไตล์-F-G-จากบทจริง-InterGold.md`) — ย่อสามย่อหน้า
ไม่มีหัวข้อย่อย มีกล่องกลยุทธ์สามบรรทัดคั่นบนสุด:

    กลยุทธ์ : {วลี}          F = สภาพตลาด · G = ชื่อเหตุการณ์ที่รออยู่
    แนวต้าน : {ราคา} ดอลลาร์
    แนวรับ : {ราคา} ดอลลาร์

**สามอย่างที่จงใจไม่ลอกจากต้นแบบ** (ไม่ใช่ลืม):

1. **พาดหัว** — ต้นแบบใช้ "บทวิเคราะห์ราคาทองคำประจำวันที่ …" แต่สเปกพาดหัวของ
   หัวหน้าถูกล็อกด้วยเทสเทียบสเปกไปแล้ว (08-10) ⇒ ใช้ `headline_format` ของระบบ
   ลอกเฉพาะ**โครงเนื้อบท** ไม่ลอกพาดหัว
2. **ราคาทองไทย (บาท)** — ต้นแบบพิมพ์คู่ `$3,960 , 63,100 บาท` แต่อัตราแปลงของเขา
   ไม่คงที่ (15.93 กับ 15.75 ในบทคนละใบ) = ราคาหน้าร้านในประเทศ ไม่ใช่ผลคูณจากสปอต
   และระบบเราไม่มีแหล่งราคาทองไทยเลย ⇒ **พิมพ์ดอลลาร์อย่างเดียว** ตัดครึ่งบาททิ้งเงียบ
3. **ย่อหน้าปัจจัยแบบเล่าข่าว** — ต้นแบบเล่ามหภาค (ฮอร์มุซ · ISM · เยน) ซึ่งเราไม่มี
   แหล่งยืนยัน ⇒ ย่อหน้าที่สองของเราพูดจาก**ปฏิทินเศรษฐกิจ**เท่านั้น ตัวเดียวกับที่
   สไตล์ D ใช้ และต้องมีวลีที่มา ไม่มีปฏิทิน = ตัดย่อหน้านั้นทิ้งเงียบ เหลือสองย่อหน้า

ด่าน `validate` แบบ fail-closed เหมือน D/E — เลขนอกทะเบียนตัวเดียว = ตกทั้งบท
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import brief_story, candle_close, consistency_gate, headline_format  # noqa: E402
from tools import image_output, wcb_source, wcb_writers  # noqa: E402
from tools.chart_story_renderer import price_text, thai_date  # noqa: E402
from tools.chart_story_writer import AUTHOR  # noqa: E402 — byline เดียวกันทั้งระบบ

STYLE_NAMES = {
    brief_story.STYLE_F: "F — บทกรอบเช้า",
    brief_story.STYLE_G: "G — บทรอเหตุการณ์เช้า",
}
FOLDERS = {
    brief_story.STYLE_F: "F-กรอบราคา",
    brief_story.STYLE_G: "G-รอเหตุการณ์",
}
IMAGE_KIND = {brief_story.STYLE_F: "range", brief_story.STYLE_G: "channel"}

# บทเช้าสั้นโดยตั้งใจ — ต้นแบบ ~230–260 คำไทย ซึ่งตกราว 1,000–1,300 อักขระ
# ต่ำกว่าเพดานล่างนี้แปลว่าย่อหน้าหายไปหนึ่งช่วง ไม่ใช่ "วันนี้เขียนสั้น"
MIN_CHARS = 700
# เพดานบนมีไว้กันไม่ให้บทเช้ากลายพันธุ์เป็นบทยาวแบบ D/E เงียบ ๆ
MAX_CHARS = 2600

BIAS_PHRASE = {
    "sideway": "แกว่งในกรอบ Sideway",
    "sideway_up": "แกว่งในกรอบ Sideway-Up",
    "sideway_down": "แกว่งในกรอบ Sideway-Down",
}
BIAS_IN_TEXT = {
    "sideway": "กรอบแนวนอน",
    "sideway_up": "กรอบที่ค่อย ๆ ยกตัว",
    "sideway_down": "กรอบที่ค่อย ๆ ลาดลง",
}

CALENDAR_SOURCE = "(ที่มา: ปฏิทินเศรษฐกิจ WorldClassBroker)"

_NUMBER = re.compile(r"\d[\d,\.]*")


def money_for(brief: dict):
    places = wcb_source.profile_for(brief["asset"])["decimals"]
    return lambda value: price_text(value, places)


def percent(value: float) -> str:
    return f"{value:.2f}"


def image_name(brief: dict) -> str:
    """ชื่อไฟล์ภาพประกอบใบเดียวของบทเช้า — มีความหมาย + วันที่ แนวเดียวกับ D/E"""
    kind = IMAGE_KIND[brief["style"]]
    return (f"{brief['asset']}-brief-{kind}-{brief['current']['date']}"
            f"{image_output.IMAGE_SUFFIX}")


def folder_for(brief: dict) -> str:
    return FOLDERS[brief["style"]]


def strategy_phrase(brief: dict) -> str:
    """บรรทัด `กลยุทธ์ :` — ตัวแยก F/G ที่คนอ่านเห็นก่อนอย่างอื่น

    F พูดสภาพตลาด · G พูดชื่อเหตุการณ์ที่รออยู่ (ตามสเปกข้อ 2.2/3.2)
    """
    if brief["style"] == brief_story.STYLE_G:
        return f"รอลุ้น{brief['event']['title']}"
    return BIAS_PHRASE[bias_of(brief)]


def bias_of(brief: dict) -> str:
    """คำที่บทใช้เรียกกรอบ — **F เรียกตามกล่อง · G เรียกตามช่องแนวโน้ม**

    ทั้งสองสไตล์วาดคนละอย่างลงภาพ (F = กล่องกรอบ · G = ช่องแนวโน้ม) บทจึงต้องเรียก
    ตามสิ่งที่ภาพของสไตล์ตัวเองแสดง ไม่ใช่ใช้ค่าเดียวกันทั้งคู่ (ดู `channel_bias`)
    """
    if brief["style"] == brief_story.STYLE_G:
        return brief_story.channel_bias(brief["channel"], brief["atr14"])
    return brief["range_box"]["bias"]


def _h1_tail(brief: dict) -> str:
    """หางพาดหัว — 🐞 เคยฮาร์ดโค้ดคำว่า "ทอง" ทั้งสองสไตล์ (พบตอนตรวจใบ SOL ก่อนส่ง
    หัวหน้า 08-10: `วิเคราะห์ SOL วันนี้ … — ทองพักฐานเหนือ 72.14`) — บั๊กตระกูล
    เดียวกับ `price_text` ที่ตรึงทศนิยม 2 ตำแหน่ง: ตัวเขียนใหม่เกิดในโลกของทองเสมอ
    ⇒ ชื่อเรียกสินทรัพย์ต้องมาจากทะเบียนทุกจุด ห้ามพิมพ์ลงไปตรง ๆ"""
    money = money_for(brief)
    short_name = wcb_source.profile_for(brief["asset"])["short_name"]
    if brief["style"] == brief_story.STYLE_G:
        return f"{short_name}พักฐานเหนือ {money(brief['support'])} รอ{brief['event']['title']}"
    return (f"{short_name}แกว่งกรอบ {money(brief['range_box']['low'])}"
            f"–{money(brief['range_box']['high'])}")


def _excerpt_clauses(brief: dict) -> list[str]:
    money = money_for(brief)
    profile = wcb_source.profile_for(brief["asset"])
    clauses = [f"{profile['short_name']}ปิดที่ {money(brief['current']['close'])} ดอลลาร์",
               f"แนวรับ {money(brief['support'])}",
               f"แนวต้าน {money(brief['resistance'])}"]
    if brief["style"] == brief_story.STYLE_G:
        clauses.append(f"อ่านแผนสั้นก่อน{brief['event']['title']}พร้อมฉากทัศน์สองทาง")
    else:
        clauses.append("อ่านกรอบราคาวันนี้พร้อมแผนซื้อขายในกรอบแบบสั้น")
    clauses.append("ทุกระดับคำนวณจากแท่งราคาจริง")
    return clauses


def frontmatter_lines(brief: dict) -> list[str]:
    title = headline_format.title(brief["asset"], brief["current"]["date"])
    return [
        "---",
        f"asset: {brief['asset']}",
        f"title: {wcb_writers.fit_title(title)}",
        f"excerpt: {wcb_writers.fit_excerpt(_excerpt_clauses(brief))}",
        f"author_slug: {wcb_writers.AUTHOR_SLUG}",
        "timeframe: Daily",
        f"trend: {'dn' if brief['regime']['down'] else 'up'}",
        "---",
        "",
    ]


def _opening_paragraph(brief: dict) -> str:
    """¶1 — F เล่ากรอบสองด้าน · G เล่าว่าราคายืนตรงไหนแล้วตลาดหยุดรอ"""
    money = money_for(brief)
    profile = wcb_source.profile_for(brief["asset"])
    box = brief["range_box"]
    close = brief["current"]["close"]
    date_text = thai_date(brief["current"]["date"])

    if brief["style"] == brief_story.STYLE_G:
        gap = (close - brief["support"]) / brief["support"] * 100
        return (f"แท่งรายวันล่าสุดของ{profile['thai_name']} ({date_text}) ปิดที่ "
                f"{money(close)} {profile['unit_phrase']} ยังยืนเหนือแนวรับสำคัญที่ "
                f"{money(brief['support'])} {profile['unit_phrase']} อยู่ "
                f"{percent(gap)} เปอร์เซ็นต์ แต่ยังไม่มีปัจจัยใหม่ที่ผลักให้หลุดกรอบไปทางใดทางหนึ่ง "
                f"จังหวะแบบนี้เป็นภาพปกติของช่วงก่อนตัวเลขใหญ่ ตลาดชะลอการตัดสินใจเพื่อรอ"
                f"{brief['event']['title']} ซึ่งเป็นตัวกำหนดทิศทางระยะสั้นมากกว่าการเคลื่อนไหวรายวันตอนนี้")

    width = (box["high"] - box["low"]) / box["low"] * 100
    position = (close - box["low"]) / (box["high"] - box["low"]) * 100
    return (f"แท่งรายวันล่าสุดของ{profile['thai_name']} ({date_text}) ปิดที่ "
            f"{money(close)} {profile['unit_phrase']} อยู่ใน{BIAS_IN_TEXT[box['bias']]}ที่กินช่วง "
            f"{money(box['low'])} ถึง {money(box['high'])} {profile['unit_phrase']} "
            f"ตลอด {box['bars']} แท่งทำการหลังสุด กรอบนี้กว้าง {percent(width)} เปอร์เซ็นต์ "
            f"และราคาล่าสุดยืนอยู่ที่ {percent(position)} เปอร์เซ็นต์ของความสูงกรอบ "
            f"ยังไม่มีการปิดแท่งออกนอกกรอบทั้งด้านบนและด้านล่าง ทิศทางจึงยังไม่ถูกเลือก")


def _factor_paragraph(brief: dict) -> str | None:
    """¶2 — พูดจากปฏิทินเท่านั้น · ไม่มีปฏิทิน = คืน None แล้วบทเหลือสองย่อหน้า

    วลีที่มาบังคับมี ตามด่าน `calendar_source_missing` ที่ใช้กับสไตล์ D อยู่แล้ว
    """
    sentences = brief.get("calendar_sentences") or []
    if not sentences:
        return None
    lead = ("ฝั่งปัจจัยพื้นฐาน รายการที่ตลาดจับตาในช่วงนี้เรียงตามเวลาคือ "
            if brief["style"] == brief_story.STYLE_F else
            "นอกจากตัวเลขที่รออยู่ ปฏิทินช่วงนี้ยังมีรายการอื่นเรียงตามเวลาคือ ")
    return lead + " ถัดมาคือ ".join(sentences) + f" {CALENDAR_SOURCE}"


def _technical_paragraph(brief: dict) -> str:
    """¶3 — F จบด้วยเงื่อนไขเดียว · G จบด้วยฉากทัศน์คู่ผูกกับผลของเหตุการณ์"""
    money = money_for(brief)
    profile = wcb_source.profile_for(brief["asset"])
    support, resistance = brief["support"], brief["resistance"]
    sma50 = brief["sma50_last"]
    close = brief["current"]["close"]
    stance = "เหนือ" if close >= sma50 else "ใต้"

    head = (f"ในเชิงเทคนิค ราคายัง{BIAS_PHRASE[bias_of(brief)].replace('แกว่งใน', 'เคลื่อนไหวใน')} "
            f"และปิดอยู่{stance}เส้นค่าเฉลี่ย 50 วันที่ {money(sma50)} {profile['unit_phrase']} "
            f"โดยมีแนวรับสำคัญที่ {money(support)} และแนวต้านที่ {money(resistance)} "
            f"{profile['unit_phrase']} ")

    if brief["style"] == brief_story.STYLE_G:
        return (head +
                "กลยุทธ์ระยะสั้นจึงเป็นการรอจังหวะย่อตัวเข้าหาแนวรับมากกว่าไล่ราคาที่ระดับนี้ "
                f"และทยอยลดสถานะเมื่อราคาเข้าใกล้แนวต้าน พร้อมติดตาม{brief['event']['title']}อย่างใกล้ชิด "
                f"เพราะหากตัวเลขออกมาอ่อนกว่าที่ตลาดคาด แนวต้าน {money(resistance)} "
                "คือด่านแรกที่จะถูกทดสอบทันที "
                f"แต่หากออกมาแข็งแกร่งกว่าคาด แนวรับ {money(support)} "
                "คือระดับที่ต้องเฝ้าว่าจะยังปิดแท่งยืนได้หรือไม่")

    return (head +
            f"เงื่อนไขที่ต้องดูมีข้อเดียว คือราคายังปิดแท่งเหนือ {money(support)} ได้หรือไม่ "
            f"หากยืนได้ กรอบเดิมยังใช้ได้และเป้าฝั่งบนคือการกลับขึ้นไปทดสอบ {money(resistance)} "
            "กลยุทธ์ระยะสั้นจึงเป็นการรอย่อสะสมบริเวณแนวรับและทยอยขายทำกำไรเมื่อราคาเข้าใกล้แนวต้าน "
            "ไม่ใช่การไล่ราคากลางกรอบซึ่งไม่ได้เปรียบทั้งสองทาง")


def render_article(brief: dict) -> str:
    """ประกอบบทเช้าใบเดียว — ลำดับบล็อกตายตัวตามสเปกข้อ 1"""
    money = money_for(brief)
    profile = wcb_source.profile_for(brief["asset"])
    date_text = brief["current"]["date"]
    picture = image_name(brief)
    alt_parts = [f"{profile['thai_name']} รายวัน {thai_date(date_text)}",
                 f"แนวรับ {money(brief['support'])}",
                 f"แนวต้าน {money(brief['resistance'])}"]
    for label in alt_parts:
        findings = consistency_gate.check_labels([label])
        if findings:
            raise ValueError(f"ข้อความ alt ไม่ผ่านด่านความสอดคล้อง: {findings[0]['message']}")

    lines = frontmatter_lines(brief)
    lines += [f"# {headline_format.h1(brief['asset'], date_text, _h1_tail(brief))}", "",
              f"*โดย {AUTHOR}*", "",
              f"![{' · '.join(alt_parts)}]({picture})", "",
              f"กลยุทธ์ : {strategy_phrase(brief)}", "",
              f"แนวต้าน : {money(brief['resistance'])} {profile['unit_phrase']}", "",
              f"แนวรับ : {money(brief['support'])} {profile['unit_phrase']}", "",
              _opening_paragraph(brief), ""]
    factors = _factor_paragraph(brief)
    if factors:
        lines += [factors, ""]
    lines += [_technical_paragraph(brief), ""]
    return "\n".join(lines).rstrip() + "\n"


def allowed_numbers(brief: dict) -> set[str]:
    """ทะเบียนเลขที่บทเช้าพูดได้ — นอกทะเบียน = ตกด่าน

    รวมเลขที่ประกอบขึ้นระหว่างเขียน (เปอร์เซ็นต์ความกว้างกรอบ ฯลฯ) โดย**คำนวณซ้ำ
    ด้วยสูตรเดียวกับตอนเขียน** ไม่ใช่ไปดูดจากข้อความที่เขียนไปแล้ว — ไม่งั้นด่านนี้
    จะรับรองเลขที่ตัวเองพิมพ์ผิด
    """
    money = money_for(brief)
    box = brief["range_box"]
    close = brief["current"]["close"]
    values = {money(close), money(brief["support"]), money(brief["resistance"]),
              money(box["low"]), money(box["high"]), money(brief["sma50_last"]),
              str(box["bars"]), "50"}
    width = (box["high"] - box["low"]) / box["low"] * 100
    position = (close - box["low"]) / (box["high"] - box["low"]) * 100
    values |= {percent(width), percent(position)}
    if brief["support"]:
        values.add(percent((close - brief["support"]) / brief["support"] * 100))
    # วันที่ในพาดหัว/บรรทัดวัน + ปีในชื่อไฟล์ภาพ
    day, month, year = brief["current"]["date"].split("-")[::-1]
    values |= {str(int(day)), str(int(month)), year,
               str(headline_format.buddhist_year(brief["current"]["date"][:4]))}
    # เลขในประโยคปฏิทิน — ประโยคเหล่านี้มาจาก `_calendar_sentences` ซึ่งพูดจาก
    # หลักฐานฟีดอยู่แล้ว (เหตุผลเดียวกับที่สไตล์ D ทำ)
    for sentence in brief.get("calendar_sentences") or []:
        for token in _NUMBER.findall(sentence):
            values.add(token.rstrip(".,"))
    for sentence in (brief.get("event") or {}).get("title", "").split():
        for token in _NUMBER.findall(sentence):
            values.add(token.rstrip(".,"))
    return values


def validate(markdown: str, brief: dict) -> dict:
    """ด่านของสไตล์ F/G — fatal ตัวเดียวก็ตกทั้งใบ"""
    findings: list[dict] = list(consistency_gate.check(markdown, brief))

    closed_detail = candle_close.verify(
        brief.get("candle_basis"), asset=brief["asset"],
        session_date=brief["current"]["date"])
    if closed_detail:
        findings.append({
            "rule": "closed_candle_required", "severity": "fatal", "line": 1,
            "message": f"บทเรียกแท่งล่าสุดว่า 'ปิด' แต่ {closed_detail}",
        })

    # โครงบทเช้า: ห้ามมีหัวข้อย่อยเลย (ต้นแบบไม่มีสักอัน — นี่คือสิ่งที่ทำให้มันเป็นบทเช้า)
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        if line.startswith("## "):
            findings.append({
                "rule": "subheading_forbidden", "severity": "fatal", "line": line_number,
                "message": f"บทเช้ามีหัวข้อย่อย '{line.strip()}' — สไตล์ F/G ไม่มีหัวข้อย่อย",
            })

    if "|" in markdown:
        findings.append({
            "rule": "table_forbidden", "severity": "fatal", "line": 1,
            "message": "พบอักขระตาราง '|' — บทสาธารณะห้ามตาราง",
        })

    for label in ("กลยุทธ์ : ", "แนวต้าน : ", "แนวรับ : "):
        if label not in markdown:
            findings.append({
                "rule": "strategy_box_incomplete", "severity": "fatal", "line": 1,
                "message": f"กล่องหัวบทขาดบรรทัด '{label.strip()}' — สไตล์ F/G บังคับครบสามบรรทัด",
            })

    picture = image_name(brief)
    if f"({picture})" not in markdown:
        findings.append({
            "rule": "missing_image", "severity": "fatal", "line": 1,
            "message": f"บทไม่ได้อ้างภาพ {picture} — บทเช้าต้องมีภาพเสมอ",
        })

    if brief.get("calendar_sentences") and CALENDAR_SOURCE not in markdown:
        findings.append({
            "rule": "calendar_source_missing", "severity": "fatal", "line": 1,
            "message": f"มีย่อหน้าปฏิทินแต่ไม่มีวลี '{CALENDAR_SOURCE}'",
        })

    # ตัวแยกสไตล์ — เขียนผิดพันธุ์ = ตก ไม่ใช่ปล่อยออกไปแล้วค่อยรู้ว่าสองสไตล์เหมือนกัน
    if brief["style"] == brief_story.STYLE_G:
        if "แต่หาก" not in markdown:
            findings.append({
                "rule": "dual_scenario_missing", "severity": "fatal", "line": 1,
                "message": "สไตล์ G ต้องจบด้วยฉากทัศน์คู่ ('เพราะหาก… แต่หาก…') แต่ไม่พบ",
            })
        if brief["event"]["title"] and brief["event"]["title"] not in markdown:
            findings.append({
                "rule": "event_not_named", "severity": "fatal", "line": 1,
                "message": f"สไตล์ G ต้องเอ่ยชื่อเหตุการณ์ '{brief['event']['title']}' ในบท",
            })
    elif "แต่หาก" in markdown:
        findings.append({
            "rule": "single_condition_required", "severity": "fatal", "line": 1,
            "message": "สไตล์ F ต้องจบด้วยเงื่อนไขเดียว แต่พบฉากทัศน์คู่ — นั่นเป็นโครงของ G",
        })

    body = markdown.split("---", 2)[-1]
    if len(body) < MIN_CHARS:
        findings.append({
            "rule": "article_too_short", "severity": "fatal", "line": 1,
            "message": f"เนื้อบท {len(body)} อักขระ ต่ำกว่าเกณฑ์ {MIN_CHARS} — น่าจะมีย่อหน้าหาย",
        })
    if len(body) > MAX_CHARS:
        findings.append({
            "rule": "article_too_long", "severity": "fatal", "line": 1,
            "message": f"เนื้อบท {len(body)} อักขระ เกินเกณฑ์ {MAX_CHARS} — "
                       "บทเช้าต้องสั้น ยาวกว่านี้คือกลายพันธุ์เป็นบท D/E",
        })

    allowed = allowed_numbers(brief)
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        if line.startswith("![") or line.startswith("title:") or line.startswith("excerpt:"):
            continue      # ชื่อไฟล์ภาพเป็น ค.ศ. โดยสเปก · หัวไฟล์ยกเลขมาจากเนื้อบทอยู่แล้ว
        for token in _NUMBER.findall(line):
            token = token.rstrip(".,")
            if token and token not in allowed:
                findings.append({
                    "rule": "number_not_in_brief", "severity": "fatal", "line": line_number,
                    "message": f"เลข '{token}' ไม่อยู่ในทะเบียนของ brief — "
                               "บทเช้าพูดได้เฉพาะเลขที่คำนวณจริง",
                })

    fatal = [item for item in findings if item.get("severity") == "fatal"]
    return {"ok": not fatal, "findings": findings,
            "style": brief["style"], "style_name": STYLE_NAMES[brief["style"]]}
