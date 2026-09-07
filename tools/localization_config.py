"""Country-localization policy resolver.

The sheet-backed registry decides *which* country and language are in scope;
this small policy file decides the stable local delivery folder and explicit
metadata overlay.  Keeping those concerns separate prevents a sheet reorder
from moving a delivered country tree.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "language" / "country-locale-registry.json"
POLICY_PATH = REPO_ROOT / "config" / "localization-country-policy.json"
ROLLOUT_PATH = REPO_ROOT / "config" / "localization-rollout-20.json"
_FOLDER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")
_ID = re.compile(r"[A-Z]{2}")
_STYLE = re.compile(r"[A-Z]")
_ASSET = re.compile(r"[A-Z][A-Z0-9_]*")


class LocalizationConfigError(ValueError):
    pass


def delivery_article_path(style: str, asset: str) -> str:
    """Return the one canonical public path below a country folder.

    Article identity remains ``D-XAUUSD`` in receipts; the delivery tree is
    deliberately more readable as ``D/XAUUSD/article.md``.  Keeping this in
    the country config avoids each packager or writer inventing its own layout.
    """
    if not isinstance(style, str) or not _STYLE.fullmatch(style.upper()):
        raise LocalizationConfigError("style must be one uppercase letter")
    if not isinstance(asset, str) or not _ASSET.fullmatch(asset.upper()):
        raise LocalizationConfigError("asset must be a canonical uppercase symbol")
    return f"{style.upper()}/{asset.upper()}/article.md"


def _read(path: Path) -> dict:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalizationConfigError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(result, dict):
        raise LocalizationConfigError(f"{path.name} must contain an object")
    return result


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_country(country_code: str, *, registry_path: Path = REGISTRY_PATH,
                    policy_path: Path = POLICY_PATH, rollout_path: Path | None = None) -> dict:
    if not isinstance(country_code, str) or not _ID.fullmatch(country_code):
        raise LocalizationConfigError("country_code must be two uppercase letters")
    registry = _read(registry_path)
    active_rollout = Path(rollout_path) if rollout_path else (ROLLOUT_PATH if Path(registry_path).resolve() == REGISTRY_PATH.resolve() else None)
    if active_rollout:
        rollout = _read(active_rollout)
        if (rollout.get("schema") != "p002-localization-rollout/v1"
                or rollout.get("country_count") != len(rollout.get("countries", []))
                or country_code not in rollout.get("countries", [])):
            raise LocalizationConfigError(f"country {country_code} is outside the active rollout")
    matches = [item for item in registry.get("countries", [])
               if isinstance(item, dict) and item.get("country_code") == country_code]
    if len(matches) != 1:
        raise LocalizationConfigError(f"country {country_code} is absent or duplicated in registry")
    policy_doc = _read(policy_path)
    if policy_doc.get("schema") != "p002-localization-country-policy/v1":
        raise LocalizationConfigError("unsupported localization country policy schema")
    policy = (policy_doc.get("countries") or {}).get(country_code)
    if not isinstance(policy, dict):
        raise LocalizationConfigError(f"country {country_code} has no explicit localization policy")
    required = ("output_folder", "metadata_country", "metadata_language", "slug_suffix",
                "link_policy", "enabled_for_localization")
    if any(key not in policy for key in required):
        raise LocalizationConfigError(f"country {country_code} policy is incomplete")
    folder = policy["output_folder"]
    if (not isinstance(folder, str) or not _FOLDER.fullmatch(folder)
            or folder.upper() in {"CON", "PRN", "AUX", "NUL"}):
        raise LocalizationConfigError(f"unsafe output_folder for {country_code}")
    if policy["link_policy"] != "preserve_source_thai":
        raise LocalizationConfigError(f"unsupported link_policy for {country_code}")
    if not isinstance(policy["enabled_for_localization"], bool):
        raise LocalizationConfigError(f"enabled_for_localization must be boolean for {country_code}")
    return {
        **matches[0], **policy,
        "registry_sha256": _digest(registry_path),
        "policy_sha256": _digest(policy_path),
        "rollout_sha256": _digest(active_rollout) if active_rollout else None,
    }


def require_manifest_country(manifest: dict) -> dict:
    country = resolve_country(manifest.get("country_code"))
    for key in ("content_locale", "language_pack"):
        if manifest.get(key) != country[key]:
            raise LocalizationConfigError(f"manifest {key} does not match country registry")
    if manifest.get("country_policy_sha256") not in {None, country["policy_sha256"]}:
        raise LocalizationConfigError("manifest country_policy_sha256 is stale")
    return country
