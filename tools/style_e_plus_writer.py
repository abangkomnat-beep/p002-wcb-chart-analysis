"""Thai article renderer and fail-closed validator for dual-timeframe Style E+."""

from __future__ import annotations

import re
from datetime import date, datetime

from tools import style_e_plus_story, wcb_writers

MIN_CHARS = 1000
STATE_HEADINGS = {
    "NO_PLAN": (
        "สถานะวันนี้: ยังไม่มีแผน M15 (NO_PLAN)",
        "ภาพรวมตลาดและกรอบ H1 (H1 Framework)",
        "เหตุผลที่ไม่มีแผนเทรด M15",
        "เงื่อนไขสำหรับประเมินรอบถัดไป",
    ),
    "NO_CHASE": (
        "สถานะวันนี้: งดไล่ราคา (NO_CHASE)",
        "ภาพรวมตลาดและกรอบ H1 (H1 Framework)",
        "เหตุผลที่งดไล่ราคาใน M15",
        "เงื่อนไขสำหรับประเมินรอบถัดไป",
    ),
    "WAIT_TRIGGER": (
        "แผน M15 วันนี้: รอยืนยันจุดเข้า (WAIT_TRIGGER)",
        "ภาพรวมตลาดและกรอบ H1 (H1 Framework)",
        "กลยุทธ์และเหตุผลของแผน M15",
        "เงื่อนไขยกเลิกแผนก่อนเข้า",
    ),
    "ENTRY_READY": (
        "แผน M15 วันนี้: Trigger พร้อม แต่ยังไม่มี Fill (ENTRY_READY)",
        "ภาพรวมตลาดและกรอบ H1 (H1 Framework)",
        "กลยุทธ์และเหตุผลของแผน M15",
        "เงื่อนไขยกเลิกแผนก่อนเข้า",
    ),
}
FORBIDDEN_TERMS = (
    "VWAP", "OBV", "RSI", "MACD", "Fibonacci", "ชวนคุย", "ข่าว",
    "แหล่งข้อมูล", "Disclaimer", "📌", "📈", "📉", "⚠", "✅", "❌",
    "Volume", "Pin Bar", "Mean Reversion", "มีโอกาสสำเร็จสูง", "คุ้มค่า",
    "ดีที่สุด", "win rate", "backtest",
)


def publication_slug(story: dict) -> str:
    return f"btcusd-eplus-h1-m15-{story['publish_date']}"


def _thai_date(value: str) -> str:
    months = ("มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
              "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม")
    parsed = date.fromisoformat(value)
    return f"{parsed.day} {months[parsed.month - 1]} {parsed.year}"


def _money(value: float) -> str:
    return f"{float(value):,.2f}"


def _pct(value: float) -> str:
    return f"{float(value):.1f}%"


def _index(value: float) -> str:
    return f"{float(value):.1f}"


def _side_label(side: str | None) -> str:
    return "BUY" if side == "buy" else ("SELL" if side == "sell" else "WAIT")


def _state_reason(story: dict) -> str:
    if story["state"] == "NO_PLAN" and story.get("side") is None:
        return f"{story['bias_reason']} จึงยังไม่สร้าง execution map M15"
    return story["decision_reason"]


