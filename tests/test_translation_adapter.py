import pytest

from tools import translation_adapter as adapter
from tools.active_rollout import ACTIVE_COUNTRIES


def _starter(document, language, source_path):
    return {
        "job_type": "markdown_agent_translation",
        "language_code": language,
        "chunks": [{"id": "body:1", "source": document}],
    }


def test_all_twenty_countries_have_a_valid_explicit_route():
    assert tuple(adapter._read_routing()["routes"]) == ACTIVE_COUNTRIES
    for country in ACTIVE_COUNTRIES:
        route = adapter.route_for(country)
        assert route["content_locale"]
        assert route["direction"] in {"ltr", "rtl"}
        if country == "TH":
            assert route["translation_required"] is False
            assert route["engine_language"] is None
        else:
            assert route["translation_required"] is True
            assert route["engine_language"]


def test_philippines_uses_co_op_tagalog_bridge_but_keeps_fil_locale():
    route = adapter.route_for("PH")
    assert route["content_locale"] == "fil-PH"
    assert route["engine_language"] == "tl"


def test_rtl_routes_are_explicit_not_inferred_from_language_name():
    assert adapter.route_for("SA")["direction"] == "rtl"
    assert adapter.route_for("AE")["direction"] == "rtl"
    assert adapter.route_for("PK")["direction"] == "rtl"


def test_prepare_job_records_source_and_protected_values_without_receipt():
    job = adapter.prepare_markdown_job(
        country_code="MY",
        document="ราคา 4,436.46 หากปิดเหนือ 4,400\n",
        source_path="TH-Thailand/E/XAUUSD/article.md",
        protected_literals=["4,436.46", "4,400"],
        starter=_starter,
    )
    assert job["schema"] == adapter.ADAPTER_SCHEMA
    assert job["state"] == "PREPARED"
    assert job["mode"] == "calibration"
    assert job["gates"]["source_qa"] == "NOT_REQUIRED_FOR_CALIBRATION"
    assert job["upstream"]["job"]["language_code"] == "ms"
    assert job["gates"]["independent_review"] == "PENDING"
    assert "receipt" not in job


def test_source_and_translated_protected_values_fail_closed():
    with pytest.raises(adapter.TranslationAdapterError, match="absent"):
        adapter.prepare_markdown_job(
            country_code="MY", document="ราคา 4,436.46", source_path="source.md",
            protected_literals=["9,999"], starter=_starter,
        )
    with pytest.raises(adapter.TranslationAdapterError, match="changed protected"):
        adapter.verify_protected_literals("ราคา 4,400", ["4,436.46"])


def test_finish_rejects_missing_or_extra_chunks_and_returns_review_candidate():
    job = adapter.prepare_markdown_job(
        country_code="MY", document="ราคา 4,436.46", source_path="source.md",
        protected_literals=["4,436.46"], starter=_starter,
    )
    with pytest.raises(adapter.TranslationAdapterError, match="missing"):
        adapter.finish_markdown_job(job, {})
    with pytest.raises(adapter.TranslationAdapterError, match="extra"):
        adapter.finish_markdown_job(job, {"body:1": "Harga 4,436.46", "body:2": "extra"})
    candidate = adapter.finish_markdown_job(
        job, {"body:1": "Harga 4,436.46"},
        finisher=lambda _, __: {"content": "Harga 4,436.46", "warnings": []},
    )
    assert candidate["state"] == "PENDING_INDEPENDENT_REVIEW"
    assert candidate["receipt"] is None


def test_finish_rejects_changed_protected_literal():
    job = adapter.prepare_markdown_job(
        country_code="MY", document="ราคา 4,436.46", source_path="source.md",
        protected_literals=["4,436.46"], starter=_starter,
    )
    with pytest.raises(adapter.TranslationAdapterError, match="protected literal"):
        adapter.finish_markdown_job(job, {"body:1": "Harga 4,436.46"},
                                     finisher=lambda _, __: {"content": "Harga 4,436.40"})


def test_protected_numeric_token_does_not_match_a_larger_number():
    with pytest.raises(adapter.TranslationAdapterError, match="protected literal"):
        adapter.verify_protected_literals("Harga 1000", {"100": 1})


def test_finish_rejects_empty_mapping_values_and_identical_thai_source():
    job = adapter.prepare_markdown_job(
        country_code="MY", document="ราคา 4,436.46", source_path="source.md",
        protected_literals=["4,436.46"], starter=_starter,
    )
    with pytest.raises(adapter.TranslationAdapterError, match="string IDs"):
        adapter.finish_markdown_job(job, {"body:1": 42})
    with pytest.raises(adapter.TranslationAdapterError, match="identical"):
        adapter.finish_markdown_job(job, {"body:1": "ราคา 4,436.46"},
                                     finisher=lambda _, __: {"content": "ราคา 4,436.46"})


def test_th_and_unknown_country_cannot_create_translation_jobs():
    with pytest.raises(adapter.TranslationAdapterError, match="Thai source"):
        adapter.prepare_markdown_job(
            country_code="TH", document="ราคา 4,436.46", source_path="source.md",
            protected_literals=["4,436.46"], starter=_starter,
        )
    with pytest.raises(adapter.TranslationAdapterError, match="outside active rollout"):
        adapter.route_for("CN")


def test_production_requires_source_receipt_and_locked_pack(monkeypatch):
    class Pack:
        locale = "ms-MY"
        version = "0.1.2"
        sha256 = "a" * 64
        status = "stable_locked"
        is_locked = True

    monkeypatch.setattr(adapter, "load_locale", lambda _: Pack())
    with pytest.raises(adapter.TranslationAdapterError, match="source context"):
        adapter.prepare_markdown_job(
            country_code="MY", document="ราคา 4,436.46", source_path="source.md",
            protected_literals=["4,436.46"], mode="production", starter=_starter,
        )


def test_production_validates_binding_before_upstream_starter(monkeypatch, tmp_path):
    class Pack:
        locale = "ms-MY"
        version = "0.1.2"
        sha256 = "a" * 64
        status = "stable_locked"
        is_locked = True

    monkeypatch.setattr(adapter, "load_locale", lambda _: Pack())
    calls = []
    monkeypatch.setattr(adapter, "validate_source_acceptance", lambda *args, **kwargs: calls.append(args))
    text = "ราคา 4,436.46"
    job = adapter.prepare_markdown_job(
        country_code="MY", document=text, source_path="source.md", protected_literals=["4,436.46"],
        mode="production", starter=_starter,
        source_context={"article": {"source_path": "source.md", "source_sha256": __import__("hashlib").sha256(text.encode()).hexdigest()},
                        "receipt_path": tmp_path / "receipt.json", "bindings_dir": tmp_path,
                        "source_business_date": "2026-09-09", "project_root": tmp_path},
    )
    assert calls
    assert job["gates"]["source_qa"] == "VERIFIED"
    assert job["language_pack"]["version"] == "0.1.2"
