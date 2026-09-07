"""Recoverable replacement of prepared country trees in the delivery day root.

The public day marker is written last.  Country trees are only exchanged after
their complete prepared inventories have been checked, and the previous trees
remain in the transaction journal area for recovery/audit.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import uuid
from pathlib import Path

from tools.localization_dependencies import delivery_root


class TransactionError(RuntimeError):
    pass


_HEX = re.compile(r"[0-9a-f]{64}")
_FOLDER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")


def validate_delivery_marker(marker: dict, source_business_date: str, *, complete: bool) -> None:
    """Validate a day marker before it is trusted or made visible.

    A prepared intent may use path-only entries until package manifests exist.
    Any marker used by a reader or installer must bind every country manifest.
    """
    if (not isinstance(marker, dict) or marker.get("schema") != "p002-localized-day/v2"
            or marker.get("source_business_date") != source_business_date):
        raise TransactionError("marker must be a localized day marker for this date")
    countries = marker.get("countries")
    if not isinstance(countries, dict) or not countries:
        raise TransactionError("marker must list countries")
    folders = set()
    for code, entry in countries.items():
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{2}", code) or not isinstance(entry, dict):
            raise TransactionError("delivery marker country entry is invalid")
        folder = entry.get("path")
        if not isinstance(folder, str) or not _FOLDER.fullmatch(folder) or folder in folders:
            raise TransactionError("delivery marker country path is invalid")
        folders.add(folder)
        if complete and (not isinstance(entry.get("release_id"), str) or not entry["release_id"]
                         or not isinstance(entry.get("manifest_sha256"), str)
                         or not _HEX.fullmatch(entry["manifest_sha256"])):
            raise TransactionError("delivery marker lacks release binding")


def _work_day(source_business_date: str) -> str:
    try:
        year, month, day = source_business_date.split("-")
        if len(year) != 4 or len(month) != 2 or len(day) != 2:
            raise ValueError
    except ValueError as exc:
        raise TransactionError("source_business_date must be YYYY-MM-DD") from exc
    return f"{day}-{month}-{year}"


def _bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _tree(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        raise TransactionError(f"missing directory: {root}")
    result = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise TransactionError(f"links are forbidden in transaction: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def _inside(root: Path, path: Path) -> Path:
    root, path = root.resolve(), path.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise TransactionError(f"path outside permitted transaction root: {path}") from exc
    return path


@contextlib.contextmanager
def _day_lock(path: Path):
    """An OS-backed lock; permanent lock file is harmless after a crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            if handle.read(1) == b"":
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    except OSError as exc:
        raise TransactionError(f"delivery day is busy: {exc}") from exc
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _journal(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TransactionError(f"cannot read transaction journal: {exc}") from exc


def _validate_prepared(project_root: Path, folder: str, country_code: str,
                       source_business_date: str, root: Path) -> dict[str, bytes]:
    """Reject arbitrary trees before any public mutation.

    Packaging writes this release manifest only after all country gates pass.
    The transaction repeats the structural and byte checks so a caller cannot
    bypass QC by putting a hand-made tree in ``prepared``.
    """
    tree = _tree(root)
    manifest_bytes = tree.get("manifest.json")
    if manifest_bytes is None:
        raise TransactionError(f"prepared {country_code} has no release manifest")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TransactionError(f"prepared {country_code} manifest is invalid") from exc
    if (manifest.get("schema") != "p002-localized-release/v2"
            or manifest.get("country_code") != country_code
            or manifest.get("source_business_date") != source_business_date):
        raise TransactionError(f"prepared {country_code} identity is not release-ready")
    required = ("generation_id", "source_manifest_sha256", "receipt_index_sha256",
                "pack_sha256", "country_policy_sha256")
    if any(not isinstance(manifest.get(key), str) or not manifest[key] for key in required):
        raise TransactionError(f"prepared {country_code} lacks QC attestation fields")
    if any(not _HEX.fullmatch(manifest[key]) for key in required[1:]):
        raise TransactionError(f"prepared {country_code} has invalid QC attestation hashes")
    expected = manifest.get("files")
    if not isinstance(expected, dict) or not expected:
        raise TransactionError(f"prepared {country_code} lacks file inventory")
    for relative, digest in expected.items():
        if (not isinstance(relative, str) or not isinstance(digest, str)
                or not _HEX.fullmatch(digest)):
            raise TransactionError(f"prepared {country_code} inventory is invalid")
        actual = tree.get(relative)
        if actual is None or _sha(actual) != digest:
            raise TransactionError(f"prepared {country_code} file inventory mismatch: {relative}")
    allowed = {"manifest.json", "README.md", *expected}
    if set(tree) != allowed:
        raise TransactionError(f"prepared {country_code} has unlisted or missing files")
    return tree


def prepare_transaction(project_root: Path, source_business_date: str, transaction_id: str,
                        countries: dict[str, str], marker: dict) -> Path:
    """Create an empty, durable transaction intent under work.

    Callers place complete country trees in ``prepared/<output_folder>`` before
    calling ``apply_transaction``.  Existing journal IDs are never reused.
    """
    if not transaction_id or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in transaction_id):
        raise TransactionError("transaction_id must be lowercase letters, digits or hyphens")
    project_root = Path(project_root).resolve()
    tx = project_root / "work" / "localization" / _work_day(source_business_date) / "transactions" / transaction_id
    if tx.exists():
        raise TransactionError("transaction id already exists")
    if not countries or len(set(countries.values())) != len(countries):
        raise TransactionError("countries require unique output folders")
    validate_delivery_marker(marker, source_business_date, complete=False)
    for code, folder in countries.items():
        entry = marker["countries"].get(code)
        if not isinstance(entry, dict) or entry.get("path") != folder:
            raise TransactionError(f"marker does not attest prepared country {code}")
    tx.mkdir(parents=True)
    intent = {"schema": "p002-localization-transaction/v1", "transaction_id": transaction_id,
              "source_business_date": source_business_date, "countries": countries,
              "marker": marker, "state": "PREPARED", "steps": []}
    _write(tx / "journal.json", _bytes(intent))
    return tx