def excerpt(story: dict) -> str:
    """SEO excerpt using the same 120–160 character contract as other styles."""
    state = str(story["state"])
    excerpts = {
        "NO_PLAN": "วิเคราะห์ BTC/USD จากแนวโน้ม H1 และแท่งปิด M15 ล่าสุด สรุปว่ายังไม่มีระดับแผนในรอบนี้ พร้อมเหตุผลจากระบบและจังหวะประเมินรอบถัดไป",
        "NO_CHASE": "วิเคราะห์ BTC/USD จากแนวโน้ม H1 และแท่งปิด M15 ล่าสุด สรุปว่างดไล่ราคาเมื่อพ้นโซน พร้อมกรอบการรอประเมินรอบถัดไปและแท่งปิดชุดถัดไป",
        "WAIT_TRIGGER": "วิเคราะห์ BTC/USD จากแนวโน้ม H1 และแผน M15 ที่มีระดับคำนวณแล้ว สรุปรอแท่งปิดยืนยัน trigger ก่อนพิจารณาเข้า โดยไม่ไล่ราคา",
        "ENTRY_READY": "วิเคราะห์ BTC/USD จากแนวโน้ม H1 และแผน M15 ที่ trigger ผ่านแล้ว สรุประดับตามระบบพร้อมย้ำว่ายังไม่มี fill หรือ position ยืนยัน",
    }
    if state not in excerpts:
        raise style_e_plus_story.StoryUnavailable(f"state ไม่รองรับ excerpt: {state}")
    text = wcb_writers.fit_excerpt([
        excerpts[state],
    ])
    if not wcb_writers.EXCERPT_MIN <= len(text) <= wcb_writers.EXCERPT_MAX:
        raise style_e_plus_story.StoryUnavailable(
            f"excerpt ยาว {len(text)} ตัวอักษร ไม่อยู่ในช่วง "
            f"{wcb_writers.EXCERPT_MIN}–{wcb_writers.EXCERPT_MAX}")
    return text


def _m15_image_alt(story: dict) -> str:
    if not story.get("plan"):
        return "ภาพที่ 2 BTC/USD M15 แสดงราคาปิดและ EMA20 โดยไม่มีแผนเทรด"
    return "ภาพที่ 2 แผนเข้าเทรด BTC/USD M15 พร้อมระดับยกเลิก Protective Stop และ TP"


def _action_plan(story: dict) -> str:
    state, plan, side = story["state"], story.get("plan"), story.get("side")
    h1_close = _money(story["current"]["close"])
    m15_close = _money(story["m15"]["current"]["close"])
    if not plan:
        label = "NO_CHASE (งดไล่ราคา)" if state == "NO_CHASE" else "NO_PLAN (เฝ้าดู)"
        status_copy = (
            f"ราคาปิดเลย Entry Zone สำหรับฝั่ง {_side_label(side)} แล้ว "
            "จึงงดไล่ราคาและรอประเมินใหม่จากแท่งปิดถัดไป"
            if state == "NO_CHASE" else
            "ปัจจุบันยังไม่เข้าเงื่อนไขการสร้างแผนเทรด M15 "
            "ให้รอราคาปิดของแท่งถัดไปเพื่อประเมินใหม่อีกครั้ง"
        )
        return (
            f"> **สถานะปัจจุบัน:** **{label}**\n>\n"
            f"> ราคาปิด H1 อยู่ที่ {h1_close} ดอลลาร์ และ M15 อยู่ที่ {m15_close} ดอลลาร์ "
            f"{status_copy}"
        )
    direction = "เหนือ" if side == "buy" else "ต่ำกว่า"
    verb = "ซื้อ" if side == "buy" else "ขาย"
    state_text = (
        "WAIT_TRIGGER (รอ trigger)"
        if state == "WAIT_TRIGGER" else
        "ENTRY_READY (เงื่อนไข Trigger ครบถ้วน · ยังไม่มีข้อมูลยืนยัน Fill)"
    )
    note = (
        f"ภาพรวม H1 ให้น้ำหนักฝั่ง {side.upper()} แต่ M15 ยังไม่ยืนยัน ห้ามเปิดสถานะทันที "
        f"ให้รอแท่ง M15 ปิดกลับ{direction} EMA20 ภายใน Entry Zone"
        if state == "WAIT_TRIGGER" else
        f"แท่ง M15 ปิดยืนยันสัญญาณ {side.upper()} และราคายังอยู่ใน Entry Zone แล้ว "
        "ระบบนี้แสดงกรอบแผนเท่านั้นและยังไม่มีข้อมูลยืนยันการเปิดสถานะจริง (Fill)"
    )
    return (
        f"> **สถานะปัจจุบัน:** **{state_text}**\n>\n> {note}\n\n"
        f"- **ทิศทางหลัก (H1 Bias):** **{_side_label(side)}**\n"
        f"- **เงื่อนไขเข้าเทรด (M15 Trigger):** แท่ง M15 ปิด{direction} "
        f"**{_money(plan['trigger'])} ดอลลาร์**\n"
        f"- **กรอบราคาเข้า{verb} (Entry Zone):** "
        f"**{_money(plan['entry_zone_low'])}–{_money(plan['entry_zone_high'])} ดอลลาร์**\n"
        f"- **ระดับยกเลิกก่อนเข้า (M15 close):** "
        f"**{_money(plan['pre_entry_invalidation_close'])} ดอลลาร์**\n"
        f"- **Protective Stop ตามแผน:** "
        f"**{_money(plan['protective_stop']['price'])} ดอลลาร์** "
        "*(inactive · มีผลได้เฉพาะหลัง external fill)*\n"
        f"- **เป้าหมายกำไร 1 (TP1):** **{_money(plan['tp1'])} ดอลลาร์** "
        f"*(อัตราผลตอบแทน {plan['rr1']:.1f}R)*\n"
        f"- **เป้าหมายกำไร 2 (TP2):** **{_money(plan['tp2'])} ดอลลาร์** "
        f"*(อัตราผลตอบแทน {plan['rr2']:.1f}R)*"
    )


