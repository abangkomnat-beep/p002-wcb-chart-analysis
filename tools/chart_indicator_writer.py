"""นักเขียนสไตล์ E — แผนเทรดตามอินดิเคเตอร์ (RSI/MACD/Fibonacci) + ด่านตรวจของสไตล์นี้เอง

โครงบทตามต้นแบบที่หัวหน้าเลือก (th.tradingview.com/chart/XAUUSD/vxcu4F8w):
หัวข้อใช้ชื่อโดยตรง ไม่ใส่เลขลำดับ — Executive Summary อยู่ด้านบนสุดแล้ว

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
from tools.chart_story_writer import _indent_prose_lines  # noqa: E402
from tools.chart_story_writer import publish_date_of as chart_story_writer_publish_date  # noqa: E402
from tools.chart_story_writer import publication_slug as chart_story_writer_publication_slug  # noqa: E402

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
H2_SCENARIOS = "แผนตามแนวโน้มหลัก"


def _h2(title: str) -> str:
    """หัวข้อ H2 ของ Style E — ใช้ชื่อโดยตรง ไม่เติมเลขลำดับ"""
    return f"## {title}"


def image_name(asset: str, date_text: str, timeframe: str = chart_indicator.TIMEFRAME) -> str:
    """ชื่อไฟล์ภาพประกอบ H1 ใบเดียวของบท"""
    timeframe_slug = "h1" if timeframe == chart_indicator.TIMEFRAME else "d1"
    return f"{asset}-{timeframe_slug}-indicators-{date_text}{image_output.IMAGE_SUFFIX}"


def _is_h1(story: dict) -> bool:
    return story.get("timeframe") == chart_indicator.TIMEFRAME


def plan_state(story: dict) -> dict:
    """สถานะแผนจุดเดียวสำหรับพาดหัว บทสรุป แผน และ CTA"""
    primary = story.get("scenarios", {}).get("primary")
    if not primary:
        return {"kind": "no_setup", "primary": None, "side": None}
    if not primary.get("daily_entry", True):
        kind = "out_of_range"
    elif primary.get("active"):
        kind = "awaiting_confirmation"
    else:
        kind = "waiting_zone"
    return {"kind": kind, "primary": primary, "side": primary["side"]}


def scenario_heading(story: dict) -> str:
    """หัวข้อแผนที่ผูกกับฝั่งหลักจริง ไม่ตรึง SELL/BUY ไว้ใน template"""
    state = plan_state(story)
    if not state["primary"]:
        return "แผนวันนี้: รอข้อมูลยืนยัน"
    return f"แผน: รอ {state['side'].upper()} ตามแนวโน้มหลัก"


def _timeframe_label(story: dict) -> str:
    return "H1" if _is_h1(story) else "รายวัน"


def _closed_bar_phrase(story: dict) -> str:
    return "แท่ง H1 ปิด" if _is_h1(story) else "แท่งรายวันปิด"


def rsi_text(value: float) -> str:
    return f"{value:.1f}"


# ---------------------------------------------------------------- ตัวเขียนบท

def _rsi_paragraph(story: dict) -> str:
    rsi = story["rsi"]
    if rsi["zone"] == "bearish":
        return ("RSI (ภาพใหญ่ยังเป็นขาลง): ฝั่งขายยังคงคุมเกมระยะกลางเนื่องจากค่า RSI "
                "ยังอยู่ต่ำกว่าเกณฑ์ 50 และยังไม่เข้าเขต Oversold (ขายมากเกินไป) "
                "จึงยังมีพื้นที่ให้ราคาทิ้งตัวลงต่อได้อีก")
    if rsi["zone"] == "bullish":
        return ("RSI (ภาพใหญ่ยังเป็นขาขึ้น): ฝั่งซื้อยังคุมเกมระยะกลางเนื่องจากค่า RSI "
                "ยังอยู่เหนือเกณฑ์ 50 และยังไม่เข้าเขต Overbought (ซื้อมากเกินไป) "
                "จึงยังมีพื้นที่ให้ราคาขยับขึ้นต่อได้")
    if rsi["zone"] == "overbought":
        return ("RSI (ภาพใหญ่ยังเป็นขาขึ้นแต่เริ่มร้อนแรง): แรงซื้อยังได้เปรียบ "
                "แต่ค่า RSI เข้าเขต Overbought แล้ว จึงต้องระวังแรงขายทำกำไรและรอการยืนยัน "
                "ก่อนตามราคา")
    return ("RSI (ภาพใหญ่ยังเป็นขาลงแต่เริ่มตึงตัว): ค่า RSI เข้าเขต Oversold แล้ว "
            "จึงมีโอกาสเกิด Technical Rebound และควรรอการยืนยันก่อนเปิดสถานะตามทิศทางเดิม")


def _macd_paragraph(story: dict) -> str:
    macd = story["macd"]
    side = (story.get("scenarios", {}).get("primary") or {}).get("side")
    follow_word = "Follow Short" if side == "sell" else "Follow Long"
    plan_word = side.upper() if side in {"buy", "sell"} else "แผน"
    if macd["bullish"] and macd["cross_date"] and not macd["histogram_shrinking"]:
        return ("MACD (ระยะสั้นฟื้นตัวขึ้น): ส่งสัญญาณรีบาวด์ขึ้นสั้นๆ จากการเกิด "
                "Bullish Crossover และแรงส่งของฝั่งซื้อยังขยายตัวต่อเนื่อง "
                f"เตือนว่าอย่าเพิ่งรีบ {follow_word} กลางทาง ให้รอแรงดีดชะลอตัวก่อน")
    if macd["bullish"]:
        return ("MACD (ระยะสั้นฟื้นตัวขึ้น): แรงส่งฝั่งซื้อกำลังพยุงราคา "
                f"แต่ยังต้องรอให้การรีบาวด์ชะลอตัวหรือมีสัญญาณยืนยันก่อนตามแผน {plan_word}")
    if macd["histogram_shrinking"]:
        return ("MACD (ระยะสั้นยังเป็นขาลงแต่เริ่มชะลอ): แรงขายยังได้เปรียบ "
                "แต่ Histogram เริ่มหดตัว จึงควรรอให้แรงเด้งจบและมีสัญญาณยืนยันก่อนเปิดสถานะ")
    return ("MACD (ระยะสั้นยังเป็นขาลง): แรงส่งฝั่งขายยังต่อเนื่อง "
            "จึงควรติดตามการเปลี่ยนทิศของ Histogram ก่อนตัดสินใจเข้าเทรด")


def _is_xauusd_h1_hybrid(story: dict) -> bool:
    """เปิดโหมด Hybrid เฉพาะ XAUUSD H1 ที่มี Fibonacci เท่านั้น."""
    return (story.get("asset") == "xauusd"
            and story.get("timeframe") == chart_indicator.TIMEFRAME
            and story.get("fib") is not None)


def _normalize_price(story: dict, value: float) -> float:
    """เปรียบเทียบราคาหลังผ่าน formatter เดียวกับค่าที่แสดงในบท."""
    return float(money_for(story)(value).replace(",", ""))


def _fib_candidate_registry(story: dict) -> list[dict]:
    """ทะเบียนระดับ Hybrid แบบคงที่ พร้อม priority สำหรับ tie-break."""
    money = money_for(story)
    fib = story.get("fib")
    if not fib:
        return []

    golden_low, golden_high = fib["golden"]
    levels = {f"{level['ratio']:g}": level["price"] for level in fib["levels"]}
    point_label = "แนวรับ" if fib["direction"] == "up" else "แนวต้าน"
    extension_label = "เป้าหมายอ้างอิง"

    level_236 = _normalize_price(story, levels["0.236"])
    level_382 = _normalize_price(story, levels["0.382"])
    level_500 = _normalize_price(story, levels["0.5"])
    zone_low = _normalize_price(story, golden_low)
    zone_high = _normalize_price(story, golden_high)
    extension = _normalize_price(story, fib["extension"])

    return [
        {"label": "0.236", "type": "point", "priority": 1,
         "kind_text": point_label, "low": level_236, "high": level_236,
         "display": f"0.236 ({money(levels['0.236'])})"},
        {"label": "0.382", "type": "point", "priority": 2,
         "kind_text": point_label, "low": level_382, "high": level_382,
         "display": f"0.382 ({money(levels['0.382'])})"},
        {"label": "0.5", "type": "point", "priority": 3,
         "kind_text": point_label, "low": level_500, "high": level_500,
         "display": f"0.5 ({money(levels['0.5'])})"},
        {"label": "Golden Zone", "type": "zone", "priority": 4,
         "kind_text": "Golden Zone", "low": zone_low, "high": zone_high,
         "display": f"Golden Zone ({money(golden_low)}–{money(golden_high)})"},
        {"label": "1.272", "type": "point", "priority": 5,
         "kind_text": extension_label, "low": extension, "high": extension,
         "display": f"1.272 ({money(fib['extension'])})"},
    ]


def _pick_fib_watch_candidates(story: dict) -> list[dict]:
    """เลือกหนึ่งรายการเมื่อ exact/in-zone และสองรายการเมื่ออยู่นอกระดับ."""
    if not story.get("fib"):
        return []

    current = _normalize_price(story, story["current"]["close"])
    registry = _fib_candidate_registry(story)
    if not registry:
        return []

    golden = next(item for item in registry if item["label"] == "Golden Zone")
    if golden["low"] <= current <= golden["high"]:
        return [golden]

    exact = [item for item in registry
             if item["type"] == "point" and item["low"] == current]
    if exact:
        return [min(exact, key=lambda item: item["priority"])]

    def distance(item: dict) -> float:
        if current < item["low"]:
            return item["low"] - current
        if current > item["high"]:
            return current - item["high"]
        return 0.0

    ranked = sorted(((item, distance(item)) for item in registry),
                    key=lambda pair: (pair[1], pair[0]["priority"]))
    return [ranked[0][0], ranked[1][0]]


def _context_relation_text(story: dict, candidates: list[dict]) -> str:
    """สร้างข้อความตำแหน่งราคาสำหรับ candidate หนึ่งหรือสองรายการ."""
    if not candidates:
        return ""

    current = _normalize_price(story, story["current"]["close"])
    if len(candidates) == 1:
        item = candidates[0]
        if item["type"] == "point":
            return f"อยู่ที่{item['kind_text']} **{item['display']}**"
        return f"อยู่ใน **{item['display']}**"

    first, second = candidates
    upper = max(first["high"], second["high"])
    lower = min(first["low"], second["low"])
    if current > upper:
        relation = "เหนือ"
    elif current < lower:
        relation = "ต่ำกว่า"
    else:
        ordered = sorted(candidates, key=lambda item: (item["low"] + item["high"]) / 2)
        return f"อยู่ระหว่าง **{ordered[0]['display']}** กับ **{ordered[1]['display']}**"

    return (f"อยู่{relation}{first['kind_text']} **{first['display']}** "
            f"ซึ่งเป็นระดับใกล้สุด ส่วน{second['kind_text']}ถัดไปคือ "
            f"**{second['display']}**")


def _hybrid_fib_lines(story: dict) -> list[str]:
    """บล็อก Fibonacci Hybrid revision 3 สำหรับ XAUUSD H1 เท่านั้น."""
    money = money_for(story)
    fib = story.get("fib")
    if not fib:
        return ["รอบนี้ระบบไม่พบ swing ที่กว้างพอผ่านเกณฑ์ (อย่างน้อย 2 เท่าของ ATR) "
                "จึงไม่วาง Fibonacci และจะไม่ตั้งระดับขึ้นเองจากความรู้สึกแทนครับ"]

    if fib["direction"] == "down":
        swing_text = (f"บนกราฟ H1 วัดจากจุดสูงสุดเดิมที่ {money(fib['swing_high']['price'])} ดอลลาร์ "
                      f"({thai_date(fib['swing_high']['date'])}) ลงมาถึงจุดต่ำสุดเดิมที่ "
                      f"{money(fib['swing_low']['price'])} ดอลลาร์ "
                      f"({thai_date(fib['swing_low']['date'])}) ซึ่งเป็นขาลงหลักที่ตลาดกำลังย้อนทดสอบ")
        point_kind = "แนวต้านรีบาวด์"
    else:
        swing_text = (f"กราฟ H1 วัดคลื่นขาขึ้นจาก {money(fib['swing_low']['price'])} ดอลลาร์ "
                      f"({thai_date(fib['swing_low']['date'])}) ถึง "
                      f"{money(fib['swing_high']['price'])} ดอลลาร์ "
                      f"({thai_date(fib['swing_high']['date'])})")
        point_kind = "แนวรับย่อตัว"

    levels = {f"{level['ratio']:g}": level["price"] for level in fib["levels"]}
    golden_low, golden_high = fib["golden"]
    watch = _context_relation_text(story, _pick_fib_watch_candidates(story))
    close = money(story["current"]["close"])
    return [
        swing_text, "", "**ระดับอ้างอิง:**", "",
        f"- **{point_kind}:** `0.236` {money(levels['0.236'])} · `0.382` {money(levels['0.382'])} · `0.5` {money(levels['0.5'])}",
        f"- **โซนหลัก/เป้าหมาย:** `Golden Zone` {money(golden_low)}–{money(golden_high)} · `1.272` {money(fib['extension'])}",
        "",
        (f"**จุดที่ต้องจับตาวันนี้:** ราคาปิด **{close}** ดอลลาร์ {watch}"
         if watch else f"**จุดที่ต้องจับตาวันนี้:** ราคาปิด **{close}** ดอลลาร์"),
    ]


def _fib_lines(story: dict) -> list[str]:
    money = money_for(story)
    fib = story["fib"]
    if not fib:
        return ["รอบนี้ระบบไม่พบ swing ที่กว้างพอผ่านเกณฑ์ (อย่างน้อย 2 เท่าของ ATR) "
                "จึงไม่วาง Fibonacci และจะไม่ตั้งระดับขึ้นเองจากความรู้สึกแทนครับ"]
    if _is_xauusd_h1_hybrid(story):
        return _hybrid_fib_lines(story)
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
        text = ("ภาพรวมอินดิเคเตอร์ยังให้น้ำหนักฝั่งบวกอย่างระมัดระวัง "
                "โดยแรงซื้อยังไม่เสียเปรียบ")
    elif not rsi_positive and not macd_positive:
        text = ("ภาพรวมจากอินดิเคเตอร์ยังให้น้ำหนักฝั่งลบ "
                "แสดงว่าแรงขายยังได้เปรียบ")
    else:
        text = ("ภาพรวมจากอินดิเคเตอร์ให้สัญญาณผสม "
                f"โดย MACD อยู่{'ฝั่งบวก' if macd_positive else 'ฝั่งลบ'} "
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
    return text + " ส่วน Fibonacci ใช้กำหนดโซนเฝ้าระวังและระดับยกเลิกแผนในหัวข้อถัดไป"


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
    """แผนหลักฉบับเดียวที่สอดคล้องกับ plan_state และกรอบวิเคราะห์ของ story"""
    money = money_for(story)
    state = plan_state(story)
    primary = state["primary"]
    if not primary:
        return ["รอบนี้ไม่มีชุด Fibonacci ที่ผ่านเกณฑ์ จึงไม่มีแผนที่ระบบกล้าตั้งให้ "
                "และจะไม่ตั้งระดับจากความรู้สึกแทนครับ"]

    plan_timeframe = _timeframe_label(story)
    entry_low = min(primary["entry_low"], primary["entry_high"])
    entry_high = max(primary["entry_low"], primary["entry_high"])
    side = primary["side"]
    structure_level = (story["fib"]["swing_high"]["price"]
                       if side == "sell" else story["fib"]["swing_low"]["price"])
    if side == "sell":
        confirmation = (f"รอแท่งเทียนปฏิเสธราคาในกรอบ {plan_timeframe} "
                        "ร่วมกับค่า RSI เด้งขึ้นแล้ววกกลับต่ำกว่า 50 "
                        "หรือ MACD Histogram เริ่มหดตัวและพลิกเป็นลบ")
        side_word = "SELL"
    else:
        confirmation = (f"รอแท่งเทียนยืนยันแรงซื้อในกรอบ {plan_timeframe} "
                        "ร่วมกับค่า RSI ยืนเหนือ 50 "
                        "หรือ MACD Histogram ขยายตัวเป็นบวก")
        side_word = "BUY"
    if state["kind"] == "awaiting_confirmation":
        status = "ราคาเข้าโซนแล้ว แต่ยังต้องรอสัญญาณยืนยันก่อนเปิดสถานะ"
    elif state["kind"] == "out_of_range":
        status = (f"ราคายังไม่เข้าโซนและโซนอยู่ไกลเกินเกณฑ์แผน {plan_timeframe} "
                  "จึงยังไม่เปิดสถานะ")
    else:
        status = "ราคายังไม่เข้าโซน จึงยังไม่เปิดสถานะ"
    review = (f"หาก{_closed_bar_phrase(story)}เหนือ {money(structure_level)} ให้หยุดรอแผนและประเมินโครงสร้างใหม่"
              if side == "sell" else
              f"หาก{_closed_bar_phrase(story)}ต่ำกว่า {money(structure_level)} ให้หยุดรอแผนและประเมินโครงสร้างใหม่")
    zone_note = (f"ช่วง {money(entry_low)}–{money(entry_high)} เป็นพื้นที่เฝ้าระวัง "
                 f"ไม่ใช่ราคาที่ต้องตั้งคำสั่ง {side_word} ทันที ราคาต้องเข้าสู่โซนและแสดงสัญญาณ"
                 + ("กลับตัวลงก่อน" if side == "sell" else "ยืนยันก่อน")
                 + " จึงค่อยประเมินจุดเข้าอีกครั้ง")
    return [
        f"- **สถานะปัจจุบัน:** {status}",
        f"- **พื้นที่เฝ้าระวัง:** {money(entry_low)}–{money(entry_high)}",
        f"- **เงื่อนไขแรก:** ราคาต้อง{'ดีดกลับเข้าสู่' if side == 'sell' else 'ย่อตัวเข้าสู่'}พื้นที่เฝ้าระวัง",
        f"- **สัญญาณยืนยัน:** {confirmation}",
        f"- **Entry:** เลือกจุดเข้าหลังเกิดสัญญาณยืนยันภายในโซน ไม่ตั้ง {side_word} อัตโนมัติเพียงเพราะราคาแตะโซน",
        f"- **SL:** {money(primary['sl'])}",
        f"- **TP1:** {money(primary['tps'][0])}",
        f"- **TP2:** {money(primary['tps'][1])}",
        f"- **TP3:** {money(primary['tps'][2])}",
        f"- **เงื่อนไขทบทวนแผน:** {review}",
        "",
        zone_note,
    ]


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
    state = plan_state(story)
    primary = state["primary"]
    if state["kind"] in {"waiting_zone", "awaiting_confirmation"}:
        side = primary["side"].upper()
        money = money_for(story)
        zone = f"{money(min(primary['entry_low'], primary['entry_high']))}–{money(max(primary['entry_low'], primary['entry_high']))}"
        trend = "เทรนด์ลง" if story["regime"]["down"] else "เทรนด์ขึ้น"
        tail = f"รีบาวด์สั้นใน{trend} · โฟกัสโซนรอ {side} {zone}"
    else:
        tail = f"{profile['short_name']}{verb} {close:,.0f} · {_indicator_watch(story)}"
    return headline_format.h1(story["asset"], chart_story_writer_publish_date(story), tail)


def _executive_summary_lines(story: dict) -> list[str]:
    """สรุปสามบรรทัดสำหรับคนที่ต้องการอ่านภาพรวมก่อนรายละเอียดอินดิเคเตอร์."""
    state = plan_state(story)
    primary = state["primary"]
    trend = "ขาลง" if story["regime"]["down"] else "ขาขึ้น"
    timeframe = _timeframe_label(story)
    if state["kind"] in {"waiting_zone", "awaiting_confirmation"}:
        money = money_for(story)
        side = primary["side"].upper()
        zone = f"{money(min(primary['entry_low'], primary['entry_high']))}–{money(max(primary['entry_low'], primary['entry_high']))}"
        status = ("ราคาอยู่ในโซนแล้ว — ยังต้องรอสัญญาณยืนยันก่อนเปิดสถานะ"
                  if state["kind"] == "awaiting_confirmation"
                  else "ราคายังไม่เข้าโซน จึงยังไม่เปิดสถานะ")
        action = f"เฝ้าดูโซนรอ {side} `{zone}` และรอสัญญาณยืนยันก่อนเปิดสถานะ"
    elif state["kind"] == "out_of_range" and primary:
        money = money_for(story)
        side = primary["side"].upper()
        zone = f"{money(min(primary['entry_low'], primary['entry_high']))}–{money(max(primary['entry_low'], primary['entry_high']))}"
        status = f"โซนรอ {side} ยังอยู่ไกลจากราคาปัจจุบัน จึงยังไม่เปิดสถานะ"
        action = f"เฝ้าดูโซนรอ {side} `{zone}` และรอสัญญาณยืนยันก่อนเปิดสถานะ"
    else:
        status = ("ยังไม่มีโซนที่ผ่านเกณฑ์สำหรับเปิดสถานะ"
                  if state["kind"] == "no_setup"
                  else "ยังไม่มีสถานะแผนที่พร้อมใช้งาน")
        action = ("เฝ้าดูอินดิเคเตอร์และรอข้อมูลที่ยืนยันได้ก่อนตัดสินใจ"
                  if state["kind"] == "no_setup"
                  else "รอข้อมูลสถานะแผนที่ครบก่อนตัดสินใจ")
    return [
        "## สรุปภาพรวมวันนี้ (Executive Summary)", "",
        f"- **Bias หลัก:** {trend}บนกราฟ {timeframe}",
        f"- **สถานะราคา:** {status}",
        f"- **Action Plan:** {action}", "",
    ]


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
    opening_asset = ("[XAUUSD](/thailand/asset-xauusd)"
                     if story["asset"] == "xauusd" else story["symbol"])

    if _is_h1(story):
        opening = (
            f"บทความนี้ประเมิน {opening_asset} ด้วย RSI, MACD และ Fibonacci Retracement โดยใช้"
            f"แท่ง H1 ล่าสุดที่ปิดแล้ว ({thai_date(story['current']['date'])}) ที่ {current_text} "
            f"ดอลลาร์ ขณะที่ภาพรวม H1 ยังอยู่ในแนวโน้ม{trend_word}")
    else:
        opening = (
            f"บทความนี้ประเมิน {opening_asset} ด้วย RSI, MACD และ Fibonacci Retracement โดยใช้"
            f"แท่งรายวันล่าสุด ({thai_date(story['current']['date'])}) ซึ่งปิดที่ {current_text} "
            f"ดอลลาร์ ขณะที่ภาพรวมรายวันยังอยู่ในแนวโน้ม{trend_word}")

    lines = chart_story_writer_frontmatter(story, title_text=seo_title(story), slug_kind="signals", excerpt_clauses=[
        f"{wcb_source.profile_for(story['asset'])['short_name']}ปิดที่ {current_text} ดอลลาร์",
        f"RSI(14) ที่ {story['rsi']['value']:.1f}",
        "สรุป Bias และโซนรอเข้าจาก RSI MACD และ Fibonacci พร้อมจุดตัดขาดทุนของแผนหลัก",
        "ทุกค่าคำนวณจากแท่งราคาจริง",
    ]) + [
        "# " + headline(story),
        "",
        opening,
        "",
        *_executive_summary_lines(story),
        *RULE,
        _h2(H2_STRUCTURE),
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
              _h2(H2_INDICATORS), "",
              f"- {_rsi_paragraph(story)}",
              f"- {_macd_paragraph(story)}", "",
              FIB_BLOCK, ""]
    lines += _fib_lines(story)
    lines += ["", *RULE, _h2(scenario_heading(story)), ""]
    lines += _scenario_lines(story)
    # Style E จบที่แผนตามแนวโน้ม — ไม่เติม disclaimer, สรุปซ้ำ หรือ CTA
    lines += [""]
    # ⚠️ ย่อหน้า "**คำเตือนความเสี่ยง:** …" ถูกถอด 2026-08-14 (ผู้ใช้สั่ง — เว็บมี
    # คำเตือนของตัวเองอยู่แล้ว บทจึงไม่ต้องพกซ้ำ) พร้อมด่าน `risk_disclaimer`
    # ที่เฝ้ามัน ⇒ **คำเตือนความเสี่ยงของสไตล์ E ตอนนี้ขึ้นกับเทมเพลตเว็บทั้งหมด**
    # ถ้าวันใดเว็บถอดของตัวเองออก บทจะไม่มีคำเตือนเลยและไม่มีอะไรฟ้อง
    # (สไตล์ D กับ A/B/C ยังมีของตัวเองตามเดิม — ไม่ได้แก้พร้อมกัน)
    lines += [""]
    article = "\n".join(_indent_prose_lines(lines))
    # เว้นวรรคชื่อกรอบให้สม่ำเสมอใน Style E โดยไม่กระทบ writer อื่น
    return article.replace("กรอบH1", "กรอบ H1").replace("แนวโน้มH1", "แนวโน้ม H1")


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
    for token in _NUMBER.findall(chart_story_writer_publication_slug(story, kind="signals")):
        allowed.add(token.rstrip(".,"))
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

    SL คือ "จุดยกเลิกมุมมอง" ของฉากทัศน์ฝั่งนั้นตรง ๆ · แผนหลักยังแสดงเป็น
    พื้นที่เฝ้าระวังแม้โซนไกลเกินเกณฑ์ จึงต้องตรวจคู่โซน ↔ SL ทุกครั้ง
    """
    pairs = []
    for key, label in (("primary", "Scenario A"),):
        scenario = story["scenarios"].get(key)
        if not scenario:
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
    expected_slug = chart_story_writer_publication_slug(story, kind="signals")
    if not re.search(rf"(?m)^slug:\s*{re.escape(expected_slug)}\s*$", markdown):
        findings.append({
            "rule": "slug_invalid", "severity": "fatal", "line": 1,
            "message": f"Style E ต้องใช้ slug: {expected_slug}",
        })
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
    primary = story["scenarios"].get("primary")
    expected_scenario_heading = scenario_heading(story)
    if primary and expected_scenario_heading not in markdown:
        findings.append({
            "rule": "scenario_section", "severity": "fatal", "line": 1,
            "message": "story มีแผนหลัก แต่บทไม่มีหัวข้อแผนหลักที่ตรงกับฝั่ง BUY/SELL — โครงต้นแบบบังคับ",
        })
    if primary:
        opposite = "BUY" if primary["side"] == "sell" else "SELL"
        if f"รอ {opposite} ตามแนวโน้มหลัก" in markdown:
            findings.append({
                "rule": "scenario_side_section", "severity": "fatal", "line": 1,
                "message": "หัวข้อแผนระบุ BUY/SELL ไม่ตรงกับฝั่ง primary ใน story",
            })
    # ประโยคอธิบาย Entry/SL/TP และวลี "ไม่ใช่คำทำนาย" ถูกถอดจาก Style E
    # ตามแม่แบบใหม่ — หน้าเว็บมีบริบทคำเตือนของตัวเองอยู่แล้ว
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
