"""สร้างภาพทดลอง Style A แบบ 6 อินดิเคเตอร์หลัก — ไม่แตะสายผลิตจริง"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import chart_public_renderer, wcb_series_source, wcb_source


def main() -> int:
    parser = argparse.ArgumentParser(description="ภาพทดลอง Style A + 6 อินดิเคเตอร์หลัก")
    parser.add_argument("--snapshot", type=Path, required=True,
                        help="raw.snapshot.json ของสาย public")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bars", type=int, default=chart_public_renderer.DAILY_BARS,
                        help="จำนวนแท่ง D1 ที่แสดง (คำนวณอินดิเคเตอร์จากประวัติเต็ม)")
    args = parser.parse_args()

    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    evidence = wcb_source.normalize(snapshot)
    # ภาพ public ต้องใช้ session ชุดเดียวกับตัวคำนวณ technicals ของ provider
    # จึงไม่คัดแท่งวันหยุดบางตาที่ endpoint ยังนับรวม (ต่างจากสายวิเคราะห์ภายใน)
    _meta, rows, _label = wcb_series_source.fetch_series_rows(
        wcb_source.tag_for(evidence["asset"]), count=2000, calendar=None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = chart_public_renderer.render_daily_indicator_lines(
        rows, evidence, args.output, bars=args.bars)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
