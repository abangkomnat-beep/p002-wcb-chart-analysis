"""สายท่อหลัก — ดึงข้อมูล ตรวจ วาดกราฟ เขียนบทความ ตรวจบทความ แล้วแยกของภายในกับของสาธารณะ

    python -m tools.build_daily_package --asset eurusd --batch-id 2026-08-03T07-00Z-daily-market

โครงผลลัพธ์ตาม §28 ของ P002_FIX_INSTRUCTIONS

    outputs/<batch_id>/<asset>/
      internal/  raw.snapshot.json · normalized.market.json · technical.evidence.json
                 source-log.json · qa-report.json · license-report.json
      public/    article.md · article.json · chart-daily.png · meta.json

ถ้าด่านข้อมูลไม่ผ่าน จะไม่มีโฟลเดอร์ public เลย — ไม่ใช่เขียนบทความแล้วค่อยติดป้ายห้ามเผยแพร่
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

from tools import article_builder, chart_renderer, integrity, license_gate  # noqa: E402
from tools import levels as level_engine  # noqa: E402
from tools import public_copy_validator, pilot_generator  # noqa: E402


ASSETS = {
    "eurusd": {
        "symbol": "EUR/USD", "yahoo": "EURUSD=X", "instrument_type": "forex_spot",
        "unit": "ดอลลาร์ต่อยูโร", "decimals": 5, "provider": "yahoo_finance",
    },
    "btcusd": {
        "symbol": "BTC/USD", "yahoo": "BTC-USD", "instrument_type": "crypto_spot",
        "unit": "ดอลลาร์ต่อบิตคอยน์", "decimals": 2, "provider": "yahoo_finance",
    },
    "xauusd": {
        "symbol": "XAU/USD", "yahoo": None, "instrument_type": "spot_metal",
        "unit": "ดอลลาร์ต่อออนซ์", "decimals": 2, "provider": "twelve_data",
    },
}


def load_rows(asset: str, config: dict, snapshot_path: Path | None):
    """คืน (rows, raw_payload, source) — XAU ยังไม่มีแหล่งดึงเอง ต้องป้อน snapshot"""
    if config["yahoo"]:
        meta, rows, url = pilot_generator.fetch_yahoo_rows(config["yahoo"])
        return rows, {"provider_meta": meta}, url
    if snapshot_path is None:
        raise SystemExit(f"{asset} ต้องใช้ --snapshot เพราะยังไม่มีแหล่งดึงข้อมูลอัตโนมัติ")
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    return payload["rows"], payload, str(snapshot_path)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build(asset: str, *, batch_id: str, output_root: Path, snapshot_path: Path | None = None,
          cutoff_at: str | None = None) -> dict:
    config = ASSETS[asset]
    cutoff_at = cutoff_at or datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    rows, raw_payload, source = load_rows(asset, config, snapshot_path)

    report = integrity.assess(
        rows, asset, calculated_at=cutoff_at, source_timestamp=cutoff_at,
        provider_indicators={},
    )
    gate = report["publication_gate"]
    data_ok = gate["status"] == "pass"

    asset_dir = output_root / batch_id / asset
    internal = asset_dir / "internal"
    write_json(internal / "raw.snapshot.json",
               {"asset": asset, "source": source, "cutoff_at": cutoff_at, "rows": rows,
                "provider": config["provider"], **raw_payload})
    write_json(internal / "normalized.market.json",
               {"asset": asset, "asset_class": report["asset_class"], "candles": report["candles"],
                "anomalies": report["anomalies"], "gap_check": report["gap_check"]})
    write_json(internal / "technical.evidence.json",
               {"indicators": report["indicators"], "pivots": report["pivots"],
                "valid_completed_bars": report["valid_completed_bars"]})
    write_json(internal / "source-log.json", [{
        "field": "rows", "count": len(rows), "source": source, "provider": config["provider"],
        "retrieved_at": cutoff_at, "reviewer": "tools.build_daily_package",
    }])

    license_result = license_gate.evaluate(
        asset, content_qa_passed=False, data_quality_passed=data_ok,
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
    chart_metadata = chart_renderer.render_daily_chart(
        candles=report["candles"], output_path=public / "chart-daily.png",
        symbol=config["symbol"], cutoff_at=cutoff_at, levels=level_map["zones"],
        indicator_series=series, hidden_indicators=hidden, decimals=config["decimals"],
    )

    article_data = article_builder.build_article_data(
        report=report, level_map=level_map, chart_metadata=chart_metadata,
        license_result=license_result, symbol=config["symbol"],
        instrument_type=config["instrument_type"], unit=config["unit"],
        decimals=config["decimals"], cutoff_at=cutoff_at, batch_id=batch_id,
    )
    markdown = article_builder.render_markdown(article_data)
    write_json(public / "article.json", article_data)
    (public / "article.md").write_text(markdown, encoding="utf-8")

    validation = public_copy_validator.validate(
        markdown, evidence=article_data, instrument_type=config["instrument_type"],
    )
    content_ok = validation["status"] == "pass"

    license_result = license_gate.evaluate(
        asset, content_qa_passed=content_ok, data_quality_passed=True,
    )
    write_json(internal / "license-report.json", license_result)
    write_json(internal / "qa-report.json", {
        "status": "pass" if content_ok else "revise",
        "stage": "public_copy",
        "publication_gate": gate,
        "public_copy": validation,
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
        "approximate_thai_words": article_builder.approximate_thai_words(markdown),
        "word_count_method": "ประมาณจากจำนวนอักษรหารสี่ ไม่ใช่ตัวตัดคำจริง",
        "data_status": "verified_by_publication_gate",
        "qa_status": "pass" if content_ok else "revise",
        "publication_clearance": license_result["clearance"],
        "validator_version": validation["validator_version"],
    })

    return {
        "asset": asset, "status": "built", "content_ok": content_ok,
        "clearance": license_result["clearance"], "validation": validation,
        "directory": asset_dir, "article": public / "article.md",
        "chart": Path(chart_metadata["static_path"]),
        "words": article_builder.approximate_thai_words(markdown),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", action="append", choices=sorted(ASSETS), required=True)
    parser.add_argument("--batch-id", required=True, help="ห้ามมีเครื่องหมาย : เพราะใช้เป็นชื่อโฟลเดอร์")
    parser.add_argument("--output-root", type=Path, default=Path("../outputs"))
    parser.add_argument("--snapshot", type=Path, help="ไฟล์ snapshot สำหรับสินทรัพย์ที่ยังดึงเองไม่ได้")
    parser.add_argument("--cutoff-at", help="เวลาตัดข้อมูลแบบ ISO ใช้ค่าเดียวกันทั้ง batch")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    cutoff = args.cutoff_at or datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    results = []
    for asset in args.asset:
        result = build(asset, batch_id=args.batch_id, output_root=args.output_root,
                       snapshot_path=args.snapshot, cutoff_at=cutoff)
        results.append(result)
        if result["status"] == "blocked":
            print(f"{asset}: ถูกกั้นที่ด่านข้อมูล — ไม่มีบทความสาธารณะ")
            for reason in result["reasons"]:
                print(f"    ข้อ {reason['rule']} {reason['code']}: {reason['detail']}")
        else:
            print(f"{asset}: สร้างบทความแล้ว ({result['words']} คำโดยประมาณ) "
                  f"· ด่านบทความ {result['validation']['status']} "
                  f"· สถานะเผยแพร่ {result['clearance']}")
            for item in result["validation"]["findings"]:
                print(f"    บรรทัด {item['line']} [{item['rule']}] {item['detail']}")
    return 0 if all(item["status"] == "built" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
