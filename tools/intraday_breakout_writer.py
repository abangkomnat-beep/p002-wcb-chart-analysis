"""นักเขียนสไตล์ I — เบรกเอาต์ความผันผวน M15

สิ่งที่ทำให้บทของสไตล์นี้ไม่ซ้ำกับ H: มันเล่า **การเดินทางของความผันผวน** ไม่ใช่ทิศ

    บีบตัว → ง้างรอที่ขอบกรอบ → ทะลุ → ไปต่อ หรือ กลับเข้ากรอบ

สถานะ "ทะลุแล้วกลับเข้ากรอบ" เป็นบทที่มีค่าที่สุดของสไตล์นี้ เพราะมันคือสิ่งที่ระบบ
สัญญาณทั่วไปไม่พูดถึง — บอกได้แค่ตอนเข้า ไม่บอกตอนที่มันไม่จริง

⛔ ห้ามเขียนว่า "เบรกแล้ว" ถ้าแท่งยังเดินอยู่ — ด่านแท่งปิดใน `intraday_writer_base`
พิสูจน์เรื่องนี้ใหม่จากศูนย์ทุกใบ ไม่ได้เชื่อธงที่ story ตั้งมา
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import intraday_breakout_story as story_module  # noqa: E402
from tools import intraday_writer_base as base  # noqa: E402
from tools import wcb_source  # noqa: E402

LETTER = "I"
STYLE_NAME = "I — เบรกเอาต์ความผันผวน"
STATES = story_module.STATES

S = story_module

STATE_PHRASE = {
    S.NORMAL: "ความผันผวนอยู่ในระดับปกติ ราคายังเดินในกรอบ",
    S.COMPRESSION: "ช่วงบีบตัว ความผันผวนหดลงสู่โซนแคบของตัวเอง",
    S.ARMED: "บีบตัวและราคาขยับเข้าใกล้ขอบกรอบแล้ว",
    S.BREAKOUT_UP: "ปิดทะลุขอบกรอบบนพร้อมแรงขยายตัว",
    S.BREAKOUT_DOWN: "ปิดหลุดขอบกรอบล่างพร้อมแรงขยายตัว",
    S.FAILED_BREAKOUT_UP: "ทะลุขึ้นแล้วกลับเข้ามาในกรอบเดิม",
    S.FAILED_BREAKOUT_DOWN: "หลุดลงแล้วกลับเข้ามาในกรอบเดิม",
    S.EXPANSION: "ความผันผวนกางออกกว้างกว่าปกติ",
}
HEADLINE_KEYWORD = {
    S.NORMAL: "ยังอยู่ในกรอบ",
    S.COMPRESSION: "บีบตัว",
    S.ARMED: "ใกล้ขอบกรอบ",
    S.BREAKOUT_UP: "ทะลุกรอบบน",
    S.BREAKOUT_DOWN: "หลุดกรอบล่าง",
    S.FAILED_BREAKOUT_UP: "กลับเข้ากรอบ",
    S.FAILED_BREAKOUT_DOWN: "กลับเข้ากรอบ",
    S.EXPANSION: "ความผันผวนกางออก",
}


def _profile(story: dict) -> dict:
    return wcb_source.profile_for(story["asset"])


def title_tail(story: dict) -> str:
    return "จังหวะบีบตัวและเบรกเอาต์บน M15"


def h1_tail(story: dict) -> str:
    name = _profile(story)["short_name"]
    tails = {
        S.NORMAL: f"{name} M15 ยังอยู่ในกรอบ ความผันผวนระดับปกติ",
        S.COMPRESSION: f"{name} M15 บีบตัวแคบ รอแท่งปิดเลือกทาง",
        S.ARMED: f"{name} M15 บีบตัวใกล้ขอบกรอบ รอแท่งปิดยืนยัน",
        S.BREAKOUT_UP: f"{name} M15 ปิดทะลุกรอบบน แรงขยายตัวเริ่มตามมา",
        S.BREAKOUT_DOWN: f"{name} M15 ปิดหลุดกรอบล่าง แรงขยายตัวเริ่มตามมา",
        S.FAILED_BREAKOUT_UP: f"{name} M15 ทะลุแล้วกลับเข้ากรอบ สัญญาณเบรกไม่สำเร็จ",
        S.FAILED_BREAKOUT_DOWN: f"{name} M15 หลุดแล้วกลับเข้ากรอบ สัญญาณเบรกไม่สำเร็จ",
        S.EXPANSION: f"{name} M15 ความผันผวนกางออก ช่วงแกว่งกว้างกว่าปกติ",
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
    return [f"{_profile(story)['short_name']}ปิดแท่ง M15 ที่ {money(story['close'])} ดอลลาร์",
            f"กรอบอ้างอิงอยู่ที่ {money(story['donchian']['lower'])} ถึง "
            f"{money(story['donchian']['upper'])}",
            f"ระบบจัดสถานะเป็น{STATE_PHRASE[story['state']]}",
            "อ่านหลักฐาน Donchian BandWidth และ ATR พร้อมภาพประกอบ"]


def h2_overview(story: dict) -> str:
    return f"ตลาดกำลังบีบตัวหรือขยายตัวบน {base.tf_words(story)['front']}"


def overview_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    profile = _profile(story)
    words = base.tf_words(story)
    channel, bandwidth, volatility = story["donchian"], story["bbw"], story["atr"]

    lead = (f"{words['bar']}ล่าสุดของ{profile['thai_name']}ปิดที่ {money(story['close'])} "
            f"{profile['unit_phrase']} เทียบกับกรอบอ้างอิง {base.plain(channel['length'])} "
            f"แท่งก่อนหน้าที่กินช่วง {money(channel['lower'])} ถึง "
            f"{money(channel['upper'])} {profile['unit_phrase']} "
            f"ระบบจัดสถานะรอบนี้เป็น {STATE_PHRASE[story['state']]}")

    squeeze_text = (f"อันดับความกว้างของแถบ BandWidth อยู่ที่ "
                    f"{base.whole(bandwidth['percentile'])} เมื่อเทียบกับประวัติ "
                    f"{base.plain(bandwidth['samples'])} ค่าล่าสุดของหัวข้อนี้เอง "
                    f"ซึ่งเป็นวิธีเดียวที่อ่านค่านี้ได้ เพราะเทียบข้ามสินทรัพย์ไม่ได้")

    if story["state"] in (S.BREAKOUT_UP, S.BREAKOUT_DOWN):
        edge = "ขอบบน" if story["state"] == S.BREAKOUT_UP else "ขอบล่าง"
        body = (f"แท่งล่าสุดปิดพ้น{edge}ของกรอบไปแล้ว และเป็นแท่งที่มีช่วงกว้าง "
                f"{base.two(story['atr']['expansion_ratio'])} เท่าของค่าเฉลี่ยการแกว่ง "
                f"ซึ่งผ่านเกณฑ์ {base.plain(story['thresholds']['breakout_tr_atr'])} เท่า "
                f"ที่ระบบใช้แยกการทะลุที่มีแรงออกจากการแตะขอบด้วยไส้แท่ง พร้อมกันนั้น "
                f"แถบ BandWidth ก็กางออกจากแท่งก่อนหน้า {squeeze_text}")
    elif story["state"] in (S.FAILED_BREAKOUT_UP, S.FAILED_BREAKOUT_DOWN):
        body = (f"รอบก่อนหน้าราคาปิดพ้นขอบกรอบไปแล้ว แต่แท่งล่าสุดกลับมาปิดอยู่ในกรอบเดิม "
                f"ระบบจึงจัดรอบนี้เป็นการทะลุที่ไม่สำเร็จ ซึ่งเป็นข้อมูลคนละชิ้นกับ"
                f"การไม่เคยทะลุเลย เพราะมันบอกว่ามีความพยายามแล้วแต่แรงไม่พอจะยืน "
                f"{squeeze_text}")
    elif story["state"] == S.ARMED:
        gap = min(channel["upper"] - story["close"], story["close"] - channel["lower"])
        body = (f"ราคาอยู่ห่างจากขอบกรอบที่ใกล้ที่สุดเพียง {money(gap)} "
                f"{profile['unit_phrase']} ขณะที่ความผันผวนยังอยู่ในโซนบีบตัว "
                f"ภาพแบบนี้คือช่วงที่ตลาดง้างรออยู่ที่ขอบ ยังไม่ใช่การทะลุ "
                f"เพราะการทะลุนับที่แท่งปิดพ้นขอบเท่านั้น {squeeze_text}")
    elif story["state"] == S.COMPRESSION:
        body = (f"ราคายังเดินอยู่ในกรอบและความผันผวนหดลงมาอยู่ในโซนแคบของตัวเอง "
                f"ช่วงแบบนี้มักเป็นช่วงสะสมพลังก่อนที่ตลาดจะเลือกทาง แต่ตัวมันเอง"
                f"ยังไม่ได้บอกว่าจะเลือกทางไหน {squeeze_text}")
    elif story["state"] == S.EXPANSION:
        body = (f"ความผันผวนกางออกกว้างกว่าปกติแล้ว ซึ่งเป็นสภาพตรงข้ามกับช่วงบีบตัว "
                f"ในสภาพแบบนี้กรอบเดิมมักถูกทดสอบบ่อยและระยะการแกว่งต่อแท่งกว้างขึ้น "
                f"{squeeze_text}")
    else:
        body = (f"ราคายังเดินอยู่ในกรอบและความผันผวนอยู่ในระดับกลาง ๆ ของตัวเอง "
                f"ไม่ได้แคบพอจะเรียกว่าบีบตัว และไม่ได้กว้างพอจะเรียกว่ากางออก "
                f"{squeeze_text}")

    return [lead, "", body]


def evidence_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    profile = _profile(story)
    channel, bandwidth, volatility = story["donchian"], story["bbw"], story["atr"]
    return [
        f"* **กรอบอ้างอิง (Donchian {base.plain(channel['length'])} แท่ง):** ขอบบน "
        f"{money(channel['upper'])} ขอบล่าง {money(channel['lower'])} กว้าง "
        f"{money(channel['width'])} {profile['unit_phrase']} "
        f"กรอบนี้คิดจากแท่งก่อนหน้าเท่านั้น แท่งที่กำลังตัดสินไม่ถูกนับเข้าไปตั้งขอบให้ตัวเอง",
        f"* **สถานะการบีบตัว (BandWidth {base.plain(bandwidth['length'])}):** ค่าล่าสุด "
        f"{base.two(bandwidth['value'])} อยู่ที่อันดับเปอร์เซ็นไทล์ "
        f"{base.whole(bandwidth['percentile'])} ของประวัติตัวเอง และ"
        f"{'กางออก' if bandwidth['rising'] else 'หดลง'}จากแท่งก่อนหน้า "
        f"เกณฑ์ที่ระบบใช้คือ {base.plain(story['thresholds']['compression_percentile'])} "
        f"สำหรับช่วงบีบตัว และ {base.plain(story['thresholds']['expansion_percentile'])} "
        f"สำหรับช่วงกางออก",
        f"* **แรงของแท่งล่าสุด (ATR {base.plain(volatility['length'])}):** ช่วงจริงของ"
        f"แท่งนี้อยู่ที่ {money(volatility['bar_true_range'])} เทียบกับค่าเฉลี่ย "
        f"{money(volatility['value'])} {profile['unit_phrase']} คิดเป็น "
        f"{base.two(volatility['expansion_ratio'])} เท่า "
        f"ตัวเลขนี้ใช้ตรวจว่าการเคลื่อนไหวมีระยะจริงหรือไม่ ไม่ได้ใช้ตัดสินทิศทาง",
        f"* **ตำแหน่งของราคาในกรอบ:** ราคาปิดห่างขอบบน "
        f"{money(channel['upper'] - story['close'])} และห่างขอบล่าง "
        f"{money(story['close'] - channel['lower'])} {profile['unit_phrase']} "
        f"สองค่านี้บอกว่าตลาดกำลังง้างอยู่ฝั่งใดของกรอบ",
    ]


def watch_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    profile = _profile(story)
    channel = story["donchian"]
    return [
        f"เงื่อนไขที่ต้องรอคือ**แท่งปิด** ไม่ใช่ราคาที่แตะระหว่างทาง ขอบที่ระบบใช้ตัดสิน"
        f"คือ {money(channel['upper'])} ด้านบน และ {money(channel['lower'])} ด้านล่าง "
        f"{profile['unit_phrase']} ราคาที่วิ่งพ้นขอบระหว่างแท่งแล้วถอยกลับมาปิดในกรอบ "
        f"ระบบจะไม่นับเป็นการทะลุ",
        "",
        f"อีกเงื่อนไขที่ต้องดูคู่กันคือแรงขยาย การทะลุที่แถบ BandWidth ไม่กางตามและช่วง"
        f"แท่งไม่ถึง {base.plain(story['thresholds']['breakout_tr_atr'])} เท่าของค่าเฉลี่ย "
        f"จะไม่ถูกจัดเป็นการทะลุที่มีแรง แม้ราคาจะปิดพ้นขอบไปแล้วก็ตาม",
    ]


def invalidation_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    profile = _profile(story)
    level = money(story["invalidation"]["level"])
    if story["state"] in (S.BREAKOUT_UP, S.BREAKOUT_DOWN):
        return [f"มุมมองรอบนี้ตั้งอยู่บนเงื่อนไขว่าราคายืนอยู่นอกกรอบได้ต่อ หากแท่งถัดไป"
                f"ปิดกลับเข้ามาในกรอบที่ระดับ {level} {profile['unit_phrase']} "
                f"ระบบจะเปลี่ยนสถานะเป็นการทะลุที่ไม่สำเร็จทันที ซึ่งเป็นการกลับด้าน"
                f"ของเรื่องเล่า ไม่ใช่แค่การอ่อนแรงลง"]
    if story["state"] in (S.FAILED_BREAKOUT_UP, S.FAILED_BREAKOUT_DOWN):
        return [f"สถานะนี้จะเปลี่ยนก็ต่อเมื่อราคากลับไปปิดพ้นขอบ {level} "
                f"{profile['unit_phrase']} ได้อีกครั้งพร้อมแรงขยาย การกลับไปทดสอบขอบเดิม"
                f"โดยไม่มีแรงหนุนมักเป็นการทดสอบซ้ำ ไม่ใช่การเริ่มรอบใหม่"]
    return [f"สิ่งที่จะเปลี่ยนภาพรอบนี้คือแท่งปิดที่พ้นขอบกรอบ โดยขอบที่ใกล้ราคาที่สุด"
            f"ตอนนี้อยู่ที่ {level} {profile['unit_phrase']} ตราบที่ยังไม่มีแท่งปิดพ้นขอบ"
            f"พร้อมแรงขยาย สถานะรอบนี้จะยังเป็นภาพเดิม และการเคลื่อนไหวภายในกรอบ"
            f"ยังไม่ถือเป็นการเลือกทาง"]


def summary_lines(story: dict) -> list[str]:
    words = base.tf_words(story)
    closing = {
        S.NORMAL: "รอบนี้ยังไม่มีเหตุการณ์ของสายเบรกเอาต์ให้ติดตาม การเฝ้าดูว่าความผันผวน"
                  "จะหดลงสู่โซนบีบตัวหรือไม่ เป็นสิ่งที่มีประโยชน์กว่าการเดาทิศล่วงหน้า",
        S.COMPRESSION: "ช่วงบีบตัวเป็นช่วงที่ควรเตรียมตัวมากกว่าตัดสินใจ เพราะข้อมูลที่มี"
                       "บอกว่าตลาดกำลังสะสมพลัง แต่ยังไม่บอกว่าจะปล่อยไปทางใด",
        S.ARMED: "เมื่อราคาง้างอยู่ที่ขอบพร้อมกับความผันผวนที่ยังแคบ รอบถัดไปคือรอบที่"
                 "มีโอกาสเกิดเหตุการณ์จริง สิ่งที่ใช้ตัดสินคือแท่งปิด ไม่ใช่การแตะขอบ",
        S.BREAKOUT_UP: "รอบนี้เข้าเงื่อนไขการทะลุที่มีแรงครบทั้งสองข้อ คือปิดพ้นขอบและ"
                       "ช่วงแท่งกว้างกว่าปกติ สิ่งที่ต้องติดตามต่อคือความต่อเนื่องในแท่งถัดไป",
        S.BREAKOUT_DOWN: "รอบนี้เข้าเงื่อนไขการทะลุที่มีแรงครบทั้งสองข้อ คือปิดพ้นขอบและ"
                         "ช่วงแท่งกว้างกว่าปกติ สิ่งที่ต้องติดตามต่อคือความต่อเนื่องในแท่งถัดไป",
        S.FAILED_BREAKOUT_UP: "การทะลุที่ไม่สำเร็จเป็นข้อมูลที่มีค่า เพราะมันบอกว่าที่ขอบนั้น"
                              "มีแรงต้านมากพอจะผลักราคากลับ ซึ่งต่างจากการที่ราคาไม่เคยไปถึงขอบเลย",
        S.FAILED_BREAKOUT_DOWN: "การทะลุที่ไม่สำเร็จเป็นข้อมูลที่มีค่า เพราะมันบอกว่าที่ขอบนั้น"
                                "มีแรงต้านมากพอจะผลักราคากลับ ซึ่งต่างจากการที่ราคาไม่เคยไปถึงขอบเลย",
        S.EXPANSION: "เมื่อความผันผวนกางออกแล้ว ระยะการแกว่งต่อแท่งจะกว้างขึ้นตาม "
                     "การประเมินระยะจากราคาถึงขอบกรอบจึงต้องใช้ค่าปัจจุบัน ไม่ใช่ค่าของช่วงเงียบ",
    }[story["state"]]
    return [f"สรุปสถานะ{words['bar']}ล่าสุด ระบบจัดให้อยู่ในกลุ่ม "
            f"{STATE_PHRASE[story['state']]} {closing}"]


# ------------------------------------------------------------------------- ภาพประกอบ

def hero_figure(story: dict) -> dict:
    profile = _profile(story)
    words = base.tf_words(story)
    return {
        "title": f"{profile['symbol']} {words['front']} พร้อมกรอบ Donchian",
        "purpose": "แสดงขอบกรอบที่ใช้ตัดสิน และตำแหน่งของแท่งล่าสุดเทียบกับขอบ",
        "alt": f"กราฟ {profile['symbol']} {words['thai']} พร้อมกรอบ Donchian "
               f"และสถานะการบีบตัว",
        "caption": f"กราฟ{profile['thai_name']} {words['thai']} พร้อมขอบกรอบ Donchian "
                   f"ที่คิดจากแท่งก่อนหน้า และแถบสถานะของรอบนี้",
        "explanation": (
            "ดังภาพที่ 1 จุดที่ต้องดูคือราคาปิดของแท่งล่าสุดอยู่ในหรือนอกขอบกรอบ "
            "ไม่ใช่ไส้แท่งที่แหย่ออกไประหว่างทาง เพราะระบบนับเฉพาะแท่งที่ปิดแล้ว"),
    }


def evidence_figure(story: dict) -> dict:
    profile = _profile(story)
    words = base.tf_words(story)
    return {
        "title": f"แผงหลักฐาน BandWidth และ ATR ของ {profile['symbol']} {words['front']}",
        "purpose": "แสดงว่าความผันผวนกำลังหดหรือกาง และแท่งล่าสุดมีระยะจริงแค่ไหน",
        "alt": f"แผงแสดงค่า BandWidth และ ATR ของ {profile['symbol']} {words['thai']}",
        "caption": f"แผงหลักฐานความผันผวน ได้แก่เส้น BandWidth พร้อมเส้นเกณฑ์บีบตัว "
                   f"และค่า ATR ของ{profile['thai_name']} {words['thai']}",
        "explanation": (
            "จากภาพที่ 2 เส้นบนคือความกว้างของแถบ Bollinger ส่วนแถบล่างคือระยะการแกว่ง"
            "ต่อแท่ง สองแผงนี้ตอบคำถามเรื่องแรง ส่วนการเปลี่ยนทางของราคาต้องอ่านจาก"
            "ขอบกรอบในภาพแรกเท่านั้น"),
    }


def number_tokens(story: dict) -> set[str]:
    money = base.money_for(story)
    channel, bandwidth, volatility = story["donchian"], story["bbw"], story["atr"]
    return {
        money(channel["upper"]), money(channel["lower"]), money(channel["width"]),
        money(channel["upper"] - story["close"]), money(story["close"] - channel["lower"]),
        money(min(channel["upper"] - story["close"], story["close"] - channel["lower"])),
        money(volatility["value"]), money(volatility["bar_true_range"]),
        base.plain(channel["length"]), base.plain(bandwidth["length"]),
        base.plain(bandwidth["samples"]), base.plain(volatility["length"]),
        base.two(bandwidth["value"]), base.whole(bandwidth["percentile"]),
        base.two(volatility["expansion_ratio"]),
        base.plain(story["thresholds"]["compression_percentile"]),
        base.plain(story["thresholds"]["expansion_percentile"]),
        base.plain(story["thresholds"]["breakout_tr_atr"]),
    }


def required_headings(story: dict) -> list[str]:
    return [base.H2_BOX, h2_overview(story), base.H2_EVIDENCE, base.H2_WATCH,
            base.H2_INVALIDATION, base.H2_SUMMARY]


def render_article(story: dict) -> str:
    return base.render_article(story, sys.modules[__name__])


def validate(markdown: str, story: dict) -> dict:
    return base.validate(markdown, story, sys.modules[__name__])
