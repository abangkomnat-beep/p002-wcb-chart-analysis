from tools.p002_gate_evidence import (
    validate_copydesk_group_evidence,
    validate_scheduler_evidence,
    validate_style_acceptance_evidence,
)


def test_scheduler_evidence_requires_real_invocation_collision_and_rollback():
    record = {
        "invocation": {"real_scheduler": True},
        "collision": {"overwrite_blocked": True},
        "rollback": {"drill_passed": True},
    }
    assert validate_scheduler_evidence(record) == []
    assert "real_scheduler_invocation_missing" in validate_scheduler_evidence({})


def test_style_acceptance_requires_each_group_evidence_in_order():
    record = {
        "sequence": ["F", "G", "I", "J"],
        "groups": {
            style: {field: True for field in ("manifest", "provenance", "attribution", "license", "rollback")}
            for style in ("F", "G", "I", "J")
        },
    }
    assert validate_style_acceptance_evidence(record) == []
    assert "F_license_evidence_missing" in validate_style_acceptance_evidence({"groups": {"F": {}}})


def test_copydesk_groups_require_hash_facts_sources_isolation_and_rights():
    fields = ("hash_manifest", "factual_checks", "source_checks", "no_cross_group_mutation", "data_rights")
    record = {"groups": {group: {field: True for field in fields} for group in ("A", "B")}}
    assert validate_copydesk_group_evidence(record) == []
    assert "A_data_rights_evidence_missing" in validate_copydesk_group_evidence({"groups": {"A": {}}})

