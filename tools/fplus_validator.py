"""Strict two-file artifact validator for BTCUSD F+."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any, Mapping

from PIL import Image

from tools.fplus_contracts import sha256_canonical


class ArtifactValidationError(ValueError):
    """Raised when a staged artifact set is not safe to promote."""


NO_TRADE_DENY = re.compile(r"\b(?:Entry|SL|TP1?|Stop Loss|Take Profit)\b", re.IGNORECASE)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_artifact_set(
    stage: str | Path, plan: Mapping[str, Any], *, image_max_bytes: int,
) -> dict[str, Any]:
    stage_path = Path(stage)
    if not stage_path.is_dir():
        raise ArtifactValidationError("staging directory does not exist")
    trade_date = str(plan.get("trade_date_bangkok", ""))
    expected_names = ["btcusd.md", f"btcusd-fplus-{trade_date}.webp"]
    actual = [path.name for path in stage_path.iterdir() if path.is_file()]
    if set(actual) != set(expected_names) or len(actual) != 2:
        raise ArtifactValidationError("artifact set must contain exactly two expected files; extra files forbidden")
    markdown_path = stage_path / expected_names[0]
    image_path = stage_path / expected_names[1]
    try:
        markdown = markdown_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ArtifactValidationError("Markdown must be UTF-8") from exc
    if plan.get("selection") == "NO_TRADE":
        if NO_TRADE_DENY.search(markdown):
            raise ArtifactValidationError("NO_TRADE artifact leaks Entry/SL/TP trade levels")
    if not markdown.startswith("---\n") or "asset: btcusd" not in markdown.lower():
        raise ArtifactValidationError("Markdown frontmatter/asset is invalid")
    if plan.get("selection") != "NO_TRADE":
        zone = plan.get("entry_zone") or {}
        required_numbers = [zone.get("low"), zone.get("high"), plan.get("stop_loss"),
                            plan.get("take_profit_1"), plan.get("rr")]
        for value in required_numbers:
            compact = f"{float(value):.8f}".rstrip("0").rstrip(".")
            if compact not in markdown:
                raise ArtifactValidationError(f"Markdown is missing selected-plan number {compact}")
    if image_path.stat().st_size > int(image_max_bytes):
        raise ArtifactValidationError("WebP size exceeds 200 KB/image_max_bytes")
    try:
        with Image.open(image_path) as image:
            if image.format != "WEBP":
                raise ArtifactValidationError("image must be a valid WebP")
            image.verify()
    except ArtifactValidationError:
        raise
    except Exception as exc:
        raise ArtifactValidationError("image is not a valid WebP") from exc
    files = [{"name": name, "sha256": _hash(stage_path / name),
              "bytes": (stage_path / name).stat().st_size} for name in expected_names]
    return {
        "files": files,
        "selected_plan_sha256": sha256_canonical(dict(plan)),
        "artifact_set_sha256": sha256_canonical(files),
    }
