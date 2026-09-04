"""Deterministic P002 quality calculator.

Agent 05 supplies criterion judgments; this module validates and combines them. It
does not inspect prose or invent scores. All decisions remain shadow metadata.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import hashlib
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "quality_scoring.json"
HASH_RE = re.compile(r"^[a-f0-9]{64}$")
SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
VISUAL_WITH_SCORE = {"optional_attached", "required_attached"}


class QualityScoringError(ValueError):
    """Malformed or unsafe evaluation input; fail closed."""


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    for key in ("content_weights", "visual_weights", "overall_weights"):
        total = sum(Decimal(str(value)) for value in config[key].values())
        if total != Decimal("1"):
            raise QualityScoringError(f"{key} weights must sum to 1, got {total}")
    if config["mode"] != "shadow" or config["evaluate_title"] is not False:
        raise QualityScoringError("quality scoring must remain shadow and exclude title")
    return config


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise QualityScoringError(message)


def _validate_hashes(hashes: dict[str, str], expected: dict[str, str] | None) -> None:
    _require(set(hashes) == {"article", "brief", "evidence"},
             "input hashes must contain exactly article, brief, evidence")
    _require(all(HASH_RE.fullmatch(value or "") for value in hashes.values()),
             "input hashes must be lowercase SHA-256")
    if expected is not None:
        _require(hashes == expected, "stale or mismatched input hash")


def _score(judgment: Any, criterion: str) -> Decimal:
    _require(isinstance(judgment, dict) and set(judgment) == {"score", "evidence"},
             f"{criterion}: judgment requires only score and evidence")
    try:
        value = Decimal(str(judgment["score"]))
    except (InvalidOperation, ValueError) as exc:
        raise QualityScoringError(f"{criterion}: score must be a finite number") from exc
    _require(value.is_finite(), f"{criterion}: score must be a finite number")
    _require(Decimal("0") <= value <= Decimal("100"), f"{criterion}: score out of range")
    _require(isinstance(judgment["evidence"], str) and judgment["evidence"].strip(),
             f"{criterion}: evidence is required")
    return value


def _weighted(judgments: dict[str, Any], weights: dict[str, float]) -> Decimal:
    _require(set(judgments) == set(weights), "criterion set does not match rubric")
    return sum((_score(judgments[key], key) * Decimal(str(weight))
                for key, weight in weights.items()), Decimal("0"))


FINDING_FIELDS = {"priority", "criterion", "location", "issue", "evidence",
                  "why_it_matters", "how_to_fix", "owner"}


def _validate_findings(findings: Any, judgments: dict[str, Any], config: dict[str, Any]) -> None:
    _require(isinstance(findings, list), "findings must be an array")
    known = set(config["content_weights"]) | set(config["visual_weights"])
    found_for: set[str] = set()
    for finding in findings:
        _require(isinstance(finding, dict) and set(finding) == FINDING_FIELDS,
                 "finding must contain exactly eight required fields")
        _require(finding["priority"] in {"HIGH", "MEDIUM", "LOW"}, "unknown priority")
        _require(finding["criterion"] in known, "unknown finding criterion")
        _require(finding["owner"] in config["owners"], "unknown finding owner")
        _require(all(isinstance(finding[key], str) and finding[key].strip()
                     for key in FINDING_FIELDS - {"priority", "owner"}),
                 "finding fields must be non-empty")
        found_for.add(finding["criterion"])
    floor = Decimal(str(config["criterion_finding_floor"]))
    missing = [key for key, value in judgments.items()
               if _score(value, key) < floor and key not in found_for]
    _require(not missing, f"criterion below {floor} requires finding: {', '.join(missing)}")


def evaluate(payload: dict[str, Any], *, config: dict[str, Any] | None = None,
             expected_hashes: dict[str, str] | None = None) -> dict[str, Any]:
    """Validate Agent 05 judgments and return a deterministic evaluation envelope."""
    config = config or load_config()
    required = {"job_id", "article_id", "attempt", "producer", "input_hashes",
                "hard_gates", "brief_compliance", "visual_applicability",
                "criterion_judgments", "findings"}
    _require(required <= set(payload), f"missing fields: {sorted(required - set(payload))}")
    _require(payload["producer"] == "agent-05-article-qa", "self-review or unknown producer")
    attempt = payload["attempt"]
    _require(isinstance(attempt, int) and 1 <= attempt <= config["max_revision_attempts"],
             "attempt must be between 1 and max_revision_attempts")
    _validate_hashes(payload["input_hashes"], expected_hashes)
    hard = payload["hard_gates"]
    brief = payload["brief_compliance"]
    _require(set(hard) == {"passed", "failures"} and isinstance(hard["passed"], bool)
             and isinstance(hard["failures"], list), "invalid hard_gates")
    _require(hard["passed"] == (not hard["failures"]), "hard gate result is inconsistent")
    _require(set(brief) == {"passed", "missing"} and isinstance(brief["passed"], bool)
             and isinstance(brief["missing"], list), "invalid brief_compliance")
    _require(brief["passed"] == (not brief["missing"]), "brief result is inconsistent")
    visual = payload["visual_applicability"]
    _require(visual in {"content_only", "optional_attached", "required_attached",
                        "required_missing"}, "unknown visual applicability")

    created_at = (payload["created_at"] if "created_at" in payload
                  else datetime.now(timezone.utc).isoformat(timespec="seconds"))
    _require_aware_iso_datetime(created_at, "evaluation created_at")

    base = {"schema": "quality-evaluation-v1", "job_id": payload["job_id"],
            "article_id": payload["article_id"], "attempt": attempt,
            "producer": payload["producer"], "rubric_version": config["rubric_version"],
            "input_hashes": payload["input_hashes"], "hard_gates": hard,
            "brief_compliance": brief, "visual_applicability": visual,
            "created_at": created_at}
    if not hard["passed"]:
        return {**base, "criterion_judgments": {}, "calculation": None,
                "status": "BLOCK_HARD_GATE", "findings": []}
    if not brief["passed"] or visual == "required_missing":
        return {**base, "criterion_judgments": {}, "calculation": None,
                "status": "BRIEF_INCOMPLETE", "findings": []}

    judgments = payload["criterion_judgments"]
    _require(isinstance(judgments, dict), "criterion_judgments must be an object")
    content_keys = set(config["content_weights"])
    visual_keys = set(config["visual_weights"])
    expected = content_keys | (visual_keys if visual in VISUAL_WITH_SCORE else set())
    _require(set(judgments) == expected, "criterion set conflicts with visual applicability")
    _validate_findings(payload["findings"], judgments, config)
    content = _weighted({key: judgments[key] for key in content_keys}, config["content_weights"])
    visual_score = None
    overall = content
    if visual in VISUAL_WITH_SCORE:
        visual_score = _weighted({key: judgments[key] for key in visual_keys},
                                 config["visual_weights"])
        overall = (content * Decimal(str(config["overall_weights"]["content"]))
                   + visual_score * Decimal(str(config["overall_weights"]["visual"])))
    quantum = Decimal(1).scaleb(-config["rounding_decimals"])
    rounded = lambda value: float(value.quantize(quantum, rounding=ROUND_HALF_UP))  # noqa: E731
    calculation = {"content_score": rounded(content),
                   "visual_score": rounded(visual_score) if visual_score is not None else None,
                   "overall_score": rounded(overall)}
    passed = overall >= Decimal(str(config["minimum_overall_score"]))
    status = "PASS_SCORE" if passed else (
        "ESCALATE_FOR_REVIEW" if attempt == config["max_revision_attempts"]
        else "REVISION_REQUIRED")
    return {**base, "criterion_judgments": judgments, "calculation": calculation,
            "status": status, "findings": payload["findings"]}


def canonical_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_revision_brief(evaluation: dict[str, Any], *, article_hash: str) -> dict[str, Any]:
    _require(evaluation["status"] in {"REVISION_REQUIRED", "ESCALATE_FOR_REVIEW"},
             "revision brief requires a revision/escalation evaluation")
    _require(evaluation["input_hashes"]["article"] == article_hash,
             "stale article hash for revision brief")
    _require(bool(evaluation["findings"]), "revision brief requires findings")
    return {"schema": "revision-brief-v1", "job_id": evaluation["job_id"],
            "article_id": evaluation["article_id"], "attempt": evaluation["attempt"],
            "evaluation_hash": canonical_hash(evaluation), "article_hash": article_hash,
            "status": evaluation["status"], "issues": evaluation["findings"]}


def _require_aware_iso_datetime(value: Any, label: str) -> None:
    _require(isinstance(value, str) and value.strip(), f"{label} is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise QualityScoringError(f"{label} is not an ISO 8601 date-time") from exc
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
             f"{label} must include a timezone")


def append_history(history: dict[str, Any] | None, evaluation: dict[str, Any]) -> dict[str, Any]:
    """Return new history; never mutate/re-number/reuse an article hash."""
    _require_aware_iso_datetime(evaluation.get("created_at"),
                                "evaluation created_at")
    if history is not None:
        _require(isinstance(history, dict)
                 and set(history) == {"schema", "job_id", "article_id", "attempts"},
                 "prior history is not canonical")
        _require(history["schema"] == "quality-attempt-history-v1",
                 "prior history schema is invalid")
        _require(history["job_id"] == evaluation["job_id"]
                 and history["article_id"] == evaluation["article_id"],
                 "history identity does not match evaluation")
        _require(isinstance(history["attempts"], list), "history attempts must be an array")
        expected_attempt_fields = {"attempt", "article_hash", "evaluation_hash",
                                   "status", "created_at"}
        prior_article_hashes: set[str] = set()
        for index, item in enumerate(history["attempts"], 1):
            _require(isinstance(item, dict) and set(item) == expected_attempt_fields,
                     "prior history attempt is not canonical")
            _require(item["attempt"] == index, "prior history attempts must be contiguous")
            _require(bool(HASH_RE.fullmatch(item["article_hash"] or ""))
                     and bool(HASH_RE.fullmatch(item["evaluation_hash"] or "")),
                     "prior history contains invalid hash")
            _require(item["status"] in {"BLOCK_HARD_GATE", "BRIEF_INCOMPLETE",
                                        "REVISION_REQUIRED", "PASS_SCORE",
                                        "ESCALATE_FOR_REVIEW"},
                     "prior history contains invalid status")
            _require_aware_iso_datetime(item["created_at"],
                                        "prior history created_at")
            _require(item["article_hash"] not in prior_article_hashes,
                     "prior history reuses an article hash")
            prior_article_hashes.add(item["article_hash"])
    attempts = list((history or {}).get("attempts", []))
    expected = len(attempts) + 1
    _require(evaluation["attempt"] == expected, "attempt history must be contiguous")
    article_hash = evaluation["input_hashes"]["article"]
    _require(all(item["article_hash"] != article_hash for item in attempts),
             "a revision attempt must bind a new article hash")
    _require(expected <= load_config()["max_revision_attempts"], "attempt exceeds maximum")
    attempts.append({"attempt": expected, "article_hash": article_hash,
                     "evaluation_hash": canonical_hash(evaluation),
                     "status": evaluation["status"], "created_at": evaluation["created_at"]})
    return {"schema": "quality-attempt-history-v1", "job_id": evaluation["job_id"],
            "article_id": evaluation["article_id"], "attempts": attempts}


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _safe_segment(value: Any, label: str) -> str:
    _require(isinstance(value, str) and value not in {".", ".."}
             and bool(SAFE_SEGMENT_RE.fullmatch(value)),
             f"unsafe {label}: must be one portable path segment")
    return value


def _contained_artifact_path(output_root: Path, job_id: Any, article_id: Any,
                             attempt: Any) -> Path:
    job = _safe_segment(job_id, "job_id")
    article = _safe_segment(article_id, "article_id")
    _require(isinstance(attempt, int) and 1 <= attempt <= 3, "unsafe attempt")
    root = output_root.resolve()
    target = (root / job / article / f"attempt-{attempt:02d}" / "evaluation.json").resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise QualityScoringError("artifact path escapes output root") from exc
    return target


def evaluate_batch(inputs: list[Path], output_root: Path,
                   *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate independently; one malformed job cannot discard another result."""
    config = config or load_config()
    seen: set[tuple[str, str, int]] = set()
    results: list[dict[str, Any]] = []
    for source in inputs:
        try:
            def reject_non_finite(value: str) -> None:
                raise QualityScoringError(f"non-finite JSON number is forbidden: {value}")

            payload = json.loads(source.read_text(encoding="utf-8"),
                                 parse_constant=reject_non_finite)
            identity = (payload["job_id"], payload["article_id"], payload["attempt"])
            _require(identity not in seen, "duplicate job/article/attempt")
            seen.add(identity)
            result = evaluate(payload, config=config)
            target = _contained_artifact_path(output_root, payload["job_id"],
                                              payload["article_id"], payload["attempt"])
            _atomic_json(target, result)
            results.append({"source": str(source), "status": "ok", "output": str(target)})
        except (KeyError, OSError, json.JSONDecodeError, QualityScoringError) as exc:
            results.append({"source": str(source), "status": "error", "error": str(exc)})
    return {"total": len(inputs), "succeeded": sum(r["status"] == "ok" for r in results),
            "failed": sum(r["status"] == "error" for r in results), "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P002 deterministic shadow scoring")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    summary = evaluate_batch(args.inputs, args.output_root)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
