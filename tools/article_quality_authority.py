"""Fail-closed authority resolver for P002 article-quality preflight.

This module is deliberately sidecar-only.  It resolves the style contract and
evidence envelope before scoring, but it is not imported by any production
writer, publisher, or output route.  A caller may use the returned envelope to
decide whether a calibration/scoring job is eligible.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - requirements.txt declares jsonschema
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "article_quality_authorities.json"
REGISTRY_SCHEMA_PATH = ROOT / "schemas" / "article-quality-authority-v1.schema.json"
EVIDENCE_SCHEMA_PATH = ROOT / "schemas" / "article-quality-evidence-v1.schema.json"
HASH_RE = re.compile(r"^[a-f0-9]{64}$")
STYLE_IDS = {"D", "E", "L", "M"}
M_CURRENT_MANIFEST_PATH = "work/qa/authority-freezes/style-m-current-contract-manifest-v1.json"
M_CURRENT_MANIFEST_SHA256 = "d630e19a6df58252fde3d5fbbeed4166266f1817caf0e2a4855b6039a0d017c5"
M_CURRENT_PACKAGE_ROOT = "work/review/style-m-r10-live-20260904-0800/04-09-2026/btcusd/internal/style-m-v7-6698a3b19c39"
M_CURRENT_VISUALS = {
    "h1_market_map": ("public/btcusd-style-m-v7-h1-market-map-2026-09-04.webp", "70d2dd2dbd791bf4a415a272dcee4d8bee21ae2abac347068bf1014d23feaba0", "H1"),
    "m15_entry_plan": ("public/btcusd-style-m-v7-m15-entry-h1-plan-2026-09-04.webp", "488c1352246bb390086a3acc152d4e11abb85e516752ffb5f52870c4e3c75375", "M15"),
}
STYLE_REQUIRED_VISUALS = {
    "D": {"structure": "D1", "levels": "D1", "weekly_calendar": "calendar"},
    "E": {"h1_fibonacci": "H1", "h1_trade_plan": "H1"},
    "L": {"h1_plan": "H1", "m15_trigger": "M15", "daily_calendar": "calendar"},
}


class AuthorityError(ValueError):
    """An unsafe, stale, ambiguous, or incomplete authority envelope."""


class CurrentManifestPending(AuthorityError):
    """M's real current 6b manifest has not been frozen yet."""


def _fail(message: str) -> None:
    raise AuthorityError(message)


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(HASH_RE.fullmatch(value))


def _parse_rfc3339(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        _fail(f"{label} must be RFC3339")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(f"{label} must include a timezone")
    return parsed


def _validate_schema(value: dict[str, Any], schema_path: Path, label: str) -> None:
    if Draft202012Validator is None:
        _fail("jsonschema dependency is required for authority validation")
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors = sorted(Draft202012Validator(schema).iter_errors(value),
                        key=lambda error: list(error.absolute_path))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"{label} schema unavailable: {exc}")
    if errors:
        first = errors[0]
        location = ".".join(str(item) for item in first.absolute_path) or "$"
        _fail(f"{label} schema invalid at {location}: {first.message}")


def _require_finite(value: Any, path: str = "$", *, reject_numeric_strings: bool = False) -> None:
    """Reject NaN/Infinity before JSON schema or canonical JSON processing."""
    if isinstance(value, float) and not math.isfinite(value):
        _fail(f"non-finite number at {path}")
    if isinstance(value, str) and reject_numeric_strings and value.strip().lower() in {
        "nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"
    }:
        _fail(f"non-finite number at {path}")
    if isinstance(value, dict):
        for key, child in value.items():
            _require_finite(child, f"{path}.{key}", reject_numeric_strings=reject_numeric_strings)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _require_finite(child, f"{path}[{index}]", reject_numeric_strings=reject_numeric_strings)


