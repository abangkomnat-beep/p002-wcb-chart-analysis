import json
from pathlib import Path

import pytest

from tools import quarantine_unscheduled_output as quarantine


def _seed(root: Path) -> Path:
    folder = root / "output/09-09-2026/TH-Thailand/F-กรอบราคา"
    folder.mkdir(parents=True)
    (folder / "xauusd.md").write_text("fixture", encoding="utf-8")
    (folder / "xauusd.webp").write_bytes(b"webp")
    return folder


def test_prepare_is_hash_inventory_only(tmp_path):
    source = _seed(tmp_path)
    result = quarantine.prepare(output_root=tmp_path / "output", work_root=tmp_path / "work",
                                business_date="2026-09-09")
    assert result["state"] == "PREPARED"
    assert [item["folder"] for item in result["records"]] == ["F-กรอบราคา"]
    assert source.is_dir()
    journal = json.loads(Path(result["journal"]).read_text(encoding="utf-8"))
    assert journal["records"][0]["files"] == {"xauusd.md": quarantine._hashes(source)["xauusd.md"],
                                                   "xauusd.webp": quarantine._hashes(source)["xauusd.webp"]}


def test_apply_moves_only_known_legacy_folder_and_keeps_hashes(tmp_path):
    source = _seed(tmp_path)
    untouched = tmp_path / "output/09-09-2026/TH-Thailand/E/XAUUSD"
    untouched.mkdir(parents=True)
    (untouched / "article.md").write_text("final", encoding="utf-8")

    result = quarantine.apply(output_root=tmp_path / "output", work_root=tmp_path / "work",
                              business_date="2026-09-09")
    target = tmp_path / "work/build/09-09-2026/TH-Thailand/F-กรอบราคา"
    assert result["state"] == "COMMITTED"
    assert not source.exists()
    assert quarantine._hashes(target) == result["records"][0]["files"]
    assert (untouched / "article.md").read_text(encoding="utf-8") == "final"
    assert quarantine.apply(output_root=tmp_path / "output", work_root=tmp_path / "work",
                            business_date="2026-09-09") == result


def test_refuses_to_overwrite_existing_work_folder(tmp_path):
    _seed(tmp_path)
    existing = tmp_path / "work/build/09-09-2026/TH-Thailand/F-กรอบราคา"
    existing.mkdir(parents=True)
    with pytest.raises(quarantine.QuarantineError, match="already exists"):
        quarantine.prepare(output_root=tmp_path / "output", work_root=tmp_path / "work",
                           business_date="2026-09-09")


def test_apply_rolls_back_folder_when_post_move_hash_check_fails(tmp_path, monkeypatch):
    source = _seed(tmp_path)
    expected = quarantine._hashes(source)
    real_hashes = quarantine._hashes
    calls = {"count": 0}

    def fail_target_hash(path):
        calls["count"] += 1
        if calls["count"] == 2:
            return {"changed": "hash"}
        return real_hashes(path)

    monkeypatch.setattr(quarantine, "_hashes", fail_target_hash)
    with pytest.raises(quarantine.QuarantineError, match="hash mismatch"):
        quarantine.apply(output_root=tmp_path / "output", work_root=tmp_path / "work",
                         business_date="2026-09-09")
    assert source.is_dir()
    assert real_hashes(source) == expected
