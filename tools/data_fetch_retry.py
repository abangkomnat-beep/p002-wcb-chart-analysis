"""One-retry wrapper for closed-chart acquisition and validation failures."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class DataFetchUnavailable(RuntimeError):
    """The same asset/timeframe failed acquisition/closed-bar validation twice."""

    def __init__(self, *, asset: str, timeframe: str, failures: list[str]) -> None:
        self.asset = asset
        self.timeframe = timeframe
        self.failures = tuple(failures)
        detail = " | ".join(f"attempt {i + 1}: {message}"
                            for i, message in enumerate(self.failures))
        super().__init__(
            f"กราฟ {asset} {timeframe} ใช้งานไม่ได้หลังลอง 2 ครั้ง: {detail}")


def run_with_one_retry(operation: Callable[[], Any], *, asset: str,
                       timeframe: str) -> Any:
    """Run an acquisition operation at most twice, preserving exact diagnostics."""
    failures: list[str] = []
    for _ in range(2):
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001 - report every provider/domain failure
            failures.append(f"{type(exc).__name__}: {exc}")
    raise DataFetchUnavailable(asset=asset, timeframe=timeframe, failures=failures)


__all__ = ["DataFetchUnavailable", "run_with_one_retry"]
