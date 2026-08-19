"""สายผลิตสไตล์ D — ดึงแท่งจริง → สร้าง story → ตรวจบท → วางบท+ภาพคู่กัน

ลำดับที่จงใจ: **ตรวจบทให้ผ่านก่อน แล้วค่อยวาดภาพและวางไฟล์** — ถ้าบทตกด่าน
โฟลเดอร์ D ของหัวข้อนั้นต้องว่าง (ล้างของรอบก่อนทิ้งด้วย) ตามหลัก fail-closed
เดียวกับ `publish_layout`: ไฟล์ที่วางอยู่ = หยิบไปใช้ได้เลย

ขอบเขต: **ทุกหัวข้อในทะเบียน** ตั้งแต่ 2026-08-11 (ผู้ใช้สั่งรัน A–G เข้าสายหลัก
ครบทุกหัวข้อ) — นโยบาย "วันละ 1 บทเฉพาะทอง" เป็นเรื่องใบขึ้นเว็บใน
`publishing_policy.json` ไม่ใช่เรื่องการผลิต · สไตล์ D ยังไม่เข้าโฟลเดอร์
`0-ขึ้นเว็บวันนี้` เพราะนโยบายยังชี้สไตล์ A · การเปลี่ยนใบขึ้นเว็บเป็นการตัดสินใจ
ของหัวหน้าผ่านผู้ใช้ ไม่ใช่ของสายท่อ
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import calendar_feed, candle_close  # noqa: E402
from tools import chart_story, chart_story_renderer, chart_story_writer, zone_memory  # noqa: E402
from tools import style_d_calendar  # noqa: E402
from tools import image_output  # noqa: E402
from tools import publish_layout, wcb_series_source, wcb_source, wcb_writers  # noqa: E402

DEFAULT_ASSET = "xauusd"
LEGACY_CALENDAR_QUOTA = 10
CALENDAR_COUNTRIES = {
    "xauusd": ("USD",),
    "eurusd": ("EUR", "USD"),
    "gbpusd": ("GBP", "USD"),
    "btcusd": ("USD",),
    "nvda": ("USD",),
    "usdthb": ("USD",),
    "solusd": ("USD",),
    "wtiusd": ("USD",),
}
ENERGY_INVENTORY_TERMS = ("น้ำมันดิบคงคลัง", "น้ำมันเบนซินคงคลัง",
                          "crude oil inventories", "gasoline inventories")

# ทะเบียนความหมายขั้นต่ำสำหรับคอลัมน์ “ส่งผลต่อสินทรัพย์” ของ XAU/USD
# ไม่ตรงทะเบียน = ไม่ส่งผล (fail-closed) ไม่อนุมานจากชื่อข่าวที่ไม่รู้ความหมาย
XAU_HIGHER_USD_STRENGTH_TERMS = (
    "empire state", "ดัชนีภาคการผลิตรัฐนิวยอร์ก", "ดัชนีภาคการผลิตเฟดฟิลาเดลเฟีย",
    "philadelphia fed", "nahb", "ดัชนีตลาดที่อยู่อาศัย", "building permits",
    "ใบอนุญาตก่อสร้าง", "housing starts", "ยอดเริ่มสร้างบ้าน", "pmi",
    "retail sales", "ยอดค้าปลีก", "gdp", "ผลิตภัณฑ์มวลรวม", "nonfarm payroll",
    "การจ้างงานนอกภาคเกษตร", "cpi", "ดัชนีราคาผู้บริโภค", "ppi",
    "ดัชนีราคาผู้ผลิต", "consumer confidence", "ความเชื่อมั่นผู้บริโภค",
)
XAU_HIGHER_USD_WEAKNESS_TERMS = (
    "unemployment rate", "อัตราการว่างงาน", "jobless claims", "ผู้ขอรับสวัสดิการว่างงาน",
    "layoffs", "การเลิกจ้าง",
)


def _calendar_number(value) -> float | None:
    """อ่านตัวเลขตัวแรกจากค่าปฏิทินที่มีหน่วยแล้ว; ไม่มี/อ่านไม่ได้คืน None"""
    import re
    if value in (None, "", "—"):
        return None
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", str(value))
    return float(match.group(0).replace(",", "")) if match else None


def weekly_event_asset_effect(event: dict, asset: str) -> str:
    """คืน ไม่ส่งผล/บวก/ลบ จาก actual-vs-forecast หรือ forecast-vs-previous

    รุ่นแรกเปิดทิศเฉพาะ XAU/USD + ข่าว USD ที่อยู่ในทะเบียนความหมายด้านบน
    สินทรัพย์/ข่าวอื่นคืน “ไม่ส่งผล” จนกว่าจะเพิ่มกฎที่ทานสอบแล้ว
    """
    if asset != "xauusd" or str(event.get("country") or "").upper() != "USD":
        return "ไม่ส่งผล"
    title = str(event.get("title") or "").casefold()
    if any(term in title for term in XAU_HIGHER_USD_STRENGTH_TERMS):
        higher_means_usd_strength = True
    elif any(term in title for term in XAU_HIGHER_USD_WEAKNESS_TERMS):
        higher_means_usd_strength = False
    else:
        return "ไม่ส่งผล"
    actual = _calendar_number(event.get("actual"))
    forecast = _calendar_number(event.get("forecast"))
    previous = _calendar_number(event.get("previous"))
    left, right = ((actual, forecast) if actual is not None and forecast is not None
                   else (forecast, previous))
    if left is None or right is None or left == right:
        return "ไม่ส่งผล"
    higher = left > right
    usd_positive = higher if higher_means_usd_strength else not higher
    return "ลบ" if usd_positive else "บวก"  # USD แข็งเป็นแรงลบต่อทองในกฎชุดนี้


def week_bounds(day_text: str) -> tuple[str, str]:
    """คืนวันจันทร์–ศุกร์ของสัปดาห์ที่ครอบวันอ้างอิง"""
    day = date.fromisoformat(day_text)
    monday = day - timedelta(days=day.weekday())
    friday = monday + timedelta(days=4)
    return monday.isoformat(), friday.isoformat()


def weekly_calendar_events(events: list[dict], *, asset: str, local_date: str,
                           limit: int = LEGACY_CALENDAR_QUOTA) -> list[dict]:
    """คัดข่าวสัปดาห์จันทร์–ศุกร์ตามสกุลเงินที่เกี่ยวข้องกับสินทรัพย์

    รายการผลกระทบสูงได้สิทธิ์ก่อน แล้วใช้ผลกระทบปานกลางเติมที่ว่าง จากนั้นจึง
    เรียงกลับตามเวลาเพื่อให้ตารางอ่านเป็นลำดับสัปดาห์
    """
    week_start, week_end = week_bounds(local_date)
    countries = set(CALENDAR_COUNTRIES.get(asset, ("USD",)))
    eligible = [dict(event) for event in events
                if week_start <= str(event.get("at") or "")[:10] <= week_end
                and str(event.get("country") or "").upper() in countries
                and str(event.get("impact") or "").lower() in ("high", "medium")
                and (asset == "wtiusd" or not any(
                    term in str(event.get("title") or "").casefold()
                    for term in ENERGY_INVENTORY_TERMS))]
    # ฟีดอาจมีรหัสคนละตัวแต่ชื่อ+เวลาเดียวกัน (เช่น preliminary กับแถวสรุป)
    # รวมเป็นแถวเดียว โดยคงระดับผลกระทบที่สูงกว่าและเติมค่าที่มีจริงจากอีกแถว
    deduplicated: dict[tuple[str, str, str], dict] = {}
    for event in eligible:
        key = (str(event.get("at") or ""), str(event.get("country") or "").upper(),
               str(event.get("title") or "").strip().casefold())
        current = deduplicated.get(key)
        if current is None:
            deduplicated[key] = event
            continue
        if (str(event.get("impact") or "").lower() == "high"
                and str(current.get("impact") or "").lower() != "high"):
            event, current = current, event
            deduplicated[key] = current
        for field in ("actual", "forecast", "previous"):
            if current.get(field) in (None, "") and event.get(field) not in (None, ""):
                current[field] = event[field]
    eligible = list(deduplicated.values())
    eligible.sort(key=lambda event: str(event.get("at") or ""))
    ranked = sorted(eligible, key=lambda event: (
        0 if str(event.get("impact") or "").lower() == "high" else 1,
        str(event.get("at") or "")))
    days = sorted({str(event.get("at") or "")[:10] for event in eligible})
    chosen = []
    if limit >= len(days):
        # สงวนหนึ่งที่ต่อวันที่มีข่าว เพื่อไม่ให้วันต้นสัปดาห์กินโควตาจนศุกร์หาย
        for day in days:
            chosen.append(next(event for event in ranked
                               if str(event.get("at") or "")[:10] == day))
    chosen_ids = {id(event) for event in chosen}
    for event in ranked:
        if len(chosen) >= limit:
            break
        if (id(event) not in chosen_ids
                and str(event.get("impact") or "").lower() == "high"):
            chosen.append(event)
            chosen_ids.add(id(event))
    # ที่เหลือเติมแบบวนรายวัน ไม่ปล่อยให้ข่าวปานกลางของวันเดียวกินพื้นที่ทั้งหมด
    medium_by_day = {
        day: [event for event in eligible
              if str(event.get("at") or "")[:10] == day
              and str(event.get("impact") or "").lower() == "medium"
              and id(event) not in chosen_ids]
        for day in days
    }
    while len(chosen) < limit and any(medium_by_day.values()):
        for day in days:
            if len(chosen) >= limit:
                break
            if medium_by_day[day]:
                event = medium_by_day[day].pop(0)
                chosen.append(event)
                chosen_ids.add(id(event))
    chosen.sort(key=lambda event: str(event.get("at") or ""))
    return chosen


def _calendar_sentence(event: dict) -> str:
    """ประโยคหลักฐานภายในของ D; รองรับทั้งค่าที่มีหน่วยและรายการไม่มีตัวเลข"""
    head = [wcb_writers.when(event["at"])]
    hhmm = wcb_writers.clock(event["at"])
    if hhmm:
        head.append(f"เวลา {hhmm} น.")
    text = " ".join(head) + f" มี {event['title']}"
    figures = [f"{label} {value}" for label, value in
               (("ผลจริง", event.get("actual")),
                ("คาดการณ์", event.get("forecast")),
                ("ครั้งก่อน", event.get("previous"))) if value]
    if figures:
        return text + " โดย" + " และ".join(figures)
    return text + " โดยยังไม่มีค่าอ้างอิงในระบบ จึงระบุได้แค่วันและเวลา"


def _weekly_calendar_payload(asset: str, events: list[dict], local_date: str) -> dict | None:
    selected = weekly_calendar_events(events, asset=asset, local_date=local_date)
    if not selected:
        return None
    annotated = []
    for event in selected:
        item = dict(event)
        item["asset_effect"] = weekly_event_asset_effect(item, asset)
        annotated.append(item)
    week_start, week_end = week_bounds(local_date)
    return {
        "sentences": [_calendar_sentence(event) for event in annotated],
        "events": annotated,
        "week_start": week_start,
        "week_end": week_end,
        "countries": list(CALENDAR_COUNTRIES.get(asset, ("USD",))),
    }


def _fetch_week(fetcher, week_start: str, week_end: str) -> dict:
    """ส่งช่วงสัปดาห์ให้ตัวดึงที่รองรับ โดยคง fake fetcher รุ่นเก่าในเทสไว้"""
    try:
        parameters = inspect.signature(fetcher).parameters.values()
    except (TypeError, ValueError):
        return fetcher()
    supports_keywords = any(parameter.kind == inspect.Parameter.VAR_KEYWORD
                            for parameter in parameters)
    names = {parameter.name for parameter in parameters}
    if supports_keywords or {"from_date", "to_date"} <= names:
        return fetcher(from_date=week_start, to_date=week_end)
    return fetcher()


def _clear_stale(folder: Path, asset: str) -> bool:
    """ลบบท+ภาพทุกใบของหัวข้อ — ของรอบก่อนต้องไม่นอนปนหน้าตาเหมือนของสด

    ภาพกวาดด้วย glob เพราะชื่อไฟล์มีวันที่ (`xauusd-d1-structure-<วัน>.webp`)
    และครอบชื่อยุคเก่าทุกแบบ (`xauusd-1.png`/`-2.png`) ไปในตัว

    กวาด**ทุกนามสกุลที่ไม่ใช่ `.md`** โดยตั้งใจ — ตั้งแต่ย้ายไป `.webp` (08-09)
    โฟลเดอร์ของวันเดียวกันอาจมี `.png` ของรอบก่อนค้าง ถ้ากวาดเฉพาะนามสกุลใหม่
    รูปเก่าจะนอนอยู่คู่รูปใหม่โดยหน้าตาเหมือนของสด และเป็นรูปที่เว็บตีกลับ
    """
    removed = False
    targets = [folder / f"{asset}.md"] + [
        path for path in folder.glob(f"{asset}*") if path.suffix.lower() != ".md"]
    for path in targets:
        if path.exists():
            path.unlink()
            removed = True
    return removed


def _calendar_block(asset: str) -> tuple[dict | None, str]:
    """ก้อนปฏิทินสำหรับหัวข้อปัจจัยพื้นฐาน (ฟีดแบ็กหัวหน้าข้อ 3 · มติผู้ใช้ 08-06 ดึก)

    ใช้ตัวคัดเดิม `wcb_writers._calendar_sentences` (กติกา "คัดด้วยความสำคัญ
    นำเสนอด้วยเวลา" ล็อกไว้ที่นั่น — ห้ามเขียนตัวคัดใหม่) · snapshot ล่ม/ไม่มีรหัส
    = บทออกโดยไม่มีหัวข้อนี้ ไม่พาสายทั้งเส้นล้ม (ปฏิทินเป็นส่วนเสริม ราคาเป็นแกน)

    **กลายเป็นสายสำรองตั้งแต่ 2026-08-10** — ค่าตั้งต้นของ `run_daily` คือ
    `calendar_block_from_feed()` (มีหน่วย + ปิด D-2) · สายนี้เหลือไว้สำหรับ
    `--no-calendar-feed` และต้อง**ตัดตัวเลขทั้งหมด**ก่อนเขียนประโยค เพราะช่อง
    `calendar` เดิมไม่มีข้อมูลหน่วย (ทีมเว็บรอบสี่ข้อ A-3: เลขเปล่า "4.09" หลุดขึ้นบทจริง)
    """
    try:
        evidence = wcb_source.fetch(asset)
        calendar_feed.strip_snapshot_values(evidence)
        local_date = evidence.get("local_date") or datetime.now(
            tz=wcb_source.BANGKOK).strftime("%Y-%m-%d")
        calendar = _weekly_calendar_payload(asset, evidence.get("calendar") or [], local_date)
    except Exception as exc:  # noqa: BLE001 — ส่วนเสริมห้ามพาบทล้ม เหตุถูกบันทึกใน result
        return None, f"unavailable: {exc}"
    if not calendar:
        return None, "empty"
    return calendar, "ok"


def calendar_block_from_feed(asset: str, *, local_date: str | None = None,
                             fetcher=calendar_feed.fetch_raw,
                             registry_path: Path | None = None) -> tuple[dict, str]:
    """สร้างปฏิทิน D จาก feed + strict relevance registry เท่านั้น.

    ความล้มเหลวของ feed/config ต้องส่ง exception ขึ้นไปให้ D fail-closed; ผลลัพธ์
    ว่างที่ถูกต้องยังคืน calendar empty-state หนึ่งหน้า จึงไม่ปะปนกับ dependency ล่ม.
    """
    today = local_date or datetime.now(tz=wcb_source.BANGKOK).strftime("%Y-%m-%d")
    week_start, week_end = style_d_calendar.week_bounds(today)
    try:
        raw = _fetch_week(fetcher, week_start, week_end)
    except style_d_calendar.StyleDCalendarUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 — แปลง I/O failure เป็น reason code เสถียร
        raise style_d_calendar.StyleDCalendarUnavailable(
            "calendar_feed_unusable", f"ปฏิทิน feed ใช้ไม่ได้: {exc}") from None
    calendar, _evidence = style_d_calendar.build_calendar(
        raw, calendar_feed.to_calendar_events(raw), asset=asset,
        local_date=today, registry_path=registry_path)
    return calendar, "empty" if calendar["empty_relevant"] else "ok"


def _local_date_for_cutoff(cutoff: str) -> str:
    stamp = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(wcb_source.BANGKOK).strftime("%Y-%m-%d")


def _ensure_calendar_manifest(calendar: dict | None, asset: str) -> dict | None:
    """แปลง fixture/ผู้เรียกรุ่นเก่าให้เป็น manifest หน้าเดียวโดยไม่แตะสายผลิตใหม่."""
    if not calendar or isinstance(calendar.get("pages"), list):
        return calendar
    events = []
    for event in calendar.get("events") or []:
        item = dict(event)
        item.setdefault("relevance", "indirect")
        item.setdefault("mechanism_th", "รายการจากแหล่งปฏิทินที่ผู้เรียกกำหนด")
        item.setdefault("direction", "undetermined")
        item.setdefault("row_units", 1)
        events.append(item)
    converted = dict(calendar)
    converted.update({"events": events, "pages": [events] if events else [[]],
                      "event_count": len(events), "empty_relevant": not events})
    converted.setdefault("evidence", {
        "schema": "style-d-calendar-evidence-v1", "asset": asset,
        "counts": {"included": len(events), "pages": 1}, "decisions": [],
    })
    return converted


def run(*, asset: str = DEFAULT_ASSET, publish_root: Path = Path("../output"),
        cutoff_at: str | None = None, fetcher=wcb_series_source.fetch_asset_rows,
        calendar_source=None,
        zone_state_dir: Path | None = None) -> dict:
    """`zone_state_dir`: ที่เก็บความจำโซน — เทส**ต้องส่ง tmp เสมอ** ไม่งั้นข้อมูล
    สังเคราะห์จะเขียนทับ state ของจริงแล้วรอบผลิตวันถัดไปโหลดของปลอม
    (เกิดจริงตอนพัฒนา 08-10: เทส pipeline ทิ้ง state ลงวันที่ 2026-02-24 ไว้)"""
    cutoff = cutoff_at or datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    day = publish_root / publish_layout.day_folder(cutoff)
    folder = day / chart_story_writer.FOLDER

    meta, rows, label = fetcher(asset)
    # 🐞 **A-1 (08-09):** ตัดแท่งที่ยังไม่ปิดทิ้ง **ก่อนทั้งการคำนวณและการวาดภาพ**
    # ตัดที่นี่ที่เดียวแล้วส่งชุดเดียวกันต่อทั้งสองทาง — ถ้าปล่อยให้ `build_story`
    # ตัดเองแล้วยังส่ง `rows` ชุดเดิมไปให้ตัววาด ภาพจะมีแท่งที่บทไม่นับอยู่ที่ขอบขวา
    rows, basis = candle_close.evaluate(rows, asset=asset)
    try:
        if calendar_source is None:
            calendar, calendar_status = calendar_block_from_feed(
                asset, local_date=_local_date_for_cutoff(cutoff))
        else:
            calendar, calendar_status = calendar_source(asset)
    except style_d_calendar.StyleDCalendarUnavailable:
        _clear_stale(folder, asset)
        try:
            from tools import publish_selection
            publish_selection.invalidate_if_selected(day, asset=asset,
                                                     style_id="d_chart_story")
        except Exception:
            pass
        raise
    calendar = _ensure_calendar_manifest(calendar, asset)
    # ความจำโซนข้ามวัน (ผู้ใช้เคาะ 08-10 #18ข) — pipeline คือจุดเดียวที่แตะ state
    # บนดิสก์ · state หาย/พัง load คืน None = คำนวณสดต่อ ไม่ตกทั้งบท
    locked = zone_memory.load(asset, state_dir=zone_state_dir)
    # วันเผยแพร่ = วันที่รอบผลิตนี้ออก (เขตเวลากรุงเทพ) — พาดหัวใช้ค่านี้ ไม่ใช่วันแท่งฐาน
    # (มติผู้ใช้ 08-14: ทุกสไตล์ต้องลงวันเดียวกันในรอบเดียวกัน)
    story = chart_story.build_story(
        rows, asset=asset, calendar=calendar, candle_basis=basis, locked=locked,
        publish_date=datetime.now(tz=wcb_source.BANGKOK).strftime("%Y-%m-%d"))
    markdown = chart_story_writer.render_article(story)
    validation = chart_story_writer.validate(markdown, story)

    result = {
        "asset": asset,
        "style": chart_story_writer.STYLE_NAME,
        "day": publish_layout.day_folder(cutoff),
        "directory": str(folder),
        "status": validation["status"],
        "char_count": validation["char_count"],
        "findings": validation["findings"],
        "source_label": label,
        "rows": len(rows),
        "calendar": calendar_status,
        "candle_basis": basis,
        # B-3.3: Title tag ออกมาจากระบบ ไม่ต้องมีใครพิมพ์เอง จึงเพี้ยนจาก H1 ไม่ได้
        "seo_title": chart_story_writer.seo_title(story),
    }
    if validation["status"] != "pass":
        result["removed_stale"] = _clear_stale(folder, asset)
        return result

    folder.mkdir(parents=True, exist_ok=True)
    _clear_stale(folder, asset)  # กวาดชุดเก่าก่อนวางใหม่ — ชื่อภาพผูกวันที่ เก่าค้างไม่ได้
    first_name, second_name = chart_story_writer.image_names(asset, story["current"]["date"])
    try:
        overview = chart_story_renderer.render_overview(story, rows, folder / first_name)
        zoom = chart_story_renderer.render_zoom(story, rows, folder / second_name)
        calendar_images = []
        if chart_story_writer.has_calendar_image(story):
            calendar_names = chart_story_writer.calendar_image_names(story)
            for page_record, filename in zip(calendar["evidence"].get("pages") or [],
                                             calendar_names):
                page_record["filename"] = filename
            calendar_images = chart_story_renderer.render_weekly_calendars(
                story, folder, calendar_names)
            evidence_path = folder / chart_story_writer.calendar_evidence_name(story)
            evidence_path.write_text(
                json.dumps(calendar["evidence"], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
        (folder / f"{asset}.md").write_text(markdown, encoding="utf-8")
    except Exception:
        # วาดล้มกลางคัน = ห้ามเหลือชุดครึ่ง ๆ กลาง ๆ ให้คนหยิบไปใช้
        _clear_stale(folder, asset)
        raise
    # อัปเดต state เฉพาะรอบที่ผ่านด่านและวางไฟล์แล้วจริง — รอบที่ตกด่านห้ามล็อก
    # ระดับชุดใหม่ (คนอ่านยังไม่เคยเห็นมัน จะเรียกว่า "โซนเดิม" ไม่ได้)
    result["zone_state"] = str(zone_memory.save(
        asset, zone_memory.build_state(story, previous=locked),
        state_dir=zone_state_dir))
    result["zone_memory"] = story.get("zone_memory")
    rendered_images = [overview, zoom] + calendar_images
    result.update({
        "article": str(folder / f"{asset}.md"),
        "images": [image["path"] for image in rendered_images],
        "image_kb": {Path(image["path"]).name: image["kb"]
                     for image in rendered_images},
        "overview": overview,
        "zoom": zoom,
        "weekly_calendar": calendar_images,
        "calendar_evidence": (str(folder / chart_story_writer.calendar_evidence_name(story))
                              if calendar_images else None),
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="สร้างบทสไตล์ D (อ่านโครงสร้างกราฟ) หนึ่งหัวข้อ")
    # คอนโซลไทย (cp874) พังเมื่อเจอ ✅/⚠️ — ตั้งก่อนพิมพ์อะไรทั้งนั้น (เหตุผลเดียวกับ
    # run_daily/brief_pipeline · เพิ่งกัดจริง 08-11: บทเขียนเสร็จแล้วแต่บรรทัดสรุปพังแทน)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser.add_argument("--asset", default=DEFAULT_ASSET)
    parser.add_argument("--publish-root", type=Path, default=Path("../output"))
    parser.add_argument("--cutoff-at", default=None)
    args = parser.parse_args(argv)
    try:
        result = run(asset=args.asset, publish_root=args.publish_root,
                     cutoff_at=args.cutoff_at)
    except (chart_story.StoryUnavailable,
            style_d_calendar.StyleDCalendarUnavailable,
            wcb_series_source.SeriesUnavailable,
            wcb_series_source.SeriesStaleData) as exc:
        print(f"⚠️ สไตล์ D ({args.asset}): {exc}")
        return 1
    if result["status"] == "pass":
        sizes = " · ".join(f"{name} {size} KB" for name, size in result["image_kb"].items())
        print(f"สไตล์ D ({args.asset}): ✅ บท {result['char_count']} อักขระ + "
              f"ภาพ {len(result['images'])} ใบ "
              f"→ {result['directory']}")
        print(f"   Title tag: {result['seo_title']}")
        print(f"   ฐานแท่ง: {result['candle_basis']['basis_session_date']} (ปิดแล้ว) · "
              f"{result['candle_basis']['rule']}")
        print(f"   ภาพ: {sizes} (เพดานเว็บ {image_output.kb(image_output.MAX_IMAGE_BYTES)} KB/ใบ)")
        return 0
    print(f"สไตล์ D ({args.asset}): ❌ ตกด่าน {len(result['findings'])} ข้อ — ไม่วางไฟล์")
    for finding in result["findings"]:
        print(f"   [{finding['rule']}] บรรทัด {finding['line']}: {finding['message']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
