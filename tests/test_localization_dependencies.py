import hashlib
import json
from pathlib import Path

from tools import localization_dependencies as deps


def _put(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _delivery(tmp_path):
    source = tmp_path / "output/07-09-2026/L-Forex-Daily/eurusd.md"
    image = source.with_name("chart.webp")
    source_hash, image_hash = _put(source, b"thai v1"), _put(image, b"image v1")
    root = tmp_path / "output/07-09-2026"
    country = root / "ZA-South-Africa"
    manifest = {"country_code": "ZA", "content_locale": "en-ZA", "generation_id": "g1", "pack_sha256": "a" * 64,
                "country_policy_sha256": "b" * 64,
                "sources": [{"article_id": "L-EURUSD", "source_path": "output/07-09-2026/L-Forex-Daily/eurusd.md",
                             "source_sha256": source_hash,
                             "images": [{"source_path": "output/07-09-2026/L-Forex-Daily/chart.webp", "source_sha256": image_hash}]}]}
    _put(country / "manifest.json", json.dumps(manifest).encode())
    marker = {"source_business_date": "2026-09-07", "countries": {"ZA": {"path": "ZA-South-Africa"}}}
    _put(root / "manifest.json", json.dumps(marker).encode())
    return source, image


def test_rebuild_and_detect_text_and_image_changes(tmp_path):
    source, image = _delivery(tmp_path)
    index = deps.rebuild_index(tmp_path, "2026-09-07")
    assert [item["status"] for item in deps.detect_changes(tmp_path, index)] == ["UNCHANGED"]
    source.write_bytes(b"thai v2")
    assert deps.plan_update(tmp_path, "2026-09-07")["changes"][0]["status"] == "MODIFIED"
    source.write_bytes(b"thai v1")
    image.write_bytes(b"image v2")
    result = deps.plan_update(tmp_path, "2026-09-07")["changes"][0]
    assert result["status"] == "MODIFIED" and result["image_changes"]


def test_missing_source_holds_instead_of_dropping_country(tmp_path):
    source, _ = _delivery(tmp_path)
    source.unlink()
    plan = deps.plan_update(tmp_path, "2026-09-07")
    assert plan["status"] == "HOLD"
    assert plan["changes"][0]["status"] == "MISSING"


def test_no_delivery_marker_is_explicitly_an_initial_release(tmp_path):
    plan = deps.plan_update(tmp_path, "2026-09-07")
    assert plan["status"] == "NO_COMMITTED_COUNTRIES"
    assert plan["dependency_state"] == "NO_COMMITTED_COUNTRIES"
    assert plan["changes"] == []
