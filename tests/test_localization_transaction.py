import json
import hashlib
from pathlib import Path

import pytest

from tools import localization_transaction as tx


def _prepared(transaction_root: Path, folder: str, text: str):
    target = transaction_root / "prepared" / folder
    target.mkdir(parents=True)
    (target / "L" / "EURUSD").mkdir(parents=True)
    (target / "L" / "EURUSD" / "article.md").write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode()).hexdigest()
    code = "ZA" if folder == "ZA-South-Africa" else "MY"
    (target / "manifest.json").write_text(json.dumps({
        "schema": "p002-localized-release/v2", "country_code": code,
        "source_business_date": "2026-09-07", "generation_id": "g1",
        "source_manifest_sha256": "a" * 64, "receipt_index_sha256": "b" * 64,
        "pack_sha256": "c" * 64, "country_policy_sha256": "d" * 64,
        "files": {"L/EURUSD/article.md": digest},
    }), encoding="utf-8")
    (target / "README.md").write_text("country release\n", encoding="utf-8")


def _marker(countries):
    return {"schema": "p002-localized-day/v2", "source_business_date": "2026-09-07",
            "countries": {code: {"path": folder, "release_id": "r1",
                                  "manifest_sha256": "f" * 64}
                          for code, folder in countries.items()}}


def test_first_delivery_and_replace_keep_the_same_public_path(tmp_path):
    marker = _marker({"ZA": "ZA-South-Africa"})
    first = tx.prepare_transaction(tmp_path, "2026-09-07", "first", {"ZA": "ZA-South-Africa"}, marker)
    _prepared(first, "ZA-South-Africa", "v1")
    assert tx.apply_transaction(tmp_path, "2026-09-07", "first")["status"] == "COMMITTED"
    root = tmp_path / "output/07-09-2026"
    assert (root / "ZA-South-Africa/L/EURUSD/article.md").read_text() == "v1"
    second = tx.prepare_transaction(tmp_path, "2026-09-07", "second", {"ZA": "ZA-South-Africa"}, marker)
    _prepared(second, "ZA-South-Africa", "v2")
    assert tx.apply_transaction(tmp_path, "2026-09-07", "second")["status"] == "COMMITTED"
    assert (root / "ZA-South-Africa/L/EURUSD/article.md").read_text() == "v2"
    assert (second / "displaced/ZA-South-Africa/L/EURUSD/article.md").read_text() == "v1"


def test_failed_install_rolls_back_existing_country_and_marker(tmp_path, monkeypatch):
    root = tmp_path / "output/07-09-2026"
    old = root / "ZA-South-Africa"
    old.mkdir(parents=True)
    (old / "manifest.json").write_text("old", encoding="utf-8")
    (root / "manifest.json").write_text("old-marker", encoding="utf-8")
    marker = _marker({"ZA": "ZA-South-Africa"})
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


def test_missing_prepared_tree_never_moves_the_current_delivery(tmp_path):
    root = tmp_path / "output/07-09-2026"
    old = root / "ZA-South-Africa"
    old.mkdir(parents=True)
    (old / "article.md").write_text("old", encoding="utf-8")
    marker = _marker({"ZA": "ZA-South-Africa"})
    pending = tx.prepare_transaction(tmp_path, "2026-09-07", "missing", {"ZA": "ZA-South-Africa"}, marker)
    with pytest.raises(tx.TransactionError):
        tx.apply_transaction(tmp_path, "2026-09-07", "missing")
    assert (old / "article.md").read_text() == "old"
    assert not (pending / "failed").exists()


def test_unattested_tree_is_rejected_before_any_public_write(tmp_path):
    marker = _marker({"MY": "MY-Malaysia"})
    pending = tx.prepare_transaction(tmp_path, "2026-09-07", "unattested", {"MY": "MY-Malaysia"}, marker)
    target = pending / "prepared/MY-Malaysia"
    target.mkdir(parents=True)
    (target / "article.md").write_text("not checked", encoding="utf-8")
    with pytest.raises(tx.TransactionError):
        tx.apply_transaction(tmp_path, "2026-09-07", "unattested")
    assert not (tmp_path / "output/07-09-2026/MY-Malaysia").exists()


def test_recover_prepared_and_rolled_back_is_idempotent(tmp_path):
    marker = _marker({"ZA": "ZA-South-Africa"})
    tx.prepare_transaction(tmp_path, "2026-09-07", "idle", {"ZA": "ZA-South-Africa"}, marker)
    assert tx.recover_transaction(tmp_path, "2026-09-07", "idle")["status"] == "PREPARED"


def test_prepared_extra_file_is_rejected_before_public_mutation(tmp_path):
    marker = _marker({"ZA": "ZA-South-Africa"})
    pending = tx.prepare_transaction(tmp_path, "2026-09-07", "extra", {"ZA": "ZA-South-Africa"}, marker)
    _prepared(pending, "ZA-South-Africa", "new")
    (pending / "prepared/ZA-South-Africa/unlisted.txt").write_text("no", encoding="utf-8")
    with pytest.raises(tx.TransactionError, match="unlisted"):
        tx.apply_transaction(tmp_path, "2026-09-07", "extra")
    assert not (tmp_path / "output/07-09-2026/ZA-South-Africa").exists()


def test_reader_requires_a_real_manifest_hash(tmp_path):
    root = tmp_path / "output/07-09-2026"
    country = root / "ZA-South-Africa"
    country.mkdir(parents=True)
    (country / "manifest.json").write_text(json.dumps({"country_code": "ZA"}), encoding="utf-8")
    marker = {"schema": "p002-localized-day/v2", "source_business_date": "2026-09-07",
              "countries": {"ZA": {"path": "ZA-South-Africa", "release_id": "r1"}}}
    (root / "manifest.json").write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(tx.TransactionError, match="release binding"):
        tx.read_delivery(tmp_path, "2026-09-07")


def test_commit_journal_failure_after_manifest_restores_previous_delivery(tmp_path, monkeypatch):
    root = tmp_path / "output/07-09-2026"
    old = root / "ZA-South-Africa"
    old.mkdir(parents=True)
    (old / "manifest.json").write_text("old", encoding="utf-8")
    (root / "manifest.json").write_text("old-marker", encoding="utf-8")
    marker = _marker({"ZA": "ZA-South-Africa"})
    pending = tx.prepare_transaction(tmp_path, "2026-09-07", "journal-fail", {"ZA": "ZA-South-Africa"}, marker)
    _prepared(pending, "ZA-South-Africa", "new")
    original = tx._atomic_write

    def fail_commit(path, data):
        if path.name == "journal.json" and b'"state": "COMMITTED"' in data:
            raise OSError("simulated final journal failure")
        return original(path, data)

    monkeypatch.setattr(tx, "_atomic_write", fail_commit)
    with pytest.raises(tx.TransactionError, match="simulated final journal"):
        tx.apply_transaction(tmp_path, "2026-09-07", "journal-fail")
    assert (root / "ZA-South-Africa/manifest.json").read_text() == "old"
    assert (root / "manifest.json").read_text() == "old-marker"
    assert tx.recover_transaction(tmp_path, "2026-09-07", "journal-fail")["status"] == "ROLLED_BACK"
