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
from tools import intraday_bars  # noqa: E402
from tools import image_output, market_calendar, voice_rules, wcb_source, wcb_writers  # noqa: E402
from tools.chart_story_renderer import price_text, thai_date  # noqa: E402

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
#
# 📏 **ขยับจาก 2,600 เป็น 3,400 เมื่อ 2026-08-11 — วัดก่อนขยับ ไม่ได้เดา**
# ใบตัวอย่างที่ผู้ใช้ส่งมามีโครงสี่หัวข้อ ซึ่งยาวกว่าโครงสามย่อหน้าเดิมโดยธรรมชาติ
# วัดเนื้อบทของใบตัวอย่างเองได้ F 2,855 อักขระ · G 2,764 ⇒ **เพดานเดิมตีตกใบตัวอย่าง
# ของหัวหน้าเอง** · ตั้งใหม่ที่ 3,400 = ใบที่ยาวสุด + ระยะเผื่อ ~19% สำหรับรอบที่
# ชื่อสินทรัพย์ยาวกว่าหรือปฏิทินมีหลายรายการ · ยังต่ำกว่าบท D/E (>1,500 อักขระขั้นต่ำ
# แต่ของจริง ~3,500–6,000) ⇒ เพดานยังทำหน้าที่กันการกลายพันธุ์ได้จริง
MAX_CHARS = 3400

BIAS_PHRASE = {
    "sideway": "แกว่งตัวในกรอบแนวนอน",
    "sideway_up": "แกว่งตัวในกรอบที่ค่อย ๆ ยกสูงขึ้น",
    "sideway_down": "แกว่งตัวในกรอบที่ค่อย ๆ ลดต่ำลง",
}
BIAS_IN_TEXT = {
    "sideway": "กรอบแนวนอน",
    "sideway_up": "กรอบที่ค่อย ๆ ยกตัว",
    "sideway_down": "กรอบที่ค่อย ๆ ลาดลง",
}

CALENDAR_SOURCE = "(ที่มา: ปฏิทินเศรษฐกิจ WorldClassBroker)"

_NUMBER = re.compile(r"\d[\d,\.]*")

# ------------------------------------------- ชื่อหัวข้อตามใบตัวอย่าง (ผู้ใช้สั่ง 08-11)
#
# 🔄 **กลับด้านจากโครงเดิมทั้งใบ** — บทเช้าเคย "ไม่มีหัวข้อย่อยเลย" โดยตั้งใจ
# (นั่นคือสิ่งที่ทำให้มันเป็นบทเช้า) และด่านมีกฎ `subheading_forbidden` บังคับไว้
# · ใบตัวอย่าง F/G ที่ผู้ใช้ส่งมา 2026-08-11 **มีหัวข้อครบสี่หัวและหัวข้อย่อยสองอัน**
# ⇒ กฎเดิมถูกกลับด้านเป็น `required_headings` (ยังปิดตาย: ขาดหัวไหนก็ตก)
#
# ⚠️ ตัวแยก F/G **ไม่ได้อยู่ที่จำนวนหัวข้ออีกแล้ว** แต่อยู่ที่ *ชนิดของแผน*:
#   F = เทรดในกรอบ (ซื้อที่แนวรับ / ขายที่แนวต้าน) — สองฝั่งแต่ไม่ผูกกับเหตุการณ์
#   G = เงื่อนไขสองทางหลังเหตุการณ์ โดยต้องรอดูการตอบสนองของตลาดประกอบ
# ด่าน `dual_scenario_missing` / `single_condition_required` ยังใช้วลี "แต่หาก"
# เป็นตัวชี้ขาดเหมือนเดิม ⇒ **ห้ามเขียน "แต่หาก" ลงบท F เด็ดขาด**
#
# **เก็บชื่อล้วน ไม่มีเลขลำดับ** (ยกเว้นกล่อง 📌 ที่ใบตัวอย่างไม่ใส่เลข) — เลขเกิดตอน
# ประกอบบทด้วย `wcb_writers.SectionNumbers` เพราะหัวข้อปฏิทินหายได้ทั้งหัว
# ⇒ ฝังเลขตายตัวเมื่อไหร่ รอบที่ไม่มีปฏิทินจะได้บทที่เลขข้าม (1 · 3 · 4)
RULE = ("---", "")
H2_BOX = "## 📌 สรุปกรอบการเทรดประจำวัน"
H2_CALENDAR = "ปัจจัยเศรษฐกิจที่ต้องจับตา"
H2_PLAN = {
    brief_story.STYLE_F: "แผนตามกรอบราคา",
    brief_story.STYLE_G: "เงื่อนไขที่ต้องจับตาหลังประกาศตัวเลข",
}
H3_UP = {
    brief_story.STYLE_F: "### 🟢 แผนสำรอง: รอ BUY ใกล้แนวรับ",
    brief_story.STYLE_G: "### 🟢 เงื่อนไขที่หนุนราคา",
}
H3_DOWN = {
    brief_story.STYLE_F: "### 🔴 แผนหลัก: รอ SELL ใกล้แนวต้าน",
    brief_story.STYLE_G: "### 🔴 เงื่อนไขที่กดดันราคา",
}
H2_SUMMARY = "สรุปคำแนะนำประจำวัน"


