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

from tools import chart_indicator, wcb_writers  # noqa: E402
from tools.chart_story_renderer import macd_for, money_for, thai_date  # noqa: E402
from tools.chart_story_writer import AUTHOR  # noqa: E402 — byline เดียวกันทั้งระบบ

STYLE_ID = "e_indicator"
STYLE_NAME = "E — อ่านอินดิเคเตอร์"
FOLDER = "E-อินดิเคเตอร์"
# นับเฉพาะตัวอักษร (เกณฑ์แบบเดียวกับสไตล์ D) — บทที่ fib ไม่ผ่านเกณฑ์ยังมี 3 หัวข้อ
# อินดิเคเตอร์เต็ม ~1,600 อักขระ · ของจริงครบชุด ~3,500+ · ต่ำกว่านี้ = โครงหาย
MIN_CHARS = 1200
RR_FLOOR = 1.2   # มาตรฐานเดียวกับ minimum_rr ของสาย A — ห้ามผ่อนเพื่อให้แผนดูดี
_NUMBER = re.compile(r"\d[\d,\.]*")


def image_name(asset: str, date_text: str) -> str:
    """ชื่อไฟล์ภาพประกอบใบเดียวของบท — ผู้ใช้สั่งรวมภาพสไตล์ E 2026-08-07
    (สามแผงในผืนเดียว: ราคา+Fibonacci+แผนเทรด / RSI / MACD ตามหน้าตาต้นแบบ)
    รูปแบบชื่อมีความหมาย+วันที่ แนวเดียวกับสไตล์ D"""
    return f"{asset}-d1-indicators-{date_text}.png"


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


