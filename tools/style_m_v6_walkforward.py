"""Leakage-safe daily walk-forward evaluation for the Style M v6 prototype.

This is a QA-only harness.  It never writes production assets and it does not
alter the v5 pipeline.  A plan is built only from rows closed at its Bangkok
midnight cutoff.  The following 24 closed H1 bars are then used exclusively to
simulate its published OCO breakout/retest lifecycle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

from tools import intraday_bars, style_m_v6_story


SCHEMA = "style-m-v6-walkforward/v1"
DEFAULT_DAYS = 180
DEFAULT_IN_SAMPLE_DAYS = 60
HORIZON_HOURS = 24


def _at(row: dict) -> datetime:
    return intraday_bars.parse_at(row["at"])


def _touches(row: dict, low: float, high: float) -> bool:
    return float(row["low"]) <= high and float(row["high"]) >= low


def _invalidated(plan: dict, row: dict) -> bool:
    close = float(row["close"])
    return close <= plan["sl"] if plan["side"] == "LONG" else close >= plan["sl"]


def _exit_model(plan: dict, bars: list[dict], *, target_key: str) -> dict:
    """All-in TP/SL sensitivity model after a conservative zone fill.

    H1 OHLC cannot establish the path when a stop and target are both touched
    within one candle.  Such bars are not assigned a win or loss.
    """
    target = float(plan[target_key])
    for row in bars:
        if plan["side"] == "LONG":
            stop_hit, target_hit = float(row["low"]) <= plan["sl"], float(row["high"]) >= target
        else:
            stop_hit, target_hit = float(row["high"]) >= plan["sl"], float(row["low"]) <= target
        if stop_hit and target_hit:
            return {"outcome": "AMBIGUOUS_BAR", "at": row["at"], "r": None}
        if target_hit:
            return {"outcome": target_key.upper(), "at": row["at"], "r": plan["rr1"] if target_key == "tp1" else plan["rr2"]}
        if stop_hit:
            return {"outcome": "STOP", "at": row["at"], "r": -1.0}
    return {"outcome": "OPEN_AT_EXPIRY", "at": None, "r": None}


def simulate(story: dict, forward_bars: list[dict]) -> dict:
    """Simulate a single daily OCO plan without using bar data in its build."""
    if len(forward_bars) != HORIZON_HOURS:
        raise ValueError(f"walk-forward horizon must have {HORIZON_HOURS} H1 bars")
    plans = story["scenarios"]
    state = {side: "WAIT_TRIGGER" for side in plans}
    active: str | None = None
    trigger_index: int | None = None
    entry_index: int | None = None
    lifecycle = {"triggered": 0, "retests": 0, "invalidations": 0}
    entry: dict | None = None

    for index, row in enumerate(forward_bars):
        if active is None:
            long_hit = float(row["close"]) > plans["long"]["trigger"]
            short_hit = float(row["close"]) < plans["short"]["trigger"]
            if long_hit == short_hit:
                continue
            active = "long" if long_hit else "short"
            other = "short" if active == "long" else "long"
            state[active] = "TRIGGERED_WAIT_RETEST"
            state[other] = "CANCELLED_OPPOSITE_TRIGGER"
            trigger_index = index
            lifecycle["triggered"] += 1
            continue

        plan = plans[active]
        if entry_index is None:
            # Retest must be a subsequent *closed* H1 bar, as the plan states.
            if index <= (trigger_index or 0):
                continue
            if _invalidated(plan, row):
                state[active] = "INVALIDATED"
                lifecycle["invalidations"] += 1
                break
            if _touches(row, plan["entry_low"], plan["entry_high"]):
                state[active] = "RETEST_OBSERVED"
                entry_index = index
                lifecycle["retests"] += 1
                entry = {
                    "at": row["at"],
                    "fill": plan["entry_high"] if plan["side"] == "LONG" else plan["entry_low"],
                    "basis": "worst_entry_boundary",
                }

    if active is None:
        state = {side: "EXPIRED" for side in plans}
    elif entry_index is None and state[active] == "TRIGGERED_WAIT_RETEST":
        state[active] = "EXPIRED"

    result = {"scenario_states": state, "triggered_side": active,
              "lifecycle": lifecycle, "entry": entry,
              "exit_models": {}}
    if active is not None and entry_index is not None:
        exit_bars = forward_bars[entry_index + 1:]
        result["exit_models"] = {
            "tp1_all_in": _exit_model(plans[active], exit_bars, target_key="tp1"),
            "tp2_all_in": _exit_model(plans[active], exit_bars, target_key="tp2"),
        }
    return result


def _exit_summary(records: list[dict], model: str) -> dict:
    results = [record["simulation"]["exit_models"].get(model) for record in records]
    results = [item for item in results if item]
    counts = Counter(item["outcome"] for item in results)
    realized = [float(item["r"]) for item in results if item["r"] is not None]
    wins = sum(1 for value in realized if value > 0)
    return {
        "trades_with_retest": len(results), "resolved": len(realized),
        "wins": wins, "losses": sum(1 for value in realized if value < 0),
        "win_rate": round(wins / len(realized), 6) if realized else None,
        "expectancy_r": round(mean(realized), 6) if realized else None,
        "outcomes": dict(sorted(counts.items())),
        "excluded_ambiguous_or_open": len(results) - len(realized),
    }


def summarize(records: list[dict]) -> dict:
    scenario_states = Counter()
    triggered = Counter()
    lifecycle = Counter()
    for record in records:
        scenario_states.update(record["simulation"]["scenario_states"].values())
        if record["simulation"]["triggered_side"]:
            triggered[record["simulation"]["triggered_side"]] += 1
        lifecycle.update(record["simulation"]["lifecycle"])
    return {
        "plan_days": len(records), "scenario_count": len(records) * 2,
        "triggered_side": dict(sorted(triggered.items())),
        "scenario_final_states": dict(sorted(scenario_states.items())),
        "lifecycle": dict(sorted(lifecycle.items())),
        "exit_sensitivity": {
            "tp1_all_in": _exit_summary(records, "tp1_all_in"),
            "tp2_all_in": _exit_summary(records, "tp2_all_in"),
        },
    }


def evaluate(rows: list[dict], *, source_label: str, source_meta: dict,
             days: int = DEFAULT_DAYS, in_sample_days: int = DEFAULT_IN_SAMPLE_DAYS) -> dict:
    if days < 1 or not 0 <= in_sample_days < days:
        raise ValueError("days/in_sample_days ไม่ถูกต้อง")
    rows = sorted(rows, key=lambda row: row["at"])
    candidates: list[tuple[int, datetime]] = []
    for index, row in enumerate(rows):
        cutoff = _at(row) + timedelta(hours=1)
        # One plan exactly at Bangkok midnight, using only already-closed H1.
        if cutoff.hour == 0 and cutoff.minute == 0 and index >= 59 and index + HORIZON_HOURS < len(rows):
            candidates.append((index, cutoff))
    if len(candidates) < days:
        raise ValueError(f"usable daily cutoffs {len(candidates)} < requested {days}")
    selected = candidates[-days:]
    records: list[dict] = []
    for ordinal, (index, cutoff) in enumerate(selected):
        prefix = rows[:index + 1]
        common = {
            "partition": "IN_SAMPLE_DIAGNOSTIC" if ordinal < in_sample_days else "OUT_OF_SAMPLE",
            "ordinal": ordinal + 1, "cutoff": cutoff.isoformat(),
            "source_rows_used": len(prefix), "source_last_bar_at": prefix[-1]["at"],
        }
        try:
            prepared = style_m_v6_story.build(prefix, cutoff=cutoff, source_label=source_label,
                                              source_meta=source_meta)
        except style_m_v6_story.StoryUnavailable as exc:
            # A fail-closed oracle is a QA finding, never a silently skipped day.
            records.append({**common, "status": "STORY_UNAVAILABLE", "error": str(exc)})
            continue
        future = rows[index + 1:index + 1 + HORIZON_HOURS]
        simulation = simulate(prepared["story"], future)
        records.append({
            **common, "status": "PASS",
            "forward_first_bar_at": future[0]["at"], "forward_last_bar_at": future[-1]["at"],
            "story": {"source_sha256": prepared["story"]["source_sha256"],
                      "atr14": prepared["story"]["indicators"]["atr14"],
                      "adx14": prepared["story"]["indicators"]["adx14"],
                      "adx_regime": prepared["story"]["indicators"]["adx_regime"],
                      "donchian": prepared["story"]["donchian"],
                      "scenarios": prepared["story"]["scenarios"]},
            "simulation": simulation,
        })
    valid_records = [record for record in records if record["status"] == "PASS"]
    in_sample = [record for record in valid_records
                 if record["partition"] == "IN_SAMPLE_DIAGNOSTIC"]
    out_sample = [record for record in valid_records
                  if record["partition"] == "OUT_OF_SAMPLE"]
    unavailable = [record for record in records if record["status"] != "PASS"]
    return {
        "schema": SCHEMA,
        "methodology": {
            "parameters": "Frozen v6 constants; no result-driven tuning.",
            "decision_clock": "one plan at Bangkok midnight after the 23:00 H1 closes",
            "signal_window": "only rows at or before cutoff are supplied to build()",
            "forward_window": "next 24 closed H1 bars, excluded from signal construction",
            "oco": "first strict close crossing a trigger cancels the opposite scenario",
            "retest": "subsequent closed H1 range must touch entry zone; worst boundary fill",
            "invalidation": "after trigger and before retest, only a closed H1 beyond SL invalidates",
            "exit": "TP1/TP2 all-in TP/SL sensitivity only; same-H1 stop+target is ambiguous and excluded",
        },
        "coverage": {
            "source_rows": len(rows), "source_first_bar_at": rows[0]["at"],
            "source_last_bar_at": rows[-1]["at"], "requested_plan_days": days,
            "attempted_plan_days": len(records), "evaluated_plan_days": len(valid_records),
            "story_unavailable_days": len(unavailable),
            "story_unavailable_reasons": dict(sorted(Counter(record["error"] for record in unavailable).items())),
            "forward_bars_per_plan": HORIZON_HOURS,
            "total_forward_bar_observations": len(valid_records) * HORIZON_HOURS,
            "in_sample_attempted_days": in_sample_days, "in_sample_evaluated_days": len(in_sample),
            "out_of_sample_attempted_days": days - in_sample_days,
            "out_of_sample_evaluated_days": len(out_sample),
        },
        "in_sample": summarize(in_sample), "out_of_sample": summarize(out_sample),
        "combined": summarize(valid_records), "records": records,
    }


def _markdown(report: dict) -> str:
    coverage, combined = report["coverage"], report["combined"]
    in_sample, out_sample = report["in_sample"], report["out_of_sample"]
    tp1, tp2 = combined["exit_sensitivity"]["tp1_all_in"], combined["exit_sensitivity"]["tp2_all_in"]
    return "\n".join([
        "# Style M v6 — Independent Walk-forward QA (180 วัน)", "",
        "## ผลสรุป", "",
        f"- พยายาม {coverage['attempted_plan_days']} วัน: สร้าง oracle ได้ {coverage['evaluated_plan_days']} วัน; unavailable {coverage['story_unavailable_days']} วัน. แบ่ง in-sample diagnostic {coverage['in_sample_evaluated_days']}/{coverage['in_sample_attempted_days']} วัน และ out-of-sample {coverage['out_of_sample_evaluated_days']}/{coverage['out_of_sample_attempted_days']} วัน (พารามิเตอร์ถูกตรึงก่อนรัน ไม่มีการปรับจากผล)",
        f"- ข้อมูล BTCUSD H1 {coverage['source_rows']:,} แท่ง: {coverage['source_first_bar_at']} ถึง {coverage['source_last_bar_at']}; ใช้ forward {coverage['total_forward_bar_observations']:,} bar-observations.",
        f"- OCO trigger: Long {combined['triggered_side'].get('long', 0)} / Short {combined['triggered_side'].get('short', 0)}; retest {combined['lifecycle'].get('retests', 0)}; invalidation ก่อน retest {combined['lifecycle'].get('invalidations', 0)}.",
        f"- sensitivity TP1 all-in: resolved {tp1['resolved']}, win-rate {tp1['win_rate']}, expectancy {tp1['expectancy_r']}R; excluded ambiguous/open {tp1['excluded_ambiguous_or_open']}.",
        f"- sensitivity TP2 all-in: resolved {tp2['resolved']}, win-rate {tp2['win_rate']}, expectancy {tp2['expectancy_r']}R; excluded ambiguous/open {tp2['excluded_ambiguous_or_open']}.",
        "", "## แยกผลตามช่วงเวลา", "",
        f"- In-sample diagnostic: TP1 expectancy {in_sample['exit_sensitivity']['tp1_all_in']['expectancy_r']}R จาก {in_sample['exit_sensitivity']['tp1_all_in']['resolved']} resolved; TP2 expectancy {in_sample['exit_sensitivity']['tp2_all_in']['expectancy_r']}R จาก {in_sample['exit_sensitivity']['tp2_all_in']['resolved']} resolved.",
        f"- Out-of-sample: TP1 expectancy {out_sample['exit_sensitivity']['tp1_all_in']['expectancy_r']}R จาก {out_sample['exit_sensitivity']['tp1_all_in']['resolved']} resolved; TP2 expectancy {out_sample['exit_sensitivity']['tp2_all_in']['expectancy_r']}R จาก {out_sample['exit_sensitivity']['tp2_all_in']['resolved']} resolved.",
        "- สรุป QA: out-of-sample เป็นลบทั้งสอง sensitivity ก่อนคิดต้นทุนธุรกรรม จึงยังไม่ผ่านเกณฑ์ integrate/promote.",
        "", "## ขอบเขตและข้อจำกัด", "",
        "- ระหว่าง QA พบและแก้ numerical precision ของ RR หลัง tick rounding ก่อนรัน final snapshot; final run สร้าง oracle ได้ 180/180 วัน. การแก้ต้องผ่าน test และ code review แยกต่างหาก.",
        "- ทุกแผนสร้างจากแท่งปิดไม่เกิน cutoff เท่านั้น; แท่ง 24 ชั่วโมงถัดไปถูกใช้เฉพาะวัดผล จึงไม่มี future leakage.",
        "- ผลกำไรเป็น sensitivity ของการถือเต็มจำนวนถึง TP1 หรือ TP2 แยกกัน ไม่ใช่ผลของการแบ่งปิดบางส่วน เพราะ v6 ยังไม่ได้ระบุกติกาจัดการ position หลัง TP1.",
        "- H1 OHLC ระบุลำดับเมื่อ SL และ TP ถูกแตะในแท่งเดียวกันไม่ได้; บาร์ดังกล่าวถูกนับ AMBIGUOUS_BAR และตัดออกจาก expectancy/win-rate แทนการเลือกผลที่เป็นคุณต่อระบบ.",
        "- ชุดนี้ประเมิน BTCUSD จากฟีดเดียวและช่วงเวลาหนึ่งเท่านั้น; ไม่รวมค่าธรรมเนียม, slippage, spread, latency หรือ execution จริง.",
        "", "รายละเอียดตัวเลขทั้งหมดและหลักฐานรายวันอยู่ใน `walkforward-report.json`.", "",
    ])


def run(*, output_dir: Path, days: int = DEFAULT_DAYS,
        in_sample_days: int = DEFAULT_IN_SAMPLE_DAYS,
        input_snapshot: Path | None = None) -> dict:
    if input_snapshot:
        source = json.loads(Path(input_snapshot).read_text(encoding="utf-8"))
        meta, rows, label = source["source_meta"], source["rows"], source["source_label"]
    else:
        retrieved = datetime.now(timezone.utc)
        meta, rows, label = intraday_bars.fetch_rows("btcusd", timeframe="1h", outputsize=5000,
                                                      now=retrieved)
        source = {"retrieved_at": retrieved.isoformat(), "source_meta": meta,
                  "source_label": label, "rows": rows}
    output_dir.mkdir(parents=True, exist_ok=True)
    source_bytes = json.dumps(source, ensure_ascii=False, sort_keys=True).encode("utf-8")
    source_path = output_dir / "source-btcusd-h1.json"
    source_path.write_bytes(source_bytes + b"\n")
    report = evaluate(rows, source_label=label, source_meta=meta, days=days,
                      in_sample_days=in_sample_days)
    report["source_snapshot"] = {"path": source_path.name,
                                 "sha256": hashlib.sha256(source_bytes).hexdigest()}
    report_path = output_dir / "walkforward-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path = output_dir / "walkforward-report.md"
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return {"report": report, "output_dir": str(output_dir),
            "source": str(source_path), "markdown": str(markdown_path)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--in-sample-days", type=int, default=DEFAULT_IN_SAMPLE_DAYS)
    parser.add_argument("--input-snapshot", type=Path)
    args = parser.parse_args()
    result = run(output_dir=args.output_dir, days=args.days, in_sample_days=args.in_sample_days,
                 input_snapshot=args.input_snapshot)
    print(json.dumps({"output_dir": result["output_dir"],
                      "coverage": result["report"]["coverage"],
                      "combined": result["report"]["combined"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
