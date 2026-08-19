"""Strict, explainable calendar relevance gate for Style D.

The live calendar feed is broad by design.  This module is the only place that may
decide whether an economic event belongs in a Style D article.  Matching is
fail-closed: a reviewed source id wins, an exact normalized English alias is the
only fallback, and unknown events are excluded rather than guessed from keywords.
"""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "config" / "style_d_calendar_relevance.json"
EXPECTED_SCHEMA = "style-d-calendar-relevance-v1"
EXPECTED_ASSETS = {
    "xauusd", "eurusd", "gbpusd", "btcusd",
    "nvda", "usdthb", "solusd", "wtiusd",
}


class StyleDCalendarUnavailable(RuntimeError):
    """A dependency or contract failed; Style D must fail closed."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


def normalize_alias(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(text.split())


def canonical_sha256(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def week_bounds(local_date: str) -> tuple[str, str]:
    current = date.fromisoformat(local_date)
    monday = current - timedelta(days=current.weekday())
    return monday.isoformat(), (monday + timedelta(days=4)).isoformat()


def load_registry(path: Path | None = None) -> dict:
    source = path or DEFAULT_REGISTRY_PATH
    try:
        registry = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StyleDCalendarUnavailable(
            "calendar_registry_unusable", f"อ่านทะเบียนปฏิทิน Style D ไม่ได้: {exc}") from None
    validate_registry(registry)
    registry = dict(registry)
    registry["_path"] = str(source)
    registry["_sha256"] = canonical_sha256(
        {key: value for key, value in registry.items() if not key.startswith("_")})
    return registry


def validate_registry(registry: dict) -> None:
    if registry.get("schema") != EXPECTED_SCHEMA:
        raise StyleDCalendarUnavailable(
            "calendar_registry_unusable", "schema ของทะเบียนปฏิทิน Style D ไม่ถูกต้อง")
    assets = set(registry.get("assets") or [])
    if assets != EXPECTED_ASSETS:
        missing = sorted(EXPECTED_ASSETS - assets)
        extra = sorted(assets - EXPECTED_ASSETS)
        raise StyleDCalendarUnavailable(
            "calendar_registry_asset_missing",
            f"ทะเบียนสินทรัพย์ไม่ครบ/เกิน: missing={missing}, extra={extra}")
    allowed_impacts = set((registry.get("matching") or {}).get("allowed_impacts") or [])
    if allowed_impacts != {"High", "Medium"}:
        raise StyleDCalendarUnavailable(
            "calendar_registry_unusable", "allowed_impacts ต้องเป็น High และ Medium")
    if (registry.get("matching") or {}).get("single_page") is not True:
        raise StyleDCalendarUnavailable(
            "calendar_registry_unusable", "Style D calendar ต้องใช้ภาพตารางหน้าเดียว")

    family_ids: set[str] = set()
    source_ids: dict[str, str] = {}
    aliases: dict[tuple[str, str], str] = {}
    for family in registry.get("families") or []:
        family_id = str(family.get("id") or "").strip()
        country = str(family.get("country") or "").strip().upper()
        if not family_id or family_id in family_ids or not country:
            raise StyleDCalendarUnavailable(
                "calendar_registry_unusable", f"family ซ้ำหรือข้อมูลไม่ครบ: {family_id!r}")
        family_ids.add(family_id)
        family_assets = family.get("assets") or {}
        if not family_assets or not set(family_assets).issubset(EXPECTED_ASSETS):
            raise StyleDCalendarUnavailable(
                "calendar_registry_unusable", f"asset mapping ของ {family_id} ไม่ถูกต้อง")
        for asset, rule in family_assets.items():
            if (not isinstance(rule, list) or len(rule) != 2
                    or rule[0] not in ("direct", "indirect") or not str(rule[1]).strip()):
                raise StyleDCalendarUnavailable(
                    "calendar_registry_unusable", f"relevance rule ของ {family_id}/{asset} ไม่ถูกต้อง")
        ids = [str(value).strip() for value in family.get("source_ids") or [] if str(value).strip()]
        title_aliases = [normalize_alias(value) for value in family.get("title_en_exact") or []
                         if normalize_alias(value)]
        if not ids and not title_aliases:
            raise StyleDCalendarUnavailable(
                "calendar_registry_unusable", f"family {family_id} ไม่มี match key")
        for source_id in ids:
            if source_id in source_ids:
                raise StyleDCalendarUnavailable(
                    "calendar_registry_unusable",
                    f"source id {source_id} ซ้ำใน {source_ids[source_id]} และ {family_id}")
            source_ids[source_id] = family_id
        for alias in title_aliases:
            key = (country, alias)
            if key in aliases:
                raise StyleDCalendarUnavailable(
                    "calendar_registry_unusable",
                    f"alias {country}/{alias} ซ้ำใน {aliases[key]} และ {family_id}")
            aliases[key] = family_id

    if not isinstance(registry.get("direction_rules"), dict):
        raise StyleDCalendarUnavailable(
            "calendar_registry_unusable", "direction_rules ต้องเป็น object")
    for asset, rules in registry["direction_rules"].items():
        if asset not in EXPECTED_ASSETS or not isinstance(rules, dict):
            raise StyleDCalendarUnavailable(
                "calendar_registry_unusable", f"direction rules ของ {asset} ไม่ถูกต้อง")
        for family_id, rule in rules.items():
            if family_id not in family_ids or rule not in ("higher_positive", "higher_negative"):
                raise StyleDCalendarUnavailable(
                    "calendar_registry_unusable",
                    f"direction rule ของ {asset}/{family_id} ไม่ถูกต้อง")


def _indexes(registry: dict) -> tuple[dict[str, dict], dict[tuple[str, str], dict]]:
    by_source: dict[str, dict] = {}
    by_alias: dict[tuple[str, str], dict] = {}
    for family in registry["families"]:
        for source_id in family.get("source_ids") or []:
            by_source[str(source_id)] = family
        for alias in family.get("title_en_exact") or []:
            by_alias[(str(family["country"]).upper(), normalize_alias(alias))] = family
    return by_source, by_alias


def classify_event(event: dict, asset: str, registry: dict) -> dict:
    """Return an auditable include/exclude decision for one normalized feed event."""
    decision = {
        "source_id": str(event.get("source_id") or ""),
        "at": event.get("at"),
        "country": str(event.get("country") or "").upper(),
        "impact": str(event.get("impact") or ""),
        "title_en": event.get("title_en"),
        "title_th": event.get("title_th") or event.get("title"),
        "family_id": None,
        "decision": "excluded",
        "reason_code": "unknown_family",
        "relevance": None,
        "mechanism_th": None,
        "direction": "undetermined",
        "direction_basis": None,
        "matched_by": None,
    }
    if decision["impact"].title() not in set(registry["matching"]["allowed_impacts"]):
        decision["reason_code"] = "outside_impact"
        return decision

    by_source, by_alias = _indexes(registry)
    family = by_source.get(decision["source_id"])
    if family is not None:
        decision["matched_by"] = "source_id"
    else:
        family = by_alias.get((decision["country"], normalize_alias(decision["title_en"])))
        if family is not None:
            decision["matched_by"] = "title_en_exact"
    if family is None:
        return decision

    decision["family_id"] = family["id"]
    asset_rule = (family.get("assets") or {}).get(asset)
    if asset_rule is None:
        decision["reason_code"] = "asset_not_allowed"
        return decision
    decision.update({
        "decision": "included",
        "reason_code": "included",
        "relevance": asset_rule[0],
        "mechanism_th": asset_rule[1],
    })
    return decision


def _number(value: object) -> float | None:
    if value in (None, "", "—"):
        return None
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", str(value))
    return float(match.group(0).replace(",", "")) if match else None


def direction_for_event(event: dict, *, family_id: str, asset: str,
                        registry: dict) -> tuple[str, str | None]:
    """ประเมินทิศเฉพาะ actual-vs-forecast และกฎที่ทบทวนแล้วใน registry."""
    rule = ((registry.get("direction_rules") or {}).get(asset) or {}).get(family_id)
    actual = _number(event.get("actual"))
    forecast = _number(event.get("forecast"))
    if not rule or actual is None or forecast is None or actual == forecast:
        return "undetermined", None
    actual_higher = actual > forecast
    positive_when_higher = rule == "higher_positive"
    positive = actual_higher if positive_when_higher else not actual_higher
    return ("positive" if positive else "negative",
            f"actual_vs_forecast:{actual:g}:{forecast:g}:{rule}")


def _row_units(event: dict, wrap_columns: int) -> int:
    title = str(event.get("title") or event.get("title_th") or event.get("title_en") or "")
    wrapped = textwrap.wrap(title, width=wrap_columns,
                            break_long_words=True, break_on_hyphens=False)
    return max(1, len(wrapped))


def paginate_events(events: list[dict], *, capacity: int, wrap_columns: int) -> list[list[dict]]:
    """Greedy pagination without truncating, dropping, or splitting an event row."""
    if not events:
        return [[]]
    pages: list[list[dict]] = []
    page: list[dict] = []
    used = 0
    for event in events:
        units = _row_units(event, wrap_columns)
        if page and used + units > capacity:
            pages.append(page)
            page, used = [], 0
        annotated = dict(event)
        annotated["row_units"] = units
        page.append(annotated)
        used += units
    if page:
        pages.append(page)
    return pages


def build_calendar(raw_payload: dict, normalized_events: list[dict], *,
                   asset: str, local_date: str, registry_path: Path | None = None) -> tuple[dict, dict]:
    """Filter the exact Monday-Friday feed and return calendar payload + evidence."""
    if not isinstance(raw_payload, dict) or not isinstance(raw_payload.get("events"), list):
        raise StyleDCalendarUnavailable("calendar_payload_invalid", "calendar feed ไม่มี events list")
    if not isinstance(normalized_events, list):
        raise StyleDCalendarUnavailable("calendar_payload_invalid", "แปลง events จาก feed ไม่สำเร็จ")
    if asset not in EXPECTED_ASSETS:
        raise StyleDCalendarUnavailable("calendar_registry_asset_missing", f"ไม่รู้จัก asset {asset}")
    registry = load_registry(registry_path)
    start, end = week_bounds(local_date)

    decisions: list[dict] = []
    included: list[dict] = []
    seen_source_ids: set[str] = set()
    for event in normalized_events:
        event_day = str(event.get("at") or "")[:10]
        if not (start <= event_day <= end):
            continue
        decision = classify_event(event, asset, registry)
        source_id = str(event.get("source_id") or "")
        if decision["decision"] == "included" and source_id and source_id in seen_source_ids:
            decision["decision"] = "excluded"
            decision["reason_code"] = "duplicate_source_id"
        if decision["decision"] == "included":
            direction, direction_basis = direction_for_event(
                event, family_id=str(decision["family_id"]), asset=asset,
                registry=registry)
            decision["direction"] = direction
            decision["direction_basis"] = direction_basis
            if source_id:
                seen_source_ids.add(source_id)
            selected = dict(event)
            selected.update({key: decision[key] for key in (
                "family_id", "relevance", "mechanism_th", "direction",
                "direction_basis", "matched_by")})
            included.append(selected)
        decisions.append(decision)

    included.sort(key=lambda item: (
        str(item.get("at") or ""), str(item.get("country") or ""),
        str(item.get("family_id") or ""), str(item.get("source_id") or "")))
    matching = registry["matching"]
    capacity = int(matching["page_row_units"])
    if matching.get("single_page"):
        # ผู้ใช้เลือกตารางเต็มภาพหน้าเดียว: ขยาย capacity ตามข้อมูลจริง ไม่ตัดข่าว
        # และไม่ลดจำนวนแถวเพื่อรักษาสัญญา relevance feed เดิม.
        capacity = max(1, sum(
            _row_units(event, int(matching["title_wrap_columns"])) for event in included))
    pages = paginate_events(
        included, capacity=capacity,
        wrap_columns=int(matching["title_wrap_columns"]))
    page_records = []
    for index, page in enumerate(pages, start=1):
        page_records.append({
            "page": index,
            "source_ids": [str(item.get("source_id") or "") for item in page],
            "row_units": sum(int(item.get("row_units") or 1) for item in page),
        })

    evidence = {
        "schema": "style-d-calendar-evidence-v1",
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "asset": asset,
        "local_date": local_date,
        "week_start": start,
        "week_end": end,
        "feed": {
            "endpoint": "calendar_feed",
            "retrieved_at": raw_payload.get("retrieved_at"),
            "sha256": canonical_sha256(raw_payload),
        },
        "registry": {
            "schema": registry["schema"], "version": registry["version"],
            "path": registry["_path"], "sha256": registry["_sha256"],
        },
        "counts": {
            "raw": len(raw_payload.get("events") or []),
            "in_week": len(decisions),
            "impact_eligible": sum(
                1 for item in decisions if item["reason_code"] != "outside_impact"),
            "included": len(included),
            "excluded": sum(1 for item in decisions if item["decision"] == "excluded"),
            "deduplicated": sum(
                1 for item in decisions if item["reason_code"] == "duplicate_source_id"),
            "pages": len(pages),
        },
        "decisions": decisions,
        "pages": page_records,
    }
    calendar = {
        "events": included,
        "week_start": start,
        "week_end": end,
        "countries": sorted({str(item.get("country") or "") for item in included}),
        "sentences": [],
        "pages": pages,
        "event_count": len(included),
        "empty_relevant": not included,
        "table_only": bool(matching.get("single_page")),
        "evidence": evidence,
    }
    return calendar, evidence
