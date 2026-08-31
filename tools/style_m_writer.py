"""Short answer-first Thai BTCUSD H1 article composer for Style M v5."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

from tools import style_m_article_contract as contract
from tools import style_m_story, wcb_writers

IMAGE_NAME = "btcusd-style-m-h1-{date}.webp"
ASSET_LINK = contract.PRIMARY_ROUTE
ANALYSIS_LINK = contract.SECONDARY_ROUTE
CTA_ASSET = f"[ดูกราฟ BTCUSD]({ASSET_LINK})"
CTA_ANALYSIS = f"[อ่านบทวิเคราะห์ล่าสุด]({ANALYSIS_LINK})"
H2 = contract.H2
FORBIDDEN = ("Style M", "decision oracle", "NO_PLAN", "INVALIDATED", "Volume Profile",
             "วอลุ่มซื้อขาย", "วอลุ่มสะสม", "แรงซื้อสะสม", "แรงซื้อจริง", "ลด Slippage",
             "สัญญาณซื้อทันที", "Breakout ยืนยันแล้ว")


class WriterContractError(RuntimeError):
    """Public copy violates the Style M v5 contract."""


def money(value: float) -> str:
    return f"{float(value):,.2f}"


def paragraph(text: str) -> str:
    return f"&emsp;{text}"


def _title(story: dict, state: str | None = None, side: str | None = None) -> str:
    side = "ซื้อ" if (side or story.get("side")) == "BUY" else "ขาย"
    day = datetime.fromisoformat(story["cutoff"]).strftime("%d/%m/%Y")
    state = state or story["state"]
    if state == "NO_PLAN":
        return f"วิเคราะห์ BTCUSD H1 วันนี้ {day}: รอโครงสร้างราคาที่ชัดเจน"
    if state == "INVALIDATED":
        return f"วิเคราะห์ BTCUSD H1 วันนี้ {day}: ประเมินแนวรับแนวต้านใหม่"
    if state == "WAIT_H1_CONFIRM":
        return f"วิเคราะห์ BTCUSD H1 วันนี้ {day}: แผน{side}รอแท่งยืนยัน"
    return f"วิเคราะห์ BTCUSD H1 วันนี้ {day}: เงื่อนไข{side}ผ่าน รอจังหวะเข้า"


def _excerpt(story: dict, state: str | None = None) -> str:
    state = state or story["state"]
    if state == "NO_PLAN":
        clauses = ["วิเคราะห์ BTCUSD H1 ล่าสุด ดูแนวรับ แนวต้าน และเงื่อนไขที่ต้องรอก่อนวางแผนเทรด",
                   "พร้อมอ่าน EMA, ATR และการกระจุกตัวของราคาปิดจากภาพเดียวกัน"]
        return wcb_writers.fit_excerpt(clauses)
    if state == "INVALIDATED":
        clauses = ["วิเคราะห์ BTCUSD H1 ล่าสุด เมื่อแผนเดิมหมดเงื่อนไข พร้อมแนวรับ แนวต้าน และจุดประเมินใหม่",
                   "อธิบายสิ่งที่ต้องเห็นก่อนกำหนดระดับครั้งถัดไป"]
        return wcb_writers.fit_excerpt(clauses)
    return wcb_writers.fit_excerpt(["วิเคราะห์ BTCUSD H1 ล่าสุด พร้อมแนวรับ แนวต้าน แผนแบบมีเงื่อนไข และจุดยกเลิกแผน",
                                    "รวมเงื่อนไข Trigger, RR และการไม่ไล่ราคา"])


def _trend(story: dict, facts: dict | None = None) -> str:
    fact_map = (facts or {}).get("facts", {})
    close = float(fact_map.get("market.latest.close", {}).get("value", story["latest"]["close"]))
    ema20 = float(fact_map.get("market.ema20", {}).get("value", story["indicators"]["ema20"]))
    ema50 = float(fact_map.get("market.ema50", {}).get("value", story["indicators"]["ema50"]))
    return "up" if close > ema20 and close > ema50 else "dn" if close < ema20 and close < ema50 else "fl"


def _news_line(events: list[dict]) -> str | None:
    if not events:
        return None
    event = events[0]
    title = str(event.get("title") or "เหตุการณ์ที่ต้องติดตาม").replace("|", "/")
    source = str(event.get("source") or "แหล่งข้อมูล").replace("|", "/")
    return (f"**ความเสี่ยงตามเวลา:** {title} · {event.get('time_thai', 'เวลาไม่ระบุ')} "
            f"([{source}]({event['url']})) — ใช้เป็นบริบทความผันผวน ไม่เปลี่ยนแผนเทคนิคอัตโนมัติ")


def _render_legacy(story: dict, events: list[dict] | None = None,
                   facts: dict | None = None) -> str:
    style_m_story.validate(story)
    events = list(events or [])[:1]
    facts = facts or contract.build(story, [], events=events)
    fact_map = facts.get("facts", {})
    state = fact_map.get("plan.state", {}).get("value", story["state"])
    side = fact_map.get("plan.side", {}).get("value", story.get("side"))
    cutoff = datetime.fromisoformat(story["cutoff"])
    date_iso = cutoff.strftime("%Y-%m-%d")
    title = _title(story, state, side)
    latest = dict(story["latest"])
    latest["close"] = fact_map.get("market.latest.close", {}).get("value", latest["close"])
    indicators = dict(story["indicators"])
    for key, fact_id in (("ema20", "market.ema20"), ("ema50", "market.ema50"), ("atr14", "market.atr14")):
        indicators[key] = fact_map.get(fact_id, {}).get("value", indicators[key])
    relation = ("เหนือ" if indicators["ema20"] > indicators["ema50"] else
                "ต่ำกว่า" if indicators["ema20"] < indicators["ema50"] else "ใกล้เคียงกับ")
    bias = "ขาขึ้น" if relation == "เหนือ" else "ขาลง" if relation == "ต่ำกว่า" else "เป็นกลาง"
    slug = f"btcusd-levels-{date_iso}"
    lines = [
        "---", f'asset: "btc"', f'title: "{title}"', f'slug: "{slug}"',
        f'excerpt: "{_excerpt(story, state)}"', f'author_slug: "{wcb_writers.author_slug_for("btcusd")}"',
        f'trend: "{_trend(story, facts)}"',
        'timeframe: "H1"',
        f'cutoff: "{story["cutoff"]}"', 'status: "draft"',
        "country: thailand", "language: th", "preview_only: false", "---", "",
        f"# {title}", "",
        paragraph(f"BTCUSD H1 ปิดล่าสุดที่ {money(latest['close'])} ดอลลาร์. เส้น EMA20 อยู่{relation} EMA50 "
                  f"จึงให้น้ำหนักภาพรวม{bias} แต่คำตอบของวันนี้ขึ้นกับการยืนหรือหลุดโซนราคาที่เห็นในภาพ"),
        "", f"![BTCUSD H1 แนวรับแนวต้านและแผนการเทรด]({IMAGE_NAME.format(date=date_iso)})", "",
        f"## {H2[0]}", "",
    ]
    support = fact_map.get("zone.support.primary")
    resistance = fact_map.get("zone.resistance.primary")
    support_text = money(support["low"]) if support else "ยังไม่มีจุดยืนยันเพียงพอ"
    resistance_text = money(resistance["high"]) if resistance else "ยังไม่มีจุดยืนยันเพียงพอ"
    pivot_values = []
    for fact_id, item in fact_map.items():
        if fact_id.startswith("structure.pivot.") and isinstance(item, dict) and item.get("value") is not None:
            pivot_values.append(money(item["value"]))
    trendline_text = ("- **เส้นแนวโน้ม:** ใช้เส้นแนวโน้มขาลงจากจุดสูงที่ยืนยันแล้วเป็นด่านติดตาม" if
                      fact_map.get("structure.trendline", {}).get("status") == "shown" else
                      "- **เส้นแนวโน้ม:** ยังไม่แสดงเส้นที่มีจุดยืนยันเพียงพอ")
    lines += [paragraph(f"โครงสร้างล่าสุดให้แนวรับใกล้ {support_text} และแนวต้านใกล้ {resistance_text} จากจุดกลับตัวที่ยืนยันแล้ว "
                        f"ค่า ATR14 อยู่ที่ {money(indicators['atr14'])} ดอลลาร์ จึงใช้เป็นกรอบประเมินความผันผวน ไม่ใช่สัญญาณทิศทาง"),
              "", f"- **EMA20:** {money(indicators['ema20'])}",
              f"- **EMA50:** {money(indicators['ema50'])}",
              f"- **ATR14:** {money(indicators['atr14'])} ดอลลาร์",
              f"- **จุดกลับตัวที่ภาพใช้:** {', '.join(pivot_values) if pivot_values else 'ยังไม่มีจุดยืนยันเพียงพอ'}",
              trendline_text,
              "- **แถบด้านซ้ายของภาพ:** การกระจุกตัวของราคาปิดใน 72 ช่วงราคา ใช้ดูบริเวณที่ราคาเคยอยู่บ่อย ไม่ใช่ข้อมูลปริมาณซื้อขายหรือแรงซื้อแรงขาย", "",
              f"## {H2[1]}", ""]
    if state == "NO_PLAN":
        lines += [paragraph(f"วันนี้ยังไม่ควรสร้างแผนเข้า เพราะ{story['reason']} ระดับ Entry, Stop Loss และเป้าหมายจึงยังไม่ถูกนำมาใช้"),
                  "", "- **เงื่อนไขกลับมาประเมิน:** รอแท่ง H1 ปิดรอบถัดไป และดูว่าราคายืนเหนือแนวต้านหรือหลุดแนวรับด้วยหลักฐานเดียวกัน", ""]
    elif state == "INVALIDATED":
        lines += [paragraph(f"แผนก่อนหน้าใช้ต่อไม่ได้เพราะ{story['reason']} ให้กลับมาอ่านแนวรับและแนวต้านจากแท่ง H1 ที่ปิดใหม่ก่อนกำหนดระดับใด ๆ"),
                  "", "- **เงื่อนไขกลับมาประเมิน:** ต้องมีโครงสร้างใหม่และระยะความเสี่ยงที่คำนวณจากข้อมูลรอบใหม่", ""]
    else:
        plan = dict(story["plan"] or {})
        for key in ("entry_low", "entry_high", "sl", "tp1", "tp2", "rr1", "rr2"):
            plan[key] = fact_map.get(f"plan.{key}", {}).get("value", plan[key])
        thai_side = "ซื้อ" if side == "BUY" else "ขาย"
        trigger = (f"แท่ง H1 ปิดเหนือ {money(plan['entry_high'])}" if side == "BUY" else
                   f"แท่ง H1 ปิดต่ำกว่า {money(plan['entry_low'])}")
        lines += [paragraph(f"ฉากทัศน์ฝั่ง{thai_side}จะมีน้ำหนักเมื่อ {trigger} แล้วรอราคากลับมาทดสอบโซน Entry"),
                  "", f"- **Trigger:** {trigger}", f"- **Entry:** {money(plan['entry_low'])}–{money(plan['entry_high'])}",
                  f"- **Stop Loss:** {money(plan['sl'])}", f"- **TP1 / TP2:** {money(plan['tp1'])} / {money(plan['tp2'])}",
                  f"- **RR โดยประมาณ:** {plan['rr1']:.2f} / {plan['rr2']:.2f} จากขอบ Entry ที่เสียเปรียบที่สุด",
                  f"- **กรอบความเสี่ยง:** Stop Loss ห่างฐานโครงสร้าง {plan['stop_buffer_atr']:.2f} ATR และความเสี่ยงสูงสุด {plan['worst_entry_risk_atr']:.2f} ATR",
                  f"- **เกณฑ์ก่อนเข้า:** RR ขั้นต่ำ TP1 {plan['min_rr1']:.2f} และ TP2 {plan['min_rr2']:.2f}; คำนวณใหม่จากราคาจับคู่จริง",
                  f"- **ยกเลิกแผน:** {'แท่ง H1 ปิดที่หรือต่ำกว่า' if side == 'BUY' else 'แท่ง H1 ปิดที่หรือสูงกว่า'} {money(plan['sl'])}",
                  "- **การจัดการ:** ยังไม่ใช่ออเดอร์ที่เปิดแล้ว; หากราคาไม่กลับเข้าโซนให้ไม่ไล่ราคา", "",
                  paragraph("ระดับเป็นเงื่อนไขจากราคาปิด ไม่รับประกันการจับคู่จริง ควรคำนวณ RR ใหม่โดยรวมค่าธรรมเนียม spread และ slippage ก่อนเข้า"), ""]
    if state in ("WAIT_H1_CONFIRM", "PLAN_VALID"):
        lines += ["- **หน้ากราฟ BTCUSD:** ดูระดับและแท่ง H1 ล่าสุดก่อนตัดสินใจ", ""]
    advisory = _news_line(events)
    if advisory:
        lines += [advisory, ""]
    lines += [f"{CTA_ASSET} หรือ {CTA_ANALYSIS}", ""]
    markdown = "\n".join(lines)
    validate(markdown, story, events=events, facts=facts)
    return markdown


_REASON_COPY = {
    "INSUFFICIENT_STRUCTURE": "หลักฐานโครงสร้างหรือ ATR ยังไม่พอ",
    "STALE_STRUCTURE": "จุดอ้างอิงเก่าเกินเกณฑ์ 72 ชั่วโมง",
    "STRUCTURE_CONFLICT": "จุดสูงกับจุดต่ำกำลังขยายคนละทิศ จึงยังไม่ได้คำตอบเดียว",
    "INVALID_GEOMETRY": "ลำดับระดับของแผนยังไม่ผ่านเกณฑ์",
    "RR_TOO_LOW": "RR ขั้นต่ำยังไม่ผ่านเกณฑ์",
    "TARGET_PASSED": "ราคาผ่านบริเวณเป้าหมายไปแล้ว รอรอบใหม่และไม่ไล่ราคา",
    "PRICE_EXTENDED": "ราคาห่างจากบริเวณแผนเกิน 1 ATR",
    "STOP_INVALIDATED": "แผนเดิมถูกยกเลิก ต้องสร้างโครงสร้างรอบใหม่",
}


def _semantic_paragraph(story: dict, facts: dict) -> str:
    semantic = facts["semantic_decision"]
    if story["state"] in ("WAIT_H1_CONFIRM", "PLAN_VALID"):
        side = "ซื้อ" if story["side"] == "BUY" else "ขาย"
        if story["state"] == "WAIT_H1_CONFIRM":
            return paragraph(
                f"รอบนี้โครงสร้างให้ภาพฝั่ง{side} แต่ยังต้องรอแท่ง H1 ปิดผ่านขอบเงื่อนไข "
                "แล้วรอราคากลับมาทดสอบ ระดับในภาพจึงยังไม่ใช่ออเดอร์ที่เปิดแล้ว และไม่ใช่สัญญาณเข้าอัตโนมัติ")
        return paragraph(
            f"รอบนี้แท่ง H1 ปิดผ่านเงื่อนไขฝั่ง{side}แล้ว แต่ยังต้องรอราคากลับมาทดสอบโซน "
            "ไม่ไล่ราคา และไม่ถือว่าการผ่านเงื่อนไขเป็นการรับประกันว่าจะจับคู่ได้จริง")
    reason = _REASON_COPY.get(story["reason_code"], story.get("reason", "เงื่อนไขของแผน"))
    if story["reason_code"] != "STRUCTURE_CONFLICT":
        return paragraph(f"รอบนี้ยังไม่มีแผนเข้าเทรด เพราะ{reason} โดยระดับที่เห็นยังไม่ใช่สัญญาณเข้าอัตโนมัติ")
    highs = story["pivots"]["highs"][-2:]
    lows = story["pivots"]["lows"][-2:]
    return paragraph(
        f"จุดสูงขยับจาก {money(highs[0]['price'])} เป็น {money(highs[1]['price'])} ซึ่งสูงขึ้น "
        f"แต่จุดต่ำขยับจาก {money(lows[0]['price'])} เป็น {money(lows[1]['price'])} ซึ่งต่ำลง "
        f"ขณะที่ราคาปิดยังอยู่ใต้ EMA20 และ EMA50 ภาพรวมจึงยังขัดกัน; {reason} "
        "รอบนี้ยังไม่มีแผนเข้าเทรด และระดับที่เห็นไม่ใช่สัญญาณเข้าอัตโนมัติ")


def _fragment_for(claim_id: str, markdown: str) -> str:
    lines = [line for line in markdown.splitlines() if line]
    selectors = {
        "claim.market.": lambda line: "BTCUSD H1 ปิดล่าสุด" in line,
        "claim.structure.": lambda line: "จุดสูงขยับจาก" in line,
        "claim.zone.": lambda line: "โครงสร้างล่าสุดให้แนวรับ" in line,
        "claim.occupancy.": lambda line: "แถบด้านซ้ายของภาพ" in line,
        "claim.analysis.trendline": lambda line: "เส้นแนวโน้ม" in line,
        "claim.analysis.breakout": lambda line: "เส้นแนวโน้ม" in line,
    }
    for prefix, predicate in selectors.items():
        if claim_id.startswith(prefix):
            match = next((line for line in lines if predicate(line)), None)
            if match:
                return match
    return next(line for line in lines if "รอบนี้" in line or "วันนี้" in line)


_ENUM_THAI = {
    "BULLISH": "EMA20 อยู่เหนือ EMA50", "BEARISH": "EMA20 อยู่ต่ำกว่า EMA50",
    "FLAT": "EMA20 กับ EMA50 อยู่ระดับเดียวกัน",
    "ABOVE_BOTH": "ราคาปิดอยู่เหนือ EMA20 และ EMA50",
    "BELOW_BOTH": "ราคาปิดอยู่ใต้ EMA20 และ EMA50",
    "BETWEEN": "ราคาปิดอยู่ระหว่าง EMA20 และ EMA50", "AT_BAND": "ราคาปิดทับแถบ EMA",
    "HIGHER_HIGH": "จุดสูงสูงขึ้น", "LOWER_HIGH": "จุดสูงลดลง", "EQUAL_HIGH": "จุดสูงเท่าเดิม",
    "HIGHER_LOW": "จุดต่ำสูงขึ้น", "LOWER_LOW": "จุดต่ำต่ำลง", "EQUAL_LOW": "จุดต่ำเท่าเดิม",
    "EXPANDING_HH_LL": "กรอบราคาขยายออกสองด้าน", "CONTRACTING_LH_HL": "กรอบราคากำลังหดตัว",
    "BULLISH_HH_HL": "โครงสร้างยกฐานและยกยอด", "BEARISH_LH_LL": "โครงสร้างลดฐานและลดยอด",
    "INSUFFICIENT": "โครงสร้างยังไม่พอ", "AMBIGUOUS_EQUAL": "โครงสร้างยังเสมอกัน",
}

_REASSESSMENT_COPY = {
    "WAIT_FOR_STRUCTURE": "รอจุดกลับตัวที่ยืนยันเพิ่ม",
    "WAIT_FOR_FRESH_STRUCTURE": "รอจุดอ้างอิงใหม่ที่อายุไม่เกิน 72 ชั่วโมง",
    "WAIT_FOR_ALIGNMENT": "รอให้ลำดับจุดสูงจุดต่ำและเส้นเฉลี่ยสอดคล้องกัน",
    "REJECT_INVALID_GEOMETRY": "รอลำดับ Entry, Stop Loss และเป้าหมายที่เรียงถูกต้อง",
    "REJECT_LOW_RR": "รอให้ระยะถึงเป้าหมายกลับมาผ่าน RR ขั้นต่ำ",
    "NO_CHASE_TARGET_PASSED": "รอโครงสร้างรอบใหม่หลังราคาผ่านจุดหมาย",
    "NO_CHASE_PRICE_EXTENDED": "รอราคากลับเข้าใกล้บริเวณแผนภายใน 1 ATR",
    "REBUILD_AFTER_INVALIDATION": "รอโครงสร้างและกรอบความเสี่ยงชุดใหม่",
}


def _body_numeric_tokens(markdown: str, claims: dict) -> list[str]:
    allowed = {"1", "14", "20", "50", "72"}
    for claim in claims.values():
        values = claim.get("value")
        stack = list(values.values()) if isinstance(values, dict) else values if isinstance(values, list) else [values]
        for value in stack:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                allowed.update({f"{float(value):,.2f}", f"{float(value):.2f}", str(value)})
    unbound = []
    body = markdown.split("---", 2)[-1]
    for line in body.splitlines():
        if not line or line.startswith("#") or line.startswith("![") or "](" in line:
            continue
        for token in re.findall(r"(?<![A-Za-z0-9])\d[\d,]*(?:\.\d+)?", line):
            if token not in allowed:
                unbound.append(token)
    return sorted(set(unbound))


def compose(story: dict, events: list[dict] | None, facts: dict) -> dict:
    """Compose copy and return typed claim bindings from the same facts snapshot."""
    events = list(events or [])[:1]
    contract.validate(facts, story=story, events=events,
                      prior_fingerprint=facts.get("prior_fingerprint"))
    claims = facts["claims"]
    semantic = facts["semantic_decision"]
    fact_map = facts["facts"]
    state, side = story["state"], story.get("side")
    cutoff = datetime.fromisoformat(story["cutoff"])
    date_iso, title = cutoff.strftime("%Y-%m-%d"), _title(story, state, side)
    lines = ["---", 'asset: "btc"', f'title: "{title}"',
             f'slug: "btcusd-levels-{date_iso}"', f'excerpt: "{_excerpt(story, state)}"',
             f'author_slug: "{wcb_writers.author_slug_for("btcusd")}"',
             f'trend: "{_trend(story, facts)}"', 'timeframe: "H1"',
             f'cutoff: "{story["cutoff"]}"', 'status: "draft"', "country: thailand",
             "language: th", "preview_only: false", "---", "", f"# {title}", ""]
    bindings: list[dict] = []
    bound: set[str] = set()

    def emit(fragment: str, claim_ids: list[str] | tuple[str, ...] = (), *, section: str):
        lines.append(fragment)
        for claim_id in claim_ids:
            claim = claims.get(claim_id)
            if not claim or "writer" not in claim["consumers"] or claim_id in bound:
                continue
            bound.add(claim_id)
            bindings.append({"binding_id": f"writer.{section}.{len(bindings) + 1:03d}",
                             "claim_id": claim_id, "consumer": "writer", "section": section,
                             "fragment": fragment,
                             "fragment_sha256": hashlib.sha256(fragment.encode("utf-8")).hexdigest(),
                             "rendered_value": claim["value"], "unit": claim["unit"],
                             "timeframe": claim["timeframe"], "at": claim.get("at"),
                             "source_fact_ids": list(claim["source_fact_ids"]),
                             "label": claim["label"],
                             "anchor_fact_ids": (list(claim["value"].get("anchor_fact_ids", []))
                                                 if isinstance(claim["value"], dict) else [])})

    reason = _REASON_COPY.get(story["reason_code"], story.get("reason", "เงื่อนไขของแผน"))
    if state == "NO_PLAN":
        if story.get("reason_code") == "STRUCTURE_CONFLICT":
            lead = ("BTCUSD H1 รอบนี้ยังไม่มีแผนเข้าเทรด เพราะราคาปิดล่าสุดอยู่ใต้เส้นค่าเฉลี่ยทั้งสองเส้น "
                    "ขณะที่โครงสร้างจุดสูงกับจุดต่ำขยายออกคนละด้าน จึงยังเลือกฝั่งไม่ได้")
        else:
            lead = f"BTCUSD H1 รอบนี้ยังไม่มีแผนเข้าเทรด เพราะ{reason} จึงยังเลือกฝั่งไม่ได้"
    elif state == "INVALIDATED":
        lead = f"BTCUSD H1 แผนเดิมถูกยกเลิก เพราะ{reason} จึงต้องรอโครงสร้างและกรอบความเสี่ยงชุดใหม่"
    elif state == "WAIT_H1_CONFIRM":
        lead = (f"BTCUSD H1 มีแผนฝั่ง{'ซื้อ' if side == 'BUY' else 'ขาย'}แบบมีเงื่อนไข "
                "แต่ยังต้องรอแท่ง H1 ปิดผ่าน Trigger และรอราคากลับมาทดสอบโซน")
    else:
        lead = (f"BTCUSD H1 ปิดผ่านเงื่อนไขฝั่ง{'ซื้อ' if side == 'BUY' else 'ขาย'}แล้ว "
                "แต่ยังต้องรอราคากลับมาทดสอบโซนโดยไม่ไล่ราคา")
    lead_claims = ["claim.plan.state"]
    if state in ("WAIT_H1_CONFIRM", "PLAN_VALID"):
        lead_claims.append("claim.plan.side")
    emit(paragraph(lead), lead_claims, section="lead")
    lines += ["", f"![BTCUSD H1 แนวรับแนวต้านและแผนการเทรด]({IMAGE_NAME.format(date=date_iso)})", "",
              f"## {H2[0]}", ""]
    close = float(fact_map["market.latest.close"]["value"])
    ema20, ema50 = float(fact_map["market.ema20"]["value"]), float(fact_map["market.ema50"]["value"])
    market = (f"หลักฐานจากราคาปิดล่าสุดคือ {money(close)} ดอลลาร์ อยู่ใต้ EMA20 {money(ema20)} ดอลลาร์ "
              f"และ EMA50 {money(ema50)} ดอลลาร์ ภาพนี้จึงบอกว่า{_ENUM_THAI[semantic['relations']['close_position']['value']]} "
              f"ขณะที่ {_ENUM_THAI[semantic['relations']['ema_stack']['value']]}" )
    emit(paragraph(market), ["claim.market.latest_close", "claim.market.ema20", "claim.market.ema50",
                             "claim.analysis.close_position", "claim.analysis.ema_stack"], section="structure")
    emit(f"- **ATR14:** {money(fact_map['market.atr14']['value'])} ดอลลาร์ ใช้วัดระยะผันผวน ไม่ใช่สัญญาณทิศทาง",
         ["claim.market.atr14"], section="structure")
    if story["reason_code"] == "STRUCTURE_CONFLICT":
        highs, lows = story["pivots"]["highs"][-2:], story["pivots"]["lows"][-2:]
        high_relation = semantic['relations']['high_relation']['value']
        low_relation = semantic['relations']['low_relation']['value']
        pattern = semantic['relations']['structure_pattern']['value']
        high_copy = ("ยอดยกสูงขึ้น" if high_relation == "HIGHER_HIGH"
                     else _ENUM_THAI[high_relation])
        low_copy = ("ฐานลดต่ำลง" if low_relation == "LOWER_LOW"
                    else _ENUM_THAI[low_relation])
        pattern_copy = _ENUM_THAI[pattern]
        if pattern == "EXPANDING_HH_LL":
            pattern_sentence = "จึงทำให้กรอบขยายออกสองด้าน"
        else:
            pattern_sentence = f"จึงทำให้กรอบเป็น{pattern_copy.removeprefix('โครงสร้าง')}"
        structure = (f"หลักฐานอีกชุดคือจุดสูงก่อนหน้า {money(highs[0]['price'])} เทียบกับจุดสูงล่าสุด {money(highs[1]['price'])} "
                     f"จึงเห็น{high_copy} ขณะที่จุดต่ำก่อนหน้า {money(lows[0]['price'])} "
                     f"เทียบกับจุดต่ำล่าสุด {money(lows[1]['price'])} จึงเห็น{low_copy} "
                     f"{pattern_sentence} และสวนทางกับภาพเส้นเฉลี่ย "
                     "นี่คือเหตุผลที่ยังให้น้ำหนักฝั่งเดียวไม่ได้")
        pivot_claims = [f"claim.structure.pivot.high.{item['index']}" for item in highs]
        pivot_claims += [f"claim.structure.pivot.low.{item['index']}" for item in lows]
        emit(paragraph(structure), pivot_claims + ["claim.analysis.high_relation",
             "claim.analysis.low_relation", "claim.analysis.structure_pattern"], section="structure")
    else:
        emit(paragraph(
            f"จุดสูง{_ENUM_THAI[semantic['relations']['high_relation']['value']]} "
            f"และจุดต่ำ{_ENUM_THAI[semantic['relations']['low_relation']['value']]} "
            f"ทำให้กรอบโครงสร้างล่าสุดเป็น{_ENUM_THAI[semantic['relations']['structure_pattern']['value']]}"),
             ["claim.analysis.high_relation", "claim.analysis.low_relation",
              "claim.analysis.structure_pattern"], section="structure")
    for family, label in (("support", "แนวรับ"), ("resistance", "แนวต้าน")):
        fact_id, claim_id = f"zone.{family}.primary", f"claim.zone.{family}.primary"
        if fact_id in fact_map:
            zone = fact_map[fact_id]
            value = money(zone["low"]) if zone["low"] == zone["high"] else f"{money(zone['low'])}–{money(zone['high'])}"
            emit(f"- **{label}:** {value} ดอลลาร์ เป็นขอบเขตสังเกตจากจุดกลับตัวที่ยืนยันแล้ว ยังไม่ใช่สัญญาณเข้า",
                 [claim_id], section="structure")
    emit("- **แถบการกระจุกตัว:** นับราคาปิดใน 72 ช่วงราคา ไม่ใช่ปริมาณซื้อขาย",
         ["claim.occupancy.disclosure"], section="structure")
    if "claim.analysis.trendline" in claims:
        emit("- **เส้นแนวโน้ม:** เชื่อมจุดสูงที่ยืนยันแล้วตามจุดอ้างอิงสองจุดในภาพ",
             ["claim.analysis.trendline"], section="structure")
    if "claim.analysis.breakout" in claims:
        emit("- **การผ่านเส้นแนวโน้ม:** มีแท่ง H1 ปิดยืนยันเหนือเส้นแล้ว",
             ["claim.analysis.breakout"], section="structure")
    lines += ["", f"## {H2[1]}", ""]
    implication = semantic["decision"]["implication"]
    if state in ("NO_PLAN", "INVALIDATED"):
        if story.get("reason_code") == "STRUCTURE_CONFLICT":
            decision_text = ("สรุปจากหลักฐานทั้งสองชุดคือยอดที่ยกสูงขึ้นสวนทางกับภาพ EMA ที่เป็นขาลง "
                             "ขณะที่ฐานที่ลดต่ำลงและราคาปิดใต้เส้นเฉลี่ยยิ่งย้ำให้ระวัง จึงยังเลือกฝั่งไม่ได้ "
                             f"เงื่อนไขที่ต้องเห็นในการกลับมาประเมินคือ {_REASSESSMENT_COPY[implication]} "
                             "และเห็นราคาปิดยืนยันไปทางเดียวกับ EMA20 และ EMA50 "
                             "การเห็นเพียงข้อเดียวก็ยังไม่ใช่สัญญาณเข้าอัตโนมัติ")
        else:
            decision_text = (f"เงื่อนไขกลับมาประเมินคือ {_REASSESSMENT_COPY[implication]} "
                             "และต้องเห็นหลักฐานยืนยันเพิ่มเติมก่อนพิจารณาแผน "
                             "การเห็นเพียงข้อเดียวยังไม่ใช่สัญญาณเข้าอัตโนมัติ")
        emit(paragraph(decision_text), ["claim.analysis.decision_implication",
                                        "claim.analysis.reassessment"], section="plan")
    else:
        plan = story["plan"]
        trigger = (f"แท่ง H1 ปิดเหนือ {money(plan['entry_high'])}" if side == "BUY"
                   else f"แท่ง H1 ปิดต่ำกว่า {money(plan['entry_low'])}")
        if state == "WAIT_H1_CONFIRM":
            emit(paragraph(f"เงื่อนไขที่ต้องรอคือ {trigger} แล้วรอกลับมาทดสอบโซน ระหว่างนี้ยังไม่ใช่ออเดอร์ที่เปิดแล้ว"),
                 ["claim.analysis.decision_implication", "claim.analysis.reassessment"], section="plan")
        else:
            emit(paragraph("เงื่อนไขผ่านแล้ว รอราคากลับมาทดสอบโซน ไม่ไล่ราคา และยังไม่ใช่ออเดอร์ที่เปิดแล้ว"),
                 ["claim.analysis.decision_implication", "claim.analysis.reassessment"], section="plan")
        emit(f"- **Trigger:** {trigger}", ["claim.plan.trigger"], section="plan")
        emit(f"- **Entry:** {money(plan['entry_low'])}–{money(plan['entry_high'])}",
             ["claim.plan.entry_low", "claim.plan.entry_high"], section="plan")
        emit(f"- **Stop Loss:** {money(plan['sl'])}", ["claim.plan.sl"], section="risk")
        emit(f"- **TP1 / TP2:** {money(plan['tp1'])} / {money(plan['tp2'])}",
             ["claim.plan.tp1", "claim.plan.tp2"], section="plan")
        emit(f"- **RR โดยประมาณ:** {plan['rr1']:.2f} / {plan['rr2']:.2f}",
             ["claim.plan.rr1", "claim.plan.rr2"], section="risk")
        emit(f"- **กรอบความเสี่ยง:** ระยะ Stop Loss จากฐานโครงสร้าง {plan['stop_buffer_atr']:.2f} ATR และความเสี่ยงขอบ Entry ไม่เกิน {plan['worst_entry_risk_atr']:.2f} ATR",
             ["claim.plan.stop_buffer_atr", "claim.plan.worst_entry_risk_atr"], section="risk")
        emit(f"- **เกณฑ์ก่อนเข้า:** RR ขั้นต่ำ TP1 {plan['min_rr1']:.2f} และ RR ขั้นต่ำ TP2 {plan['min_rr2']:.2f}",
             ["claim.plan.min_rr1", "claim.plan.min_rr2"], section="risk")
        emit(f"- **ยกเลิกแผน:** แท่ง H1 ปิด{'ที่หรือต่ำกว่า' if side == 'BUY' else 'ที่หรือสูงกว่า'} {money(plan['sl'])}",
             ["claim.plan.invalidation"], section="risk")
        emit("หลังจับคู่จริง Stop Loss จึงเป็นระดับควบคุมความเสี่ยง ไม่ใช่เงื่อนไขก่อนเข้า",
             ["claim.plan.post_entry_stop"], section="risk")
        emit(paragraph("ระดับนี้ไม่รับประกันการจับคู่จริง ต้องคำนวณ RR ใหม่โดยรวมค่าธรรมเนียม spread และ slippage ก่อนเข้า หากราคาไม่กลับเข้าโซนให้ไม่ไล่ราคา"),
             ["claim.plan.execution_costs"], section="risk")
    if events:
        advisory = _news_line(events)
        if advisory:
            emit(advisory, ["claim.news.risk_context"], section="news")
    lines += ["", f"{CTA_ASSET} หรือ {CTA_ANALYSIS}", ""]
    markdown = "\n".join(lines)
    required = {claim_id for claim_id, claim in claims.items()
                if claim.get("required") and "writer" in claim.get("consumers", [])}
    missing = sorted(required - bound)
    if missing:
        raise WriterContractError(f"writer binding ไม่ครบ: {missing}")
    validate(markdown, story, events=events, facts=facts)
    unbound = _body_numeric_tokens(markdown, claims)
    return {"markdown": markdown, "claim_report": {
        "schema": "style-m-writer-claim-report/v1",
        "facts_sha256": facts["facts_sha256"],
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "bindings": bindings,
        "unbound_numeric_tokens": unbound,
        "forbidden_claim_ids": sorted(
            claim_id for claim_id, claim in facts["claims"].items()
            if claim["permission"] == "FORBIDDEN"),
    }}


def render(story: dict, events: list[dict] | None = None,
           facts: dict | None = None) -> str:
    facts = facts or contract.build(story, [], events=events)
    return compose(story, events or [], facts)["markdown"]


def validate(markdown: str, story: dict, *, events: list[dict] | None = None,
             facts: dict | None = None) -> dict:
    findings: list[str] = []
    headings = [line[3:] for line in markdown.splitlines() if line.startswith("## ")]
    if headings != list(H2):
        findings.append("H2 ไม่ตรง contract")
    if markdown.count("btcusd-style-m-h1-") != 1:
        findings.append("ต้องอ้างภาพ Style M เพียงหนึ่งครั้ง")
    if CTA_ASSET not in markdown or CTA_ANALYSIS not in markdown:
        findings.append("CTA route ไม่ครบ allowlist")
    if f"# [BTCUSD]" in markdown:
        findings.append("H1 ต้องเป็น plain text")
    for phrase in FORBIDDEN:
        if phrase.lower() in markdown.lower():
            findings.append(f"พบคำต้องห้าม: {phrase}")
    state = facts.get("facts", {}).get("plan.state", {}).get("value", story["state"]) if facts else story["state"]
    if state in ("NO_PLAN", "INVALIDATED"):
        for label in ("**Entry:**", "**Stop Loss:**", "**TP1 / TP2:**", "**RR โดยประมาณ:**"):
            if label in markdown:
                findings.append("state ที่ไม่มีแผนมีระดับเทรด")
    if state == "WAIT_H1_CONFIRM" and "ยังไม่ใช่ออเดอร์ที่เปิดแล้ว" not in markdown:
        findings.append("WAIT H1 CONFIRM ถูกเขียนเหมือน active order")
    for event in events or []:
        if event.get("url") not in markdown:
            findings.append("ข่าวขาด source URL")
    if findings:
        raise WriterContractError("; ".join(findings))
    return {"ok": True, "findings": [], "characters": len(markdown),
            "headings": list(H2), "news_events": len(events or [])}


__all__ = ["ANALYSIS_LINK", "ASSET_LINK", "CTA_ANALYSIS", "CTA_ASSET", "FORBIDDEN", "H2", "IMAGE_NAME",
           "WriterContractError", "compose", "render", "validate"]
