import json
from pathlib import Path

import pytest

from tools import localization_config as config


def test_za_and_my_are_explicit_and_have_stable_delivery_folders():
    za, my = config.resolve_country("ZA"), config.resolve_country("MY")
    assert (za["content_locale"], za["language_pack"], za["output_folder"]) == (
        "en-ZA", "en-001", "ZA-South-Africa")
    assert (my["content_locale"], my["language_pack"], my["output_folder"]) == (
        "ms-MY", "ms-MY", "MY-Malaysia")
    assert za["link_policy"] == my["link_policy"] == "preserve_source_thai"


def test_country_delivery_article_path_is_country_then_style_then_asset():
    assert config.delivery_article_path("2026-09-07", "ZA", "l", "eurusd") == "L/EURUSD/P002-20260907-ZA-L-EURUSD-article.md"
    with pytest.raises(config.LocalizationConfigError):
        config.delivery_article_path("2026-09-07", "ZA", "LL", "EURUSD")


def test_country_requires_explicit_policy(tmp_path):
    registry = {"countries": [{"country_code": "AA", "content_locale": "aa-AA", "language_pack": "aa-AA"}]}
    policy = {"schema": "p002-localization-country-policy/v1", "countries": {}}
    registry_path, policy_path = tmp_path / "registry.json", tmp_path / "policy.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(config.LocalizationConfigError, match="no explicit"):
        config.resolve_country("AA", registry_path=registry_path, policy_path=policy_path)


def test_manifest_mapping_and_policy_hash_are_checked():
    za = config.resolve_country("ZA")
    assert config.require_manifest_country({
        "country_code": "ZA", "content_locale": "en-ZA", "language_pack": "en-001",
        "country_policy_sha256": za["policy_sha256"],
    })["country_code"] == "ZA"
    with pytest.raises(config.LocalizationConfigError, match="content_locale"):
        config.require_manifest_country({"country_code": "ZA", "content_locale": "ms-MY", "language_pack": "en-001"})
