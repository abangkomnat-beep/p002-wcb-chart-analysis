"""ตัวเขียนบท Style K — ประกอบบท 6 ส่วนจากหลักฐานที่ถูก freeze แล้วเท่านั้น

**ตัวเขียนไม่ตีความเพิ่ม** ทุกประโยคที่มีตัวเลข ทิศทาง หรือเงื่อนไข ต้องผูกกลับไปที่
`evidence_id` ได้ · sidecar `article.json` เก็บ mapping นั้นไว้ให้ด่านตรวจเดินตามได้จริง
ไม่ใช่เชื่อคำอ้าง

ทำไมไม่ให้โมเดลภาษาเขียนอิสระแล้วค่อยตรวจ: บทที่เขียนอิสระจะกลืนตัวเลขที่ไม่มีหลักฐาน
เข้าไปในประโยคสวย ๆ แล้วด่านต้องมาไล่จับทีหลัง · ที่นี่กลับด้าน — ประโยคถูกประกอบจาก
หลักฐาน ตัวเลขจึงเข้ามาไม่ได้ถ้าไม่มีที่มา (Agent 08 ขัดสำนวนทีหลังได้ แต่ห้ามแตะตัวเลข)

มติผู้ใช้ 08-14: บทไม่อธิบายศัพท์ — ใช้ศัพท์ไทยตรง ๆ ห้ามมีประโยคขยาย
"…ในที่นี้หมายถึง…" / "…คือ…" (กลไก GLOSS เดิมถูกถอดออกแล้ว)
"""

from __future__ import annotations

import re

from tools import style_k_selector as sel
from tools import voice_rules

SECTIONS = [
    "ภาพตลาดตอนนี้",
    "เรื่องที่กราฟกำลังบอก",
    "หลักฐานสำคัญ",
    "สถานการณ์ A และ B",
    "สัญญาณที่บอกว่ามุมมองนี้ไม่เป็นไปตามคาด",
    "สิ่งที่ต้องจับตาในรอบถัดไป",
]

# กลไกอธิบายศัพท์ (GLOSS/_gloss_once) ถูกถอด 08-14 ตามมติผู้ใช้ — Style K ไม่อธิบายคำ
# ประโยคขยาย "…ในที่นี้หมายถึง…" / "…คือ…" ห้ามโผล่ในบท ใช้ศัพท์ไทยตรง ๆ โดยไม่ขยายความ

REGIME_TEXT = {
    sel.REGIME_TREND: "ตลาดอยู่ในช่วงมีทิศทางชัด",
    sel.REGIME_EXPANSION: "ตลาดอยู่ในช่วงที่ความผันผวนกำลังขยายตัว",
    sel.REGIME_COMPRESSION: "ตลาดอยู่ในช่วงที่ช่วงแกว่งบีบแคบกว่าปกติ",
    sel.REGIME_RANGE: "ตลาดอยู่ในช่วงแกว่งออกข้าง",
    sel.REGIME_TRANSITION: "ตลาดอยู่ในช่วงเปลี่ยนผ่าน",
}

BIAS_TEXT = {"bullish": "ฝั่งขึ้น", "bearish": "ฝั่งลง", "neutral": "ยังไม่เลือกข้าง"}

# ชื่อกลุ่มเทคนิคฉบับผู้อ่าน — เลขทะเบียนภายใน (GROUP_NAMES ใน style_k_techniques)
# ห้ามโผล่ในบท เพราะผู้อ่านไม่มีทางรู้ว่าเลขไหนคืออะไร (มติผู้ใช้ B-20260813-K · K-L-01)
GROUP_NAMES_TH = {
    1: "โครงสร้างราคา",
    2: "การอ่านสภาพคล่อง",
    3: "โซนแรงซื้อแรงขาย",
    4: "แนวโน้มและแรงส่ง",
    5: "การวัดความผันผวน",
    6: "ปริมาณการซื้อขาย",
    7: "ระดับฟีโบนักชี",
    8: "การเทียบหลายกรอบเวลา",
}

_THAI_COUNT = {1: "มุมนี้", 2: "สองมุมนี้", 3: "สามมุมนี้", 4: "สี่มุมนี้",
               5: "ห้ามุมนี้", 6: "หกมุมนี้", 7: "เจ็ดมุมนี้", 8: "แปดมุมนี้"}

