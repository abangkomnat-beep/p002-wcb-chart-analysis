import hashlib
import json
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch

from tools import localization_queue as queue


def put(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value).encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def test_queue_selects_only_hash_bound_active_admission(tmp_path):
    shutil.copytree(Path(__file__).parents[1] / "config", tmp_path / "config")
    record = tmp_path / "work/admission.json"
    digest = put(record, {"source_business_date": "2026-09-09"})
    index = tmp_path / "work/localization/admission-index.json"
    put(index, {"schema": queue.SCHEMA, "records": [
        {"country_code": "ZA", "active": True, "admission_path": "work/admission.json", "admission_sha256": digest},
        {"country_code": "SG", "active": False, "admission_path": "work/admission.json", "admission_sha256": digest}]})
    validated = {"delivery_manifest_sha256": "a" * 64, "language_pack": "en-001", "pack_version": "0.1.0", "pack_sha256": "b" * 64}
    with patch.object(queue.localization_admission, "validate", return_value=validated):
        result = queue.select(project_root=tmp_path, output_root=tmp_path / "output", business_date="2026-09-10", index_path=index, scope=("ZA", "SG"))
    assert result["selected"] == ["ZA"]
    assert result["held"][0]["country_code"] == "SG"


def test_queue_holds_changed_admission_bytes(tmp_path):
    shutil.copytree(Path(__file__).parents[1] / "config", tmp_path / "config")
    record = tmp_path / "work/admission.json"
    put(record, {"source_business_date": "2026-09-09"})
    index = tmp_path / "work/localization/admission-index.json"
    put(index, {"schema": queue.SCHEMA, "records": [{"country_code": "ZA", "active": True,
        "admission_path": "work/admission.json", "admission_sha256": "0" * 64}]})
    result = queue.select(project_root=tmp_path, output_root=tmp_path / "output", business_date="2026-09-10", index_path=index, scope=("ZA",))
    assert result["selected"] == []
    assert result["held"][0]["reason"] == "ADMISSION_EVIDENCE_CHANGED"


def test_default_scope_reads_all_foreign_rollout_and_admits_enabled_subset(tmp_path):
    source = Path(__file__).parents[1]
    shutil.copytree(source / "config", tmp_path / "config")
    shutil.copytree(source / "language", tmp_path / "language")
    record = tmp_path / "work/admission.json"
    digest = put(record, {"source_business_date": "2026-09-09"})
    rollout = json.loads((tmp_path / "config/localization-rollout-20.json").read_text(encoding="utf-8"))
    foreign = [code for code in rollout["countries"] if code != "TH"]
    index = tmp_path / "work/localization/admission-index.json"
    put(index, {"schema": queue.SCHEMA, "records": [
        {"country_code": code, "active": True, "admission_path": "work/admission.json", "admission_sha256": digest}
        for code in foreign]})
    validated = {"delivery_manifest_sha256": "a" * 64, "language_pack": "en-001", "pack_version": "0.1.0", "pack_sha256": "b" * 64}
    with patch.object(queue.localization_admission, "validate", return_value=validated):
        result = queue.select(project_root=tmp_path, output_root=tmp_path / "output", business_date="2026-09-10", index_path=index)
    assert {row["country_code"] for row in result["records"]} == set(foreign)
    assert "TH" not in result["selected"]
    assert set(result["selected"]) == {"ZA", "MY", "BR", "AR", "CL", "RU", "MX", "NG", "SG"}
    assert {row["country_code"] for row in result["held"]} == {"SA", "AE", "CO", "KE", "PH", "KR", "IN", "TR", "PK", "BD"}
    assert len(result["rollout_sha256"]) == 64


def test_default_scope_fails_closed_for_rollout_registry_policy_integrity(tmp_path):
    source = Path(__file__).parents[1]
    shutil.copytree(source / "config", tmp_path / "config")
    shutil.copytree(source / "language", tmp_path / "language")
    rollout_path = tmp_path / "config/localization-rollout-20.json"
    rollout = json.loads(rollout_path.read_text(encoding="utf-8"))
    rollout["countries"].append("XX")
    rollout["country_count"] = 21
    rollout_path.write_text(json.dumps(rollout))
    with patch.object(queue.localization_admission, "validate"):
        try:
            queue._default_scope(tmp_path)
        except queue.QueueError:
            pass
        else:
            raise AssertionError("invalid rollout must fail closed")


@pytest.mark.parametrize("case", ("duplicate_registry", "missing_registry", "missing_policy"))
def test_default_scope_fails_closed_for_missing_or_duplicate_bindings(tmp_path, case):
    source = Path(__file__).parents[1]
    shutil.copytree(source / "config", tmp_path / "config")
    shutil.copytree(source / "language", tmp_path / "language")
    registry_path = tmp_path / "language/country-locale-registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if case == "duplicate_registry":
        registry["countries"].append(dict(registry["countries"][0]))
    elif case == "missing_registry":
        registry["countries"] = [row for row in registry["countries"] if row["country_code"] != "AE"]
    else:
        policy_path = tmp_path / "config/localization-country-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        del policy["countries"]["AE"]
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(queue.QueueError):
        queue._default_scope(tmp_path)
