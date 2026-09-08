import pytest
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import headline_format
from tools.style_d_weekly_title import (
    StyleDWeeklyTitleError,
    canonical_period,
    period_for_story,
    thai_range,
    validate_localized_title,
)
from tools.language_patch import validate_localized_candidate


def test_thai_weekly_title_and_boundary_ranges():
    assert headline_format.weekly_title(
        "wtiusd", "2026-09-07", "2026-09-11",
        "แนวรับแนวต้านจากกราฟ WTI/USD",
    ) == "วิเคราะห์น้ำมันดิบรายสัปดาห์ วันที่ 7-11 กันยายน 2026 — แนวรับแนวต้านจากกราฟ WTI/USD"
    assert thai_range("2026-09-28", "2026-10-02") == "28 กันยายน 2026-2 ตุลาคม 2026"
    assert thai_range("2026-12-28", "2027-01-01") == "28 ธันวาคม 2026-1 มกราคม 2027"


def test_period_uses_source_calendar_and_rejects_bad_shape():
    story = {"publish_date": "2026-09-08", "calendar": {
        "week_start": "2026-09-07", "week_end": "2026-09-11"}}
    assert period_for_story(story, strict_publication=True) == ("2026-09-07", "2026-09-11")
    assert period_for_story({"publish_date": "2026-09-08"}) == ("2026-09-07", "2026-09-11")
    with pytest.raises(StyleDWeeklyTitleError):
        canonical_period("2026-09-08", "2026-09-12")


def test_localized_title_gate_checks_week_semantics_without_requiring_english_order():
    assert validate_localized_title(
        "Crude oil weekly 7–11 September 2026 — WTI support and resistance",
        "2026-09-07", "2026-09-11", locale="en-ZA") == []
    findings = validate_localized_title(
        "Crude oil weekly 7–12 September 2026",
        "2026-09-07", "2026-09-11", locale="en-ZA")
    assert "title is missing one or both week boundary days" in findings


def test_language_candidate_gate_binds_style_d_title_to_manifest_period():
    source = b"---\ntitle: source\n---\nbody\n"
    target = b"---\ntitle: Crude oil weekly 7-12 September 2026\n---\nbody\n"
    digest = lambda value: hashlib.sha256(value).hexdigest()
    result = validate_localized_candidate(
        source, target,
        job={"style": "D", "week_start": "2026-09-07", "week_end": "2026-09-11",
             "source_sha256": digest(source), "target_sha256": digest(target)},
        claim_map={}, trusted_receipts=[], pack_info={})
    assert "STYLE_D_WEEK_TITLE" in {item["code"] for item in result["findings"]}


def test_language_candidate_gate_rejects_overlong_localized_title():
    source = b"---\ntitle: source\n---\nbody\n"
    long_title = "Crude oil weekly 7-11 September 2026 — " + "x" * 70
    target = f"---\ntitle: {long_title}\n---\nbody\n".encode()
    digest = lambda value: hashlib.sha256(value).hexdigest()
    result = validate_localized_candidate(
        source, target,
        job={"style": "D", "week_start": "2026-09-07", "week_end": "2026-09-11",
             "source_sha256": digest(source), "target_sha256": digest(target)},
        claim_map={}, trusted_receipts=[], pack_info={})
    assert "TITLE_TOO_LONG" in {item["code"] for item in result["findings"]}
