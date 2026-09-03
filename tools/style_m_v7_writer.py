"""Public Thai writer for Style M v7, preserving the v6 editorial contract.

The editorial structure, SEO metadata and reader-facing cautions remain stable;
only the canonical Entry/SL/TP geometry and its ADR14 explanation are changed.
"""
from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP

from tools import public_number_policy, style_m_v7_contract, style_m_v7_story
from tools import trade_plan_public_adapters


H2 = (
    "1. บริบทราคาและอินดิเคเตอร์ชี้วัด (Market Structure & Indicators)",
    "2. แผนการเทรดรายวัน (Trade Scenarios)",
    "3. จุดสร้างสภาพคล่องและโซนกับดักราคา (Liquidity Pools & Trap Zones)",
    "4. แผนสำรองกรณีเกิด False Breakout (Plan B / Alternative Scenario)",
    "5. เงื่อนไขการเข้าเทรดและบริหารความเสี่ยง",
)
ASSET_LINK = "/thailand/asset-btc"
ANALYSIS_LINK = "/thailand/analysis"
IMAGE_NAME = "btcusd-style-m-v7-h1-{date}.webp"
FORBIDDEN = ("EMA", "WAIT_TRIGGER", "PLAN_VALID", "INVALIDATED",
             "SCENARIOS_READY", "decision oracle", "Volume Profile", "MIXED",
             "INSUFFICIENT", "BULLISH_HH_HL", "BEARISH_LH_LL", "QUIET_RANGE",
             "TRANSITION", "TRENDING", "H1 ATR")
STRUCTURE_COPY = {
    "MIXED": "โครงสร้างยังผสม",
    "INSUFFICIENT": "จุดกลับตัวยังมีไม่พอ",
    "BULLISH_HH_HL": "ยอดและฐานยกสูงขึ้น",
    "BEARISH_LH_LL": "ยอดและฐานลดต่ำลง",
}
REGIME_COPY = {
    "QUIET_RANGE": "ความแรงของแนวโน้มยังต่ำ ตลาดมีลักษณะแกว่งในกรอบ",
    "TRANSITION": "ความแรงของแนวโน้มอยู่ในช่วงเปลี่ยนผ่าน",
    "TRENDING": "ความแรงของแนวโน้มอยู่ในระดับสูง",
}
THAI_MONTHS = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
               "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")


def whole_number(value: float) -> str:
    rounded = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.0f}"


def thai_date(value: str) -> str:
    stamp = style_m_v7_story._at(value)
    return f"{stamp.day} {THAI_MONTHS[stamp.month - 1]} {stamp.year}"


def _regime_sentence(story: dict) -> tuple[str, str]:
    indicators = story["indicators"]
    squeeze = story["squeeze"]["status"] == "CONFIRMED"
    if squeeze:
        lead = ("กำลังเคลื่อนไหวเข้าสู่ช่วงบีบอัดความผันผวน (Volatility Squeeze) "
                "ตามความกว้าง Donchian เทียบ ATR และค่า ADX ที่ยังต่ำ")
    elif indicators["adx_regime"] == "QUIET_RANGE":
        lead = "กำลังแกว่งตัวในกรอบและยังไม่มีแรงแนวโน้มชัดจากค่า ADX"
    elif indicators["adx_regime"] == "TRANSITION":
        lead = "อยู่ในช่วงเปลี่ยนผ่านของแรงแนวโน้ม จึงยังต้องรอแท่ง H1 ปิดยืนยัน"
    else:
        lead = "มีแรงแนวโน้มสูงขึ้น แต่ยังต้องรอแท่ง H1 ปิดยืนยันก่อนเข้าแผน"
    position_copy = {
        "CENTER": "แกว่งอยู่กึ่งกลางระหว่างขอบบนและขอบล่างของกรอบ Donchian 24 ชั่วโมง",
        "NEAR_UPPER": "ขยับเข้าใกล้ขอบบนของกรอบ Donchian 24 ชั่วโมง",
        "NEAR_LOWER": "ขยับเข้าใกล้ขอบล่างของกรอบ Donchian 24 ชั่วโมง",
    }[story["market_position"]]
    return lead, position_copy


