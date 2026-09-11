"""Verifier for the user-approved 20-country rollout.

The historical 34-country sheet registry remains available for provenance.
This module reads the separate active rollout file and never rewrites either
registry, preventing sheet rank and rollout order from being mixed.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROLLOUT_PATH = REPO_ROOT / "config" / "localization-rollout-20.json"
COUNTRY_REGISTRY_PATH = REPO_ROOT / "language" / "country-locale-registry.json"
POLICY_PATH = REPO_ROOT / "config" / "localization-country-policy.json"

ACTIVE_COUNTRIES = (
    "TH", "MY", "BR", "AR", "CL", "RU", "MX", "ZA", "NG", "SG",
    "SA", "AE", "CO", "KE", "PH", "KR", "IN", "TR", "PK", "BD",
)


class RolloutRegistryError(ValueError):
    pass


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RolloutRegistryError(f"cannot read registry: {path}") from exc


def load_active(path: Path = ROLLOUT_PATH) -> dict:
    data = _read(Path(path))
    countries = tuple(data.get("countries") or ())
    if countries != ACTIVE_COUNTRIES or len(set(countries)) != 20:
        raise RolloutRegistryError("active rollout must match the exact 20-country list")
    statuses = data.get("delivery_status")
    if not isinstance(statuses, dict) or set(statuses) != set(ACTIVE_COUNTRIES):
        raise RolloutRegistryError("active rollout status keys do not match country list")
    if data.get("country_count") != 20:
        raise RolloutRegistryError("active rollout country_count must be 20")
    return data


def country_record(code: str, path: Path = COUNTRY_REGISTRY_PATH) -> dict:
    if code not in ACTIVE_COUNTRIES:
        raise RolloutRegistryError(f"country is outside active rollout: {code}")
    data = _read(Path(path))
    matches = [item for item in data.get("countries", [])
               if item.get("country_code") == code]
    if len(matches) != 1:
        raise RolloutRegistryError(f"missing or duplicate country provenance: {code}")
    return matches[0]


def requested_selection(codes: list[str] | tuple[str, ...], *,
                        rollout_path: Path = ROLLOUT_PATH,
                        policy_path: Path = POLICY_PATH) -> dict:
    """Describe a requested country batch without claiming delivery or admission.

    The rollout file records the user's ordering and historical status.  It is
    deliberately not delivery evidence, so a runner must consume this report
    as four separate states rather than treating a requested country as ready.
    """
    rollout = load_active(rollout_path)
    if not isinstance(codes, (list, tuple)) or not codes:
        raise RolloutRegistryError("requested countries must be a non-empty list")
    if any(not isinstance(code, str) or code not in ACTIVE_COUNTRIES for code in codes):
        raise RolloutRegistryError("requested country is outside active rollout")
    if len(set(codes)) != len(codes):
        raise RolloutRegistryError("requested countries must not contain duplicates")

    policies = _read(Path(policy_path)).get("countries")
    if not isinstance(policies, dict):
        raise RolloutRegistryError("country policy is malformed")
    rows = []
    for code in codes:
        record = country_record(code)
        policy = policies.get(code)
        if not isinstance(policy, dict) or not isinstance(policy.get("enabled_for_localization"), bool):
            raise RolloutRegistryError(f"country policy is incomplete: {code}")
        # Thailand is the source country; it is eligible even though it is not
        # a localization target.  Every other country needs the explicit flag.
        eligible = code == "TH" or policy["enabled_for_localization"]
        rows.append({
            "country_code": code,
            "content_locale": record["content_locale"],
            "language_pack": record["language_pack"],
            "output_folder": policy["output_folder"],
            "requested": True,
            "eligible": eligible,
            "rollout_status": rollout["delivery_status"][code],
            "delivered": "UNVERIFIED",
            "admitted": "UNVERIFIED",
            "hold_reason": None if eligible else "LOCALIZATION_DISABLED",
        })
    return {
        "schema": "p002-requested-country-selection/v1",
        "requested": list(codes),
        "eligible": [row["country_code"] for row in rows if row["eligible"]],
        "held": [row["country_code"] for row in rows if not row["eligible"]],
        "countries": rows,
    }
