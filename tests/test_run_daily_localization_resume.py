import json
from pathlib import Path
from unittest.mock import patch

from tools import run_daily


def test_resume_calls_dispatch_before_any_source_or_output_producer(capsys):
    with patch.object(run_daily.normal_localization_orchestrator, "run", return_value={"status": "WAITING_WRITER_OR_REVIEW"}) as dispatch, \
         patch.object(run_daily, "scheduled_lane_plan", side_effect=AssertionError("source planner called")), \
         patch.object(run_daily.country_first_output, "migrate_day", side_effect=AssertionError("output migration called")):
        assert run_daily.main(["--resume-localization", "2026-09-10", "--dry-run"]) == 2
        assert dispatch.call_args.args[1] == "2026-09-10"
        assert dispatch.call_args.kwargs == {"dry_run": True}
        assert json.loads(capsys.readouterr().out)["status"] == "WAITING_WRITER_OR_REVIEW"


def test_resume_reports_source_gate_error_without_starting_normal_run(capsys):
    with patch.object(run_daily.normal_localization_orchestrator, "run", side_effect=run_daily.normal_localization_orchestrator.DispatchError("stale source")), \
         patch.object(run_daily, "scheduled_lane_plan", side_effect=AssertionError("source planner called")):
        assert run_daily.main(["--resume-localization", "2026-09-10"]) == 1
        assert json.loads(capsys.readouterr().out) == {"status": "HOLD", "error": "stale source"}


def test_resume_cli_forwards_explicit_recovery_bundle_from_temporary_root(tmp_path, capsys):
    runtime_file = tmp_path / "Repo/tools/run_daily.py"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text("# temporary CLI root\n", encoding="utf-8")
    bundle = tmp_path / "work/localization/10-09-2026/recovery/E-XAUUSD/recovery-bundle.json"
    bundle.parent.mkdir(parents=True)
    bundle.write_text("{}", encoding="utf-8")
    with patch.object(run_daily, "__file__", str(runtime_file)), \
         patch.object(run_daily.normal_localization_orchestrator, "run",
                      return_value={"status": "HOLD_NO_ADMITTED_COUNTRIES"}) as dispatch, \
         patch.object(run_daily, "scheduled_lane_plan", side_effect=AssertionError("source planner called")):
        assert run_daily.main(["--resume-localization", "2026-09-10", "--dry-run",
                               "--recovery-bundle", str(bundle)]) == 2
    assert dispatch.call_args.args == (tmp_path, "2026-09-10")
    assert dispatch.call_args.kwargs == {"dry_run": True, "recovery_bundle_path": Path(bundle)}
    assert json.loads(capsys.readouterr().out)["status"] == "HOLD_NO_ADMITTED_COUNTRIES"
