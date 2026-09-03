"""คำสั่งเดียวจบรอบวัน — แทนที่การพิมพ์ 3 คำสั่งเดิมด้วยคำสั่งเดียว

    python -m tools.run_daily

**ตั้งแต่ 2026-08-05 ดึก (คำสั่งผู้ใช้): นักเขียน A/B/C เป็นชุดเดียวที่วางลง `output/`**
แทนที่ ①②③ (ณธาร/กฤช/ปุณณ์) — ค่าตั้งต้นของคำสั่งนี้จึงเป็น:

    1. สายหลักฐานภายในคำนวณ D1 + level map + แผนเทรด + ด่านความเสี่ยง
       โดยไม่วาดกราฟและไม่สร้างบท ①②③ แม้แต่ใน work
    2. สายสาธารณะ A/B รันครบทุกด่าน แล้ววางลง output/<วัน>/ ตามปกติ (Style C ปิดจาก daily route)
       ⚠️ สายนี้ต้องมีรหัส (`WCB_SNAPSHOT_KEY` / `WCB_SNAPSHOT_KEY_FILE`)
       ⇒ ตั้งแต่การสลับนี้ รหัสกลายเป็นของจำเป็นต่อการได้บทประจำวัน
    3. วางชุด local handoff หลายบทใน `output/<วัน>/0-ขึ้นเว็บวันนี้/` ตาม policy v2:
       จันทร์ 5 บท (XAUUSD D/E, BTCUSD M, Forex L สองคู่) และอังคาร–ศุกร์ 4 บท
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

**ตัวนี้เป็นแค่ตัวห่อ ไม่มีตรรกะของตัวเอง** — เรียก `run_internal_line()` /
`run_public_line()` / `dispatch()` ของ build_daily_package กับ `frontmatter_guard.main()`
ตรง ๆ ⇒ ด่านตรวจทุกชั้น (ข้อมูล/ความสด/ความละเอียด/สิทธิ์/ตัวเลขบทความ/ความยาว
รายสไตล์) ยังทำงานครบตามเดิม เพราะมันอยู่ข้างในสายท่อ ไม่ได้อยู่ที่ตัวสั่งงาน

exit code: 0 = ทุกหัวข้อสร้างสำเร็จและไม่มี frontmatter แปลกปลอม · ไม่เป็นศูนย์ = มีอย่างน้อย
หนึ่งอย่างสะดุด (ดูบรรทัดสรุปท้ายรอบว่าตัวไหน)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

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
from tools import publish_layout, publish_selection  # noqa: E402

DEFAULT_ASSETS = sorted(build_daily_package.ASSETS)
REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "article_styles.json"
STYLE_E = "E"
STYLE_M = style_m_daily.STYLE_LETTER
STYLE_CHOICES = (STYLE_E, forex_daily_plan.STYLE_LETTER, STYLE_M)
FOREX_ASSETS = tuple(forex_daily_plan.ASSETS)


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
                        help="ไม่ระบุ = both (หลักฐานภายใน + สายสาธารณะ A/B; C ปิดจาก daily route)")
    parser.add_argument("--batch-id", help="ไม่ระบุ = สร้างจากเวลาปัจจุบัน (UTC)")
    # เก็บ parser compatibility ให้คำสั่งเก่าไม่พัง แต่ปิดสิทธิ์เผยแพร่ถาวรตามคำสั่ง
    # ผู้ใช้ 2026-08-24 — ถอดตัวเขียน ①②③ เหลือเฉพาะหลักฐานภายใน
    parser.add_argument("--publish-internal", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--skip-guard", action="store_true",
                        help="ข้ามยาม frontmatter — ใช้เฉพาะตอนรันทดลองที่ไม่ได้จะส่งของ")
    parser.add_argument("--skip-selection", action="store_true",
                        help="ไม่ต้องวางโฟลเดอร์ใบขึ้นเว็บ (config/publishing_policy.json)")
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
    args = parser.parse_args(argv)
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

    # Validate the H/I/J production route before any pipeline can fetch or
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
                if not args.skip_style_hij:
                    hij_route = HIJProductionRoute.load()
                if not args.skip_style_d:
                    d_route = DProductionRoute.load()
                if not args.skip_style_e:
                    e_route = EProductionRoute.load()
                if not args.skip_style_fg:
                    f_route = FProductionRoute.load()
                    g_route = GProductionRoute.load()
            elif args.style == STYLE_E:
                e_route = EProductionRoute.load()
            if args.style in (None, STYLE_M):
                m_route = MProductionRoute.load()
            if args.style in (None, forex_daily_plan.STYLE_LETTER) and not args.skip_forex_daily_plan:
                l_registration = load_l_registration()
        except RegistryError as exc:
            print(f"⚠️ ทะเบียน Unified ใช้งานไม่ได้ — {exc}")
            return 1

    cutoff_dt = datetime.now(tz=timezone.utc)
    cutoff = cutoff_dt.isoformat(timespec="seconds")
    batch_id = args.batch_id or default_batch_id(cutoff_dt)

    if args.style == forex_daily_plan.STYLE_LETTER:
        selected_assets = args.asset
        if selected_assets is None:
            selected_assets = scheduled_style_l_assets(cutoff)
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
        print("สรุป Style M: " + ("✅ สำเร็จ" if code == 0 else "⚠️ มีด่านที่ไม่ผ่าน"))
        return code

    if args.style == STYLE_E:
        selected_assets = [asset for asset in (args.asset or list(e_route.assets))
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

    assets = args.asset or DEFAULT_ASSETS
    core_assets = [asset for asset in assets if asset not in FOREX_ASSETS]
    forex_assets = [asset for asset in assets if asset in FOREX_ASSETS]
    if args.asset is None:
        scheduled = scheduled_style_l_assets(cutoff)
        if scheduled is None:
            return 1
        forex_assets = scheduled
    build_code = 0
    print(f"รอบวัน P002 · batch {batch_id} · สาย {args.line} · หัวข้อ {', '.join(assets)}")

    if args.publish_internal:
        print("ธง --publish-internal ถูกยกเลิกแล้ว — สายภายใน "
              "สร้างเฉพาะหลักฐานและจะไม่สร้างบท ①②③")

    if args.line == build_daily_package.LINE_BOTH:
        # ค่าตั้งต้นใหม่ (คำสั่งผู้ใช้ 2026-08-05 ดึก): A/B/C คือชุดเดียวที่ลง output/
        # สายภายในยังรันเต็มทุกด่านเพื่อหลักฐาน+แผนเทรด แต่ไม่มีทางวางไฟล์ลง
        # output อีก — A/B/C เป็นสายบทความสาธารณะที่แทนที่ ①②③ แล้ว
        print("สายหลักฐานภายใน: คำนวณ D1 + level map + แผนเทรด + risk audit "
              "โดยไม่สร้างบท ①②③ (A/B/C แทนที่แล้ว)")
        if core_assets:
            build_code = build_daily_package.run_internal_line(
                line_args(build_daily_package.LINE_INTERNAL,
                          no_publish=True, asset_list=core_assets), cutoff)
            print()
            build_code = build_code | build_daily_package.run_public_line(
                line_args(build_daily_package.LINE_PUBLIC, no_publish=False,
                          asset_list=core_assets), cutoff)
        else:
            print("ไม่มีสินทรัพย์ non-Forex — ข้ามสาย A/B/C และหลักฐานภายใน")
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
    if not args.skip_style_d and args.line != build_daily_package.LINE_INTERNAL:
        for asset in core_assets:
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

    if not args.skip_style_e and args.line != build_daily_package.LINE_INTERNAL:
        e_assets = [asset for asset in core_assets if asset in e_route.assets]
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
            and style_m_daily.ASSET in core_assets):
        print()
        style_m_code, _ = run_style_m(m_route, cutoff)
        build_code |= style_m_code

    # สไตล์ F/G (บทเช้า) — **วันที่เงื่อนไข G ครบ ได้ทั้งคู่** (ผู้ใช้สั่ง 2026-08-13)
    # วันที่ไม่ครบได้ F ใบเดียวตามเดิม เพราะ G ที่เงื่อนไขไม่ครบคือบทที่ขัดกับรูปของ
    # ตัวเอง ไม่ใช่บทที่หายไป · `--fg-single` = กลับพฤติกรรมเดิม (สไตล์เดียวต่อวัน)
    if not args.skip_style_fg and args.line != build_daily_package.LINE_INTERNAL:
        for asset in core_assets:
            print()
            try:
                runner = brief_pipeline.run if args.fg_single else brief_pipeline.run_pair
                results = runner(asset=asset, publish_root=Path("../output"),
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
    if not args.skip_style_hij and args.line != build_daily_package.LINE_INTERNAL:
        intraday_assets = intraday_story.production_assets()
        for asset in core_assets:
            if asset not in intraday_assets:
                continue
            print()
            try:
                round_result = hij_route.run_round(
                    asset=asset, publish_root=Path("../output"), cutoff_at=cutoff)
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

    # กฎสากล: trade-plan sidecar เป็น internal-only ทุกสินทรัพย์/ทุกสไตล์
    # กวาดก่อนเลือกแม้ผู้ใช้ข้าม selection เพื่อให้คำสั่งรอบวันไม่มีทางทิ้งไว้ใน output
    day_dir = Path("../output") / publish_layout.day_folder(cutoff)
    publish_selection.purge_forbidden_output_files(day_dir)

    # เลือกใบขึ้นเว็บ **ก่อน** ยาม frontmatter เสมอ เพราะสำเนาที่วางไว้ต้องโดนกวาดด้วย
    # (basic-memory แทรก `permalink:` ให้ไฟล์ .md ใต้ Desktop\Claude โดยอัตโนมัติ —
    #  ใบที่ก๊อปทีหลังจะรอดยามไปขึ้นเว็บพร้อม frontmatter แปลกปลอม)
    if not args.skip_selection and args.line != build_daily_package.LINE_INTERNAL:
        selected = publish_selection.select(day_dir)
        if selected["status"] == "ready":
            if "ready_count" in selected:
                print(f"\nชุดขึ้นเว็บรอบนี้: {selected['ready_count']}/"
                      f"{selected['expected_count']} บท → {selected['directory']}")
            else:
                print(f"\nใบขึ้นเว็บรอบนี้: {selected['article']}")
        else:
            print(f"\n⚠️ ยังไม่มีใบขึ้นเว็บ — {selected['reason']} "
                  f"· คาดว่าจะเจอที่ {selected['expected']}")

    guard_code = 0
    if not args.skip_guard:
        print("\nยาม frontmatter — ตัวรีโป:")
        guard_code |= frontmatter_guard.main(["."])
        print("ยาม frontmatter — บทความรอบที่จะส่ง (../output):")
        guard_code |= frontmatter_guard.main(["../output"])

    print("\nสรุปรอบ: สายท่อ "
          + ("✅ ทุกหัวข้อสำเร็จ" if build_code == 0 else "⚠️ มีหัวข้อที่สะดุด (ดูบรรทัดของหัวข้อนั้นข้างบน)")
          + " · frontmatter "
          + ("— ข้ามตามธง" if args.skip_guard else
             ("✅ สะอาด" if guard_code == 0 else "⚠️ เจอของแปลก — ล้างด้วย python -m tools.frontmatter_guard <ที่> --fix")))
    return build_code or guard_code


if __name__ == "__main__":
    raise SystemExit(main())
