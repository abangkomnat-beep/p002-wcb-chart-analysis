"""Create an honest, resumable default-localization dispatch boundary.

This module intentionally does not translate, review, package, transact, or
admit.  It binds the current default queue to a frozen source manifest and
creates writer-owned work requests only for already admitted countries.  A
separate writer and independent reviewer execution must advance those jobs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from tools import localization_queue, localization_transaction, source_qa_acceptance, update_localized_outputs

SCHEMA = "p002-normal-localization-dispatch/v1"
BACKEND_VERSION = "0.20.1"
WRITER_HANDOFF_SCHEMA = "p002-localization-writer-handoff/v1"
REVIEWED_HANDOFF_SCHEMA = "p002-localization-reviewed-handoff/v1"


class DispatchError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DispatchError(f"cannot read {path}") from exc
    if not isinstance(data, dict):
        raise DispatchError("JSON document must be an object")
    return data


def _backend(project: Path) -> dict[str, str]:
    """Report the missing writer dependency without pretending to translate."""
    try:
        installed = importlib.metadata.version("co-op-translator")
    except importlib.metadata.PackageNotFoundError:
        runtimes = (project / "work" / "translation-env" / "Scripts" / "python.exe",
                    project.parent / "work" / "translation-env" / "Scripts" / "python.exe")
        runtime = next((path for path in runtimes if path.is_file()), None)
        if runtime is not None:
            return {"status": "AVAILABLE_IN_PROJECT_ENV", "reason": "invoke the verified project translation environment", "required_version": BACKEND_VERSION, "interpreter": str(runtime)}
        return {"status": "UNAVAILABLE", "reason": "co-op-translator is not installed", "required_version": BACKEND_VERSION}
    if installed != BACKEND_VERSION:
        return {"status": "UNAVAILABLE", "reason": f"co-op-translator version {installed} differs", "required_version": BACKEND_VERSION}
    return {"status": "AGENT_ASSISTED", "reason": "separate writer execution required", "required_version": BACKEND_VERSION, "interpreter": sys.executable}


def discover_source_bindings(project_root: Path, business_date: str) -> Path:
    """Resolve exactly one frozen binding, preferring a hash-bound workflow.

    A daily runner must never pick the newest revision by filename.  Existing
    workflow state is authoritative when it supplies a still-matching binding;
    without one, exactly one SOURCE_READY binding for the day is required.
    """
    project = Path(project_root).resolve()
    try:
        folder = date.fromisoformat(business_date).strftime("%d-%m-%Y")
    except ValueError as exc:
        raise DispatchError("business_date must be YYYY-MM-DD") from exc
    day_root = project / "work" / "localization" / folder
    workflow_paths = sorted((day_root / "workflows").glob("*/state.json")) if (day_root / "workflows").is_dir() else []
    workflow_candidates: set[Path] = set()
    for state_path in workflow_paths:
        state = _read(state_path)
        if state.get("schema") != "p002-localization-workflow/v1" or state.get("source_business_date") != business_date:
            continue
        stored, digest = state.get("source_bindings_path"), state.get("source_bindings_sha256")
        if not isinstance(stored, str) or not isinstance(digest, str):
            continue
        candidate = Path(stored).resolve()
        try:
            candidate.relative_to(project)
        except ValueError as exc:
            raise DispatchError("workflow source binding escapes project") from exc
        if not candidate.is_file() or _sha(candidate) != digest:
            raise DispatchError(f"workflow source binding is stale: {state_path}")
        workflow_candidates.add(candidate)
    if len(workflow_candidates) == 1:
        return next(iter(workflow_candidates))
    if len(workflow_candidates) > 1:
        raise DispatchError("ambiguous workflow source bindings; specify the authoritative workflow binding")

    candidates: list[Path] = []
    for candidate in sorted(day_root.glob("source-bindings*/source-bindings.json")):
        data = _read(candidate)
        if data.get("schema") == "p002-source-bindings/v2" and data.get("status") == "SOURCE_READY" and data.get("source_business_date") == business_date:
            candidates.append(candidate.resolve())
    if len(candidates) != 1:
        raise DispatchError("expected exactly one SOURCE_READY source binding when no workflow binding exists")
    return candidates[0]


def _relative_to(project: Path, path: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError as exc:
        raise DispatchError(f"{label} escapes project") from exc


def _recovered_article(*, project: Path, bindings_path: Path, bundle_path: Path,
                       article: dict[str, Any], business_date: str) -> dict[str, Any]:
    """Resolve only a manifest-declared, byte-for-byte recovery bundle."""
    bundle = _read(bundle_path)
    if bundle.get("schema") != "p002-source-recovery-bundle/v1":
        raise DispatchError("unsupported recovery bundle schema")
    if bundle.get("article_id") != article["article_id"] or bundle.get("source_business_date") != business_date:
        raise DispatchError("recovery bundle article/date differs from frozen binding")
    if bundle.get("binding_manifest_sha256") != _sha(bindings_path):
        raise DispatchError("recovery bundle binding manifest hash differs")
    targets = bundle.get("binding_target_paths")
    if not isinstance(targets, dict) or targets.get("article") != article["source_path"]:
        raise DispatchError("recovery bundle canonical article path differs")
    expected_image_paths = [item.get("path") for item in article.get("images") or []]
    if targets.get("images") != expected_image_paths:
        raise DispatchError("recovery bundle canonical image paths differ")
    files = bundle.get("files")
    if not isinstance(files, list):
        raise DispatchError("recovery bundle files are missing")
    base = bundle_path.parent.resolve()
    by_role: dict[str, list[dict[str, Any]]] = {}
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("role"), str):
            raise DispatchError("recovery bundle file entry is invalid")
        staged = item.get("staged_path")
        if not isinstance(staged, str) or not staged:
            raise DispatchError("recovery bundle staged path is missing")
        path = (base / staged).resolve()
        try:
            path.relative_to(base)
        except ValueError as exc:
            raise DispatchError("recovery bundle staged path escapes bundle") from exc
        if not path.is_file() or _sha(path) != item.get("sha256"):
            raise DispatchError(f"recovery bundle staged hash differs: {staged}")
        by_role.setdefault(item["role"], []).append({**item, "_path": path})
    article_files = by_role.get("article", [])
    if len(article_files) != 1 or article_files[0].get("sha256") != article["source_sha256"]:
        raise DispatchError("recovery bundle article hash differs from frozen binding")
    image_files = by_role.get("image", [])
    expected_hashes = [item.get("sha256") for item in article.get("images") or []]
    if len(image_files) != len(expected_hashes) or sorted(item.get("sha256") for item in image_files) != sorted(expected_hashes):
        raise DispatchError("recovery bundle image hashes differ from frozen binding")
    images_by_hash = {item["sha256"]: item for item in image_files}
    if len(images_by_hash) != len(image_files):
        raise DispatchError("recovery bundle duplicate image hashes are ambiguous")
    recovered = dict(article)
    recovered["source_path"] = _relative_to(project, article_files[0]["_path"], "recovery article")
    recovered["images"] = [{**image, "path": _relative_to(project, images_by_hash[image["sha256"]]["_path"], "recovery image")}
                           for image in article.get("images") or []]
    return recovered


def _frozen_sources(project: Path, business_date: str, bindings_path: Path,
                    recovery_bundle_path: Path | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        expected_date = date.fromisoformat(business_date).isoformat()
    except ValueError as exc:
        raise DispatchError("business_date must be YYYY-MM-DD") from exc
    bindings = _read(bindings_path)
    if bindings.get("schema") != "p002-source-bindings/v2" or bindings.get("status") != "SOURCE_READY":
        raise DispatchError("source bindings are not SOURCE_READY p002-source-bindings/v2")
    if bindings.get("source_business_date") != expected_date:
        raise DispatchError("source bindings date differs from dispatch date")
    articles = bindings.get("articles")
    if not isinstance(articles, list) or not articles:
        raise DispatchError("source bindings have no articles")
    recovery_article_id = None
    if recovery_bundle_path is not None:
        recovery_article_id = _read(Path(recovery_bundle_path)).get("article_id")
        if not isinstance(recovery_article_id, str) or recovery_article_id not in {item.get("article_id") for item in articles if isinstance(item, dict)}:
            raise DispatchError("recovery bundle article is not in frozen binding")
    jobs = []
    for article in articles:
        if not isinstance(article, dict):
            raise DispatchError("source article is invalid")
        required = ("article_id", "source_path", "source_sha256", "claim_map_path", "claim_map_sha256")
        if any(not isinstance(article.get(key), str) or not article[key] for key in required):
            raise DispatchError("source article lacks a required binding")
        resolved_article = (_recovered_article(project=project, bindings_path=bindings_path,
                                                bundle_path=Path(recovery_bundle_path).resolve(), article=article,
                                                business_date=business_date)
                            if recovery_bundle_path is not None and article["article_id"] == recovery_article_id
                            else article)
        source = (project / resolved_article["source_path"]).resolve()
        claims = (bindings_path.parent / article["claim_map_path"]).resolve()
        try:
            source.relative_to(project)
            claims.relative_to(bindings_path.parent.resolve())
        except ValueError as exc:
            raise DispatchError("source binding path escapes its root") from exc
        if not source.is_file() or _sha(source) != article["source_sha256"]:
            raise DispatchError(f"source hash differs for {article['article_id']}")
        if not claims.is_file() or _sha(claims) != article["claim_map_sha256"]:
            raise DispatchError(f"claim-map hash differs for {article['article_id']}")
        receipt = bindings_path.parent / "receipts" / f"{article['article_id']}.json"
        if not receipt.is_file():
            raise DispatchError(f"frozen source QA is not verified for {article['article_id']}: receipt is missing")
        try:
            source_qa_acceptance.validate_source_acceptance(
                receipt, resolved_article, source_business_date=business_date,
                bindings_dir=bindings_path.parent, project_root=project)
        except source_qa_acceptance.SourceAcceptanceError as exc:
            raise DispatchError(f"frozen source QA is not verified for {article['article_id']}: {exc}") from exc
        job = {key: article[key] for key in required}
        job["source_receipt_path"] = str(receipt)
        job["source_receipt_sha256"] = _sha(receipt)
        if resolved_article is not article:
            job["recovery_bundle_path"] = str(Path(recovery_bundle_path).resolve())
            job["resolved_source_path"] = resolved_article["source_path"]
        jobs.append(job)
    return bindings, jobs


def _inside(root: Path, value: str, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise DispatchError(f"{label} is required")
    path = (root / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise DispatchError(f"{label} escapes project") from exc
    return path


def _hashed_file(project: Path, value: str, digest: str, label: str) -> str:
    path = _inside(project, value, label)
    if not path.is_file() or not isinstance(digest, str) or _sha(path) != digest:
        raise DispatchError(f"{label} is missing or its hash differs")
    return value


def _installed_delivery_matches(project: Path, business_date: str, country: str, digest: str) -> bool:
    """Confirm the queue's admitted delivery is actually installed this day."""
    try:
        folder = date.fromisoformat(business_date).strftime("%d-%m-%Y")
    except ValueError:
        return False
    day_root = project / "output" / folder
    if not day_root.is_dir():
        return False
    for country_root in day_root.iterdir():
        manifest_path = country_root / "manifest.json"
        if not country_root.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = _read(manifest_path)
        except DispatchError:
            continue
        if (manifest.get("country_code") == country
                and _sha(manifest_path) == digest):
            return True
    return False