def validate_registry(registry: dict[str, Any]) -> dict[str, Any]:
    """Validate an authority registry, including duplicate identity checks."""
    if not isinstance(registry, dict):
        _fail("registry must be an object")
    _validate_schema(registry, REGISTRY_SCHEMA_PATH, "registry")
    authorities = registry["authorities"]
    identities: set[tuple[str, str, str]] = set()
    for authority in authorities:
        identity = (authority["style_id"], authority["authority_version"], authority["effective_from"])
        if identity in identities:
            _fail(f"duplicate authority identity: {identity[0]}/{identity[1]}")
        identities.add(identity)
        _validate_artifact_ref(authority["brief"], "brief")
        _validate_artifact_ref(authority["machine_contract"], "machine contract")
        for key in ("evidence_schema", "visual_manifest"):
            if key in authority:
                _validate_artifact_ref(authority[key], key)
        _validate_path(authority["validator"]["entrypoint"], "validator entrypoint")
        _parse_rfc3339(authority["effective_from"], "authority effective_from")
        role_ids = [item["role_id"] for item in authority.get("visual_roles", [])]
        if len(role_ids) != len(set(role_ids)):
            _fail(f"duplicate visual role_id in authority: {authority['style_id']}")
    return registry


def validate_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Validate an evidence envelope without resolving its authority."""
    if not isinstance(evidence, dict):
        _fail("evidence must be an object")
    _require_finite(evidence, reject_numeric_strings=True)
    _validate_schema(evidence, EVIDENCE_SCHEMA_PATH, "evidence")
    _parse_rfc3339(evidence.get("production_date"), "evidence production_date")
    _parse_rfc3339(evidence["authority"].get("effective_at"), "evidence effective_at")
    for field in ("article_sha256", "source_facts_sha256", "evidence_sha256"):
        if not _is_hash(evidence.get(field)):
            _fail(f"evidence required hash is invalid: {field}")
    authority = evidence["authority"]
    if not _is_hash(authority.get("brief_sha256")):
        _fail("evidence brief hash is required")
    _validate_path(authority.get("brief_path"), "brief path")
    for path_key, hash_key in (("machine_contract_path", "machine_contract_sha256"),
                               ("visual_manifest_path", "visual_manifest_sha256")):
        if path_key in authority or hash_key in authority:
            if path_key not in authority or not _is_hash(authority.get(hash_key)):
                _fail(f"evidence {path_key} and {hash_key} must be bound together")
            _validate_path(authority[path_key], path_key)
    visual_roles: set[str] = set()
    for visual in evidence.get("visuals", []):
        _validate_visual(visual)
        role = visual.get("role", visual.get("role_id"))
        if role in visual_roles:
            _fail(f"duplicate visual role: {role}")
        visual_roles.add(role)
    return evidence


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Load the production sidecar registry; never called by production routes."""
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"authority registry unavailable: {exc}")
    validate_registry(registry)
    _verify_registry_artifacts(registry, path.parent.parent)
    return registry