def attest_transaction_marker(project_root: Path, source_business_date: str,
                              transaction_id: str, marker: dict) -> None:
    """Bind a prepared transaction to package manifests before apply."""
    project_root = Path(project_root).resolve()
    journal_path = (project_root / "work" / "localization" / _work_day(source_business_date)
                    / "transactions" / transaction_id / "journal.json")
    journal = _journal(journal_path)
    if journal.get("state") != "PREPARED":
        raise TransactionError("transaction is not prepared")
    validate_delivery_marker(marker, source_business_date, complete=True)
    for code, folder in journal.get("countries", {}).items():
        entry = marker["countries"].get(code)
        if not isinstance(entry, dict) or entry.get("path") != folder:
            raise TransactionError(f"marker does not attest prepared country {code}")
    journal["marker"] = marker
    _write(journal_path, _bytes(journal))


def apply_transaction(project_root: Path, source_business_date: str, transaction_id: str) -> dict:
    project_root = Path(project_root).resolve()
    tx = project_root / "work" / "localization" / _work_day(source_business_date) / "transactions" / transaction_id
    journal_path = tx / "journal.json"
    journal = _journal(journal_path)
    if journal.get("state") != "PREPARED":
        raise TransactionError("transaction is not prepared")
    validate_delivery_marker(journal.get("marker"), source_business_date, complete=True)
    root = delivery_root(project_root, source_business_date)
    root.mkdir(parents=True, exist_ok=True)
    with _day_lock(root / ".delivery.lock"):
        before_marker = root / "manifest.json"
        marker_before = before_marker.read_bytes() if before_marker.exists() else None
        _write(tx / "before" / "marker.json", marker_before or b"")
        journal.update(state="APPLYING", steps=[], marker_before_exists=marker_before is not None)
        _write(journal_path, _bytes(journal))
        try:
            for code, folder in journal["countries"].items():
                prepared = _inside(tx / "prepared", tx / "prepared" / folder)
                target = _inside(root, root / folder)
                expected = _validate_prepared(project_root, folder, code, source_business_date, prepared)
                displaced = tx / "displaced" / folder
                if target.exists():
                    if displaced.exists():
                        raise TransactionError("displaced target already exists")
                    journal["steps"].append({"country_code": code, "folder": folder,
                                             "state": "OLD_DISPLACING"})
                    _write(journal_path, _bytes(journal))
                    displaced.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(target, displaced)
                    journal["steps"][-1]["state"] = "OLD_DISPLACED"
                    _write(journal_path, _bytes(journal))
                journal["steps"].append({"country_code": code, "folder": folder,
                                         "state": "NEW_INSTALLING"})
                _write(journal_path, _bytes(journal))
                os.replace(prepared, target)
                if _tree(target) != expected:
                    raise TransactionError(f"installed country differs from prepared inventory: {code}")
                journal["steps"][-1]["state"] = "NEW_INSTALLED"
                _write(journal_path, _bytes(journal))
            marker_data = _bytes(journal["marker"])
            temp = root / f".manifest-{uuid.uuid4().hex}.tmp"
            _write(temp, marker_data)
            os.replace(temp, root / "manifest.json")
            journal.update(state="COMMITTED", marker_sha256=_sha(marker_data))
            _write(journal_path, _bytes(journal))
            return {"status": "COMMITTED", "delivery_root": str(root), "transaction_id": transaction_id}
        except Exception:
            # Recover under the same lock and then surface the original failure.
            _rollback_locked(root, tx, journal, marker_before)
            raise


