"""ชั้นจัดวางไฟล์ที่ผู้ใช้เอาไปอัปจริง — แยกขาดจากกองไฟล์ทำงานของสายท่อ

ก่อนหน้านี้โฟลเดอร์ผลผลิตปนกันสามอย่างในที่เดียว: ไฟล์ที่เอาไปอัป · ไฟล์หลักฐาน
ฝั่ง internal · และรหัส batch ที่คนอ่านไม่รู้ว่าแปลว่าอะไร ผู้ใช้เปิดแล้วหาไม่เจอว่า
ต้องหยิบไฟล์ไหน (คำสั่งผู้ใช้ 2026-08-04 — "ไฟล์ output ดูแล้วงงมาก ตัดเรื่อง internal ออก")

โครงที่ผู้ใช้สั่ง — มีแค่นี้ ไม่มีอย่างอื่นปนในโฟลเดอร์ที่ผู้ใช้เปิด:

    output/04-082026/1-ณธาร-รายงานตลาด/xauusd.md
                                       /xauusd.webp
                    /2-กฤช-โครงสร้างราคา/xauusd.md
                                       /xauusd.webp
                    /3-ปุณณ์-จังหวะตลาด/ ...

ชื่อไฟล์ .md กับ .webp ตรงกันทุกคู่ เพื่อให้จับคู่ตอนอัปขึ้นเว็บได้โดยไม่ต้องเปิดดู
ไฟล์หลักฐาน ผลด่าน และของฝั่ง internal ทั้งหมดไปอยู่ใต้ `work/build/` แทน
— ยังครบเหมือนเดิมทุกไฟล์ ไม่ได้ตัดทิ้ง แค่ย้ายออกจากสายตา

สองอย่างที่ชั้นนี้รับผิดชอบเงียบ ๆ (แก้ 2026-08-05 หลังผู้ใช้ให้ตรวจเรื่องขนาดไฟล์):

- **โฟลเดอร์นี้สะท้อนรอบล่าสุดเสมอ** — สไตล์ที่ตกด่านต้องไม่เหลือไฟล์ของรอบก่อน
  ค้างไว้ ทั้งที่ชื่อไฟล์กับวันที่ในโฟลเดอร์บอกว่าเป็นของสด (ดู `_clear_stale`)
- **กราฟเก็บชุดเดียวต่อหัวข้อ** ทั้งสามโฟลเดอร์ต่อร่วมไฟล์เดียวกัน (ดู `_place_chart`)
  ผู้ใช้เห็นและใช้เหมือนไฟล์ปกติทุกประการ
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import image_output, license_gate, public_copy_validator, voice_rules, writers  # noqa: E402
from tools import chart_public_renderer, publish_selection, wcb_copy_validator, wcb_writers  # noqa: E402


def day_folder(cutoff_at: str) -> str:
    """ชื่อโฟลเดอร์รายวันตามที่ผู้ใช้สั่ง — วันเวลาไทย รูปแบบ DD-MMYYYY เช่น 04-082026"""
    key = voice_rules.thai_day_key(cutoff_at)
    if key is None:
        raise ValueError(f"อ่านเวลา '{cutoff_at}' ไม่ออก จึงตั้งชื่อโฟลเดอร์วันไม่ได้")
    return key


CLEARANCE_FILENAME = "สถานะสิทธิ์-อ่านก่อนนำไปใช้.md"


def _provider_entries() -> dict:
    """รายการ provider ที่สายท่อใช้จริงตอนนี้ — อ่านสดทุกครั้ง ไม่แคช

    ป้ายต้องสะท้อนทะเบียน ณ รอบที่รัน ถ้าแคชไว้แล้วมีคนแก้ทะเบียนกลาง
    ป้ายจะบอกสถานะเก่าซึ่งอันตรายกว่าไม่มีป้าย
    """
    registry = license_gate.load_registry()
    return {name: entry
            for name, entry in (registry.get("providers") or {}).items()
            if name.startswith("wcb_")}


def write_clearance_notice(publish_root: Path, cutoff_at: str, *,
                           clearance: str, reasons: list[str] | None = None) -> Path:
    """ติดป้ายสถานะสิทธิ์ไว้ในโฟลเดอร์วัน — คนเปิดโฟลเดอร์ต้องเห็นก่อนหยิบไฟล์ไปใช้

    ทำไมต้องมี: `output/README.md` เขียนว่า "ไฟล์ที่วางอยู่ในโฟลเดอร์นักเขียน = ผ่านด่าน
    ตรวจแล้ว หยิบไปอัปได้เลย" ซึ่ง**จริงเฉพาะด่านเนื้อหา** ไม่ใช่ด่านสิทธิ์ · ตอนนี้ทุกบท
    ในคลังยังเป็น `approved-internal-only` เพราะยังไม่รู้ว่าข้อมูลราคามาจากเจ้าไหน
    ⇒ คนที่ทำตาม README ตรงตัวจะเผยแพร่โดยไม่มีสิทธิ์ (พบ 2026-08-05)

    ป้ายนี้เขียนทับทุกรอบ จึงสะท้อนสถานะล่าสุดเสมอ ไม่ค้างจากรอบก่อน
    """
    day = publish_root / day_folder(cutoff_at)
    day.mkdir(parents=True, exist_ok=True)
    cleared = clearance == license_gate.APPROVED_PUBLIC
    lines = [
        "# สถานะสิทธิ์ของบทความในโฟลเดอร์นี้",
        "",
        f"**สถานะล่าสุด:** `{clearance}`",
        "",
    ]
    if cleared:
        lines += ["## ✅ เผยแพร่ได้ — นำขึ้นเว็บหรือโซเชียลได้", ""]
        # ป้ายต้องบอก **ฐานของการอนุมัติ** ด้วย ไม่ใช่แค่ผลลัพธ์
        # เพราะทะเบียนสิทธิ์รองรับสองแบบที่ต่างกันมาก: ตรวจสัญญาแล้วจริง กับ
        # เจ้าของงานสั่งอนุมัติโดยรับความเสี่ยงเอง · คนที่หยิบไฟล์ไปใช้ควรรู้ว่าอันไหน
        for name, entry in _provider_entries().items():
            if entry.get("contract_reviewed") is False and entry.get("cleared_by"):
                lines += [
                    f"> ⚠️ `{name}` ปลดด้วย **การอนุมัติของ{entry['cleared_by']}** "
                    "ไม่ใช่ผลการตรวจสัญญาต้นทาง",
                    ">",
                    "> ยังไม่มีใครอ่านสัญญาของผู้ให้บริการข้อมูล และยังไม่ทราบว่าเป็นเจ้าไหน",
                    "> ถ้าคำตอบจากทีมเว็บ (E1/E7) กลับมาว่าสิทธิ์ไม่ครอบคลุม",
                    "> **ต้องถอนบทที่เผยแพร่ไปแล้วและแก้ทะเบียนสิทธิ์ทันที**",
                    "",
                ]
    else:
        lines += [
            "## 🔒 ยังนำขึ้นเว็บหรือโซเชียลไม่ได้",
            "",
            "ไฟล์ในโฟลเดอร์นี้**ผ่านด่านเนื้อหาแล้ว** คือทุกตัวเลขชี้กลับหลักฐานได้",
            "แต่ **ยังไม่ผ่านด่านสิทธิ์ข้อมูล** ซึ่งเป็นคนละชั้นกัน",
            "",
            "ใช้ได้: อ่านภายใน · ตรวจคุณภาพ · ส่งให้คนในทีมดู",
            "ใช้ไม่ได้: ขึ้นเว็บ · โพสต์โซเชียล · ส่งต่อให้บุคคลที่สาม",
            "",
            "### ติดตรงไหน",
            "",
        ]
        lines += [f"- {reason}" for reason in (reasons or ["ไม่ได้ระบุเหตุผล"])]
        lines += ["", "ปลดล็อกได้เมื่อได้คำตอบข้อ 1 จากทีมเว็บ WCB (รายการ E1 ใน `EXTERNAL.md`)"]
    target = day / CLEARANCE_FILENAME
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def publish_asset(*, asset: str, article_data: dict, technical_evidence: dict,
                  chart_source: Path, publish_root: Path, cutoff_at: str,
                  instrument_type: str, trade_branch: dict | None = None) -> dict:
    """เขียนบทความสามสไตล์ของสินทรัพย์หนึ่งตัวลงโครงที่ผู้ใช้เปิดใช้จริง

    แต่ละสไตล์ผ่านด่านตรวจของตัวเองก่อนเสมอ — **ไม่ผ่าน = ไม่มีไฟล์ในโฟลเดอร์นั้น**
    เหมือนกติกาเดิมของสไตล์ ① ทุกประการ (fail-closed) เพราะไฟล์ที่วางอยู่ในโฟลเดอร์นี้
    แปลว่า "หยิบไปอัปได้เลย" ถ้าปล่อยของที่ยังไม่ผ่านลงมาปน ความหมายนั้นจะหายไปทันที

    "ไม่มีไฟล์" ต้องรวมถึง **ไฟล์ของรอบก่อนในวันเดียวกัน** ด้วย — เดิมเขียนเฉพาะตัวที่ผ่าน
    แล้วไม่แตะอะไรอีก ของที่ถูกตีตกรอบนี้จึงยังนอนอยู่จากรอบก่อนโดยหน้าตาเหมือนของสด
    (พบ 2026-08-05 · เทสเดิมไม่เจอเพราะทดสอบบนโฟลเดอร์เปล่าทุกครั้ง)

    `trade_branch` คือผลของสาขาแผนการเทรดฝั่ง internal — ชั้นนี้ไม่ตัดสินเองว่าแผนไหน
    พูดได้ ปล่อยให้ `writers.plan_for_public` เป็นคนตัดสินที่เดียว แล้วส่งต่อเฉพาะ
    นักเขียนที่ประกาศว่าใช้แผน (`uses_trade_plan`) — คนอื่นไม่ได้รับแม้แต่ค่าเดียว
    """
    # ด่านไฟล์ภาพ (กติกาเว็บ 08-09) ยิงก่อนวางอะไรทั้งนั้น — กราฟใบเดียวถูกใช้ทุกสไตล์
    # ถ้ามันผิดนามสกุลหรือเกินเพดาน ทุกโฟลเดอร์จะได้ของที่เว็บตีกลับพร้อมกันหมด
    # ⇒ หยุดตั้งแต่ยังไม่มีไฟล์ลงพื้น ดีกว่าตกกลางทางแล้วเหลือของค้างครึ่งชุด
    image_output.verify(chart_source)
    day = publish_root / day_folder(cutoff_at)
    plan = writers.plan_for_public(trade_branch)
    results = []
    chart_master: Path | None = None  # ไฟล์กราฟจริงของรอบนี้ — สไตล์ที่เหลือต่อร่วมกับตัวนี้
    for writer in writers.WRITERS:
        writer_plan = plan if writer.get("uses_trade_plan") else None
        markdown = writer["render"](article_data, chart_name=f"{asset}{image_output.IMAGE_SUFFIX}",
                                    plan=writer_plan)
        evidence = {"article": article_data, "technical": technical_evidence}
        ratio_values = None
        if writer_plan:
            # หลักฐานของหัวข้อแผนเข้ากองเฉพาะสไตล์ที่เขียนหัวข้อนั้นจริง
            # ไม่งั้นสไตล์อื่นจะได้เลขชุดใหญ่ขึ้นฟรี ๆ ทั้งที่ไม่ได้ใช้
            evidence["trade_plan"] = writers.plan_evidence(writer_plan)
            ratio_values = writers.plan_ratio_values(writer_plan)
        validation = public_copy_validator.validate(
            markdown,
            evidence=evidence,
            instrument_type=instrument_type,
            profile=writer["profile"],
            ratio_values=ratio_values,
        )
        entry = {
            "writer_id": writer["id"],
            "pen_name": writer["pen_name"],
            "style": writer["style"],
            "folder": writer["folder"],
            "status": validation["status"],
            "word_count": validation["word_count"],
            "fatal_count": validation["fatal_count"],
            "trade_plan_included": bool(writer_plan),
            "findings": validation["findings"],
        }
        if validation["status"] == "pass":
            target = day / writer["folder"]
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{asset}.md").write_text(markdown, encoding="utf-8")
            chart_target = target / f"{asset}{image_output.IMAGE_SUFFIX}"
            _place_chart(chart_source, chart_target, share_with=chart_master)
            if chart_master is None:
                chart_master = chart_target
            entry["article"] = str(target / f"{asset}.md")
            entry["chart"] = str(chart_target)
            entry["removed_stale"] = False
        else:
            # ตกด่านแล้วโฟลเดอร์อาจยังมีของรอบก่อนของวันเดียวกันค้างอยู่
            # ปล่อยไว้ = ของที่ถูกตีตกนอนปนกับของสด โดยไม่มีอะไรบอกว่ามันเก่า
            entry["removed_stale"] = _clear_stale(day / writer["folder"], asset)
        results.append(entry)
    return {"asset": asset, "day": day_folder(cutoff_at), "directory": str(day),
            "trade_plan_public": _plan_note(trade_branch, plan),
            "writers": results}


def publish_wcb_asset(*, asset: str, evidence: dict, snapshot: dict,
                      publish_root: Path, cutoff_at: str,
                      plan: dict | None = None) -> dict:
    """สายสาธารณะ — เขียนบท A/B/C ลงโครงเดียวกับสายภายใน แต่ไม่มีไฟล์กราฟ

    กราฟของสายนี้เป็นหมุด `[[chart:..]]` ที่เว็บวาดเอง จึงไม่มี `.webp` ให้วาง
    กติกา fail-closed เหมือนกันทุกประการ: สไตล์ไหนตกด่าน = ไม่มีไฟล์ของสไตล์นั้น
    และต้องล้างของรอบก่อนในวันเดียวกันทิ้งด้วย ไม่ใช่ปล่อยให้นอนปนกับของสด

    `plan` ต้องผ่านด่านมาแล้วก่อนถึงชั้นนี้ (`writers.plan_for_public` +
    `wcb_writers.plan_rejection`) — ชั้นนี้ไม่ตัดสินเองว่าแผนไหนพูดได้ เหมือนที่
    `publish_asset` ของสายภายในไม่ตัดสินเอง · ส่งเฉพาะสไตล์ที่ประกาศว่าใช้แผน
    """
    day = publish_root / day_folder(cutoff_at)
    results = []
    for writer in wcb_writers.WCB_WRITERS:
        writer_plan = plan if writer.get("uses_trade_plan") else None
        markdown = writer["render"](evidence, writer_plan)
        # หลักฐานของหัวข้อแผนเข้ากองเฉพาะสไตล์ที่เขียนหัวข้อนั้นจริง
        validation = wcb_copy_validator.validate(markdown, snapshot, plan=writer_plan)
        findings = list(validation["findings"])
        status = validation["status"]
        fatal_count = validation["fatal_count"]

        # ด่านตรวจบังคับขั้นต่ำร่วมของสัญญา (600 คำ) แต่สเปกกำหนดของแต่ละสไตล์ไว้สูงกว่า
        # สองเลขไม่เคยตรงกัน ⇒ สไตล์ B เคยออกมา 820 คำ ทั้งที่สเปกเขียนว่า 900–1,600
        # แล้วผ่านด่านได้โดยไม่มีอะไรฟ้อง · เกณฑ์รายสไตล์อยู่ในทะเบียนนักเขียน
        # ที่เดียวกับตัว render จึงเลื่อนไปคนละทางไม่ได้
        if validation["word_count"] < writer["min_words"]:
            findings.append({
                "rule": "style_word_floor", "severity": "fatal", "line": 1,
                "message": (f"{writer['style']} ได้ {validation['word_count']} คำ "
                            f"ต่ำกว่าเกณฑ์ {writer['min_words']} คำของสไตล์นี้ตามสเปก"),
            })
            status, fatal_count = "fail", fatal_count + 1

        entry = {
            "writer_id": writer["id"],
            "style": writer["style"],
            "folder": writer["folder"],
            "status": status,
            "word_count": validation["word_count"],
            "fatal_count": fatal_count,
            "trade_plan_included": bool(writer_plan),
            "findings": findings,
        }
        if status == "pass":
            target = day / writer["folder"]
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{asset}.md").write_text(markdown, encoding="utf-8")
            entry["article"] = str(target / f"{asset}.md")
            entry["removed_stale"] = False
        else:
            entry["removed_stale"] = _clear_stale(day / writer["folder"], asset)
        results.append(entry)
    web_images = _wcb_web_images(asset=asset, evidence=evidence, day=day,
                                 results=results)
    return {"asset": asset, "day": day_folder(cutoff_at), "directory": str(day),
            "writers": results, "web_images": web_images}


def _wcb_web_images(*, asset: str, evidence: dict, day: Path,
                    results: list[dict]) -> dict | None:
    """ภาพซูมแนบ + ฉบับแนบภาพ ของใบที่จะขึ้นเว็บ (ผู้ใช้สั่ง 08-10 ค่ำ)

    ทำเฉพาะสินทรัพย์ที่นโยบายชี้ขึ้นเว็บ และเฉพาะเมื่อใบสไตล์นั้นผ่านด่านแล้ว —
    วางคู่ไฟล์หมุดในโฟลเดอร์สไตล์เดียวกัน (`<asset>-web-*.webp` + `<asset>-แนบภาพ.md`)
    แล้ว `publish_selection` คัดลอกตามไปที่โฟลเดอร์ขึ้นเว็บ

    **พังแล้วไม่ล้มทั้งรอบ** — ภาพชุดนี้เป็นของแนบทางเลือก ใบหมุดยังใช้ได้เสมอ
    (ต่างจากภาพของสไตล์ D ที่บทอ้างถึงจึงขาดไม่ได้) · แต่ต้องบันทึกเหตุลง result
    ให้เห็น ไม่เงียบหาย
    """
    try:
        policy = json.loads((Path(_REPO_ROOT) / "config" / "publishing_policy.json")
                            .read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": "policy_unreadable", "error": str(exc)}
    if asset != policy.get("web_asset"):
        return None
    web_entry = next((item for item in results
                      if item["writer_id"] == policy.get("web_style")
                      and item["status"] == "pass"), None)
    if web_entry is None:
        return {"status": "web_style_not_passed"}
    folder = day / web_entry["folder"]
    # 🆕 **ทุกสไตล์สาธารณะที่ผ่านด่านได้ชุดภาพเดียวกัน** (ผู้ใช้สั่ง 2026-08-10)
    # เหตุผลเดียวกับ `_place_chart`: กราฟผูกกับหัวข้อ ไม่ได้ผูกกับสไตล์การเขียน
    # B กับ C มีหมุด `[[chart:]]` ของตัวเองอยู่แล้ว แค่ไม่เคยมีไฟล์ภาพวางคู่ให้
    others = [day / item["folder"] for item in results
              if item["status"] == "pass" and item is not web_entry]
    date_text = evidence.get("local_date") or ""
    daily_name, h4_name = chart_public_renderer.image_names(asset, date_text)
    touched = [folder, *others]
    mode = publish_selection.chart_mode_for(policy)
    try:
        from tools import wcb_series_source
        _meta, rows, _label = wcb_series_source.fetch_asset_rows(asset)
        daily = chart_public_renderer.render_daily_zoom(
            rows, evidence, folder / daily_name)
        h4 = chart_public_renderer.render_h4(evidence, folder / h4_name)
        used = {target: _attach_images(target, asset, daily_name, h4_name, mode=mode)
                for target in touched}
        # ภาพที่ไม่มีฉบับแนบภาพใบไหนอ้างถึงเลย = ภาพกำพร้า ต้องไม่นอนอยู่ในโฟลเดอร์
        # (สไตล์ C มีหมุดรายวันอย่างเดียว ไม่มีหมุดราย 4 ชั่วโมง)
        wanted = {name for names in used.values() for name in names}
        for name in (daily_name, h4_name):
            if name not in wanted:
                (folder / name).unlink(missing_ok=True)
        for target in others:
            for name in used[target]:
                _place_chart(folder / name, target / name, share_with=folder / name)
    except Exception as exc:  # noqa: BLE001 — ของแนบทางเลือก ห้ามฆ่ารอบผลิต
        for target in touched:                        # ห้ามเหลือชุดครึ่งเดียว
            # โหมดแนบภาพสลับ `<asset>.md` ไปแล้วบางโฟลเดอร์ได้ ⇒ ต้อง**คืนใบหมุด
            # กลับเป็นใบหลัก**ก่อน ไม่ใช่แค่ลบภาพ · ถ้าลบภาพเฉย ๆ จะเหลือบทที่อ้าง
            # รูปซึ่งไม่มีอยู่จริง ซึ่งเว็บตีกลับทั้งใบ (แย่กว่าไม่มีภาพแนบเสียอีก)
            fallback = target / f"{asset}{publish_selection.PIN_FALLBACK_SUFFIX}.md"
            if fallback.is_file():
                (target / f"{asset}.md").write_text(
                    fallback.read_text(encoding="utf-8"), encoding="utf-8")
            for name in (daily_name, h4_name, f"{asset}-แนบภาพ.md", fallback.name):
                (target / name).unlink(missing_ok=True)
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    return {"status": "ready", "images": sorted(wanted),
            "variant": f"{asset}-แนบภาพ.md",
            "folders": {target.name: used[target] for target in touched},
            "kb": {daily_name: daily["kb"], h4_name: h4["kb"]}}


def _attach_images(folder: Path, asset: str, daily_name: str, h4_name: str,
                   *, mode: str) -> list[str]:
    """วางฉบับแนบภาพของโฟลเดอร์หนึ่ง — คืน**ชื่อภาพที่ใบหลักอ้างจริง**

    คืนรายชื่อที่อ้างจริงแทนที่จะคืนทั้งคู่ เพราะแต่ละสไตล์มีหมุดกราฟไม่เท่ากัน
    (A/B มีทั้งรายวันและราย 4 ชั่วโมง · C มีรายวันอย่างเดียว) — วางภาพที่บทไม่ได้
    อ้างถึงลงโฟลเดอร์ = ภาพกำพร้า คนหยิบไปอัปแล้วไม่รู้ว่าจะแปะตรงไหน

    🆕 **โหมด `attached_images` (ค่าตั้งต้นตั้งแต่ 2026-08-11 · ผู้ใช้สั่ง):** สลับที่นี่
    เลย ไม่ใช่ไปสลับตอนคัดลอกขึ้นโฟลเดอร์ขึ้นเว็บ — โฟลเดอร์สไตล์ต้องมี `<asset>.md`
    เป็นใบเดียวกับที่ขึ้นเว็บจริง ไม่งั้นคนเปิดโฟลเดอร์สไตล์จะเห็นคนละใบกับที่ตัวเอง
    เพิ่งอัปไป และมีสองไฟล์เนื้อเดียวกันนอนคู่กันโดยไม่รู้ว่าอันไหนของจริง

    **ลบไฟล์ของอีกโหมดทิ้งเสมอ** — สลับโหมดกลับไปกลับมาแล้วเหลือทั้งสองชื่อในโฟลเดอร์
    คือกับดักเดียวกับใบค้างของเมื่อวาน: หน้าตาเหมือนของสดทุกประการ
    """
    legacy = folder / f"{asset}-แนบภาพ.md"
    fallback = folder / f"{asset}{publish_selection.PIN_FALLBACK_SUFFIX}.md"
    # ต้นทางของหมุดคือใบสำรองถ้ามีอยู่แล้ว ไม่ใช่ `<asset>.md` เสมอไป — เรียกซ้ำบน
    # โฟลเดอร์ที่สลับไปแล้ว (หรือสลับโหมดกลับ) จะอ่านฉบับแนบภาพมาเป็น "หมุด" แล้ว
    # ใบหมุดหายไปจากระบบทั้งใบโดยไม่มีอะไรฟ้อง
    source = fallback if fallback.is_file() else folder / f"{asset}.md"
    pins = source.read_text(encoding="utf-8")
    variant = chart_public_renderer.swap_pins_for_images(pins, daily_name, h4_name)
    if mode == publish_selection.CHART_MODE_IMAGES:
        fallback.write_text(pins, encoding="utf-8")
        (folder / f"{asset}.md").write_text(variant, encoding="utf-8")
        legacy.unlink(missing_ok=True)
    else:
        (folder / f"{asset}.md").write_text(pins, encoding="utf-8")
        legacy.write_text(variant, encoding="utf-8")
        fallback.unlink(missing_ok=True)
    return [name for name in (daily_name, h4_name) if f"({name})" in variant]


def _place_chart(source: Path, target: Path, *, share_with: Path | None) -> None:
    """วางกราฟลงโฟลเดอร์นักเขียน — สไตล์ที่ 2 และ 3 ต่อร่วมไฟล์เดียวกับสไตล์แรก

    กราฟผูกกับหัวข้อ ไม่ได้ผูกกับสไตล์การเขียน ทั้งสามโฟลเดอร์จึงได้ไฟล์เดียวกันเป๊ะเสมอ
    (วัด 08-05: รูปคือ 1.41 MB จาก 1.49 MB ที่ผลิตต่อวัน คือ 95% และซ้ำ 3 ชุด)
    ผู้ใช้ยังเห็น `.webp` ครบทุกโฟลเดอร์เหมือนเดิม เปิดได้ ลากไปอัปได้ตามปกติ

    **ตัวแรกต้องก๊อปจริง ห้ามต่อร่วมกับ `chart_source`** ซึ่งอยู่ใต้ `work/build/`
    ของรอบนั้น — ถ้าไปต่อร่วมกับต้นทาง รอบถัดไปที่เขียนทับไฟล์ในกองงานจะลากไฟล์ที่
    ตีพิมพ์ไปแล้วเปลี่ยนตามไปด้วยโดยไม่มีใครสั่ง

    ลบของเดิมก่อนเขียนทุกครั้ง เพราะการก๊อปทับไฟล์ที่เป็นข้อต่อร่วมอยู่จะไปแก้เนื้อ
    ของโฟลเดอร์อื่นที่ต่อร่วมกันอยู่ด้วย
    """
    target.unlink(missing_ok=True)
    if share_with is not None:
        try:
            os.link(share_with, target)
            return
        except (OSError, NotImplementedError, AttributeError):
            # ระบบไฟล์ต่อร่วมกันไม่ได้ (FAT32 · บางโฟลเดอร์ที่ sync ขึ้นคลาวด์)
            # ถอยไปก๊อปจริง — เปลืองที่เท่าเดิมแต่ผลลัพธ์ที่ผู้ใช้เห็นถูกต้องเหมือนกัน
            pass
    shutil.copyfile(source, target)


def _clear_stale(folder: Path, asset: str) -> bool:
    """ลบคู่ `.md`/`.webp` ของสินทรัพย์ที่ตกด่าน — คืน True ถ้ามีของเก่าให้ลบจริง

    ลบเฉพาะคู่ของสินทรัพย์ตัวนี้ ไม่ล้างทั้งโฟลเดอร์ เพราะหัวข้ออื่นของวันเดียวกัน
    ที่ผ่านด่านไปแล้วอยู่ในโฟลเดอร์เดียวกันและต้องไม่โดนหางเลข
    """
    removed = False
    # `.png` ยังอยู่ในรายการเพราะโฟลเดอร์ของวันเดียวกันอาจมีของยุคก่อน 08-09 ค้างอยู่
    #
    # ชุดแนบภาพต้องโดนกวาดด้วย (`-แนบภาพ.md` ยุคก่อน 08-11 · `-หมุดกราฟ.md` ยุคใหม่
    # · `-web-*.webp`) — สไตล์ที่ตกด่านแล้วเหลือใบสำรองกับรูปนอนอยู่ คือใบที่คนหยิบ
    # ไปวางได้ทั้งที่บทของรอบนี้ไม่ผ่านด่าน
    names = [f"{asset}.md", f"{asset}{image_output.IMAGE_SUFFIX}", f"{asset}.png",
             f"{asset}-แนบภาพ.md", f"{asset}{publish_selection.PIN_FALLBACK_SUFFIX}.md"]
    for path in [folder / name for name in names] + sorted(
            folder.glob(f"{asset}-web-*.webp")):
        if path.exists():
            path.unlink()
            removed = True
    return removed


def _plan_note(trade_branch: dict | None, plan: dict | None) -> dict:
    """บันทึกว่าหัวข้อแผนขึ้นบทความหรือไม่ **และเพราะอะไร**

    วันที่ไม่มีหัวข้อแผนต้องแยกออกได้ว่าเป็น "วันนี้ไม่มีจังหวะจริง" หรือ "ระบบพัง"
    ถ้าไม่บันทึกเหตุผลไว้ ทั้งสองกรณีจะหน้าตาเหมือนกันเป๊ะคือหัวข้อหายไปเฉย ๆ
    """
    if plan:
        return {"included": True, "reason": None,
                "classification": plan["classification"], "bias": plan["bias"],
                "rr_first_target": plan["targets"][0]["rr"]}
    branch = trade_branch or {}
    status = branch.get("status")
    if status != "built":
        return {"included": False, "reason": f"trade_branch_status:{status or 'missing'}"}
    inner = branch.get("plan") or {}
    if inner.get("classification") == "no_trade":
        return {"included": False, "reason": "no_trade",
                "detail": inner.get("detail") or inner.get("reason")}
    # เหลือกรณีเดียว: มีแผนครบแต่ด่านความเสี่ยงไม่ได้ตัดสิน `pass`
    # ต้องบันทึกทั้งคำตัดสินและรหัสข้อที่ยิง ไม่งั้นวันที่หัวข้อหายจะดูเหมือนกันไปหมด
    audit = branch.get("audit") or {}
    return {"included": False,
            "reason": f"risk_audit_verdict:{audit.get('verdict') or 'missing'}",
            "detail": [item["id"] for item in audit.get("findings") or []
                       if item["severity"] in ("blocking", "required")]}
