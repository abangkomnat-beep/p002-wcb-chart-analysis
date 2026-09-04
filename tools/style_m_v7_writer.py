"""Style M R6 writer: preserved SEO frontmatter with a two-image contract."""
from __future__ import annotations

import re

from tools import public_number_policy, style_m_v7_contract, trade_plan_public_adapters

R6_H2 = ("บริบทราคาและอินดิเคเตอร์ชี้วัด", "แผนการเทรดรายวัน",
         "แผนสำรองกรณีเกิด False Breakout", "เงื่อนไขการเข้าเทรด")
H2 = R6_H2
ASSET_LINK = "/thailand/asset-btc"
ANALYSIS_LINK = "/thailand/analysis"
IMAGE_NAMES = {"h1_market_map": "btcusd-style-m-v7-h1-market-map-{date}.webp",
               "m15_entry_plan": "btcusd-style-m-v7-m15-entry-h1-plan-{date}.webp"}
IMAGE_NAME = IMAGE_NAMES["h1_market_map"]
FORBIDDEN = ("EMA", "WAIT_TRIGGER", "PLAN_VALID", "INVALIDATED", "SCENARIOS_READY",
             "decision oracle", "Volume Profile", "MIXED", "INSUFFICIENT")


def whole_number(value) -> str:
    return public_number_policy.whole_number(value)


def thai_date(value: str) -> str:
    year, month, day = value[:10].split("-")
    return f"{day}/{month}/{year}"


def _level(value):
    return "—" if value is None else whole_number(value)


def _coefficient(value) -> str:
    return f"{float(value):.2f}"


def _image_names(prepared, date_iso):
    names = prepared.get("image_names") or {}
    return {role: names.get(role, template.format(date=date_iso))
            for role, template in IMAGE_NAMES.items()}


def _public_block(story, article_bytes):
    contract = trade_plan_public_adapters.style_m_v7(
        story=story, article_name="btc.md", article_bytes=article_bytes)
    if not contract.get("publishable"):
        return ""
    lines = trade_plan_public_adapters.public_plan_block(contract).splitlines()
    projected = []
    for line in lines:
        if line.startswith("> - **BUY Trigger:**") or line.startswith("> - **SELL Trigger:**"):
            side = "BUY" if "BUY Trigger" in line else "SELL"
            plan = story["scenarios"]["long" if side == "BUY" else "short"]
            entry = f"{_level(plan['entry_low'])}–{_level(plan['entry_high'])}"
            line = line.replace(" | **SL:**", f" | **Entry:** {entry} | **SL:**", 1)
        if "RR ยังไม่หัก spread/slippage" in line:
            continue
        projected.append(line)
    return "\n".join(projected)