def _rollback_locked(root: Path, tx: Path, journal: dict, marker_before: bytes | None) -> None:
    for step in reversed(journal.get("steps", [])):
        folder = step["folder"]
        target, displaced = root / folder, tx / "displaced" / folder
        if step["state"] in {"NEW_INSTALLING", "NEW_INSTALLED"} and target.exists() and target.is_dir():
            failed = tx / "failed" / folder
            failed.parent.mkdir(parents=True, exist_ok=True)
            if failed.exists():
                raise TransactionError("cannot safely preserve failed replacement")
            os.replace(target, failed)
        if step["state"] in {"OLD_DISPLACING", "OLD_DISPLACED"} and displaced.exists():
            os.replace(displaced, target)
    marker = root / "manifest.json"
    if marker_before is None:
        if marker.exists():
            marker.unlink()
    else:
        _write(marker, marker_before)
    journal["state"] = "ROLLED_BACK"
    _write(tx / "journal.json", _bytes(journal))


def recover_transaction(project_root: Path, source_business_date: str, transaction_id: str) -> dict:
    """Conservative recovery: only a fully committed transaction is accepted."""
    project_root = Path(project_root).resolve()
    tx = project_root / "work" / "localization" / _work_day(source_business_date) / "transactions" / transaction_id
    journal = _journal(tx / "journal.json")
    root = delivery_root(project_root, source_business_date)
    with _day_lock(root / ".delivery.lock"):
        if journal.get("state") == "COMMITTED":
            marker = root / "manifest.json"
            if not marker.is_file() or _sha(marker.read_bytes()) != journal.get("marker_sha256"):
                raise TransactionError("committed journal and marker disagree; manual recovery required")
            return {"status": "COMMITTED", "transaction_id": transaction_id}
        if journal.get("state") == "PREPARED":
            return {"status": "PREPARED", "transaction_id": transaction_id}
        if journal.get("state") == "ROLLED_BACK":
            return {"status": "ROLLED_BACK", "transaction_id": transaction_id}
        if journal.get("state") != "APPLYING":
            raise TransactionError("unknown transaction state; manual recovery required")
        marker_before = ((tx / "before" / "marker.json").read_bytes()
                         if journal.get("marker_before_exists") else None)
        _rollback_locked(root, tx, journal, marker_before)
        return {"status": "ROLLED_BACK", "transaction_id": transaction_id}


def read_delivery(project_root: Path, source_business_date: str) -> dict[str, dict[str, bytes]]:
    """Return a consistent in-memory delivery snapshot while holding the writer lock."""
    project_root = Path(project_root).resolve()
    root = delivery_root(project_root, source_business_date)
    with _day_lock(root / ".delivery.lock"):
        marker_path = root / "manifest.json"
        if not marker_path.is_file():
            raise TransactionError("no committed delivery marker")
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise TransactionError("delivery marker is invalid") from exc
        validate_delivery_marker(marker, source_business_date, complete=True)
        snapshot = {}
        for code, entry in (marker.get("countries") or {}).items():
            folder = entry.get("path") if isinstance(entry, dict) else None
            tree = _tree(_inside(root, root / folder))
            manifest = json.loads(tree.get("manifest.json", b"").decode("utf-8"))
            if manifest.get("country_code") != code:
                raise TransactionError("delivery country identity mismatch")
            if _sha(tree["manifest.json"]) != entry["manifest_sha256"]:
                raise TransactionError("delivery country manifest hash mismatch")
            snapshot[code] = tree
        return snapshot