def money_for(brief: dict):
    places = wcb_source.profile_for(brief["asset"])["decimals"]
    return lambda value: price_text(value, places)


def unit_for(brief: dict) -> str:
    """หน่วยที่อ่านลื่นในบท — รายละเอียด CFD ระบุครั้งเดียว ไม่ต่อท้ายทุกตัวเลข"""
    profile = wcb_source.profile_for(brief["asset"])
    return profile["unit_short"] if brief["asset"] == "nvda" else profile["unit_phrase"]


def percent(value: float) -> str:
    return f"{value:.2f}"


def timeframe_of(brief: dict) -> str | None:
    return brief.get("timeframe")


def tf_words(brief: dict) -> dict:
    """คำเรียกกรอบเวลาที่บทกับภาพใช้ร่วมกัน — จุดเดียวที่แปลรหัสกรอบเป็นภาษาไทย

    แท่งรายวันคือเส้นทางเดิม (ไม่มี `timeframe`) · intraday อ่านจากทะเบียนของ
    `intraday_bars` เพื่อไม่ให้มีคำเรียกสองชุดในระบบ
    """
    timeframe = timeframe_of(brief)
    if timeframe is None:
        return {"bar": "แท่งรายวัน", "ma_unit": "วัน", "slug": "d1", "front": "Daily"}
    spec = intraday_bars.spec_for(timeframe)
    return {"bar": f"แท่ง{spec['thai']}", "ma_unit": spec["ma_unit"],
            "slug": timeframe, "front": timeframe.upper()}


def tf_heading_words(brief: dict) -> dict:
    """คำเรียกกรอบเวลาที่ **ชื่อหัวข้อ** ใช้ — ต่อยอดจาก `tf_words` ไม่ได้ตั้งชุดใหม่

    ใบตัวอย่างเขียนหัวข้อแรกว่า "ภาพรวมเทคนิครายชั่วโมง (1H Chart Structure)"
    ⇒ ต้องการสองรูป: คำไทยแบบไม่มี "แท่ง" นำหน้า และรหัสกรอบตัวใหญ่สำหรับวงเล็บอังกฤษ
    · แท่งรายวันไม่มีรหัส `timeframe` ⇒ ใช้ `D1` ซึ่งเป็นคำที่สายกราฟใช้อยู่แล้ว
    """
    words = tf_words(brief)
    return {"thai": words["bar"].replace("แท่ง", "", 1),
            "code": "D1" if timeframe_of(brief) is None else words["front"]}


def image_name(brief: dict) -> str:
    """ชื่อไฟล์ภาพประกอบใบเดียวของบทเช้า — มีความหมาย + กรอบเวลา + วันที่

    **กรอบเวลาต้องอยู่ในชื่อไฟล์** ไม่งั้นใบ 1h กับใบรายวันของวันเดียวกันชื่อชนกัน
    แล้วทับกันเงียบ ๆ (บทเรียนเดียวกับที่เว็บตั้งชื่อบทจากสินทรัพย์+วันที่)
    """
    if brief["style"] == brief_story.STYLE_F:
        stem = f"range-{tf_words(brief)['slug']}-trade-plan"
    else:
        stem = f"{IMAGE_KIND[brief['style']]}-{tf_words(brief)['slug']}"
    return (f"{brief['asset']}-brief-{stem}-{brief['current']['date']}"
            f"{image_output.IMAGE_SUFFIX}")


def folder_for(brief: dict) -> str:
    return FOLDERS[brief["style"]]


def strategy_phrase(brief: dict) -> str:
    """บรรทัด `กลยุทธ์ :` — ตัวแยก F/G ที่คนอ่านเห็นก่อนอย่างอื่น

    F พูดสภาพตลาด · G พูดชื่อเหตุการณ์ที่รออยู่ (ตามสเปกข้อ 2.2/3.2)
    """
    if brief["style"] == brief_story.STYLE_G:
        return f"จับตา{brief['event']['title']}"
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
    return (f"{short_name}แกว่งกรอบ {money(brief['support'])}"
            f"–{money(brief['resistance'])}")


