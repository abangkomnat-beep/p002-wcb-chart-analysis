"""นักเขียนสไตล์ J — ย่อแล้วไปต่อ หรือกำลังเสียแนวโน้ม (M30 → M15)

บทนี้ตอบคำถามที่คนอ่านถามบ่อยที่สุดเวลาราคาย่อ และเป็นคำถามที่ H กับ I ตอบไม่ได้:

    ตอนนี้ราคาย่อเพื่อไปต่อ หรือย่อจนเริ่มเสียทรงแล้ว

โครงบทเดินตามลำดับเดียวกับตรรกะ: **บริบทก่อน แล้วค่อยจังหวะ** — ถ้าเขียนกลับลำดับ
บทจะกลายเป็นการอ่านแท่ง M15 แล้วหาเหตุผลจาก M30 มาสนับสนุนทีหลัง ซึ่งเป็นคนละเรื่อง

⚠️ บทนี้พูดถึงกรอบเวลาสองชั้น ⇒ **ทุกประโยคต้องบอกว่ากำลังพูดถึงชั้นไหน**
ประโยคที่ไม่ระบุกรอบเวลาในบทสองชั้นคือประโยคที่คนอ่านตีความผิดได้ทันที
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import intraday_pullback_story as story_module  # noqa: E402
from tools import intraday_writer_base as base  # noqa: E402
from tools import wcb_source  # noqa: E402

LETTER = "J"
STYLE_NAME = "J — ย่อแล้วไปต่อ"
STATES = story_module.STATES

S = story_module

STATE_PHRASE = {
    S.NO_M30_BIAS: "ยังไม่มีทิศหลักจากกรอบใหญ่ให้ยึด",
    S.M30_BULL_CONTEXT: "บริบทขาขึ้นของกรอบใหญ่ ยังไม่เข้าโซนย่อ",
    S.M30_BEAR_CONTEXT: "บริบทขาลงของกรอบใหญ่ ยังไม่เข้าโซนย่อ",
    S.PULLBACK_FORMING: "กำลังย่อเข้าโซนอ้างอิงของกรอบใหญ่",
    S.PULLBACK_CONFIRMED: "ย่อแล้วเริ่มกลับไปตามทิศหลัก",
    S.PULLBACK_FAILED: "การย่อลึกจนเสียโครงของกรอบใหญ่",
    S.TREND_RESUMED: "กลับไปเดินตามทิศหลักต่อแล้ว",
}
HEADLINE_KEYWORD = {
    S.NO_M30_BIAS: "ยังไม่มีทิศหลัก",
    S.M30_BULL_CONTEXT: "บริบทขาขึ้น",
    S.M30_BEAR_CONTEXT: "บริบทขาลง",
    S.PULLBACK_FORMING: "อยู่ในช่วงย่อ",
    S.PULLBACK_CONFIRMED: "เริ่มกลับไปตามทิศ",
    S.PULLBACK_FAILED: "เสียโครง",
    S.TREND_RESUMED: "กลับไปเดินตามทิศ",
}
BIAS_WORD = {"up": "ขาขึ้น", "down": "ขาลง"}
CLOUD_POSITION = {"above": "เหนือเมฆ", "below": "ใต้เมฆ", "inside": "อยู่ในเมฆ"}


def _profile(story: dict) -> dict:
    return wcb_source.profile_for(story["asset"])


def _context_words(story: dict) -> dict:
    return base.tf_words(story, story["context_timeframe"])


def title_tail(story: dict) -> str:
    return "การย่อในเทรนด์จาก Ichimoku M30 และ CHOP M15"


def h1_tail(story: dict) -> str:
    # ⚠️ **ห้ามเว้นวรรคระหว่างชื่อสินทรัพย์กับคำไทยที่ตามมา** — ภาษาไทยเขียนติดกัน
    # 🐞 พบตอนอ่านบทจริงใบแรก 08-13: `บิทคอยน์ อยู่ในบริบท…` ช่องว่างตรงนั้นแยกประธาน
    # ออกจากกริยา อ่านสะดุดทันที · เว้นวรรคได้เฉพาะหน้าอักษรละติน (`M30`) ซึ่งจำเป็นจริง
    name = _profile(story)["short_name"]
    tails = {
        S.NO_M30_BIAS: f"{name}ยังไม่มีทิศหลักจาก M30 ให้ M15 ยึด",
        S.M30_BULL_CONTEXT: f"{name}อยู่ในบริบทขาขึ้นของ M30 ยังไม่เข้าโซนย่อ",
        S.M30_BEAR_CONTEXT: f"{name}อยู่ในบริบทขาลงของ M30 ยังไม่เข้าโซนย่อ",
        S.PULLBACK_FORMING: f"{name}อยู่ในช่วงย่อบน M15 ภายในทิศหลักของ M30",
        S.PULLBACK_CONFIRMED: f"{name}ย่อแล้วเริ่มกลับไปตามทิศหลักของ M30",
        S.PULLBACK_FAILED: f"{name}ย่อลึกจนเสียโครงของ M30 แล้ว",
        S.TREND_RESUMED: f"{name}กลับไปเดินตามทิศหลักของ M30 ต่อ",
    }
    return tails[story["state"]]


def headline_keyword(story: dict) -> str:
    return HEADLINE_KEYWORD[story["state"]]


def state_phrase(story: dict) -> str:
    return f"`{story['state']}` — {STATE_PHRASE[story['state']]}"


def timeframe_phrase(story: dict) -> str:
    context, trigger = _context_words(story), base.tf_words(story)
    return (f"บริบทจาก{context['bar']} ({context['front']}) และจังหวะจาก"
            f"{trigger['bar']} ({trigger['front']}) ที่ปิดแล้วทั้งคู่")


def excerpt_clauses(story: dict) -> list[str]:
    money = base.money_for(story)
    return [f"{_profile(story)['short_name']}ปิดแท่ง M15 ที่ {money(story['close'])} ดอลลาร์",
            f"ระบบจัดสถานะเป็น{STATE_PHRASE[story['state']]}",
            f"โซนอ้างอิงของการย่ออยู่ที่ {money(story['pullback_zone']['low'])} ถึง "
            f"{money(story['pullback_zone']['high'])}",
            "อ่านบริบท Ichimoku พร้อมภาพประกอบสองชั้น"]


def h2_overview(story: dict) -> str:
    return f"ทิศหลักจาก {_context_words(story)['front']} และจังหวะบน {base.tf_words(story)['front']}"


def overview_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    profile = _profile(story)
    context, trigger = _context_words(story), base.tf_words(story)
    cloud = story["ichimoku"]
    zone = story["pullback_zone"]

    lead = (f"{trigger['bar']}ล่าสุดของ{profile['thai_name']}ปิดที่ "
            f"{money(story['close'])} {profile['unit_phrase']} ระบบอ่านบริบทหลักจาก"
            f"{context['bar']}ก่อน แล้วจึงดูจังหวะบน{trigger['bar']} ลำดับนี้สำคัญ "
            f"เพราะถ้าอ่านจังหวะก่อนบริบท บทจะกลายเป็นการหาเหตุผลมารองรับสิ่งที่เห็นไปแล้ว")

    frame = (f"บน{context['bar']} ราคาอยู่{CLOUD_POSITION[cloud['position']]} "
             f"เส้น Tenkan อยู่ที่ {money(cloud['tenkan'])} และ Kijun อยู่ที่ "
             f"{money(cloud['kijun'])} {profile['unit_phrase']} ")
    if story["direction"]:
        bias_text = (frame + f"องค์ประกอบทั้งสามชั้นพูดตรงกันว่าบริบทหลักเป็น"
                             f"{BIAS_WORD[story['direction']]} ระบบจึงให้ชั้นที่สองทำงานต่อ")
    else:
        bias_text = (frame + "องค์ประกอบยังพูดไม่ตรงกัน ระบบจึงถือว่าเป็นช่วงเปลี่ยนผ่าน "
                             "และไม่ประกาศทิศหลักให้รอบนี้")

    zone_text = (f"โซนอ้างอิงระหว่าง {money(zone['low'])} ถึง {money(zone['high'])} "
                 f"{profile['unit_phrase']} ซึ่งเป็นช่วงระหว่างเส้น Tenkan กับ Kijun "
                 f"ของกรอบใหญ่")
    chop_text = (f"ค่า CHOP ล่าสุดอยู่ที่ {base.one(story['chop']['value'])} "
                 f"{'ลดลง' if story['chop']['falling'] else 'เพิ่มขึ้น'}จากแท่งก่อนหน้า")
    if story["state"] in (S.PULLBACK_FORMING, S.PULLBACK_CONFIRMED, S.TREND_RESUMED):
        detail = (f"บน{trigger['bar']} ราคาเข้ามาทำงานกับ{zone_text} "
                  f"ระบบใช้โซนนี้วัดว่าการย่อยังอยู่ในระเบียบเดิมหรือไม่ {chop_text}")
    elif story["state"] == S.PULLBACK_FAILED:
        detail = (f"บน{trigger['bar']} ราคาเดินพ้น{zone_text}ไปแล้ว "
                  f"ซึ่งเป็นเส้นแบ่งที่ระบบใช้แยกการพักตัวออกจากการเสียโครง {chop_text}")
    else:
        detail = (f"บน{trigger['bar']} ราคายังไม่เข้ามาใน{zone_text} "
                  f"จึงยังไม่มีการย่อให้ประเมิน {chop_text}")
    return [lead, "", bias_text, "", detail]


def evidence_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    profile = _profile(story)
    context, trigger = _context_words(story), base.tf_words(story)
    cloud, chop, volatility = story["ichimoku"], story["chop"], story["atr"]
    now = cloud["cloud_now"]
    return [
        f"* **ตำแหน่งเทียบเมฆ ({context['front']}):** ราคาอยู่"
        f"{CLOUD_POSITION[cloud['position']]} ขอบเมฆด้านบน {money(now['top'])} "
        f"ด้านล่าง {money(now['bottom'])} {profile['unit_phrase']} "
        f"ค่าชุดนี้คำนวณจากข้อมูลเมื่อ {base.plain(cloud['base'])} แท่งก่อน "
        f"ตามกติกาการเลื่อนเมฆไปข้างหน้า",
        f"* **Tenkan เทียบ Kijun ({context['front']}):** เส้นคู่นี้เป็นทั้งตัวยืนยันบริบท "
        f"และเป็นขอบของโซนอ้างอิงที่ใช้วัดว่าการย่อยังอยู่ในระเบียบเดิมหรือไม่",
        f"* **สภาพตลาดบน {trigger['front']} (Choppiness {base.plain(chop['length'])}):** "
        f"ค่าล่าสุด {base.one(chop['value'])} เกณฑ์ที่ระบบใช้คือ "
        f"{base.plain(story['thresholds']['chop_trending'])} สำหรับช่วงที่เดินเป็นทาง "
        f"และ {base.plain(story['thresholds']['chop_choppy'])} สำหรับช่วงที่แกว่งสับ",
        f"* **ความกว้างการแกว่งบน {trigger['front']} (ATR {base.plain(volatility['length'])}):** "
        f"ค่าล่าสุด {money(volatility['value'])} {profile['unit_phrase']} และ"
        f"{'กว้างขึ้น' if volatility['rising'] else 'แคบลง'}จากแท่งก่อนหน้า",
    ]


def watch_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    profile = _profile(story)
    context, trigger = _context_words(story), base.tf_words(story)
    zone = story["pullback_zone"]
    return [
        f"โซนที่ต้องจับตาคือ {money(zone['low'])} ถึง {money(zone['high'])} "
        f"{profile['unit_phrase']} การที่ราคาบน{trigger['bar']}เข้ามาในโซนนี้แล้ว"
        f"ปิดกลับไปตามทิศหลักของ{context['bar']} คือรูปแบบของการย่อที่ยังอยู่ในระเบียบ",
        "",
        f"อีกสิ่งที่ดูคู่กันคือค่า CHOP บน{trigger['bar']} ค่าที่ลดลงต่อเนื่องแปลว่า"
        f"ตลาดเริ่มกลับมาเดินเป็นทางหลังช่วงแกว่งสับ ซึ่งเป็นเงื่อนไขประกอบการยืนยัน "
        f"ไม่ใช่เงื่อนไขที่ตัดสินได้ด้วยตัวเอง",
    ]


def invalidation_lines(story: dict) -> list[str]:
    money = base.money_for(story)
    profile = _profile(story)
    context = _context_words(story)
    level = money(story["invalidation"]["level"])
    if story["direction"] is None:
        return [f"รอบนี้ยังไม่มีทิศหลักให้เสีย สิ่งที่จะทำให้ระบบเริ่มอ่านเป็นแนวโน้มได้"
                f"คือราคาบน{context['bar']}กลับไปยืนพ้นเมฆพร้อมกับที่เส้น Tenkan และ "
                f"Kijun เรียงตัวไปทางเดียวกัน ตราบที่ยังขัดกัน การพูดว่าราคาย่อในแนวโน้ม"
                f"ยังไม่มีฐานรองรับ"]
    side = "ต่ำกว่า" if story["direction"] == "up" else "สูงกว่า"
    return [f"มุมมองว่านี่คือการย่อในแนวโน้มจะใช้ไม่ได้ทันที หากมีแท่ง"
            f"{base.tf_words(story)['thai']}ปิด{side}เส้น Kijun ของ{context['bar']} "
            f"ที่ {level} {profile['unit_phrase']} เพราะนั่นคือการพักตัวที่เดินลึกเกิน"
            f"ระเบียบของแนวโน้มเดิม อีกทางคือบริบทของ{context['bar']}เองเสียไป "
            f"โดยราคากลับเข้าไปอยู่ในเมฆ หรือเส้น Tenkan กับ Kijun สลับข้างกัน"]


def summary_lines(story: dict) -> list[str]:
    context = _context_words(story)
    closing = {
        S.NO_M30_BIAS: "เมื่อกรอบใหญ่ยังไม่มีทิศ การถามว่าย่อเพื่อไปต่อหรือไม่ยังไม่มี"
                       "ความหมาย รอบที่บริบทกลับมาชัดจะเป็นรอบที่คำถามนี้ตอบได้",
        S.M30_BULL_CONTEXT: "บริบทมีแล้วแต่ยังไม่มีการย่อให้ประเมิน รอบนี้จึงเป็นการบันทึก"
                            "ว่าเงื่อนไขชั้นแรกพร้อม และรอให้ชั้นที่สองเกิดขึ้นจริง",
        S.M30_BEAR_CONTEXT: "บริบทมีแล้วแต่ยังไม่มีการย่อให้ประเมิน รอบนี้จึงเป็นการบันทึก"
                            "ว่าเงื่อนไขชั้นแรกพร้อม และรอให้ชั้นที่สองเกิดขึ้นจริง",
        S.PULLBACK_FORMING: "การย่อกำลังก่อตัวในโซนอ้างอิง ซึ่งยังไม่ใช่การยืนยัน "
                            "สิ่งที่จะแยกว่าเป็นการพักหรือการเสียโครงคือแท่งปิดถัดไป",
        S.PULLBACK_CONFIRMED: "รอบนี้เข้าเงื่อนไขการย่อที่กลับไปตามทิศหลักครบแล้ว "
                              "สิ่งที่ต้องติดตามต่อคือความต่อเนื่อง ไม่ใช่การยืนยันซ้ำ",
        S.PULLBACK_FAILED: "เมื่อการพักตัวเดินลึกเกินเส้นที่ใช้ตัดสิน สิ่งที่เปลี่ยนไม่ใช่"
                           "ความแรงของแนวโน้ม แต่เป็นเงื่อนไขที่ใช้เรียกมันว่าแนวโน้ม",
        S.TREND_RESUMED: "การกลับไปทำจุดสุดขั้วใหม่ต่อจากการย่อที่ยืนยันแล้ว คือรูปแบบ"
                         "ที่ปิดวงจรของสไตล์นี้พอดี รอบถัดไปจึงเริ่มนับวงจรใหม่",
    }[story["state"]]
    return [f"สรุปภาพรวมสองชั้นโดยอ่านบริบทจาก{context['bar']} ระบบจัดให้อยู่ในกลุ่ม "
            f"{STATE_PHRASE[story['state']]} {closing}"]


# ------------------------------------------------------------------------- ภาพประกอบ

def hero_figure(story: dict) -> dict:
    profile = _profile(story)
    context = _context_words(story)
    return {
        # ภาพหลักของ J เป็นกรอบ **บริบท** ไม่ใช่กรอบของบท ⇒ ชื่อไฟล์ต้องบอกกรอบของภาพ
        "timeframe": story["context_timeframe"],
        "title": f"{profile['symbol']} {context['front']} พร้อมเมฆ Ichimoku",
        "purpose": "แสดงบริบทหลักของกรอบใหญ่ที่ใช้เป็นเงื่อนไขชั้นแรก",
        "alt": f"กราฟ {profile['symbol']} {context['thai']} พร้อมเมฆ Ichimoku "
               f"เส้น Tenkan และ Kijun",
        "caption": f"กราฟ{profile['thai_name']} {context['thai']} พร้อมเมฆ Ichimoku "
                   f"เส้น Tenkan และ Kijun ซึ่งเป็นชั้นบริบทของสไตล์นี้",
        "explanation": (
            "ดังภาพที่ 1 สิ่งที่ต้องดูคือราคาอยู่พ้นเมฆด้านใด และเส้น Tenkan กับ Kijun "
            "เรียงตัวไปทางเดียวกันหรือไม่ ภาพนี้ตัดสินเฉพาะบริบท ส่วนจังหวะอยู่ในภาพที่ 2"),
    }


def evidence_figure(story: dict) -> dict:
    profile = _profile(story)
    trigger = base.tf_words(story)
    return {
        "title": f"{profile['symbol']} {trigger['front']} พร้อมโซนย่อและค่า CHOP",
        "purpose": "แสดงว่าการย่อรอบล่าสุดเดินถึงขั้นไหนเทียบกับโซนอ้างอิง",
        "alt": f"กราฟ {profile['symbol']} {trigger['thai']} พร้อมโซนอ้างอิงของการย่อ "
               f"และแผงค่า CHOP",
        "caption": f"กราฟ{profile['thai_name']} {trigger['thai']} พร้อมแถบโซนอ้างอิง"
                   f"ระหว่างเส้น Tenkan กับ Kijun ของกรอบใหญ่ และแผงค่า CHOP",
        "explanation": (
            "จากภาพที่ 2 แถบแนวนอนคือโซนอ้างอิงที่ยกมาจากกรอบใหญ่ ไม่ใช่เส้นที่คำนวณ"
            "จากกรอบเล็ก ส่วนแผงล่างคือค่าที่บอกว่าตลาดมีระเบียบแค่ไหน"),
    }


def number_tokens(story: dict) -> set[str]:
    money = base.money_for(story)
    cloud, chop, volatility = story["ichimoku"], story["chop"], story["atr"]
    zone, now = story["pullback_zone"], story["ichimoku"]["cloud_now"]
    tokens = {
        money(cloud["tenkan"]), money(cloud["kijun"]),
        money(now["top"]), money(now["bottom"]),
        money(zone["low"]), money(zone["high"]),
        money(volatility["value"]),
        base.one(chop["value"]), base.plain(chop["length"]),
        base.plain(volatility["length"]), base.plain(cloud["base"]),
        base.plain(story["thresholds"]["chop_trending"]),
        base.plain(story["thresholds"]["chop_choppy"]),
    }
    # กรอบเวลาชั้นบริบทมีเลขติดมากับชื่อ ("ราย 30 นาที" · "M30")
    context = _context_words(story)
    import re as _re
    for text in (context["bar"], context["front"], context["short"], context["code"]):
        tokens |= {token.rstrip(".,") for token in _re.findall(r"\d[\d,\.]*", text)}
    return tokens


def required_headings(story: dict) -> list[str]:
    return [base.H2_BOX, h2_overview(story), base.H2_EVIDENCE, base.H2_WATCH,
            base.H2_INVALIDATION, base.H2_SUMMARY]


def render_article(story: dict) -> str:
    return base.render_article(story, sys.modules[__name__])


def validate(markdown: str, story: dict) -> dict:
    return base.validate(markdown, story, sys.modules[__name__])
