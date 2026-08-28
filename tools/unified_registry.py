"""Registry foundation for the Unified article-style pipeline.

This module deliberately has no connection to the production command path.  It
normalises the existing v1 registry in memory and validates a v2 registry
before a caller is allowed to construct a plan or execute an adapter.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

SUPPORTED_SCHEMA = {"article-styles-v1", "article-styles-v2"}
TARGET_LETTERS = tuple("ABCDEFGHIJLM")
KNOWN_ADAPTERS = {
    "internal_evidence_123",
    "abc_public",
    "d_chart_story",
    "e_indicator",
    "fg_brief",
    "hij_intraday",
    "forex_daily_plan",
    "style_m_daily",
    "legacy",
}
MODES = {"legacy", "shadow", "unified"}


class RegistryError(ValueError):
    """A fail-closed registry validation error."""

    code = "REGISTRY_INVALID"


class RegistryIOError(RegistryError):
    code = "REGISTRY_IO"


@dataclass(frozen=True)
class StyleEntry:
    id: str
    letter: str
    name: str
    folder: str
    execution_unit: str = "legacy"
    adapter: str = "legacy"
    order: int = 0
    assets: tuple[str, ...] = ()
    timeframes: tuple[str, ...] = ()
    trigger: str = "daily"
    production: bool = False
    line_eligibility: str = "both"
    migration_mode: str = "legacy"
    publish_eligible: bool = True
    failure_policy: str = "isolated"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionUnit:
    id: str
    members: tuple[str, ...]
    order: int
    migration_mode: str = "legacy"
    rollback_mode: str = "legacy"
    execute_once_per_asset: bool = True


@dataclass(frozen=True)
class ArticleStylesRegistry:
    schema: str
    styles: Mapping[str, StyleEntry]
    execution_units: Mapping[str, ExecutionUnit]
    source_schema: str

    @property
    def letters(self) -> tuple[str, ...]:
        return tuple(sorted(entry.letter for entry in self.styles.values()))

    def by_letter(self, letter: str) -> StyleEntry:
        for entry in self.styles.values():
            if entry.letter == letter:
                return entry
        raise RegistryError(f"unknown style letter: {letter}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "styles": {
                key: {
                    "id": value.id,
                    "letter": value.letter,
                    "name": value.name,
                    "folder": value.folder,
                    "execution_unit": value.execution_unit,
                    "adapter": value.adapter,
                    "order": value.order,
                    "assets": list(value.assets),
                    "requirements": {"timeframes": list(value.timeframes)},
                    "trigger": value.trigger,
                    "production": value.production,
                    "line_eligibility": value.line_eligibility,
                    "migration_mode": value.migration_mode,
                    "publish_eligible": value.publish_eligible,
                    "failure_policy": value.failure_policy,
                    **dict(value.metadata),
                }
                for key, value in self.styles.items()
            },
            "execution_units": {
                key: {
                    "id": value.id,
                    "members": list(value.members),
                    "order": value.order,
                    "migration_mode": value.migration_mode,
                    "rollback_mode": value.rollback_mode,
                    "execute_once_per_asset": value.execute_once_per_asset,
                }
                for key, value in self.execution_units.items()
            },
        }


def _as_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RegistryError(f"{field_name} must be a list of strings")
    return tuple(value)


def _style_from_raw(style_id: str, raw: Mapping[str, Any], *, v1: bool) -> StyleEntry:
    if not isinstance(raw, Mapping):
        raise RegistryError(f"style {style_id!r} must be an object")
    letter = raw.get("letter")
    if not isinstance(letter, str) or len(letter) != 1 or not letter.isalpha():
        raise RegistryError(f"style {style_id!r} has invalid letter")
    requirements = raw.get("requirements") if isinstance(raw.get("requirements"), Mapping) else {}
    assets = _as_tuple(raw.get("assets", []), f"styles.{style_id}.assets")
    timeframes = _as_tuple(raw.get("timeframes", requirements.get("timeframes", [])), f"styles.{style_id}.timeframes")
    execution_unit = str(raw.get("execution_unit", "legacy" if v1 else ""))
    adapter = str(raw.get("adapter", "legacy" if v1 else ""))
    metadata = {k: v for k, v in raw.items() if k not in {
        "id", "letter", "name", "folder", "execution_unit", "adapter", "order",
        "assets", "timeframes", "requirements", "trigger", "production",
        "line_eligibility", "migration_mode", "publish_eligible", "failure_policy",
    }}
    return StyleEntry(
        id=str(raw.get("id", style_id)),
        letter=letter.upper(),
        name=str(raw.get("name", style_id)),
        folder=str(raw.get("folder", style_id)),
        execution_unit=execution_unit,
        adapter=adapter,
        order=int(raw.get("order", 0)),
        assets=assets,
        timeframes=timeframes,
        trigger=str(raw.get("trigger", "daily")),
        production=bool(raw.get("production", False)),
        line_eligibility=str(raw.get("line_eligibility", "both")),
        migration_mode=str(raw.get("migration_mode", "legacy")),
        publish_eligible=bool(raw.get("publish_eligible", True)),
        failure_policy=str(raw.get("failure_policy", "isolated")),
        metadata=metadata,
    )


def normalize_registry(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Convert v1 or v2 input to a JSON-like v2 document without I/O."""
    if not isinstance(raw, Mapping):
        raise RegistryError("registry must be an object")
    schema = raw.get("schema")
    if schema not in SUPPORTED_SCHEMA:
        raise RegistryError(f"unsupported registry schema: {schema!r}")
    styles_raw = raw.get("styles")
    if not isinstance(styles_raw, Mapping):
        raise RegistryError("registry.styles must be an object")
    styles: dict[str, dict[str, Any]] = {}
    for index, (style_id, value) in enumerate(styles_raw.items()):
        entry = _style_from_raw(str(style_id), value, v1=schema == "article-styles-v1")
        if schema == "article-styles-v1" and "order" not in value:
            entry = StyleEntry(**{**entry.__dict__, "order": index})
        styles[str(style_id)] = {
            "id": entry.id, "letter": entry.letter, "name": entry.name,
            "folder": entry.folder, "execution_unit": entry.execution_unit,
            "adapter": entry.adapter, "order": entry.order,
            "assets": list(entry.assets), "timeframes": list(entry.timeframes),
            "trigger": entry.trigger, "production": entry.production,
            "line_eligibility": entry.line_eligibility,
            "migration_mode": entry.migration_mode,
            "publish_eligible": entry.publish_eligible,
            "failure_policy": entry.failure_policy,
            **dict(entry.metadata),
        }
    units_raw = raw.get("execution_units")
    units: dict[str, dict[str, Any]] = {}
    if isinstance(units_raw, Mapping):
        for unit_id, value in units_raw.items():
            if not isinstance(value, Mapping):
                raise RegistryError(f"execution_units.{unit_id} must be an object")
            units[str(unit_id)] = dict(value)
    if not units:
        # v1 remains usable as a legacy read.  No production route consumes this
        # object; it only describes the existing H/I/J registration in memory.
        grouped: dict[str, list[str]] = {}
        for style_id, value in styles.items():
            grouped.setdefault(str(value["execution_unit"]), []).append(style_id)
        for idx, (unit_id, members) in enumerate(sorted(grouped.items())):
            units[unit_id] = {
                "id": unit_id, "members": members, "order": idx,
                "migration_mode": "legacy", "rollback_mode": "legacy",
                "execute_once_per_asset": True,
            }
    return {
        "schema": "article-styles-v2",
        "styles": styles,
        "execution_units": units,
        "source_schema": schema,
    }


