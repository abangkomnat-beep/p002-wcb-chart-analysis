"""สายผลิตบทเช้าสไตล์ F/G — ดึงแท่งจริง → คิดโครง → ตรวจบท → วางบท+ภาพคู่กัน

ลำดับและหลัก fail-closed เหมือนสายของสไตล์ D/E ทุกประการ: **ตรวจบทให้ผ่านก่อน
แล้วค่อยวาดภาพและวางไฟล์** — บทตกด่าน โฟลเดอร์ของสไตล์นั้นต้องว่าง (ล้างของรอบก่อน
ทิ้งด้วย) เพื่อไม่ให้ไฟล์เก่านอนอยู่โดยหน้าตาเหมือนของสด

ขอบเขต: **ทุกหัวข้อในทะเบียน และเข้ารอบผลิตรายวัน (`run_daily`) แล้ว** ตั้งแต่
2026-08-11 ตามคำสั่งผู้ใช้ (รัน A–G เข้าสายหลักครบทุกหัวข้อ) · ยังไม่เข้าโฟลเดอร์
ขึ้นเว็บ — การเปลี่ยนใบขึ้นเว็บเป็นการตัดสินใจของหัวหน้าผ่านผู้ใช้ ไม่ใช่ของสายท่อ

เลือกสไตล์อัตโนมัติเป็นค่าตั้งต้น (มีเหตุการณ์แรงรอ + ช่องแนวโน้มพิสูจน์ได้ ⇒ G
นอกนั้น F) · บังคับด้วย `--style f|g` ได้ แต่บังคับ G ในวันที่เงื่อนไขไม่ครบ = ล้ม
ไม่ใช่วาดช่องที่พิสูจน์ไม่ได้

**`run_pair()` คือทางที่รอบผลิตรายวันใช้ตั้งแต่ 2026-08-13 (ผู้ใช้สั่ง)** — วันที่
เงื่อนไข G ครบจะได้ทั้ง F และ G คนละโฟลเดอร์ · วันที่ไม่ครบได้ F ใบเดียวตามเดิม
เพราะ G ที่เงื่อนไขไม่ครบเป็นบทที่ขัดกับรูปของตัวเอง ไม่ใช่บทที่หายไป · F/G ยังไม่มี
สัญญา slug จึงห้ามวางสองสไตล์ของวันเดียวกันขึ้นเว็บ; ข้อยกเว้น D/E ที่ใช้
`levels`/`signals` ตั้งแต่ 2026-08-21 ไม่ได้ขยายมาถึงสายนี้
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import brief_renderer, brief_story, brief_writer, calendar_feed  # noqa: E402
from tools import candle_close, image_output, intraday_bars  # noqa: E402
from tools import publish_layout, public_number_policy, wcb_series_source, wcb_source, wcb_writers  # noqa: E402

DEFAULT_ASSET = "xauusd"
CALENDAR_LIMIT = 3
# กรอบเวลาตั้งต้นของบทเช้า — **ราย 1 ชั่วโมงตามต้นแบบ** (ผู้ใช้สั่ง 2026-08-10)
#
# เหตุผลเชิงเนื้อหา ไม่ใช่ความชอบ: บนแท่งรายวัน แนวรับที่บทประกาศห่างราคา 5-10%
# ⇒ ประโยค "รอย่อตัวเข้าหาแนวรับ" ทำตามไม่ได้จริงในวันเดียว · ต้นแบบห่าง ~1.2%
# ตั้งเป็น None = กลับไปใช้แท่งรายวัน (เส้นทางเดิม ยังใช้ได้ทุกอย่าง)
DEFAULT_TIMEFRAME = "1h"


def _clear_stale(folder: Path, asset: str) -> bool:
    """ลบบท+ภาพทุกใบของหัวข้อ — เหตุผลเดียวกับสาย D/E (กวาดทุกนามสกุลที่ไม่ใช่ .md)"""
    removed = False
    targets = [folder / f"{asset}.md"] + [
        path for path in folder.glob(f"{asset}*") if path.suffix.lower() != ".md"]
    for path in targets:
        if path.exists():
            path.unlink()
            removed = True
    return removed


def calendar_block(asset: str, *, fetcher=calendar_feed.fetch_raw) -> tuple[dict, str]:
    """ก้อนปฏิทินของบทเช้า — คืนทั้ง **รายการดิบ** และ **ประโยคสำเร็จรูป**

    ต่างจาก `chart_story_pipeline.calendar_block_from_feed` ตรงที่บทเช้าต้องใช้
    รายการดิบด้วย ไม่ใช่แค่ประโยค เพราะตัวตัดสิน F↔G (`brief_story.pending_event`)
    ต้องดูช่อง `impact`/`actual`/`at` ของแต่ละรายการ ซึ่งประโยคสำเร็จรูปไม่มีแล้ว

    ปฏิทินล่ม = คืนก้อนว่างพร้อมเหตุผล **ไม่พาสายทั้งเส้นล้ม** (ปฏิทินเป็นส่วนเสริม
    ราคาเป็นแกน) — ผลคือวันนั้นได้สไตล์ F ที่ไม่มีย่อหน้าปัจจัย ซึ่งยังเป็นบทที่ถูกต้อง
    """
    try:
        raw = fetcher()
        today = datetime.now(tz=wcb_source.BANGKOK).strftime("%Y-%m-%d")
        events = calendar_feed.to_calendar_events(raw)
        pseudo = {"calendar": events, "local_date": today}
        sentences = wcb_writers._calendar_sentences(pseudo, limit=CALENDAR_LIMIT)
        # รายการต้นทางของประโยคชุดบน — ตัวคัด/ลำดับเดียวกัน ⇒ จับคู่ 1:1 ได้เสมอ
        # บทเช้าใช้จัดกลุ่มปฏิทินตามวัน (`wcb_writers.calendar_day_groups`)
        selected = wcb_writers._calendar_events(pseudo, CALENDAR_LIMIT)
    except Exception as exc:  # noqa: BLE001 — ส่วนเสริมห้ามพาบทล้ม เหตุถูกบันทึกใน result
        return {"events": [], "sentences": [], "selected": [],
                "local_date": None}, f"unavailable: {exc}"
    status = "ok" if sentences else "empty"
    return {"events": events, "sentences": sentences, "selected": selected,
            "local_date": today}, status


def load_bars(asset: str, *, timeframe: str | None,
              fetcher=None) -> tuple[list[dict], dict, str]:
    """ดึงแท่ง + ตัดแท่งที่ยังไม่ปิด — **จุดเดียวที่แยกเส้นทางรายวันกับ intraday**

    ทั้งสองเส้นทางคืนรูปเดียวกัน (rows, basis, ป้ายแหล่ง) เพื่อให้ `run()` ข้างล่าง
    ไม่ต้องรู้ว่ากำลังเดินเส้นไหน · ตัดแท่งที่นี่ที่เดียวแล้วส่งชุดเดียวกันให้ทั้งตัวคิด
    และตัววาด (หลัก A-1 — ถ้าตัดคนละที่ ภาพจะมีแท่งที่บทไม่นับอยู่ที่ขอบขวา)
    """
    if timeframe is None:
        meta, rows, label = (fetcher or wcb_series_source.fetch_asset_rows)(asset)
        rows, basis = candle_close.evaluate(rows, asset=asset)
        return rows, basis, label
    meta, rows, label = (fetcher or intraday_bars.fetch_rows)(asset, timeframe=timeframe)
    rows, basis = intraday_bars.evaluate(rows, asset=asset, timeframe=timeframe)
    return rows, basis, label


def run(*, asset: str = DEFAULT_ASSET, style: str | None = None,
        timeframe: str | None = DEFAULT_TIMEFRAME,
        publish_root: Path = Path("../output"), cutoff_at: str | None = None,
        fetcher=None, calendar_source=calendar_block,
        keep_other: bool = False) -> dict:
    cutoff = cutoff_at or datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    day = publish_root / publish_layout.day_folder(cutoff)

    rows, basis, label = load_bars(asset, timeframe=timeframe, fetcher=fetcher)
    calendar, calendar_status = calendar_source(asset)

    brief = brief_story.build_brief(
        rows, asset=asset, style=style, calendar=calendar["events"],
        calendar_sentences=calendar["sentences"],
        calendar_events=calendar.get("selected"),
        local_date=calendar["local_date"],
        candle_basis=basis, timeframe=timeframe)

    folder = day / brief_writer.folder_for(brief)
    folder.mkdir(parents=True, exist_ok=True)
    cleared = _clear_stale(folder, asset)
    # สไตล์อีกตัวของวันเดียวกันต้องไม่ค้าง — F กับ G เป็นบทของวันเดียวกันคนละพันธุ์
    # ถ้าเมื่อวานรัน G แล้ววันนี้ระบบเลือก F ไฟล์ G เก่าจะนอนอยู่ในโฟลเดอร์ของวันนี้
    # โดยหน้าตาเหมือนของสด
    #
    # `keep_other=True` มีที่ใช้ที่เดียวคือ `run_pair()` ซึ่งกำลังตั้งใจวางทั้งคู่ของ
    # วันเดียวกัน — ผู้เรียกอื่นห้ามเปิด ไม่งั้นใบของรอบก่อนจะรอดมานอนปนของสด
    if not keep_other:
        other = brief_story.STYLE_F if brief["style"] == brief_story.STYLE_G else brief_story.STYLE_G
        other_folder = day / brief_writer.FOLDERS[other]
        if other_folder.exists():
            _clear_stale(other_folder, asset)

    markdown = brief_writer.render_article(brief)
    result = brief_writer.validate(markdown, brief)
    result |= {"asset": asset, "source": label, "calendar_status": calendar_status,
               "cleared_stale": cleared, "folder": str(folder),
               "timeframe": timeframe or "1day",
               "bar_at": brief["current"].get("at") or brief["current"]["date"],
               "event": (brief.get("event") or {}).get("title")}
    if not result["ok"]:
        return result

    markdown = public_number_policy.publicize(markdown)
    number_findings = public_number_policy.validate(markdown)
    if number_findings:
        raise RuntimeError("; ".join(number_findings))
    result["number_policy"] = public_number_policy.POLICY_VERSION

    (folder / f"{asset}.md").write_text(markdown, encoding="utf-8")
    picture = folder / brief_writer.image_name(brief)
    try:
        result["image"] = brief_renderer.render(brief, rows, picture)
    except image_output.ImageGateError as exc:
        _clear_stale(folder, asset)
        result |= {"ok": False, "findings": result["findings"] + [{
            "rule": "image_gate", "severity": "fatal", "line": 1, "message": str(exc)}]}
        return result
    result["article"] = str(folder / f"{asset}.md")
    return result


def run_pair(**kwargs) -> list[dict]:
    """ผลิตบทเช้าของหัวข้อหนึ่ง — **ได้ทั้ง F และ G ในวันที่เงื่อนไข G ครบ** (ผู้ใช้สั่ง 2026-08-13)

    ทำไมไม่ใช่ "ออกทั้งคู่ทุกวัน": G ต้องผ่านสามข้อพร้อมกัน (เหตุการณ์แรงที่ยังไม่
    ประกาศ · ช่องแนวโน้มมีจุดแตะครบ · ราคาปิดยังอยู่ในช่อง) ขาดข้อใดข้อหนึ่ง
    `build_brief` ยก `BriefUnavailable` ทิ้งทั้งใบ ไม่ใช่เขียนแบบอ่อนลง — บังคับให้
    ออกก็ได้แค่บทที่ขัดกับรูปของตัวเอง · **ส่วน F ผลิตได้เสมอ** ไม่มีเงื่อนไขเพิ่ม
    ⇒ "วันที่เงื่อนไขครบ" = วันที่ตัวเลือกอัตโนมัติตอบ G พอดี

    ลำดับสำคัญ: รอบแรกปล่อยให้กวาดโฟลเดอร์อีกสไตล์ตามปกติ (ของรอบก่อนต้องไม่รอด)
    แล้วรอบสองจึงเขียนทับด้วยของสด โดยเปิด `keep_other` กันไม่ให้ไปลบใบที่เพิ่งวาง

    คืนลิสต์เรียงตามลำดับที่ผลิต — 1 ใบในวันที่ได้ F · 2 ใบในวันที่ได้ G
    """
    first = run(**kwargs)
    if first["style"] != brief_story.STYLE_G:
        return [first]
    return [first, run(**{**kwargs, "style": brief_story.STYLE_F, "keep_other": True})]


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description="สร้างบทเช้าสไตล์ F/G หนึ่งใบ")
    parser.add_argument("--asset", default=DEFAULT_ASSET)
    parser.add_argument("--style", choices=[brief_story.STYLE_F, brief_story.STYLE_G],
                        help="ไม่ระบุ = ให้ระบบเลือกจากเหตุการณ์ที่รออยู่")
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME,
                        choices=[*intraday_bars.TIMEFRAMES, "1day"],
                        help=f"ไม่ระบุ = {DEFAULT_TIMEFRAME} ตามต้นแบบ · 1day = แท่งรายวัน")
    parser.add_argument("--publish-root", default="../output")
    parser.add_argument("--cutoff-at")
    args = parser.parse_args(argv)

    result = run(asset=args.asset, style=args.style,
                 timeframe=None if args.timeframe == "1day" else args.timeframe,
                 publish_root=Path(args.publish_root), cutoff_at=args.cutoff_at)
    print(f"[{result['style_name']}] {result['asset']} · {result['timeframe']} "
          f"(แท่งฐาน {result['bar_at']}) — "
          f"{'ผ่าน' if result['ok'] else 'ตกด่าน'} · ปฏิทิน {result['calendar_status']}")
    if result.get("event"):
        print(f"  เหตุการณ์ที่รออยู่: {result['event']}")
    for finding in result["findings"]:
        print(f"  [{finding['severity']}] {finding['rule']} (บรรทัด {finding['line']}): "
              f"{finding['message']}")
    if result.get("image"):
        print(f"  ภาพ: {Path(result['image']['path']).name} · {result['image']['kb']} KB")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