def compose(prepared: dict, events=None, *, image_name: str | None = None) -> str:
    story = prepared.get("story", prepared)
    facts = prepared.get("facts")
    if facts is None:
        raise ValueError("v7 writer ต้องได้รับ canonical facts")
    style_m_v7_contract.validate(facts, story=story)
    cutoff, date_iso = story["cutoff"], story["cutoff"][:10]
    date_thai = thai_date(cutoff)
    names = _image_names(prepared, date_iso)
    if image_name:
        names["h1_market_map"] = image_name
    latest = story["latest"]; indicators = story["indicators"]; donchian = story["donchian"]
    structure = {"MIXED": "โครงสร้างผสม", "BULLISH_HH_HL": "โครงสร้างขาขึ้น",
                 "BEARISH_LH_LL": "โครงสร้างขาลง"}.get(
                     story.get("structure", {}).get("pattern"), "โครงสร้างราคาล่าสุด")
    long_plan, short_plan = story["scenarios"]["long"], story["scenarios"]["short"]
    geometry = facts["facts"]["risk_geometry"]; volatility = geometry.get("volatility", {})
    # Keep ADR14 coefficients as ratios through the whole-number price-label
    # publicizer; these are policy constants, not BTC price fields.
    entry_width_ratio = _coefficient(geometry.get("entry_width_coefficient", 0.10))
    risk_floor_ratio = _coefficient(geometry.get("risk_floor_coefficient", 0.50))
    risk_cap_ratio = _coefficient(geometry.get("risk_cap_coefficient", 1.00))
    title = f"วิเคราะห์ BTCUSD (H1) {date_thai}: แผนสองฝั่งจากกรอบ Donchian"
    excerpt = "วิเคราะห์ BTCUSD จากโครงสร้าง H1, Donchian, ADX และ ADR14 พร้อมแผน Entry สองฝั่งและแนวทางรับมือ False Breakout"
    lines = [
        "---", 'asset: "btc"', f'title: "{title}"',
        f'slug: "btcusd-donchian-adx-{date_iso}"', f'excerpt: "{excerpt}"',
        'author_slug: "world-class-broker-team"', 'timeframe: "H1"',
        f'cutoff: "{cutoff}"', 'status: "draft"', 'country: thailand',
        'language: th', 'preview_only: false', "---", "",
        f"# วิเคราะห์ BTCUSD (H1) ประจำวันที่ {date_thai}: แผนสองฝั่งจากกรอบ Donchian", "",
        f"&emsp;เมื่อดู [กราฟ BTCUSD แบบเรียลไทม์]({ASSET_LINK}) บนไทม์เฟรม H1 ราคาปิดล่าสุดอยู่ที่ {whole_number(latest['close'])} ดอลลาร์ โดยใช้โครงสร้างราคาและ Donchian เป็นกรอบอ่านบริบท", "",
        f"&emsp;แผนวันนี้รอแท่ง H1 ปิดยืนยัน Trigger ก่อนพิจารณา Retest ในโซน Entry ทั้ง BUY และ SELL; ระดับทั้งหมดมาจาก canonical ADR14 policy เดียวกัน", "",
        f"![กราฟ BTCUSD H1 Market Map แสดงโครงสร้างราคา Donchian และ Trap Zone วันที่ {date_thai}]({names['h1_market_map']})", "",
        f"## {R6_H2[0]}", "",
        f"* **ระดับราคาปิด H1 ล่าสุด:** {whole_number(latest['close'])} ดอลลาร์",
        f"* **กรอบ Donchian 24 ชม.:** ขอบบน {whole_number(donchian['upper'])} ดอลลาร์ และขอบล่าง {whole_number(donchian['lower'])} ดอลลาร์",
        f"* **ความกว้างกรอบ:** {whole_number(donchian['width'])} ดอลลาร์ ใช้ประกอบการประเมินระยะ ไม่ใช่สัญญาณเข้า",
        f"* **ADX (14):** {whole_number(indicators['adx14'])} และ ATR (14): {whole_number(indicators['atr14'])} ดอลลาร์ ใช้เป็นบริบทความแรงและความผันผวน",
        f"* **โครงสร้างราคา:** {structure}", "",
        f"## {R6_H2[1]}", "",
        "&emsp;รอแท่ง H1 ปิดยืนยัน Trigger ก่อน แล้วจึงพิจารณา Retest ใน Entry zone; หากฝั่งใด Trigger ก่อน ให้ยกเลิกอีกฝั่งตามกฎ OCO", "",
        f"![กราฟ BTCUSD M15 Entry Plan จากแผน H1 แสดง Buy และ Sell Entry SL TP1 และ TP2 วันที่ {date_thai}]({names['m15_entry_plan']})", "",
        f"&emsp;Trap Zone อยู่ระหว่าง Trigger SELL {_level(short_plan['trigger'])} และ Trigger BUY {_level(long_plan['trigger'])} ดอลลาร์; Donchian lower {_level(donchian['lower'])} และ upper {_level(donchian['upper'])} เป็น reference ไม่ใช่สัญญาณเข้าโดยลำพัง. OCO หมายถึงเมื่อฝั่งหนึ่ง Trigger อีกฝั่งถูกยกเลิก", "",
        f"## {R6_H2[2]}", "",
        f"* **Bull Trap:** หาก H1 ปิดเหนือ {_level(long_plan['trigger'])} แล้วกลับเข้ากรอบ ให้ยกเลิก BUY และรอข้อมูลแท่งปิดใหม่",
        f"* **Bear Trap:** หาก H1 ปิดต่ำกว่า {_level(short_plan['trigger'])} แล้วกลับเข้ากรอบ ให้ยกเลิก SELL และรอข้อมูลแท่งปิดใหม่",
        "* ไม่ไล่ราคาเมื่อไม่มี Retest; ประเมินแผนใหม่เมื่อโครงสร้างและแท่งปิดเปลี่ยน", "",
        f"## {R6_H2[3]}", "",
        "&emsp;ระบบใช้ OCO และยืนยันด้วยแท่ง H1 ปิดตาม closed_h1_strict_cross ก่อนวางแผน Retest; Entry, SL, TP1 และ TP2 เป็นระดับจาก ADR14 canonical policy",
        f"&emsp;ADR14 = {_level(volatility.get('value'))} ดอลลาร์ จากข้อมูลวันปิดสมบูรณ์ {volatility.get('closed_daily_bars', 0)} วัน; policy ใช้ Entry width __R6_ENTRY_WIDTH__, risk floor __R6_RISK_FLOOR__ และ cap __R6_RISK_CAP__ ของ ADR14", "",
        f"สามารถอ่าน [บทวิเคราะห์เทคนิคทั้งหมด]({ANALYSIS_LINK}) เพื่อเปรียบเทียบบริบทเพิ่มเติม", "",
    ]
    advisory = (events or [])[:1]
    if advisory:
        event = advisory[0]
        lines.extend([f"**ข่าวที่ต้องติดตาม:** {event.get('title', 'เหตุการณ์ที่ต้องติดตาม')} · {event.get('time_thai', 'เวลาไม่ระบุ')} ([{event.get('source', 'แหล่งข้อมูล')}]({event.get('url', ANALYSIS_LINK)}))", ""])
    markdown = public_number_policy.publicize("\n".join(lines))
    markdown = (markdown.replace("__R6_ENTRY_WIDTH__", entry_width_ratio)
                        .replace("__R6_RISK_FLOOR__", risk_floor_ratio)
                        .replace("__R6_RISK_CAP__", risk_cap_ratio))
    block = _public_block(story, markdown.encode("utf-8"))
    if block:
        markdown += "\n\n" + block
    validate(markdown, story, facts)
    return markdown