def _h1_overview(story: dict) -> str:
    dmi = story["indicators"]["dmi_adx"]
    bbw = story["indicators"]["bbw"]
    atr = story["indicators"]["atr"]
    dc = story["indicators"]["donchian"]
    kc = story["indicators"]["keltner"]
    dominant = "+DI" if dmi["plus_di"] > dmi["minus_di"] else "-DI"
    return (
        f"- **ทิศทางและความแรง:** +DI {_index(dmi['plus_di'])} เทียบกับ -DI "
        f"{_index(dmi['minus_di'])} ทำให้ {dominant} ได้เปรียบ ขณะที่ ADX14 "
        f"{_index(dmi['adx'])} {'ผ่านเกณฑ์ขั้นต่ำของระบบสำหรับประกอบการยืนยัน bias H1' if dmi['adx'] >= 20 else 'ยังไม่ผ่านเกณฑ์ขั้นต่ำของระบบสำหรับยืนยัน bias H1'}\n"
        f"- **ความผันผวน:** BandWidth อยู่ในอันดับ {_pct(bbw['percentile'])} และ ATR14 "
        f"เท่ากับ {_money(atr['value'])} ดอลลาร์ หรืออันดับ {_pct(atr['percentile'])} "
        "ใช้ประเมินว่าตลาดมีระยะเคลื่อนไหวเพียงพอ ไม่ได้ใช้เลือกทิศเพียงตัวเดียว\n"
        f"- **กรอบราคา H1:** Donchian20 อยู่ที่ {_money(dc['lower'])}–{_money(dc['upper'])} "
        f"ดอลลาร์ ส่วน Keltner อยู่ที่ {_money(kc['lower'])}–{_money(kc['upper'])} ดอลลาร์ "
        "ระดับเหล่านี้ใช้เป็นบริบทของแนวโน้ม ไม่ใช่จุดเข้าเทรดรอบนี้\n"
        f"- **ข้อสรุป:** {story['bias_reason']}"
    )


