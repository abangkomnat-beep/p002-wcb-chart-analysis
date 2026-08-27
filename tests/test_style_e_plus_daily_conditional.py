"""RED contracts for BTCUSD E+ Daily Conditional DC-T/v1.

This file deliberately targets the approved pure boundary
``tools.style_e_plus_daily_conditional``.  The boundary does not exist on the
B100 baseline, so these tests must fail until the additive implementation is
provided.  Fixtures are deterministic and offline; no production/output path
or user-owned research harness is imported.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import math
import socket
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
BANGKOK = timezone(timedelta(hours=7))
CUTOFF = datetime(2026, 8, 27, 8, 0, tzinfo=BANGKOK)
EXPIRY = CUTOFF + timedelta(days=1)
FORBIDDEN = {
    "entry", "entry_zone", "stop", "sl", "tp", "risk", "sizing",
    "quantity", "order", "fill", "position", "protective_stop", "execution",
}


def _dc():
    """Load the approved production boundary (expected RED failure on baseline)."""
    return importlib.import_module("tools.style_e_plus_daily_conditional")


def _strict(state: str = "NO_PLAN", side: str | None = None, *, plan=None,
            reason: str | None = None) -> dict:
    return {
        "state": state,
        "side": side,
        "plan": copy.deepcopy(plan),
        "adaptive_reason_code": reason,
        "adaptive_stop": {"evaluated": False, "accepted": False},
        "adaptive_context": {"sha256": "a" * 64},
        "lifecycle": {
            "mode": "manual_analysis_only",
            "external_fill_evidence_accepted": False,
            "position_confirmed": False,
            "protective_stop_active": False,
        },
    }


def _basis(timeframe: str, *, close_at: datetime = CUTOFF) -> dict:
    bar_at = close_at.astimezone(UTC) - (timedelta(hours=1)
                                         if timeframe == "1h" else timedelta(minutes=15))
    return {
        "asset": "btcusd", "timeframe": timeframe, "candle_state": "closed",
        "basis_bar_at": bar_at.isoformat().replace("+00:00", "Z"),
        "basis_close_at": close_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "source": "fixture",
    }


def _rows(timeframe: str, *, after_cutoff: bool = False,
          forming: bool = False, count: int = 241) -> list[dict]:
    step = timedelta(hours=1) if timeframe == "1h" else timedelta(minutes=15)
    end = CUTOFF.astimezone(UTC) + (step if after_cutoff else timedelta(0))
    start = end - step * (count - 1)
    result = []
    for i in range(count):
        at = start + step * i
        result.append({
            "at": at.isoformat().replace("+00:00", "Z"),
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
            "forming": forming,
        })
    if timeframe == "1h":
        # The previous 20 decision bars have a known Donchian range; the
        # current signal bar remains excluded by the production contract.
        result[-11]["high"] = 110.0
        result[-11]["low"] = 90.0
    return result


def _m15_with_close(close: float, *, at_offset: int = 0) -> list[dict]:
    # Evaluation fixtures are observed after the 08:00 creation cutoff.
    result = _rows("15min", after_cutoff=True)
    result[-1]["close"] = close
    result[-1]["open"] = close
    result[-1]["high"] = max(101.0, close)
    result[-1]["low"] = min(99.0, close)
    if at_offset:
        for i in range(abs(at_offset)):
            index = -1 - i
            result[index]["close"] = close
            result[index]["open"] = close
            result[index]["high"] = max(101.0, close)
            result[index]["low"] = min(99.0, close)
    return result


def _create(*, strict=None, now: datetime = CUTOFF, h1=None, m15=None,
            prior_artifact=None, **kwargs):
    dc = _dc()
    h1_basis = kwargs.pop("h1_basis", _basis("1h"))
    m15_basis = kwargs.pop("m15_basis", _basis("15min"))
    return dc.create(
        strict_story=strict or _strict(), h1_rows=h1 or _rows("1h"),
        m15_rows=m15 or _rows("15min"), session_cutoff=CUTOFF, now=now,
        h1_basis=h1_basis, m15_basis=m15_basis,
        prior_artifact=prior_artifact, **kwargs)


def _conditional(value):
    if isinstance(value, dict) and "daily_conditional" in value:
        return value["daily_conditional"]
    return value


def _evaluate(creation, *, strict=None, evaluated_at=None, h1=None, m15=None,
              **kwargs):
    dc = _dc()
    return dc.evaluate(
        creation=creation, strict_story=strict or _strict(),
        h1_rows=h1 or _rows("1h"), m15_rows=m15 or _rows("15min"),
        evaluated_at=evaluated_at or CUTOFF + timedelta(hours=1), **kwargs)


def _keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key).lower()
            yield from _keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _keys(child)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _assert_no_forbidden(value):
    assert not FORBIDDEN.intersection(_keys(value))


# --- Creation, cutoff, geometry and daily coverage (7) ---------------------

def test_dc_c01_creation_at_0800_uses_only_closed_prefix():
    conditional = _conditional(_create())
    assert conditional["schema"] == "style-e-plus-daily-conditional/v1"
    assert conditional["session_timezone"] == "Asia/Bangkok"
    assert conditional["session_cutoff"] == "2026-08-27T08:00:00+07:00"
    assert conditional["effective_from"] == conditional["session_cutoff"]
    assert conditional["expires_at"] == "2026-08-28T08:00:00+07:00"
    assert conditional["watch_geometry"] == {
        "donchian_length": 20, "watch_buffer_h1_atr": 0.25,
            "buy_watch": "110.66", "sell_watch": "89.34",
    }


def test_dc_c02_pre_0800_uses_prior_or_returns_control_outcome():
    with pytest.raises(_dc().NoValidPriorSession):
        _create(now=CUTOFF - timedelta(seconds=1))
    prior = _create()
    result = _create(now=CUTOFF - timedelta(seconds=1), prior_artifact=prior)
    assert result == prior


def test_dc_c03_late_creation_anchors_geometry_to_cutoff():
    baseline = _conditional(_create(h1=_rows("1h", count=242),
                                    m15=_rows("15min", count=242)))
    late_h1 = _rows("1h", count=242)
    late_m15 = _rows("15min", count=242)
    late_h1.append({**late_h1[-1], "at": "2026-08-27T02:00:00Z"})
    late_m15.append({**late_m15[-1], "at": "2026-08-27T01:15:00Z"})
    late = _conditional(_create(now=CUTOFF + timedelta(minutes=10),
                                h1=late_h1, m15=late_m15))
    assert late["session_cutoff"] == baseline["session_cutoff"]
    assert late["watch_geometry"] == baseline["watch_geometry"]


def test_dc_c04_strict_wait_trigger_is_not_required():
    conditional = _conditional(_create(strict=_strict("WAIT_TRIGGER", "buy", plan={"variant": "B"})))
    assert conditional["status"] == "NOT_REQUIRED_STRICT_AVAILABLE"
    assert conditional["legs"] == []
    _assert_no_forbidden(conditional)


def test_dc_c05_strict_entry_ready_is_not_required():
    conditional = _conditional(_create(strict=_strict("ENTRY_READY", "sell", plan={"variant": "B"})))
    assert conditional["status"] == "NOT_REQUIRED_STRICT_AVAILABLE"
    assert conditional["legs"] == []


def test_dc_c06_no_plan_and_no_chase_start_two_sided_armed():
    for state in ("NO_PLAN", "NO_CHASE"):
        conditional = _conditional(_create(strict=_strict(state)))
        assert conditional["status"] == "ARMED"
        assert [leg["side"] for leg in conditional["legs"]] == ["buy", "sell"]
        assert conditional["selected_side"] is None
        assert conditional["trigger_bar_at"] is None
        _assert_no_forbidden(conditional)


def test_dc_c07_invalid_or_nonfinite_geometry_fails_closed_without_legs():
    h1 = _rows("1h")
    h1[-11]["high"] = math.inf
    result = _create(h1=h1)
    conditional = _conditional(result)
    assert conditional["status"] in {"STALE_DATA", "INVALIDATED"}
    assert conditional.get("legs", []) == []


# --- Trigger semantics and cancellation (8) --------------------------------

def test_dc_t01_buy_trigger_requires_close_strictly_above():
    creation = _create()
    result = _evaluate(creation, m15=_m15_with_close(111.0))
    conditional = _conditional(result)
    assert conditional["status"] == "WATCH_TRIGGERED_WAIT_REVALIDATION"
    assert conditional["selected_side"] == "buy"


def test_dc_t02_sell_trigger_requires_close_strictly_below():
    creation = _create()
    result = _evaluate(creation, m15=_m15_with_close(89.0))
    conditional = _conditional(result)
    assert conditional["status"] == "WATCH_TRIGGERED_WAIT_REVALIDATION"
    assert conditional["selected_side"] == "sell"


def test_dc_t03_equality_does_not_trigger_even_at_tolerance_boundary():
    creation = _create()
    result = _evaluate(creation, m15=_m15_with_close(110.66))
    conditional = _conditional(result)
    assert conditional["status"] == "ARMED"
    assert conditional["selected_side"] is None


def test_dc_t04_intrabar_wick_without_close_does_not_trigger():
    m15 = _rows("15min", after_cutoff=True)
    m15[-1].update({"high": 111.0, "low": 99.0, "close": 100.0})
    conditional = _conditional(_evaluate(_create(), m15=m15))
    assert conditional["status"] == "ARMED"
    assert conditional["trigger_bar_at"] is None


def test_dc_t05_first_buy_trigger_cancels_opposite_forever():
    creation = _create()
    m15 = _m15_with_close(111.0, at_offset=2)
    m15[-1]["close"] = 89.0
    m15[-1]["open"] = m15[-1]["high"] = m15[-1]["low"] = 89.0
    conditional = _conditional(_evaluate(creation, m15=m15))
    assert conditional["selected_side"] == "buy"
    assert any(leg["side"] == "sell" and leg["status"] == "CANCELLED_BY_OPPOSITE_TRIGGER"
               for leg in conditional["legs"])


def test_dc_t06_first_sell_trigger_cancels_opposite_forever():
    creation = _create()
    m15 = _m15_with_close(89.0, at_offset=2)
    m15[-1]["close"] = 111.0
    m15[-1]["open"] = m15[-1]["high"] = m15[-1]["low"] = 111.0
    conditional = _conditional(_evaluate(creation, m15=m15))
    assert conditional["selected_side"] == "sell"
    assert any(leg["side"] == "buy" and leg["status"] == "CANCELLED_BY_OPPOSITE_TRIGGER"
               for leg in conditional["legs"])


def test_dc_t07_trigger_bar_never_produces_ready_plan():
    creation = _create()
    strict_ready = _strict("ENTRY_READY", "buy", plan={"variant": "B", "stop": 1, "tp1": 2})
    conditional = _conditional(_evaluate(creation, strict=strict_ready,
                                         m15=_m15_with_close(111.0)))
    assert conditional["status"] == "WATCH_TRIGGERED_WAIT_REVALIDATION"
    _assert_no_forbidden(conditional)


def test_dc_t08_dual_trigger_or_unordered_events_fail_closed():
    creation = _create()
    m15 = _m15_with_close(111.0)
    m15[-2]["close"] = 89.0
    with pytest.raises(_dc().ContractError):
        _evaluate(creation, m15=m15)


# --- On-demand stateless evaluation, idempotency and concurrency (7) --------

def test_dc_o01_no_rerun_does_not_mutate_creation_to_expired():
    creation = _create()
    before = copy.deepcopy(creation)
    assert creation == before
    assert _conditional(creation)["status"] == "ARMED"
    assert _conditional(creation)["expires_at"] == "2026-08-28T08:00:00+07:00"


def test_dc_o02_one_rerun_writes_derived_only():
    creation = _create()
    original = _canonical(creation)
    derived = _evaluate(creation, m15=_m15_with_close(111.0))
    assert _canonical(creation) == original
    assert derived is not creation
    assert derived["evaluation_cutoff"]


def test_dc_o03_same_input_rerun_is_byte_idempotent():
    creation = _create()
    left = _evaluate(creation)
    right = _evaluate(creation)
    assert _canonical(left) == _canonical(right)
    assert _digest(left) == _digest(right)


def test_dc_o04_multiple_reruns_recompute_from_immutable_creation():
    creation = _create()
    first = _evaluate(creation, m15=_m15_with_close(111.0))
    second = _evaluate(creation, m15=_m15_with_close(100.0))
    fresh = _evaluate(copy.deepcopy(creation), m15=_m15_with_close(100.0))
    assert _canonical(second) == _canonical(fresh)
    assert _canonical(creation) != _canonical(first) or _conditional(first)["status"] != "ARMED"


def test_dc_o05_out_of_order_completion_cannot_overwrite_newer_cutoff():
    creation = _create()
    late = _evaluate(creation, evaluated_at=CUTOFF + timedelta(hours=2))
    early = _evaluate(creation, evaluated_at=CUTOFF + timedelta(hours=1))
    assert late["evaluation_cutoff"] != early["evaluation_cutoff"]
    assert _conditional(late)["session_cutoff"] == _conditional(early)["session_cutoff"]
    assert _canonical(creation) == _canonical(_create())


def test_dc_o06_concurrent_identical_evaluations_are_deterministic():
    creation = _create()
    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(lambda _: _evaluate(creation), range(4)))
    assert len({_digest(output) for output in outputs}) == 1


def test_dc_o07_evaluation_is_stateless_and_has_no_mutable_latest_record():
    creation = _create()
    first = _evaluate(creation, evaluated_at=CUTOFF + timedelta(hours=1))
    second = _evaluate(creation, evaluated_at=CUTOFF + timedelta(hours=2))
    assert first["evaluation_cutoff"] != second["evaluation_cutoff"]
    assert "latest" not in second and "latest" not in first


# --- Strict B100 revalidation and compatibility (6) -------------------------

def test_dc_r01_buy_next_closed_bar_can_be_ready_by_strict_b100():
    creation = _create()
    plan = {"variant": "B", "protective_stop": {"active": False}, "tp1": 115.0, "tp2": 120.0}
    result = _evaluate(creation, strict=_strict("WAIT_TRIGGER", "buy", plan=plan),
                       m15=_m15_with_close(111.0, at_offset=2))
    conditional = _conditional(result)
    assert conditional["status"] == "READY_AFTER_STRICT_REVALIDATION"
    assert conditional["strict_plan_ref"]["session_id"]
    assert set(conditional["strict_plan_ref"]) == {"session_id", "evaluation_cutoff", "strict_plan_sha256"}
    _assert_no_forbidden(conditional)


def test_dc_r02_sell_next_closed_bar_can_be_ready_by_strict_b100():
    creation = _create()
    plan = {"variant": "B", "protective_stop": {"active": False}, "tp1": 85.0, "tp2": 80.0}
    result = _evaluate(creation, strict=_strict("ENTRY_READY", "sell", plan=plan),
                       m15=_m15_with_close(89.0, at_offset=2))
    assert _conditional(result)["status"] == "READY_AFTER_STRICT_REVALIDATION"


def test_dc_r03_strict_no_plan_keeps_waiting_without_fallback():
    creation = _create()
    result = _evaluate(creation, strict=_strict("NO_PLAN"), m15=_m15_with_close(111.0, at_offset=2))
    conditional = _conditional(result)
    assert conditional["status"] == "WATCH_TRIGGERED_WAIT_REVALIDATION"
    _assert_no_forbidden(conditional)


def test_dc_r04_opposite_strict_bias_invalidates_locked_side():
    creation = _create()
    plan = {"variant": "B", "protective_stop": {"active": False}}
    result = _evaluate(creation, strict=_strict("WAIT_TRIGGER", "sell", plan=plan),
                       m15=_m15_with_close(111.0, at_offset=2))
    assert _conditional(result)["status"] == "INVALIDATED"
    _assert_no_forbidden(_conditional(result))


def test_dc_r05_all_b100_rejections_have_no_a_fallback_or_trade_fields():
    creation = _create()
    for reason in ("NO_CONFIRMED_SWING", "STOP_GT_3ATR", "TARGET_SPACE_LT_1_5R"):
        result = _evaluate(creation, strict=_strict("NO_PLAN", reason=reason),
                           m15=_m15_with_close(111.0, at_offset=2))
        conditional = _conditional(result)
        assert conditional["status"] == "WATCH_TRIGGERED_WAIT_REVALIDATION"
        _assert_no_forbidden(conditional)
        # The machine state contains the letter A (REVALIDATION); guard the
        # actual forbidden A-style fallback marker instead of any character.
        assert '"variant": "A"' not in json.dumps(conditional, ensure_ascii=False)


def test_dc_r06_strict_v4_projection_and_hash_remain_unchanged():
    strict = _strict("NO_PLAN")
    conditional = _conditional(_create(strict=strict))
    projection = {
        "state": strict["state"], "side": strict["side"], "plan": strict["plan"],
        "adaptive_reason_code": strict["adaptive_reason_code"],
        "adaptive_stop": strict["adaptive_stop"],
        "adaptive_context_sha256": strict["adaptive_context"]["sha256"],
        "lifecycle": strict["lifecycle"],
    }
    assert conditional["strict_projection_hash"] == _digest(projection)


# --- Expiry and session boundary (5) ----------------------------------------

def test_dc_x01_bar_before_expiry_is_eligible():
    result = _evaluate(_create(), evaluated_at=EXPIRY - timedelta(seconds=1),
                       m15=_m15_with_close(111.0))
    assert _conditional(result)["status"] == "WATCH_TRIGGERED_WAIT_REVALIDATION"


def test_dc_x02_expiry_precedes_any_new_trigger():
    result = _evaluate(_create(), evaluated_at=EXPIRY, m15=_m15_with_close(111.0))
    conditional = _conditional(result)
    assert conditional["status"] == "EXPIRED"
    assert conditional.get("selected_side") is None


def test_dc_x03_bar_closing_exactly_at_expiry_is_ineligible():
    m15 = _m15_with_close(111.0)
    m15[-1]["at"] = EXPIRY.astimezone(UTC).isoformat().replace("+00:00", "Z")
    result = _evaluate(_create(), evaluated_at=EXPIRY - timedelta(seconds=1), m15=m15)
    assert _conditional(result)["status"] == "ARMED"


def test_dc_x04_next_session_does_not_carry_previous_state():
    old = _create()
    new_cutoff = EXPIRY
    new = _dc().create(
        strict_story=_strict(), h1_rows=_rows("1h"), m15_rows=_rows("15min"),
        session_cutoff=new_cutoff, now=new_cutoff,
        h1_basis=_basis("1h", close_at=new_cutoff),
        m15_basis=_basis("15min", close_at=new_cutoff), prior_artifact=old)
    assert _conditional(new)["session_cutoff"] != _conditional(old)["session_cutoff"]
    assert _conditional(new)["selected_side"] is None


def test_dc_x05_utc_and_bangkok_timestamps_are_equivalent():
    left = _conditional(_create(now=CUTOFF))
    right = _conditional(_create(now=CUTOFF.astimezone(UTC)))
    assert left["session_cutoff"] == right["session_cutoff"]
    assert left["expires_at"] == right["expires_at"]
    assert _digest(left) == _digest(right)


# --- STALE_DATA and recovery (5) --------------------------------------------

def test_dc_s01_missing_closed_prefix_is_stale_without_event():
    m15 = _rows("15min", after_cutoff=True)[:-2]
    conditional = _conditional(_evaluate(_create(), m15=m15))
    assert conditional["status"] == "STALE_DATA"
    assert conditional.get("selected_side") is None


def test_dc_s02_gap_duplicate_or_out_of_order_prefix_is_stale():
    m15 = _rows("15min")
    m15[-1]["at"] = m15[-2]["at"]
    conditional = _conditional(_evaluate(_create(), m15=m15))
    assert conditional["status"] == "STALE_DATA"
    assert conditional.get("selected_side") is None


def test_dc_s03_forming_or_future_bar_is_stale():
    m15 = _rows("15min", forming=True)
    conditional = _conditional(_evaluate(_create(), m15=m15))
    assert conditional["status"] == "STALE_DATA"
    future = _rows("15min", after_cutoff=True)
    future[-1]["close_at"] = (CUTOFF + timedelta(hours=3)).astimezone(UTC).isoformat().replace("+00:00", "Z")
    conditional = _conditional(_evaluate(_create(), m15=future))
    assert conditional["status"] == "STALE_DATA"


def test_dc_s04_invalid_source_basis_is_stale():
    with pytest.raises(_dc().StaleData):
        _create(h1_basis={**_basis("1h"), "candle_state": "forming"})


def test_dc_s05_recovery_recomputes_from_creation_not_stale_cache():
    creation = _create()
    stale = _evaluate(creation, m15=_rows("15min", forming=True))
    recovered = _evaluate(creation, m15=_m15_with_close(111.0))
    fresh = _evaluate(copy.deepcopy(creation), m15=_m15_with_close(111.0))
    assert _conditional(stale)["status"] == "STALE_DATA"
    assert _canonical(recovered) == _canonical(fresh)


# --- Tamper, hash and forbidden fields (8) ----------------------------------

def test_dc_h01_watch_geometry_tamper_is_rejected():
    conditional = _conditional(_create())
    conditional["watch_geometry"]["buy_watch"] = "999.00"
    with pytest.raises(_dc().ContractError):
        _dc().validate(conditional, strict_story=_strict(), now=CUTOFF)


def test_dc_h02_session_cutoff_or_expiry_tamper_is_rejected():
    conditional = _conditional(_create())
    conditional["expires_at"] = "2026-08-29T08:00:00+07:00"
    with pytest.raises(_dc().ContractError):
        _dc().validate(conditional, strict_story=_strict(), now=CUTOFF)


def test_dc_h03_status_selection_and_trigger_bar_tamper_is_rejected():
    conditional = _conditional(_create())
    conditional["status"] = "READY_AFTER_STRICT_REVALIDATION"
    conditional["selected_side"] = "buy"
    with pytest.raises(_dc().ContractError):
        _dc().validate(conditional, strict_story=_strict(), now=CUTOFF)


def test_dc_h04_strict_reference_or_projection_hash_tamper_is_rejected():
    conditional = _conditional(_create())
    conditional["strict_projection_hash"] = "0" * 64
    with pytest.raises(_dc().ContractError):
        _dc().validate(conditional, strict_story=_strict(), now=CUTOFF)


def test_dc_h05_conditional_sha256_tamper_is_rejected():
    conditional = _conditional(_create())
    conditional["sha256"] = "0" * 64
    with pytest.raises(_dc().ContractError):
        _dc().validate(conditional, strict_story=_strict(), now=CUTOFF)


def test_dc_h06_every_forbidden_field_is_rejected_before_ready():
    for field in FORBIDDEN:
        conditional = _conditional(_create())
        conditional[field] = 1
        with pytest.raises(_dc().ContractError):
            _dc().validate(conditional, strict_story=_strict(), now=CUTOFF)


def test_dc_h07_ready_has_reference_only_not_duplicate_trade_geometry():
    strict = _strict("ENTRY_READY", "buy", plan={"variant": "B"})
    conditional = _conditional(_evaluate(_create(), strict=strict,
                                         m15=_m15_with_close(111.0, at_offset=2)))
    assert set(conditional["strict_plan_ref"]) == {"session_id", "evaluation_cutoff", "strict_plan_sha256"}
    _assert_no_forbidden(conditional)


def test_dc_h08_planless_story_never_exposes_ghost_levels():
    conditional = _conditional(_create())
    _assert_no_forbidden(conditional)
    assert conditional["status"] == "ARMED"


# --- Content/package and scope/security guards (5) --------------------------

def test_dc_p01_writer_keeps_strict_no_plan_and_labels_watch_not_entry():
    story = _create()
    story["story"]["_incomplete_fixture"] = True
    writer = importlib.import_module("tools.style_e_plus_writer")
    markdown = writer.render_article(story["story"] if "story" in story else story)
    assert "NO_PLAN" in markdown
    assert "ไม่ใช่จุดเข้า" in markdown or "NOT ENTRY" in markdown
    assert "SL" not in markdown.split("Daily Conditional", 1)[-1]


def test_dc_p02_package_visual_replay_hash_and_output_scope_are_separate():
    dc = _dc()
    creation = _create()
    assert creation["manifest"]["conditional_sha256"] == _conditional(creation)["sha256"]
    assert creation["manifest"]["story_schema"] == "style-e-plus-story/v5"
    assert creation["manifest"]["source_snapshot_schema"] == "style-e-plus-source-snapshot/v3"
    assert creation["manifest"]["schema"] == "style-e-plus-manifest/v5"
    replay = dc.replay(creation)
    assert _canonical(replay) == _canonical(creation)
    assert "0-ขึ้นเว็บวันนี้" not in json.dumps(creation, ensure_ascii=False)


def test_dc_g01_import_has_no_network_or_cwd_side_effect():
    calls = []
    before = sorted(path.name for path in Path.cwd().iterdir())
    original_urlopen = urllib.request.urlopen
    original_connect = socket.create_connection
    urllib.request.urlopen = lambda *args, **kwargs: calls.append(args) or (_ for _ in ()).throw(
        AssertionError("network during DC import"))
    socket.create_connection = lambda *args, **kwargs: calls.append(args) or (_ for _ in ()).throw(
        AssertionError("socket during DC import"))
    try:
        importlib.import_module("tools.style_e_plus_daily_conditional")
    finally:
        urllib.request.urlopen = original_urlopen
        socket.create_connection = original_connect
    assert calls == []
    assert sorted(path.name for path in Path.cwd().iterdir()) == before


def test_dc_g02_pure_evaluation_uses_explicit_rows_without_fetch_or_scheduler():
    dc = _dc()
    forbidden = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("implicit fetch/poll"))
    original = getattr(dc, "fetch_rows", None)
    if original is not None:
        dc.fetch_rows = forbidden
    try:
        result = dc.evaluate(
            creation=_create(), strict_story=_strict(), h1_rows=_rows("1h"),
            m15_rows=_rows("15min"), evaluated_at=CUTOFF + timedelta(hours=1))
    finally:
        if original is not None:
            dc.fetch_rows = original
    assert result
    assert not any(isinstance(t, threading.Thread) and t.is_alive()
                   for t in threading.enumerate() if t.name != threading.current_thread().name)


def test_dc_g03_execution_and_research_surfaces_are_forbidden():
    conditional = _conditional(_create())
    assert conditional["manual_only"] is True
    assert conditional["execution_enabled"] is False
    assert "style_e_plus_adaptive_stop_ab" not in json.dumps(conditional)
    _assert_no_forbidden(conditional)


# --- Contract Gate hardening (7) --------------------------------------------

def test_dc_gate_exact_conditional_schema_and_role():
    dc = _dc()
    conditional = _conditional(_create())
    assert set(conditional) == dc.CONDITIONAL_KEYS
    assert conditional["role"] == "secondary_additive"
    assert conditional["contract"] == "DC-T/v1"
    assert "contract_version" not in conditional
    assert "session_id" not in conditional
    assert conditional["creation_basis"] == {
        "h1_bar_at": "2026-08-27T00:00:00Z",
        "m15_bar_at": "2026-08-27T00:45:00Z",
    }
    assert conditional["legs"] == [
        {"side": "buy", "status": "ARMED",
         "trigger_rule": "m15_close_strictly_above_buy_watch"},
        {"side": "sell", "status": "ARMED",
         "trigger_rule": "m15_close_strictly_below_sell_watch"},
    ]


def test_dc_gate_naive_timestamp_is_rejected():
    with pytest.raises(_dc().ContractError):
        _dc().create(strict_story=_strict(), h1_rows=_rows("1h"),
                     m15_rows=_rows("15min"), session_cutoff="2026-08-27 08:00:00",
                     now=CUTOFF, h1_basis=_basis("1h"), m15_basis=_basis("15min"))


def test_dc_gate_post_0800_observed_prefix_uses_explicit_close_at():
    creation = _create()
    m15 = _rows("15min", after_cutoff=True)
    m15[-1]["close"] = 111.0
    m15[-1]["open"] = 111.0
    m15[-1]["high"] = 111.0
    m15[-1]["low"] = 111.0
    m15[-1]["close_at"] = "2026-08-27T01:30:00Z"
    result = _evaluate(creation, m15=m15,
                       evaluated_at=datetime(2026, 8, 27, 10, 0, tzinfo=BANGKOK))
    assert _conditional(result)["selected_side"] == "buy"
    assert _conditional(result)["trigger_bar_at"] == "2026-08-27T01:30:00Z"


def test_dc_gate_close_at_not_row_at_controls_eligibility():
    creation = _create()
    m15 = _rows("15min", after_cutoff=True)
    m15[-1]["close"] = 111.0
    m15[-1]["open"] = 111.0
    m15[-1]["high"] = 111.0
    m15[-1]["low"] = 111.0
    m15[-1]["close_at"] = "2026-08-28T01:00:00Z"
    result = _evaluate(creation, m15=m15,
                       evaluated_at=datetime(2026, 8, 27, 10, 0, tzinfo=BANGKOK))
    assert _conditional(result)["status"] == "ARMED"


def test_dc_gate_unknown_key_rejected_even_with_recomputed_hash():
    conditional = _conditional(_create())
    conditional["unknown"] = True
    conditional["sha256"] = _digest({key: value for key, value in conditional.items()
                                      if key != "sha256"})
    with pytest.raises(_dc().ContractError):
        _dc().validate(conditional, strict_story=_strict(), now=CUTOFF)


def test_dc_gate_revalidation_requires_variant_b():
    creation = _create()
    strict_a = _strict("WAIT_TRIGGER", "buy", plan={"variant": "A"})
    result = _evaluate(creation, strict=strict_a,
                       m15=_m15_with_close(111.0, at_offset=2))
    assert _conditional(result)["status"] == "WATCH_TRIGGERED_WAIT_REVALIDATION"
    assert _conditional(result)["strict_plan_ref"] is None


def test_dc_gate_persistence_keys_are_deterministic_and_storage_free():
    dc = _dc()
    creation = _create()
    key = dc.evaluation_key(creation, evaluated_at=CUTOFF + timedelta(hours=1),
                            observed_prefix_hash="b" * 64)
    assert key == dc.evaluation_key(creation, evaluated_at=CUTOFF + timedelta(hours=1),
                                    observed_prefix_hash="b" * 64)
    assert key != dc.evaluation_key(creation, evaluated_at=CUTOFF + timedelta(hours=2),
                                    observed_prefix_hash="b" * 64)
    assert not any(path.name.startswith("latest") for path in Path.cwd().iterdir())


# --- Tester Gate T hardening (6) --------------------------------------------

def test_dc_gate_state_invariants_reject_duplicate_or_mismatched_legs_after_hash():
    dc = _dc()
    conditional = _conditional(_create())
    conditional["legs"][1] = copy.deepcopy(conditional["legs"][0])
    conditional["sha256"] = _digest({key: value for key, value in conditional.items()
                                      if key != "sha256"})
    with pytest.raises(dc.ContractError):
        dc.validate(conditional, strict_story=_strict(), now=CUTOFF)

    triggered = _conditional(_evaluate(_create(), m15=_m15_with_close(111.0)))
    triggered["selected_side"] = None
    triggered["sha256"] = _digest({key: value for key, value in triggered.items()
                                    if key != "sha256"})
    with pytest.raises(dc.ContractError):
        dc.validate(triggered, strict_story=_strict(), now=CUTOFF + timedelta(hours=1))


def test_dc_gate_geometry_semantics_reject_invalid_order_and_nonfinite_values_after_hash():
    dc = _dc()
    for buy, sell in (("80.00", "90.00"), ("NaN", "89.00")):
        conditional = _conditional(_create())
        conditional["watch_geometry"]["buy_watch"] = buy
        conditional["watch_geometry"]["sell_watch"] = sell
        conditional["sha256"] = _digest({key: value for key, value in conditional.items()
                                          if key != "sha256"})
        with pytest.raises(dc.ContractError):
            dc.validate(conditional, strict_story=_strict(), now=CUTOFF)


def test_dc_gate_strict_reference_requires_canonical_timestamp_and_bound_plan():
    dc = _dc()
    strict = _strict("WAIT_TRIGGER", "buy", plan={"variant": "B", "tp1": 115.0})
    result = _evaluate(_create(), strict=strict, m15=_m15_with_close(111.0, at_offset=2))
    conditional = _conditional(result)
    conditional["strict_plan_ref"]["evaluation_cutoff"] = "2026-08-27T09:00:00"
    conditional["sha256"] = _digest({key: value for key, value in conditional.items()
                                      if key != "sha256"})
    with pytest.raises(dc.ContractError):
        dc.validate(conditional, strict_story=strict, now=CUTOFF + timedelta(hours=1))

    conditional = _conditional(result)
    conditional["strict_plan_ref"]["strict_plan_sha256"] = "b" * 64
    conditional["sha256"] = _digest({key: value for key, value in conditional.items()
                                      if key != "sha256"})
    with pytest.raises(dc.ContractError):
        dc.validate(conditional, strict_story=strict, now=CUTOFF + timedelta(hours=1))


def test_dc_gate_strict_oracle_rejects_top_level_tamper_with_recomputed_hash():
    dc = _dc()
    artifact = _create()
    tampered = copy.deepcopy(artifact)
    tampered["state"] = "WAIT_TRIGGER"
    tampered["side"] = "buy"
    tampered["daily_conditional"]["strict_projection_hash"] = dc._strict_hash(
        _strict("WAIT_TRIGGER", "buy"))
    conditional = tampered["daily_conditional"]
    conditional["sha256"] = _digest({key: value for key, value in conditional.items()
                                      if key != "sha256"})
    with pytest.raises(dc.ContractError):
        dc.validate(tampered, strict_story=dc._strict_from_artifact(tampered), now=CUTOFF)


def test_dc_gate_writer_fails_closed_for_unmarked_incomplete_strict_story():
    writer = importlib.import_module("tools.style_e_plus_writer")
    story = copy.deepcopy(_create()["story"])
    story.pop("_incomplete_fixture", None)
    with pytest.raises(writer.style_e_plus_story.StoryUnavailable):
        writer.render_article(story)


def test_dc_gate_pre0800_rejects_tampered_prior_before_returning_it():
    dc = _dc()
    prior = _create()
    prior["daily_conditional"]["expires_at"] = "2026-08-29T08:00:00+07:00"
    prior["daily_conditional"]["sha256"] = _digest({
        key: value for key, value in prior["daily_conditional"].items()
        if key != "sha256"})
    with pytest.raises(dc.NoValidPriorSession):
        _create(now=CUTOFF - timedelta(seconds=1), prior_artifact=prior)


def test_dc_gate_geometry_requires_creation_oracle_after_recomputed_conditional_hash():
    dc = _dc()
    artifact = _create()
    artifact["daily_conditional"]["watch_geometry"] = {
        "donchian_length": 20, "watch_buffer_h1_atr": 0.25,
        "buy_watch": "109.00", "sell_watch": "999.00",
    }
    conditional = artifact["daily_conditional"]
    conditional["sha256"] = _digest({key: value for key, value in conditional.items()
                                      if key != "sha256"})
    with pytest.raises(dc.ContractError):
        dc.validate(artifact, strict_story=dc._strict_from_artifact(artifact), now=CUTOFF)


def test_dc_gate_final_m15_malformed_ohlc_or_close_at_is_stale():
    m15 = _m15_with_close(111.0)
    m15[-1]["high"] = 100.0
    conditional = _conditional(_evaluate(_create(), m15=m15))
    assert conditional["status"] == "STALE_DATA"

    m15 = _m15_with_close(111.0)
    m15[-1]["close_at"] = "not-a-timestamp"
    conditional = _conditional(_evaluate(_create(), m15=m15))
    assert conditional["status"] == "STALE_DATA"


def test_dc_gate_planless_strict_status_cannot_be_labeled_not_required():
    conditional = _conditional(_create(strict=_strict("WAIT_TRIGGER", "buy")))
    assert conditional["status"] == "ARMED"


def test_dc_gate_ready_propagates_revalidated_strict_projection_consistently():
    dc = _dc()
    strict = _strict("WAIT_TRIGGER", "buy", plan={"variant": "B", "tp1": 115.0})
    result = _evaluate(_create(), strict=strict,
                       m15=_m15_with_close(111.0, at_offset=2))
    assert result["state"] == strict["state"]
    assert result["side"] == strict["side"]
    assert result["plan"] == strict["plan"]
    conditional = result["daily_conditional"]
    assert conditional["strict_projection_hash"] == dc._strict_hash(strict)
    assert result["strict_projection_oracle"]["projection"] == dc._strict_projection(strict)
    assert conditional["strict_plan_ref"]["strict_plan_sha256"] == _digest(strict["plan"])


def test_dc_gate_writer_rejects_conditional_tamper_even_when_sha_is_recomputed():
    writer = importlib.import_module("tools.style_e_plus_writer")
    story = copy.deepcopy(_create()["story"])
    story["daily_conditional"]["watch_geometry"]["buy_watch"] = "999.00"
    conditional = story["daily_conditional"]
    conditional["sha256"] = _digest({key: value for key, value in conditional.items()
                                      if key != "sha256"})
    with pytest.raises(writer.style_e_plus_story.StoryUnavailable):
        writer.render_article(story)


def test_dc_gate_strict_status_parity_rejects_relabel_after_conditional_rehash():
    dc = _dc()
    artifact = _create()
    conditional = artifact["daily_conditional"]
    conditional["status"] = "NOT_REQUIRED_STRICT_AVAILABLE"
    conditional["legs"] = []
    conditional["sha256"] = _digest({key: value for key, value in conditional.items()
                                      if key != "sha256"})
    with pytest.raises(dc.ContractError):
        dc.validate(conditional, strict_story=_strict(),
                    geometry_oracle=artifact["watch_geometry_oracle"], now=CUTOFF)


def test_dc_gate_h1_final_malformed_ohlc_or_close_at_is_stale():
    h1 = _rows("1h")
    h1[-1]["high"] = 99.0
    assert _conditional(_evaluate(_create(), h1=h1))["status"] == "STALE_DATA"

    h1 = _rows("1h")
    h1[-1]["close_at"] = "not-a-timestamp"
    assert _conditional(_evaluate(_create(), h1=h1))["status"] == "STALE_DATA"


def test_dc_gate_geometry_oracle_and_conditional_rehash_cannot_bypass_manifest_binding():
    dc = _dc()
    artifact = _create()
    geometry = artifact["daily_conditional"]["watch_geometry"]
    geometry["buy_watch"] = "109.00"
    geometry["sell_watch"] = "89.00"
    artifact["watch_geometry_oracle"] = {
        "geometry": copy.deepcopy(geometry), "sha256": _digest(geometry),
    }
    conditional = artifact["daily_conditional"]
    conditional["sha256"] = _digest({key: value for key, value in conditional.items()
                                      if key != "sha256"})
    with pytest.raises(dc.ContractError):
        dc.validate(artifact, strict_story=dc._strict_from_artifact(artifact), now=CUTOFF)


def test_dc_gate_no_event_keeps_root_and_nested_strict_projection_byte_equivalent():
    dc = _dc()
    strict = _strict("WAIT_TRIGGER", "buy", plan={"variant": "B", "tp1": 115.0})
    result = _evaluate(_create(), strict=strict, m15=_rows("15min"))
    assert result["state"] == strict["state"]
    assert result["plan"] == strict["plan"]
    assert result["story"]["strict_projection_oracle"]["projection"] == dc._strict_projection(strict)
    assert result["daily_conditional"]["strict_projection_hash"] == dc._strict_hash(strict)


def test_dc_gate_replay_and_evaluate_reject_derived_artifact_inputs():
    dc = _dc()
    creation = _create()
    derived = _evaluate(creation)
    with pytest.raises(dc.ContractError):
        dc.replay(derived)
    with pytest.raises(dc.ContractError):
        dc.evaluate(creation=derived, strict_story=_strict(), h1_rows=_rows("1h"),
                    m15_rows=_rows("15min"), evaluated_at=CUTOFF + timedelta(hours=1))


def test_dc_gate_basis_must_match_selected_closed_prefix_rows():
    dc = _dc()
    mismatched = _basis("1h", close_at=CUTOFF - timedelta(hours=1))
    artifact = _create(h1_basis=mismatched)
    assert _conditional(artifact)["status"] == "STALE_DATA"
    with pytest.raises(dc.StaleData):
        dc.create(strict_story=_strict(), h1_rows=_rows("1h"), m15_rows=_rows("15min"),
                  session_cutoff=CUTOFF, now=CUTOFF, h1_basis=_basis("15min"),
                  m15_basis=_basis("15min"))


def test_dc_gate_revalidation_uses_only_immediate_next_closed_bar():
    creation = _create()
    strict = _strict("WAIT_TRIGGER", "buy", plan={"variant": "B"})
    m15 = _m15_with_close(111.0)
    m15[-3]["close"] = m15[-3]["open"] = m15[-3]["high"] = m15[-3]["low"] = 111.0
    m15[-2]["close"] = m15[-2]["open"] = m15[-2]["high"] = m15[-2]["low"] = 100.0
    result = _evaluate(creation, strict=strict, m15=m15)
    assert _conditional(result)["status"] == "WATCH_TRIGGERED_WAIT_REVALIDATION"


def test_dc_gate_nested_story_geometry_oracle_tamper_fails_against_manifest():
    dc = _dc()
    story = copy.deepcopy(_create()["story"])
    geometry = story["daily_conditional"]["watch_geometry"]
    geometry["buy_watch"] = "109.00"
    geometry["sell_watch"] = "89.00"
    story["watch_geometry_oracle"] = {
        "geometry": copy.deepcopy(geometry), "sha256": _digest(geometry),
    }
    story["daily_conditional"]["sha256"] = _digest({
        key: value for key, value in story["daily_conditional"].items()
        if key != "sha256"})
    with pytest.raises(dc.ContractError):
        dc.validate(story, strict_story=dc._strict_from_artifact(story))
