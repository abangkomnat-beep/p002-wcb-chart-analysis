"""ตัวเขียนบท Style K — ประกอบบท 6 ส่วนจากหลักฐานที่ถูก freeze แล้วเท่านั้น

**ตัวเขียนไม่ตีความเพิ่ม** ทุกประโยคที่มีตัวเลข ทิศทาง หรือเงื่อนไข ต้องผูกกลับไปที่
`evidence_id` ได้ · sidecar `article.json` เก็บ mapping นั้นไว้ให้ด่านตรวจเดินตามได้จริง
ไม่ใช่เชื่อคำอ้าง

ทำไมไม่ให้โมเดลภาษาเขียนอิสระแล้วค่อยตรวจ: บทที่เขียนอิสระจะกลืนตัวเลขที่ไม่มีหลักฐาน
เข้าไปในประโยคสวย ๆ แล้วด่านต้องมาไล่จับทีหลัง · ที่นี่กลับด้าน — ประโยคถูกประกอบจาก
หลักฐาน ตัวเลขจึงเข้ามาไม่ได้ถ้าไม่มีที่มา (Agent 08 ขัดสำนวนทีหลังได้ แต่ห้ามแตะตัวเลข)

ศัพท์เทคนิคทุกคำที่โผล่ครั้งแรกต้องมีวงเล็บอธิบายว่า "คืออะไร" — ดู `GLOSS`
"""

from __future__ import annotations

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

# คำอธิบายครั้งแรกที่ใช้ศัพท์ — (ศัพท์, ความหมาย) ประกอบเป็นประโยคเต็ม ไม่ใช่วงเล็บห้อยท้าย
#
# เคยเขียนเป็นวงเล็บต่อท้ายประโยคแล้วอ่านแล้วขาด เพราะคำอธิบายไปลอยอยู่หลังตัวเลข
# โดยไม่มีอะไรเชื่อม ⇒ ประกอบเป็นประโยค "…ในที่นี้หมายถึง…" แทน
GLOSS = {
    "swing": ("จุดกลับตัว", "จุดที่ราคาเคยหยุดแล้วเปลี่ยนทิศ ใช้เป็นหมุดวัดโครงสร้าง"),
    "bos": ("การทะลุโครงสร้าง", "การที่ราคาปิดพ้นยอดหรือฐานเดิมที่ยืนยันแล้ว"),
    "equal": ("ระดับที่เท่ากัน", "ยอดหรือฐานสองจุดที่ราคาใกล้เคียงกันมาก "
                                "ซึ่งมักมีคำสั่งหยุดขาดทุนกองอยู่"),
    "sweep": ("การกวาดสภาพคล่อง", "การที่ราคาแทงพ้นระดับเดิมชั่วคราวแล้วถูกดันกลับ"),
    "zone": ("โซนอุปสงค์–อุปทาน", "ช่วงราคาที่เคยมีแรงซื้อหรือแรงขายเข้ามาชัดเจน"),
    # ตัวย่ออังกฤษไปอยู่ท้ายคำอธิบาย ไม่ใช่ในวงเล็บกลางประโยค — วงเล็บชนคำไทยแล้วอ่านสะดุด
    "rsi": ("ดัชนีแรงสัมพัทธ์", "ตัววัดว่าราคาขึ้นแรงหรือลงแรงเกินปกติแค่ไหนในรอบ 14 วัน "
                               "ซึ่งภาษาอังกฤษเรียกว่า RSI"),
    "atr": ("ช่วงแกว่งเฉลี่ย", "ระยะที่ราคาขยับต่อวันโดยเฉลี่ย ใช้บอกความผันผวน "
                              "ซึ่งภาษาอังกฤษเรียกว่า ATR"),
    "fib": ("ระดับย่อตัวฟีโบนักชี", "สัดส่วนที่ราคามักพักตัวหลังวิ่งเป็นช่วงยาว"),
}

REGIME_TEXT = {
    sel.REGIME_TREND: "ตลาดอยู่ในช่วงมีทิศทางชัด",
    sel.REGIME_EXPANSION: "ตลาดอยู่ในช่วงที่ความผันผวนกำลังขยายตัว",
    sel.REGIME_COMPRESSION: "ตลาดอยู่ในช่วงที่ช่วงแกว่งบีบแคบกว่าปกติ",
    sel.REGIME_RANGE: "ตลาดอยู่ในช่วงแกว่งออกข้าง",
    sel.REGIME_TRANSITION: "ตลาดอยู่ในช่วงเปลี่ยนผ่าน",
}

BIAS_TEXT = {"bullish": "ฝั่งขึ้น", "bearish": "ฝั่งลง", "neutral": "ยังไม่เลือกข้าง"}


class ArticleUnbuildable(RuntimeError):
    """เขียนบทไม่ได้ตามหลักฐานที่มี — เป็นผลลัพธ์ที่ถูกต้อง ไม่ใช่ความล้มเหลว"""


def _fmt(value: float, instrument: str) -> str:
    return voice_rules.format_price(value, instrument)


