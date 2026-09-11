"""Durable storage for prepared P002 translation jobs.

This store only writes to the project work area.  A prepared job is evidence
for a writer; it is never an accepted translation or a release transaction.
"""
from __future__ import annotations

import json
import hashlib
import os
import re
import tempfile
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping

DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
NAME_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]*$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class TranslationJobStoreError(ValueError):
    pass


@contextmanager
def _exclusive_lock(directory: Path, name: str):
    lock = directory / f".{name}.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise TranslationJobStoreError(f"job write is already in progress: {name}") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.close(descriptor)
        yield
    finally:
        lock.unlink(missing_ok=True)


def _validate_name(label: str, value: str) -> None:
    if not NAME_RE.fullmatch(value):
        raise TranslationJobStoreError(f"invalid {label}: {value!r}")


def _base_path(work_root: Path, business_date: str, country_code: str, lane: str) -> Path:
    if not DATE_RE.fullmatch(business_date):
        raise TranslationJobStoreError("business date must be DD-MM-YYYY")
    try:
        if datetime.strptime(business_date, "%d-%m-%Y").strftime("%d-%m-%Y") != business_date:
            raise ValueError
    except ValueError as exc:
        raise TranslationJobStoreError("business date must be DD-MM-YYYY") from exc
    _validate_name("country", country_code)
    _validate_name("lane", lane)
    root = Path(work_root).resolve()
    base = (root / "localization" / business_date / "translation-jobs" / country_code / lane).resolve()
    if root not in base.parents:
        raise TranslationJobStoreError("job path escapes work root")
    return base


def write_prepared_job(
    work_root: Path,
    business_date: str,
    country_code: str,
    lane: str,
    job: Mapping[str, Any],
) -> Path:
    """Write an immutable revision, reusing one only for the same source hash."""
    source_hash = str((job.get("source") or {}).get("sha256") or "")
    cache_key = str(job.get("cache_key") or "")
    cache_identity = job.get("cache_identity")
    if not HASH_RE.fullmatch(source_hash):
        raise TranslationJobStoreError("prepared job must include a SHA256 source hash")
    if not HASH_RE.fullmatch(cache_key):
        raise TranslationJobStoreError("prepared job must include a cache key")
    if not isinstance(cache_identity, Mapping):
        raise TranslationJobStoreError("prepared job must include cache identity")
    computed_cache_key = hashlib.sha256(
        json.dumps(dict(cache_identity), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    expected_cache_key = hashlib.sha256(
        json.dumps(dict(cache_identity), sort_keys=True).encode("utf-8")
    ).hexdigest()
    if cache_key not in {computed_cache_key, expected_cache_key}:
        raise TranslationJobStoreError("prepared job cache key does not match cache identity")
    base = _base_path(work_root, business_date, country_code, lane)
    base.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(base.parent, base.name):
        existing = sorted(base.parent.glob(base.name + "-r*.json"))
        for path in existing:
            try:
                prior = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise TranslationJobStoreError(f"cannot read existing job: {path}") from exc
            if prior.get("cache_key") == cache_key:
                return path
        revisions = [int(match.group(1)) for path in existing
                     if (match := re.fullmatch(re.escape(base.name) + r"-r(\d{4})\.json", path.name))]
        revision = max(revisions, default=0) + 1
        destination = base.parent / f"{base.name}-r{revision:04d}.json"
        payload = json.dumps(dict(job), ensure_ascii=False, indent=2) + "\n"
        descriptor, temporary = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=base.parent, text=True)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise
        return destination
