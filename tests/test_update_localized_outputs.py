import json
from pathlib import Path

from tools import update_localized_outputs as command


def _day(tmp_path):
    source = tmp_path / "output/07-09-2026/L-Forex-Daily/eurusd.md"
    source.parent.mkdir(parents=True)
    source.write_text("thai", encoding="utf-8")
    import hashlib
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    country = tmp_path / "output/07-09-2026/ZA-South-Africa"
    country.mkdir(parents=True)
    (country / "manifest.json").write_text(json.dumps({
        "country_code": "ZA", "content_locale": "en-ZA", "generation_id": "g1",
        "sources": [{"article_id": "L-EURUSD", "source_path": "output/07-09-2026/L-Forex-Daily/eurusd.md",
                     "source_sha256": source_hash, "images": []}],
    }), encoding="utf-8")
    root = country.parent
    (root / "manifest.json").write_text(json.dumps({"source_business_date": "2026-09-07",
                                                       "countries": {"ZA": {"path": "ZA-South-Africa"}}}), encoding="utf-8")


def test_prepare_update_writes_a_stable_impact_plan(tmp_path):
    _day(tmp_path)
    plan, path = command.write_impact_plan(tmp_path, "2026-09-07")
    assert plan["status"] == "READY"
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8"))["changes"][0]["status"] == "UNCHANGED"


def test_cli_plan_update_is_read_only(tmp_path, capsys):
    _day(tmp_path)
    assert command.main(["--project-root", str(tmp_path), "--date", "2026-09-07", "--plan-update"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "READY"
    assert not (tmp_path / "work").exists()