def _handoff_for(*, project: Path, handoff_root: Path, country: str, business_date: str) -> dict[str, Any] | None:
    path = (handoff_root / f"{country}.json").resolve()
    try:
        path.relative_to(handoff_root.resolve())
    except ValueError as exc:
        raise DispatchError("handoff path escapes root") from exc
    if not path.exists():
        return None
    handoff = _read(path)
    if handoff.get("country_code") != country or handoff.get("source_business_date") != business_date:
        raise DispatchError(f"handoff country/date differs for {country}")
    schema = handoff.get("schema")
    writer = handoff.get("writer_execution_id")
    if not isinstance(writer, str) or not writer:
        raise DispatchError(f"handoff writer execution is missing for {country}")
    if schema == WRITER_HANDOFF_SCHEMA:
        _hashed_file(project, handoff.get("candidate_manifest_path"), handoff.get("candidate_manifest_sha256"), "candidate manifest")
        return {"state": "WAITING_REVIEW", "handoff_path": str(path), "writer_execution_id": writer}
    if schema != REVIEWED_HANDOFF_SCHEMA:
        raise DispatchError(f"unsupported handoff schema for {country}")
    reviewer = handoff.get("reviewer_execution_id")
    if not isinstance(reviewer, str) or not reviewer or reviewer == writer:
        raise DispatchError(f"reviewer must be distinct from writer for {country}")
    if handoff.get("review_status") != "PASS":
        return {"state": "WAITING_REVIEW", "handoff_path": str(path), "writer_execution_id": writer,
                "reviewer_execution_id": reviewer, "reason": "REVIEW_NOT_PASS"}
    for path_key, hash_key, label in (
        ("manifest_path", "manifest_sha256", "localized manifest"),
        ("receipt_index_path", "receipt_index_sha256", "receipt index"),
        ("review_receipt_path", "review_receipt_sha256", "review receipt"),
    ):
        _hashed_file(project, handoff.get(path_key), handoff.get(hash_key), label)
    release_id = handoff.get("release_id")
    if not isinstance(release_id, str) or not release_id:
        raise DispatchError(f"release id is missing for {country}")
    return {"state": "READY_FOR_PACKAGE", "handoff_path": str(path), "writer_execution_id": writer,
            "reviewer_execution_id": reviewer, "manifest": handoff["manifest_path"],
            "receipt_index": handoff["receipt_index_path"], "release_id": release_id}


