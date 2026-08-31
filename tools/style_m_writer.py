"""Short answer-first Thai BTCUSD H1 article composer for Style M v4."""

from __future__ import annotations

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
    """Public copy violates the Style M v4 contract."""


def money(value: float) -> str:
    return f"{float(value):,.2f}"


def paragraph(text: str) -> str:
    return f"&emsp;{text}"


def _title(story: dict, state: str | None = None) -> str:
    side = "ซื้อ" if story.get("side") == "BUY" else "ขาย"
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


def render(story: dict, events: list[dict] | None = None, facts: dict | None = None) -> str:
    style_m_story.validate(story)
    events = list(events or [])[:1]
    facts = facts or contract.build(story, [], events=events)
    fact_map = facts.get("facts", {})
    state = fact_map.get("plan.state", {}).get("value", story["state"])
    cutoff = datetime.fromisoformat(story["cutoff"])
    date_iso = cutoff.strftime("%Y-%m-%d")
    title = _title(story, state)
    latest = dict(story["latest"])
    latest["close"] = fact_map.get("market.latest.close", {}).get("value", latest["close"])
    indicators = dict(story["indicators"])
    for key, fact_id in (("ema20", "market.ema20"), ("ema50", "market.ema50"), ("atr14", "market.atr14")):
        indicators[key] = fact_map.get(fact_id, {}).get("value", indicators[key])
    side = story.get("side")
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
           "WriterContractError", "render", "validate"]
