"""Public Thai writer for Style M v6 dual scenarios."""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP

from tools import public_number_policy, style_m_v6_story, web_frontmatter_contract


H2 = (
    "1. บริบทราคาและอินดิเคเตอร์ชี้วัด (Market Structure & Indicators)",
    "2. แผนการเทรดรายวัน (Trade Scenarios)",
    "3. จุดสร้างสภาพคล่องและโซนกับดักราคา (Liquidity Pools & Trap Zones)",
    "4. แผนสำรองกรณีเกิด False Breakout (Plan B / Alternative Scenario)",
    "5. เงื่อนไขการเข้าเทรดและบริหารความเสี่ยง",
)
ASSET_LINK = "/thailand/asset-btc"
ANALYSIS_LINK = "/thailand/analysis"
FORBIDDEN = ("EMA", "NO_PLAN", "WAIT_TRIGGER", "PLAN_VALID", "INVALIDATED",
             "SCENARIOS_READY", "decision oracle", "Volume Profile", "MIXED",
             "INSUFFICIENT", "BULLISH_HH_HL", "BEARISH_LH_LL", "QUIET_RANGE",
             "TRANSITION", "TRENDING")
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
    stamp = style_m_v6_story._at(value)
    return f"{stamp.day} {THAI_MONTHS[stamp.month - 1]} {stamp.year}"


def ratio_text(value: float) -> str:
    return public_number_policy.ratio(f"{float(value):.2f}")


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
    position = story["market_position"]
    position_copy = {
        "CENTER": "แกว่งอยู่กึ่งกลางระหว่างขอบบนและขอบล่างของกรอบ Donchian 24 ชั่วโมง",
        "NEAR_UPPER": "ขยับเข้าใกล้ขอบบนของกรอบ Donchian 24 ชั่วโมง",
        "NEAR_LOWER": "ขยับเข้าใกล้ขอบล่างของกรอบ Donchian 24 ชั่วโมง",
    }[position]
    return lead, position_copy


def _news_line(events: list[dict]) -> str | None:
    """Render trusted news verbatim; its decimals are source-owned evidence."""
    if not events:
        return None
    event = events[0]
    title = str(event.get("title") or "เหตุการณ์ที่ต้องติดตาม").replace("|", "/")
    source = str(event.get("source") or "แหล่งข้อมูล").replace("|", "/")
    time_thai = str(event.get("time_thai") or "เวลาไม่ระบุ")
    url = str(event.get("url") or "/thailand/analysis")
    return (f"**ข่าวที่ต้องติดตาม:** {title} · {time_thai} "
            f"([{source}]({url})) — ตัวเลขข่าวคงตามต้นฉบับและใช้เป็นบริบทความผันผวน")


def _scenario_block(label: str, plan: dict) -> list[str]:
    side = "ซื้อ" if plan["side"] == "LONG" else "ขาย"
    caution = "ห้ามไล่ราคา หากราคาห่างจากโซนเกิน 1 ATR" if plan["no_chase"] else "ยังไม่มีเหตุผลให้ไล่ราคา; รอ Trigger แล้วรอ retest"
    return [
        f"### แผน {label} ({side})",
        f"- **Trigger:** แท่ง H1 ปิด{('เหนือ' if plan['side'] == 'LONG' else 'ต่ำกว่า')} {whole_number(plan['trigger'])}",
        f"- **Entry หลัง retest:** {whole_number(plan['entry_low'])}–{whole_number(plan['entry_high'])}",
        f"- **Stop Loss:** {whole_number(plan['sl'])}",
        f"- **TP1 / TP2:** {whole_number(plan['tp1'])} / {whole_number(plan['tp2'])}",
        "- **RR โดยประมาณ:** TP1 3 ต่อ 2 / TP2 2 ต่อ 1",
        f"- **เงื่อนไข:** {caution}; แท่งที่ Trigger ยังไม่นับเป็น retest และการแตะโซนไม่ยืนยันการจับคู่จริง",
    ]


