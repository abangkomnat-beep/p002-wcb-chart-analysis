"""Thai article composer and fail-closed validator for Style M."""

from __future__ import annotations

from datetime import datetime

from tools import style_m_story


IMAGE_NAME = "btcusd-style-m-h1-{date}.webp"
ASSET_LINK = "/thailand/asset-btc"
H2 = (
    "สรุปวันนี้และสถานะแผน",
    "โครงสร้างราคาและโซนสำคัญ",
    "แผนเทรดและเงื่อนไขยกเลิก",
    "ข่าว เหตุการณ์ และความเสี่ยงวันนี้",
)
FORBIDDEN = ("Volume Profile", "วอลุ่มสะสม", "แรงซื้อจริง", "ลด Slippage",
             "สัญญาณซื้อทันที", "Breakout ยืนยันแล้ว")


class WriterContractError(RuntimeError):
    """Public copy violates the Style M contract."""


def money(value: float) -> str:
    return f"{float(value):,.2f}"


def paragraph(text: str) -> str:
    """Indent prose paragraphs without disturbing Markdown lists or tables."""
    return f"&emsp;{text}"


def _title(story: dict) -> str:
    state, side = story["state"], story.get("side")
    thai_side = "ซื้อ" if side == "BUY" else "ขาย"
    if state == "NO_PLAN":
        return "BTCUSD H1: วันนี้ยังไม่มีแผน รอโครงสร้างชัดเจน"
    if state == "INVALIDATED":
        return "BTCUSD H1: แผนเดิมถูกยกเลิก รอประเมินใหม่"
    if state == "WAIT_H1_CONFIRM":
        return f"BTCUSD H1: แผน{thai_side}รอแท่ง H1 ยืนยัน"
    return f"BTCUSD H1: เงื่อนไข{thai_side}ผ่านแล้ว รอจัดการตามแผน"


def _news_rows(events: list[dict]) -> list[str]:
    if not events:
        return ["| — | ไม่พบเหตุการณ์สำคัญที่ผ่านเกณฑ์หลักฐานในรอบนี้ | — | "
                "ไม่มีข้อสรุปทิศทางเพิ่มเติมจากข่าว | ใช้เงื่อนไขเทคนิคเดิมและไม่เติมข่าวจากการคาดเดา |"]
    rows: list[str] = []
    for event in events[:3]:
        title = str(event["title"]).replace("|", "/")
        url = str(event["url"])
        source = str(event.get("source") or "แหล่งข้อมูลทางการ").replace("|", "/")
        label = f"{title} ([{source}]({url}))"
        cells = [event["time_thai"], label, event["risk_level"],
                 event["impact"], event["plan_action"]]
        rows.append("| " + " | ".join(str(cell).replace("|", "/") for cell in cells) + " |")
    return rows


