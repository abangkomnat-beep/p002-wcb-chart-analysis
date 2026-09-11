import json
from pathlib import Path

import pytest

from tools import localization_workflow as workflow
from tools import prepare_locale_pack_candidates as proposals
from tools import prepare_source_claim_maps as claims


def _locale(root: Path, locale: str, contents: str):
    path = root / "language/locales" / locale / "baseline.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def test_pack_proposals_use_locked_registry_default_and_keep_drafts_versioned(tmp_path, monkeypatch):
    repo = tmp_path / "Repo"
    locales = ("ms-MY", "ru-RU")
    for locale in locales:
        _locale(repo, locale, locale)
    monkeypatch.setattr(proposals, "ROOT", repo)
    monkeypatch.setattr(proposals, "target_pack_locales", lambda: locales)

    def verified(locale):
        path = repo / "language/locales" / locale
        return {"pack_dir": path, "version": "0.1.2" if locale == "ms-MY" else "0.1.0",
                "status": "stable_locked" if locale == "ms-MY" else "draft",
                "actual_sha256": proposals.pack_sha256(path),
                "recorded_sha256": proposals.pack_sha256(path)}

    monkeypatch.setattr(proposals, "verify", verified)
    first = proposals.prepare("08-09-2026")
    first_index = json.loads((first / "index.json").read_text(encoding="utf-8"))
    assert first_index["locales"][0]["status"] == "reuse_locked"
    assert first_index["locales"][0]["pack_version"] == "0.1.2"
    assert first_index["locales"][1]["proposal_revision"] == "r0001"
    second = proposals.prepare("08-09-2026")
    second_index = json.loads((second / "index.json").read_text(encoding="utf-8"))
    assert all(item["unchanged"] for item in second_index["locales"])
    _locale(repo, "ru-RU", "changed")
    third = proposals.prepare("08-09-2026")
    assert (third / "ru-RU/0.1.0/r0001/baseline.json").read_text(encoding="utf-8") == "ru-RU"
    assert (third / "ru-RU/0.1.0/r0002/baseline.json").read_text(encoding="utf-8") == "changed"
    with pytest.raises(ValueError):
        proposals.prepare("../../outside")