def compose(prepared: dict, events: list[dict] | None = None, *,
            image_name: str = "btcusd-style-m-h1-2026-08-31.webp") -> str:
    story = prepared.get("story", prepared)
    style_m_v6_story.validate(story)
    cutoff = story["cutoff"]
    date_iso = cutoff[:10]
    date_thai = thai_date(cutoff)
    latest = story["latest"]
    indicators = story["indicators"]
    donchian = story["donchian"]
    structure = story["structure"]
    long_plan = story["scenarios"]["long"]
    short_plan = story["scenarios"]["short"]
    lead, position_copy = _regime_sentence(story)
    adx_move = "เพิ่มขึ้น" if indicators.get("adx_rising") else "ลดลงหรือทรงตัว"
    title = (f"วิเคราะห์ BTCUSD (H1) {date_thai}: วางแผนสองฝั่งจากกรอบ Donchian "
             "พร้อมระวังจุดสบัดราคา")
    excerpt = ("เจาะลึกสภาวะ BTCUSD หลังราคาบีบตัวในกรอบ Donchian 24 ชม. "
               "วางแผน Long/Short พร้อมวิเคราะห์โซน Liquidity แบบอ้างอิงและแผนสำรองรับมือ False Breakout"
               if story["squeeze"]["status"] == "CONFIRMED" else
               "วิเคราะห์สภาวะ BTCUSD ในกรอบ Donchian 24 ชม. "
               "วางแผน Long/Short ด้วย ATR และอ่าน ADX เป็นความแรงของแนวโน้ม")
    lines = [
        "---", 'asset: "btc"', f'title: "{title}"',
        f'slug: "btcusd-donchian-adx-{date_iso}"', f'excerpt: "{excerpt}"',
        f'author_slug: "{web_frontmatter_contract.author_slug_for("btc")}"', 'timeframe: "H1"',
        f'cutoff: "{cutoff}"', 'status: "draft"', 'country: thailand',
        'language: th', 'preview_only: false', "---", "",
        f"# วิเคราะห์ BTCUSD (H1) ประจำวันที่ {date_thai}: แผนสองฝั่งจากกรอบ Donchian",
        "",
        f"&emsp;เมื่อดู [กราฟ BTCUSD แบบเรียลไทม์]({ASSET_LINK}) บนไทม์เฟรม H1 "
        f"ราคา {lead} หลังอ่านแท่งปิดล่าสุดแล้ว "
        f"{position_copy} โดยโครงสร้างราคาใช้จัดลำดับการอ่านแผน ไม่ได้ตัดแผนฝั่งใดทิ้ง",
        "",
        "&emsp;ในสภาวะเช่นนี้ การเข้าสั่งซื้อขายทันที ณ ราคาปัจจุบันมีความเสี่ยง "
        "แผนวันนี้จึงเน้นตั้งรับและรอให้ราคาเลือกทิศทางอย่างเด็ดขาด โดยกำหนดจุด "
        "Breakout ยืนยันสัญญาณ (Trigger) ก่อนหาจังหวะย่อทดสอบ (Retest) ทั้งฝั่ง Long "
        "และ Short เพื่อเปรียบเทียบความคุ้มค่าและความเสี่ยง",
        "",
        f"![BTCUSD H1 กรอบ Donchian และแผนสองฝั่ง]({image_name})", "",
        f"## {H2[0]}", "",
        f"* **ระดับราคาปิด H1 ล่าสุด:** {whole_number(latest['close'])} ดอลลาร์ "
        f"({position_copy})",
        f"* **กรอบ Donchian 24 ชม.:** ขอบบน {whole_number(donchian['upper'])} ดอลลาร์ "
        f"และขอบล่าง {whole_number(donchian['lower'])} ดอลลาร์",
        f"* **ความกว้างกรอบ:** {whole_number(donchian['width'])} ดอลลาร์ "
        "ใช้ประกอบการประเมินระยะ ไม่ใช่ตัวบอกทิศทาง",
        f"* **ADX (14):** {whole_number(indicators['adx14'])} "
        f"(ก่อนหน้า {whole_number(indicators['previous_adx14'])}; "
        f"{REGIME_COPY[indicators['adx_regime']]}; {adx_move}จากแท่งก่อน) "
        "— ADX วัดความแรง ไม่บอกทิศทางราคา",
        f"* **ATR (14):** {whole_number(indicators['atr14'])} ดอลลาร์ "
        "ใช้ประเมินระยะการแกว่งตัวและกำหนดความเสี่ยง",
        f"* **โครงสร้างราคา:** {STRUCTURE_COPY.get(structure['pattern'], 'โครงสร้างราคาล่าสุด')} "
        "ใช้ประกอบการจัดลำดับ ไม่ใช่ตัวตัดแผน",
        "",
        f"## {H2[1]}", "",
        "&emsp;ทั้งสองแผนเป็นเงื่อนไขรอแท่ง H1 ปิดผ่าน Trigger แล้วรอราคากลับมา "
        "ทดสอบโซน Entry ก่อนพิจารณาการจับคู่จริง หากฝั่งใด Trigger ก่อน ให้ยกเลิก "
        "อีกฝั่งตามกฎ OCO",
        "",
        "| รายละเอียด | แผน Long (ฝั่งซื้อ) | แผน Short (ฝั่งขาย) |",
        "| :--- | :--- | :--- |",
        f"| **เงื่อนไข Trigger** | แท่ง H1 ปิดเหนือ **{whole_number(long_plan['trigger'])}** | "
        f"แท่ง H1 ปิดต่ำกว่า **{whole_number(short_plan['trigger'])}** |",
        f"| **โซน Entry (หลัง Retest)** | **{whole_number(long_plan['entry_low'])} – {whole_number(long_plan['entry_high'])}** | "
        f"**{whole_number(short_plan['entry_low'])} – {whole_number(short_plan['entry_high'])}** |",
        f"| **Stop Loss (SL)** | **{whole_number(long_plan['sl'])}** | **{whole_number(short_plan['sl'])}** |",
        f"| **Target Price (TP1 / TP2)** | **{whole_number(long_plan['tp1'])} / {whole_number(long_plan['tp2'])}** | "
        f"**{whole_number(short_plan['tp1'])} / {whole_number(short_plan['tp2'])}** |",
        "",
        f"## {H2[2]}", "",
        f"* **Buy-Side Liquidity Reference (เหนือ {whole_number(donchian['upper'])} ดอลลาร์):** "
        "ขอบบน Donchian เป็นโซนอ้างอิงที่ผู้เล่นมักจับตาเมื่อราคา Breakout ขึ้น "
        "ไม่ใช่การยืนยันว่ามีคำสั่งจริงอยู่ที่ระดับนี้",
        f"* **Sell-Side Liquidity Reference (ใต้ {whole_number(donchian['lower'])} ดอลลาร์):** "
        "ขอบล่าง Donchian เป็นโซนอ้างอิงสำหรับการ Breakout ลงและการกวาดระดับ "
        "ไม่ใช่การยืนยันว่ามีคำสั่งคงค้างอยู่จริง",
        f"* **กับดักราคากลางกรอบ (Trap Zone {whole_number(short_plan['trigger'])} – "
        f"{whole_number(long_plan['trigger'])} ดอลลาร์):** เมื่อ ADX ต่ำกว่า 20 "
        "การแกว่งในช่วงนี้อาจเกิด Whipsaw ได้ จึงไม่ไล่ราคาโดยไม่มีแท่ง H1 ปิดยืนยัน",
        "",
        f"## {H2[3]}", "",
        f"* **กรณีเกิด Bull Trap:** หากแท่ง H1 ปิดเหนือ {whole_number(long_plan['trigger'])} "
        f"แต่แท่ง H1 ถัดไปปิดต่ำกว่า {whole_number(short_plan['trigger'])} ให้ยกเลิกแผน Long "
        "และรอประเมินแผน Short ตามข้อมูลแท่งปิด",
        f"* **กรณีเกิด Bear Trap:** หากแท่ง H1 ปิดต่ำกว่า {whole_number(short_plan['trigger'])} "
        f"แต่แท่ง H1 ถัดไปปิดเหนือ {whole_number(long_plan['trigger'])} ให้ยกเลิกแผน Short "
        "และรอประเมินแผน Long ตามข้อมูลแท่งปิด",
        f"* **กฎยกเลิกแผน:** หากราคาไม่มี Retest แต่พุ่งถึง TP1 ที่ "
        f"{whole_number(long_plan['tp1'])}/{whole_number(short_plan['tp1'])} ทันที "
        "ให้ยกเลิกการตั้งออเดอร์ของ leg นั้นและรอสร้างกรอบใหม่",
        "",
        f"## {H2[4]}", "",
        "&emsp;ระบบใช้เงื่อนไข OCO (One-Cancels-the-Other) หากฝั่งใด Trigger ก่อน "
        "ให้ยกเลิกแผนอีกฝั่งทันที การเข้าออเดอร์เกิดขึ้นเมื่อแท่ง H1 ปิดยืนยันผ่าน "
        "Trigger แล้วย้อนกลับมา Retest ในโซน Entry เท่านั้น",
        "",
        "&emsp;ระดับ Stop Loss เป็นจุดตัดขาดทุนตามแผน ไม่ใช่ราคาที่รับประกันการจับคู่ "
        "ในสภาวะตลาดจริง ควรเผื่อ Spread และ Slippage เสมอ และ RR ยังไม่หัก "
        "spread/slippage; ก่อนใช้งานต้องคำนวณใหม่จากราคาจับคู่จริง", "",
        f"&emsp;สามารถอ่าน [บทวิเคราะห์เทคนิคทั้งหมด]({ANALYSIS_LINK}) "
        "เพื่อเปรียบเทียบบริบทเพิ่มเติม", "",
    ]
    advisory = _news_line(list(events or [])[:1])
    if advisory:
        lines.extend(["", advisory])
    markdown = public_number_policy.publicize("\n".join(lines))
    validate(markdown, story, events=events)
    return markdown


