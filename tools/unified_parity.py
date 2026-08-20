"""Frozen, temp-root shadow parity harness for Unified A–J.

The harness exercises injected legacy-shaped adapters; it never imports the
production CLI and never talks to a provider.  Expected values are loaded from
``tests/fixtures/unified/parity_expected.json`` and are compared, not created,
by a test run.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from .result_envelope import ResultEnvelope
from .source_planner import ApiTrace, SourcePlanner, SourceRequest, TraceRecorder
from .unified_orchestrator import (
    OutputFS,
    PublishGuard,
    RunContext,
    SelectionPort,
    StateStore,
    UnifiedStyleOrchestrator,
)

UNIT_ORDER = (
    "INTERNAL_EVIDENCE_123", "ABC_PUBLIC", "D_CHART_STORY",
    "E_INDICATOR", "FG_BRIEF", "HIJ_INTRADAY",
)
UNIT_MEMBERS = {
    "INTERNAL_EVIDENCE_123": (),
    "ABC_PUBLIC": ("style_a", "style_b", "style_c"),
    "D_CHART_STORY": ("style_d",),
    "E_INDICATOR": ("style_e",),
    "FG_BRIEF": ("style_f", "style_g"),
    "HIJ_INTRADAY": ("style_h", "style_i", "style_j"),
}
LETTERS = {f"style_{letter.lower()}": letter for letter in "ABCDEFGHIJ"}


@dataclass(frozen=True)
class ParityScenario:
    scenario_id: str
    name: str
    asset: str = "xauusd"
    expected_exit: int = 0
    failing_unit: str | None = None
    hij_status: str = "PASS"
    hij_timeframes: tuple[str, ...] = ("15min", "30min")
    state_transitions: tuple[str, ...] = ()
    selection_guard: bool = False


@dataclass
class ParityEvidence:
    scenario_id: str
    status: str
    output_tree: list[str]
    artifact_hashes: dict[str, str]
    content_hash: str
    state_hash: str | None
    source_trace: list[dict[str, Any]]
    exit_code: int
    selection_calls: int
    guard_calls: int
    state_reads: int
    state_writes: int
    transitions: list[dict[str, Any]] = field(default_factory=list)
    unit_statuses: dict[str, str] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_scenarios() -> tuple[ParityScenario, ...]:
    return (
        ParityScenario("G01", "morning preview"),
        ParityScenario("G02", "preview selection"),
        ParityScenario("G03", "confirm"),
        ParityScenario("G04", "repeat confirm"),
        ParityScenario("G05", "daily default"),
        ParityScenario("G06", "publish internal guard"),
        ParityScenario("G07", "internal line"),
        ParityScenario("G08", "skip flags"),
        ParityScenario("G09", "D chart story"),
        ParityScenario("G10", "E indicator"),
        ParityScenario("G11", "F only"),
        ParityScenario("G12", "G plus F"),
        ParityScenario("G13", "HIJ allowlist", hij_status="SKIP", hij_timeframes=("15min",)),
        ParityScenario("G14", "HIJ state transition", state_transitions=("TREND", "PULLBACK")),
        ParityScenario("G15", "failure isolation", expected_exit=1, failing_unit="D_CHART_STORY"),
        ParityScenario("G16", "selection and guard order", selection_guard=True),
    )


def frozen_registry() -> dict[str, Any]:
    styles: dict[str, Any] = {}
    for order, (style_id, letter) in enumerate(LETTERS.items()):
        unit = next(unit_id for unit_id, members in UNIT_MEMBERS.items() if style_id in members)
        adapter = {
            "ABC_PUBLIC": "abc_public", "D_CHART_STORY": "d_chart_story",
            "E_INDICATOR": "e_indicator", "FG_BRIEF": "fg_brief",
            "HIJ_INTRADAY": "hij_intraday",
        }[unit]
        styles[style_id] = {
            "id": style_id, "letter": letter, "name": f"Style {letter}",
            "folder": f"{letter}-frozen", "execution_unit": unit,
            "adapter": adapter, "order": order, "assets": ["xauusd"],
            "timeframes": ["1d"], "trigger": "daily", "production": False,
            "migration_mode": "legacy", "publish_eligible": True,
        }
    units = {
        unit_id: {
            "id": unit_id, "members": list(members), "order": order,
            "migration_mode": "legacy", "rollback_mode": "legacy",
            "execute_once_per_asset": True,
        }
        for order, (unit_id, members) in enumerate(UNIT_MEMBERS.items())
    }
    return {"schema": "article-styles-v2", "styles": styles, "execution_units": units}


def _hash_json(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


class ShadowParityHarness:
    def __init__(self, *, fixture_root: Path | None = None) -> None:
        self.fixture_root = fixture_root or Path(__file__).parents[1] / "tests" / "fixtures" / "unified"

    def _plans(self, scenario: ParityScenario) -> tuple[dict[str, Any], ApiTrace]:
        planner = SourcePlanner()
        trace = ApiTrace()
        plans: dict[str, Any] = {}
        for unit in UNIT_ORDER:
            timeframes = scenario.hij_timeframes if unit == "HIJ_INTRADAY" else {
                "D_CHART_STORY": ("1d",), "E_INDICATOR": ("1h",),
                "FG_BRIEF": ("calendar",),
            }.get(unit, ("1d",))
            requests = [SourceRequest("fixture", scenario.asset, timeframe,
                                      f"{scenario.scenario_id}:{unit}") for timeframe in timeframes]
            plan = planner.plan(execution_unit=unit, asset=scenario.asset, requests=requests)
            plans[unit] = plan
            recorder = TraceRecorder(trace)
            for request in plan.ordered_requests:
                recorder.fetch(request, lambda _request: {"frozen": True})
        return plans, trace

    def run(self, scenario: ParityScenario) -> ParityEvidence:
        with TemporaryDirectory(prefix=f"p002-{scenario.scenario_id.lower()}-") as root:
            root_path = Path(root)
            context = RunContext(
                run_id=f"shadow-{scenario.scenario_id}", cutoff_at="2026-08-20T00:00:00Z",
                assets=(scenario.asset,), output_root=root_path / "output",
                work_root=root_path / "work", state_root=root_path / "state",
                mode="shadow", no_publish=True,
            )
            output = OutputFS(context.output_root)
            state = StateStore(context.state_root)
            selection = SelectionPort(selected=(scenario.asset,))
            guard = PublishGuard()
            plans, trace = self._plans(scenario)
            transitions: list[dict[str, Any]] = []

            def make_adapter(unit: str):
                def adapter(_context, asset, _plan, output_fs, state_store):
                    if unit == scenario.failing_unit:
                        raise RuntimeError(f"frozen failure {scenario.scenario_id}:{unit}")
                    status = "SKIP" if unit == "HIJ_INTRADAY" and scenario.hij_status == "SKIP" else "PASS"
                    if unit == "HIJ_INTRADAY" and scenario.state_transitions:
                        key = f"{asset}/HIJ"
                        for value in scenario.state_transitions:
                            previous = state_store.read(key, {"state": "NONE"})
                            if previous.get("state") != value:
                                state_store.write(key, {"state": value, "scenario": scenario.scenario_id})
                            transitions.append({"from": previous.get("state"), "to": value})
                    payload = {
                        "scenario": scenario.scenario_id, "unit": unit,
                        "asset": asset, "status": status,
                        "children": [LETTERS[style] for style in UNIT_MEMBERS[unit]],
                    }
                    output_fs.write_json(f"artifacts/{unit}.json", payload)
                    return {"status": status, "children": [
                        {"style_id": LETTERS[style], "status": status}
                        for style in UNIT_MEMBERS[unit]
                    ]}
                return adapter

            orchestrator = UnifiedStyleOrchestrator(
                {unit: make_adapter(unit) for unit in UNIT_ORDER}
            )
            results = orchestrator.execute(
                context, frozen_registry(), plans, output_fs=output, state_store=state
            )
            if scenario.selection_guard:
                selection.select((scenario.asset,))
                guard.check(no_publish=True)
                guard.check(no_publish=True)
            snapshot = output.snapshot()
            output_tree = sorted(snapshot)
            content_hash = _hash_json({
                "scenario": scenario.scenario_id,
                "results": [
                    {"unit": result.execution_unit, "status": result.aggregate_status,
                     "children": [child.status for child in result.children]}
                    for result in results
                ],
            })
            state_files = sorted(state.root.rglob("*.json")) if state.root.exists() else []
            state_hash = _hash_json({str(path.relative_to(state.root)): json.loads(path.read_text(encoding="utf-8"))
                                     for path in state_files}) if state_files else None
            overall = "FAIL" if any(result.exit_code for result in results) else "PASS"
            return ParityEvidence(
                scenario_id=scenario.scenario_id, status=overall,
                output_tree=output_tree,
                artifact_hashes=snapshot, content_hash=content_hash,
                state_hash=state_hash,
                source_trace=[asdict(entry) for entry in trace.entries],
                exit_code=1 if overall == "FAIL" else 0,
                selection_calls=selection.calls, guard_calls=guard.calls,
                state_reads=state.read_count, state_writes=state.write_count,
                transitions=transitions,
                unit_statuses={result.execution_unit: result.aggregate_status for result in results},
            )

    def run_all(self, *, evidence_root: Path | None = None) -> list[ParityEvidence]:
        evidence = [self.run(scenario) for scenario in default_scenarios()]
        if evidence_root is not None:
            root = Path(evidence_root)
            root.mkdir(parents=True, exist_ok=True)
            for item in evidence:
                (root / f"{item.scenario_id}.json").write_text(
                    json.dumps(item.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        return evidence

    def verify(self, evidence: Sequence[ParityEvidence], expected: Mapping[str, Any]) -> list[str]:
        findings: list[str] = []
        by_id = {item.scenario_id: item for item in evidence}
        for scenario in default_scenarios():
            actual = by_id.get(scenario.scenario_id)
            wanted = expected.get(scenario.scenario_id)
            if actual is None or wanted is None:
                findings.append(f"{scenario.scenario_id}: missing evidence/expectation")
                continue
            checks = {
                "status": actual.status,
                "output_tree": actual.output_tree,
                "content_hash": actual.content_hash,
                "state_hash": actual.state_hash,
                "exit_code": actual.exit_code,
                "selection_calls": actual.selection_calls,
                "guard_calls": actual.guard_calls,
                "state_reads": actual.state_reads,
                "state_writes": actual.state_writes,
                "transitions": actual.transitions,
                "unit_statuses": actual.unit_statuses,
                "output_files": len(actual.output_tree),
                "trace_count": len(actual.source_trace),
            }
            for key, actual_value in checks.items():
                if key in wanted and actual_value != wanted[key]:
                    findings.append(f"{scenario.scenario_id}: {key} mismatch")
            if "source_trace" in wanted and actual.source_trace != wanted["source_trace"]:
                findings.append(f"{scenario.scenario_id}: source_trace mismatch")
            if "artifact_hashes" in wanted and actual.artifact_hashes != wanted["artifact_hashes"]:
                findings.append(f"{scenario.scenario_id}: artifact_hashes mismatch")
        return findings


def load_expected(path: Path | None = None) -> dict[str, Any]:
    fixture = path or Path(__file__).parents[1] / "tests" / "fixtures" / "unified" / "parity_expected.json"
    return json.loads(fixture.read_text(encoding="utf-8"))


__all__ = ["ParityEvidence", "ParityScenario", "ShadowParityHarness", "default_scenarios", "frozen_registry", "load_expected"]