def _gloss_once(used: set, key: str) -> str:
    """คืนประโยคอธิบายเฉพาะครั้งแรกที่ศัพท์นั้นถูกใช้ในบทเดียวกัน"""
    if key in used:
        return ""
    used.add(key)
    term, meaning = GLOSS[key]
    return f" · {term}ในที่นี้หมายถึง{meaning}"


def _evidence_sentence(unit: dict, instrument: str, used: set,
                       refs: list[dict]) -> str:
    """หนึ่งหลักฐาน = หนึ่งประโยคที่บอก 'เห็นอะไร' แล้วต่อด้วย 'แปลว่าอะไร'"""
    observation = unit["observation"]
    kind = observation.get("type", "")
    text = unit["interpretation"]

    if kind in {"higher_high_higher_low", "lower_high_lower_low", "mixed_structure"}:
        high = unit["level_refs"][0]["price"]
        low = unit["level_refs"][1]["price"]
        refs.append({"value": _fmt(high, instrument), "evidence_id": unit["evidence_id"],
                     "role": "ยอดล่าสุด"})
        refs.append({"value": _fmt(low, instrument), "evidence_id": unit["evidence_id"],
                     "role": "ฐานล่าสุด"})
        gloss = _gloss_once(used, "swing")
        return (f"{text} โดยยอดล่าสุดอยู่ที่ {_fmt(high, instrument)} "
                f"และฐานล่าสุดอยู่ที่ {_fmt(low, instrument)}{gloss}")

    if kind == "break_of_structure":
        level = observation["level"]
        refs.append({"value": _fmt(level, instrument), "evidence_id": unit["evidence_id"],
                     "role": "ระดับที่ถูกทะลุ"})
        return f"{text} ที่ระดับ {_fmt(level, instrument)}{_gloss_once(used, 'bos')}"

    if kind in {"equal_highs", "equal_lows"}:
        price = unit["level_refs"][0]["price"]
        refs.append({"value": _fmt(price, instrument), "evidence_id": unit["evidence_id"],
                     "role": "ระดับที่เท่ากัน"})
        return f"{text} บริเวณ {_fmt(price, instrument)}{_gloss_once(used, 'equal')}"

    if kind == "liquidity_sweep":
        level = observation["level"]
        refs.append({"value": _fmt(level, instrument), "evidence_id": unit["evidence_id"],
                     "role": "ระดับที่ถูกกวาด"})
        return f"{text} ที่ระดับ {_fmt(level, instrument)}{_gloss_once(used, 'sweep')}"

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
                f"และ{state}{_gloss_once(used, 'zone')}")

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
        return f"{text} ที่ค่า {value:.1f}{_gloss_once(used, 'rsi')}"

    if kind == "atr_percentile":
        percent = observation["percentile"] * 100
        refs.append({"value": f"{percent:.0f}", "evidence_id": unit["evidence_id"],
                     "role": "เปอร์เซ็นไทล์ความผันผวน"})
        return (f"{text} อยู่ที่เปอร์เซ็นไทล์ที่ {percent:.0f} ของประวัติที่มี"
                f"{_gloss_once(used, 'atr')}")

    if kind == "fib_retracement":
        nearest = observation["nearest"]
        refs.append({"value": _fmt(nearest["price"], instrument),
                     "evidence_id": unit["evidence_id"], "role": "ระดับย่อตัวที่ใกล้ราคาที่สุด"})
        return (f"{text} ระดับที่ใกล้ราคาปัจจุบันที่สุดอยู่ที่ "
                f"{_fmt(nearest['price'], instrument)}{_gloss_once(used, 'fib')}")

    return text


