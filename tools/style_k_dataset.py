"""ชั้นข้อมูลของ Style K pilot — เลือกแหล่ง ตัดที่ cutoff และ freeze แบบกันมองอนาคต

โมดูลนี้เป็น**ประตูเดียว**ที่ชั้นวิเคราะห์ใช้แตะข้อมูลราคา ทุกอย่างหลังจากนี้
(evidence / selector / scenario / article / chart) รับได้เฉพาะสิ่งที่ออกจากที่นี่

สามกติกาที่โมดูลนี้บังคับ และเหตุผลที่ต้องบังคับตรงนี้ไม่ใช่ปลายทาง:

1. **แท่งสุดท้ายของทุก snapshot ถือว่ายังไม่ปิด** — วัดจากของจริงแล้ว snapshot
   ที่เก็บระหว่างวันมีแท่งของวันนั้นค้างอยู่เป็นแถวท้ายเสมอ ถ้าไม่ตัดทิ้ง
   บทของวัน D จะเห็นราคาที่ยังวิ่งอยู่แล้วนับเป็น "ปิดแล้ว" (มติผู้ใช้ 2026-08-13)

2. **ชื่อโฟลเดอร์ build โกหกได้ ต้องอ่าน `cutoff_at` ในไฟล์** — โฟลเดอร์
   `2026-08-04T19-40Z-fix-style1` มี `cutoff_at` เป็น `2026-08-05T01:27:47Z`
   ถ้าจัดชั้นความน่าเชื่อถือจากชื่อโฟลเดอร์จะได้ tier ผิดทั้งชุด

3. **ตัดที่ cutoff ก่อนคำนวณ ไม่ใช่คำนวณแล้วค่อยกรอง** — indicator ทุกตัวกิน
   ทั้ง series ถ้าส่งของเกิน cutoff เข้าไปแล้วค่อยตัดผลลัพธ์ ค่าที่ได้ปนอนาคตไปแล้ว
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = REPO_ROOT.parent
CONFIG_PATH = REPO_ROOT / "config" / "style_k_pilot.json"
BUILD_ROOT = PROJECT_ROOT / "work" / "build"
PILOT_ROOT = PROJECT_ROOT / "work" / "style-k-fast-track-2026-08-14"

TIER_A = "A"
TIER_B = "B"
TIER_C = "C"


class DatasetUnusable(RuntimeError):
    """ไม่มีแหล่งที่ใช้ได้สำหรับ session นี้ — ต้องหยุด ไม่ใช่เดินต่อด้วยของใกล้เคียง"""


def load_config(path: Path | None = None) -> dict:
    return json.loads((path or CONFIG_PATH).read_text(encoding="utf-8"))


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hash_payload(payload) -> str:
    """แฮชของ "ความหมาย" ไม่ใช่ของไฟล์ — sort_keys ทำให้ลำดับคีย์ไม่ทำให้แฮชเพี้ยน

    ใช้ `\\n` ตายตัวและ ensure_ascii=False เพื่อไม่ให้ CRLF หรือการ escape ภาษาไทย
    ทำให้แฮชต่างกันระหว่างเครื่อง (กับดักที่เคยทำให้ hash ของชั้นภาษาเพี้ยนมาแล้ว)
    """
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- แท่งที่ปิดแล้ว

def closed_rows(rows: list[dict]) -> list[dict]:
    """ตัดแถวท้ายทิ้งเสมอ — ดูกติกาข้อ 1 ที่หัวไฟล์"""
    if len(rows) <= 1:
        return []
    return rows[:-1]


def rows_upto(rows: list[dict], session_date: str) -> list[dict]:
    """เก็บเฉพาะแท่งที่ `date <= session_date` — นี่คือจุดตัด no-lookahead จุดเดียว"""
    return [row for row in rows if row["date"] <= session_date]


def rows_after(rows: list[dict], session_date: str) -> list[dict]:
    return [row for row in rows if row["date"] > session_date]


# ---------------------------------------------------------------- สำรวจแหล่ง

def _read_snapshot(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not payload.get("rows"):
        return None
    return payload


def discover_snapshots(asset: str, *, build_root: Path | None = None,
                       extra_paths: list[Path] | None = None) -> list[dict]:
    """คืนรายการแหล่งของ asset นี้ เรียงตาม `cutoff_at` จากเก่าไปใหม่

    แต่ละรายการมี: path, cutoff_at, closed_dates (set), rows
    """
    root = build_root or BUILD_ROOT
    paths = sorted(root.glob(f"*/{asset}/internal/raw.snapshot.json"))
    paths.extend(extra_paths or [])

    found: list[dict] = []
    for path in paths:
        payload = _read_snapshot(path)
        if payload is None:
            continue
        closed = closed_rows(payload["rows"])
        if not closed:
            continue
        found.append({
            "path": path,
            "cutoff_at": payload.get("cutoff_at") or "",
            "rows": closed,
            "closed_dates": {row["date"] for row in closed},
            "provider": payload.get("provider"),
            "source": payload.get("source"),
        })
    found.sort(key=lambda item: item["cutoff_at"])
    return found


def _capture_lag_days(cutoff_at: str, session_date: str) -> int | None:
    try:
        captured = datetime.fromisoformat(cutoff_at).astimezone(timezone.utc).date()
    except (TypeError, ValueError):
        return None
    return (captured - date.fromisoformat(session_date)).days


def select_analysis_source(asset: str, session_date: str, *, snapshots: list[dict],
                           config: dict) -> dict:
    """เลือกแหล่งสำหรับชั้นวิเคราะห์ของวัน D และตัดสิน tier

    เลือก snapshot ที่ **เก็บเร็วที่สุด** ในบรรดาที่มีแท่งปิดของวัน D อยู่แล้ว —
    ยิ่งเก็บเร็ว โอกาสที่ provider แก้ค่าย้อนหลังยิ่งน้อย จึงเป็นตัวแทน
    point-in-time ที่ซื่อสัตย์ที่สุดเท่าที่มี
    """
    candidates = [snap for snap in snapshots if session_date in snap["closed_dates"]]
    if not candidates:
        raise DatasetUnusable(
            f"{asset} {session_date}: ไม่มี snapshot ใดที่มีแท่งปิดของวันนี้ — "
            "Tier C ห้ามใช้เป็น Golden Sample และห้ามเดาราคาจากไฟล์ภาพ/บทเก่า"
        )
    chosen = candidates[0]
    lag = _capture_lag_days(chosen["cutoff_at"], session_date)
    max_lag = config["tier_rule"]["a_max_capture_lag_days"]

    limitations: list[str] = []
    if lag is None:
        tier = TIER_C
        limitations.append("cutoff_at ของแหล่งอ่านไม่ได้ ตรวจสอบเวลาที่เก็บไม่ได้")
    elif lag <= max_lag:
        tier = TIER_A
    else:
        tier = TIER_B
        limitations.append(
            f"reconstructed_as_of: แหล่งที่เก่าที่สุดที่มีแท่งปิดของ {session_date} "
            f"ถูกเก็บช้ากว่าวันปิด {lag} วัน — ค่าอาจถูก provider แก้ย้อนหลังก่อนเราเก็บ"
        )
    return {
        "snapshot": chosen,
        "confidence_tier": tier,
        "capture_lag_days": lag,
        "limitations": limitations,
    }


def shared_sessions(snapshots_by_asset: dict[str, list[dict]]) -> list[str]:
    """วันทำการร่วมของทุก asset — ทองหยุดเสาร์อาทิตย์ คริปโทไม่หยุด

    ใช้ "session ร่วม" ไม่ใช่วันปฏิทิน เพื่อให้ H+1 ของสองหัวข้อหมายถึงช่วงเวลาเดียวกัน
    """
    sets = []
    for snaps in snapshots_by_asset.values():
        union: set[str] = set()
        for snap in snaps:
            union |= snap["closed_dates"]
        sets.append(union)
    if not sets:
        return []
    common = set.intersection(*sets)
    return sorted(common)


def horizon_sessions(calendar: list[str], session_date: str, steps: int) -> list[str]:
    """คืน session ร่วมถัดไป `steps` ตัวหลังวัน D — ไม่ครบคืนลิสต์สั้นกว่า ไม่เติมเอง"""
    later = [day for day in calendar if day > session_date]
    return later[:steps]


# ---------------------------------------------------------------- Inventory

def build_inventory(*, config: dict | None = None, build_root: Path | None = None,
                    extra_sources: dict[str, list[Path]] | None = None,
                    generated_at: str | None = None) -> dict:
    config = config or load_config()
    extra_sources = extra_sources or {}
    assets = list(config["assets"])

    snapshots = {
        asset: discover_snapshots(asset, build_root=build_root,
                                  extra_paths=extra_sources.get(asset))
        for asset in assets
    }
    calendar = shared_sessions(snapshots)

    entries: list[dict] = []
    for session_date in config["sessions"]:
        for asset in assets:
            entry = {
                "asset": asset,
                "session_date": session_date,
                "cutoff": f"{session_date}T23:59:59+00:00",
            }
            try:
                picked = select_analysis_source(asset, session_date,
                                                snapshots=snapshots[asset], config=config)
            except DatasetUnusable as exc:
                entry.update({
                    "confidence_tier": TIER_C,
                    "source_files": [],
                    "source_hashes": {},
                    "available_timeframes": [],
                    "bar_count_by_timeframe": {},
                    "has_volume_provenance": False,
                    "limitations": [str(exc)],
                    "horizons": {},
                })
                entries.append(entry)
                continue

            snap = picked["snapshot"]
            analysis_rows = rows_upto(snap["rows"], session_date)
            rel = str(snap["path"].relative_to(PROJECT_ROOT)).replace("\\", "/")
            entry.update({
                "confidence_tier": picked["confidence_tier"],
                "capture_lag_days": picked["capture_lag_days"],
                "source_files": [rel],
                "source_hashes": {rel: sha256_of(snap["path"])},
                "source_captured_at": snap["cutoff_at"],
                "available_timeframes": ["D1"],
                "bar_count_by_timeframe": {"D1": len(analysis_rows)},
                "last_analysis_bar": analysis_rows[-1]["date"] if analysis_rows else None,
                "has_volume_provenance": any("volume" in row for row in analysis_rows[-5:]),
                "limitations": list(picked["limitations"]),
                "horizons": {
                    "H+1": horizon_sessions(calendar, session_date, 1),
                    "H+3": horizon_sessions(calendar, session_date, 3),
                },
            })
            # ประวัติสั้นเป็นข้อจำกัด point-in-time จริง ไม่ใช่บั๊ก — snapshot ก่อน
            # 2026-08-05 เก็บแค่ 130 แท่งตามค่าตั้งต้นเดิมของสายท่อ เทคนิคที่ต้องการ
            # แท่งมากกว่านั้น (เช่น sma200) จึง `unavailable` ในวันเหล่านั้นโดยชอบธรรม
            depth = len(analysis_rows)
            for name, need in config["minimum_bars"].items():
                if depth < need:
                    entry["limitations"].append(
                        f"ประวัติ ณ วันนั้นมี {depth} แท่ง ไม่ถึง {need} ที่ '{name}' ต้องใช้ — เทคนิคที่พึ่งค่านี้เป็น unavailable"
                    )
            if len(entry["horizons"]["H+1"]) < 1:
                entry["limitations"].append("H+1 not_available: ไม่มี session ร่วมที่ปิดแล้วหลังวัน D")
            if len(entry["horizons"]["H+3"]) < 3:
                entry["limitations"].append("H+3 not_available: session ร่วมที่ปิดแล้วหลังวัน D ไม่ครบ 3 ตัว")
            entries.append(entry)

    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timezone": config["timezone"],
        "pilot_id": config["pilot_id"],
        "shared_session_calendar": calendar,
        "closed_bar_rule": config["closed_bar_rule"],
        "tier_rule": config["tier_rule"],
        "sessions": entries,
    }


def inventory_problems(inventory: dict) -> list[str]:
    """เกณฑ์รับของขั้น Inventory — คืนลิสต์ว่างแปลว่าผ่าน"""
    problems: list[str] = []
    entries = inventory["sessions"]
    if len(entries) != 14:
        problems.append(f"ต้องมี 14 entries ได้ {len(entries)}")

    seen = set()
    for entry in entries:
        key = (entry["asset"], entry["session_date"])
        if key in seen:
            problems.append(f"คู่ asset/date ซ้ำ: {key}")
        seen.add(key)

        if entry["confidence_tier"] == TIER_C:
            problems.append(f"{key}: Tier C — ไม่มีแหล่งที่มีแท่งปิดของวันนั้น")
            continue

        for rel, digest in entry["source_hashes"].items():
            path = PROJECT_ROOT / rel
            if not path.exists():
                problems.append(f"{key}: ไม่พบไฟล์ {rel}")
            elif sha256_of(path) != digest:
                problems.append(f"{key}: hash ไม่ตรงไฟล์ {rel}")

        last = entry.get("last_analysis_bar")
        if last is None or last > entry["session_date"]:
            problems.append(f"{key}: แท่งสุดท้ายของชั้นวิเคราะห์ = {last} เกิน cutoff")
        if not entry["horizons"].get("H+1"):
            problems.append(f"{key}: ไม่มี H+1 — evaluation ทำไม่ได้")
    return problems


# ---------------------------------------------------------------- Analysis bundle

def analysis_bundle(entry: dict, *, project_root: Path | None = None) -> dict:
    """โหลดแท่งของชั้นวิเคราะห์ตาม inventory entry — **ไม่มีทางคืนแท่งหลัง cutoff**

    ทุกผู้ใช้งานปลายทางต้องผ่านฟังก์ชันนี้ ไม่ใช่เปิดไฟล์ snapshot เอง
    """
    root = project_root or PROJECT_ROOT
    rel = entry["source_files"][0]
    payload = json.loads((root / rel).read_text(encoding="utf-8"))
    rows = rows_upto(closed_rows(payload["rows"]), entry["session_date"])
    return {
        "asset": entry["asset"],
        "session_date": entry["session_date"],
        "cutoff": entry["cutoff"],
        "confidence_tier": entry["confidence_tier"],
        "rows": rows,
        "source_files": entry["source_files"],
        "source_hashes": entry["source_hashes"],
        "limitations": list(entry["limitations"]),
    }


def evaluation_bundle(entry: dict, *, outcome_sources: dict[str, Path],
                      project_root: Path | None = None) -> dict:
    """แท่งหลังวัน D สำหรับชั้นวัดผล — เรียกได้ต่อเมื่อ freeze ของ session นี้ผ่านแล้ว

    คนละฟังก์ชันคนละไฟล์นำเข้ากับ `analysis_bundle` โดยตั้งใจ: ถ้าใครเผลอเรียก
    ตัวนี้ในชั้นวิเคราะห์ จะเห็นในโค้ดทันทีว่าผิด ไม่ใช่ธงบูลีนที่มองข้ามได้
    """
    root = project_root or PROJECT_ROOT
    path = outcome_sources[entry["asset"]]
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    closed = closed_rows(payload["rows"])
    horizons = entry["horizons"]
    wanted = set(horizons.get("H+3") or horizons.get("H+1") or [])
    return {
        "asset": entry["asset"],
        "session_date": entry["session_date"],
        "horizons": horizons,
        "rows": [row for row in closed if row["date"] in wanted],
        "source_file": str(Path(path).relative_to(root)).replace("\\", "/"),
        "source_hash": sha256_of(Path(path)),
    }