def _scenario_block(scenario: dict, *, label: str, headline: str,
                    money, confirm_text: str) -> list[str]:
    """หนึ่งฉากทัศน์ — ใช้ร่วมกันทั้ง Scenario A (primary) และ B (counter)

    E-3 (ฟีดแบ็กหัวหน้า 08-07): ทุกราคาที่พูดถึงต้องบอกด้วยว่าเป็น Fib ระดับไหน —
    เดิม TP1 ถูกใช้ในทั้งสองฉากทัศน์แต่บทไม่เคยบอกว่ามันคือ Fib 0.236 คนอ่านหาที่มา
    ของตัวเลขไม่เจอ · และต้องบอกสถานะว่าฉากทัศน์นี้ "active" หรือ "รอ" — เดิมเคยเขียนว่า
    "รอราคาย่อกลับลงมา" ทั้งที่ราคาอยู่ในโซนนั้นแล้ว ขัดกับความจริงตรง ๆ
    """
    lines = [f"**Scenario {label}: {scenario['name']} — {headline}**", "",
             f"- **เงื่อนไข:** {scenario['condition']}",
             f"- **Confirmation:** {confirm_text}",
             f"- **Entry Zone:** {money(min(scenario['entry_low'], scenario['entry_high']))}–"
             f"{money(max(scenario['entry_low'], scenario['entry_high']))} ดอลลาร์ "
             f"(Fibonacci {scenario['entry_label']})",
             f"- **SL:** {money(scenario['sl'])} ดอลลาร์ (เลยจุดตั้งต้น swing พร้อมระยะเผื่อ)"]
    tp_parts = [f"TP{order} {money(target)} (Fib {ratio})"
               for order, (target, ratio) in enumerate(
                   zip(scenario["tps"], scenario["tp_labels"]), 1)]
    lines.append(f"- **TP:** {' · '.join(tp_parts)} ดอลลาร์")
    if scenario["rr1"] is not None:
        rr_line = (f"- **RR (คำนวณถึง TP1 จากขอบที่เสียเปรียบของโซนเข้า "
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
        ("A", "ฝั่งที่สอดคล้องกับเทรนด์หลัก",
         f"รอแท่งเทียนแสดง{'แรงขาย' if primary['side'] == 'sell' else 'แรงซื้อ'}ชัดเจนในโซน "
         "(เช่น Engulfing หรือไส้ปฏิเสธราคายาว) ประกอบกับ "
         + ("RSI วกกลับลงต่ำกว่าเส้นกึ่งกลาง 50 อีกครั้ง หรือ Histogram ของ MACD พลิกเป็นลบ"
            if primary["side"] == "sell"
            else "RSI ยกตัวกลับเหนือเส้นกึ่งกลาง 50 หรือ Histogram ของ MACD พลิกเป็นบวก")
         + " — ไม่มีสัญญาณยืนยัน ไม่มีการเข้า", primary),
        ("B", "ฝั่งสวนเทรนด์ เล่นสั้นเท่านั้น",
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
            f"**Scenario {label} ({scenario['name']}) ไม่แสดงในบทนี้** — โซนเข้าอยู่ห่างจาก"
            "ราคาปัจจุบันเกินเกณฑ์แผนรายวันของระบบ จึงเป็นระดับเชิงโครงสร้างระยะยาว "
            "ไม่ใช่จังหวะเข้าของวันนี้")
    if not near:
        lines.append("รอบนี้ทั้งสองฉากทัศน์อยู่ห่างจากราคาปัจจุบันเกินเกณฑ์แผนรายวันของระบบ "
                     "จึงไม่มีแผนที่ระบบกล้าแนะนำในกรอบรายวัน และจะไม่ขยับเกณฑ์เพื่อให้มีแผนครับ")
    return lines


def render_article(story: dict) -> str:
    money = money_for(story)
    combined_image = image_name(story["asset"], story["current"]["date"])
    down = story["regime"]["down"]
    current_text = money(story["current"]["close"])
    trend_word = "ขาลง" if down else "ขาขึ้น"

    opening = (
        f"บทวิเคราะห์ฉบับนี้อ่าน {story['symbol']} ผ่านเลนส์อินดิเคเตอร์ล้วน ๆ ครับ — "
        "โมเมนตัมจาก RSI แรงส่งจาก MACD และแผนที่ระดับราคาจาก Fibonacci Retracement "
        f"แท่งรายวันล่าสุดปิดที่ {current_text} ดอลลาร์ ท่ามกลางโหมดตลาด{trend_word} "
        "ทุกค่าและทุกระดับในบทนี้คำนวณจากแท่งราคาจริงชุดเดียวกับที่ใช้วาดภาพประกอบ "
        "ไม่มีเลขใดตั้งขึ้นตามความรู้สึก")

    lines = [
        f"# แผนเทรดตามอินดิเคเตอร์ {story['symbol']} (D1) วันที่ "
        f"{thai_date(story['current']['date'])} — RSI · MACD · Fibonacci",
        "",
        f"*โดย {AUTHOR}*",
        "",
        opening,
        "",
        "## 1. โครงสร้างราคา (Market Structure)",
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
    lines += [structure, "",
              f"![{' · '.join(alt_parts)}]({combined_image})", "",
              "## 2. โมเมนตัม RSI (14)", "",
              _rsi_paragraph(story), "",
              "## 3. แรงส่ง MACD (12, 26, 9)", "",
              _macd_paragraph(story), "",
              "## 4. Fibonacci Retracement", ""]
    lines += _fib_lines(story)
    lines += ["", "## 5. Trading Scenario", ""]
    lines += _scenario_lines(story)
    lines += [
        "",
        "ระดับ Entry/SL/TP ทั้งหมดเป็นเงื่อนไขสมมุติที่คำนวณจากระดับ Fibonacci และ ATR "
        "ไม่ใช่คำทำนาย ราคาไม่จำเป็นต้องมาถึงโซนใดโซนหนึ่ง — หน้าที่ของแผนคือบอกล่วงหน้าว่า "
        "ถ้าราคามาถึงจุดไหนแล้วเกิดอะไร เราจะทำอะไร ไม่ใช่บอกว่าพรุ่งนี้ตลาดจะไปทางไหน",
        "",
        "## สรุปประจำวัน",
        "",
    ]
    summary = "เกมของวันนี้สรุปสั้นที่สุดได้ว่า: "
    rsi_state = {"overbought": "RSI ร้อนจัดในเขต Overbought",
                 "oversold": "RSI ตึงตัวในเขต Oversold",
                 "bullish": "RSI ยืนฝั่งแรงซื้อ",
                 "bearish": "RSI ยังอยู่ฝั่งแรงขาย"}[story["rsi"]["zone"]]
    macd_state = "MACD ฝั่งบวก" if story["macd"]["bullish"] else "MACD ฝั่งลบ"
    summary += f"{rsi_state} · {macd_state}"
    if story["macd"]["histogram_shrinking"]:
        summary += " (แรงส่งเริ่มแผ่ว)"
    if fib:
        golden_low, golden_high = fib["golden"]
        summary += (f" · จุดตัดสินใจสำคัญคือ Golden Zone {money(golden_low)}–"
                    f"{money(golden_high)} ดอลลาร์ ")
        summary += ("รอราคาเข้าโซนพร้อมสัญญาณยืนยันก่อนเสมอ — อินดิเคเตอร์ทั้งสามตัวชี้จุดรอ "
                    "ไม่ได้ชี้ให้ไล่ราคากลางอากาศครับ")
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
    for date_text in dates:
        if not date_text:
            continue
        year, _month, day = date_text.split("-")
        allowed.add(year)
        allowed.add(str(int(day)))
    return allowed


def validate(markdown: str, story: dict) -> dict:
    """ด่านของสไตล์ E — fail-closed: findings ระดับ fatal ตัวเดียวก็ตก"""
    findings: list[dict] = []
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
    if markdown.lstrip().startswith("---"):
        findings.append({
            "rule": "frontmatter_forbidden", "severity": "fatal", "line": 1,
            "message": "บทสไตล์ E ต้องไม่มี frontmatter",
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