def _verify_registry_artifacts(registry: dict[str, Any], root: Path) -> None:
    """Verify every registered artifact against bytes on disk for production loads."""
    root = root.resolve()
    for authority in registry["authorities"]:
        refs = [authority["brief"], authority["machine_contract"]]
        refs.extend(ref for key in ("evidence_schema", "visual_manifest")
                    if (ref := authority.get(key)) is not None)
        for ref in refs:
            path = (root / ref["path"]).resolve()
            try:
                path.relative_to(root)
            except ValueError as exc:
                _fail(f"registered artifact escapes repository: {ref['path']}")
            if not path.is_file():
                _fail(f"registered artifact is missing: {ref['path']}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != ref["sha256"]:
                _fail(f"registered artifact hash drift: {ref['path']}")


def _validate_path(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label} is required")
    path = value.replace("\\", "/")
    candidate = Path(path)
    if path.startswith("/") or candidate.is_absolute() or re.match(r"^[A-Za-z]:", path):
        _fail(f"unsafe absolute {label}")
    parts = [part for part in path.split("/") if part]
    if ".." in parts or any(part in {".", ""} for part in parts):
        _fail(f"unsafe path escape in {label}")
    # Existing symlinks are rejected even when their textual path is benign.
    current = ROOT
    for part in parts:
        current = current / part
        if current.is_symlink():
            _fail(f"symlink is not allowed in {label}")


def _validate_artifact_ref(value: Any, label: str) -> None:
    if not isinstance(value, dict) or set(value) - {"path", "sha256", "role"}:
        _fail(f"invalid {label} reference")
    if not _is_hash(value.get("sha256")):
        _fail(f"{label} hash is required")
    _validate_path(value.get("path"), f"{label} path")


def _validate_visual(visual: Any) -> None:
    if not isinstance(visual, dict):
        _fail("visual role record must be an object")
    allowed = {"role", "role_id", "path", "sha256", "timeframe", "source_kind"}
    if set(visual) - allowed:
        _fail("visual role has unknown fields")
    role = visual.get("role", visual.get("role_id"))
    if not isinstance(role, str) or not role.strip():
        _fail("visual role is required")
    _validate_path(visual.get("path"), "visual path")
    if not _is_hash(visual.get("sha256")):
        _fail(f"visual role {role} hash is invalid")
    if "source_kind" in visual and visual["source_kind"] not in {
        "contemporaneous", "reconstructed", "candidate_only", "current_authority"
    }:
        _fail(f"visual role {role} source kind is invalid")


def _authority_for(registry: dict[str, Any], style: str, version: str,
                   effective_at: datetime) -> dict[str, Any]:
    matches = [item for item in registry["authorities"]
               if item["style_id"] == style and item["authority_version"] == version
               and _parse_rfc3339(item["effective_from"], "authority effective_from") <= effective_at]
    if not matches:
        _fail(f"unknown authority style/version: {style}/{version}")
    return max(matches, key=lambda item: _parse_rfc3339(
        item["effective_from"], "authority effective_from"))


def _require_brief_binding(authority: dict[str, Any], evidence: dict[str, Any]) -> None:
    supplied = evidence["authority"]
    if supplied["authority_id"] != authority["authority_id"]:
        _fail("authority identity does not match evidence")
    if supplied["brief_path"] != authority["brief"]["path"]:
        _fail("brief path is wrong-style or not the registered authority")
    if supplied["brief_sha256"] != authority["brief"]["sha256"]:
        _fail("brief hash drift or stale authority")
    registered_manifest = authority.get("visual_manifest")
    if not registered_manifest:
        _fail("visual manifest authority reference is required")
    if supplied["machine_contract_path"] != authority["machine_contract"]["path"]:
        _fail("machine contract path is not the registered authority")
    if supplied["machine_contract_sha256"] != authority["machine_contract"]["sha256"]:
        _fail("machine contract hash drift or stale authority")
    if supplied["visual_manifest_path"] != registered_manifest["path"]:
        _fail("visual manifest path is not the registered authority")
    if supplied["visual_manifest_sha256"] != registered_manifest["sha256"]:
        _fail("visual manifest hash drift or stale authority")
    if supplied.get("authority_version") != authority["authority_version"]:
        _fail("authority version is stale or mismatched")


def _safe_artifact(root: Path, relative: Any, label: str) -> Path:
    """Resolve a repository artifact while rejecting escapes and symlinks."""
    _validate_path(relative, label)
    base = root.resolve()
    target = (base / relative).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        _fail(f"{label} escapes trusted artifact root")
    current = base
    for part in Path(relative.replace("\\", "/")).parts:
        current = current / part
        if current.is_symlink():
            _fail(f"symlink is not allowed in {label}")
    if not target.is_file():
        _fail(f"{label} is missing; NO_SCORE")
    return target


def _verify_file_hash(root: Path, relative: str, expected: str, label: str) -> Path:
    target = _safe_artifact(root, relative, label)
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        _fail(f"{label} hash drift; NO_SCORE")
    return target


def _verify_evidence_artifacts(root: Path, authority: dict[str, Any],
                               evidence: dict[str, Any]) -> dict[str, Any]:
    """Verify every caller-provided binding when a trusted root is explicit."""
    contents: dict[str, Any] = {}
    for path_key, hash_key, label in (
        ("article_path", "article_sha256", "article"),
        ("source_facts_path", "source_facts_sha256", "source facts"),
        ("evidence_path", "evidence_sha256", "evidence"),
    ):
        target = _verify_file_hash(root, evidence[path_key], evidence[hash_key], label)
        if path_key in {"source_facts_path", "evidence_path"}:
            try:
                contents[path_key] = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                _fail(f"{label} must be valid JSON: {exc}")
    for key in ("story", "technical", "calendar", "indicator_facts",
                "trade_plan_qa", "timeframe_facts"):
        section = evidence.get(key)
        if isinstance(section, dict):
            target = _verify_file_hash(root, section["path"], section["sha256"], f"{key} evidence")
            try:
                contents[key] = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                _fail(f"{key} evidence must be valid JSON: {exc}")
    refs = ((authority["brief"], "brief"), (authority["machine_contract"], "machine contract"),
            (authority["visual_manifest"], "authority visual manifest"))
    for ref, label in refs:
        _verify_file_hash(root, ref["path"], ref["sha256"], label)
    manifest = evidence.get("visual_manifest")
    if not isinstance(manifest, dict):
        _fail("immutable per-article visual manifest is required; NO_SCORE")
    manifest_path = _verify_file_hash(root, manifest["path"], manifest["sha256"], "per-article visual manifest")
    try:
        manifest_bytes = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"per-article visual manifest is invalid: {exc}")
    if not isinstance(manifest_bytes, dict) or manifest_bytes.get("immutable") is not True:
        _fail("per-article visual manifest bytes are not immutable")
    canonical = canonical_hash({key: value for key, value in manifest_bytes.items() if key != "sha256"})
    if manifest.get("canonical_sha256") is not None and canonical != manifest["canonical_sha256"]:
        _fail("per-article visual manifest canonical hash drift; NO_SCORE")
    for visual in evidence["visuals"]:
        _verify_file_hash(root, visual["path"], visual["sha256"], "visual")
    return contents


