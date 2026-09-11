import json
import hashlib

import pytest

from tools.translation_job_store import TranslationJobStoreError, write_prepared_job


def _job(value="a"):
    identity = {"value": value}
    return {"source": {"sha256": value * 64},
            "cache_identity": identity,
            "cache_key": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
            "state": "PREPARED"}


def test_store_is_idempotent_for_same_source_and_revisions_changed_source(tmp_path):
    first = write_prepared_job(tmp_path, "09-09-2026", "MY", "E-XAUUSD", _job("a"))
    assert first.name == "E-XAUUSD-r0001.json"
    assert write_prepared_job(tmp_path, "09-09-2026", "MY", "E-XAUUSD", _job("a")) == first
    second = write_prepared_job(tmp_path, "09-09-2026", "MY", "E-XAUUSD", _job("b"))
    assert second.name == "E-XAUUSD-r0002.json"
    assert json.loads(second.read_text(encoding="utf-8"))["state"] == "PREPARED"
    assert not (tmp_path / "output").exists()


def test_store_rejects_path_escape_and_missing_source_hash(tmp_path):
    with pytest.raises(TranslationJobStoreError):
        write_prepared_job(tmp_path, "../../outside", "MY", "E-XAUUSD", _job())
    with pytest.raises(TranslationJobStoreError):
        write_prepared_job(tmp_path, "09-09-2026", "MY", "../outside", _job())
    with pytest.raises(TranslationJobStoreError, match="SHA256"):
        write_prepared_job(tmp_path, "09-09-2026", "MY", "E-XAUUSD", {"source": {}})


def test_store_uses_cache_key_not_source_hash_for_reuse(tmp_path):
    first = _job("a")
    second = _job("a")
    second["cache_identity"] = {"value": "b"}
    second["cache_key"] = hashlib.sha256(json.dumps(second["cache_identity"], sort_keys=True).encode()).hexdigest()
    assert write_prepared_job(tmp_path, "09-09-2026", "MY", "E-XAUUSD", first).name.endswith("r0001.json")
    assert write_prepared_job(tmp_path, "09-09-2026", "MY", "E-XAUUSD", second).name.endswith("r0002.json")


def test_store_rejects_caller_supplied_cache_key_that_does_not_match_identity(tmp_path):
    job = _job()
    job["cache_key"] = "b" * 64
    with pytest.raises(TranslationJobStoreError, match="does not match"):
        write_prepared_job(tmp_path, "09-09-2026", "MY", "E-XAUUSD", job)
