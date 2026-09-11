"""P002-owned adapter for Co-op Translator's provider-free Markdown jobs.

The upstream library only splits and reconstructs Markdown.  P002 owns the
country routing, source identity, protected values, job journal and every
quality/admission gate.  This module deliberately has no provider-backed
translation entry point.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from tools.active_rollout import ACTIVE_COUNTRIES, country_record
from tools.locale_loader import load_locale
from tools.source_qa_acceptance import validate_source_acceptance

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTING_PATH = REPO_ROOT / "config" / "translation-engine-routing.json"
ADAPTER_SCHEMA = "p002-agent-translation-job/v1"


class TranslationAdapterError(ValueError):
    """Raised before a translation job can leave P002 control."""


def _read_routing(path: Path = ROUTING_PATH) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TranslationAdapterError(f"cannot read translation routing: {path}") from exc
    if data.get("schema") != "p002-translation-engine-routing/v1":
        raise TranslationAdapterError("unsupported translation routing schema")
    routes = data.get("routes")
    if not isinstance(routes, dict) or tuple(routes) != ACTIVE_COUNTRIES:
        raise TranslationAdapterError("translation routes must match the exact active 20-country rollout")
    upstream = data.get("upstream") or {}
    if upstream.get("mode") != "agent-assisted" or upstream.get("provider_calls_allowed") is not False:
        raise TranslationAdapterError("only provider-free agent-assisted translation is allowed")
    return data


def route_for(country_code: str, path: Path = ROUTING_PATH) -> dict[str, Any]:
    """Return a country route with its P002 locale and direction verified."""
    data = _read_routing(path)
    if country_code not in ACTIVE_COUNTRIES:
        raise TranslationAdapterError(f"country is outside active rollout: {country_code}")
    route = dict(data["routes"][country_code])
    record = country_record(country_code)
    required = route.get("translation_required")
    language = route.get("engine_language")
    if country_code == "TH":
        if required or language is not None:
            raise TranslationAdapterError("TH must remain the untranslated source route")
    elif required is not True or not isinstance(language, str) or not language:
        raise TranslationAdapterError(f"missing engine language for {country_code}")
    return {
        "country_code": country_code,
        "content_locale": record["content_locale"],
        "language_pack": record["language_pack"],
        "direction": record["direction"],
        "engine_language": language,
        "translation_required": required,
    }


def _default_starter(document: str, language: str, source_path: str) -> dict[str, Any]:
    expected = _read_routing()["upstream"]["version"]
    try:
        installed = importlib.metadata.version("co-op-translator")
    except importlib.metadata.PackageNotFoundError as exc:
        raise TranslationAdapterError("Co-op Translator runtime is unavailable.") from exc
    if installed != expected:
        raise TranslationAdapterError(f"Co-op Translator version drift: expected {expected}, got {installed}")
    try:
        from co_op_translator.api import start_markdown_agent_translation
    except (ImportError, ModuleNotFoundError) as exc:
        raise TranslationAdapterError(
            "Co-op Translator runtime is unavailable. Use P002 work/translation-env and install its locked dependencies."
        ) from exc
    return start_markdown_agent_translation(document, language, source_path=source_path)


def _default_finisher(job: Mapping[str, Any], translated_chunks: Any) -> dict[str, Any]:
    try:
        from co_op_translator.api import finish_markdown_agent_translation
    except (ImportError, ModuleNotFoundError) as exc:
        raise TranslationAdapterError("Co-op Translator runtime is unavailable.") from exc
    return finish_markdown_agent_translation(job, translated_chunks)


def _translation_ids(translated_chunks: Any) -> dict[str, str]:
    if isinstance(translated_chunks, Mapping):
        if any(not isinstance(key, str) or not isinstance(value, str) or not value.strip()
               for key, value in translated_chunks.items()):
            raise TranslationAdapterError("translated chunk mapping requires non-empty string IDs and text")
        return dict(translated_chunks)
    if not isinstance(translated_chunks, list):
        raise TranslationAdapterError("translated chunks must be a mapping or list")
    result: dict[str, str] = {}
    for item in translated_chunks:
        if not isinstance(item, Mapping):
            raise TranslationAdapterError("translated chunk must be an object")
        chunk_id = item.get("chunk_id", item.get("id"))
        text = next((item[key] for key in ("translated_text", "translation", "content", "text") if key in item), None)
        if not isinstance(chunk_id, str) or not isinstance(text, str) or not text.strip():
            raise TranslationAdapterError("translated chunk requires non-empty id and text")
        if chunk_id in result:
            raise TranslationAdapterError("duplicate translated chunk id")
        result[chunk_id] = text
    return result


def prepare_markdown_job(
    *,
    country_code: str,
    document: str,
    source_path: str,
    protected_literals: list[str],
    mode: str = "calibration",
    source_context: Mapping[str, Any] | None = None,
    starter: Callable[[str, str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Make a resumable, provider-free translation job.

    The returned object is only a candidate.  It has no QC receipt and cannot
    be packaged as Output.  Protected literals are recorded before handing the
    Markdown chunks to a host agent, then verified after reconstruction.
    """
    if mode not in {"calibration", "production"}:
        raise TranslationAdapterError("translation mode must be calibration or production")
    route = route_for(country_code)
    if not route["translation_required"]:
        raise TranslationAdapterError("the Thai source route does not create a translation job")
    if not document.strip():
        raise TranslationAdapterError("source document is empty")
    normalized_literals = sorted({str(value) for value in protected_literals if str(value)})
    missing = [value for value in normalized_literals if value not in document]
    if missing:
        raise TranslationAdapterError("protected literal is absent from source: " + ", ".join(missing))
    pack = load_locale(route["language_pack"])
    source = {"path": source_path, "sha256": hashlib.sha256(document.encode("utf-8")).hexdigest(),
              "locale": "th-TH"}
    source_qa = "NOT_REQUIRED_FOR_CALIBRATION"
    if mode == "production":
        if not pack.is_locked:
            raise TranslationAdapterError(f"production requires a locked language pack: {route['language_pack']}")
        context = dict(source_context or {})
        required_context = ("article", "receipt_path", "bindings_dir", "source_business_date")
        absent = [key for key in required_context if key not in context]
        if absent:
            raise TranslationAdapterError("production source context missing: " + ", ".join(absent))
        article = context["article"]
        if article.get("source_path") != source_path or article.get("source_sha256") != source["sha256"]:
            raise TranslationAdapterError("production source does not match its frozen binding")
        validate_source_acceptance(
            Path(context["receipt_path"]), article,
            source_business_date=str(context["source_business_date"]),
            bindings_dir=Path(context["bindings_dir"]),
            project_root=Path(context.get("project_root", REPO_ROOT.parent)),
        )
        source_qa = "VERIFIED"
    upstream_job = (starter or _default_starter)(document, route["engine_language"], source_path)
    if not isinstance(upstream_job, dict) or not isinstance(upstream_job.get("chunks"), list):
        raise TranslationAdapterError("Co-op Translator returned an invalid agent job")
    cache_identity = {
        "source_sha256": source["sha256"], "route": route,
        "pack": {"locale": pack.locale, "version": pack.version, "sha256": pack.sha256},
        "upstream_version": _read_routing()["upstream"]["version"],
        "adapter_version": _read_routing().get("adapter_version"), "mode": mode,
        "source_binding": {key: (source_context or {}).get("article", {}).get(key)
                           for key in ("source_images_sha256", "claim_map_sha256")},
        "protected_literals": normalized_literals,
    }
    return {
        "schema": ADAPTER_SCHEMA,
        "state": "PREPARED",
        "mode": mode,
        "route": route,
        "source": source,
        "source_document": document,
        "cache_key": hashlib.sha256(json.dumps(cache_identity, sort_keys=True).encode("utf-8")).hexdigest(),
        "cache_identity": cache_identity,
        "language_pack": {"locale": pack.locale, "version": pack.version,
                          "sha256": pack.sha256, "status": pack.status},
        "protected_literals": normalized_literals,
        "protected_literal_counts": {value: _literal_count(document, value)
                                     for value in normalized_literals},
        "upstream": {
            "distribution": "co-op-translator",
            "version": _read_routing()["upstream"]["version"],
            "mode": "agent-assisted",
            "job": upstream_job,
        },
        "gates": {
            "source_qa": source_qa,
            "language_pack": "VERIFIED" if pack.is_locked else "DRAFT_CALIBRATION_ONLY",
            "translation": "PENDING",
            "independent_review": "PENDING",
            "qc": "PENDING",
            "admission": "PENDING",
        },
    }


