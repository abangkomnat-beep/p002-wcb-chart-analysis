"""Locked risk boundaries shared by every F+ trade candidate."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from fixtures.fplus.contract_support import require_module


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCKED = json.loads((REPO_ROOT / "config" / "risk_thresholds.json").read_text(encoding="utf-8"))["thresholds"]


def evaluate(**overrides):
    risk = require_module("tools.fplus_risk")
    payload = {
        "direction": "long",
        "entry_zone": {"low": 100.0, "high": 101.0},
        "stop_loss": 96.0,
        "take_profit_1": 107.0,
        "current_price": 100.0,
        "atr": 4.0,
    }
    payload.update(overrides)
    return risk.evaluate_risk(thresholds=LOCKED, **payload)


def test_locked_thresholds_are_1_2_1_0_2_0():
    assert LOCKED == {"minimum_rr": 1.2, "minimum_stop_atr": 1.0, "maximum_entry_atr": 2.0}


def test_risk_loader_reads_single_source_and_returns_raw_file_fingerprint(monkeypatch, tmp_path):
    risk = require_module("tools.fplus_risk")
    source = REPO_ROOT / "config" / "risk_thresholds.json"
    copied = tmp_path / "risk_thresholds.json"
    copied.write_bytes(source.read_bytes())
    monkeypatch.setattr(risk, "RISK_PATH", copied, raising=False)

    policy = risk.load_risk_thresholds()

    assert policy["thresholds"] == LOCKED
    assert policy["source"] == str(copied.resolve())
    assert policy["sha256"] == hashlib.sha256(copied.read_bytes()).hexdigest()


def test_risk_loader_has_no_duplicated_threshold_constant():
    risk = require_module("tools.fplus_risk")
    assert not hasattr(risk, "LOCKED_THRESHOLDS"), (
        "config/risk_thresholds.json must be the sole threshold source"
    )


def test_risk_loader_does_not_fall_back_to_duplicated_constants(monkeypatch, tmp_path):
    risk = require_module("tools.fplus_risk")
    missing = tmp_path / "missing-risk-thresholds.json"
    monkeypatch.setattr(risk, "RISK_PATH", missing, raising=False)
    with pytest.raises((ValueError, FileNotFoundError), match="risk|threshold|source|file"):
        risk.load_risk_thresholds()


def test_rr_boundary_uses_worst_long_entry_edge_and_is_inclusive():
    # Worst long entry is zone.high=101: risk=5, reward=6, RR=1.2 exactly.
    result = evaluate()
    assert result["rr_worst_edge"] == pytest.approx(1.2)
    assert result["eligible"] is True
    assert result["entry_edge_used"] == 101.0


def test_rr_below_boundary_fails():
    result = evaluate(take_profit_1=106.99)
    assert result["eligible"] is False
    assert "RR_BELOW_MINIMUM" in result["reason_codes"]


def test_short_uses_disadvantaged_low_edge():
    result = evaluate(
        direction="short", entry_zone={"low": 99.0, "high": 100.0},
        stop_loss=104.0, take_profit_1=93.0, current_price=100.0,
    )
    assert result["entry_edge_used"] == 99.0
    assert result["rr_worst_edge"] == pytest.approx(1.2)
    assert result["eligible"] is True


def test_stop_one_atr_and_entry_two_atr_boundaries_are_inclusive():
    stop_boundary = evaluate(stop_loss=97.0, take_profit_1=105.8, atr=4.0)
    assert stop_boundary["stop_atr"] == pytest.approx(1.0)
    assert stop_boundary["eligible"] is True
    distance_boundary = evaluate(entry_zone={"low": 108.0, "high": 108.0},
                                 stop_loss=104.0, take_profit_1=112.8)
    assert distance_boundary["entry_distance_atr"] == pytest.approx(2.0)
    assert distance_boundary["eligible"] is True


@pytest.mark.parametrize("overrides,reason", [
    ({"stop_loss": 97.01, "take_profit_1": 110.0}, "STOP_BELOW_MINIMUM_ATR"),
    ({"entry_zone": {"low": 108.01, "high": 108.01}, "stop_loss": 104.0,
      "take_profit_1": 113.0}, "ENTRY_TOO_FAR_ATR"),
    ({"stop_loss": 101.0}, "NON_POSITIVE_RISK"),
])
def test_risk_failures_are_reason_coded(overrides, reason):
    result = evaluate(**overrides)
    assert result["eligible"] is False
    assert reason in result["reason_codes"]