def _section(section: Any, label: str, required_keys: set[str]) -> dict[str, Any]:
    if not isinstance(section, dict) or not {"path", "sha256", "required_keys"} <= set(section):
        _fail(f"{label} typed evidence is missing required keys: {sorted(required_keys)}")
    if not _is_hash(section.get("sha256")) or not isinstance(section.get("path"), str):
        _fail(f"{label} requires path and SHA-256")
    keys = section.get("required_keys")
    # The sidecar list is a declaration only.  It is deliberately not used to
    # establish authority: the required semantic fields are checked below from
    # the parsed bytes of the hash-bound artifact.
    if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):
        _fail(f"{label} required_keys declaration is invalid")
    return section


def _validate_trade_plan_values(plan: Any, label: str) -> None:
    """Require concrete finite numeric trade-plan values in bound JSON."""
    if not isinstance(plan, dict):
        _fail(f"{label} bound bytes are not an object")
    for field in ("entry", "stop_loss", "take_profit"):
        value = plan.get(field)
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                not math.isfinite(float(value))):
            _fail(f"{label} requires meaningful numeric {field} value")


def _validate_d_technical_values(technical: Any) -> None:
    """Require meaningful, typed D technical facts from the bound JSON."""
    if not isinstance(technical, dict):
        _fail("D technical bound bytes are not an object")
    close = technical.get("current_close")
    if (isinstance(close, bool) or not isinstance(close, (int, float)) or
            not math.isfinite(float(close))):
        _fail("D technical requires finite numeric current_close value")
    bias = technical.get("structure_bias")
    if not isinstance(bias, str) or not bias.strip():
        _fail("D technical requires non-empty structure_bias")
    for field in ("support_levels", "resistance_levels"):
        levels = technical.get(field)
        if not isinstance(levels, list) or not levels:
            _fail(f"D technical requires non-empty {field}")
        if any(isinstance(level, bool) or not isinstance(level, (int, float)) or
               not math.isfinite(float(level)) for level in levels):
            _fail(f"D technical {field} must contain finite numeric values")


