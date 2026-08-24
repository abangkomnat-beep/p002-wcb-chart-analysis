"""Directory-level transaction and recovery for an F+ artifact generation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping


class InjectedTransactionFailure(RuntimeError):
    """Fault-injection exception used to prove recovery behavior."""


class ArtifactTransaction:
    def __init__(self, *, work_root: str | Path, output_root: str | Path):
        self.work_root = Path(work_root)
        self.output_root = Path(output_root)
        self.journal_root = self.work_root / "internal" / "fplus" / "transactions"
        self.backup_root = self.work_root / "internal" / "fplus" / "backups"
        self.journal_root.mkdir(parents=True, exist_ok=True)
        self.backup_root.mkdir(parents=True, exist_ok=True)

    def _journal_path(self, relative: Path) -> Path:
        key = hashlib.sha256(str(relative).replace("\\", "/").encode("utf-8")).hexdigest()
        return self.journal_root / f"{key}.json"

    @staticmethod
    def _write_journal(path: Path, journal: Mapping[str, Any]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(journal, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                             encoding="utf-8")
        os.replace(temporary, path)

    @staticmethod
    def _manifest_matches(directory: Path, manifest: Mapping[str, Any]) -> bool:
        if not directory.is_dir():
            return False
        expected = {item["name"]: item["sha256"] for item in manifest.get("files", [])}
        actual_names = {path.name for path in directory.iterdir() if path.is_file()}
        if actual_names != set(expected):
            return False
        for name, expected_hash in expected.items():
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected_hash:
                return False
        return True

    @staticmethod
    def _raise_if(fault_at: str | None, point: str) -> None:
        if fault_at == point:
            raise InjectedTransactionFailure(f"injected transaction failure at {point}")

    def commit(
        self, stage: str | Path, *, relative_final_dir: str | Path,
        manifest: Mapping[str, Any], force: bool = False,
        fault_at: str | None = None,
    ) -> dict[str, Any]:
        stage_path = Path(stage)
        relative = Path(relative_final_dir)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("relative_final_dir must stay below output_root")
        final = self.output_root / relative
        final.parent.mkdir(parents=True, exist_ok=True)
        if not self._manifest_matches(stage_path, manifest):
            raise ValueError("staging files do not match manifest")
        journal_path = self._journal_path(relative)
        backup = self.backup_root / f"{manifest.get('run_id', 'run')}-g{manifest.get('generation', 1)}-previous"
        journal: dict[str, Any] = {
            "phase": "prepared", "stage": str(stage_path), "final": str(final),
            "backup": str(backup), "relative_final_dir": str(relative),
            "manifest": dict(manifest), "force": bool(force),
        }
        self._write_journal(journal_path, journal)
        self._raise_if(fault_at, "prepared")
        if final.exists():
            if not force:
                raise FileExistsError(f"final artifact directory already exists: {final}")
            if backup.exists():
                raise FileExistsError(f"immutable transaction backup already exists: {backup}")
            os.replace(final, backup)
            journal["phase"] = "old_parked"
            self._write_journal(journal_path, journal)
            self._raise_if(fault_at, "old_parked")
        os.replace(stage_path, final)
        journal["phase"] = "new_visible"
        self._write_journal(journal_path, journal)
        self._raise_if(fault_at, "new_visible")
        if not self._manifest_matches(final, manifest):
            if backup.exists() and not final.exists():
                os.replace(backup, final)
            raise ValueError("promoted files do not match manifest")
        self._raise_if(fault_at, "before_lock_commit")
        journal["phase"] = "awaiting_lock_commit"
        self._write_journal(journal_path, journal)
        return {"final_dir": str(final), "transaction_journal": str(journal_path),
                "manifest": dict(manifest)}

    def recover(self, *, relative_final_dir: str | Path) -> dict[str, Any]:
        relative = Path(relative_final_dir)
        journal_path = self._journal_path(relative)
        if not journal_path.is_file():
            raise FileNotFoundError(f"transaction journal not found: {journal_path}")
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        final = Path(journal["final"])
        stage = Path(journal["stage"])
        backup = Path(journal["backup"])
        manifest = journal["manifest"]
        if self._manifest_matches(final, manifest):
            journal["phase"] = "recovered_new_visible"
        elif backup.is_dir():
            if final.exists():
                raise RuntimeError("unsafe recovery: invalid final directory is still visible")
            os.replace(backup, final)
            journal["phase"] = "recovered_previous"
        elif self._manifest_matches(stage, manifest) and not final.exists():
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage, final)
            journal["phase"] = "recovered_new_visible"
        elif final.is_dir():
            journal["phase"] = "recovered_previous_visible"
        else:
            raise RuntimeError("transaction cannot be recovered safely")
        self._write_journal(journal_path, journal)
        return {"final_dir": str(final), "transaction_journal": str(journal_path),
                "phase": journal["phase"], "manifest": manifest}

    def mark_lock_committed(self, *, relative_final_dir: str | Path) -> dict[str, Any]:
        """Advance the journal only after the production lock CAS succeeds."""
        relative = Path(relative_final_dir)
        journal_path = self._journal_path(relative)
        if not journal_path.is_file():
            raise FileNotFoundError(f"transaction journal not found: {journal_path}")
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        final = Path(journal["final"])
        if not self._manifest_matches(final, journal["manifest"]):
            raise RuntimeError("cannot commit journal: visible artifacts fail manifest verification")
        journal["phase"] = "lock_committed"
        self._write_journal(journal_path, journal)
        return {"transaction_journal": str(journal_path), "phase": "lock_committed"}

    def journal(self, *, relative_final_dir: str | Path) -> dict[str, Any] | None:
        path = self._journal_path(Path(relative_final_dir))
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
