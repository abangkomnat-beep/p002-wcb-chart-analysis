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

**Lane ที่ชั้นนี้เป็นเจ้าของสะท้อนรอบล่าสุดเสมอ** — ล้างเฉพาะ Lane นั้นก่อนเขียน
ห้ามล้าง `0-ขึ้นเว็บวันนี้` ทั้งราก เพราะรากเดียวกันมี Lane ของทอง BTC และ Forex

รันเดี่ยว ๆ ได้ (ปกติ `run_daily` เรียกให้เองท้ายรอบ):

    python -m tools.publish_selection ../output/06-08-2026
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import (chart_story_writer, image_output, trade_plan_public_contract,
                   wcb_writers)  # noqa: E402

POLICY_PATH = _REPO_ROOT / "config" / "publishing_policy.json"

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
DEFAULT_SELECTION_LANE = "01-Primary-Selection"


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
    """เลือกใบขึ้นเว็บไม่ได้ — หยุดและรายงานสาเหตุทางคอนโซลให้ชัดเจน"""


def load_policy(path: Path | None = None) -> dict:
    return json.loads((path or POLICY_PATH).read_text(encoding="utf-8"))


def selection_target(day_dir: Path, policy: dict) -> Path:
    """Return the one lane owned by the primary selector; siblings are protected."""
    root = day_dir / policy.get("selection_folder", "0-ขึ้นเว็บวันนี้")
    lane = str(policy.get("selection_lane") or DEFAULT_SELECTION_LANE)
    if not lane or lane in (".", "..") or Path(lane).name != lane:
        raise SelectionUnavailable(f"selection_lane ไม่ปลอดภัย: {lane!r}")
    return root / lane


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
    if policy.get("schema_version") == 2:
        removed = False
        root = day_dir / policy.get("selection_folder", "0-ขึ้นเว็บวันนี้")
        for lane in policy.get("upload_lanes", []):
            if lane.get("style") != style_id:
                continue
            lane_assets = lane.get("assets", [lane.get("asset")])
            if asset not in lane_assets:
                continue
            target = root / str(lane.get("destination_folder", ""))
            if target.is_dir():
                shutil.rmtree(target)
                removed = True
        return removed
    if policy.get("web_asset") != asset or policy.get("web_style") != style_id:
        return False
    target = selection_target(day_dir, policy)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    return True


def select(day_dir: Path, *, policy: dict | None = None) -> dict:
    """วางใบที่ต้องเอาขึ้นเว็บไว้ในโฟลเดอร์ของมัน แล้วคืนสรุปว่าเลือกใบไหนเพราะอะไร

    ไม่โยนเมื่อหาไฟล์ไม่เจอ — คืน `status: "missing"` พร้อมเหตุผลทางคอนโซล
    เพราะวันที่หัวข้อนั้นตกด่านเป็นเรื่องที่เกิดได้ตามปกติ (fail-closed ของด่านตรวจ)
    ไม่ใช่ระบบพัง ⇒ ไม่ควรทำให้ทั้งรอบ exit ไม่เป็นศูนย์
    """
    policy = policy or load_policy()
    if policy.get("schema_version") == 2:
        return select_lanes(day_dir, policy=policy)
    asset = policy["web_asset"]
    folder = style_folder(policy["web_style"])
    target = selection_target(day_dir, policy)
    source = day_dir / folder / f"{asset}.md"

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    if not source.is_file():
        reason = (f"นโยบายชี้ให้ใช้ {asset} สไตล์ {folder} "
                  "แต่รอบนี้ไม่มีไฟล์นั้นในโฟลเดอร์วัน")
        return {"status": "missing", "asset": asset, "style_folder": folder,
                "expected": str(source), "reason": reason, "directory": str(target)}

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
    return {"status": "ready", "asset": asset, "style_folder": folder,
            "article": str(placed), "images": images,
            "chart_mode": mode, "pin_fallback": pin_fallback,
            "attach_variant": attach_variant, "directory": str(target)}


_DAY_RE = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")
_IMAGE_REF_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def _frontmatter(article: Path) -> dict[str, str]:
    match = _FRONTMATTER_RE.match(article.read_text(encoding="utf-8"))
    if not match:
        return {}
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _safe_child(root: Path, name: str, *, field: str) -> Path:
    if (not isinstance(name, str) or not name or Path(name).is_absolute()
            or Path(name).name != name or name in {".", ".."}):
        raise SelectionUnavailable(f"{field} ไม่ปลอดภัย: {name!r}")
    return root / name


