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
from tools import image_output, wcb_source, wcb_writers  # noqa: E402
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

# ------------------------------------------- ชื่อหัวข้อตามใบตัวอย่าง (ผู้ใช้สั่ง 08-11)
#
# 🔄 **กลับด้านจากโครงเดิมทั้งใบ** — บทเช้าเคย "ไม่มีหัวข้อย่อยเลย" โดยตั้งใจ
# (นั่นคือสิ่งที่ทำให้มันเป็นบทเช้า) และด่านมีกฎ `subheading_forbidden` บังคับไว้
# · ใบตัวอย่าง F/G ที่ผู้ใช้ส่งมา 2026-08-11 **มีหัวข้อครบสี่หัวและหัวข้อย่อยสองอัน**
# ⇒ กฎเดิมถูกกลับด้านเป็น `required_headings` (ยังปิดตาย: ขาดหัวไหนก็ตก)
#
# ⚠️ ตัวแยก F/G **ไม่ได้อยู่ที่จำนวนหัวข้ออีกแล้ว** แต่อยู่ที่ *ชนิดของแผน*:
#   F = เทรดในกรอบ (ซื้อที่แนวรับ / ขายที่แนวต้าน) — สองฝั่งแต่ไม่ผูกกับเหตุการณ์
#   G = ฉากทัศน์ผูกผลของเหตุการณ์ ("เพราะหาก… แต่หาก…")
# ด่าน `dual_scenario_missing` / `single_condition_required` ยังใช้วลี "แต่หาก"
# เป็นตัวชี้ขาดเหมือนเดิม ⇒ **ห้ามเขียน "แต่หาก" ลงบท F เด็ดขาด**
#
# **เก็บชื่อล้วน ไม่มีเลขลำดับ** (ยกเว้นกล่อง 📌 ที่ใบตัวอย่างไม่ใส่เลข) — เลขเกิดตอน
# ประกอบบทด้วย `wcb_writers.SectionNumbers` เพราะหัวข้อปฏิทินหายได้ทั้งหัว
# ⇒ ฝังเลขตายตัวเมื่อไหร่ รอบที่ไม่มีปฏิทินจะได้บทที่เลขข้าม (1 · 3 · 4)
RULE = ("---", "")
H2_BOX = "## 📌 สรุปกรอบการเทรดประจำวัน"
H2_CALENDAR = "ปัจจัยเศรษฐกิจที่ต้องจับตา (Economic Events)"
H2_PLAN = {
    brief_story.STYLE_F: "แผนการเทรดและแนวทางการเล่นในกรอบ (Trading Plan)",
    brief_story.STYLE_G: "แผนการเทรดและฉากทัศน์ราคา (Trading Plan & Scenarios)",
}
H3_UP = {
    brief_story.STYLE_F: "### 🟢 ฝั่งสะสมแรงซื้อ (Buy at Support)",
    brief_story.STYLE_G: "### 🟢 ฉากทัศน์ฝั่งขึ้น (Bullish Case)",
}
H3_DOWN = {
    brief_story.STYLE_F: "### 🔴 ฝั่งขายตามกรอบ (Sell at Resistance)",
    brief_story.STYLE_G: "### 🔴 ฉากทัศน์ฝั่งลง (Bearish Case)",
}
H2_SUMMARY = "สรุปคำแนะนำประจำวัน"


