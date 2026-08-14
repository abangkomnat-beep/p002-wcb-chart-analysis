"""ชั้นบรรณาธิการรายเช้า — ตรวจขอบเขตก่อนส่งต่อให้ ``tools.run_daily``.

ไม่ใส่ ``--confirm`` = preview อย่างเดียว ไม่เรียก API และไม่เขียนไฟล์ใด ๆ
ใส่ ``--confirm`` = บันทึก morning plan แล้วรันเฉพาะสินทรัพย์ในแผน
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import build_daily_package, publish_layout, publish_selection, run_daily, wcb_writers  # noqa: E402

SCHEMA_VERSION = 1
THAI_TZ = ZoneInfo("Asia/Bangkok")
DEFAULT_PLAN_ROOT = _REPO_ROOT / "work" / "editorial"
DEFAULT_OUTPUT_ROOT = _REPO_ROOT.parent / "output"
GOLD = "xauusd"


class MorningPlanError(ValueError):
    """คำสั่งเช้าขัดกับกติกาบรรณาธิการและต้องหยุดก่อนแตะสายผลิต."""


def normalize(values: list[str] | None) -> list[str]:
    return list(dict.fromkeys(value.strip().lower() for value in (values or []) if value.strip()))


def parse_run_date(value: str | None, *, today: date | None = None) -> date:
    if value is None:
        return today or datetime.now(THAI_TZ).date()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise MorningPlanError("--date ต้องเป็นรูปแบบ YYYY-MM-DD") from exc


def build_plan(*, write: list[str] | None = None, watch: list[str] | None = None,
               exclude: list[str] | None = None, run_date: date,
               confirmed: bool = False, now: datetime | None = None) -> dict:
    selected = normalize(write)
    watched = normalize(watch)
    excluded = normalize(exclude)
    known = set(build_daily_package.ASSETS)

    unknown = sorted(set(selected + excluded) - known)
    if unknown:
        raise MorningPlanError(
            f"ไม่รู้จักสินทรัพย์: {', '.join(unknown)} · รองรับ: {', '.join(sorted(known))}")
    if GOLD in excluded:
        raise MorningPlanError("งด xauusd ไม่ได้ เพราะทองคำเป็นบทบังคับวันละ 1 บท")
    conflicts = sorted(set(selected) & set(excluded))
    watch_conflicts = sorted(set(watched) & set(excluded))
    if conflicts or watch_conflicts:
        names = sorted(set(conflicts + watch_conflicts))
        raise MorningPlanError(f"รายการขัดแย้งกับหมวดงด: {', '.join(names)}")

    assets = [GOLD, *(asset for asset in selected if asset != GOLD)]
    stamp = now or datetime.now(timezone.utc)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_date": run_date.isoformat(),
        "timezone": "Asia/Bangkok",
        "write_assets": assets,
        "watch_topics": watched,
        "excluded_assets": excluded,
        "ownership": {
            GOLD: wcb_writers.author_slug_for(GOLD),
            "default": wcb_writers.author_slug_for("eurusd"),
        },
        "gold_daily_limit": 1,
        "event_extra_per_asset_limit": 1,
        "event_extra_site_limit": 3,
        "event_min_spacing_hours": 3,
        "confirmed": confirmed,
        "status": "confirmed",
        "created_at": stamp.isoformat(timespec="seconds"),
        "completed_at": None,
        "exit_code": None,
    }


def validate_plan(plan: dict) -> None:
    """Runtime validator แบบ fail-closed โดยไม่เพิ่ม dependency jsonschema."""
    required = {
        "schema_version", "run_date", "timezone", "write_assets", "watch_topics",
        "excluded_assets", "ownership", "gold_daily_limit",
        "event_extra_per_asset_limit", "event_extra_site_limit",
        "event_min_spacing_hours", "confirmed", "status",
    }
    missing = sorted(required - set(plan))
    if missing:
        raise MorningPlanError(f"morning plan ขาด field: {', '.join(missing)}")
    if plan["schema_version"] != 1 or plan["timezone"] != "Asia/Bangkok":
        raise MorningPlanError("schema_version หรือ timezone ของ morning plan ไม่ถูกต้อง")
    if not plan["write_assets"] or plan["write_assets"][0] != GOLD:
        raise MorningPlanError("write_assets ต้องขึ้นต้นด้วย xauusd")
    if len(plan["write_assets"]) != len(set(plan["write_assets"])):
        raise MorningPlanError("write_assets มีค่าซ้ำ")
    invalid_topics = [topic for topic in plan["watch_topics"]
                      if not re.fullmatch(r"[a-z0-9_-]+", topic)]
    if invalid_topics:
        raise MorningPlanError(
            f"watch topic ใช้ได้เฉพาะ a-z, 0-9, _ และ -: {', '.join(invalid_topics)}")
    if set(plan["write_assets"]) & set(plan["excluded_assets"]):
        raise MorningPlanError("write_assets ขัดกับ excluded_assets")
    if plan["ownership"] != {GOLD: "natthaphon-s", "default": "world-class-broker-team"}:
        raise MorningPlanError("ownership ไม่ตรงทะเบียนผู้เขียน")
    if (plan["gold_daily_limit"], plan["event_extra_per_asset_limit"],
            plan["event_extra_site_limit"], plan["event_min_spacing_hours"]) != (1, 1, 3, 3):
        raise MorningPlanError("เพดานบทความไม่ตรงกติกาที่อนุมัติ")


def plan_path(plan_root: Path, run_date: date) -> Path:
    return plan_root / f"{run_date.isoformat()}-morning-plan.json"


def save_plan(path: Path, plan: dict, *, exclusive: bool = False) -> None:
    validate_plan(plan)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "x" if exclusive else "w"
    with path.open(mode, encoding="utf-8", newline="\n") as stream:
        json.dump(plan, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def preview(plan: dict) -> str:
    others = [asset for asset in plan["write_assets"] if asset != GOLD]
    lines = [
        f"แผนเช้า P002 · {plan['run_date']} · Asia/Bangkok",
        f"ผลิต: {', '.join(plan['write_assets'])}",
        f"  - {GOLD}: natthaphon-s (บทหลักสูงสุด 1 บท)",
        f"  - สินทรัพย์อื่น: {', '.join(others) if others else 'ไม่มี'}"
        " · world-class-broker-team",
        f"เฝ้าข่าว: {', '.join(plan['watch_topics']) if plan['watch_topics'] else 'ไม่มี'}"
        " (เสนอเท่านั้น ไม่สร้างบท)",
        f"งด: {', '.join(plan['excluded_assets']) if plan['excluded_assets'] else 'ไม่มี'}",
    ]
    return "\n".join(lines)


_AUTHOR_RE = re.compile(r"(?m)^author_slug:\s*([^\s#]+)\s*$")


def verify_author_ownership(day_dir: Path, assets: list[str]) -> list[str]:
    """ตรวจทุกไฟล์บทที่ชื่อขึ้นต้นด้วย symbol; ไฟล์ประกอบชื่ออื่นไม่เกี่ยว."""
    findings: list[str] = []
    for asset in assets:
        expected = wcb_writers.author_slug_for(asset)
        for article in day_dir.rglob(f"{asset}*.md") if day_dir.is_dir() else ():
            text = article.read_text(encoding="utf-8")
            match = _AUTHOR_RE.search(text)
            if not match:
                findings.append(f"{article}: ไม่มี author_slug (ต้องเป็น {expected})")
            elif match.group(1) != expected:
                findings.append(f"{article}: author_slug={match.group(1)} ต้องเป็น {expected}")
    return findings


def run_confirmed(plan: dict, *, target: Path, output_root: Path) -> int:
    """บันทึก guard ก่อนรัน แล้วส่งเฉพาะ write_assets ให้ run_daily."""
    try:
        save_plan(target, plan, exclusive=True)
    except FileExistsError:
        raise MorningPlanError(
            f"วันนี้มี morning plan ที่ยืนยันแล้ว: {target} · ปฏิเสธการรันซ้ำเพื่อกันบททองซ้ำ")

    plan["status"] = "running"
    save_plan(target, plan)
    argv: list[str] = []
    for asset in plan["write_assets"]:
        argv.extend(["--asset", asset])
    argv.append("--skip-selection")

    original = Path.cwd()
    try:
        try:
            os.chdir(_REPO_ROOT)
            code = run_daily.main(argv)
        finally:
            os.chdir(original)
    except Exception as exc:  # noqa: BLE001 — ต้องปิด plan เป็น failed ก่อนคืนข้อผิดพลาด
        print(f"⚠️ สายผลิตหยุด: {exc}")
        code = 1

    cutoff = datetime.now(timezone.utc).isoformat(timespec="seconds")
    day_dir = output_root / publish_layout.day_folder(cutoff)
    findings = verify_author_ownership(day_dir, plan["write_assets"])
    if findings:
        for finding in findings:
            print(f"⚠️ {finding}")
        code |= 1

    # ชั้นเลือกเดิมยังรองรับใบขึ้นเว็บเพียงใบเดียว และ policy ปัจจุบันชี้ xauusd
    # จึงเรียกครั้งเดียวหลังทุกสินทรัพย์ผลิตเสร็จ ไม่ให้ run_daily เรียกซ้ำต่อ asset.
    if code == 0:
        selected = publish_selection.select(day_dir)
        if selected["status"] == "ready":
            print(f"ใบขึ้นเว็บทองคำ: {selected['article']}")
        else:
            print(f"⚠️ ยังไม่มีใบทองคำขึ้นเว็บ — {selected['expected']}")
            code |= 1

    plan["status"] = "completed" if code == 0 else "failed"
    plan["completed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    plan["exit_code"] = code
    save_plan(target, plan)
    return code


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description="วางแผนและรันกองบรรณาธิการ P002 ประจำเช้า")
    parser.add_argument("--write", action="append", metavar="ASSET")
    parser.add_argument("--watch", action="append", metavar="TOPIC")
    parser.add_argument("--exclude", action="append", metavar="ASSET")
    parser.add_argument("--date", metavar="YYYY-MM-DD")
    parser.add_argument("--confirm", action="store_true",
                        help="ไม่มีธงนี้ = preview เท่านั้น ไม่เขียนไฟล์และไม่เรียก API")
    parser.add_argument("--plan-root", type=Path, default=DEFAULT_PLAN_ROOT,
                        help=argparse.SUPPRESS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT,
                        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        run_date = parse_run_date(args.date)
        today = datetime.now(THAI_TZ).date()
        if args.confirm and run_date != today:
            raise MorningPlanError(
                "รุ่นแรกอนุญาต --date ย้อนหลังสำหรับ preview เท่านั้น; การผลิตต้องเป็นวันที่ไทยวันนี้")
        plan = build_plan(write=args.write, watch=args.watch, exclude=args.exclude,
                          run_date=run_date, confirmed=args.confirm)
        validate_plan(plan)
        print(preview(plan))
        if not args.confirm:
            print("\nPREVIEW เท่านั้น · เพิ่ม --confirm เมื่อตรวจรายการแล้ว")
            return 0
        return run_confirmed(plan, target=plan_path(args.plan_root, run_date),
                             output_root=args.output_root)
    except MorningPlanError as exc:
        print(f"หยุด: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