def _lane_assets(lane: dict, publish_date: str) -> list[str]:
    configured = lane.get("assets")
    if configured == "scheduled_forex":
        from tools import forex_daily_plan
        return forex_daily_plan.scheduled_assets(f"{publish_date}T12:00:00+07:00")
    if not isinstance(configured, list) or not configured or any(
            not isinstance(asset, str) or not asset for asset in configured):
        raise SelectionUnavailable(f"lane {lane.get('id')} ต้องกำหนด assets เป็น list")
    return list(configured)


def _validate_v2(policy: dict) -> list[dict]:
    lanes = policy.get("upload_lanes")
    if not isinstance(lanes, list) or not lanes:
        raise SelectionUnavailable("schema v2 ต้องมี upload_lanes อย่างน้อยหนึ่ง lane")
    seen_ids: set[str] = set()
    seen_destinations: set[str] = set()
    for lane in lanes:
        required = {"id", "destination_folder", "source_folder", "style", "schedule",
                    "assets", "max_articles", "article", "images", "slug_template"}
        if not isinstance(lane, dict) or not required <= set(lane):
            raise SelectionUnavailable("lane มีฟิลด์ไม่ครบตาม schema v2")
        lane_id = lane["id"]
        if not isinstance(lane_id, str) or not lane_id or lane_id in seen_ids:
            raise SelectionUnavailable("lane id ซ้ำหรือไม่ถูกต้อง")
        destination = lane["destination_folder"]
        _safe_child(Path("."), destination, field="destination_folder")
        if destination in seen_destinations:
            raise SelectionUnavailable("destination_folder ซ้ำ")
        _safe_child(Path("."), lane["source_folder"], field="source_folder")
        contract_template = lane.get("trade_plan_contract")
        if contract_template is not None:
            if not isinstance(contract_template, str) or "{asset}" not in contract_template:
                raise SelectionUnavailable(
                    f"lane {lane_id} ต้องกำหนด trade_plan_contract ที่ผูก {{asset}} หรือ null")
            _safe_child(Path("."), contract_template.replace("{asset}", "asset"),
                        field="trade_plan_contract")
        weekdays = lane["schedule"].get("weekdays") if isinstance(lane["schedule"], dict) else None
        if (not isinstance(weekdays, list)
                or any(not isinstance(day, int) or day not in range(7) for day in weekdays)):
            raise SelectionUnavailable(f"ตาราง lane {lane_id} ไม่ถูกต้อง")
        if not isinstance(lane["max_articles"], int) or lane["max_articles"] < 1:
            raise SelectionUnavailable(f"max_articles ของ lane {lane_id} ไม่ถูกต้อง")
        seen_ids.add(lane_id)
        seen_destinations.add(destination)
    return lanes