def money_for(brief: dict):
    places = wcb_source.profile_for(brief["asset"])["decimals"]
    return lambda value: price_text(value, places)


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
    kind = IMAGE_KIND[brief["style"]]
    return (f"{brief['asset']}-brief-{kind}-{tf_words(brief)['slug']}-"
            f"{brief['current']['date']}{image_output.IMAGE_SUFFIX}")


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
        gap = (close - brief["support"]) / brief["support"] * 100
        return (f"{bar_word}ล่าสุดของ{profile['thai_name']} ({date_text}) ปิดที่ "
                f"{money(close)} {profile['unit_phrase']} ยังยืนเหนือแนวรับสำคัญที่ "
                f"{money(brief['support'])} {profile['unit_phrase']} อยู่ "
                f"{percent(gap)} เปอร์เซ็นต์ แต่ยังไม่มีปัจจัยใหม่ที่ผลักให้หลุดกรอบไปทางใดทางหนึ่ง "
                f"จังหวะแบบนี้เป็นภาพปกติของช่วงก่อนตัวเลขใหญ่ ตลาดชะลอการตัดสินใจเพื่อรอ"
                f"{brief['event']['title']} ซึ่งเป็นตัวกำหนดทิศทางระยะสั้นมากกว่าการแกว่งตัวในช่วงนี้")

    width = (box["high"] - box["low"]) / box["low"] * 100
    position = (close - box["low"]) / (box["high"] - box["low"]) * 100
    return (f"{bar_word}ล่าสุดของ{profile['thai_name']} ({date_text}) ปิดที่ "
            f"{money(close)} {profile['unit_phrase']} อยู่ใน{BIAS_IN_TEXT[box['bias']]}ที่กินช่วง "
            f"{money(box['low'])} ถึง {money(box['high'])} {profile['unit_phrase']} "
            f"ตลอด {box['bars']} แท่งหลังสุด กรอบนี้กว้าง {percent(width)} เปอร์เซ็นต์ "
            f"และราคาล่าสุดยืนอยู่ที่ {percent(position)} เปอร์เซ็นต์ของความสูงกรอบ "
            f"ยังไม่มีการปิดแท่งออกนอกกรอบทั้งด้านบนและด้านล่าง ทิศทางจึงยังไม่ถูกเลือก")


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
    sentences = brief.get("calendar_sentences") or []
    if not sentences:
        return None
    profile = wcb_source.profile_for(brief["asset"])
    if brief["style"] == brief_story.STYLE_F:
        lead = (f"ช่วงนี้มีตัวเลขเศรษฐกิจสำคัญของสหรัฐฯ ที่จะส่งผลต่อความผันผวนของ"
                f"ราคา{profile['short_name']}โดยตรง ดังนี้:")
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

    return (f"ในเชิงเทคนิค ราคายัง{BIAS_PHRASE[bias_of(brief)].replace('แกว่งใน', 'เคลื่อนไหวใน')} "
            f"และปิดอยู่{stance}เส้นค่าเฉลี่ย 50 {tf_words(brief)['ma_unit']}ที่ "
            f"**{money(sma50)}** {profile['unit_phrase']} "
            f"โดยมีแนวรับสำคัญที่ **{money(support)}** และแนวต้านที่ **{money(resistance)}** "
            f"{profile['unit_phrase']} "
            "ตราบที่ยังไม่มีการปิดแท่งออกนอกกรอบ ทิศทางระยะสั้นยังไม่ถูกเลือก")


