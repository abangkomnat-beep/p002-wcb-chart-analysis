"""นักเขียนสไตล์ E — แผนเทรดตามอินดิเคเตอร์ (RSI/MACD/Fibonacci) + ด่านตรวจของสไตล์นี้เอง

โครงบทตามต้นแบบที่หัวหน้าเลือก (th.tradingview.com/chart/XAUUSD/vxcu4F8w):
หัวข้อเรียงเลขแบบแผนเทรด — 1. โครงสร้างราคา · 2. RSI · 3. MACD · 4. Fibonacci
· 5. Trading Scenario สองฝั่งพร้อม เงื่อนไข/Confirmation/Entry Zone/SL/TP/RR

เส้นแบ่งเดียวกับสไตล์ D: **ศัพท์กรอบวิเคราะห์ใช้ได้ แต่ตัวเลขต้องมาจาก story เท่านั้น**
ด่าน `validate` แบบ fail-closed — เลขนอกทะเบียนตัวเดียว = ตกทั้งบท

RR ที่แสดงเป็นค่าคำนวณจริงจากระดับ (ไม่ใช่คำโฆษณา "1:3 ขึ้นไป" แบบต้นแบบ)
และถ้า RR ต่ำกว่ามาตรฐานขั้นต่ำของระบบ (1.2 — ค่าเดียวกับ minimum_rr ของสาย A)
บทจะบอกตรง ๆ ให้รอราคาเข้าลึกกว่านี้ ไม่ผ่อนเกณฑ์เพื่อให้แผนดูน่าเข้า

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
from tools import image_output, wcb_source, wcb_writers  # noqa: E402
from tools.chart_story_renderer import macd_for, money_for, thai_date  # noqa: E402
# หัวไฟล์ใช้ตัวประกอบเดียวกับสไตล์ D — คนละสไตล์แต่สัญญาไฟล์กับเว็บชุดเดียวกัน
# (แยกเขียนเองเมื่อไหร่ สองสไตล์จะเพี้ยนกันได้ แบบเดียวกับบทเรียน B-3.3)
from tools.chart_story_writer import frontmatter_lines as chart_story_writer_frontmatter  # noqa: E402

STYLE_ID = "e_indicator"
STYLE_NAME = "E — อ่านอินดิเคเตอร์"
FOLDER = "E-อินดิเคเตอร์"
# นับเฉพาะตัวอักษร (เกณฑ์แบบเดียวกับสไตล์ D) — บทที่ fib ไม่ผ่านเกณฑ์ยังมี 3 หัวข้อ
# อินดิเคเตอร์เต็ม ~1,600 อักขระ · ของจริงครบชุด ~3,500+ · ต่ำกว่านี้ = โครงหาย
MIN_CHARS = 1200
RR_FLOOR = 1.2   # มาตรฐานเดียวกับ minimum_rr ของสาย A — ห้ามผ่อนเพื่อให้แผนดูดี
_NUMBER = re.compile(r"\d[\d,\.]*")

# ------------------------------------------- ชื่อหัวข้อตามใบตัวอย่าง (ผู้ใช้สั่ง 08-11)
#
# คัดลอกจาก `01-CC/Input/ภาษาการเขียน/สไตล์E.md` ทีละตัวอักษร — ห้ามแก้ถ้อยคำเอง
# **จำนวนหัวข้อลดจากหกเหลือห้า** เพราะใบตัวอย่างรวบ RSI กับ MACD เป็นหัวข้อเดียว
# ⚠️ เลขลำดับหัวข้ออยู่ในทะเบียน `allowed_numbers()` แล้ว ("1"–"5")
RULE = ("---", "")
H2_STRUCTURE = "ภาพรวมโครงสร้างตลาด (Market Structure)"
H2_INDICATORS = "เจาะลึกสัญญาณอินดิเคเตอร์ (Technical Indicators)"
H2_FIB = "ระดับราคาสำคัญ Fibonacci Retracement"
H2_SCENARIOS = "แผนการเทรดและจุดเข้าซื้อขาย (Trading Scenarios)"
H2_SUMMARY = "สรุปภาพรวมและคำแนะนำประจำวัน"


def image_name(asset: str, date_text: str) -> str:
    """ชื่อไฟล์ภาพประกอบใบเดียวของบท — ผู้ใช้สั่งรวมภาพสไตล์ E 2026-08-07
    (สามแผงในผืนเดียว: ราคา+Fibonacci+แผนเทรด / RSI / MACD ตามหน้าตาต้นแบบ)
    รูปแบบชื่อมีความหมาย+วันที่ แนวเดียวกับสไตล์ D"""
    return f"{asset}-d1-indicators-{date_text}{image_output.IMAGE_SUFFIX}"


def rsi_text(value: float) -> str:
    return f"{value:.1f}"


def rr_display(rr: float) -> str:
    return f"1:{rr:.1f}"


# ---------------------------------------------------------------- ตัวเขียนบท

def _rsi_paragraph(story: dict) -> str:
    rsi = story["rsi"]
    direction = "โค้งขึ้น" if rsi["rising"] else "โค้งลง"
    text = (f"RSI (14) รายวันล่าสุดอยู่ที่ {rsi_text(rsi['value'])} "
            f"และ{direction}เมื่อเทียบกับ {chart_indicator.RSI_SLOPE_BARS} แท่งก่อนหน้า ")
    if rsi["zone"] == "overbought":
        text += ("ค่าเกิน 70 เข้าเขต Overbought แล้ว — โมเมนตัมขาขึ้นแรงจริง "
                 "แต่เป็นย่านที่การไล่ราคามีความเสี่ยงต่อแรงขายทำกำไรมากขึ้นทุกแท่ง")
    elif rsi["zone"] == "oversold":
        text += ("ค่าต่ำกว่า 30 เข้าเขต Oversold แล้ว — แรงขายกดมาลึกจนตลาดตึงตัว "
                 "โอกาสเกิดแรงเด้งทางเทคนิค (Technical Rebound) เริ่มสะสมตัว")
    elif rsi["zone"] == "bullish":
        text += ("ค่ายืนเหนือเส้นกึ่งกลาง 50 ได้ แปลว่าแรงซื้อระยะกลางยังคุมเกมอยู่ "
                 "และยังไม่แตะเขต Overbought ที่ 70 — โมเมนตัมมีพื้นที่ให้วิ่งต่อ")
    else:
        text += ("ค่ายังอยู่ใต้เส้นกึ่งกลาง 50 แปลว่าฝั่งขายยังคุมโมเมนตัมระยะกลาง "
                 "แต่ยังไม่ลงไปแตะเขต Oversold ที่ 30 — แรงขายมีอยู่จริงแต่ยังไม่สุดทาง")
    return text


def _macd_paragraph(story: dict) -> str:
    money = money_for(story)
    macd_fmt = macd_for(story)
    macd = story["macd"]
    state = "ฝั่งบวก (เส้น MACD อยู่เหนือเส้น Signal)" if macd["bullish"] \
        else "ฝั่งลบ (เส้น MACD อยู่ใต้เส้น Signal)"
    text = (f"MACD (12, 26, 9) ตอนนี้อยู่{state} "
            f"ค่าเส้น MACD ล่าสุด {macd_fmt(macd['line'])} เทียบเส้น Signal ที่ "
            f"{macd_fmt(macd['signal'])} ทำให้ Histogram อยู่ที่ {macd_fmt(macd['histogram'])} ")
    if macd["cross_date"]:
        cross_kind = "ตัดขึ้น (Bullish Crossover)" if macd["bullish"] else "ตัดลง (Bearish Crossover)"
        text += f"การ{cross_kind} ครั้งล่าสุดเกิดเมื่อ {thai_date(macd['cross_date'])} "
    if macd["histogram_shrinking"]:
        text += ("และแท่ง Histogram กำลังหดตัวลง — แรงส่งของรอบปัจจุบันเริ่มแผ่ว "
                 "เป็นสัญญาณเตือนล่วงหน้าว่าโมเมนตัมอาจใกล้สลับฝั่ง ยังไม่ใช่สัญญาณกลับตัวในตัวเอง")
    else:
        text += ("และแท่ง Histogram ยังขยายตัวต่อเนื่อง — แรงส่งของฝั่งปัจจุบันยังไม่มีอาการอ่อนแรง")
    return text


def _fib_lines(story: dict) -> list[str]:
    money = money_for(story)
    fib = story["fib"]
    if not fib:
        return ["รอบนี้ระบบไม่พบ swing ที่กว้างพอผ่านเกณฑ์ (อย่างน้อย 2 เท่าของ ATR) "
                "จึงไม่วาง Fibonacci และจะไม่ตั้งระดับขึ้นเองจากความรู้สึกแทนครับ"]
    if fib["direction"] == "down":
        swing_text = (f"วัดจากจุดสูงสุดของ swing ที่ {money(fib['swing_high']['price'])} ดอลลาร์ "
                      f"({thai_date(fib['swing_high']['date'])}) ลงมาหาจุดต่ำสุดที่ "
                      f"{money(fib['swing_low']['price'])} ดอลลาร์ "
                      f"({thai_date(fib['swing_low']['date'])}) — ขาลงหลักที่ตลาดกำลังย้อนทดสอบ")
    else:
        swing_text = (f"วัดจากจุดต่ำสุดของ swing ที่ {money(fib['swing_low']['price'])} ดอลลาร์ "
                      f"({thai_date(fib['swing_low']['date'])}) ขึ้นไปหาจุดสูงสุดที่ "
                      f"{money(fib['swing_high']['price'])} ดอลลาร์ "
                      f"({thai_date(fib['swing_high']['date'])}) — ขาขึ้นหลักที่ตลาดกำลังย่อทดสอบ")
    levels = {f"{level['ratio']:g}": level["price"] for level in fib["levels"]}
    golden_low, golden_high = fib["golden"]
    return [
        swing_text, "",
        "ระดับย้อนกลับ (Retracement) ที่ได้จาก swing ชุดนี้:", "",
        # 🐞 **B-3.2 (ทีมเว็บ 2026-08-09):** ภาพวาดเส้นที่บทไม่ได้พูดถึง ⇒ นอกจากตัด
        # 0.705/0.886 ออกจากชุดข้อมูลแล้ว ต้องเติม 0.236 ลงในรายการนี้ด้วย เพราะเดิม
        # ราคาระดับ 0.236 โผล่ในบทเฉพาะตอนที่ฉากทัศน์ผ่านเกณฑ์ระยะห่างรายวัน (เป็น TP1)
        # — วันไหนทั้งสองฉากทัศน์อยู่ไกลเกินเกณฑ์ เส้นนี้จะกลายเป็นเส้นกำพร้าบนภาพทันที
        f"- **0.236** — {money(levels['0.236'])} ดอลลาร์: ชั้นย้อนตื้นสุดของชุดนี้ "
        "หลุดขึ้น/ลงผ่านชั้นนี้ไม่ได้ แปลว่าการย้อนยังไม่เริ่มจริงจัง",
        f"- **0.382** — {money(levels['0.382'])} ดอลลาร์: ด่านแรกของการย้อน "
        "หากราคากลับตัวจากแถวนี้ แปลว่าฝั่งเดิมยังแข็งแรงมาก",
        f"- **0.5** — {money(levels['0.5'])} ดอลลาร์: จุดกึ่งกลางทางจิตวิทยา "
        "ที่เทรดเดอร์จำนวนมากใช้แบ่งเกมว่าการย้อนนี้ \"ลึกเกินครึ่ง\" แล้วหรือยัง",
        f"- **Golden Zone (0.618–0.786)** — {money(golden_low)}–{money(golden_high)} ดอลลาร์: "
        "โซนกลับตัวที่สถิติของสาย Fibonacci ให้น้ำหนักสูงสุด (OTE — Optimal Trade Entry) "
        "และเป็นหัวใจของแผนในหัวข้อถัดไป",
        f"- **1.272 (เป้าขยาย)** — {money(fib['extension'])} ดอลลาร์: "
        "เป้าต่อเนื่องหากราคาทะลุปลาย swing เดิมออกไปได้",
    ]


def _scenario_heading(scenario: dict, label: str) -> str:
    """หัวข้อย่อยของฉากทัศน์ตามใบตัวอย่าง 08-11 — `### 📈 แผน A: ฝั่ง SELL (…)`

    **ฝั่งซื้อ/ขายมาจาก `scenario["name"]` ไม่ได้เดาจากตัวอักษร A/B** — วันที่โหมด
    ตลาดพลิก แผนหลักจะเป็นฝั่งตรงข้ามกับวันก่อน ถ้าตรึงไว้ตามตัวอักษร หัวข้อจะโกหก
    · รูปแบบชื่อคือ `"SELL (Follow Trend)"` ⇒ แทรกคำไทยเข้าไปในวงเล็บ
    อ่านรูปไม่ออก = ใช้ชื่อดิบ ไม่เดาต่อ (กติกาเดียวกับ `_calendar_block` ของ A/B/C)

    อีโมจิผูกกับ**ตัวอักษรแผน ไม่ใช่ฝั่ง** — ลอกจากใบตัวอย่างตรง ๆ (ใบใช้ 📈 กับแผน A
    ที่เป็นฝั่ง SELL) เพราะมันทำหน้าที่เป็นหมายเลขแผน ไม่ใช่ลูกศรบอกทิศ
    """
    emoji = "📈" if label == "A" else "📉"
    note = "เทรดตามแนวโน้มใหญ่" if label == "A" else "เก็งกำไรระยะสั้น"
    name = scenario["name"]
    if " (" in name and name.endswith(")"):
        side, kind = name[:-1].split(" (", 1)
        return f"### {emoji} แผน {label}: ฝั่ง {side} ({kind} — {note})"
    return f"### {emoji} แผน {label}: {name} ({note})"


def _scenario_block(scenario: dict, *, label: str, headline: str,
                    money, confirm_text: str) -> list[str]:
    """หนึ่งฉากทัศน์ — ใช้ร่วมกันทั้ง Scenario A (primary) และ B (counter)

    E-3 (ฟีดแบ็กหัวหน้า 08-07): ทุกราคาที่พูดถึงต้องบอกด้วยว่าเป็น Fib ระดับไหน —
    เดิม TP1 ถูกใช้ในทั้งสองฉากทัศน์แต่บทไม่เคยบอกว่ามันคือ Fib 0.236 คนอ่านหาที่มา
    ของตัวเลขไม่เจอ · และต้องบอกสถานะว่าฉากทัศน์นี้ "active" หรือ "รอ" — เดิมเคยเขียนว่า
    "รอราคาย่อกลับลงมา" ทั้งที่ราคาอยู่ในโซนนั้นแล้ว ขัดกับความจริงตรง ๆ

    🔄 08-11: บรรทัดหัวเปลี่ยนจาก `**Scenario A: …**` เป็นหัวข้อย่อย `###` ตามใบตัวอย่าง
    และคำบรรยายสไตล์ของแผนย้ายลงมาเป็นบรรทัดตัวเอียงใต้หัวข้อ (ใบตัวอย่างวางแบบนี้)
    """
    lines = [_scenario_heading(scenario, label), "",
             f"*{headline}*", "",
             f"- **เงื่อนไข:** {scenario['condition']}",
             f"- **Confirmation:** {confirm_text}",
             f"- **Entry Zone:** {money(min(scenario['entry_low'], scenario['entry_high']))}–"
             f"{money(max(scenario['entry_low'], scenario['entry_high']))} ดอลลาร์ "
             f"(Fibonacci {scenario['entry_label']})",
             f"- **SL:** {money(scenario['sl'])} ดอลลาร์ "
             "(เลยจุดตั้งต้น swing และห่างขอบโซนเข้าอย่างน้อย 1 เท่าของ ATR)"]
    tp_parts = [f"TP{order} {money(target)} (Fib {ratio})"
               for order, (target, ratio) in enumerate(
                   zip(scenario["tps"], scenario["tp_labels"]), 1)]
    lines.append(f"- **TP:** {' · '.join(tp_parts)} ดอลลาร์")
    if scenario["rr1"] is not None:
        # 🔄 08-11 บ่าย (ผู้ใช้สั่ง — ชุดเดียวกับสไตล์ D): ป้าย "RR" เปลี่ยนเป็นคำไทยเต็ม
        rr_line = (f"- **อัตราส่วนความเสี่ยงต่อผลตอบแทน (คำนวณถึง TP1 จากขอบที่เสียเปรียบของโซนเข้า "
                   f"{money(scenario['disadvantaged_entry'])}):** ประมาณ {rr_display(scenario['rr1'])}")
        if scenario["rr1"] < RR_FLOOR:
            rr_line += (" — ต่ำกว่ามาตรฐานขั้นต่ำของระบบแม้วัดจากขอบเสียเปรียบแล้ว "
                        "ห้ามเข้าจนกว่าราคาจะให้จังหวะที่ดีกว่านี้")
        lines.append(rr_line)
    lines.append("- **สถานะวันนี้:** " + (
        "🟢 ราคาปัจจุบันอยู่ในโซนเข้าแล้ว — ฉากทัศน์นี้ active รอสัญญาณยืนยันอย่างเดียว"
        if scenario.get("active")
        else "⚪ ราคายังไม่เข้าโซน — ฉากทัศน์นี้เป็นแผนรอ ยังไม่ใช่จังหวะเข้าวันนี้"))
    return lines


def _scenario_lines(story: dict) -> list[str]:
    money = money_for(story)
    scenarios = story["scenarios"]
    primary, counter = scenarios["primary"], scenarios["counter"]
    if not primary:
        return ["รอบนี้ไม่มีชุด Fibonacci ที่ผ่านเกณฑ์ จึงไม่มีแผนที่ระบบกล้าตั้งให้ "
                "และจะไม่ตั้งระดับจากความรู้สึกแทนครับ"]

    # E-1 (ฟีดแบ็กหัวหน้า 08-07): บังคับกฎระยะห่างรายวัน (10×ATR) กับสไตล์ E ด้วย —
    # เดิมไม่มีตัวกรองนี้เลย ⇒ Golden Zone เคยห่างราคา 14.8–20.6% (13.8–19.2×ATR) แต่ยัง
    # ถูกเสนอเป็นแผนหลักของบท "รายวัน" กฎเดียวกับที่บังคับสไตล์ D ในรายการ #14 ของ STATUS.md
    near = [(label, headline, confirm, scenario) for label, headline, confirm, scenario in (
        ("A", "เน้นความชัวร์และได้เปรียบตามเทรนด์หลัก",
         f"รอแท่งเทียนแสดง{'แรงขาย' if primary['side'] == 'sell' else 'แรงซื้อ'}ชัดเจนในโซน "
         "(เช่น Engulfing หรือไส้ปฏิเสธราคายาว) ประกอบกับ "
         + ("RSI วกกลับลงต่ำกว่าเส้นกึ่งกลาง 50 อีกครั้ง หรือ Histogram ของ MACD พลิกเป็นลบ"
            if primary["side"] == "sell"
            else "RSI ยกตัวกลับเหนือเส้นกึ่งกลาง 50 หรือ Histogram ของ MACD พลิกเป็นบวก")
         + " — ไม่มีสัญญาณยืนยัน ไม่มีการเข้า", primary),
        ("B", "เป็นการเทรดสวนเทรนด์หลัก ควรใช้ขนาดสัญญา (Lot Size) ที่เล็กลง",
         f"ต้องเห็น{'แรงรับ' if counter['side'] == 'buy' else 'แรงต้าน'}ใน Timeframe ย่อย "
         "(1H/15M) ก่อนเสมอ เพราะเป็นการเดินสวนเทรนด์หลัก ขนาดสถานะควรเล็กกว่าปกติ",
         counter),
    ) if scenario.get("daily_entry", True)]
    far = [(label, scenario) for label, scenario in
           (("A", primary), ("B", counter)) if not scenario.get("daily_entry", True)]

    lines: list[str] = []
    for index, (label, headline, confirm, scenario) in enumerate(near):
        if index:
            lines.append("")
        lines += _scenario_block(scenario, label=label, headline=headline,
                                 money=money, confirm_text=confirm)
    for label, scenario in far:
        if lines:
            lines.append("")
        lines.append(
            f"**แผน {label} ({scenario['name']}) ไม่แสดงในบทนี้** — โซนเข้าอยู่ห่างจาก"
            "ราคาปัจจุบันเกินเกณฑ์แผนรายวันของระบบ จึงเป็นระดับเชิงโครงสร้างระยะยาว "
            "ไม่ใช่จังหวะเข้าของวันนี้")
    if not near:
        lines.append("รอบนี้ทั้งสองฉากทัศน์อยู่ห่างจากราคาปัจจุบันเกินเกณฑ์แผนรายวันของระบบ "
                     "จึงไม่มีแผนที่ระบบกล้าแนะนำในกรอบรายวัน และจะไม่ขยับเกณฑ์เพื่อให้มีแผนครับ")
    else:
        # 🔄 08-11 บ่าย (ผู้ใช้สั่ง — แบบเดียวกับ Execution Plan ของสไตล์ D):
        # ลำดับขั้นตอนที่ต้องทำ "ตามลำดับ" จริง ข้ามขั้นไม่ได้ — ใช้กับแผนไหนก็ได้
        # ที่แสดงในบท · ผ่าน `listing` เพื่อเคารพสวิตช์ bullet ของเว็บ
        lines += ["", "**ขั้นตอนปฏิบัติ — ลำดับก่อนเข้าเทรด:**", ""]
        lines += wcb_writers.listing("", [
            "**ขั้นที่ 1 —** รอให้ราคาเดินเข้า Entry Zone ของแผนที่เลือกก่อน "
            "ไม่ไล่ราคากลางอากาศ",
            "**ขั้นที่ 2 —** รอสัญญาณ Confirmation ตามที่แผนนั้นระบุให้ครบ — "
            "ไม่มีสัญญาณ ไม่มีการเข้า",
            "**ขั้นที่ 3 —** เข้าแล้ววางจุด Stoplossตามระดับของแผนทันที "
            "และทยอยทำกำไรตามลำดับ TP ที่วางไว้",
        ])
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
    return headline_format.h1(
        story["asset"], story["current"]["date"],
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
        turn = "ตัดขึ้น" if story["macd"]["bullish"] else "ตัดลง"
        return f"MACD เพิ่ง{turn}"
    return "เช็ก RSI กับ MACD ก่อนเข้าไม้"


def seo_title(story: dict) -> str:
    """Title tag ของสไตล์ E — หางของตัวเอง ไม่ใช่หางคงที่ของทะเบียน

    ⚠️ **ห้ามใช้หางทะเบียนเหมือนสไตล์ D** — สองสไตล์ผลิตจากข้อมูลวันเดียวกัน ถ้าใช้หาง
    เดียวกันจะได้ Title เหมือนกันเป๊ะสองใบ (เกิดจริงรอบแรกของการแก้นี้) · เว็บตั้งชื่อบท
    จากสินทรัพย์+วันที่ ⇒ สองใบที่พาดหัวเหมือนกันแยกไม่ออกว่าใบไหนเป็นใบไหน

    หางปัจจุบันเป็นแบบที่ผู้ใช้เลือกจากห้าตัวเลือก (2026-08-10) — เน้นสิ่งที่ผู้อ่านได้
    แทนการไล่ชื่ออินดิเคเตอร์ เพราะคนที่ยังไม่รู้จักชื่อเครื่องมือจะไม่คลิกพาดหัวที่เป็นศัพท์ล้วน

    ⚠️ **หางนี้สัญญาว่าบทมี "จุดเข้า" ⇒ ห้ามถอดฉากทัศน์สองฝั่งออกจากบทโดยไม่แก้หางด้วย**
    ตรวจแล้วตอนเลือก: บทมีโซนเข้า · SL · RR ทั้งฝั่งซื้อและฝั่งขายจริง พร้อมสถานะรายวัน
    ว่าราคาเข้าโซนหรือยัง · พาดหัวที่สัญญาของที่บทไม่มีคือปัญหา YMYL ไม่ใช่แค่ SEO
    """
    profile = wcb_source.profile_for(story["asset"])
    return headline_format.title(story["asset"], story["current"]["date"],
                                 f"จุดเข้าจากสัญญาณเทคนิค {profile['symbol']}")


def render_article(story: dict) -> str:
    money = money_for(story)
    combined_image = image_name(story["asset"], story["current"]["date"])
    down = story["regime"]["down"]
    current_text = money(story["current"]["close"])
    trend_word = "ขาลง" if down else "ขาขึ้น"
    heads = wcb_writers.SectionNumbers()

    opening = (
        f"บทวิเคราะห์ฉบับนี้อ่าน {story['symbol']} ผ่านเลนส์อินดิเคเตอร์ล้วน ๆ ครับ — "
        "โมเมนตัมจาก RSI แรงส่งจาก MACD และแผนที่ระดับราคาจาก Fibonacci Retracement "
        f"แท่งรายวันล่าสุดปิดที่ {current_text} ดอลลาร์ ท่ามกลางโหมดตลาด{trend_word} "
        "ทุกค่าและทุกระดับในบทนี้คำนวณจากแท่งราคาจริงชุดเดียวกับที่ใช้วาดภาพประกอบ "
        "ไม่มีเลขใดตั้งขึ้นตามความรู้สึก")

    lines = chart_story_writer_frontmatter(story, title_text=seo_title(story), excerpt_clauses=[
        f"{wcb_source.profile_for(story['asset'])['short_name']}ปิดที่ {current_text} ดอลลาร์",
        f"RSI(14) ที่ {story['rsi']['value']:.1f}",
        "อ่านสัญญาณ RSI MACD และระดับ Fibonacci พร้อมจุดเข้าและจุด Stoplossทั้งสองฝั่ง",
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

    structure = (f"ภาพใหญ่ย้อนหลัง {story['display']['bars']} แท่งรายวัน "
                 f"โหมดตลาดตามความชันของเส้นค่าเฉลี่ย 50 วันเป็น{trend_word} ")
    if story["regime"]["flip_date"]:
        structure += f"ต่อเนื่องมาตั้งแต่ {thai_date(story['regime']['flip_date'])} "
    if story["sma50_last"] is not None:
        position = "เหนือ" if story["current"]["close"] >= story["sma50_last"] else "ใต้"
        structure += (f"ขณะที่ราคาปัจจุบันยืนอยู่{position}เส้นค่าเฉลี่ย 50 วัน "
                      f"(ล่าสุดอยู่ที่ {money(story['sma50_last'])} ดอลลาร์) ")
    fib = story["fib"]
    if fib:
        if fib["direction"] == "down":
            structure += (
                f"ขาเคลื่อนไหวหลักของรอบนี้คือการไหลลงจาก {money(fib['swing_high']['price'])} "
                f"สู่ {money(fib['swing_low']['price'])} ดอลลาร์ "
                "และตอนนี้ตลาดอยู่ในเฟสย้อนทดสอบ (Retracement) ของขานั้น — "
                "คำถามสำคัญคือการย้อนจะหยุดที่ชั้นไหนของ Fibonacci")
        else:
            structure += (
                f"ขาเคลื่อนไหวหลักของรอบนี้คือการไต่ขึ้นจาก {money(fib['swing_low']['price'])} "
                f"สู่ {money(fib['swing_high']['price'])} ดอลลาร์ "
                "และตอนนี้ตลาดอยู่ในเฟสย่อทดสอบ (Retracement) ของขานั้น — "
                "คำถามสำคัญคือการย่อจะหยุดที่ชั้นไหนของ Fibonacci")
    # alt text ใส่ตัวเลขระดับสำคัญ (แนวเดียวกับฟีดแบ็กหัวหน้าต่อสไตล์ D) · ภาพเดียว
    # สามแผงตามคำสั่งผู้ใช้ 2026-08-07 — วางหลังหัวข้อแรก ที่เหลืออ้างภาพเดียวกัน
    alt_parts = [f"ภาพประกอบ — ราคา · Fibonacci · RSI · MACD ของ {story['symbol']}"]
    if fib:
        golden_low, golden_high = fib["golden"]
        alt_parts.append(f"Golden Zone {money(golden_low)}–{money(golden_high)}")
    # 🔄 08-11: RSI กับ MACD เคยเป็นหัวข้อใหญ่คนละหัว — ใบตัวอย่างรวบเป็นหัวข้อเดียว
    # ("เจาะลึกสัญญาณอินดิเคเตอร์") แล้วแยกด้วย bullet ที่ขึ้นต้นด้วยชื่อเครื่องมือแทน
    # ⇒ ชื่อเครื่องมือยังอยู่ครบทุกตัว ไม่ได้หายไปกับหัวข้อ แค่ย้ายที่
    lines += [structure, "",
              f"![{' · '.join(alt_parts)}]({combined_image})", "",
              *RULE,
              heads.head(H2_INDICATORS), "",
              f"- {_rsi_paragraph(story)}",
              f"- {_macd_paragraph(story)}", "",
              *RULE,
              heads.head(H2_FIB), ""]
    lines += _fib_lines(story)
    lines += ["", *RULE, heads.head(H2_SCENARIOS), ""]
    lines += _scenario_lines(story)
    lines += [
        "",
        "ระดับ Entry/SL/TP ทั้งหมดเป็นเงื่อนไขสมมุติที่คำนวณจากระดับ Fibonacci และ ATR "
        "ไม่ใช่คำทำนาย ราคาไม่จำเป็นต้องมาถึงโซนใดโซนหนึ่ง — หน้าที่ของแผนคือบอกล่วงหน้าว่า "
        "ถ้าราคามาถึงจุดไหนแล้วเกิดอะไร เราจะทำอะไร ไม่ใช่บอกว่าพรุ่งนี้ตลาดจะไปทางไหน",
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
                 "bullish": "RSI ยืนฝั่งแรงซื้อ",
                 "bearish": "RSI ยังอยู่ฝั่งแรงขาย"}[story["rsi"]["zone"]]
    macd_state = "MACD ฝั่งบวก" if story["macd"]["bullish"] else "MACD ฝั่งลบ"
    summary = f"เกมของวันนี้สรุปสั้นที่สุดได้ว่า: {rsi_state} · {macd_state}"
    if story["macd"]["histogram_shrinking"]:
        summary += " (แรงส่งเริ่มแผ่ว)"
    primary = story["scenarios"]["primary"]
    counter = story["scenarios"]["counter"]
    near_primary = bool(primary and primary.get("daily_entry", True))
    near_counter = bool(counter and counter.get("daily_entry", True))
    if fib and (near_primary or near_counter):
        golden_low, golden_high = fib["golden"]
        # ⚠️ ข้อ "ทำไม" ห้ามอ้างว่าแผนตั้งต้นจาก Golden Zone แบบเหมารวม — วันที่แผน A
        # (ฝั่งที่ใช้โซนนี้จริง) อยู่ไกลเกินเกณฑ์และถูกซ่อน บทจะเหลือแต่แผน B ที่ใช้
        # โซนอื่น ⇒ ประโยคเหมารวมจะโกหกทั้งที่เลขทุกตัวมีต้นทาง (ด่านเลขจับไม่ได้ —
        # กับดักเดียวกับ "จุดกลางกรอบ" ของสไตล์ F)
        why = ("**ทำไมต้องดูโซนนี้:** เป็นชั้นย้อนกลับที่สถิติของสาย Fibonacci ให้น้ำหนัก"
               "การกลับตัวสูงสุด (OTE)")
        if near_primary:
            why += " และแผนหลักของบทนี้ (แผน A) ตั้งต้นจากโซนนี้"
        why += " — ราคากลางทางไม่ให้ความได้เปรียบกับฝั่งไหน"
        summary_items = [
            f"**ต้องดูอะไร:** จุดตัดสินใจสำคัญคือ Golden Zone {money(golden_low)}–"
            f"{money(golden_high)} ดอลลาร์ คู่กับสัญญาณยืนยันจาก RSI และ MACD",
            why,
            "**ทำอย่างไร:** เดินตามขั้นตอนปฏิบัติในหัวข้อ 4 — รอราคาเข้าโซนของแผน "
            "รอ Confirmation ให้ครบ แล้วจึงเข้าพร้อมจุด Stoploss ไม่ไล่ราคากลางอากาศ",
        ]
        outcomes = []
        if near_primary:
            outcomes.append(f"ราคาเข้าโซนแผน A พร้อมสัญญาณยืนยัน = เดินตามแผน A "
                            f"เป้าแรกที่ TP1 {money(primary['tps'][0])} ดอลลาร์")
        if near_counter:
            outcomes.append("ราคาเข้าโซนแผน B พร้อมสัญญาณยืนยัน = เก็งกำไรสวนเทรนด์หลัก "
                            "ด้วยขนาดสัญญาที่เล็กลง")
        outcomes.append("ราคาไม่เข้าโซนไหนเลย = วันของการเฝ้าดู ไม่มีการเข้า — "
                        "ทั้งหมดเป็นเงื่อนไข ไม่ใช่คำทำนาย")
        summary_items.append("**แล้วจะเป็นอย่างไรต่อ:** " + " · ".join(outcomes))
        lines += [summary, ""] + wcb_writers.listing("", summary_items) + [""]
        summary = ("อินดิเคเตอร์ทั้งสามตัวชี้จุดรอ ไม่ได้ชี้ให้ไล่ราคากลางอากาศครับ")
    elif fib:
        golden_low, golden_high = fib["golden"]
        summary += (f" · จุดตัดสินใจสำคัญคือ Golden Zone {money(golden_low)}–"
                    f"{money(golden_high)} ดอลลาร์ "
                    "แต่รอบนี้แผนทั้งหมดอยู่ห่างเกินเกณฑ์รายวัน จึงเป็นวันของการเฝ้าดูครับ")
    else:
        summary += " · รอบนี้ไม่มีชุด Fibonacci ที่ผ่านเกณฑ์ จึงเป็นวันของการเฝ้าดูมากกว่าลงมือครับ"
    lines += [summary, "",
              "**คำเตือนความเสี่ยง:** บทวิเคราะห์นี้จัดทำจากค่าอินดิเคเตอร์เพื่อการศึกษาและติดตามตลาด "
              "ไม่ใช่คำแนะนำการลงทุน และไม่ใช่คำชักชวนให้ซื้อขายสินทรัพย์ใด ๆ "
              "การเทรดสวนเทรนด์หรือเข้าโดยไม่มีสัญญาณยืนยันมีความเสี่ยงสูงเป็นพิเศษ "
              + wcb_writers._closing(),
              ""]
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
        "1", "2", "3", "4", "5", "9", "12", "14", "15", "26", "30", "50", "70",
        str(story["display"]["bars"]), str(story["display"]["fib_bars"]),
        str(chart_indicator.RSI_SLOPE_BARS),
    }
    for ratio in chart_indicator.FIB_RATIOS:
        allowed.add(f"{ratio:g}")
    allowed.add(f"{chart_indicator.EXTENSION_RATIO:g}")
    allowed.add(f"{RR_FLOOR:g}")

    prices = [story["current"]["close"]]
    if story.get("sma50_last") is not None:
        prices.append(story["sma50_last"])
    fib = story["fib"]
    if fib:
        prices += [fib["swing_high"]["price"], fib["swing_low"]["price"], fib["extension"]]
        prices += [level["price"] for level in fib["levels"]]
        prices += list(fib["golden"])
    for key in ("primary", "counter"):
        scenario = story["scenarios"][key]
        if scenario:
            prices += [scenario["entry_low"], scenario["entry_high"], scenario["entry_mid"],
                       scenario["sl"], *scenario["tps"]]
            if scenario["rr1"] is not None:
                allowed.add(f"{scenario['rr1']:.1f}")
    for value in prices:
        allowed.add(money(value))

    allowed.add(rsi_text(story["rsi"]["value"]))
    for key in ("line", "signal", "histogram"):
        allowed.add(macd_fmt(story["macd"][key]).lstrip("-"))

    # ชื่อไฟล์ภาพมีวันที่เต็มรูป (เช่น 2026-08-06) — เลขเดือน/วันแบบมีศูนย์นำ
    # ไม่ตรงกับทะเบียนวันที่ปกติ ต้องเพิ่มจากชื่อไฟล์ตรง ๆ
    for token in _NUMBER.findall(image_name(story["asset"], story["current"]["date"])):
        allowed.add(token.rstrip(".,"))

    dates = [story["current"]["date"], story["regime"]["flip_date"],
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
    for key, label in (("primary", "Scenario A"), ("counter", "Scenario B")):
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

    # 🐞 **A-1 (08-09):** บทเปิดด้วย "แท่งรายวันล่าสุดปิดที่ X" เหมือนสไตล์ D
    # ⇒ ผูกคำว่า "ปิด" กับแท่งที่พิสูจน์ได้ว่าปิดแล้วเท่านั้น พิสูจน์ไม่ได้ = ไม่ออกไฟล์
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
    name = image_name(story["asset"], story["current"]["date"])
    if f"({name})" not in markdown:
        findings.append({
            "rule": "missing_image", "severity": "fatal", "line": 1,
            "message": f"บทความไม่ได้อ้างภาพ {name} — สไตล์ E ต้องอ้างภาพประกอบเสมอ",
        })
    if story["scenarios"]["primary"] and "Trading Scenario" not in markdown:
        findings.append({
            "rule": "scenario_section", "severity": "fatal", "line": 1,
            "message": "story มีแผนสองฝั่ง แต่บทไม่มีหัวข้อ Trading Scenario — โครงต้นแบบบังคับ",
        })
    if "ไม่ใช่คำทำนาย" not in markdown:
        findings.append({
            "rule": "scenario_disclaimer", "severity": "fatal", "line": 1,
            "message": "ไม่พบประโยคประกาศว่าแผนเป็นเงื่อนไข ไม่ใช่คำทำนาย",
        })
    if "คำเตือนความเสี่ยง" not in markdown:
        findings.append({
            "rule": "risk_disclaimer", "severity": "fatal", "line": 1,
            "message": "ไม่พบส่วนคำเตือนความเสี่ยงท้ายบท",
        })
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