def _has_meaningful_value(value: Any) -> bool:
    """Return whether a decoded JSON value carries non-empty information."""
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value) and any(_has_meaningful_value(child) for child in value.values())
    if isinstance(value, list):
        return bool(value) and all(_has_meaningful_value(child) for child in value)
    return False


def _has_finite_numeric(value: Any) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.isfinite(float(value))
    if isinstance(value, dict):
        return any(_has_finite_numeric(child) for child in value.values())
    if isinstance(value, list):
        return any(_has_finite_numeric(child) for child in value)
    return False


def _validate_timeframe_fact_objects(facts: Any, label: str) -> None:
    """Require one non-empty fact object for every authoritative timeframe."""
    if not isinstance(facts, dict) or set(facts.get("timeframes", [])) != {"H4", "H1", "M30", "M15"}:
        _fail(f"{label} must bind H4/H1/M30/M15")
    fact_map = facts.get("facts", facts)
    for timeframe in ("H4", "H1", "M30", "M15"):
        fact = fact_map.get(timeframe) if isinstance(fact_map, dict) else None
        if (not isinstance(fact, dict) or not fact or
                not isinstance(fact.get("close"), (int, float)) or
                isinstance(fact.get("close"), bool) or
                not math.isfinite(float(fact["close"])) or
                not isinstance(fact.get("bias"), str) or
                not fact["bias"].strip()):
            _fail(f"{label} is missing fact object for {timeframe}")


def _validate_typed_evidence(style: str, evidence: dict[str, Any],
                             contents: dict[str, Any]) -> None:
    if style == "D":
        _section(evidence.get("story"), "D story", {"article_id", "sections"})
        _section(evidence.get("technical"), "D technical", {"current_close", "structure_bias", "support_levels", "resistance_levels"})
        _section(evidence.get("calendar"), "D calendar", {"items"})
        for key, required in (("story", {"article_id", "sections"}),
                              ("technical", {"current_close", "structure_bias", "support_levels", "resistance_levels"}),
                              ("calendar", {"items"})):
            if not isinstance(contents.get(key), dict) or not required <= set(contents[key]):
                _fail(f"D {key} bytes do not contain required semantic fields")
        story = contents["story"]
        if (not isinstance(story.get("article_id"), str) or
                story["article_id"] != evidence["article_id"] or
                not isinstance(story.get("sections"), list) or
                not story["sections"] or
                not all(_has_meaningful_value(section) for section in story["sections"])):
            _fail("D story bytes do not contain meaningful article sections")
        _validate_d_technical_values(contents["technical"])
        if (not isinstance(contents["calendar"].get("items"), list) or
                not all(_has_meaningful_value(item) for item in contents["calendar"]["items"])):
            _fail("D calendar bytes do not contain a typed items list")
    elif style == "E":
        source = contents.get("source_facts_path")
        if not isinstance(source, dict) or set(source.get("timeframes", [])) != {"H1", "M15"}:
            _fail("E source inputs must bind H1 and M15")
        _section(evidence.get("indicator_facts"), "E indicator facts", {"indicator", "fibonacci_levels"})
        _section(evidence.get("trade_plan_qa"), "E trade-plan QA", {"entry", "stop_loss", "take_profit"})
        indicator = contents.get("indicator_facts")
        qa_content = contents.get("trade_plan_qa")
        if (not isinstance(contents.get("indicator_facts"), dict) or
                not {"indicator", "fibonacci_levels"} <= set(indicator) or
                not isinstance(qa_content, dict) or
                qa_content.get("status") != "PASS" or
                qa_content.get("plan_status") not in {"ACTIVE", "NEUTRAL-OCO"}):
            _fail("E trade-plan QA/status is not approved")
        if (not isinstance(indicator.get("indicator"), str) or
                not indicator["indicator"].strip() or
                not isinstance(indicator.get("fibonacci_levels"), list) or
                not indicator["fibonacci_levels"] or
                not all(_has_meaningful_value(level) and _has_finite_numeric(level)
                        for level in indicator["fibonacci_levels"])):
            _fail("E indicator facts require meaningful finite fibonacci data")
        _validate_trade_plan_values(qa_content, "E trade-plan QA")
    elif style == "L":
        bound_facts = contents.get("timeframe_facts")
        _validate_timeframe_fact_objects(bound_facts, "L timeframe facts")
        _section(evidence.get("timeframe_facts"), "L timeframe facts", {"H4", "H1", "M30", "M15"})
        _section(evidence.get("trade_plan_qa"), "L trade-plan QA", {"entry", "stop_loss", "take_profit"})
        qa_content = contents.get("trade_plan_qa")
        if (not isinstance(qa_content, dict) or
                qa_content.get("status") != "PASS" or
                qa_content.get("plan_status") not in {"ACTIVE", "NEUTRAL-OCO"}):
            _fail("L trade-plan QA/status is not approved")
        _validate_trade_plan_values(qa_content, "L trade-plan QA")


