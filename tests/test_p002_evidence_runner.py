import json

from tools.p002_evidence_runner import run
from tools.p002_gate_evidence import (
    validate_copydesk_group_evidence,
    validate_scheduler_evidence,
    validate_style_acceptance_evidence,
)


def test_frozen_evidence_runner_writes_actual_gate_records_without_production(tmp_path):
    records = run(tmp_path / "frozen")
    assert validate_scheduler_evidence(records["P2"]) == []
    assert validate_style_acceptance_evidence(records["P3"]) == []
    assert validate_copydesk_group_evidence(records["P8"]) == []
    assert json.loads((tmp_path / "frozen" / "p2-evidence.json").read_text()) == records["P2"]
