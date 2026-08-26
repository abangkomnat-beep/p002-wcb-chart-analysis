"""Thai article renderer and fail-closed validator for dual-timeframe Style E+."""

from __future__ import annotations

import re
from datetime import date, datetime

from tools import style_e_plus_story, wcb_writers

MIN_CHARS = 1000
HEADINGS = (
    "สรุปแผนเทรดวันนี้ (M15 Execution Plan)",
    "ภาวะตลาดและทิศทางเทรนด์ (H1 Overview)",
    "กลยุทธ์การเข้าเทรดระยะสั้น (M15 Execution)",
    "เงื่อนไขการยกเลิกแผน (Invalidation)",
)
FORBIDDEN_TERMS = (
    "VWAP", "OBV", "RSI", "MACD", "Fibonacci", "ชวนคุย", "ข่าว",
    "แหล่งข้อมูล", "Disclaimer", "📌", "📈", "📉", "⚠", "✅", "❌",
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
    text = wcb_writers.fit_excerpt([
        "วิเคราะห์ BTC/USD จากบริบทแนวโน้ม H1 และจังหวะดำเนินแผนบน M15 ด้วยข้อมูลแท่งปิดล่าสุด",
        f"สรุปสถานะ {state} พร้อมเงื่อนไขเข้า จุดยกเลิก และเป้าหมายโดยไม่ไล่ราคา",
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
        return (
            f"> **สถานะปัจจุบัน:** **{label}**\n>\n"
            f"> H1 ปิดที่ {h1_close} ดอลลาร์ และ M15 ปิดที่ {m15_close} ดอลลาร์ "
            f"แต่รอบนี้ไม่สร้างระดับเข้าเทรด เนื่องจาก {_state_reason(story)}"
        )
    direction = "เหนือ" if side == "buy" else "ต่ำกว่า"
    verb = "ซื้อ" if side == "buy" else "ขาย"
    state_text = (
        "WAIT_TRIGGER (รอ trigger)"
        if state == "WAIT_TRIGGER" else
        "ENTRY_READY (trigger ผ่านแล้ว · ยังไม่มี fill)"
    )
    note = (
        f"ภาพรวม H1 ให้น้ำหนักฝั่ง {side.upper()} แต่ M15 ยังไม่ยืนยัน ห้ามเปิดสถานะทันที "
        f"ให้รอแท่ง M15 ปิดกลับ{direction} EMA20 ภายใน Entry Zone"
        if state == "WAIT_TRIGGER" else
        f"แท่ง M15 ปิดยืนยัน trigger ฝั่ง {side.upper()} และยังอยู่ใน Entry Zone "
        "แต่รุ่นนี้ไม่รับหลักฐาน fill จึงยังไม่ยืนยันว่ามี position"
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
        f"{_index(dmi['adx'])} {'ยืนยันว่าแนวโน้มมีแรง' if dmi['adx'] >= 20 else 'ยังไม่ยืนยันแรงแนวโน้ม'}\n"
        f"- **ความผันผวน:** BandWidth อยู่ในอันดับ {_pct(bbw['percentile'])} และ ATR14 "
        f"เท่ากับ {_money(atr['value'])} ดอลลาร์ หรืออันดับ {_pct(atr['percentile'])} "
        "ใช้ประเมินว่าตลาดมีระยะเคลื่อนไหวเพียงพอ ไม่ได้ใช้เลือกทิศเพียงตัวเดียว\n"
        f"- **กรอบราคา H1:** Donchian20 อยู่ที่ {_money(dc['lower'])}–{_money(dc['upper'])} "
        f"ดอลลาร์ ส่วน Keltner อยู่ที่ {_money(kc['lower'])}–{_money(kc['upper'])} ดอลลาร์ "
        "ระดับเหล่านี้ใช้เป็นบริบทของแนวโน้ม ไม่ใช่จุดเข้าเทรดรอบนี้\n"
        f"- **ข้อสรุป H1:** {story['bias_reason']}"
    )


def _m15_execution(story: dict) -> str:
    m15 = story["m15"]
    indicators = m15["indicators"]
    plan = story.get("plan")
    if not plan:
        return (
            f"M15 ปิดล่าสุดที่ {_money(m15['current']['close'])} ดอลลาร์ โดย EMA20 อยู่ที่ "
            f"{_money(indicators['ema20'])} ดอลลาร์ แต่ไม่มี execution map ในรอบนี้ เพราะ "
            f"{_state_reason(story)} ระบบจะคำนวณใหม่จากแท่งปิด M15 ถัดไป"
        )
    side = plan["side"]
    direction = "เหนือ" if side == "buy" else "ต่ำกว่า"
    return (
        f"จุดเข้าเทรดถูกย้ายจาก H1 ลงมาอยู่ที่ M15 โดยใช้ EMA20 ที่ "
        f"{_money(indicators['ema20'])} ดอลลาร์เป็นแกนกลาง และใช้ ATR14 M15 ที่ "
        f"{_money(indicators['atr']['value'])} ดอลลาร์กำหนดความกว้างของโซน\n\n"
        f"- **จังหวะยืนยัน:** รอ M15 ปิด{direction} EMA20 แบบ strict ภายใน Entry Zone "
        "การแตะระดับระหว่างแท่งยังไม่ถือว่าผ่านเงื่อนไข\n"
        f"- **การจำกัดความเสี่ยง:** Protective Stop ตามแผนอยู่ห่างจากขอบ Entry Zone "
        "ฝั่งเสียเปรียบ 1 ATR แต่ยัง inactive จนกว่าจะมี external fill "
        f"ทำให้ระยะเสี่ยงจากขอบเสียเปรียบเท่ากับ {_money(plan['risk'])} ดอลลาร์\n"
        "- **การจบแผน:** TP1 และ TP2 คำนวณจากระยะเสี่ยงจริง 1.5R และ 2.0R "
        "จึงเปรียบเทียบ Risk/Reward ได้จากภาพ M15 โดยตรง"
    )


def _invalidation(story: dict) -> str:
    plan = story.get("plan")
    if not plan:
        return (
            f"รอบนี้ไม่มีระดับยกเลิกเชิงตัวเลข เพราะสถานะเป็น {story['state']} "
            "ให้รอข้อมูลแท่งปิด H1 และ M15 ชุดถัดไปก่อนประเมินใหม่"
        )
    side = plan["side"]
    direction = "ต่ำกว่า" if side == "buy" else "สูงกว่า"
    target = "TP1" if side == "buy" else "TP1"
    return (
        f"- หลังเวลาเริ่มมีผล {plan['effective_from']} หากแท่ง M15 "
        f"ปิด{direction} **{_money(plan['pre_entry_invalidation_close'])} ดอลลาร์** "
        f"ให้ยกเลิกแผน {side.upper()} ก่อนเข้า เหตุการณ์นี้ไม่ใช่ Stop Loss\n"
        "- Protective Stop ในภาพเป็นระดับวางแผนเท่านั้น ยังไม่ active และรุ่นนี้ไม่อ้างผลการออกจากสถานะ\n"
        f"- หากราคาเคลื่อนไปถึง {target} โดยไม่ย้อนเข้า Entry Zone ให้ถือว่าพ้นระยะแผน "
        "ห้ามไล่ราคาและรอคำนวณรอบใหม่"
    )


def render_article(story: dict) -> str:
    style_e_plus_story.validate_story(story)
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
        "## สรุปแผนเทรดวันนี้ (M15 Execution Plan)", "", _action_plan(story), "",
        f"![ภาพที่ 1 โครงสร้าง BTC/USD H1 และความพร้อมของแนวโน้ม]({h1_image})", "",
        "## ภาวะตลาดและทิศทางเทรนด์ (H1 Overview)", "", _h1_overview(story), "",
        f"![{_m15_image_alt(story)}]({m15_image})", "",
        "## กลยุทธ์การเข้าเทรดระยะสั้น (M15 Execution)", "", _m15_execution(story), "",
        "## เงื่อนไขการยกเลิกแผน (Invalidation)", "", _invalidation(story), "",
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
    if tuple(headings) != HEADINGS:
        findings.append(_finding("h2_structure", "หัวข้อ H2 ไม่ตรงโครง Style E+ H1/M15 หรือมีเลขลำดับ"))
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
    if story.get("bias_reason") not in markdown:
        findings.append(_finding(
            "bias_reason_copy", "บทต้องแสดงเหตุผล H1 จาก story แบบตรงข้อความ"))
    char_count = len(re.sub(r"\s+", "", markdown))
    if char_count < MIN_CHARS:
        findings.append(_finding(
            "minimum_length", f"บทมี {char_count} อักขระ ต่ำกว่าเกณฑ์ {MIN_CHARS}"))
    ok = not findings
    return {"status": "pass" if ok else "fail", "ok": ok,
            "char_count": char_count, "findings": findings,
            "slug": publication_slug(story) if isinstance(story, dict) and story.get("publish_date") else None,
            "validated_at": (now or datetime.now()).isoformat(timespec="seconds")}
