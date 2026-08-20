"""Declarative source planning and injectable API trace.

`SourcePlanner` only describes requests.  The trace recorder is an explicit
test seam; it never opens a socket, retries, deduplicates, caches, or fetches.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Mapping


@dataclass(frozen=True)
class SourceRequest:
    provider: str
    asset: str
    timeframe: str
    request_role: str
    endpoint_kind: str = "series"
    required_by: tuple[str, ...] = ()
    ordinal: int = 0


@dataclass(frozen=True)
class SourcePlan:
    schema_version: str
    execution_unit: str
    asset: str
    ordered_requests: tuple[SourceRequest, ...]
    dependency_edges: tuple[tuple[str, str], ...] = ()
    api_parity_key: str = ""

    @property
    def count(self) -> int:
        return len(self.ordered_requests)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "execution_unit": self.execution_unit,
            "asset": self.asset,
            "ordered_requests": [asdict(item) for item in self.ordered_requests],
            "dependency_edges": [list(edge) for edge in self.dependency_edges],
            "api_parity_key": self.api_parity_key,
        }


class SourcePlanner:
    """Build a request declaration from explicit values or registry metadata."""

    def plan(self, *, execution_unit: str, asset: str,
             requests: Iterable[Mapping[str, Any] | SourceRequest],
             dependency_edges: Iterable[tuple[str, str]] = ()) -> SourcePlan:
        ordered: list[SourceRequest] = []
        for ordinal, item in enumerate(requests):
            if isinstance(item, SourceRequest):
                request = item
                if request.ordinal != ordinal:
                    request = SourceRequest(**{**asdict(request), "ordinal": ordinal})
            else:
                request = SourceRequest(
                    provider=str(item["provider"]), asset=str(item.get("asset", asset)),
                    timeframe=str(item["timeframe"]), request_role=str(item["request_role"]),
                    endpoint_kind=str(item.get("endpoint_kind", "series")),
                    required_by=tuple(item.get("required_by", ())), ordinal=ordinal,
                )
            if request.asset != asset:
                raise ValueError("source request asset differs from plan asset")
            ordered.append(request)
        key = "|".join(f"{r.provider}:{r.asset}:{r.timeframe}:{r.request_role}:{r.ordinal}" for r in ordered)
        return SourcePlan("source-plan-v1", execution_unit, asset, tuple(ordered),
                          tuple(dependency_edges), key)


@dataclass(frozen=True)
class TraceEntry:
    provider: str
    asset: str
    timeframe: str
    request_role: str
    ordinal: int


@dataclass
class ApiTrace:
    entries: list[TraceEntry] = field(default_factory=list)

    def record(self, *, provider: str, asset: str, timeframe: str,
               request_role: str) -> TraceEntry:
        entry = TraceEntry(provider, asset, timeframe, request_role, len(self.entries))
        self.entries.append(entry)
        return entry

    @property
    def count(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {"count": self.count, "entries": [asdict(item) for item in self.entries]}

    def parity_key(self) -> str:
        return "|".join(f"{e.provider}:{e.asset}:{e.timeframe}:{e.request_role}:{e.ordinal}" for e in self.entries)

    def assert_matches(self, plan: SourcePlan) -> None:
        expected = [
            (request.provider, request.asset, request.timeframe, request.request_role, request.ordinal)
            for request in plan.ordered_requests
        ]
        actual = [(entry.provider, entry.asset, entry.timeframe, entry.request_role, entry.ordinal)
                  for entry in self.entries]
        if actual != expected:
            raise AssertionError(f"API trace differs from declarative plan: expected={expected!r} actual={actual!r}")


class TraceRecorder:
    """Injected fetch seam.  The supplied callback is the only data source."""

    def __init__(self, trace: ApiTrace | None = None) -> None:
        self.trace = trace or ApiTrace()

    def fetch(self, request: SourceRequest, provider: Callable[[SourceRequest], Any]) -> Any:
        self.trace.record(provider=request.provider, asset=request.asset,
                          timeframe=request.timeframe, request_role=request.request_role)
        return provider(request)


__all__ = ["ApiTrace", "SourcePlan", "SourcePlanner", "SourceRequest", "TraceEntry", "TraceRecorder"]