def _atomic_swap(stage: Path, target: Path) -> None:
    backup = target.parent / f".{target.name}.backup-{next(tempfile._get_candidate_names())}"
    had_target = target.exists()
    try:
        if had_target:
            os.replace(target, backup)
        os.replace(stage, target)
    except Exception:
        if target.exists() and not had_target:
            shutil.rmtree(target, ignore_errors=True)
        if had_target and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _inventory_article(day_dir: Path, lane: dict, asset: str,
                       publish_date: str) -> dict:
    source_folder = _safe_child(day_dir, lane["source_folder"], field="source_folder")
    article_name = str(lane["article"]).replace("{asset}", asset)
    article = _safe_child(source_folder, article_name, field="article")
    result = {
        "id": lane["id"], "asset": asset, "status": "failed",
        "source_folder": lane["source_folder"],
        "destination_folder": lane["destination_folder"], "article_name": article_name,
    }
    if not article.is_file():
        result["reason"] = f"ไม่พบบท {article_name} ใน source lane"
        return result
    meta = _frontmatter(article)
    expected_slug = str(lane["slug_template"]).format(asset=asset, date=publish_date)
    if meta.get("slug") != expected_slug:
        result["reason"] = f"slug ไม่ตรงสัญญา: ต้องเป็น {expected_slug}"
        return result
    contract_template = lane.get("trade_plan_contract")
    contract_name = None
    contract_path = None
    if contract_template is not None:
        contract_name = str(contract_template).replace("{asset}", asset)
        contract_path = _safe_child(source_folder, contract_name,
                                    field="trade_plan_contract")
        if not contract_path.is_file():
            result["reason"] = f"ไม่มี public trade-plan contract: {contract_name}"
            result["trade_plan_contract"] = {"status": "FAIL", "findings": [
                {"code": "CONTRACT_MISSING", "field": "trade_plan_contract",
                 "message": "selector fail-closed ก่อนคัดขึ้นเว็บ"}
            ]}
            return result
        try:
            contract_payload = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            result["reason"] = f"อ่าน public trade-plan contract ไม่ได้: {exc}"
            result["trade_plan_contract"] = {"status": "FAIL", "findings": [
                {"code": "CONTRACT_UNREADABLE", "field": "trade_plan_contract",
                 "message": str(exc)}
            ]}
            return result
        contract_report = trade_plan_public_contract.validate(
            contract_payload, article_name=article_name, article_bytes=article.read_bytes(),
            style_id=lane["style"], asset=asset, publish_date=date.fromisoformat(publish_date))
        result["trade_plan_contract"] = contract_report
        if contract_report["status"] != "PASS":
            codes = ", ".join(item["code"] for item in contract_report["findings"])
            result["reason"] = f"public trade-plan contract ไม่ผ่าน: {codes}"
            return result
    refs: list[str] = []
    for raw_ref in _IMAGE_REF_RE.findall(article.read_text(encoding="utf-8")):
        ref = raw_ref.split("?", 1)[0].split("#", 1)[0].strip().replace("\\", "/")
        if not ref or Path(ref).name != ref:
            result["reason"] = f"image reference ไม่อยู่ใน source lane: {raw_ref}"
            return result
        image = source_folder / ref
        if not image.is_file():
            result["reason"] = f"ภาพที่บทอ้างหาย: {ref}"
            return result
        try:
            image_output.verify(image)
        except image_output.ImageGateError as exc:
            result["reason"] = str(exc)
            return result
        refs.append(ref)
    patterns = [str(pattern).replace("{asset}", asset) for pattern in lane["images"]]
    missing_patterns = [pattern for pattern in patterns
                        if not any(Path(ref).match(pattern) for ref in refs)]
    if missing_patterns:
        result["reason"] = "ภาพบังคับของ lane อ้างไม่ครบ: " + ", ".join(missing_patterns)
        return result
    freshness = _freshness_problem(article, lane, refs, publish_date)
    if freshness:
        result["reason"] = freshness
        return result
    result.update({"status": "ready", "article": article, "images": refs,
                   "source": source_folder, "slug": expected_slug,
                   "contract": contract_path, "contract_name": contract_name,
                   "contract_sha256": (trade_plan_public_contract.sha256_bytes(
                       contract_path.read_bytes()) if contract_path else None)})
    return result


def _public_selection_report(*, inventories: list[dict], publish_date: str,
                             external_publish: bool) -> dict:
    """Build a path-safe report proving that every copied article passed the gate."""
    lanes = []
    for item in inventories:
        entry = {
            "lane_id": item["id"], "asset": item["asset"],
            "status": item["status"], "article": item["article_name"],
            "destination_folder": item["destination_folder"],
            "reason": item.get("reason"),
            "trade_plan_contract": item.get("trade_plan_contract"),
        }
        if item.get("status") == "ready":
            entry.update({
                "images": item["images"],
            })
            if item.get("contract_name") is not None:
                entry.update({
                    "contract": item["contract_name"],
                    "contract_sha256": item["contract_sha256"],
                })
        lanes.append(entry)
    return {
        "schema": "p002-public-selection-report/v1",
        "publish_date": publish_date,
        "external_publish": external_publish,
        "trade_plan_contract_required": any(
            item.get("contract_name") is not None for item in inventories),
        "status": ("PASS" if all(item["status"] == "ready" for item in inventories)
                   else "BLOCK_PARTIAL"),
        "lanes": lanes,
    }


