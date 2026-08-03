"""ประกอบบทความสาธารณะจากหลักฐาน — ตัวเลขทุกตัวมาจาก evidence pack เท่านั้น

ลำดับที่บังคับ: สร้าง article.json (หลักฐาน) ก่อน แล้วค่อยเรนเดอร์ Markdown จากไฟล์นั้น
ทำแบบนี้ตัวเลขในบทความจะตรงกับหลักฐานโดยโครงสร้าง ไม่ต้องหวังว่าใครจะพิมพ์ตรง

โครงหัวข้อใช้ชุด v3 ตามที่ผู้ใช้เคาะเมื่อ 2026-08-03
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import levels as level_engine  # noqa: E402
from tools.chart_renderer import thai_datetime_text  # noqa: E402


CONTRACT = "WCB Daily Output Contract v3"
SCHEMA_VERSION = "3.0.0"

SECTIONS = (
    "ภาพรวมตลาด",
    "ปัจจัยขับเคลื่อน",
    "มุมมองทางเทคนิค",
    "ระดับตัดสินใจ",
    "ฉากทัศน์",
    "เหตุการณ์ที่ต้องติดตาม",
    "มุมสำหรับผู้ลงทุนไทย",
    "กราฟ",
    "ความเสี่ยง",
)

INSTRUMENT_LABEL = {
    "forex_spot": "อัตราแลกเปลี่ยนตลาดสปอต",
    "crypto_spot": "คริปโทเคอร์เรนซีตลาดสปอต",
    "spot_metal": "โลหะมีค่าตลาดสปอต",
}

# field นโยบาย/พารามิเตอร์ภายใน — ห้ามอยู่ในไฟล์ฝั่ง public ไม่ว่าชั้นไหนของ JSON
# ขยายรายการได้ที่นี่ที่เดียว: ตัวตัด (strip_internal_fields) และเทสกันหลุดซ้ำ
# (tests/test_public_output_hygiene.py) อ่านจากชุดเดียวกันนี้
PUBLIC_FIELD_DENYLIST = frozenset({
    "merge_tolerance",
    "quality_status",
    "approved_for_publication",
    "allowed_language",
    "forbidden_language",
})


def strip_internal_fields(node):
    """คืนสำเนาที่ตัด field ภายในออกทุกชั้น — ใช้กับข้อมูลที่กำลังจะเขียนฝั่ง public เท่านั้น

    ฝั่ง internal เก็บ field เหล่านี้ไว้ได้ตามเดิม เพราะมีประโยชน์ต่อการ audit
    """
    if isinstance(node, dict):
        return {key: strip_internal_fields(value)
                for key, value in node.items() if key not in PUBLIC_FIELD_DENYLIST}
    if isinstance(node, list):
        return [strip_internal_fields(item) for item in node]
    return node


def change_summary(report: dict) -> dict:
    """ค่าการเปลี่ยนแปลงที่บทความใช้ — บันทึกลง technical.evidence.json เป็นหลักฐาน

    บทความแสดง "ขนาด" ของการเปลี่ยนแปลง (ค่าสัมบูรณ์) คู่กับคำบอกทิศ เพิ่มขึ้น/ลดลง
    จึงต้องบันทึกทั้งค่าจริงที่มีเครื่องหมายและขนาดที่แสดงจริง ไม่อย่างนั้นวันที่ราคาลง
    validator จะหาตัวเลขในบทความไม่เจอในหลักฐาน (number_without_evidence)
    """
    candles = report.get("candles") or []
    if not candles:
        return {"latest_close": None, "previous_close": None, "change": None,
                "change_percent": None, "change_magnitude": None,
                "change_percent_magnitude": None}
    price = float(candles[-1]["close"])
    valid = [item for item in candles
             if item.get("is_expected_session") and item["candle_state"] == "closed"]
    previous_close = float(valid[-1]["close"]) if valid else None
    change = price - previous_close if previous_close is not None else None
    percent = (change / previous_close * 100) if change is not None and previous_close else None
    return {
        "latest_close": price,
        "previous_close": previous_close,
        "change": change,
        "change_percent": percent,
        "change_magnitude": abs(change) if change is not None else None,
        "change_percent_magnitude": abs(percent) if percent is not None else None,
    }


def _fmt(value: float | None, decimals: int) -> str:
    return "-" if value is None else f"{value:,.{decimals}f}"


def _trend_words(price: float, sma20, sma50) -> tuple[str, str]:
    """คืน (คำอธิบายภาพ, คำเดียวสำหรับพาดหัว) โดยไม่ใส่เหตุผลที่ไม่มีหลักฐาน"""
    if sma20 is None:
        return "ยังไม่มีเส้นค่าเฉลี่ยที่ข้อมูลยาวพอจะใช้อ่านแนวโน้ม", "ทรงตัว"
    above20 = price > sma20
    if sma50 is None:
        return ("ราคายืนเหนือค่าเฉลี่ย 20 วัน" if above20 else "ราคาอยู่ใต้ค่าเฉลี่ย 20 วัน"), \
               ("ยืนเหนือค่าเฉลี่ยสั้น" if above20 else "หลุดค่าเฉลี่ยสั้น")
    above50 = price > sma50
    if above20 and above50:
        return "ราคายืนเหนือค่าเฉลี่ยทั้ง 20 และ 50 วัน", "ยืนเหนือค่าเฉลี่ย"
    if not above20 and not above50:
        return "ราคาอยู่ใต้ค่าเฉลี่ยทั้ง 20 และ 50 วัน", "อยู่ใต้ค่าเฉลี่ย"
    return "ราคาอยู่ระหว่างค่าเฉลี่ย 20 กับ 50 วัน ภาพสองกรอบยังไม่ไปทางเดียวกัน", "ภาพสองกรอบขัดกัน"


def _nearest(levels: list[dict], price: float, role: str) -> dict | None:
    candidates = []
    for level in levels:
        if not level.get("approved_for_publication"):
            continue
        anchor = level.get("value")
        if anchor is None:
            anchor = (float(level["zone_low"]) + float(level["zone_high"])) / 2
        if role == "above" and anchor > price:
            candidates.append((anchor - price, level, anchor))
        elif role == "below" and anchor < price:
            candidates.append((price - anchor, level, anchor))
    if not candidates:
        return None
    distance, level, anchor = min(candidates, key=lambda item: item[0])
    return {"level": level, "anchor": anchor}


def _level_text(entry: dict | None, decimals: int) -> str:
    if entry is None:
        return "ยังไม่มีระดับที่ผ่านการตรวจในทิศนี้"
    level = entry["level"]
    if level.get("zone_low") is not None:
        return (f"{level['label']} ที่ {_fmt(float(level['zone_low']), decimals)}"
                f"-{_fmt(float(level['zone_high']), decimals)}")
    return f"{level['label']} ที่ {_fmt(float(level['value']), decimals)}"


def build_article_data(
    *,
    report: dict,
    level_map: dict,
    chart_metadata: dict,
    license_result: dict,
    symbol: str,
    instrument_type: str,
    unit: str,
    decimals: int,
    cutoff_at: str,
    batch_id: str,
    verified_news: list[dict] | None = None,
    thai_investor_data: dict | None = None,
) -> dict:
    candles = report["candles"]
    latest = candles[-1]
    summary = change_summary(report)
    price = summary["latest_close"]
    previous_close = summary["previous_close"]
    change = summary["change"]
    percent = summary["change_percent"]

    published = report["published_indicator_values"]
    sma20, sma50 = published.get("sma20"), published.get("sma50")
    rsi14, atr14 = published.get("rsi14"), published.get("atr14")
    technical_text, headline_state = _trend_words(price, sma20, sma50)

    zones = level_map["zones"]
    resistance = _nearest(zones, price, "above")
    support = _nearest(zones, price, "below")

    bull = level_engine.classify_scenario(
        target=resistance["anchor"] if resistance else None,
        invalidation=support["anchor"] if support else None,
        levels=zones, has_h4=False, has_intraday=False,
    )
    bear = level_engine.classify_scenario(
        target=support["anchor"] if support else None,
        invalidation=resistance["anchor"] if resistance else None,
        levels=zones, has_h4=False, has_intraday=False,
    )

    headline = f"{symbol} {headline_state} — จุดตัดสินอยู่ที่ {_level_text(resistance, decimals)}"
    if resistance is None:
        headline = f"{symbol} {headline_state} — รอระดับใหม่ยืนยันทิศทาง"

    payload = {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "instrument": {
            "symbol": symbol,
            "instrument_type": instrument_type,
            "instrument_label": INSTRUMENT_LABEL.get(instrument_type, instrument_type),
            "unit": unit,
            "decimals": decimals,
            "cutoff_at": cutoff_at,
            "cutoff_public": thai_datetime_text(cutoff_at),
            "candle_state": latest["candle_state"],
            "session_timezone": report["session_timezone"],
            "public_timezone": report["public_timezone"],
        },
        "headline": headline,
        "snapshot": {
            "price": price,
            "previous_close": previous_close,
            "change": change,
            "percent": percent,
            "open": float(latest["open"]),
            "high": float(latest["high"]),
            "low": float(latest["low"]),
            "valid_completed_bars": report["valid_completed_bars"],
        },
        "drivers": {
            "verified_news": verified_news or [],
            "causal_claims_allowed": bool(verified_news),
        },
        "technical": {
            "daily_summary": technical_text,
            "sma20": sma20, "sma50": sma50, "rsi14": rsi14, "atr14": atr14,
            "unavailable_indicators": [
                name for name, item in report["indicators"].items()
                if not item["approved_for_publication"]
            ],
            "timeframes_available": ["1d"],
        },
        # ฝั่ง public เอาเฉพาะระดับที่ผ่านการตรวจแล้ว — ระดับที่ไม่ผ่านอยู่ฝั่ง internal
        "levels": [level for level in zones if level.get("approved_for_publication")],
        "decision_levels": {
            "nearest_resistance": resistance["level"]["id"] if resistance else None,
            "nearest_resistance_text": _level_text(resistance, decimals),
            "nearest_support": support["level"]["id"] if support else None,
            "nearest_support_text": _level_text(support, decimals),
        },
        "scenarios": [
            {"name": "bull", **bull, "target": resistance["anchor"] if resistance else None,
             "invalidation": support["anchor"] if support else None},
            {"name": "bear", **bear, "target": support["anchor"] if support else None,
             "invalidation": resistance["anchor"] if resistance else None},
        ],
        "events_to_watch": [],
        "thai_investor": thai_investor_data,
        "visuals": chart_metadata,
        # ชุดนี้เป็น Public Article Pack — ผลด่านและรายละเอียดสัญญาสิทธิ์เป็นของภายใน
        # เก็บไว้เฉพาะสิ่งที่ผู้อ่านต้องเห็นจริง คือเครดิตแหล่งข้อมูลเมื่อสัญญาบังคับ
        "attribution_required": license_result.get("attribution_required", []),
    }
    # ตัด field นโยบายภายใน (merge_tolerance, quality_status, ฯลฯ) ออกทุกชั้น
    # ก่อนไฟล์นี้จะกลายเป็น public/article.json
    return strip_internal_fields(payload)


def render_markdown(data: dict) -> str:
    instrument = data["instrument"]
    decimals = instrument["decimals"]
    snapshot = data["snapshot"]
    technical = data["technical"]
    symbol = instrument["symbol"]
    state_text = "แท่งล่าสุดกำลังก่อตัว" if instrument["candle_state"] == "forming" else "แท่งล่าสุดปิดแล้ว"

    change_text = (
        f"{'เพิ่มขึ้น' if (snapshot['change'] or 0) >= 0 else 'ลดลง'} "
        f"{_fmt(abs(snapshot['change']), decimals)} ({_fmt(abs(snapshot['percent'] or 0), 2)}%)"
        if snapshot["change"] is not None else "ยังเทียบกับราคาปิดก่อนหน้าไม่ได้"
    )

    lines = [
        "---",
        f"title: '{data['headline']}'",
        f"symbol: {symbol}",
        f"instrument_type: {instrument['instrument_type']}",
        f"cutoff_at: '{instrument['cutoff_at']}'",
        f"timezone: {instrument['public_timezone']}",
        "---",
        "",
        f"# {data['headline']}",
        "",
        f"*ข้อมูล ณ {instrument['cutoff_public']} — {state_text}*",
        "",
        # Lead 3 ประโยค: เกิดอะไร / บริบท / ต้องดูอะไรต่อ
        f"{symbol} อยู่ที่ {_fmt(snapshot['price'], decimals)} {instrument['unit']} {change_text} "
        f"เทียบกับราคาปิดของรอบการซื้อขายก่อนหน้า "
        f"{technical['daily_summary']} "
        f"ระดับที่ใช้ตัดสินใจรอบถัดไปคือ {data['decision_levels']['nearest_resistance_text']} "
        f"ทางขึ้น และ {data['decision_levels']['nearest_support_text']} ทางลง",
        "",
        "## ภาพรวมตลาด",
        "",
        "| รายการ | ค่า |",
        "|---|---:|",
        f"| ราคาล่าสุด | {_fmt(snapshot['price'], decimals)} |",
        f"| ราคาปิดก่อนหน้า | {_fmt(snapshot['previous_close'], decimals)} |",
        f"| เปลี่ยนแปลง | {_fmt(snapshot['change'], decimals)} ({_fmt(snapshot['percent'], 2)}%) |",
        f"| เปิด / สูงสุด / ต่ำสุด | {_fmt(snapshot['open'], decimals)} / "
        f"{_fmt(snapshot['high'], decimals)} / {_fmt(snapshot['low'], decimals)} |",
        "",
        f"ตัวเลขชุดนี้อ่านจากแท่งรายวันที่ตรวจแล้วว่าอยู่ในปฏิทินการซื้อขายจริง จำนวน "
        f"{snapshot['valid_completed_bars']} แท่ง และ{state_text}",
        "",
        "## ปัจจัยขับเคลื่อน",
        "",
    ]

    if data["drivers"]["verified_news"]:
        for item in data["drivers"]["verified_news"]:
            lines.append(f"- {item['headline']} ({item['source_name']}) — {item['summary']}")
    else:
        lines.append(
            "รอบนี้ยังไม่มีข่าวที่ยืนยันแหล่งที่มาและเวลาได้ภายในสองวันก่อนเวลาตัดข้อมูล "
            "บทวิเคราะห์จึงอ่านจากพฤติกรรมราคาและระดับสำคัญเป็นหลัก และไม่ระบุสาเหตุของการเคลื่อนไหว "
            "เพราะการเดาเหตุจากจังหวะเวลาที่ใกล้กันไม่ใช่หลักฐาน"
        )

    lines += ["", "## มุมมองทางเทคนิค", ""]
    technical_bits = [f"กรอบรายวัน: {technical['daily_summary']}"]
    if technical["sma20"] is not None:
        technical_bits.append(f"ค่าเฉลี่ย 20 วันอยู่ที่ {_fmt(technical['sma20'], decimals)}")
    if technical["sma50"] is not None:
        technical_bits.append(f"ค่าเฉลี่ย 50 วันอยู่ที่ {_fmt(technical['sma50'], decimals)}")
    if technical["rsi14"] is not None:
        technical_bits.append(f"RSI 14 วันอยู่ที่ {_fmt(technical['rsi14'], 1)} ใช้อ่านโมเมนตัมเท่านั้น")
    if technical["atr14"] is not None:
        technical_bits.append(
            f"ค่าความผันผวนเฉลี่ย 14 วันอยู่ที่ {_fmt(technical['atr14'], decimals)} "
            "ใช้ประเมินระยะแกว่งที่สมเหตุสมผลของหนึ่งวัน"
        )
    lines.append(" · ".join(technical_bits))
    lines += [
        "",
        "ชุดข้อมูลรอบนี้มีเฉพาะกรอบรายวัน ยังไม่มีกรอบ 4 ชั่วโมงหรือ 1 ชั่วโมงที่ตรวจสอบได้ "
        "บทวิเคราะห์จึงพูดได้ถึงระดับมุมมองรายวัน ไม่ลงรายละเอียดจังหวะเข้าออกระหว่างวัน",
        "",
        "## ระดับตัดสินใจ",
        "",
        "| ระดับ | ราคา | บทบาท | ที่มา |",
        "|---|---:|---|---|",
    ]

    # data["levels"] ถูกกรองเหลือเฉพาะระดับที่ผ่านการตรวจแล้วตั้งแต่ตอนประกอบข้อมูล
    for level in data["levels"]:
        if level.get("zone_low") is not None:
            price_text = f"{_fmt(float(level['zone_low']), decimals)}-{_fmt(float(level['zone_high']), decimals)}"
        else:
            price_text = _fmt(float(level["value"]), decimals)
        role_text = {"support": "แนวรับ", "resistance": "แนวต้าน",
                     "bias_divider": "เส้นแบ่งมุมมอง"}.get(level["role"], level["role"])
        lines.append(f"| {level['label']} | {price_text} | {role_text} | {level['calculation_method']} |")

    lines += ["", "## ฉากทัศน์", ""]
    for scenario in data["scenarios"]:
        direction = "ทางขึ้น" if scenario["name"] == "bull" else "ทางลง"
        kind = {"watchlist": "เฝ้าดู", "daily_scenario": "มุมมองรายวัน",
                "trade_setup": "แผนเทรด"}[scenario["classification"]]
        target_text = _fmt(scenario["target"], decimals) if scenario["target"] is not None else "ยังไม่มี"
        invalid_text = (_fmt(scenario["invalidation"], decimals)
                        if scenario["invalidation"] is not None else "ยังไม่มี")
        lines.append(
            f"- **{direction} ({kind})** — เป้าหมายที่ตรวจสอบได้ {target_text} · "
            f"จุดที่ถือว่ามุมมองนี้ผิด {invalid_text}"
        )
    lines.append("")
    lines.append(
        "ทั้งสองฉากทัศน์เป็นมุมมองระดับวัน ไม่ใช่คำสั่งซื้อขาย เพราะข้อมูลรอบนี้ไม่มีกรอบเวลาสั้น "
        "ที่จะใช้ยืนยันจังหวะเข้าได้"
    )

    lines += ["", "## เหตุการณ์ที่ต้องติดตาม", ""]
    if data["events_to_watch"]:
        for event in data["events_to_watch"]:
            lines.append(f"- {event['time_local']} · {event['name']}")
    else:
        lines.append(
            "รอบนี้ยังไม่มีปฏิทินเหตุการณ์ที่ตรวจสอบแหล่งได้ จึงยังไม่ระบุกำหนดการใด "
            "ให้ติดตามการยืนหรือหลุดระดับในตารางด้านบนเป็นหลัก"
        )

    if data.get("thai_investor"):
        thai = data["thai_investor"]
        lines += ["", "## มุมสำหรับผู้ลงทุนไทย", "",
                  f"อัตราแลกเปลี่ยนที่ใช้อ้างอิงอยู่ที่ {_fmt(thai['usdthb'], 2)} บาทต่อดอลลาร์"]

    lines += [
        "",
        "## กราฟ",
        "",
        f"![{data['visuals']['alt_text']}]({Path(data['visuals']['static_path']).name})",
        "",
        # คำบรรยายต้องบอกสิ่งที่กราฟแสดงและไม่แสดง ไม่ใช่พูดเรื่องเวลาซ้ำกับบรรทัดบนสุด
        f"*กราฟรายวัน {data['visuals']['displayed_bars']} แท่ง แสดงระดับตัดสินใจ "
        f"{len(data['visuals']['labels_shown'])} อันดับแรกและ"
        + (f"เส้นค่าเฉลี่ย {', '.join(name.upper() for name in data['visuals']['plotted_indicators'])}"
           if data["visuals"]["plotted_indicators"] else "ยังไม่มีเส้นค่าเฉลี่ยที่ข้อมูลยาวพอจะแสดง")
        + " · ระดับที่เหลือในตารางด้านบนไม่ได้ติดป้ายบนกราฟเพื่อไม่ให้ภาพรก*",
        "",
        "## ความเสี่ยง",
        "",
    ]
    risk_bits = []
    if instrument["candle_state"] == "forming":
        risk_bits.append("แท่งรายวันล่าสุดยังไม่ปิด ตัวเลขจึงเปลี่ยนได้จนจบ session")
    if technical["unavailable_indicators"]:
        risk_bits.append(
            "เครื่องมือบางตัวยังคำนวณไม่ได้เพราะข้อมูลย้อนหลังไม่พอ จึงไม่นำมาใช้และไม่แสดงบนกราฟ"
        )
    risk_bits.append("ข้อมูลรอบนี้มาจากผู้ให้ข้อมูลรายเดียว ยังไม่มีแหล่งที่สองมาทวนตัวเลข")
    risk_bits.append(
        "ส่วนต่างราคาซื้อขาย การลื่นของราคา และการใช้เงินทุนเกินตัว ทำให้ผลจริงต่างจากที่ประเมินไว้ได้"
    )
    lines.append(" · ".join(risk_bits))
    lines += [
        "",
        "บทวิเคราะห์นี้จัดทำเพื่อให้ข้อมูลและการศึกษา ไม่ใช่คำแนะนำเฉพาะบุคคล "
        "ผู้ลงทุนควรกำหนดขนาดสถานะและจุดตัดขาดทุนให้เหมาะกับตนเอง",
        "",
    ]
    return "\n".join(lines)


def prose_only(text: str) -> str:
    """ตัด frontmatter ตาราง หัวข้อ และ markup ภาพออก เหลือเฉพาะเนื้อความที่คนอ่านเป็นประโยค"""
    body = text.split("---", 2)[2] if text.startswith("---") else text
    keep = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("|", "#", "![", "*ข้อมูล ณ", "*กราฟรายวัน")):
            continue
        keep.append(stripped.lstrip("-* ").strip())
    return " ".join(keep)


def approximate_thai_words(text: str) -> int:
    """ประมาณจำนวนคำไทยจากจำนวนอักษรของเนื้อความ (เฉลี่ยราว 4 อักษรต่อคำ)

    เป็นค่าประมาณเพื่อคุมความยาว ไม่ใช่ตัวตัดคำจริง และไม่นับตารางกับหัวข้อ
    """
    body = "".join(character for character in prose_only(text) if not character.isspace())
    return round(len(body) / 4)
