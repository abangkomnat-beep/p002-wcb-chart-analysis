"""Evidence-only validators for P002 release gates.

These validators inspect an in-memory evidence record and never invoke the
pipeline, write output, or change production configuration.
"""

from __future__ import annotations


def validate_scheduler_evidence(record: dict) -> list[str]:
    errors: list[str] = []
    if record.get("invocation", {}).get("real_scheduler") is not True:
        errors.append("real_scheduler_invocation_missing")
    if record.get("collision", {}).get("overwrite_blocked") is not True:
        errors.append("overwrite_collision_evidence_missing")
    if record.get("rollback", {}).get("drill_passed") is not True:
        errors.append("scheduler_rollback_drill_missing")
    return errors


def validate_style_acceptance_evidence(record: dict, order=("F", "G", "I", "J")) -> list[str]:
    errors: list[str] = []
    groups = record.get("groups", {})
    for style in order:
        item = groups.get(style, {})
        for field in ("manifest", "provenance", "attribution", "license", "rollback"):
            if not item.get(field):
                errors.append(f"{style}_{field}_evidence_missing")
    if [style for style in record.get("sequence", [])] != list(order):
        errors.append("style_sequence_not_FG_then_IJ")
    return errors


def validate_copydesk_group_evidence(record: dict, groups=("A", "B")) -> list[str]:
    errors: list[str] = []
    for group in groups:
        item = record.get("groups", {}).get(group, {})
        for field in ("hash_manifest", "factual_checks", "source_checks", "no_cross_group_mutation", "data_rights"):
            if not item.get(field):
                errors.append(f"{group}_{field}_evidence_missing")
    return errors
