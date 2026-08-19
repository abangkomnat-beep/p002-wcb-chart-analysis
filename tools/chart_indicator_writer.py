"""นักเขียนสไตล์ E — แผนเทรดตามอินดิเคเตอร์ (RSI/MACD/Fibonacci) + ด่านตรวจของสไตล์นี้เอง

โครงบทตามต้นแบบที่หัวหน้าเลือก (th.tradingview.com/chart/XAUUSD/vxcu4F8w):
หัวข้อเรียงเลขแบบแผนเทรด — 1. ภาพรวม RSI/MACD/Fibonacci · 2. เจาะอินดิเคเตอร์
· 3. ระดับ Fibonacci · 4. Trading Scenario · 5. สรุป

เส้นแบ่งเดียวกับสไตล์ D: **ศัพท์กรอบวิเคราะห์ใช้ได้ แต่ตัวเลขต้องมาจาก story เท่านั้น**
ด่าน `validate` แบบ fail-closed — เลขนอกทะเบียนตัวเดียว = ตกทั้งบท

ตามคำสั่งผู้ใช้ 2026-08-19 สไตล์ E ไม่แสดงหรือใช้ R:R เป็นส่วนหนึ่งของแผนแล้ว
บทคงเฉพาะเงื่อนไข Entry Zone, SL, TP และสถานะของราคาเทียบโซน

สไตล์นี้ไม่อยู่ใน `WCB_WRITERS` โดยเจตนา — แยกขาดจาก A/B/C และ D
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import candle_close, chart_indicator, chart_story, consistency_gate, headline_format  # noqa: E402
from tools import intraday_bars  # noqa: E402
from tools import image_output, wcb_source, wcb_writers  # noqa: E402
from tools.chart_story_renderer import macd_for, money_for, thai_date  # noqa: E402
# หัวไฟล์ใช้ตัวประกอบเดียวกับสไตล์ D — คนละสไตล์แต่สัญญาไฟล์กับเว็บชุดเดียวกัน
# (แยกเขียนเองเมื่อไหร่ สองสไตล์จะเพี้ยนกันได้ แบบเดียวกับบทเรียน B-3.3)
from tools.chart_story_writer import frontmatter_lines as chart_story_writer_frontmatter  # noqa: E402
from tools.chart_story_writer import publish_date_of as chart_story_writer_publish_date  # noqa: E402

STYLE_ID = "e_indicator"
STYLE_NAME = "E — อ่านอินดิเคเตอร์"
FOLDER = "E-อินดิเคเตอร์"
# นับเฉพาะตัวอักษร (เกณฑ์แบบเดียวกับสไตล์ D) — บทที่ fib ไม่ผ่านเกณฑ์ยังมี 3 หัวข้อ
# อินดิเคเตอร์เต็ม ~1,600 อักขระ · ของจริงครบชุด ~3,500+ · ต่ำกว่านี้ = โครงหาย
MIN_CHARS = 1200
# คงไว้เพื่อให้สมุดสถิติรุ่นเก่าอ่านข้อมูลย้อนหลังได้เท่านั้น สายผลิตและบท Style E
# ไม่บันทึก ไม่แสดง และไม่ตัดสินแผนด้วย R:R แล้วตามคำสั่งผู้ใช้ 2026-08-19
RR_FLOOR = 1.2
_NUMBER = re.compile(r"\d[\d,\.]*")

# ------------------------------------------- ชื่อหัวข้อตามใบตัวอย่าง (ผู้ใช้สั่ง 08-11)
#
# คัดลอกจาก `01-CC/Input/ภาษาการเขียน/สไตล์E.md` ทีละตัวอักษร — ห้ามแก้ถ้อยคำเอง
# **จำนวนหัวข้อลดเหลือสี่** เพราะผู้ใช้สั่งรวม RSI/MACD/Fibonacci เป็นหัวข้อเดียว
# ⚠️ เลขลำดับหัวข้ออยู่ในทะเบียน `allowed_numbers()` แล้ว ("1"–"4")
RULE = ("---", "")
H2_STRUCTURE = "ภาพรวมสัญญาณ RSI, MACD และ Fibonacci"
H2_INDICATORS = "เจาะลึก RSI, MACD และ Fibonacci"
FIB_BLOCK = "**ระดับ Fibonacci Retracement**"
H2_SCENARIOS = "แผนการเทรดและจุดเข้าซื้อขาย (Trading Scenarios)"
H2_SUMMARY = "สรุปภาพรวมและคำแนะนำประจำวัน"


def image_name(asset: str, date_text: str, timeframe: str = chart_indicator.TIMEFRAME) -> str:
    """ชื่อไฟล์ภาพประกอบ H1 ใบเดียวของบท"""
    timeframe_slug = "h1" if timeframe == chart_indicator.TIMEFRAME else "d1"
    return f"{asset}-{timeframe_slug}-indicators-{date_text}{image_output.IMAGE_SUFFIX}"


def _is_h1(story: dict) -> bool:
    return story.get("timeframe") == chart_indicator.TIMEFRAME


def rsi_text(value: float) -> str:
    return f"{value:.1f}"


# ---------------------------------------------------------------- ตัวเขียนบท

def _rsi_paragraph(story: dict) -> str:
    rsi = story["rsi"]
    direction = "โค้งขึ้น" if rsi["rising"] else "โค้งลง"
    timeframe_text = "บนกราฟ H1 ล่าสุด" if _is_h1(story) else "รายวันล่าสุด"
    text = (f"RSI (14) {timeframe_text}อยู่ที่ {rsi_text(rsi['value'])} "
            f"และเริ่ม{direction}เมื่อเทียบกับ {chart_indicator.RSI_SLOPE_BARS} แท่งก่อนหน้า ")
    if rsi["zone"] == "overbought":
        text += ("ค่าเกิน 70 เข้าเขต Overbought แล้ว — โมเมนตัมขาขึ้นแรงจริง "
                 "แต่เป็นย่านที่การไล่ราคามีความเสี่ยงต่อแรงขายทำกำไรมากขึ้นทุกแท่ง")
    elif rsi["zone"] == "oversold":
        text += ("ค่าต่ำกว่า 30 เข้าเขต Oversold แล้ว — แรงขายกดมาลึกจนตลาดตึงตัว "
                 "โอกาสเกิดแรงเด้งทางเทคนิค (Technical Rebound) เริ่มสะสมตัว")
    elif rsi["zone"] == "bullish":
        text += ("ค่านี้ยังอยู่เหนือเส้นกึ่งกลาง 50 สะท้อนว่าแรงซื้อระยะกลางยังได้เปรียบ "
                 "แต่ยังไม่แตะเขต Overbought ที่ 70 จึงต้องติดตามว่าแรงซื้อจะรักษา"
                 "ความต่อเนื่องได้หรือไม่")
    else:
        text += ("ค่ายังอยู่ใต้เส้นกึ่งกลาง 50 แปลว่าฝั่งขายยังคุมโมเมนตัมระยะกลาง "
                 "แต่ยังไม่ลงไปแตะเขต Oversold ที่ 30 — แรงขายมีอยู่จริงแต่ยังไม่สุดทาง")
    return text


def _macd_paragraph(story: dict) -> str:
    money = money_for(story)
    macd_fmt = macd_for(story)
    macd = story["macd"]
    state = "ฝั่งบวก โดยเส้น MACD อยู่เหนือเส้นสัญญาณ (Signal)" if macd["bullish"] \
        else "ฝั่งลบ (เส้น MACD อยู่ใต้เส้น Signal)"
    text = (f"MACD (12, 26, 9) ตอนนี้อยู่{state} "
            f"ค่าเส้น MACD ล่าสุดอยู่ที่ {macd_fmt(macd['line'])} เทียบกับเส้นสัญญาณที่ "
            f"{macd_fmt(macd['signal'])} ส่วน Histogram อยู่ที่ {macd_fmt(macd['histogram'])} ")
    if macd["cross_date"]:
        cross_kind = "ตัดขึ้น (Bullish Crossover)" if macd["bullish"] else "ตัดลง (Bearish Crossover)"
        text += f"การ{cross_kind} ครั้งล่าสุดเกิดเมื่อ {thai_date(macd['cross_date'])} "
    if macd["histogram_shrinking"]:
        text += ("ขณะที่แท่ง Histogram กำลังหดตัว สะท้อนว่าแรงส่งของรอบปัจจุบันเริ่มชะลอ "
                 "แต่ยังไม่เพียงพอที่จะยืนยันการกลับตัว")
    else:
        text += ("และแท่ง Histogram ยังขยายตัวต่อเนื่อง — แรงส่งของฝั่งปัจจุบันยังไม่มีอาการอ่อนแรง")
    return text


def _fib_lines(story: dict) -> list[str]:
    money = money_for(story)
    fib = story["fib"]
    if not fib:
        return ["รอบนี้ระบบไม่พบ swing ที่กว้างพอผ่านเกณฑ์ (อย่างน้อย 2 เท่าของ ATR) "
                "จึงไม่วาง Fibonacci และจะไม่ตั้งระดับขึ้นเองจากความรู้สึกแทนครับ"]
    # 🔄 ย่อ 08-14 รอบสี่ (ผู้ใช้เลือกแบบ A): คำอธิบายทุกชั้นเหลือใจความ ตัดบรรทัดนำ
    # "ระดับย้อนกลับ (Retracement) ที่ได้จาก swing ชุดนี้:" ทิ้ง (หัวข้อบอกอยู่แล้ว)
    # ⚠️ ราคาทุกชั้นต้องยังอยู่ครบ — ด่าน `fib_level_not_in_article` ตรวจว่าเส้นที่ภาพ
    # จะขีดมีในบทไหม ขาดชั้นไหน = เส้นกำพร้า บทตกทั้งใบ (ย่อได้แค่คำอธิบาย ไม่ใช่เลข)
    if fib["direction"] == "down":
        swing_prefix = "บนกราฟ H1 " if _is_h1(story) else ""
        swing_text = (f"{swing_prefix}วัดจากจุดสูงสุดเดิมที่ {money(fib['swing_high']['price'])} ดอลลาร์ "
                      f"({thai_date(fib['swing_high']['date'])}) ลงมาถึงจุดต่ำสุดเดิมที่ "
                      f"{money(fib['swing_low']['price'])} ดอลลาร์ "
                      f"({thai_date(fib['swing_low']['date'])}) ซึ่งเป็นขาลงหลักที่ตลาดกำลังย้อนทดสอบ")
    else:
        swing_prefix = "บนกราฟ H1 " if _is_h1(story) else ""
        swing_text = (f"{swing_prefix}วัดจากจุดต่ำสุดเดิมที่ {money(fib['swing_low']['price'])} ดอลลาร์ "
                      f"({thai_date(fib['swing_low']['date'])}) ขึ้นไปถึงจุดสูงสุดเดิมที่ "
                      f"{money(fib['swing_high']['price'])} ดอลลาร์ "
                      f"({thai_date(fib['swing_high']['date'])}) — ขาขึ้นหลักที่ตลาดกำลังย่อทดสอบ")
    levels = {f"{level['ratio']:g}": level["price"] for level in fib["levels"]}
    golden_low, golden_high = fib["golden"]
    if fib["direction"] == "down":
        level_0236 = ("แนวรับแรกของการรีบาวด์ หากกลับลงมาต่ำกว่าระดับนี้ "
                      "แรงส่งของการฟื้นตัวจะเริ่มลดลง")
        level_0382 = "แนวต้านแรก ใช้ประเมินว่าการรีบาวด์จะเดินหน้าต่อได้หรือไม่"
        golden_text = "พื้นที่แนวต้านหลักของการรีบาวด์"
        extension_text = "แนวอ้างอิงด้านล่าง หากราคาหลุดจุดต่ำสุดเดิม"
    else:
        level_0236 = ("แนวรับแรกของการย่อตัว หากราคาหลุดระดับนี้ "
                      "การพักฐานอาจลึกลงไปยังแนวรับถัดไป")
        level_0382 = "แนวรับถัดไป ใช้ประเมินว่าแรงซื้อจะกลับเข้ามารองรับราคาได้หรือไม่"
        golden_text = "พื้นที่แนวรับหลักของการย่อตัว"
        extension_text = "แนวอ้างอิงด้านบน หากราคาทะลุจุดสูงสุดเดิม"
    return [
        swing_text, "",
        # 🐞 **B-3.2 (ทีมเว็บ 2026-08-09):** ภาพวาดเส้นที่บทไม่ได้พูดถึง ⇒ นอกจากตัด
        # 0.705/0.886 ออกจากชุดข้อมูลแล้ว ต้องเติม 0.236 ลงในรายการนี้ด้วย เพราะเดิม
        # ราคาระดับ 0.236 โผล่ในบทเฉพาะตอนที่ฉากทัศน์ผ่านเกณฑ์ระยะห่างรายวัน (เป็น TP1)
        # — วันไหนทั้งสองฉากทัศน์อยู่ไกลเกินเกณฑ์ เส้นนี้จะกลายเป็นเส้นกำพร้าบนภาพทันที
        f"- **0.236** — {money(levels['0.236'])} ดอลลาร์: {level_0236}",
        f"- **0.382** — {money(levels['0.382'])} ดอลลาร์: {level_0382}",
        f"- **0.5** — {money(levels['0.5'])} ดอลลาร์: "
        "กึ่งกลางของคลื่นหลัก ใช้ดูว่าราคาย้อนกลับมาเกินครึ่งทางแล้วหรือยัง",
        # (OTE — Optimal Trade Entry) ถูกถอดจากบรรทัดนี้ 08-14 (ผู้ใช้สั่ง — ไม่ขยายศัพท์)
        # · หาง "และเป็นหัวใจของแผนในหัวข้อถัดไป" ถอดรอบสี่ (ผู้ใช้สั่ง)
        f"- **Golden Zone (0.618–0.786)** — {money(golden_low)}–{money(golden_high)} ดอลลาร์: "
        f"{golden_text}",
        f"- **1.272** — {money(fib['extension'])} ดอลลาร์: {extension_text}",
    ]


def _indicator_overview(story: dict) -> str:
    """หัวข้อเปิดของสไตล์ E — อ่าน RSI, MACD และ Fibonacci โดยไม่ยืมภาษาโครงสร้าง D."""
    rsi = story["rsi"]
    macd = story["macd"]
    rsi_positive = rsi["zone"] in {"bullish", "overbought"}
    macd_positive = macd["bullish"]

    if rsi_positive and macd_positive:
        text = (f"ภาพรวมอินดิเคเตอร์ยังให้น้ำหนักฝั่งบวกอย่างระมัดระวัง RSI อยู่ที่ "
                f"{rsi_text(rsi['value'])} และ MACD ยังอยู่ฝั่งบวก "
                "สะท้อนว่าแรงซื้อยังไม่เสียเปรียบ")
    elif not rsi_positive and not macd_positive:
        text = (f"ภาพรวมจากอินดิเคเตอร์ยังให้น้ำหนักฝั่งลบ RSI อยู่ที่ "
                f"{rsi_text(rsi['value'])} และ MACD อยู่ฝั่งลบ "
                "แสดงว่าแรงขายยังได้เปรียบ")
    else:
        text = (f"ภาพรวมจากอินดิเคเตอร์ให้สัญญาณผสม RSI อยู่ที่ "
                f"{rsi_text(rsi['value'])} ขณะที่ MACD อยู่"
                f"{'ฝั่งบวก' if macd_positive else 'ฝั่งลบ'} "
                "จึงยังไม่เห็นแรงส่งที่สอดคล้องกันทั้งสองตัว")

    rsi_curve = "โค้งขึ้น" if rsi["rising"] else "โค้งลง"
    if macd["histogram_shrinking"]:
        text += (f" อย่างไรก็ตาม RSI เริ่ม{rsi_curve} ขณะที่แท่งฮิสโตแกรม (Histogram) ของ MACD หดตัว "
                 "แสดงว่าแรงส่งกำลังชะลอลง")
    else:
        text += (f" ขณะที่ RSI เริ่ม{rsi_curve}และ Histogram ของ MACD ยังขยายตัว "
                 "บอกว่าแรงส่งของฝั่งปัจจุบันยังต่อเนื่อง")

    fib = story.get("fib")
    if not fib:
        return text + " ส่วน Fibonacci รอบนี้ยังไม่มี swing ที่ผ่านเกณฑ์สำหรับวางระดับ"

    levels = {round(float(level["ratio"]), 3): level["price"] for level in fib["levels"]}
    first, second = levels.get(0.236), levels.get(0.382)
    if first is None or second is None:
        return text + " ในด้านระดับราคาให้ติดตามแนว Fibonacci ที่ระบบคำนวณไว้ในหัวข้อถัดไป"

    money = money_for(story)
    profile = wcb_source.profile_for(story["asset"])
    asset_name = profile["seo_name"]
    joiner = " " if re.search(r"[A-Za-z0-9/]$", asset_name) else ""
    if fib["direction"] == "down" and story["current"]["close"] >= first:
        text += (f" ด้านระดับราคา {asset_name}{joiner}ยืนเหนือ Fibonacci 0.236 ที่ "
                 f"{money(first)} ดอลลาร์แล้ว")
        if story["current"]["close"] < second:
            text += f" โดยมี Fibonacci 0.382 บริเวณ {money(second)} ดอลลาร์เป็นแนวต้านถัดไป"
        else:
            text += f" และกำลังประเมินแรงซื้อเหนือ Fibonacci 0.382 ที่ {money(second)} ดอลลาร์"
    else:
        text += (f" ในด้านระดับราคา Fibonacci 0.236 ที่ {money(first)} ดอลลาร์ และ "
                 f"Fibonacci 0.382 ที่ {money(second)} ดอลลาร์ เป็นสองระดับแรกที่ต้องติดตาม")
    return text


def _scenario_name_thai(scenario: dict, label: str) -> str:
    side_en = scenario["side"].upper()
    side_th = "ซื้อ" if scenario["side"] == "buy" else "ขาย"
    kind_en = "Follow Trend" if label == "A" else "Counter Trend"
    kind_th = "ตามแนวโน้ม" if label == "A" else "สวนแนวโน้ม"
    return f"ฝั่ง{side_th}{kind_th} ({side_en} — {kind_en})"


def _scenario_heading(scenario: dict, label: str) -> str:
    """หัวข้อย่อยของฉากทัศน์ตามใบตัวอย่าง 08-11 — `### 📈 แผน A: ฝั่ง SELL (…)`

    **ฝั่งซื้อ/ขายมาจาก `scenario["name"]` ไม่ได้เดาจากตัวอักษร A/B** — วันที่โหมด
    ตลาดพลิก แผนหลักจะเป็นฝั่งตรงข้ามกับวันก่อน ถ้าตรึงไว้ตามตัวอักษร หัวข้อจะโกหก
    · รูปแบบชื่อคือ `"SELL (Follow Trend)"` ⇒ แทรกคำไทยเข้าไปในวงเล็บ
    อ่านรูปไม่ออก = ใช้ชื่อดิบ ไม่เดาต่อ (กติกาเดียวกับ `_calendar_block` ของ A/B/C)

    หัวข้อไม่ใช้อีโมจิตามมติผู้ใช้ 2026-08-18
    """
    note = "เทรดตามแนวโน้มใหญ่" if label == "A" else "เก็งกำไรระยะสั้น"
    name = scenario["name"]
    if " (" in name and name.endswith(")"):
        side, kind = name[:-1].split(" (", 1)
        return f"### แผน {label}: ฝั่ง {side} ({kind} — {note})"
    return f"### แผน {label}: {name} ({note})"


def _scenario_block(scenario: dict, *, label: str, headline: str,
                    money, confirm_text: str) -> list[str]:
    """แผนหลักฝั่งเดียวที่หลักฐาน H1 สนับสนุนมากที่สุด

    E-3 (ฟีดแบ็กหัวหน้า 08-07): ทุกราคาที่พูดถึงต้องบอกด้วยว่าเป็น Fib ระดับไหน —
    เดิม TP1 ถูกใช้ในทั้งสองฉากทัศน์แต่บทไม่เคยบอกว่ามันคือ Fib 0.236 คนอ่านหาที่มา
    ของตัวเลขไม่เจอ · และต้องบอกสถานะว่าฉากทัศน์นี้ "active" หรือ "รอ" — เดิมเคยเขียนว่า
    "รอราคาย่อกลับลงมา" ทั้งที่ราคาอยู่ในโซนนั้นแล้ว ขัดกับความจริงตรง ๆ

    🔄 08-11: บรรทัดหัวเปลี่ยนจาก `**Scenario A: …**` เป็นหัวข้อย่อย `###` ตามใบตัวอย่าง
    และคำบรรยายสไตล์ของแผนย้ายลงมาเป็นบรรทัดตัวเอียงใต้หัวข้อ (ใบตัวอย่างวางแบบนี้)
    """
    lines = [_scenario_heading(scenario, label), "",
             f"*{headline}*", "",
             f"- **เงื่อนไข:** {scenario['condition'].replace('ปลาย swing เดิมแล้ว', 'จุดต่ำสุดเดิมและ') if scenario['side'] == 'buy' else scenario['condition'].replace('ปลาย swing เดิมแล้ว', 'จุดสูงสุดเดิมและ')}",
             f"- **สัญญาณยืนยัน:** {confirm_text}",
             # ป้าย "(Fibonacci …)" ท้าย Entry/TP ถูกถอด 08-14 รอบสอง (ผู้ใช้สั่ง) —
             # ที่มาของทุกระดับยังไล่ได้จากหัวข้อ 3 ซึ่งลิสต์ราคาของทุกชั้น Fib อยู่แล้ว
             # และด่าน `fib_level_not_in_article` ตรวจที่ราคา ไม่ใช่ป้าย
             f"- **Entry Zone:** {money(min(scenario['entry_low'], scenario['entry_high']))}–"
             f"{money(max(scenario['entry_low'], scenario['entry_high']))} ดอลลาร์",
             # วงเล็บอธิบายที่มาของ SL ถูกถอด 08-14 (ผู้ใช้สั่ง: หัวข้อ 4 เอาแค่ตัวเลขสำคัญ)
             f"- **SL:** {money(scenario['sl'])} ดอลลาร์"]
    tp_parts = [f"TP{order} {money(target)} ดอลลาร์"
                for order, target in enumerate(scenario["tps"], 1)]
    lines.append(f"- **TP:** {' · '.join(tp_parts)}")
    lines.append("- **สถานะวันนี้:** " + (
        "ราคาอยู่ในโซนเข้าแล้ว — รอสัญญาณยืนยัน"
        if scenario.get("active")
        else "ราคายังไม่เข้าโซน — แผนรอ"))
    return lines


def _scenario_lines(story: dict) -> list[str]:
    money = money_for(story)
    primary = story["scenarios"]["primary"]
    if not primary:
        return ["รอบนี้ไม่มีชุด Fibonacci ที่ผ่านเกณฑ์ จึงไม่มีแผนที่ระบบกล้าตั้งให้ "
                "และจะไม่ตั้งระดับจากความรู้สึกแทนครับ"]

    # E-1 (ฟีดแบ็กหัวหน้า 08-07): บังคับกฎระยะห่างรายวัน (10×ATR) กับสไตล์ E ด้วย —
    # เดิมไม่มีตัวกรองนี้เลย ⇒ Golden Zone เคยห่างราคา 14.8–20.6% (13.8–19.2×ATR) แต่ยัง
    # ถูกเสนอเป็นแผนหลักของบท "รายวัน" กฎเดียวกับที่บังคับสไตล์ D ในรายการ #14 ของ STATUS.md
    # 🔄 08-14 (ผู้ใช้สั่ง): หัวข้อ 4 ต้องกระชับ เอาแค่ตัวเลขสำคัญ — คำบรรยายแผนกับ
    # ประโยค Confirmation ถูกตัดให้เหลือใจความ (สัญญาณอะไร ที่กรอบไหน) ไม่เล่าเหตุผลซ้ำ
    plan_timeframe = "H1" if _is_h1(story) else "รายวัน"
    if not primary.get("daily_entry", True):
        return [
            f"**แผน A: {_scenario_name_thai(primary, 'A')} ไม่แสดงในบทนี้** — "
            f"โซนเข้าห่างจากราคาปัจจุบันเกินเกณฑ์แผน{(' ' if _is_h1(story) else '')}{plan_timeframe}",
            f"รอบนี้แผนฝั่งที่หลักฐานสนับสนุนมากที่สุดยังอยู่ไกลเกินเกณฑ์ {plan_timeframe} "
            "จึงเฝ้าดูโดยไม่สร้างแผนฝั่งตรงข้ามมาทดแทนครับ",
        ]

    confirm = (f"แท่งเทียนแสดง{'แรงขาย' if primary['side'] == 'sell' else 'แรงซื้อ'}ชัดเจนในโซน "
               + ("+ RSI กลับใต้เส้น 50 หรือ Histogram ของ MACD พลิกเป็นลบ"
                  if primary["side"] == "sell"
                  else "+ RSI กลับเหนือเส้น 50 หรือ Histogram ของ MACD พลิกเป็นบวก"))
    lines = _scenario_block(primary, label="A", headline="เทรดตามเทรนด์หลัก",
                            money=money, confirm_text=confirm)
    # บล็อก "ขั้นตอนปฏิบัติ — ลำดับก่อนเข้าเทรด" (3 ขั้น · เพิ่ม 08-11) ถูกถอด 08-14
    # ตามคำสั่งผู้ใช้: หัวข้อ 4 เอาแค่ตัวเลขสำคัญ ไม่ขยายความ — ใจความของสามขั้น
    # (รอเข้าโซน · รอ Confirmation · วาง SL) อยู่ในช่อง Entry Zone/Confirmation/SL
    # ของแต่ละแผนครบแล้ว
    return lines


def headline(story: dict) -> str:
    """H1 ของสไตล์ E — รูปแบบเดียวกับ D ตามสเปก SEO ของหัวหน้า (2026-08-10)

    หางบอกว่าบทนี้อ่านด้วยเครื่องมืออะไร ซึ่งเป็นจุดต่างของสไตล์นี้ — สไตล์ D
    เล่าโครงสร้างกราฟ สไตล์ E เล่าอินดิเคเตอร์ · ส่วนหน้ายังมาจาก `headline_format`
    จุดเดียวกับทุกสไตล์ ห้ามประกอบเอง
    """
    profile = wcb_source.profile_for(story["asset"])
    close = story["current"]["close"]
    sma50 = story["sma50_last"]
    verb = "ยืน" if sma50 is None or close >= sma50 else "หลุด"
    # 🔄 08-14 (มติผู้ใช้): พาดหัวลงวันเผยแพร่ ไม่ใช่วันแท่งฐาน — ต้องตรงกับ
    # ทุกสไตล์ในรอบเดียวกัน · วันแท่งฐานยังบอกไว้ในย่อหน้าเปิดของบท
    return headline_format.h1(
        story["asset"], chart_story_writer_publish_date(story),
        f"{profile['short_name']}{verb} {close:,.0f} {_indicator_watch(story)}")


def _indicator_watch(story: dict) -> str:
    """วลี "ต้องจับตาอะไร" ของสไตล์ E — เล่าด้วยสภาพอินดิเคเตอร์เป็นภาษาคน

    ของเดิมคือ "อ่าน RSI MACD Fibonacci XAU/USD" ซึ่งบอกแค่ว่าบทใช้เครื่องมืออะไร
    ไม่ได้บอกว่าเกิดอะไรขึ้น (ผู้ใช้ 2026-08-10: "อ่านแล้วยังงง ไม่เข้าใจ")
    ⛔ ห้ามชี้ทิศ — บอกสภาพที่วัดได้เท่านั้น
    """
    rsi = story["rsi"]["value"]
    if rsi >= 70:
        return "RSI เข้าเขตซื้อมากเกินไป"
    if rsi <= 30:
        return "RSI เข้าเขตขายมากเกินไป"
    if story["macd"]["cross_date"]:
        side = "ฝั่งบวก" if story["macd"]["bullish"] else "ฝั่งลบ"
        return f"MACD ยังอยู่{side}"
    return "เช็ก RSI กับ MACD ก่อนเข้าไม้"


def seo_title(story: dict) -> str:
    """Title tag ของสไตล์ E — หางของตัวเอง ไม่ใช่หางคงที่ของทะเบียน

    ⚠️ **ห้ามใช้หางทะเบียนเหมือนสไตล์ D** — สองสไตล์ผลิตจากข้อมูลวันเดียวกัน ถ้าใช้หาง
    เดียวกันจะได้ Title เหมือนกันเป๊ะสองใบ (เกิดจริงรอบแรกของการแก้นี้) · เว็บตั้งชื่อบท
    จากสินทรัพย์+วันที่ ⇒ สองใบที่พาดหัวเหมือนกันแยกไม่ออกว่าใบไหนเป็นใบไหน

    หางปัจจุบันเป็นแบบที่ผู้ใช้เลือกจากห้าตัวเลือก (2026-08-10) — เน้นสิ่งที่ผู้อ่านได้
    แทนการไล่ชื่ออินดิเคเตอร์ เพราะคนที่ยังไม่รู้จักชื่อเครื่องมือจะไม่คลิกพาดหัวที่เป็นศัพท์ล้วน

    หางนี้สัญญาว่าบทมี "จุดเข้า" ของแผนหลักฝั่งเดียว ซึ่งต้องมีโซนเข้า · SL · TP
    และสถานะว่าราคาเข้าโซนหรือยัง
    """
    profile = wcb_source.profile_for(story["asset"])
    return headline_format.title(story["asset"], chart_story_writer_publish_date(story),
                                 f"จุดเข้าจากสัญญาณเทคนิค {profile['symbol']}")


def render_article(story: dict) -> str:
    money = money_for(story)
    combined_image = image_name(story["asset"], story["current"]["date"],
                                story.get("timeframe", "1day"))
    down = story["regime"]["down"]
    current_text = money(story["current"]["close"])
    trend_word = "ขาลง" if down else "ขาขึ้น"
    heads = wcb_writers.SectionNumbers()

    if _is_h1(story):
        opening = (
            f"บทความนี้ประเมิน {story['symbol']} ด้วย RSI, MACD และ Fibonacci Retracement โดยใช้"
            f"แท่ง H1 ล่าสุดที่ปิดแล้ว ({thai_date(story['current']['date'])}) ที่ {current_text} "
            f"ดอลลาร์ ขณะที่ภาพรวม H1 ยังอยู่ในแนวโน้ม{trend_word}")
    else:
        opening = (
            f"บทความนี้ประเมิน {story['symbol']} ด้วย RSI, MACD และ Fibonacci Retracement โดยใช้"
            f"แท่งรายวันล่าสุด ({thai_date(story['current']['date'])}) ซึ่งปิดที่ {current_text} "
            f"ดอลลาร์ ขณะที่ภาพรวมรายวันยังอยู่ในแนวโน้ม{trend_word}")

    lines = chart_story_writer_frontmatter(story, title_text=seo_title(story), excerpt_clauses=[
        f"{wcb_source.profile_for(story['asset'])['short_name']}ปิดที่ {current_text} ดอลลาร์",
        f"RSI(14) ที่ {story['rsi']['value']:.1f}",
        "อ่านสัญญาณ RSI MACD และระดับ Fibonacci พร้อมจุดเข้าและจุดตัดขาดทุนของแผนหลัก",
        "ทุกค่าคำนวณจากแท่งราคาจริง",
    ]) + [
        "# " + headline(story),
        "",
        opening,
        "",
        *RULE,
        heads.head(H2_STRUCTURE),
        "",
    ]

    fib = story["fib"]
    # alt text ใส่ตัวเลขระดับสำคัญ (แนวเดียวกับฟีดแบ็กหัวหน้าต่อสไตล์ D) · ภาพเดียว
    # สามแผงตามคำสั่งผู้ใช้ 2026-08-07 — วางหลังหัวข้อแรก ที่เหลืออ้างภาพเดียวกัน
    alt_timeframe = " H1" if _is_h1(story) else ""
    alt_parts = [f"ภาพประกอบ{alt_timeframe} — ราคา · Fibonacci · RSI · MACD ของ {story['symbol']}"]
    if fib:
        golden_low, golden_high = fib["golden"]
        alt_parts.append(f"Golden Zone {money(golden_low)}–{money(golden_high)}")
    # 🔄 08-11: RSI กับ MACD เคยเป็นหัวข้อใหญ่คนละหัว — ใบตัวอย่างรวบเป็นหัวข้อเดียว
    # ("เจาะลึกสัญญาณอินดิเคเตอร์") แล้วแยกด้วย bullet ที่ขึ้นต้นด้วยชื่อเครื่องมือแทน
    # ⇒ ชื่อเครื่องมือยังอยู่ครบทุกตัว ไม่ได้หายไปกับหัวข้อ แค่ย้ายที่
    lines += [_indicator_overview(story), "",
              f"![{' · '.join(alt_parts)}]({combined_image})", "",
              *RULE,
              heads.head(H2_INDICATORS), "",
              f"- {_rsi_paragraph(story)}",
              f"- {_macd_paragraph(story)}", "",
              FIB_BLOCK, ""]
    lines += _fib_lines(story)
    lines += ["", *RULE, heads.head(H2_SCENARIOS), ""]
    lines += _scenario_lines(story)
    lines += [
        "",
        # 🔄 ย่อ 08-14 (ผู้ใช้สั่ง) — คงวลี "ไม่ใช่คำทำนาย" ไว้เพราะเป็นคำประกาศบังคับ
        # ของด่าน `scenario_disclaimer`
        "ระดับ Entry/SL/TP ทั้งหมดเป็นเงื่อนไขที่คำนวณจากระดับ Fibonacci และ ATR "
        "ไม่ใช่คำทำนาย",
        "",
        *RULE,
        heads.head(H2_SUMMARY),
        "",
    ]
    # ---- 5. สรุป — "ต้องดูอะไร ทำไม อย่างไร แล้วจะเป็นอย่างไรต่อ" (ผู้ใช้สั่ง 08-11
    # บ่าย ชุดเดียวกับสไตล์ D) · ทุกระดับเป็นค่าเดิมจาก story และยังเป็นเงื่อนไข
    # ไม่ใช่คำทำนาย — วันที่ไม่มีแผนรายวันให้ทำตาม ใช้สรุปแบบสั้นเดิม
    rsi_state = {"overbought": "RSI ร้อนจัดในเขต Overbought",
                 "oversold": "RSI ตึงตัวในเขต Oversold",
                 "bullish": "RSI ยังสะท้อนว่าแรงซื้อได้เปรียบ",
                 "bearish": "RSI ยังอยู่ฝั่งแรงขาย"}[story["rsi"]["zone"]]
    macd_state = "MACD ยังอยู่ฝั่งบวก" if story["macd"]["bullish"] else "MACD ยังอยู่ฝั่งลบ"
    # 🔄 08-14 (ผู้ใช้สั่ง): "สรุปสั้นที่สุดได้ว่า" ตัดทิ้ง — หัวข้อเป็นสรุปอยู่แล้ว
    momentum = f"{rsi_state} · {macd_state}"
    if story["macd"]["histogram_shrinking"]:
        momentum += " (แรงส่งเริ่มแผ่ว)"
    summary = f"เกมของวันนี้: {momentum}"
    primary = story["scenarios"]["primary"]
    near_primary = bool(primary and primary.get("daily_entry", True))
    if fib and near_primary:
        # 🔄 08-14 รอบสอง (ผู้ใช้สั่ง): แบบสี่คำถาม (ดูอะไร/ทำไม/อย่างไร/แล้วไงต่อ)
        # อ่านแล้วยังไม่เข้าใจ — เปลี่ยนเป็นสรุปจริงที่เปิดอ่านหัวข้อนี้หัวข้อเดียวแล้วจบ:
        # ราคาวันนี้อยู่ตรงไหน · รอเข้าฝั่ง BUY หรือ SELL · รอเข้าที่เท่าไร · ต้องรอดูอะไร
        # ตัวเลขทุกตัวเป็นค่าเดียวกับในหัวข้อ 4 (แผนเดียวกัน ไม่ใช่เลขใหม่)
        # 🔄 08-14 รอบสาม (ผู้ใช้สั่ง): ฝั่งที่รอเข้าเหลือชื่อฝั่งเปล่า ๆ (ชื่อแผนกับ
        # คำขยาย "ตาม/สวนเทรนด์" อยู่ในหัวข้อ 4 ครบแล้ว) — เว้นวันที่มีสองแผนพร้อมกัน
        # ซึ่งต้องคงป้ายแผนไว้ ไม่งั้นจับคู่กับบรรทัด "จุดที่รอเข้า" ไม่ได้
        plans = [("A", primary)]
        two = False
        sides = primary["side"].upper()
        entry_parts = []
        for label, scenario in plans:
            text = (f"{money(min(scenario['entry_low'], scenario['entry_high']))}–"
                    f"{money(max(scenario['entry_low'], scenario['entry_high']))} "
                    f"· SL {money(scenario['sl'])} · TP1 {money(scenario['tps'][0])}")
            entry_parts.append(f"แผน {label}: {text}" if two else text)
        # สิ่งที่ต้องสังเกต = เงื่อนไขที่ยัง "ไม่ครบ" ของวันนี้ เรียงตามลำดับที่ต้องเกิดจริง
        # (ราคาเข้าโซน ⇒ แรงรับ/แรงต้านใน TF ย่อย) แล้วจบ — ผู้ใช้สั่งย่อ 08-14 รอบสี่:
        # ตัดหมายเหตุ MACD (สภาพแรงส่งอยู่บรรทัด "ราคาวันนี้" แล้ว) และตัดวลี
        # "ไม่ใช่คำทำนาย" ท้ายบรรทัด — ด่าน `scenario_disclaimer` ยังผ่านเพราะประโยค
        # ปิดหัวข้อ 4 ถือวลีนั้นอยู่ ⚠️ ถ้าวันใดถอดประโยคนั้น ต้องหาที่ใหม่ให้วลีนี้
        trigger_timeframe = "15M/5M" if _is_h1(story) else "1H/15M"
        confirm = (f"สัญญาณยืนยันใน {trigger_timeframe} ของฝั่งที่ราคาไปถึงก่อน" if two else
                   ("แรงรับ" if plans[0][1]["side"] == "buy" else "แรงต้าน") + f"ใน {trigger_timeframe}")
        single_scenario = next((scenario for _label, scenario in plans), None) if not two else None
        watch_check = (f"ว่า{confirm} ช่วยให้ราคายืนได้หรือไม่"
                       if single_scenario and single_scenario["side"] == "buy"
                       else f"ว่า{confirm} เกิดขึ้นชัดเจนหรือไม่")
        watch = (f"ราคาอยู่ในโซนเข้าแล้ว — เหลือดู{watch_check}"
                 if any(scenario.get("active") for _label, scenario in plans)
                 else f"รอราคาเข้าโซนก่อน แล้วดู{watch_check} "
                      "ขณะนี้ยังไม่เข้าเกณฑ์ จึงเฝ้าดูโดยไม่เข้า")
        price_label = "ราคาล่าสุด" if _is_h1(story) else "ราคาวันนี้"
        price_context = (f"แท่ง H1 ปิดที่ {current_text} ดอลลาร์ แนวโน้ม H1 ยังเป็น{trend_word}"
                         if _is_h1(story) else
                         f"ปิดที่ {current_text} ดอลลาร์ แนวโน้มรายวันยังเป็น{trend_word}")
        summary_items = [
            f"**{price_label}:** {price_context} "
            f"· {momentum}",
            f"**ฝั่งที่รอเข้า:** {sides}",
            f"**จุดที่รอเข้า:** {' · '.join(entry_parts)}",
            f"**สิ่งที่ต้องสังเกต:** {watch}",
        ]
        lines += wcb_writers.listing("", summary_items)
        summary = None
    elif fib:
        golden_low, golden_high = fib["golden"]
        summary += (f" · จุดตัดสินใจสำคัญคือ Golden Zone {money(golden_low)}–"
                    f"{money(golden_high)} ดอลลาร์ "
                    f"แต่รอบนี้แผนหลักอยู่ห่างเกินเกณฑ์{' H1' if _is_h1(story) else 'รายวัน'} "
                    f"จึงเป็น{'ช่วง' if _is_h1(story) else 'วัน'}ของการเฝ้าดูครับ")
    else:
        summary += " · รอบนี้ไม่มีชุด Fibonacci ที่ผ่านเกณฑ์ จึงเป็นวันของการเฝ้าดูมากกว่าลงมือครับ"
    if summary is not None:      # สาขาที่มีแผนรายวันจบด้วย bullet แล้ว ไม่มีย่อหน้าปิดเพิ่ม
        lines += [summary]
    # ⚠️ ย่อหน้า "**คำเตือนความเสี่ยง:** …" ถูกถอด 2026-08-14 (ผู้ใช้สั่ง — เว็บมี
    # คำเตือนของตัวเองอยู่แล้ว บทจึงไม่ต้องพกซ้ำ) พร้อมด่าน `risk_disclaimer`
    # ที่เฝ้ามัน ⇒ **คำเตือนความเสี่ยงของสไตล์ E ตอนนี้ขึ้นกับเทมเพลตเว็บทั้งหมด**
    # ถ้าวันใดเว็บถอดของตัวเองออก บทจะไม่มีคำเตือนเลยและไม่มีอะไรฟ้อง
    # (สไตล์ D กับ A/B/C ยังมีของตัวเองตามเดิม — ไม่ได้แก้พร้อมกัน)
    lines += [""]
    return "\n".join(lines)


# ---------------------------------------------------------------- ด่านตรวจ

def allowed_numbers(story: dict) -> set[str]:
    """ทะเบียนเลขที่บทมีสิทธิ์พูดถึง — สร้างจาก story เท่านั้น

    เลขคงที่ = พารามิเตอร์อินดิเคเตอร์/อัตราส่วน Fibonacci ที่เป็นศัพท์กรอบวิเคราะห์
    (12/26/9/14/30/50/70, 0.236…1.272) ไม่ใช่ค่าที่วัดจากตลาด
    """
    money = money_for(story)
    macd_fmt = macd_for(story)
    allowed = {
        "1", "2", "3", "4", "9", "12", "14", "15", "26", "30", "50", "70",
        str(story["display"]["bars"]), str(story["display"]["fib_bars"]),
        str(chart_indicator.RSI_SLOPE_BARS),
    }
    for ratio in chart_indicator.FIB_RATIOS:
        allowed.add(f"{ratio:g}")
    allowed.add(f"{chart_indicator.EXTENSION_RATIO:g}")
    prices = [story["current"]["close"]]
    if story.get("sma50_last") is not None:
        prices.append(story["sma50_last"])
    fib = story["fib"]
    if fib:
        prices += [fib["swing_high"]["price"], fib["swing_low"]["price"], fib["extension"]]
        prices += [level["price"] for level in fib["levels"]]
        prices += list(fib["golden"])
    for key in ("primary",):
        scenario = story["scenarios"][key]
        if scenario:
            prices += [scenario["entry_low"], scenario["entry_high"], scenario["entry_mid"],
                       scenario["sl"], *scenario["tps"]]
    for value in prices:
        allowed.add(money(value))

    allowed.add(rsi_text(story["rsi"]["value"]))
    for key in ("line", "signal", "histogram"):
        allowed.add(macd_fmt(story["macd"][key]).lstrip("-"))

    # ชื่อไฟล์ภาพมีวันที่เต็มรูป (เช่น 2026-08-06) — เลขเดือน/วันแบบมีศูนย์นำ
    # ไม่ตรงกับทะเบียนวันที่ปกติ ต้องเพิ่มจากชื่อไฟล์ตรง ๆ
    for token in _NUMBER.findall(image_name(story["asset"], story["current"]["date"],
                                            story.get("timeframe", "1day"))):
        allowed.add(token.rstrip(".,"))

    # วันเผยแพร่โผล่ในพาดหัวและ Title tag (มติ 08-14) ⇒ ต้องอยู่ในทะเบียนด้วย
    dates = [chart_story_writer_publish_date(story),
             story["current"]["date"], story["regime"]["flip_date"],
             story["macd"]["cross_date"],
             story["display"]["start_date"], story["display"]["end_date"]]
    if fib:
        dates += [fib["swing_high"]["date"], fib["swing_low"]["date"]]
    # ราคาปิดแบบปัดที่ใช้ในพาดหัว ("ทองยืน 4,343") — ค่าเดียวกับราคาปิดจริง คนละการจัดรูป
    allowed.add(f"{story['current']['close']:,.0f}")
    for date_text in dates:
        if not date_text:
            continue
        year, _month, day = date_text.split("-")
        # ปีเดียวพอ — บท ชื่อไฟล์ภาพ และทะเบียนภายใน เป็น ค.ศ. ระบบเดียวกันหมด
        # ตั้งแต่ 08-11 (เดิมต้องขึ้นทะเบียนคู่ ค.ศ./พ.ศ. เพราะบทพิมพ์คนละระบบกับข้อมูล)
        allowed.add(year)
        allowed.add(str(int(day)))
    return allowed


def invalidation_pairs(story: dict) -> list[dict]:
    """ทุกคู่ (โซนเข้า ↔ SL) ที่บทสไตล์ E พูดถึง — B-1 (เกณฑ์เดียวกับสไตล์ D)

    SL คือ "จุดยกเลิกมุมมอง" ของฉากทัศน์ฝั่งนั้นตรง ๆ · ฉากทัศน์ที่ไม่ผ่านเกณฑ์
    ระยะห่างรายวันไม่ถูกแสดงในบท จึงไม่ต้องตรวจ (บทไม่ได้เสนอให้ใครทำตาม)
    """
    pairs = []
    for key, label in (("primary", "Scenario A"),):
        scenario = story["scenarios"].get(key)
        if not scenario or not scenario.get("daily_entry", True):
            continue
        pairs.append({
            "label": f"{label} ({scenario['name']})",
            "zone_low": min(scenario["entry_low"], scenario["entry_high"]),
            "zone_high": max(scenario["entry_low"], scenario["entry_high"]),
            "invalidation": scenario["sl"],
        })
    return pairs


def validate(markdown: str, story: dict) -> dict:
    """ด่านของสไตล์ E — fail-closed: findings ระดับ fatal ตัวเดียวก็ตก"""
    findings: list[dict] = []
    # ด่านความสอดคล้อง D-4.5 — ชุดเดียวกับสไตล์ D (โครงสร้างไฟล์เดียวกัน)
    findings.extend(consistency_gate.check(markdown, story))
    money = money_for(story)

    # ผู้ใช้ถอด R:R ออกจาก Style E 2026-08-19 — กันทั้งป้ายไทยและตัวย่ออังกฤษ
    # เพื่อไม่ให้กลับมาแฝงในบทจากการแก้ template รอบหลัง
    if ("อัตราส่วนเสี่ยง:ผลตอบแทน" in markdown
            or re.search(r"(?i)(?:\bR\s*:\s*R\b|\bRisk\s*/\s*Reward\b)", markdown)):
        findings.append({
            "rule": "risk_reward_forbidden", "severity": "fatal", "line": 1,
            "message": "Style E ไม่ใช้ R:R ในแผนแล้ว — คงเฉพาะ Entry, SL และ TP",
        })

    # 🐞 **A-1 (08-09):** บทเปิดด้วย "แท่งรายวันล่าสุดปิดที่ X" เหมือนสไตล์ D
    # ⇒ ผูกคำว่า "ปิด" กับแท่งที่พิสูจน์ได้ว่าปิดแล้วเท่านั้น พิสูจน์ไม่ได้ = ไม่ออกไฟล์
    if story.get("timeframe") == chart_indicator.TIMEFRAME:
        closed_detail = intraday_bars.verify(
            story.get("candle_basis"), asset=story["asset"],
            bar_at=story["current"].get("at") or "")
    else:
        closed_detail = candle_close.verify(
            story.get("candle_basis"), asset=story["asset"],
            session_date=story["current"]["date"])
    if closed_detail:
        findings.append({
            "rule": "closed_candle_required", "severity": "fatal", "line": 1,
            "message": f"บทเรียกราคาแท่งล่าสุดว่า 'ปิด' แต่ {closed_detail}",
        })

    # 🐞 **B-1 (08-09):** เกณฑ์ 1×ATR ต้องบังคับทุกสไตล์ ไม่ใช่เฉพาะสไตล์ D
    for message in chart_story.invalidation_findings(
            invalidation_pairs(story), story["atr14"]):
        findings.append({
            "rule": "invalidation_inside_entry_zone", "severity": "fatal", "line": 1,
            "message": message,
        })

    # 🐞 **B-3.2 (08-09):** ทุกเส้น Fibonacci ที่ artifact ถือไว้จะถูกวาดลงภาพทั้งชุด
    # ⇒ บทต้องพูดถึงราคาของทุกเส้นนั้น ไม่งั้นภาพมีเส้นที่บทไม่เคยอธิบาย (เส้นกำพร้า)
    if story["fib"]:
        for level in story["fib"]["levels"]:
            if money(level["price"]) not in markdown:
                findings.append({
                    "rule": "fib_level_not_in_article", "severity": "fatal", "line": 1,
                    "message": f"ภาพจะขีดเส้น Fibonacci {level['ratio']:g} ที่ "
                               f"{money(level['price'])} แต่บทไม่ได้พูดถึงระดับนี้เลย "
                               "— กราฟกับบทต้องมีเส้นชุดเดียวกัน",
                })
    allowed = allowed_numbers(story)
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        for token in _NUMBER.findall(line):
            token = token.rstrip(".,")
            if token and token not in allowed:
                findings.append({
                    "rule": "number_not_in_story", "severity": "fatal", "line": line_number,
                    "message": f"เลข '{token}' ไม่อยู่ในทะเบียนของ story — "
                               "บทสไตล์ E พูดได้เฉพาะเลขที่คำนวณจริง",
                })
    name = image_name(story["asset"], story["current"]["date"],
                      story.get("timeframe", "1day"))
    if f"({name})" not in markdown:
        findings.append({
            "rule": "missing_image", "severity": "fatal", "line": 1,
            "message": f"บทความไม่ได้อ้างภาพ {name} — สไตล์ E ต้องอ้างภาพประกอบเสมอ",
        })
    if story["scenarios"]["primary"] and "Trading Scenario" not in markdown:
        findings.append({
            "rule": "scenario_section", "severity": "fatal", "line": 1,
            "message": "story มีแผนหลัก แต่บทไม่มีหัวข้อ Trading Scenario — โครงต้นแบบบังคับ",
        })
    if "ไม่ใช่คำทำนาย" not in markdown:
        findings.append({
            "rule": "scenario_disclaimer", "severity": "fatal", "line": 1,
            "message": "ไม่พบประโยคประกาศว่าแผนเป็นเงื่อนไข ไม่ใช่คำทำนาย",
        })
    # ด่าน `risk_disclaimer` (บังคับให้ท้ายบทมีย่อหน้าคำเตือนความเสี่ยง) ถูกถอด
    # 2026-08-14 พร้อมย่อหน้าที่มันเฝ้า — ผู้ใช้สั่งถอดเพราะเว็บมีคำเตือนของตัวเองแล้ว
    # ⚠️ ถ้าวันใดเอาย่อหน้ากลับเข้าบท ต้องเอาด่านนี้กลับมาด้วย ไม่งั้นย่อหน้าหายเงียบ
    # ได้อีกโดยไม่มีอะไรฟ้อง (เหตุผลเดิมที่ตั้งด่านไว้ตั้งแต่แรก — บทขึ้นเว็บอัตโนมัติ
    # ไม่มีคนตรวจซ้ำ) · บทเรียนเดียวกับด่าน `entry_section` ของสไตล์ D
    # 🔄 **กลับด้าน 2026-08-10** — เดิมห้ามมี · ตอนนี้บังคับให้มี (เหตุผลเดียวกับสไตล์ D)
    if not markdown.lstrip().startswith("---"):
        findings.append({
            "rule": "frontmatter_required", "severity": "fatal", "line": 1,
            "message": "บทสไตล์ E ต้องมี frontmatter พร้อมช่อง title",
        })
    elif not re.search(r"(?m)^title:\s*\S", markdown):
        findings.append({
            "rule": "frontmatter_required", "severity": "fatal", "line": 1,
            "message": "frontmatter ไม่มีช่อง title",
        })
    # สเปก SEO 2026-08-10 — Title tag กับ H1 ต้องไม่เหมือนกัน (กฎเดียวกับสไตล์ D)
    first_line = next((line for line in markdown.splitlines() if line.startswith("# ")), "")
    if first_line and headline_format.same_headline(seo_title(story), first_line[2:]):
        findings.append({
            "rule": "title_equals_h1", "severity": "fatal", "line": 1,
            "message": "Title tag กับ H1 เหมือนกัน — สเปก SEO บังคับให้หางต่างกัน",
        })
    char_count = len(re.sub(r"\s", "", markdown))
    if char_count < MIN_CHARS:
        findings.append({
            "rule": "style_length_floor", "severity": "fatal", "line": 1,
            "message": f"เนื้อหามี {char_count} อักขระ ต่ำกว่าเกณฑ์ {MIN_CHARS} ของสไตล์ E",
        })
    fatal_count = sum(1 for finding in findings if finding["severity"] == "fatal")
    return {
        "status": "pass" if fatal_count == 0 else "fail",
        "fatal_count": fatal_count,
        "char_count": char_count,
        "findings": findings,
    }
