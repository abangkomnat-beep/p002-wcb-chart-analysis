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
import shutil
import uuid
from pathlib import Path

from tools.localization_dependencies import delivery_root


class TransactionError(RuntimeError):
    pass


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
    if not isinstance(marker, dict):
        raise TransactionError("marker must be an object")
    tx.mkdir(parents=True)
    intent = {"schema": "p002-localization-transaction/v1", "transaction_id": transaction_id,
              "source_business_date": source_business_date, "countries": countries,
              "marker": marker, "state": "PREPARED", "steps": []}
    _write(tx / "journal.json", _bytes(intent))
    return tx


def apply_transaction(project_root: Path, source_business_date: str, transaction_id: str) -> dict:
    project_root = Path(project_root).resolve()
    tx = project_root / "work" / "localization" / _work_day(source_business_date) / "transactions" / transaction_id
    journal_path = tx / "journal.json"
    journal = _journal(journal_path)
    if journal.get("state") != "PREPARED":
        raise TransactionError("transaction is not prepared")
    root = delivery_root(project_root, source_business_date)
    root.mkdir(parents=True, exist_ok=True)
    with _day_lock(root / ".delivery.lock"):
        before_marker = root / "manifest.json"
        marker_before = before_marker.read_bytes() if before_marker.exists() else None
        _write(tx / "before" / "marker.json", marker_before or b"")
        steps = []
        try:
            for code, folder in journal["countries"].items():
                prepared = _inside(tx / "prepared", tx / "prepared" / folder)
                target = _inside(root, root / folder)
                expected = _tree(prepared)
                displaced = tx / "displaced" / folder
                if target.exists():
                    if displaced.exists():
                        raise TransactionError("displaced target already exists")
                    displaced.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(target, displaced)
                    steps.append({"country_code": code, "folder": folder, "state": "OLD_DISPLACED"})
                    journal["steps"] = steps
                    _write(journal_path, _bytes({**journal, "state": "APPLYING"}))
                os.replace(prepared, target)
                if _tree(target) != expected:
                    raise TransactionError(f"installed country differs from prepared inventory: {code}")
                steps.append({"country_code": code, "folder": folder, "state": "NEW_INSTALLED"})
                journal["steps"] = steps
                _write(journal_path, _bytes({**journal, "state": "APPLYING"}))
            marker_data = _bytes(journal["marker"])
            temp = root / f".manifest-{uuid.uuid4().hex}.tmp"
            _write(temp, marker_data)
            os.replace(temp, root / "manifest.json")
            journal.update(state="COMMITTED", steps=steps, marker_sha256=_sha(marker_data))
            _write(journal_path, _bytes(journal))
            return {"status": "COMMITTED", "delivery_root": str(root), "transaction_id": transaction_id}
        except Exception:
            # Recover under the same lock and then surface the original failure.
            _rollback_locked(root, tx, journal, marker_before)
            raise


def _rollback_locked(root: Path, tx: Path, journal: dict, marker_before: bytes | None) -> None:
    for _, folder in reversed(list(journal.get("countries", {}).items())):
        target, displaced = root / folder, tx / "displaced" / folder
        if target.exists() and target.is_dir():
            failed = tx / "failed" / folder
            failed.parent.mkdir(parents=True, exist_ok=True)
            if failed.exists():
                raise TransactionError("cannot safely preserve failed replacement")
            os.replace(target, failed)
        if displaced.exists():
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
        marker_before = (tx / "before" / "marker.json").read_bytes() if (tx / "before" / "marker.json").exists() else None
        _rollback_locked(root, tx, journal, marker_before)
        return {"status": "ROLLED_BACK", "transaction_id": transaction_id}
