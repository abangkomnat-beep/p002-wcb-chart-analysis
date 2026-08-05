"""นักเขียนสามคน สามสไตล์ — จาก evidence pack ก้อนเดียวกัน

ระบบมี Technical Set สามชุด (แนวโน้ม · โมเมนตัม · ระดับราคา) มาตั้งแต่ต้น
แต่ผลลัพธ์ถูกยุบรวมเป็นบทความสไตล์เดียว ผู้ใช้จึงเห็นเสียงเดียว (คำสั่งผู้ใช้ 2026-08-04)
โมดูลนี้แยกออกเป็นนักเขียนสามคน แต่ละคนอ่าน `article_data` ก้อนเดียวกันแล้วเล่าคนละแบบ

    ณธาร  — รายงานตลาด      ร้อยแก้วทางการ 4 ช่วง หัวข้อเดียว (ของเดิม ไม่แตะ)
    กฤช   — โครงสร้างราคา    รายงานนักวิเคราะห์ หัวข้อย่อยเลขกำกับ ป้ายตัวหนา รายการโซน
    ปุณณ์  — จังหวะตลาด       ประโยคสั้น เปิดด้วยโมเมนตัม ปิดด้วยรายการสิ่งที่ต้องจับตา

**กติกาที่ทั้งสามคนใช้ร่วมกันและห้ามยกเว้น**

- เลขทุกตัวต้องมาจาก `article_data` ผ่าน `voice_rules.format_*` เท่านั้น
  ห้ามคำนวณใหม่ในชั้นนี้ — ด่าน `public_copy_validator` จะจับได้ทันทีถ้าฝืน
- ระบบมีข้อมูลรายวันเท่านั้น ⇒ ห้ามภาษาชี้จังหวะเข้าแบบระหว่างวันทุกสไตล์
- evidence ไม่พอ = ตัดประโยคนั้นเงียบ ไม่มีคำแก้ตัว ไม่มีหัวข้อว่าง

**ตัวเลขจุดเข้า / จุดตัดขาดทุน / อัตราส่วนผลตอบแทน — สไตล์ ② เท่านั้น**

มติเดิมข้อ 14ก กันตัวเลขชุดนี้ไว้ฝั่ง internal · ผู้ใช้ **ปลดล็อกเมื่อ 2026-08-04**
ให้ใส่ในสไตล์ของกฤชได้ (สไตล์ ① กับ ③ ไม่มี ตามเดิม) โดยยังคงข้อจำกัดอีกสองข้อไว้ครบ:

1. ระดับที่พูดถึงต้องเป็นค่าจาก `level-map.zones` ที่อนุมัติแล้วเท่านั้น — ห้ามสร้างเลขใหม่
2. ภาษาต้องเป็นเงื่อนไขระดับวัน ("เมื่อแท่งรายวันปิดใต้ …") ตาม `allowed_language` ของ
   `levels.classify_scenario` — ห้าม "เข้า Buy ตรงนี้" เพราะเราไม่มีข้อมูลระหว่างวัน
   ที่จะยืนยันจังหวะนั้นได้จริง (ดู `forbidden_language` ในโมดูลเดียวกัน)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import article_builder, risk_auditor, voice_rules  # noqa: E402


# ---------------------------------------------------------------- โปรไฟล์โครงสร้าง
# ด่านตรวจใช้ค่าชุดนี้แทนกฎตายตัวของสไตล์เดิม — สไตล์ต่างกันโครงสร้างต่างกันได้
# แต่กฎเนื้อหา (ตัวเลขตรง evidence · ห้ามศัพท์ระบบ · ห้ามตาราง · H1 หัวเดียว) เหมือนกันหมด
STRICT_PROSE_PROFILE = {
    "allow_subheadings": False,
    "require_technical_heading": True,
    "word_min": voice_rules.WORD_MIN,
    "word_max": voice_rules.WORD_MAX,
}


def _chart_name(data: dict, override: str | None) -> str:
    return override or Path(data["visuals"]["static_path"]).name


def _caption(data: dict) -> tuple[str, str]:
    """ข้อความ alt และ caption ของกราฟ — ใช้สูตรเดียวกันทุกสไตล์"""
    symbol = data["instrument"]["symbol"]
    days = data["visuals"].get("average_line_days") or []
    alt = f"กราฟแท่งเทียนรายวันของ {symbol} พร้อมแนวรับ แนวต้าน และเส้นค่าเฉลี่ยสำคัญ"
    if not days:
        return alt, f"กราฟรายวันของ {symbol} พร้อมแนวรับและแนวต้านสำคัญ"
    if len(days) == 1:
        days_text = f"{days[0]} วัน"
    else:
        days_text = f"{', '.join(str(day) for day in days[:-1])} กับ {days[-1]} วัน"
    return alt, f"กราฟรายวันของ {symbol} พร้อมแนวรับ แนวต้าน และเส้นค่าเฉลี่ย {days_text}"


def _frontmatter(data: dict) -> list[str]:
    instrument = data["instrument"]
    return [
        "---",
        f"title: '{data['headline']}'",
        f"symbol: {instrument['symbol']}",
        f"instrument_type: {instrument['instrument_type']}",
        f"cutoff_at: '{instrument['cutoff_at']}'",
        f"timezone: {instrument['public_timezone']}",
        "---",
        "",
    ]


def _chart_block(data: dict, chart_name: str | None) -> list[str]:
    alt, caption = _caption(data)
    return ["", f"![{alt}]({_chart_name(data, chart_name)})", "", f"*{caption}*", ""]


def _price(data: dict, value: float) -> str:
    return voice_rules.format_price(value, data["instrument"]["instrument_type"])


def _bullish(data: dict) -> bool:
    """ฝั่งที่ได้เปรียบ — ทั้งสามคนต้องอ่านภาพตรงกัน และต้องตรงกับแผนฝั่ง internal ด้วย

    สไตล์ต่างกันได้ที่วิธีเล่า แต่ห้ามต่างกันที่ข้อสรุป ไม่งั้นบทความสามฉบับของวันเดียวกัน
    จะขัดกันเอง แล้วผู้อ่านที่เห็นทั้งสามฉบับจะไม่รู้ว่าเชื่อฉบับไหน

    **ตำแหน่งเทียบเส้นค่าเฉลี่ยมาก่อน RSI เสมอ** (กติกากลางอยู่ที่
    `voice_rules.price_vs_averages`) · ผลพลอยได้คือมันไม่มีวันขัดกับ
    `trade_plan.infer_bias` ได้อีก เพราะแผนจะมีทิศก็ต่อเมื่อราคาเรียงตัวอยู่ข้างเดียว
    ของทั้งสองเส้นเท่านั้น — ซึ่งเป็นเงื่อนไขเดียวกับสองสาขาแรกข้างล่างนี้
    """
    technical = data["technical"]
    price = data["snapshot"]["price"]
    position = voice_rules.price_vs_averages(price, technical["ma20"], technical["ma50"])
    if position == "below":
        return False
    if position == "above":
        return True
    phrase = article_builder._buy_sell_phrase(
        price, technical["ma20"], technical["ma50"], technical["rsi14"])
    return bool(phrase) and "แรงซื้อยัง" in phrase and "อ่อนแรง" not in phrase


def _news_sentences(data: dict) -> list[str]:
    """ประเด็นข่าวที่ผ่านชั้นคัดกรอง — คืนลิสต์ว่างเมื่อไม่มีข่าว (ตัดเงียบ)"""
    items = data.get("drivers", {}).get("verified_news") or []
    if not items:
        return []
    lines = [f"ประเด็นที่ตลาดให้น้ำหนักในรอบนี้คือ{items[0]['event']} "
             f"ซึ่งส่งผลต่อ{items[0]['signal']}"]
    if len(items) > 1:
        lines.append(f"อีกเรื่องที่ต้องติดตามคู่กันคือ{items[1]['event']} "
                     f"ซึ่งโยงกับ{items[1]['signal']}")
    names, seen = [], set()
    for item in items:
        name = article_builder._safe_source_name(item.get("source", ""))
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    if names:
        joined = names[0] if len(names) == 1 else f"{' '.join(names[:-1])} และ {names[-1]}"
        lines.append(f"ทั้งหมดนี้อ้างจากรายงานของ {joined} ในรอบวันทำการล่าสุด")
    return lines


# ------------------------------------------------- แผนการเทรดที่ปล่อยขึ้นบทความได้
def plan_for_public(trade_branch: dict | None) -> dict | None:
    """คืนแผนที่ **พูดถึงในบทความสาธารณะได้** หรือ None ถ้ายังไม่มีแผนที่พูดได้

    เกณฑ์ผ่านสามข้อ — ผิดข้อใดข้อหนึ่ง = ไม่มีหัวข้อแผนในบทความเลย ไม่ใช่มีแล้วติดป้าย:

    1. สาขาแผนต้องสร้างสำเร็จ (`status: built`) — สาขาล้มหรือถูกด่านความเสี่ยง veto
       (`blocked`) ไม่มีสิทธิ์ขึ้นบทความ
    2. ต้องไม่ใช่ `no_trade` — วันที่เส้นค่าเฉลี่ยยังไม่เรียงตัว ระบบตอบว่า "ไม่มีจังหวะ"
       ซึ่งเป็นคำตอบที่ถูก การเค้นตัวเลขออกมาในวันแบบนั้นคือการแต่งแผนขึ้นเอง
    3. **ด่านความเสี่ยงต้องตัดสิน `pass` เท่านั้น** — `revise` ก็ไม่ผ่าน

    **ข้อ 3 เคยรับ `revise` ด้วย · ปิดทางนั้นเมื่อ 2026-08-05 หลังวัดของจริง**

    เหตุผลเดิมคือเกณฑ์ใน `risk_auditor` ยังไม่ผ่านการวัด จะเอาเลขที่เรายังไม่เชื่อเอง
    มาห้ามเผยแพร่ไม่ได้ · ระยะ 4 วัดแล้ว 484 วัน (121 วัน × 4 สินทรัพย์) เหตุผลนั้นจึงหมดอายุ
    และสิ่งที่วัดเจอแรงกว่าที่คิด — **ไม่มีแผนไหนได้ `pass` เลยสักวันเดียวจาก 221 แผน**
    เพราะจุดตัดขาดทุนกับเป้าหมายถูกดึงจากตารางระดับชุดเดียวกัน ระยะสองฝั่งจึงล็อกกัน
    (ผลเต็ม: `01-CC/Output/2026-08-05_ผลวัดระยะ4-เกณฑ์ความเสี่ยง-P002.md`)

    ⇒ ด่านนี้จึงปิดสนิทโดยตั้งใจในตอนนี้ **ไม่ใช่ความผิดพลาด** — ผู้ใช้เลือกทาง ข เมื่อ
    2026-08-05 คือถอนตัวเลขแผนออกจากบทความจนกว่าตัวสร้างแผนจะถูกออกแบบใหม่ (ทาง ค)
    แผนยังถูกสร้างและเก็บครบฝั่ง internal ตามเดิม ไม่ได้ถูกปิดการทำงาน

    **ห้ามผ่อนเกณฑ์ใน `risk_auditor.DEFAULT_THRESHOLDS` เพื่อให้ด่านนี้เปิด** — ทางออกที่
    ผู้ใช้เลือกคือแก้วิธีเลือกเป้าหมาย ไม่ใช่ลดเกณฑ์ลงมาหาผลลัพธ์
    """
    if not trade_branch or trade_branch.get("status") != "built":
        return None
    plan = trade_branch.get("plan")
    if not plan or plan.get("classification") == "no_trade":
        return None
    if not (plan.get("entry") and plan.get("stop") and plan.get("targets")):
        return None
    audit = trade_branch.get("audit") or {}
    # `pass` เท่านั้น — ผลตรวจที่หายไปหรืออ่านไม่ออกก็ถือว่าไม่ผ่าน (fail-closed)
    if audit.get("verdict") != risk_auditor.VERDICT_PASS:
        return None
    return plan


def plan_evidence(plan: dict) -> dict:
    """เฉพาะค่าที่หัวข้อแผนพูดถึงจริง — ไม่ยกทั้งแผนเข้ากองหลักฐาน

    กองหลักฐานยิ่งกว้าง ด่านตรวจตัวเลขยิ่งหลวม เพราะเลขในบทความผ่านได้ถ้าตรงกับ
    ค่าใดก็ได้ในกอง · แผนเต็มมีทั้งคะแนนความเชื่อมั่นและระยะเทียบความผันผวนปนอยู่
    ซึ่งไม่มีตัวไหนถูกเขียนลงบทความเลย
    """
    return {
        "entry_zone": plan["entry"]["zone"],
        "entry_edge": plan["entry"]["edge"],
        "stop": plan["stop"]["value"],
        "targets": [target["value"] for target in plan["targets"]],
    }


def plan_ratio_values(plan: dict) -> list[float]:
    """ค่าอัตราส่วนผลตอบแทนต่อความเสี่ยงที่บทความได้รับอนุญาตให้เขียน"""
    return [target["rr"] for target in plan["targets"]]


# ================================================================ ① ณธาร — รายงานตลาด
def render_market_report(data: dict, *, chart_name: str | None = None,
                         plan: dict | None = None) -> str:
    """สไตล์ที่ 1 — ของเดิมทุกตัวอักษร ไม่แตะ

    ห่อ `article_builder.render_markdown` ไว้เฉย ๆ เพื่อให้เรียกผ่านทะเบียนนักเขียนได้
    เหมือนอีกสองคน · ของเดิมถูกล็อกด้วยเทสชุด pilot-baseline อยู่ ห้ามเปลี่ยนถ้อยคำ
    รับ `plan` ไว้ให้ลายเซ็นตรงกันทั้งสามคนเท่านั้น — สไตล์นี้ไม่ใช้และจะไม่ใช้
    """
    return article_builder.render_markdown(data, chart_name=chart_name)


# ============================================================ ② กฤช — โครงสร้างราคา
def _structure_intro(data: dict) -> str:
    """ย่อหน้านำแบบบทวิเคราะห์ — เปิดด้วยบริบทข่าว/ภาพรวม แล้วค่อยลงราคา

    ต่างจากสไตล์ ① ที่เปิดด้วยราคาเปิดตลาดทันที — คนอ่านบทวิเคราะห์อยากรู้ก่อนว่า
    "ทำไมราคาถึงมาอยู่ตรงนี้" แล้วค่อยรู้ว่า "ตรงนี้คือตรงไหน"
    """
    instrument = data["instrument"]
    snapshot = data["snapshot"]
    symbol = instrument["symbol"]
    unit = instrument["unit"]
    context = data.get("context") or {}

    pieces: list[str] = []
    news = data.get("drivers", {}).get("verified_news") or []
    if news:
        pieces.append(f"ภาพของ{instrument['instrument_label']}รอบนี้ถูกกำหนดด้วย"
                      f"{news[0]['event']}เป็นหลัก "
                      f"โดยตลาดกำลังหาคำตอบเรื่อง{news[0]['signal']}")

    direction_word = {"up": "ฝั่งซื้อกลับมาคุมเกม", "down": "ฝั่งขายยังกดราคาต่อ",
                      "flat": "สองฝั่งยังไม่มีใครชนะ"}.get(data["move"]["direction"])
    weight = {voice_rules.MOVE_STRONG: "อย่างมีน้ำหนัก",
              voice_rules.MOVE_QUIET: "แบบยังไม่ขาดลอย"}.get(data["move"]["class"], "")
    if direction_word:
        opening = f"ในรอบการซื้อขายล่าสุด {direction_word}"
        if weight:
            opening += weight
        pieces.append(opening + f" ราคาล่าสุดของ {symbol} อยู่ที่ {_price(data, snapshot['price'])} {unit}")
    else:
        pieces.append(f"ราคาล่าสุดของ {symbol} อยู่ที่ {_price(data, snapshot['price'])} {unit}")

    # ต้องบอกให้ชัดว่าเป็นกรอบ "แนวรับ-แนวต้านที่ใกล้ที่สุด" ไม่ใช่กรอบราคา 20 วัน
    # ที่ย่อหน้าถัดไปเล่า — สองกรอบนี้คนละอันและมักบอกคนละเรื่องกัน
    band = (context.get("levels") or {}).get("band_position")
    band_text = {"lower": "ค่อนไปทางขอบล่าง", "middle": "กลาง ๆ",
                 "upper": "ค่อนไปทางขอบบน"}.get(band)
    if band_text:
        pieces.append(f"ซึ่งอยู่{band_text}ของกรอบแนวรับ-แนวต้านที่ใกล้ที่สุด")
    return " ".join(pieces)


def _structure_today(data: dict) -> list[str]:
    """หัวข้อ 1 — สิ่งที่เกิดขึ้น + กรอบที่ผ่านมา (ป้ายตัวหนานำแต่ละย่อหน้า)"""
    instrument = data["instrument"]
    snapshot = data["snapshot"]
    unit = instrument["unit"]
    context = data.get("context") or {}
    lines: list[str] = []

    happened = [f"เปิดที่ {_price(data, snapshot['open'])} "
                f"แล้วขึ้นไปสูงสุด {_price(data, snapshot['high'])} "
                f"ต่ำสุด {_price(data, snapshot['low'])} {unit}"]
    percent = snapshot.get("percent_magnitude")
    previous = snapshot.get("previous_close")
    if percent is not None and previous is not None:
        word = {"up": "บวก", "down": "ลบ"}.get(data["move"]["direction"], "เปลี่ยนแปลง")
        happened.append(f"คิดเป็น{word}ราว {voice_rules.format_percent(percent)}% "
                        f"จากราคาปิดก่อนหน้าที่ {_price(data, previous)}")
    lines.append("**สิ่งที่เกิดขึ้น:** " + " ".join(happened))

    frame: list[str] = []
    ranges = context.get("ranges") or {}
    short = ranges.get("short")
    if short:
        frame.append(f"กรอบ {short['window']} วันทำการล่าสุดอยู่ระหว่าง "
                     f"{_price(data, short['low'])} ถึง {_price(data, short['high'])} {unit}")
        if short.get("percent_from_high") is not None and short["price_side_high"] != "at":
            word = "ต่ำกว่า" if short["price_side_high"] == "below" else "สูงกว่า"
            frame.append(f"ราคาล่าสุด{word}ยอดของกรอบราว "
                         f"{voice_rules.format_percent(short['percent_from_high'])}%")
    long_range = ranges.get("long")
    if long_range:
        frame.append(f"ถ้าถอยไปมอง {long_range['window']} วันทำการ เพดานอยู่ที่ "
                     f"{_price(data, long_range['high'])} และพื้นอยู่ที่ "
                     f"{_price(data, long_range['low'])} {unit}")
    streak = context.get("streak") or {}
    if streak.get("days") and streak["days"] >= article_builder.STREAK_MIN_DAYS \
            and streak.get("direction") in ("up", "down"):
        word = "ปิดบวก" if streak["direction"] == "up" else "ปิดลบ"
        frame.append(f"ก่อนหน้านี้ราคา{word}ติดกัน {streak['days']} วันทำการ")
    if frame:
        lines.append("**กรอบที่ผ่านมา:** " + " ".join(frame))
    return lines


def _structure_chart(data: dict) -> list[str]:
    """หัวข้อ 2 — โครงสร้างกราฟ แยกเป็นสามป้าย: เส้นค่าเฉลี่ย · โมเมนตัม · ความผันผวน"""
    technical = data["technical"]
    context = data.get("context") or {}
    unit = data["instrument"]["unit"]
    price = data["snapshot"]["price"]
    ma20, ma50, rsi14 = technical["ma20"], technical["ma50"], technical["rsi14"]
    lines: list[str] = []

    average: list[str] = []
    if ma20 is not None and ma50 is not None:
        if price > ma20 and price > ma50:
            read = "ราคายืนเหนือทั้งสองเส้น ซึ่งเป็นการเรียงตัวฝั่งขาขึ้น"
        elif price < ma20 and price < ma50:
            read = "ราคาอยู่ใต้ทั้งสองเส้น ซึ่งเป็นการเรียงตัวฝั่งขาลง"
        else:
            read = "ราคาถูกขนาบอยู่ระหว่างสองเส้น ซึ่งเป็นภาพที่ยังไม่เลือกทาง"
        average.append(f"เส้น 20 วันอยู่ที่ {_price(data, ma20)} และเส้น 50 วันอยู่ที่ "
                       f"{_price(data, ma50)} {unit} {read}")
    elif ma20 is not None:
        side = "เหนือ" if price > ma20 else "ใต้"
        average.append(f"เส้น 20 วันอยู่ที่ {_price(data, ma20)} {unit} ราคาล่าสุดอยู่{side}เส้นนี้")
    structure = (context.get("moving_average") or {}).get("structure")
    if structure == "short_above_long":
        average.append("เส้นระยะสั้นตัดขึ้นนำเส้นระยะยาวแล้ว")
    elif structure == "short_below_long":
        average.append("เส้นระยะสั้นยังตามหลังเส้นระยะยาวอยู่")
    short_line = ((context.get("moving_average") or {}).get("entries") or {}).get("ma20") or {}
    motion = {"up": "และตัวเส้นเองยังไต่ขึ้น", "down": "และตัวเส้นเองยังชี้ลง",
              "flat": "และตัวเส้นเองแทบไม่ขยับ"}.get(short_line.get("slope"))
    if motion:
        average.append(motion + f"เมื่อเทียบกับ {short_line['slope_lookback']} วันทำการก่อน")
    if average:
        lines.append("**เส้นค่าเฉลี่ย:** " + " ".join(average))

    zone = voice_rules.rsi_zone(rsi14)
    if zone:
        value, side = zone
        read = {"above": "อยู่เหนือโซนกลาง แปลว่าแรงซื้อยังพอมีเหลือ",
                "below": "อยู่ต่ำกว่าโซนกลาง แปลว่าแรงซื้อยังไม่กลับมาเต็มที่",
                "at": "อยู่พอดีโซนกลาง ซึ่งเป็นจุดที่ยังไม่เอนไปทางไหน"}[side]
        lines.append(f"**โมเมนตัม:** ค่า RSI อยู่ที่ {value} ซึ่ง{read}")

    volatility = context.get("volatility")
    if volatility:
        verdict = {"wider": "กว้างกว่าปกติ จังหวะราคาจึงเหวี่ยงแรงกว่าที่เคย",
                   "narrower": "แคบกว่าปกติ ตลาดกำลังอั้นแรงอยู่",
                   "similar": "พอ ๆ กับปกติ ยังไม่มีอะไรผิดจังหวะ"}[volatility["comparison"]]
        lines.append(f"**ความผันผวน:** ช่วงแกว่งรอบล่าสุดอยู่ที่ราว "
                     f"{voice_rules.format_percent(volatility['today_range_percent'])}% ของราคา "
                     f"เทียบค่าเฉลี่ย {volatility['window']} วันทำการที่ราว "
                     f"{voice_rules.format_percent(volatility['average_range_percent'])}% "
                     f"ถือว่า{verdict}")
    return lines


def _zone_text(data: dict, item: dict, level_index: dict) -> str:
    """ระดับหนึ่งค่า เขียนเป็นโซนเมื่อต้นทางเป็นโซนจริง — ห้ามแต่งช่วงขึ้นเอง

    ระดับที่เป็นจุดเดียวก็เขียนเป็นจุดเดียว การขยายให้เป็นช่วงเองคือการสร้างตัวเลข
    ที่ evidence ไม่มี ซึ่งด่านตรวจจะตีตกทันที และถึงผ่านก็เป็นการโกหกผู้อ่าน
    """
    view = level_index.get(item["level_id"]) or {}
    low, high = view.get("zone_low"), view.get("zone_high")
    if low is not None and high is not None:
        low_text, high_text = _price(data, low), _price(data, high)
        if low_text != high_text:
            return f"{low_text} ถึง {high_text}"
    return item["text"]


def _structure_zones(data: dict) -> list[str]:
    """หัวข้อ 3 — โซนที่ต้องจับตา เป็นรายการ แล้วปิดด้วยเงื่อนไขสองทาง"""
    block = data["sr_block"]
    unit = data["instrument"]["unit"]
    level_index = {view["id"]: view for view in data.get("levels") or []}
    context = data.get("context") or {}
    lines: list[str] = []

    if block["supports"]:
        lines.append("**โซนแนวรับที่ต้องเฝ้า:**")
        lines.append("")
        for order, item in enumerate(block["supports"], start=1):
            role = {1: "ด่านแรกที่ราคาจะไปทดสอบถ้าย่อลง",
                    2: "ด่านรองที่รับไว้ถ้าด่านแรกหลุด",
                    3: "ด่านลึกสุดของกรอบนี้"}.get(order, "ด่านถัดไป")
            lines.append(f"- {_zone_text(data, item, level_index)} {unit} — {role}")
        lines.append("")
    if block["resistances"]:
        lines.append("**โซนแนวต้านที่ต้องเฝ้า:**")
        lines.append("")
        for order, item in enumerate(block["resistances"], start=1):
            role = {1: "ด่านแรกที่ต้องผ่านให้ได้ก่อน",
                    2: "ด่านรองที่รอถ้าผ่านด่านแรกไปแล้ว",
                    3: "เพดานบนของกรอบนี้"}.get(order, "ด่านถัดไป")
            lines.append(f"- {_zone_text(data, item, level_index)} {unit} — {role}")
        lines.append("")

    levels = context.get("levels") or {}
    distance: list[str] = []
    if levels.get("support_distance_percent") is not None:
        distance.append("ห่างจากแนวรับแรกราว "
                        f"{voice_rules.format_percent(levels['support_distance_percent'])}%")
    if levels.get("resistance_distance_percent") is not None:
        distance.append("ห่างจากแนวต้านแรกราว "
                        f"{voice_rules.format_percent(levels['resistance_distance_percent'])}%")
    if distance:
        lines.append("**ระยะจากราคาปัจจุบัน:** " + " และ".join(distance))
    return lines


def _structure_conditions(data: dict) -> str:
    """เงื่อนไขสองทางระดับวัน — ภาษาที่ใช้ได้จริงกับข้อมูลรายวัน ไม่ใช่จังหวะเข้าระหว่างวัน"""
    block = data["sr_block"]
    supports, resistances = block["supports"], block["resistances"]
    bullish = _bullish(data)
    clauses: list[str] = []
    if resistances:
        follow = " และ ".join(item["text"] for item in resistances[1:3])
        clause = f"ถ้าปิดวันเหนือ {resistances[0]['text']} ได้"
        clause += (f" ทางขึ้นจะเปิดไปหา {follow}" if follow
                   else " ภาพฝั่งซื้อจะแข็งแรงขึ้นชัดเจน")
        clauses.append(clause)
    if supports:
        follow = " และ ".join(item["text"] for item in supports[1:3])
        clause = f"ถ้าปิดวันหลุด {supports[0]['text']} ลงมา"
        clause += (f" จะเปิดทางลงไปหา {follow}" if follow
                   else " ภาพฝั่งขายจะกลับมาคุมเกม")
        clauses.append(clause)
    if not clauses:
        return ""
    if len(clauses) == 2 and not bullish:
        clauses.reverse()
    return "**เงื่อนไขที่ต้องเห็น:** " + " ในทางกลับกัน ".join(clauses)


def _structure_plan(data: dict, plan: dict) -> list[str]:
    """หัวข้อ 4 — จุดเข้า จุดตัดขาดทุน และอัตราส่วนผลตอบแทนต่อความเสี่ยง

    เปิดใช้ตามคำสั่งผู้ใช้ 2026-08-04 (ปลดมติข้อ 14ก เฉพาะสไตล์นี้)

    สองอย่างที่ยังไม่ปลดและห้ามเผลอ:
    - **ภาษาต้องเป็นเงื่อนไขระดับวัน** — เราไม่มีข้อมูลระหว่างวัน จึงยืนยันจังหวะเข้า
      ระหว่างวันไม่ได้ · ที่เขียนได้คือ "เมื่อแท่งรายวันปิดใต้/เหนือระดับนี้"
    - **ทุกระดับต้องเป็นค่าที่อนุมัติแล้ว** — ค่าทั้งหมดในหัวข้อนี้มาจาก `plan` ตรง ๆ
      ซึ่ง `trade_plan.build` ประกอบจาก level map ที่ผ่านด่านแล้วเท่านั้น
    """
    unit = data["instrument"]["unit"]
    entry, stop = plan["entry"], plan["stop"]
    down = plan["bias"] == "down"
    lines: list[str] = []

    stack = {
        "price_below_falling_stack": "ราคายืนใต้เส้น 20 วัน และเส้น 20 วันเองก็อยู่ใต้เส้น 50 วัน",
        "price_above_rising_stack": "ราคายืนเหนือเส้น 20 วัน และเส้น 20 วันเองก็อยู่เหนือเส้น 50 วัน",
    }.get(plan["bias_reason"])
    opening = "**ทิศที่แผนนี้เล่น:** " + ("ฝั่งขาย" if down else "ฝั่งซื้อ")
    if stack:
        opening += f" เพราะ{stack}"
    lines.append(opening)

    trigger = "ใต้" if down else "เหนือ"
    entry_line = f"**จุดเข้า:** เมื่อแท่งรายวันปิด{trigger} {_price(data, entry['edge'])} {unit}"
    low, high = entry["zone"]
    low_text, high_text = _price(data, low), _price(data, high)
    if low_text != high_text:
        entry_line += f" ซึ่งเป็นขอบของโซน {low_text} ถึง {high_text}"
    entry_line += f" — ตราบที่ยังไม่มีแท่งรายวันปิด{trigger}ระดับนี้ ก็ยังไม่เข้าเงื่อนไข"
    lines.append(entry_line)

    lines.append(f"**จุดตัดขาดทุน:** {_price(data, stop['value'])} {unit} — "
                 f"ถ้าราคากลับไปปิดวัน{'เหนือ' if down else 'ใต้'}ระดับนี้ "
                 "แผนนี้จบทันที ไม่ต้องรอดูต่อ")

    names = {1: "เป้าหมายแรก", 2: "เป้าหมายที่สอง"}
    for order, target in enumerate(plan["targets"][:2], start=1):
        lines.append(f"**{names[order]}:** {_price(data, target['value'])} {unit} "
                     f"คิดเป็น {voice_rules.format_ratio(target['rr'])} "
                     "เท่าของระยะที่ต้องยอมเสี่ยง")

    # อัตราส่วนต่ำกว่า 1 คือข้อเท็จจริงเชิงระยะทาง ไม่ใช่ความเห็น — ปิดบังไม่ได้
    # และเขียนตรง ๆ ปลอดภัยกว่าซ่อนหัวข้อทั้งอัน เพราะคนอ่านเห็นเลขสองชั้นอยู่แล้ว
    if len(plan["targets"]) > 1 and plan["targets"][0]["rr"] < 1:
        lines.append("**สิ่งที่ต้องชั่งน้ำหนัก:** เป้าหมายแรกให้ผลตอบแทนน้อยกว่าระยะที่ต้อง"
                     "ยอมเสี่ยง แผนนี้จึงคุ้มต่อเมื่อถือไปถึงเป้าหมายชั้นที่สองเท่านั้น")
    return lines


def _structure_summary(data: dict) -> list[str]:
    """สรุปเป็นรายการสั้น — ท่าปิดของบทวิเคราะห์ที่ผู้ใช้ยกตัวอย่างมา"""
    instrument = data["instrument"]
    block = data["sr_block"]
    bullish = _bullish(data)
    lines = []
    lines.append(f"- **{instrument['block_label']} ที่ {_price(data, data['snapshot']['price'])} "
                 f"{instrument['unit']}:** "
                 + ("ฝั่งซื้อยังได้เปรียบตราบที่ยังไม่หลุดแนวรับแรก"
                    if bullish else
                    "ฝั่งขายยังได้เปรียบตราบที่ยังผ่านแนวต้านแรกไปไม่ได้"))
    if block["supports"] and block["resistances"]:
        lines.append(f"- **กรอบที่ยังใช้ได้:** {block['supports'][0]['text']} ถึง "
                     f"{block['resistances'][0]['text']} {instrument['unit']} "
                     "ตราบที่ยังอยู่ในกรอบนี้ ภาพรวมคือการแกว่งไม่ใช่การเปลี่ยนทิศ")
    flip = block["resistances"][0]["text"] if not bullish and block["resistances"] else (
        block["supports"][0]["text"] if block["supports"] else None)
    if flip:
        word = "ยืนเหนือ" if not bullish else "หลุด"
        lines.append(f"- **จุดที่ภาพจะพลิก:** ราคา{word} {flip} {instrument['unit']} "
                     "แบบปิดวันได้ คือสัญญาณที่ต้องกลับมาทบทวนภาพทั้งหมดใหม่")
    return lines


def render_price_structure(data: dict, *, chart_name: str | None = None,
                           plan: dict | None = None) -> str:
    """สไตล์ที่ 2 — รายงานนักวิเคราะห์แบบมีหัวข้อย่อยและรายการโซน

    หน้าตาอิงบทวิเคราะห์ที่ผู้ใช้ยกตัวอย่างมา (2026-08-04): หัวข้อเลขกำกับ ป้ายตัวหนา
    นำแต่ละย่อหน้า รายการโซนเป็น bullet และปิดด้วยสรุปเป็นรายการ

    `plan` คือแผนที่ผ่าน `plan_for_public` แล้วเท่านั้น — ส่ง None มาเมื่อวันนั้น
    ไม่มีแผนที่พูดได้ แล้วบทความจะข้ามหัวข้อ 4 ไปเงียบ ๆ โดยที่หัวข้ออื่นยังครบ
    (ตัวเลือกทิศทางสองทางยังอยู่ในบรรทัด "เงื่อนไขที่ต้องเห็น" ของหัวข้อ 3 ตามเดิม)
    """
    lines = [
        *_frontmatter(data),
        f"# {data['headline']}",
        "",
        f"*ข้อมูล ณ {data['instrument']['cutoff_public']}*",
        "",
        _structure_intro(data),
        "",
        "## 1. ภาพตลาดรอบล่าสุด",
        "",
    ]
    for paragraph in _structure_today(data):
        lines.extend([paragraph, ""])
    lines.extend(["## 2. โครงสร้างกราฟ", ""])
    for paragraph in _structure_chart(data):
        lines.extend([paragraph, ""])
    lines.extend(["## 3. โซนที่ต้องจับตา", ""])
    for line in _structure_zones(data):
        lines.append(line)
    if lines[-1] != "":
        lines.append("")
    conditions = _structure_conditions(data)
    if conditions:
        lines.extend([conditions, ""])
    if plan:
        lines.extend(["## 4. แผนที่ตัวเลขรองรับ", ""])
        for paragraph in _structure_plan(data, plan):
            lines.extend([paragraph, ""])
    lines.extend(["## สรุป", ""])
    lines.extend(_structure_summary(data))
    lines.extend(_chart_block(data, chart_name))
    return "\n".join(lines)


PRICE_STRUCTURE_PROFILE = {
    "allow_subheadings": True,
    "require_technical_heading": False,
    # ยาวกว่าสไตล์ ① เพราะมีหัวข้อย่อยและรายการโซนกินที่ — วัดจากฉบับจริงทั้งสี่สินทรัพย์
    # ช่วงนี้ต้องครอบทั้งวันที่มีหัวข้อแผน (+ราว 100 คำ) และวันที่ไม่มี — วัดได้ 460–580
    "word_min": 380,
    "word_max": 760,
}


# ============================================================== ③ ปุณณ์ — จังหวะตลาด
def _tempo_lead(data: dict) -> str:
    """เปิดด้วยจังหวะ ไม่ใช่ราคา — คนอ่านสไตล์นี้อยากรู้ก่อนว่า "วันนี้ตลาดอารมณ์ไหน" """
    context = data.get("context") or {}
    snapshot = data["snapshot"]
    instrument = data["instrument"]
    volatility = context.get("volatility")
    sentences: list[str] = []

    if volatility:
        mood = {"wider": "ตลาดเหวี่ยงกว่าปกติ",
                "narrower": "ตลาดนิ่งกว่าปกติ",
                "similar": "ตลาดเดินจังหวะปกติ"}[volatility["comparison"]]
        sentences.append(f"{mood}ในรอบล่าสุด")
    move = data["move"]
    tempo = {
        ("up", voice_rules.MOVE_STRONG): "ราคาขึ้นแรง",
        ("up", voice_rules.MOVE_NORMAL): "ราคาขยับขึ้น",
        ("down", voice_rules.MOVE_STRONG): "ราคาลงแรง",
        ("down", voice_rules.MOVE_NORMAL): "ราคาย่อลง",
    }.get((move["direction"], move["class"]))
    if move["class"] == voice_rules.MOVE_QUIET:
        tempo = "ราคาแทบไม่ไปไหน"
    if tempo:
        percent = snapshot.get("percent_magnitude")
        line = f"{tempo}มาอยู่ที่ {_price(data, snapshot['price'])} {instrument['unit']}"
        if percent is not None:
            line += f" คิดเป็นราว {voice_rules.format_percent(percent)}% จากวันก่อน"
        sentences.append(line)
    else:
        sentences.append(f"ราคาล่าสุดอยู่ที่ {_price(data, snapshot['price'])} {instrument['unit']}")
    sentences.append(f"ระหว่างวันแตะสูงสุด {_price(data, snapshot['high'])} "
                     f"และต่ำสุด {_price(data, snapshot['low'])}")
    return " ".join(sentences)


def _tempo_momentum(data: dict) -> str:
    """ย่อหน้าโมเมนตัม — ประโยคสั้น เรียงต่อกันเป็นจังหวะ"""
    technical = data["technical"]
    context = data.get("context") or {}
    price = data["snapshot"]["price"]
    unit = data["instrument"]["unit"]
    ma20, ma50, rsi14 = technical["ma20"], technical["ma50"], technical["rsi14"]
    sentences: list[str] = []

    zone = voice_rules.rsi_zone(rsi14)
    if zone:
        value, side = zone
        sentences.append({
            "above": f"RSI อยู่ที่ {value} ยังอยู่ฝั่งบนของโซนกลาง",
            "below": f"RSI อยู่ที่ {value} ยังไม่กลับขึ้นเหนือโซนกลาง",
            "at": f"RSI อยู่ที่ {value} พอดีโซนกลาง ยังไม่เอนไปทางไหน"}[side])
    if ma20 is not None:
        side = "เหนือ" if price > ma20 else "ใต้"
        sentences.append(f"ราคาอยู่{side}เส้น 20 วันที่ {_price(data, ma20)} {unit}")
    if ma50 is not None:
        side = "เหนือ" if price > ma50 else "ใต้"
        sentences.append(f"และอยู่{side}เส้น 50 วันที่ {_price(data, ma50)} {unit}")
    volatility = context.get("volatility")
    if volatility:
        sentences.append("ช่วงแกว่งรอบล่าสุดกินราว "
                         f"{voice_rules.format_percent(volatility['today_range_percent'])}% "
                         f"ของราคา ค่าเฉลี่ย {volatility['window']} วันทำการอยู่ราว "
                         f"{voice_rules.format_percent(volatility['average_range_percent'])}%")
    streak = context.get("streak") or {}
    if streak.get("days") and streak["days"] >= article_builder.STREAK_MIN_DAYS \
            and streak.get("direction") in ("up", "down"):
        word = "บวก" if streak["direction"] == "up" else "ลบ"
        sentences.append(f"ก่อนหน้านี้ปิด{word}ติดกันมาแล้ว {streak['days']} วันทำการ")
    return " ".join(sentences)


def _tempo_frame(data: dict) -> str:
    """ย่อหน้ากรอบราคา — บอกว่าตอนนี้ยืนอยู่ตรงไหนของสนาม"""
    context = data.get("context") or {}
    unit = data["instrument"]["unit"]
    ranges = context.get("ranges") or {}
    sentences: list[str] = []
    short = ranges.get("short")
    if short:
        sentences.append(f"กรอบ {short['window']} วันทำการล่าสุดคือ "
                         f"{_price(data, short['low'])} ถึง {_price(data, short['high'])} {unit}")
    band = (context.get("levels") or {}).get("band_position")
    where = {"lower": "ตอนนี้ราคาอยู่ค่อนไปทางพื้นกรอบ",
             "middle": "ตอนนี้ราคาอยู่กลางกรอบ",
             "upper": "ตอนนี้ราคาอยู่ค่อนไปทางเพดานกรอบ"}.get(band)
    if where:
        sentences.append(where)
    long_range = ranges.get("long")
    if long_range:
        sentences.append(f"ภาพใหญ่ {long_range['window']} วันทำการ เพดานเดิมอยู่ที่ "
                         f"{_price(data, long_range['high'])} พื้นเดิมอยู่ที่ "
                         f"{_price(data, long_range['low'])} {unit}")
    return " ".join(sentences)


def _tempo_checklist(data: dict) -> list[str]:
    """ปิดด้วยรายการสิ่งที่ต้องจับตา — สั้น อ่านจบใน 10 วินาที"""
    block = data["sr_block"]
    unit = data["instrument"]["unit"]
    bullish = _bullish(data)
    lines = ["สิ่งที่ต้องจับตาต่อจากนี้"]
    lines.append("")
    if block["supports"]:
        follow = (" ถัดลงไปคือ " + block["supports"][1]["text"]
                  if len(block["supports"]) > 1 else "")
        lines.append(f"- แนวรับแรกอยู่ที่ {block['supports'][0]['text']} {unit}{follow} "
                     "— หลุดแบบปิดวันเมื่อไหร่ ภาพระยะสั้นเสียทันที")
    if block["resistances"]:
        follow = (" ถัดขึ้นไปคือ " + block["resistances"][1]["text"]
                  if len(block["resistances"]) > 1 else "")
        lines.append(f"- แนวต้านแรกอยู่ที่ {block['resistances'][0]['text']} {unit}{follow} "
                     "— ผ่านแบบปิดวันได้เมื่อไหร่ ภาพถึงจะเปลี่ยนจริง")
    lines.append("- ฝั่งที่ได้เปรียบตอนนี้คือ" + ("ฝั่งซื้อ" if bullish else "ฝั่งขาย")
                 + " แต่เป็นการได้เปรียบแบบมีเงื่อนไข ไม่ใช่แบบขาดลอย")
    return lines


def render_market_tempo(data: dict, *, chart_name: str | None = None,
                        plan: dict | None = None) -> str:
    """สไตล์ที่ 3 — ประโยคสั้น เปิดด้วยจังหวะและโมเมนตัม ปิดด้วยรายการที่ต้องจับตา

    เป็นเสียงที่ต่างจากอีกสองคนชัดที่สุด: ไม่มีหัวข้อย่อย ไม่มีย่อหน้ายาว
    เขียนให้คนที่เปิดอ่านตอนตลาดกำลังเดิน ไม่ใช่คนที่นั่งอ่านรายงานตอนเย็น
    รับ `plan` ไว้ให้ลายเซ็นตรงกันเท่านั้น — ผู้ใช้สั่งให้ตัวเลขแผนอยู่ในสไตล์ ② คนเดียว
    """
    lines = [
        *_frontmatter(data),
        f"# {data['headline']}",
        "",
        f"*ข้อมูล ณ {data['instrument']['cutoff_public']}*",
        "",
        _tempo_lead(data),
        "",
    ]
    for paragraph in (_tempo_momentum(data), _tempo_frame(data)):
        if paragraph:
            lines.extend([paragraph, ""])
    # ข่าวรวมเป็นย่อหน้าเดียว — สไตล์นี้ประโยคสั้นอยู่แล้ว ถ้าแยกทีละประโยคเป็นย่อหน้า
    # จะกลายเป็นบทความขาด ๆ ไม่ใช่บทความจังหวะกระชับ
    news = _news_sentences(data)
    if news:
        lines.extend([" ".join(news), ""])
    lines.extend(_tempo_checklist(data))
    lines.extend(_chart_block(data, chart_name))
    return "\n".join(lines)


TEMPO_PROFILE = {
    "allow_subheadings": False,
    "require_technical_heading": False,
    # สั้นกว่าอีกสองสไตล์โดยเจตนา — ประโยคสั้นคือตัวสไตล์ ไม่ใช่ความมักง่าย
    # พื้น 220 ไม่ใช่ 260: วัดจริงทั้งสี่สินทรัพย์ได้ 259–275 คำ และวันที่ไม่มีข่าวเลย
    # จะหายไปอีกราว 25 คำ ⇒ พื้นที่ตั้งไว้ชิดเกินจะตีบทความดี ๆ ตกเพราะวันนั้นข่าวเงียบ
    "word_min": 220,
    "word_max": 480,
}


# ---------------------------------------------------------------- ทะเบียนนักเขียน
# `folder` คือชื่อโฟลเดอร์ที่ผู้ใช้เห็นใน output/ — เปลี่ยนได้ แต่เปลี่ยนแล้วโฟลเดอร์
# ของวันเก่ากับวันใหม่จะชื่อไม่ตรงกัน ให้เปลี่ยนพร้อมแจ้งผู้ใช้เท่านั้น
WRITERS = (
    {
        "id": "market_report",
        "pen_name": "ณธาร",
        "style": "รายงานตลาด",
        "folder": "1-ณธาร-รายงานตลาด",
        "render": render_market_report,
        "profile": STRICT_PROSE_PROFILE,
        "uses_trade_plan": False,
        "summary": "ร้อยแก้วทางการแบบสำนักข่าว สี่ช่วง หัวข้อเดียว — สไตล์ตั้งต้นของระบบ",
    },
    {
        "id": "price_structure",
        "pen_name": "กฤช",
        "style": "โครงสร้างราคา",
        "folder": "2-กฤช-โครงสร้างราคา",
        "render": render_price_structure,
        "profile": PRICE_STRUCTURE_PROFILE,
        # คนเดียวที่ได้ตัวเลขจุดเข้า/จุดตัดขาดทุน/อัตราส่วน (คำสั่งผู้ใช้ 2026-08-04)
        "uses_trade_plan": True,
        "summary": "รายงานนักวิเคราะห์ หัวข้อย่อยเลขกำกับ ป้ายตัวหนา รายการโซน "
                   "มีจุดเข้า จุดตัดขาดทุน และอัตราส่วนผลตอบแทน ปิดด้วยสรุปเป็นข้อ",
    },
    {
        "id": "market_tempo",
        "pen_name": "ปุณณ์",
        "style": "จังหวะตลาด",
        "folder": "3-ปุณณ์-จังหวะตลาด",
        "render": render_market_tempo,
        "profile": TEMPO_PROFILE,
        "uses_trade_plan": False,
        "summary": "ประโยคสั้น เปิดด้วยโมเมนตัมและความผันผวน ปิดด้วยรายการสิ่งที่ต้องจับตา",
    },
)


def by_id(writer_id: str) -> dict:
    for writer in WRITERS:
        if writer["id"] == writer_id:
            return writer
    raise KeyError(f"ไม่รู้จักนักเขียน '{writer_id}' — มีให้เลือก "
                   f"{', '.join(item['id'] for item in WRITERS)}")
