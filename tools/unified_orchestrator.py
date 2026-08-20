"""Inactive/shadow control-plane seams for Unified A–J.

Nothing in this module is imported by ``run_daily``.  A caller must opt into
``mode='shadow'`` explicitly and inject temporary roots and adapter callbacks.
The default mode is ``legacy`` and returns a transparent skip envelope.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import gettempdir
from typing import Any, Callable, Mapping, Sequence

from .result_envelope import ArtifactRef, Finding, ResultEnvelope, sha256_file
from .source_planner import SourcePlan
from .unified_registry import ArticleStylesRegistry, RegistryLoader


class SideEffectDenied(PermissionError):
    """A shadow execution attempted a forbidden publish or root escape."""


@dataclass(frozen=True)
class RunContext:
    run_id: str
    cutoff_at: str
    line: str = "both"
    assets: tuple[str, ...] = ()
    output_root: Path = field(default_factory=lambda: Path(gettempdir()) / "p002-unified-output")
    work_root: Path = field(default_factory=lambda: Path(gettempdir()) / "p002-unified-work")
    state_root: Path = field(default_factory=lambda: Path(gettempdir()) / "p002-unified-state")
    mode: str = "legacy"
    no_publish: bool = True
    flags: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in {"legacy", "shadow", "unified"}:
            raise ValueError(f"unsupported pipeline mode: {self.mode}")
        if self.mode != "legacy" and not self.no_publish:
            raise SideEffectDenied("shadow foundation requires no_publish=True")
        for name in ("output_root", "work_root", "state_root"):
            value = Path(getattr(self, name))
            object.__setattr__(self, name, value)


class OutputFS:
    """Filesystem port rooted at a caller-owned temporary directory."""

    def __init__(self, root: Path, *, read_only: bool = False) -> None:
        self.root = Path(root).resolve()
        self.read_only = read_only
        self.writes = 0

    def _safe(self, relative: str | Path) -> Path:
        path = Path(relative)
        if path.is_absolute():
            raise SideEffectDenied("OutputFS accepts relative paths only")
        target = (self.root / path).resolve()
        if target != self.root and self.root not in target.parents:
            raise SideEffectDenied("OutputFS path escapes its root")
        return target

    def write_bytes(self, relative: str | Path, data: bytes) -> Path:
        if self.read_only:
            raise SideEffectDenied("OutputFS is read-only")
        target = self._safe(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.writes += 1
        return target

    def write_json(self, relative: str | Path, value: Any) -> Path:
        return self.write_bytes(relative, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())

    def snapshot(self) -> dict[str, str]:
        if not self.root.exists():
            return {}
        return {path.relative_to(self.root).as_posix(): sha256_file(path)
                for path in self.root.rglob("*") if path.is_file()}


class StateStore:
    """JSON state port with explicit read/write counters for H/I/J tests."""

    def __init__(self, root: Path, *, read_only: bool = False) -> None:
        self.root = Path(root).resolve()
        self.read_only = read_only
        self.read_count = 0
        self.write_count = 0
        self._writes_by_key: dict[str, int] = {}

    def _path(self, key: str) -> Path:
        if not key or Path(key).is_absolute() or ".." in Path(key).parts:
            raise SideEffectDenied("state key must be a relative safe path")
        return (self.root / key).with_suffix(".json")

    def read(self, key: str, default: Any = None) -> Any:
        self.read_count += 1
        path = self._path(key)
        if not path.is_file():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, key: str, value: Any) -> Path:
        if self.read_only:
            raise SideEffectDenied("StateStore is read-only")
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.write_count += 1
        self._writes_by_key[key] = self._writes_by_key.get(key, 0) + 1
        return path

    def writes_for(self, key: str) -> int:
        return self._writes_by_key.get(key, 0)


class SelectionPort:
    def __init__(self, *, selected: Sequence[str] = ()) -> None:
        self.selected = tuple(selected)
        self.calls = 0

    def select(self, candidates: Sequence[str]) -> tuple[str, ...]:
        self.calls += 1
        return self.selected or tuple(candidates)


class PublishGuard:
    def __init__(self, *, allow: bool = False) -> None:
        self.allow = allow
        self.calls = 0

    def check(self, *, no_publish: bool = True) -> bool:
        self.calls += 1
        if no_publish or not self.allow:
            return False
        return True

    def publish(self, *_args: Any, no_publish: bool = True, **_kwargs: Any) -> None:
        self.calls += 1
        if no_publish or not self.allow:
            raise SideEffectDenied("publish is denied by shadow foundation guard")


Adapter = Callable[[RunContext, str, SourcePlan, OutputFS, StateStore], Any]


class UnifiedStyleOrchestrator:
    """Execute injected adapters only in explicit shadow mode."""

    def __init__(self, adapters: Mapping[str, Adapter] | None = None,
                 *, registry_loader: RegistryLoader | None = None) -> None:
        self.adapters = dict(adapters or {})
        self.registry_loader = registry_loader or RegistryLoader()

    def execute(self, context: RunContext, registry: ArticleStylesRegistry | Mapping[str, Any],
                source_plans: Mapping[str, SourcePlan], *,
                output_fs: OutputFS | None = None, state_store: StateStore | None = None) -> list[ResultEnvelope]:
        loaded = self.registry_loader.load(registry) if not isinstance(registry, ArticleStylesRegistry) else registry
        # Validate all routing data before creating roots, opening files, or invoking callbacks.
        output = output_fs or OutputFS(context.output_root)
        state = state_store or StateStore(context.state_root)
        if context.mode == "legacy":
            return [ResultEnvelope.skip(context.run_id, asset, unit.id,
                                        [loaded.styles[m].letter for m in unit.members],
                                        "LEGACY_MODE")
                    for unit in sorted(loaded.execution_units.values(), key=lambda item: item.order)
                    for asset in context.assets]
        results: list[ResultEnvelope] = []
        for unit in sorted(loaded.execution_units.values(), key=lambda item: item.order):
            style_ids = list(unit.members)
            for asset in context.assets:
                plan = source_plans.get(unit.id)
                if plan is None or plan.asset != asset:
                    results.append(ResultEnvelope.skip(context.run_id, asset, unit.id,
                                                       [loaded.styles[m].letter for m in style_ids],
                                                       "MISSING_SOURCE_PLAN"))
                    continue
                adapter = self.adapters.get(unit.id)
                if adapter is None:
                    results.append(ResultEnvelope.skip(context.run_id, asset, unit.id,
                                                       [loaded.styles[m].letter for m in style_ids],
                                                       "NO_ADAPTER"))
                    continue
                try:
                    raw = adapter(context, asset, plan, output, state)
                    envelope = ResultEnvelope.from_legacy(raw, run_id=context.run_id,
                                                          asset=asset, execution_unit=unit.id,
                                                          style_ids=[loaded.styles[m].letter for m in style_ids])
                except Exception as exc:  # normalize but do not hide a FAIL
                    envelope = ResultEnvelope.fail(context.run_id, asset, unit.id,
                                                    [loaded.styles[m].letter for m in style_ids],
                                                    exception=exc)
                results.append(envelope)
        return results


def rollback_smoke(registry: ArticleStylesRegistry | Mapping[str, Any]) -> dict[str, str]:
    """Prove every unit has a legacy rollback mode without invoking it."""
    loaded = RegistryLoader().load(registry) if not isinstance(registry, ArticleStylesRegistry) else registry
    return {unit.id: unit.rollback_mode for unit in loaded.execution_units.values()}


class VisualReferenceReviewer:
    """Agent10-compatible read-only visual/reference inspection port."""

    read_only = True

    def inspect(self, path: Path) -> dict[str, Any]:
        path = Path(path)
        data = path.read_bytes()
        return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "write": False}

    def write(self, *_args: Any, **_kwargs: Any) -> None:
        raise SideEffectDenied("Agent10 is read-only during foundation/parity review")

    def repair(self, *_args: Any, **_kwargs: Any) -> None:
        raise SideEffectDenied("Agent10 repair is forbidden during foundation/parity review")


def decoded_rgba_digest(path: Path) -> tuple[tuple[int, int], str]:
    """Return dimensions and decoded RGBA digest for a D/E image.

    Pillow is intentionally optional; if it is absent the caller gets a clear
    failure instead of silently comparing compressed/raw bytes.
    """
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("Pillow is required for decoded pixel parity") from exc
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        return rgba.size, hashlib.sha256(rgba.tobytes()).hexdigest()


def compare_decoded_pixel_parity(actual: Path, expected: Path, *, allowlisted: bool = False) -> dict[str, Any]:
    """Compare D/E images on decoded dimensions and RGBA pixels.

    Raw compressed-file hashes are audit-only. A mismatch is FAIL unless an
    already-approved volatile allowlist explicitly marks it review-only; this
    helper never edits either image.
    """
    actual_dimensions, actual_digest = decoded_rgba_digest(actual)
    expected_dimensions, expected_digest = decoded_rgba_digest(expected)
    same = actual_dimensions == expected_dimensions and actual_digest == expected_digest
    return {
        "status": "PASS" if same else ("ALLOWLISTED" if allowlisted else "FAIL"),
        "dimensions": {"actual": actual_dimensions, "expected": expected_dimensions},
        "pixel_sha256": {"actual": actual_digest, "expected": expected_digest},
        "raw_sha256_audit": {"actual": sha256_file(Path(actual)), "expected": sha256_file(Path(expected))},
    }


__all__ = [
    "OutputFS", "PublishGuard", "RunContext", "SelectionPort", "SideEffectDenied",
    "StateStore", "UnifiedStyleOrchestrator", "VisualReferenceReviewer",
    "compare_decoded_pixel_parity", "decoded_rgba_digest", "rollback_smoke",
]