def _m15_execution(story: dict) -> str:
    m15 = story["m15"]
    indicators = m15["indicators"]
    plan = story.get("plan")
    if not plan:
        market = (
            f"M15 ปิดล่าสุดที่ {_money(m15['current']['close'])} ดอลลาร์ "
            f"(EMA20 อยู่ที่ {_money(indicators['ema20'])} ดอลลาร์)"
        )
        if story["state"] == "NO_CHASE":
            return (
                f"{market} {story['decision_reason']} ระบบจึงไม่สร้าง Execution Map "
                "ในรอบนี้และจะคำนวณใหม่จากแท่งปิด M15 ถัดไป"
            )
        return (
            f"{market} ระบบไม่สร้าง Execution Map ในรอบนี้ เนื่องจาก"
            f"{story['decision_reason']} และจะคำนวณใหม่จากแท่งปิด M15 ถัดไป"
        )
    side = plan["side"]
    direction = "เหนือ" if side == "buy" else "ต่ำกว่า"
    confirmation = (
        "แท่ง M15 ปิดยืนยัน Trigger แล้ว แต่ระบบยังไม่มีข้อมูลยืนยันการเปิดสถานะจริง (Fill)"
        if story["state"] == "ENTRY_READY" else
        f"ต้องรอให้แท่ง M15 ปิดสมบูรณ์ (Candle Close) {direction} EMA20 "
        "ภายใน Entry Zone เท่านั้น การแตะระดับระหว่างแท่งยังไม่ถือว่าเกิด Trigger"
    )
    stop_direction = "ต่ำกว่า" if side == "buy" else "สูงกว่า"
    stop_edge = "ขอบล่าง" if side == "buy" else "ขอบบน"
    risk_edge = "ขอบบน" if side == "buy" else "ขอบล่าง"
    return (
        f"{story['decision_reason']} จุดเข้าเทรดถูกย้ายจาก H1 ลงมาอยู่ที่ M15 โดยใช้ EMA20 ที่ "
        f"{_money(indicators['ema20'])} ดอลลาร์เป็นแกนกลาง และใช้ ATR14 M15 ที่ "
        f"{_money(indicators['atr']['value'])} ดอลลาร์กำหนดความกว้างของโซน\n\n"
        f"- **จังหวะยืนยัน:** {confirmation}\n"
        f"- **การจำกัดความเสี่ยง:** ระดับ Protective Stop คำนวณไว้{stop_direction}{stop_edge}"
        f"ของ Entry Zone เป็นระยะ 1 ATR และเมื่อวัดจาก{risk_edge}ของโซน "
        f"ระยะเสี่ยงตามแผนเท่ากับ {_money(plan['risk'])} ดอลลาร์ "
        "ระดับนี้ยังไม่มีผลจนกว่าจะมีข้อมูลยืนยันการเปิดสถานะจริง (Fill)\n"
        "- **การจบแผน:** TP1 และ TP2 คำนวณจากระยะเสี่ยงจริง 1.5R และ 2.0R "
        "จึงเปรียบเทียบ Risk/Reward ได้จากภาพ M15 โดยตรง"
    )


def _invalidation(story: dict) -> str:
    plan = story.get("plan")
    if not plan:
        return (
            f"สถานะ {story['state']} ไม่มีระดับยกเลิกเชิงตัวเลขหรือแผนที่ต้องติดตาม "
            "ให้รอข้อมูลแท่งปิด H1 และ M15 ชุดถัดไปก่อนประเมินใหม่"
        )
    side = plan["side"]
    direction = "ต่ำกว่า" if side == "buy" else "สูงกว่า"
    return (
        f"- หลังเวลาเริ่มมีผล {plan['effective_from']} หากแท่ง M15 "
        f"ปิด{direction} **{_money(plan['pre_entry_invalidation_close'])} ดอลลาร์** "
        f"ให้ยกเลิกแผน {side.upper()} ก่อนเข้า เหตุการณ์นี้ไม่ใช่ Stop Loss\n"
        "- Protective Stop ในภาพเป็นระดับวางแผนเท่านั้น ยังไม่ active และรุ่นนี้ไม่อ้างผลการออกจากสถานะ\n"
        "- หากแท่ง M15 ปิดเลย Entry Zone ไปตามทิศทางของแผน "
        "ระบบจะเปลี่ยนเป็น NO_CHASE ให้งดไล่ราคาและรอคำนวณรอบใหม่"
    )


def render_article(story: dict) -> str:
    style_e_plus_story.validate_story(story)
    headings = STATE_HEADINGS.get(story["state"])
    if headings is None:
        raise style_e_plus_story.StoryUnavailable(f"state ไม่รองรับ heading: {story['state']}")
    h1_image, m15_image = story["images"]["h1"], story["images"]["m15"]
    summary = excerpt(story)
    lines = [
        "---",
        f'title: "วิเคราะห์ BTC/USD (H1/M15) ประจำวันที่ {_thai_date(story["publish_date"])}"',
        f'date: "{story["publish_date"]}"',
        f'slug: "{publication_slug(story)}"',
        f'excerpt: "{summary}"',
        f'author_slug: "{wcb_writers.author_slug_for(story["asset"])}"',
        f'image: "{h1_image}"',
        f'image_m15: "{m15_image}"',
        'asset: "BTC/USD"',
        'timeframe: "H1/M15"',
        "---", "",
        f"## {headings[0]}", "", _action_plan(story), "",
        f"![ภาพที่ 1 โครงสร้าง BTC/USD H1 และความพร้อมของแนวโน้ม]({h1_image})", "",
        f"## {headings[1]}", "", _h1_overview(story), "",
        f"![{_m15_image_alt(story)}]({m15_image})", "",
        f"## {headings[2]}", "", _m15_execution(story), "",
        f"## {headings[3]}", "", _invalidation(story), "",
    ]
    return "\n".join(lines)