def _literal_count(document: str, literal: str) -> int:
    """Count protected tokens while allowing ordinary prose punctuation.

    A date/price token cannot be a substring of another number.  Punctuation
    immediately after a token is allowed (``2026, update``), except when it
    continues a decimal/grouped number (``2026.5`` or ``1,2026``).
    """
    if not any(char.isdigit() for char in literal):
        pattern = rf"(?<!\w){re.escape(literal)}(?!\w)"
        return len(re.findall(pattern, document))
    count = 0
    for match in re.finditer(re.escape(literal), document):
        start, end = match.span()
        before, after = document[start - 1:start], document[end:end + 1]
        if before and before.isdigit() or after and after.isdigit():
            continue
        # A separator adjacent to a digit is part of a surrounding numeric
        # literal, while a separator followed by prose is just punctuation.
        if before in {".", ","} and start >= 2 and document[start - 2].isdigit():
            continue
        if after in {".", ","} and end + 1 < len(document) and document[end + 1].isdigit():
            continue
        count += 1
    return count


def verify_protected_literals(translated_document: str, protected_literals: Mapping[str, int] | list[str]) -> None:
    """Fail closed when a translated candidate changes any protected value."""
    expected = dict(protected_literals) if isinstance(protected_literals, Mapping) else {
        value: 1 for value in protected_literals
    }
    changed = [value for value, count in expected.items()
               if _literal_count(translated_document, value) != count]
    if changed:
        raise TranslationAdapterError("translated document changed protected literal: " + ", ".join(changed))


