"""Render deterministic en-ZA EUR/USD recovery images from preserved run inputs."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from tools import forex_daily_calendar_renderer, forex_daily_plan, wcb_source


def render(historical_run: Path, output_dir: Path) -> dict:
    trace = json.loads((historical_run / "evidence" / "eurusd-decision-trace.json").read_text(encoding="utf-8"))
    inputs = json.loads((historical_run / "input" / "eurusd-closed-bars.json").read_text(encoding="utf-8"))
    if trace.get("asset") != "eurusd" or inputs.get("asset") != "eurusd":
        raise ValueError("recovery input must be EURUSD")
    events = trace.get("events")
    if not isinstance(events, list) or len(events) != 1 or events[0].get("source_id") != "400922":
        raise ValueError("recovery calendar event custody is invalid")
    rows = inputs.get("rows")
    required = ("1h", "4h", "15min")
    if not isinstance(rows, dict) or any(not isinstance(rows.get(key), list) for key in required):
        raise ValueError("recovery price rows are incomplete")
    output_dir.mkdir(parents=True, exist_ok=False)
    scenario = trace["scenario"]
    h1_name = "eurusd-forex-daily-h1-plan.webp"
    m15_name = "eurusd-forex-daily-m15-trigger.webp"
    h1_path, m15_path = output_dir / h1_name, output_dir / m15_name
    forex_daily_plan.save_h1_chart("eurusd", rows["1h"], rows["4h"], trace["h4"], trace["h1"],
                                   scenario, trace["preferred_direction"], trace["bases"]["1h"],
                                   h1_path, locale="en-ZA")
    forex_daily_plan.save_m15_chart("eurusd", rows["15min"], trace["model"], trace["states"], scenario,
                                    trace["preferred_direction"], trace["bases"]["15min"],
                                    trace["decision_policy"], m15_path, locale="en-ZA")
    cutoff = datetime.fromisoformat(trace["cutoff_utc"])
    rendered = forex_daily_calendar_renderer.render_daily_calendar(
        asset="eurusd", symbol=wcb_source.profile_for("eurusd")["symbol"], article_date="2026-09-07",
        events=events, output_dir=output_dir, cutoff=cutoff, locale="en-ZA")
    expected = {h1_name, m15_name, "eurusd-forex-daily-calendar-2026-09-07.webp"}
    actual = {item.name for item in output_dir.glob("*.webp")}
    if actual != expected or len(rendered) != 1:
        raise RuntimeError("recovery renderer image inventory mismatch")
    return {"status": "PASS", "output": str(output_dir), "files": sorted(actual)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-run", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(render(Path(args.historical_run).resolve(), Path(args.output_dir).resolve())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