def _excerpt_clauses(brief: dict) -> list[str]:
    money = money_for(brief)
    profile = wcb_source.profile_for(brief["asset"])
    clauses = [f"{profile['short_name']}ปิดที่ {money(brief['current']['close'])} ดอลลาร์",
               f"แนวรับ {money(brief['support'])}",
               f"แนวต้าน {money(brief['resistance'])}"]
    if brief["style"] == brief_story.STYLE_G:
        clauses.append(f"อ่านแผนสั้นก่อน{brief['event']['title']} พร้อมเงื่อนไขสองทาง")
    else:
        clauses.append("อ่านกรอบราคาวันนี้พร้อมแผนซื้อขายในกรอบแบบสั้น")
    clauses.append("ทุกระดับคำนวณจากแท่งราคาจริง")
    return clauses


def frontmatter_lines(brief: dict) -> list[str]:
    title = headline_format.title(brief["asset"], brief["publication_date"])
    return [
        "---",
        f"asset: {brief['asset']}",
        f"title: {wcb_writers.fit_title(title)}",
        f"excerpt: {wcb_writers.fit_excerpt(_excerpt_clauses(brief))}",
        f"author_slug: {wcb_writers.author_slug_for(brief['asset'])}",
        f"timeframe: {tf_words(brief)['front']}",
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

    bar_word = tf_words(brief)["bar"]
    if brief["style"] == brief_story.STYLE_G:
        return (f"{bar_word}ล่าสุดของ{profile['thai_name']} ({date_text}) ปิดที่ "
                f"{money(close)} {unit_for(brief)} และยังเคลื่อนไหวระหว่างแนวรับ "
                f"{money(brief['support'])} กับแนวต้าน {money(brief['resistance'])} "
                f"{unit_for(brief)} ก่อนการประกาศ{brief['event']['title']} "
                "ตัวเลขดังกล่าวอาจเพิ่มความผันผวน แต่ทิศทางราคายังต้องดูการตอบสนอง"
                "ของตลาดหลังประกาศ")

    position = (close - box["low"]) / (box["high"] - box["low"]) * 100
    if position >= 70:
        location = "ขึ้นมาอยู่ใกล้ขอบบนของกรอบ"
    elif position <= 30:
        location = "ลงมาอยู่ใกล้ขอบล่างของกรอบ"
    else:
        location = "ยังเคลื่อนไหวอยู่ช่วงกลางกรอบ"
    instrument = (" โดยเป็นราคาอ้างอิงของสัญญา CFD" if brief["asset"] == "nvda" else "")
    return (f"{bar_word}ล่าสุดของ{profile['thai_name']} ({date_text}) ปิดที่ "
            f"{money(close)} {unit_for(brief)}{instrument} ราคา{location}ระหว่าง "
            f"{money(brief['support'])} ถึง {money(brief['resistance'])} {unit_for(brief)} "
            "แต่ยังไม่ปิดออกนอกกรอบ จึงต้องรอดูว่าราคาจะตอบสนองต่อขอบด้านใดก่อน")


def _factor_lines(brief: dict) -> list[str] | None:
    """หัวข้อ 2 — พูดจากปฏิทินเท่านั้น · ไม่มีปฏิทิน = คืน None แล้วบทไม่มีหัวข้อนี้

    🔄 08-11 บ่าย (ผู้ใช้สั่ง): เปลี่ยนจากร้อยแก้วเป็น **bullet จัดกลุ่มตามวัน**
    ตามใบตัวอย่าง F/G (`* **วัน**` → `* **HH:MM น.** รายการ`) — ใช้ตัวหั่นตัวเดียว
    กับ A/B/C (`wcb_writers.calendar_day_groups`) ไม่เขียนประโยคชุดใหม่ ·
    จับคู่ประโยคกับรายการไม่ได้ (เช่น brief เก่าไม่มี `calendar_events`) =
    **ถอยไปร้อยแก้วแบบเดิมทั้งชุด** ไม่ใช่เดา

    🔄 08-11: วลีที่มาอยู่เป็นบรรทัดปิดท้ายบทตามใบตัวอย่าง
    — **ด่าน `calendar_source_missing` ยังบังคับให้มีเหมือนเดิม** เปลี่ยนแค่ที่วาง
    """
    sentences = []
    for raw in (brief.get("calendar_sentences") or []):
        sentence = re.sub(r"\s*\([A-Za-z][^)]*\)", "", raw)
        sentence = sentence.replace(" ซึ่งจัดเป็นรายการผลกระทบสูง", " ซึ่งมีความสำคัญสูง")
        sentence = sentence.replace(
            " โดยรายการนี้ไม่มีตัวเลขครั้งก่อนหรือค่าคาดที่อ้างอิงได้ในระบบ จึงระบุได้แค่วันและเวลา",
            " โดยขณะจัดทำบทวิเคราะห์ยังไม่มีตัวเลขครั้งก่อนและค่าคาดการณ์")
        sentence = sentence.replace(
            " โดยยังไม่มีค่าอ้างอิงในระบบ จึงระบุได้แค่วันและเวลา",
            " โดยขณะจัดทำบทวิเคราะห์ยังไม่มีค่าอ้างอิง")
        sentences.append(sentence)
    if not sentences:
        return None
    profile = wcb_source.profile_for(brief["asset"])
    if brief["style"] == brief_story.STYLE_F:
        lead = (f"รายการเศรษฐกิจสหรัฐฯ ที่อาจเพิ่มความผันผวนให้ราคา"
                f"{profile['short_name']}ในช่วงนี้ มีดังนี้:")
        prose_lead = "รายการที่ตลาดจับตาในช่วงนี้เรียงตามเวลาคือ "
    else:
        lead = "นอกจากตัวเลขที่รออยู่ ปฏิทินช่วงนี้ยังมีรายการสำคัญของสหรัฐฯ เรียงตามเวลา ดังนี้:"
        prose_lead = "นอกจากตัวเลขที่รออยู่ ปฏิทินช่วงนี้ยังมีรายการอื่นเรียงตามเวลาคือ "
    groups = wcb_writers.calendar_day_groups(sentences,
                                             brief.get("calendar_events") or [])
    if groups is None:
        return [prose_lead + " ถัดมาคือ ".join(sentences)]
    return [lead, ""] + wcb_writers.nested_listing(groups)


def _technical_paragraph(brief: dict) -> str:
    """ย่อหน้าอ่านเทคนิคของหัวข้อ 1 — **อ่านค่าอย่างเดียว ไม่มีกลยุทธ์**

    🔄 08-11: เดิมย่อหน้านี้ปิดท้ายด้วยกลยุทธ์/ฉากทัศน์ด้วย เพราะบทเช้าไม่มีหัวข้อ
    จึงต้องยัดทุกอย่างไว้ในสามย่อหน้า · ใบตัวอย่างแยกแผนออกเป็นหัวข้อ 3 ของตัวเอง
    ⇒ ที่นี่เหลือเฉพาะ "ราคาอยู่ตรงไหนเทียบอะไร" ส่วน "แล้วยังไงต่อ" ย้ายไป `_plan_lines`
    """
    money = money_for(brief)
    profile = wcb_source.profile_for(brief["asset"])
    support, resistance = brief["support"], brief["resistance"]
    sma50 = brief["sma50_last"]
    close = brief["current"]["close"]
    stance = "เหนือ" if close >= sma50 else "ใต้"

    if brief["style"] == brief_story.STYLE_F:
        return (f"ราคาปิดอยู่{stance}เส้นค่าเฉลี่ย 50 {tf_words(brief)['ma_unit']}ที่ "
                f"**{money(sma50)}** {unit_for(brief)} ขณะที่แนวรับอยู่บริเวณ "
                f"**{money(support)}** และแนวต้านอยู่บริเวณ **{money(resistance)}** "
                f"{unit_for(brief)} ตราบใดที่ราคายังปิดอยู่ระหว่างสองระดับนี้ "
                "ภาพระยะสั้นยังเป็นการแกว่งตัวในกรอบ")
    return (f"ราคายัง{BIAS_PHRASE[bias_of(brief)]} และปิดอยู่{stance}เส้นค่าเฉลี่ย 50 "
            f"{tf_words(brief)['ma_unit']}ที่ **{money(sma50)}** {unit_for(brief)} "
            f"แนวรับอยู่ที่ **{money(support)}** ส่วนแนวต้านอยู่ที่ "
            f"**{money(resistance)}** {unit_for(brief)} สองระดับนี้ใช้ดูว่าตลาด"
            "เลือกทิศทางใดหลังตัวเลขออก")


def h2_technical(brief: dict) -> str:
    """ชื่อหัวข้อแรก — F พูด "เทคนิค" · G พูด "ราคา<สินทรัพย์>" ตามใบตัวอย่าง

    ⚠️ ชื่อสินทรัพย์ต้องมาจากทะเบียนเสมอ — บั๊ก `_h1_tail` ที่เคยฮาร์ดโค้ดคำว่า "ทอง"
    ลงบท SOL คือบทเรียนตรงนี้ (พบตอนตรวจใบก่อนส่งหัวหน้า 08-10)
    """
    words = tf_heading_words(brief)
    tail = words["thai"]
    if brief["style"] == brief_story.STYLE_G:
        return f"ภาพรวมราคา{wcb_source.profile_for(brief['asset'])['short_name']}{tail}"
    return f"ภาพรวมเทคนิค{tail}"


def _plan_lines(brief: dict) -> list[str]:
    """หัวข้อ 3 — สองฝั่งใต้หัวข้อย่อยตามใบตัวอย่าง

    ⚠️ **F กับ G เล่าคนละชนิดของแผน ไม่ใช่คนละถ้อยคำของแผนเดียวกัน**
    F เป็นแผนกลไกในกรอบ (ซื้อขอบล่าง ขายขอบบน) ซึ่งใช้ได้โดยไม่ต้องรู้ว่าจะมีข่าวอะไร
    G ผูกทั้งสองฝั่งเข้ากับ *ผลของเหตุการณ์* ที่ระบุชื่อไว้ ⇒ ถ้าวันไหนสองอันนี้
    เขียนเหมือนกัน แปลว่าสไตล์หนึ่งกลายพันธุ์ ไม่ใช่ว่าเราประหยัดโค้ดได้

    ⛔ ห้ามใส่วลี "แต่หาก" ในกิ่ง F — ด่าน `single_condition_required` ใช้วลีนั้น
    เป็นตัวชี้ว่าบทเขียนผิดพันธุ์ (ดูคอมเมนต์ทะเบียนหัวข้อด้านบน)
    """
    money = money_for(brief)
    unit = unit_for(brief)
    style = brief["style"]
    bar = tf_words(brief)["bar"]
    support, resistance = money(brief["support"]), money(brief["resistance"])

    if style == brief_story.STYLE_G:
        event = brief["event"]["title"]
        lines = [f"ก่อน{event} ราคายังไม่ปิดออกจากกรอบ จึงควรรอทั้งผลประกาศ "
                 f"การตอบสนองของบอนด์ยีลด์และดอลลาร์ รวมถึงการปิด{bar}ยืนยันก่อนครับ", ""]
        lines += [H3_UP[style], "",
                  f"- **เงื่อนไข:** หากผล{event} ออกมาอ่อนกว่าที่ตลาดคาด",
                  "- **สิ่งที่ต้องเกิดร่วมกัน:** บอนด์ยีลด์หรือดอลลาร์อ่อนลง และราคามีแรงซื้อรองรับ",
                  f"- **ระดับยืนยัน:** จับตาการปิด{bar}เหนือแนวต้าน **{resistance}** {unit}", ""]
        lines += [H3_DOWN[style], "",
                  f"- **เงื่อนไข:** แต่หากผล{event} ออกมาแข็งแกร่งกว่าคาด",
                  "- **สิ่งที่ต้องเกิดร่วมกัน:** บอนด์ยีลด์หรือดอลลาร์แข็งขึ้น และแรงขายเพิ่มขึ้น",
                  f"- **ระดับที่ต้องรักษา:** แนวรับ **{support}** {unit} หากราคาปิด{bar}"
                  "ต่ำกว่าระดับนี้ ภาพระยะสั้นจะอ่อนลง", ""]
        return lines

    box = brief["range_box"]
    plan = brief["trade_plan"]
    close = brief["current"]["close"]
    position = (close - box["low"]) / (box["high"] - box["low"])
    if position >= 0.70:
        lead = (f"ราคาล่าสุดอยู่ใกล้แนวต้าน **{resistance}** {unit} จึงไม่ควรไล่ราคา "
                "ควรรอดูแรงขายบริเวณขอบบนหรือรอให้ราคาปิดผ่านแนวต้านก่อน")
    elif position <= 0.30:
        lead = (f"ราคาล่าสุดอยู่ใกล้แนวรับ **{support}** {unit} จุดสำคัญคือการตอบสนอง"
                "บริเวณขอบล่าง หากยังยืนได้จึงค่อยประเมินโอกาสกลับเข้าหากลางกรอบ")
    else:
        lead = ("ราคายังอยู่ช่วงกลางกรอบ จังหวะได้เปรียบจึงอยู่ที่การรอให้ราคาเข้าใกล้"
                "แนวรับหรือแนวต้านก่อนตัดสินใจ")
    sell = {key: money(value) for key, value in plan["sell"].items()}
    buy = {key: money(value) for key, value in plan["buy"].items()}
    lines = [lead, "",
             "### 🔴 แผนหลัก: รอ SELL ใกล้แนวต้าน", "",
             f"- **จุดเปิดขาย(Open):** **{sell['open']}** เมื่อราคาขึ้นทดสอบแล้ว"
             "ไม่สามารถผ่านแนวต้านได้",
             f"- **จุดปิดทำกำไร(TP):** **{sell['tp']}**",
             f"- **จุดหยุดขาดทุน(SL):** **{sell['sl']}**", "",
             "### 🟢 แผนสำรอง: รอ BUY ใกล้แนวรับ", "",
             f"- **จุดเปิดซื้อ(Open):** **{buy['open']}** เมื่อราคาหยุดลงและเริ่มกลับขึ้น",
             f"- **จุดปิดทำกำไร(TP):** **{buy['tp']}**",
             f"- **จุดหยุดขาดทุน(SL):** **{buy['sl']}**", ""]
    return lines


def _recommendation_lines(brief: dict) -> list[str]:
    """หัวข้อ 4 — รายการคำแนะนำสามข้อตามใบตัวอย่าง

    ทุกเลขที่อ้างถึงเป็นค่าเดิมจาก brief (ราคาปิด · แนวรับ · แนวต้าน · ขอบกรอบ)
    **ไม่มีเลขใหม่** — หัวข้อนี้เป็นการย้ำสิ่งที่บทพูดไปแล้ว ไม่ใช่ที่เพิ่มข้อมูล
    """
    money = money_for(brief)
    box = brief["range_box"]
    close = money(brief["current"]["close"])
    support, resistance = money(brief["support"]), money(brief["resistance"])
    bar = tf_words(brief)["bar"]

    if brief["style"] == brief_story.STYLE_G:
        event = brief["event"]["title"]
        return [
            f"1. **รอผลและแท่งยืนยัน:** {event} อาจทำให้ราคาแกว่งแรงในช่วงแรก "
            f"จึงควรรอการปิด{bar}ก่อนประเมินทิศทาง",
            f"2. **ฝั่งบน:** การปิดเหนือ **{resistance}** จะทำให้ภาพระยะสั้นดีขึ้น",
            f"3. **ฝั่งล่าง:** การปิดต่ำกว่า **{support}** จะทำให้แรงขายกลับมาได้เปรียบครับ",
            "",
        ]
    plan = brief["trade_plan"]
    sell = {key: money(value) for key, value in plan["sell"].items()}
    buy = {key: money(value) for key, value in plan["buy"].items()}
    return [
        f"{wcb_source.profile_for(brief['asset'])['symbol']} ปิดที่ **{close}** และกำลัง"
        f"เข้าใกล้แนวต้าน **{resistance}** แผนแรกจึงเป็นการรอ SELL บริเวณแนวต้าน "
        f"โดยตั้ง TP ที่ **{sell['tp']}** และ SL ที่ **{sell['sl']}**",
        "",
        f"หากราคาไม่ขึ้นถึงแนวต้านและกลับลงมาที่ **{support}** ให้เปลี่ยนมารอดูแผน "
        f"BUY โดยตั้ง TP ที่ **{buy['tp']}** และ SL ที่ **{buy['sl']}**",
        "",
    ]


def bar_clock(brief: dict) -> str | None:
    """เวลาเริ่มแท่งฐานในรูปที่คนอ่านคุ้น — `19.00` แบบต้นแบบ ไม่ใช่ `19:00`

    ต้นแบบใช้จุดคั่นชั่วโมงกับนาที (`09.42 น.`) เราลอกจุดนี้เพราะเป็นธรรมเนียมไทย
    และไม่ชนกับกฎใดในระบบ · แท่งรายวันไม่มีเวลา ⇒ คืน None แล้วบรรทัดนี้พูดแค่วัน
    """
    at = brief["current"].get("at")
    return at[11:16].replace(":", ".") if at else None


def stamp_line(brief: dict) -> str:
    """บรรทัดบอกฐานข้อมูลของบท — ต้องบอก**กรอบเวลา**เสมอ

    เหตุผล: ภาพของ F/G เป็นการ์ดที่หน้าตาเหมือนกันทุกกรอบเวลา ถ้าบทไม่บอกว่าอ่านจาก
    แท่งอะไร คนอ่านจะเดาเอง และเดาผิดได้ (ต้นแบบเป็นราย 1 ชั่วโมง — ของเราเคยเป็น
    รายวัน) · เขียนกำกับทั้งในบทและบนแถบท้ายการ์ด
    """
    words = tf_words(brief)
    clock = bar_clock(brief)
    tail = f" เวลา {clock} น. (เวลาไทย)" if clock else ""
    return f"ข้อมูล ณ {words['bar']}ที่ปิดแล้วของ {thai_date(brief['current']['date'])}{tail}"


def render_article(brief: dict) -> str:
    """ประกอบบทเช้าใบเดียว — ลำดับบล็อกตายตัวตามสเปกข้อ 1"""
    money = money_for(brief)
    profile = wcb_source.profile_for(brief["asset"])
    date_text = brief["current"]["date"]
    publish_date = brief["publication_date"]
    picture = image_name(brief)
    words = tf_words(brief)
    alt_parts = [f"{profile['thai_name']} {words['bar']} {thai_date(date_text)}",
                 f"แนวรับ {money(brief['support'])}",
                 f"แนวต้าน {money(brief['resistance'])}"]
    for label in alt_parts:
        findings = consistency_gate.check_labels([label])
        if findings:
            raise ValueError(f"ข้อความ alt ไม่ผ่านด่านความสอดคล้อง: {findings[0]['message']}")

    heads = wcb_writers.SectionNumbers()
    lines = frontmatter_lines(brief)
    lines += [f"# {headline_format.h1(brief['asset'], publish_date, _h1_tail(brief))}", "",
              f"*{stamp_line(brief)}*", "",
              *RULE,
              H2_BOX,
              f"* **กลยุทธ์หลัก:** {strategy_phrase(brief)}",
              f"* **แนวต้านสำคัญ:** {money(brief['resistance'])} {unit_for(brief)}",
              f"* **แนวรับสำคัญ:** {money(brief['support'])} {unit_for(brief)}", "",
              *RULE,
              heads.head(h2_technical(brief)), "",
              _opening_paragraph(brief), "",
              _technical_paragraph(brief), "",
              f"![{' · '.join(alt_parts)}]({picture})", ""]
    factors = _factor_lines(brief)
    if factors:
        # โหมด bullet ปิดท้ายด้วยบรรทัดว่างมาแล้ว (จาก nested_listing) — เติมเฉพาะ
        # ทางร้อยแก้วที่ยังไม่มี เพื่อไม่ให้มีบรรทัดว่างซ้อนสองบรรทัด
        lines += [*RULE, heads.head(H2_CALENDAR), "", *factors]
        if lines[-1] != "":
            lines.append("")
    lines += [*RULE, heads.head(H2_PLAN[brief["style"]]), ""]
    lines += _plan_lines(brief)
    lines += [*RULE, heads.head(H2_SUMMARY), ""]
    lines += _recommendation_lines(brief)
    if factors:
        # วลีที่มาปิดท้ายบทเหมือนใบตัวอย่าง — ตัวเดียวกับที่ด่าน `calendar_source_missing`
        # มองหา ⇒ ย้ายที่ได้ แต่หายไม่ได้
        lines += [*RULE, f"*{CALENDAR_SOURCE}*"]
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
              str(box["bars"]), "50",
              # เลขลำดับหัวข้อ (## 1.–## 4.) และเลขข้อของรายการคำแนะนำ (1.–3.)
              # เป็นเลขนับในเอกสาร ไม่ใช่ค่าที่วัดจากตลาด — เพิ่มพร้อมโครงใหม่ 08-11
              "1", "2", "3", "4"}
    for side in (brief.get("trade_plan") or {}).values():
        if isinstance(side, dict):
            values |= {money(value) for value in side.values()
                       if isinstance(value, (int, float))}
    clock = bar_clock(brief)
    if clock:
        values |= {clock, clock.split(".")[0], clock.split(".")[1]}
    # เลขที่ติดมากับ**ชื่อกรอบเวลา**เอง ("ราย 1 ชั่วโมง" · "timeframe: 1H")
    # ไม่ใช่ค่าที่วัดจากตลาด แต่ด่านมองเป็นเลขเหมือนกัน ⇒ ต้องขึ้นทะเบียนให้ครบ
    words = tf_words(brief)
    for text in (words["bar"], words["front"], words["ma_unit"]):
        values |= {token.rstrip(".,") for token in _NUMBER.findall(text)}
    width = (box["high"] - box["low"]) / box["low"] * 100
    position = (close - box["low"]) / (box["high"] - box["low"]) * 100
    values |= {percent(width), percent(position)}
    if brief["support"]:
        values.add(percent((close - brief["support"]) / brief["support"] * 100))
    # วันที่ในพาดหัว/บรรทัดวัน + ปีในชื่อไฟล์ภาพ — ค.ศ. ระบบเดียวทั้งบทและชื่อไฟล์
    for date_value in (brief["current"]["date"], brief["publication_date"]):
        day, month, year = date_value.split("-")[::-1]
        values |= {str(int(day)), str(int(month)), year}
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

    # ด่านแท่งปิด — คนละเส้นทางตามกรอบเวลา แต่หลักเดียวกัน: พิสูจน์ใหม่จากศูนย์
    # ไม่อ่านค่าธง · intraday ใช้ `intraday_bars` เพราะปฏิทินตลาดรายวันตอบแท่งชั่วโมงไม่ได้
    if timeframe_of(brief) is None:
        closed_detail = candle_close.verify(
            brief.get("candle_basis"), asset=brief["asset"],
            session_date=brief["current"]["date"])
    else:
        closed_detail = intraday_bars.verify(
            brief.get("candle_basis"), asset=brief["asset"],
            bar_at=brief["current"].get("at"))
    if closed_detail:
        findings.append({
            "rule": "closed_candle_required", "severity": "fatal", "line": 1,
            "message": f"บทเรียกแท่งล่าสุดว่า 'ปิด' แต่ {closed_detail}",
        })

    # 🔄 **กลับด้าน 2026-08-11 ตามใบตัวอย่างที่ผู้ใช้ส่งมา**
    # เดิมกฎนี้ชื่อ `subheading_forbidden` และ **ห้าม `## ` ทุกบรรทัด** เพราะต้นแบบ
    # InterGold ที่ใช้ตอน 08-10 ไม่มีหัวข้อเลย · ใบตัวอย่างชุดใหม่มีครบสี่หัว
    # ⇒ กลับเป็นทะเบียนหัวข้อบังคับ ซึ่งยังปิดตายเท่าเดิม: ขาดหัวไหนก็ตกทั้งใบ
    # (หัวข้อ 2 ปฏิทินไม่บังคับ เพราะไม่มีปฏิทิน = ตัดหัวข้อนั้นทิ้งเงียบตามกติกาแกน)
    required = [H2_BOX, h2_technical(brief), H2_PLAN[brief["style"]], H2_SUMMARY,
                H3_UP[brief["style"]], H3_DOWN[brief["style"]]]
    for head in required:
        if head not in markdown:
            findings.append({
                "rule": "heading_missing", "severity": "fatal", "line": 1,
                "message": f"บทเช้าขาดหัวข้อ '{head.strip()}' — โครงตามใบตัวอย่างบังคับให้มี",
            })
    if brief.get("calendar_sentences") and H2_CALENDAR not in markdown:
        findings.append({
            "rule": "heading_missing", "severity": "fatal", "line": 1,
            "message": f"มีรายการปฏิทินแต่ไม่มีหัวข้อ '{H2_CALENDAR.strip()}'",
        })

    if "|" in markdown:
        findings.append({
            "rule": "table_forbidden", "severity": "fatal", "line": 1,
            "message": "พบอักขระตาราง '|' — บทสาธารณะห้ามตาราง",
        })

    # volume มีจริงเฉพาะหุ้น (ใบแจ้งหัวหน้า 2026-08-13) — F/G เป็นบททอง/คู่เงิน
    # ซึ่งปลายทางส่ง volume เป็น null ทุกแท่ง จึงไม่มีตัวเลขจริงให้อ้าง
    if market_calendar.for_asset(brief["asset"]).asset_class \
            not in voice_rules.VOLUME_ALLOWED_INSTRUMENT_TYPES:
        for line_number, line in enumerate(markdown.splitlines(), start=1):
            volume_term = voice_rules.volume_term_in(line)
            if volume_term:
                findings.append({
                    "rule": "volume_forbidden", "severity": "fatal", "line": line_number,
                    "message": f"พบคำตระกูล volume \"{volume_term}\" ในบทของ "
                               f"{brief['asset']} — ข้อมูล volume มีจริงเฉพาะหุ้น "
                               "ตลาด OTC ไม่มีตัวเลขให้อ้าง",
                })

    # กล่องสรุปหัวบท — ใบตัวอย่างเปลี่ยนจากสามบรรทัด `กลยุทธ์ : …` เป็น bullet ตัวหนา
    # ใต้หัวข้อ 📌 · **ยังบังคับครบสามบรรทัดเหมือนเดิม** เปลี่ยนแค่รูป
    for label in ("* **กลยุทธ์หลัก:**", "* **แนวต้านสำคัญ:**", "* **แนวรับสำคัญ:**"):
        if label not in markdown:
            findings.append({
                "rule": "strategy_box_incomplete", "severity": "fatal", "line": 1,
                "message": f"กล่องหัวบทขาดบรรทัด '{label}' — สไตล์ F/G บังคับครบสามบรรทัด",
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
