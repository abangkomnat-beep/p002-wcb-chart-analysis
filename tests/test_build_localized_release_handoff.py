import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tools import build_localized_release_handoff as bridge


def test_completed_anchors_do_not_create_a_synthetic_open_question():
    assert bridge._proposal_questions({"open_questions": []}, []) == []
    assert bridge._proposal_questions({"open_questions": ["Unresolved translation"]}, []) == ["Unresolved translation"]
    with pytest.raises(bridge.HandoffError, match="unresolved fields"):
        bridge._proposal_questions({"open_questions": []}, ["C1"])
    with pytest.raises(bridge.HandoffError):
        bridge._proposal_questions({"open_questions": "not a list"}, [])


def put(path: Path, value) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False).encode("utf-8") if isinstance(value, dict) else value)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("tamper_target", [False, True])
@pytest.mark.parametrize("candidate_schema,country_code,locale,pack", [
    ("p002-localized-writer-retry/v1", "NG", "en-NG", "en-001"),
    ("p002-localized-writer-production/v1", "SA", "ar-SA", "ar-001"),
])
@pytest.mark.parametrize("writer_questions", [["Independent review required"], []])
def test_bridge_keeps_missing_review_anchors_as_hold_and_resolves_relative_image(
        tmp_path, tamper_target, candidate_schema, country_code, locale, pack, writer_questions):
    project = tmp_path / "project"
    candidate = project / "work/localization/10-09-2026/writer/NG"
    image = candidate / "candidates/E-XAUUSD/images/ng.webp"
    image_hash = put(image, b"not-a-render-test")
    article = candidate / "candidates/E-XAUUSD/article.md"
    target_hash = put(article, b"---\nasset: xauusd\n---\nTarget 1.23\n![x](images/ng.webp)\n")
    claim = {"claims": [{"id": "C1", "source_quote": "source", "protected": []}]}
    claims = project / "work/localization/10-09-2026/source/claims/e.json"
    claim_hash = put(claims, claim)
    source_receipt = {"schema": "source/v1", "status": "PASS", "reviewer_execution_id": "source-reviewer",
                      "binding_hashes": {"source_sha256": "a" * 64, "claim_map_sha256": claim_hash}}
    put(project / "work/localization/10-09-2026/source/receipts/E-XAUUSD.json", source_receipt)
    source = {"source_business_date": "2026-09-10", "expected_article_keys": ["E-XAUUSD"], "articles": [{
        "article_id": "E-XAUUSD", "style": "E", "asset": "XAUUSD", "source_path": "output/day/source.md",
        "source_sha256": "a" * 64, "source_canonical_sha256": "a" * 64,
        "claim_map_path": "claims/e.json", "claim_map_sha256": claim_hash,
        "images": [{"name": "th.webp", "path": "output/day/th.webp", "sha256": "b" * 64}]}]}
    source_path = project / "work/localization/10-09-2026/source/source-bindings.json"
    source_hash = put(source_path, source)
    candidate_manifest = {"schema": candidate_schema, "source_business_date": "2026-09-10",
                          "country": country_code, "content_locale": locale, "language_pack": pack,
                          "pack_version": "0.1.0", "pack_sha256": "c" * 64,
                          "source_manifest_sha256": source_hash, "execution_id": "writer-execution",
                          "articles": [{"article_id": "E-XAUUSD", "source_sha256": "a" * 64,
                                        "candidate_path": "candidates/E-XAUUSD/article.md", "candidate_sha256": target_hash,
                                        "proposal_path": "proposals/e.json", "images": [{"target_path": "candidates/E-XAUUSD/images/ng.webp", "source_sha256": "b" * 64, "target_sha256": image_hash}]}]}
    put(candidate / "manifest.json", candidate_manifest)
    writer_proposal = {"schema": "p002-localized-proposal/v2", "article_id": "E-XAUUSD",
                       "source_sha256": "a" * 64, "pack_sha256": "c" * 64,
                       "writer_execution_id": "writer-execution",
                       "target_markdown": article.read_text(encoding="utf-8"),
                       "alignment": [{"claim_id": "C1", "target_field": None, "target_quote": None,
                                      "source_quote_sha256": "e" * 64,
                                      "source_receipt_id": "source-e-xauusd"}],
                       "open_questions": writer_questions, "attempt": 1}
    proposal_path = candidate / "proposals/e.json"
    put(proposal_path, writer_proposal)
    country = {"content_locale": locale, "language_pack": pack, "policy_sha256": "d" * 64}
    output = project / "work/localization/10-09-2026/tmp"
    with patch.object(bridge.localization_config, "resolve_country", return_value=country):
        if tamper_target:
            article.write_bytes(b"unreviewed replacement")
            with pytest.raises(bridge.HandoffError, match="candidate target hash mismatch"):
                bridge.build(project_root=project, candidate_root=candidate, source_bindings=source_path, output_run=output)
            assert not (output / "source-manifest.json").exists()
            return
        result = bridge.build(project_root=project, candidate_root=candidate, source_bindings=source_path, output_run=output)
    assert result["status"] == "HOLD_INDEPENDENT_REVIEW"
    manifest = json.loads((output / "source-manifest.json").read_text(encoding="utf-8"))
    assert manifest["articles"][0]["images"][0]["candidate_path"].endswith("ng.webp")
    proposal = json.loads((output / "proposals/e-xauusd.json").read_text(encoding="utf-8"))
    assert proposal["open_questions"] == writer_questions
    assert proposal["alignment"][0]["target_quote"] is None
    assert proposal["alignment"][0]["source_quote_sha256"] == "e" * 64
    assert (output / "proposals/e-xauusd.json").read_bytes() == proposal_path.read_bytes()
    report = json.loads((output / "handoff-report.json").read_text(encoding="utf-8"))
    assert report["source_manifest_sha256"] == hashlib.sha256((output / "source-manifest.json").read_bytes()).hexdigest()