def _news_line(events: list[dict]) -> str | None:
    if not events:
        return None
    event = events[0]
    title = str(event.get("title") or "เหตุการณ์ที่ต้องติดตาม").replace("|", "/")
    source = str(event.get("source") or "แหล่งข้อมูล").replace("|", "/")
    time_thai = str(event.get("time_thai") or "เวลาไม่ระบุ")
    url = str(event.get("url") or ANALYSIS_LINK)
    return (f"**ข่าวที่ต้องติดตาม:** {title} · {time_thai} "
            f"([{source}]({url})) — ตัวเลขข่าวคงตามต้นฉบับและใช้เป็นบริบทความผันผวน")


def _level(value: float | None) -> str:
    return "—" if value is None else whole_number(value)


def compose(prepared: dict, events: list[dict] | None = None, *, image_name: str | None = None) -> str:
    story = prepared.get("story", prepared)
    facts = prepared.get("facts")
    if facts is None:
        raise ValueError("v7 writer ต้องได้รับ canonical facts")
    style_m_v7_contract.validate(facts, story=story)
    cutoff = story["cutoff"]
    date_iso, date_thai = cutoff[:10], thai_date(cutoff)
    latest, indicators = story["latest"], story["indicators"]
    donchian, structure = story["donchian"], story["structure"]
    long_plan, short_plan = story["scenarios"]["long"], story["scenarios"]["short"]
    lead, position_copy = _regime_sentence(story)
    adx_move = "เพิ่มขึ้น" if indicators.get("adx_rising") else "ลดลงหรือทรงตัว"
    geo = facts["facts"]["risk_geometry"]
    vol = geo["volatility"]
    title = (f"วิเคราะห์ BTCUSD (H1) {date_thai}: วางแผนสองฝั่งจากกรอบ Donchian "
             "พร้อมระวังจุดสบัดราคา")
    excerpt = ("เจาะลึกสภาวะ BTCUSD หลังราคาบีบตัวในกรอบ Donchian 24 ชม. "
               "วางแผน Long/Short พร้อมวิเคราะห์โซน Liquidity แบบอ้างอิงและแผนสำรองรับมือ False Breakout"
               if story["squeeze"]["status"] == "CONFIRMED" else
               "วิเคราะห์สภาวะ BTCUSD ในกรอบ Donchian 24 ชม. "
               "วางแผน Long/Short ด้วย ATR และอ่าน ADX เป็นความแรงของแนวโน้ม")
    image_name = image_name or IMAGE_NAME.format(date=date_iso)
    lines = [
        "---", 'asset: "btc"', f'title: "{title}"',
        f'slug: "btcusd-donchian-adx-{date_iso}"', f'excerpt: "{excerpt}"',
        'author_slug: "world-class-broker-team"', 'timeframe: "H1"',
        f'cutoff: "{cutoff}"', 'status: "draft"', 'country: thailand',
        'language: th', 'preview_only: false', "---", "",
        f"# วิเคราะห์ BTCUSD (H1) ประจำวันที่ {date_thai}: แผนสองฝั่งจากกรอบ Donchian", "",
        f"&emsp;เมื่อดู [กราฟ BTCUSD แบบเรียลไทม์]({ASSET_LINK}) บนไทม์เฟรม H1 ราคา {lead} หลังอ่านแท่งปิดล่าสุดแล้ว {position_copy} โดยโครงสร้างราคาใช้จัดลำดับการอ่านแผน ไม่ได้ตัดแผนฝั่งใดทิ้ง", "",
        "&emsp;ในสภาวะเช่นนี้ การเข้าสั่งซื้อขายทันที ณ ราคาปัจจุบันมีความเสี่ยง แผนวันนี้จึงเน้นตั้งรับและรอให้ราคาเลือกทิศทางอย่างเด็ดขาด โดยกำหนดจุด Breakout ยืนยันสัญญาณ (Trigger) ก่อนหาจังหวะย่อทดสอบ (Retest) ทั้งฝั่ง Long และ Short เพื่อเปรียบเทียบความคุ้มค่าและความเสี่ยง", "",
        f"![BTCUSD H1 กรอบ Donchian และแผนสองฝั่ง]({image_name})", "",
        f"## {H2[0]}", "",
        f"* **ระดับราคาปิด H1 ล่าสุด:** {whole_number(latest['close'])} ดอลลาร์ ({position_copy})",
        f"* **กรอบ Donchian 24 ชม.:** ขอบบน {whole_number(donchian['upper'])} ดอลลาร์ และขอบล่าง {whole_number(donchian['lower'])} ดอลลาร์",
        f"* **ความกว้างกรอบ:** {whole_number(donchian['width'])} ดอลลาร์ ใช้ประกอบการประเมินระยะ ไม่ใช่ตัวบอกทิศทาง",
        f"* **ADX (14):** {whole_number(indicators['adx14'])} (ก่อนหน้า {whole_number(indicators['previous_adx14'])}; {REGIME_COPY[indicators['adx_regime']]}; {adx_move}จากแท่งก่อน) — ADX วัดความแรง ไม่บอกทิศทางราคา",
        f"* **ATR (14):** {whole_number(indicators['atr14'])} ดอลลาร์ ใช้เป็นบริบทความผันผวนระยะสั้น ไม่ใช่ค่าคำนวณ Entry/SL/TP ของแผนนี้",
        f"* **โครงสร้างราคา:** {STRUCTURE_COPY.get(structure['pattern'], 'โครงสร้างราคาล่าสุด')} ใช้ประกอบการจัดลำดับ ไม่ใช่ตัวตัดแผน", "",
        f"## {H2[1]}", "",
        "&emsp;ทั้งสองแผนเป็นเงื่อนไขรอแท่ง H1 ปิดผ่าน Trigger แล้วรอราคากลับมาทดสอบโซน Entry ก่อนพิจารณาการจับคู่จริง หากฝั่งใด Trigger ก่อน ให้ยกเลิกอีกฝั่งตามกฎ OCO", "",
        "| รายละเอียด | แผน Long (ฝั่งซื้อ) | แผน Short (ฝั่งขาย) |", "| :--- | :--- | :--- |",
        f"| **เงื่อนไข Trigger** | แท่ง H1 ปิดเหนือ **{_level(long_plan['trigger'])}** | แท่ง H1 ปิดต่ำกว่า **{_level(short_plan['trigger'])}** |",
        f"| **โซน Entry (หลัง Retest)** | **{_level(long_plan.get('entry_low'))} – {_level(long_plan.get('entry_high'))}** | **{_level(short_plan.get('entry_low'))} – {_level(short_plan.get('entry_high'))}** |",
        f"| **Stop Loss (SL)** | **{_level(long_plan.get('sl'))}** | **{_level(short_plan.get('sl'))}** |",
        f"| **Target Price (TP1 / TP2)** | **{_level(long_plan.get('tp1'))} / {_level(long_plan.get('tp2'))}** | **{_level(short_plan.get('tp1'))} / {_level(short_plan.get('tp2'))}** |", "",
        f"## {H2[2]}", "",
        f"* **Buy-Side Liquidity Reference (เหนือ {whole_number(donchian['upper'])} ดอลลาร์):** ขอบบน Donchian เป็นโซนอ้างอิงที่ผู้เล่นมักจับตาเมื่อราคา Breakout ขึ้น ไม่ใช่การยืนยันว่ามีคำสั่งจริงอยู่ที่ระดับนี้",
        f"* **Sell-Side Liquidity Reference (ใต้ {whole_number(donchian['lower'])} ดอลลาร์):** ขอบล่าง Donchian เป็นโซนอ้างอิงสำหรับการ Breakout ลงและการกวาดระดับ ไม่ใช่การยืนยันว่ามีคำสั่งคงค้างอยู่จริง",
        f"* **กับดักราคากลางกรอบ (Trap Zone {whole_number(short_plan['trigger'])} – {whole_number(long_plan['trigger'])} ดอลลาร์):** เมื่อ ADX ต่ำกว่า 20 การแกว่งในช่วงนี้อาจเกิด Whipsaw ได้ จึงไม่ไล่ราคาโดยไม่มีแท่ง H1 ปิดยืนยัน", "",
        f"## {H2[3]}", "",
        f"* **กรณีเกิด Bull Trap:** หากแท่ง H1 ปิดเหนือ {whole_number(long_plan['trigger'])} แต่แท่ง H1 ถัดไปปิดต่ำกว่า {whole_number(short_plan['trigger'])} ให้ยกเลิกแผน Long และรอประเมินแผน Short ตามข้อมูลแท่งปิด",
        f"* **กรณีเกิด Bear Trap:** หากแท่ง H1 ปิดต่ำกว่า {whole_number(short_plan['trigger'])} แต่แท่ง H1 ถัดไปปิดเหนือ {whole_number(long_plan['trigger'])} ให้ยกเลิกแผน Short และรอประเมินแผน Long ตามข้อมูลแท่งปิด",
        f"* **กฎยกเลิกแผน:** หากราคาไม่มี Retest แต่พุ่งถึง TP1 ที่ {_level(long_plan.get('tp1'))}/{_level(short_plan.get('tp1'))} ทันที ให้ยกเลิกการตั้งออเดอร์ของ leg นั้นและรอสร้างกรอบใหม่", "",
        f"## {H2[4]}", "",
        "&emsp;ระบบใช้เงื่อนไข OCO (One-Cancels-the-Other) หากฝั่งใด Trigger ก่อน ให้ยกเลิกแผนอีกฝั่งทันที การเข้าออเดอร์เกิดขึ้นเมื่อแท่ง H1 ปิดยืนยันผ่าน Trigger แล้วย้อนกลับมา Retest ในโซน Entry เท่านั้น", "",
        (f"&emsp;ระดับ Entry/SL/TP ของแผนนี้ใช้ ADR14 = {_level(vol.get('value'))} ดอลลาร์ จากวันปิดสมบูรณ์ "
         f"{vol.get('closed_daily_bars', 0)} วัน ถึง {vol.get('last_closed_date', 'ไม่พร้อม')} "
         "โดยใช้ Entry width หนึ่งในสิบของ ADR14, risk floor ครึ่งหนึ่งของ ADR14 "
         "และ cap เท่ากับ ADR14; ATR ใช้เป็นบริบทเท่านั้น ไม่ใช่ตัวคำนวณแผน"), "",
        "&emsp;ระดับ Stop Loss เป็นจุดตัดขาดทุนตามแผน ไม่ใช่ราคาที่รับประกันการจับคู่ในสภาวะตลาดจริง ควรเผื่อ Spread และ Slippage เสมอ และ RR ยังไม่หัก spread/slippage; ก่อนใช้งานต้องคำนวณใหม่จากราคาจับคู่จริง", "",
        f"&emsp;สามารถอ่าน [บทวิเคราะห์เทคนิคทั้งหมด]({ANALYSIS_LINK}) เพื่อเปรียบเทียบบริบทเพิ่มเติม", "",
    ]
    advisory = _news_line(list(events or [])[:1])
    if advisory:
        lines.extend(["", advisory])
    markdown = public_number_policy.publicize("\n".join(lines))
    public_contract = trade_plan_public_adapters.style_m_v7(
        story=story, article_name="btc.md", article_bytes=markdown.encode("utf-8"))
    if public_contract.get("publishable"):
        markdown += "\n\n" + trade_plan_public_adapters.public_plan_block(public_contract)
    validate(markdown, story, facts)
    return markdown


