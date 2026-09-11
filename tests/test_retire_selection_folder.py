from pathlib import Path

import pytest

from tools import retire_selection_folder as retirement


def _seed(root: Path, *, matching: bool = True):
    day = root / "output/09-09-2026"
    country = day / "TH-Thailand/E/XAUUSD"
    legacy = day / retirement.FOLDER / "02-XAUUSD-Style-E"
    country.mkdir(parents=True)
    legacy.mkdir(parents=True)
    (country / "article.md").write_text("current", encoding="utf-8")
    (legacy / "article.md").write_text("current" if matching else "different", encoding="utf-8")
    (legacy / "selection-report.json").write_text("{}", encoding="utf-8")
    return day, legacy


def test_prepare_requires_each_copy_to_match_one_country_file(tmp_path):
    _day, legacy = _seed(tmp_path, matching=False)
    with pytest.raises(retirement.RetirementError, match="does not match"):
        retirement.prepare(output_root=tmp_path / "output", work_root=tmp_path / "work",
                           business_date="2026-09-09")
    assert legacy.is_dir()


def test_apply_moves_verified_copy_to_work_with_idempotent_journal(tmp_path):
    _day, legacy = _seed(tmp_path)
    first = retirement.apply(output_root=tmp_path / "output", work_root=tmp_path / "work",
                             business_date="2026-09-09")
    target = tmp_path / "work/localization/09-09-2026/output-country-cutover/legacy-selection-copy"
    assert first["state"] == "COMMITTED"
    assert not legacy.exists()
    assert (target / "02-XAUUSD-Style-E/article.md").read_text(encoding="utf-8") == "current"
    second = retirement.apply(output_root=tmp_path / "output", work_root=tmp_path / "work",
                              business_date="2026-09-09")
    assert second["idempotent"] is True


def test_recover_restores_only_the_committed_hash_matched_folder(tmp_path):
    _day, legacy = _seed(tmp_path)
    retirement.apply(output_root=tmp_path / "output", work_root=tmp_path / "work",
                     business_date="2026-09-09")
    recovered = retirement.recover(output_root=tmp_path / "output", work_root=tmp_path / "work",
                                   business_date="2026-09-09")
    assert recovered["state"] == "RECOVERED"
    assert (legacy / "article.md").read_text(encoding="utf-8") == "current"


def test_recover_refuses_modified_archive(tmp_path):
    _day, _legacy = _seed(tmp_path)
    retirement.apply(output_root=tmp_path / "output", work_root=tmp_path / "work",
                     business_date="2026-09-09")
    target = tmp_path / "work/localization/09-09-2026/output-country-cutover/legacy-selection-copy"
    (target / "02-XAUUSD-Style-E/article.md").write_text("changed", encoding="utf-8")
    with pytest.raises(retirement.RetirementError, match="changed"):
        retirement.recover(output_root=tmp_path / "output", work_root=tmp_path / "work",
                           business_date="2026-09-09")


def test_prepare_rejects_symlink_in_legacy_tree(tmp_path):
    _day, legacy = _seed(tmp_path)
    link = legacy / "link.md"
    try:
        link.symlink_to(legacy / "article.md")
    except OSError:
        pytest.skip("symlink privileges unavailable")
    with pytest.raises(retirement.RetirementError, match="symlink"):
        retirement.prepare(output_root=tmp_path / "output", work_root=tmp_path / "work",
                           business_date="2026-09-09")
