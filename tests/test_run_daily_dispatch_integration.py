from unittest.mock import patch

from tools import run_daily


def test_normal_entrypoint_reports_held_localization_as_partial_after_source_path(capsys):
    calls = []

    def dispatch(*args, **kwargs):
        calls.append((args, kwargs))
        return {"status": "HOLD_NO_ADMITTED_COUNTRIES"}

    with patch.object(run_daily.normal_localization_orchestrator, "run", side_effect=dispatch), \
         patch.object(run_daily, "scheduled_lane_plan", return_value={"E": ("xauusd",), "M": ("btcusd",), "L": ("gbpusd", "usdcad")}), \
         patch.object(run_daily, "run_style_l", return_value=(0, {})), \
         patch.object(run_daily, "run_style_e", return_value=(0, {})), \
         patch.object(run_daily, "run_style_m", return_value=(0, {})), \
         patch.object(run_daily.build_daily_package, "run_internal_line", return_value=0), \
         patch.object(run_daily.country_first_output, "migrate_day", return_value={"records": []}), \
         patch.object(run_daily.country_first_output, "repair_canonical_day", return_value={"records": []}), \
         patch.object(run_daily.localization_queue, "write_receipt", return_value={"selected": [], "held": []}), \
         patch.object(run_daily.frontmatter_guard, "main", return_value=0), \
         patch.object(run_daily.publish_selection, "purge_forbidden_output_files", return_value=[]), \
         patch.object(run_daily, "datetime") as clock:
        from datetime import datetime, timezone
        clock.now.return_value = datetime(2026, 9, 10, 3, tzinfo=timezone.utc)
        assert run_daily.main(["--skip-selection", "--skip-guard"]) == 2

    assert calls and calls[0][0][1] == "2026-09-10"
    assert calls[0][1] == {"dry_run": False}
    assert "สะดุด/ค้าง" in capsys.readouterr().out
