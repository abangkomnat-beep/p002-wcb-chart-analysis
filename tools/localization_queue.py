"""Select enrolled localized countries for a normal daily run.

The index is Lead-owned: it contains hash-bound admission records, not a
directory scan.  Selection is deliberately separate from daily translation
and delivery; an enrolled country is a queue member, never proof that today's
localized output has already passed review.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from tools import active_rollout, localization_admission

SCHEMA = "p002-localization-admission-index/v1"
NORMAL_SCOPE = ("ZA", "MY", "BR", "AR", "CL", "MX", "RU", "NG", "SG", "SA")


class QueueError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QueueError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise QueueError("index must be an object")
    return value


def _inside(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise QueueError("index path is required")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise QueueError("index path escapes project") from exc
    return path


def _policy(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QueueError(f"cannot read country policy: {path}") from exc
    countries = data.get("countries")
    if data.get("schema") != "p002-localization-country-policy/v1" or not isinstance(countries, dict):
        raise QueueError("unsupported country policy")
    return countries


def _config_path(project_root: Path, name: str) -> Path:
    project = Path(project_root).resolve()
    direct = project / "config" / name
    nested = project / "Repo" / "config" / name
    return direct if direct.is_file() or not nested.is_file() else nested


def _registry(path: Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QueueError(f"cannot read locale registry: {path}") from exc
    countries = data.get("countries") if isinstance(data, dict) else None
    if not isinstance(countries, list):
        raise QueueError("locale registry is malformed")
    result: dict[str, dict[str, Any]] = {}
    for item in countries:
        code = item.get("country_code") if isinstance(item, dict) else None
        if not isinstance(code, str) or code in result:
            raise QueueError("locale registry has duplicate or invalid country")
        result[code] = item
    return result


def _default_scope(project_root: Path) -> tuple[tuple[str, ...], str]:
    rollout_path = _config_path(project_root, "localization-rollout-20.json")
    rollout = _read(rollout_path)
    countries = rollout.get("countries")
    if rollout.get("schema") != "p002-localization-rollout/v1" or not isinstance(countries, list):
        raise QueueError("unsupported localization rollout")
    if rollout.get("country_count") != 20 or len(countries) != 20 or len(set(countries)) != 20:
        raise QueueError("localization rollout must contain 20 unique countries")
    if "TH" not in countries:
        raise QueueError("localization rollout must include TH source country")
    foreign = tuple(code for code in countries if code != "TH")
    if len(foreign) != 19 or any(not isinstance(code, str) for code in foreign):
        raise QueueError("localization rollout foreign scope must contain 19 countries")
    statuses = rollout.get("delivery_status")
    if not isinstance(statuses, dict) or set(statuses) != set(countries):
        raise QueueError("localization rollout status keys do not match countries")
    registry = _registry(_config_path(project_root, "../language/country-locale-registry.json"))
    policies = _policy(_config_path(project_root, "localization-country-policy.json"))
    for code in foreign:
        if code not in registry:
            raise QueueError(f"locale registry is missing rollout country: {code}")
        policy = policies.get(code)
        if not isinstance(policy, dict) or not isinstance(policy.get("enabled_for_localization"), bool):
            raise QueueError(f"country policy is incomplete for {code}")
    return foreign, _sha(rollout_path)


def default_policy_path(project_root: Path) -> Path:
    """Support the P002 project root while retaining direct Repo-root tests."""
    project = Path(project_root).resolve()
    direct = project / "config" / "localization-country-policy.json"
    nested = project / "Repo" / "config" / "localization-country-policy.json"
    return direct if direct.is_file() or not nested.is_file() else nested


def select(*, project_root: Path, output_root: Path, business_date: str,
           index_path: Path, scope: tuple[str, ...] | list[str] | None = None,
           policy_path: Path | None = None) -> dict[str, Any]:
    try:
        today = date.fromisoformat(business_date)
    except (TypeError, ValueError) as exc:
        raise QueueError("business_date must be YYYY-MM-DD") from exc
    project, output = Path(project_root).resolve(), Path(output_root).resolve()
    index_path = Path(index_path).resolve()
    data = _read(index_path)
    if data.get("schema") != SCHEMA or not isinstance(data.get("records"), list):
        raise QueueError("unsupported admission index")
    records, seen, indexed = [], set(), {}
    for entry in data["records"]:
        if not isinstance(entry, dict) or set(entry) != {"country_code", "active", "admission_path", "admission_sha256"}:
            raise QueueError("invalid admission index entry")
        code = entry["country_code"]
        if not isinstance(code, str) or code in seen or not isinstance(entry["active"], bool):
            raise QueueError("duplicate or invalid country entry")
        seen.add(code)
        indexed[code] = entry

    rollout_sha256 = None
    if scope is None:
        requested, rollout_sha256 = _default_scope(project)
        policies = _policy(Path(policy_path) if policy_path else default_policy_path(project))
    else:
        requested = tuple(scope)
        if not requested or len(set(requested)) != len(requested) or any(not isinstance(code, str) for code in requested):
            raise QueueError("scope must be a non-empty unique country-code list")
        policies = _policy(Path(policy_path) if policy_path else default_policy_path(project))

    for code in requested:
        entry = indexed.get(code)
        if policies is not None:
            policy = policies.get(code)
            if not isinstance(policy, dict) or not isinstance(policy.get("enabled_for_localization"), bool):
                raise QueueError(f"country policy is incomplete for {code}")
            if not policy["enabled_for_localization"]:
                records.append({"country_code": code, "selected": False, "reason": "LOCALIZATION_DISABLED"})
                continue
        if entry is None:
            records.append({"country_code": code, "selected": False, "reason": "NOT_ENROLLED"})
            continue
        admission_path = _inside(project, entry["admission_path"])
        if not admission_path.is_file() or _sha(admission_path) != entry["admission_sha256"]:
            records.append({"country_code": code, "selected": False, "reason": "ADMISSION_EVIDENCE_CHANGED"})
            continue
        try:
            validated = localization_admission.validate(admission_path, project_root=project, output_root=output)
            admitted_day = date.fromisoformat(_read(admission_path)["source_business_date"])
            if admitted_day > today:
                raise QueueError("admission is from a future business date")
            records.append({"country_code": code, "selected": bool(entry["active"]),
                            "reason": None if entry["active"] else "INDEX_INACTIVE",
                            "admission_path": entry["admission_path"],
                            "delivery_manifest_sha256": validated["delivery_manifest_sha256"],
                            "language_pack": validated["language_pack"], "pack_version": validated["pack_version"],
                            "pack_sha256": validated["pack_sha256"]})
        except (localization_admission.AdmissionError, QueueError, KeyError, ValueError) as exc:
            records.append({"country_code": code, "selected": False, "reason": f"ADMISSION_HOLD:{exc}"})
    rank = {code: i for i, code in enumerate(requested if scope is not None else active_rollout.ACTIVE_COUNTRIES)}
    records.sort(key=lambda item: rank.get(item["country_code"], len(rank)))
    result = {"schema": "p002-localization-default-queue/v1", "status": "PASS", "business_date": business_date,
            "index_sha256": _sha(index_path), "selected": [r["country_code"] for r in records if r["selected"]],
            "held": [r for r in records if not r["selected"]], "records": records}
    if rollout_sha256 is not None:
        result["rollout_sha256"] = rollout_sha256
    return result


def write_receipt(*, project_root: Path, output_root: Path, business_date: str,
                  index_path: Path, work_root: Path,
                  scope: tuple[str, ...] | list[str] | None = None,
                  policy_path: Path | None = None) -> dict[str, Any]:
    result = select(project_root=project_root, output_root=output_root, business_date=business_date,
                    index_path=index_path, scope=scope, policy_path=policy_path)
    target = Path(work_root) / "localization" / date.fromisoformat(business_date).strftime("%d-%m-%Y") / "queue" / "default-localization-queue.json"
    data = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != data:
        raise QueueError("queue receipt already exists with different bytes")
    if not target.exists():
        target.write_bytes(data)
    return {**result, "receipt_path": str(target)}
