"""นักเขียนสไตล์ H — แรงเทรนด์ระหว่างวัน M30

บทนี้ **ไม่ใช่** บทแบบ "อินดิเคเตอร์หลายตัวบอกซื้อ" — มันตอบสี่ข้อตามลำดับ:

    1. ตอนนี้ตลาดมีเทรนด์หรือยัง          (ADX)
    2. ถ้ามี ฝั่งไหนคุมทิศ                (DMI)
    3. ราคายังยืนฝั่งเดียวกับเส้นตามทิศไหม  (Supertrend)
    4. สัญญาณที่บอกว่ามุมมองนี้ไม่เป็นไปตามคาด (เส้น Supertrend ณ แท่งล่าสุด)

ภาษาที่ใช้ถูกล็อกด้วยด่านใน `intraday_writer_base`:
เขียน "ADX อยู่เหนือเกณฑ์ที่ระบบใช้จำแนกเทรนด์" ได้ · เขียน "ADX ให้สัญญาณซื้อ" ไม่ได้
เขียน "ATR กว้างขึ้น แปลว่าช่วงแกว่งกว้างขึ้น" ได้ · เขียน "ATR เป็นขาขึ้น" ไม่ได้

## รูปบทฉบับ 2026-08-14 (ผู้ใช้ส่งใบตัวอย่างมาทั้งใบ — เขียนตามถ้อยคำนั้น)

ต่างจากโครงเดิมหกจุด และทั้งหกอยู่ที่ *รูป* ไม่ใช่ *ตรรกะ*:

    พาดหัวคร่อมวันที่ด้วยวงเล็บ · กล่องหัวบทเป็น "สรุปภาพรวมตลาด" พร้อมจุดสีสถานะ ·
    หัวข้อที่มีเลขลดชั้นเป็น `###` · หัวข้อ 1 เป็นรายการสามข้อแทนร้อยแก้วสองย่อหน้า ·
    ถอดย่อหน้าเชื่อมภาพ (คำบรรยายใต้ภาพรับหน้าที่นั้นแทน) · หัวข้อท้ายเป็น
    "💡 บทสรุปการเทรด (Executive Summary)" ไม่มีเลขลำดับ

⚠️ **สองจุดที่ถ้อยคำในใบตัวอย่างถูกปรับ ไม่ได้ลอกทั้งดุ้น** — ทั้งคู่เป็นจุดที่ใบเดิม
ให้ ADX บอกทิศ ซึ่งชนกฎแกนของสไตล์นี้ (ทิศมาจาก DI เท่านั้น) และชน `_direction_abuse`:

    "ADX ยืนเหนือ 25 = เทรนด์ขาลงทรงพลัง"      → "แรงของแนวโน้มยังหนุนเต็ม"
    "ADX ต่ำกว่า 20 = แรงส่งฝั่งขายเริ่มแผ่ว"     → "แรงส่งของแนวโน้มเริ่มแผ่ว"

ความหมายที่ผู้ใช้ต้องการ (เกณฑ์ 25/20 คือสวิตช์ของรอบนี้) ยังอยู่ครบทั้งสองบรรทัด
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import headline_format  # noqa: E402
from tools import intraday_trend_story as story_module  # noqa: E402
from tools import intraday_writer_base as base  # noqa: E402
from tools import wcb_source  # noqa: E402

LETTER = "H"
STYLE_NAME = "H — แรงเทรนด์ระหว่างวัน"
STATES = story_module.STATES

S = story_module

# ------------------------------------------------------------------ รูปโครงของสไตล์นี้
#
# ค่าสี่ตัวนี้คือจุดที่ H แทนที่โครงกลางของ H/I/J (ดู `intraday_writer_base._spec_text`)
SECTION_PREFIX = "###"
BOX_HEAD = "## สรุปภาพรวมตลาด"
SUMMARY_HEAD = "### บทสรุปการเทรด (Executive Summary)"

# คำประจำสถานะ — ใช้ทั้งกล่องหัวบท พาดหัว ป้ายบนภาพ และด่าน `headline_matches_state`
# **ชุดเดียวทุกที่โดยตั้งใจ** ถ้าแยกชุดกันเมื่อไหร่ พาดหัวจะหลุดจากสถานะได้เงียบ ๆ
STATE_LABEL = {
    S.BULL_TREND: "ขาขึ้นชัดเจน",
    S.BEAR_TREND: "ขาลงชัดเจน",
    S.EARLY_BULL: "เริ่มเอนขึ้น",
    S.EARLY_BEAR: "เริ่มเอนลง",
    S.TRANSITION: "ช่วงเปลี่ยนผ่าน",
    S.NO_TREND: "ไร้ทิศ",
}
STATE_NOTE = {
    S.BULL_TREND: "สัญญาณทางเทคนิคยืนยันครบทุกมิติ",
    S.BEAR_TREND: "สัญญาณทางเทคนิคยืนยันครบทุกมิติ",
    S.EARLY_BULL: "ทิศเริ่มชัด แต่แรงเทรนด์ยังไม่ยืนยัน",
    S.EARLY_BEAR: "ทิศเริ่มชัด แต่แรงเทรนด์ยังไม่ยืนยัน",
    S.TRANSITION: "หลักฐานสองชิ้นยังขัดกัน",
    S.NO_TREND: "ยังไม่มีแรงเทรนด์ ตลาดแกว่งในกรอบ",
}
# คำเรียกสถานะในบทสรุปท้ายบท — ใบตัวอย่างใช้ "เต็มตัว" ที่นี่ ต่างจากป้าย "ชัดเจน"
# ในกล่องหัวบทโดยเจตนา (กล่องรายงานสถานะ · บทสรุปเล่าความหมายของมัน)
SUMMARY_LABEL = dict(STATE_LABEL, **{S.BULL_TREND: "ขาขึ้นเต็มตัว",
                                    S.BEAR_TREND: "ขาลงเต็มตัว"})
# คำอังกฤษกำกับสถานะในบทสรุปท้ายบท (ตามใบตัวอย่าง — `"ขาลงเต็มตัว (Bear Trend)"`)
STATE_ENGLISH = {
    S.BULL_TREND: "Bull Trend", S.BEAR_TREND: "Bear Trend",
    S.EARLY_BULL: "Early Bull", S.EARLY_BEAR: "Early Bear",
    S.TRANSITION: "Transition", S.NO_TREND: "No Trend",
}
HEADLINE_KEYWORD = {
    S.BULL_TREND: "ขาขึ้น",
    S.BEAR_TREND: "ขาลง",
    S.EARLY_BULL: "ยังไม่ยืนยัน",
    S.EARLY_BEAR: "ยังไม่ยืนยัน",
    S.TRANSITION: "ช่วงเปลี่ยนผ่าน",
    S.NO_TREND: "ยังไม่มีแรงเทรนด์",
}
# คำที่ใช้เรียก "ผู้คุมทิศ" — มาจาก DI เท่านั้น
HOLDER = {"up": "ฝั่งซื้อ", "down": "ฝั่งขาย", "flat": "ยังไม่มีฝั่งใดนำชัด"}
FORCE = {"up": "แรงซื้อ", "down": "แรงขาย"}
# คำฝั่งแบบสากลที่ใบตัวอย่างใช้ ("ฝั่ง Sell ยังคงเป็นผู้คุมเกม")
SIDE_EN = {"up": "Buy", "down": "Sell"}


def _profile(story: dict) -> dict:
    return wcb_source.profile_for(story["asset"])


def _unit(story: dict) -> str:
    """หน่วยรูปสั้นสำหรับต่อท้ายตัวเลขในรายการ — USD/THB เป็น 'บาท' ไม่ใช่ 'ดอลลาร์'"""
    return _profile(story)["unit_short"]


def _above(story: dict) -> bool:
    return story["close"] > story["supertrend"]["value"]


# ------------------------------------------------------------------------ พาดหัวและกล่อง

def title_tail(story: dict) -> str:
    return "แรงเทรนด์ M30 จาก DMI และ ADX"


def h1_tail(story: dict) -> str:
    tails = {
        S.BULL_TREND: f"M30 ขาขึ้นครองตลาด ฝั่ง {SIDE_EN['up']} ยังได้เปรียบ",
        S.BEAR_TREND: f"M30 ขาลงครองตลาด ฝั่ง {SIDE_EN['down']} ยังได้เปรียบ",
        S.EARLY_BULL: "M30 เริ่มเอนขึ้น แต่แรงเทรนด์ยังไม่ยืนยัน",
        S.EARLY_BEAR: "M30 เริ่มเอนลง แต่แรงเทรนด์ยังไม่ยืนยัน",
        S.TRANSITION: "M30 อยู่ในช่วงเปลี่ยนผ่าน ยังไม่มีฝั่งใดคุมเกม",
        S.NO_TREND: "M30 ยังไม่มีแรงเทรนด์ รอตลาดเลือกทาง",
    }
    return tails[story["state"]]


def h1_line(story: dict) -> str:
    """พาดหัวของ H — คร่อมวันที่ด้วยวงเล็บตามใบตัวอย่าง 08-14"""
    return headline_format.h1(story["asset"], story["bar_date"], h1_tail(story),
                              wrap_date=True)


def stamp_line(story: dict) -> str:
    words = base.tf_words(story)
    return (f"ข้อมูล ณ แท่งเทียน {words['short']} ({words['front']}) ปิดตลาดเวลา "
            f"{base.bar_clock(story).replace('.', ':')} น. (เวลาไทย)")


def headline_keyword(story: dict) -> str:
    return HEADLINE_KEYWORD[story["state"]]


def state_phrase(story: dict) -> str:
    # กล่องหัวบทเป็นภาษาคนอ่าน ไม่แสดงรหัสภายใน เช่น `(BEAR_TREND)`
    return STATE_LABEL[story["state"]]


def timeframe_phrase(story: dict) -> str:
    words = base.tf_words(story)
    return f"{words['bar']} (Timeframe {words['front']})"


def _invalidation_note(story: dict) -> str:
    if story["direction"] is None:
        return "ระดับที่ระบบใช้ตัดสินเมื่อสถานะเริ่มชี้ทิศ"
    up = story["direction"] == "up"
    return f"ราคา{'ต่ำกว่า' if up else 'สูงกว่า'}นี้ เทรนด์{'ขาขึ้น' if up else 'ขาลง'}เสียทรง"


def invalidation_label(story: dict) -> str:
    """ชื่อระดับตามบทบาทบนกราฟ ไม่ใช้ศัพท์ระบบกับคนอ่าน

    ระดับล้มมุมมองของขาลงอยู่เหนือราคา จึงทำหน้าที่เป็นแนวต้านที่หากผ่านได้
    โครงสร้างเทรนด์จะเปลี่ยน ส่วนขาขึ้นใช้แนวรับด้วยหลักเดียวกัน
    """
    return {"down": "แนวต้านเปลี่ยนเทรนด์",
            "up": "แนวรับเปลี่ยนเทรนด์"}.get(
        story["direction"], "ระดับเปลี่ยนเทรนด์")


def box_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    return [
        BOX_HEAD,
        f"* **สถานะเทรนด์:** **{state_phrase(story)}** — "
        f"{STATE_NOTE[story['state']]}",
        f"* **กรอบเวลาวิเคราะห์:** {timeframe_phrase(story)}",
        f"* **{invalidation_label(story)}:** "
        f"**{money(story['invalidation']['level'])} {_unit(story)}** "
        f"({_invalidation_note(story)})",
    ]


def excerpt_clauses(story: dict) -> list[str]:
    money = base.money_for(story)
    return [f"{_profile(story)['short_name']}ปิดแท่ง M30 ที่ {money(story['close'])} "
            f"{_unit(story)}",
            f"ระบบจัดสถานะรอบนี้เป็น{STATE_LABEL[story['state']]}",
            f"ADX อยู่ที่ {base.one(story['dmi']['adx'])}",
            "อ่านหลักฐาน DMI Supertrend และ ATR พร้อมภาพประกอบ"]


# ------------------------------------------------------------------------ หัวข้อ 1

def h2_overview(story: dict) -> str:
    return f"ภาพรวมโครงสร้างราคาและโมเมนตัม ({base.tf_words(story)['front']})"


OVERVIEW_CLAUSE = {
    S.BULL_TREND: "โดยโครงสร้างราคายังคงได้แรงหนุนในฝั่งขาขึ้นอย่างสมบูรณ์ "
                  "ซึ่งยืนยันผ่าน 3 เครื่องมือทางเทคนิคหลัก:",
    S.BEAR_TREND: "โดยโครงสร้างราคายังคงถูกกดดันในฝั่งขาลงอย่างสมบูรณ์ "
                  "ซึ่งยืนยันผ่าน 3 เครื่องมือทางเทคนิคหลัก:",
    S.EARLY_BULL: "โดยโครงสร้างราคาเริ่มเอนขึ้น แต่ยังไม่ครบเงื่อนไขที่ระบบเรียกว่า"
                  "เทรนด์เต็มตัว อ่านได้จาก 3 เครื่องมือทางเทคนิคหลัก:",
    S.EARLY_BEAR: "โดยโครงสร้างราคาเริ่มเอนลง แต่ยังไม่ครบเงื่อนไขที่ระบบเรียกว่า"
                  "เทรนด์เต็มตัว อ่านได้จาก 3 เครื่องมือทางเทคนิคหลัก:",
    S.TRANSITION: "โดยหลักฐานสองชิ้นยังพูดไม่ตรงกัน ระบบจึงไม่ประกาศทิศให้รอบนี้ "
                  "อ่านได้จาก 3 เครื่องมือทางเทคนิคหลัก:",
    S.NO_TREND: "โดยแรงของแนวโน้มยังต่ำกว่าเกณฑ์ที่ระบบใช้จำแนก ตลาดจึงอยู่ในภาวะ"
                "แกว่งในกรอบ อ่านได้จาก 3 เครื่องมือทางเทคนิคหลัก:",
}


def _dmi_sentence(story: dict) -> str:
    dmi = story["dmi"]
    if dmi["direction"] == "flat":
        return (f"ค่า +DI อยู่ที่ **{base.one(dmi['plus_di'])}** กับ -DI ที่ "
                f"**{base.one(dmi['minus_di'])}** ยังไม่ห่างกันพอให้ฝั่งใดขึ้นนำในรอบนี้")
    lead, lag = (("-DI", "+DI") if dmi["direction"] == "down" else ("+DI", "-DI"))
    high, low = max(dmi["plus_di"], dmi["minus_di"]), min(dmi["plus_di"], dmi["minus_di"])
    return (f"ค่า {lead} อยู่ที่ **{base.one(high)}** พุ่งสูงกว่า {lag} ที่ "
            f"**{base.one(low)}** อย่างชัดเจน สะท้อนว่า{FORCE[dmi['direction']]}"
            f"เป็นผู้ควบคุมการเคลื่อนไหวในรอบนี้")


def _adx_move(story: dict) -> str:
    """คำกริยาที่บอกว่า ADX ขยับไปทางไหน — **ความแข็งแรง ไม่ใช่ทิศราคา**"""
    dmi = story["dmi"]
    if dmi["previous_adx"] is None:
        return "อยู่ที่"
    if dmi["adx"] > dmi["previous_adx"]:
        return "ไต่ระดับขึ้นมาอยู่ที่"
    if dmi["adx"] < dmi["previous_adx"]:
        return "ย่อลงมาอยู่ที่"
    return "ทรงตัวอยู่ที่"


def _adx_sentence(story: dict) -> str:
    dmi, thresholds = story["dmi"], story["thresholds"]
    value = f"ค่า ADX {_adx_move(story)} **{base.one(dmi['adx'])}**"
    if dmi["adx"] >= thresholds["trend"]:
        return (f"{value} (ข้ามเกณฑ์ความแข็งแกร่งที่ {base.plain(thresholds['trend'])}) "
                f"ยืนยันว่าการเคลื่อนไหวรอบนี้มีแรงตามทิศรองรับ "
                f"ไม่ใช่การแกว่งไร้ทิศทาง (Sideways)")
    if dmi["adx"] >= thresholds["no_trend"]:
        return (f"{value} ซึ่งอยู่ระหว่างเกณฑ์ {base.plain(thresholds['no_trend'])} กับ "
                f"{base.plain(thresholds['trend'])} แปลว่าเริ่มมีแรงตามทิศแล้ว "
                f"แต่ยังไม่ถึงระดับที่ระบบเรียกว่าเทรนด์เต็มตัว")
    return (f"{value} ต่ำกว่าเกณฑ์ {base.plain(thresholds['no_trend'])} "
            f"ที่ระบบใช้เป็นเส้นแบ่งว่ามีแรงเทรนด์หรือไม่ "
            f"รอบนี้จึงอ่านเป็นการแกว่งในกรอบ (Sideways) มากกว่าการเดินเป็นทาง")


def _supertrend_sentence(story: dict) -> str:
    money = base.money_for(story)
    line = f"**{money(story['supertrend']['value'])} {_unit(story)}**"
    stance = "เหนือ" if _above(story) else "ใต้"
    if story["supertrend"]["flipped"]:
        return f"ราคาเพิ่งพลิกมาปิดอยู่{stance}เส้น Supertrend ({line}) ในแท่งนี้"
    return f"ราคายังคงปิดรักษาระดับอยู่{stance}เส้น Supertrend ({line}) อย่างต่อเนื่อง"


def overview_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    profile, words = _profile(story), base.tf_words(story)
    lead = (f"ราคา{profile['thai_name']} ({profile['symbol']}) {words['thai']} "
            f"ล่าสุดปิดที่ **{money(story['close'])} {_unit(story)}** "
            f"{OVERVIEW_CLAUSE[story['state']]}")
    return [lead, "",
            f"1. **การครองทิศทาง (DMI):** {_dmi_sentence(story)}",
            f"2. **ความแรงของเทรนด์ (ADX):** {_adx_sentence(story)}",
            f"3. **แนวโน้มราคา (Supertrend):** {_supertrend_sentence(story)}"]


# ------------------------------------------------------------------------ หัวข้อ 2

def h2_evidence(story: dict) -> str:
    if story["state"] in (S.BULL_TREND, S.BEAR_TREND):
        return "เจาะลึก 3 หลักฐานยืนยันความแข็งแกร่ง"
    return "เจาะลึก 3 หลักฐานทางเทคนิค"


def _evidence_intro(story: dict) -> str:
    if story["direction"] is None:
        return "เมื่อแยกพิจารณาเครื่องมือทางเทคนิคแต่ละตัว จะเห็นหน้าที่ของแต่ละชิ้นดังนี้:"
    return (f"เมื่อแยกพิจารณาเครื่องมือทางเทคนิคแต่ละตัว "
            f"จะพบโครงสร้างที่สนับสนุน{HOLDER[story['direction']]}ดังนี้:")


def _adx_evidence_tail(story: dict) -> str:
    dmi, thresholds = story["dmi"], story["thresholds"]
    if dmi["adx"] >= thresholds["trend"]:
        if thresholds["trend"] in story["adx_crossed"]:
            return (f"การข้ามระดับ {base.plain(thresholds['trend'])} ขึ้นมา "
                    f"เป็นการยืนยันว่าแรงของเทรนด์รอบนี้แข็งแกร่งขึ้น")
        return (f"การยืนเหนือระดับ {base.plain(thresholds['trend'])} ต่อเนื่อง "
                f"ยืนยันว่าแรงของแนวโน้มรอบนี้ยังอยู่ครบ")
    if dmi["adx"] >= thresholds["no_trend"]:
        return (f"ยังอยู่ใต้ระดับ {base.plain(thresholds['trend'])} "
                f"ที่ระบบใช้แบ่งว่าแรงพอเรียกว่าเทรนด์แล้วหรือยัง")
    return (f"ยังอยู่ใต้ระดับ {base.plain(thresholds['no_trend'])} "
            f"ที่ระบบใช้แบ่งว่ามีแรงเทรนด์หรือไม่")


def _atr_tail(story: dict) -> str:
    if story["atr"]["rising"]:
        return "สะท้อนว่าช่วงแกว่งต่อแท่งกำลังกว้างขึ้น"
    if story["direction"] is None:
        return "สะท้อนว่าช่วงแกว่งต่อแท่งกำลังแคบลง"
    frame = "ขาขึ้น" if story["direction"] == "up" else "ขาลง"
    return f"สะท้อนว่าราคาเริ่มเข้าสู่ช่วงพักตัวสะสมแรงในกรอบ{frame}"


def evidence_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    dmi, volatility = story["dmi"], story["atr"]
    atr_percent = volatility["value"] / story["close"] * 100 if story["close"] else 0.0
    lead, lag = (("-DI", "+DI") if dmi["direction"] == "down" else ("+DI", "-DI"))
    high, low = max(dmi["plus_di"], dmi["minus_di"]), min(dmi["plus_di"], dmi["minus_di"])
    if dmi["direction"] == "flat":
        dmi_text = (f"ค่า +DI ({base.one(dmi['plus_di'])}) กับ -DI "
                    f"({base.one(dmi['minus_di'])}) ยังไม่ห่างกันพอ "
                    f"รอบนี้จึงยังไม่มีฝั่งใดคุมเกม")
    else:
        dmi_text = (f"ค่า {lead} ({base.one(high)}) อยู่เหนือ {lag} ({base.one(low)}) "
                    f"อย่างขาดลอย ฝั่ง {SIDE_EN[dmi['direction']]} ยังคงเป็นผู้คุมเกม")
    adx_move = (f"ปรับตัวเพิ่มขึ้นจาก {base.one(dmi['previous_adx'])} มาอยู่ที่"
                if dmi["previous_adx"] is not None and dmi["adx"] > dmi["previous_adx"]
                else f"ปรับตัวลดลงจาก {base.one(dmi['previous_adx'])} มาอยู่ที่"
                if dmi["previous_adx"] is not None and dmi["adx"] < dmi["previous_adx"]
                else "อยู่ที่")
    return [
        _evidence_intro(story), "",
        f"* **คุมเชิงทิศทาง (DMI {base.plain(dmi['length'])}):** {dmi_text}",
        f"* **ความแรงเทรนด์ (ADX {base.plain(dmi['length'])}):** {adx_move} "
        f"**{base.one(dmi['adx'])}** {_adx_evidence_tail(story)}",
        f"* **ความผันผวน (ATR {base.plain(volatility['length'])}):** ค่า ATR อยู่ที่ "
        f"**{money(volatility['value'])} {_unit(story)} ({base.two(atr_percent)}%)** "
        f"ซึ่ง{'กว้างขึ้น' if volatility['rising'] else 'แคบลง'}จากแท่งก่อนหน้า "
        f"{_atr_tail(story)}",
    ]


# ------------------------------------------------------------------------ หัวข้อ 3

def h2_watch(story: dict) -> str:
    return "ระดับราคาและเงื่อนไขตัดสินใจ (Key Levels)"


def _level_name(story: dict) -> str:
    return {"up": "ด่านรับสำคัญ", "down": "ด่านต้านสำคัญ"}.get(
        story["direction"], "ระดับชี้ขาด")


def watch_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    thresholds, words = story["thresholds"], base.tf_words(story)
    gap = abs(story["close"] - story["invalidation"]["level"])
    if story["direction"] is None:
        hold = (f"เมื่อราคาปิดไปยืนฝั่งเดียวกับเส้นนี้ พร้อมกับที่ ADX ขึ้นเหนือเกณฑ์ "
                f"{base.plain(thresholds['no_trend'])} ระบบจึงจะเริ่มจัดสถานะให้มีทิศ")
    else:
        side = "ใต้" if story["direction"] == "up" else "เหนือ"
        hold = (f"ตราบใดที่ราคายังไม่สามารถปิดแท่ง {words['front']} {side}ระดับนี้ได้ "
                f"ภาพรวมยังคงเน้นฝั่ง {SIDE_EN[story['direction']]} เป็นหลัก")
    return [
        f"* **{_level_name(story)} (Invalidation Point): "
        f"{money(story['invalidation']['level'])} {_unit(story)}**",
        f"  * เส้น Supertrend อยู่ห่างจากราคาปัจจุบันประมาณ **{money(gap)} "
        f"{_unit(story)}**",
        f"  * {hold}",
        "* **เกณฑ์วัดแรงโมเมนตัม (ADX Thresholds):**",
        f"  * หาก ADX ยืนเหนือ **{base.plain(thresholds['trend'])}** "
        f"= แรงของแนวโน้มยังหนุนเต็ม",
        f"  * หาก ADX ปรับตัวลดลงต่ำกว่า **{base.plain(thresholds['no_trend'])}** "
        f"= แรงส่งของแนวโน้มเริ่มแผ่ว ตลาดอาจเข้าสู่การพักตัวออกข้าง",
    ]


# ------------------------------------------------------------------------ หัวข้อ 4

def h2_invalidation(story: dict) -> str:
    return "สัญญาณเตือนเมื่อมุมมองเปลี่ยน (Invalidation Scenario)"


def invalidation_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    thresholds, words = story["thresholds"], base.tf_words(story)
    level = f"{money(story['invalidation']['level'])} {_unit(story)}"
    if story["direction"] is None:
        return [
            "รอบนี้ระบบยังไม่ประกาศทิศ จึงยังไม่มีมุมมองให้เสีย "
            "สิ่งที่จะเปลี่ยนภาพมี 2 เงื่อนไข:", "",
            f"1. **แท่ง {words['front']} ปิดไปยืนฝั่งเดียวกับเส้น Supertrend ที่ "
            f"{level}:** หลักฐานชิ้นที่สามจะกลับมาพูดตรงกับ DMI อีกครั้ง",
            f"2. **ADX ยืนเหนือ {base.plain(thresholds['no_trend'])}:** "
            f"แปลว่าแรงกลับเข้ามาแล้ว ระบบจึงจะเริ่มจัดสถานะให้มีทิศ",
        ]
    up = story["direction"] == "up"
    return [
        f"โครงสร้าง{'ขาขึ้น' if up else 'ขาลง'}จะถูกยกเลิกหรือลดน้ำหนักลง "
        f"ทันทีที่เกิด 2 เงื่อนไขนี้:", "",
        f"1. **แท่ง {words['front']} ปิด{'ใต้' if up else 'เหนือ'} {level}:** "
        f"ถือเป็นการเบรกเกราะ{'รับ' if up else 'ต้าน'} Supertrend "
        f"สภาพ{'ขาขึ้น' if up else 'ขาลง'}จะถูกยกเลิกทันที "
        f"และเปลี่ยนเข้าสู่เฟสพักตัวหรือกลับตัว",
        f"2. **ADX ร่วงต่ำกว่า {base.plain(thresholds['no_trend'])}:** "
        f"สะท้อนว่าแรงส่ง (Momentum) หมดลง "
        f"แม้ราคาจะยังไม่เบรกแนว{'รับ' if up else 'ต้าน'} "
        f"แต่การเก็งกำไรฝั่ง {SIDE_EN[story['direction']]} จะเริ่มเสียเปรียบ",
    ]


# ------------------------------------------------------------------------ หัวข้อสรุป

def summary_head(story: dict) -> str:
    return SUMMARY_HEAD


def summary_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    profile, words = _profile(story), base.tf_words(story)
    head = (f"กราฟ{profile['thai_name']} {words['front']} อยู่ในสภาวะ "
            f"**\"{SUMMARY_LABEL[story['state']]} ({STATE_ENGLISH[story['state']]})\"**")
    level = f"**{money(story['invalidation']['level'])} {_unit(story)}**"
    tails = {
        S.BULL_TREND: f"ทั้งในมิติทิศทางและแรงส่ง การย่อตัวลงมาระหว่างทาง (Pullback) "
                      f"ยังมองเป็นเพียง **\"การพักตัวในกรอบขาขึ้น\"** เพื่อไปต่อ "
                      f"จนกว่าจะมีแท่งเทียนปิดหลุดใต้ {level} ลงมา",
        S.BEAR_TREND: f"ทั้งในมิติทิศทางและแรงส่ง การดีดตัวสลับขึ้นมาระหว่างทาง (Rebound) "
                      f"ยังมองเป็นเพียง **\"การพักตัวในกรอบขาลง\"** เพื่อลงต่อ "
                      f"จนกว่าจะมีแท่งเทียนปิดยืนเหนือ {level} ได้สำเร็จ",
        S.EARLY_BULL: f"ทิศเริ่มชัดแล้วแต่แรงส่งยังไม่ถึงเกณฑ์ที่ระบบเรียกว่าเทรนด์เต็มตัว "
                      f"การรอให้ ADX ยืนเหนือ {base.plain(story['thresholds']['trend'])} "
                      f"ก่อน จึงเป็นการอ่านที่ตรงกับหลักฐานมากกว่าการสรุปไปก่อน",
        S.EARLY_BEAR: f"ทิศเริ่มชัดแล้วแต่แรงส่งยังไม่ถึงเกณฑ์ที่ระบบเรียกว่าเทรนด์เต็มตัว "
                      f"การรอให้ ADX ยืนเหนือ {base.plain(story['thresholds']['trend'])} "
                      f"ก่อน จึงเป็นการอ่านที่ตรงกับหลักฐานมากกว่าการสรุปไปก่อน",
        S.TRANSITION: "หลักฐานสองชิ้นยังพูดไม่ตรงกัน สิ่งที่ระบบทำคือรอ ไม่ใช่เลือกข้างให้ "
                      "รอบถัดไปที่ทั้งสองชิ้นกลับมาพูดตรงกันจะเป็นรอบที่มีข้อสรุปจริง",
        S.NO_TREND: "แรงของแนวโน้มยังต่ำกว่าเกณฑ์ที่ระบบใช้จำแนก "
                    "การเคลื่อนไหวที่เห็นจึงเป็นการแกว่งในกรอบมากกว่าการเดินเป็นทาง "
                    "รอบนี้ยังไม่มีข้อสรุปเรื่องทิศให้ประกาศ",
    }
    return [f"{head} {tails[story['state']]}"]


# ------------------------------------------------------------------------- ภาพประกอบ

def badge_text(story: dict) -> str:
    """ป้ายสถานะบนภาพ — ข้อความไทยชุดเดียวกับกล่องหัวบท

    ใบตัวอย่าง 08-14 สั่งถอด `BEAR_TREND` ตัวพิมพ์ใหญ่ติดขีดล่างออกจากภาพ เพราะมัน
    อ่านเหมือนชื่อตัวแปรในโค้ด · ยังคงหลัก "ป้ายยกมาจากสถานะ ไม่ตีความใหม่บนภาพ"
    เพราะข้อความมาจาก `STATE_LABEL` ตัวเดียวกับที่บทใช้ ไม่ใช่คำที่ตัววาดคิดเอง
    """
    return f"สถานะ: {STATE_LABEL[story['state']]}"


def _hero_reading(story: dict) -> str:
    return {"up": "แสดงแรงหนุนจากเส้น Supertrend และจุดตัดสินใจสำคัญ",
            "down": "แสดงการกดดันของเส้น Supertrend และจุดตัดสินใจสำคัญ"}.get(
        story["direction"], "แสดงตำแหน่งราคาเทียบเส้น Supertrend และจุดตัดสินใจสำคัญ")


def hero_figure(story: dict) -> dict:
    profile, words = _profile(story), base.tf_words(story)
    return {
        "title": f"{profile['symbol']} {words['front']} พร้อมเส้น Supertrend",
        "purpose": "แสดงว่าราคายืนฝั่งไหนของเส้นตามทิศ และสถานะที่ระบบจัดให้",
        "alt": f"กราฟ {profile['symbol']} {words['thai']} พร้อมเส้น Supertrend "
               f"และสถานะแรงเทรนด์",
        "caption": f"กราฟ {profile['symbol']} ({words['front']}) {_hero_reading(story)}",
    }


def evidence_figure(story: dict) -> dict:
    profile, words = _profile(story), base.tf_words(story)
    reading = ("ยืนยันความแข็งแกร่งของเทรนด์"
               if story["state"] in (S.BULL_TREND, S.BEAR_TREND)
               else "บอกทิศ แรง และความกว้างของการแกว่งในรอบนี้")
    return {
        "title": f"แผงหลักฐาน DMI ADX และ ATR ของ {profile['symbol']} {words['front']}",
        "purpose": "แยกให้เห็นว่าหลักฐานแต่ละชิ้นทำหน้าที่คนละอย่าง",
        "alt": f"แผงแสดงเส้น DMI และ ADX พร้อมค่า ATR ของ {profile['symbol']} "
               f"{words['thai']}",
        "caption": f"แผงเครื่องมือ DMI, ADX และ ATR ของ {profile['symbol']} "
                   f"({words['front']}) {reading}",
    }


# ------------------------------------------------------------------------- ด่านและทะเบียน

def number_tokens(story: dict) -> set[str]:
    money = base.money_for(story)
    dmi, trend_line, volatility = story["dmi"], story["supertrend"], story["atr"]
    tokens = {
        base.one(dmi["plus_di"]), base.one(dmi["minus_di"]), base.one(dmi["adx"]),
        base.plain(dmi["length"]), base.plain(trend_line["length"]),
        base.plain(trend_line["multiplier"]), base.plain(volatility["length"]),
        base.plain(story["thresholds"]["trend"]),
        base.plain(story["thresholds"]["no_trend"]),
        money(trend_line["value"]), money(volatility["value"]),
        money(abs(story["close"] - story["invalidation"]["level"])),
        base.two(volatility["value"] / story["close"] * 100 if story["close"] else 0.0),
    }
    if dmi["previous_adx"] is not None:
        tokens.add(base.one(dmi["previous_adx"]))
    return tokens


def required_headings(story: dict) -> list[str]:
    return [BOX_HEAD, h2_overview(story), h2_evidence(story), h2_watch(story),
            h2_invalidation(story), SUMMARY_HEAD]


def render_article(story: dict) -> str:
    return base.render_article(story, sys.modules[__name__])


def validate(markdown: str, story: dict) -> dict:
    return base.validate(markdown, story, sys.modules[__name__])
