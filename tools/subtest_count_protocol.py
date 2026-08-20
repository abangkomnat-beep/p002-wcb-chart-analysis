"""Repeatable subTest accounting protocol for P002 regression evidence.

Usage: ``python -m tools.subtest_count_protocol -q``.  It counts every
``unittest.TestCase.subTest`` invocation by test node and emits a JSON record
after pytest exits.  It does not change test behavior or production files.
"""
from __future__ import annotations

import argparse
import json
import sys
import unittest
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
    counts: Counter[str] = Counter()
    original = unittest.TestCase.subTest

    def tracked(self: unittest.TestCase, *subtest_args, **subtest_kwargs):
        label = ",".join(f"{key}={value!r}" for key, value in sorted(subtest_kwargs.items()))
        counts[f"{self.id()} [{label}]" if label else self.id()] += 1
        return original(self, *subtest_args, **subtest_kwargs)

    unittest.TestCase.subTest = tracked  # type: ignore[assignment]
    try:
        exit_code = pytest.main(args.pytest_args or ["-q"])
    finally:
        unittest.TestCase.subTest = original  # type: ignore[assignment]
    print(json.dumps({
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "exit_code": int(exit_code),
        "subtest_total": sum(counts.values()),
        "by_node": dict(sorted(counts.items())) if not summary_only else {},
    }, ensure_ascii=True, sort_keys=True))
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
