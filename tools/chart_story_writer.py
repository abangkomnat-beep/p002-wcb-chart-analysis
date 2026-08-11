"""นักเขียนสไตล์ D — บทวิเคราะห์อ่านโครงสร้างกราฟ + ด่านตรวจของสไตล์นี้เอง

สำนวนตามบทอ้างอิงที่หัวหน้าเลือก (th.investing.com/analysis/article-200458003):
เน้นบรรยาย + ศัพท์เทคนิคสาย SMC/Price Action หนาแน่น (Market Structure, Demand
Zone, Deep Discount, Smart Money, CHoCH, Stop Hunt, BOS, Dynamic Resistance,
Timeframe ย่อย) · จัดเรียงอ่านง่าย: ย่อหน้าสั้น หัวข้อย่อยตัวหนา bullet นำด้วยชื่อโซน

เส้นแบ่งที่ยึดไว้: **ศัพท์กรอบวิเคราะห์ใช้ได้ แต่ตัวเลขต้องมาจาก story เท่านั้น**
คำอย่าง "Liquidity ใต้โซน" เป็นภาษากรอบวิเคราะห์ (ตำรา SMC) ไม่ใช่ค่าที่วัด —
เขียนให้ชัดว่าเป็นการตีความตามแนวคิด ไม่แอบอ้างเป็นข้อมูล

กติกาที่ทำให้ D ต่างจาก A/B/C:
- บทความอ่านจาก story artifact ก้อนเดียวกับที่ตัววาดใช้ — เลขทุกตัวชี้กลับภาพได้
- ด่าน `validate` แบบ fail-closed: เลขนอกทะเบียน story ตัวเดียว = ตกทั้งบท
- จุดเข้าซื้อ (SMC POI) ต้องมีเมื่อระบบคำนวณได้ · ฉากทัศน์ต้องประกาศว่าเป็น
  "เงื่อนไข ไม่ใช่คำทำนาย" · ต้องมีคำเตือนความเสี่ยงท้ายบท — ด่านบังคับทั้งสามข้อ

สไตล์นี้ไม่อยู่ใน `WCB_WRITERS` โดยเจตนา (คำสั่งหัวหน้า 2026-08-06:
"ไม่นำไปใช้กับ A/B/C") — ทะเบียนและด่านของสองสายต้องแยกขาดจากกัน
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import candle_close, chart_story, consistency_gate, headline_format, image_output  # noqa: E402
from tools import wcb_source, wcb_writers  # noqa: E402
from tools.chart_story_renderer import decimals_for, money_for, thai_date  # noqa: E402

STYLE_ID = "d_chart_story"
STYLE_NAME = "D — อ่านโครงสร้างกราฟ"
FOLDER = "D-โครงสร้างกราฟ"
# นับเฉพาะตัวอักษร — ภาษาไทยไม่เว้นวรรคระหว่างคำ นับคำแบบสายอื่นไม่ได้
# เกณฑ์ตั้งจากบทที่โครงครบแต่ตลาด "จนระดับ" (ไม่มีโซน/แนวต้านผ่านเกณฑ์เลย) ~1,700
# อักขระ ซึ่งยังเป็นบทที่ถูกต้อง · ของจริงข้อมูลครบจะได้ ~4,000+ · ต่ำกว่านี้ = โครงหาย
MIN_CHARS = 1500
_NUMBER = re.compile(r"\d[\d,\.]*")


# 🔄 **ถอดบรรทัด byline ออกจากเนื้อบททุกสไตล์ 2026-08-11 (คำสั่งผู้ใช้)**
# ตรงกับสเปกไฟล์ของทีมเว็บที่เขียนไว้ว่า "⛔ ห้ามใส่บรรทัดชื่อผู้เขียน" — หน้าเว็บมี
# กล่องผู้เขียนของมันเองซึ่งอ่านจาก `author_slug` ⇒ เขียนชื่อในเนื้อบทอีกที = ชื่อซ้ำสองที่
# ตัวคนเขียนตอนนี้สื่อผ่าน `wcb_writers.author_slug_for()` ช่องเดียว

# วลีบอกแหล่งของย่อหน้าปัจจัยพื้นฐาน — ต้องเหมือน A/B/C เป๊ะ (กฎเหล็ก: ปัจจัยพื้นฐาน
# ต้องมีแหล่งอ้างอิงเสมอ) · เก็บเป็นค่าคงที่เพื่อให้ด่าน `calendar_source_missing`
# เทียบข้อความเดียวกับที่เขียนลงบท ไม่ใช่พิมพ์ซ้ำสองที่แล้วเพี้ยนกัน
CALENDAR_SOURCE_NOTE = " (ที่มา: ปฏิทินเศรษฐกิจ WorldClassBroker)"

# ------------------------------------------- ชื่อหัวข้อตามใบตัวอย่าง (ผู้ใช้สั่ง 08-11)
#
# คัดลอกจาก `01-CC/Input/ภาษาการเขียน/สไตล์D.md` ทีละตัวอักษร — ห้ามแก้ถ้อยคำเอง
# **จำนวนหัวข้อลดจากหกเหลือห้า** เพราะใบตัวอย่างรวบ "จุดเข้าซื้อ" กับ "แผนการอ่านกราฟ"
# เป็นหัวข้อเดียว (SMC Execution Plan) แล้วแยกด้วยหัวข้อย่อยแทน — ซึ่งอ่านลื่นกว่า
# เพราะฉากทัศน์กับจุดเข้าคือเรื่องเดียวกัน คนอ่านไม่ต้องเลื่อนกลับไปมาระหว่างสองหัวข้อ
#
# ⚠️ **เก็บชื่อล้วน ไม่มีเลขลำดับ** — เลขเกิดตอนประกอบบทด้วย `wcb_writers.SectionNumbers`
# เพราะหัวข้อปฏิทินหายได้ทั้งหัวเมื่อรอบนั้นไม่มีรายการ (เหตุผลเต็มใน docstring ของคลาส)
# เลขที่เกิดขึ้นต้องอยู่ในทะเบียน `allowed_numbers()` ด้วย (ด่านของ D นับทุกเลขในบท)
RULE = ("---", "")
H2_STRUCTURE = "ภาพรวมโครงสร้างตลาด (Market Structure)"
H2_LEVELS = "ระดับราคาสำคัญบนกระดาน (Key Levels)"
H3_SUPPLY = "### 🔴 ฝั่งแนวต้านด้านบน (Supply Zone)"
H3_DEMAND = "### 🟢 ฝั่งแนวรับด้านล่าง (Demand Zone / POI)"
H2_PLAN = "แผนการเทรดและจุดเข้าซื้อที่ได้เปรียบ (SMC Execution Plan)"
H3_BULLISH = "### 📈 ฉากทัศน์ฝั่งขึ้น (Bullish Scenario — Breakout & Retest)"
H3_BEARISH = "### 📉 ฉากทัศน์ฝั่งลง (Bearish Scenario — Rejection)"
H2_CALENDAR = "ปัจจัยเศรษฐกิจที่ต้องจับตา"
H2_SUMMARY = "สรุปภาพรวม"


def image_names(asset: str, date_text: str) -> tuple[str, str]:
    """ชื่อไฟล์ภาพคู่บท — สองภาพแยกตามคำสั่งผู้ใช้ 2026-08-07 (D ไม่รวมภาพ)
    รูปแบบชื่อมีความหมาย+วันที่ ตามที่หัวหน้าแนะนำในฟีดแบ็ก 08-06
    นามสกุลมาจาก `image_output` ที่เดียว — เว็บรับเฉพาะ .webp (กติกา 08-09)"""
    suffix = image_output.IMAGE_SUFFIX
    return (f"{asset}-d1-structure-{date_text}{suffix}",
            f"{asset}-d1-levels-{date_text}{suffix}")


# ---------------------------------------------------------------- ตัวเขียนบท

def _channel_position(story: dict) -> str:
    """ตำแหน่งราคาปัจจุบันเทียบเส้นหลักของกรอบ — คำพูดต้องตามเลข ไม่ใช่ตามอารมณ์"""
    channel = story["channel"]
    if not channel:
        return ""
    edge = "ขอบบน" if channel["main_is_upper"] else "ขอบล่าง"
    gap = story["current"]["close"] - channel["main_at_last"]
    if channel["main_is_upper"]:
        if gap > 0:
            return (f"แท่งล่าสุดปิดทะลุขึ้นเหนือแนว{edge}ของกรอบเป็นที่เรียบร้อย "
                    "ซึ่งยังต้องพิสูจน์ว่าเป็นการทะลุจริง ไม่ใช่ False Breakout")
        if abs(gap) <= story["atr14"]:
            return f"ราคากำลังชนแนว{edge}ของกรอบอยู่พอดี — จุดวัดใจของทั้งสองฝั่ง"
        return f"ราคายังเคลื่อนอยู่ภายในกรอบ ใต้แนว{edge}"
    if gap < 0:
        return (f"แท่งล่าสุดหลุดใต้แนว{edge}ของกรอบแล้ว "
                "ซึ่งยังต้องพิสูจน์ว่าเป็นการหลุดจริง ไม่ใช่ False Breakdown")
    if gap <= story["atr14"]:
        return f"ราคากำลังทดสอบแนว{edge}ของกรอบอยู่พอดี"
    return f"ราคายังเคลื่อนอยู่ภายในกรอบ เหนือแนว{edge}"


def _sma_position(story: dict) -> str:
    """ความสัมพันธ์ราคากับ SMA50 — แนวต้าน/แนวรับพลวัต พูดด้วยตัวเลขจริง"""
    money = money_for(story)
    sma50 = story["sma50_last"]
    if sma50 is None:
        return ""
    close = story["current"]["close"]
    if story["regime"]["down"]:
        if close >= sma50:
            return (f"ที่ต้องจับตาเป็นพิเศษคือราคาดันตัวกลับขึ้นมายืนเหนือเส้นค่าเฉลี่ย 50 วัน "
                    f"(ปัจจุบันอยู่ที่ {money(sma50)} ดอลลาร์) ที่ทำหน้าที่เป็นแนวต้านพลวัต "
                    "(Dynamic Resistance) กดราคามาตลอดรอบขาลง — นี่คือสัญญาณแรกว่าโมเมนตัม"
                    "ฝั่งขายเริ่มแผ่ว แต่หนึ่งสัญญาณยังไม่ใช่การกลับเทรนด์ ต้องรอโครงสร้างยืนยันครับ")
        return (f"ราคายังถูกกดอยู่ใต้เส้นค่าเฉลี่ย 50 วัน (ปัจจุบันอยู่ที่ {money(sma50)} "
                "ดอลลาร์) ที่ทำหน้าที่เป็นแนวต้านพลวัต (Dynamic Resistance) ของรอบขาลง "
                "ตราบใดที่ยังยืนเหนือเส้นนี้ไม่ได้ โมเมนตัมฝั่งขายยังคุมเกมอยู่ครับ")
    if close >= sma50:
        return (f"ราคายังยืนเหนือเส้นค่าเฉลี่ย 50 วัน (ปัจจุบันอยู่ที่ {money(sma50)} ดอลลาร์) "
                "ที่ทำหน้าที่เป็นแนวรับพลวัต (Dynamic Support) ของรอบขาขึ้น โครงสร้างยังแข็งแรงครับ")
    return (f"ราคาหลุดลงมาใต้เส้นค่าเฉลี่ย 50 วัน (ปัจจุบันอยู่ที่ {money(sma50)} ดอลลาร์) "
            "ซึ่งเคยเป็นแนวรับพลวัตของรอบขาขึ้น — สัญญาณเตือนแรกว่าโมเมนตัมกำลังเปลี่ยนมือครับ")


def headline_price_for(story: dict):
    """ตัวจัดรูปราคา**เฉพาะในพาดหัว** — กระชับกว่าในเนื้อบท

    ตัวอย่างของหัวหน้าเขียน "ทองยืน 4,262" ไม่ใช่ "4,262.35" · พาดหัวมีที่จำกัดและ
    ทศนิยมไม่ได้ช่วยให้ตัดสินใจคลิก · ตัวเลขเต็มความละเอียดยังอยู่ในเนื้อบทครบทุกตัว

    ⚠️ **คู่เงินปัดจำนวนเต็มไม่ได้** — 1.15403 จะเหลือ "1" ซึ่งไม่มีความหมาย
    ⇒ ปัดเฉพาะสินทรัพย์ที่ราคาเป็นหลักร้อยขึ้นไปและทะเบียนใช้ทศนิยมไม่เกิน 2
    """
    money = money_for(story)
    places = decimals_for(story)

    def render(value: float) -> str:
        if places <= 2 and abs(value) >= 100:
            return f"{value:,.0f}"
        return money(value)
    return render


def _headline_hook(story: dict) -> str:
    """วลีพาดหัวจากสภาพจริงของโครงสร้าง — เลือกจากเงื่อนไขที่วัดได้เท่านั้น

    🆕 **เขียนใหม่ 2026-08-10 (ผู้ใช้: "อ่านแล้วยังงง ไม่เข้าใจ")** — ของเดิมเป็นศัพท์
    ของคนอ่านกราฟ ("จังหวะวัดใจหน้ากรอบขาลง" / "โครงสร้างขาขึ้นยังคุมเกม") คนที่เห็น
    พาดหัวในผลค้นหายังไม่ได้อ่านบท จึงไม่รู้ว่ากรอบไหน วัดใจอะไร ⇒ ไม่มีเหตุผลให้คลิก

    หลักที่ใช้แทน — ตรงกับตัวอย่างที่หัวหน้าให้มา ("ทองยืน 4,262 รอ Fed ชี้ทาง"):
    **บอกว่าตอนนี้อยู่ตรงไหน แล้วต้องจับตาอะไรต่อ** ด้วยคำที่คนทั่วไปใช้จริง

    ⛔ **ยังห้ามชี้ทิศราคา** (ระยะ 3b/`RL-006` ผู้ใช้ยังไม่เคาะ) — ใช้ "จับตา"/"ทดสอบ"
    ซึ่งบอกว่าระดับนั้นสำคัญ ไม่ได้บอกว่าราคาจะไปถึง · ห้ามใช้ "ลุ้น"/"เป้า"/"พุ่ง"
    """
    close = story["current"]["close"]
    money = headline_price_for(story)
    above = sorted(level["mean"] for level in story["resistance"] if level["mean"] > close)
    below = sorted((zone["mean"] for zone in story["zones"] if zone["mean"] < close),
                   reverse=True)
    # ระดับที่ใกล้ราคาที่สุดคือระดับที่คนอ่านต้องดูก่อน — เลือกฝั่งตามโหมดตลาด
    # เพื่อไม่ให้พาดหัวชวนคิดว่าราคาจะวิ่งสวนโหมดที่บทกำลังเล่า
    if story["regime"]["down"] and below:
        return f"จับตาโซนรับ {money(below[0])}"
    if not story["regime"]["down"] and above:
        return f"จับตาแนวต้าน {money(above[0])}"
    if above:
        return f"จับตาแนวต้าน {money(above[0])}"
    if below:
        return f"จับตาโซนรับ {money(below[0])}"
    return "อ่านระดับสำคัญของรอบนี้"


def _h1_tail(story: dict) -> str:
    """หางของ H1 — สาระของ**วันนั้น** ตามตัวอย่างที่หัวหน้าให้มา ("ทองยืน 4,262 รอ Fed ชี้ทาง")

    ประกอบจากของที่วัดได้ล้วน: คำสั้นของสินทรัพย์ + ยืน/หลุดเทียบเส้นค่าเฉลี่ย 50 วัน +
    ราคาปิดจริง + วลีโครงสร้าง · **ราคาปัดเป็นจำนวนเต็มเฉพาะในพาดหัว** เพื่อความกระชับ
    (ตัวอย่างของหัวหน้าเขียน "4,262" ไม่ใช่ "4,262.35") ตัวเลขเต็มยังอยู่ในเนื้อบทครบ
    """
    profile = wcb_source.profile_for(story["asset"])
    close = story["current"]["close"]
    sma50 = story["sma50_last"]
    verb = "ยืน" if sma50 is None or close >= sma50 else "หลุด"
    return f"{profile['short_name']}{verb} {close:,.0f} {_headline_hook(story)}"


def headline(story: dict) -> str:
    """H1 ของบท — ส่วนหน้าใช้ร่วมกับ Title tag จุดเดียว หางเป็นสาระของวัน

    🐞 **B-3.3 (ทีมเว็บ 2026-08-09):** หัวเรื่องในบทเขียน "ทองคำโลก" แต่ Title tag ที่
    ส่งไปด้วยเขียน "ทองคำ" ⇒ สองที่ไม่ตรงกัน · ต้นเหตุคือ**ระบบไม่เคยผลิต Title tag เลย**
    มันถูกพิมพ์มือลงจดหมายส่งหัวหน้า จึงเพี้ยนจาก H1 ได้โดยไม่มีอะไรจับ

    🆕 **สเปก SEO 2026-08-10 กลับทิศข้อนี้บางส่วน:** หัวหน้าสั่งว่า Title กับ H1
    **ต้องไม่เหมือนกัน** (คนละหน้าที่: Title คือช่องคำค้น H1 คือช่องเล่าสาระของวัน)
    ⇒ ทางที่รักษาบทเรียน B-3.3 ไว้พร้อมกันคือ **แยกเฉพาะหาง ส่วนหน้ายังออกจากที่เดียว**
    (`headline_format.prefix`) · เขียนคนละเส้นทั้งสองอันเมื่อไหร่ ชื่อสินทรัพย์กับวันที่
    จะเพี้ยนกันได้อีก · และมีด่าน `title_equals_h1` กันหางชนกันโดยไม่ตั้งใจ

    S-1 (ฟีดแบ็กหัวหน้า 2026-08-07): พาดหัวต้องมีคำว่า "ทองคำ" — คนไทยค้น
    "ราคาทองวันนี้" / "วิเคราะห์ทองคำ" ไม่ได้ค้น "XAU/USD"
    """
    return headline_format.h1(story["asset"], story["current"]["date"], _h1_tail(story))


def seo_title(story: dict) -> str:
    """Title tag ที่หลังบ้านเอาไปใช้ — เดือนเต็ม + หางของสไตล์ D (สเปก 2026-08-10)

    ระบบผลิตให้เอง ไม่มีใครพิมพ์มือ (สายผลิตส่งออกใน `chart_story_pipeline.run()`)

    ⚠️ **ห้ามปล่อยให้ตกไปใช้หางคงที่ของทะเบียน** — หางทะเบียนเป็นของสไตล์ A ที่ไม่ได้
    ส่งหางของตัวเองมา · เคยพลาดข้อนี้จริง (ผู้ใช้จับได้ 2026-08-10): D เรียก
    `headline_format.title()` เปล่า ๆ จึงได้หางเดียวกับ A เป๊ะทั้งบรรทัด และเทสไม่จับ
    เพราะตัวที่เทียบพาดหัวว่าซ้ำกันไหมดูแค่ A/B/C ซึ่งอยู่คนละโมดูลกับ D/E
    ⇒ ตอนนี้มีเทสเทียบครบทั้งห้าสไตล์แล้ว (`test_headline_format.พาดหัวข้ามทุกสไตล์`)

    หางของ D ชี้ไปที่ของที่บทนี้มีจริงและสไตล์อื่นไม่มี: ระดับแนวรับแนวต้านที่วาดลงภาพ
    """
    profile = wcb_source.profile_for(story["asset"])
    return headline_format.title(story["asset"], story["current"]["date"],
                                 f"แนวรับแนวต้านจากกราฟ {profile['symbol']}")


def frontmatter_lines(story: dict, *, excerpt_clauses: list[str] | None = None,
                      title_text: str | None = None) -> list[str]:
    """หัวไฟล์ของสไตล์ D/E — **เปิดใช้ 2026-08-10 ตามคำสั่งผู้ใช้ (ทุกสไตล์ต้องมี title)**

    เดิมสไตล์นี้ห้ามมี frontmatter (กฎ `frontmatter_forbidden`) ซึ่งตั้งไว้ตอนยังไม่รู้ว่า
    หลังบ้านรับได้ไหม · ทีมเว็บตอบแล้ว 08-09 ว่า **ส่งมาเองได้และแนะนำให้ส่ง** เพราะ
    ค่าที่ส่งมาชนะค่าที่ระบบเดาเสมอ ⇒ ส่ง `title`/`excerpt` เองดีกว่าปล่อยให้เว็บเดา

    `excerpt` = meta description ตัวจริงของหน้า — ยกจากคำโปรยที่บทมีอยู่แล้ว

    ⚠️ **สไตล์ E ใช้ฟังก์ชันนี้ร่วมกันแต่ story คนละโครง** (ไม่มีช่อง `resistance`/`zones`)
    ⇒ ผู้เรียกส่ง `excerpt_clauses` ของตัวเองมาได้ ห้ามให้ตัวนี้เดาโครงของอีกสไตล์
    """
    excerpt = wcb_writers.fit_excerpt(excerpt_clauses or _excerpt_clauses(story))
    title = title_text or seo_title(story)
    return [
        "---",
        f"asset: {story['asset']}",
        f"title: {wcb_writers.fit_title(title)}",
        f"excerpt: {excerpt}",
        f"author_slug: {wcb_writers.author_slug_for(story['asset'])}",
        "timeframe: Daily",
        f"trend: {'dn' if story['regime']['down'] else 'up'}",
        "---",
        "",
    ]


def _excerpt_clauses(story: dict) -> list[str]:
    """ประโยคสำหรับคำโปรย — ต่อกันจนถึงช่วงความยาวที่ระบบนำเข้าบังคับ (120–160)"""
    money = money_for(story)
    profile = wcb_source.profile_for(story["asset"])
    clauses = [f"{profile['short_name']}ปิดที่ {money(story['current']['close'])} ดอลลาร์"]
    if story["resistance"]:
        clauses.append(f"แนวต้านแรก {money(story['resistance'][0]['mean'])}")
    if story["zones"]:
        clauses.append(f"โซนรับ {money(story['zones'][0]['mean'])}")
    clauses += ["อ่านโครงสร้างกราฟรายวันพร้อมจุดเข้าและจุดยกเลิกมุมมองทั้งสองฝั่ง",
                "ทุกระดับคำนวณจากแท่งราคาจริง"]
    return clauses


def _memory_note(level: dict, story: dict, *, kind: str = "โซน") -> str:
    """วลีกำกับความต่อเนื่อง — ระดับที่ล็อกข้ามวันบอกคนอ่านตรง ๆ ว่าเป็นชุดเดิม

    ผู้ใช้เคาะ 08-10 (#18ข): ระดับล็อกจนกว่าราคาปิดทะลุ — ความต่อเนื่องข้ามวัน
    คือจุดขายของบท ไม่ใช่แค่กติกาภายใน · วันเดียวกับที่ล็อกไม่ต้องกำกับ (ยังไม่ "เดิม")
    """
    locked_since = level.get("locked_since")
    if not locked_since or locked_since >= story["current"]["date"]:
        return ""
    return f"({kind}เดิมที่ใช้อ้างอิงมาตั้งแต่ {thai_date(locked_since)}) "


def _h3_entry(story: dict, money) -> str:
    """หัวข้อย่อยแผนเข้าเทรด — ใบตัวอย่างใส่ราคาโซนรับลงในชื่อหัวข้อเลย

    ราคาที่ใส่คือ **ค่าเดียวกับจุดเข้าอันดับหนึ่งในเนื้อหัวข้อ** ไม่ใช่ค่าใหม่
    ⇒ ขึ้นทะเบียนใน `allowed_numbers()` อยู่แล้วผ่าน `entry["price"]`
    ไม่มีจุดเข้า = ไม่ใส่ราคา (ห้ามใส่เลขที่หัวข้อไม่ได้พูดถึงจริงในเนื้อ)
    """
    entries = story.get("entries") or []
    if entries:
        return f"### 💡 แผนการเข้าเทรดบริเวณโซนรับ {money(entries[0]['price'])} ดอลลาร์"
    return "### 💡 แผนการเข้าเทรดบริเวณโซนรับ"


def render_article(story: dict) -> str:
    money = money_for(story)
    profile = wcb_source.profile_for(story["asset"])
    first_image, second_image = image_names(story["asset"], story["current"]["date"])
    down = story["regime"]["down"]
    current_text = money(story["current"]["close"])
    zones = story["zones"]
    above = sorted(level["mean"] for level in story["resistance"])
    channel = story["channel"]
    entries = story["entries"]
    heads = wcb_writers.SectionNumbers()

    # ---- บทนำแบบเล่าเรื่อง (Market Overview) ----
    if down:
        opening = (
            f"{story['symbol']} กำลังเขียนบทที่น่าติดตามที่สุดของรอบนี้ครับ "
            f"หลังจบรอบขาขึ้นใหญ่ด้วยการทำจุดสูงสุดที่ {money(story['peak']['high'])} ดอลลาร์"
            f"เมื่อ {thai_date(story['peak']['date'])} โครงสร้างตลาด (Market Structure) "
            "ก็พลิกเป็นขาลงเต็มตัว ราคาไล่ทำ Lower High และ Lower Low ต่อเนื่อง"
            f"ภายใน Bearish Channel จนแท่งล่าสุดปิดที่ {current_text} ดอลลาร์ ")
    else:
        opening = (
            f"{story['symbol']} ยังอยู่ในรอบขาขึ้นที่โครงสร้างแข็งแรงครับ ราคาไล่ทำ "
            "Higher High และ Higher Low ต่อเนื่องภายใน Bullish Channel "
            f"แท่งล่าสุดปิดที่ {current_text} ดอลลาร์ ")
    opening += _channel_position(story)
    opening += (
        " บทวิเคราะห์ฉบับนี้จะพาไล่ตั้งแต่โครงสร้างรอบใหญ่ ระดับสำคัญ "
        "จุดเข้าซื้อที่ได้เปรียบตามแนวคิด Smart Money "
        "ไปจนถึงแผนรับมือทั้งสองฝั่ง — ทุกเส้น ทุกโซน และตัวเลขทุกตัว "
        "คำนวณจากแท่งราคาจริงทั้งหมด ไม่มีเส้นใดวาดขึ้นตามความรู้สึก")
    # พาดหัวมาจาก `headline()` ที่เดียว — Title tag ใช้ตัวเดียวกัน (B-3.3)
    lines = frontmatter_lines(story) + [
        "# " + headline(story),
        "",
        opening,
        "",
        *RULE,
        heads.head(H2_STRUCTURE),
        "",
    ]

    view_para = f"**มุมมองตลาด:** ภาพใหญ่ย้อนหลัง {story['display']['bars']} แท่งรายวันเล่าเรื่องครบหนึ่งวัฏจักร "
    if down:
        view_para += (
            "ขาขึ้นรอบก่อนไต่บันไดอย่างมีระเบียบ ก่อนแรงซื้อจะหมดเชื้อเพลิงบริเวณยอด "
            "แล้วเกิดการกระจายของ (Distribution) จนโครงสร้างหักลงเป็นขาลง ")
        if channel:
            view_para += (
                f"กรอบ Bearish Channel ที่ครอบการไหลลงลากผ่านจุดกลับตัวจริงรวม "
                f"{channel['touch_count']} จุด เริ่มนับจาก {thai_date(channel['start_date'])} "
                "— ยิ่งราคาเคารพกรอบหลายครั้ง กรอบยิ่งเป็นแนวอ้างอิงที่ตลาดใช้ร่วมกันจริง "
                + _memory_note(channel, story, kind="กรอบ"))
        if zones:
            zone1 = zones[0]
            # การเล่าเรื่องจำนวนครั้งที่แตะ: ตามหลัก SMC โซนที่ถูกแตะซ้ำถือว่า
            # ถูกใช้ (mitigated) ไปมากแล้ว — ห้ามเล่าว่า "ยิ่งแตะยิ่งแข็ง"
            # (ฟีดแบ็กหัวหน้า 08-06 ข้อ 2 · เลือกทางเล่าแบบ "แนวอ้างอิงร่วมของตลาด")
            view_para += (
                f"ขณะเดียวกันด้านล่าง ตลาดใช้บริเวณ {money(zone1['mean'])} ดอลลาร์ "
                f"เป็นแนวอ้างอิงร่วมกันมาแล้ว {zone1['touches']} ครั้ง "
                "— แต่ต้องอ่านให้ถูกด้าน: ตามหลัก Price Action ออร์เดอร์ในโซน"
                "ถูกใช้ไปส่วนหนึ่งทุกครั้งที่ราคาลงมาแตะ การกลับมาครั้งถัดไปจึงเป็น"
                "บททดสอบของโซน ไม่ใช่หลักประกันว่าจะเด้ง "
                "ความหมายที่แท้จริงของระดับนี้คือ: ถ้าครั้งหน้าเอาไม่อยู่ "
                "นั่นคือสัญญาณเปลี่ยนโครงสร้างที่ทั้งตลาดเห็นพร้อมกัน — "
                "โครงสร้างแบบนี้จบได้สองทางเท่านั้น: ทะลุกรอบขึ้น หรือหลุดฐานลง")
    else:
        view_para += ("ราคายังรักษาลำดับ Higher High / Higher Low ไว้ได้ครบ "
                      "และยังไม่มีสัญญาณการกระจายของ (Distribution) ที่โครงสร้างยืนยัน")
    lines += [view_para, ""]

    momentum_para = "**โมเมนตัมและเส้นค่าเฉลี่ย:** เส้นหนาที่เปลี่ยนสีบนภาพคือเส้นค่าเฉลี่ย 50 วัน — เขียวช่วงยกตัว แดงช่วงหัวลง "
    if story["regime"]["flip_date"]:
        mode = "ขาลง" if down else "ขาขึ้น"
        momentum_para += (
            f"รอบนี้พลิกเป็นโหมด{mode}ตั้งแต่ {thai_date(story['regime']['flip_date'])} "
            "และยังไม่พลิกกลับ ")
    momentum_para += _sma_position(story)
    # alt text ใส่ตัวเลขระดับสำคัญ — ฟีดแบ็กหัวหน้า (เรื่องเล็ก) · เลขต้องมาจาก story
    alt_parts = [f"ภาพที่ 1 — โครงสร้างรอบใหญ่ {story['symbol']} รายวัน"]
    if zones:
        alt_parts.append(f"โซนรับ {money(zones[0]['mean'])}")
    if above:
        alt_parts.append(f"แนวต้านแรก {money(above[0])}")
    lines += [momentum_para, "",
              f"![{' · '.join(alt_parts)}]({first_image})", "",
              *RULE,
              heads.head(H2_LEVELS), ""]

    # 🐞 **CSS ยังไม่รองรับตาราง/bullet ในเนื้อบท (ฟีดแบ็กหัวหน้า 2026-08-07)**
    # `.an-body` มีสไตล์ให้แค่ h2/h3/p — ทั้งตาราง `|...|` และลิสต์ `- ` จะขึ้นเว็บแบบ
    # ไม่มีเส้น ไม่มีระยะห่าง อ่านแทบไม่ได้บนมือถือ ⇒ เขียนเป็นย่อหน้าปกติไปก่อนทั้งหมด
    # จนกว่าฝั่งเว็บจะเพิ่ม CSS ให้ `.an-body table/th/td` และ `.an-body ul`
    # (หัวข้อย่อย `###` ใช้ได้ — `.an-body` มีสไตล์ให้ h3 อยู่แล้ว จึงเป็นทางเดียวที่
    #  แยกฝั่งบน/ฝั่งล่างออกจากกันได้ตามใบตัวอย่างโดยไม่ต้องรอ CSS ใหม่)
    if zones or above:
        lines += ["ระดับทุกเส้นด้านล่างมาจากจุดกลับตัวจริงที่ถูกแตะซ้ำในอดีต "
                  "ไม่ใช่ตัวเลขกลม ๆ จากความรู้สึกครับ ", ""]
    if zones:
        zone1 = zones[0]
        demand_para = (f"ฝั่งล่าง **Demand Zone (POI 1)** อยู่ในช่วง {money(zone1['low'])}–"
                       f"{money(zone1['high'])} ดอลลาร์ เป็นแนวอ้างอิงที่ตลาดใช้ร่วมกันมาแล้ว "
                       f"{zone1['touches']} ครั้ง ")
        demand_para += _memory_note(zone1, story)
        if zone1["includes_week52_low"]:
            demand_para += "ครอบจุดต่ำสุดในรอบ 52 สัปดาห์ไว้ในตัว "
        demand_para += ("มุม SMC ต้องพูดตรง ๆ ว่าโซนที่ถูกแตะหลายครั้งถือว่าออร์เดอร์ถูกใช้ "
                        "(Mitigated) ไปมากแล้ว น้ำหนักจึงไม่ได้อยู่ที่จำนวนครั้ง "
                        "แต่อยู่ที่ปฏิกิริยาครั้งถัดไป: รับอยู่ = ระดับยังทำงาน "
                        "หลุดพร้อมปิดวันใต้โซน = สัญญาณเปลี่ยนโครงสร้างที่ชัดที่สุดบนกระดาน")
        if len(zones) > 1:
            zone2 = zones[1]
            demand_para += (f" ถัดลงไปอีกมี **Deep Discount (POI 2)** ที่ {money(zone2['low'])}–"
                            f"{money(zone2['high'])} ดอลลาร์ ฐานเก่าที่ตลาดเคยใช้อ้างอิง "
                            f"{zone2['touches']} ครั้ง")
            if zone2["includes_week52_low"]:
                demand_para += (" และเป็นที่อยู่ของจุดต่ำสุดรอบ 52 สัปดาห์ — แนวรับเชิงเทคนิค"
                                "กับเชิงจิตวิทยาซ้อนกันพอดี")
            if not zone2.get("daily_entry", True):
                demand_para += (" — **หมายเหตุสำคัญ: นี่คือระดับกรอบหลายเดือน อยู่ห่างจากราคา"
                                "ปัจจุบันมาก ใส่ไว้เพื่อให้เห็นภาพโครงสร้างใหญ่ ไม่ใช่ระดับสำหรับ"
                                "แผนรายวัน**")
            else:
                demand_para += " เป็นพื้นที่ราคาส่วนลดลึกในมุมมองเชิงโครงสร้างหากราคาลงมาถึง"
    if above:
        supply_para = f"ฝั่งบน **Supply / แนวต้านด้านบน** ชั้นแรกอยู่ที่ {money(above[0])} ดอลลาร์ "
        if len(above) > 1:
            supply_para += f"ตามด้วย {money(above[1])} "
        if len(above) > 2:
            supply_para += f"และ {money(above[2])} "
        supply_para += ("— ทั้งหมดคืออดีต Swing High ที่ยังมีแรงขายค้าง (Unfilled Supply) "
                        "รอรับราคาอยู่หากเด้งขึ้นไปถึง ปิดวันเหนือชั้นแรกได้จริงคือสัญญาณ "
                        "Break of Structure ฝั่งขึ้น ส่วนชั้นที่เหลือเป็นเป้าถัดไปตามลำดับ")
        lines += [H3_SUPPLY, "", supply_para, ""]
    if zones:
        # ใบตัวอย่างเรียง Supply ก่อน Demand (ไล่จากบนลงล่างตามที่ตาอ่านกราฟ)
        # — ของเดิมเรียงกลับกัน ⇒ ย่อหน้า Demand ถูกประกอบไว้ข้างบนแล้ววางที่นี่
        lines += [H3_DEMAND, "", demand_para, ""]
    if story["sma50_last"] is not None and (zones or above):
        sma50 = story["sma50_last"]
        side = "ใต้ราคา" if story["current"]["close"] >= sma50 else "เหนือราคา"
        flip = ("ราคากลับไปปิดใต้เส้นนี้ = โมเมนตัมคืนฝั่งขาย" if side == "ใต้ราคา"
                else "ราคายืนเหนือเส้นนี้ได้ = โมเมนตัมเริ่มกลับฝั่งซื้อ")
        lines += [f"อีกเส้นที่ต้องจับตาคือเส้นค่าเฉลี่ย 50 วันที่ {money(sma50)} ดอลลาร์ "
                  f"ตอนนี้อยู่{side} — {flip}", ""]
    if not zones and not above:
        lines += ["หน้าต่างนี้ไม่มีระดับที่ผ่านเกณฑ์การแตะซ้ำของระบบ "
                  "จึงไม่มีระดับให้ระบุ และบทความจะไม่สร้างระดับขึ้นเองแทนครับ", ""]

    # ---- 3. แผนการเทรดและจุดเข้าซื้อที่ได้เปรียบ (SMC Execution Plan) ----
    #
    # 🔄 **รวบสองหัวข้อเดิม ("จุดเข้าซื้อ" + "แผนการอ่านกราฟ") เป็นหัวข้อเดียว 08-11**
    # ตามใบตัวอย่าง · ลำดับในใบคือ เกริ่นหลักคิด → ภาพที่ 2 → ฉากทัศน์ขึ้น → ฉากทัศน์ลง
    # → แผนเข้าที่โซนรับ ⇒ **จุดเข้าย้ายมาอยู่ท้ายสุด** เพราะต้องอ่านฉากทัศน์ก่อน
    # จึงจะรู้ว่าจุดเข้านั้นใช้ในสถานการณ์ไหน (ของเดิมเล่าจุดเข้าก่อนแล้วค่อยเล่าเงื่อนไข)
    lines += [*RULE, heads.head(H2_PLAN), ""]
    lines += ["หลักคิดของ Smart Money Concepts คือ **ไม่ไล่ราคากลางอากาศ** "
              "แต่รอให้ราคากลับมาหาพื้นที่ที่แรงซื้อเคยแสดงตัวจริงครับ", ""]
    zoom_alt_parts = [f"ภาพที่ 2 — ระดับตัดสินใจ จุดเข้าซื้อ และฉากทัศน์ {story['symbol']}"]
    if entries:
        zoom_alt_parts.append(f"จุดเข้าซื้อ {money(entries[0]['price'])}")
    if story["scenarios"]["up"]:
        zoom_alt_parts.append(f"เงื่อนไขฝั่งขึ้น {money(story['scenarios']['up']['trigger'])}")
    lines += [f"![{' · '.join(zoom_alt_parts)}]({second_image})", ""]

    entry_lines: list[str] = []
    if entries:
        entry_lines += [
            "ราคาแนะนำด้านล่างคือกึ่งกลางของโซนที่แรงซื้อเคยแสดงตัว "
            "พร้อมจุดยกเลิกมุมมองชัดเจนทุกจุดครับ",
            "",
        ]
        entry_parts = []
        for entry in entries:
            depth = ("Demand Zone หลัก" if entry["rank"] == 1
                     else "Deep Discount — พื้นที่ได้เปรียบสูงสุด")
            entry_parts.append(
                f"**จุดเข้าซื้อ {entry['rank']} ที่ {money(entry['price'])} ดอลลาร์** "
                f"(ช่วง {money(entry['zone_low'])}–{money(entry['zone_high'])} · {depth}) "
                f"โซนนี้ถูกใช้เป็นแนวอ้างอิงมาแล้ว {entry['touches']} ครั้ง — "
                "ยิ่งถูกใช้ซ้ำ ออร์เดอร์ในโซนยิ่งเหลือน้อย จึงต้องรอการยืนยันแรงซื้อจริง"
                "ก่อนเข้าเสมอ ไม่เข้าล่วงหน้า "
                f"จุดยกเลิกมุมมอง (Invalidation): ราคาปิดวันต่ำกว่า "
                f"{money(entry['invalidation'])} ดอลลาร์")
        entry_lines.append(" ".join(entry_parts))
        excluded = [zone for zone in story["zones"] if not zone.get("daily_entry", True)]
        if excluded:
            excluded_parts = [
                f"โซนลึกบริเวณ {money(zone['mean'])} ดอลลาร์ (POI {zone['rank']})"
                for zone in excluded]
            entry_lines += ["",
                            " และ ".join(excluded_parts)
                            + " อยู่ห่างจากราคาปัจจุบันเกินเกณฑ์แผนรายวันของระบบ "
                            "จึงไม่จัดเป็นจุดเข้าในบทนี้ — เป็นระดับเชิงโครงสร้างกรอบหลายเดือนเท่านั้น"]
        execution = (
            "**Execution Plan:** อย่ารีบสวนมีดขณะราคากำลังร่วง และอย่าไล่ราคากลางช่องว่างครับ "
            "ให้รอราคาย่อกลับเข้าโซนก่อน แล้วสลับไป Timeframe ย่อย (1H/15M) "
            "เพื่อหาการยืนยันตัวตนของ Smart Money — เช่นการเกิด CHoCH (Change of Character) "
            "หรือ Stop Hunt ที่ราคาจิ้มกวาดสภาพคล่องใต้โซนแล้วดีดกลับอย่างรวดเร็ว — "
            "ได้สัญญาณยืนยันแล้วจึงค่อยพิจารณาเข้า ไม่มีสัญญาณ ไม่มีการเข้า")
        if story["current"]["close"] > entries[0]["zone_high"]:
            execution += (
                " เหตุที่ไม่แนะนำให้เข้าที่ราคาปัจจุบัน เพราะราคาลอยอยู่เหนือโซนแรกพอสมควร "
                "การเข้ากลางอากาศคือการยอมเสียทั้งแต้มต่อราคา (Risk to Reward) "
                "และตำแหน่งจุดตัดขาดทุนที่ดี — การรอให้ราคาลงมาหาเราคือหัวใจของแนวคิดนี้ครับ")
        entry_lines += ["", execution]
    elif story["zones"]:
        entry_lines += ["โซนรับที่ระบบวัดได้รอบนี้ทั้งหมดอยู่ห่างจากราคาปัจจุบันเกินเกณฑ์แผนรายวัน "
                        "จึงไม่มีจุดเข้าที่ระบบกล้าแนะนำในกรอบรายวัน "
                        "และจะไม่ขยับเกณฑ์เพื่อให้มีจุดเข้าครับ"]
    else:
        entry_lines += ["รอบนี้ไม่มีโซนที่ผ่านเกณฑ์การแตะซ้ำ จึงไม่มีจุดเข้าที่ระบบกล้าแนะนำ "
                        "และจะไม่ตั้งราคาขึ้นเองจากความรู้สึกแทนครับ"]

    up = story["scenarios"]["up"]
    down_scenario = story["scenarios"]["down"]
    if up:
        text = (f"**เงื่อนไข:** กุญแจอยู่ที่{up['condition']} "
                f"({money(up['trigger'])} ดอลลาร์) การปิดเหนือระดับนี้ได้จริง"
                "จะมีน้ำหนักเป็น Break of Structure (BOS) ฝั่งขึ้น")
        if up["targets"]:
            targets = " และ ".join(money(value) for value in up["targets"])
            text += f" เปิดทางเข้าหา Supply ถัดไปที่ {targets} ดอลลาร์ตามลำดับ"
        text += (f" มุมมองนี้ตกทันทีเมื่อ{up['invalidation']} "
                 "ซึ่งจะกลายเป็น False Breakout ที่มักตามด้วยแรงขายรอบใหม่ครับ")
        lines += [H3_BULLISH, "", text, ""]
        # จุดเข้าฝั่งขึ้นพร้อมเลขยกเลิก — ฟีดแบ็กหัวหน้าข้อ 4 (เดิมฝั่งขึ้นไม่มีจุดเข้าเลย)
        lines += [
            f"**จุดเข้าฝั่งขึ้น (Breakout-Continuation):** สำหรับคนที่อยากตามแรงดีด "
            "อย่าไล่ราคาตอนกำลังทะลุ — รอให้ปิดวันเหนือ "
            f"{money(up['trigger'])} ดอลลาร์ให้จบก่อน แล้วรอจังหวะราคาย่อกลับมาทดสอบ"
            f"แนวที่เพิ่งทะลุในช่วง {money(up['entry_low'])}–{money(up['entry_high'])} "
            "ดอลลาร์ (Retest — แนวต้านเดิมพลิกเป็นแนวรับ) พร้อมสัญญาณแรงซื้อใน Timeframe ย่อย "
            f"จุดยกเลิกมุมมอง (Invalidation): ราคาปิดวันกลับต่ำกว่า "
            f"{money(up['entry_invalidation'])} ดอลลาร์ — ถึงตรงนั้นการทะลุถือว่าล้มเหลว "
            "ไม่ถัวไม่รอครับ", ""]
    if down_scenario:
        text = (f"**เงื่อนไข:** สัญญาณอันตรายคือ{down_scenario['condition']} "
                f"({money(down_scenario['trigger'])} ดอลลาร์) เพราะแปลว่า Demand Zone "
                "ถูกเจาะ แรงซื้อที่เคยรับอยู่ถอยกระดาน และโซนที่เคยเป็นแนวรับ"
                "จะพลิกบทบาทเป็นแนวต้าน (Role Reversal) ทันที")
        if down_scenario["targets"]:
            targets = " และ ".join(money(value) for value in down_scenario["targets"])
            text += f" เป้าถัดไปของฝั่งขายคือ {targets} ดอลลาร์"
        text += f" มุมมองนี้ตกทันทีเมื่อ{down_scenario['invalidation']}"
        lines += [H3_BEARISH, "", text, ""]
    if not up and not down_scenario:
        lines += ["รอบนี้ไม่มีระดับที่ผ่านเกณฑ์พอจะตั้งเงื่อนไขได้ทั้งสองฝั่ง "
                  "ระบบจึงไม่ตั้งฉากทัศน์ และจะไม่ตั้งเป้าจากความรู้สึกแทนครับ", ""]

    lines += [_h3_entry(story, money), ""] + entry_lines + [""]
    lines += [
        "ระดับฉากทัศน์ที่กำกับไว้บนภาพที่สองเป็นเงื่อนไขสมมุติจากระดับที่คำนวณได้ "
        "ไม่ใช่คำทำนาย ราคาไม่จำเป็นต้องไปถึงระดับใดระดับหนึ่ง "
        "หน้าที่ของมันคือบอกล่วงหน้าว่าจุดไหนทำให้มุมมองเปลี่ยน ไม่ใช่บอกว่าพรุ่งนี้จะเกิดอะไร", ""]

    # ---- ปัจจัยพื้นฐานจากปฏิทินจริง — ฟีดแบ็กหัวหน้าข้อ 3 · มติผู้ใช้ 08-06 ดึก:
    # ใช้ปฏิทินเศรษฐกิจที่วัดได้แทนลิงก์ข่าว (โรงงานข่าวของเว็บยังไม่ต่อ) ·
    # ระบบไม่เดาเหตุผลย้อนหลัง — เขียนได้เฉพาะกำหนดการข้างหน้าที่มีในข้อมูลจริง
    calendar = story.get("calendar")
    if calendar and calendar.get("sentences"):
        sentences = calendar["sentences"]
        lines += [*RULE, heads.head(H2_CALENDAR), "",
                  "กราฟบอกว่า \"ระดับไหนสำคัญ\" แต่ตัวที่มักเป็นชนวนให้ราคาวิ่งถึงระดับเหล่านั้น "
                  "คือกำหนดการเศรษฐกิจข้างหน้า ไล่รายการที่ใกล้ที่สุดจากปฏิทินจริงของระบบ "
                  # 🐞 **เก็บของค้างจากใบก่อน (08-09):** ย่อหน้านี้ยกตัวเลขจากปฏิทิน
                  # เหมือนสไตล์ A/B/C แต่ปิดท้ายด้วยช่องว่างเปล่า **ไม่มีวลีบอกที่มา**
                  # ทั้งที่กฎเหล็กของระบบคือปัจจัยพื้นฐานต้องมีแหล่งอ้างอิงเสมอ
                  # (A/B/C ปิดท้ายด้วยวลีเดียวกันนี้ที่ `wcb_writers` บรรทัด 848/986/1064)
                  "ด่านแรกคือ" + sentences[0]
                  + (" ต่อด้วย " + " ต่อด้วย ".join(sentences[1:]) if sentences[1:] else "")
                  + CALENDAR_SOURCE_NOTE,
                  "",
                  "บทนี้จงใจไม่เดาย้อนหลังว่าราคาที่ผ่านมาขยับเพราะข่าวใด — "
                  "สิ่งที่ยืนยันได้จริงคือกำหนดการข้างหน้า และระดับราคาที่วัดได้บนกราฟครับ", ""]

    summary = f"---\n\n{heads.head(H2_SUMMARY)}\n\nทั้งกระดานวันนี้ย่อลงเหลือคำถามเดียวครับ — "
    if up and zones:
        summary += (
            f"ราคาจะยืนยันแรงดีดด้วย BOS เหนือ {money(up['trigger'])} ดอลลาร์ "
            "หรือจะถูก Supply ด้านบนตีกลับลงมาให้ Demand Zone ทำงานอีกครั้ง "
            "คำตอบไม่ได้อยู่ที่การเดา แต่อยู่ที่ราคาปิดเทียบระดับที่ระบบวัดไว้ให้แล้วทั้งหมด")
    elif up:
        summary += (f"ราคาจะผ่านด่าน {money(up['trigger'])} ดอลลาร์ได้หรือไม่ "
                    "คำตอบอยู่ที่ราคาปิด ไม่ใช่การเดา")
    else:
        summary += "โครงสร้างจะเลือกทางไหน คำตอบอยู่ที่ราคาปิดเทียบระดับบนภาพ ไม่ใช่การเดา"
    summary += (" กราฟทั้งสองใบกับตัวเลขทุกตัวในบทนี้มาจากแท่งราคาชุดเดียวกัน "
                "ตรวจย้อนกลับได้ครบทุกจุด")
    lines += [summary, "", _internal_links(story, profile), "",
              "**คำเตือนความเสี่ยง:** บทวิเคราะห์นี้จัดทำจากโครงสร้างราคาเพื่อการศึกษาและติดตามตลาด "
              "ไม่ใช่คำแนะนำการลงทุน และไม่ใช่คำชักชวนให้ซื้อขายสินทรัพย์ใด ๆ "
              + wcb_writers._closing(),
              ""]
    return "\n".join(lines)


def _internal_links(story: dict, profile: dict) -> str:
    """S-2 (ฟีดแบ็กหัวหน้า 2026-08-07): บทไม่มี internal link เลยสักลิงก์

    ใช้เฉพาะที่อยู่ที่ยืนยันแล้วว่ามีจริง (`EXTERNAL.md` E5 — ทีมเว็บส่งมา 2026-08-06)
    **ห้ามใส่โดเมนเต็ม** เว็บยังเปลี่ยนที่อยู่หลักอยู่ · สอง URL นี้ = 2 ลิงก์ ต่ำกว่า
    เพดาน 5 ลิงก์ที่ระบบอนุญาต — ยังไม่เพิ่มลิงก์บทเมื่อวานเพราะ slug ของบทที่ขึ้นเว็บ
    จริงถูกกำหนดตอนอัปโหลด เราไม่รู้ล่วงหน้าว่าลิงก์คงที่แบบไหนถูกต้อง
    """
    tag = wcb_source.tag_for(story["asset"])
    return (f"ติดตามราคา{profile['short_name']}แบบเรียลไทม์ได้ที่ "
            f"[หน้าราคา{profile['short_name']}]"
            f"(/thailand/asset-{tag}) และดูบทวิเคราะห์ย้อนหลังทั้งหมดได้ที่ "
            "[คลังบทวิเคราะห์](/thailand/analysis)")


# ---------------------------------------------------------------- ด่านตรวจ

def allowed_numbers(story: dict) -> set[str]:
    """ทะเบียนเลขที่บทความมีสิทธิ์พูดถึง — สร้างจาก story เท่านั้น

    "15" มาจาก Timeframe ย่อย 1H/15M ใน Execution Plan (ศัพท์กรอบวิเคราะห์ ไม่ใช่ค่าที่วัด)
    "1"–"5" คือ**เลขลำดับหัวข้อ** ของโครงห้าหัวข้อตามใบตัวอย่าง 08-11 (ก่อนหน้านั้น
    หัวข้อไม่มีเลขลำดับ และ "4" ไม่เคยอยู่ในทะเบียน ⇒ หัวข้อ 4 ทำบทตกด่านตัวเองทันที)
    """
    money = money_for(story)
    allowed = {
        str(story["display"]["bars"]), str(story["display"]["zoom_bars"]),
        "1", "2", "3", "4", "5", "15", "50", "52", "200",
    }
    prices = [story["current"]["close"], story["peak"]["high"], story["trough"]["low"],
              story["week52_low"]]
    for key in ("sma50_last", "sma200_last"):
        if story.get(key) is not None:
            prices.append(story[key])
    for level in story["resistance"]:
        prices.append(level["mean"])
        allowed.add(str(level["touches"]))
    for zone in story["zones"]:
        prices += [zone["mean"], zone["low"], zone["high"]]
        allowed.add(str(zone["touches"]))
    # จุดยกเลิกของจุดเข้าไม่เท่ากับขอบโซนอีกแล้วหลังปิด B-1 ⇒ เป็นราคาที่ต้องขึ้นทะเบียนเอง
    for entry in story.get("entries", []):
        prices.append(entry["invalidation"])
    channel = story["channel"]
    if channel:
        allowed.add(str(channel["touch_count"]))
        prices += [channel["main_at_last"], channel["parallel_at_last"]]
    for side in ("up", "down"):
        scenario = story["scenarios"][side]
        if scenario:
            prices += [scenario["trigger"], *scenario["targets"]]
            for key in ("entry_low", "entry_high", "entry_invalidation"):
                if scenario.get(key) is not None:
                    prices.append(scenario[key])
    headline_money = headline_price_for(story)
    for value in prices:
        allowed.add(money(value))
        # รูปแบบกระชับที่ใช้ในพาดหัว — ค่าเดียวกัน คนละการจัดรูป ไม่ใช่เลขใหม่
        allowed.add(headline_money(value))
    # ชื่อไฟล์ภาพมีวันที่เต็มรูป (เช่น 2026-08-06) — เลขเดือน/วันแบบมีศูนย์นำ
    # ไม่ตรงกับทะเบียนวันที่ปกติ ต้องเพิ่มจากชื่อไฟล์ตรง ๆ
    for name in image_names(story["asset"], story["current"]["date"]):
        for token in _NUMBER.findall(name):
            allowed.add(token.rstrip(".,"))
    # ประโยคปฏิทินมาจาก evidence จริงผ่าน `_calendar_sentences` — เลขในประโยค
    # (เวลา น. / ค่าครั้งก่อน) เป็นส่วนหนึ่งของ story จึงเข้าทะเบียนทั้งชุด
    calendar = story.get("calendar")
    if calendar and calendar.get("sentences"):
        for sentence in calendar["sentences"]:
            for token in _NUMBER.findall(sentence):
                allowed.add(token.rstrip(".,"))
    dates = [story["current"]["date"], story["peak"]["date"], story["trough"]["date"],
             story["regime"]["flip_date"],
             story["display"]["start_date"], story["display"]["end_date"]]
    if channel:
        dates.append(channel["start_date"])
    dates += [zone["last_date"] for zone in story["zones"]]
    dates += [level["last_date"] for level in story["resistance"]]
    # วันล็อกของความจำข้ามวัน (#18ข) — โผล่ในวลี "โซนเดิมที่ใช้อ้างอิงมาตั้งแต่..."
    dates += [zone.get("locked_since") for zone in story["zones"]]
    dates += [level.get("locked_since") for level in story["resistance"]]
    if channel:
        dates.append(channel.get("locked_since"))
    for date_text in dates:
        if not date_text:
            continue
        year, _month, day = date_text.split("-")
        # ปีเดียวพอ — บท ชื่อไฟล์ภาพ และทะเบียนภายใน เป็น ค.ศ. ระบบเดียวกันหมด
        # ตั้งแต่ 08-11 (เดิมต้องขึ้นทะเบียนคู่ ค.ศ./พ.ศ. เพราะบทพิมพ์คนละระบบกับข้อมูล)
        allowed.add(year)
        allowed.add(str(int(day)))
    # ราคาปิดแบบปัดจำนวนเต็มที่ใช้เฉพาะในพาดหัว ("ทองยืน 4,342") — ค่าเดียวกับ
    # ราคาปิดจริง ไม่ใช่เลขใหม่ แต่รูปแบบต่างจาก money() จึงต้องขึ้นทะเบียนแยก
    allowed.add(f"{story['current']['close']:,.0f}")
    return allowed


def invalidation_pairs(story: dict) -> list[dict]:
    """ทุกคู่ (โซนเข้า ↔ จุดยกเลิกมุมมอง) ที่บทสไตล์ D พูดถึง — B-1

    **ต้องครบทุกคู่** ไม่ใช่เฉพาะคู่ที่เคยถูกฟ้อง · เพิ่มจุดเข้าแบบใหม่เมื่อไหร่
    ต้องมาต่อรายการที่นี่ด้วย ไม่งั้นด่านจะเงียบใส่คู่ใหม่แบบเดียวกับที่เกิดกับ
    "จุดเข้าซื้อ 1" รอบนี้
    """
    pairs = [{
        "label": f"จุดเข้าซื้อ {entry['rank']} (Demand Zone)",
        "zone_low": entry["zone_low"],
        "zone_high": entry["zone_high"],
        "invalidation": entry["invalidation"],
    } for entry in story.get("entries", [])]
    up = story["scenarios"].get("up")
    if up and up.get("entry_invalidation") is not None:
        pairs.append({
            "label": "จุดเข้าฝั่งขึ้น (Breakout-Continuation)",
            "zone_low": up["entry_low"],
            "zone_high": up["entry_high"],
            "invalidation": up["entry_invalidation"],
        })
    return pairs


def validate(markdown: str, story: dict) -> dict:
    """ด่านของสไตล์ D — fail-closed: findings ระดับ fatal ตัวเดียวก็ตก"""
    findings: list[dict] = []
    # ด่านความสอดคล้อง D-4.5 (ผู้ใช้เคาะ 08-10): ทิศ frontmatter=regime ·
    # ปี พ.ศ. ทั้งใบ · วันที่ Title=H1 — บทขัดกันเองต้องตกก่อนออกไฟล์
    findings.extend(consistency_gate.check(markdown, story))
    allowed = allowed_numbers(story)
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        for token in _NUMBER.findall(line):
            token = token.rstrip(".,")
            if token and token not in allowed:
                findings.append({
                    "rule": "number_not_in_story", "severity": "fatal", "line": line_number,
                    "message": f"เลข '{token}' ไม่อยู่ในทะเบียนของ story — "
                               "บทสไตล์ D พูดได้เฉพาะเลขที่อยู่บนภาพ",
                })
    for name in image_names(story["asset"], story["current"]["date"]):
        if f"({name})" not in markdown:
            findings.append({
                "rule": "missing_image", "severity": "fatal", "line": 1,
                "message": f"บทความไม่ได้อ้างภาพ {name} — สไตล์ D ต้องอ้างครบทั้งสองภาพ",
            })
    if story.get("entries") and "จุดเข้าซื้อ" not in markdown:
        findings.append({
            "rule": "entry_section", "severity": "fatal", "line": 1,
            "message": "story มีจุดเข้าซื้อ (SMC POI) แต่บทไม่มีหัวข้อนี้ — ผู้ใช้สั่งให้มีเสมอ",
        })
    if "ไม่ใช่คำทำนาย" not in markdown:
        findings.append({
            "rule": "scenario_disclaimer", "severity": "fatal", "line": 1,
            "message": "ไม่พบประโยคประกาศว่าฉากทัศน์เป็นเงื่อนไข ไม่ใช่คำทำนาย",
        })
    if "คำเตือนความเสี่ยง" not in markdown:
        findings.append({
            "rule": "risk_disclaimer", "severity": "fatal", "line": 1,
            "message": "ไม่พบส่วนคำเตือนความเสี่ยงท้ายบท — โครงบทอ้างอิงบังคับให้มี",
        })
    # 🔄 **กลับด้าน 2026-08-10** — เดิมห้ามมี frontmatter · ตอนนี้ **บังคับให้มี**
    # เพราะทุกสไตล์ต้องส่ง `title` เอง (คำสั่งผู้ใช้ + ทีมเว็บแนะนำให้ส่งเองมาแต่แรก)
    if not markdown.lstrip().startswith("---"):
        findings.append({
            "rule": "frontmatter_required", "severity": "fatal", "line": 1,
            "message": "บทสไตล์ D ต้องมี frontmatter พร้อมช่อง title",
        })
    elif not re.search(r"(?m)^title:\s*\S", markdown):
        findings.append({
            "rule": "frontmatter_required", "severity": "fatal", "line": 1,
            "message": "frontmatter ไม่มีช่อง title",
        })
    # สเปก SEO ของหัวหน้า 2026-08-10: Title tag กับ H1 **ต้องไม่เหมือนกัน** —
    # คนละหน้าที่ (Title = ช่องคำค้น ต้องนิ่ง · H1 = ช่องเล่าสาระของวัน)
    # เขียนชนกันเมื่อไหร่บทไม่ออก ไม่ใช่ออกไปแล้วค่อยรู้ตอนขึ้นเว็บ
    first_line = next((line for line in markdown.splitlines() if line.startswith("# ")), "")
    if first_line and headline_format.same_headline(seo_title(story), first_line[2:]):
        findings.append({
            "rule": "title_equals_h1", "severity": "fatal", "line": 1,
            "message": "Title tag กับ H1 เหมือนกัน — สเปก SEO บังคับให้หางต่างกัน",
        })
    # กฎเหล็ก: ปัจจัยพื้นฐานต้องมีแหล่งอ้างอิงเสมอ — มีย่อหน้าปฏิทินแล้วไม่มีวลีที่มา = ตก
    calendar_block = story.get("calendar")
    if calendar_block and calendar_block.get("sentences") \
            and CALENDAR_SOURCE_NOTE.strip() not in markdown:
        findings.append({
            "rule": "calendar_source_missing", "severity": "fatal", "line": 1,
            "message": "ย่อหน้าปัจจัยพื้นฐานยกตัวเลขจากปฏิทินแต่ไม่มีวลีบอกแหล่ง "
                       f"'{CALENDAR_SOURCE_NOTE.strip()}' — ต้องมีเหมือนสไตล์ A/B/C",
        })
    # 🐞 **A-1 (ทีมเว็บ 2026-08-09) — ด่านที่ผูกคำว่า "ปิด" เข้ากับสภาพจริงของแท่ง**
    # บททุกใบของสไตล์นี้เขียน "แท่งล่าสุดปิดที่ X" ⇒ ถ้าพิสูจน์ไม่ได้ว่าแท่งฐานปิดแล้ว
    # **บทตกด่าน ไม่ออกไฟล์** ไม่มีทางเลือก "ปล่อยผ่านพร้อมป้ายเตือน" เพราะป้ายเตือน
    # ไม่ได้ทำให้ตัวเลขในบทตรงกับกราฟบนหน้าเดียวกัน ซึ่งคือปัญหาที่แท้จริง
    # ด่านนี้**ไม่อ่านธง** `current.candle_state` มาตัดสิน แต่ให้ `candle_close.verify()`
    # ไล่คำนวณเวลาปิดจาก `config/market_calendar.json` ใหม่แล้วเทียบนาฬิกาจริงตอนตรวจ
    closed_detail = candle_close.verify(
        story.get("candle_basis"), asset=story["asset"],
        session_date=story["current"]["date"])
    if closed_detail:
        findings.append({
            "rule": "closed_candle_required", "severity": "fatal", "line": 1,
            "message": f"บทเรียกราคาแท่งล่าสุดว่า 'ปิด' แต่ {closed_detail}",
        })

    # 🐞 D-1 (08-07) → **B-1 (08-09): เดิมด่านนี้ตรวจคู่เดียว (โซน Retest ฝั่งขึ้น)**
    # ทีมเว็บจึงเจอ "จุดเข้าซื้อ 1" ที่จุดยกเลิกเท่ากับขอบล่างโซนเป๊ะหลุดออกไปได้
    # ⇒ ตอนนี้กวาด**ทุกคู่ในบท** ผ่านเกณฑ์กลางตัวเดียว (`chart_story.MIN_INVALIDATION_ATR`)
    # บทเรียนที่เกิดซ้ำในโปรเจกต์นี้: แก้เฉพาะตัวที่ฟ้องอย่างเดียวไม่พอ ต้องกวาดทั้งไฟล์
    for message in chart_story.invalidation_findings(
            invalidation_pairs(story), story["atr14"]):
        findings.append({
            "rule": "invalidation_inside_entry_zone", "severity": "fatal", "line": 1,
            "message": message,
        })

    # 🐞 **B-3.1 (08-09):** จำนวนครั้งที่บทอ้างต้องนับจากจุดที่อยู่ในโซนที่บทตีพิมพ์จริง
    # — เคยนับจากกลุ่มที่กว้างกว่าโซน 2 เท่า ทำให้บทอ้าง 7 ครั้งแต่ในโซนมีจริง 5 ครั้ง
    for zone in story["zones"]:
        touch_prices = zone.get("touch_prices")
        if touch_prices is None:
            findings.append({
                "rule": "zone_touch_evidence_missing", "severity": "fatal", "line": 1,
                "message": f"โซน {zone['mean']} ไม่มีรายการราคาที่ใช้นับจำนวนครั้ง "
                           "— ตัวเลข 'ถูกใช้อ้างอิง N ครั้ง' ต้องชี้กลับจุดจริงได้",
            })
            continue
        outside = [value for value in touch_prices
                   if not zone["low"] <= value <= zone["high"]]
        if outside or len(touch_prices) != zone["touches"]:
            findings.append({
                "rule": "zone_touch_count_mismatch", "severity": "fatal", "line": 1,
                "message": f"โซน {zone['low']}–{zone['high']} อ้างว่าถูกแตะ {zone['touches']} ครั้ง "
                           f"แต่มีจุดนอกโซน {len(outside)} จุด — บทพูดเกินสิ่งที่วัดได้",
            })
    char_count = len(re.sub(r"\s", "", markdown))
    if char_count < MIN_CHARS:
        findings.append({
            "rule": "style_length_floor", "severity": "fatal", "line": 1,
            "message": f"เนื้อหามี {char_count} อักขระ ต่ำกว่าเกณฑ์ {MIN_CHARS} ของสไตล์ D",
        })
    fatal_count = sum(1 for finding in findings if finding["severity"] == "fatal")
    return {
        "status": "pass" if fatal_count == 0 else "fail",
        "fatal_count": fatal_count,
        "char_count": char_count,
        "findings": findings,
    }
