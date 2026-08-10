"""สายท่อหลัก — ดึงข้อมูล ตรวจ วาดกราฟ เขียนบทความ ตรวจบทความ แล้วแยกของภายในกับของสาธารณะ

    python -m tools.build_daily_package --asset eurusd --batch-id 2026-08-03T07-00Z-daily-market

ผลลัพธ์ลงสองที่ที่แยกขาดจากกัน (จัดใหม่ 2026-08-04 ตามคำสั่งผู้ใช้)

**1. กองไฟล์ทำงาน** `--output-root` (ค่าตั้งต้น `../work/build`) — ของครบเหมือนเดิมทุกไฟล์

    work/build/<batch_id>/<asset>/
      internal/  raw.snapshot.json · normalized.market.json · technical.evidence.json
                 source-log.json · qa-report.json · license-report.json · news-log.json
                 publish-report.json (สไตล์ไหนผ่าน/ไม่ผ่านด่าน เพราะอะไร)
      public/    article.md · article.json · chart-daily.webp · meta.json

**2. ของที่ผู้ใช้หยิบไปอัป** `--publish-root` (ค่าตั้งต้น `../output`) — มีแค่ .md กับ .webp

    output/<DD-MMYYYY>/<นักเขียน>/<asset>.md + <asset>.webp

บทความสามสไตล์จาก evidence pack ก้อนเดียวกัน (ดู `tools/writers.py`) — ต่างกันที่วิธีเล่า
ไม่ใช่ต่างกันที่ข้อสรุป · แต่ละสไตล์ผ่านด่านตรวจของตัวเองก่อนถึงจะมีไฟล์วางลงไป

สไตล์ ② (กฤช) เป็นคนเดียวที่เขียนตัวเลขจุดเข้า จุดตัดขาดทุน และอัตราส่วนผลตอบแทน
ต่อความเสี่ยง (คำสั่งผู้ใช้ 2026-08-04 ปลดมติข้อ 14ก) โดยรับแผนจากสาขา internal เดิม
ไม่ได้คำนวณเอง — วันที่ไม่มีจังหวะ หัวข้อนั้นหายไปทั้งอัน ไม่ใช่เขียนว่า "ไม่มีแผน"

fail-closed ทุกชั้นตามเดิม: ด่านข้อมูลไม่ผ่าน = ไม่มีโฟลเดอร์ public เลย ไม่ใช่เขียนบทความ
แล้วค่อยติดป้ายห้ามเผยแพร่ · ด่านบทความไม่ผ่าน = ย้ายทุกไฟล์ไป internal/rejected/ เพื่อ audit
· สไตล์ไหนไม่ผ่านด่าน = ไม่มีไฟล์ของสไตล์นั้นใน output/ ไม่ใช่วางไว้แล้วติดป้าย
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import article_builder, calendar_feed, chart_renderer, integrity, license_gate  # noqa: E402
from tools import levels as level_engine  # noqa: E402
from tools import news_fallback, news_source, public_copy_validator  # noqa: E402
from tools import image_output, pilot_generator, publish_layout, risk_auditor  # noqa: E402
from tools import trade_plan, voice_rules, writers  # noqa: E402
from tools import wcb_copy_validator, wcb_series_source, wcb_source, wcb_writers  # noqa: E402


# แหล่งข้อมูลเดียวของระบบคือ WCB series API ตั้งแต่ 2026-08-05
# **MT5 ถูกถอดออกทั้งระบบตามคำสั่งผู้ใช้** — repo ที่ส่งมอบต้องรันได้โดยผู้รับไม่ต้อง
# ติดตั้ง terminal ไม่ต้องเปิดบัญชีโบรก และไม่ต้องอยู่บน Windows
# ประวัติการอ่านสัญญาของโบรกยังเก็บไว้ในทะเบียนสิทธิ์ (`mt5_raw_trading` สถานะ retired)
# Yahoo ยังอยู่แต่เป็นทางสำรองที่ต้องสั่งด้วย --source yahoo เท่านั้น
# ห้ามให้สายท่อสลับแหล่งเองเงียบ ๆ เมื่อแหล่งหลักล้ม — ล้มต้องเห็นว่าล้ม
SOURCE_WCB = "wcb"
SOURCE_YAHOO = "yahoo"
SOURCE_SNAPSHOT = "snapshot"
WCB_SERIES_PROVIDER_KEY = wcb_series_source.PROVIDER_KEY

# สองสายที่เดินคู่กันในสายท่อเดียว (เชื่อมเข้ามา 2026-08-05 ตามคำสั่งผู้ใช้)
#   internal — แท่ง D1 · สไตล์ ①②③ · สิทธิ์ข้อมูลยังไม่ยืนยัน ⇒ ใช้ภายในเท่านั้น
#   public   — snapshot API ของ WCB · 4 กรอบเวลา · สไตล์ A/B/C · รอยืนยันสิทธิ์
# แยกเป็นสองสายแทนที่จะสลับ --source เพราะต่างกันทั้งรูปข้อมูล ตัวเขียน และด่านตรวจ
LINE_INTERNAL = "internal"
LINE_PUBLIC = "public"
# รันทั้งสองสายด้วยคำสั่งเดียว — ปลายทางเผยแพร่คือเว็บ WCB เอง (ผู้ใช้ยืนยัน 2026-08-05)
# ยังไม่ยุบตัวเขียนสองชุดเข้าด้วยกัน เพราะสัญญาส่งออกของเว็บยังไม่เคยทดสอบนำเข้าจริง
# (หน้าบทวิเคราะห์ยังไม่เปิด — ข้อ 2 ที่ถามทีมเว็บไป) ถ้ายุบก่อนแล้วสัญญาเปลี่ยน
# จะไม่เหลือสายที่ใช้งานได้เลย · สายภายในยังถือสาขาแผนการเทรดซึ่งสายเว็บไม่มี
LINE_BOTH = "both"
WCB_PROVIDER_KEY = "wcb_snapshot_api"

# ช่อง `wcb` คือ tag ที่ WCB API รู้จัก — `btcusd` เป็นตัวเดียวที่ชื่อไม่ตรงกับหัวข้อของเรา
# ช่อง `default_source` แยกรายหัวข้อเพราะแหล่งใหม่ไม่ได้ครอบคลุมทุกตลาดเท่ากัน
# ช่อง `provider` ต้องตรงกับ default_source เสมอ ไม่งั้นรายงานสิทธิ์จะชี้ผิดสัญญา
ASSETS = {
    "eurusd": {
        "symbol": "EUR/USD", "yahoo": "EURUSD=X", "wcb": "eurusd",
        "instrument_type": "forex_spot",
        "unit": "ดอลลาร์ต่อยูโร", "decimals": 5, "provider": WCB_SERIES_PROVIDER_KEY,
        "default_source": SOURCE_WCB,
    },
    # เพิ่ม 2026-08-06 ตามคำสั่งผู้ใช้ · ปลายทางรู้จัก tag `gbpusd` ตรงชื่อ (วัดจริงแล้ว
    # ได้ symbol "GBP/USD" ความละเอียดเต็มห้าตำแหน่งจาก series endpoint)
    "gbpusd": {
        "symbol": "GBP/USD", "yahoo": "GBPUSD=X", "wcb": "gbpusd",
        "instrument_type": "forex_spot",
        "unit": "ดอลลาร์ต่อปอนด์", "decimals": 5, "provider": WCB_SERIES_PROVIDER_KEY,
        "default_source": SOURCE_WCB,
    },
    # ⚠️ tag ต้องเป็น `btc` เท่านั้น ห้ามใช้ `btcusd` แม้ปลายทางจะรับชื่อนั้นด้วย
    # ทั้งสองชื่อตอบ 200 และคืน symbol "BTC/USD" เหมือนกัน แต่ **เป็นคนละชุดข้อมูล**
    # วัดจริง 2026-08-05 หลังทีม dev อัปให้: `btc` ให้ครบเจ็ดวัน · `btcusd` ยังเป็นชุดเก่า
    # จันทร์-ศุกร์ ⇒ หยิบผิดชื่อจะได้ข้อมูลขาดสุดสัปดาห์โดยไม่มีอะไรฟ้อง
    "btcusd": {
        "symbol": "BTC/USD", "yahoo": "BTC-USD", "wcb": "btc",
        "instrument_type": "crypto_spot",
        "unit": "ดอลลาร์ต่อบิทคอยน์", "decimals": 2, "provider": WCB_SERIES_PROVIDER_KEY,
        "default_source": SOURCE_WCB,
    },
    "xauusd": {
        "symbol": "XAU/USD", "yahoo": None, "wcb": "xauusd",
        "instrument_type": "spot_metal",
        "unit": "ดอลลาร์ต่อออนซ์", "decimals": 2, "provider": WCB_SERIES_PROVIDER_KEY,
        "default_source": SOURCE_WCB,
    },
    # หุ้นรายตัว — หัวข้อที่สี่ (คำสั่งผู้ใช้ 2026-08-04) ใช้ CFD ของโบรกเจ้าเดิม
    # ปฏิทินต่างจากสามตัวแรก: ตลาดหุ้นสหรัฐหยุดตามวันหยุดของตลาด ไม่ใช่แค่เสาร์อาทิตย์
    "nvda": {
        "symbol": "NVDA", "yahoo": "NVDA", "wcb": "nvda",
        "instrument_type": "stock_cfd",
        "unit": "ดอลลาร์ต่อหุ้น", "decimals": 2, "provider": WCB_SERIES_PROVIDER_KEY,
        "default_source": SOURCE_WCB,
    },
    # เพิ่ม 2026-08-10 ตามคำสั่งผู้ใช้ — ทดสอบยิง API จริงก่อนลงทะเบียน (ไม่เดา):
    # tag `usdthb` ตอบ 200 คืน symbol "USD/THB" ราคาห้าตำแหน่งเหมือนคู่เงินอื่น ·
    # series endpoint ให้ 331 แท่ง ข้ามเสาร์-อาทิตย์ปกติแบบ forex_spot
    "usdthb": {
        "symbol": "USD/THB", "yahoo": "USDTHB=X", "wcb": "usdthb",
        "instrument_type": "forex_spot",
        "unit": "บาทต่อดอลลาร์", "decimals": 5, "provider": WCB_SERIES_PROVIDER_KEY,
        "default_source": SOURCE_WCB,
    },
    # ⚠️ tag ต้องเป็น `sol` เท่านั้น (แบบเดียวกับ `btc` ไม่ใช่ `btcusd`) — วัดจริง 08-10:
    # `sol` กับ `solusd` ตอบเหมือนกันทั้งคู่ตอนนี้ แต่ยึด tag สั้นตามธรรมเนียมเดิมของคริปโท
    # series endpoint ให้ 420 แท่ง มีข้อมูลวันเสาร์-อาทิตย์ครบ (ไม่มีปัญหาแบบ E6/E8 ของ BTC)
    "solusd": {
        "symbol": "SOL/USD", "yahoo": "SOL-USD", "wcb": "sol",
        "instrument_type": "crypto_spot",
        "unit": "ดอลลาร์ต่อเหรียญ", "decimals": 2, "provider": WCB_SERIES_PROVIDER_KEY,
        "default_source": SOURCE_WCB,
    },
}


def resolve_source(source: str | None, snapshot_path: Path | None,
                   asset: str | None = None) -> str:
    """ตัดสินว่ารอบนี้ใช้แหล่งไหน — ไม่มีการเดาใจเมื่อคำสั่งขัดกันเอง

    source=None คือ "เลือกให้" : มีไฟล์ snapshot ก็ใช้ไฟล์ ไม่มีก็ตามค่าตั้งต้นของหัวข้อนั้น
    ค่าตั้งต้นแยกรายหัวข้อเพราะ WCB ไม่ได้ครอบคลุมทุกตลาดเท่ากัน ระบุ `asset` มาด้วยเสมอ
    ไม่ระบุจะได้ WCB ซึ่งเป็นแหล่งหลักของระบบ
    สั่ง --source yahoo พร้อมแนบ snapshot = คำสั่งขัดกัน ต้องฟ้อง ไม่ใช่เงียบแล้วเลือกข้างเอง
    """
    if source is None:
        if snapshot_path is not None:
            return SOURCE_SNAPSHOT
        if asset is None:
            return SOURCE_WCB
        return ASSETS[asset]["default_source"]
    if source != SOURCE_SNAPSHOT and snapshot_path is not None:
        raise SystemExit(
            f"--source {source} ใช้พร้อม --snapshot ไม่ได้ — เลือกอย่างใดอย่างหนึ่ง")
    return source


def load_rows(asset: str, config: dict, snapshot_path: Path | None,
              *, source: str | None = None,
              max_bar_age_days: int = wcb_series_source.MAX_BAR_AGE_DAYS):
    """คืน (rows, raw_payload, source_label)

    WCB series API เป็นทางหลัก · yahoo/snapshot ใช้ได้เฉพาะเมื่อสั่งด้วยธงชัดเจน
    ข้อผิดพลาดของแหล่งข้อมูลปล่อยให้ลอยขึ้นไป ไม่กลืนแล้วสลับแหล่ง
    """
    source = resolve_source(source, snapshot_path, asset)
    if source == SOURCE_WCB:
        meta, rows, label = wcb_series_source.fetch_asset_rows(
            asset, max_age_days=max_bar_age_days)
        return rows, {"provider_meta": meta}, label
    if source == SOURCE_YAHOO:
        if not config["yahoo"]:
            raise SystemExit(f"{asset} ไม่มีสัญลักษณ์ฝั่ง Yahoo ให้ดึง")
        meta, rows, url = pilot_generator.fetch_yahoo_rows(config["yahoo"])
        return rows, {"provider_meta": meta}, url
    if snapshot_path is None:
        raise SystemExit(f"--source snapshot ต้องระบุ --snapshot ด้วย ({asset})")
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    return payload["rows"], payload, str(snapshot_path)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_trade_branch(*, report: dict, level_map: dict, news: dict, internal: Path,
                       config: dict, asset: str, cutoff_at: str, batch_id: str) -> dict:
    """สาขาข้าง: แผนการเทรดฝั่ง internal + ด่านตรวจความเสี่ยง

    **สาขานี้ล้มไม่ทำให้บทความล้ม** — สไตล์ ② เล่าตัวเลขแผนได้ก็จริง (ผู้ใช้ปลดมติ
    ข้อ 14ก เมื่อ 2026-08-04) แต่หัวข้อนั้นเป็นส่วนเสริมที่หายไปเงียบได้ ไม่ใช่แกนบทความ
    · สาขาล้ม = ไม่มีหัวข้อแผน ไม่ใช่ไม่มีบทความ · หลักการเดียวกับข่าว
    — แต่ล้มแล้วต้องเห็นว่าล้ม ไม่กลืนเงียบ

    แผนที่ถูก veto (`verdict: block`) ไม่ออกจากระบบ — เขียนลง `internal/rejected-plan/`
    เพื่อให้ตรวจย้อนได้ว่าตกเพราะอะไร แบบเดียวกับ `internal/rejected/` ของบทความ
    """
    try:
        plan = trade_plan.build(
            report=report, level_map=level_map, news=news, asset=asset,
            symbol=config["symbol"], instrument_type=config["instrument_type"],
            cutoff_at=cutoff_at, batch_id=batch_id,
        )
        audit = risk_auditor.audit(plan, level_map=level_map, news=news)
    except Exception as exc:  # noqa: BLE001 — สาขาข้างห้ามลากสายท่อหลักล้ม
        write_json(internal / "trade-plan-error.json", {
            "status": "error", "error_type": type(exc).__name__, "detail": str(exc),
            "note": "แผนการเทรดล้ม แต่บทความยังเดินต่อตามหลักสาขาข้าง",
        })
        return {"status": "error", "detail": str(exc)}

    blocked = audit["verdict"] == risk_auditor.VERDICT_BLOCK
    target_dir = (internal / "rejected-plan") if blocked else internal
    write_json(target_dir / "trade-plan.json", plan)
    write_json(target_dir / "risk-audit.json", audit)
    if audit["findings"]:
        write_json(target_dir / "revision-order.json", {
            "verdict": audit["verdict"],
            "confidence_score": audit["confidence_score"],
            "round": audit["round"],
            "max_rounds": audit["max_rounds"],
            "findings": audit["findings"],
        })
    return {
        "status": "blocked" if blocked else "built",
        "classification": plan["classification"],
        "verdict": audit["verdict"],
        "confidence_score": audit["confidence_score"],
        "findings": len(audit["findings"]),
        "directory": target_dir,
        # ตัวแผนกับผลตรวจเดินทางต่อไปถึงชั้นจัดวางไฟล์ เพราะสไตล์ ② เขียนตัวเลขจุดเข้า
        # จุดตัดขาดทุน และอัตราส่วนแล้ว (คำสั่งผู้ใช้ 2026-08-04 ปลดมติข้อ 14ก)
        # ผู้ตัดสินว่าแผนไหนพูดได้อยู่ที่ `writers.plan_for_public` ที่เดียว ไม่ใช่ตรงนี้
        "plan": plan,
        "audit": audit,
    }


def build(asset: str, *, batch_id: str, output_root: Path, snapshot_path: Path | None = None,
          cutoff_at: str | None = None, source: str | None = None,
          max_bar_age_days: int = wcb_series_source.MAX_BAR_AGE_DAYS,
          use_news: bool = True, use_trade_plan: bool = True,
          publish_root: Path | None = None) -> dict:
    config = ASSETS[asset]
    cutoff_at = cutoff_at or datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    source = resolve_source(source, snapshot_path, asset)
    rows, raw_payload, source_label = load_rows(
        asset, config, snapshot_path, source=source, max_bar_age_days=max_bar_age_days)
    # provider ที่บันทึกต้องตรงกับแหล่งที่ใช้จริงในรอบนี้ ไม่ใช่ค่าตั้งต้นของสินทรัพย์
    provider_used = {
        SOURCE_WCB: WCB_SERIES_PROVIDER_KEY,
        SOURCE_YAHOO: "yahoo_finance",
    }.get(source, f"snapshot:{snapshot_path}")

    report = integrity.assess(
        rows, asset, calculated_at=cutoff_at, source_timestamp=cutoff_at,
        provider_indicators={},
    )
    gate = report["publication_gate"]
    data_ok = gate["status"] == "pass"

    asset_dir = output_root / batch_id / asset
    internal = asset_dir / "internal"
    write_json(internal / "raw.snapshot.json",
               {"asset": asset, "source": source_label, "cutoff_at": cutoff_at, "rows": rows,
                "provider": provider_used, **raw_payload})
    write_json(internal / "normalized.market.json",
               {"asset": asset, "asset_class": report["asset_class"],
                "session_timezone": report["session_timezone"],
                "public_timezone": report["public_timezone"],
                "candles": report["candles"],
                "anomalies": report["anomalies"], "gap_check": report["gap_check"]})
    technical_evidence = {
        "indicators": report["indicators"], "pivots": report["pivots"],
        "valid_completed_bars": report["valid_completed_bars"],
        # ค่า change/change_percent ที่บทความใช้ ต้องถูกบันทึกเป็นหลักฐาน
        # ไม่ใช่ให้ตัวสร้างบทความคำนวณเองแล้วหายไป (ดู article_builder.change_summary)
        **article_builder.change_summary(report),
    }
    write_json(internal / "technical.evidence.json", technical_evidence)
    # หลักฐานความสดและเขตเวลาของแหล่ง — ต้องบันทึกทุกครั้งทั้งตอนผ่านและไม่ผ่าน
    # เพื่อให้ตรวจย้อนได้ว่าตัวเลขในบทความมาจากแท่งที่สดจริงหรือของค้าง
    provider_meta = raw_payload.get("provider_meta", {}) if isinstance(raw_payload, dict) else {}
    write_json(internal / "source-log.json", [{
        "field": "rows", "count": len(rows), "source": source_label, "provider": provider_used,
        "source_mode": source,
        "broker": provider_meta.get("broker"),
        "server_offset_hours": provider_meta.get("server_offset_hours"),
        "server_offset_status": provider_meta.get("server_offset_status"),
        "last_bar_session_date": provider_meta.get("last_bar_session_date"),
        "last_bar_age_days": provider_meta.get("last_bar_age_days"),
        "freshness_max_age_days": provider_meta.get("freshness_max_age_days"),
        "freshness_attempts_used": provider_meta.get("freshness_attempts_used"),
        "empty_sessions": provider_meta.get("p002_empty_sessions", []),
        "warnings": provider_meta.get("warnings", []),
        "retrieved_at": cutoff_at, "reviewer": "tools.build_daily_package",
    }])

    # ตัดสินสิทธิ์ด้วยแหล่งที่ใช้จริงในรอบนี้ ไม่ใช่ค่าตั้งต้นในทะเบียน
    # ตั้งแต่ย้ายแหล่งหลัก หัวข้อเดียวกันรันได้จากหลายแหล่งที่คนละสัญญากัน
    license_providers = [provider_used]
    license_result = license_gate.evaluate(
        asset, content_qa_passed=False, data_quality_passed=data_ok,
        providers=license_providers,
    )
    write_json(internal / "license-report.json", license_result)

    if not data_ok:
        qa_report = {
            "status": "blocked",
            "stage": "data_integrity",
            "publication_gate": gate,
            "public_copy": None,
            "note": "ด่านข้อมูลไม่ผ่าน จึงไม่สร้างบทความและกราฟสาธารณะ",
        }
        write_json(internal / "qa-report.json", qa_report)
        return {"asset": asset, "status": "blocked", "stage": "data_integrity",
                "reasons": gate["reasons"], "directory": asset_dir}

    level_map = level_engine.build_level_map(report)
    public = asset_dir / "public"
    series = {
        name: chart_renderer.rolling_mean_series(report["candles"], period)
        for name, period in (("sma20", 20), ("sma50", 50))
        if report["indicators"][name]["approved_for_publication"]
    }
    hidden = [
        {"indicator": name, "required_bars": item["required_bars"],
         "visible_bars": report["valid_completed_bars"]}
        for name, item in report["indicators"].items()
        if not item["approved_for_publication"] and name in ("sma20", "sma50")
    ]
    # ชั้นแปลงภาษาก่อนของขึ้นฝั่ง public: ป้ายระดับเป็นภาษาคน + เลขบนภาพปัดกติกา
    # เดียวกับบทความ — ชื่อเทคนิคเต็มยังอยู่ครบใน level_map ฝั่ง internal
    reference_price = float(report["candles"][-1]["close"])
    chart_levels, level_id_map = article_builder.public_level_views(
        level_map["zones"], reference_price)
    chart_metadata = chart_renderer.render_daily_chart(
        candles=report["candles"], output_path=public / f"chart-daily{image_output.IMAGE_SUFFIX}",
        symbol=config["symbol"], cutoff_at=cutoff_at, levels=chart_levels,
        indicator_series=series, hidden_indicators=hidden, decimals=config["decimals"],
        price_text=lambda value: voice_rules.format_price(value, config["instrument_type"]),
    )
    # สมุดแปลฝั่ง internal: ระดับชื่อเทคนิคเต็ม + ตารางรหัส public + โค้ดเครื่องมือบนกราฟ
    write_json(internal / "level-map.json", {
        "reference_price": reference_price,
        "levels": level_map["levels"],
        "zones": level_map["zones"],
        "public_id_map": level_id_map,
        "public_labels": {view["id"]: view["label"] for view in chart_levels},
        "chart": {
            "plotted_indicators": chart_metadata["plotted_indicator_codes"],
            "hidden_indicators": chart_metadata["hidden_indicator_codes"],
        },
    })

    # ช่วง ② ปัจจัยจับตา — ข่าวล้มไม่หยุดสายท่อ (ต่างจากราคา) แต่ต้องบันทึกว่าล้มเพราะอะไร
    news = news_source.collect(asset, now=datetime.now(tz=timezone.utc)) if use_news else {
        "asset": asset, "items": [], "provider_used": None,
        "attempts": [], "cut_reason": "disabled_by_flag"}
    write_json(internal / "news-log.json", news)

    # สาขาข้าง — แผนการเทรดฝั่ง internal (Agent 06) + ด่านความเสี่ยง (Agent 07)
    # วางไว้ตรงนี้เพราะต้องการ level_map กับข่าวครบแล้ว · ผลไม่ย้อนกลับไปแตะบทความ
    trade_branch = build_trade_branch(
        report=report, level_map=level_map, news=news, internal=internal,
        config=config, asset=asset, cutoff_at=cutoff_at, batch_id=batch_id,
    ) if use_trade_plan else {"status": "disabled_by_flag"}

    article_data = article_builder.build_article_data(
        report=report, level_map=level_map, chart_metadata=chart_metadata,
        license_result=license_result, symbol=config["symbol"],
        instrument_type=config["instrument_type"], unit=config["unit"],
        decimals=config["decimals"], cutoff_at=cutoff_at, batch_id=batch_id,
        verified_news=news["items"],
    )
    markdown = article_builder.render_markdown(article_data)
    write_json(public / "article.json", article_data)
    (public / "article.md").write_text(markdown, encoding="utf-8")

    # หลักฐานเชิงบริบทของ v1.1 (ราคาย้อนหลัง เส้นค่าเฉลี่ย ความผันผวน โครงสร้างระดับ)
    # ถูกคำนวณในชั้น build_article_data — บันทึกคู่ไว้ฝั่ง internal ด้วย เพื่อให้ audit
    # ตัวเลขที่บทความเล่าได้จากไฟล์หลักฐานโดยตรง ไม่ต้องเปิด article.json ฝั่ง public
    technical_evidence = {**technical_evidence, "context": article_data["context"]}
    write_json(internal / "technical.evidence.json", technical_evidence)

    # หลักฐานที่ใช้ตรวจตัวเลข = ข้อมูลบทความ + technical.evidence.json
    # เพื่อให้ขนาดการเปลี่ยนแปลงที่บทความแสดง (เช่น "ลดลง 920.04") เทียบกับหลักฐานเจอ
    # แม้ค่าจริงติดลบ — ตัวจับตัวเลขของ validator อ่านเฉพาะขนาด ไม่อ่านเครื่องหมาย
    validation = public_copy_validator.validate(
        markdown, evidence={"article": article_data, "technical": technical_evidence},
        instrument_type=config["instrument_type"],
    )
    content_ok = validation["status"] == "pass"

    license_result = license_gate.evaluate(
        asset, content_qa_passed=content_ok, data_quality_passed=True,
        providers=license_providers,
    )
    write_json(internal / "license-report.json", license_result)
    write_json(internal / "qa-report.json", {
        "status": "pass" if content_ok else "rejected",
        "stage": "public_copy",
        "publication_gate": gate,
        "public_copy": validation,
        "public_output": "public/" if content_ok else "internal/rejected/",
        # v1.1 ตัดหมายเหตุ + disclaimer ออกจากบทความ public — เก็บไว้ตรงนี้เพื่อ audit
        "omitted_public_lines": article_builder.internal_note_lines(
            article_data["instrument"]["candle_state"]),
    })
    write_json(public / "meta.json", {
        "batch_id": batch_id,
        "asset": asset,
        "symbol": config["symbol"],
        "contract": article_builder.CONTRACT,
        "schema_version": article_builder.SCHEMA_VERSION,
        "cutoff_at": cutoff_at,
        "cutoff_public": article_data["instrument"]["cutoff_public"],
        "candle_state": article_data["instrument"]["candle_state"],
        "word_count": voice_rules.count_public_words(markdown),
        "word_count_method": ("ตัวนับ deterministic ใน tools/voice_rules.py — token ละติน/ตัวเลขนับตรง "
                              f"คำไทยประมาณจากอักขระ/{voice_rules.THAI_CHARS_PER_WORD} (ล็อกด้วยเทส)"),
        "data_status": "verified_by_publication_gate",
        "qa_status": "pass" if content_ok else "rejected",
        "publication_clearance": license_result["clearance"],
        "validator_version": validation["validator_version"],
    })

    if not content_ok:
        # fail-closed: ด่านบทความไม่ผ่าน = ไม่มีของสาธารณะ เหมือนด่านข้อมูล
        # แต่ย้ายทุกไฟล์ไป internal/rejected/ เพื่อให้ audit ได้ว่าถูกตีตกเพราะอะไร
        rejected = internal / "rejected"
        if rejected.exists():
            shutil.rmtree(rejected)
        shutil.move(str(public), str(rejected))
        return {
            "asset": asset, "status": "rejected", "stage": "public_copy",
            "content_ok": False, "clearance": license_result["clearance"],
            "validation": validation, "directory": asset_dir,
            "article": rejected / "article.md",
            "words": voice_rules.count_public_words(markdown),
            "trade_plan": trade_branch,
        }

    # ชั้นจัดวางไฟล์ที่ผู้ใช้เอาไปอัปจริง — บทความสามสไตล์จาก evidence pack ก้อนเดียวกัน
    # วางลง output/<วัน>/<นักเขียน>/ โดยไม่มีไฟล์ฝั่ง internal ปน (คำสั่งผู้ใช้ 2026-08-04)
    # สไตล์ ① ที่เขียนไว้ข้างบนยังอยู่ครบใน bundle เหมือนเดิม ชั้นนี้เป็นมุมมองที่วางทับ
    published = None
    if publish_root is not None:
        published = publish_layout.publish_asset(
            asset=asset, article_data=article_data, technical_evidence=technical_evidence,
            # static_path ใน metadata เป็นชื่อไฟล์เปล่า (พาธในเครื่องถูกกรองออกตั้งแต่ชั้นกราฟ)
            # ตัวไฟล์จริงอยู่ใต้ public/ ของ batch นี้ — ต้องประกอบพาธเอง
            chart_source=public / Path(chart_metadata["static_path"]).name,
            publish_root=publish_root,
            cutoff_at=cutoff_at, instrument_type=config["instrument_type"],
            trade_branch=trade_branch,
        )
        # สายภายในก็วางไฟล์ลงคลังเดียวกันด้วยสถานะสิทธิ์เดียวกัน จึงต้องติดป้ายเหมือนกัน
        published["clearance_notice"] = str(publish_layout.write_clearance_notice(
            publish_root, cutoff_at, clearance=license_result["clearance"],
            reasons=license_result["license_reasons"]))
        write_json(internal / "publish-report.json", published)

    return {
        "asset": asset, "status": "built", "content_ok": content_ok,
        "clearance": license_result["clearance"], "validation": validation,
        "directory": asset_dir, "article": public / "article.md",
        "chart": Path(chart_metadata["static_path"]),
        "words": voice_rules.count_public_words(markdown),
        "trade_plan": trade_branch,
        "published": published,
    }


def load_trade_branch(asset_dir: Path) -> dict | None:
    """อ่านแผนที่ **สายภายในเขียนไว้ในรอบเดียวกัน** — ไม่คำนวณแผนใหม่ที่สายนี้

    ตัวเลขแผนที่จะขึ้นบทความต้องมาจาก `internal/trade-plan.json` ซึ่งเป็นไฟล์หลักฐาน
    ที่ผ่านด่านความเสี่ยงมาแล้ว (มติผู้ใช้ข้อ 15 — ชั้นบทความไม่คำนวณเอง) การอ่านจาก
    ไฟล์จึงไม่ใช่ทางลัด แต่เป็นวิธีที่ทำให้ข้อผูกพันนั้นเป็นจริงตามตัวอักษร

    **แผนที่ถูกด่านความเสี่ยง veto ไปอยู่ `internal/rejected-plan/` ซึ่งฟังก์ชันนี้ไม่อ่าน**
    ⇒ แผนที่ถูกตีตกไม่มีทางเล็ดลอดขึ้นบทความ แม้ด่านชั้นถัดไปจะพลาด (fail-closed สองชั้น)

    คืน None เมื่อรอบนั้นสายภายในไม่ได้รัน หรือรันแล้วไม่มีแผน — ทั้งสองกรณีแปลว่า
    "ไม่มีหัวข้อแผนในบทความ" ซึ่งเป็นผลที่ถูกต้อง ไม่ใช่ความผิดพลาดที่ต้องกู้
    """
    internal = asset_dir / "internal"
    plan_path, audit_path = internal / "trade-plan.json", internal / "risk-audit.json"
    if not (plan_path.is_file() and audit_path.is_file()):
        return None
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return {"status": "built", "plan": plan, "audit": audit}


def resolve_public_plan(evidence: dict, trade_branch: dict | None) -> tuple[dict | None, str | None]:
    """ตัดสินว่าหัวข้อแผนขึ้นบท A/B/C ได้ไหม — คืน (แผนที่ใช้ได้, เหตุผลที่ไม่ผ่าน)

    ด่านสองชั้นที่ต่างหน้าที่กัน ห้ามรวมเป็นชั้นเดียว:

    1. `writers.plan_for_public` — **แผนนี้ดีพอจะพูดถึงไหม** (ผ่านด่านความเสี่ยง `pass`
       และไม่ใช่ `no_trade`) · ชั้นเดียวกับที่สไตล์ ② ใช้ ⇒ สองสายไม่มีวันใช้เกณฑ์ต่างกัน
    2. `wcb_writers.plan_rejection` — **แผนนี้เล่าคู่กับก้อน snapshot นี้ได้ไหม**
       ซึ่งเป็นคำถามที่มีเฉพาะสายนี้ เพราะแผนมาจาก series API แต่บทมาจาก snapshot API
    """
    plan = writers.plan_for_public(trade_branch)
    if plan is None:
        branch = trade_branch or {}
        inner = branch.get("plan") or {}
        if not trade_branch:
            return None, "no_internal_plan_in_batch"
        if inner.get("classification") == "no_trade":
            return None, "no_trade"
        verdict = (branch.get("audit") or {}).get("verdict")
        return None, f"risk_audit_verdict:{verdict or 'missing'}"
    rejection = wcb_writers.plan_rejection(evidence, plan)
    if rejection:
        return None, rejection
    return plan, None


def build_public(asset: str, *, batch_id: str, output_root: Path,
                 publish_root: Path | None = None, snapshot_path: Path | None = None,
                 cutoff_at: str | None = None,
                 max_age_minutes: int = wcb_source.MAX_AGE_MINUTES,
                 trade_branch: dict | None = None,
                 calendar_feed_fetcher=None) -> dict:
    """สายสาธารณะ — snapshot API ของ WCB → บท A/B/C → ด่านตรวจ → โครงที่หยิบไปอัป

    **ไม่ได้ใช้ทางเดียวกับ `build()` โดยตั้งใจ** เพราะสองสายใช้คนละอย่างแทบทุกชั้น:
    สายนี้ไม่ต้องคำนวณอินดิเคเตอร์เอง (API ส่งมาให้) ไม่ต้องวาดกราฟ (เว็บวาดจากหมุด)
    และบังคับสัญญาส่งออกคนละฉบับ · การยัดเข้าทางเดิมจะได้ if/else เต็มไปหมด
    โดยไม่ได้ใช้โค้ดร่วมกันจริงสักบรรทัด

    ที่ยังใช้ร่วมกันจริงคือ **ด่านสิทธิ์ข้อมูล** และ **โครงโฟลเดอร์ผลผลิต** ซึ่งอยู่ที่เดิมทั้งคู่

    `calendar_feed_fetcher` (เพิ่ม 2026-08-07): เรียก `fetcher(asset)` แล้วได้ก้อนดิบ
    ของ `/api/calendar/feed` กลับมา — **ไม่ระบุ (ค่าตั้งต้น) = ไม่แตะปฏิทินตัวใหม่เลย**
    ยังใช้ช่อง `calendar` เดิมใน snapshot ทุกประการ (พฤติกรรมเดิม ปลอดภัยกับเทสเดิม
    ทุกตัว) · ปลายทางจริง (`tools.run_daily`) ส่ง `calendar_feed.fetch_raw` เข้ามา
    เพื่อสลับไปใช้ฟีดใหม่ · ฟีดล่ม/ยิงไม่ได้ = fallback ปฏิทินเดิมอัตโนมัติ ไม่พารอบทั้งหมดล้ม
    """
    cutoff_at = cutoff_at or datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    if snapshot_path is not None:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
        source_label = str(snapshot_path)
    else:
        # ต้องแปลงชื่อหัวข้อเป็น tag ก่อนเสมอ — `btcusd` ปลายทางไม่รู้จัก รู้จักแค่ `btc`
        payload = wcb_source.fetch_payload(wcb_source.tag_for(asset))
        source_label = "wcb_snapshot_api"
    # ด่านความสดหยุดสายท่อจริง · ด่านความละเอียดติดธงแล้วเขียนต่อ (ผู้ใช้สั่ง 2026-08-05)
    # เพราะการปัดของปลายทางกระทบเฉพาะค่าที่เป็นราคา ไม่ได้กระทบทั้งก้อน — ดูเหตุผลเต็มที่
    # `wcb_source.ensure_resolution` · ตัวเขียนยุบเส้นที่ค่าชนกันให้เองแล้ว
    evidence = wcb_source.ensure_resolution(
        wcb_source.ensure_fresh(wcb_source.normalize(payload), max_age_minutes))
    if evidence.get("coarse_prices"):
        print(f"    ⚠️ {asset}: {evidence['coarse_note']}")

    # ปฏิทินตัวใหม่ /api/calendar/feed — แทนที่ evidence["calendar"] เมื่อมีตัวดึงมาให้
    # เท่านั้น ดูเหตุผลเต็มใน tools/calendar_feed.py — เลขจากฟีดนี้ต้องพ่วง
    # calendar_feed= เข้าด่านตรวจด้วยเสมอ
    calendar_feed_raw = None
    if calendar_feed_fetcher is not None:
        try:
            calendar_feed_raw = calendar_feed_fetcher(asset)
            calendar_feed.merge(evidence, calendar_feed_raw)
            print(f"    🗓️ {asset}: ปฏิทินจากฟีดใหม่ {len(evidence['calendar'])} รายการ")
        except calendar_feed.CalendarFeedUnusable as exc:
            print(f"    ⚠️ {asset}: ปฏิทินตัวใหม่ใช้ไม่ได้รอบนี้ ({exc}) — ใช้ปฏิทินเดิมแบบตัดตัวเลข")
            calendar_feed_raw = None
    if calendar_feed_raw is None:
        # ปฏิทินไม่ได้มาจากฟีดใหม่ (ปิดสวิตช์ หรือฟีดล่มแล้ว fallback) — ค่าในช่อง
        # calendar เดิมไม่มีหน่วยติดมา ต้องตัดทั้งค่าตามกติกาหน่วย (ทีมเว็บรอบสี่
        # 2026-08-10 ข้อ A-3) เหลือชื่อ+เวลา ประโยคปิดตัวเองใน _calendar_sentences
        stripped = calendar_feed.strip_snapshot_values(evidence)
        if stripped:
            print(f"    ✂️ {asset}: ตัดตัวเลขปฏิทิน snapshot {stripped} รายการ "
                  "(ไม่มีข้อมูลหน่วย) — เหลือชื่อรายการและเวลา")

    # ชั้นข่าวสำรอง — **ปิดสวิตช์อยู่ตั้งแต่วันแรก (ผู้ใช้สั่ง 2026-08-07)** รอคำตอบ E11
    # ปิดอยู่ = ไม่ยิงเครือข่ายเลยและ evidence ไม่ถูกแตะ · ดูเหตุผลเต็มใน tools/news_fallback.py
    fallback_log = news_fallback.apply(evidence, asset=asset)
    if fallback_log["used"]:
        print(f"    📰 {asset}: ใช้ข่าวจากชั้นสำรอง {fallback_log['added']} ชิ้น "
              f"({fallback_log['snapshot_news']})")

    asset_dir = output_root / batch_id / asset
    # **แยกโฟลเดอร์หลักฐานของสองสาย** — ทั้งสองสายเคยเขียนชื่อไฟล์ชุดเดียวกัน
    # (`raw.snapshot.json` · `source-log.json` · `qa-report.json` · `license-report.json`
    # · `publish-report.json`) ลง `internal/` เดียวกัน · ตราบใดที่สองสายรันคนละ batch
    # ก็ไม่มีใครทับใคร แต่ `tools.run_daily` รันทั้งสองสายด้วย batch เดียว (2026-08-05)
    # ⇒ หลักฐานของสายภายในถูกเขียนทับทุกวัน · เรื่องนี้สำคัญขึ้นมากตั้งแต่ A/B/C
    # แทนที่ ①②③ ในคลัง เพราะของสายภายในกลายเป็น**หลักฐานล้วน ๆ** ไม่มีบทให้ดูแทน
    internal = asset_dir / "internal" / "public-line"
    # เก็บก้อนดิบเสมอ ไม่ใช่ก้อนที่แปลงแล้ว — ตรวจย้อนกลับและรันซ้ำได้
    write_json(internal / "raw.snapshot.json", payload)
    # บันทึกทุกรอบแม้ตอนปิดสวิตช์ — ต้องตรวจย้อนได้ว่าบทของวันไหนใช้ข่าวจากชั้นไหน
    write_json(internal / "news-fallback-log.json", fallback_log)
    write_json(internal / "source-log.json", [{
        "field": "snapshot", "source": source_label, "provider": WCB_PROVIDER_KEY,
        "generated_at": evidence["generated_at"],
        "age_minutes": wcb_source.age_minutes(evidence),
        "news_count": len(evidence["news"]), "calendar_count": len(evidence["calendar"]),
        "retrieved_at": cutoff_at, "reviewer": "tools.build_daily_package",
    }])

    # หัวข้อแผนการเทรดในบท A/B/C (ผู้ใช้สั่งเปิด 2026-08-05) — แผนมาจากไฟล์หลักฐาน
    # ที่สายภายในเขียนไว้ใน batch เดียวกัน ไม่ได้คำนวณที่นี่ · ไม่มีแผน = ไม่มีหัวข้อ
    if trade_branch is None:
        trade_branch = load_trade_branch(asset_dir)
    plan, plan_reason = resolve_public_plan(evidence, trade_branch)
    write_json(internal / "trade-plan-note.json", {
        "included": plan is not None,
        "reason": plan_reason,
        "source": "internal/trade-plan.json" if trade_branch else None,
        "bias": (plan or {}).get("bias"),
        "rr_first_target": plan["targets"][0]["rr"] if plan else None,
    })

    # เขียนบททุกสไตล์ลงกองงานก่อนเสมอ เพื่อให้ตรวจได้แม้ด่านสิทธิ์จะกั้นการเผยแพร่
    drafts = {}
    for writer in wcb_writers.WCB_WRITERS:
        writer_plan = plan if writer.get("uses_trade_plan") else None
        markdown = writer["render"](evidence, writer_plan)
        result = wcb_copy_validator.validate(markdown, payload, plan=writer_plan,
                                             calendar_feed=calendar_feed_raw)
        (internal / "drafts").mkdir(parents=True, exist_ok=True)
        (internal / "drafts" / f"{writer['id']}.md").write_text(markdown, encoding="utf-8")
        drafts[writer["id"]] = {"style": writer["style"], "validation": result}
    content_ok = all(item["validation"]["status"] == "pass" for item in drafts.values())

    license_result = license_gate.evaluate(
        asset, providers=[WCB_PROVIDER_KEY],
        content_qa_passed=content_ok, data_quality_passed=True)
    write_json(internal / "license-report.json", license_result)
    write_json(internal / "qa-report.json",
               {writer_id: item["validation"] for writer_id, item in drafts.items()})

    # **`output/` คือคลังในเครื่อง ไม่ใช่การเผยแพร่** — README ของโฟลเดอร์นั้นระบุชัดว่า
    # "ไม่ใช่ของที่ส่งมอบ" และ "ห้าม push ขึ้น GitHub หรือที่เก็บออนไลน์ใด ๆ"
    #
    # เดิมสายนี้ผูกการวางไฟล์ไว้กับ `APPROVED_PUBLIC` ⇒ บทที่ผ่านด่านเนื้อหาครบทุกข้อ
    # ไปกองอยู่ที่ `internal/drafts/` แล้วไม่มีใครเห็น · ขณะที่บทของสายภายใน (①②③)
    # นั่งอยู่ใน `output/` มาตลอดด้วยสถานะ `approved-internal-only` เท่ากันเป๊ะ
    # ⇒ สองสายใช้เกณฑ์คนละชุดกับโฟลเดอร์เดียวกัน ซึ่งเป็นความไม่สอดคล้อง ไม่ใช่ความปลอดภัย
    #
    # เกณฑ์จริงของโฟลเดอร์นี้คือ **ผ่านด่านเนื้อหา** · สถานะสิทธิ์เป็นคนละชั้นที่ยังคุมอยู่
    # และยังเป็น `approved-internal-only` เหมือนเดิมทุกประการ — **ไม่มีอะไรถูกปลดล็อก**
    # ตัวที่กันการเผยแพร่จริงคือด่านสิทธิ์ตอนส่งออก ไม่ใช่การไม่เขียนไฟล์ลงคลังในเครื่อง
    published = None
    if content_ok and publish_root is not None:
        published = publish_layout.publish_wcb_asset(
            asset=asset, evidence=evidence, snapshot=payload,
            publish_root=publish_root, cutoff_at=cutoff_at, plan=plan)
        published["clearance"] = license_result["clearance"]
        published["cleared_for_publication"] = (
            license_result["clearance"] == license_gate.APPROVED_PUBLIC)
        published["clearance_notice"] = str(publish_layout.write_clearance_notice(
            publish_root, cutoff_at, clearance=license_result["clearance"],
            reasons=license_result["license_reasons"]))
        write_json(internal / "publish-report.json", published)

    return {
        "asset": asset, "line": LINE_PUBLIC,
        "status": "built" if content_ok else "rejected",
        "content_ok": content_ok, "clearance": license_result["clearance"],
        "license_reasons": license_result["license_reasons"],
        "directory": asset_dir, "drafts": drafts, "published": published,
        "trade_plan_public": {"included": plan is not None, "reason": plan_reason,
                              "bias": (plan or {}).get("bias"),
                              "rr_first_target": plan["targets"][0]["rr"] if plan else None},
    }


def run_public_line(args, cutoff: str) -> int:
    """ตัวสั่งงานของสายสาธารณะ — แยกจาก main() เพื่อไม่ให้ทางเดิมรกด้วย if ของสายใหม่"""
    results = []
    for asset in args.asset:
        try:
            result = build_public(
                asset, batch_id=args.batch_id, output_root=args.output_root,
                publish_root=None if args.no_publish else args.publish_root,
                snapshot_path=args.snapshot, cutoff_at=cutoff,
                calendar_feed_fetcher=(
                    (lambda _asset: calendar_feed.fetch_raw())
                    if getattr(args, "calendar_feed", False) else None))
        except wcb_source.KeyMissing as exc:
            print(f"{asset}: หยุด — {exc}")
            results.append({"asset": asset, "status": "source_failed"})
            continue
        except (wcb_source.SnapshotUnusable, wcb_source.SnapshotStale,
                wcb_source.SnapshotTooCoarse) as exc:
            print(f"{asset}: หยุดที่แหล่งข้อมูล — {exc}")
            results.append({"asset": asset, "status": "source_failed"})
            continue
        results.append(result)

        print(f"{asset} (สายสาธารณะ): ด่านบทความ "
              f"{'ผ่านครบสามสไตล์' if result['content_ok'] else 'มีสไตล์ที่ตก'} "
              f"· สถานะเผยแพร่ {result['clearance']}")
        note = result["trade_plan_public"]
        print("    หัวข้อแผนในบทความ: "
              + (f"มี ({note['bias']} · อัตราส่วนเป้าแรก {note['rr_first_target']:.2f})"
                 if note["included"] else f"ไม่มี — {note['reason']}"))
        for writer_id, item in result["drafts"].items():
            validation = item["validation"]
            mark = "✓" if validation["status"] == "pass" else "✗"
            print(f"    {mark} {item['style']} {validation['word_count']} คำ "
                  f"· กราฟ {validation['chart_markers']} จุด")
            for finding in validation["findings"]:
                if finding["severity"] == "fatal":
                    print(f"        [{finding['rule']}] {finding['detail']}")
        if result["published"]:
            print(f"    วางลงคลังในเครื่อง {result['published']['directory']} แล้ว")
            if not result["published"]["cleared_for_publication"]:
                # **ต้องบอกทุกครั้งที่วางไฟล์โดยยังไม่มีสิทธิ์** — คลังในเครื่องกับการเผยแพร่
                # เป็นคนละชั้น คนที่เห็นไฟล์อยู่ในโฟลเดอร์ต้องไม่เข้าใจว่ามันเคลียร์แล้ว
                print("    🔒 ยังไม่ได้รับสิทธิ์เผยแพร่ — ห้ามนำขึ้นเว็บหรือโซเชียล")
                for reason in result["license_reasons"]:
                    print(f"        ด่านสิทธิ์ข้อมูล: {reason}")
        else:
            # ไม่ได้วาง = ต้องบอกเหตุผลเสมอ ไม่งั้นดูเหมือนสายท่อเงียบไปเฉย ๆ
            print("    ไม่ได้วางลงคลัง เพราะมีสไตล์ที่ตกด่านเนื้อหา — ร่างอยู่ที่ "
                  f"{result['directory']}/internal/drafts/")
    return 0 if all(item["status"] == "built" for item in results) else 1


def main():
    # ต้องตั้งก่อน parse_args() — argparse พิมพ์ข้อความช่วยเหลือแล้วออกจากโปรแกรมทันที
    # ที่ `--help` ถ้ายังไม่ตั้ง คอนโซลโค้ดเพจไทย (cp874) จะพังทันทีที่เจออักขระอย่าง `·`
    # (พบ 2026-08-05 ตอนเพิ่มธง --line ซึ่งมีอักขระนั้นในข้อความช่วยเหลือ)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", action="append", choices=sorted(ASSETS), required=True)
    parser.add_argument("--line", choices=[LINE_INTERNAL, LINE_PUBLIC, LINE_BOTH],
                        default=LINE_INTERNAL,
                        help=f"{LINE_INTERNAL} = แท่ง D1 + สไตล์ ①②③ (ค่าตั้งต้น) · "
                             f"{LINE_PUBLIC} = snapshot API ของ WCB + สไตล์ A/B/C · "
                             f"{LINE_BOTH} = รันทั้งสองสายในคำสั่งเดียว")
    parser.add_argument("--batch-id", required=True, help="ห้ามมีเครื่องหมาย : เพราะใช้เป็นชื่อโฟลเดอร์")
    # ของทำงานกับของที่เอาไปอัป แยกรากคนละที่ตั้งแต่ 2026-08-04
    # ค่าตั้งต้นเดิมของ --output-root คือ ../outputs (มี s) ซึ่งไม่มีอยู่จริงในโปรเจกต์
    # ทุกคนจึงต้องพิมพ์ --output-root ทุกครั้ง ไม่งั้นไฟล์ไปโผล่โฟลเดอร์ใหม่ที่ไม่มีใครดู
    parser.add_argument("--output-root", type=Path, default=Path("../work/build"),
                        help="รากของกองไฟล์ทำงาน — หลักฐาน ผลด่าน และของฝั่ง internal")
    parser.add_argument("--publish-root", type=Path, default=Path("../output"),
                        help="รากของไฟล์ที่เอาไปอัปจริง — output/<วัน>/<นักเขียน>/<สินทรัพย์>.md|.webp")
    parser.add_argument("--no-publish", action="store_true",
                        help="สร้าง bundle อย่างเดียว ไม่ต้องวางไฟล์ลงโครงที่เอาไปอัป")
    parser.add_argument("--snapshot", type=Path, help="ไฟล์ snapshot (ใช้กับ --source snapshot)")
    parser.add_argument("--cutoff-at", help="เวลาตัดข้อมูลแบบ ISO ใช้ค่าเดียวกันทั้ง batch")
    parser.add_argument("--source",
                        choices=[SOURCE_WCB, SOURCE_YAHOO, SOURCE_SNAPSHOT],
                        default=None,
                        help="แหล่งข้อมูล — ไม่ระบุ = WCB series API "
                             "(หรือ snapshot ถ้าแนบ --snapshot มา) · yahoo เป็นทางสำรอง")
    parser.add_argument("--max-bar-age-days", type=int,
                        default=wcb_series_source.MAX_BAR_AGE_DAYS,
                        help="เพดานอายุแท่งล่าสุดของด่านความสด — ผ่อนได้เฉพาะกรณีวันหยุดยาวจริง")
    parser.add_argument("--no-news", action="store_true",
                        help="ไม่ต้องดึงข่าว — ได้บทความแบบระยะ 1 ที่ไม่มีช่วง ② ปัจจัยจับตา")
    parser.add_argument("--no-trade-plan", action="store_true",
                        help="ข้ามสาขาแผนการเทรดฝั่ง internal — บทความและกราฟไม่เปลี่ยน")
    # เปิดเป็นค่าตั้งต้นตั้งแต่ 2026-08-10 (มติผู้ใช้ · ทีมเว็บรอบสี่ข้อ A-3) — สายปฏิทิน
    # เก่าใน snapshot ไม่มีข้อมูลหน่วย เลขเปล่า "4.09" เคยหลุดขึ้นบทจริง · ปิดได้ด้วย
    # --no-calendar-feed เพื่อดีบั๊ก แต่เลขปฏิทินจะถูกตัดทั้งหมด (ด่านหน่วยยังคุมเสมอ)
    parser.add_argument("--calendar-feed", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="ใช้ /api/calendar/feed แทนช่อง calendar เดิมใน snapshot "
                             "(มีหน่วยตัวเลข + ครอบคลุมกว้างกว่า) — เปิดเป็นค่าตั้งต้น "
                             "· --no-calendar-feed = สายเก่าแบบตัดตัวเลขทั้งหมด")
    args = parser.parse_args()

    cutoff = args.cutoff_at or datetime.now(tz=timezone.utc).isoformat(timespec="seconds")

    return dispatch(args, cutoff)


def dispatch(args, cutoff: str) -> int:
    """เลือกว่ารอบนี้เดินสายไหน — แยกจาก main() เพื่อให้เทสเรียกได้โดยไม่ต้องผ่าน argparse"""
    if args.line == LINE_PUBLIC:
        return run_public_line(args, cutoff)
    if args.line == LINE_BOTH:
        # สายภายในก่อนเสมอ — ถ้าข้อมูลราคาเสียจะรู้ตั้งแต่สายแรก ไม่ต้องรอยิง API รอบสอง
        internal_code = run_internal_line(args, cutoff)
        print()
        public_code = run_public_line(args, cutoff)
        return internal_code or public_code
    return run_internal_line(args, cutoff)


def run_internal_line(args, cutoff: str) -> int:
    """ตัวสั่งงานของสายภายใน — บทความ ①②③ + สาขาแผนการเทรด"""
    # เรียกครั้งแรกโดยไม่ระบุหัวข้อเพื่อให้ด่านคำสั่งขัดกันทำงานก่อนลงมือทั้งชุด
    resolve_source(args.source, args.snapshot)
    results = []
    for asset in args.asset:
        effective_source = resolve_source(args.source, args.snapshot, asset)
        if effective_source != SOURCE_WCB:
            print(f"⚠️  {asset}: ใช้แหล่ง '{effective_source}' ไม่ใช่ WCB series API "
                  "— บันทึกไว้ใน source-log.json แล้ว")
        try:
            result = build(asset, batch_id=args.batch_id, output_root=args.output_root,
                           snapshot_path=args.snapshot, cutoff_at=cutoff,
                           source=effective_source, max_bar_age_days=args.max_bar_age_days,
                           use_news=not args.no_news,
                           use_trade_plan=not args.no_trade_plan,
                           publish_root=None if args.no_publish else args.publish_root)
        except (wcb_series_source.SeriesUnavailable, wcb_series_source.SeriesStaleData) as exc:
            # แหล่งข้อมูลล้ม = หยุดสินทรัพย์นั้น ไม่สลับแหล่งเองและไม่เขียนจากของเก่า
            print(f"{asset}: หยุดที่แหล่งข้อมูล — {exc}")
            results.append({"asset": asset, "status": "source_failed"})
            continue
        results.append(result)
        if result["status"] == "blocked":
            print(f"{asset}: ถูกกั้นที่ด่านข้อมูล — ไม่มีบทความสาธารณะ")
            for reason in result["reasons"]:
                print(f"    ข้อ {reason['rule']} {reason['code']}: {reason['detail']}")
        elif result["status"] == "rejected":
            print(f"{asset}: ด่านบทความไม่ผ่าน — ย้ายผลทั้งหมดไป internal/rejected "
                  f"ไม่มีโฟลเดอร์ public")
            for item in result["validation"]["findings"]:
                print(f"    บรรทัด {item['line']} [{item['rule']}] {item['detail']}")
        else:
            print(f"{asset}: สร้างบทความแล้ว ({result['words']} คำโดยประมาณ) "
                  f"· ด่านบทความ {result['validation']['status']} "
                  f"· สถานะเผยแพร่ {result['clearance']}")
            for item in result["validation"]["findings"]:
                print(f"    บรรทัด {item['line']} [{item['rule']}] {item['detail']}")
            published = result.get("published")
            if published:
                note = published["trade_plan_public"]
                print("    หัวข้อแผนในบทความ: "
                      + (f"มี ({note['bias']} · อัตราส่วนเป้าแรก {note['rr_first_target']:.2f})"
                         if note["included"] else f"ไม่มี — {note['reason']}"))
                for entry in published["writers"]:
                    mark = "✓" if entry["status"] == "pass" else "✗"
                    print(f"    {mark} {entry['pen_name']} ({entry['style']}) "
                          f"{entry['word_count']} คำ → {entry['folder']}/{asset}.md")
                    if entry["status"] != "pass":
                        for item in entry["findings"]:
                            if item["severity"] == "fatal":
                                print(f"        [{item['rule']}] {item['detail']}")
        branch = result.get("trade_plan") or {}
        if branch.get("status") in ("built", "blocked"):
            print(f"    แผนเทรด (internal): {branch['classification']} "
                  f"· ด่านความเสี่ยง {branch['verdict']} "
                  f"· คะแนน {branch['confidence_score']}/10 · สั่งแก้ {branch['findings']} ข้อ")
        elif branch.get("status") == "error":
            print(f"    ⚠️  แผนเทรดล้ม (บทความไม่กระทบ): {branch['detail']}")
    return 0 if all(item["status"] == "built" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
