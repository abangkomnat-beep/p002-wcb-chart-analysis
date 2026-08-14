"""โครงร่วมของนักเขียนสไตล์ H/I/J + ด่านตรวจของสามสไตล์นี้

ข้อเสนอ §54–58 พูดข้อเดียวซ้ำหลายรอบ และมันถูก: **สไตล์ที่มีแต่ State Machine คือ
เครื่องปั๊มสัญญาณ ไม่ใช่สไตล์บทวิเคราะห์** จะเป็นสไตล์ได้ต้องครบสี่ชั้น

    ตรรกะวิเคราะห์ + โครงบทความ + ภาพประกอบ + คำอธิบายที่คนอ่านเข้าใจ

ไฟล์นี้คุมสามชั้นหลัง ส่วนชั้นแรกอยู่ในโมดูล `*_story.py` — และเส้นแบ่งนี้ปิดตาย:

⛔ **ตัวเขียนห้ามคำนวณ indicator · ห้ามสร้างระดับราคาใหม่ · ห้ามเปลี่ยนสถานะ ·
ห้ามเปลี่ยนบทที่ไม่มีทิศให้พาดหัวมีทิศ · ห้ามอ้างเหตุ-ผลที่ไม่มีในหลักฐาน ·
ห้ามเรียก ATR/ADX/CHOP/BandWidth ว่าขึ้นหรือลงในความหมายของทิศราคา**

ห้าข้อบนไม่ใช่คำเตือนลอย ๆ — ทุกข้อมีด่านเชิงกลไกอยู่ใน `validate()` ข้างล่าง
เพราะกฎที่ไม่มีด่านคือกฎที่จะถูกลืมในรอบที่งานเร่ง

โครงบทเป็นชุดเดียวทั้งสามสไตล์ (ข้อเสนอ §81) ต่างกันที่ *เนื้อ* ไม่ใช่ที่ *รูป* —
คนอ่านที่อ่านบท H เป็นแล้วต้องอ่าน I และ J เป็นทันทีโดยไม่ต้องเรียนโครงใหม่
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import consistency_gate, headline_format, image_output, market_calendar  # noqa: E402
from tools import intraday_bars, intraday_story, voice_rules, wcb_source, wcb_writers  # noqa: E402
from tools.chart_story_renderer import price_text, thai_date  # noqa: E402

# ความยาวบท — วัดด้วย `voice_rules.count_public_words` เท่านั้น
#
# ⚠️ **ห้ามใช้ `len()` หรือนับช่องว่าง** ภาษาไทยไม่เว้นวรรคระหว่างคำ นับแบบนั้นจะได้
# ตัวเลขต่ำกว่าจริงราวครึ่งหนึ่ง แล้วเพดานทั้งชุดจะหลวมโดยไม่มีใครรู้
# (บทเรียนเดียวกับ "งบความยาว Title 70" ที่เคยวัดด้วย `len()` แล้วเข้มเกินจริง 16%)
#
# 📏 **ช่วง 300–780 คำ — วัดจากบทจริงทั้งสามสไตล์ก่อนตั้ง ไม่ได้เดา**
# วัด 2026-08-13 ด้วยแท่งจริงของ BTCUSD: H = 797 · I = 820 · J = 915 คำ (ก่อนตัดความซ้ำ)
# หลังตัดความซ้ำออกแล้วอยู่ราว 700–770 ⇒ เพดาน 780 = ใบที่ยาวสุด + ระยะเผื่อเล็กน้อย
#
# **ทำไมสูงกว่าเกณฑ์บทรายวัน (350–560 ของ `voice_rules`)** ทั้งที่บทระหว่างวันควรสั้นกว่า:
# โครงของ H/I/J บังคับสองอย่างที่บทรายวันไม่มี — ย่อหน้าเชื่อมภาพกับข้อสรุปสองใบ
# (~110 คำ) · กล่องสถานะหัวบท ⇒ เป็น**ภาคบังคับตามข้อเสนอ §57–58** ไม่ใช่ความฟุ่มเฟือย
#
# มติผู้ใช้ 08-14: หัวข้ออธิบายศัพท์ (~90 คำ) ถูกถอดออกจากโครง — บทไม่อธิบายคำ
# พื้นต่ำจึงลดจาก 380 เหลือ 300 ตามคำที่หายไปทั้งหัว
#
# ต่ำกว่า 300 แปลว่ามีหัวข้อหายไปทั้งหัว (โครงมีห้าหัวข้อ + สองภาพ)
MIN_WORDS, MAX_WORDS = 300, 780

RULE = ("---", "")

H2_BOX = "## 📌 สรุปสถานะรอบนี้"
H2_EVIDENCE = "หลักฐานการวิเคราะห์ทีละชิ้น"
H2_WATCH = "ระดับและเงื่อนไขที่ต้องจับตา"
H2_INVALIDATION = "สัญญาณที่บอกว่ามุมมองนี้ไม่เป็นไปตามคาด"
# หัวข้ออธิบายศัพท์ (H2_GLOSSARY) ถูกถอด 08-14 ตามมติผู้ใช้ — บทไม่อธิบายคำ
# ⚠️ ต้องไม่ซ้ำกับข้อความในกล่อง `H2_BOX` — ด่านหัวข้อตรวจด้วยการหาสตริงในบท
# ถ้าสองชื่อเป็นสตริงย่อยของกัน หัวข้อหนึ่งหายไปแล้วด่านยังผ่าน (ตรวจของปลอมได้)
H2_SUMMARY = "สรุปแนวโน้มรอบนี้"

_NUMBER = re.compile(r"\d[\d,\.]*")

# คำกำกับท้ายการ์ดของภาพหลักแต่ละสไตล์ — อยู่ที่นี่เพราะทั้งตัวเขียนและตัววาดใช้
STYLE_FOOTER = {
    "H": "ภาพหลัก แรงเทรนด์และเส้น Supertrend",
    "I": "ภาพหลัก กรอบ Donchian และแท่งที่ใช้ตัดสิน",
    "J": "ชั้นบริบท Ichimoku",
}

# ------------------------------------------------------------------ ทะเบียนคำต้องห้าม
#
# ตัวชี้วัดที่ **ไม่มีสิทธิ์บอกทิศ** — ข้อเสนอ §5 อธิบายไว้ตรงประเด็นว่า ATR วัด
# ความผันผวน ไม่ใช่ทิศทาง · ADX วัดความแข็งแรง ไม่ใช่ทิศ (ทิศต้องมาจาก DI เท่านั้น)
# · CHOP บอกว่าสับหรือมีทิศ ไม่ได้บอกว่าทิศไหน · BandWidth บอกว่ากางหรือหด
NON_DIRECTIONAL = ("ATR", "ADX", "CHOP", "BandWidth", "BBW", "Choppiness")
# คำที่ถ้าไปอยู่ใกล้ชื่อข้างบนแปลว่าบทกำลังให้มันโหวตทิศ
DIRECTION_WORDS = ("ขาขึ้น", "ขาลง", "สัญญาณซื้อ", "สัญญาณขาย", "ฝั่งซื้อ", "ฝั่งขาย",
                   "ให้ซื้อ", "ให้ขาย", "Buy", "Sell", "เป็นบวก", "เป็นลบ",
                   "ชี้ขึ้น", "ชี้ลง", "บอกทิศ")
# ระยะที่ถือว่า "อยู่ใกล้กัน" — กว้างพอครอบประโยคย่อย แคบพอไม่จับคนละประโยค
NEAR_CHARS = 24

# คำโอ้อวดผลงานที่ห้ามใช้จนกว่าจะมี backtest บนข้อมูล P002 จริง (ข้อเสนอ §34–35)
PERFORMANCE_CLAIMS = ("แม่นยำ", "ชนะตลาด", "การันตี", "ทำกำไรได้แน่", "ความแม่นสูง",
                      "win rate", "Win Rate", "พิสูจน์แล้วว่าแม่น", "ไม่มีทางพลาด")
# คำของ "แผนการเทรด" ซึ่งเป็นงานของสายอื่น ไม่ใช่ของ H/I/J (ข้อเสนอ §26)
TRADE_PLAN_WORDS = ("จุดเข้าเทรด", "Stoploss", "Stop Loss", "Take Profit", "TP1",
                    "ทำกำไรที่", "ขนาดสัญญา", "Lot Size", "อัตราผลตอบแทนต่อความเสี่ยง")
# ร่องรอยของการนับคะแนนอินดิเคเตอร์ (ข้อเสนอ §5)
VOTE_WORDS = ("คะแนน", "โหวต", "เสียงส่วนใหญ่ของอินดิเคเตอร์")


# ------------------------------------------------------------------------ ตัวช่วยรูปแบบ

def money_for(story: dict):
    places = wcb_source.profile_for(story["asset"])["decimals"]
    return lambda value: price_text(value, places)


def one(value: float) -> str:
    """ทศนิยมหนึ่งตำแหน่ง — ค่าดัชนีอย่าง ADX/DI/CHOP/BandWidth"""
    return f"{value:.1f}"


def two(value: float) -> str:
    return f"{value:.2f}"


def whole(value: float) -> str:
    return f"{value:.0f}"


def plain(value: float) -> str:
    """เลขพารามิเตอร์ที่ต้องอ่านเหมือนที่เขียนใน config — `3.0` → `3` · `61.8` → `61.8`"""
    return f"{value:g}"


def tf_words(story: dict, timeframe: str | None = None) -> dict:
    spec = intraday_bars.spec_for(timeframe or story["timeframe"])
    code = (timeframe or story["timeframe"])
    return {"bar": f"แท่ง{spec['thai']}", "thai": spec["thai"], "short": spec["short"],
            "code": code, "front": {"15min": "M15", "30min": "M30"}.get(code, code.upper())}


def bar_clock(story: dict, key: str = "bar_at") -> str:
    """เวลาเริ่มแท่งฐานแบบไทย — `04.30` ไม่ใช่ `04:30` (ธรรมเนียมเดียวกับบทเช้า F/G)"""
    return str(story[key])[11:16].replace(":", ".")


def image_name(story: dict, spec, slot: str, timeframe: str | None = None) -> str:
    """ชื่อไฟล์ภาพ — ต้องมีทั้งตัวอักษรสไตล์ กรอบเวลา และวันที่

    ถ้าขาดกรอบเวลา ภาพ M15 กับ M30 ของหัวข้อเดียวกันในวันเดียวกันจะชื่อชนกันแล้ว
    ทับกันเงียบ ๆ (บทเรียนเดิมจากสายบทเช้า)

    ⚠️ `timeframe` ต้องเป็น**กรอบของภาพใบนั้น ไม่ใช่ของบท** — สไตล์ J มีภาพหลักเป็น
    กรอบใหญ่ (M30) แต่บทมีฐานเป็นกรอบเล็ก (M15) ⇒ ตั้งชื่อตามบทจะได้ไฟล์ที่ชื่อบอก
    กรอบหนึ่งแต่ข้างในเป็นอีกกรอบ ซึ่งเป็นข้อมูลผิดที่ตรวจไม่เจอด้วยด่านใด
    """
    code = timeframe or tf_words(story)["code"]
    return (f"{story['asset']}-{spec.LETTER.lower()}-{slot}-"
            f"{code}-{story['bar_date']}{image_output.IMAGE_SUFFIX}")


def figures(story: dict, spec) -> list[dict]:
    """ทะเบียนภาพของบทนี้ — ตัวเขียน ตัววาด และด่าน อ่านทะเบียนเดียวกัน

    ข้อเสนอ §80 สั่งให้ Writer รับข้อมูลรูป ไม่ใช่แค่ Story JSON — ทำที่นี่ที่เดียว
    เพื่อไม่ให้ชื่อไฟล์ในบทกับชื่อไฟล์ที่ตัววาดเซฟหลุดจากกันได้เลย
    """
    hero, evidence = spec.hero_figure(story), spec.evidence_figure(story)
    return [{"id": "fig1", "slot": "hero", **hero,
             "name": image_name(story, spec, "hero", hero.get("timeframe"))},
            {"id": "fig2", "slot": "evidence", **evidence,
             "name": image_name(story, spec, "evidence", evidence.get("timeframe"))}]


def checked_label(text: str) -> str:
    findings = consistency_gate.check_labels([text])
    if findings:
        raise ValueError(f"ข้อความประกอบภาพไม่ผ่านด่านความสอดคล้อง: {findings[0]['message']}")
    return text


# ------------------------------------------------------------------------ ประกอบบท

def stamp_line(story: dict, spec) -> str:
    """บรรทัดฐานข้อมูล — ต้องบอกกรอบเวลาและเวลาแท่งเสมอ

    บทระหว่างวันสองใบของวันเดียวกันต่างกันแค่เวลาแท่ง ถ้าไม่พิมพ์เวลากำกับ คนอ่าน
    แยกไม่ออกว่ากำลังอ่านของรอบไหน และ **บทเก่ากับบทใหม่จะดูเหมือนกันทุกประการ**
    """
    words = tf_words(story)
    return (f"ข้อมูล ณ {words['bar']}ที่ปิดแล้วของ {thai_date(story['bar_date'])} "
            f"เวลา {bar_clock(story)} น. (เวลาไทย)")


def frontmatter_lines(story: dict, spec) -> list[str]:
    title = headline_format.title(story["asset"], story["bar_date"], spec.title_tail(story))
    return [
        "---",
        f"asset: {story['asset']}",
        f"title: {wcb_writers.fit_title(title)}",
        f"excerpt: {wcb_writers.fit_excerpt(spec.excerpt_clauses(story))}",
        f"author_slug: {wcb_writers.author_slug_for(story['asset'])}",
        f"timeframe: {tf_words(story)['front']}",
        f"trend: {'dn' if story.get('direction') == 'down' else 'up'}",
        "---",
        "",
    ]


def _figure_block(figure: dict, index: int) -> list[str]:
    """ภาพหนึ่งใบ + คำอธิบายภาพ (+ ย่อหน้าเชื่อมภาพกับข้อสรุปถ้าสไตล์นั้นยังใช้)

    ข้อเสนอ §76 บังคับย่อหน้าเชื่อมไว้ตอนตั้งโครง เพราะภาพที่ไม่มีประโยคโยงกลับ
    ข้อสรุปคือของประดับ · **สไตล์ H ถอดย่อหน้านั้นออกตามใบที่ผู้ใช้สั่ง 08-14**
    (คำบรรยายใต้ภาพของ H ถูกเขียนใหม่ให้บอกทั้งว่าเห็นอะไรและเห็นไปทำไมในบรรทัดเดียว)
    ⇒ สไตล์ที่ไม่ส่งช่อง `explanation` มา = ไม่มีย่อหน้านั้น · I/J ยังส่งอยู่ตามเดิม
    """
    block = [f"![{checked_label(figure['alt'])}]({figure['name']})", "",
             f"*ภาพที่ {index}: {checked_label(figure['caption'])}*", ""]
    if figure.get("explanation"):
        block += [figure["explanation"], ""]
    return block


def _spec_text(spec, name: str, story: dict, default):
    """ค่าที่สไตล์ **แทนที่ได้** — ไม่ประกาศไว้ = ใช้ของกลาง

    รับได้ทั้งค่าคงที่และฟังก์ชันที่รับ story (หัวข้อบางหัวของ H เปลี่ยนถ้อยคำ
    ตามสถานะ) · ตัวช่วยนี้มีเพื่อให้ H เปลี่ยน *รูป* ได้โดยไม่ต้องแตกโครงเป็นสองชุด
    """
    value = getattr(spec, name, None)
    if value is None:
        return default
    return value(story) if callable(value) else value


def box_lines(story: dict, spec) -> list[str]:
    """กล่องสถานะหัวบท — ของกลางที่ I/J ใช้ (H เขียนกล่องของตัวเองผ่าน `box_lines`)"""
    money = money_for(story)
    return [H2_BOX,
            f"* **สถานะที่ระบบจัดให้:** {spec.state_phrase(story)}",
            f"* **กรอบเวลาที่ใช้ตัดสิน:** {spec.timeframe_phrase(story)}",
            f"* **ระดับที่ทำให้มุมมองนี้เสีย:** {money(story['invalidation']['level'])} "
            f"{wcb_source.profile_for(story['asset'])['unit_phrase']}"]


def render_article(story: dict, spec) -> str:
    """ประกอบบทหนึ่งใบตามโครงกลางของ H/I/J

    ลำดับบล็อกเป็นชุดเดียวทั้งสามสไตล์ · จุดที่สไตล์แทนที่ได้มีเท่าที่ระบุไว้ข้างล่าง
    เท่านั้น (พาดหัว · บรรทัดฐานข้อมูล · กล่องสรุป · ชื่อหัวข้อ · ระดับหัวข้อ ·
    หัวข้อสรุปท้ายบท) — ไม่ประกาศ = ได้ของกลางเหมือนเดิม
    """
    picture = figures(story, spec)
    heads = wcb_writers.SectionNumbers(prefix=getattr(spec, "SECTION_PREFIX", "##"))

    default_h1 = headline_format.h1(story["asset"], story["bar_date"], spec.h1_tail(story))
    lines = frontmatter_lines(story, spec)
    lines += [f"# {_spec_text(spec, 'h1_line', story, default_h1)}", "",
              f"*{_spec_text(spec, 'stamp_line', story, stamp_line(story, spec))}*", "",
              *RULE, *_spec_text(spec, "box_lines", story, box_lines(story, spec)), "",
              *RULE, heads.head(spec.h2_overview(story)), ""]
    lines += spec.overview_lines(story)
    lines += [""] if lines[-1] != "" else []
    lines += _figure_block(picture[0], 1)

    lines += [*RULE, heads.head(_spec_text(spec, "h2_evidence", story, H2_EVIDENCE)), ""]
    lines += spec.evidence_lines(story)
    lines += [""] if lines[-1] != "" else []
    lines += _figure_block(picture[1], 2)

    lines += [*RULE, heads.head(_spec_text(spec, "h2_watch", story, H2_WATCH)), ""]
    lines += spec.watch_lines(story)
    lines += [""] if lines[-1] != "" else []

    lines += [*RULE,
              heads.head(_spec_text(spec, "h2_invalidation", story, H2_INVALIDATION)), ""]
    lines += spec.invalidation_lines(story)
    lines += [""] if lines[-1] != "" else []

    # หัวข้อสรุปของ H ไม่มีเลขลำดับ (`### 💡 บทสรุปการเทรด`) ⇒ ต้องไม่เรียก
    # `heads.head()` เมื่อสไตล์แทนที่ไว้ ไม่งั้นตัวนับเลื่อนโดยไม่มีหัวข้อรองรับ
    summary_head = getattr(spec, "summary_head", None)
    summary_head = (heads.head(H2_SUMMARY) if summary_head is None
                    else summary_head(story) if callable(summary_head) else summary_head)
    lines += [*RULE, summary_head, ""]
    lines += spec.summary_lines(story)
    return "\n".join(lines).rstrip() + "\n"


# ------------------------------------------------------------------------ ทะเบียนเลข

def base_numbers(story: dict, spec) -> set[str]:
    """เลขที่บททุกสไตล์พูดได้ — สไตล์เติมของตัวเองผ่าน `spec.number_tokens`

    หลักเดียวกับสไตล์ D/E/F/G: **คำนวณซ้ำด้วยสูตรเดียวกับตอนเขียน ไม่ดูดจากข้อความ
    ที่เขียนไปแล้ว** — ถ้าดูดจากข้อความ ด่านจะรับรองเลขที่ตัวเองพิมพ์ผิด
    """
    money = money_for(story)
    values = {money(story["close"]), money(story["invalidation"]["level"]),
              # เลขลำดับหัวข้อ (ห้าหัว หลังถอดหัวข้อศัพท์ 08-14) + ลำดับภาพ
              "1", "2", "3", "4", "5"}
    clock = bar_clock(story)
    values |= {clock, clock.split(".")[0], clock.split(".")[1]}
    day, month, year = story["bar_date"].split("-")[::-1]
    values |= {str(int(day)), str(int(month)), year}
    words = tf_words(story)
    for text in (words["bar"], words["front"], words["short"], words["code"]):
        values |= {token.rstrip(".,") for token in _NUMBER.findall(text)}
    return values | set(spec.number_tokens(story))


# ------------------------------------------------------------------------ ด่านตรวจ

def _fatal(rule: str, line: int, message: str) -> dict:
    return {"rule": rule, "severity": "fatal", "line": line, "message": message}


def _direction_abuse(markdown: str) -> list[dict]:
    """ด่าน `atr_not_used_as_direction` + `adx_direction_not_inferred_without_di`

    จับที่ **ระยะห่างระหว่างชื่อกับคำบอกทิศ** ไม่ใช่จับทั้งชื่อ — บทต้องพูดถึง ATR
    และ ADX ได้ตามปกติ สิ่งที่ห้ามคือการให้มันบอกทิศ
    """
    findings = []
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        for name in NON_DIRECTIONAL:
            for match in re.finditer(re.escape(name), line):
                window = line[match.end():match.end() + NEAR_CHARS]
                for word in DIRECTION_WORDS:
                    if word in window:
                        findings.append(_fatal(
                            "indicator_direction_abuse", line_number,
                            f"บทให้ '{name}' บอกทิศด้วยคำว่า '{word}' — {name} "
                            "ไม่ใช่ตัวชี้ทิศ (ทิศมาจาก DI / โครงราคาเท่านั้น)"))
                        break
    return findings


def validate(markdown: str, story: dict, spec) -> dict:
    """ด่านของสไตล์ H/I/J — fatal ตัวเดียวก็ตกทั้งใบ ไม่มีการเตือนแล้วปล่อยผ่าน"""
    gate_story = {"regime": {"down": story.get("direction") == "down"}}
    findings: list[dict] = list(consistency_gate.check(markdown, gate_story))

    # ด่าน `intraday_bar_closed` — พิสูจน์ใหม่จากศูนย์ ไม่อ่านค่าธงในก้อนหลักฐาน
    closed_detail = intraday_bars.verify(story.get("candle_basis"), asset=story["asset"],
                                         bar_at=story["bar_at"])
    if closed_detail:
        findings.append(_fatal("intraday_bar_closed", 1,
                               f"บทอ้างแท่งที่ปิดแล้ว แต่ {closed_detail}"))

    # ด่าน `state_consistency` — สถานะที่บทประกาศต้องเป็นสถานะที่ story ตัดสินจริง
    if story["state"] not in spec.STATES:
        findings.append(_fatal("state_consistency", 1,
                               f"สถานะ '{story['state']}' ไม่อยู่ในทะเบียนของสไตล์นี้"))

    # ด่าน `headline_matches_state` — พาดหัวต้องพูดเรื่องเดียวกับสถานะ
    #
    # นี่คือด่านที่กันความผิดพลาดที่แพงที่สุดของสายนี้: สถานะกลาง ๆ แต่พาดหัวชี้ทิศ
    h1_line = next((line for line in markdown.splitlines() if line.startswith("# ")), "")
    keyword = spec.headline_keyword(story)
    if keyword and keyword not in h1_line:
        findings.append(_fatal(
            "headline_matches_state", 1,
            f"พาดหัวไม่มีคำว่า '{keyword}' ซึ่งเป็นคำประจำสถานะ {story['state']} "
            "— พาดหัวกับสถานะต้องเล่าเรื่องเดียวกัน"))
    if story.get("direction") is None:
        for word in ("ขาขึ้น", "ขาลง"):
            if word in h1_line:
                findings.append(_fatal(
                    "headline_matches_state", 1,
                    f"สถานะ {story['state']} ไม่ชี้ทิศ แต่พาดหัวเขียนว่า '{word}'"))

    findings += _direction_abuse(markdown)

    for phrase in PERFORMANCE_CLAIMS:
        if phrase in markdown:
            findings.append(_fatal(
                "performance_claim_forbidden", 1,
                f"พบคำโอ้อวดผลงาน '{phrase}' — สไตล์ระหว่างวันยังไม่มีผล backtest "
                "บนข้อมูลของระบบ จึงพูดเรื่องความแม่นหรือกำไรไม่ได้"))
    for phrase in TRADE_PLAN_WORDS:
        if phrase in markdown:
            findings.append(_fatal(
                "trade_plan_forbidden", 1,
                f"พบถ้อยคำแผนการเทรด '{phrase}' — H/I/J บอกสถานะและหลักฐานเท่านั้น "
                "การคิดจุดเข้า/จุดตัดขาดทุนเป็นงานของสายที่มีด่านความเสี่ยงของตัวเอง"))
    for phrase in VOTE_WORDS:
        if phrase in markdown:
            findings.append(_fatal(
                "indicator_vote_forbidden", 1,
                f"พบร่องรอยการนับเสียงอินดิเคเตอร์ ('{phrase}') — สไตล์นี้ให้แต่ละตัว"
                "ทำหน้าที่ของตัวเอง ไม่ใช่โหวตกัน"))

    # ด่าน `no_lookahead` เชิงโครงสร้าง — สองข้อที่พลาดแล้วมองไม่เห็นจากตัวบท
    if story["schema"].startswith("intraday-breakout") and not story["donchian"].get(
            "excludes_signal_bar"):
        findings.append(_fatal("donchian_excludes_signal_bar", 1,
                               "กรอบ Donchian รวมแท่งสัญญาณเข้าไปด้วย — แท่งนั้นจะ"
                               "ทะลุกรอบของตัวเองไม่ได้ตลอดกาล"))
    if story["schema"].startswith("intraday-pullback"):
        cloud = story["ichimoku"]["cloud_now"]
        if cloud.get("calculated_at") == cloud.get("plotted_at"):
            findings.append(_fatal(
                "ichimoku_displacement_valid", 1,
                "ค่าเมฆ Ichimoku ถูกคำนวณจากแท่งเดียวกับที่นำไปเทียบราคา — "
                "เมฆถูกพล็อตล่วงหน้า การเทียบแบบนี้คือการอ่านค่าที่ยังไม่เกิด"))

    for head in spec.required_headings(story):
        if head not in markdown:
            findings.append(_fatal("heading_missing", 1,
                                   f"บทขาดหัวข้อ '{head.strip()}' — โครงของ H/I/J บังคับ"))

    if "|" in markdown:
        findings.append(_fatal("table_forbidden", 1,
                               "พบอักขระตาราง '|' — บทสาธารณะห้ามตาราง"))

    # volume มีจริงเฉพาะหุ้น (ใบแจ้งหัวหน้า 2026-08-13) — ชนิดอื่นปลายทางส่ง null
    # ทุกแท่ง จึงไม่มีตัวเลขจริงให้อ้าง (วัดยืนยันแล้วกับ 15min/30min ทุกสัญลักษณ์)
    if market_calendar.for_asset(story["asset"]).asset_class \
            not in voice_rules.VOLUME_ALLOWED_INSTRUMENT_TYPES:
        for line_number, line in enumerate(markdown.splitlines(), start=1):
            volume_term = voice_rules.volume_term_in(line)
            if volume_term:
                findings.append(_fatal(
                    "volume_forbidden", line_number,
                    f"พบคำตระกูล volume \"{volume_term}\" ในบทของ {story['asset']} "
                    "— ข้อมูล volume มีจริงเฉพาะหุ้น ตลาด OTC ไม่มีตัวเลขให้อ้าง"))

    for figure in figures(story, spec):
        if f"({figure['name']})" not in markdown:
            findings.append(_fatal(
                "missing_image", 1,
                f"บทไม่ได้อ้างภาพ {figure['name']} — ภาพประกอบเป็นภาคบังคับของ H/I/J "
                "ไม่ใช่ของเสริม"))

    body = markdown.split("---", 2)[-1]
    word_count = voice_rules.count_public_words(body)
    if word_count < MIN_WORDS:
        findings.append(_fatal("article_too_short", 1,
                               f"เนื้อบท {word_count} คำ ต่ำกว่าเกณฑ์ {MIN_WORDS} "
                               "— น่าจะมีหัวข้อหายไปทั้งหัว"))
    if word_count > MAX_WORDS:
        findings.append(_fatal("article_too_long", 1,
                               f"เนื้อบท {word_count} คำ เกินเกณฑ์ {MAX_WORDS} "
                               "— บทระหว่างวันยาวกว่านี้คือกลายพันธุ์เป็นบทรายวัน"))

    allowed = base_numbers(story, spec)
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        if line.startswith("![") or line.startswith("title:") or line.startswith("excerpt:"):
            continue
        for token in _NUMBER.findall(line):
            token = token.rstrip(".,")
            if token and token not in allowed:
                findings.append(_fatal(
                    "number_not_in_story", line_number,
                    f"เลข '{token}' ไม่อยู่ในทะเบียนของ story — บทพูดได้เฉพาะเลขที่"
                    "คำนวณจริงจากแท่งที่ปิดแล้ว"))

    fatal = [item for item in findings if item.get("severity") == "fatal"]
    return {"ok": not fatal, "findings": findings, "style": story["style"],
            "style_name": spec.STYLE_NAME, "state": story["state"],
            "words": word_count}


def folder_for(story: dict, *, styles: dict | None = None) -> str:
    return intraday_story.style_entry(story["style"], styles=styles)["folder"]
