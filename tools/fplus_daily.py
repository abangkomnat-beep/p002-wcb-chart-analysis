"""Manual-only command-line boundary for BTCUSD F+.

This module intentionally contains no timer, scheduler, loop, or publishing hook.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
from zoneinfo import ZoneInfo

from tools.fplus_config import ConfigError, validate_config
from tools.fplus_contracts import FPlusRunRequest, sha256_canonical


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "fplus_btc_daily.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run BTCUSD F+ manually on demand")
    parser.add_argument("--mode", choices=("shadow", "local"), required=True)
    parser.add_argument("--shadow-id")
    parser.add_argument("--cutoff-at")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--force-reason")
    parser.add_argument("--work-root", default="work")
    parser.add_argument("--output-root", default="output")
    parser.add_argument("--state-root", default="state")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--asset", default="btcusd", choices=("btcusd",))
    return parser


def _iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_runtime_config() -> dict:
    return validate_config(json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8")))


def _enforce_cli_rollout(parser: argparse.ArgumentParser, mode: str, config: dict) -> None:
    phase = config["rollout"]["phase"]
    if phase == "disabled":
        parser.error("F+ rollout is disabled")
    if mode == "shadow" and phase != "shadow":
        parser.error(f"shadow mode is forbidden in rollout phase {phase}")
    if mode == "local" and phase not in {"local", "cutover"}:
        parser.error(f"local mode is forbidden in rollout phase {phase}")


def parse_request(argv: list[str] | None = None) -> FPlusRunRequest:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.mode == "shadow":
        if not args.shadow_id:
            parser.error("shadow mode requires --shadow-id")
        if args.force or args.force_reason:
            parser.error("--force is available in local mode only")
    elif args.shadow_id:
        parser.error("--shadow-id is valid only in shadow mode")
    if args.force and not (args.force_reason and args.force_reason.strip()):
        parser.error("--force requires --force-reason")
    if args.force_reason and not args.force:
        parser.error("--force-reason requires --force")

    try:
        config = load_runtime_config()
    except (OSError, json.JSONDecodeError, ConfigError) as exc:
        parser.error(f"invalid F+ config: {exc}")
    now = datetime.now(timezone.utc)
    if args.cutoff_at:
        try:
            cutoff = datetime.fromisoformat(args.cutoff_at.replace("Z", "+00:00"))
        except ValueError as exc:
            parser.error(f"invalid --cutoff-at: {exc}")
        if cutoff.tzinfo is None:
            parser.error("--cutoff-at must include timezone")
        cutoff = cutoff.astimezone(timezone.utc)
    else:
        cutoff = now
    trade_date = cutoff.astimezone(ZoneInfo("Asia/Bangkok")).date().isoformat()
    return FPlusRunRequest.from_dict({
        "schema_version": "fplus-run-request-v1",
        "run_id": str(uuid.uuid4()),
        "asset": args.asset,
        "mode": args.mode,
        "requested_at_utc": _iso_utc(now),
        "decision_cutoff_utc": _iso_utc(cutoff),
        "trade_date_bangkok": trade_date,
        "generation_request": "force" if args.force else "normal",
        "force_reason": args.force_reason.strip() if args.force_reason else None,
        "work_root": args.work_root,
        "output_root": args.output_root,
        "state_root": args.state_root,
        "config_fingerprint": sha256_canonical(config),
        "shadow_id": args.shadow_id,
    })


def main(argv: list[str] | None = None, *, runtime_factory=None) -> int:
    """Run the concrete manual pipeline and emit its result envelope."""
    try:
        request = parse_request(argv)
        if runtime_factory is None:
            from tools.fplus_runtime import FPlusRuntime
            runtime = FPlusRuntime()
        else:
            runtime = runtime_factory(request)
        result = runtime.run(request)
    except SystemExit:
        raise
    except Exception as exc:
        result = {"status": "failed_retryable", "reason_codes": [type(exc).__name__],
                  "message": str(exc)}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return {
        "committed": 0, "no_trade_committed": 0, "already_done": 0,
        "shadow_pass": 0, "shadow_already_done": 0, "in_progress": 20,
        "blocked_retryable": 30, "shadow_fail": 40, "failed_retryable": 40,
    }.get(str(result.get("status")), 40)


if __name__ == "__main__":
    raise SystemExit(main())
