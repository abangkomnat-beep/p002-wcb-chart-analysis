"""CP2 gate for the first reversible Unified A–J production change set."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

from tools import intraday_pipeline, intraday_story, run_daily
from tools.hij_unified_adapter import (
    HIJIntradayAdapter,
    HIJProductionRoute,
    STYLE_IDS,
    UNIT_ID,
)
from tools.source_planner import SourcePlanner
from tools.unified_orchestrator import OutputFS, RunContext, StateStore
from tools.unified_registry import RegistryError, RegistryLoader

REPO = Path(__file__).parents[1]
REGISTRY_PATH = REPO / "config" / "article_styles.json"
CUTOFF = "2026-08-20T01:00:00+00:00"
NOW = datetime(2026, 8, 20, 1, 0, tzinfo=timezone.utc)


def _registry(mode: str = "unified") -> dict:
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    raw["execution_units"][UNIT_ID]["migration_mode"] = mode
    return raw


def _route(mode: str = "unified") -> HIJProductionRoute:
    return HIJProductionRoute(RegistryLoader().load(_registry(mode)))


def _round_result(*, ok: bool = True) -> dict:
    return {
        "ok": ok,
        "asset": "xauusd",
        "states": {style_id: "fixture" for style_id in STYLE_IDS},
        "skipped": [],
        "articles": [],
    }


def _tree(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def _rows(count: int, *, minutes: int) -> list[dict]:
    start = datetime(2026, 8, 1)
    values = []
    for index in range(count):
        moment = start + timedelta(minutes=minutes * index)
        base = 100.0 + index
        values.append({
            "date": moment.strftime("%Y-%m-%d"),
            "at": moment.strftime("%Y-%m-%d %H:%M:%S"),
            "open": base, "high": base + 0.5,
            "low": base - 0.5, "close": base + 0.5,
        })
    return values


def _frozen_fetcher(trace: list[str]):
    rows = {"30min": _rows(300, minutes=30), "15min": _rows(601, minutes=15)}

    def fetch(asset, *, timeframe, outputsize):
        trace.append(f"{asset}:{timeframe}:{outputsize}")
        payload = rows[timeframe]
        return ({"asset": asset, "timeframe": timeframe, "count": len(payload)},
                [dict(item) for item in payload], f"fixture:{timeframe}")

    return fetch


def test_registry_selects_one_hij_unit_and_preserves_policy():
    route = HIJProductionRoute.load()
    assert route.migration_mode == "unified"
    unit = route.registry.execution_units[UNIT_ID]
    assert unit.execute_once_per_asset is True
    assert unit.rollback_mode == "legacy"
    assert unit.members == STYLE_IDS
    entries = [route.registry.styles[item] for item in STYLE_IDS]
    assert [entry.letter for entry in entries] == ["H", "I", "J"]
    assert all(entry.production for entry in entries)
    assert all(entry.assets == ("btcusd", "xauusd", "usdjpy") for entry in entries)
    assert [entry.timeframes for entry in entries] == [
        ("30min",), ("15min",), ("30min", "15min"),
    ]


def test_unified_route_calls_legacy_group_once_with_exact_production_arguments(tmp_path):
    raw = _round_result()
    with mock.patch.object(intraday_pipeline, "run_round", return_value=raw) as runner:
        result = _route("unified").run_round(
            asset="xauusd", publish_root=tmp_path / "output", cutoff_at=CUTOFF,
        )
    assert result is raw
    runner.assert_called_once_with(
        asset="xauusd", publish_root=tmp_path / "output", cutoff_at=CUTOFF,
    )


def test_rollback_toggle_uses_direct_legacy_route_and_is_reversible(tmp_path):
    raw = _round_result()
    with mock.patch.object(intraday_pipeline, "run_round", return_value=raw) as runner, \
            mock.patch("tools.hij_unified_adapter.UnifiedStyleOrchestrator.execute") as execute:
        result = _route("legacy").run_round(
            asset="btcusd", publish_root=tmp_path / "output", cutoff_at=CUTOFF,
        )
    assert result is raw
    execute.assert_not_called()
    runner.assert_called_once_with(
        asset="btcusd", publish_root=tmp_path / "output", cutoff_at=CUTOFF,
    )


def test_shadow_or_invalid_route_fails_before_legacy_side_effects(tmp_path):
    with mock.patch.object(intraday_pipeline, "run_round") as runner:
        with pytest.raises(RegistryError, match="refuses"):
            _route("shadow").run_round(
                asset="xauusd", publish_root=tmp_path / "output", cutoff_at=CUTOFF,
            )
    runner.assert_not_called()

    invalid = _registry()
    invalid["execution_units"][UNIT_ID]["members"] = list(reversed(STYLE_IDS))
    invalid_path = tmp_path / "invalid-registry.json"
    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(RegistryError, match="members must be"):
        HIJProductionRoute.load(invalid_path)


def test_adapter_keeps_child_failures_and_exception_message_observable(tmp_path):
    context = RunContext(
        "r", CUTOFF, assets=("xauusd",), mode="unified", no_publish=False,
        output_root=tmp_path / "output", state_root=tmp_path / "state",
    )
    plan = SourcePlanner().plan(
        execution_unit=UNIT_ID, asset="xauusd", requests=(),
    )
    raw = {
        **_round_result(ok=False),
        "articles": [{"style": STYLE_IDS[0], "ok": False, "published": False}],
        "skipped": [{"style": STYLE_IDS[1], "reason": "fixture skip"}],
    }
    with mock.patch.object(intraday_pipeline, "run_round", return_value=raw):
        envelope = HIJIntradayAdapter(
            publish_root=tmp_path / "output", cutoff_at=CUTOFF,
        )(context, "xauusd", plan, OutputFS(tmp_path / "audit"), StateStore(tmp_path / "state"))
    assert envelope.status == "FAIL"
    assert [item.status for item in envelope.children] == ["FAIL", "SKIP", "SKIP"]
    assert envelope.exit_code == 1

    with mock.patch.object(intraday_pipeline, "run_round", side_effect=RuntimeError("fixture down")):
        envelope = HIJIntradayAdapter(
            publish_root=tmp_path / "output", cutoff_at=CUTOFF,
        )(context, "xauusd", plan, OutputFS(tmp_path / "audit"), StateStore(tmp_path / "state"))
    assert envelope.status == "FAIL"
    assert envelope.findings[0].message == "fixture down"


def test_actual_legacy_unified_parity_state_io_api_order_and_production_safety(tmp_path):
    production_output = REPO.parent / "output"
    production_state = REPO / "state"
    safety_before = (_tree(production_output), _tree(production_state))
    manifests = {}

    for mode in ("legacy", "unified"):
        trace: list[str] = []
        output_root = tmp_path / mode / "output"
        state_root = tmp_path / mode / "state"
        with mock.patch.object(intraday_story, "read_state",
                               wraps=intraday_story.read_state) as reads, \
                mock.patch.object(intraday_story, "write_state",
                                  wraps=intraday_story.write_state) as writes:
            result = _route(mode).run_round(
                asset="btcusd", publish_root=output_root, cutoff_at=CUTOFF,
                _runner_kwargs={
                    "fetcher": _frozen_fetcher(trace), "now": NOW,
                    "state_dir": state_root, "dry_run": True,
                },
            )
        # Legacy performs one state read while building each story and one
        # published-state read while selecting it; migration must not add any.
        assert reads.call_count == 6
        assert writes.call_count == 3
        assert trace == ["btcusd:30min:500", "btcusd:15min:500"]
        manifests[mode] = {
            "ok": result["ok"],
            "states": result["states"],
            "skipped": result["skipped"],
            "decision": result["decision"],
            "articles": result["articles"],
            "published": result["published"],
            "state": _tree(state_root),
            "output": _tree(output_root),
            "api_trace": trace,
        }

    assert manifests["legacy"] == manifests["unified"]
    assert safety_before == (_tree(production_output), _tree(production_state))


def test_run_daily_registry_failure_stops_before_any_pipeline_side_effect():
    with mock.patch.object(HIJProductionRoute, "load",
                           side_effect=RegistryError("fixture invalid")), \
            mock.patch.object(run_daily.build_daily_package, "run_internal_line") as internal, \
            mock.patch.object(run_daily.build_daily_package, "run_public_line") as public, \
            mock.patch.object(run_daily.chart_story_pipeline, "run") as style_d:
        assert run_daily.main(["--asset", "xauusd"]) == 1
    internal.assert_not_called()
    public.assert_not_called()
    style_d.assert_not_called()


def test_run_daily_hij_failure_isolated_per_asset_and_later_asset_still_runs():
    route = mock.Mock()
    route.run_round.side_effect = [
        RuntimeError("btcusd fixture failure"),
        {**_round_result(), "asset": "xauusd"},
    ]
    style_d = {"status": "pass", "directory": "d", "findings": []}
    style_e = {"status": "pass", "directory": "e", "char_count": 1,
               "findings": []}
    with mock.patch.object(HIJProductionRoute, "load", return_value=route), \
            mock.patch.object(run_daily.intraday_story, "production_assets",
                              return_value={"btcusd", "xauusd"}), \
            mock.patch.object(run_daily.build_daily_package, "run_internal_line",
                              return_value=0), \
            mock.patch.object(run_daily.build_daily_package, "run_public_line",
                              return_value=0), \
            mock.patch.object(run_daily.chart_story_pipeline, "run",
                              return_value=style_d), \
            mock.patch.object(run_daily.chart_indicator_pipeline, "run",
                              return_value=style_e), \
            mock.patch.object(run_daily.brief_pipeline, "run_pair", return_value=[]), \
            mock.patch.object(run_daily.publish_selection, "select",
                              return_value={"status": "ready", "article": "x"}), \
            mock.patch.object(run_daily.frontmatter_guard, "main", return_value=0):
        code = run_daily.main(["--asset", "btcusd", "--asset", "xauusd"])
    assert code == 1
    assert [call.kwargs["asset"] for call in route.run_round.call_args_list] == [
        "btcusd", "xauusd",
    ]