def finish_markdown_job(
    job: Mapping[str, Any],
    translated_chunks: Mapping[str, Any] | list[Mapping[str, Any]],
    *,
    finisher: Callable[[Mapping[str, Any], Any], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Reconstruct a candidate only when every expected chunk is present once."""
    if job.get("schema") != ADAPTER_SCHEMA or job.get("state") != "PREPARED":
        raise TranslationAdapterError("job is not a prepared P002 translation job")
    upstream = job.get("upstream") or {}
    upstream_job = upstream.get("job")
    if not isinstance(upstream_job, Mapping):
        raise TranslationAdapterError("job has no upstream translation payload")
    expected = [str(chunk.get("id")) for chunk in upstream_job.get("chunks", [])]
    if not expected or len(expected) != len(set(expected)):
        raise TranslationAdapterError("upstream job has invalid chunk IDs")
    supplied = _translation_ids(translated_chunks)
    missing = [chunk_id for chunk_id in expected if chunk_id not in supplied]
    extra = sorted(set(supplied) - set(expected))
    if missing or extra:
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if extra:
            detail.append("extra=" + ",".join(extra))
        raise TranslationAdapterError("translated chunk set mismatch: " + " ".join(detail))
    result = (finisher or _default_finisher)(upstream_job, translated_chunks)
    content = result.get("content") if isinstance(result, Mapping) else None
    if not isinstance(content, str) or not content.strip():
        raise TranslationAdapterError("Co-op Translator returned empty reconstructed content")
    if content == job.get("source_document"):
        raise TranslationAdapterError("translated candidate is identical to the Thai source")
    verify_protected_literals(content, job.get("protected_literal_counts") or job["protected_literals"])
    return {
        "schema": "p002-translated-candidate/v1",
        "state": "PENDING_INDEPENDENT_REVIEW",
        "source_sha256": job["source"]["sha256"],
        "target_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "content": content,
        "chunk_ids": expected,
        "findings": list(result.get("warnings") or []),
        "receipt": None,
    }