def validate(markdown: str, story: dict, facts: dict) -> dict:
    style_m_v7_contract.validate(facts, story=story)
    headings = re.findall(r"^## (.+)$", markdown, flags=re.MULTILINE)
    if headings != list(H2):
        raise ValueError("H2 ไม่ตรง editorial contract v6")
    frontmatter = markdown.split("---", 2)[1]
    for field in ("asset", "title", "slug", "excerpt", "author_slug", "timeframe", "cutoff", "status", "country", "language", "preview_only"):
        if not re.search(rf"(?m)^{field}:\s*", frontmatter):
            raise ValueError(f"frontmatter ขาดฟิลด์เดิม: {field}")
    body = markdown.split("> ### ข้อมูลสัญญาแผนเทรดสาธารณะ", 1)[0]
    for token in FORBIDDEN:
        if token in body:
            raise ValueError(f"พบคำต้องห้ามใน public copy: {token}")
    for token in ("วอลลุ่ม", "วอลุ่ม", "Volume Profile", "Order Book"):
        if token in body:
            raise ValueError(f"พบข้อมูลที่ไม่มีแหล่งยืนยัน: {token}")
    if markdown.count("| รายละเอียด | แผน Long (ฝั่งซื้อ) | แผน Short (ฝั่งขาย) |") != 1:
        raise ValueError("ตารางแผน Long/Short ต้องมีหนึ่งตาราง")
    for plan in story["scenarios"].values():
        if whole_number(plan["trigger"]) not in markdown:
            raise ValueError("ไม่พบ Trigger canonical")
        if plan["state"] != "NO_PLAN":
            for field in ("entry_low", "entry_high", "sl", "tp1", "tp2"):
                if whole_number(plan[field]) not in markdown:
                    raise ValueError(f"ไม่พบค่าระดับ canonical: {field}")
    return {"ok": True, "headings": headings, "chars": len(markdown)}


__all__ = ["ANALYSIS_LINK", "ASSET_LINK", "H2", "IMAGE_NAME", "compose", "validate", "whole_number"]