def validate(markdown: str, story: dict, facts: dict) -> dict:
    style_m_v7_contract.validate(facts, story=story)
    headings = re.findall(r"^## (.+)$", markdown, flags=re.MULTILINE)
    if headings != list(R6_H2):
        raise ValueError("H2 ไม่ตรง Style M R6 editorial contract")
    frontmatter = markdown.split("---", 2)[1]
    for field in ("asset", "title", "slug", "excerpt", "author_slug", "timeframe", "cutoff", "status", "country", "language", "preview_only"):
        if not re.search(rf"(?m)^{field}:\s*", frontmatter):
            raise ValueError(f"frontmatter ขาดฟิลด์: {field}")
    body = markdown.split("> ### ข้อมูลสัญญาแผนเทรดสาธารณะ", 1)[0]
    for token in FORBIDDEN:
        if token in body:
            raise ValueError(f"พบคำต้องห้ามใน public copy: {token}")
    if "| รายละเอียด |" in body:
        raise ValueError("R6 ห้าม plan table")
    forbidden = ("ระดับ Stop Loss เป็นจุดตัดขาดทุนตามแผน", "ไม่ใช่ราคาที่รับประกันการจับคู่", "การรับประกันการจับคู่", "ควรเผื่อ Spread และ Slippage เสมอ", "RR ยังไม่หัก spread/slippage", "ก่อนใช้งานต้องคำนวณใหม่จากราคาจับคู่จริง")
    if any(token in body for token in forbidden):
        raise ValueError("พบข้อความ legacy risk disclosure")
    refs = re.findall(r"!\[[^]]*\]\(([^)]+)\)", markdown)
    if len(refs) != 2 or len(set(refs)) != 2:
        raise ValueError("R6 ต้องมี image refs สองไฟล์ที่ distinct")
    for plan in story["scenarios"].values():
        if plan.get("state") == "NO_PLAN":
            continue
        for field in ("trigger", "entry_low", "entry_high", "sl", "tp1", "tp2"):
            if whole_number(plan[field]) not in markdown:
                raise ValueError(f"ไม่พบค่าระดับ canonical: {field}")
    return {"ok": True, "headings": headings, "image_refs": refs, "chars": len(markdown)}


__all__ = ["H2", "R6_H2", "IMAGE_NAME", "IMAGE_NAMES", "compose", "validate", "whole_number"]
