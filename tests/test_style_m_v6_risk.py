from datetime import datetime, timedelta
import hashlib
from pathlib import Path

import pytest

from tools import style_m_v6_risk as risk
from tools import style_m_v6_story as story


def _rows(days=20):
    start = datetime(2026, 1, 1, 0, tzinfo=story.BANGKOK)
    out = []
    for i in range(days * 24):
        p = 100 + (i % 9) * 0.1
        out.append({"at": (start + timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S"),
                    "open": p, "high": p + 2, "low": p - 1, "close": p + .5})
    return out


def test_daily_metrics_exclude_forming_day_and_use_closed_days_only():
    rows = _rows()
    cutoff = datetime(2026, 1, 20, 11, tzinfo=story.BANGKOK)
    bars = risk.completed_daily_bars(rows, cutoff=cutoff)
    assert bars[-1]["date"] == "2026-01-19"
    for metric in risk.DAILY_METRICS:
        result = risk.daily_volatility(rows, cutoff=cutoff, metric=metric)
        assert result["last_closed_date"] == "2026-01-19"


def test_insufficient_daily_bars_fails_closed():
    with pytest.raises(risk.RiskUnavailable):
        risk.daily_volatility(_rows(10), cutoff=datetime(2026, 1, 10, 11, tzinfo=story.BANGKOK), metric="ADR14")


def test_candidate_grid_and_policy_have_metadata_and_tick_rr():
    built = story.build(_rows(8), cutoff=datetime(2026, 1, 8, 11, tzinfo=story.BANGKOK), source_label="fixture")
    volatility = {"metric": "ADR14", "value": 30.0, "length": 14,
                  "last_closed_date": "2026-01-07"}
    chosen = risk.apply_policy(built["story"], volatility=volatility,
                               floor_coefficient=.35, max_cap_coefficient=1.25,
                               candidate_id="ADR14_F0.35_C1.25")
    assert chosen["risk_contract"]["candidate_id"] == "ADR14_F0.35_C1.25"
    for plan in chosen["scenarios"].values():
        if plan["state"] != "NO_PLAN":
            assert plan["rr1"] >= 1.5 and plan["rr2"] >= 2.0
            assert plan["risk_policy"] == "ADR14_F0.35_C1.25"


def test_cap_breach_is_oco_fail_closed():
    built = story.build(_rows(8), cutoff=datetime(2026, 1, 8, 11, tzinfo=story.BANGKOK), source_label="fixture")
    chosen = risk.apply_policy(built["story"], volatility={"metric": "ADR14", "value": .01},
                               floor_coefficient=.65, max_cap_coefficient=.85,
                               candidate_id="ADR14_F0.65_C0.85")
    assert all(plan["state"] == "NO_PLAN" for plan in chosen["scenarios"].values())


def test_calibration_provenance_and_per_cutoff_risk_metadata_are_reproducible():
    rows = _rows(20)
    snapshot_path = "qa/frozen/source-btcusd-h1.json"
    source_commit = "a" * 40
    file_sha256 = "b" * 64
    report = risk.calibrate(rows, source_label="fixture", source_meta={"snapshot_id": "S1"},
                            days=1, in_sample_days=0,
                            dataset_snapshot_path=snapshot_path,
                            dataset_snapshot_source_commit=source_commit,
                            dataset_snapshot_file_sha256=file_sha256)
    provenance = report["provenance"]
    expected_dataset = risk.snapshot_hash({"source_label": "fixture", "source_meta": {"snapshot_id": "S1"}, "rows": rows})
    assert provenance["dataset_snapshot_hash"] == expected_dataset
    assert provenance["candidate_grid_hash"] == risk.snapshot_hash(risk.candidate_grid())
    assert provenance["code_hash"] == hashlib.sha256(Path(risk.__file__).read_bytes()).hexdigest()
    assert len(provenance["execution_cost_config_hash"]) == 64
    assert provenance["dataset_snapshot_path"] == snapshot_path
    assert provenance["dataset_snapshot_source_commit"] == source_commit
    assert provenance["dataset_snapshot_file_sha256"] == file_sha256
    candidate = report["candidates"]["ADR14_F0.35_C1.25"]
    record = candidate["records"][0]
    assert record["cutoff"] and record["candidate_id"] == "ADR14_F0.35_C1.25"
    assert record["dataset_snapshot_hash"] == provenance["dataset_snapshot_hash"]
    assert record["candidate_config_hash"] == risk.snapshot_hash(candidate["candidate"])
    metadata = record["risk_metadata"]
    assert "volatility_metric" in metadata and "volatility_value" in metadata
    assert "floor_coefficient" in metadata and "structural_anchor" in metadata
    assert "structural_risk" in metadata and "final_risk" in metadata
    assert "max_risk_cap" in metadata and "no_plan_reason" in metadata
    assert record["risk_metadata_hash"] == risk.snapshot_hash(metadata)
