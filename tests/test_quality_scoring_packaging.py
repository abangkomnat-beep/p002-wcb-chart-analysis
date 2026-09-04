from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_jsonschema_dependency_is_declared_at_tested_floor():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "jsonschema>=4.26" in requirements


def test_readme_links_shadow_scoring_runbook():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/QUALITY-SCORING-RUNBOOK.md" in readme
    assert "ไม่มีผลต่อ publish selector" in readme


def test_runbook_has_operational_and_testable_rollback_contracts():
    runbook = (ROOT / "docs" / "QUALITY-SCORING-RUNBOOK.md").read_text(encoding="utf-8")
    required = ["Single และ batch", "Human-readable summary", "append-only history",
                "batch-50", "ABANDONED_PRE_MERGE", "git status --short",
                "git revert <promotion-sha>", "git diff --check", "ไม่มีผลต่อ publish selector"]
    assert all(text in runbook for text in required)
    assert "ห้ามใช้ `git reset --hard`" in runbook
    assert "ห้ามลบ worktree" in runbook


def test_quality_summary_help_supports_direct_and_module_invocation():
    commands = ([sys.executable, "tools/quality_summary.py", "--help"],
                [sys.executable, "-m", "tools.quality_summary", "--help"])
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                                   check=False, timeout=20)
        assert completed.returncode == 0, completed.stderr
        assert "--output" in completed.stdout