# ตารางแทนคำที่ผู้ใช้อนุมัติ (calibration B-20260813-K) สำหรับข้อความ interpretation
# ที่ฝังอยู่ใน analysis records ซึ่ง freeze ด้วย hash ไปแล้ว — แก้ record ตรง ๆ ไม่ได้
# เพราะจะทำลายการตรึงแบบ walk-forward · ต้นทาง (style_k_techniques) แก้แล้ว
# records ที่สร้างหลังจากนี้จึงไม่เข้าเงื่อนไขแทนคำอีก
APPROVED_REWORDINGS = [
    ("มักเป็นบริเวณที่คำสั่งหยุดขาดทุนไปกอง",
     "มักเป็นบริเวณที่คำสั่งหยุดขาดทุนกระจุกตัวอยู่"),
    ("โซนที่ราคาเคยถูกขายลงมา ยังอยู่เหนือราคาปัจจุบัน",
     "โซนที่เคยมีแรงขายกดราคาลงมา ซึ่งยังอยู่เหนือราคาปัจจุบัน"),
]


class ArticleUnbuildable(RuntimeError):
    """เขียนบทไม่ได้ตามหลักฐานที่มี — เป็นผลลัพธ์ที่ถูกต้อง ไม่ใช่ความล้มเหลว"""


def _fmt(value: float, instrument: str) -> str:
    return voice_rules.format_price(value, instrument)


def _evidence_sentence(unit: dict, instrument: str,
                       refs: list[dict]) -> str:
    """หนึ่งหลักฐาน = หนึ่งประโยคที่บอก 'เห็นอะไร' แล้วต่อด้วย 'แปลว่าอะไร'"""
    observation = unit["observation"]
    kind = observation.get("type", "")
    text = unit["interpretation"]
    for before, after in APPROVED_REWORDINGS:
        text = text.replace(before, after)

    if kind in {"higher_high_higher_low", "lower_high_lower_low", "mixed_structure"}:
        high = unit["level_refs"][0]["price"]
        low = unit["level_refs"][1]["price"]
        refs.append({"value": _fmt(high, instrument), "evidence_id": unit["evidence_id"],
                     "role": "ยอดล่าสุด"})
        refs.append({"value": _fmt(low, instrument), "evidence_id": unit["evidence_id"],
                     "role": "ฐานล่าสุด"})
        return (f"{text} โดยยอดล่าสุดอยู่ที่ {_fmt(high, instrument)} "
                f"และฐานล่าสุดอยู่ที่ {_fmt(low, instrument)}")

    if kind == "break_of_structure":
        level = observation["level"]
        refs.append({"value": _fmt(level, instrument), "evidence_id": unit["evidence_id"],
                     "role": "ระดับที่ถูกทะลุ"})
        return f"{text} ที่ระดับ {_fmt(level, instrument)}"

    if kind in {"equal_highs", "equal_lows"}:
        price = unit["level_refs"][0]["price"]
        refs.append({"value": _fmt(price, instrument), "evidence_id": unit["evidence_id"],
                     "role": "ระดับที่เท่ากัน"})
        return f"{text} บริเวณ {_fmt(price, instrument)}"

    if kind == "liquidity_sweep":
        level = observation["level"]
        refs.append({"value": _fmt(level, instrument), "evidence_id": unit["evidence_id"],
                     "role": "ระดับที่ถูกกวาด"})
        return f"{text} ที่ระดับ {_fmt(level, instrument)}"

    if kind.endswith("_zone"):
        lower, upper = observation["lower"], observation["upper"]
        refs.append({"value": _fmt(lower, instrument), "evidence_id": unit["evidence_id"],
                     "role": "ขอบล่างโซน"})
        refs.append({"value": _fmt(upper, instrument), "evidence_id": unit["evidence_id"],
                     "role": "ขอบบนโซน"})
        state = "ยังไม่เคยถูกทดสอบซ้ำ" if observation["touch_count"] == 0 \
            else f"ถูกทดสอบซ้ำมาแล้ว {observation['touch_count']} ครั้ง"
        refs.append({"value": str(observation["touch_count"]),
                     "evidence_id": unit["evidence_id"], "role": "จำนวนครั้งที่ถูกทดสอบ"})
        return (f"{text} ช่วง {_fmt(lower, instrument)}–{_fmt(upper, instrument)} "
                f"และ{state}")

    if kind == "price_vs_moving_averages":
        ma20, ma50 = observation["ma20"], observation["ma50"]
        refs.append({"value": _fmt(ma20, instrument), "evidence_id": unit["evidence_id"],
                     "role": "เส้นค่าเฉลี่ย 20 วัน"})
        refs.append({"value": _fmt(ma50, instrument), "evidence_id": unit["evidence_id"],
                     "role": "เส้นค่าเฉลี่ย 50 วัน"})
        return (f"{text} เส้นค่าเฉลี่ย 20 วันอยู่ที่ {_fmt(ma20, instrument)} "
                f"และเส้น 50 วันอยู่ที่ {_fmt(ma50, instrument)}")

    if kind == "rsi14":
        value = observation["value"]
        refs.append({"value": f"{value:.1f}", "evidence_id": unit["evidence_id"], "role": "ค่า RSI"})
        return f"{text} ที่ค่า {value:.1f}"

    if kind == "atr_percentile":
        percent = observation["percentile"] * 100
        refs.append({"value": f"{percent:.0f}", "evidence_id": unit["evidence_id"],
                     "role": "เปอร์เซ็นไทล์ความผันผวน"})
        return f"{text} อยู่ที่เปอร์เซ็นไทล์ที่ {percent:.0f} ของประวัติที่มี"

    if kind == "fib_retracement":
        nearest = observation["nearest"]
        refs.append({"value": _fmt(nearest["price"], instrument),
                     "evidence_id": unit["evidence_id"], "role": "ระดับย่อตัวที่ใกล้ราคาที่สุด"})
        return (f"{text} ระดับที่ใกล้ราคาปัจจุบันที่สุดอยู่ที่ "
                f"{_fmt(nearest['price'], instrument)}")

    return text


