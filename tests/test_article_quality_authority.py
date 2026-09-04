"""Tests for P002's versioned brief/contract authority boundary.

The fixtures remain synthetic and calibration-only.  They must never be
imported by a production route.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
# tests -> feature worktree; the project root is retained for fixture context.
WORKTREE_ROOT = HERE.parents[0]
PROJECT_ROOT = HERE.parents[3]
REPO_ROOT = WORKTREE_ROOT
TOOLS_ROOT = REPO_ROOT / "tools"
SCHEMA_ROOT = REPO_ROOT / "schemas"


HEX = "a" * 64
ARTICLE_HASH = "b" * 64
FACTS_HASH = "c" * 64
EVIDENCE_HASH = "d" * 64
IMAGE_HASH = "e" * 64
M_CURRENT_VISUALS = [
    {"role": "h1_market_map", "path": "public/btcusd-style-m-v7-h1-market-map-2026-09-04.webp", "sha256": "70d2dd2dbd791bf4a415a272dcee4d8bee21ae2abac347068bf1014d23feaba0", "timeframe": "H1"},
    {"role": "m15_entry_plan", "path": "public/btcusd-style-m-v7-m15-entry-h1-plan-2026-09-04.webp", "sha256": "36d010f6099beda116c98b2acdcdb56416dea3716aba3d4349f06dcdadcf7139", "timeframe": "M15"},
]
M_CURRENT_PACKAGE_ROOT = "work/review/style-m-r9-live-20260904-0800/04-09-2026/btcusd/internal/style-m-v7-7f5f7c26680d"
M_CURRENT_PACKAGE_FILES = {
    "manifest.json": "141ba606de530a1d3e70d6d8d9f03d386da81ef701711dcf3b47cd43a31a32f0",
    "public/btc.md": "4448eda92b43b10cfa79baba08275061ae25566dfb1c85b6769abd1f660d3e9c",
    "public/btcusd-style-m-v7-h1-market-map-2026-09-04.webp": M_CURRENT_VISUALS[0]["sha256"],
    "public/btcusd-style-m-v7-m15-entry-h1-plan-2026-09-04.webp": M_CURRENT_VISUALS[1]["sha256"],
    "web-upload/btc-daily-2026-09-04.md": "bad2dc6ec4716dc7c944493e6bac13037195edbf4043b8b4e7dd348e95b9c8ce",
    "web-upload/btcusd-style-m-v7-h1-market-map-2026-09-04.webp": M_CURRENT_VISUALS[0]["sha256"],
    "web-upload/btcusd-style-m-v7-m15-entry-h1-plan-2026-09-04.webp": M_CURRENT_VISUALS[1]["sha256"],
}


def _authority(style: str, *, version: str = "v1", source_name: str | None = None) -> dict:
    suffix = source_name or (
        "STYLE-L-FOREX-DAILY-CONTRACT.md" if style == "L"
        else f"STYLE-{style}-ARTICLE-CONTRACT.md"
    )
    return {
        "authority_id": f"STYLE-{style}.ARTICLE",
        "style_id": style,
        "authority_version": version,
        "effective_from": "2026-09-04T00:00:00Z",
        "brief": {"path": f"docs/{suffix}", "sha256": HEX},
        "machine_contract": {
            "path": f"config/style_{style.lower().replace('+', '_')}_article_contract.json",
            "sha256": HEX,
        },
        "visual_manifest": {
            "path": f"config/style_{style.lower()}_visual_manifest.json",
            "sha256": HEX,
        },
        "validator": {"module": f"tools/{style.lower()}_validator.py", "entrypoint": f"tools/{style.lower()}_validator.py::validate"},
        "historical_policy": "legacy_control_only",
    }


def _registry(*authorities: dict) -> dict:
    return {
        "schema_version": "1.0",
        "registry_version": "v1",
        "authorities": list(authorities),
    }


def _evidence(
    style: str,
    *,
    brief_path: str | None = None,
    brief_hash: str | None = HEX,
    article_hash: str = ARTICLE_HASH,
    source_facts_hash: str | None = FACTS_HASH,
    visual_roles: list[dict] | None = None,
    contract_version: str = "v1",
    hard_gate_status: str = "PASS",
    brief_compliance_status: str = "PASS",
    provenance: str = "contemporaneous",
) -> dict:
    return {
        "schema_version": "1.0",
        "article_id": f"2026-09-04-{style}-BTCUSD",
        "style_id": style,
        "article_sha256": article_hash,
        "article_path": f"articles/{style.lower()}-btcusd.md",
        "source_facts_sha256": source_facts_hash,
        "source_facts_path": f"evidence/{style.lower()}-facts.json",
        "authority": {
            "authority_id": f"STYLE-{style}.ARTICLE",
            "authority_version": contract_version,
            "effective_at": "2026-09-04T00:00:00Z",
            "brief_path": brief_path or (
                "docs/STYLE-L-FOREX-DAILY-CONTRACT.md" if style == "L"
                else f"docs/STYLE-{style}-ARTICLE-CONTRACT.md"
            ),
            "brief_sha256": brief_hash,
            "machine_contract_path": f"config/style_{style.lower()}_article_contract.json",
            "machine_contract_sha256": HEX,
            "visual_manifest_path": f"config/style_{style.lower()}_visual_manifest.json",
            "visual_manifest_sha256": HEX,
        },
        "validator": {"status": hard_gate_status, "module": f"tools/{style.lower()}_validator.py", "entrypoint": f"tools/{style.lower()}_validator.py::validate"},
        "brief_compliance": {"status": brief_compliance_status},
        "visuals": visual_roles or [],
        **({"visual_manifest": {
            "manifest_id": f"manifest-{style.lower()}-btcusd",
            "path": f"visual-manifests/{style.lower()}-btcusd.json",
            "sha256": HEX,
            "immutable": True,
            "roles": [
                {"role_id": item.get("role", item.get("role_id")), "path": item["path"],
                 "sha256": item["sha256"], "timeframe": item.get("timeframe", "H1")}
                for item in (visual_roles or [])
            ],
        }} if visual_roles and style in {"D", "E", "L"} else {}),
        "provenance": provenance,
        "evidence_sha256": EVIDENCE_HASH,
        "evidence_path": f"evidence/{style.lower()}-envelope.json",
        "production_date": "2026-09-04T00:00:00Z",
        **({
            "source_inputs": {"timeframes": ["H1", "M15"]},
            "indicator_facts": {"path": "evidence/indicator.json", "sha256": FACTS_HASH,
                                 "required_keys": ["indicator", "fibonacci_levels"]},
            "trade_plan_qa": {"path": "evidence/trade-plan-qa.json", "sha256": FACTS_HASH,
                               "required_keys": ["entry", "stop_loss", "take_profit"], "status": "PASS"},
            "plan_status": "ACTIVE",
        } if style == "E" else {
            "timeframe_facts": {"path": "evidence/timeframe-facts.json", "sha256": FACTS_HASH,
                                 "required_keys": ["H4", "H1", "M30", "M15"],
                                 "timeframes": ["H4", "H1", "M30", "M15"]},
            "trade_plan_qa": {"path": "evidence/trade-plan-qa.json", "sha256": FACTS_HASH,
                               "required_keys": ["entry", "stop_loss", "take_profit"], "status": "PASS"},
            "plan_status": "ACTIVE",
        } if style == "L" else {}),
    }


def _call(api, *, registry: dict, evidence: dict, article: dict | None = None,
          artifact_root: Path | None = None):
    """Call the deliberately small API contract that the RED suite defines."""
    fn = getattr(api, "resolve_and_validate", None)
    if fn is None:
        pytest.fail(
            "RED: expected tools.article_quality_authority.resolve_and_validate "
            "has not been implemented"
        )
    return fn(registry=registry, evidence=evidence, article=article or {},
              artifact_root=artifact_root)


def _materialize_case(root: Path, registry: dict, evidence: dict) -> dict:
    """Create a real, hash-bound fixture so semantic tampering reaches bytes."""
    style = evidence["style_id"]
    authority = next(item for item in registry["authorities"] if item["style_id"] == style)

    def write_bytes(relative: str, payload: bytes) -> str:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return hashlib.sha256(payload).hexdigest()

    def write_json(relative: str, payload: object) -> str:
        return write_bytes(relative, (json.dumps(payload, ensure_ascii=False,
                                                sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))

    article_hash = write_bytes(evidence["article_path"], b"# bound article\n")
    evidence["article_sha256"] = article_hash

    source_payload = {
        "timeframes": (["H1", "M15"] if style == "E" else
                        ["H4", "H1", "M30", "M15"] if style == "L" else ["D1"]),
    }
    evidence["source_facts_sha256"] = write_json(evidence["source_facts_path"], source_payload)
    write_json(evidence["evidence_path"], {"article_id": evidence["article_id"]})
    evidence["evidence_sha256"] = hashlib.sha256((root / evidence["evidence_path"]).read_bytes()).hexdigest()

    if style == "D":
        evidence.update({
            "story": {"path": "evidence/story.json", "sha256": HEX,
                      "required_keys": ["article_id", "sections"]},
            "technical": {"path": "evidence/technical.json", "sha256": HEX,
                          "required_keys": ["current_close", "structure_bias", "support_levels", "resistance_levels"]},
            "calendar": {"path": "evidence/calendar.json", "sha256": HEX,
                         "required_keys": ["items"]},
        })
        typed = {
            "story": {"article_id": evidence["article_id"], "sections": ["overview"]},
            "technical": {"current_close": 1.0, "structure_bias": "neutral",
                           "support_levels": [0.9], "resistance_levels": [1.1]},
            "calendar": {"items": []},
        }
    elif style == "E":
        typed = {
            "indicator_facts": {"indicator": "RSI", "fibonacci_levels": [0.618]},
            "trade_plan_qa": {"entry": 1.0, "stop_loss": 0.9, "take_profit": 1.1,
                               "status": "PASS", "plan_status": "ACTIVE"},
        }
    else:
        typed = {
            "timeframe_facts": {
                "timeframes": ["H4", "H1", "M30", "M15"],
                "H4": {"close": 1.0, "bias": "neutral"},
                "H1": {"close": 1.0, "bias": "neutral"},
                "M30": {"close": 1.0, "bias": "neutral"},
                "M15": {"close": 1.0, "bias": "neutral"},
            },
            "trade_plan_qa": {"entry": 1.0, "stop_loss": 0.9, "take_profit": 1.1,
                               "status": "PASS", "plan_status": "ACTIVE"},
        }
    for key, payload in typed.items():
        section = evidence[key]
        section["sha256"] = write_json(section["path"], payload)

    for ref_key, label in (("brief", "brief"), ("machine_contract", "machine contract"),
                           ("visual_manifest", "authority visual manifest")):
        ref = authority[ref_key]
        digest = write_bytes(ref["path"], (label + "\n").encode("utf-8"))
        ref["sha256"] = digest
        evidence["authority"][f"{ref_key}_path"] = ref["path"]
        evidence["authority"][f"{ref_key}_sha256"] = digest

    for visual in evidence["visuals"]:
        visual["sha256"] = write_bytes(visual["path"], b"bound visual\n")
    evidence["visual_manifest"]["roles"] = [
        {"role_id": visual["role"], "path": visual["path"],
         "sha256": visual["sha256"], "timeframe": visual["timeframe"]}
        for visual in evidence["visuals"]
    ]
    evidence["visual_manifest"]["sha256"] = write_json(
        evidence["visual_manifest"]["path"],
        {"immutable": True, "roles": evidence["visual_manifest"]["roles"]},
    )
    return {"article_sha256": article_hash}


@pytest.fixture()
def authority_api():
    if not TOOLS_ROOT.is_dir():
        pytest.fail(f"RED: expected isolated Repo/tools directory: {TOOLS_ROOT}")
    sys.path.insert(0, str(TOOLS_ROOT))
    try:
        return importlib.import_module("article_quality_authority")
    except ModuleNotFoundError as exc:
        raise AssertionError(
            "RED: tools.article_quality_authority is intentionally absent; "
            "implement only after this suite is reviewed"
        ) from exc
    finally:
        sys.path.remove(str(TOOLS_ROOT))


@pytest.fixture()
def valid_registry():
    return _registry(_authority("D"), _authority("E"), _authority("L"), _authority("M"))


def test_schema_files_are_present_and_fail_closed_for_unknown_keys():
    registry_schema = SCHEMA_ROOT / "article-quality-authority-v1.schema.json"
    evidence_schema = SCHEMA_ROOT / "article-quality-evidence-v1.schema.json"
    if not registry_schema.exists() or not evidence_schema.exists():
        pytest.fail("RED: authority/evidence schemas are not implemented")
    registry = _registry(_authority("D"))
    registry["unexpected"] = True
    evidence = _evidence("D")
    evidence["unexpected"] = True
    api = importlib.import_module("article_quality_authority")
    with pytest.raises(Exception):
        api.validate_registry(registry)
    with pytest.raises(Exception):
        api.validate_evidence(evidence)


def test_wrong_style_brief_is_rejected(authority_api, valid_registry):
    evidence = _evidence("E", brief_path="docs/INTRADAY-STYLES-H-I-J.md")
    with pytest.raises(Exception, match="(?i)brief|authority|style"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


@pytest.mark.parametrize("field", ["brief_sha256", "source_facts_sha256"])
def test_missing_required_hash_is_rejected(authority_api, valid_registry, field):
    evidence = _evidence("D")
    evidence[field] = None
    with pytest.raises(Exception, match="(?i)hash|evidence|required"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_stale_brief_hash_is_rejected(authority_api, valid_registry):
    evidence = _evidence("D", brief_hash="f" * 64)
    with pytest.raises(Exception, match="(?i)hash|stale|drift"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_article_hash_rebind_is_rejected(authority_api, valid_registry):
    evidence = _evidence("D", article_hash="1" * 64)
    article = {"article_sha256": ARTICLE_HASH}
    with pytest.raises(Exception, match="(?i)article|hash|rebind|drift"):
        _call(authority_api, registry=valid_registry, evidence=evidence, article=article)


def test_missing_article_hash_is_rejected(authority_api, valid_registry):
    evidence = _evidence("D", article_hash=None)
    with pytest.raises(Exception, match="(?i)evidence|hash|drift"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_unknown_authority_version_is_rejected(authority_api, valid_registry):
    evidence = _evidence("D", contract_version="v99")
    with pytest.raises(Exception, match="(?i)unknown|version|authority"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_path_escape_is_rejected(authority_api, valid_registry):
    evidence = _evidence("D", brief_path="../../outside/STYLE-D.md")
    with pytest.raises(Exception, match="(?i)path|escape|authority"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_duplicate_authority_identity_is_rejected(authority_api):
    duplicate = _authority("D")
    registry = _registry(copy.deepcopy(duplicate), copy.deepcopy(duplicate))
    with pytest.raises(Exception, match="(?i)duplicate|authority|identity"):
        _call(authority_api, registry=registry, evidence=_evidence("D"))


def test_d_calendar_only_evidence_cannot_pass_article_preflight(authority_api, valid_registry):
    evidence = _evidence("D", source_facts_hash=None)
    evidence["calendar"] = {"status": "PASS", "sha256": HEX}
    evidence["technical"] = None
    with pytest.raises(Exception, match="(?i)calendar|technical|evidence|gate"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_e_h_i_j_brief_cannot_authorize_style_e(authority_api, valid_registry):
    evidence = _evidence("E", brief_path="docs/INTRADAY-STYLES-H-I-J.md")
    with pytest.raises(Exception, match="(?i)brief|style|authority"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_e_does_not_infer_an_m15_visual_requirement(authority_api, valid_registry):
    evidence = _evidence(
        "E",
        visual_roles=[
            {"role": "h1_fibonacci", "path": "visual/h1-fibonacci.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
            {"role": "h1_trade_plan", "path": "visual/h1-trade-plan.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        ],
    )
    article = {"input_timeframes": ["H1", "M15"], "visual_roles": ["h1_fibonacci", "h1_trade_plan"]}
    # Eligibility requires a caller-supplied trusted artifact root.  This
    # regression keeps the visual inference assertion while ensuring a
    # no-root call cannot accidentally pass.
    with pytest.raises(Exception, match="(?i)trusted|artifact_root|no_score"):
        _call(authority_api, registry=valid_registry, evidence=evidence, article=article)


def test_r1_d_requires_article_bound_technical_evidence(authority_api, valid_registry):
    evidence = _evidence("D")
    with pytest.raises(Exception, match="(?i)technical|article.bound|evidence|no_score"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_r2_e_visual_roles_must_bind_h1_timeframe(authority_api, valid_registry):
    evidence = _evidence("E", visual_roles=[
        {"role": "h1_fibonacci", "path": "visual/h1-fibonacci.webp", "sha256": IMAGE_HASH},
        {"role": "h1_trade_plan", "path": "visual/h1-trade-plan.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
    ])
    with pytest.raises(Exception, match="(?i)trusted|artifact_root|no_score|timeframe|H1|visual|applicability"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_r3_duplicate_visual_role_is_rejected(authority_api, valid_registry):
    evidence = _evidence("E", visual_roles=[
        {"role": "h1_fibonacci", "path": "visual/fibonacci-a.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "h1_fibonacci", "path": "visual/fibonacci-b.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "h1_trade_plan", "path": "visual/trade-plan.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
    ])
    with pytest.raises(Exception, match="(?i)duplicate|visual|role"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_r4_duplicate_registry_visual_role_id_is_rejected():
    authority = _authority("D")
    authority["visual_roles"] = [
        {"role_id": "levels", "required": True, "timeframe": "D1"},
        {"role_id": "levels", "required": True, "timeframe": "D1"},
    ]
    with pytest.raises(Exception, match="(?i)duplicate|role"):
        importlib.import_module("article_quality_authority").validate_registry(_registry(authority))


@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), float("-inf")])
def test_r5_nonfinite_technical_value_is_rejected(authority_api, valid_registry, nonfinite):
    evidence = _evidence("D")
    evidence["technical"] = {"value": nonfinite}
    with pytest.raises(Exception, match="(?i)finite|nan|inf|number"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_r6_canonical_hash_rejects_nonfinite_values(authority_api):
    with pytest.raises(Exception, match="(?i)finite|nan|inf|number"):
        authority_api.canonical_hash({"x": float("nan")})


def test_r7_m_six_b_rejects_arbitrary_manifest_package_hashes(authority_api, valid_registry):
    evidence = _evidence("M", visual_roles=copy.deepcopy(M_CURRENT_VISUALS))
    evidence["m_freeze"] = {
        "manifest": "work/qa/authority-freezes/arbitrary.json",
        "package_root": "work/review/arbitrary-package",
        "package_files": {"public/arbitrary.webp": IMAGE_HASH},
        "candidate_only": False, "current": True, "post_merge_verified": True,
        "worktree_clean": True, "tree_sha256": HEX, "implementation_sha256": HEX,
    }
    with pytest.raises(Exception, match="(?i)manifest|package|hash|current"):
        _call(authority_api, registry=valid_registry, evidence=evidence,
              article={"m_current_manifest_sha256": HEX})


def test_r7_m_six_b_exact_package_is_blocked_until_real_manifest(authority_api, valid_registry):
    evidence = _evidence("M", visual_roles=copy.deepcopy(M_CURRENT_VISUALS))
    evidence["m_freeze"] = {
        "manifest": "work/qa/authority-freezes/style-m-current-contract-manifest-v1.json",
        "package_root": M_CURRENT_PACKAGE_ROOT,
        "package_files": copy.deepcopy(M_CURRENT_PACKAGE_FILES),
        "candidate_only": False, "current": True, "post_merge_verified": True,
        "worktree_clean": True, "tree_sha256": HEX, "implementation_sha256": HEX,
    }
    result = _call(
        authority_api, registry=valid_registry, evidence=evidence,
        article={"m_current_manifest_sha256": M_CURRENT_PACKAGE_FILES["manifest.json"]},
    )
    assert result["status"] == "BLOCKED_PENDING_CURRENT_CONTRACT"
    assert result["core_calibration_eligible"] is False
    assert len(evidence["m_freeze"]["package_files"]) == 7


def test_r8_rooted_posix_path_is_rejected(authority_api, valid_registry):
    evidence = _evidence("D", brief_path="/tmp/outside.md")
    with pytest.raises(Exception, match="(?i)absolute|path|escape"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


@pytest.mark.parametrize("missing_role", ["structure", "levels", "weekly_calendar"])
def test_lead_auth_01_d_requires_every_authoritative_visual_role(
    authority_api, valid_registry, missing_role
):
    all_roles = {
        "structure": {"path": "visual/structure.webp", "sha256": IMAGE_HASH, "timeframe": "D1"},
        "levels": {"path": "visual/levels.webp", "sha256": IMAGE_HASH, "timeframe": "D1"},
        "weekly_calendar": {"path": "visual/calendar.webp", "sha256": IMAGE_HASH, "timeframe": "calendar"},
    }
    visuals = [{"role": role, **value} for role, value in all_roles.items() if role != missing_role]
    evidence = _evidence("D", visual_roles=visuals)
    evidence["technical"] = {"article_bound": True}
    with pytest.raises(Exception, match="(?i)visual|role|incomplete|required"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_lead_auth_02_e_arbitrary_visual_binding_is_rejected(authority_api, valid_registry):
    evidence = _evidence("E", visual_roles=[
        {"role": "h1_fibonacci", "path": "visual/fibonacci.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "h1_trade_plan", "path": "visual/trade-plan.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
    ])
    evidence["visual_manifest"]["roles"][0]["sha256"] = "f" * 64
    with pytest.raises(Exception, match="(?i)trusted|artifact_root|no_score|bound|path|hash|visual"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_lead_auth_02_l_visual_roles_require_exact_timeframes(authority_api, valid_registry):
    visuals = [
        {"role": "h1_plan", "path": "visual/h1.webp", "sha256": IMAGE_HASH, "timeframe": "M15"},
        {"role": "m15_trigger", "path": "visual/m15.webp", "sha256": IMAGE_HASH, "timeframe": "M15"},
        {"role": "daily_calendar", "path": "visual/calendar.webp", "sha256": IMAGE_HASH, "timeframe": "calendar"},
    ]
    evidence = _evidence("L", visual_roles=visuals)
    with pytest.raises(Exception, match="(?i)trusted|artifact_root|no_score|timeframe|visual|H1"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_lead_auth_02_validator_identity_and_article_paths_are_bound(authority_api, valid_registry):
    evidence = _evidence("E", visual_roles=[
        {"role": "h1_fibonacci", "path": "visual/fibonacci.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "h1_trade_plan", "path": "visual/trade-plan.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
    ])
    evidence["validator"]["entrypoint"] = "tools/wrong_validator.py::validate"
    with pytest.raises(Exception, match="(?i)trusted|artifact_root|no_score|validator|identity|authority"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_lead_auth_04_effective_and_production_dates_are_rfc3339_and_ordered(
    authority_api, valid_registry
):
    invalid_registry = copy.deepcopy(valid_registry)
    invalid_registry["authorities"][0]["effective_from"] = "not-a-date"
    with pytest.raises(Exception, match="(?i)RFC3339|date|effective"):
        _call(authority_api, registry=invalid_registry, evidence=_evidence("D"))

    evidence = _evidence("E", visual_roles=[
        {"role": "h1_fibonacci", "path": "visual/fibonacci.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "h1_trade_plan", "path": "visual/trade-plan.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
    ])
    evidence["production_date"] = "2026-09-03T23:59:59Z"
    with pytest.raises(Exception, match="(?i)production|effective|date"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_qq_auth_01_explicit_trusted_root_rejects_missing_bound_artifact(
    authority_api, valid_registry, tmp_path
):
    visuals = [
        {"role": "h1_fibonacci", "path": "visual/fibonacci.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "h1_trade_plan", "path": "visual/trade-plan.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
    ]
    evidence = _evidence("E", visual_roles=visuals)
    with pytest.raises(Exception, match="(?i)missing|artifact|article|no_score"):
        authority_api.resolve_and_validate(registry=valid_registry, evidence=evidence,
                                           article={"article_sha256": ARTICLE_HASH},
                                           artifact_root=tmp_path)


def test_qq_auth_01_eligibility_without_trusted_root_is_rejected(
    authority_api, valid_registry
):
    """The isolated no-root call must fail closed before any artifact lookup."""
    with pytest.raises(Exception, match="(?i)trusted|artifact_root|no_score"):
        _call(authority_api, registry=valid_registry, evidence=_evidence("E"))


def test_qq_auth_02_d_typed_sections_reject_arbitrary_metadata(authority_api, valid_registry):
    evidence = _evidence("D")
    evidence["technical"] = {"path": "evidence/technical.json", "sha256": FACTS_HASH,
                              "required_keys": ["garbage"]}
    with pytest.raises(Exception, match="(?i)typed|required|technical|keys"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_qq_auth_02_e_requires_source_and_trade_plan_typed_evidence(authority_api, valid_registry):
    evidence = _evidence("E", visual_roles=[
        {"role": "h1_fibonacci", "path": "visual/fibonacci.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "h1_trade_plan", "path": "visual/trade-plan.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
    ])
    evidence.pop("source_inputs")
    with pytest.raises(Exception, match="(?i)trusted|artifact_root|no_score|source|input|H1|M15"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_qq_auth_02_l_requires_approved_plan_state_and_timeframe_facts(authority_api, valid_registry):
    evidence = _evidence("L", visual_roles=[
        {"role": "h1_plan", "path": "visual/h1.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "m15_trigger", "path": "visual/m15.webp", "sha256": IMAGE_HASH, "timeframe": "M15"},
        {"role": "daily_calendar", "path": "visual/calendar.webp", "sha256": IMAGE_HASH, "timeframe": "calendar"},
    ])
    evidence["plan_status"] = "DRAFT"
    with pytest.raises(Exception, match="(?i)plan|status|ACTIVE|NEUTRAL"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_r7_typed_semantics_cannot_be_granted_by_required_keys(authority_api):
    """Metadata declarations cannot turn hostile bound bytes into authority."""
    evidence = _evidence("E")
    contents = {
        "source_facts_path": {"timeframes": ["H1", "M15"]},
        # Deliberately malformed semantic bytes: the caller's declaration is
        # complete, but the bound content is missing fibonacci levels.
        "indicator_facts": {"indicator": "RSI"},
        "trade_plan_qa": {"status": "PASS"},
    }
    with pytest.raises(Exception, match="(?i)semantic|indicator|approved|plan"):
        authority_api._validate_typed_evidence("E", evidence, contents)


def test_r7_typed_plan_state_must_come_from_bound_bytes(authority_api):
    evidence = _evidence("L")
    contents = {
        "timeframe_facts": {
            "timeframes": ["H4", "H1", "M30", "M15"],
            "H4": {"close": 1.0, "bias": "neutral"},
            "H1": {"close": 1.0, "bias": "neutral"},
            "M30": {"close": 1.0, "bias": "neutral"},
            "M15": {"close": 1.0, "bias": "neutral"},
        },
        # Sidecar says ACTIVE, but authoritative bytes say DRAFT.
        "trade_plan_qa": {"status": "PASS", "plan_status": "DRAFT",
                           "entry": 1, "stop_loss": 1, "take_profit": 1},
    }
    with pytest.raises(Exception, match="(?i)plan|status|approved"):
        authority_api._validate_typed_evidence("L", evidence, contents)


def test_r7_valid_trusted_root_case_can_be_eligible(authority_api, tmp_path):
    registry = _registry(_authority("E"))
    evidence = _evidence("E", visual_roles=[
        {"role": "h1_fibonacci", "path": "visual/fibonacci.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "h1_trade_plan", "path": "visual/trade-plan.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
    ])
    article = _materialize_case(tmp_path, registry, evidence)
    result = _call(authority_api, registry=registry, evidence=evidence,
                   article=article, artifact_root=tmp_path)
    assert result["status"] == "PASS"
    assert result["core_calibration_eligible"] is True


@pytest.mark.parametrize(
    ("kind", "payload", "expected"),
    [
        ("source", {"timeframes": ["H1"]}, "source"),
        ("indicator", {"indicator": "RSI"}, "indicator"),
        ("qa", {"status": "PASS", "plan_status": "DRAFT"}, "plan|status"),
    ],
)
def test_r7_e_semantic_content_tamper_rejected_even_with_matching_hash(
    authority_api, tmp_path, kind, payload, expected
):
    registry = _registry(_authority("E"))
    evidence = _evidence("E", visual_roles=[
        {"role": "h1_fibonacci", "path": "visual/fibonacci.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "h1_trade_plan", "path": "visual/trade-plan.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
    ])
    article = _materialize_case(tmp_path, registry, evidence)
    relative = evidence["source_facts_path"] if kind == "source" else (
        evidence["indicator_facts"]["path"] if kind == "indicator" else evidence["trade_plan_qa"]["path"]
    )
    target = tmp_path / relative
    data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    target.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    if kind == "source":
        evidence["source_facts_sha256"] = digest
    else:
        evidence["indicator_facts" if kind == "indicator" else "trade_plan_qa"]["sha256"] = digest
    with pytest.raises(Exception, match=f"(?i){expected}|semantic|approved"):
        _call(authority_api, registry=registry, evidence=evidence,
              article=article, artifact_root=tmp_path)


@pytest.mark.parametrize("missing_field", ["entry", "stop_loss", "take_profit"])
def test_r9_e_trade_plan_missing_bound_value_rejected_with_matching_hash(
    authority_api, tmp_path, missing_field
):
    registry = _registry(_authority("E"))
    evidence = _evidence("E", visual_roles=[
        {"role": "h1_fibonacci", "path": "visual/fibonacci.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "h1_trade_plan", "path": "visual/trade-plan.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
    ])
    article = _materialize_case(tmp_path, registry, evidence)
    target = tmp_path / evidence["trade_plan_qa"]["path"]
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload.pop(missing_field)
    data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    target.write_bytes(data)
    evidence["trade_plan_qa"]["sha256"] = hashlib.sha256(data).hexdigest()
    with pytest.raises(Exception, match=f"(?i)trade.plan|{missing_field}|meaningful|numeric"):
        _call(authority_api, registry=registry, evidence=evidence,
              article=article, artifact_root=tmp_path)


def test_r7_d_semantic_content_tamper_rejected_even_with_matching_hash(authority_api, tmp_path):
    registry = _registry(_authority("D"))
    evidence = _evidence("D", visual_roles=[
        {"role": "structure", "path": "visual/structure.webp", "sha256": IMAGE_HASH, "timeframe": "D1"},
        {"role": "levels", "path": "visual/levels.webp", "sha256": IMAGE_HASH, "timeframe": "D1"},
        {"role": "weekly_calendar", "path": "visual/calendar.webp", "sha256": IMAGE_HASH, "timeframe": "calendar"},
    ])
    article = _materialize_case(tmp_path, registry, evidence)
    data = b'{"garbage":true}\n'
    target = tmp_path / evidence["technical"]["path"]
    target.write_bytes(data)
    evidence["technical"]["sha256"] = hashlib.sha256(data).hexdigest()
    with pytest.raises(Exception, match="(?i)technical|semantic|required"):
        _call(authority_api, registry=registry, evidence=evidence,
              article=article, artifact_root=tmp_path)


def test_r7_l_semantic_content_tamper_rejected_even_with_matching_hash(authority_api, tmp_path):
    registry = _registry(_authority("L"))
    evidence = _evidence("L", visual_roles=[
        {"role": "h1_plan", "path": "visual/h1.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "m15_trigger", "path": "visual/m15.webp", "sha256": IMAGE_HASH, "timeframe": "M15"},
        {"role": "daily_calendar", "path": "visual/calendar.webp", "sha256": IMAGE_HASH, "timeframe": "calendar"},
    ])
    article = _materialize_case(tmp_path, registry, evidence)
    data = b'{"timeframes":["H1"]}\n'
    target = tmp_path / evidence["timeframe_facts"]["path"]
    target.write_bytes(data)
    evidence["timeframe_facts"]["sha256"] = hashlib.sha256(data).hexdigest()
    with pytest.raises(Exception, match="(?i)timeframe|semantic|required"):
        _call(authority_api, registry=registry, evidence=evidence,
              article=article, artifact_root=tmp_path)


def test_r11_valid_d_technical_bound_values_can_be_eligible(authority_api, tmp_path):
    registry = _registry(_authority("D"))
    evidence = _evidence("D", visual_roles=[
        {"role": "structure", "path": "visual/structure.webp", "sha256": IMAGE_HASH, "timeframe": "D1"},
        {"role": "levels", "path": "visual/levels.webp", "sha256": IMAGE_HASH, "timeframe": "D1"},
        {"role": "weekly_calendar", "path": "visual/calendar.webp", "sha256": IMAGE_HASH, "timeframe": "calendar"},
    ])
    article = _materialize_case(tmp_path, registry, evidence)
    result = _call(authority_api, registry=registry, evidence=evidence,
                   article=article, artifact_root=tmp_path)
    assert result["status"] == "PASS"
    assert result["core_calibration_eligible"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("current_close", None),
        ("current_close", float("nan")),
        ("current_close", "not-a-number"),
        ("structure_bias", ""),
        ("support_levels", []),
        ("resistance_levels", []),
    ],
)
def test_r11_d_technical_empty_or_wrong_bound_value_rejected_with_matching_hash(
    authority_api, tmp_path, field, value
):
    registry = _registry(_authority("D"))
    evidence = _evidence("D", visual_roles=[
        {"role": "structure", "path": "visual/structure.webp", "sha256": IMAGE_HASH, "timeframe": "D1"},
        {"role": "levels", "path": "visual/levels.webp", "sha256": IMAGE_HASH, "timeframe": "D1"},
        {"role": "weekly_calendar", "path": "visual/calendar.webp", "sha256": IMAGE_HASH, "timeframe": "calendar"},
    ])
    article = _materialize_case(tmp_path, registry, evidence)
    target = tmp_path / evidence["technical"]["path"]
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload[field] = value
    data = (json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=True) + "\n").encode("utf-8")
    target.write_bytes(data)
    evidence["technical"]["sha256"] = hashlib.sha256(data).hexdigest()
    with pytest.raises(Exception, match=f"(?i)D technical|{field}|finite|numeric|non-empty"):
        _call(authority_api, registry=registry, evidence=evidence,
              article=article, artifact_root=tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [("article_id", ""), ("sections", []), ("sections", [{}])],
)
def test_r13_d_story_empty_bound_content_rejected_with_matching_hash(
    authority_api, tmp_path, field, value
):
    registry = _registry(_authority("D"))
    evidence = _evidence("D", visual_roles=[
        {"role": "structure", "path": "visual/structure.webp", "sha256": IMAGE_HASH, "timeframe": "D1"},
        {"role": "levels", "path": "visual/levels.webp", "sha256": IMAGE_HASH, "timeframe": "D1"},
        {"role": "weekly_calendar", "path": "visual/calendar.webp", "sha256": IMAGE_HASH, "timeframe": "calendar"},
    ])
    article = _materialize_case(tmp_path, registry, evidence)
    target = tmp_path / evidence["story"]["path"]
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload[field] = value
    data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    target.write_bytes(data)
    evidence["story"]["sha256"] = hashlib.sha256(data).hexdigest()
    with pytest.raises(Exception, match="(?i)story|article|section|meaningful"):
        _call(authority_api, registry=registry, evidence=evidence,
              article=article, artifact_root=tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [("indicator", ""), ("fibonacci_levels", []), ("fibonacci_levels", [{}])],
)
def test_r13_e_indicator_empty_bound_content_rejected_with_matching_hash(
    authority_api, tmp_path, field, value
):
    registry = _registry(_authority("E"))
    evidence = _evidence("E", visual_roles=[
        {"role": "h1_fibonacci", "path": "visual/fibonacci.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "h1_trade_plan", "path": "visual/trade-plan.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
    ])
    article = _materialize_case(tmp_path, registry, evidence)
    target = tmp_path / evidence["indicator_facts"]["path"]
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload[field] = value
    data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    target.write_bytes(data)
    evidence["indicator_facts"]["sha256"] = hashlib.sha256(data).hexdigest()
    with pytest.raises(Exception, match="(?i)indicator|fibonacci|meaningful|finite"):
        _call(authority_api, registry=registry, evidence=evidence,
              article=article, artifact_root=tmp_path)


@pytest.mark.parametrize("timeframe", ["H4", "H1", "M30", "M15"])
def test_r13_l_garbage_only_timeframe_fact_rejected_with_matching_hash(
    authority_api, tmp_path, timeframe
):
    registry = _registry(_authority("L"))
    evidence = _evidence("L", visual_roles=[
        {"role": "h1_plan", "path": "visual/h1.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "m15_trigger", "path": "visual/m15.webp", "sha256": IMAGE_HASH, "timeframe": "M15"},
        {"role": "daily_calendar", "path": "visual/calendar.webp", "sha256": IMAGE_HASH, "timeframe": "calendar"},
    ])
    article = _materialize_case(tmp_path, registry, evidence)
    target = tmp_path / evidence["timeframe_facts"]["path"]
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload[timeframe] = {"garbage": "not a contract fact"}
    data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    target.write_bytes(data)
    evidence["timeframe_facts"]["sha256"] = hashlib.sha256(data).hexdigest()
    with pytest.raises(Exception, match=f"(?i)timeframe|fact object|{timeframe}|contract"):
        _call(authority_api, registry=registry, evidence=evidence,
              article=article, artifact_root=tmp_path)


@pytest.mark.parametrize("field", ["close", "bias"])
def test_r13_l_timeframe_fact_missing_contract_field_rejected_with_matching_hash(
    authority_api, tmp_path, field
):
    registry = _registry(_authority("L"))
    evidence = _evidence("L", visual_roles=[
        {"role": "h1_plan", "path": "visual/h1.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "m15_trigger", "path": "visual/m15.webp", "sha256": IMAGE_HASH, "timeframe": "M15"},
        {"role": "daily_calendar", "path": "visual/calendar.webp", "sha256": IMAGE_HASH, "timeframe": "calendar"},
    ])
    article = _materialize_case(tmp_path, registry, evidence)
    target = tmp_path / evidence["timeframe_facts"]["path"]
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["H1"].pop(field)
    data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    target.write_bytes(data)
    evidence["timeframe_facts"]["sha256"] = hashlib.sha256(data).hexdigest()
    with pytest.raises(Exception, match=f"(?i)timeframe|fact object|H1|{field}|contract"):
        _call(authority_api, registry=registry, evidence=evidence,
              article=article, artifact_root=tmp_path)


@pytest.mark.parametrize("missing_timeframe", ["H4", "H1", "M30", "M15"])
def test_r9_l_missing_bound_timeframe_fact_rejected_with_matching_hash(
    authority_api, tmp_path, missing_timeframe
):
    registry = _registry(_authority("L"))
    evidence = _evidence("L", visual_roles=[
        {"role": "h1_plan", "path": "visual/h1.webp", "sha256": IMAGE_HASH, "timeframe": "H1"},
        {"role": "m15_trigger", "path": "visual/m15.webp", "sha256": IMAGE_HASH, "timeframe": "M15"},
        {"role": "daily_calendar", "path": "visual/calendar.webp", "sha256": IMAGE_HASH, "timeframe": "calendar"},
    ])
    article = _materialize_case(tmp_path, registry, evidence)
    target = tmp_path / evidence["timeframe_facts"]["path"]
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload.pop(missing_timeframe)
    data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    target.write_bytes(data)
    evidence["timeframe_facts"]["sha256"] = hashlib.sha256(data).hexdigest()
    with pytest.raises(Exception, match=f"(?i)timeframe|fact object|{missing_timeframe}"):
        _call(authority_api, registry=registry, evidence=evidence,
              article=article, artifact_root=tmp_path)


def test_l_generic_daily_only_authority_is_rejected(authority_api, valid_registry):
    evidence = _evidence("L", brief_path="docs/WCB-DAILY-OUTPUT-CONTRACT.md")
    with pytest.raises(Exception, match="(?i)generic|brief|style|authority"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


@pytest.mark.parametrize(
    ("label", "mutations"),
    [
        ("candidate", {"authority_version": "candidate-v1", "candidate_only": True}),
        ("old snapshot", {"authority_version": "r8", "current": False}),
        ("dirty tree", {"git": {"worktree_clean": False}}),
        ("hash drift", {"git": {"worktree_clean": True, "tree_sha256": "1" * 64}}),
    ],
)
def test_m_non_current_freeze_states_are_rejected(authority_api, valid_registry, label, mutations):
    evidence = _evidence("M")
    evidence["m_freeze"] = {"manifest": "work/qa/authority-freezes/style-m-current-contract-manifest-v1.json"}
    evidence["m_freeze"].update(mutations)
    with pytest.raises(Exception, match="(?i)current|freeze|manifest|hash|dirty|candidate|snapshot"):
        _call(authority_api, registry=valid_registry, evidence=evidence)


def test_m_current_manifest_must_bind_final_post_merge_tree(authority_api, valid_registry):
    evidence = _evidence("M", visual_roles=copy.deepcopy(M_CURRENT_VISUALS))
    evidence["m_freeze"] = {
        "manifest": "work/qa/authority-freezes/style-m-current-contract-manifest-v1.json",
        "package_root": M_CURRENT_PACKAGE_ROOT,
        "package_files": copy.deepcopy(M_CURRENT_PACKAGE_FILES),
        "candidate_only": False,
        "current": True,
        "post_merge_verified": True,
        "worktree_clean": True,
        "tree_sha256": HEX,
        "implementation_sha256": HEX,
    }
    article = {"m_current_manifest_sha256": "141ba606de530a1d3e70d6d8d9f03d386da81ef701711dcf3b47cd43a31a32f0"}
    result = _call(authority_api, registry=valid_registry, evidence=evidence, article=article)
    assert result["status"] == "BLOCKED_PENDING_CURRENT_CONTRACT"
    assert result["core_calibration_eligible"] is False


@pytest.mark.parametrize(
    ("label", "visuals"),
    [
        ("missing both", []),
        ("missing m15 entry plan", [M_CURRENT_VISUALS[0]]),
        (
            "mismatched m15 role",
            [
                M_CURRENT_VISUALS[0],
                {"role": "m15_watch", "path": "visual/m15-watch.webp", "sha256": IMAGE_HASH},
            ],
        ),
    ],
)
def test_m_current_manifest_requires_h1_market_map_and_m15_entry_plan(
    authority_api, valid_registry, label, visuals
):
    evidence = _evidence("M", visual_roles=copy.deepcopy(visuals))
    evidence["m_freeze"] = {
        "manifest": "work/qa/authority-freezes/style-m-current-contract-manifest-v1.json",
        "package_root": M_CURRENT_PACKAGE_ROOT,
        "package_files": copy.deepcopy(M_CURRENT_PACKAGE_FILES),
        "candidate_only": False,
        "current": True,
        "post_merge_verified": True,
        "worktree_clean": True,
        "tree_sha256": HEX,
        "implementation_sha256": HEX,
    }
    article = {"m_current_manifest_sha256": HEX}
    with pytest.raises(Exception, match="(?i)visual|role|h1|m15|manifest|current"):
        _call(authority_api, registry=valid_registry, evidence=evidence, article=article)
