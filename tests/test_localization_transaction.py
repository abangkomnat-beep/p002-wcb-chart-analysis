import json
from pathlib import Path

import pytest

from tools import localization_transaction as tx


def _prepared(transaction_root: Path, folder: str, text: str):
    target = transaction_root / "prepared" / folder
    target.mkdir(parents=True)
    (target / "manifest.json").write_text(json.dumps({"text": text}), encoding="utf-8")
    (target / "L-EURUSD").mkdir()
    (target / "L-EURUSD" / "article.md").write_text(text, encoding="utf-8")


def test_first_delivery_and_replace_keep_the_same_public_path(tmp_path):
    marker = {"source_business_date": "2026-09-07", "countries": {"ZA": {"path": "ZA-South-Africa"}}}
    first = tx.prepare_transaction(tmp_path, "2026-09-07", "first", {"ZA": "ZA-South-Africa"}, marker)
    _prepared(first, "ZA-South-Africa", "v1")
    assert tx.apply_transaction(tmp_path, "2026-09-07", "first")["status"] == "COMMITTED"
    root = tmp_path / "output/Ready-to-Upload/07-09-2026"
    assert (root / "ZA-South-Africa/L-EURUSD/article.md").read_text() == "v1"
    second = tx.prepare_transaction(tmp_path, "2026-09-07", "second", {"ZA": "ZA-South-Africa"}, marker)
    _prepared(second, "ZA-South-Africa", "v2")
    assert tx.apply_transaction(tmp_path, "2026-09-07", "second")["status"] == "COMMITTED"
    assert (root / "ZA-South-Africa/L-EURUSD/article.md").read_text() == "v2"
    assert (second / "displaced/ZA-South-Africa/L-EURUSD/article.md").read_text() == "v1"


def test_failed_install_rolls_back_existing_country_and_marker(tmp_path, monkeypatch):
    root = tmp_path / "output/Ready-to-Upload/07-09-2026"
    old = root / "ZA-South-Africa"
    old.mkdir(parents=True)
    (old / "manifest.json").write_text("old", encoding="utf-8")
    (root / "manifest.json").write_text("old-marker", encoding="utf-8")
    marker = {"source_business_date": "2026-09-07", "countries": {"ZA": {"path": "ZA-South-Africa"}}}
    pending = tx.prepare_transaction(tmp_path, "2026-09-07", "broken", {"ZA": "ZA-South-Africa"}, marker)
    _prepared(pending, "ZA-South-Africa", "new")
    original = tx._tree
    calls = {"count": 0}
    def fail_after_install(path):
        calls["count"] += 1
        if calls["count"] == 2:
            raise tx.TransactionError("simulated verification failure")
        return original(path)
    monkeypatch.setattr(tx, "_tree", fail_after_install)
    with pytest.raises(tx.TransactionError):
        tx.apply_transaction(tmp_path, "2026-09-07", "broken")
    assert (root / "ZA-South-Africa/manifest.json").read_text() == "old"
    assert (root / "manifest.json").read_text() == "old-marker"
