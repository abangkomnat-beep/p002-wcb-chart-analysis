"""Public Thai writer for Style M v6 dual scenarios."""

from __future__ import annotations

import re

from tools import style_m_v6_story


H2 = ("BTCUSD H1 กับกรอบ Donchian วันนี้", "แผน Long และ Short วันนี้")
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


def money(value: float) -> str:
    return f"{float(value):,.2f}"


def _scenario_block(label: str, plan: dict) -> list[str]:
    side = "ซื้อ" if plan["side"] == "LONG" else "ขาย"
    caution = "ห้ามไล่ราคา หากราคาห่างจากโซนเกิน 1 ATR" if plan["no_chase"] else "ยังไม่มีเหตุผลให้ไล่ราคา; รอ Trigger แล้วรอ retest"
    return [
        f"### แผน {label} ({side})",
        f"- **Trigger:** แท่ง H1 ปิด{('เหนือ' if plan['side'] == 'LONG' else 'ต่ำกว่า')} {money(plan['trigger'])}",
        f"- **Entry หลัง retest:** {money(plan['entry_low'])}–{money(plan['entry_high'])}",
        f"- **Stop Loss:** {money(plan['sl'])}",
        f"- **TP1 / TP2:** {money(plan['tp1'])} / {money(plan['tp2'])}",
        f"- **RR โดยประมาณ:** {plan['rr1']:.2f} / {plan['rr2']:.2f}",
        f"- **เงื่อนไข:** {caution}; แท่งที่ Trigger ยังไม่นับเป็น retest และการแตะโซนไม่ยืนยันการจับคู่จริง",
    ]


def compose(prepared: dict, *, image_name: str = "btcusd-style-m-h1-2026-08-31.webp") -> str:
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
        f"&emsp;ราคาปิดล่าสุดอยู่ที่ {money(latest['close'])} ดอลลาร์ ขณะที่กรอบ Donchian 24 ชั่วโมงมีขอบบน {money(donchian['upper'])} และขอบล่าง {money(donchian['lower'])} ดอลลาร์ จึงใช้สองระดับนี้เป็นฐานหา Trigger รอบถัดไป",
        f"- **ATR14:** {money(indicators['atr14'])} ดอลลาร์ ใช้วัดระยะความผันผวน ไม่ใช่ตัวบอกทิศ",
        f"- **ADX14:** {indicators['adx14']:.1f} (ก่อนหน้า {indicators['previous_adx14']:.1f}; {REGIME_COPY[indicators['adx_regime']]}; {adx_move}จากแท่งก่อน) — ADX วัดความแรง ไม่บอกว่าราคาจะขึ้นหรือลง",
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
    lines.extend([
        "",
        "&emsp;ระดับทั้งหมดเป็นแผนเชิงเงื่อนไข ต้องคำนวณ RR ใหม่จากราคาจับคู่จริง รวมค่าธรรมเนียม spread และ slippage และ Stop Loss ไม่ใช่ราคาที่รับประกันการจับคู่",
        "",
        "[ดูกราฟ BTCUSD](/thailand/asset-btc) หรือ [อ่านบทวิเคราะห์ล่าสุด](/thailand/analysis)",
        "",
    ])
    markdown = "\n".join(lines)
    validate(markdown, story)
    return markdown


def validate(markdown: str, story: dict) -> dict:
    headings = re.findall(r"^## (.+)$", markdown, flags=re.MULTILINE)
    if headings != list(H2):
        raise ValueError("H2 ไม่ตรง contract v6")
    for token in FORBIDDEN:
        if token in markdown:
            raise ValueError(f"พบคำต้องห้ามใน public copy: {token}")
    for plan in story["scenarios"].values():
        for value in (plan["trigger"], plan["entry_low"], plan["entry_high"], plan["sl"], plan["tp1"], plan["tp2"]):
            if money(value) not in markdown:
                raise ValueError(f"ไม่พบค่าระดับในบทความ: {value}")
    return {"ok": True, "headings": headings, "chars": len(markdown)}


__all__ = ["H2", "compose", "validate"]