render = render_article


def _finding(rule: str, message: str) -> dict:
    return {"rule": rule, "severity": "fatal", "line": 1, "message": message}


def validate(markdown: str, story: dict, *, now: datetime | None = None) -> dict:
    findings: list[dict] = []
    try:
        style_e_plus_story.validate_story(story, now=now)
    except style_e_plus_story.StoryUnavailable as exc:
        findings.append(_finding("story_contract", str(exc)))
    expected = ""
    if not findings:
        try:
            expected = render_article(story)
        except style_e_plus_story.StoryUnavailable as exc:
            findings.append(_finding("story_contract", str(exc)))
    if expected and markdown != expected:
        findings.append(_finding(
            "deterministic_copy", "บทไม่ตรงผล render จาก story ทุกตัวอักษร — อาจมีเลขหรือสถานะถูกแก้มือ"))
    headings = re.findall(r"^##\s+(.+)$", markdown, flags=re.MULTILINE)
    expected_headings = STATE_HEADINGS.get(story.get("state"))
    if expected_headings is None or tuple(headings) != expected_headings:
        findings.append(_finding("h2_structure", "หัวข้อ H2 ไม่ตรงโครง Style E+ ตามสถานะ หรือมีเลขลำดับ"))
    if re.search(r"^##\s+\d+[\.\)]", markdown, flags=re.MULTILINE):
        findings.append(_finding("numbered_h2", "หัวข้อ H2 ห้ามมีเลขลำดับ"))
    for term in FORBIDDEN_TERMS:
        if term.lower() in markdown.lower():
            findings.append(_finding("forbidden_term", f"พบถ้อยคำต้องห้าม: {term}"))
    images = story.get("images") or {}
    for role in ("h1", "m15"):
        name = images.get(role, "")
        if not name or markdown.count(f"]({name})") != 1:
            findings.append(_finding("image_reference", f"บทต้องอ้างภาพ {role.upper()} หนึ่งครั้ง"))
    if story.get("state") in {"NO_PLAN", "NO_CHASE"}:
        for term in ("Entry Zone):", "Protective Stop ตามแผน):", "TP1):", "TP2):"):
            if term in markdown:
                findings.append(_finding("plan_forbidden", f"{story['state']} ห้ามมี {term}"))
        if "ภาพที่ 2 แผนเข้าเทรด BTC/USD M15 พร้อมระดับยกเลิก" in markdown:
            findings.append(_finding(
                "planless_image_copy", f"{story['state']} ห้ามบรรยายภาพ M15 ว่ามีแผนเข้า/SL/TP"))
    bias_reason = story.get("bias_reason")
    if not bias_reason or markdown.count(bias_reason) != 1:
        findings.append(_finding(
            "bias_reason_copy", "บทต้องแสดงเหตุผล H1 จาก story แบบตรงข้อความเพียงหนึ่งครั้ง"))
    decision_reason = story.get("decision_reason")
    if not decision_reason or markdown.count(decision_reason) != 1:
        findings.append(_finding(
            "decision_reason_copy", "บทต้องแสดงเหตุผล state จาก story แบบตรงข้อความเพียงหนึ่งครั้ง"))
    char_count = len(re.sub(r"\s+", "", markdown))
    if char_count < MIN_CHARS:
        findings.append(_finding(
            "minimum_length", f"บทมี {char_count} อักขระ ต่ำกว่าเกณฑ์ {MIN_CHARS}"))
    ok = not findings
    return {"status": "pass" if ok else "fail", "ok": ok,
            "char_count": char_count, "findings": findings,
            "slug": publication_slug(story) if isinstance(story, dict) and story.get("publish_date") else None,
            "validated_at": (now or datetime.now()).isoformat(timespec="seconds")}
