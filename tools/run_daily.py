"""คำสั่งเดียวจบรอบวัน — แทนที่การพิมพ์ 3 คำสั่งเดิมด้วยคำสั่งเดียว

    python -m tools.run_daily

**คำสั่งผู้ใช้ล่าสุด: ปิดสายการผลิต A/B/C จาก `run_daily`**
รอบปกติคงไว้เฉพาะหลักฐานภายในและ lane D/E/M/L ที่อนุมัติ — ค่าตั้งต้นของคำสั่งนี้จึงเป็น:

    1. สายหลักฐานภายในคำนวณ D1 + level map + แผนเทรด + ด่านความเสี่ยง
       โดยไม่วาดกราฟและไม่สร้างบท ①②③ แม้แต่ใน work
    2. สาย public legacy A/B/C ไม่ถูกเรียกจาก run_daily และไม่วางลง output/<วัน>/
       แม้ระบุ --line public หรือใช้ค่าเริ่มต้น --line both
    3. สร้าง lane D/E/M/L และ local handoff ตามคำสั่ง/ตารางที่อนุมัติ
       โดยยังไม่ส่ง CMS/โซเชียลอัตโนมัติ
    4. 🆕 สไตล์ระหว่างวัน H/I/J (M15/M30) เฉพาะหัวข้อที่ทะเบียนเปิดไว้ —
       ผู้ใช้สั่งเปิดเข้ารอบวัน 2026-08-13 · คุมด้วยธง `production` ใน
       `config/article_styles.json` ไม่ใช่ธงบรรทัดคำสั่ง ⇒ ปิดทีละสไตล์ได้โดยไม่แก้โค้ด
    5. Style L — Forex Daily Trade Plan สำหรับ 5 คู่ Forex — ลงทะเบียนใน
       `config/article_styles.json` และรันเดี่ยวได้ด้วย `--style L`
    6. Style M — BTCUSD H1 Visual Daily เป็น BTC route ประจำวันแทน E+;
       E+ คงเรียกผ่าน manual pipeline โดยตรง ไม่ผ่าน daily route
    7. ยาม frontmatter ตรวจตัวรีโป + ../output ปิดท้าย

สายภายในเป็นหลักฐานและแผนประกอบเท่านั้น จึงห้ามวางลง `output/` ทุกกรณี
รวมถึงเมื่อเรียก `--line internal` โดยตรง ส่วนธงเก่า `--publish-internal` รับไว้แบบ
no-op ชั่วคราวเพื่อไม่ให้สคริปต์เดิมพัง แต่ไม่มีสิทธิ์เปิดการเผยแพร่อีก

**ตัวนี้เป็นแค่ตัวห่อของสายที่ยังเปิดใช้งาน** — เรียก `run_internal_line()` /
`dispatch()` ของ build_daily_package กับ `frontmatter_guard.main()`
ตรง ๆ ⇒ ด่านตรวจทุกชั้น (ข้อมูล/ความสด/ความละเอียด/สิทธิ์/ตัวเลขบทความ/ความยาว
รายสไตล์) ยังทำงานครบตามเดิม เพราะมันอยู่ข้างในสายท่อ ไม่ได้อยู่ที่ตัวสั่งงาน

exit code: 0 = ทุกหัวข้อสร้างสำเร็จและไม่มี frontmatter แปลกปลอม · ไม่เป็นศูนย์ = มีอย่างน้อย
หนึ่งอย่างสะดุด (ดูบรรทัดสรุปท้ายรอบว่าตัวไหน)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import brief_pipeline, build_daily_package, calendar_feed, chart_indicator_pipeline, chart_story_pipeline, frontmatter_guard  # noqa: E402
from tools import forex_daily_plan, intraday_pipeline, intraday_story, style_m_daily  # noqa: E402
from tools.hij_unified_adapter import HIJProductionRoute  # noqa: E402
from tools.d_unified_adapter import DProductionRoute  # noqa: E402
from tools.e_unified_adapter import EProductionRoute  # noqa: E402
from tools.f_unified_adapter import FProductionRoute  # noqa: E402
from tools.g_unified_adapter import GProductionRoute  # noqa: E402
from tools.m_unified_adapter import MProductionRoute  # noqa: E402
from tools.unified_registry import RegistryError, RegistryLoader, StyleEntry  # noqa: E402
from tools import country_first_output, localization_queue, publish_layout, publish_selection  # noqa: E402
from tools import normal_localization_orchestrator  # noqa: E402
from tools.daily_source_selector import (  # noqa: E402
    SourceSelectorError,
    source_keys_for_date,
)

DEFAULT_ASSETS = sorted(build_daily_package.ASSETS)
REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "article_styles.json"
STYLE_E = "E"
STYLE_M = style_m_daily.STYLE_LETTER
STYLE_CHOICES = (STYLE_E, forex_daily_plan.STYLE_LETTER, STYLE_M)
FOREX_ASSETS = tuple(forex_daily_plan.ASSETS)


def scheduled_lane_plan(source_business_date: str) -> dict[str, tuple[str, ...]]:
    """Return the one permitted production plan for a Bangkok business date.

    `daily_source_selector` owns this policy.  Keeping the small grouped view
    here lets the dispatcher decide which writers may be loaded and called;
    it must never fall back to the historical "all assets" default.
    """
    grouped: dict[str, list[str]] = {}
    for style, asset in source_keys_for_date(source_business_date):
        grouped.setdefault(style, []).append(asset.lower())
    return {style: tuple(assets) for style, assets in grouped.items()}


def default_batch_id(cutoff: datetime) -> str:
    """ชื่อ batch จากเวลาตัดข้อมูล — ห้ามมี `:` เพราะใช้เป็นชื่อโฟลเดอร์"""
    return cutoff.strftime("%Y-%m-%dT%H-%MZ-daily")


def load_l_registration(path: Path | None = None) -> StyleEntry:
    """โหลดทะเบียน Style L และหยุดก่อนแตะ network/output เมื่อ contract ไม่ตรงกัน"""
    registry = RegistryLoader().load(path or REGISTRY_PATH)
    try:
        entry = registry.styles[forex_daily_plan.STYLE_ID]
        unit = registry.execution_units[entry.execution_unit]
    except KeyError as exc:
        raise RegistryError(f"missing Style L registration: {exc.args[0]}") from exc
    if entry.letter != forex_daily_plan.STYLE_LETTER:
        raise RegistryError("Style L registration has the wrong letter")
    if entry.adapter != "forex_daily_plan" or entry.execution_unit != "L_FOREX_DAILY":
        raise RegistryError("Style L must use L_FOREX_DAILY/forex_daily_plan")
    if tuple(unit.members) != (forex_daily_plan.STYLE_ID,):
        raise RegistryError("L_FOREX_DAILY must contain only l_forex_daily_plan")
    if tuple(entry.assets) != tuple(forex_daily_plan.ASSETS):
        raise RegistryError("Style L registry assets do not match the production implementation")
    if tuple(entry.timeframes) != tuple(forex_daily_plan.TIMEFRAMES):
        raise RegistryError("Style L registry timeframes do not match the production implementation")
    if entry.line_eligibility != build_daily_package.LINE_PUBLIC:
        raise RegistryError("Style L must be public-line eligible")
    if unit.execute_once_per_asset:
        raise RegistryError("L_FOREX_DAILY must execute once per selected asset batch")
    return entry


def run_style_l(assets: list[str], cutoff: str) -> tuple[int, dict | None]:
    """รัน Style L พร้อมสรุปมาตรฐานเดียวกันทั้งรอบเต็มและ `--style L`"""
    try:
        result = forex_daily_plan.run_round(
            assets=assets, publish_root=Path("../output"), cutoff_at=cutoff)
    except Exception as exc:  # noqa: BLE001 — ต้องแปลงเป็นผล fail-closed ของรอบ
        print(f"⚠️ {forex_daily_plan.STYLE_NAME}: {exc}")
        return 1, None
    if result["ok"]:
        statuses = ", ".join(
            f"{asset.upper()}={item['readiness']}"
            for asset, item in result["assets"].items())
        destination = result.get("destination")
        suffix = (f" → {destination}" if destination else
                  " · ไม่มีไฟล์เข้า web-import (asset ถูก HOLD)")
        print(f"{forex_daily_plan.STYLE_NAME}: ✅ {statuses}{suffix}")
        return 0, result
    print(f"⚠️ {forex_daily_plan.STYLE_NAME}: ตกด่าน fail-closed — ไม่วางไฟล์ · "
          + " | ".join(result["errors"]))
    return 1, result


def scheduled_style_l_assets(cutoff: str) -> list[str] | None:
    """คืน batch ตามตาราง; contract เสียคืน None เพื่อหยุดก่อนรันสายข้อมูล."""
    try:
        return forex_daily_plan.scheduled_assets(cutoff)
    except RuntimeError as exc:
        print(f"⚠️ ตาราง Style L ใช้งานไม่ได้ — {exc}")
        return None


def run_style_e(route: EProductionRoute, assets: list[str], cutoff: str) -> tuple[int, list[dict]]:
    """Run legacy Style E only; BTCUSD E+ is not a daily-route option."""
    code = 0
    results: list[dict] = []
    for asset in assets:
        try:
            result = route.run_round(
                asset=asset, publish_root=Path("../output"), cutoff_at=cutoff)
        except Exception as exc:  # noqa: BLE001 — surface the failed asset and continue
            print(f"⚠️ สไตล์ E ({asset}): {exc}")
            code |= 1
            continue
        results.append(dict(result))
        if result.get("status") != "pass":
            print(f"⚠️ สไตล์ E ({asset}): ตกด่าน {len(result.get('findings') or [])} ข้อ — ไม่วางไฟล์")
            code |= 1
            continue
        if result.get("variant") == "e_plus_h1_m15":
            print(f"สไตล์ E+ ({asset}): ✅ บท {result['char_count']} อักขระ "
                  f"+ ภาพ H1/M15 2 ใบ → {result['directory']}")
        else:
            print(f"สไตล์ E ({asset}): ✅ บท {result['char_count']} อักขระ "
                  f"+ ภาพรวมใบเดียว → {result['directory']}")
    return code, results


def run_style_m(route: MProductionRoute, cutoff: str, *, publish: bool = True) -> tuple[int, dict | None]:
    """Run BTCUSD Style M from the latest H1 closed before invocation."""
    try:
        result = route.run_round(
            asset=style_m_daily.ASSET, publish_root=Path("../output"),
            work_root=Path("../work/build"), cutoff_at=cutoff, publish=publish)
    except style_m_daily.DailyStyleMNotDue as exc:
        print(f"Style M: ข้ามรอบ — {exc}")
        return 0, {"status": "skipped", "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001 — fail closed without hiding the cause
        print(f"⚠️ {style_m_daily.STYLE_NAME}: {exc}")
        return 1, None
    if result.get("status") != "pass":
        print(f"⚠️ {style_m_daily.STYLE_NAME}: ผลลัพธ์ไม่ผ่าน")
        return 1, result
    destination = result.get("directory") or result.get("shadow")
    print(f"{style_m_daily.STYLE_NAME}: ✅ {result.get('state')} → {destination}")
    return 0, result


def main(argv: list[str] | None = None) -> int:
    # คอนโซลไทย (cp874) พังเมื่อเจออักขระอย่าง `·` — ตั้งก่อนพิมพ์อะไรทั้งนั้น
    # (เหตุผลเดียวกับใน build_daily_package.main)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="รันรอบวันของ P002 ครบทุกขั้นด้วยคำสั่งเดียว")
    parser.add_argument("--asset", action="append", choices=DEFAULT_ASSETS,
                        help="ไม่ระบุ = ครบทุกสินทรัพย์และทุกสไตล์ที่เปิดในทะเบียน")
    parser.add_argument("--style", type=str.upper, choices=STYLE_CHOICES,
                        help="รันเฉพาะสไตล์ที่ระบุ (รองรับ: E, L, M)")
    parser.add_argument("--line", choices=[build_daily_package.LINE_INTERNAL,
                                           build_daily_package.LINE_PUBLIC,
                                           build_daily_package.LINE_BOTH],
                        default=build_daily_package.LINE_BOTH,
                        help="ไม่ระบุ = both (หลักฐานภายใน + สาย D/E/M/L; A/B/C ปิดจาก daily route)")
    parser.add_argument("--batch-id", help="ไม่ระบุ = สร้างจากเวลาปัจจุบัน (UTC)")
    parser.add_argument("--dry-run", action="store_true",
                        help="แสดงรายการตามตารางของวัน แล้วออกโดยไม่โหลดข้อมูลหรือเขียนไฟล์")
    parser.add_argument("--include-experimental", action="store_true",
                        help="เปิด F/G/H/I/J ที่อยู่นอกตารางหลักสำหรับงานทดลองที่ระบุชัดเจน")
    # เก็บ parser compatibility ให้คำสั่งเก่าไม่พัง แต่ปิดสิทธิ์เผยแพร่ถาวรตามคำสั่ง
    # ผู้ใช้ 2026-08-24 — ถอดตัวเขียน ①②③ เหลือเฉพาะหลักฐานภายใน
    parser.add_argument("--publish-internal", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--skip-guard", action="store_true",
                        help="ข้ามยาม frontmatter — ใช้เฉพาะตอนรันทดลองที่ไม่ได้จะส่งของ")
    parser.add_argument("--skip-selection", action="store_true",
                        help="ไม่ต้องวางโฟลเดอร์ใบขึ้นเว็บ (config/publishing_policy.json)")
    parser.add_argument("--skip-localization-queue", action="store_true",
                        help="ข้ามการออก receipt คิว localization — ใช้เฉพาะการทดสอบที่ไม่ใช่รอบส่งมอบ")
    parser.add_argument("--skip-style-d", action="store_true",
                        help="ข้ามบทสไตล์ D (อ่านโครงสร้างกราฟ + ภาพ 2–3 ใบ)")
    parser.add_argument("--skip-style-e", action="store_true",
                        help="ข้ามบทสไตล์ E (อ่านอินดิเคเตอร์ RSI/MACD/Fibonacci "
                             "+ ภาพรวมใบเดียว)")
    parser.add_argument("--skip-style-fg", action="store_true",
                        help="ข้ามบทเช้าสไตล์ F/G (ระบบเลือก F หรือ G เองตามเงื่อนไขวัน)")
    parser.add_argument("--skip-style-hij", action="store_true",
                        help="ข้ามบทระหว่างวันสไตล์ H/I/J (M15/M30) ทั้งรอบ "
                             "— ปิดทีละสไตล์ให้ตั้ง production=false ในทะเบียนแทน")
    parser.add_argument("--skip-forex-daily-plan", action="store_true",
                        help="ข้าม Forex Daily Plan ของคู่เงินทั้ง 5 คู่ทั้งรอบ")
    parser.add_argument("--fg-single", action="store_true",
                        help="บทเช้าออกสไตล์เดียวต่อวันแบบเดิม — ค่าตั้งต้นคือออกทั้ง F "
                             "และ G ในวันที่เงื่อนไข G ครบ (ผู้ใช้สั่ง 2026-08-13)")
    # เปิดเป็นค่าตั้งต้นตั้งแต่ 2026-08-10 — ดูเหตุผลเดียวกับใน build_daily_package.main
    parser.add_argument("--calendar-feed", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="ใช้ /api/calendar/feed แทนช่อง calendar เดิมใน snapshot "
                             "ทั้ง A/B/C และ D — เปิดเป็นค่าตั้งต้น "
                             "· --no-calendar-feed = สายเก่าแบบตัดตัวเลขทั้งหมด")
    parser.add_argument("--resume-localization", metavar="YYYY-MM-DD",
                        help="resume frozen localization jobs only; do not rebuild Thai source")
    parser.add_argument("--recovery-bundle", metavar="PATH",
                        help="opt-in hash-bound source recovery bundle for localization dispatch")
    args = parser.parse_args(argv)
    if args.resume_localization:
        if args.skip_localization_queue or args.style or args.asset or args.include_experimental:
            parser.error("--resume-localization cannot be combined with source/skip queue overrides")
        try:
            dispatch_options = {"dry_run": args.dry_run}
            if args.recovery_bundle:
                dispatch_options["recovery_bundle_path"] = Path(args.recovery_bundle)
            result = normal_localization_orchestrator.run(
                Path(__file__).resolve().parents[2], args.resume_localization, **dispatch_options)
        except (normal_localization_orchestrator.DispatchError, localization_queue.QueueError) as exc:
            print(json.dumps({"status": "HOLD", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        # Dispatch is work awaiting agents, never proof of daily delivery.
        return 2
    cutoff_dt = datetime.now(tz=timezone.utc)
    cutoff = cutoff_dt.isoformat(timespec="seconds")
    business_date = cutoff_dt.astimezone(ZoneInfo("Asia/Bangkok")).date().isoformat()
    try:
        daily_plan = scheduled_lane_plan(business_date)
    except SourceSelectorError as exc:
        print(f"⚠️ ตารางรอบวันใช้งานไม่ได้ — {exc}")
        return 1

    # A normal daily invocation may produce only the published calendar lanes.
    # A caller who asks for a subset gets the same guard; experimental work is
    # an explicit opt-in and cannot happen by accident through the default.
    if not args.include_experimental:
        if args.style is not None:
            permitted = set(daily_plan.get(args.style, ()))
            requested = set(args.asset or permitted)
            out_of_schedule = sorted(requested - permitted)
            if out_of_schedule:
                parser.error("NOT_SCHEDULED สำหรับวัน " + business_date + ": "
                             + ", ".join(f"{args.style}-{asset.upper()}" for asset in out_of_schedule))
        elif args.asset:
            permitted_assets = {asset for assets in daily_plan.values() for asset in assets}
            out_of_schedule = sorted(set(args.asset) - permitted_assets)
            if out_of_schedule:
                parser.error("NOT_SCHEDULED สำหรับวัน " + business_date + ": "
                             + ", ".join(asset.upper() for asset in out_of_schedule))
    if args.style == forex_daily_plan.STYLE_LETTER:
        if args.line == build_daily_package.LINE_INTERNAL:
            parser.error("--style L ใช้กับ --line internal ไม่ได้ เพราะ L เป็นบทสาย public")
        if args.skip_forex_daily_plan:
            parser.error("--style L ใช้พร้อม --skip-forex-daily-plan ไม่ได้")
    if args.style == STYLE_E:
        if args.line == build_daily_package.LINE_INTERNAL:
            parser.error("--style E ใช้กับ --line internal ไม่ได้ เพราะ E เป็นบทสาย public")
        if args.skip_style_e:
            parser.error("--style E ใช้พร้อม --skip-style-e ไม่ได้")
        if args.asset and style_m_daily.ASSET in args.asset:
            parser.error("E+ ถูกปิดจาก run_daily; BTCUSD ให้ใช้ Style M หรือทาง manual โดยตรง")
    if args.style == STYLE_M and args.line == build_daily_package.LINE_INTERNAL:
        parser.error("--style M ใช้กับ --line internal ไม่ได้ เพราะ M เป็นบทสาย public")

    if args.dry_run:
        payload = {
            "business_date": business_date,
            "lanes": [
                {"style": style, "asset": asset}
                for style, assets in daily_plan.items() for asset in assets
            ],
            "experimental_lanes_enabled": args.include_experimental,
        }
        if not args.skip_localization_queue:
            project_root = Path(__file__).resolve().parents[2]
            index_path = project_root / "work" / "localization" / "admission-index.json"
            try:
                queue = localization_queue.select(project_root=project_root, output_root=project_root / "output",
                                                   business_date=business_date, index_path=index_path,
                                                   scope=None,
                                                   policy_path=localization_queue.default_policy_path(project_root))
                payload["localization_queue"] = {"selected": queue["selected"], "held": queue["held"]}
            except localization_queue.QueueError as exc:
                payload["localization_queue"] = {"status": "HOLD", "reason": str(exc)}
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 1
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not daily_plan and not args.include_experimental:
        print("NOT_SCHEDULED: ไม่มีงานรายวันในวันเสาร์–อาทิตย์")
        return 0

    # Validate only routes which this date is allowed to call before any
    # pipeline can fetch or write.  In particular, a Wednesday default run
    # must not even initialise D/F/G/H/I/J writers.
    # write.  A broken registry therefore fails closed with zero side effects.
    hij_route = None
    d_route = None
    e_route = None
    f_route = None
    g_route = None
    l_registration = None
    m_route = None
    if args.line != build_daily_package.LINE_INTERNAL:
        try:
            if args.style is None:
                if args.include_experimental and not args.skip_style_hij:
                    hij_route = HIJProductionRoute.load()
                if not args.skip_style_d and daily_plan.get("D"):
                    d_route = DProductionRoute.load()
                if not args.skip_style_e and daily_plan.get(STYLE_E):
                    e_route = EProductionRoute.load()
                if args.include_experimental and not args.skip_style_fg:
                    f_route = FProductionRoute.load()
                    g_route = GProductionRoute.load()
            elif args.style == STYLE_E:
                e_route = EProductionRoute.load()
            if ((args.style is None and daily_plan.get(STYLE_M))
                    or args.style == STYLE_M):
                m_route = MProductionRoute.load()
            if ((args.style is None and daily_plan.get(forex_daily_plan.STYLE_LETTER)
                 or args.style == forex_daily_plan.STYLE_LETTER)
                    and not args.skip_forex_daily_plan):
                l_registration = load_l_registration()
        except RegistryError as exc:
            print(f"⚠️ ทะเบียน Unified ใช้งานไม่ได้ — {exc}")
            return 1

    batch_id = args.batch_id or default_batch_id(cutoff_dt)

    def normalize_country_first_output() -> int:
        """Complete legacy handoff even for a style-only invocation."""
        business_date = cutoff_dt.astimezone(ZoneInfo("Asia/Bangkok")).date().isoformat()
        try:
            migrated = country_first_output.migrate_day(
                output_root=Path("../output"), work_root=Path("../work"),
                business_date=business_date)
            repaired = country_first_output.repair_canonical_day(
                output_root=Path("../output"), work_root=Path("../work"),
                business_date=business_date)
            moved = [f"{item['style']}/{item['asset']}" for item in migrated["records"]
                     if item["status"] == "migrated"]
            fixed = [f"{item['style']}/{item['asset']}" for item in repaired["records"]]
            if moved:
                print("country-first output: " + ", ".join(moved))
            if fixed:
                print("country-first image names repaired: " + ", ".join(fixed))
            return 0
        except Exception as exc:
            print(f"⚠️ country-first output migration failed: {exc}")
            return 1

    if args.style == forex_daily_plan.STYLE_LETTER:
        selected_assets = args.asset
        if selected_assets is None:
            selected_assets = list(daily_plan.get("L", ()))
            if selected_assets is None:
                return 1
            if not selected_assets:
                print("Style L: เสาร์–อาทิตย์ข้ามรอบ Forex ตามตารางประจำสัปดาห์")
                return 0
        unsupported = [asset for asset in selected_assets if asset not in l_registration.assets]
        if unsupported:
            parser.error("Style L ไม่รองรับ asset: " + ", ".join(unsupported))
        print(f"รอบเฉพาะ Style L · batch {batch_id} · หัวข้อ {', '.join(selected_assets)}")
        style_code, style_result = run_style_l(selected_assets, cutoff)
        guard_code = 0
        if (not args.skip_guard and style_result and style_result.get("ok")
                and style_result.get("destination")):
            print("ยาม frontmatter — ผลผลิต Style L:")
            guard_code = frontmatter_guard.main([str(style_result["destination"])])
        code = style_code | guard_code
        code |= normalize_country_first_output()
        print("สรุป Style L: " + ("✅ สำเร็จ" if code == 0 else "⚠️ มีด่านที่ไม่ผ่าน"))
        return code

    if args.style == STYLE_M:
        selected_assets = args.asset or [style_m_daily.ASSET]
        unsupported = [asset for asset in selected_assets if asset not in m_route.assets]
        if unsupported:
            parser.error("Style M ไม่รองรับ asset: " + ", ".join(unsupported))
        print(f"รอบเฉพาะ Style M · batch {batch_id} · หัวข้อ btcusd")
        style_code, style_result = run_style_m(m_route, cutoff)
        guard_code = 0
        if (not args.skip_guard and style_result and style_result.get("status") == "pass"
                and style_result.get("directory")):
            print("ยาม frontmatter — ผลผลิต Style M:")
            guard_code = frontmatter_guard.main([str(style_result["directory"])])
        code = style_code | guard_code
        code |= normalize_country_first_output()
        print("สรุป Style M: " + ("✅ สำเร็จ" if code == 0 else "⚠️ มีด่านที่ไม่ผ่าน"))
        return code

    if args.style == STYLE_E:
        selected_assets = [asset for asset in (args.asset or list(daily_plan.get("E", ())))
                           if asset != style_m_daily.ASSET]
        unsupported = [asset for asset in selected_assets if asset not in e_route.assets]
        if unsupported:
            parser.error("Style E ไม่รองรับ asset: " + ", ".join(unsupported))
        print(f"รอบเฉพาะ Style E · batch {batch_id} · หัวข้อ {', '.join(selected_assets)}")
        style_code, style_results = run_style_e(e_route, selected_assets, cutoff)
        guard_code = 0
        if not args.skip_guard:
            for result in style_results:
                if result.get("status") == "pass":
                    guard_code |= frontmatter_guard.main([str(result["directory"])])
        code = style_code | guard_code
        code |= normalize_country_first_output()
        print("สรุป Style E: " + ("✅ สำเร็จ" if code == 0 else "⚠️ มีด่านที่ไม่ผ่าน"))
        return code

    # ประกอบชุดธงให้เหมือนพิมพ์คำสั่งเต็มเป๊ะ — ค่าตั้งต้นทุกตัวคัดลอกจาก parser ของ
    # build_daily_package ห้ามคิดค่าใหม่ตรงนี้ ไม่งั้นสองทางเข้าให้ผลต่างกัน
    def line_args(line: str, *, no_publish: bool,
                  asset_list: list[str]) -> argparse.Namespace:
        return argparse.Namespace(
            asset=asset_list,
            line=line,
            batch_id=batch_id,
            output_root=Path("../work/build"),
            publish_root=Path("../output"),
            no_publish=no_publish,
            snapshot=None,
            cutoff_at=cutoff,
            source=None,
            max_bar_age_days=build_daily_package.wcb_series_source.MAX_BAR_AGE_DAYS,
            no_news=False,
            no_trade_plan=False,
            skip_c_event=(line == build_daily_package.LINE_PUBLIC),
            calendar_feed=args.calendar_feed,
        )

    # Do not derive the daily batch from DEFAULT_ASSETS.  That historical
    # value contains work that is not scheduled today and was the direct cause
    # of unwanted Thai F/G/H/I/J output.  The selector's keys are authoritative.
    planned_assets = list(dict.fromkeys(
        asset for style_assets in daily_plan.values() for asset in style_assets))
    assets = args.asset or planned_assets
    core_assets = [asset for asset in assets if asset not in FOREX_ASSETS]
    forex_assets = [asset for asset in assets if asset in FOREX_ASSETS]
    build_code = 0
    print(f"รอบวัน P002 · batch {batch_id} · สาย {args.line} · หัวข้อ {', '.join(assets)}")

    if args.publish_internal:
        print("ธง --publish-internal ถูกยกเลิกแล้ว — สายภายใน "
              "สร้างเฉพาะหลักฐานและจะไม่สร้างบท ①②③")

    if args.line == build_daily_package.LINE_BOTH:
        # A/B/C ถูกปิดจากรอบผลิตปกติแล้ว — ห้ามเรียก run_public_line เพราะ
        # legacy public line จะสร้าง A/B/C ลง output แม้จะใช้ --skip-selection
        print("สายหลักฐานภายใน: คำนวณ D1 + level map + แผนเทรด + risk audit "
              "โดยไม่สร้าง A/B/C หรือบท ①②③")
        if core_assets:
            build_code = build_daily_package.run_internal_line(
                line_args(build_daily_package.LINE_INTERNAL,
                          no_publish=True, asset_list=core_assets), cutoff)
        else:
            print("ไม่มีสินทรัพย์ non-Forex — ข้ามสายหลักฐานภายใน")
    elif args.line == build_daily_package.LINE_PUBLIC:
        # คง flag เพื่อ compatibility แต่ปิด legacy A/B/C อย่างเด็ดขาดใน run_daily
        print("สาย public legacy A/B/C ถูกปิดจาก run_daily — ข้ามสายนี้")
        build_code = 0
    else:
        if core_assets:
            build_code = build_daily_package.dispatch(
                line_args(args.line,
                          no_publish=args.line == build_daily_package.LINE_INTERNAL,
                          asset_list=core_assets), cutoff)
        else:
            build_code = 0
            print("ไม่มีสินทรัพย์ non-Forex — ข้ามสายอื่นตาม L-only contract")

    # สไตล์ D/E/F/G — เข้าสายหลัก**ครบทุกหัวข้อ** ตามคำสั่งผู้ใช้ 2026-08-11
    # (เดิม D/E จำกัดเฉพาะทอง และ F/G ยังไม่เข้ารอบเลย — นโยบาย "วันละ 1 บทเฉพาะทอง"
    #  เป็นเรื่องใบขึ้นเว็บใน publishing_policy.json ไม่ใช่เรื่องการผลิต)
    # ล้มรายหัวข้อ = รายงานหัวข้อนั้นสะดุด ไม่ดึงสายอื่นล้มตาม (หลักเดิมของสายเสริม)
    if (not args.skip_style_d and d_route is not None
            and args.line != build_daily_package.LINE_INTERNAL):
        for asset in [asset for asset in core_assets if asset in daily_plan.get("D", ())]:
            print()
            try:
                style_d = d_route.run_round(
                    asset=asset, publish_root=Path("../output"), cutoff_at=cutoff)
            except Exception as exc:  # noqa: BLE001 — สายเสริมห้ามพาทั้งรอบล้ม
                print(f"⚠️ สไตล์ D ({asset}): {exc}")
                build_code |= 1
            else:
                if style_d["status"] == "pass":
                    image_count = len(style_d.get("images") or []) or 2
                    print(f"สไตล์ D ({asset}): ✅ บท + ภาพ {image_count} ใบ "
                          f"→ {style_d['directory']}")
                else:
                    print(f"⚠️ สไตล์ D ({asset}): ตกด่าน {len(style_d['findings'])} ข้อ — ไม่วางไฟล์")
                    build_code |= 1

    if (not args.skip_style_e and e_route is not None
            and args.line != build_daily_package.LINE_INTERNAL):
        e_assets = [asset for asset in core_assets
                    if asset in e_route.assets and asset in daily_plan.get(STYLE_E, ())]
        # ผู้ใช้สั่ง 2026-08-28: BTCUSD default ใช้ M; E+ เก็บ manual เท่านั้น
        if args.style is None:
            e_assets = [asset for asset in e_assets if asset != style_m_daily.ASSET]
        if e_assets:
            print()
            style_e_code, _ = run_style_e(e_route, e_assets, cutoff)
            build_code |= style_e_code

    # Style M — BTCUSD default daily route; E+ ไม่รันในรอบปกติแล้ว
    if (args.style is None and m_route is not None and m_route.production
            and args.line != build_daily_package.LINE_INTERNAL
            and style_m_daily.ASSET in core_assets
            and style_m_daily.ASSET in daily_plan.get(STYLE_M, ())):
        print()
        style_m_code, _ = run_style_m(m_route, cutoff)
        build_code |= style_m_code

    # สไตล์ F/G (บทเช้า) — **วันที่เงื่อนไข G ครบ ได้ทั้งคู่** (ผู้ใช้สั่ง 2026-08-13)
    # วันที่ไม่ครบได้ F ใบเดียวตามเดิม เพราะ G ที่เงื่อนไขไม่ครบคือบทที่ขัดกับรูปของ
    # ตัวเอง ไม่ใช่บทที่หายไป · `--fg-single` = กลับพฤติกรรมเดิม (สไตล์เดียวต่อวัน)
    experimental_root = Path("../work") / "experimental" / publish_layout.day_folder(cutoff)
    if (args.include_experimental and not args.skip_style_fg
            and args.line != build_daily_package.LINE_INTERNAL):
        for asset in core_assets:
            print()
            try:
                runner = brief_pipeline.run if args.fg_single else brief_pipeline.run_pair
                results = runner(asset=asset, publish_root=experimental_root,
                                 cutoff_at=cutoff)
            except Exception as exc:  # noqa: BLE001 — สายเสริมห้ามพาทั้งรอบล้ม
                print(f"⚠️ สไตล์ F/G ({asset}): {exc}")
                build_code |= 1
            else:
                for style_fg in ([results] if args.fg_single else results):
                    if style_fg["ok"]:
                        print(f"สไตล์ {style_fg['style_name']} ({asset}): ✅ บท + ภาพกรอบราคา "
                              f"→ {style_fg['folder']}")
                    else:
                        print(f"⚠️ สไตล์ {style_fg['style_name']} ({asset}): "
                              f"ตกด่าน {len(style_fg['findings'])} ข้อ — ไม่วางไฟล์")
                        build_code |= 1

    # สไตล์ H/I/J (ระหว่างวัน M15/M30) — เข้ารอบวันตามคำสั่งผู้ใช้ 2026-08-13
    # คุมด้วยธง `production` ในทะเบียน `config/article_styles.json` ⇒ ปิดกลับทีละสไตล์
    # ได้โดยไม่ต้องแก้ไฟล์นี้ · หัวข้อที่ไม่มีสไตล์ไหนเปิดอยู่จะถูกข้ามตั้งแต่ต้น
    # ไม่ยิงดึงแท่งเปล่า ๆ (allowlist ตอนนี้: btcusd, xauusd)
    #
    # รอบวันปล่อยได้ **หลายสไตล์ต่อหัวข้อ** ต่างจากการยิงตามจังหวะปิดแท่ง — เหตุผลอยู่ใน
    # intraday_article_selector.select_all · เกณฑ์ "มีเรื่องให้เขียน" ไม่ได้ถูกผ่อน
    # ⇒ วันที่ตลาดนิ่ง สไตล์นั้นจะเงียบ ซึ่งถูกต้องแล้ว ไม่ใช่ความผิดพลาด
    if (args.include_experimental and not args.skip_style_hij
            and args.line != build_daily_package.LINE_INTERNAL):
        intraday_assets = intraday_story.production_assets()
        for asset in core_assets:
            if asset not in intraday_assets:
                continue
            print()
            try:
                round_result = hij_route.run_round(
                    asset=asset, publish_root=experimental_root, cutoff_at=cutoff)
            except Exception as exc:  # noqa: BLE001 — สายเสริมห้ามพาทั้งรอบล้ม
                print(f"⚠️ สไตล์ H/I/J ({asset}): {exc}")
                build_code |= 1
                continue
            for item in round_result["skipped"]:
                print(f"สไตล์ H/I/J ({asset}): ข้าม {item['style']} — {item['reason']}")
            for article in round_result["articles"]:
                if article["published"]:
                    print(f"สไตล์ {article['style_name']} ({asset}): ✅ บท "
                          f"{article['words']} คำ + ภาพ 2 ใบ → {article['folder']}")
                else:
                    print(f"⚠️ สไตล์ {article['style_name']} ({asset}): "
                          f"ตกด่าน {len(article['findings'])} ข้อ — ไม่วางไฟล์")
            if not round_result["articles"]:
                print(f"สไตล์ H/I/J ({asset}): ไม่มีสไตล์ใดมีเรื่องใหม่ให้เขียนรอบนี้ "
                      f"(สถานะ {round_result['states']})")
            build_code |= 0 if round_result["ok"] else 1

    # Style L — Forex Daily Trade Plan: สองคู่ตามตารางอยู่ใน batch เดียว
    # แต่ละคู่มีบทหนึ่งฉบับพร้อมภาพ H1 และ M15
    # ปล่อยทั้งชุดแบบ fail-closed แล้ว selector ท้ายรอบจะคัดสองคู่ตามตารางเข้า
    # multi-lane local handoff ร่วมกับ XAUUSD D/E และ BTCUSD M
    if (l_registration is not None and l_registration.production
            and args.line != build_daily_package.LINE_INTERNAL):
        forex_assets = [asset for asset in forex_assets if asset in l_registration.assets]
        if forex_assets:
            print()
            style_l_code, _ = run_style_l(forex_assets, cutoff)
            build_code |= style_l_code

    # Handoff เดียวของ output รุ่นประเทศก่อนสไตล์: ตัวเขียน legacy บางสายยัง
    # สร้างไฟล์ไว้ที่โฟลเดอร์สไตล์เดิม จึงย้ายอย่างมี journal ก่อนเลือกใบขึ้นเว็บ
    # เพื่อไม่ให้เกิดสำเนาสองชุดเมื่อรันรอบถัดไป
    business_date = cutoff_dt.astimezone(ZoneInfo("Asia/Bangkok")).date().isoformat()
    try:
        migrated = country_first_output.migrate_day(
            output_root=Path("../output"), work_root=Path("../work"),
            business_date=business_date)
        repaired = country_first_output.repair_canonical_day(
            output_root=Path("../output"), work_root=Path("../work"),
            business_date=business_date)
        moved = [f"{item['style']}/{item['asset']}" for item in migrated["records"]
                 if item["status"] == "migrated"]
        if moved:
            print("country-first output: " + ", ".join(moved))
        fixed = [f"{item['style']}/{item['asset']}" for item in repaired["records"]]
        if fixed:
            print("country-first image names repaired: " + ", ".join(fixed))
    except Exception as exc:  # migration fail-closed; never select a mixed layout
        print(f"⚠️ country-first output migration failed: {exc}")
        return build_code or 1

    # กฎสากล: trade-plan sidecar เป็น internal-only ทุกสินทรัพย์/ทุกสไตล์
    # กวาดก่อนเลือกแม้ผู้ใช้ข้าม selection เพื่อให้คำสั่งรอบวันไม่มีทางทิ้งไว้ใน output
    day_dir = Path("../output") / publish_layout.day_folder(cutoff)
    publish_selection.purge_forbidden_output_files(day_dir)

    # เลือกใบขึ้นเว็บ **ก่อน** ยาม frontmatter เสมอ เพราะสำเนาที่วางไว้ต้องโดนกวาดด้วย
    # (basic-memory แทรก `permalink:` ให้ไฟล์ .md ใต้ Desktop\Claude โดยอัตโนมัติ —
    #  ใบที่ก๊อปทีหลังจะรอดยามไปขึ้นเว็บพร้อม frontmatter แปลกปลอม)
    selected = None
    selection_code = 0
    if not args.skip_selection and args.line != build_daily_package.LINE_INTERNAL:
        try:
            with publish_selection.defer_continuity_until_final_guard():
                selected = publish_selection.select(day_dir)
        except Exception as exc:  # noqa: BLE001 — required handoff fails closed
            selection_code = 1
            selected = {"status": "unavailable", "reason": f"selection_exception:{exc}",
                        "expected": "ไม่ทราบ"}
        if selected["status"] == "ready":
            if "ready_count" in selected:
                print(f"\nชุดขึ้นเว็บรอบนี้: {selected['ready_count']}/"
                      f"{selected['expected_count']} บท → {selected['directory']}")
            else:
                print(f"\nใบขึ้นเว็บรอบนี้: {selected['article']}")
        else:
            selection_code = 1
            print(f"\n⚠️ ยังไม่มีใบขึ้นเว็บ — {selected['reason']} "
                  f"· คาดว่าจะเจอที่ {selected.get('expected', 'ไม่ทราบ')}")

    guard_code = 0
    if not args.skip_guard:
        print("\nยาม frontmatter — ตัวรีโป:")
        guard_code |= frontmatter_guard.main(["."])
        print("ยาม frontmatter — บทความรอบที่จะส่ง (../output):")
        guard_code |= frontmatter_guard.main(["../output"])

    # Baseline is accepted only after the exact handoff has passed the final
    # output guard. This remains a local selected-delivery receipt, not proof
    # of web publication.
    continuity_code = 0
    if (not args.skip_selection and args.line != build_daily_package.LINE_INTERNAL
            and not args.skip_guard and build_code == 0 and selection_code == 0
            and selected is not None and selected["status"] == "ready" and guard_code == 0
            and selected.get("selection_report") and selected.get("lanes")):
        try:
            report = json.loads(Path(selected["selection_report"]).read_text(encoding="utf-8"))
            selected["continuity"] = publish_selection.finalize_continuity(
                day_dir, inventories=selected["lanes"], selection_report=report,
                target=Path(selected["directory"]))
            if selected["continuity"].get("status") not in {"recorded", "pass"}:
                continuity_code = 1
        except Exception as exc:  # noqa: BLE001 — baseline recording fails closed
            continuity_code = 1
            selected["continuity"] = {"status": "continuity_error", "reason": str(exc)}

    queue_code = 0
    localization_code = 0
    localization_dispatch = None
    if not args.skip_localization_queue:
        project_root = Path(__file__).resolve().parents[2]
        index_path = project_root / "work" / "localization" / "admission-index.json"
        try:
            queue = localization_queue.write_receipt(project_root=project_root, output_root=project_root / "output",
                                                      business_date=business_date, index_path=index_path,
                                                      work_root=project_root / "work",
                                                      scope=None,
                                                      policy_path=localization_queue.default_policy_path(project_root))
            print("localization queue: " + (", ".join(queue["selected"]) or "ไม่มีประเทศที่ admitted")
                  + (f" · hold {len(queue['held'])}" if queue["held"] else ""))
        except localization_queue.QueueError as exc:
            queue_code = 1
            print(f"⚠️ localization queue HOLD: {exc}")

    # The normal entrypoint records the agent-assisted localization boundary
    # after source production. It reports waiting/hold states but does not
    # turn a source-only success into a fabricated delivery PASS.
    if not args.skip_localization_queue:
        try:
            dispatch_options = {"dry_run": False}
            if args.recovery_bundle:
                dispatch_options["recovery_bundle_path"] = Path(args.recovery_bundle)
            localization_dispatch = normal_localization_orchestrator.run(
                Path(__file__).resolve().parents[2], business_date, **dispatch_options)
            print("localization dispatch: " + str(localization_dispatch.get("status")))
            if localization_dispatch.get("status") != "ALREADY_DELIVERED":
                localization_code = 2
        except (normal_localization_orchestrator.DispatchError, localization_queue.QueueError) as exc:
            localization_dispatch = {"status": "HOLD", "error": str(exc)}
            print(f"⚠️ localization dispatch HOLD: {exc}")
            localization_code = 1

    print("\nสรุปรอบ: สายท่อ "
          + ("✅ ทุกหัวข้อสำเร็จ" if build_code == 0 and localization_code == 0
             else "⚠️ มีหัวข้อที่สะดุด/ค้าง (ดูบรรทัดของหัวข้อนั้นข้างบน)")
          + " · frontmatter "
          + ("— ข้ามตามธง" if args.skip_guard else
             ("✅ สะอาด" if guard_code == 0 else "⚠️ เจอของแปลก — ล้างด้วย python -m tools.frontmatter_guard <ที่> --fix")))
    return build_code or guard_code or selection_code or continuity_code or queue_code or localization_code


if __name__ == "__main__":
    raise SystemExit(main())
