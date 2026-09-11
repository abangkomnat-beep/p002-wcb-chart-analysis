import json
from pathlib import Path

import pytest

from tools.attach_independent_review_receipts import AttachError, attach


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = value if isinstance(value, bytes) else (json.dumps(value) + "\n").encode()
    path.write_bytes(data)
    return __import__("hashlib").sha256(data).hexdigest()


@pytest.mark.parametrize("include_receipt_id", [True, False])
def test_attach_requires_complete_distinct_review_coverage(tmp_path, include_receipt_id):
    handoff = tmp_path / "handoff"
    reviewer = tmp_path / "reviewer"
    write(handoff / "source-manifest.json", {"articles": [{"article_id": "E-XAUUSD", "proposal_path": "proposals/e.json"}]})
    write(handoff / "proposals/e.json", {"writer_execution_id": "writer"})
    receipts = []
    for gate in ("language", "semantic", "visual", "package_input"):
        path = reviewer / "receipts" / f"{gate}.json"
        digest = write(path, {"receipt_id": gate, "status": "PASS", "verdict": "PASS", "article_id": "E-XAUUSD", "gate": gate, "writer_execution_id": "writer", "reviewer_execution_id": "reviewer"})
        entry = {"path": f"receipts/{gate}.json", "sha256": digest}
        if include_receipt_id:
            entry["receipt_id"] = gate
        receipts.append(entry)
    write(reviewer / "receipts/index.json", {"receipts": receipts})
    write(handoff / "receipts/index.json", {"receipts": []})
    result = attach(handoff_root=handoff, reviewer_root=reviewer)
    assert result["review_receipts"] == 4
    assert json.loads((handoff / "receipts/index.json").read_text())["status"] == "READY_FOR_PACKAGE_INPUT_REVIEW"
