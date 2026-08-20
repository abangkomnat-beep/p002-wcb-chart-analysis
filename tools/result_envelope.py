"""Side-effect-free result contract used by the shadow control plane."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

STATUSES = {"PASS", "SKIP", "FAIL"}
_SECRET = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*[^,\s]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_message(value: str) -> str:
    return _SECRET.sub(r"\1=<redacted>", str(value))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    message: str
    style_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", _safe_message(self.message))


@dataclass(frozen=True)
class ArtifactRef:
    path_relative: str
    media_type: str = "application/octet-stream"
    bytes: int | None = None
    sha256: str | None = None
    pixel_sha256: str | None = None


@dataclass(frozen=True)
class EvidenceRef:
    path_relative_or_reference: str
    kind: str
    sha256: str | None = None


@dataclass(frozen=True)
class SourceManifestItem:
    provider: str
    timeframe: str
    request_role: str
    ordinal: int


@dataclass
class ResultEnvelope:
    run_id: str
    asset: str
    execution_unit: str
    style_ids: list[str]
    status: str
    reason_code: str
    findings: list[Finding] = field(default_factory=list)
    exception_type: str | None = None
    artifacts: list[ArtifactRef] = field(default_factory=list)
    evidence: list[EvidenceRef] = field(default_factory=list)
    source_manifest: list[SourceManifestItem] = field(default_factory=list)
    legacy_result: Mapping[str, Any] | None = None
    started_at: str = field(default_factory=_now)
    completed_at: str = field(default_factory=_now)
    duration_ms: int = 0
    children: list["ResultEnvelope"] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"invalid result status: {self.status}")
        if self.exception_type:
            self.exception_type = self.exception_type.split(".")[-1]

    @classmethod
    def pass_(cls, run_id: str, asset: str, execution_unit: str,
              style_ids: Sequence[str], **kwargs: Any) -> "ResultEnvelope":
        return cls(run_id, asset, execution_unit, list(style_ids), "PASS", "OK", **kwargs)

    @classmethod
    def skip(cls, run_id: str, asset: str, execution_unit: str,
             style_ids: Sequence[str], reason_code: str = "SKIPPED_POLICY",
             **kwargs: Any) -> "ResultEnvelope":
        return cls(run_id, asset, execution_unit, list(style_ids), "SKIP", reason_code, **kwargs)

    @classmethod
    def fail(cls, run_id: str, asset: str, execution_unit: str,
             style_ids: Sequence[str], reason_code: str = "LEGACY_FAILURE",
             exception: BaseException | None = None, **kwargs: Any) -> "ResultEnvelope":
        return cls(
            run_id, asset, execution_unit, list(style_ids), "FAIL", reason_code,
            exception_type=type(exception).__name__ if exception else None,
            **kwargs,
        )

    @classmethod
    def from_legacy(cls, result: Any, *, run_id: str, asset: str,
                    execution_unit: str, style_ids: Sequence[str]) -> "ResultEnvelope":
        """Normalize a legacy result without changing its return object."""
        if isinstance(result, ResultEnvelope):
            return result
        if isinstance(result, Mapping):
            raw_status = str(result.get("status", "PASS")).upper()
            status = raw_status if raw_status in STATUSES else "FAIL"
            reason = str(result.get("reason_code", "OK" if status == "PASS" else "LEGACY_FAILURE"))
        elif result is False or result is None:
            status, reason = "FAIL", "LEGACY_FALSE_RESULT"
        else:
            status, reason = "PASS", "OK"
        envelope = cls(run_id, asset, execution_unit, list(style_ids), status, reason,
                       legacy_result=result if isinstance(result, Mapping) else {"value": repr(result)})
        if isinstance(result, Mapping):
            children = result.get("children", ())
            if isinstance(children, Sequence) and not isinstance(children, (str, bytes)):
                for child in children:
                    if isinstance(child, ResultEnvelope):
                        envelope.children.append(child)
                    elif isinstance(child, Mapping):
                        child_style = child.get("style_id", child.get("style", ""))
                        child_env = cls.from_legacy(
                            child, run_id=run_id, asset=asset,
                            execution_unit=execution_unit,
                            style_ids=[str(child_style)] if child_style else list(style_ids),
                        )
                        envelope.children.append(child_env)
        return envelope

    def add_child(self, child: "ResultEnvelope") -> None:
        self.children.append(child)

    @property
    def aggregate_status(self) -> str:
        statuses = [self.status, *(child.aggregate_status for child in self.children)]
        if "FAIL" in statuses:
            return "FAIL"
        if "PASS" in statuses:
            return "PASS"
        return "SKIP"

    @property
    def exit_code(self) -> int:
        return 0 if self.aggregate_status != "FAIL" else 1

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status
        value["aggregate_status"] = self.aggregate_status
        value["exit_code"] = self.exit_code
        value["schema_version"] = "result-envelope-v1"
        return value


__all__ = ["ArtifactRef", "EvidenceRef", "Finding", "ResultEnvelope", "SourceManifestItem", "sha256_file"]
