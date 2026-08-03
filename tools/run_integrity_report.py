"""ยิงด่านตรวจข้อมูลใส่ชุดข้อมูลที่เผยแพร่ไปแล้ว เพื่อดูว่า "ถ้ามีด่านตั้งแต่แรก" ผลจะต่างอย่างไร

ใช้ snapshot ที่อยู่ใน OUTPUT/ เป็น input จึงได้ผลเดิมทุกครั้ง ไม่ต้องต่อเน็ต

    python -m tools.run_integrity_report --output-dir work/integrity-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import integrity  # noqa: E402


ASSETS = {
    "xauusd": "2026-08-03_xauusd",
    "eurusd": "2026-08-03_forex-eurusd",
    "btcusd": "2026-08-03_crypto-btcusd",
}


def resolve_output_dir() -> Path:
    """ชุด baseline อาจวางแบนใน OUTPUT/ หรือถูกจัดลงโฟลเดอร์ย่อยตามวันที่"""
    root = Path(__file__).resolve().parents[2] / "OUTPUT"
    probe = f"{ASSETS['xauusd']}.snapshot.json"
    if (root / probe).is_file():
        return root
    nested = sorted((path for path in root.glob("*/") if (path / probe).is_file()), reverse=True)
    return nested[0] if nested else root


OUTPUT_DIR = resolve_output_dir()


def provider_indicators(snapshot: dict) -> dict:
    """ค่า indicator ที่ provider ส่งมาสำเร็จรูป (กรณี XAU) — บันทึกไว้แต่ไม่อนุมัติ"""
    provided = snapshot.get("provided_technicals")
    if not provided:
        return {}
    values = provided.get("values", {})
    mapped = {"sma20": values.get("sma20"), "sma50": values.get("sma50"), "rsi14": values.get("rsi")}
    return {name: value for name, value in mapped.items() if value is not None}


def run(asset: str, basename: str, output_dir: Path) -> dict:
    snapshot = json.loads((OUTPUT_DIR / f"{basename}.snapshot.json").read_text(encoding="utf-8"))
    report = integrity.assess(
        snapshot["rows"],
        asset,
        calculated_at=snapshot["generated_at"],
        source_timestamp=snapshot["generated_at"],
        provider_indicators=provider_indicators(snapshot),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{basename}.integrity.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def describe(report: dict) -> str:
    gate = report["publication_gate"]
    lines = [
        f"### {report['asset']} ({report['asset_class']})",
        f"- แท่งทั้งหมด {len(report['candles'])} · ใช้คำนวณได้ {report['valid_completed_bars']}",
        f"- แท่งนอกปฏิทิน: {', '.join(report['gap_check']['unexpected_sessions']) or 'ไม่มี'}",
        f"- session ที่ขาด: {', '.join(report['gap_check']['missing_sessions']) or 'ไม่มี'}",
        f"- indicator ที่เผยแพร่ได้: {', '.join(sorted(report['published_indicator_values'])) or 'ไม่มี'}",
        f"- ฐาน Pivot: {report['pivots']['basis_session_date']} "
        f"({report['pivots']['basis_candle_state']}) สถานะ {report['pivots']['quality_status']}",
        f"- **ด่านเผยแพร่: {gate['status'].upper()}**",
    ]
    for reason in gate["reasons"]:
        lines.append(f"  - ข้อ {reason['rule']} `{reason['code']}` — {reason['detail']}")
    for warning in gate["warnings"]:
        lines.append(f"  - เตือน: {warning}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    sections = []
    for asset, basename in ASSETS.items():
        report = run(asset, basename, args.output_dir)
        sections.append(describe(report))

    summary = "\n\n".join(sections)
    summary_path = args.output_dir / "SUMMARY.md"
    summary_path.write_text(f"# ผลด่านตรวจข้อมูล\n\n{summary}\n", encoding="utf-8")

    # คอนโซลบางเครื่องเป็น cp874 จึงพิมพ์อักขระบางตัวไม่ได้ ให้แทนที่แทนการล้ม
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    print(summary)
    print(f"\nบันทึกที่ {summary_path}")


if __name__ == "__main__":
    main()