def build_dispatch(*, project_root: Path, business_date: str, index_path: Path,
                   bindings_path: Path, scope: tuple[str, ...] | list[str] | None = None,
                   policy_path: Path | None = None, handoff_root: Path | None = None,
                   recovery_bundle_path: Path | None = None) -> dict[str, Any]:
    project = Path(project_root).resolve()
    bindings_path = Path(bindings_path).resolve()
    bindings, source_articles = _frozen_sources(project, business_date, bindings_path,
                                                 recovery_bundle_path=recovery_bundle_path)
    queue = localization_queue.select(project_root=project, output_root=project / "output",
                                      business_date=business_date, index_path=Path(index_path),
                                      scope=scope, policy_path=policy_path)
    backend = _backend(project)
    effective_scope = tuple(scope) if scope is not None else tuple(
        item["country_code"] for item in queue.get("records", [])
    )
    handoffs = Path(handoff_root).resolve() if handoff_root else project / "work" / "localization" / date.fromisoformat(business_date).strftime("%d-%m-%Y") / "normal-handoffs"
    jobs = []
    for country in queue["selected"]:
        queue_record = next((item for item in queue.get("records", [])
                             if item.get("country_code") == country and item.get("selected")), None)
        # A country already verified by the admission queue for this delivery
        # date must not be sent back to a writer.  This is the resume/idempotent
        # path: the default runner reports the existing delivery and leaves its
        # bytes untouched.
        if (queue_record and isinstance(queue_record.get("delivery_manifest_sha256"), str)
                and _installed_delivery_matches(project, business_date, country,
                                                 queue_record["delivery_manifest_sha256"])):
            jobs.append({"country_code": country, "state": "ALREADY_DELIVERED",
                         "delivery_manifest_sha256": queue_record["delivery_manifest_sha256"],
                         "admission_path": queue_record.get("admission_path")})
            continue
        try:
            handoff = _handoff_for(project=project, handoff_root=handoffs, country=country, business_date=business_date)
        except DispatchError as exc:
            jobs.append({"country_code": country, "state": "HOLD_HANDOFF", "reason": str(exc)})
            continue
        if handoff is not None:
            jobs.append({"country_code": country, **handoff})
            continue
        for article in source_articles:
            job = {
                "country_code": country,
                "article_id": article["article_id"],
                "state": "WAITING_WRITER",
                "source_path": article["source_path"],
                "source_sha256": article["source_sha256"],
                "claim_map_path": article["claim_map_path"],
                "claim_map_sha256": article["claim_map_sha256"],
                "source_receipt_path": article["source_receipt_path"],
                "source_receipt_sha256": article["source_receipt_sha256"],
                "next_required_execution": "writer-distinct-from-independent-reviewer",
            }
            if "recovery_bundle_path" in article:
                job["recovery_bundle_path"] = article["recovery_bundle_path"]
                job["resolved_source_path"] = article["resolved_source_path"]
            jobs.append(job)
    identity = {
        "business_date": business_date, "scope": list(effective_scope), "queue_index_sha256": queue["index_sha256"],
        "source_bindings_sha256": _sha(bindings_path), "source_article_count": len(source_articles),
        "selected": queue["selected"], "held": queue["held"], "jobs": jobs,
    }
    states = {job["state"] for job in jobs}
    status = "HOLD_NO_ADMITTED_COUNTRIES" if not jobs else (
        "PARTIAL_HELD" if queue["held"] else
        "ALREADY_DELIVERED" if states == {"ALREADY_DELIVERED"} else
        "PARTIAL_HOLD_HANDOFF" if "HOLD_HANDOFF" in states else
        "READY_FOR_PACKAGE" if states == {"READY_FOR_PACKAGE"} else
        "WAITING_WRITER_OR_REVIEW")
    return {
        "schema": SCHEMA,
        "status": status,
        "business_date": business_date,
        "scope": list(effective_scope),
        "dispatch_identity_sha256": hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "source_bindings_path": str(bindings_path),
        "source_bindings_sha256": _sha(bindings_path),
        "queue": {"selected": queue["selected"], "held": queue["held"], "index_sha256": queue["index_sha256"]},
        "writer_backend": backend,
        "handoff_root": str(handoffs),
        "jobs": jobs,
        "admission_note": "Admission enrolls a country for dispatch; it is not proof of this date's delivery.",
        "resume_note": "Reuse this dispatch only when its immutable bytes and dispatch identity match; writer/reviewer/package/transaction/admission remain separate gates.",
    }