def build_article(*, record: dict, selection: dict, manifest: dict, config: dict,
                  entry: dict) -> tuple[str, dict]:
    """คืน (markdown, sidecar) — โยน `ArticleUnbuildable` เมื่อไม่มี scenario ให้เขียน"""
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

    used: set = set()
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
        atr_text = (f" ช่วงแกว่งเฉลี่ยต่อวันอยู่ที่ราว {_fmt(atr_value, instrument)} จุด "
                    f"ซึ่งเป็นกรอบระยะที่ควรใช้ตั้งความคาดหวังของรอบถัดไป"
                    f"{_gloss_once(used, 'atr')}")
    lines.append(f"## {SECTIONS[0]}")
    lines.append(
        f"{display} ปิดรอบวันที่ {record['session_date']} ที่ {_fmt(reference, instrument)} "
        f"{REGIME_TEXT[selection['regime']]} และหลักฐานที่หนักที่สุดในกราฟตอนนี้เอียงไป"
        f"{BIAS_TEXT[selection['bias']]}{atr_text}"
    )

    # 2 เรื่องที่กราฟกำลังบอก — เล่าเป็นเรื่อง ไม่ใช่ลิสต์เทคนิค
    lines.append(f"\n## {SECTIONS[1]}")
    lines.append(
        f"สิ่งที่ทำให้ภาพรวมเอียงไปทางนี้คือ{_evidence_sentence(primary, instrument, used, refs)} "
        f"เหตุผลที่หลักฐานชิ้นนี้ถูกยกเป็นตัวหลักของวันคือมันตรงกับสภาวะตลาดที่วัดได้มากที่สุด "
        f"ไม่ใช่เพราะเป็นเครื่องมือที่ซับซ้อนที่สุด"
    )
    if conflicting:
        lines.append(
            f"ขณะเดียวกันมีหลักฐานที่เดินสวนทางอยู่ด้วย คือ"
            f"{_evidence_sentence(conflicting[0], instrument, used, refs)} "
            f"จุดนี้ทำให้ภาพยังไม่ใช่ทางเดียวชัดเจน และเป็นเหตุผลที่ต้องมีเงื่อนไขยืนยันก่อนเชื่อทิศทาง"
        )

    # 3 หลักฐานสำคัญ
    lines.append(f"\n## {SECTIONS[2]}")
    for unit in supporting:
        lines.append(f"- {_evidence_sentence(unit, instrument, used, refs)}")
    unavailable = record["unavailable_groups"]
    if unavailable:
        names = ", ".join(str(group) for group in unavailable)
        lines.append(
            f"- ข้อมูลที่ไม่มีในรอบนี้: กลุ่มเทคนิคหมายเลข {names} ใช้ไม่ได้เพราะไม่มีข้อมูลรองรับ "
            f"บทนี้จึงไม่อ้างอิงถึงมันเลย"
        )

    # 4 สถานการณ์ A/B
    lines.append(f"\n## {SECTIONS[3]}")
    for scenario in (scenario_a, scenario_b):
        confirm = scenario["confirmation_rule"]
        label = "สถานการณ์ A" if scenario["scenario_id"] == "A" else "สถานการณ์ B"
        side = "เหนือ" if confirm["comparison"] == "gt" else "ใต้"
        refs.append({"value": _fmt(confirm["level"], instrument),
                     "evidence_id": confirm["level_evidence_id"],
                     "role": f"ระดับยืนยันของ{label}"})
        lines.append(
            f"- **{label} ({BIAS_TEXT[scenario['bias']]}):** ถ้าราคาปิดรายวัน{side}ระดับ "
            f"{_fmt(confirm['level'], instrument)} ซึ่งเป็น{confirm['level_label']} "
            f"ถือว่าเงื่อนไขของสถานการณ์นี้ถูกยืนยัน"
        )
    lines.append(
        "สถานการณ์ B ไม่ใช่ทางที่ผิด แต่เป็นทางสำรองที่ยังไม่ถูกเรียกใช้ "
        "ถ้าเงื่อนไขของมันไม่เกิดขึ้น ก็ไม่ได้แปลว่าการอ่านกราฟผิด"
    )

    # 5 สัญญาณที่บอกว่ามุมมองนี้ไม่เป็นไปตามคาด
    invalidate = scenario_a["invalidation_rule"]
    side = "ใต้" if invalidate["comparison"] == "lt" else "เหนือ"
    refs.append({"value": _fmt(invalidate["level"], instrument),
                 "evidence_id": invalidate["level_evidence_id"], "role": "ระดับที่หักล้างมุมมองหลัก"})
    lines.append(f"\n## {SECTIONS[4]}")
    lines.append(
        f"ถ้าราคาปิดรายวัน{side}ระดับ {_fmt(invalidate['level'], instrument)} "
        f"ซึ่งเป็น{invalidate['level_label']} ให้ถือว่ามุมมองหลักของวันนี้ไม่เป็นไปตามคาด "
        f"และควรกลับไปอ่านกราฟใหม่ตั้งแต่ต้น ไม่ใช่ถือมุมมองเดิมแล้วรอให้ราคากลับมาหา "
        f"ระดับนี้ถูกเลือกเพราะมีหลักฐานรองรับ ไม่ใช่เพราะเป็นตัวเลขกลม"
    )

    # 6 สิ่งที่ต้องจับตาในรอบถัดไป
    lines.append(f"\n## {SECTIONS[5]}")
    watch = [f"ระดับ {_fmt(scenario_a['confirmation_rule']['level'], instrument)} "
             f"ว่าจะมีแท่งปิดพ้นไปได้จริงหรือแค่แทะแล้วถอย",
             f"ระดับ {_fmt(invalidate['level'], instrument)} ว่ายังยืนอยู่หรือถูกทะลุ"]
    if volatility and volatility["observation"]["state"] != "normal":
        watch.append("การเปลี่ยนของช่วงแกว่ง เพราะช่วงที่บีบแคบมักตามด้วยการขยายตัวแรง "
                     "แต่ตัวมันเองไม่ได้บอกว่าจะออกทางไหน")
    lines.append(
        "สิ่งที่ควรจับตาในรอบถัดไปคือ" + " ถัดมาคือ".join(watch) +
        " การรอให้เงื่อนไขเกิดก่อนจึงค่อยตัดสินใจ ทำให้ไม่ต้องเดาทิศทางล่วงหน้า"
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
