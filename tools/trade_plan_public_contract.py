"""Fail-closed public trade-plan contract shared by daily D/E/L/M lanes.

This module validates release metadata only.  It never derives, adjusts, or
fills a price level.  Style-specific calculation code remains responsible for
the plan and may issue ``DATA_HOLD`` instead of a publishable contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any


SCHEMA = "p002-public-trade-plan/v1"
REPORT_SCHEMA = "p002-public-trade-plan-validation/v1"
PUBLISHABLE_STATUSES = {"WAIT_TRIGGER", "ACTIVE"}
FORBIDDEN_PUBLIC_STATUSES = {"DATA_HOLD", "BLOCK_QA"}
SIDES = {"BUY", "SELL", "OCO"}
LEG_SIDES = {"BUY", "SELL"}
RR_DISCLOSURE = "RR ยังไม่หัก spread/slippage"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
TOP_KEYS = {"schema", "style_id", "asset", "article", "article_sha256",
            "qa_status", "publishable", "plan_status", "side", "current_close",
            "cutoff_at", "valid_until", "evidence_hash", "rr_policy_version", "plans"}
LEG_KEYS = {"side", "trigger", "entry_zone", "stop_loss", "take_profit",
            "risk_reward", "rr_basis", "invalidation"}
POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "trade_plan_public_contract.json"


def load_policy(path: Path | None = None) -> dict[str, Any]:
    policy = json.loads((path or POLICY_PATH).read_text(encoding="utf-8"))
    required = {"schema_version", "contract_schema", "rr_policy_version",
                "minimum_gross_rr", "rr_geometry_tolerance", "rr_entry_reference",
                "rr_basis", "expiry_hours_by_style"}
    if not required <= set(policy):
        raise ValueError("trade-plan public policy ขาดฟิลด์บังคับ")
    if (policy["schema_version"] != 1 or policy["contract_schema"] != SCHEMA
            or policy["rr_basis"] != "gross_pre_cost"
            or policy["rr_entry_reference"] != "adverse_edge"
            or not _number(policy["minimum_gross_rr"])
            or not _number(policy["rr_geometry_tolerance"])
            or not isinstance(policy["expiry_hours_by_style"], dict)):
        raise ValueError("trade-plan public policy ไม่ถูกต้อง")
    return policy


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _finding(findings: list[dict[str, str]], code: str, field: str,
             message: str) -> None:
    findings.append({"code": code, "field": field, "message": message})


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)) and float(value) > 0)


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _walk_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_strings(nested)


def public_plan_block(contract: dict) -> str:
    """Canonical visible plan projection used for exact D/E/M article parity."""
    from tools import public_number_policy

    lines = ["**สัญญาแผนเทรดสาธารณะ**", "",
             f"- Side: **{contract['side']}**",
             f"- Status: **{contract['plan_status']}**"]
    for leg in contract["plans"]:
        trigger = public_number_policy.whole_number(leg["trigger"]["value"])
        low = public_number_policy.whole_number(leg["entry_zone"]["low"])
        high = public_number_policy.whole_number(leg["entry_zone"]["high"])
        stop = public_number_policy.whole_number(leg["stop_loss"])
        targets = ", ".join(public_number_policy.whole_number(value)
                            for value in leg["take_profit"])
        ratios = ", ".join(
            f"{Fraction(str(value)).limit_denominator(100).numerator} ต่อ "
            f"{Fraction(str(value)).limit_denominator(100).denominator}"
            for value in leg["risk_reward"])
        invalidation = leg["invalidation"]
        invalidation_value = (
            f" ที่ {public_number_policy.whole_number(invalidation['value'])}"
            if "value" in invalidation else "")
        lines.extend([
            f"- {leg['side']} Trigger: {leg['trigger']['condition']} ที่ {trigger}",
            f"- Entry Zone: {low}–{high}", f"- SL: {stop}", f"- TP: {targets}",
            f"- RR ({leg['rr_basis']}): {ratios}",
            f"- Invalidation: {invalidation['condition']}{invalidation_value}",
        ])
    lines.extend([
        f"- Cutoff at: {contract['cutoff_at']}",
        f"- Valid until: {contract['valid_until']}",
        f"- Evidence hash: `{contract['evidence_hash']}`",
        f"- {RR_DISCLOSURE}",
    ])
    return "\n".join(lines)


def _numbers_in_backticks(cell: str) -> list[float]:
    return [float(value.replace(",", "")) for value in
            re.findall(r"`([0-9][0-9,]*(?:\.[0-9]+)?)`", cell)]


def _same_numbers(actual: list[float], expected: list[Any], *, tolerance: float = 1e-9) -> bool:
    return (len(actual) == len(expected)
            and all(math.isclose(left, float(right), rel_tol=tolerance, abs_tol=tolerance)
                    for left, right in zip(actual, expected)))


def _style_l_parity(article: str, contract: dict) -> bool:
    if (f"| แผนสาธารณะ | **{contract.get('side')}** |" not in article
            or f"| สถานะตอนนี้ | **{contract.get('plan_status')}** |" not in article
            or f"- Cutoff at: `{contract.get('cutoff_at')}`" not in article
            or f"- Valid until: `{contract.get('valid_until')}`" not in article
            or f"- Evidence hash: `{contract.get('evidence_hash')}`" not in article):
        return False
    rows = {}
    row_counts = {}
    for line in article.splitlines():
        if line.startswith("| BUY |") or line.startswith("| SELL |"):
            cells = [cell.strip() for cell in line.split("|")[1:-1]]
            if len(cells) == 7:
                row_counts[cells[0]] = row_counts.get(cells[0], 0) + 1
                rows[cells[0]] = cells
    expected_sides = {leg.get("side") for leg in contract.get("plans", [])}
    if (set(rows) != expected_sides
            or any(row_counts.get(side, 0) != 1 for side in expected_sides)
            or sum(row_counts.values()) != len(expected_sides)):
        return False
    for leg in contract.get("plans", []):
        cells = rows[leg["side"]]
        trigger_word = "M15 ปิดเหนือ" if leg["side"] == "BUY" else "M15 ปิดต่ำกว่า"
        invalidation_word = "H1 ปิดต่ำกว่า" if leg["side"] == "BUY" else "H1 ปิดเหนือ"
        if (trigger_word not in cells[1] or invalidation_word not in cells[6]
                or not _same_numbers(_numbers_in_backticks(cells[1]), [leg["trigger"]["value"]])
                or not _same_numbers(_numbers_in_backticks(cells[2]),
                                     [leg["entry_zone"]["low"], leg["entry_zone"]["high"]])
                or not _same_numbers(_numbers_in_backticks(cells[3]), [leg["stop_loss"]])
                or not _same_numbers(_numbers_in_backticks(cells[4]), leg["take_profit"])
                or not all(_visible_ratio(cells[5], ratio)
                           for ratio in leg["risk_reward"])
                or not _same_numbers(_numbers_in_backticks(cells[6]),
                                     [leg["invalidation"].get("value")])):
            return False
    return True


def _number_variants(value: float) -> set[str]:
    """Return the decimal/rounded forms used by public number formatters."""
    variants = {str(value)}
    for places in range(0, 9):
        rendered = f"{float(value):,.{places}f}".rstrip("0").rstrip(".")
        variants.add(rendered)
        variants.add(rendered.replace(",", ""))
    return {item for item in variants if item and item not in {"-0", "-0.0"}}


def _visible_number(section: str, value: Any) -> bool:
    if not _number(value):
        return False
    return any(re.search(rf"(?<![\d.]){re.escape(token)}(?![\d.])", section)
               for token in _number_variants(float(value)))


def _visible_ratio(section: str, value: Any) -> bool:
    if not _number(value):
        return False
    rendered = f"{float(value):.2f}R"
    fraction = Fraction(str(value)).limit_denominator(100)
    return (rendered in section or f"{float(value):g}R" in section
            or f"{fraction.numerator} ต่อ {fraction.denominator}" in section)


def _validate_visible_plan(article_text: str, contract: dict[str, Any],
                           style_id: str, findings: list[dict[str, str]]) -> None:
    marker = ("**แผนตามสถานการณ์**" if style_id == "l_forex_daily_plan"
              else "**สัญญาแผนเทรดสาธารณะ**")
    start = article_text.find(marker)
    if start < 0:
        return
    section = article_text[start:]
    for index, leg in enumerate(contract.get("plans") or []):
        if not isinstance(leg, dict):
            continue
        prefix = f"plans[{index}]"
        side = leg.get("side")
        if f"{side}" not in section:
            _finding(findings, "ARTICLE_SIDE_MISMATCH", prefix + ".side",
                     "side ที่แสดงในบทไม่ตรงกับ sidecar")
        trigger = leg.get("trigger") or {}
        zone = leg.get("entry_zone") or {}
        checks = (("trigger.value", trigger.get("value")),
                  ("entry_zone.low", zone.get("low")),
                  ("entry_zone.high", zone.get("high")),
                  ("stop_loss", leg.get("stop_loss")))
        for field, value in checks:
            if not _visible_number(section, value):
                _finding(findings, "ARTICLE_VALUE_MISMATCH", f"{prefix}.{field}",
                         "ค่าระดับในบทไม่ตรงกับ canonical sidecar")
        for target_index, target in enumerate(leg.get("take_profit") or []):
            if not _visible_number(section, target):
                _finding(findings, "ARTICLE_VALUE_MISMATCH",
                         f"{prefix}.take_profit[{target_index}]",
                         "ค่า TP ในบทไม่ตรงกับ canonical sidecar")
        for rr_index, ratio in enumerate(leg.get("risk_reward") or []):
            if not _visible_ratio(section, ratio):
                _finding(findings, "ARTICLE_RR_MISMATCH",
                         f"{prefix}.risk_reward[{rr_index}]",
                         "ค่า RR ในบทไม่ตรงกับ canonical sidecar")
        invalidation = leg.get("invalidation") or {}
        if "value" in invalidation and not _visible_number(section, invalidation["value"]):
            _finding(findings, "ARTICLE_VALUE_MISMATCH", f"{prefix}.invalidation.value",
                     "ค่า invalidation ในบทไม่ตรงกับ canonical sidecar")
    if contract.get("evidence_hash") not in section:
        _finding(findings, "ARTICLE_EVIDENCE_MISMATCH", "evidence_hash",
                 "evidence hash ในบทไม่ตรงกับ canonical sidecar")
    valid_until = str(contract.get("valid_until"))
    if valid_until not in section and valid_until.rstrip("Z") not in section:
        _finding(findings, "ARTICLE_VALID_UNTIL_MISMATCH", "valid_until",
                 "valid_until ในบทไม่ตรงกับ canonical sidecar")
def _validate_leg(leg: Any, index: int, findings: list[dict[str, str]], *,
                  minimum_rr: float, plan_status: Any,
                  current_close: Any, rr_tolerance: float) -> None:
    prefix = f"plans[{index}]"
    if not isinstance(leg, dict):
        _finding(findings, "PLAN_NOT_OBJECT", prefix, "plan leg ต้องเป็น object")
        return
    for field in sorted(LEG_KEYS - set(leg)):
        _finding(findings, "PLAN_FIELD_MISSING", f"{prefix}.{field}",
                 "plan leg ขาดฟิลด์บังคับ")
    for field in sorted(set(leg) - LEG_KEYS):
        _finding(findings, "UNKNOWN_PLAN_FIELD", f"{prefix}.{field}",
                 "public plan leg ห้ามมีฟิลด์นอก schema")

    side = leg.get("side")
    if side not in LEG_SIDES:
        _finding(findings, "PLAN_SIDE_INVALID", f"{prefix}.side",
                 "plan leg ต้องเป็น BUY หรือ SELL")

    trigger = leg.get("trigger")
    if not isinstance(trigger, dict):
        _finding(findings, "TRIGGER_INVALID", f"{prefix}.trigger",
                 "trigger ต้องเป็น object")
    else:
        if set(trigger) != {"condition", "value"}:
            _finding(findings, "TRIGGER_KEYS_INVALID", f"{prefix}.trigger",
                     "trigger ต้องมีเฉพาะ condition/value")
        condition = trigger.get("condition")
        if not _nonempty(condition):
            _finding(findings, "TRIGGER_CONDITION_MISSING",
                     f"{prefix}.trigger.condition", "trigger ต้องมีเงื่อนไขแท่งปิด")
        elif (len(condition.strip()) < 8
              or not re.search(r"close|closed|ปิด", condition, flags=re.IGNORECASE)):
            _finding(findings, "TRIGGER_CONDITION_TOO_WEAK",
                     f"{prefix}.trigger.condition",
                     "trigger condition ต้องระบุ closed/close/ปิดอย่างชัดเจน")
        if not _number(trigger.get("value")):
            _finding(findings, "TRIGGER_VALUE_INVALID", f"{prefix}.trigger.value",
                     "trigger value ต้องเป็นตัวเลขบวกที่ finite")
        elif _number(current_close) and side in LEG_SIDES:
            trigger_value = float(trigger["value"])
            close_value = float(current_close)
            if plan_status == "WAIT_TRIGGER":
                strict = trigger_value > close_value if side == "BUY" else trigger_value < close_value
                if not strict:
                    _finding(findings, "WAIT_TRIGGER_ALREADY_CROSSED",
                             f"{prefix}.trigger.value",
                             "WAIT_TRIGGER ต้องยังไม่ข้าม trigger แบบ strict")
            elif plan_status == "ACTIVE":
                strict = close_value > trigger_value if side == "BUY" else close_value < trigger_value
                if not strict:
                    _finding(findings, "ACTIVE_TRIGGER_NOT_CROSSED",
                             f"{prefix}.trigger.value",
                             "ACTIVE ต้องข้าม trigger แบบ strict ด้วยราคาปิด")

    zone = leg.get("entry_zone")
    low = high = None
    if not isinstance(zone, dict):
        _finding(findings, "ENTRY_ZONE_INVALID", f"{prefix}.entry_zone",
                 "entry_zone ต้องเป็น object")
    else:
        if set(zone) != {"low", "high"}:
            _finding(findings, "ENTRY_ZONE_KEYS_INVALID", f"{prefix}.entry_zone",
                     "entry_zone ต้องมีเฉพาะ low/high")
        low, high = zone.get("low"), zone.get("high")
        if not _number(low) or not _number(high):
            _finding(findings, "ENTRY_ZONE_VALUE_INVALID", f"{prefix}.entry_zone",
                     "entry low/high ต้องเป็นตัวเลขบวกที่ finite")
        elif float(low) > float(high):
            _finding(findings, "ENTRY_ZONE_ORDER_INVALID", f"{prefix}.entry_zone",
                     "entry low ต้องไม่สูงกว่า entry high")

    stop = leg.get("stop_loss")
    if not _number(stop):
        _finding(findings, "STOP_LOSS_INVALID", f"{prefix}.stop_loss",
                 "stop_loss ต้องเป็นตัวเลขบวกที่ finite")

    targets = leg.get("take_profit")
    if (not isinstance(targets, list) or not targets
            or any(not _number(target) for target in targets)):
        _finding(findings, "TAKE_PROFIT_INVALID", f"{prefix}.take_profit",
                 "take_profit ต้องมีตัวเลขบวกอย่างน้อยหนึ่งค่า")

    ratios = leg.get("risk_reward")
    if (not isinstance(ratios, list) or not ratios
            or any(not _number(ratio) for ratio in ratios)):
        _finding(findings, "RISK_REWARD_INVALID", f"{prefix}.risk_reward",
                 "risk_reward ต้องมีตัวเลขบวกอย่างน้อยหนึ่งค่า")
    elif isinstance(targets, list) and len(ratios) != len(targets):
        _finding(findings, "RISK_REWARD_COUNT_MISMATCH", f"{prefix}.risk_reward",
                 "จำนวน RR ต้องตรงกับจำนวน TP")
    elif any(float(ratio) < minimum_rr for ratio in ratios):
        _finding(findings, "RISK_REWARD_BELOW_MINIMUM", f"{prefix}.risk_reward",
                 f"gross RR ทุกเป้าต้องไม่น้อยกว่า {minimum_rr:g}")
    if leg.get("rr_basis") != "gross_pre_cost":
        _finding(findings, "RR_BASIS_INVALID", f"{prefix}.rr_basis",
                 "TPR v1 ต้องระบุ RR เป็น gross_pre_cost จาก style oracle")

    invalidation = leg.get("invalidation")
    if not isinstance(invalidation, dict):
        _finding(findings, "INVALIDATION_INVALID", f"{prefix}.invalidation",
                 "invalidation ต้องเป็น object")
    else:
        if not set(invalidation) <= {"condition", "value"}:
            _finding(findings, "INVALIDATION_KEYS_INVALID", f"{prefix}.invalidation",
                     "invalidation มีฟิลด์นอก schema")
        if not _nonempty(invalidation.get("condition")):
            _finding(findings, "INVALIDATION_CONDITION_MISSING",
                     f"{prefix}.invalidation.condition",
                     "invalidation ต้องมีเงื่อนไขที่ตรวจสอบได้")
        if "value" in invalidation and not _number(invalidation.get("value")):
            _finding(findings, "INVALIDATION_VALUE_INVALID",
                     f"{prefix}.invalidation.value",
                     "invalidation value ต้องเป็นตัวเลขบวกที่ finite")

    if (side in LEG_SIDES and _number(stop) and _number(low) and _number(high)
            and isinstance(targets, list) and targets
            and all(_number(target) for target in targets)):
        if side == "BUY" and not (float(stop) < float(low) <= float(high)
                                   and all(float(target) > float(high) for target in targets)):
            _finding(findings, "PLAN_GEOMETRY_INVALID", prefix,
                     "BUY ต้องมี SL ต่ำกว่า entry และ TP สูงกว่า entry")
        if side == "SELL" and not (float(stop) > float(high) >= float(low)
                                    and all(float(target) < float(low) for target in targets)):
            _finding(findings, "PLAN_GEOMETRY_INVALID", prefix,
                     "SELL ต้องมี SL สูงกว่า entry และ TP ต่ำกว่า entry")
        adverse_entry = float(high) if side == "BUY" else float(low)
        risk = (adverse_entry - float(stop) if side == "BUY"
                else float(stop) - adverse_entry)
        rewards = ([float(target) - adverse_entry for target in targets]
                   if side == "BUY" else
                   [adverse_entry - float(target) for target in targets])
        if (risk > 0 and isinstance(ratios, list)
                and len(ratios) == len(rewards)
                and all(_number(ratio) for ratio in ratios)):
            for rr_index, (reward, claimed) in enumerate(zip(rewards, ratios)):
                actual = reward / risk
                if not math.isclose(actual, float(claimed), rel_tol=rr_tolerance,
                                    abs_tol=rr_tolerance):
                    _finding(findings, "RISK_REWARD_GEOMETRY_MISMATCH",
                             f"{prefix}.risk_reward[{rr_index}]",
                             "RR ต้องคำนวณจาก adverse entry edge ของ entry zone")


def validate(contract: Any, *, article_name: str, article_bytes: bytes,
             style_id: str, asset: str,
             publish_date: date | None = None,
             expected_evidence_hash: str | None = None,
             policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a deterministic validation report; never mutate the contract."""
    findings: list[dict[str, str]] = []
    if not isinstance(contract, dict):
        _finding(findings, "CONTRACT_NOT_OBJECT", "$", "contract ต้องเป็น object")
        return {"schema": REPORT_SCHEMA, "status": "FAIL", "findings": findings}

    try:
        policy = policy or load_policy()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _finding(findings, "RR_POLICY_INVALID", "rr_policy", str(exc))
        policy = {"rr_policy_version": None, "minimum_gross_rr": math.inf}
    for field in sorted(TOP_KEYS - set(contract)):
        _finding(findings, "CONTRACT_FIELD_MISSING", field,
                 "public trade-plan contract ขาดฟิลด์บังคับ")
    for field in sorted(set(contract) - TOP_KEYS):
        _finding(findings, "UNKNOWN_CONTRACT_FIELD", field,
                 "public contract ห้ามมีฟิลด์นอก schema")

    if contract.get("schema") != SCHEMA:
        _finding(findings, "SCHEMA_INVALID", "schema", f"schema ต้องเป็น {SCHEMA}")
    for field, expected in (("style_id", style_id), ("asset", asset),
                            ("article", article_name)):
        if contract.get(field) != expected:
            _finding(findings, "BINDING_MISMATCH", field,
                     f"{field} ต้องตรง lane/article: {expected}")

    article_hash = sha256_bytes(article_bytes)
    if contract.get("article_sha256") != article_hash:
        _finding(findings, "ARTICLE_HASH_MISMATCH", "article_sha256",
                 "contract ไม่ได้ผูกกับ bytes ของบทความปัจจุบัน")
    try:
        article_text = article_bytes.decode("utf-8")
    except UnicodeDecodeError:
        article_text = ""
    article_text = article_text.replace("\r\n", "\n")
    if RR_DISCLOSURE not in article_text:
        _finding(findings, "RR_DISCLOSURE_MISSING", "article",
                 f"บท public ต้องระบุว่า {RR_DISCLOSURE}")
    # Windows text writes may normalize the article to CRLF; parity is about
    # content, not line-ending convention.
    article_text = article_text.replace("\r\n", "\n")
    marker = ("**แผนตามสถานการณ์**" if style_id == "l_forex_daily_plan"
              else "**สัญญาแผนเทรดสาธารณะ**")
    marker_count = article_text.count(marker)
    if style_id == "l_forex_daily_plan":
        # L is rendered as a single scenario table; never fall back to a
        # generic block or silently accept duplicate side rows.
        visible_plan_matches = marker_count == 1 and _style_l_parity(article_text, contract)
    else:
        try:
            canonical_block = public_plan_block(contract)
            visible_plan_matches = (marker_count == 1
                                    and article_text.count(canonical_block) == 1
                                    and canonical_block in article_text)
        except (KeyError, TypeError, ValueError):
            visible_plan_matches = False
    if not visible_plan_matches:
        code = ("ARTICLE_PLAN_BLOCK_DUPLICATE" if marker_count != 1
                else "ARTICLE_PLAN_VALUE_MISMATCH")
        _finding(findings, code, "article",
                 "บท public ต้องมี plan block เดียวและค่าทุก field/leg ต้องตรง sidecar")
    elif contract.get("publishable") is True:
        _validate_visible_plan(article_text, contract, style_id, findings)
    evidence_hash = contract.get("evidence_hash")
    if not isinstance(evidence_hash, str) or not _SHA256.fullmatch(evidence_hash):
        _finding(findings, "EVIDENCE_HASH_INVALID", "evidence_hash",
                 "evidence_hash ต้องเป็น SHA-256 lowercase 64 ตัว")
    elif evidence_hash == "0" * 64:
        _finding(findings, "EVIDENCE_HASH_ZERO", "evidence_hash",
                 "evidence_hash ห้ามเป็นค่า placeholder ศูนย์")
    if (expected_evidence_hash is not None
            and evidence_hash != expected_evidence_hash):
        _finding(findings, "EVIDENCE_HASH_MISMATCH", "evidence_hash",
                 "contract ไม่ได้ผูกกับ canonical evidence ของรอบผลิต")

    if contract.get("qa_status") != "PASS_QA":
        _finding(findings, "QA_NOT_PASS", "qa_status",
                 "เฉพาะ PASS_QA เท่านั้นที่เข้า public handoff ได้")
    if contract.get("publishable") is not True:
        _finding(findings, "NOT_PUBLISHABLE", "publishable",
                 "publishable ต้องเป็น true แบบ explicit")
    if contract.get("plan_status") not in PUBLISHABLE_STATUSES:
        _finding(findings, "PLAN_STATUS_NOT_PUBLISHABLE", "plan_status",
                 "public plan ต้องเป็น WAIT_TRIGGER หรือ ACTIVE")
    if not _number(contract.get("current_close")):
        _finding(findings, "CURRENT_CLOSE_INVALID", "current_close",
                 "current_close ต้องเป็นราคาปิด canonical ที่เป็นตัวเลขบวก")
    if contract.get("rr_policy_version") != policy.get("rr_policy_version"):
        _finding(findings, "RR_POLICY_VERSION_MISMATCH", "rr_policy_version",
                 "contract ต้องผูก RR policy version ที่ selector ใช้")
    if any(token.upper() in FORBIDDEN_PUBLIC_STATUSES
           for token in _walk_strings(contract)):
        _finding(findings, "HOLD_STATUS_PRESENT", "$",
                 "DATA_HOLD/BLOCK_QA ห้ามอยู่ใน public contract")

    side = contract.get("side")
    if side not in SIDES:
        _finding(findings, "SIDE_INVALID", "side", "side ต้องเป็น BUY, SELL หรือ OCO")
    plans = contract.get("plans")
    if not isinstance(plans, list) or not plans:
        _finding(findings, "PLANS_MISSING", "plans", "ต้องมี plan leg อย่างน้อยหนึ่งแผน")
        plans = []
    for index, leg in enumerate(plans):
        _validate_leg(
            leg, index, findings,
            minimum_rr=float(policy["minimum_gross_rr"]),
            plan_status=contract.get("plan_status"),
            current_close=contract.get("current_close"),
            rr_tolerance=float(policy["rr_geometry_tolerance"]))
    leg_sides = [leg.get("side") for leg in plans if isinstance(leg, dict)]
    if side == "OCO" and (len(plans) != 2 or sorted(leg_sides) != ["BUY", "SELL"]):
        _finding(findings, "OCO_LEGS_INVALID", "plans",
                 "OCO ต้องมี BUY และ SELL อย่างละหนึ่ง leg")
    elif side in LEG_SIDES and (len(plans) != 1 or leg_sides != [side]):
        _finding(findings, "SINGLE_SIDE_LEG_INVALID", "plans",
                 "BUY/SELL contract ต้องมี leg เดียวและทิศตรงกัน")

    raw_cutoff = contract.get("cutoff_at")
    raw_until = contract.get("valid_until")
    try:
        cutoff_at = datetime.fromisoformat(str(raw_cutoff).replace("Z", "+00:00"))
        valid_until = datetime.fromisoformat(str(raw_until).replace("Z", "+00:00"))
        if (cutoff_at.tzinfo is None or cutoff_at.utcoffset() is None
                or valid_until.tzinfo is None or valid_until.utcoffset() is None):
            raise ValueError("timezone missing")
        if publish_date is not None and valid_until.date() < publish_date:
            _finding(findings, "VALID_UNTIL_BEFORE_PUBLISH_DATE", "valid_until",
                     "valid_until ต้องไม่ก่อนวันเผยแพร่")
        ttl_hours = policy.get("expiry_hours_by_style", {}).get(style_id)
        if ttl_hours is None:
            _finding(findings, "TTL_POLICY_MISSING", "valid_until",
                     "style นี้ไม่มี TTL policy")
        else:
            expected_until = cutoff_at + timedelta(hours=float(ttl_hours))
            if valid_until != expected_until:
                _finding(findings, "TTL_NOT_EXACT", "valid_until",
                         f"valid_until ต้องเท่ากับ cutoff_at + {ttl_hours:g} ชั่วโมง")
    except (TypeError, ValueError):
        _finding(findings, "TTL_DATETIME_INVALID", "cutoff_at/valid_until",
                 "cutoff_at และ valid_until ต้องเป็น ISO 8601 date-time ที่มี timezone")

    return {
        "schema": REPORT_SCHEMA,
        "status": "PASS" if not findings else "FAIL",
        "article_sha256": article_hash,
        "evidence_hash": evidence_hash if isinstance(evidence_hash, str) else None,
        "plan_status": contract.get("plan_status"),
        "side": side,
        "findings": findings,
    }


__all__ = ["RR_DISCLOSURE", "SCHEMA", "REPORT_SCHEMA", "load_policy",
           "public_plan_block", "validate", "sha256_bytes"]
