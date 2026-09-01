"""Public Thai writer for Style M v6 dual scenarios."""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP

from tools import public_number_policy, style_m_v6_story


H2 = ("BTCUSD H1 กับกรอบ Donchian วันนี้", "แผน Long และ Short วันนี้")
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


def whole_number(value: float) -> str:
    rounded = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.0f}"


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
    date = cutoff[:10]
    latest = story["latest"]
    indicators = story["indicators"]
    donchian = story["donchian"]
    structure = story["structure"]
    ordered = story["scenario_order"]
    first = story["scenarios"][ordered[0]]
    second = story["scenarios"][ordered[1]]
    adx_move = "เพิ่มขึ้น" if indicators.get("adx_rising") else "ลดลงหรือทรงตัว"
    lines = [
        "---",
        'asset: "btc"',
        f'title: "วิเคราะห์ BTCUSD H1 วันนี้ {date}: แผนสองฝั่งจากกรอบ Donchian"',
        f'slug: "btcusd-donchian-adx-{date}"',
        'excerpt: "วิเคราะห์กรอบ Donchian 24 ชั่วโมง วางแผน Long และ Short ด้วย ATR และอ่าน ADX เป็นความแรงของแนวโน้ม"',
        'author_slug: "world-class-broker-team"',
        'timeframe: "H1"',
        f'cutoff: "{cutoff}"',
        'status: "draft"',
        'country: thailand',
        'language: th',
        'preview_only: false',
        "---",
        "",
        f"# วิเคราะห์ BTCUSD H1 วันนี้ {date}: แผนสองฝั่งจากกรอบ Donchian",
        "",
        f"&emsp;รอบนี้มีแผนเฝ้ารอทั้ง Long และ Short จากกรอบราคาล่าสุด โดยฝั่งที่นำเสนอเป็นลำดับแรกคือแผน{('ซื้อ' if first['side'] == 'LONG' else 'ขาย')}ตามโครงสร้างราคา ไม่ใช่คำสั่งให้เข้าเทรดทันที",
        "",
        f"![BTCUSD H1 กรอบ Donchian และแผนสองฝั่ง]({image_name})",
        "",
        f"## {H2[0]}",
        "",
        f"&emsp;ราคาปิดล่าสุดอยู่ที่ {whole_number(latest['close'])} ดอลลาร์ ขณะที่กรอบ Donchian 24 ชั่วโมงมีขอบบน {whole_number(donchian['upper'])} และขอบล่าง {whole_number(donchian['lower'])} ดอลลาร์ จึงใช้สองระดับนี้เป็นฐานหา Trigger รอบถัดไป",
        f"- **ATR14:** {whole_number(indicators['atr14'])} ดอลลาร์ ใช้วัดระยะความผันผวน ไม่ใช่ตัวบอกทิศ",
        f"- **ADX14:** {whole_number(indicators['adx14'])} (ก่อนหน้า {whole_number(indicators['previous_adx14'])}; {REGIME_COPY[indicators['adx_regime']]}; {adx_move}จากแท่งก่อน) — ADX วัดความแรง ไม่บอกว่าราคาจะขึ้นหรือลง",
        f"- **โครงสร้างราคา:** {STRUCTURE_COPY.get(structure['pattern'], 'โครงสร้างราคาล่าสุด')} ใช้จัดลำดับการอ่านแผนเท่านั้น ไม่ตัดแผนฝั่งใดทิ้ง",
        "",
        f"## {H2[1]}",
        "",
        "&emsp;ทั้งสองแผนเป็นเงื่อนไขรอแท่ง H1 ปิดผ่านระดับที่กำหนด จากนั้นรอราคากลับมาทดสอบโซน Entry ก่อนพิจารณาการจับคู่จริง หากอีกฝั่ง Trigger ก่อน ให้ยกเลิกอีกฝั่งจนถึงรอบวันถัดไป",
        "",
    ]
    lines.extend(_scenario_block("Long", story["scenarios"]["long"]))
    lines.extend([""])
    lines.extend(_scenario_block("Short", story["scenarios"]["short"]))
    advisory = _news_line(list(events or [])[:1])
    if advisory:
        lines.extend(["", advisory])
    lines.extend([
        "",
        "&emsp;RR ยังไม่หัก spread/slippage และระดับทั้งหมดเป็นแผนเชิงเงื่อนไข ต้องคำนวณ RR ใหม่จากราคาจับคู่จริง รวมค่าธรรมเนียม spread และ slippage โดย Stop Loss ไม่ใช่ราคาที่รับประกันการจับคู่",
        "",
        f"[ดูกราฟ BTCUSD]({ASSET_LINK}) หรือ [อ่านบทวิเคราะห์ล่าสุด]({ANALYSIS_LINK})",
        "",
    ])
    markdown = public_number_policy.publicize("\n".join(lines))
    validate(markdown, story, events=events)
    return markdown


def validate(markdown: str, story: dict, events: list[dict] | None = None) -> dict:
    headings = re.findall(r"^## (.+)$", markdown, flags=re.MULTILINE)
    if headings != list(H2):
        raise ValueError("H2 ไม่ตรง contract v6")
    for token in FORBIDDEN:
        if token in markdown:
            raise ValueError(f"พบคำต้องห้ามใน public copy: {token}")
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
    return {"ok": True, "headings": headings, "chars": len(markdown)}


__all__ = ["ANALYSIS_LINK", "ASSET_LINK", "H2", "compose", "validate",
           "whole_number"]
