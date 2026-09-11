import json

from tools import country_delivery_coverage as coverage


def _manifest(folder, country, *, day="2026-09-09", contents=b"article"):
    article = folder / "E-XAUUSD/article.md"
    article.parent.mkdir(parents=True)
    article.write_bytes(contents)
    digest = coverage._sha(article)
    (folder / "manifest.json").write_text(json.dumps({
        "schema": "p002-localized-release/v2", "country_code": country,
        "source_business_date": day, "expected_articles": 4,
        "files": {"E-XAUUSD/article.md": digest},
    }), encoding="utf-8")


def test_report_keeps_missing_country_separate_from_thai_selector(tmp_path):
    day = tmp_path / "output/09-09-2026"
    _manifest(day / "MY-Malaysia", "MY")
    result = coverage.report(output_root=tmp_path / "output", work_root=tmp_path / "work",
                             business_date="2026-09-09", countries=["MY", "BR"])
    assert result["status"] == "HOLD"
    assert result["delivered_count"] == 1
    assert result["countries"][1]["reason"] == "DELIVERY_MANIFEST_MISSING"


def test_report_passes_only_when_each_country_manifest_and_files_match(tmp_path):
    day = tmp_path / "output/09-09-2026"
    _manifest(day / "MY-Malaysia", "MY")
    _manifest(day / "BR-Brazil", "BR")
    result = coverage.report(output_root=tmp_path / "output", work_root=tmp_path / "work",
                             business_date="2026-09-09", countries=["MY", "BR"])
    assert result["status"] == "PASS"
    assert result["delivered_count"] == 2
