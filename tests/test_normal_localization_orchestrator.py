import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tools import localization_queue, normal_localization_orchestrator as orchestrator


def put(path: Path, value: dict | str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = value.encode("utf-8") if isinstance(value, str) else json.dumps(value).encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def setup_project(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    foreign_scope = ("MY", "BR", "AR", "CL", "RU", "MX", "ZA", "NG", "SG", "SA",
                     "AE", "CO", "KE", "PH", "KR", "IN", "TR", "PK", "BD")
    source = tmp_path / "output/10-09-2026/TH-Thailand/E/XAUUSD/article.md"
    source_hash = put(source, "Thai source 4,414")
    image_one = tmp_path / "output/10-09-2026/TH-Thailand/E/XAUUSD/image-one.webp"
    image_two = tmp_path / "output/10-09-2026/TH-Thailand/E/XAUUSD/image-two.webp"
    image_one_hash = put(image_one, "first image")
    image_two_hash = put(image_two, "second image")
    images = [{"name": "image-one.webp", "path": "output/10-09-2026/TH-Thailand/E/XAUUSD/image-one.webp", "sha256": image_one_hash},
              {"name": "image-two.webp", "path": "output/10-09-2026/TH-Thailand/E/XAUUSD/image-two.webp", "sha256": image_two_hash}]
    image_inventory_hash = hashlib.sha256("\n".join(f"{item['name']}:{item['sha256']}" for item in images).encode("utf-8")).hexdigest()
    claims = tmp_path / "work/localization/10-09-2026/source-bindings-r0003/claims/e-xauusd.json"
    claims_hash = put(claims, {"claims": []})
    bindings = claims.parent.parent / "source-bindings.json"
    put(bindings, {"schema": "p002-source-bindings/v2", "status": "SOURCE_READY", "source_business_date": "2026-09-10", "articles": [{"article_id": "E-XAUUSD", "source_path": "output/10-09-2026/TH-Thailand/E/XAUUSD/article.md", "source_sha256": source_hash, "images": images, "source_images_sha256": image_inventory_hash, "claim_map_path": "claims/e-xauusd.json", "claim_map_sha256": claims_hash}]})
    put(claims.parent.parent / "receipts/E-XAUUSD.json", {"fixture": "source-qa-is-mocked-by-dispatch-tests"})
    policy = tmp_path / "config/localization-country-policy.json"
    countries = {code: {"enabled_for_localization": code != "SA"} for code in foreign_scope}
    put(policy, {"schema": "p002-localization-country-policy/v1", "countries": countries})
    put(tmp_path / "config/localization-rollout-20.json", {
        "schema": "p002-localization-rollout/v1", "country_count": 20,
        "countries": ["TH", *foreign_scope],
        "delivery_status": {code: "pending" for code in ["TH", *foreign_scope]},
    })
    put(tmp_path / "language/country-locale-registry.json", {
        "countries": [{"country_code": code} for code in ["TH", *foreign_scope]],
    })
    admission = tmp_path / "work/admission/za.json"
    admission_hash = put(admission, {"source_business_date": "2026-09-09"})
    index = tmp_path / "work/localization/admission-index.json"
    put(index, {"schema": localization_queue.SCHEMA, "records": [{"country_code": "ZA", "active": True, "admission_path": "work/admission/za.json", "admission_sha256": admission_hash}]})
    return bindings, index, policy, tmp_path / "work"


def recovery_bundle(tmp_path: Path, bindings: Path, *, wrong_hash: bool = False) -> Path:
    source_root = tmp_path / "output/10-09-2026/TH-Thailand/E/XAUUSD"
    stage = tmp_path / "work/localization/10-09-2026/recovery/E-XAUUSD"
    article_hash = put(stage / "article.md", (source_root / "article.md").read_text(encoding="utf-8"))
    image_one_hash = put(stage / "one.webp", (source_root / "image-one.webp").read_text(encoding="utf-8"))
    image_two_hash = put(stage / "two.webp", (source_root / "image-two.webp").read_text(encoding="utf-8"))
    binding = json.loads(bindings.read_text(encoding="utf-8"))
    article = binding["articles"][0]
    files = [{"role": "article", "staged_path": "article.md", "sha256": article_hash},
             {"role": "image", "staged_path": "one.webp", "sha256": image_one_hash},
             {"role": "image", "staged_path": "two.webp", "sha256": image_two_hash}]
    if wrong_hash:
        files[1]["sha256"] = "0" * 64
    bundle = stage / "recovery-bundle.json"
    put(bundle, {"schema": "p002-source-recovery-bundle/v1", "article_id": "E-XAUUSD", "source_business_date": "2026-09-10",
                 "binding_manifest_sha256": hashlib.sha256(bindings.read_bytes()).hexdigest(),
                 "binding_target_paths": {"article": article["source_path"], "images": [item["path"] for item in article["images"]]},
                 "files": files})
    return bundle


def test_dispatch_uses_admission_only_and_holds_unenrolled_independently(tmp_path):
    bindings, index, policy, _ = setup_project(tmp_path)
    validated = {"delivery_manifest_sha256": "a" * 64, "language_pack": "en-001", "pack_version": "0.1.0", "pack_sha256": "b" * 64}
    with patch.object(localization_queue.localization_admission, "validate", return_value=validated), \
         patch.object(orchestrator.source_qa_acceptance, "validate_source_acceptance", return_value={}):
        result = orchestrator.build_dispatch(project_root=tmp_path, business_date="2026-09-10", index_path=index, bindings_path=bindings, policy_path=policy)
    assert result["status"] == "PARTIAL_HELD"
    assert [(job["country_code"], job["article_id"], job["state"]) for job in result["jobs"]] == [("ZA", "E-XAUUSD", "WAITING_WRITER")]
    held = {item["country_code"]: item["reason"] for item in result["queue"]["held"]}
    assert held["MY"] == "NOT_ENROLLED"
    assert held["NG"] == "NOT_ENROLLED"
    assert held["SA"] == "LOCALIZATION_DISABLED"
    assert not (tmp_path / "output/10-09-2026/ZA-South-Africa").exists()


def test_dispatch_does_not_restart_a_country_with_verified_delivery(tmp_path):
    bindings, index, policy, _ = setup_project(tmp_path)
    delivery_manifest = tmp_path / "output/10-09-2026/ZA-South-Africa/manifest.json"
    delivery_hash = put(delivery_manifest, {"country_code": "ZA", "source_business_date": "2026-09-10"})
    queue = {"selected": ["ZA"], "held": [], "index_sha256": "c" * 64,
             "records": [{"country_code": "ZA", "selected": True,
                          "delivery_manifest_sha256": delivery_hash,
                          "admission_path": "work/admission/za.json"}]}
    with patch.object(localization_queue, "select", return_value=queue), \
         patch.object(orchestrator.source_qa_acceptance, "validate_source_acceptance", return_value={}):
        result = orchestrator.build_dispatch(project_root=tmp_path, business_date="2026-09-10",
                                             index_path=index, bindings_path=bindings, policy_path=policy)
    assert result["status"] == "ALREADY_DELIVERED"
    assert result["jobs"] == [{"country_code": "ZA", "state": "ALREADY_DELIVERED",
                                "delivery_manifest_sha256": delivery_hash,
                                "admission_path": "work/admission/za.json"}]


def test_dispatch_is_immutable_and_resumes_same_inputs(tmp_path):
    bindings, index, policy, work = setup_project(tmp_path)
    validated = {"delivery_manifest_sha256": "a" * 64, "language_pack": "en-001", "pack_version": "0.1.0", "pack_sha256": "b" * 64}
    with patch.object(localization_queue.localization_admission, "validate", return_value=validated), \
         patch.object(orchestrator.source_qa_acceptance, "validate_source_acceptance", return_value={}):
        first = orchestrator.write_dispatch(project_root=tmp_path, work_root=work, business_date="2026-09-10", index_path=index, bindings_path=bindings, policy_path=policy)
        second = orchestrator.write_dispatch(project_root=tmp_path, work_root=work, business_date="2026-09-10", index_path=index, bindings_path=bindings, policy_path=policy)
    assert first["resumed"] is False
    assert second["resumed"] is True
    data = json.loads(Path(first["receipt_path"]).read_text(encoding="utf-8"))
    assert data["jobs"][0]["state"] == "WAITING_WRITER"
    assert data["writer_backend"]["status"] in {"UNAVAILABLE", "AGENT_ASSISTED"}


def test_new_business_day_requires_its_own_frozen_binding_and_dispatch(tmp_path):
    bindings, index, policy, work = setup_project(tmp_path)
    source = tmp_path / "output/11-09-2026/TH-Thailand/E/XAUUSD/article.md"
    source_hash = put(source, "Thai source for a new business day")
    claims = tmp_path / "work/localization/11-09-2026/source-bindings-r0001/claims/e-xauusd.json"
    claims_hash = put(claims, {"claims": []})
    next_bindings = claims.parent.parent / "source-bindings.json"
    put(next_bindings, {"schema": "p002-source-bindings/v2", "status": "SOURCE_READY", "source_business_date": "2026-09-11", "articles": [{"article_id": "E-XAUUSD", "source_path": "output/11-09-2026/TH-Thailand/E/XAUUSD/article.md", "source_sha256": source_hash, "claim_map_path": "claims/e-xauusd.json", "claim_map_sha256": claims_hash}]})
    put(claims.parent.parent / "receipts/E-XAUUSD.json", {"fixture": "source-qa-is-mocked-by-dispatch-tests"})
    validated = {"delivery_manifest_sha256": "a" * 64, "language_pack": "en-001", "pack_version": "0.1.0", "pack_sha256": "b" * 64}
    with patch.object(localization_queue.localization_admission, "validate", return_value=validated), \
         patch.object(orchestrator.source_qa_acceptance, "validate_source_acceptance", return_value={}):
        old = orchestrator.write_dispatch(project_root=tmp_path, work_root=work, business_date="2026-09-10", index_path=index, bindings_path=bindings, policy_path=policy)
        fresh = orchestrator.write_dispatch(project_root=tmp_path, work_root=work, business_date="2026-09-11", index_path=index, bindings_path=next_bindings, policy_path=policy)
    assert old["receipt_path"] != fresh["receipt_path"]
    assert fresh["business_date"] == "2026-09-11"
    assert fresh["jobs"][0]["source_path"].startswith("output/11-09-2026/")


def test_dispatch_fails_closed_when_frozen_source_bytes_change(tmp_path):
    bindings, index, policy, _ = setup_project(tmp_path)
    source = tmp_path / "output/10-09-2026/TH-Thailand/E/XAUUSD/article.md"
    source.write_text("changed", encoding="utf-8")
    with pytest.raises(orchestrator.DispatchError, match="source hash differs"):
        orchestrator.build_dispatch(project_root=tmp_path, business_date="2026-09-10", index_path=index, bindings_path=bindings, policy_path=policy)


def test_dispatch_fails_closed_when_frozen_source_path_is_missing(tmp_path):
    bindings, index, policy, _ = setup_project(tmp_path)
    source = tmp_path / "output/10-09-2026/TH-Thailand/E/XAUUSD/article.md"
    source.unlink()
    with pytest.raises(orchestrator.DispatchError, match="source hash differs"):
        orchestrator.build_dispatch(project_root=tmp_path, business_date="2026-09-10", index_path=index, bindings_path=bindings, policy_path=policy)


def test_dispatch_rejects_schema_only_source_qa_receipt(tmp_path):
    bindings, index, policy, _ = setup_project(tmp_path)
    with pytest.raises(orchestrator.DispatchError, match="frozen source QA is not verified"):
        orchestrator.build_dispatch(project_root=tmp_path, business_date="2026-09-10", index_path=index, bindings_path=bindings, policy_path=policy)


def test_handoff_hold_isolated_to_its_country_and_creates_new_dispatch_version(tmp_path):
    bindings, index, policy, work = setup_project(tmp_path)
    index_data = json.loads(index.read_text(encoding="utf-8"))
    admission_hash = index_data["records"][0]["admission_sha256"]
    index_data["records"].append({"country_code": "MY", "active": True, "admission_path": "work/admission/za.json", "admission_sha256": admission_hash})
    put(index, index_data)
    handoffs = work / "localization/10-09-2026/normal-handoffs"
    put(handoffs / "ZA.json", {"schema": "wrong", "country_code": "ZA", "source_business_date": "2026-09-10", "writer_execution_id": "writer-za"})
    validated = {"delivery_manifest_sha256": "a" * 64, "language_pack": "en-001", "pack_version": "0.1.0", "pack_sha256": "b" * 64}
    with patch.object(localization_queue.localization_admission, "validate", return_value=validated), \
         patch.object(orchestrator.source_qa_acceptance, "validate_source_acceptance", return_value={}):
        first = orchestrator.write_dispatch(project_root=tmp_path, work_root=work, business_date="2026-09-10", index_path=index, bindings_path=bindings, policy_path=policy, handoff_root=handoffs)
        candidate = tmp_path / "work/candidates/my-manifest.json"
        candidate_hash = put(candidate, {"candidate": "writer-ready"})
        put(handoffs / "MY.json", {"schema": orchestrator.WRITER_HANDOFF_SCHEMA, "country_code": "MY", "source_business_date": "2026-09-10", "writer_execution_id": "writer-my", "candidate_manifest_path": "work/candidates/my-manifest.json", "candidate_manifest_sha256": candidate_hash})
        second = orchestrator.write_dispatch(project_root=tmp_path, work_root=work, business_date="2026-09-10", index_path=index, bindings_path=bindings, policy_path=policy, handoff_root=handoffs)
    assert first["status"] == "PARTIAL_HELD"
    assert any(job["country_code"] == "MY" and job["state"] == "WAITING_WRITER" for job in first["jobs"])
    assert any(job["country_code"] == "MY" and job["state"] == "WAITING_REVIEW" for job in second["jobs"])
    assert first["receipt_path"] != second["receipt_path"]


def test_run_discovers_single_ready_binding_and_does_not_write_on_dry_run(tmp_path):
    bindings, _, _, _ = setup_project(tmp_path)
    with patch.object(orchestrator.source_qa_acceptance, "validate_source_acceptance", return_value={}):
        result = orchestrator.run(tmp_path, "2026-09-10", dry_run=True)
    assert result["dry_run"] is True
    assert Path(result["source_bindings_path"]) == bindings.resolve()
    assert result["status"] == "HOLD_NO_ADMITTED_COUNTRIES"
    assert not (tmp_path / "work/localization/10-09-2026/normal-dispatch").exists()


def test_discovery_rejects_ambiguous_ready_revisions_without_workflow_binding(tmp_path):
    bindings, _, _, _ = setup_project(tmp_path)
    duplicate = bindings.parent.parent / "source-bindings-r0004/source-bindings.json"
    put(duplicate, json.loads(bindings.read_text(encoding="utf-8")))
    with pytest.raises(orchestrator.DispatchError, match="exactly one SOURCE_READY"):
        orchestrator.discover_source_bindings(tmp_path, "2026-09-10")


def test_discovery_prefers_hash_bound_workflow_binding(tmp_path):
    bindings, _, _, _ = setup_project(tmp_path)
    duplicate = bindings.parent.parent / "source-bindings-r0004/source-bindings.json"
    put(duplicate, json.loads(bindings.read_text(encoding="utf-8")))
    state = tmp_path / "work/localization/10-09-2026/workflows/current/state.json"
    put(state, {"schema": "p002-localization-workflow/v1", "source_business_date": "2026-09-10",
                "source_bindings_path": str(bindings.resolve()), "source_bindings_sha256": hashlib.sha256(bindings.read_bytes()).hexdigest()})
    assert orchestrator.discover_source_bindings(tmp_path, "2026-09-10") == bindings.resolve()


def test_cli_dispatch_is_actionable_but_never_claims_translation(tmp_path, capsys):
    bindings, index, policy, work = setup_project(tmp_path)
    validated = {"delivery_manifest_sha256": "a" * 64, "language_pack": "en-001", "pack_version": "0.1.0", "pack_sha256": "b" * 64}
    with patch.object(localization_queue.localization_admission, "validate", return_value=validated), \
         patch.object(orchestrator.source_qa_acceptance, "validate_source_acceptance", return_value={}):
        code = orchestrator.main(["--project-root", str(tmp_path), "--work-root", str(work), "--date", "2026-09-10",
                                  "--admission-index", str(index), "--source-bindings", str(bindings), "--policy", str(policy)])
    result = json.loads(capsys.readouterr().out)
    assert code == 2
    assert result["status"] == "PARTIAL_HELD"
    assert result["jobs"][0]["state"] == "WAITING_WRITER"
    assert "content" not in result["jobs"][0]