def _article(path: Path, image: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ราคา 4,436.46 จะขึ้นถ้าปิดเหนือ 4,432\n\n![ภาพ](" + image + ")\n", encoding="utf-8")
    (path.parent / image).write_bytes(b"webp")


def test_claim_map_is_paragraph_bound_preserves_full_number_and_revisions(tmp_path, monkeypatch):
    repo = tmp_path / "Repo"
    monkeypatch.setattr(claims, "ROOT", repo)
    for style, asset, _, _ in claims.lanes_for_date("2026-09-08"):
        _article(repo.parent / f"output/08-09-2026/TH-Thailand/{style}/{asset}/P002-20260908-TH-{style}-{asset}-article.md",
                 f"P002-20260908-TH-{style}-{asset}-img01.webp")
    run = claims.prepare("2026-09-08")
    claim = json.loads((run / "claims/e-xauusd.json").read_text(encoding="utf-8"))
    assert len(claim["claims"]) == 2
    assert "4,436.46" in [item["value_text"] for item in claim["claims"][0]["protected"]]
    assert claim["claims"][0]["semantic_markers"]["condition"] == ["ถ้า"]
    assert claims.prepare("2026-09-08") == run
    article = repo.parent / "output/08-09-2026/TH-Thailand/E/XAUUSD/P002-20260908-TH-E-XAUUSD-article.md"
    article.write_text(article.read_text(encoding="utf-8") + "\nแก้ไข", encoding="utf-8")
    assert claims.prepare("2026-09-08").name == "source-bindings-r0002"


def test_claim_markers_capture_conditional_and_certainty_language_in_style_e():
    markers = claims._markers("รอสัญญาณยืนยันก่อนเปิดสถานะ หากไม่ครบเงื่อนไข จึงยังไม่เปิดสถานะ")
    assert "รอ" in markers["condition"]
    assert "ก่อน" in markers["condition"]
    assert "เงื่อนไข" in markers["condition"]
    assert "ยังไม่" in markers["condition"]
    assert "จึง" in markers["certainty"]
    assert "ไม่ใช่" not in markers["certainty"]


def test_workflow_state_is_resumable_and_never_creates_output(tmp_path):
    state = workflow.start(tmp_path, "2026-09-08", "my-br-ar-r1", ["MY", "BR", "AR"])
    assert state.is_file()
    assert workflow.start(tmp_path, "2026-09-08", "my-br-ar-r1", ["MY", "BR", "AR"]) == state
    source = tmp_path / "source.json"
    candidate = tmp_path / "candidate.json"
    source.write_text("source", encoding="utf-8")
    candidate.write_text("candidate", encoding="utf-8")
    data = workflow.record_country_gate(
        tmp_path, "2026-09-08", "my-br-ar-r1", "MY", "CANDIDATES_READY",
        pack_sha256="a" * 64, source_receipt_sha256=workflow._sha(source),
        candidate_manifest_sha256=workflow._sha(candidate), source_receipt_path=source,
        candidate_manifest_path=candidate,
    )
    assert data["countries"]["MY"]["state"] == "CANDIDATES_READY"
    assert not (tmp_path / "output").exists()


def test_workflow_rejects_skipped_transition_and_missing_review_evidence(tmp_path):
    workflow.start(tmp_path, "2026-09-08", "my-br-ar-r1", ["MY"])
    with pytest.raises(workflow.WorkflowError, match="invalid country workflow transition"):
        workflow.record_country_gate(tmp_path, "2026-09-08", "my-br-ar-r1", "MY", "READY_TO_PACKAGE")
    source = tmp_path / "source.json"
    candidate = tmp_path / "candidate.json"
    source.write_text("source", encoding="utf-8")
    candidate.write_text("candidate", encoding="utf-8")
    workflow.record_country_gate(
        tmp_path, "2026-09-08", "my-br-ar-r1", "MY", "CANDIDATES_READY",
        pack_sha256="a" * 64, source_receipt_sha256=workflow._sha(source),
        candidate_manifest_sha256=workflow._sha(candidate), source_receipt_path=source,
        candidate_manifest_path=candidate,
    )
    workflow.record_country_gate(tmp_path, "2026-09-08", "my-br-ar-r1", "MY", "REVIEW_PENDING")
    with pytest.raises(workflow.WorkflowError, match="review receipt"):
        workflow.record_country_gate(tmp_path, "2026-09-08", "my-br-ar-r1", "MY", "READY_TO_PACKAGE")


def test_workflow_rejects_hash_string_without_matching_evidence_file(tmp_path):
    workflow.start(tmp_path, "2026-09-08", "my-br-ar-r1", ["MY"])
    with pytest.raises(workflow.WorkflowError, match="evidence is missing"):
        workflow.record_country_gate(
            tmp_path, "2026-09-08", "my-br-ar-r1", "MY", "CANDIDATES_READY",
            pack_sha256="a" * 64, source_receipt_sha256="b" * 64,
            candidate_manifest_sha256="c" * 64, source_receipt_path=tmp_path / "missing-source.json",
            candidate_manifest_path=tmp_path / "missing-candidate.json",
        )


def test_workflow_binds_explicit_source_revision_and_rejects_drift(tmp_path):
    revision = tmp_path / "source-bindings-r0002"
    revision.mkdir()
    manifest = revision / "source-bindings.json"
    manifest.write_text('{"source_business_date":"2026-09-08"}\n', encoding="utf-8")
    digest = workflow._sha(manifest)

    state = workflow.start(
        tmp_path, "2026-09-08", "explicit-source-r2", ["MY"],
        source_bindings_revision_dir=revision, source_bindings_sha256=digest)
    data = json.loads(state.read_text(encoding="utf-8"))
    assert data["source_bindings_path"] == str(manifest.resolve())
    assert data["source_bindings_sha256"] == digest
    resumed = workflow.resume(
        tmp_path, "2026-09-08", "explicit-source-r2",
        source_bindings_revision_dir=revision, source_bindings_sha256=digest)
    assert resumed["source_bindings_sha256"] == digest

    manifest.write_text('{"source_business_date":"2026-09-08","revision":2}\n', encoding="utf-8")
    with pytest.raises(workflow.WorkflowError, match="stale or mismatched|hash mismatch"):
        workflow.resume(tmp_path, "2026-09-08", "explicit-source-r2")
    with pytest.raises(workflow.WorkflowError, match="stale or mismatched"):
        workflow.record_country_gate(tmp_path, "2026-09-08", "explicit-source-r2", "MY",
                                     "REVIEW_PENDING")