def render(story: dict, events: list[dict] | None = None) -> str:
    style_m_story.validate(story)
    events = list(events or [])[:3]
    cutoff = datetime.fromisoformat(story["cutoff"])
    date_iso = cutoff.strftime("%Y-%m-%d")
    date_thai = cutoff.strftime("%d/%m/%Y")
    image_name = IMAGE_NAME.format(date=date_iso)
    title = _title(story)
    linked_title = title.replace("BTCUSD", f"[BTCUSD]({ASSET_LINK})", 1)
    latest = story["latest"]
    indicators = story["indicators"]
    state = story["state"]
    side = story.get("side")
    bias = ("บวก" if indicators["ema20"] > indicators["ema50"] else
            "ลบ" if indicators["ema20"] < indicators["ema50"] else "เป็นกลาง")
    lines = [
        "---", f'title: "{title}"', 'style: "M"', 'asset: "BTCUSD"',
        'timeframe: "H1"', f'cutoff: "{story["cutoff"]}"', f'status: "{state}"',
        "preview_only: false", "---", "", f"# {linked_title}", "",
        f"**Style M — แผนภาพรายวัน H1** · ข้อมูลถึงแท่งปิด {date_thai} เวลา "
        f"{cutoff.strftime('%H:%M')} น. ประเทศไทย · ราคาปิดล่าสุด {money(latest['close'])} ดอลลาร์",
        "", f"![BTCUSD H1 Visual Daily Plan]({image_name})", "",
        f"## {H2[0]}", "",
    ]
    if state == "NO_PLAN":
        lines += [
            paragraph(f"BTCUSD บนกรอบ H1 มีน้ำหนักเชิง{bias} แต่เงื่อนไขยังไม่ครบสำหรับสร้างแผนที่มี Entry, Stop Loss และเป้าหมายอย่างมีหลักฐาน"),
            "", f"- **สถานะแผน:** NO PLAN — {story['reason']}",
            "- **ขั้นถัดไป:** รอแท่ง H1 ปิดรอบถัดไปและไม่ฝืนสร้างระดับเทรด", "",
        ]
    elif state == "INVALIDATED":
        lines += [
            paragraph(f"BTCUSD บนกรอบ H1 มีน้ำหนักเชิง{bias} แต่หลักฐานล่าสุดทำให้แผนก่อนหน้าหมดสภาพ"),
            "", f"- **สถานะแผน:** INVALIDATED — {story['reason']}",
            "- **ขั้นถัดไป:** ยังไม่มีออเดอร์หรือแผนใหม่จนกว่าจะคำนวณจากแท่งปิดรอบถัดไป", "",
        ]
    else:
        thai_side = "ซื้อ" if side == "BUY" else "ขาย"
        status_text = "แผนเฝ้ารอ" if state == "WAIT_H1_CONFIRM" else "เงื่อนไขผ่าน"
        lines += [
            paragraph(f"BTCUSD บนกรอบ H1 มีน้ำหนักเชิง{bias} และโครงสร้างล่าสุดรองรับฉากทัศน์ฝั่ง{thai_side}"),
            "", f"- **สถานะแผน:** {status_text}ฝั่ง{thai_side}",
            "- **สถานะคำสั่ง:** ยังไม่ใช่ออเดอร์ที่เปิดแล้ว",
            "- **กรอบตัดสินใจ:** ใช้แท่ง H1 ปิดและจัดการคำสั่งจริงแยกต่างหาก", "",
        ]
    lines += [f"## {H2[1]}", "",
              paragraph("ภาพใช้จุดกลับตัวที่ยืนยันด้วยแท่งข้างเคียงเพื่อวางแนวโน้มและโซนสำคัญ โดยอ้างอิงเฉพาะราคาที่ปิดแล้ว"),
              "", f"- **EMA20:** {money(indicators['ema20'])}",
              f"- **EMA50:** {money(indicators['ema50'])}",
              f"- **ATR14:** {money(indicators['atr14'])} ดอลลาร์",
              "- **แถบด้านซ้าย:** แสดงการกระจุกตัวของช่วงราคา ไม่ใช่ข้อมูลปริมาณซื้อขาย และไม่ได้ใช้ยืนยันแรงซื้อหรือแรงขาย", "",
              f"## {H2[2]}", ""]
    if state in ("NO_PLAN", "INVALIDATED"):
        lines += [
            paragraph("วันนี้ไม่มีแผนที่พร้อมกำหนดจุดเข้า จุดตัดขาดทุน หรือเป้าหมาย เพราะ decision oracle ไม่อนุญาตให้สร้างระดับเมื่อโครงสร้างไม่ครบหรือถูกยกเลิกแล้ว"),
            "", "- **เงื่อนไขกลับมาประเมิน:** รอแท่ง H1 ปิดรอบถัดไป",
            "- **ด่านที่ต้องผ่าน:** โครงสร้างใหม่, RR, ระยะห่างราคา และความสดของข้อมูล", "",
        ]
    else:
        plan = story["plan"]
        trigger = (f"แท่ง H1 ปิดเหนือ {money(plan['entry_high'])}"
                   if side == "BUY" else
                   f"แท่ง H1 ปิดต่ำกว่า {money(plan['entry_low'])}")
        retest = "ย่อลง" if side == "BUY" else "ดีดขึ้น"
        invalidation = (f"แท่ง H1 ปิดที่หรือต่ำกว่า {money(plan['sl'])}"
                        if side == "BUY" else
                        f"แท่ง H1 ปิดที่หรือสูงกว่า {money(plan['sl'])}")
        entry_limit = (f"ไม่เกิน {money(plan['dynamic_entry_limit'])}"
                       if side == "BUY" else
                       f"ไม่ต่ำกว่า {money(plan['dynamic_entry_limit'])}")
        lines += [
            f"- **Trigger:** {trigger}",
            f"- **วิธีเข้า:** หลัง Trigger รอราคา{retest}กลับมาทดสอบโซน Entry",
            "- **กรณีไม่เข้าแผน:** หากราคาไม่กลับเข้าโซน Entry ให้ไม่ไล่ราคาและรอแผนใหม่",
            f"- **Entry:** {money(plan['entry_low'])}–{money(plan['entry_high'])}",
            f"- **Stop Loss:** {money(plan['sl'])}",
            f"- **TP1:** {money(plan['tp1'])} — RR ประมาณ {plan['rr1']:.2f}",
            f"- **TP2:** {money(plan['tp2'])} — RR ประมาณ {plan['rr2']:.2f}",
            f"- **ฐานคำนวณ RR:** {'ขอบบน' if side == 'BUY' else 'ขอบล่าง'} Entry",
            f"- **ระยะ SL หลังฐานโครงสร้าง:** {plan['stop_buffer_atr']:.2f} ATR",
            f"- **ความเสี่ยงจากขอบ Entry ที่เสียเปรียบที่สุด:** {plan['worst_entry_risk_atr']:.2f} ATR",
            f"- **กฎ RR ก่อนเข้า:** คำนวณใหม่จากราคาที่คาดว่าจะจับคู่จริง โดย TP1 ต้องมี RR ไม่น้อยกว่า {plan['min_rr1']:.2f} และ TP2 ไม่น้อยกว่า {plan['min_rr2']:.2f}",
            f"- **ขีดจำกัดราคาที่เข้าจริง:** {entry_limit}",
            "", f"- **ก่อน Trigger — ยกเลิกแผน:** {invalidation}",
            f"- **หลังเข้าออเดอร์ — Stop Loss:** {money(plan['sl'])}", "",
            paragraph("ราคาที่จับคู่จริงอาจคลาดเคลื่อนจากระดับแผน โดยเฉพาะในช่วงที่ตลาดผันผวน"), "",
            paragraph("RR ข้างต้นเป็นค่าจากระดับแผนก่อนค่าธรรมเนียม spread และ slippage จริง เมื่อ SL กว้างขึ้นต้องลดขนาดสถานะตามสัดส่วนเพื่อคงวงเงินความเสี่ยงเดิม"), "",
            "**ห้ามไล่ราคา** เมื่อเกิดกรณีใดกรณีหนึ่งต่อไปนี้:", "",
            "- ราคาไม่กลับเข้าโซน Entry หลัง Trigger",
            "- ราคาที่คาดว่าจะจับคู่จริงไม่ผ่านกฎ RR ขั้นต่ำ",
            "- ราคาถึง TP1 ก่อนเข้าแผน",
            "- ถึง cutoff ของฉบับถัดไปโดยยังไม่ได้คำนวณแผนใหม่", "",
        ]
    lines += [f"## {H2[3]}", "",
              "| เวลาไทย | เหตุการณ์ | ระดับความเสี่ยง | สิ่งที่อาจเกิดขึ้น | แผนรับมือ |",
              "|---|---|---|---|---|", *_news_rows(events), ""]
    markdown = "\n".join(lines)
    validate(markdown, story, events=events)
    return markdown