# JL-202: ระดับที่ห่างราคาปิดต่ำกว่านี้ (เท่าของ ATR) ถือว่าอยู่ในระยะแกว่งปกติ
# ต้องมีคำเตือนกำกับ — คำว่า "ยืนยัน" บนระดับระยะ noise ให้ข้อมูลน้อยกว่าที่เสียง
NOISE_DISTANCE_ATR = 0.25

# JL-204: ระดับจากคนละ family ที่ห่างกันไม่เกินสัดส่วนนี้ของ ATR ถือเป็น confluence
CONFLUENCE_DISTANCE_ATR = 0.1


# ลำดับลดทอนเมื่อบทเกินงบคำ (เพดาน 560 เป็นข้อจำกัดจากแผนที่อนุมัติแล้ว):
# full → compact (ตัดระยะแบบไม่มีคำเตือน) → minimal (ตัด confluence ด้วย)
# คำเตือนระยะ noise (JL-202) และที่มาของระดับ (JL-201) ไม่ถูกตัดในทุกโหมด —
# สองอย่างนี้คือการเปิดเผยความเสี่ยง ส่วนที่ตัดยังอยู่ครบใน scenarios.json/sidecar
EXTRAS_MODES = ("full", "compact", "minimal")


def _rule_extras(rule: dict, *, record: dict, narrated: set, atr_unit: dict | None,
                 instrument: str, refs: list[dict], scenario_label: str,
                 mode: str = "full") -> str:
    """ประโยคขยายของระดับใน scenario ตามใบสั่ง Agent 07 (JL-201/202/204)

    ทำงานจากของที่อยู่ใน record ล้วน ๆ จึงใช้กับ analysis records ที่ freeze แล้วได้
    โดยไม่แตะ manifest — ระยะและ confluence คำนวณซ้ำได้เสมอจากหลักฐานเดิม
    """
    parts: list[str] = []
    level = rule["level"]
    by_id = {unit["evidence_id"]: unit for unit in record["evidence"]}

    # JL-202 — ระยะถึงระดับเป็นสัดส่วนของช่วงแกว่งเฉลี่ย + คำเตือนเมื่ออยู่ในระยะ noise
    if atr_unit is not None:
        atr = atr_unit["observation"]["atr14"]
        distance = abs(level - record["reference_price"]) / atr
        shown = f"{distance:.1f}" if distance >= 0.05 else "0.1"
        refs.append({"value": shown, "evidence_id": atr_unit["evidence_id"],
                     "role": f"ระยะถึงระดับของ{scenario_label} (เท่าของช่วงแกว่งเฉลี่ย)"})
        if distance < NOISE_DISTANCE_ATR:
            prefix = "ห่างเพียง" if distance >= 0.05 else "ห่างไม่ถึง"
            parts.append(f"ระดับนี้{prefix} {shown} เท่าของช่วงแกว่งเฉลี่ย "
                         f"การแกว่งปกติวันเดียวก็ปิดข้ามได้")
        elif mode == "full":
            parts.append(f"ระดับนี้ห่างราว {shown} เท่าของช่วงแกว่งเฉลี่ย")

    # JL-201 — ระดับที่มาจากหลักฐานนอกชุดที่บทเล่า ต้องบอกผู้อ่าน ไม่ใช่แค่ manifest
    source = by_id.get(rule["level_evidence_id"])
    if source is not None and source["evidence_id"] not in narrated:
        story = source["interpretation"]
        for before, after in APPROVED_REWORDINGS:
            story = story.replace(before, after)
        observation = source["observation"]
        span = ""
        if "lower" in observation and "upper" in observation:
            lower = _fmt(observation["lower"], instrument)
            upper = _fmt(observation["upper"], instrument)
            refs.append({"value": lower, "evidence_id": source["evidence_id"],
                         "role": "ขอบล่างของหลักฐานที่มาของระดับ"})
            refs.append({"value": upper, "evidence_id": source["evidence_id"],
                         "role": "ขอบบนของหลักฐานที่มาของระดับ"})
            span = f" ช่วง {lower}–{upper}"
        parts.append(f"และมาจาก{story}{span} ซึ่งบทไม่ได้เล่าข้างต้น")

    # JL-204 — confluence ที่ผู้อ่านมองไม่เห็นต้องถูกเล่า: ระดับจากคนละ family ภายใน
    # 0.1 ATR **ของหลักฐานที่บทไม่ได้เล่า** — คู่ทับที่เล่าอยู่แล้วผู้อ่านเห็นเองได้
    # การเล่าซ้ำมีแต่เปลืองงบคำ (เพดาน 560)
    if atr_unit is not None and mode != "minimal":
        atr = atr_unit["observation"]["atr14"]
        base_family = source["independence_family"] if source else None
        best = None
        for unit in record["evidence"]:
            if unit["quality"] == "unavailable" or unit["evidence_id"] in narrated:
                continue
            if unit["independence_family"] == base_family:
                continue
            for ref in unit.get("level_refs") or []:
                price = ref.get("price")
                if price is None:
                    continue
                gap = abs(float(price) - level)
                if gap <= CONFLUENCE_DISTANCE_ATR * atr and (best is None or gap < best[0]):
                    best = (gap, ref.get("label", ""), float(price), unit["evidence_id"])
        if best is not None:
            _, label, price, evidence_id = best
            shown_price = _fmt(price, instrument)
            refs.append({"value": shown_price, "evidence_id": evidence_id,
                         "role": f"ระดับ confluence ของ{scenario_label}"})
            for number in _label_numbers(label):
                refs.append({"value": number, "evidence_id": evidence_id,
                             "role": f"ตัวเลขในชื่อระดับ confluence ของ{scenario_label}"})
            parts.append(f"และยังทับกับ{label} ที่ {shown_price}")

    return (" " + " ".join(parts)) if parts else ""


