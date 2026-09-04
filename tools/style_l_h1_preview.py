"""Local-only adapter for reviewing the Style L H1 contract before wiring production."""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path

from tools import style_l_h1_plan


def synthetic_review_source() -> dict:
    closes = [1.03, 1.04, 1.05, 1.04, 1.03, 1.02, 1.015, 1.01,
              1.001, 1.012, 1.018, 1.025, 1.03, 1.035, 1.04, 1.045,
              1.05, 1.055, 1.06, 1.065, 1.07, 1.075, 1.08, 1.085]
    rows = []
    for index, close in enumerate(closes):
        high, low = close + 0.003, close - 0.003
        if index == 8:
            low = 1.0
        if index == 2:
            high = 1.08
        if index == 16:
            high = 1.10
        if index == 19:
            high = 1.13
        rows.append({"at": f"2026-09-01T{index:02d}:00:00+00:00",
                     "open": close, "high": high, "low": low,
                     "close": close, "closed": True})
    return {"asset": "eurusd", "h4_bias": "up", "h1_rows": rows,
            "h4_rows": [], "atr14": 0.01, "stop_atr": 1.5,
            "decision_at": "2026-09-05T00:00:00+00:00"}


def build_preview(source: dict) -> dict:
    plan = style_l_h1_plan.build_h1_plan(
        source["asset"], source["h4_bias"], source["h1_rows"], source.get("h4_rows", []),
        decision_at=datetime.fromisoformat(source["decision_at"]),
        atr14=source.get("atr14"), stop_atr=source.get("stop_atr", 1.5),
    )
    return {
        "phase": "PHASE_1_CONTRACT_PROTOTYPE",
        "production_wired": False,
        "visual_status": "PLACEHOLDER_HOLD_NOT_B3",
        "plan": plan,
        "visual_contract": style_l_h1_plan.resolve_h1_visual_contract(plan),
        "public_table": style_l_h1_plan.render_public_table(plan),
    }


def render_review_html(preview: dict) -> str:
    plan = preview["plan"]
    leg = plan["plans"][0]
    canonical_decimals = plan["canonical_decimals"]
    rows = [
        ("Entry", style_l_h1_plan._display_zone(
            leg["entry_zone"], canonical_decimals=canonical_decimals)),
        ("SL", style_l_h1_plan.public_price(
            leg["stop_loss"], canonical_decimals=canonical_decimals)),
        ("TP1", style_l_h1_plan.public_price(
            leg["take_profit"][0], canonical_decimals=canonical_decimals)),
        ("TP2", style_l_h1_plan.public_price(
            leg["take_profit"][1], canonical_decimals=canonical_decimals)),
    ]
    level_cards = "".join(
        f'<div class="level"><b>{html.escape(name)}</b><span>{html.escape(value)}</span></div>'
        for name, value in rows)
    return f"""<!doctype html><html lang=\"th\"><meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Style L H1 contract preview</title><style>
body{{font:16px system-ui;margin:24px;color:#17352b;background:#fbfaf7}} .grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.panel{{border:1px solid #b9c9c1;border-radius:14px;padding:18px;background:white;min-height:180px}} .levels{{display:grid;gap:8px}}
.level{{display:flex;justify-content:space-between;border-left:5px solid #c99b22;padding:8px;background:#f3f6f4}} .table-wrap{{overflow-x:auto;margin-top:18px}}
table{{border-collapse:collapse;width:100%;min-width:760px;background:white}} th,td{{border:1px solid #cbd5d0;padding:10px;text-align:left}} th{{background:#123f31;color:white}}
.nowrap{{white-space:nowrap;word-break:keep-all}} .hold{{background:#fff2cc;padding:12px;border-radius:8px}} @media(max-width:640px){{.grid{{grid-template-columns:1fr}} body{{margin:12px}}}}
</style><body><h1>Style L — H1 Contract Preview</h1><p class=\"hold\">PHASE-1 CONTRACT PROTOTYPE · production_wired=false · HOLD_DATA_COVERAGE</p>
<p><b>Visual status:</b> PLACEHOLDER_HOLD_NOT_B3 — semantic/layout review only.</p><div class=\"grid\"><section class=\"panel\"><h2>H1 Context · 120 closed bars</h2><p>H4 bias: {html.escape(str(plan['direction']).upper())}</p><p>Confirmed structure only; no M15 public authority.</p></section>
<section class=\"panel\"><h2>H1 Execution Zoom · 48 bars + 24 slots</h2><div class=\"levels\">{level_cards}</div></section></div>
<div class=\"table-wrap\"><table><thead><tr><th>Side</th><th>H1 setup</th><th>Entry</th><th>SL</th><th>TP &amp; RR</th><th>Invalidation</th></tr></thead>
<tbody><tr><td class=\"nowrap\">{leg['side']}</td><td>{plan['status']}</td><td class=\"nowrap\">{rows[0][1]}</td><td class=\"nowrap\">{rows[1][1]}</td>
<td><span class=\"nowrap\">TP1 – {rows[2][1]} ({leg['risk_reward'][0]:g}R)</span><br><span class=\"nowrap\">TP2 – {rows[3][1]} ({leg['risk_reward'][1]:g}R)</span></td>
<td><span class=\"nowrap\">H1 structure {style_l_h1_plan.public_price(leg['invalidation']['value'], canonical_decimals=canonical_decimals)}</span></td></tr></tbody></table></div>
<p>ราคาแสดง 3 ตำแหน่งเพื่ออ่านง่าย; ระบบคำนวณจากค่าความละเอียดเต็ม</p></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--synthetic-review", action="store_true")
    args = parser.parse_args()
    if args.synthetic_review:
        source = synthetic_review_source()
    elif args.source:
        source = json.loads(args.source.read_text(encoding="utf-8"))
    else:
        parser.error("source is required unless --synthetic-review is used")
    preview = build_preview(source)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(
        json.dumps(preview, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.destination.with_suffix(".html").write_text(
        render_review_html(preview), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