def write_dispatch(*, project_root: Path, work_root: Path, business_date: str, index_path: Path,
                   bindings_path: Path, scope: tuple[str, ...] | list[str] | None = None,
                   policy_path: Path | None = None, handoff_root: Path | None = None,
                   recovery_bundle_path: Path | None = None) -> dict[str, Any]:
    result = build_dispatch(project_root=project_root, business_date=business_date, index_path=index_path,
                            bindings_path=bindings_path, scope=scope, policy_path=policy_path, handoff_root=handoff_root,
                            recovery_bundle_path=recovery_bundle_path)
    dispatch_id = result["dispatch_identity_sha256"][:16]
    target = Path(work_root) / "localization" / date.fromisoformat(business_date).strftime("%d-%m-%Y") / "normal-dispatch" / f"dispatch-{dispatch_id}.json"
    data = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    resumed = target.exists()
    if resumed and target.read_bytes() != data:
        raise DispatchError("dispatch already exists with different immutable inputs")
    if not resumed:
        target.write_bytes(data)
    return {**result, "receipt_path": str(target), "resumed": resumed}


def run(project_root: Path, business_date: str, dry_run: bool = False,
        recovery_bundle_path: Path | None = None) -> dict[str, Any]:
    """Integration API for one daily invocation after Thai source production.

    It discovers an unambiguous frozen source binding and only creates or
    resumes an agent dispatch.  It never translates autonomously or treats a
    previous journal as admission.
    """
    project = Path(project_root).resolve()
    bindings = discover_source_bindings(project, business_date)
    common = {"project_root": project, "business_date": business_date,
              "index_path": project / "work" / "localization" / "admission-index.json",
              "bindings_path": bindings,
              "policy_path": localization_queue.default_policy_path(project)}
    if dry_run:
        return {**build_dispatch(**common, recovery_bundle_path=recovery_bundle_path), "dry_run": True}
    return write_dispatch(**common, work_root=project / "work", recovery_bundle_path=recovery_bundle_path)