def validate_registry(raw: Mapping[str, Any] | ArticleStylesRegistry,
                      *, require_target: bool = False) -> ArticleStylesRegistry:
    """Validate all routing-critical fields before side effects."""
    if isinstance(raw, ArticleStylesRegistry):
        registry = raw
    else:
        doc = normalize_registry(raw)
        styles: dict[str, StyleEntry] = {}
        for key, value in doc["styles"].items():
            styles[key] = _style_from_raw(key, value, v1=False)
        units: dict[str, ExecutionUnit] = {}
        for key, value in doc["execution_units"].items():
            members = _as_tuple(value.get("members"), f"execution_units.{key}.members")
            units[key] = ExecutionUnit(
                id=str(value.get("id", key)), members=members,
                order=int(value.get("order", 0)),
                migration_mode=str(value.get("migration_mode", "legacy")),
                rollback_mode=str(value.get("rollback_mode", "legacy")),
                execute_once_per_asset=bool(value.get("execute_once_per_asset", True)),
            )
        registry = ArticleStylesRegistry("article-styles-v2", styles, units, doc["source_schema"])
    if not registry.styles:
        raise RegistryError("registry.styles must not be empty")
    letters = [entry.letter for entry in registry.styles.values()]
    if len(letters) != len(set(letters)):
        raise RegistryError("duplicate style letter")
    if "K" in letters:
        raise RegistryError("Style K is retired and must not be registered")
    if require_target and set(letters) != set(TARGET_LETTERS):
        raise RegistryError("target registry must contain exactly Styles A–J, L and M")
    orders = [entry.order for entry in registry.styles.values()]
    if len(orders) != len(set(orders)):
        raise RegistryError("duplicate style order")
    for key, entry in registry.styles.items():
        if entry.execution_unit not in registry.execution_units:
            raise RegistryError(f"style {key!r} references unknown execution unit")
        if entry.adapter not in KNOWN_ADAPTERS:
            raise RegistryError(f"style {key!r} references unknown adapter {entry.adapter!r}")
        if entry.migration_mode not in MODES:
            raise RegistryError(f"style {key!r} has invalid migration mode")
        if entry.line_eligibility not in {"internal", "public", "both"}:
            raise RegistryError(f"style {key!r} has invalid line eligibility")
    unit_members: set[str] = set()
    unit_orders = []
    for key, unit in registry.execution_units.items():
        if unit.id != key or (not unit.members and key != "INTERNAL_EVIDENCE_123"):
            raise RegistryError(f"execution unit {key!r} has invalid identity/members")
        if unit.migration_mode not in MODES or unit.rollback_mode not in MODES:
            raise RegistryError(f"execution unit {key!r} has invalid mode")
        unit_orders.append(unit.order)
        for member in unit.members:
            if member not in registry.styles:
                raise RegistryError(f"execution unit {key!r} references unknown style {member!r}")
            if registry.styles[member].execution_unit != key:
                raise RegistryError(f"style/unit membership mismatch for {member!r}")
            unit_members.add(member)
    if len(unit_orders) != len(set(unit_orders)):
        raise RegistryError("duplicate execution unit order")
    if unit_members != set(registry.styles):
        raise RegistryError("every style must belong to exactly one execution unit")
    return registry


class RegistryLoader:
    """Read JSON or mappings; never writes and never performs network work."""

    def load(self, source: str | Path | Mapping[str, Any], *, require_target: bool = False) -> ArticleStylesRegistry:
        if isinstance(source, Mapping):
            raw = source
        else:
            path = Path(source)
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RegistryIOError(str(exc)) from exc
        return validate_registry(raw, require_target=require_target)


__all__ = [
    "ArticleStylesRegistry", "ExecutionUnit", "RegistryError", "RegistryLoader",
    "StyleEntry", "normalize_registry", "validate_registry",
]