def validate(markdown: str, story: dict, *, events: list[dict] | None = None) -> dict:
    findings: list[str] = []
    headings = [line[3:] for line in markdown.splitlines() if line.startswith("## ")]
    if headings != list(H2):
        findings.append("H2 ไม่ตรง contract")
    if markdown.count("btcusd-style-m-h1-") != 1:
        findings.append("ต้องอ้างภาพ Style M เพียงหนึ่งครั้ง")
    if f"[BTCUSD]({ASSET_LINK})" not in markdown:
        findings.append("หัวข้อขาดลิงก์ไปหน้ากราฟ BTCUSD")
    for phrase in FORBIDDEN:
        if phrase.lower() in markdown.lower():
            findings.append(f"พบคำต้องห้าม: {phrase}")
    if "| เวลาไทย | เหตุการณ์ | ระดับความเสี่ยง | สิ่งที่อาจเกิดขึ้น | แผนรับมือ |" not in markdown:
        findings.append("ข่าวไม่ใช่ตารางตาม contract")
    if story["state"] in ("NO_PLAN", "INVALIDATED"):
        trade_section = markdown.split(f"## {H2[2]}", 1)[1].split(f"## {H2[3]}", 1)[0]
        for label in ("**Entry:**", "**Stop Loss:**", "**TP1:**", "**TP2:**"):
            if label in trade_section:
                findings.append("NO PLAN/INVALIDATED มีระดับเทรด")
    if story["state"] == "WAIT_H1_CONFIRM" and "ยังไม่ใช่ออเดอร์ที่เปิดแล้ว" not in markdown:
        findings.append("WAIT H1 CONFIRM ถูกเขียนเหมือน active order")
    for event in events or []:
        if event.get("url") not in markdown:
            findings.append("ข่าวขาด source URL")
    if findings:
        raise WriterContractError("; ".join(findings))
    return {"ok": True, "findings": [], "characters": len(markdown),
            "headings": list(H2), "news_events": len(events or [])}


__all__ = ["ASSET_LINK", "H2", "IMAGE_NAME", "WriterContractError", "render", "validate"]