def _label_numbers(label: str) -> list[str]:
    return re.findall(r"\d[\d,\.]*\d|\d", label)


def build_article(*, record: dict, selection: dict, manifest: dict, config: dict,
                  entry: dict) -> tuple[str, dict]:
    """คืน (markdown, sidecar) — โยน `ArticleUnbuildable` เมื่อไม่มี scenario ให้เขียน

    ไล่โหมด extras จาก full → minimal จนกว่าจะเข้าเพดานคำ (ดูคำอธิบาย `EXTRAS_MODES`) —
    วันที่หลักฐานแน่นจนบทเต็มเกินงบ การตัดต้องเป็นลำดับที่ประกาศไว้ ไม่ใช่บทพังเงียบ
    """
    word_max = config["article"]["word_max"]
    for mode in EXTRAS_MODES:
        markdown, sidecar = _compose_article(record=record, selection=selection,
                                             manifest=manifest, config=config,
                                             entry=entry, extras_mode=mode)
        if sidecar["word_count"] <= word_max:
            break
    sidecar["extras_mode"] = mode
    return markdown, sidecar


def _compose_article(*, record: dict, selection: dict, manifest: dict, config: dict,
                     entry: dict, extras_mode: str = "full") -> tuple[str, dict]:
    if selection["decision"] != sel.DECISION_ARTICLE or not manifest["scenarios"]:
        raise ArticleUnbuildable(manifest.get("no_trade_reason") or "ไม่มีสถานการณ์ให้เขียน")

    asset = record["asset"]
    asset_config = config["assets"][asset]
    instrument = asset_config["instrument_type"]
    display = asset_config["display"]
    reference = record["reference_price"]
    by_id = {unit["evidence_id"]: unit for unit in record["evidence"]}

    primary = by_id[selection["primary_evidence_id"]]
    supporting = [by_id[key] for key in selection["supporting_evidence_ids"]]
    conflicting = [by_id[key] for key in selection["conflicting_evidence_ids"]]
    scenario_a, scenario_b = manifest["scenarios"][0], manifest["scenarios"][1]

    refs: list[dict] = [{"value": _fmt(reference, instrument), "evidence_id": "reference_price",
                         "role": "ราคาปิดของวันที่วิเคราะห์"}]
    lines: list[str] = []

    # 1 ภาพตลาดตอนนี้ — เปิดด้วยผลต่อราคา ไม่ใช่ชื่อเทคนิค
    volatility = next((unit for unit in record["evidence"]
                       if unit["observation"].get("type") == "atr_percentile"), None)
    atr_text = ""
    if volatility:
        atr_value = volatility["observation"]["atr14"]
        refs.append({"value": _fmt(atr_value, instrument),
                     "evidence_id": volatility["evidence_id"], "role": "ช่วงแกว่งเฉลี่ยต่อวัน"})
        # วลี "กรอบระยะที่ควรใช้ตั้งความคาดหวัง" ถูกถอด 08-14 — ซ้ำซ้อนตั้งแต่ทุกระดับ
        # ใน scenario บอกระยะของตัวเองเป็นสัดส่วน ATR แล้ว (JL-202) และงบคำมีเพดาน 560
        atr_text = f" ช่วงแกว่งเฉลี่ยต่อวันอยู่ที่ราว {_fmt(atr_value, instrument)} จุด"
    lines.append(f"## {SECTIONS[0]}")
    lines.append(
        f"{display} ปิดรอบวันที่ {record['session_date']} ที่ {_fmt(reference, instrument)} "
        f"{REGIME_TEXT[selection['regime']]} และหลักฐานที่มีน้ำหนักมากที่สุดในกราฟตอนนี้เอียงไป"
        f"{BIAS_TEXT[selection['bias']]}{atr_text}"
    )

    # 2 เรื่องที่กราฟกำลังบอก — เล่าเป็นเรื่อง ไม่ใช่ลิสต์เทคนิค
    lines.append(f"\n## {SECTIONS[1]}")
    lines.append(
        f"สิ่งที่ทำให้ภาพรวมเอียงไปทางนี้คือ{_evidence_sentence(primary, instrument, refs)} "
        f"เหตุผลที่หลักฐานชิ้นนี้ถูกยกเป็นตัวหลักของวันคือหลักฐานนี้ตรงกับสภาวะตลาดที่วัดได้มากที่สุด "
        f"ไม่ใช่เพราะเป็นเครื่องมือที่ซับซ้อนที่สุด"
    )
    if conflicting:
        lines.append(
            f"ขณะเดียวกันมีหลักฐานที่เดินสวนทางอยู่ด้วย คือ"
            f"{_evidence_sentence(conflicting[0], instrument, refs)} "
            f"จุดนี้ทำให้ภาพยังไม่ใช่ทางเดียวชัดเจน และเป็นเหตุผลที่ต้องมีเงื่อนไขยืนยันก่อนเชื่อทิศทาง"
        )

    # 3 หลักฐานสำคัญ
    lines.append(f"\n## {SECTIONS[2]}")
    for unit in supporting:
        lines.append(f"- {_evidence_sentence(unit, instrument, refs)}")
    unavailable = record["unavailable_groups"]
    if unavailable:
        thai_names = [GROUP_NAMES_TH[group] for group in unavailable]
        if len(thai_names) == 1:
            names = thai_names[0]
        elif len(thai_names) == 2:
            names = f"{thai_names[0]}และ{thai_names[1]}"
        else:
            names = f"{' '.join(thai_names[:-1])} และ{thai_names[-1]}"
        count_word = _THAI_COUNT.get(len(thai_names), "มุมเหล่านี้")
        lines.append(
            f"- ข้อมูลที่ไม่มีในรอบนี้: {names}ใช้ไม่ได้เพราะไม่มีข้อมูลรองรับ "
            f"บทนี้จึงไม่นำ{count_word}มาใช้เลย"
        )

    # 4 สถานการณ์ A/B — แต่ละระดับพ่วงระยะ/ที่มา/confluence ตามใบสั่ง Agent 07
    narrated = {selection["primary_evidence_id"], *selection["supporting_evidence_ids"],
                *selection["conflicting_evidence_ids"]}
    extras_done_levels: set = set()
    lines.append(f"\n## {SECTIONS[3]}")
    for scenario in (scenario_a, scenario_b):
        confirm = scenario["confirmation_rule"]
        label = "สถานการณ์ A" if scenario["scenario_id"] == "A" else "สถานการณ์ B"
        side = "เหนือ" if confirm["comparison"] == "gt" else "ใต้"
        refs.append({"value": _fmt(confirm["level"], instrument),
                     "evidence_id": confirm["level_evidence_id"],
                     "role": f"ระดับยืนยันของ{label}"})
        extras = _rule_extras(confirm, record=record, narrated=narrated,
                              atr_unit=volatility, instrument=instrument,
                              refs=refs, scenario_label=label, mode=extras_mode)
        extras_done_levels.add(confirm["level"])
        lines.append(
            f"- **{label} ({BIAS_TEXT[scenario['bias']]}):** ถ้าราคาปิดรายวัน{side}ระดับ "
            f"{_fmt(confirm['level'], instrument)} ซึ่งเป็น{confirm['level_label']} "
            f"ถือว่าสถานการณ์นี้ถูกยืนยัน{extras}"
        )
    lines.append(
        "สถานการณ์ B ไม่ใช่ทางที่ผิด แต่เป็นทางสำรองที่เงื่อนไขยังมาไม่ถึง "
        "ถ้าเงื่อนไขนั้นไม่เกิดขึ้น ก็ไม่ได้แปลว่าการอ่านกราฟผิด"
    )

    # 5 สัญญาณที่บอกว่ามุมมองนี้ไม่เป็นไปตามคาด — ขยายเฉพาะระดับที่ยังไม่ถูกขยายข้างบน
    # (ตอนที่ B เป็นกระจกของ A ระดับนี้ถูกเล่าครบแล้วในบรรทัดของ B ไม่ต้องเปลืองคำซ้ำ)
    invalidate = scenario_a["invalidation_rule"]
    side = "ใต้" if invalidate["comparison"] == "lt" else "เหนือ"
    refs.append({"value": _fmt(invalidate["level"], instrument),
                 "evidence_id": invalidate["level_evidence_id"], "role": "ระดับที่หักล้างมุมมองหลัก"})
    # โหมด minimal ตัด extras ของหัวข้อนี้ทั้งก้อน — เป็นระดับที่สามที่น้ำหนักการอ่าน
    # น้อยสุด และตัวเลขทั้งหมดยังอยู่ใน scenarios.json (distance_atr) ครบ
    invalidate_extras = ""
    if invalidate["level"] not in extras_done_levels and extras_mode != "minimal":
        invalidate_extras = _rule_extras(invalidate, record=record, narrated=narrated,
                                         atr_unit=volatility, instrument=instrument,
                                         refs=refs, scenario_label="ระดับหักล้างมุมมองหลัก",
                                         mode=extras_mode)
    lines.append(f"\n## {SECTIONS[4]}")
    lines.append(
        f"ถ้าราคาปิดรายวัน{side}ระดับ {_fmt(invalidate['level'], instrument)} "
        f"ซึ่งเป็น{invalidate['level_label']} ให้ถือว่ามุมมองหลักของวันนี้ไม่เป็นไปตามคาด "
        f"และควรกลับไปอ่านกราฟใหม่ตั้งแต่ต้น ไม่ใช่ถือมุมมองเดิมแล้วรอให้ราคากลับมาหา "
        f"ระดับนี้ถูกเลือกเพราะมีหลักฐานรองรับ ไม่ใช่เพราะเป็นตัวเลขกลม{invalidate_extras}"
    )

    # 6 สิ่งที่ต้องจับตาในรอบถัดไป
    lines.append(f"\n## {SECTIONS[5]}")
    watch = [f"ระดับ {_fmt(scenario_a['confirmation_rule']['level'], instrument)} "
             f"ว่าจะมีแท่งปิดพ้นไปได้จริงหรือเพียงทดสอบแล้วถอยกลับ",
             f"ระดับ {_fmt(invalidate['level'], instrument)} ว่ายังยืนอยู่หรือถูกทะลุ"]
    if volatility and volatility["observation"]["state"] != "normal":
        watch.append("การเปลี่ยนของช่วงแกว่ง เพราะช่วงที่บีบแคบมักตามด้วยการขยายตัวแรง "
                     "แต่ตัวมันเองไม่ได้บอกว่าจะออกทางไหน")
    # ประโยคเปิดเดิม ("สิ่งที่ควรจับตาในรอบถัดไปคือ") ซ้ำกับชื่อหัวข้อ — ตัดออก 08-14
    # เพื่อคืนงบคำให้การเปิดเผยระยะ/ที่มา/confluence ตามใบสั่ง Agent 07
    lines.append(
        "อันดับแรกคือ" + " ถัดมาคือ".join(watch) +
        " การรอให้เงื่อนไขเกิดก่อนจึงค่อยตัดสินใจ"
    )

    body = "\n".join(lines) + "\n"
    front = _frontmatter(record=record, entry=entry, selection=selection,
                        asset_config=asset_config, config=config)
    markdown = front + "\n" + body

    sidecar = {
        "asset": asset,
        "session_date": record["session_date"],
        "cutoff": record["cutoff"],
        "style": "K",
        "status": config["status"],
        "author_slug": asset_config["author_slug"],
        "confidence_tier": record["confidence_tier"],
        "regime": selection["regime"],
        "bias": selection["bias"],
        "decision": selection["decision"],
        "word_count": voice_rules.count_public_words(markdown),
        "word_counter": config["article"]["word_counter"],
        "sections": SECTIONS,
        "number_refs": refs,
        "evidence_used": [selection["primary_evidence_id"],
                          *selection["supporting_evidence_ids"],
                          *selection["conflicting_evidence_ids"]],
        "unavailable_groups": record["unavailable_groups"],
        "limitations": entry["limitations"],
    }
    return markdown, sidecar