def _validate_style_rules(authority: dict[str, Any], evidence: dict[str, Any],
                          article: dict[str, Any], artifact_root: Path | None = None) -> None:
    style = authority["style_id"]
    brief_path = evidence["authority"]["brief_path"].upper()
    for field in ("article_path", "source_facts_path", "evidence_path"):
        _validate_path(evidence[field], field)
    if evidence["validator"]["entrypoint"] != authority["validator"]["entrypoint"]:
        _fail("validator identity does not match the style authority")
    if evidence["validator"]["module"] != authority["validator"].get("module"):
        _fail("validator module identity does not match the style authority")
    if style == "E" and "INTRADAY-STYLES-H-I-J" in brief_path:
        _fail("wrong-style brief cannot authorize Style E")
    if style == "L" and ("WCB-DAILY-OUTPUT-CONTRACT" in brief_path or
                          "STYLE-L-FOREX-DAILY" not in brief_path):
        _fail("generic daily brief cannot authorize Style L")
    if style == "D":
        if (evidence.get("source_facts_sha256") is None or
                not isinstance(evidence.get("technical"), dict) or
                not evidence.get("technical")):
            _fail("Style D requires article-bound technical evidence; calendar-only is NO_SCORE")
    if style == "E":
        roles = {item.get("role", item.get("role_id")): item for item in evidence.get("visuals", [])}
        required = STYLE_REQUIRED_VISUALS["E"]
        if set(roles) != set(required):
            _fail("Style E requires exactly two H1 visual roles")
        for role, expected_timeframe in required.items():
            if roles[role].get("timeframe") != expected_timeframe:
                _fail(f"Style E visual role {role} must bind timeframe H1")
    if style == "L":
        roles = {item.get("role", item.get("role_id")) for item in evidence.get("visuals", [])}
        required = STYLE_REQUIRED_VISUALS["L"]
        if set(roles) != set(required):
            _fail("Style L requires topology, plan, and calendar visual roles")
        by_role = {item.get("role", item.get("role_id")): item for item in evidence["visuals"]}
        for role, expected_timeframe in required.items():
            if by_role[role].get("timeframe") != expected_timeframe:
                _fail(f"Style L visual role {role} must bind timeframe {expected_timeframe}")
    if style in {"D", "E", "L"}:
        required = STYLE_REQUIRED_VISUALS[style]
        roles = {item.get("role", item.get("role_id")): item for item in evidence.get("visuals", [])}
        if set(roles) != set(required):
            _fail(f"Style {style} visual role set is incomplete")
        manifest = evidence.get("visual_manifest")
        if not isinstance(manifest, dict):
            _fail(f"Style {style} requires an immutable per-article visual manifest")
        bound = {item["role_id"]: item for item in manifest["roles"]}
        if set(bound) != set(required):
            _fail(f"Style {style} visual manifest role set is incomplete")
        for role, timeframe in required.items():
            visual = roles[role]
            declared = bound[role]
            if (visual.get("path") != declared["path"] or
                    visual.get("sha256") != declared["sha256"] or
                    visual.get("timeframe") != declared["timeframe"] or
                    declared["timeframe"] != timeframe):
                _fail(f"Style {style} visual is not bound to authoritative role/path/hash: {role}")
    if style == "M":
        freeze = evidence.get("m_freeze")
        if not isinstance(freeze, dict):
            _fail("M current freeze manifest is required")
        if (freeze.get("manifest") != M_CURRENT_MANIFEST_PATH or
                freeze.get("candidate_only") is not False or freeze.get("current") is not True or
                freeze.get("post_merge_verified") is not True or
                freeze.get("worktree_clean") is not True):
            _fail("M candidate/old/dirty freeze is not current authority")
        expected_package_files = {
            "manifest.json": M_CURRENT_MANIFEST_SHA256,
            "public/btc.md": "cf90a229d09d6914c90c4928ca69e5b3ac8b4b87ac7d57572fe8577b490416b1",
            "public/btcusd-style-m-v7-h1-market-map-2026-09-04.webp": M_CURRENT_VISUALS["h1_market_map"][1],
            "public/btcusd-style-m-v7-m15-entry-h1-plan-2026-09-04.webp": M_CURRENT_VISUALS["m15_entry_plan"][1],
            "web-upload/btc-daily-2026-09-04.md": "c4966a158386f61235835826360602a552f47fc102d88d3c40b2ad67d2fd7f76",
            "web-upload/btcusd-style-m-v7-h1-market-map-2026-09-04.webp": M_CURRENT_VISUALS["h1_market_map"][1],
            "web-upload/btcusd-style-m-v7-m15-entry-h1-plan-2026-09-04.webp": M_CURRENT_VISUALS["m15_entry_plan"][1],
        }
        if freeze["package_root"] != M_CURRENT_PACKAGE_ROOT:
            _fail("M current package root is not the frozen package")
        if freeze["package_files"] != expected_package_files:
            _fail("M current package files are arbitrary or mismatched")
        if not _is_hash(freeze.get("tree_sha256")) or not _is_hash(freeze.get("implementation_sha256")):
            _fail("M current freeze requires final tree and implementation hashes")
        expected_roles = set(M_CURRENT_VISUALS)
        actual = {item.get("role", item.get("role_id")) for item in evidence.get("visuals", [])}
        if actual != expected_roles:
            _fail("M current manifest requires h1_market_map and m15_entry_plan visual roles")
        if article.get("m_current_manifest_sha256") != M_CURRENT_MANIFEST_SHA256:
            _fail("M current manifest hash is not the frozen current manifest")
        for visual in evidence.get("visuals", []):
            role = visual.get("role", visual.get("role_id"))
            expected_path, expected_hash, expected_timeframe = M_CURRENT_VISUALS[role]
            if (visual.get("path") != expected_path or visual.get("sha256") != expected_hash or
                    visual.get("timeframe") != expected_timeframe):
                _fail(f"M current package visual binding is arbitrary or mismatched: {role}")
        manifest_path = (ROOT / M_CURRENT_MANIFEST_PATH).resolve()
        if not manifest_path.is_file():
            raise CurrentManifestPending("M current contract manifest is absent; BLOCKED_PENDING_CURRENT_CONTRACT")
        if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != M_CURRENT_MANIFEST_SHA256:
            _fail("M current contract manifest bytes do not match frozen hash")
        package_root = (ROOT / M_CURRENT_PACKAGE_ROOT).resolve()
        try:
            package_root.relative_to(ROOT)
        except ValueError as exc:
            _fail("M current package root escapes repository")
        for relative, expected_hash in expected_package_files.items():
            package_file = (package_root / relative).resolve()
            try:
                package_file.relative_to(package_root)
            except ValueError as exc:
                _fail("M current package file escapes package root")
            if not package_file.is_file():
                _fail(f"M current package file is missing: {relative}")
            if hashlib.sha256(package_file.read_bytes()).hexdigest() != expected_hash:
                _fail(f"M current package file hash drift: {relative}")


