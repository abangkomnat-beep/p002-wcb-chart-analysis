"""Artifact gate for exact two-file F+ output and No-trade hygiene."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from fixtures.fplus.contract_support import load_json, require_module


def make_webp(path: Path, *, size=(1200, 675), quality=50):
    Image.new("RGB", size, "#101722").save(path, "WEBP", quality=quality)


def make_stage(path: Path, plan: dict):
    path.mkdir()
    (path / "btcusd.md").write_text(
        "---\nasset: btcusd\ntrade_date: 2026-08-24\n---\n# BTCUSD F+\n\nงดเทรดและรอแท่งปิดยืนยันใหม่\n"
        if plan["selection"] == "NO_TRADE" else
        "---\nasset: btcusd\ntrade_date: 2026-08-24\n---\n# BTCUSD F+\n\nEntry 70000-70100\nSL 69500\nTP1 70820\nRR 1.2\n",
        encoding="utf-8",
    )
    make_webp(path / "btcusd-fplus-2026-08-24.webp")


def test_validator_accepts_exact_two_file_trade_set_and_returns_manifest(tmp_path):
    validator = require_module("tools.fplus_validator")
    stage = tmp_path / "stage"
    plan = load_json("selected_trade.json")
    make_stage(stage, plan)
    manifest = validator.validate_artifact_set(stage, plan, image_max_bytes=204_800)
    assert [item["name"] for item in manifest["files"]] == [
        "btcusd.md", "btcusd-fplus-2026-08-24.webp",
    ]
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])
    assert len(manifest["artifact_set_sha256"]) == 64


@pytest.mark.parametrize("extra_name", ["decision.json", "selected-plan.json", "style-e.md"])
def test_validator_rejects_internal_or_extra_files_in_final_set(tmp_path, extra_name):
    validator = require_module("tools.fplus_validator")
    stage = tmp_path / "stage"
    plan = load_json("selected_trade.json")
    make_stage(stage, plan)
    (stage / extra_name).write_text("{}", encoding="utf-8")
    with pytest.raises(validator.ArtifactValidationError, match="exact|extra|two|2"):
        validator.validate_artifact_set(stage, plan, image_max_bytes=204_800)


def test_no_trade_validator_rejects_entry_sl_tp_leak(tmp_path):
    validator = require_module("tools.fplus_validator")
    stage = tmp_path / "stage"
    plan = load_json("selected_no_trade.json")
    make_stage(stage, plan)
    (stage / "btcusd.md").write_text("# No-trade\nEntry 70000\nSL 69000\nTP 71000", encoding="utf-8")
    with pytest.raises(validator.ArtifactValidationError, match="NO_TRADE|Entry|trade"):
        validator.validate_artifact_set(stage, plan, image_max_bytes=204_800)


def test_validator_rejects_wrong_image_name(tmp_path):
    validator = require_module("tools.fplus_validator")
    stage = tmp_path / "stage"
    plan = load_json("selected_trade.json")
    make_stage(stage, plan)
    image = stage / "btcusd-fplus-2026-08-24.webp"
    image.rename(stage / "wrong.webp")
    with pytest.raises(validator.ArtifactValidationError):
        validator.validate_artifact_set(stage, plan, image_max_bytes=204_800)


def test_validator_rejects_oversize_webp(tmp_path):
    validator = require_module("tools.fplus_validator")
    stage = tmp_path / "stage"
    plan = load_json("selected_trade.json")
    make_stage(stage, plan)
    image = stage / "btcusd-fplus-2026-08-24.webp"
    with image.open("ab") as handle:
        handle.write(b"x" * 204_800)
    with pytest.raises(validator.ArtifactValidationError, match="size|bytes|200"):
        validator.validate_artifact_set(stage, plan, image_max_bytes=204_800)
