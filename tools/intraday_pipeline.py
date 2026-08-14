"""สายผลิตบทระหว่างวัน สไตล์ H/I/J — ดึงแท่ง → คิดสถานะทั้งสาม → เลือกใบ → ตรวจ → วาง

ลำดับและหลัก fail-closed เหมือนสาย D/E และ F/G ทุกประการ:
**ตรวจบทให้ผ่านก่อน แล้วค่อยวาดภาพและวางไฟล์** — บทตกด่าน โฟลเดอร์ของสไตล์นั้นต้องว่าง
(ล้างของรอบก่อนทิ้งด้วย) เพื่อไม่ให้ไฟล์เก่านอนอยู่โดยหน้าตาเหมือนของสด

สิ่งที่ต่างจากสายเดิมมีสองอย่าง และทั้งคู่มาจากธรรมชาติของ intraday:

1. **คิดทั้งสามสไตล์ทุกรอบ** — เพราะสามสไตล์อ่านตลาดเดียวกันคนละแง่
2. **ความจำสถานะ** — ตัวตัดสินว่ารอบนี้มีเรื่องใหม่หรือไม่ และเป็นเงื่อนไขที่ทำให้
   สถานะอย่าง `FAILED_BREAKOUT_*` เป็นไปได้เลย · เขียนความจำ**ทุกรอบ**ไม่ว่าจะได้บทหรือไม่
   แต่ธง `published` ตั้งเฉพาะรอบที่บทออกจริง

**ทางเข้าสองทาง จำนวนใบต่อรอบต่างกัน และความต่างนี้ตั้งใจ:**

| ทางเข้า | ใช้เมื่อไหร่ | ปล่อยได้ |
|---|---|---|
| `run()` | ยิงตามจังหวะปิดแท่ง (ทุก 15/30 นาที) | อย่างมาก **1 ใบ** |
| `run_round()` | รอบวัน (`run_daily`) วันละครั้ง | **ทุกใบที่มีเรื่องให้เขียน** |

เหตุผลเต็มอยู่ใน `intraday_article_selector.select_all` — โดยย่อคือกติกาหนึ่งใบต่อรอบ
แก้ปัญหาของการยิงถี่ ไม่ใช่ปัญหาของการมีหลายสไตล์ · เกณฑ์ "มีเรื่องให้เขียน"
ไม่ถูกผ่อนทั้งสองทาง

**ธง `production` ในทะเบียน** `config/article_styles.json` คุมว่าสไตล์ไหนเข้ารอบวัน
(`run_round(production_only=True)` เป็นค่าตั้งต้น) ส่วนการสั่งมือผ่าน `run()` ทำได้เสมอ
ไม่ว่าธงจะเปิดหรือปิด — ปิดธงคือ "ยังไม่ออกอัตโนมัติ" ไม่ใช่ "ห้ามรัน"
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import image_output, intraday_article_selector as selector  # noqa: E402
from tools import intraday_bars, intraday_breakout_story, intraday_breakout_writer  # noqa: E402
from tools import intraday_pullback_story, intraday_pullback_writer  # noqa: E402
from tools import intraday_renderer, intraday_story  # noqa: E402
from tools import intraday_trend_story, intraday_trend_writer  # noqa: E402
from tools import intraday_writer_base, publish_layout  # noqa: E402

DEFAULT_ASSET = "btcusd"
CONTEXT_TIMEFRAME = "30min"
TRIGGER_TIMEFRAME = "15min"
# ขอเผื่อจากปลายทาง — ต้องคลุมหน้าต่างเปอร์เซ็นไทล์ของ BandWidth (200 ค่า)
# บวกช่วงอุ่นเครื่องของ Ichimoku (52+26) และแท่งที่ถูกตัดเพราะยังไม่ปิด
OUTPUTSIZE = 500

WRITERS = {
    intraday_trend_story.STYLE_ID: intraday_trend_writer,
    intraday_breakout_story.STYLE_ID: intraday_breakout_writer,
    intraday_pullback_story.STYLE_ID: intraday_pullback_writer,
}


def load_bars(asset: str, timeframe: str, *, fetcher=None,
              now: datetime | None = None) -> tuple[list[dict], dict, str]:
    """ดึงแท่ง + ตัดแท่งที่ยังเดินอยู่ — ตัดที่นี่ที่เดียวแล้วส่งชุดเดียวกันให้ทุกคน

    ถ้าปล่อยให้ตัวคิดกับตัววาดตัดคนละที่ ภาพจะมีแท่งที่บทไม่นับอยู่ที่ขอบขวา
    (หลักเดียวกับ A-1 ของสายเดิม)
    """
    fetch = fetcher or intraday_bars.fetch_rows
    _meta, rows, label = fetch(asset, timeframe=timeframe, outputsize=OUTPUTSIZE)
    rows, basis = intraday_bars.evaluate(rows, asset=asset, timeframe=timeframe, now=now)
    return rows, basis, label


def build_stories(asset: str, *, context_rows: list[dict], context_basis: dict,
                  trigger_rows: list[dict], trigger_basis: dict,
                  state_dir: Path | None = None,
                  params: dict | None = None, styles: dict | None = None
                  ) -> tuple[list[dict], list[dict]]:
    """คิดทั้งสามสไตล์ — คืน (story ที่คิดได้, เหตุผลของตัวที่คิดไม่ได้)

    สไตล์ที่คิดไม่ได้ **ไม่พาสายทั้งเส้นล้ม** เพราะสามตัวเป็นอิสระต่อกัน · แต่เหตุผล
    ต้องถูกบันทึกและพิมพ์ออกมาเสมอ ไม่ใช่เงียบหาย (เงียบ = วันหนึ่งจะไม่มีใครรู้ว่า
    สไตล์หนึ่งไม่เคยผลิตเลยมาสองสัปดาห์แล้ว)
    """
    stories, skipped = [], []
    plans = [
        (intraday_trend_story.STYLE_ID, CONTEXT_TIMEFRAME,
         lambda previous: intraday_trend_story.build(
             context_rows, asset=asset, timeframe=CONTEXT_TIMEFRAME,
             candle_basis=context_basis, previous_state=previous,
             params=params, styles=styles)),
        (intraday_breakout_story.STYLE_ID, TRIGGER_TIMEFRAME,
         lambda previous: intraday_breakout_story.build(
             trigger_rows, asset=asset, timeframe=TRIGGER_TIMEFRAME,
             candle_basis=trigger_basis, previous_state=previous,
             params=params, styles=styles)),
        (intraday_pullback_story.STYLE_ID, TRIGGER_TIMEFRAME,
         lambda previous: intraday_pullback_story.build(
             context_rows, trigger_rows, asset=asset,
             context_timeframe=CONTEXT_TIMEFRAME, trigger_timeframe=TRIGGER_TIMEFRAME,
             candle_basis=trigger_basis, context_basis=context_basis,
             previous_state=previous, params=params, styles=styles)),
    ]
    for style_id, timeframe, build in plans:
        memory = intraday_story.read_state(style_id, asset, timeframe, state_dir=state_dir)
        # ⛔ รันซ้ำแท่งเดิมต้องไม่ถูกนับเป็น "สถานะเปลี่ยน" — ถ้าความจำเป็นของแท่งเดียวกัน
        # ให้ใช้สถานะก่อนหน้าของมัน ไม่ใช่สถานะที่มันบันทึกไว้เอง (ไม่งั้นรันสองครั้ง
        # ติดกันจะได้ state_changed=False เสมอ ซึ่งบังเอิญถูก แต่ด้วยเหตุผลผิด)
        previous = memory.get("state")
        try:
            stories.append(build(previous))
        except intraday_story.StoryUnavailable as exc:
            skipped.append({"style": style_id, "reason": str(exc)})
    return stories, skipped


def _clear_stale(folder: Path, asset: str) -> bool:
    removed = False
    targets = [folder / f"{asset}.md"] + [
        path for path in folder.glob(f"{asset}*") if path.suffix.lower() != ".md"]
    for path in targets:
        if path.exists():
            path.unlink()
            removed = True
    return removed


def _prepare(asset: str, *, fetcher, now: datetime | None,
             state_dir: Path | None) -> dict:
    """ดึงแท่งสองกรอบครั้งเดียวแล้วคิดครบทุกสไตล์ — ขั้นร่วมของ `run()` และ `run_round()`

    ดึงที่นี่ที่เดียวสำคัญกว่าที่คิด: ถ้าปล่อยให้แต่ละสไตล์ดึงเอง สามใบที่ออกในรอบ
    เดียวกันอาจอ้างแท่งฐานคนละแท่ง แล้วหน้าเว็บวันเดียวกันจะประกาศราคาปิดไม่ตรงกัน
    """
    context_rows, context_basis, context_label = load_bars(
        asset, CONTEXT_TIMEFRAME, fetcher=fetcher, now=now)
    trigger_rows, trigger_basis, trigger_label = load_bars(
        asset, TRIGGER_TIMEFRAME, fetcher=fetcher, now=now)
    stories, skipped = build_stories(
        asset, context_rows=context_rows, context_basis=context_basis,
        trigger_rows=trigger_rows, trigger_basis=trigger_basis, state_dir=state_dir)
    return {
        "rows_by_timeframe": {CONTEXT_TIMEFRAME: context_rows,
                              TRIGGER_TIMEFRAME: trigger_rows},
        "source": f"{context_label} + {trigger_label}",
        "context_bar_at": context_rows[-1]["at"], "trigger_bar_at": trigger_rows[-1]["at"],
        "stories": stories, "skipped": skipped,
        "by_style": {story["style"]: story for story in stories},
    }


def _publish_one(story: dict, *, rows_by_timeframe: dict[str, list[dict]],
                 publish_root: Path, cutoff: str, dry_run: bool) -> dict:
    """เขียน ตรวจ วาด และวางบทของสไตล์เดียว — ไม่แตะความจำสถานะ (ผู้เรียกทำเอง)

    ลำดับ fail-closed อยู่ในนี้ทั้งหมด: ตรวจบทไม่ผ่าน = ไม่วางอะไรเลย ·
    วาดภาพไม่ผ่าน = ลบบทที่เพิ่งวางทิ้ง เพราะบทที่ไม่มีภาพคือบทที่ไม่ครบสัญญา
    """
    writer = WRITERS[story["style"]]
    markdown = writer.render_article(story)
    result = writer.validate(markdown, story)
    summary = {"style": story["style"], "style_name": result["style_name"],
               "state": story["state"], "words": result["words"],
               "findings": result["findings"], "ok": result["ok"], "published": False}
    if not result["ok"]:
        return summary
    if dry_run:
        summary["markdown"] = markdown
        return summary

    asset = story["asset"]
    day = Path(publish_root) / publish_layout.day_folder(cutoff)
    folder = day / intraday_writer_base.folder_for(story)
    folder.mkdir(parents=True, exist_ok=True)
    summary["cleared_stale"] = _clear_stale(folder, asset)
    summary["folder"] = str(folder)

    (folder / f"{asset}.md").write_text(markdown, encoding="utf-8")
    try:
        # ส่งแท่ง **ทั้งสองกรอบ** ให้ตัววาดเลือกเอง — สายผลิตไม่มีทางรู้ว่าภาพใบไหน
        # ของสไตล์ไหนใช้กรอบอะไร และการเดาผิดที่นี่เคยทำให้ภาพของ H เป็นแท่ง M15
        # ที่มีเส้นของ M30 ลากทับ (พบ 2026-08-13)
        summary["images"] = intraday_renderer.render(
            story, rows_by_timeframe, folder, writer)
    except (image_output.ImageGateError, intraday_renderer.ChartMismatch) as exc:
        # ภาพเป็นภาคบังคับ ⇒ ภาพล้ม = บททั้งใบต้องไม่เหลืออยู่ ไม่ใช่ปล่อยบทที่ไม่มีภาพ
        _clear_stale(folder, asset)
        summary |= {"ok": False, "published": False}
        summary["findings"] = summary["findings"] + [{
            "rule": "image_gate", "severity": "fatal", "line": 1, "message": str(exc)}]
        return summary

    summary["article"] = str(folder / f"{asset}.md")
    summary["published"] = True
    return summary


def run_round(*, asset: str, publish_root: Path = Path("../output"),
              cutoff_at: str | None = None, fetcher=None, now: datetime | None = None,
              state_dir: Path | None = None, dry_run: bool = False,
              styles: dict | None = None, production_only: bool = True) -> dict:
    """รอบผลิตของหัวข้อเดียว — ปล่อย **ทุกสไตล์ที่มีเรื่องให้เขียน** ในรอบนั้น

    ต่างจาก `run()` ตรงจำนวนใบที่ปล่อยได้ และตรงที่กรองด้วยธง `production` ในทะเบียน
    ⇒ ตัวนี้คือทางเข้าของรอบวัน ส่วน `run()` เป็นทางเข้าของการยิงตามจังหวะปิดแท่ง
    เหตุผลที่รอบวันปล่อยได้หลายใบอยู่ใน `intraday_article_selector.select_all`

    สไตล์หนึ่งล้ม **ไม่ดึงสไตล์อื่นล้มตาม** (หลักเดียวกับสายเสริม D/E/F/G ในรอบวัน)
    แต่ `ok` ของทั้งรอบจะเป็นเท็จ เพื่อให้ exit code ของรอบวันสะท้อนว่ามีอะไรสะดุด
    """
    cutoff = cutoff_at or datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    prepared = _prepare(asset, fetcher=fetcher, now=now, state_dir=state_dir)
    stories = prepared["stories"]

    allowed = (set(intraday_story.production_styles(styles=styles))
               if production_only else set(WRITERS))
    in_round = [story for story in stories if story["style"] in allowed]
    off_round = [{"style": story["style"], "reason": "ธง production ยังปิดอยู่ในทะเบียน"}
                 for story in stories if story["style"] not in allowed]

    decision = selector.select_all(
        in_round, last_published_state=selector.last_published(
            asset=asset, state_dir=state_dir))
    summary = {
        "ok": True, "asset": asset, "cutoff_at": cutoff, "source": prepared["source"],
        "context_bar_at": prepared["context_bar_at"],
        "trigger_bar_at": prepared["trigger_bar_at"],
        "states": {story["style"]: story["state"] for story in stories},
        "skipped": prepared["skipped"] + off_round, "decision": decision, "articles": [],
    }

    chosen = set(decision["styles"])
    for story in in_round:
        if story["style"] not in chosen:
            continue
        article = _publish_one(story, rows_by_timeframe=prepared["rows_by_timeframe"],
                               publish_root=publish_root, cutoff=cutoff, dry_run=dry_run)
        summary["articles"].append(article)
        summary["ok"] = summary["ok"] and article["ok"]

    # ความจำเขียน**ทุกสไตล์ที่คิดได้** ไม่ใช่เฉพาะใบที่ออก — สไตล์ที่รอบนี้เงียบก็ต้อง
    # จำสถานะไว้ ไม่งั้นรอบหน้าจะเห็นเป็น "รอบแรก" แล้วปล่อยบทซ้ำเรื่องเดิม
    published_styles = {article["style"] for article in summary["articles"]
                        if article["published"]}
    for story in stories:
        intraday_story.remember(story, state_dir=state_dir,
                                published=story["style"] in published_styles)
    summary["published"] = sorted(published_styles)
    return summary


def run(*, asset: str = DEFAULT_ASSET, publish_root: Path = Path("../output"),
        cutoff_at: str | None = None, force_style: str | None = None,
        fetcher=None, now: datetime | None = None, state_dir: Path | None = None,
        dry_run: bool = False) -> dict:
    cutoff = cutoff_at or datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    prepared = _prepare(asset, fetcher=fetcher, now=now, state_dir=state_dir)
    stories, skipped = prepared["stories"], prepared["skipped"]
    by_style = prepared["by_style"]

    if force_style:
        if force_style not in by_style:
            reason = next((item["reason"] for item in skipped
                           if item["style"] == force_style),
                          "สไตล์นี้ไม่อยู่ในรายการที่คิดได้รอบนี้")
            return {"ok": False, "asset": asset, "published": False,
                    "reason": f"บังคับสไตล์ {force_style} ไม่ได้ — {reason}",
                    "skipped": skipped, "stories": [], "findings": []}
        decision = {"schema": selector.SCHEMA, "publish": True, "style": force_style,
                    "state": by_style[force_style]["state"],
                    "reason": "ผู้เรียกบังคับสไตล์นี้", "candidates":
                    [selector.candidate(story) for story in stories], "suppressed":
                    [style for style in by_style if style != force_style]}
    else:
        decision = selector.select(
            stories, last_published_state=selector.last_published(
                asset=asset, state_dir=state_dir))

    summary = {
        "ok": True, "asset": asset, "cutoff_at": cutoff, "source": prepared["source"],
        "context_bar_at": prepared["context_bar_at"],
        "trigger_bar_at": prepared["trigger_bar_at"],
        "states": {story["style"]: story["state"] for story in stories},
        "skipped": skipped, "decision": decision, "published": False, "findings": [],
    }

    if not decision["publish"]:
        for story in stories:
            intraday_story.remember(story, state_dir=state_dir, published=False)
        return summary

    story = by_style[decision["style"]]
    article = _publish_one(story, rows_by_timeframe=prepared["rows_by_timeframe"],
                           publish_root=publish_root, cutoff=cutoff, dry_run=dry_run)
    summary |= {key: value for key, value in article.items() if key != "ok"}
    summary["ok"] = article["ok"]
    for item in stories:
        intraday_story.remember(item, state_dir=state_dir,
                                published=article["published"]
                                and item["style"] == story["style"])
    return summary


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description="สร้างบทระหว่างวันสไตล์ H/I/J หนึ่งรอบ")
    parser.add_argument("--asset", default=DEFAULT_ASSET)
    parser.add_argument("--style", choices=sorted(WRITERS),
                        help="บังคับสไตล์ — ไม่ระบุ = ให้ตัวเลือกบทตัดสินจากสถานะ")
    parser.add_argument("--publish-root", default="../output")
    parser.add_argument("--cutoff-at")
    parser.add_argument("--state-dir")
    parser.add_argument("--dry-run", action="store_true",
                        help="คิดและตรวจบทแต่ไม่วางไฟล์ ไม่วาดภาพ")
    parser.add_argument("--round", action="store_true",
                        help="รอบวันแบบเดียวกับ run_daily — ปล่อยทุกสไตล์ที่มีเรื่องให้เขียน "
                             "และนับเฉพาะสไตล์ที่ธง production เปิด")
    parser.add_argument("--all-styles", action="store_true",
                        help="ใช้กับ --round: ไม่สนธง production (สำหรับทดลองก่อนเปิดจริง)")
    parser.add_argument("--json", action="store_true", help="พิมพ์ผลเป็น JSON")
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir) if args.state_dir else None
    if args.round:
        result = run_round(asset=args.asset, publish_root=Path(args.publish_root),
                           cutoff_at=args.cutoff_at, state_dir=state_dir,
                           dry_run=args.dry_run, production_only=not args.all_styles)
    else:
        result = run(asset=args.asset, publish_root=Path(args.publish_root),
                     cutoff_at=args.cutoff_at, force_style=args.style,
                     state_dir=state_dir, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
        return 0 if result["ok"] else 1

    print(f"[{result['asset']}] แท่งฐาน M30 {result.get('context_bar_at')} · "
          f"M15 {result.get('trigger_bar_at')}")
    for style_id, state in (result.get("states") or {}).items():
        print(f"  สถานะ {style_id}: {state}")
    for item in result.get("skipped") or []:
        print(f"  ข้าม {item['style']}: {item['reason']}")
    decision = result.get("decision") or {}
    if args.round:
        print(f"  คำตัดสิน: {'ผลิต ' + ', '.join(decision.get('styles') or []) if decision.get('publish') else 'ไม่ผลิต'}"
              f" — {decision.get('reason') or result.get('reason')}")
        for article in result.get("articles") or []:
            _print_article(article)
    else:
        print(f"  คำตัดสิน: {'ผลิต ' + str(decision.get('style')) if decision.get('publish') else 'ไม่ผลิต'}"
              f" — {decision.get('reason') or result.get('reason')}")
        _print_article(result)
    return 0 if result["ok"] else 1


def _print_article(article: dict) -> None:
    for finding in article.get("findings") or []:
        print(f"  [{finding['severity']}] {finding['rule']} (บรรทัด {finding['line']}): "
              f"{finding['message']}")
    if article.get("published"):
        print(f"  บท: {article['article']} · {article['words']} คำ")
        for image in article.get("images") or []:
            print(f"  ภาพ: {Path(image['path']).name} · {image['kb']} KB")


if __name__ == "__main__":
    raise SystemExit(main())
