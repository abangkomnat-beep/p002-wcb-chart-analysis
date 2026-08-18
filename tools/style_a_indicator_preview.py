"""สร้างภาพทดลอง Style A แบบมีแผงอินดิเคเตอร์ — ไม่แตะสายผลิตจริง"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools import chart_public_renderer, wcb_series_source, wcb_source


def main() -> int:
    parser = argparse.ArgumentParser(description="ภาพทดลอง Style A + อินดิเคเตอร์ครบ")
    parser.add_argument("--snapshot", type=Path, required=True,
                        help="raw.snapshot.json ของสาย public")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    evidence = wcb_source.normalize(snapshot)
    _meta, rows, _label = wcb_series_source.fetch_asset_rows(evidence["asset"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = chart_public_renderer.render_daily_indicator_dashboard(
        rows, evidence, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
