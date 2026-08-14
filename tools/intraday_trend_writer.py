"""นักเขียนสไตล์ H — แรงเทรนด์ระหว่างวัน M30

บทนี้ **ไม่ใช่** บทแบบ "อินดิเคเตอร์หลายตัวบอกซื้อ" — มันตอบสี่ข้อตามลำดับ:

    1. ตอนนี้ตลาดมีเทรนด์หรือยัง          (ADX)
    2. ถ้ามี ฝั่งไหนคุมทิศ                (DMI)
    3. ราคายังยืนฝั่งเดียวกับเส้นตามทิศไหม  (Supertrend)
    4. สัญญาณที่บอกว่ามุมมองนี้ไม่เป็นไปตามคาด (เส้น Supertrend ณ แท่งล่าสุด)

ภาษาที่ใช้ถูกล็อกด้วยด่านใน `intraday_writer_base`:
เขียน "ADX อยู่เหนือเกณฑ์ที่ระบบใช้จำแนกเทรนด์" ได้ · เขียน "ADX ให้สัญญาณซื้อ" ไม่ได้
เขียน "ATR กว้างขึ้น แปลว่าช่วงแกว่งกว้างขึ้น" ได้ · เขียน "ATR เป็นขาขึ้น" ไม่ได้
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import intraday_trend_story as story_module  # noqa: E402
from tools import intraday_writer_base as base  # noqa: E402
from tools import wcb_source  # noqa: E402

LETTER = "H"
STYLE_NAME = "H — แรงเทรนด์ระหว่างวัน"
STATES = story_module.STATES

S = story_module

# คำประจำสถานะ — ใช้ทั้งในกล่องหัวบท พาดหัว และด่าน `headline_matches_state`
# **ตัวเดียวกันทั้งสามที่โดยตั้งใจ** ถ้าแยกชุดกันเมื่อไหร่ พาดหัวจะหลุดจากสถานะได้เงียบ ๆ
STATE_PHRASE = {
    S.BULL_TREND: "ภาวะเทรนด์ขาขึ้นที่มีแรงยืนยันครบเงื่อนไข",
    S.BEAR_TREND: "ภาวะเทรนด์ขาลงที่มีแรงยืนยันครบเงื่อนไข",
    S.EARLY_BULL: "ทิศเริ่มเอนขึ้นแต่แรงเทรนด์ยังไม่ยืนยัน",
    S.EARLY_BEAR: "ทิศเริ่มเอนลงแต่แรงเทรนด์ยังไม่ยืนยัน",
    S.TRANSITION: "ช่วงเปลี่ยนผ่าน หลักฐานสองชิ้นยังขัดกัน",
    S.NO_TREND: "ยังไม่มีแรงเทรนด์ ตลาดแกว่งไร้ทิศ",
}
HEADLINE_KEYWORD = {
    S.BULL_TREND: "ภาวะเทรนด์ขาขึ้น",
    S.BEAR_TREND: "ภาวะเทรนด์ขาลง",
    S.EARLY_BULL: "ยังไม่ยืนยัน",
    S.EARLY_BEAR: "ยังไม่ยืนยัน",
    S.TRANSITION: "ช่วงเปลี่ยนผ่าน",
    S.NO_TREND: "ยังไม่มีแรงเทรนด์",
}
# คำที่ใช้เรียก "ผู้คุมทิศ" — มาจาก DI เท่านั้น
HOLDER = {"up": "ฝั่งซื้อ", "down": "ฝั่งขาย", "flat": "ยังไม่มีฝั่งใดนำชัด"}


def _profile(story: dict) -> dict:
    return wcb_source.profile_for(story["asset"])


def title_tail(story: dict) -> str:
    return f"แรงเทรนด์ M30 จาก DMI และ ADX"


def h1_tail(story: dict) -> str:
    name = _profile(story)["short_name"]
    tails = {
        S.BULL_TREND: f"{name} M30 เข้าสู่ภาวะเทรนด์ขาขึ้น {HOLDER['up']}ยังคุมจังหวะ",
        S.BEAR_TREND: f"{name} M30 เข้าสู่ภาวะเทรนด์ขาลง {HOLDER['down']}ยังคุมจังหวะ",
        S.EARLY_BULL: f"{name} M30 เริ่มเอนขึ้น แต่แรงเทรนด์ยังไม่ยืนยัน",
        S.EARLY_BEAR: f"{name} M30 เริ่มเอนลง แต่แรงเทรนด์ยังไม่ยืนยัน",
        S.TRANSITION: f"{name} M30 อยู่ในช่วงเปลี่ยนผ่านของแนวโน้ม",
        S.NO_TREND: f"{name} M30 ยังไม่มีแรงเทรนด์ รอตลาดเลือกทาง",
    }
    return tails[story["state"]]


def headline_keyword(story: dict) -> str:
    return HEADLINE_KEYWORD[story["state"]]


def state_phrase(story: dict) -> str:
    return f"`{story['state']}` — {STATE_PHRASE[story['state']]}"


def timeframe_phrase(story: dict) -> str:
    words = base.tf_words(story)
    return f"{words['bar']} ({words['front']}) ที่ปิดแล้ว"


def excerpt_clauses(story: dict) -> list[str]:
    money = base.money_for(story)
    return [f"{_profile(story)['short_name']}ปิดแท่ง M30 ที่ {money(story['close'])} ดอลลาร์",
            f"ระบบจัดสถานะเป็น{STATE_PHRASE[story['state']]}",
            f"ADX อยู่ที่ {base.one(story['dmi']['adx'])}",
            "อ่านหลักฐาน DMI Supertrend และ ATR พร้อมภาพประกอบ"]


def h2_overview(story: dict) -> str:
    return f"ภาพรวมแรงเทรนด์บน {base.tf_words(story)['front']} ตอนนี้"


def overview_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    profile = _profile(story)
    words = base.tf_words(story)
    dmi, trend_line = story["dmi"], story["supertrend"]
    stance = "เหนือ" if story["close"] > trend_line["value"] else "ใต้"
    thresholds = story["thresholds"]

    lead = (f"{words['bar']}ล่าสุดของ{profile['thai_name']}ปิดที่ {money(story['close'])} "
            f"{profile['unit_phrase']} ระบบจัดสถานะรอบนี้เป็น "
            f"{STATE_PHRASE[story['state']]} โดยอ่านจากหลักฐานสามชิ้นที่ทำหน้าที่ต่างกัน")

    if story["state"] in (S.BULL_TREND, S.BEAR_TREND):
        body = (f"ชุดเส้น DMI ให้น้ำหนักไปทาง{HOLDER[dmi['direction']]} จาก +DI ที่ "
                f"{base.one(dmi['plus_di'])} เทียบกับ -DI ที่ {base.one(dmi['minus_di'])} "
                f"ขณะที่ ADX อยู่ที่ {base.one(dmi['adx'])} ซึ่งเหนือเกณฑ์ "
                f"{base.plain(thresholds['trend'])} ที่ระบบใช้จำแนกว่าการเคลื่อนไหวรอบนี้"
                f"มีแรงตามทิศมากกว่าการแกว่งไปมา และราคายังปิดอยู่{stance}เส้น Supertrend "
                f"ที่ {money(trend_line['value'])} {profile['unit_phrase']} "
                f"หลักฐานทั้งสามชิ้นจึงชี้ไปทางเดียวกันในรอบนี้")
    elif story["state"] in (S.EARLY_BULL, S.EARLY_BEAR):
        body = (f"ชุดเส้น DMI เริ่มให้น้ำหนักไปทาง{HOLDER[dmi['direction']]} จาก +DI ที่ "
                f"{base.one(dmi['plus_di'])} เทียบกับ -DI ที่ {base.one(dmi['minus_di'])} "
                f"แต่ ADX ยังอยู่ที่ {base.one(dmi['adx'])} ซึ่งอยู่ระหว่างเกณฑ์ "
                f"{base.plain(thresholds['no_trend'])} กับ {base.plain(thresholds['trend'])} "
                f"แปลว่าการเคลื่อนไหวเริ่มมีทิศแล้วแต่ยังไม่ถึงระดับที่ระบบเรียกว่าเทรนด์เต็มตัว "
                f"ราคายังปิด{stance}เส้น Supertrend ที่ {money(trend_line['value'])} "
                f"{profile['unit_phrase']} จึงเป็นภาพของแนวโน้มที่กำลังก่อตัว ไม่ใช่แนวโน้มที่ยืนยันแล้ว")
    elif story["state"] == S.TRANSITION:
        body = (f"รอบนี้หลักฐานสองชิ้นพูดไม่ตรงกัน ชุดเส้น DMI ให้น้ำหนักไปทาง"
                f"{HOLDER[dmi['direction']]} จาก +DI ที่ {base.one(dmi['plus_di'])} "
                f"เทียบกับ -DI ที่ {base.one(dmi['minus_di'])} แต่ราคากลับปิดอยู่{stance}"
                f"เส้น Supertrend ที่ {money(trend_line['value'])} {profile['unit_phrase']} "
                f"ขณะที่ ADX อยู่ที่ {base.one(dmi['adx'])} "
                f"ภาพแบบนี้เป็นภาพของตลาดที่กำลังเปลี่ยนมือ ระบบจึงไม่ประกาศทิศให้รอบนี้")
    else:
        body = (f"ADX อยู่ที่ {base.one(dmi['adx'])} ซึ่งต่ำกว่าเกณฑ์ "
                f"{base.plain(thresholds['no_trend'])} ที่ระบบใช้เป็นเส้นแบ่งว่ามีแรงเทรนด์หรือไม่ "
                f"เมื่อความแข็งแรงยังไม่ถึงเกณฑ์ คำถามเรื่องว่าใครคุมทิศจึงยังไม่ควรถูกถาม "
                f"แม้ +DI จะอยู่ที่ {base.one(dmi['plus_di'])} และ -DI อยู่ที่ "
                f"{base.one(dmi['minus_di'])} ก็ตาม รอบนี้จึงอ่านได้ว่าตลาดยังแกว่งอยู่ในกรอบ"
                f"มากกว่าจะเดินเป็นทิศ")
    return [lead, "", body]


def evidence_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    profile = _profile(story)
    dmi, trend_line, volatility = story["dmi"], story["supertrend"], story["atr"]
    atr_percent = volatility["value"] / story["close"] * 100 if story["close"] else 0.0
    adx_move = ("ขยับขึ้นจาก " + base.one(dmi["previous_adx"])
                if dmi["previous_adx"] is not None and dmi["adx"] > dmi["previous_adx"]
                else ("ลดลงจาก " + base.one(dmi["previous_adx"])
                      if dmi["previous_adx"] is not None else "ยังไม่มีค่าก่อนหน้าให้เทียบ"))
    return [
        f"* **ใครคุมทิศ (DMI {base.plain(dmi['length'])}):** +DI อยู่ที่ "
        f"{base.one(dmi['plus_di'])} และ -DI อยู่ที่ {base.one(dmi['minus_di'])} "
        f"เส้นที่สูงกว่าคือฝั่งที่มีแรงเคลื่อนตามทิศมากกว่าในรอบที่ผ่านมา "
        f"รอบนี้จึงอ่านว่า{HOLDER[dmi['direction']]}เป็นผู้ถือจังหวะ",
        f"* **แรงของแนวโน้ม (ADX):** ค่าล่าสุด {base.one(dmi['adx'])} โดย{adx_move} "
        f"ระบบใช้ {base.plain(story['thresholds']['no_trend'])} เป็นเส้นแบ่งว่ามีแรงหรือไม่ "
        f"และ {base.plain(story['thresholds']['trend'])} เป็นเส้นแบ่งว่าแรงพอเรียกว่าเทรนด์แล้ว "
        f"ค่านี้บอกความแข็งแรงเท่านั้น ไม่ได้ระบุว่าราคาจะไปทางใด",
        f"* **เส้นตามทิศ (Supertrend {base.plain(trend_line['length'])} คูณ "
        f"{base.plain(trend_line['multiplier'])}):** เส้นอยู่ที่ {money(trend_line['value'])} "
        f"{profile['unit_phrase']} และราคาปิดอยู่"
        f"{'เหนือ' if story['close'] > trend_line['value'] else 'ใต้'}เส้น "
        f"{'ซึ่งเพิ่งพลิกฝั่งในแท่งนี้' if trend_line['flipped'] else 'ต่อเนื่องจากแท่งก่อนหน้า'}",
        f"* **ความกว้างของการแกว่ง (ATR {base.plain(volatility['length'])}):** ค่าล่าสุด "
        f"{money(volatility['value'])} {profile['unit_phrase']} คิดเป็น "
        f"{base.two(atr_percent)} เปอร์เซ็นต์ของราคาปัจจุบัน และ"
        f"{'กว้างขึ้น' if volatility['rising'] else 'แคบลง'}จากแท่งก่อนหน้า",
    ]


def watch_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    profile = _profile(story)
    thresholds, dmi = story["thresholds"], story["dmi"]
    gap = abs(story["close"] - story["invalidation"]["level"])
    lines = [
        f"ระดับแรกที่ต้องจับตาคือเส้น Supertrend ที่ {money(story['invalidation']['level'])} "
        f"{profile['unit_phrase']} ซึ่งห่างจากราคาปิดล่าสุดอยู่ {money(gap)} "
        f"{profile['unit_phrase']} ตราบที่ราคายังไม่ปิดข้ามเส้นนี้ สถานะที่ระบบจัดไว้จะยังไม่เปลี่ยน",
        "",
        f"ฝั่งความแข็งแรง เกณฑ์ที่ระบบเฝ้าคือ {base.plain(thresholds['no_trend'])} และ "
        f"{base.plain(thresholds['trend'])} การที่ ADX ขยับข้ามเกณฑ์ใดเกณฑ์หนึ่งจะเปลี่ยน"
        f"ความหมายของรอบนี้ทันที แม้ราคายังไม่ไปไหน ปัจจุบันค่าอยู่ที่ "
        f"{base.one(dmi['adx'])}",
    ]
    return lines


def invalidation_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    profile = _profile(story)
    if story["direction"] is None:
        return [f"รอบนี้ระบบยังไม่ประกาศทิศ จึงยังไม่มีมุมมองให้เสีย สิ่งที่จะเปลี่ยนภาพคือ"
                f"การที่ ADX ขยับขึ้นเหนือเกณฑ์ {base.plain(story['thresholds']['no_trend'])} "
                f"พร้อมกับที่ราคาปิดไปยืนฝั่งเดียวกับเส้น Supertrend ที่ "
                f"{money(story['invalidation']['level'])} {profile['unit_phrase']} "
                f"เมื่อสองอย่างนี้เกิดพร้อมกัน ระบบจะเริ่มจัดสถานะให้มีทิศ"]
    side = "ต่ำกว่า" if story["direction"] == "up" else "สูงกว่า"
    return [f"มุมมองรอบนี้ตั้งอยู่บนเงื่อนไขว่าราคายังยืนฝั่งเดิมของเส้น Supertrend "
            f"หากมี{base.tf_words(story)['bar']}ปิด{side}ระดับ "
            f"{money(story['invalidation']['level'])} {profile['unit_phrase']} "
            f"ให้ถือว่าหลักฐานชิ้นที่สามหายไปแล้ว และสถานะจะถูกลดลงเป็นช่วงเปลี่ยนผ่านทันที "
            f"อีกทางหนึ่งที่ทำให้ต้องลดน้ำหนักคือการที่ ADX ร่วงกลับใต้เกณฑ์ "
            f"{base.plain(story['thresholds']['no_trend'])} ซึ่งแปลว่าแรงที่เคยมีหายไป "
            f"แม้ราคาจะยังอยู่ฝั่งเดิมก็ตาม"]


def glossary_lines(story: dict) -> list[str]:
    return [
        "* **DMI (+DI / -DI):** คู่เส้นที่เปรียบเทียบว่าการเคลื่อนไหวขึ้นหรือลง "
        "มีระยะมากกว่ากันในช่วงที่ผ่านมา เส้นที่สูงกว่าคือฝั่งที่กำลังถือจังหวะ",
        "* **ADX:** ตัววัดว่าการเคลื่อนไหวรอบนี้เดินเป็นแนวโน้มชัดแค่ไหน "
        "ค่าสูงแปลว่าเดินเป็นทาง ค่าต่ำแปลว่าแกว่งไปมา ตัวเลขนี้ไม่ได้ระบุว่าราคาจะไปทางใด",
        "* **Supertrend:** เส้นที่วิ่งตามราคาโดยใช้ระยะจากความผันผวนเป็นตัวกำหนด "
        "ใช้ดูว่าราคายังยืนอยู่ฝั่งเดิมของเส้นหรือข้ามไปแล้ว",
        "* **ATR:** ค่าเฉลี่ยความกว้างของการแกว่งต่อหนึ่งแท่ง ใช้ประเมินว่าตลาดเหวี่ยงแรงแค่ไหน",
    ]


def summary_lines(story: dict) -> list[str]:
    words = base.tf_words(story)
    closing = {
        S.BULL_TREND: "รอบนี้อ่านได้ว่าเป็นแนวโน้มที่มีแรงยืนยันแล้ว การย่อระหว่างทาง"
                      "ยังถือเป็นการพักในแนวโน้ม ตราบที่เงื่อนไขข้างต้นยังไม่เสีย",
        S.BEAR_TREND: "รอบนี้อ่านได้ว่าเป็นแนวโน้มที่มีแรงยืนยันแล้ว การเด้งระหว่างทาง"
                      "ยังถือเป็นการพักในแนวโน้ม ตราบที่เงื่อนไขข้างต้นยังไม่เสีย",
        S.EARLY_BULL: "รอบนี้เป็นภาพของแนวโน้มที่กำลังก่อตัว การรอให้ความแข็งแรงยืนยัน"
                      "ก่อนจึงเป็นการอ่านที่ตรงกับหลักฐานมากกว่าการสรุปไปก่อน",
        S.EARLY_BEAR: "รอบนี้เป็นภาพของแนวโน้มที่กำลังก่อตัว การรอให้ความแข็งแรงยืนยัน"
                      "ก่อนจึงเป็นการอ่านที่ตรงกับหลักฐานมากกว่าการสรุปไปก่อน",
        S.TRANSITION: "เมื่อหลักฐานสองชิ้นขัดกัน สิ่งที่ระบบทำคือรอ ไม่ใช่เลือกข้างให้ "
                      "รอบถัดไปที่ทั้งสองชิ้นกลับมาพูดตรงกันจะเป็นรอบที่มีข้อสรุปจริง",
        S.NO_TREND: "เมื่อความแข็งแรงยังต่ำกว่าเกณฑ์ การเคลื่อนไหวที่เห็นเป็นการแกว่ง"
                    "มากกว่าการเดินเป็นทาง รอบนี้จึงยังไม่มีข้อสรุปเรื่องทิศให้ประกาศ",
    }[story["state"]]
    return [f"สรุปสถานะ{words['bar']}ล่าสุด ระบบจัดให้อยู่ในกลุ่ม "
            f"{STATE_PHRASE[story['state']]} {closing}"]


# ------------------------------------------------------------------------- ภาพประกอบ

def hero_figure(story: dict) -> dict:
    profile = _profile(story)
    words = base.tf_words(story)
    return {
        "title": f"{profile['symbol']} {words['front']} พร้อมเส้น Supertrend",
        "purpose": "แสดงว่าราคายืนฝั่งไหนของเส้นตามทิศ และสถานะที่ระบบจัดให้",
        "alt": f"กราฟ {profile['symbol']} {words['thai']} พร้อมเส้น Supertrend "
               f"และสถานะแรงเทรนด์",
        "caption": f"กราฟ{profile['thai_name']} {words['thai']} พร้อมเส้น Supertrend "
                   f"และแถบสถานะที่ระบบจัดให้ในรอบนี้",
        "explanation": (
            "ดังภาพที่ 1 จุดที่ต้องดูคือความสัมพันธ์ระหว่างแท่งล่าสุดกับเส้น Supertrend "
            "ไม่ใช่ความชันของเส้น ส่วนแถบสถานะมุมบนเป็นผลลัพธ์ที่ระบบคำนวณไว้ก่อนเขียนบท"),
    }


def evidence_figure(story: dict) -> dict:
    profile = _profile(story)
    words = base.tf_words(story)
    return {
        "title": f"แผงหลักฐาน DMI ADX และ ATR ของ {profile['symbol']} {words['front']}",
        "purpose": "แยกให้เห็นว่าหลักฐานแต่ละชิ้นทำหน้าที่คนละอย่าง",
        "alt": f"แผงแสดงเส้น DMI และ ADX พร้อมค่า ATR ของ {profile['symbol']} "
               f"{words['thai']}",
        "caption": f"แผงหลักฐานสามชั้น ได้แก่คู่เส้น DMI เส้น ADX พร้อมเกณฑ์สองเส้น "
                   f"และค่า ATR ของ{profile['thai_name']} {words['thai']}",
        "explanation": (
            "จากภาพที่ 2 คู่เส้น DMI ตอบเรื่องฝั่งที่ถือจังหวะ เส้น ADX ตอบเรื่องความแข็งแรง"
            "เทียบกับเกณฑ์สองเส้นที่ลากไว้ ส่วนแถบล่างตอบเรื่องความกว้างของการแกว่งเท่านั้น "
            "สามแผงนี้ต้องอ่านแยกหน้าที่ ไม่ใช่รวมเป็นข้อสรุปเดียว"),
    }


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
    return [base.H2_BOX, h2_overview(story), base.H2_EVIDENCE, base.H2_WATCH,
            base.H2_INVALIDATION, base.H2_GLOSSARY, base.H2_SUMMARY]


def render_article(story: dict) -> str:
    return base.render_article(story, sys.modules[__name__])


def validate(markdown: str, story: dict) -> dict:
    return base.validate(markdown, story, sys.modules[__name__])