def resolve_and_validate(*, registry: dict[str, Any], evidence: dict[str, Any],
                         article: dict[str, Any] | None = None,
                         artifact_root: Path | str | None = None) -> dict[str, Any]:
    """Resolve authority, verify gates, and return score eligibility metadata."""
    article = article or {}
    validate_registry(registry)
    validate_evidence(evidence)
    style = evidence["style_id"]
    if style not in STYLE_IDS:
        _fail(f"unknown style: {style}")
    supplied_article_hash = article.get("article_sha256")
    if supplied_article_hash is not None and supplied_article_hash != evidence["article_sha256"]:
        _fail("article hash rebind or drift detected")
    effective_at = _parse_rfc3339(evidence["authority"]["effective_at"], "evidence effective_at")
    production_date = _parse_rfc3339(evidence["production_date"], "evidence production_date")
    if production_date < effective_at:
        _fail("production date is before effective authority date")
    authority = _authority_for(registry, style, evidence["authority"]["authority_version"], effective_at)
    if _parse_rfc3339(authority["effective_from"], "authority effective_from") > production_date:
        _fail("authority is outside the production date window")
    _require_brief_binding(authority, evidence)
    if artifact_root is None and style != "M":
        _fail("trusted artifact_root is required for eligibility; NO_SCORE")
    try:
        _validate_style_rules(authority, evidence, article, Path(artifact_root) if artifact_root is not None else None)
        contents: dict[str, Any] = {}
        if artifact_root is not None:
            contents = _verify_evidence_artifacts(Path(artifact_root), authority, evidence)
        _validate_typed_evidence(style, evidence, contents)
    except CurrentManifestPending:
        return {"status": "BLOCKED_PENDING_CURRENT_CONTRACT",
                "core_calibration_eligible": False,
                "authority_id": authority["authority_id"],
                "authority_version": authority["authority_version"],
                "reason_codes": ["CURRENT_MANIFEST_ABSENT"]}
    if evidence["validator"]["status"] != "PASS":
        _fail("hard gate is not PASS; NO_SCORE")
    if evidence["brief_compliance"]["status"] != "PASS":
        _fail("brief compliance is not PASS; NO_SCORE")
    provenance = evidence.get("provenance", "contemporaneous")
    if provenance == "reconstructed":
        return {"status": "CONTROL_ONLY", "core_calibration_eligible": False,
                "authority_id": authority["authority_id"],
                "authority_version": authority["authority_version"],
                "reason_codes": ["RECONSTRUCTED_EVIDENCE_CONTROL_ONLY"]}
    return {"status": "PASS", "core_calibration_eligible": True,
            "authority_id": authority["authority_id"],
            "authority_version": authority["authority_version"],
            "reason_codes": []}


def canonical_hash(value: dict[str, Any]) -> str:
    """Hash canonical JSON for sidecar binding and immutable manifests."""
    _require_finite(value, reject_numeric_strings=True)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
