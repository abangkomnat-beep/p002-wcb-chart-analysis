"""Repeatable subTest accounting protocol for P002 regression evidence.

Usage: ``python -m tools.subtest_count_protocol -q``.  It counts every
``unittest.TestCase.subTest`` invocation by test node and emits a JSON record
after pytest exits.  It does not change test behavior or production files.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone

import pytest


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or [])
    summary_only = "--summary-only" in argv
    argv = [item for item in argv if item != "--summary-only"]
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    subtests: list[tuple[str, str]] = []

    class Collector:
        def pytest_terminal_summary(self, terminalreporter, exitstatus, config):
            for key in ("subtests passed", "subtests failed"):
                for report in terminalreporter.stats.get(key, []):
                    context = getattr(report, "context", None)
                    kwargs = getattr(context, "kwargs", {}) if context is not None else {}
                    label = ",".join(f"{name}={value}" for name, value in sorted(kwargs.items()))
                    subtests.append((report.nodeid, label))

    exit_code = pytest.main(args.pytest_args or ["-q"], plugins=[Collector()])
    by_node = Counter(f"{node} [{label}]" if label else node for node, label in subtests)
    by_test = Counter(node for node, _label in subtests)
    print(json.dumps({
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "exit_code": int(exit_code),
        "subtest_total": len(subtests),
        "by_node": dict(sorted(by_node.items())) if not summary_only else {},
        "by_test": dict(sorted(by_test.items())),
    }, ensure_ascii=True, sort_keys=True))
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