def h2_technical(brief: dict) -> str:
    """ชื่อหัวข้อแรก — F พูด "เทคนิค" · G พูด "ราคา<สินทรัพย์>" ตามใบตัวอย่าง

    ⚠️ ชื่อสินทรัพย์ต้องมาจากทะเบียนเสมอ — บั๊ก `_h1_tail` ที่เคยฮาร์ดโค้ดคำว่า "ทอง"
    ลงบท SOL คือบทเรียนตรงนี้ (พบตอนตรวจใบก่อนส่งหัวหน้า 08-10)
    """
    words = tf_heading_words(brief)
    tail = f"{words['thai']} ({words['code']} Chart Structure)"
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
    unit = wcb_source.profile_for(brief["asset"])["unit_phrase"]
    style = brief["style"]
    bar = tf_words(brief)["bar"]
    support, resistance = money(brief["support"]), money(brief["resistance"])

    if style == brief_story.STYLE_G:
        event = brief["event"]["title"]
        lines = [f"ราคายังพักฐานในกรอบและตลาดชะลอการตัดสินใจเพื่อรอ{event} "
                 "กลยุทธ์ที่ได้เปรียบจึงเป็นการรอตั้งรับเมื่อราคาย่อตัว "
                 "แทนการไล่ราคาบริเวณกลางกรอบครับ", ""]
        lines += [H3_UP[style], "",
                  f"- **เงื่อนไข:** เพราะหาก{event}ออกมาอ่อนกว่าที่ตลาดคาด",
                  f"- **เป้าหมาย:** แรงหนุนจะส่งให้ราคาขึ้นทดสอบแนวต้าน **{resistance}** {unit} "
                  "ซึ่งเป็นด่านแรกที่จะถูกทดสอบทันที", ""]
        lines += [H3_DOWN[style], "",
                  f"- **เงื่อนไข:** แต่หาก{event}ออกมาแข็งแกร่งกว่าคาด",
                  f"- **แนวทางรับมือ:** ราคาอาจถูกกดลงมาทดสอบแนวรับ **{support}** {unit} "
                  f"ให้จับตาว่าจะยังปิด{bar}ยืนเหนือระดับนี้ได้หรือไม่ "
                  "ยืนได้ยังเป็นจุดสะสมฝั่งซื้อที่น่าสนใจ", ""]
        return lines

    lines = [f"เงื่อนไขสำคัญของวันนี้อยู่ที่การยืนเหนือแนวรับ **{support}** {unit} "
             f"หากราคายังไม่ปิด{bar}หลุดกรอบล่าง ตลาดยังมีโอกาสขึ้นไปทดสอบขอบบนที่ "
             f"**{resistance}** ได้ต่อเนื่องครับ", ""]
    lines += [H3_UP[style], "",
              f"- **จุดเข้าเทรด:** รอราคาย่อตัวลงมาใกล้บริเวณแนวรับ **{support}**",
              f"- **เป้าหมายทำกำไร:** ทยอยปิดทำกำไรเมื่อราคาขึ้นเข้าใกล้แนวต้าน **{resistance}**",
              f"- **จุด Stoploss:** เมื่อราคาปิด{bar}ต่ำกว่า **{support}** ชัดเจน", ""]
    lines += [H3_DOWN[style], "",
              f"- **จุดเข้าเทรด:** หาจังหวะเปิดสถานะฝั่งขายเมื่อราคาขึ้นทดสอบแนวต้าน "
              f"**{resistance}** แล้วเกิดสัญญาณกลับตัว",
              f"- **เป้าหมายทำกำไร:** บริเวณแนวรับ **{support}**",
              f"- **จุด Stoploss:** เมื่อราคาปิด{bar}ทะลุผ่าน **{resistance}** ขึ้นไปได้", ""]
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
            f"1. **ไม่แนะนำให้ไล่ราคา:** ควรรอจังหวะย่อตัวเข้าใกล้แนวรับ **{support}** "
            "เพื่อหาจังหวะเข้าเทรดฝั่งซื้อ",
            f"2. **ทยอยทำกำไร:** เมื่อราคาขึ้นเข้าใกล้แนวต้าน **{resistance}** "
            "ควรถอนทุนหรือแบ่งปิดทำกำไรออกมาก่อน",
            f"3. **คุมความเสี่ยงช่วงประกาศข่าว:** บริหารขนาดสัญญา (Lot Size) และตั้งจุด Stoploss "
            f"ทุกครั้ง เนื่องจากตลาดอาจผันผวนสูงในช่วงที่{event}ออกครับ",
            "",
        ]
    return [
        # ⚠️ ใบตัวอย่างเขียนว่า "ราคาบริเวณนี้เป็นจุดกลางกรอบ" ได้ เพราะวันนั้นราคา
        # อยู่กลางกรอบพอดี · **เราเขียนตามไม่ได้** — ย่อหน้าเปิดของบทเดียวกันบอก
        # ตำแหน่งในกรอบเป็นเปอร์เซ็นต์อยู่แล้ว วันที่ราคาอยู่ขอบบน 93% บทจะขัดกันเอง
        # (ด่านเลขจับไม่ได้เพราะทุกเลขมีต้นทางครบ — กับดักเดียวกับ `_forecast_caveat`)
        f"1. **หลีกเลี่ยงการไล่ราคาโดยไม่รอจังหวะ:** ราคาบริเวณ **{close}** ยังอยู่ในกรอบเดิม "
        "การเข้าโดยไม่รอให้ย่อเข้าใกล้แนวรับหรือเด้งเข้าใกล้แนวต้านก่อน "
        "ทำให้อัตราผลตอบแทนต่อความเสี่ยงไม่ได้เปรียบทั้งสองทาง",
        f"2. **จับตาการทะลุกรอบ (Breakout):** หากมีปัจจัยข่าวดันให้ราคาปิด{bar}ทะลุกรอบ "
        f"**{money(box['low'])}–{money(box['high'])}** ฝั่งใดฝั่งหนึ่ง "
        "ให้เปลี่ยนแผนไปเทรดตามทิศทางที่ตลาดเลือก",
        "3. **คุมความเสี่ยงช่วงข่าวออก:** บริหารขนาดสัญญา (Lot Size) และตั้งจุด Stoploss "
        "ทุกครั้งก่อนเข้าออเดอร์ครับ",
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
    lines += [f"# {headline_format.h1(brief['asset'], date_text, _h1_tail(brief))}", "",
              f"*{stamp_line(brief)}*", "",
              *RULE,
              H2_BOX,
              f"* **กลยุทธ์หลัก:** {strategy_phrase(brief)}",
              f"* **แนวต้านสำคัญ:** {money(brief['resistance'])} {profile['unit_phrase']}",
              f"* **แนวรับสำคัญ:** {money(brief['support'])} {profile['unit_phrase']}", "",
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
    day, month, year = brief["current"]["date"].split("-")[::-1]
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