def validate(markdown: str, story: dict, events: list[dict] | None = None) -> dict:
    headings = re.findall(r"^## (.+)$", markdown, flags=re.MULTILINE)
    if headings != list(H2):
        raise ValueError("H2 ไม่ตรง contract v6")
    body = markdown.split("> ### ข้อมูลสัญญาแผนเทรดสาธารณะ", 1)[0]
    for token in FORBIDDEN:
        if token == "WAIT_TRIGGER":
            continue
        if token in body:
            raise ValueError(f"พบคำต้องห้ามใน public copy: {token}")
    for token in ("วอลลุ่ม", "วอลุ่ม", "Volume Profile", "Order Book"):
        if token in body:
            raise ValueError(f"พบข้อมูลที่ไม่มีแหล่งยืนยัน: {token}")
    if markdown.count("| รายละเอียด | แผน Long (ฝั่งซื้อ) | แผน Short (ฝั่งขาย) |") != 1:
        raise ValueError("ตารางแผน Long/Short ต้องมีหนึ่งตาราง")
    if "| **RR โดยประมาณ (TP1 / TP2)** |" in markdown:
        raise ValueError("บท Style M สาธารณะไม่แสดงแถว RR")
    if markdown.count("### แผน Long") != 0 or markdown.count("### แผน Short") != 0:
        raise ValueError("ห้ามใช้ scenario heading แบบเก่าปะปน")
    for plan in story["scenarios"].values():
        for value in (plan["trigger"], plan["entry_low"], plan["entry_high"], plan["sl"], plan["tp1"], plan["tp2"]):
            if whole_number(value) not in markdown:
                raise ValueError(f"ไม่พบค่าระดับในบทความ: {value}")
    technical_copy = "\n".join(
        line for line in markdown.splitlines()
        if not line.startswith("**ข่าวที่ต้องติดตาม:**"))
    decimals = re.findall(r"(?<![A-Za-z0-9])\d[\d,]*\.\d+", technical_copy)
    if decimals:
        raise ValueError(f"public technical copy ห้ามมีทศนิยม: {sorted(set(decimals))}")
    if story["squeeze"]["status"] == "CONFIRMED" and "Volatility Squeeze" not in body:
        raise ValueError("squeeze ที่ยืนยันแล้วต้องมีคำอธิบายในบท")
    return {"ok": True, "headings": headings, "chars": len(markdown)}


__all__ = ["ANALYSIS_LINK", "ASSET_LINK", "H2", "compose", "validate",
           "whole_number"]
