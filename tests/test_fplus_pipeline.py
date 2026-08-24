"""Standalone orchestration, shadow isolation and publishing-boundary contracts."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from fixtures.fplus.contract_support import load_json, require_module


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISHING_POLICY_SHA256 = "df0bd585a1134677e26eef918a7e907708d0f13a470e5b32d21186dfb402c200"
PROTECTED_SHA256 = {
    "docs/QC-GATES.md": "0b15921ba8b9572553a3e5ad8511b6c13624c359305a9f0d68cbb08295f0e377",
    "docs/WCB-DAILY-OUTPUT-CONTRACT.md": "e2ce6bfef99b520fb452fe74e9d53ca65fd5a5ac55e7d79d19bc77e6e2c6c4a5",
    "tests/test_article_builder.py": "8599c37a5034150ace0f5c0c7b81dafbd5e2dd1d141efff223fe758d2398263a",
    "tests/test_run_daily.py": "7547c14b6a2c1134f2c08ecce257ae4ed7a7c0b692ba07d39e35d4cca785c286",
    "tools/build_daily_package.py": "83a5605820579dfdd7a635e77cf484e4e704903e69d01e632fb450600706b6be",
    "tools/run_daily.py": "1d72f410a7437077fffa5c18f2b3317d8a3cf482ff0848cbe0b8f33167bdde46",
}


class RecordingAdapters:
    """Builder-facing dependency port used to prove orchestration side effects."""
    def __init__(self, *, acquire_status="claimed", data_status="pass",
                 news_status="pass", selection="J"):
        self.calls: list[str] = []
        self.acquire_status = acquire_status
        self.data_status = data_status
        self.news_status = news_status
        self.selection = selection

    def acquire_production(self, request):
        self.calls.append("acquire_production")
        return {"status": self.acquire_status, "generation": 1,
                "paths": ["old.md", "old.webp"], "hashes": {}}

    def acquire_shadow(self, request):
        self.calls.append("acquire_shadow")
        return {"status": "claimed", "generation": 1}

    def fetch_snapshot(self, request):
        self.calls.append("fetch_snapshot")
        return {"snapshot_id": "snapshot", "calendar": {"events": []}}

    def evaluate_data(self, snapshot, config):
        self.calls.append("evaluate_data")
        return {"price_data_status": self.data_status,
                "reason_codes": [] if self.data_status == "pass" else ["STALE_15MIN"]}

    def evaluate_news(self, snapshot, request, config):
        self.calls.append("evaluate_news")
        return {"status": self.news_status,
                "reason_codes": [] if self.news_status == "pass" else ["NEWS_GATE_UNPROVEN"]}

    def evaluate_candidates(self, snapshot, config):
        self.calls.append("evaluate_candidates")
        return [{"candidate": name, "eligible": name == self.selection}
                for name in ("J", "I", "E_LOGIC", "F")]

    def route(self, candidate_decisions, gate_report):
        self.calls.append("route")
        selected = self.selection if gate_report["news"]["status"] == "pass" else "NO_TRADE"
        return load_json("selected_no_trade.json" if selected == "NO_TRADE" else "selected_trade.json")

    def stage_artifacts(self, selected_plan, request, config):
        self.calls.append("stage_artifacts")
        return {"staging_dir": "stage", "manifest": {"files": ["btcusd.md", "chart.webp"]}}

    def promote(self, staged, request, config):
        self.calls.append("promote")
        return {"paths": ["btcusd.md", "chart.webp"], "hashes": {"md": "a", "webp": "b"}}

    def commit_production(self, request, promoted, selected_plan):
        self.calls.append("commit_production")
        return {"status": "committed"}

    def mark_retryable(self, request, gate_report):
        self.calls.append("mark_retryable")

    def record_shadow(self, request, selected_plan, staged):
        self.calls.append("record_shadow")
        return {"status": "shadow_pass", "selection": selected_plan["selection"]}


def request(mode="shadow") -> dict:
    return {
        "run_id": "run-1", "asset": "btcusd", "mode": mode,
        "shadow_id": "S01" if mode == "shadow" else None,
        "decision_cutoff_utc": "2026-08-24T02:00:00Z",
        "trade_date_bangkok": "2026-08-24", "generation_request": "normal",
    }


def config_for(mode: str) -> dict:
    config = load_json("config_valid.json")
    config["rollout"]["phase"] = "shadow" if mode == "shadow" else "local"
    return config


def test_local_already_done_returns_before_any_network_or_market_work():
    pipeline = require_module("tools.fplus_pipeline")
    adapters = RecordingAdapters(acquire_status="already_done")
    result = pipeline.run_pipeline(request("local"), config=config_for("local"),
                                   adapters=adapters)
    assert result["status"] == "already_done"
    assert adapters.calls == ["acquire_production"]


def test_price_data_block_is_retryable_and_never_builds_artifacts():
    pipeline = require_module("tools.fplus_pipeline")
    adapters = RecordingAdapters(data_status="blocked_retryable")
    result = pipeline.run_pipeline(request("local"), config=config_for("local"),
                                   adapters=adapters)
    assert result["status"] == "blocked_retryable"
    assert adapters.calls == ["acquire_production", "fetch_snapshot", "evaluate_data", "mark_retryable"]
    assert "stage_artifacts" not in adapters.calls
    assert "commit_production" not in adapters.calls


def test_news_unproven_commits_one_no_trade_job_in_local_mode():
    pipeline = require_module("tools.fplus_pipeline")
    adapters = RecordingAdapters(news_status="unproven")
    result = pipeline.run_pipeline(request("local"), config=config_for("local"),
                                   adapters=adapters)
    assert result["status"] == "no_trade_committed"
    assert result["selection"] == "NO_TRADE"
    assert adapters.calls[-3:] == ["stage_artifacts", "promote", "commit_production"]


def test_shadow_uses_separate_guard_and_never_promotes_or_commits_production():
    pipeline = require_module("tools.fplus_pipeline")
    adapters = RecordingAdapters(selection="I")
    result = pipeline.run_pipeline(request("shadow"), config=config_for("shadow"),
                                   adapters=adapters)
    assert result["status"] == "shadow_pass"
    assert adapters.calls[0] == "acquire_shadow"
    assert "acquire_production" not in adapters.calls
    assert "promote" not in adapters.calls
    assert "commit_production" not in adapters.calls
    assert adapters.calls[-1] == "record_shadow"


def test_rollout_shadow_rejects_local_before_lock_or_network():
    pipeline = require_module("tools.fplus_pipeline")
    adapters = RecordingAdapters()
    with pytest.raises(pipeline.PipelineContractError, match="rollout|phase|shadow|local"):
        pipeline.run_pipeline(request("local"), config=config_for("shadow"), adapters=adapters)
    assert adapters.calls == []


def test_pipeline_requires_shadow_id_even_for_direct_callers():
    pipeline = require_module("tools.fplus_pipeline")
    adapters = RecordingAdapters()
    invalid = request("shadow")
    invalid["shadow_id"] = None
    with pytest.raises(pipeline.PipelineContractError, match="shadow|S01|S02|S03"):
        pipeline.run_pipeline(invalid, config=config_for("shadow"), adapters=adapters)
    assert adapters.calls == []


def test_publishing_policy_and_protected_collision_set_remain_byte_identical():
    policy = REPO_ROOT / "config" / "publishing_policy.json"
    assert hashlib.sha256(policy.read_bytes()).hexdigest() == PUBLISHING_POLICY_SHA256
    for relative, expected in PROTECTED_SHA256.items():
        assert hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest() == expected, relative


def test_publish_selection_has_no_fplus_route_or_folder():
    source = (REPO_ROOT / "tools" / "publish_selection.py").read_text(encoding="utf-8").lower()
    assert "fplus" not in source
    assert "f+-btcusd-แผนระยะสั้น" not in source


def test_fplus_modules_do_not_import_publishing_or_legacy_writers():
    forbidden = {
        "tools.publish_selection", "tools.chart_indicator_writer",
        "tools.intraday_trend_writer", "tools.intraday_breakout_writer",
        "tools.intraday_pullback_writer",
    }
    for path in sorted((REPO_ROOT / "tools").glob("fplus_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.add(module)
                imports.update(f"{module}.{alias.name}" for alias in node.names)
        assert not (imports & forbidden), f"{path.name} crosses publishing/legacy writer boundary"


def test_no_fplus_scheduler_or_automation_artifact_exists():
    forbidden_suffixes = {".yml", ".yaml", ".xml", ".bat", ".ps1"}
    artifacts = [path for path in REPO_ROOT.rglob("*fplus*")
                 if path.is_file() and path.suffix.lower() in forbidden_suffixes]
    assert artifacts == []


def test_shadow_ids_are_manual_s01_to_s03_only():
    pipeline = require_module("tools.fplus_pipeline")
    for shadow_id in ("S01", "S02", "S03"):
        validated = pipeline.validate_shadow_id(shadow_id)
        assert validated == shadow_id
    for invalid in ("", "S00", "S04", "AUTO", "09:05"):
        try:
            pipeline.validate_shadow_id(invalid)
        except pipeline.PipelineContractError:
            pass
        else:
            raise AssertionError(f"shadow id must be rejected: {invalid}")
