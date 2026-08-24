"""ชั้นเลือกว่า "รอบนี้บทไหนขึ้นเว็บ" — คนละคำถามกับ "บทไหนผลิตได้"

ตั้งแต่ 2026-08-06 หัวหน้าตอบใบคำถาม P002 ข้อ 3 ว่า **วันละ 1 บท เฉพาะทองคำ
สไตล์เดียว** ส่วนหัวข้ออื่นให้ผลิตเก็บไว้ได้แต่ยังไม่ขึ้นเว็บ

สายท่อจึงยังผลิตครบเหมือนเดิมทุกหัวข้อทุกสไตล์ (ห้ามลดกำลังผลิตเพราะนโยบายเผยแพร่
เปลี่ยน — วันที่นโยบายเปลี่ยนกลับจะไม่มีของเทียบ และงานที่หายไปจะเงียบ) แล้วชั้นนี้
วาง**สำเนาใบเดียว**ไว้ในโฟลเดอร์ที่ชี้ชัดว่าใบนี้คือใบที่ต้องเอาไปวาง

**ทำไมต้องมีโฟลเดอร์นี้ ทั้งที่คนเปิดหาไฟล์เองก็ได้:** เป็นทางส่งมอบแบบเดิมที่เลือก
ใบหลักหนึ่งใบให้หยิบง่าย · ตั้งแต่ 2026-08-21 ทีมเว็บยืนยัน `slug` แยก D/E แล้ว
จึงลง D/E วันเดียวกันได้เมื่อใช้สัญญา slug ที่ด่านของแต่ละสไตล์บังคับ

🆕 **ตั้งแต่ 2026-08-11 (ผู้ใช้สั่ง) ใบหลักของสาย A/B/C คือฉบับแนบภาพ** — `<asset>.md`
ที่วางไว้อ้างภาพซูมของเราเอง 2 ใบ (ต้องอัปโหลดรูปคู่ไปด้วย) · ใบหมุด `[[chart:]]`
เดิมย้ายไปเป็น `<asset>-หมุดกราฟ.md` ใช้เมื่อหน้าหลังบ้านไม่มีช่องแนบรูป
⇒ คุมด้วย `web_chart_mode` ในไฟล์นโยบาย กลับเป็น `"pins"` ได้โดยไม่แก้โค้ด

**โฟลเดอร์นี้สะท้อนรอบล่าสุดเสมอ** — ล้างก่อนเขียนทุกครั้ง เหตุผลเดียวกับ
`publish_layout._clear_stale`: ใบของเมื่อวานที่ค้างอยู่ในโฟลเดอร์ชื่อ "ขึ้นเว็บวันนี้"
คือกับดักที่แพงที่สุดของโฟลเดอร์แบบนี้

รันเดี่ยว ๆ ได้ (ปกติ `run_daily` เรียกให้เองท้ายรอบ):

    python -m tools.publish_selection ../output/06-08-2026
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import chart_story_writer, image_output, wcb_writers  # noqa: E402

POLICY_PATH = _REPO_ROOT / "config" / "publishing_policy.json"
READ_ME = "อ่านก่อน.md"

# สไตล์ D อยู่นอกทะเบียน `wcb_writers.WCB_WRITERS` โดยเจตนา (คำสั่งหัวหน้า 2026-08-06:
# "ไม่นำไปใช้กับ A/B/C" — ทะเบียนและด่านของสองสายต้องแยกขาดจากกัน) ⇒ ชั้นเลือกนี้
# ต้องรู้จักโฟลเดอร์ของ D เองแยกต่างหาก ไม่ใช่ไปยัดเข้าทะเบียนของ A/B/C
#
# D มีสัญญาส่งออกคนละฉบับกับ A/B/C แต่ทีมเว็บยืนยัน 2026-08-21 แล้วว่า
# รับ frontmatter + Markdown + ภาพ WebP ตามชื่อไฟล์ได้ · D ใช้ slug `levels`
# ส่วน E ใช้ `signals`; ด่านของนักเขียนบังคับรูปแบบก่อนออกไฟล์
_STYLE_FOLDERS_OUTSIDE_WCB_WRITERS = {"d_chart_story": chart_story_writer.FOLDER}

# 🆕 **ฉบับแนบภาพเป็นใบหลักตั้งแต่ 2026-08-11 (คำสั่งผู้ใช้)** — ก่อนหน้านี้เป็นแค่
# ทางเลือกวางคู่ใบหมุด แล้วให้คนเลือกเองหน้างาน ซึ่งเป็นการเลือกที่ตัดสินผิดได้ทุกวัน
#
# ทำไมสลับทั้งที่ใบหมุดยังใช้ได้: กราฟที่เว็บวาดจากหมุดเป็นมุมกว้างเกินไป (เหตุผลเดิม
# ที่สั่งทำภาพซูมเมื่อ 08-10) ⇒ ใบที่คนหยิบไปวางโดยไม่คิดควรเป็นใบที่ภาพถูกต้อง
#
# **ใบหมุดไม่ถูกลบทิ้ง** — ย้ายไปเป็น `<asset>-หมุดกราฟ.md` ในโฟลเดอร์เดียวกัน
# เพราะกติกา 08-09 บอกว่าหมุดใช้ได้เฉพาะนำเข้ามือ ถ้าวันไหนหน้าหลังบ้านไม่มีช่อง
# แนบรูป ใบหมุดคือทางเดียวที่ยังลงได้ · ลบทิ้ง = วันนั้นไม่มีบทขึ้นเว็บเลย
CHART_MODE_IMAGES = "attached_images"
CHART_MODE_PINS = "pins"
DEFAULT_CHART_MODE = CHART_MODE_IMAGES
PIN_FALLBACK_SUFFIX = "-หมุดกราฟ"


def chart_mode_for(policy: dict) -> str:
    """โหมดกราฟของใบขึ้นเว็บ — ค่าที่ไม่รู้จักต้องล้มดัง ไม่ใช่ตกไปโหมดตั้งต้นเงียบ ๆ

    เหตุผลเดียวกับ `style_folder`: พิมพ์ผิดในไฟล์นโยบายแล้วระบบยังเดินต่อได้ แปลว่า
    วันหนึ่งใบผิดแบบขึ้นเว็บโดยไม่มีใครรู้ว่าเปลี่ยนตอนไหน
    """
    mode = policy.get("web_chart_mode", DEFAULT_CHART_MODE)
    if mode not in (CHART_MODE_IMAGES, CHART_MODE_PINS):
        raise SelectionUnavailable(
            f"นโยบายชี้โหมดกราฟ '{mode}' ซึ่งไม่มีอยู่จริง "
            f"(มีอยู่: {CHART_MODE_IMAGES}, {CHART_MODE_PINS})")
    return mode


class SelectionUnavailable(RuntimeError):
    """เลือกใบขึ้นเว็บไม่ได้ — ต้องบอกว่าเพราะอะไร ห้ามวางโฟลเดอร์ว่างไว้เฉย ๆ

    โฟลเดอร์ว่างกับ "วันนี้ไม่มีบทให้ขึ้น" หน้าตาเหมือนกันเป๊ะ ⇒ ต้องมีใบอธิบาย
    วางแทนเสมอ ไม่งั้นคนเปิดจะคิดว่าระบบยังไม่ได้รัน
    """


def load_policy(path: Path | None = None) -> dict:
    return json.loads((path or POLICY_PATH).read_text(encoding="utf-8"))


def style_folder(writer_id: str) -> str:
    for writer in wcb_writers.WCB_WRITERS:
        if writer["id"] == writer_id:
            return writer["folder"]
    if writer_id in _STYLE_FOLDERS_OUTSIDE_WCB_WRITERS:
        return _STYLE_FOLDERS_OUTSIDE_WCB_WRITERS[writer_id]
    known = [w["id"] for w in wcb_writers.WCB_WRITERS] + list(_STYLE_FOLDERS_OUTSIDE_WCB_WRITERS)
    raise SelectionUnavailable(
        f"นโยบายชี้สไตล์ '{writer_id}' ซึ่งไม่มีในทะเบียนที่รู้จัก (มีอยู่: {', '.join(known)})")


def is_frontmatter_style(writer_id: str) -> bool:
    """คงชื่อเดิมเพื่อ compatibility: True คือสาย WCB_WRITERS; D แยกทางจัดภาพเอง"""
    return writer_id not in _STYLE_FOLDERS_OUTSIDE_WCB_WRITERS


def invalidate_if_selected(day_dir: Path, *, asset: str, style_id: str,
                           policy: dict | None = None) -> bool:
    """ล้างใบขึ้นเว็บที่ชี้ชุด D ซึ่งเพิ่ง fail เพื่อไม่ให้ของเก่าดูเหมือนของสด."""
    policy = policy or load_policy()
    if policy.get("web_asset") != asset or policy.get("web_style") != style_id:
        return False
    target = day_dir / policy.get("selection_folder", "0-ขึ้นเว็บวันนี้")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    folder = style_folder(style_id)
    (target / READ_ME).write_text(
        _missing_note(policy, folder, asset), encoding="utf-8")
    return True


def select(day_dir: Path, *, policy: dict | None = None) -> dict:
    """วางใบที่ต้องเอาขึ้นเว็บไว้ในโฟลเดอร์ของมัน แล้วคืนสรุปว่าเลือกใบไหนเพราะอะไร

    ไม่โยนเมื่อหาไฟล์ไม่เจอ — คืน `status: "missing"` พร้อมเหตุผล แล้ววางใบอธิบายไว้
    เพราะวันที่หัวข้อนั้นตกด่านเป็นเรื่องที่เกิดได้ตามปกติ (fail-closed ของด่านตรวจ)
    ไม่ใช่ระบบพัง ⇒ ไม่ควรทำให้ทั้งรอบ exit ไม่เป็นศูนย์
    """
    policy = policy or load_policy()
    asset = policy["web_asset"]
    folder = style_folder(policy["web_style"])
    target = day_dir / policy.get("selection_folder", "0-ขึ้นเว็บวันนี้")
    source = day_dir / folder / f"{asset}.md"

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    if not source.is_file():
        (target / READ_ME).write_text(_missing_note(policy, folder, asset), encoding="utf-8")
        return {"status": "missing", "asset": asset, "style_folder": folder,
                "expected": str(source), "directory": str(target)}

    placed = target / source.name
    shutil.copyfile(source, placed)
    images = []
    mode = CHART_MODE_PINS
    pin_fallback = None
    attach_variant = None
    if is_frontmatter_style(policy["web_style"]):
        # ภาพซูมของเราเอง (ผู้ใช้สั่ง 08-10 ค่ำ — กราฟจากหมุดมุมกว้างเกินไป):
        # ถ้ารอบผลิตวางชุด `<asset>-web-*.webp` + `<asset>-แนบภาพ.md` ไว้ ให้ตามมาด้วย
        # ไม่มีชุดนี้ = ใช้ใบหมุดตามเดิม ไม่ใช่ความผิดพลาด
        for image in sorted((day_dir / folder).glob(f"{asset}-web-*.webp")):
            image_output.verify(image)
            shutil.copyfile(image, target / image.name)
            images.append(image.name)
        variant_source = day_dir / folder / f"{asset}-แนบภาพ.md"
        fallback_source = day_dir / folder / f"{asset}{PIN_FALLBACK_SUFFIX}.md"
        # 🆕 สไตล์ที่เลิกมีใบหมุดสำรองโดยเจตนา (ธง `pin_fallback` ในทะเบียนนักเขียน —
        # A ตั้งแต่ 08-11 บ่าย ผู้ใช้สั่ง "เอาไฟล์ md -หมุดกราฟ ออกทั้งหมด"):
        # ห้ามพาใบหมุดตามไปหรือสร้างใหม่ในโฟลเดอร์ขึ้นเว็บ ไม่ว่าโฟลเดอร์สไตล์
        # จะเป็นโครงยุคไหน — ใบเดียวของสไตล์นั้นคือฉบับแนบภาพ
        keep_fallback = wcb_writers.by_id(policy["web_style"]).get("pin_fallback", True)
        if images and chart_mode_for(policy) == CHART_MODE_IMAGES:
            if fallback_source.is_file() and keep_fallback:
                # โครงใหม่ (ตั้งแต่ 08-11): `publish_layout` สลับให้ตั้งแต่โฟลเดอร์สไตล์แล้ว
                # ⇒ `<asset>.md` ที่เพิ่งคัดลอกมาคือฉบับแนบภาพอยู่ก่อนแล้ว แค่พาใบสำรองตามไป
                pin_fallback = fallback_source.name
                shutil.copyfile(fallback_source, target / pin_fallback)
                mode = CHART_MODE_IMAGES
            elif fallback_source.is_file():
                # ใบหมุดตกค้างจากยุคก่อนธงถูกปิด — ใบหลักสลับเป็นฉบับแนบภาพแล้ว
                # แค่ไม่พาใบสำรองตามไป (และไม่ถือเป็นของหาย)
                mode = CHART_MODE_IMAGES
            elif variant_source.is_file():
                # โครงเก่า (โฟลเดอร์วันที่ผลิตก่อน 08-11 แล้วเอามารันชั้นนี้ซ้ำ) — สลับที่นี่
                # แทน · ถ้าไม่รองรับ ใบหมุดจะกลายเป็นใบหลักเงียบ ๆ ทั้งที่นโยบายสั่งแนบภาพ
                #
                # เขียนทับด้วย `write_text` แทนการ rename ไขว้กันสองไฟล์ เพราะขั้นตอน
                # rename ไขว้ที่ล้มกลางทางจะเหลือโฟลเดอร์ที่ไม่มี `<asset>.md` เลย ซึ่ง
                # หน้าตาเหมือน "วันนี้ตกด่าน" ทั้งที่บทผ่านแล้ว
                if keep_fallback:
                    pin_fallback = f"{asset}{PIN_FALLBACK_SUFFIX}.md"
                    (target / pin_fallback).write_text(
                        placed.read_text(encoding="utf-8"), encoding="utf-8")
                placed.write_text(variant_source.read_text(encoding="utf-8"),
                                  encoding="utf-8")
                mode = CHART_MODE_IMAGES
            elif not keep_fallback:
                # โครงใหม่ของสไตล์ไร้ใบหมุด: `<asset>.md` เป็นฉบับแนบภาพอยู่แล้ว
                # และไม่มีใบสำรองให้พาไปโดยออกแบบ
                mode = CHART_MODE_IMAGES
        elif images and variant_source.is_file():
            # โหมดหมุด (ทางถอยของ 08-10): ใบหลักยังเป็นหมุด ฉบับแนบภาพวางคู่ไว้เฉย ๆ
            attach_variant = variant_source.name
            shutil.copyfile(variant_source, target / attach_variant)
    if not is_frontmatter_style(policy["web_style"]):
        # D ฝังรูปเป็นไฟล์ภาพจริง (ไม่ใช้หมุดกราฟแบบ A/B/C) — ต้องคัดลอกตามไปด้วย
        # ไม่งั้นไฟล์ .md ที่วางไว้จะอ้างรูปที่ไม่มีอยู่ในโฟลเดอร์เดียวกัน
        #
        # ด่านสุดท้ายก่อนถึงมือเว็บ (กติกา 08-09): ทุกใบต้อง .webp และไม่เกิน 200 KB
        # ตรวจซ้ำที่นี่ทั้งที่ตัววาดตรวจไปแล้ว เพราะโฟลเดอร์วันเป็นของที่คนแก้ด้วยมือได้
        # และรูปที่ถูกวางไว้ตั้งแต่ยุคก่อน 08-09 ยังหน้าตาเหมือนของสดทุกประการ
        # ตก = ยก ImageGateError ทั้งรอบ ไม่วางใบครึ่ง ๆ ที่เว็บจะตีกลับทั้งบท
        for image in sorted((day_dir / folder).glob(f"{asset}-*")):
            if not image_output.is_web_image(image):
                continue
            image_output.verify(image)
            shutil.copyfile(image, target / image.name)
            images.append(image.name)
        image_output.verify_folder(target)
    (target / READ_ME).write_text(
        _ready_note(policy, folder, asset, source.name, images,
                    attach_variant=attach_variant, chart_mode=mode,
                    pin_fallback=pin_fallback), encoding="utf-8")
    return {"status": "ready", "asset": asset, "style_folder": folder,
            "article": str(placed), "images": images,
            "chart_mode": mode, "pin_fallback": pin_fallback,
            "attach_variant": attach_variant, "directory": str(target)}


def _ready_note(policy: dict, folder: str, asset: str, filename: str,
                images: list[str] | None = None,
                attach_variant: str | None = None,
                chart_mode: str = CHART_MODE_PINS,
                pin_fallback: str | None = None) -> str:
    others = ", ".join(policy.get("produced_but_not_published") or []) or "— ไม่มี"
    frontmatter_style = is_frontmatter_style(policy["web_style"])
    if frontmatter_style and chart_mode == CHART_MODE_IMAGES:
        image_list = "` และ `".join(images or [])
        how_to = [
            f"เปิดไฟล์ **`{filename}`** ในโฟลเดอร์นี้ คัดลอกทั้งไฟล์ไปวางในหน้าหลังบ้าน",
            f"**แล้วอัปโหลดรูปในโฟลเดอร์นี้ด้วยทั้ง 2 ใบ:** `{image_list}`",
            "บทอ้างรูปสองใบนี้ตรง ๆ — ไม่อัปโหลด = ช่องกราฟว่างทั้งบท",
            "",
            "> 🆕 **ใบหลักเป็นฉบับแนบภาพตั้งแต่ 2026-08-11 (ผู้ใช้สั่ง)** — เดิมเป็นใบหมุด "
            "`[[chart:...]]` ที่ให้เว็บวาดเอง แต่กราฟที่ได้เป็นมุมกว้างเกินไป",
        ]
        if pin_fallback:
            how_to += [
                "",
                "## ถ้าหน้าหลังบ้านไม่มีช่องแนบ/อัปโหลดรูป",
                "",
                f"ใช้ **`{pin_fallback}`** ในโฟลเดอร์นี้แทน — เป็นบทเดียวกันเป๊ะ ต่างแค่ใช้หมุด "
                "`[[chart:...]]` ให้เว็บวาดกราฟเอง (ใช้เวลา 5–15 วินาที) และไม่ต้องอัปรูป",
                "⛔ **ห้ามใช้สองฉบับพร้อมกัน** — เว็บตั้งชื่อบทจากสินทรัพย์+วันที่ ใบหลังทับใบแรกเงียบ ๆ",
            ]
        else:
            how_to += [
                "",
                "> ℹ️ สไตล์นี้**ไม่มีใบหมุดสำรองแล้ว** (ผู้ใช้สั่งเลิก 2026-08-11) — "
                "ถ้าหน้าหลังบ้านไม่มีช่องแนบรูป ให้แจ้ง CC ก่อน อย่าดัดแปลงไฟล์เอง",
            ]
    elif frontmatter_style:
        how_to = [
            f"เปิดไฟล์ **`{filename}`** ในโฟลเดอร์นี้ คัดลอกทั้งไฟล์ไปวางในหน้าหลังบ้าน",
            "ระบบเว็บอ่านส่วนหัวเองและวาดกราฟจากหมุด `[[chart:...]]` ให้ (ใช้เวลา 5–15 วินาที)",
        ]
        if attach_variant:
            image_list = "` และ `".join(images or [])
            how_to += [
                "",
                "## 🆕 ทางเลือกแก้กราฟมุมกว้าง (ผู้ใช้สั่ง 08-10)",
                "",
                f"มีฉบับ **`{attach_variant}`** ที่แทนหมุดด้วยภาพซูมของเราเอง 2 ใบ: `{image_list}`",
                "**ถ้าหน้าหลังบ้านมีช่องแนบ/อัปโหลดรูป:** ใช้ฉบับนี้ + อัปโหลดรูปทั้งสองใบ",
                "**ถ้าไม่มีช่องแนบรูป:** ใช้ใบหมุดตามเดิม (ฉบับแนบภาพจะอ้างรูปที่ไปไม่ถึงเว็บ ห้ามใช้)",
                "⛔ **ห้ามใช้สองฉบับพร้อมกัน** และผลการลองครั้งแรกให้แจ้ง CC บันทึกเป็นคำตอบถาวร",
            ]
    else:
        image_list = "` และ `".join(images or [])
        image_count = len(images or [])
        how_to = [
            f"**สไตล์นี้ (D — อ่านโครงสร้างกราฟ) เป็นคนละสัญญากับ A/B/C**",
            f"ไฟล์ **`{filename}`** มี frontmatter พร้อม `slug` และมี H1 ของบทหนึ่งตำแหน่ง",
            f"ต้องอัปโหลดรูปแนบทั้งหมด {image_count} ใบด้วย: `{image_list}` "
            "— บทความอ้างอิงรูปเหล่านี้ตรง ๆ",
            "ไม่มีหมุด `[[chart:...]]` ให้เว็บวาดเองเหมือน A/B/C",
            "",
            "**ทีมเว็บยืนยัน 2026-08-21 แล้วว่าหน้าหลังบ้านรับ Markdown และภาพแนบรูปแบบนี้ได้**",
        ]
    return "\n".join([
        "# ใบที่ต้องเอาขึ้นเว็บรอบนี้",
        "",
        *how_to,
        "",
        "> **กดแล้วขึ้นเว็บทันที ไม่มีคิวรอตรวจ** — คนอ่านเห็นเลย",
        "> ลบออกได้ที่หน้าเดียวกันถ้าพลาด",
        "",
        "## ทำไมมีใบเดียว",
        "",
        f"- นโยบายรอบนี้: **วันละ {policy.get('articles_per_day', 1)} บท** · หัวข้อ **{asset}** · สไตล์ **{folder}**",
        f"- ผู้ตัดสิน: {policy.get('decided_by', '—')}",
        f"- เหตุผล: {policy.get('reason', '—')}",
        "",
        "## หัวข้ออื่นของวันนี้",
        "",
        f"ผลิตครบและผ่านด่านแล้วเหมือนเดิม ({others}) แต่**ยังไม่ขึ้นเว็บ**",
        "อยู่ในโฟลเดอร์สไตล์ข้าง ๆ ตามปกติ ใช้อ่านภายในและเก็บเป็นของเทียบได้",
        "",
        "> D/E วางวันเดียวกันได้เมื่อใช้ slug `levels`/`signals` ตามสัญญา; "
        "สไตล์อื่นยังห้ามวางร่วมวันจนกว่าจะมี slug ของตัวเอง",
        "",
    ])


def _missing_note(policy: dict, folder: str, asset: str) -> str:
    return "\n".join([
        "# รอบนี้ยังไม่มีใบให้ขึ้นเว็บ",
        "",
        f"นโยบายชี้ให้ใช้ **{asset}** สไตล์ **{folder}** แต่รอบนี้ไม่มีไฟล์นั้นในโฟลเดอร์วัน",
        "",
        "แปลว่าอย่างใดอย่างหนึ่ง — เปิดบรรทัดสรุปของรอบเพื่อดูว่าอันไหน:",
        "",
        "1. หัวข้อนั้น**ตกด่านตรวจ** ⇒ ไม่มีไฟล์ตามกติกา fail-closed (พฤติกรรมถูก)",
        "2. สายท่อสะดุดก่อนถึงหัวข้อนั้น เช่นดึงข้อมูลไม่ได้หรือก้อนไม่สด",
        "",
        "**ห้ามหยิบสไตล์อื่นหรือหัวข้ออื่นขึ้นแทนเอง** — นโยบายเผยแพร่ผ่านผู้ใช้มา",
        "การสลับเองทำให้วันที่มีปัญหากับวันปกติแยกไม่ออกบนหน้าเว็บ",
        "",
    ])


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        print("ใช้: python -m tools.publish_selection <โฟลเดอร์วัน เช่น ../output/06-08-2026>")
        return 2
    result = select(Path(args[0]))
    if result["status"] == "ready":
        print(f"ใบขึ้นเว็บรอบนี้: {result['article']}")
        return 0
    print(f"ยังไม่มีใบให้ขึ้นเว็บ — คาดว่าจะเจอที่ {result['expected']} "
          f"(ดูคำอธิบายใน {result['directory']}/{READ_ME})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
