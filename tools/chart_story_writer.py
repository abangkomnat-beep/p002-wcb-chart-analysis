"""นักเขียนสไตล์ D — บทวิเคราะห์อ่านโครงสร้างกราฟ + ด่านตรวจของสไตล์นี้เอง

โครงบทตามบทอ้างอิงที่หัวหน้าเลือก (th.investing.com/analysis/article-200458003 —
บทเดียวกับที่ภาพตัวอย่างของหัวหน้ามาจาก): เปิดด้วยเรื่องเล่าภาพใหญ่ → มุมมอง
โครงสร้าง (ภาพ 1) → พื้นที่น่าจับตาแบบ POI เป็นช่วงราคา (ภาพ 2) → แผนการอ่านเกม
สองฝั่งพร้อมจุดยกเลิกมุมมอง → สรุป → คำเตือนความเสี่ยง · น้ำเสียงนักวิเคราะห์
ลงท้าย "ครับ" · ใช้ bullet กับตัวหนาได้ (ต่างจากสัญญา A/B/C ที่ห้าม)

กติกาที่ทำให้ D ต่างจาก A/B/C:
- บทความอ่านจาก story artifact ก้อนเดียวกับที่ตัววาดใช้ — เลขทุกตัวในบท
  จึงชี้กลับไปที่เลขบนภาพได้เสมอ (ไม่มีเลขจากความจำหรือจากข่าว)
- ด่านตรวจ `validate` ทำงานแบบ fail-closed: เจอเลขที่ไม่อยู่ในทะเบียนของ story
  แม้ตัวเดียว = ตกทั้งบท (หลัก YMYL เดียวกับสายอื่นของ P002)
- POI เป็น "พื้นที่สังเกตการณ์" พร้อมเงื่อนไข ไม่ใช่คำสั่งซื้อขาย และฉากทัศน์ต้อง
  ประกาศตัวว่าเป็น "เงื่อนไข ไม่ใช่คำทำนาย" — ด่านบังคับ

สไตล์นี้ไม่อยู่ใน `WCB_WRITERS` โดยเจตนา (คำสั่งหัวหน้า 2026-08-06:
"ไม่นำไปใช้กับ A/B/C") — ทะเบียนและด่านของสองสายต้องแยกขาดจากกัน
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import chart_story, wcb_writers  # noqa: E402
from tools.chart_story_renderer import price_text, thai_date  # noqa: E402

STYLE_ID = "d_chart_story"
STYLE_NAME = "D — อ่านโครงสร้างกราฟ"
FOLDER = "D-โครงสร้างกราฟ"
# นับเฉพาะตัวอักษร — ภาษาไทยไม่เว้นวรรคระหว่างคำ นับคำแบบสายอื่นไม่ได้
# เกณฑ์ตั้งจากบทที่โครงครบแต่ตลาด "จนระดับ" (ไม่มีโซน/แนวต้านผ่านเกณฑ์เลย) ~1,700
# อักขระ ซึ่งยังเป็นบทที่ถูกต้อง · ของจริงข้อมูลครบจะได้ ~3,000+ · ต่ำกว่านี้ = โครงหาย
MIN_CHARS = 1500
_NUMBER = re.compile(r"\d[\d,\.]*")


def image_names(asset: str) -> tuple[str, str]:
    """ชื่อไฟล์ภาพคู่บท — เลขต่อท้ายคือลำดับที่บทความอ้างถึง"""
    return (f"{asset}-1.png", f"{asset}-2.png")


# ---------------------------------------------------------------- ตัวเขียนบท

def _channel_position(story: dict) -> str:
    """ตำแหน่งราคาปัจจุบันเทียบเส้นหลักของกรอบ — คำพูดต้องตามเลข ไม่ใช่ตามอารมณ์"""
    channel = story["channel"]
    if not channel:
        return ""
    edge = "ขอบบน" if channel["main_is_upper"] else "ขอบล่าง"
    gap = story["current"]["close"] - channel["main_at_last"]
    if channel["main_is_upper"]:
        if gap > 0:
            return (f"แท่งล่าสุดปิดเหนือแนว{edge}ของกรอบแล้ว "
                    "ซึ่งยังต้องรอการยืนยันว่ายืนได้จริง ไม่ใช่การทะลุหลอก")
        if abs(gap) <= story["atr14"]:
            return f"ราคากำลังทดสอบแนว{edge}ของกรอบอยู่พอดี"
        return f"ราคายังเคลื่อนอยู่ภายในกรอบ ต่ำกว่าแนว{edge}"
    if gap < 0:
        return (f"แท่งล่าสุดหลุดใต้แนว{edge}ของกรอบแล้ว "
                "ซึ่งยังต้องรอการยืนยันว่าหลุดจริง ไม่ใช่การหลุดหลอก")
    if gap <= story["atr14"]:
        return f"ราคากำลังทดสอบแนว{edge}ของกรอบอยู่พอดี"
    return f"ราคายังเคลื่อนอยู่ภายในกรอบ เหนือแนว{edge}"


def _headline_hook(story: dict) -> str:
    """วลีพาดหัวจากสภาพจริงของโครงสร้าง — เลือกจากเงื่อนไขที่วัดได้เท่านั้น"""
    channel = story["channel"]
    if channel and channel["main_is_upper"]:
        gap = story["current"]["close"] - channel["main_at_last"]
        if gap > 0:
            return "จังหวะวัดใจหน้ากรอบขาลง"
        if abs(gap) <= story["atr14"]:
            return "แรงดีดทดสอบขอบกรอบขาลง"
        return "ยังเดินอยู่ในกรอบขาลง"
    if channel and not channel["main_is_upper"]:
        return "โครงสร้างขาขึ้นยังคุมเกม"
    return "อ่านโครงสร้างราคารอบล่าสุด"


def render_article(story: dict) -> str:
    first_image, second_image = image_names(story["asset"])
    mode = "ขาลง" if story["regime"]["down"] else "ขาขึ้น"
    current_text = price_text(story["current"]["close"])
    zones = story["zones"]
    above = sorted(level["mean"] for level in story["resistance"])
    channel = story["channel"]

    lines = [
        f"# {story['symbol']}: {_headline_hook(story)} — มุมมองโครงสร้างราคา "
        f"{thai_date(story['current']['date'])}",
        "",
        # ---- บทนำแบบเล่าเรื่อง (ไม่มีหัวข้อ ตามบทอ้างอิง) ----
        f"{story['symbol']} เดินทางมาถึงจุดที่ต้องตัดสินใจครับ ราคาปิดล่าสุดที่ {current_text} ดอลลาร์ "
        f"ในวันที่โหมดตลาดตามเส้นค่าเฉลี่ย 50 วันยังเป็น{mode} "
        + (_channel_position(story) + " " if channel else "")
        + "บทวิเคราะห์ฉบับนี้จะพาไล่ดูตั้งแต่โครงสร้างรอบใหญ่ พื้นที่ที่ควรจับตา (POI) "
          "ไปจนถึงแผนการอ่านเกมทั้งสองฝั่ง โดยทุกเส้นทุกโซนบนภาพและตัวเลขทุกตัวในบท "
          "คำนวณจากแท่งราคาจริงทั้งหมด ไม่มีการวาดหรือประมาณขึ้นตามความรู้สึก",
        "",
        "## มุมมองเชิงโครงสร้าง: หนึ่งรอบวัฏจักรในภาพเดียว",
        "",
    ]

    story_para = (
        f"ภาพแรกคือแผนที่รอบใหญ่ย้อนหลัง {story['display']['bars']} แท่งรายวัน "
        f"ราคาไต่ขึ้นอย่างมีระเบียบตลอดขาขึ้นรอบก่อน จนทำจุดสูงสุดที่ "
        f"{price_text(story['peak']['high'])} ดอลลาร์เมื่อ {thai_date(story['peak']['date'])} "
        "จากนั้นเกมเปลี่ยน โครงสร้างกลายเป็นการไหลลงภายในกรอบแนวโน้มสีแดง ")
    if story["regime"]["flip_date"]:
        story_para += (
            f"เส้นหนาที่เปลี่ยนสีคือเส้นค่าเฉลี่ย 50 วัน — เขียวช่วงยกตัว แดงช่วงหัวลง — "
            f"ซึ่งพลิกเป็นโหมด{mode}มาตั้งแต่ {thai_date(story['regime']['flip_date'])} "
            "และยังไม่พลิกกลับ ")
    if channel:
        story_para += (
            f"ตัวกรอบลากผ่านจุดกลับตัวจริงบนกราฟรวม {channel['touch_count']} จุด "
            f"เริ่มนับจาก {thai_date(channel['start_date'])} "
            "ยิ่งราคาเคารพกรอบหลายครั้ง กรอบยิ่งเป็นแนวอ้างอิงที่ตลาดใช้ร่วมกันจริง")
    if zones:
        zone1 = zones[0]
        story_para += (
            f" ส่วนด้านล่าง แรงขายถูกรับไว้ซ้ำ ๆ บริเวณ {price_text(zone1['mean'])} ดอลลาร์ "
            f"รวม {zone1['touches']} ครั้งโดยไม่หลุด นี่คือรอยเท้าของแรงซื้อที่มองข้ามไม่ได้ครับ")
    lines += [story_para, "", f"![ภาพที่ 1 — โครงสร้างรอบใหญ่ {story['symbol']}]({first_image})", "",
              "## พื้นที่ที่น่าจับตา (POI)", ""]

    lines += [
        "จากโครงสร้างข้างบน ระบบกลั่นออกมาเป็นพื้นที่สังเกตการณ์ที่ราคาเคยพิสูจน์ตัวเองมาแล้วจริง "
        "ย้ำว่านี่คือพื้นที่รอดูปฏิกิริยาราคา ไม่ใช่จุดให้กระโดดเข้าเทรดทันทีครับ",
        "",
    ]
    if zones:
        zone1 = zones[0]
        poi1 = (f"- **POI 1 — โซนรับหลัก {price_text(zone1['low'])}–{price_text(zone1['high'])}:** "
                f"พื้นที่ที่ราคาลงมาแตะแล้วเด้งกลับ {zone1['touches']} ครั้ง ")
        if zone1["includes_week52_low"]:
            poi1 += "และครอบจุดต่ำสุดในรอบ 52 สัปดาห์ไว้ในตัว "
        poi1 += "ตราบใดที่ราคายืนเหนือโซนนี้ได้ ฝั่งซื้อยังถือแต้มต่อเชิงโครงสร้าง"
        lines.append(poi1)
        if len(zones) > 1:
            zone2 = zones[1]
            poi2 = (f"- **POI 2 — โซนรับลึก {price_text(zone2['low'])}–{price_text(zone2['high'])}:** "
                    f"ฐานเก่าที่เคยรับราคาไว้ {zone2['touches']} ครั้ง ")
            if zone2["includes_week52_low"]:
                poi2 += "และเป็นที่อยู่ของจุดต่ำสุดรอบ 52 สัปดาห์ "
            poi2 += "จะมีความหมายก็ต่อเมื่อ POI 1 ต้านไม่อยู่"
            lines.append(poi2)
    if above:
        resistance_text = (f"- **แนวต้านสำคัญ:** ชั้นแรกที่ {price_text(above[0])} ดอลลาร์ ")
        if len(above) > 1:
            resistance_text += f"ถัดขึ้นไปเป็น {price_text(above[1])} "
        if len(above) > 2:
            resistance_text += f"และ {price_text(above[2])} "
        resistance_text += "— ทุกเส้นมาจากจุดกลับตัวจริงในอดีต ไม่ใช่ตัวเลขกลม ๆ จากความรู้สึก"
        lines.append(resistance_text)
    if not zones and not above:
        lines.append("- หน้าต่างนี้ไม่มีระดับที่ผ่านเกณฑ์การแตะซ้ำของระบบ "
                     "จึงไม่มี POI ให้ระบุ และบทความจะไม่สร้างระดับขึ้นเองแทนครับ")
    # ---- จุดเข้าซื้อที่ได้เปรียบ (SMC POI) — ผู้ใช้สั่งเพิ่ม 2026-08-06 ----
    lines += ["", "## จุดเข้าซื้อที่ได้เปรียบ (SMC POI)", ""]
    entries = story["entries"]
    if entries:
        lines += [
            "หลักคิดแบบ SMC คือไม่ไล่ราคากลางอากาศ แต่รอให้ราคากลับมาหาพื้นที่ที่แรงซื้อ"
            "เคยแสดงตัวจริง ราคาแนะนำด้านล่างคือกึ่งกลางของโซนเหล่านั้น "
            "พร้อมจุดยกเลิกมุมมองชัดเจนทุกจุดครับ",
            "",
        ]
        for entry in entries:
            depth = ("โซนรับหลัก" if entry["rank"] == 1
                     else "โซนรับลึก — พื้นที่ได้เปรียบสูงสุด")
            lines.append(
                f"- **จุดเข้าซื้อ {entry['rank']} ที่ {price_text(entry['price'])} ดอลลาร์** "
                f"(ช่วง {price_text(entry['zone_low'])}–{price_text(entry['zone_high'])} · {depth}): "
                f"พื้นที่นี้รับราคามาแล้ว {entry['touches']} ครั้ง "
                "เข้าเมื่อราคากลับลงมาในช่วงและมีสัญญาณการกลับตัวยืนยันในไทม์เฟรมย่อยก่อนเสมอ "
                f"จุดยกเลิกมุมมอง: ราคาปิดวันต่ำกว่า {price_text(entry['invalidation'])} ดอลลาร์")
        if story["current"]["close"] > entries[0]["zone_high"]:
            lines += ["",
                      "เหตุที่ไม่แนะนำให้เข้าที่ราคาปัจจุบัน เพราะราคาลอยอยู่เหนือโซนแรก "
                      "การเข้ากลางช่องว่างคือการยอมเสียแต้มต่อ ทั้งจุดยกเลิกที่อยู่ไกล"
                      "และโอกาสโดนย่อทับ การรอให้ราคาลงมาหาเราคือหัวใจของแนวคิดนี้ครับ"]
    else:
        lines += ["รอบนี้ไม่มีโซนที่ผ่านเกณฑ์การแตะซ้ำ จึงไม่มีจุดเข้าที่ระบบกล้าแนะนำ "
                  "และจะไม่ตั้งราคาขึ้นเองจากความรู้สึกแทนครับ"]
    lines += ["", f"![ภาพที่ 2 — ระดับตัดสินใจ จุดเข้าซื้อ และฉากทัศน์]({second_image})", "",
              "## แผนการอ่านเกมสองฝั่ง", ""]

    scenario_lines = []
    up = story["scenarios"]["up"]
    if up:
        text = (f"**ฝั่งขึ้น:** กุญแจอยู่ที่{up['condition']} ({price_text(up['trigger'])} ดอลลาร์) "
                "ถ้าปิดเหนือได้จริงและไม่ใช่การทะลุหลอก")
        if up["targets"]:
            targets = " และ ".join(f"{price_text(value)}" for value in up["targets"])
            text += f" เส้นทางบนภาพเปิดไปหา {targets} ดอลลาร์ตามลำดับ"
        text += f" มุมมองนี้ตกทันทีเมื่อ{up['invalidation']}ครับ"
        scenario_lines.append(text)
    down = story["scenarios"]["down"]
    if down:
        text = (f"**ฝั่งลง:** ระวังเมื่อ{down['condition']} ({price_text(down['trigger'])} ดอลลาร์) "
                "เพราะแปลว่าแรงซื้อที่เคยรับอยู่ถอยแล้ว")
        if down["targets"]:
            targets = " และ ".join(f"{price_text(value)}" for value in down["targets"])
            text += f" พื้นที่รับถัดไปคือ {targets} ดอลลาร์"
        text += f" มุมมองนี้ตกทันทีเมื่อ{down['invalidation']}"
        scenario_lines.append(text)
    if not scenario_lines:
        scenario_lines.append("รอบนี้ไม่มีระดับที่ผ่านเกณฑ์พอจะตั้งเงื่อนไขได้ทั้งสองฝั่ง "
                              "ระบบจึงไม่ตั้งฉากทัศน์ และจะไม่ตั้งเป้าจากความรู้สึกแทนครับ")
    scenario_lines.append(
        "ระดับฉากทัศน์ที่กำกับไว้บนภาพที่สองเป็นเงื่อนไขสมมุติจากระดับที่คำนวณได้ "
        "ไม่ใช่คำทำนาย ราคาไม่จำเป็นต้องไปถึงระดับใดระดับหนึ่ง "
        "หน้าที่ของมันคือบอกล่วงหน้าว่าจุดไหนทำให้มุมมองเปลี่ยน ไม่ใช่บอกว่าพรุ่งนี้จะเกิดอะไร")
    for text in scenario_lines:
        lines += [text, ""]

    summary = (f"## สรุปประจำวัน\n\nวันนี้ทั้งกระดานย่อลงเหลือคำถามเดียวครับ — ")
    if up and zones:
        summary += (
            f"ราคาจะยืนยันแรงดีดด้วยการปิดเหนือ {price_text(up['trigger'])} ดอลลาร์ "
            f"หรือจะถูกตีกลับลงไปทดสอบโซนรับหลักอีกครั้ง "
            "คำตอบไม่ได้อยู่ที่การเดา แต่อยู่ที่ราคาปิดเทียบระดับที่ระบบวัดไว้ให้แล้วทั้งหมด")
    elif up:
        summary += (f"ราคาจะผ่านด่าน {price_text(up['trigger'])} ดอลลาร์ได้หรือไม่ "
                    "คำตอบอยู่ที่ราคาปิด ไม่ใช่การเดา")
    else:
        summary += ("โครงสร้างจะเลือกทางไหน คำตอบอยู่ที่ราคาปิดเทียบระดับบนภาพ ไม่ใช่การเดา")
    summary += (" กราฟทั้งสองใบกับตัวเลขทุกตัวในบทนี้มาจากแท่งราคาชุดเดียวกัน "
                "ตรวจย้อนกลับได้ครบทุกจุด")
    lines += [summary, "",
              "**คำเตือนความเสี่ยง:** บทวิเคราะห์นี้จัดทำจากโครงสร้างราคาเพื่อการศึกษาและติดตามตลาด "
              "ไม่ใช่คำแนะนำการลงทุน และไม่ใช่คำชักชวนให้ซื้อขายสินทรัพย์ใด ๆ "
              + wcb_writers._closing(),
              ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- ด่านตรวจ

def allowed_numbers(story: dict) -> set[str]:
    """ทะเบียนเลขที่บทความมีสิทธิ์พูดถึง — สร้างจาก story เท่านั้น"""
    allowed = {
        str(story["display"]["bars"]), str(story["display"]["zoom_bars"]),
        "1", "2", "3", "5", "50", "52", "200",
    }
    prices = [story["current"]["close"], story["peak"]["high"], story["trough"]["low"],
              story["week52_low"]]
    for level in story["resistance"]:
        prices.append(level["mean"])
        allowed.add(str(level["touches"]))
    for zone in story["zones"]:
        prices += [zone["mean"], zone["low"], zone["high"]]
        allowed.add(str(zone["touches"]))
    channel = story["channel"]
    if channel:
        allowed.add(str(channel["touch_count"]))
        prices += [channel["main_at_last"], channel["parallel_at_last"]]
    for side in ("up", "down"):
        scenario = story["scenarios"][side]
        if scenario:
            prices += [scenario["trigger"], *scenario["targets"]]
    for value in prices:
        allowed.add(price_text(value))
    dates = [story["current"]["date"], story["peak"]["date"], story["trough"]["date"],
             story["regime"]["flip_date"],
             story["display"]["start_date"], story["display"]["end_date"]]
    if channel:
        dates.append(channel["start_date"])
    dates += [zone["last_date"] for zone in story["zones"]]
    dates += [level["last_date"] for level in story["resistance"]]
    for date_text in dates:
        if not date_text:
            continue
        year, _month, day = date_text.split("-")
        allowed.add(year)
        allowed.add(str(int(day)))
    return allowed


def validate(markdown: str, story: dict) -> dict:
    """ด่านของสไตล์ D — fail-closed: findings ระดับ fatal ตัวเดียวก็ตก"""
    findings: list[dict] = []
    allowed = allowed_numbers(story)
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        for token in _NUMBER.findall(line):
            token = token.rstrip(".,")
            if token and token not in allowed:
                findings.append({
                    "rule": "number_not_in_story", "severity": "fatal", "line": line_number,
                    "message": f"เลข '{token}' ไม่อยู่ในทะเบียนของ story — "
                               "บทสไตล์ D พูดได้เฉพาะเลขที่อยู่บนภาพ",
                })
    for name in image_names(story["asset"]):
        if f"({name})" not in markdown:
            findings.append({
                "rule": "missing_image", "severity": "fatal", "line": 1,
                "message": f"บทความไม่ได้อ้างภาพ {name} — สไตล์ D ต้องอ้างครบทั้งสองภาพ",
            })
    if story.get("entries") and "จุดเข้าซื้อ" not in markdown:
        findings.append({
            "rule": "entry_section", "severity": "fatal", "line": 1,
            "message": "story มีจุดเข้าซื้อ (SMC POI) แต่บทไม่มีหัวข้อนี้ — ผู้ใช้สั่งให้มีเสมอ",
        })
    if "ไม่ใช่คำทำนาย" not in markdown:
        findings.append({
            "rule": "scenario_disclaimer", "severity": "fatal", "line": 1,
            "message": "ไม่พบประโยคประกาศว่าฉากทัศน์เป็นเงื่อนไข ไม่ใช่คำทำนาย",
        })
    if "คำเตือนความเสี่ยง" not in markdown:
        findings.append({
            "rule": "risk_disclaimer", "severity": "fatal", "line": 1,
            "message": "ไม่พบส่วนคำเตือนความเสี่ยงท้ายบท — โครงบทอ้างอิงบังคับให้มี",
        })
    if markdown.lstrip().startswith("---"):
        findings.append({
            "rule": "frontmatter_forbidden", "severity": "fatal", "line": 1,
            "message": "บทสไตล์ D ต้องไม่มี frontmatter",
        })
    char_count = len(re.sub(r"\s", "", markdown))
    if char_count < MIN_CHARS:
        findings.append({
            "rule": "style_length_floor", "severity": "fatal", "line": 1,
            "message": f"เนื้อหามี {char_count} อักขระ ต่ำกว่าเกณฑ์ {MIN_CHARS} ของสไตล์ D",
        })
    fatal_count = sum(1 for finding in findings if finding["severity"] == "fatal")
    return {
        "status": "pass" if fatal_count == 0 else "fail",
        "fatal_count": fatal_count,
        "char_count": char_count,
        "findings": findings,
    }
