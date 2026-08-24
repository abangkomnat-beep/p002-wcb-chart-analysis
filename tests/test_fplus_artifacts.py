"""Directory-level transaction contract preventing mixed generations."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from fixtures.fplus.contract_support import require_module


def prepare_stage(root: Path, generation: int) -> tuple[Path, dict]:
    stage = root / f"stage-{generation}"
    stage.mkdir(parents=True)
    files = {
        "btcusd.md": f"generation={generation}\n".encode(),
        "btcusd-fplus-2026-08-24.webp": f"WEBP-generation={generation}".encode(),
    }
    manifest_files = []
    for name, content in files.items():
        (stage / name).write_bytes(content)
        manifest_files.append({"name": name, "sha256": hashlib.sha256(content).hexdigest(),
                               "bytes": len(content)})
    return stage, {"run_id": f"run-{generation}", "generation": generation,
                   "files": manifest_files}


def assert_single_generation(final: Path):
    values = {path.read_bytes().split(b"=")[-1].strip() for path in final.iterdir()}
    assert len(values) == 1, "final contains a mixed Markdown/WebP generation"


def test_first_commit_promotes_the_complete_directory(tmp_path):
    artifacts = require_module("tools.fplus_artifacts")
    store = artifacts.ArtifactTransaction(work_root=tmp_path / "work",
                                          output_root=tmp_path / "output")
    stage, manifest = prepare_stage(tmp_path, 1)
    result = store.commit(stage, relative_final_dir=Path("24-08-2026") / "F+-BTCUSD-แผนระยะสั้น",
                          manifest=manifest)
    final = Path(result["final_dir"])
    assert sorted(path.name for path in final.iterdir()) == [
        "btcusd-fplus-2026-08-24.webp", "btcusd.md",
    ]
    assert_single_generation(final)


@pytest.mark.parametrize("failpoint", [
    "prepared", "old_parked", "new_visible", "before_lock_commit",
])
def test_force_faults_never_leave_a_mixed_generation(tmp_path, failpoint):
    artifacts = require_module("tools.fplus_artifacts")
    store = artifacts.ArtifactTransaction(work_root=tmp_path / "work",
                                          output_root=tmp_path / "output")
    relative = Path("24-08-2026") / "F+-BTCUSD-แผนระยะสั้น"
    first, manifest1 = prepare_stage(tmp_path, 1)
    store.commit(first, relative_final_dir=relative, manifest=manifest1)
    second, manifest2 = prepare_stage(tmp_path, 2)
    with pytest.raises(artifacts.InjectedTransactionFailure):
        store.commit(second, relative_final_dir=relative, manifest=manifest2,
                     force=True, fault_at=failpoint)
    recovered = Path(store.recover(relative_final_dir=relative)["final_dir"])
    assert_single_generation(recovered)


def test_transaction_journal_is_internal_not_in_final(tmp_path):
    artifacts = require_module("tools.fplus_artifacts")
    store = artifacts.ArtifactTransaction(work_root=tmp_path / "work",
                                          output_root=tmp_path / "output")
    stage, manifest = prepare_stage(tmp_path, 1)
    result = store.commit(stage, relative_final_dir=Path("24-08-2026") / "F+-BTCUSD-แผนระยะสั้น",
                          manifest=manifest)
    final = Path(result["final_dir"])
    assert not list(final.glob("*.json"))
    assert Path(result["transaction_journal"]).is_file()
    assert not Path(result["transaction_journal"]).is_relative_to(final)
