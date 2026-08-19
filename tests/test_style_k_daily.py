"""ล็อกทางเข้าสั่งมือของ Style K ไม่ให้พังบนคอนโซล Windows ภาษาไทย."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import style_k_daily  # noqa: E402


def test_reader_dir_uses_shared_date_folder_layout():
    assert style_k_daily.reader_dir("2026-08-17").parts[-2:] == (
        "17-08-2026", "K-Synthesis Writer"
    )


def test_main_sets_utf8_console_and_runs_configured_asset():
    config = {"assets": {"xauusd": {}}}
    result = {"asset": "xauusd", "session_date": "2026-08-17", "tier": "A",
              "decision": "trade", "problems": [], "article": "internal.md",
              "no_trade_reason": None, "word_count": 420}

    with mock.patch.object(style_k_daily, "load_config", return_value=config), \
            mock.patch.object(style_k_daily, "run_asset", return_value=result) as run, \
            mock.patch.object(style_k_daily.sys.stdout, "reconfigure") as reconfigure:
        assert style_k_daily.main(["--asset", "xauusd"]) == 0

    reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")
    run.assert_called_once_with("xauusd", config)