def _frontmatter(*, record, entry, selection, asset_config, config) -> str:
    return "\n".join([
        "---",
        f"title: {asset_config['display']} — อ่านกราฟรอบวันที่ {record['session_date']}",
        f"asset: {record['asset']}",
        f"author_slug: {asset_config['author_slug']}",
        "style: K",
        f"status: {config['status']}",
        "published: false",
        f"session_date: {record['session_date']}",
        f"cutoff: {record['cutoff']}",
        f"confidence_tier: {record['confidence_tier']}",
        f"regime: {selection['regime']}",
        "---",
    ]) + "\n"


def article_problems(markdown: str, sidecar: dict, *, config: dict,
                     record: dict) -> list[str]:
    """ด่านกลไกของบท — ตรวจโครง จำนวนคำ และการอ้างกลับหลักฐาน"""
    problems: list[str] = []
    limits = config["article"]

    count = voice_rules.count_public_words(markdown)
    if not limits["word_min"] <= count <= limits["word_max"]:
        problems.append(f"จำนวนคำ {count} อยู่นอกกรอบ {limits['word_min']}–{limits['word_max']}")

    position = -1
    for heading in limits["sections"]:
        found = markdown.find(f"## {heading}")
        if found < 0:
            problems.append(f"ไม่พบหัวข้อ '{heading}'")
        elif found < position:
            problems.append(f"หัวข้อ '{heading}' อยู่ผิดลำดับ")
        else:
            position = found

    ids = {unit["evidence_id"] for unit in record["evidence"]} | {"reference_price"}
    for ref in sidecar["number_refs"]:
        if ref["evidence_id"] not in ids:
            problems.append(f"ตัวเลข {ref['value']} อ้าง evidence_id ที่ไม่มี: {ref['evidence_id']}")

    by_id = {unit["evidence_id"]: unit for unit in record["evidence"]}
    for evidence_id in sidecar["evidence_used"]:
        unit = by_id.get(evidence_id)
        if unit and unit["quality"] == "unavailable":
            problems.append(f"บทอ้างเทคนิคที่ใช้ไม่ได้: {evidence_id}")

    if sidecar["author_slug"] != config["assets"][record["asset"]]["author_slug"]:
        problems.append("author_slug ไม่ตรงกับทะเบียนผู้เขียนของหัวข้อนี้")
    return problems
