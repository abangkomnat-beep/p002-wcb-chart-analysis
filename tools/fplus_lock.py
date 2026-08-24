"""Atomic local daily-lock store for one BTCUSD F+ job per Bangkok date."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any, Iterator, Mapping


class LockContractError(RuntimeError):
    """Raised for invalid ownership or force-lock operations."""


_THREAD_GUARDS: dict[str, threading.RLock] = {}
_THREAD_GUARDS_LOCK = threading.Lock()


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise LockContractError("lock time must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise LockContractError("lock time must include timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class LocalLockStore:
    """JSON-backed CAS semantics suitable for a single persistent filesystem."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        guard_key = str(self.root.resolve()).lower()
        with _THREAD_GUARDS_LOCK:
            self._thread_guard = _THREAD_GUARDS.setdefault(guard_key, threading.RLock())

    def _path(self, key: str) -> Path:
        if not key.startswith("fplus:btcusd:"):
            raise LockContractError("invalid BTCUSD F+ production lock key")
        trade_date = key.rsplit(":", 1)[-1]
        try:
            datetime.strptime(trade_date, "%Y-%m-%d")
        except ValueError as exc:
            raise LockContractError("lock key must end in YYYY-MM-DD") from exc
        return self.root / f"{trade_date}.json"

    @contextmanager
    def _exclusive(self, path: Path) -> Iterator[None]:
        guard = path.with_suffix(path.suffix + ".guard")
        with self._thread_guard:
            guard.parent.mkdir(parents=True, exist_ok=True)
            handle = guard.open("a+b")
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    if handle.read(1) == b"":
                        handle.write(b"0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LockContractError(f"lock record is unreadable: {path}") from exc

    @staticmethod
    def _write(path: Path, record: Mapping[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp")
        temporary.write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def acquire(
        self, *, key: str, run_id: str, now_utc: str, lease_seconds: int,
        cutoff_at_utc: str, config_fingerprint: str, force: bool,
        force_reason: str | None,
    ) -> dict[str, Any]:
        if force and (not isinstance(force_reason, str) or not force_reason.strip()):
            raise LockContractError("force requires a non-blank audit reason")
        if int(lease_seconds) <= 0:
            raise LockContractError("lease_seconds must be positive")
        now = _utc(now_utc)
        _utc(cutoff_at_utc)
        path = self._path(key)
        with self._exclusive(path):
            current = self._read(path)
            if current and current.get("status") == "committed":
                if not force:
                    result = dict(current)
                    result["status"] = "already_done"
                    return result
                generation = int(current.get("generation", 1)) + 1
                supersedes = current.get("run_id")
                history = list(current.get("history", []))
                history.append({key_: current.get(key_) for key_ in (
                    "run_id", "generation", "status", "artifact_hashes", "committed_at"
                )})
            elif current and current.get("status") == "claimed":
                lease_expires = _utc(current["lease_expires_at"])
                if lease_expires > now:
                    result = dict(current)
                    result["status"] = "in_progress"
                    return result
                generation = int(current.get("generation", 1))
                supersedes = current.get("run_id")
                history = list(current.get("history", []))
            elif current:
                generation = int(current.get("generation", 1))
                supersedes = current.get("run_id")
                history = list(current.get("history", []))
            else:
                generation = 1
                supersedes = None
                history = []
            record = {
                "key": key,
                "run_id": run_id,
                "generation": generation,
                "status": "claimed",
                "claimed_at": _iso(now),
                "heartbeat_at": _iso(now),
                "lease_expires_at": _iso(now + timedelta(seconds=int(lease_seconds))),
                "cutoff_at_utc": cutoff_at_utc,
                "config_fingerprint": config_fingerprint,
                "supersedes_run_id": supersedes,
                "force_reason": force_reason.strip() if force_reason else None,
                "history": history,
            }
            self._write(path, record)
            return dict(record)

    def commit(
        self, *, key: str, run_id: str, now_utc: str,
        artifact_hashes: Mapping[str, str],
    ) -> dict[str, Any]:
        now = _utc(now_utc)
        path = self._path(key)
        with self._exclusive(path):
            record = self._read(path)
            if not record or record.get("run_id") != run_id or record.get("status") != "claimed":
                raise LockContractError("only the active lease owner may commit")
            record["status"] = "committed"
            record["committed_at"] = _iso(now)
            record["heartbeat_at"] = _iso(now)
            record["artifact_hashes"] = dict(artifact_hashes)
            self._write(path, record)
            return dict(record)

    def mark_retryable(
        self, *, key: str, run_id: str, status: str,
        reason_codes: list[str], now_utc: str,
    ) -> dict[str, Any]:
        if status not in {"blocked_retryable", "failed_retryable"}:
            raise LockContractError("retryable status is invalid")
        now = _utc(now_utc)
        path = self._path(key)
        with self._exclusive(path):
            record = self._read(path)
            if not record or record.get("run_id") != run_id:
                raise LockContractError("only the lease owner may mark retryable")
            record["status"] = status
            record["updated_at"] = _iso(now)
            record["reason_codes"] = list(reason_codes)
            self._write(path, record)
            return dict(record)

    def heartbeat(
        self, *, key: str, run_id: str, now_utc: str, lease_seconds: int,
    ) -> dict[str, Any]:
        """Extend an active lease; only its current owner can do so."""
        if int(lease_seconds) <= 0:
            raise LockContractError("lease_seconds must be positive")
        now = _utc(now_utc)
        path = self._path(key)
        with self._exclusive(path):
            record = self._read(path)
            if not record or record.get("run_id") != run_id or record.get("status") != "claimed":
                raise LockContractError("only the active lease owner may heartbeat")
            if _utc(record["lease_expires_at"]) <= now:
                raise LockContractError("cannot heartbeat an expired lease")
            record["heartbeat_at"] = _iso(now)
            record["lease_expires_at"] = _iso(now + timedelta(seconds=int(lease_seconds)))
            self._write(path, record)
            return dict(record)

    def get(self, *, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        with self._exclusive(path):
            record = self._read(path)
            return dict(record) if record else None

    def reconcile_committed(
        self, *, key: str, run_id: str, generation: int, now_utc: str,
        artifact_hashes: Mapping[str, str], artifact_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        """Complete the lock CAS after a verified directory became visible."""
        now = _utc(now_utc)
        path = self._path(key)
        with self._exclusive(path):
            record = self._read(path)
            if not record:
                raise LockContractError("cannot reconcile without a lock record")
            if record.get("status") == "committed":
                return dict(record)
            if record.get("run_id") != run_id or int(record.get("generation", 0)) != int(generation):
                raise LockContractError("artifact journal does not own the current lock generation")
            if record.get("status") not in {"claimed", "failed_retryable"}:
                raise LockContractError("lock state cannot be reconciled as committed")
            record["status"] = "committed"
            record["committed_at"] = _iso(now)
            record["heartbeat_at"] = _iso(now)
            record["artifact_hashes"] = dict(artifact_hashes)
            record["paths"] = list(artifact_paths or [])
            record["reconciled_from_artifacts"] = True
            self._write(path, record)
            return dict(record)


class LocalShadowStore(LocalLockStore):
    """Separate S01-S03 guard/audit namespace that never consumes a daily lock."""

    @staticmethod
    def _parts(key: str) -> tuple[str, str]:
        prefix = "fplus-shadow:btcusd:"
        if not key.startswith(prefix):
            raise LockContractError("invalid BTCUSD F+ shadow key")
        remainder = key[len(prefix):]
        try:
            trade_date, shadow_id = remainder.split(":", 1)
            datetime.strptime(trade_date, "%Y-%m-%d")
        except (ValueError, TypeError) as exc:
            raise LockContractError("shadow key must contain trade date and S01-S03") from exc
        if shadow_id not in {"S01", "S02", "S03"}:
            raise LockContractError("shadow_id must be S01, S02 or S03")
        return trade_date, shadow_id

    def _path(self, key: str) -> Path:
        trade_date, shadow_id = self._parts(key)
        path = self.root / trade_date / f"{shadow_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def acquire_shadow(
        self, *, key: str, run_id: str, shadow_id: str, now_utc: str,
        lease_seconds: int, cutoff_at_utc: str, config_fingerprint: str,
    ) -> dict[str, Any]:
        _, key_shadow_id = self._parts(key)
        if shadow_id != key_shadow_id:
            raise LockContractError("shadow_id must match the shadow guard key")
        result = super().acquire(
            key=key, run_id=run_id, now_utc=now_utc,
            lease_seconds=lease_seconds, cutoff_at_utc=cutoff_at_utc,
            config_fingerprint=config_fingerprint, force=False, force_reason=None,
        )
        if result.get("status") == "already_done":
            result["status"] = "shadow_already_done"
        result["shadow_id"] = shadow_id
        return result

    def record_shadow(
        self, *, key: str, run_id: str, shadow_id: str, now_utc: str,
        audit: Mapping[str, Any], status: str = "shadow_pass",
    ) -> dict[str, Any]:
        if status not in {"shadow_pass", "shadow_fail"}:
            raise LockContractError("invalid shadow audit status")
        _, key_shadow_id = self._parts(key)
        if shadow_id != key_shadow_id:
            raise LockContractError("shadow_id must match the shadow audit key")
        now = _utc(now_utc)
        path = self._path(key)
        with self._exclusive(path):
            record = self._read(path)
            if not record or record.get("run_id") != run_id or record.get("status") != "claimed":
                raise LockContractError("only the shadow guard owner may write its audit")
            record["status"] = "committed"
            record["shadow_status"] = status
            record["shadow_id"] = shadow_id
            record["committed_at"] = _iso(now)
            record["audit"] = dict(audit)
            self._write(path, record)
            return {**record, "status": status}
