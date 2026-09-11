from unittest.mock import patch

import pytest

from tools import localization_queue, normal_localization_orchestrator as orchestrator
from tests.test_normal_localization_orchestrator import recovery_bundle, setup_project


def test_explicit_recovery_bundle_uses_only_hash_bound_staged_bytes(tmp_path):
    bindings, index, policy, _ = setup_project(tmp_path)
    bundle = recovery_bundle(tmp_path, bindings)
    for path in (tmp_path / "output/10-09-2026/TH-Thailand/E/XAUUSD").iterdir():
        path.unlink()
    validated = {"delivery_manifest_sha256": "a" * 64, "language_pack": "en-001", "pack_version": "0.1.0", "pack_sha256": "b" * 64}
    with patch.object(localization_queue.localization_admission, "validate", return_value=validated), \
         patch.object(orchestrator.source_qa_acceptance, "validate_source_acceptance", return_value={}):
        result = orchestrator.build_dispatch(project_root=tmp_path, business_date="2026-09-10", index_path=index,
                                             bindings_path=bindings, policy_path=policy,
                                             recovery_bundle_path=bundle)
    job = result["jobs"][0]
    assert job["recovery_bundle_path"] == str(bundle.resolve())
    assert job["resolved_source_path"].endswith("recovery/E-XAUUSD/article.md")


def test_recovery_bundle_rejects_wrong_staged_image_hash(tmp_path):
    bindings, index, policy, _ = setup_project(tmp_path)
    bundle = recovery_bundle(tmp_path, bindings, wrong_hash=True)
    with pytest.raises(orchestrator.DispatchError, match="staged hash differs"):
        orchestrator.build_dispatch(project_root=tmp_path, business_date="2026-09-10", index_path=index,
                                     bindings_path=bindings, policy_path=policy,
                                     recovery_bundle_path=bundle)