def prepare_verified(*, project_root: Path, dispatch: dict[str, Any], transaction_id: str) -> dict[str, Any]:
    """Delegate only independently reviewed handoffs to the existing package/transaction contract."""
    if dispatch.get("schema") != SCHEMA:
        raise DispatchError("unsupported dispatch schema")
    jobs = [{key: job[key] for key in ("manifest", "receipt_index", "release_id")}
            for job in dispatch.get("jobs", []) if job.get("state") == "READY_FOR_PACKAGE"]
    if not jobs:
        raise DispatchError("no independently reviewed handoff is ready for package")
    return update_localized_outputs.prepare_countries_for_delivery(Path(project_root), dispatch["business_date"], transaction_id, jobs)


def apply_verified(*, project_root: Path, business_date: str, transaction_id: str) -> dict[str, Any]:
    """Apply a previously prepared transaction; admission remains a separate CC action."""
    return localization_transaction.apply_transaction(Path(project_root), business_date, transaction_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--work-root", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--admission-index", required=True)
    parser.add_argument("--source-bindings", required=True)
    parser.add_argument("--policy")
    parser.add_argument("--handoff-root")
    parser.add_argument("--recovery-bundle", help="explicit hash-bound work recovery bundle; default is disabled")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare-verified", action="store_true")
    modes.add_argument("--apply-transaction", action="store_true")
    parser.add_argument("--transaction-id")
    args = parser.parse_args(argv)
    try:
        if args.apply_transaction:
            if not args.transaction_id:
                raise DispatchError("--transaction-id is required for --apply-transaction")
            result = apply_verified(project_root=Path(args.project_root), business_date=args.date, transaction_id=args.transaction_id)
        else:
            result = write_dispatch(project_root=Path(args.project_root), work_root=Path(args.work_root),
                                    business_date=args.date, index_path=Path(args.admission_index),
                                    bindings_path=Path(args.source_bindings), policy_path=Path(args.policy) if args.policy else None,
                                    handoff_root=Path(args.handoff_root) if args.handoff_root else None,
                                    recovery_bundle_path=Path(args.recovery_bundle) if args.recovery_bundle else None)
            if args.prepare_verified:
                if not args.transaction_id:
                    raise DispatchError("--transaction-id is required for --prepare-verified")
                result["prepared_transaction"] = prepare_verified(project_root=Path(args.project_root), dispatch=result,
                                                                     transaction_id=args.transaction_id)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") in {"READY_FOR_PACKAGE", "WAITING_WRITER_OR_REVIEW", "PARTIAL_HOLD_HANDOFF"} or result.get("status") == "PREPARED" else 2
    except (DispatchError, localization_queue.QueueError) as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