def _freshness_problem(article: Path, lane: dict, refs: list[str],
                       publish_date: str) -> str | None:
    """Reject a current slug wrapped around stale chart/article evidence."""
    published = date.fromisoformat(publish_date)
    max_age = int(lane.get("max_data_age_days", 1))
    style = lane["style"]
    text = article.read_text(encoding="utf-8")
    meta = _frontmatter(article)
    evidence_dates: list[date] = []
    if style in {"d_chart_story", "e_indicator", "m_btcusd_h1_visual_daily"}:
        for ref in refs:
            match = re.search(r"(\d{4}-\d{2}-\d{2})\.webp$", ref)
            if match and not (style == "d_chart_story" and "weekly-calendar" in ref):
                evidence_dates.append(date.fromisoformat(match.group(1)))
        if style == "m_btcusd_h1_visual_daily":
            cutoff = meta.get("cutoff", "")[:10]
            if cutoff != publish_date:
                return f"cutoff ของ Style M ไม่ตรงวันเผยแพร่: {cutoff or 'missing'}"
    elif style == "l_forex_daily_plan":
        match = re.search(r"ตัดข้อมูลเมื่อ\s*(\d{2})/(\d{2})/(\d{4})", text)
        if not match:
            return "Style L ไม่มีวันที่ตัดข้อมูลในหลักฐานท้ายบท"
        day, month, year = map(int, match.groups())
        evidence_dates.append(date(year, month, day))
    if not evidence_dates:
        return "ไม่มี data date evidence ให้ตรวจ freshness"
    if len(set(evidence_dates)) != 1:
        return "หลักฐานในบทใช้ data date ไม่ตรงกัน"
    age = (published - evidence_dates[0]).days
    if age < 0:
        return "data date เป็นอนาคตของวันเผยแพร่"
    if age > max_age:
        return f"ข้อมูล stale เกิน {max_age} วัน (เก่า {age} วัน)"
    return None


def select_lanes(day_dir: Path, *, policy: dict | None = None) -> dict:
    """Build every scheduled local upload article, then replace the handoff atomically."""
    policy = policy or load_policy()
    lanes = _validate_v2(policy)
    match = _DAY_RE.fullmatch(Path(day_dir).name)
    if not match:
        raise SelectionUnavailable(f"ชื่อโฟลเดอร์วันไม่ตรง DD-MM-YYYY: {Path(day_dir).name}")
    day, month, year = map(int, match.groups())
    publish_day = date(year, month, day)
    publish_date = publish_day.isoformat()
    active = [lane for lane in lanes if lane.get("enabled", True)
              and publish_day.weekday() in lane["schedule"]["weekdays"]]
    inventories: list[dict] = []
    for lane in active:
        assets = _lane_assets(lane, publish_date)
        if len(assets) > lane["max_articles"]:
            raise SelectionUnavailable(
                f"lane {lane['id']} ได้ {len(assets)} บท เกิน max_articles={lane['max_articles']}")
        inventories.extend(_inventory_article(Path(day_dir), lane, asset, publish_date)
                           for asset in assets)
    target = Path(day_dir) / policy.get("selection_folder", "0-ขึ้นเว็บวันนี้")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent))
    try:
        for item in inventories:
            if item["status"] != "ready":
                continue
            destination = stage / item["destination_folder"]
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item["article"], destination / item["article_name"])
            if item.get("contract") is not None:
                shutil.copyfile(item["contract"], destination / item["contract_name"])
            for image_name in item["images"]:
                destination_image = destination / image_name
                if not destination_image.exists():
                    shutil.copyfile(item["source"] / image_name, destination_image)
                    image_output.verify(destination_image)
        selection_report = _public_selection_report(
            inventories=inventories, publish_date=publish_date,
            external_publish=bool(policy.get("external_publish", False)))
        (stage / "selection-report.json").write_text(
            json.dumps(selection_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        _atomic_swap(stage, target)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    ready = sum(item["status"] == "ready" for item in inventories)
    expected = len(inventories)
    status = "ready" if ready == expected else ("partial" if ready else "unavailable")
    first = next((item for item in inventories if item["status"] == "ready"), None)
    return {
        "status": status, "expected_count": expected, "ready_count": ready,
        "lanes": inventories, "directory": str(target),
        "selection_report": str(target / "selection-report.json"),
        "article": (str(Path(first["destination_folder"]) / first["article_name"])
                    if first else None),
        "reason": ("ครบทุกบทตามตาราง" if status == "ready"
                   else "มีบทตก fail-closed; ไม่ใช้ไฟล์จากวันอื่น"),
        "expected": f"คาดหวัง {expected} บท แต่พร้อม {ready}",
    }


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        print("ใช้: python -m tools.publish_selection <โฟลเดอร์วัน เช่น ../output/06-08-2026>")
        return 2
    result = select(Path(args[0]))
    if result["status"] == "ready":
        if "ready_count" in result:
            print(f"ชุดขึ้นเว็บรอบนี้: {result['ready_count']}/{result['expected_count']} บท")
        else:
            print(f"ใบขึ้นเว็บรอบนี้: {result['article']}")
        return 0
    print(f"ยังไม่มีใบให้ขึ้นเว็บ — {result['reason']} "
          f"· คาดว่าจะเจอที่ {result['expected']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
