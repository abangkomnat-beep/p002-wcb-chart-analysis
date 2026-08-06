"""นักเขียนสไตล์ D — บทวิเคราะห์อ่านโครงสร้างกราฟ + ด่านตรวจของสไตล์นี้เอง

สำนวนตามบทอ้างอิงที่หัวหน้าเลือก (th.investing.com/analysis/article-200458003):
เน้นบรรยาย + ศัพท์เทคนิคสาย SMC/Price Action หนาแน่น (Market Structure, Demand
Zone, Deep Discount, Smart Money, CHoCH, Stop Hunt, BOS, Dynamic Resistance,
Timeframe ย่อย) · จัดเรียงอ่านง่าย: ย่อหน้าสั้น หัวข้อย่อยตัวหนา bullet นำด้วยชื่อโซน

เส้นแบ่งที่ยึดไว้: **ศัพท์กรอบวิเคราะห์ใช้ได้ แต่ตัวเลขต้องมาจาก story เท่านั้น**
คำอย่าง "Liquidity ใต้โซน" เป็นภาษากรอบวิเคราะห์ (ตำรา SMC) ไม่ใช่ค่าที่วัด —
เขียนให้ชัดว่าเป็นการตีความตามแนวคิด ไม่แอบอ้างเป็นข้อมูล

กติกาที่ทำให้ D ต่างจาก A/B/C:
- บทความอ่านจาก story artifact ก้อนเดียวกับที่ตัววาดใช้ — เลขทุกตัวชี้กลับภาพได้
- ด่าน `validate` แบบ fail-closed: เลขนอกทะเบียน story ตัวเดียว = ตกทั้งบท
- จุดเข้าซื้อ (SMC POI) ต้องมีเมื่อระบบคำนวณได้ · ฉากทัศน์ต้องประกาศว่าเป็น
  "เงื่อนไข ไม่ใช่คำทำนาย" · ต้องมีคำเตือนความเสี่ยงท้ายบท — ด่านบังคับทั้งสามข้อ

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
# อักขระ ซึ่งยังเป็นบทที่ถูกต้อง · ของจริงข้อมูลครบจะได้ ~4,000+ · ต่ำกว่านี้ = โครงหาย
MIN_CHARS = 1500
_NUMBER = re.compile(r"\d[\d,\.]*")


AUTHOR = "ณัฐพล ศิริมงคล"   # byline ตามที่ระบบตั้งไว้ — ฟีดแบ็กหัวหน้า 08-06 (เรื่องเล็ก)


def image_name(asset: str, date_text: str) -> str:
    """ชื่อไฟล์ภาพประกอบใบเดียวของบท — ผู้ใช้สั่งรวมสองภาพ 2026-08-06 ดึก
    (แผงบน = ภาพรวมโครงสร้าง · แผงล่าง = ระยะใกล้พร้อมจุดเข้าซื้อและฉากทัศน์)
    ชื่อมีความหมาย+วันที่ ตามฟีดแบ็กหัวหน้า 08-06 (เรื่องเล็ก)"""
    return f"{asset}-d1-structure-{date_text}.png"


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
            return (f"แท่งล่าสุดปิดทะลุขึ้นเหนือแนว{edge}ของกรอบเป็นที่เรียบร้อย "
                    "ซึ่งยังต้องพิสูจน์ว่าเป็นการทะลุจริง ไม่ใช่ False Breakout")
        if abs(gap) <= story["atr14"]:
            return f"ราคากำลังชนแนว{edge}ของกรอบอยู่พอดี — จุดวัดใจของทั้งสองฝั่ง"
        return f"ราคายังเคลื่อนอยู่ภายในกรอบ ใต้แนว{edge}"
    if gap < 0:
        return (f"แท่งล่าสุดหลุดใต้แนว{edge}ของกรอบแล้ว "
                "ซึ่งยังต้องพิสูจน์ว่าเป็นการหลุดจริง ไม่ใช่ False Breakdown")
    if gap <= story["atr14"]:
        return f"ราคากำลังทดสอบแนว{edge}ของกรอบอยู่พอดี"
    return f"ราคายังเคลื่อนอยู่ภายในกรอบ เหนือแนว{edge}"


def _sma_position(story: dict) -> str:
    """ความสัมพันธ์ราคากับ SMA50 — แนวต้าน/แนวรับพลวัต พูดด้วยตัวเลขจริง"""
    sma50 = story["sma50_last"]
    if sma50 is None:
        return ""
    close = story["current"]["close"]
    if story["regime"]["down"]:
        if close >= sma50:
            return (f"ที่ต้องจับตาเป็นพิเศษคือราคาดันตัวกลับขึ้นมายืนเหนือเส้นค่าเฉลี่ย 50 วัน "
                    f"(ปัจจุบันอยู่ที่ {price_text(sma50)} ดอลลาร์) ที่ทำหน้าที่เป็นแนวต้านพลวัต "
                    "(Dynamic Resistance) กดราคามาตลอดรอบขาลง — นี่คือสัญญาณแรกว่าโมเมนตัม"
                    "ฝั่งขายเริ่มแผ่ว แต่หนึ่งสัญญาณยังไม่ใช่การกลับเทรนด์ ต้องรอโครงสร้างยืนยันครับ")
        return (f"ราคายังถูกกดอยู่ใต้เส้นค่าเฉลี่ย 50 วัน (ปัจจุบันอยู่ที่ {price_text(sma50)} "
                "ดอลลาร์) ที่ทำหน้าที่เป็นแนวต้านพลวัต (Dynamic Resistance) ของรอบขาลง "
                "ตราบใดที่ยังยืนเหนือเส้นนี้ไม่ได้ โมเมนตัมฝั่งขายยังคุมเกมอยู่ครับ")
    if close >= sma50:
        return (f"ราคายังยืนเหนือเส้นค่าเฉลี่ย 50 วัน (ปัจจุบันอยู่ที่ {price_text(sma50)} ดอลลาร์) "
                "ที่ทำหน้าที่เป็นแนวรับพลวัต (Dynamic Support) ของรอบขาขึ้น โครงสร้างยังแข็งแรงครับ")
    return (f"ราคาหลุดลงมาใต้เส้นค่าเฉลี่ย 50 วัน (ปัจจุบันอยู่ที่ {price_text(sma50)} ดอลลาร์) "
            "ซึ่งเคยเป็นแนวรับพลวัตของรอบขาขึ้น — สัญญาณเตือนแรกว่าโมเมนตัมกำลังเปลี่ยนมือครับ")


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
    combined_image = image_name(story["asset"], story["current"]["date"])
    down = story["regime"]["down"]
    current_text = price_text(story["current"]["close"])
    zones = story["zones"]
    above = sorted(level["mean"] for level in story["resistance"])
    channel = story["channel"]
    entries = story["entries"]

    # ---- บทนำแบบเล่าเรื่อง (Market Overview) ----
    if down:
        opening = (
            f"{story['symbol']} กำลังเขียนบทที่น่าติดตามที่สุดของรอบนี้ครับ "
            f"หลังจบรอบขาขึ้นใหญ่ด้วยการทำจุดสูงสุดที่ {price_text(story['peak']['high'])} ดอลลาร์"
            f"เมื่อ {thai_date(story['peak']['date'])} โครงสร้างตลาด (Market Structure) "
            "ก็พลิกเป็นขาลงเต็มตัว ราคาไล่ทำ Lower High และ Lower Low ต่อเนื่อง"
            f"ภายใน Bearish Channel จนแท่งล่าสุดปิดที่ {current_text} ดอลลาร์ ")
    else:
        opening = (
            f"{story['symbol']} ยังอยู่ในรอบขาขึ้นที่โครงสร้างแข็งแรงครับ ราคาไล่ทำ "
            "Higher High และ Higher Low ต่อเนื่องภายใน Bullish Channel "
            f"แท่งล่าสุดปิดที่ {current_text} ดอลลาร์ ")
    opening += _channel_position(story)
    opening += (
        " บทวิเคราะห์ฉบับนี้จะพาไล่ตั้งแต่โครงสร้างรอบใหญ่ ระดับสำคัญ "
        "จุดเข้าซื้อที่ได้เปรียบตามแนวคิด Smart Money "
        "ไปจนถึงแผนรับมือทั้งสองฝั่ง — ทุกเส้น ทุกโซน และตัวเลขทุกตัว "
        "คำนวณจากแท่งราคาจริงทั้งหมด ไม่มีเส้นใดวาดขึ้นตามความรู้สึก")
    lines = [
        f"# {story['symbol']}: {_headline_hook(story)} — บทวิเคราะห์โครงสร้างราคา "
        f"{thai_date(story['current']['date'])}",
        "",
        f"*โดย {AUTHOR}*",
        "",
        opening,
        "",
        "## โครงสร้างตลาด (Market Structure)",
        "",
    ]

    view_para = f"**มุมมองตลาด:** ภาพใหญ่ย้อนหลัง {story['display']['bars']} แท่งรายวันเล่าเรื่องครบหนึ่งวัฏจักร "
    if down:
        view_para += (
            "ขาขึ้นรอบก่อนไต่บันไดอย่างมีระเบียบ ก่อนแรงซื้อจะหมดเชื้อเพลิงบริเวณยอด "
            "แล้วเกิดการกระจายของ (Distribution) จนโครงสร้างหักลงเป็นขาลง ")
        if channel:
            view_para += (
                f"กรอบ Bearish Channel ที่ครอบการไหลลงลากผ่านจุดกลับตัวจริงรวม "
                f"{channel['touch_count']} จุด เริ่มนับจาก {thai_date(channel['start_date'])} "
                "— ยิ่งราคาเคารพกรอบหลายครั้ง กรอบยิ่งเป็นแนวอ้างอิงที่ตลาดใช้ร่วมกันจริง ")
        if zones:
            zone1 = zones[0]
            # การเล่าเรื่องจำนวนครั้งที่แตะ: ตามหลัก SMC โซนที่ถูกแตะซ้ำถือว่า
            # ถูกใช้ (mitigated) ไปมากแล้ว — ห้ามเล่าว่า "ยิ่งแตะยิ่งแข็ง"
            # (ฟีดแบ็กหัวหน้า 08-06 ข้อ 2 · เลือกทางเล่าแบบ "แนวอ้างอิงร่วมของตลาด")
            view_para += (
                f"ขณะเดียวกันด้านล่าง ตลาดใช้บริเวณ {price_text(zone1['mean'])} ดอลลาร์ "
                f"เป็นแนวอ้างอิงร่วมกันมาแล้ว {zone1['touches']} ครั้ง "
                "— แต่ต้องอ่านให้ถูกด้าน: ตามหลัก Price Action ออร์เดอร์ในโซน"
                "ถูกใช้ไปส่วนหนึ่งทุกครั้งที่ราคาลงมาแตะ การกลับมาครั้งถัดไปจึงเป็น"
                "บททดสอบของโซน ไม่ใช่หลักประกันว่าจะเด้ง "
                "ความหมายที่แท้จริงของระดับนี้คือ: ถ้าครั้งหน้าเอาไม่อยู่ "
                "นั่นคือสัญญาณเปลี่ยนโครงสร้างที่ทั้งตลาดเห็นพร้อมกัน — "
                "โครงสร้างแบบนี้จบได้สองทางเท่านั้น: ทะลุกรอบขึ้น หรือหลุดฐานลง")
    else:
        view_para += ("ราคายังรักษาลำดับ Higher High / Higher Low ไว้ได้ครบ "
                      "และยังไม่มีสัญญาณการกระจายของ (Distribution) ที่โครงสร้างยืนยัน")
    lines += [view_para, ""]

    momentum_para = "**โมเมนตัมและเส้นค่าเฉลี่ย:** เส้นหนาที่เปลี่ยนสีบนภาพคือเส้นค่าเฉลี่ย 50 วัน — เขียวช่วงยกตัว แดงช่วงหัวลง "
    if story["regime"]["flip_date"]:
        mode = "ขาลง" if down else "ขาขึ้น"
        momentum_para += (
            f"รอบนี้พลิกเป็นโหมด{mode}ตั้งแต่ {thai_date(story['regime']['flip_date'])} "
            "และยังไม่พลิกกลับ ")
    momentum_para += _sma_position(story)
    # alt text ใส่ตัวเลขระดับสำคัญ — ฟีดแบ็กหัวหน้า (เรื่องเล็ก) · เลขต้องมาจาก story
    alt_parts = [f"โครงสร้าง {story['symbol']} รายวัน"]
    if zones:
        alt_parts.append(f"โซนรับ {price_text(zones[0]['mean'])}")
    if above:
        alt_parts.append(f"แนวต้านแรก {price_text(above[0])}")
    lines += [momentum_para, "",
              f"![{' · '.join(alt_parts)} — แผงบนภาพรวม แผงล่างระดับตัดสินใจ]({combined_image})", "",
              "## ระดับสำคัญบนกระดาน (Key Levels)", ""]

    if zones or above:
        lines += ["ระดับทุกเส้นด้านล่างมาจากจุดกลับตัวจริงที่ถูกแตะซ้ำในอดีต "
                  "ไม่ใช่ตัวเลขกลม ๆ จากความรู้สึกครับ", ""]
    if zones:
        zone1 = zones[0]
        demand_line = (f"- **Demand Zone (POI 1) — {price_text(zone1['low'])}–{price_text(zone1['high'])}:** "
                       f"แนวอ้างอิงที่ตลาดใช้ร่วมกันมาแล้ว {zone1['touches']} ครั้ง ")
        if zone1["includes_week52_low"]:
            demand_line += "ครอบจุดต่ำสุดในรอบ 52 สัปดาห์ไว้ในตัว "
        demand_line += ("มุม SMC ต้องพูดตรง ๆ ว่าโซนที่ถูกแตะหลายครั้งถือว่าออร์เดอร์ถูกใช้ "
                        "(Mitigated) ไปมากแล้ว น้ำหนักจึงไม่ได้อยู่ที่จำนวนครั้ง "
                        "แต่อยู่ที่ปฏิกิริยาครั้งถัดไป: รับอยู่ = ระดับยังทำงาน · "
                        "หลุดพร้อมปิดวันใต้โซน = สัญญาณเปลี่ยนโครงสร้างที่ชัดที่สุดบนกระดาน")
        lines.append(demand_line)
        if len(zones) > 1:
            zone2 = zones[1]
            deep_line = (f"- **Deep Discount (POI 2) — {price_text(zone2['low'])}–{price_text(zone2['high'])}:** "
                         f"ฐานเก่าที่ตลาดเคยใช้อ้างอิง {zone2['touches']} ครั้ง ")
            if zone2["includes_week52_low"]:
                deep_line += ("และเป็นที่อยู่ของจุดต่ำสุดรอบ 52 สัปดาห์ — แนวรับเชิงเทคนิค"
                              "กับเชิงจิตวิทยาซ้อนกันพอดี ")
            if not zone2.get("daily_entry", True):
                deep_line += ("**หมายเหตุสำคัญ: นี่คือระดับกรอบหลายเดือน อยู่ห่างจากราคาปัจจุบันมาก "
                              "ใส่ไว้เพื่อให้เห็นภาพโครงสร้างใหญ่ ไม่ใช่ระดับสำหรับแผนรายวัน**")
            else:
                deep_line += "พื้นที่ราคาส่วนลดลึกในมุมมองเชิงโครงสร้างหากราคาลงมาถึง"
            lines.append(deep_line)
    if above:
        supply_line = (f"- **Supply / แนวต้านด้านบน:** ชั้นแรกที่ {price_text(above[0])} ดอลลาร์ ")
        if len(above) > 1:
            supply_line += f"ตามด้วย {price_text(above[1])} "
        if len(above) > 2:
            supply_line += f"และ {price_text(above[2])} "
        supply_line += ("— ทั้งหมดคืออดีต Swing High ที่ยังมีแรงขายค้าง (Unfilled Supply) "
                        "รอรับราคาอยู่หากเด้งขึ้นไปถึง")
        lines.append(supply_line)
    if not zones and not above:
        lines.append("- หน้าต่างนี้ไม่มีระดับที่ผ่านเกณฑ์การแตะซ้ำของระบบ "
                     "จึงไม่มีระดับให้ระบุ และบทความจะไม่สร้างระดับขึ้นเองแทนครับ")

    # ---- ตารางสรุประดับ — ฟีดแบ็กหัวหน้าข้อ 8 (ยืนยันแล้วว่าเว็บ render ตารางได้) ----
    if zones or above:
        lines += ["", "สรุปทุกระดับไว้ที่เดียวสำหรับคนที่สแกนอ่าน:", "",
                  "| ระดับ (ดอลลาร์) | ประเภท | ตำแหน่ง | เงื่อนไขที่ทำให้มุมมองเปลี่ยน |",
                  "|---|---|---|---|"]
        for order, value in enumerate(sorted(above, reverse=True)):
            tier = len(above) - order
            condition = ("ปิดวันเหนือระดับนี้ = Break of Structure ฝั่งขึ้น" if tier == 1
                         else f"เป้าถัดไปหากผ่านชั้นที่ {tier - 1} ได้")
            lines.append(f"| {price_text(value)} | Supply / แนวต้านชั้นที่ {tier} | เหนือราคา "
                         f"| {condition} |")
        if story["sma50_last"] is not None:
            sma50 = story["sma50_last"]
            side = "ใต้ราคา" if story["current"]["close"] >= sma50 else "เหนือราคา"
            flip = ("ราคากลับไปปิดใต้เส้น = โมเมนตัมคืนฝั่งขาย" if side == "ใต้ราคา"
                    else "ราคายืนเหนือเส้นได้ = โมเมนตัมเริ่มกลับฝั่งซื้อ")
            lines.append(f"| {price_text(sma50)} | เส้นค่าเฉลี่ย 50 วัน (แนวพลวัต) | {side} | {flip} |")
        for zone in zones:
            zone_label = ("Demand Zone (POI 1)" if zone["rank"] == 1
                          else "Deep Discount (POI 2)")
            if not zone.get("daily_entry", True):
                zone_label += " — กรอบหลายเดือน"
            lines.append(f"| {price_text(zone['low'])}–{price_text(zone['high'])} | {zone_label} "
                         f"| ใต้ราคา | ปิดวันต่ำกว่า {price_text(zone['low'])} = โครงสร้างเปลี่ยน |")

    # ---- จุดเข้าซื้อที่ได้เปรียบ (SMC POI) — ผู้ใช้สั่งเพิ่ม 2026-08-06 ----
    lines += ["", "## จุดเข้าซื้อที่ได้เปรียบ (SMC POI)", ""]
    if entries:
        lines += [
            "หลักคิดของ Smart Money Concepts คือไม่ไล่ราคากลางอากาศ "
            "แต่รอให้ราคากลับมาหาพื้นที่ที่แรงซื้อเคยแสดงตัวจริง "
            "ราคาแนะนำด้านล่างคือกึ่งกลางของโซนเหล่านั้น พร้อมจุดยกเลิกมุมมองชัดเจนทุกจุดครับ",
            "",
        ]
        for entry in entries:
            depth = ("Demand Zone หลัก" if entry["rank"] == 1
                     else "Deep Discount — พื้นที่ได้เปรียบสูงสุด")
            lines.append(
                f"- **จุดเข้าซื้อ {entry['rank']} ที่ {price_text(entry['price'])} ดอลลาร์** "
                f"(ช่วง {price_text(entry['zone_low'])}–{price_text(entry['zone_high'])} · {depth}): "
                f"โซนนี้ถูกใช้เป็นแนวอ้างอิงมาแล้ว {entry['touches']} ครั้ง — "
                "ยิ่งถูกใช้ซ้ำ ออร์เดอร์ในโซนยิ่งเหลือน้อย จึงต้องรอการยืนยันแรงซื้อจริง"
                "ก่อนเข้าเสมอ ไม่เข้าล่วงหน้า "
                f"จุดยกเลิกมุมมอง (Invalidation): ราคาปิดวันต่ำกว่า "
                f"{price_text(entry['invalidation'])} ดอลลาร์")
        excluded = [zone for zone in story["zones"] if not zone.get("daily_entry", True)]
        for zone in excluded:
            lines.append(
                f"- โซนลึกบริเวณ {price_text(zone['mean'])} ดอลลาร์ (POI {zone['rank']}) "
                "อยู่ห่างจากราคาปัจจุบันเกินเกณฑ์แผนรายวันของระบบ "
                "จึงไม่จัดเป็นจุดเข้าในบทนี้ — เป็นระดับเชิงโครงสร้างกรอบหลายเดือนเท่านั้น")
        execution = (
            "**Execution Plan:** อย่ารีบสวนมีดขณะราคากำลังร่วง และอย่าไล่ราคากลางช่องว่างครับ "
            "ให้รอราคาย่อกลับเข้าโซนก่อน แล้วสลับไป Timeframe ย่อย (1H/15M) "
            "เพื่อหาการยืนยันตัวตนของ Smart Money — เช่นการเกิด CHoCH (Change of Character) "
            "หรือ Stop Hunt ที่ราคาจิ้มกวาดสภาพคล่องใต้โซนแล้วดีดกลับอย่างรวดเร็ว — "
            "ได้สัญญาณยืนยันแล้วจึงค่อยพิจารณาเข้า ไม่มีสัญญาณ ไม่มีการเข้า")
        if story["current"]["close"] > entries[0]["zone_high"]:
            execution += (
                " เหตุที่ไม่แนะนำให้เข้าที่ราคาปัจจุบัน เพราะราคาลอยอยู่เหนือโซนแรกพอสมควร "
                "การเข้ากลางอากาศคือการยอมเสียทั้งแต้มต่อราคา (Risk to Reward) "
                "และตำแหน่งจุดตัดขาดทุนที่ดี — การรอให้ราคาลงมาหาเราคือหัวใจของแนวคิดนี้ครับ")
        lines += ["", execution]
    elif story["zones"]:
        lines += ["โซนรับที่ระบบวัดได้รอบนี้ทั้งหมดอยู่ห่างจากราคาปัจจุบันเกินเกณฑ์แผนรายวัน "
                  "จึงไม่มีจุดเข้าที่ระบบกล้าแนะนำในกรอบรายวัน "
                  "และจะไม่ขยับเกณฑ์เพื่อให้มีจุดเข้าครับ"]
    else:
        lines += ["รอบนี้ไม่มีโซนที่ผ่านเกณฑ์การแตะซ้ำ จึงไม่มีจุดเข้าที่ระบบกล้าแนะนำ "
                  "และจะไม่ตั้งราคาขึ้นเองจากความรู้สึกแทนครับ"]
    lines += ["", "## แผนการอ่านกราฟ", ""]

    scenario_lines = []
    up = story["scenarios"]["up"]
    if up:
        text = (f"**Bullish Scenario:** กุญแจอยู่ที่{up['condition']} "
                f"({price_text(up['trigger'])} ดอลลาร์) การปิดเหนือระดับนี้ได้จริง"
                "จะมีน้ำหนักเป็น Break of Structure (BOS) ฝั่งขึ้น")
        if up["targets"]:
            targets = " และ ".join(price_text(value) for value in up["targets"])
            text += f" เปิดทางเข้าหา Supply ถัดไปที่ {targets} ดอลลาร์ตามลำดับ"
        text += (f" มุมมองนี้ตกทันทีเมื่อ{up['invalidation']} "
                 "ซึ่งจะกลายเป็น False Breakout ที่มักตามด้วยแรงขายรอบใหม่ครับ")
        scenario_lines.append(text)
        # จุดเข้าฝั่งขึ้นพร้อมเลขยกเลิก — ฟีดแบ็กหัวหน้าข้อ 4 (เดิมฝั่งขึ้นไม่มีจุดเข้าเลย)
        scenario_lines.append(
            f"**จุดเข้าฝั่งขึ้น (Breakout-Continuation):** สำหรับคนที่อยากตามแรงดีด "
            "อย่าไล่ราคาตอนกำลังทะลุ — รอให้ปิดวันเหนือ "
            f"{price_text(up['trigger'])} ดอลลาร์ให้จบก่อน แล้วรอจังหวะราคาย่อกลับมาทดสอบ"
            f"แนวที่เพิ่งทะลุในช่วง {price_text(up['entry_low'])}–{price_text(up['entry_high'])} "
            "ดอลลาร์ (Retest — แนวต้านเดิมพลิกเป็นแนวรับ) พร้อมสัญญาณแรงซื้อใน Timeframe ย่อย "
            f"จุดยกเลิกมุมมอง (Invalidation): ราคาปิดวันกลับต่ำกว่า "
            f"{price_text(up['entry_invalidation'])} ดอลลาร์ — ถึงตรงนั้นการทะลุถือว่าล้มเหลว "
            "ไม่ถัวไม่รอครับ")
    down_scenario = story["scenarios"]["down"]
    if down_scenario:
        text = (f"**Bearish Scenario:** สัญญาณอันตรายคือ{down_scenario['condition']} "
                f"({price_text(down_scenario['trigger'])} ดอลลาร์) เพราะแปลว่า Demand Zone "
                "ถูกเจาะ แรงซื้อที่เคยรับอยู่ถอยกระดาน และโซนที่เคยเป็นแนวรับ"
                "จะพลิกบทบาทเป็นแนวต้าน (Role Reversal) ทันที")
        if down_scenario["targets"]:
            targets = " และ ".join(price_text(value) for value in down_scenario["targets"])
            text += f" เป้าถัดไปของฝั่งขายคือ {targets} ดอลลาร์"
        text += f" มุมมองนี้ตกทันทีเมื่อ{down_scenario['invalidation']}"
        scenario_lines.append(text)
    if not scenario_lines:
        scenario_lines.append("รอบนี้ไม่มีระดับที่ผ่านเกณฑ์พอจะตั้งเงื่อนไขได้ทั้งสองฝั่ง "
                              "ระบบจึงไม่ตั้งฉากทัศน์ และจะไม่ตั้งเป้าจากความรู้สึกแทนครับ")
    scenario_lines.append(
        "ระดับฉากทัศน์ที่กำกับไว้บนแผงล่างของภาพเป็นเงื่อนไขสมมุติจากระดับที่คำนวณได้ "
        "ไม่ใช่คำทำนาย ราคาไม่จำเป็นต้องไปถึงระดับใดระดับหนึ่ง "
        "หน้าที่ของมันคือบอกล่วงหน้าว่าจุดไหนทำให้มุมมองเปลี่ยน ไม่ใช่บอกว่าพรุ่งนี้จะเกิดอะไร")
    for text in scenario_lines:
        lines += [text, ""]

    # ---- ปัจจัยพื้นฐานจากปฏิทินจริง — ฟีดแบ็กหัวหน้าข้อ 3 · มติผู้ใช้ 08-06 ดึก:
    # ใช้ปฏิทินเศรษฐกิจที่วัดได้แทนลิงก์ข่าว (โรงงานข่าวของเว็บยังไม่ต่อ) ·
    # ระบบไม่เดาเหตุผลย้อนหลัง — เขียนได้เฉพาะกำหนดการข้างหน้าที่มีในข้อมูลจริง
    calendar = story.get("calendar")
    if calendar and calendar.get("sentences"):
        lines += ["## ปัจจัยพื้นฐานที่ต้องจับตา", "",
                  "กราฟบอกว่า \"ระดับไหนสำคัญ\" แต่ตัวที่มักเป็นชนวนให้ราคาวิ่งถึงระดับเหล่านั้น "
                  "คือกำหนดการเศรษฐกิจข้างหน้า รายการที่ใกล้ที่สุดจากปฏิทินจริงของระบบ:", ""]
        lines += [f"- {sentence}" for sentence in calendar["sentences"]]
        lines += ["",
                  "บทนี้จงใจไม่เดาย้อนหลังว่าราคาที่ผ่านมาขยับเพราะข่าวใด — "
                  "สิ่งที่ยืนยันได้จริงคือกำหนดการข้างหน้า และระดับราคาที่วัดได้บนกราฟครับ", ""]

    summary = "## สรุปประจำวัน\n\nทั้งกระดานวันนี้ย่อลงเหลือคำถามเดียวครับ — "
    if up and zones:
        summary += (
            f"ราคาจะยืนยันแรงดีดด้วย BOS เหนือ {price_text(up['trigger'])} ดอลลาร์ "
            "หรือจะถูก Supply ด้านบนตีกลับลงมาให้ Demand Zone ทำงานอีกครั้ง "
            "คำตอบไม่ได้อยู่ที่การเดา แต่อยู่ที่ราคาปิดเทียบระดับที่ระบบวัดไว้ให้แล้วทั้งหมด")
    elif up:
        summary += (f"ราคาจะผ่านด่าน {price_text(up['trigger'])} ดอลลาร์ได้หรือไม่ "
                    "คำตอบอยู่ที่ราคาปิด ไม่ใช่การเดา")
    else:
        summary += "โครงสร้างจะเลือกทางไหน คำตอบอยู่ที่ราคาปิดเทียบระดับบนภาพ ไม่ใช่การเดา"
    summary += (" กราฟกับตัวเลขทุกตัวในบทนี้มาจากแท่งราคาชุดเดียวกัน "
                "ตรวจย้อนกลับได้ครบทุกจุด")
    lines += [summary, "",
              "**คำเตือนความเสี่ยง:** บทวิเคราะห์นี้จัดทำจากโครงสร้างราคาเพื่อการศึกษาและติดตามตลาด "
              "ไม่ใช่คำแนะนำการลงทุน และไม่ใช่คำชักชวนให้ซื้อขายสินทรัพย์ใด ๆ "
              + wcb_writers._closing(),
              ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- ด่านตรวจ

def allowed_numbers(story: dict) -> set[str]:
    """ทะเบียนเลขที่บทความมีสิทธิ์พูดถึง — สร้างจาก story เท่านั้น

    "15" มาจาก Timeframe ย่อย 1H/15M ใน Execution Plan (ศัพท์กรอบวิเคราะห์ ไม่ใช่ค่าที่วัด)
    """
    allowed = {
        str(story["display"]["bars"]), str(story["display"]["zoom_bars"]),
        "1", "2", "3", "5", "15", "50", "52", "200",
    }
    prices = [story["current"]["close"], story["peak"]["high"], story["trough"]["low"],
              story["week52_low"]]
    for key in ("sma50_last", "sma200_last"):
        if story.get(key) is not None:
            prices.append(story[key])
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
            for key in ("entry_low", "entry_high", "entry_invalidation"):
                if scenario.get(key) is not None:
                    prices.append(scenario[key])
    for value in prices:
        allowed.add(price_text(value))
    # ชื่อไฟล์ภาพมีวันที่เต็มรูป (เช่น 2026-08-06) — เลขเดือน/วันแบบมีศูนย์นำ
    # ไม่ตรงกับทะเบียนวันที่ปกติ ต้องเพิ่มจากชื่อไฟล์ตรง ๆ
    for token in _NUMBER.findall(image_name(story["asset"], story["current"]["date"])):
        allowed.add(token.rstrip(".,"))
    # ประโยคปฏิทินมาจาก evidence จริงผ่าน `_calendar_sentences` — เลขในประโยค
    # (เวลา น. / ค่าครั้งก่อน) เป็นส่วนหนึ่งของ story จึงเข้าทะเบียนทั้งชุด
    calendar = story.get("calendar")
    if calendar and calendar.get("sentences"):
        for sentence in calendar["sentences"]:
            for token in _NUMBER.findall(sentence):
                allowed.add(token.rstrip(".,"))
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
    name = image_name(story["asset"], story["current"]["date"])
    if f"({name})" not in markdown:
        findings.append({
            "rule": "missing_image", "severity": "fatal", "line": 1,
            "message": f"บทความไม่ได้อ้างภาพ {name} — สไตล์ D ต้องอ้างภาพประกอบเสมอ",
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
