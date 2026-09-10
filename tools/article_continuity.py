"""Reader dialogue backed by immutable, verified handoff/publication records.

This store is internal work data, never an output sidecar. Rendering a candidate
does not assert publication or consume the published question history.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import math
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

SCHEMA = "p002-reader-dialogue/v1"
DELIVERY_SCHEMA = "p002-selected-delivery/v1"
DELIVERY_BATCH_SCHEMA = "p002-selected-delivery-batch/v1"
THAI = timezone(timedelta(hours=7))
UPDATE = "## อัปเดตจากแผนครั้งก่อน"
QUESTION = "## คุณมองตลาดอย่างไร?"


def digest(value):
    data = value.encode("utf-8") if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def moment(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("cutoff/publication timestamp requires timezone")
    return result


def normalize(text):
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE).casefold()


def _atomic(path, value):
    if "output" in {part.casefold() for part in path.resolve().parts}:
        raise ValueError("continuity evidence must remain outside public output")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".dialogue-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(name, path)
        except FileExistsError:
            if _read(path) != value:
                raise ValueError("immutable record collision")
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _verified(record):
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        return False
    seed = {key: record.get(key) for key in ("schema", "asset", "style", "contract", "locale", "cutoff", "evidence_hash", "source_article_hash")}
    # A layout rewrite is a new immutable representation of the same reviewed
    # article.  Keep the original candidate intact and include the explicit
    # parent binding in the new revision seed so it cannot collide with it.
    if "representation" in record:
        seed["representation"] = record["representation"]
    return (record.get("qc_pass") is True and digest(seed) == record.get("revision")
            and digest(record.get("markdown", "")) == record.get("article_hash")
            and digest(record.get("evidence")) == record.get("evidence_hash")
            and digest({k: v for k, v in record.items() if k != "record_hash"}) == record.get("record_hash"))


def published_history(root, *, asset, style, contract, cutoff, locale="th"):
    """Verify entire record and confirmation; same-day drafts cannot be baselines."""
    now = moment(cutoff)
    history = []
    for path in (Path(root) / "published").glob("*.json"):
        entry = _read(path)
        if not entry:
            continue
        record, receipt = entry.get("record"), entry.get("confirmation", {})
        key = {"asset": asset, "style": style, "locale": locale}
        if contract is not None:
            key["contract"] = contract
        if not _verified(record) or any(record.get(k) != v for k, v in key.items()):
            continue
        if digest(receipt) != entry.get("confirmation_hash"):
            continue
        try:
            published = moment(receipt["published_at"])
            prior_cutoff = moment(record["cutoff"])
        except (KeyError, ValueError, TypeError):
            continue
        if (not receipt.get("receipt") or not receipt.get("confirmed_by")
                or receipt.get("article_hash") != record["article_hash"]
                or receipt.get("evidence_hash") != record["evidence_hash"]
                or not prior_cutoff <= published <= now
                or published.astimezone(THAI).date() >= now.astimezone(THAI).date()):
            continue
        history.append(entry)
    return sorted(history, key=lambda e: (moment(e["confirmation"]["published_at"]), e["record"]["revision"]), reverse=True)


def _verified_delivery(root, entry):
    if not isinstance(entry, dict) or entry.get("schema") != DELIVERY_SCHEMA:
        return False
    record, receipt = entry.get("record"), entry.get("delivery", {})
    if not _verified(record) or digest(receipt) != entry.get("delivery_hash"):
        return False
    batch = _read(Path(root) / "delivery_batches" / f"{entry.get('batch_id')}.json")
    return bool(
        isinstance(batch, dict)
        and batch.get("schema") == DELIVERY_BATCH_SCHEMA
        and batch.get("finalized") is True
        and digest({k: v for k, v in batch.items() if k != "batch_hash"}) == batch.get("batch_hash")
        and entry.get("batch_id") == batch.get("batch_id")
        and record["revision"] in batch.get("revisions", [])
        and receipt.get("receipt_type") == "selected_delivery"
        and receipt.get("publication_verified") is False
        and receipt.get("article_hash") == record["article_hash"]
        and receipt.get("evidence_hash") == record["evidence_hash"]
        and receipt.get("selection_hash") == batch.get("selection_hash")
        and receipt.get("article_date") == batch.get("article_date")
    )


def delivery_history(root, *, asset, style, contract, cutoff, locale="th"):
    """Return finalized delivery records from prior Thai article dates only."""
    now = moment(cutoff)
    matches = []
    for path in (Path(root) / "deliveries").glob("*/*.json"):
        entry = _read(path)
        if not _verified_delivery(root, entry):
            continue
        record, receipt = entry["record"], entry["delivery"]
        key = {"asset": asset, "style": style, "locale": locale}
        if contract is not None:
            key["contract"] = contract
        if any(record.get(k) != v for k, v in key.items()):
            continue
        try:
            prior = moment(record["cutoff"])
            article_date = datetime.fromisoformat(receipt["article_date"]).date()
            selected = moment(receipt["selected_at"])
        except (KeyError, ValueError, TypeError):
            continue
        if (prior.astimezone(THAI).date() != article_date
                or article_date >= now.astimezone(THAI).date()):
            continue
        matches.append(entry)
    latest = {}
    for entry in matches:
        day = entry["delivery"]["article_date"]
        key = (moment(entry["delivery"]["selected_at"]), entry["batch_id"])
        if day not in latest or key > latest[day][0]:
            latest[day] = (key, entry)
    return [pair[1] for pair in sorted(latest.values(), key=lambda pair: pair[0], reverse=True)]


def accepted_history(root, *, asset, style, contract, cutoff, locale="th"):
    """Use selected-delivery history automatically, retaining manual audit support."""
    deliveries = delivery_history(root, asset=asset, style=style, contract=contract,
                                  cutoff=cutoff, locale=locale)
    manual = published_history(root, asset=asset, style=style, contract=contract,
                               cutoff=cutoff, locale=locale)
    combined = [(moment(e["record"]["cutoff"]), e["record"]["revision"], e)
                for e in deliveries + manual]
    seen = set()
    result = []
    for _, revision, entry in sorted(combined, key=lambda item: item[:2], reverse=True):
        if revision not in seen:
            seen.add(revision)
            result.append(entry)
    return result


def history_date(entry):
    return entry["record"]["cutoff"]


# Each semantic key is a genuinely different reader task. None introduces a price
# or asserts an event not already visible in the article.
QUESTIONS = [
    ("reading", "clarity", "ส่วนไหนของบทวันนี้ที่คุณอยากให้ขยายความ เพื่ออ่านกราฟต่อได้ชัดขึ้น?"),
    ("reading", "evidence", "คุณเชื่อมข้อมูลในบทกับสิ่งที่เห็นบนกราฟอย่างไร?"),
    ("reading", "followup", "จากเนื้อหาวันนี้ คุณอยากชวนผู้อ่านคนอื่นแลกเปลี่ยนประเด็นใดต่อ?"),
    ("structure", "focus", "ส่วนไหนของกราฟวันนี้ที่คุณกำลังติดตามเป็นพิเศษ เพราะอะไร?"),
    ("confirmation", "missing", "คุณอยากเห็นข้อมูลส่วนไหนชัดขึ้นก่อนประเมินภาพตลาดรอบถัดไป?"),
    ("levels", "reaction", "ปฏิกิริยาของราคาบริเวณระดับที่กล่าวถึงในบทนี้ แบบไหนที่คุณอยากติดตามต่อ?"),
    ("interpretation", "alternative", "คุณอ่านภาพตลาดในบทนี้ต่างออกไปตรงไหน และใช้เหตุผลอะไรประกอบ?"),
    ("structure", "timeframe", "เมื่อมองกรอบเวลาที่ใช้ในบทนี้ คุณคิดว่าส่วนไหนช่วยอธิบายภาพราคาได้ชัดที่สุด?"),
    ("confirmation", "patience", "เงื่อนไขใดที่คุณคิดว่าควรให้เวลาราคาพิสูจน์ต่อจากภาพวันนี้?"),
    ("levels", "attention", "จากระดับที่บทนี้ชวนจับตา คุณอยากให้บทถัดไปติดตามบริเวณไหนเป็นพิเศษ?"),
    ("interpretation", "uncertainty", "จุดไหนในภาพวันนี้ที่คุณยังตีความได้หลายทาง และเพราะอะไร?"),
    ("structure", "explanation", "ถ้าจะอธิบายกราฟวันนี้ให้เพื่อนฟัง คุณจะเริ่มจากส่วนไหน?"),
    ("confirmation", "reconsider", "ข้อมูลส่วนไหนในบทนี้ที่คุณจะกลับมาทบทวนเมื่อมีแท่งใหม่ปิด?"),
    ("levels", "comparison", "คุณใช้วิธีสังเกตราคาใกล้ระดับที่บทนี้ระบุไว้อย่างไร?"),
    ("interpretation", "learning", "บทวันนี้ช่วยให้คุณเห็นอะไรชัดขึ้น และมีประเด็นไหนที่อยากแลกเปลี่ยนเพิ่มเติม?"),
]


def plan_facts(evidence):
    """Project existing levels, without recalculating formulas or guessing events."""
    source = evidence.get("plan") or evidence.get("scenario") or evidence.get("story") or evidence
    keys = ("side", "status", "plans", "scenarios", "support", "resistance", "supports", "resistances", "zones", "public_plan_key")
    facts = {key: source[key] for key in keys if key in source}
    def strip_metadata(value):
        if isinstance(value, dict):
            return {k: strip_metadata(v) for k, v in value.items() if k not in
                    {"evidence_hash", "source_sha256", "article_sha256", "date", "cutoff_at", "created_at", "updated_at", "source"}}
        if isinstance(value, list):
            return [strip_metadata(v) for v in value]
        return value
    facts = strip_metadata(facts)
    return facts


def evaluate_outcome(previous, evidence, cutoff):
    from tools.article_continuity_outcomes import evaluate
    return evaluate(previous, evidence, cutoff)

def describe_update(baseline, evidence, previous_at, cutoff):
    date = moment(previous_at).astimezone(THAI).strftime("%d/%m/%Y")
    prior = plan_facts(baseline["evidence"])
    current = plan_facts(evidence)
    if prior and current:
        comparison = ("กรอบและเงื่อนไขรอบนี้ยังตรงกับรอบก่อน เราจึงคงประเด็นที่ต้องติดตามเดิมไว้"
                      if prior == current else "กรอบหรือเงื่อนไขรอบนี้มีการเปลี่ยนแปลง จึงปรับประเด็นที่ต้องติดตามตามรายละเอียดด้านล่าง")
        names = {"BUY": "ฝั่งขาขึ้น", "SELL": "ฝั่งขาลง"}
        if prior != current:
            changed = [label for key, label in (("zones", "โซนราคา"), ("supports", "แนวรับ"), ("support", "แนวรับ"),
                ("resistances", "แนวต้าน"), ("resistance", "แนวต้าน"), ("plans", "เงื่อนไขและระดับของแผน"),
                ("scenarios", "ฉากทัศน์ราคา"), ("status", "สถานะของแผน")) if prior.get(key) != current.get(key)]
            if changed:
                comparison = "รอบนี้มีการปรับ" + "และ".join(dict.fromkeys(changed)) + "จากข้อมูลแท่งปิดล่าสุด รายละเอียดที่ต้องติดตามอยู่ในแผนรอบนี้"
        if prior.get("side") != current.get("side") and prior.get("side") in names and current.get("side") in names:
            comparison = f"แผนเปลี่ยนจาก{names[prior['side']]}มาเป็น{names[current['side']]}ตามเงื่อนไขของข้อมูลรอบปัจจุบัน"
    else:
        comparison = "รอบนี้เรากลับมาทบทวนภาพราคาจากข้อมูลแท่งปิดล่าสุดตามรายละเอียดด้านล่าง"
    source = baseline["evidence"].get("plan") or baseline["evidence"].get("scenario") or baseline["evidence"].get("story") or baseline["evidence"]
    expiry = source.get("valid_until")
    try:
        expired = expiry is not None and moment(expiry) <= moment(cutoff)
    except ValueError:
        expired = False
    from tools.article_continuity_outcomes import evaluate
    outcome = evaluate(baseline["evidence"], evidence, cutoff) or ("แผนครั้งก่อนพ้นช่วงเวลาที่กำหนดแล้ว แต่ยังยืนยันผลระหว่างอายุแผนไม่ได้จากหลักฐานติดตามผลที่มี"
               if expired else "ยังยืนยันผลของแผนครั้งก่อนไม่ได้จากหลักฐานติดตามผลที่มี")
    return f"จากแผนครั้งก่อนวันที่ {date} {comparison} ส่วนผลของแผนเดิม {outcome}"


def validate_sections(markdown, record):
    findings = []
    if markdown.count(QUESTION) != 1 or record["question"].count("?") != 1:
        findings.append("exactly one closing question required")
    if re.search(r"BUY|SELL|ซื้อหรือขาย|ขนาดพอร์ต|เงินลงทุน", record["question"], re.I):
        findings.append("leading or personal trading question")
    if re.search(r"\d", record["question"]):
        findings.append("question introduces numeric claim")
    if bool(record.get("baseline_revision")) != (markdown.count(UPDATE) == 1):
        findings.append("baseline provenance/section mismatch")
    if record["question"] not in markdown:
        findings.append("question text mismatch")
    if markdown != record.get("markdown") or digest(markdown) != record.get("article_hash"):
        findings.append("article identity mismatch")
    if record.get("update") and record["update"] not in markdown:
        findings.append("prior evidence update mismatch")
    if re.search(r"(?m)^## ", markdown.split(QUESTION, 1)[-1]):
        findings.append("question must be final content heading")
    if findings:
        raise ValueError("; ".join(findings))


def _insert(markdown, update, question, *, style=None):
    if UPDATE in markdown or QUESTION in markdown:
        raise ValueError("reader dialogue already present")
    if update:
        # Style D งานผลิตใหม่ต้องให้ H2 โครงสร้างเป็นบรรทัดแรกของ body;
        # สรุป continuity จึงอยู่หลังส่วนโครงสร้าง (ก่อน H2 ถัดไป) แทนการ
        # แทรกหน้า H2 แรกแบบสัญญาเก่า. สไตล์อื่นคงตำแหน่งเดิมไว้.
        if str(style or "").upper() == "D":
            headings = list(re.finditer(r"(?m)^## ", markdown))
            match = headings[1] if len(headings) > 1 else None
        else:
            match = re.search(r"(?m)^## ", markdown)
        index = match.start() if match else len(markdown)
        markdown = markdown[:index].rstrip() + "\n\n" + UPDATE + "\n\n" + update + "\n\n" + markdown[index:]
    # Keep required disclaimer/evidence footer last, after final content section.
    footer = re.search(r"(?m)^(?:> บทวิเคราะห์|\*หลักฐาน:)", markdown)
    index = footer.start() if footer else len(markdown)
    return (markdown[:index].rstrip() + "\n\n" + QUESTION + "\n\n" + question
            + " แสดงความคิดเห็นแลกเปลี่ยนกันด้านล่างได้ครับ\n\n" + markdown[index:]).rstrip() + "\n"


def enrich(markdown, *, asset, style, contract, cutoff, evidence, store_root, contexts=None):
    if not eligible(asset, style):
        return markdown, None
    evidence = deepcopy(evidence)
    if style not in {"D", "E", "L", "M"}:
        raise ValueError("reader dialogue only supports approved D/E/L/M")
    cutoff = moment(cutoff).isoformat()
    seed = {"schema": SCHEMA, "asset": asset, "style": style, "contract": contract,
            "locale": "th", "cutoff": cutoff, "evidence_hash": digest(evidence),
            "source_article_hash": digest(markdown)}
    revision = digest(seed)
    existing = _read(Path(store_root) / "candidates" / (revision + ".json"))
    if existing is not None:
        if not _verified(existing) or existing.get("revision") != revision:
            raise ValueError("stored candidate integrity failure")
        return existing["markdown"], existing
    history = accepted_history(store_root, asset=asset, style=style, contract=contract, cutoff=cutoff)
    question_history = accepted_history(store_root, asset=asset, style=style, contract=None, cutoff=cutoff)
    recent = [entry["record"] for entry in question_history[:10]]
    texts = {normalize(r["question"]) for r in recent}
    semantics = {r["semantic_key"] for r in recent}
    families = {r["question_family"] for r in recent[:3]}
    batch_texts = set()
    for path in (Path(store_root) / "candidates").glob("*.json"):
        other = _read(path)
        if (_verified(other) and (other["asset"], other["style"]) != (asset, style)
                and moment(other["cutoff"]).astimezone(THAI).date() == moment(cutoff).astimezone(THAI).date()):
            batch_texts.add(normalize(other["question"]))
    offset = int(digest(asset + style + cutoff)[:8], 16) % len(QUESTIONS)
    options = QUESTIONS[offset:] + QUESTIONS[:offset]
    grounded = set(contexts or ()) | {"structure", "confirmation", "interpretation", "reading"}
    if re.search(r"แนวรับ|แนวต้าน|ระดับ|กรอบราคา|SL|TP", markdown):
        grounded.add("levels")
    chosen = next((q for q in options if q[0] in grounded and q[0] not in families and q[1] not in semantics and normalize(q[2]) not in texts | batch_texts), None)
    if chosen is None:
        raise ValueError("no context-safe nonrepeating question; editorial revision required")
    update = None
    baseline = history[0]["record"] if history else None
    if baseline:
        update = describe_update(baseline, evidence, history_date(history[0]), cutoff)
    result = _insert(markdown, update, chosen[2], style=style)
    record = {**seed, "revision": revision, "evidence": evidence, "markdown": result,
              "article_hash": digest(result), "question": chosen[2], "question_family": chosen[0],
              "semantic_key": chosen[1], "baseline_revision": baseline["revision"] if baseline else None,
              "update": update,
              "baseline_article_hash": baseline["article_hash"] if baseline else None,
              "continuity_reason": "outcome_unverified" if baseline else "no_verified_delivery",
              "qc_pass": True}
    record["record_hash"] = digest(record)
    validate_sections(result, record)
    return result, record


def save_candidate(store_root, record, markdown, qc_pass=True):
    if record is None:
        return None
    if not qc_pass or not _verified(record) or digest(markdown) != record["article_hash"]:
        raise ValueError("candidate requires passing QC and exact final article hash")
    path = Path(store_root) / "candidates" / (record["revision"] + ".json")
    prior = _read(path)
    if prior is not None and prior != record:
        raise ValueError("immutable candidate collision")
    if prior is None:
        _atomic(path, record)
    return path


def _without_dialogue(markdown, record):
    """Remove the generated closing dialogue while preserving the article body."""
    question = str(record.get("question") or "")
    block = f"\n\n{QUESTION}\n\n{question} แสดงความคิดเห็นแลกเปลี่ยนกันด้านล่างได้ครับ"
    if block not in markdown:
        return markdown
    source = markdown.replace(block, "", 1)
    update = str(record.get("update") or "")
    if update:
        source = source.replace(f"\n\n{UPDATE}\n\n{update}", "", 1)
    return source.rstrip() + "\n"


def bind_layout_representation(store_root, parent, markdown, *, article_name,
                               contract_name=None, contract_sha256=None,
                               source_layout="legacy", target_layout="country_first"):
    """Create a verified immutable candidate for a path-only layout rewrite.

    The parent candidate remains immutable.  Evidence values are carried
    forward, while the article binding is updated to the exact canonical
    filename/hash and provenance records the parent revision.
    """
    if not _verified(parent):
        raise ValueError("representation parent is not a verified candidate")
    representation = {
        "kind": "layout_rewrite",
        "source_layout": source_layout,
        "target_layout": target_layout,
        "parent_revision": parent["revision"],
        "parent_article_hash": parent["article_hash"],
    }
    record = deepcopy(parent)
    record.pop("record_hash", None)
    evidence = deepcopy(record.get("evidence") or {})
    plan = evidence.get("plan")
    if isinstance(plan, dict):
        plan["article"] = article_name
        plan["article_sha256"] = digest(markdown)
    record["evidence"] = evidence
    record["evidence_hash"] = digest(evidence)
    record["source_article_hash"] = digest(_without_dialogue(markdown, parent))
    record["markdown"] = markdown
    record["article_hash"] = digest(markdown)
    record["representation"] = representation
    if contract_name is not None:
        record["representation"]["contract_name"] = contract_name
    if contract_sha256 is not None:
        record["representation"]["contract_sha256"] = contract_sha256
    seed = {key: record.get(key) for key in ("schema", "asset", "style", "contract", "locale", "cutoff", "evidence_hash", "source_article_hash")}
    seed["representation"] = representation
    record["revision"] = digest(seed)
    record["record_hash"] = digest(record)
    validate_sections(markdown, record)
    save_candidate(store_root, record, markdown)
    return record


def layout_equivalent(left, right):
    """Compare article semantics while ignoring image path-only rewrites."""
    image = re.compile(r"(!\[[^\]]*\]\()[^)]+(\))")
    return image.sub(r"\1<image>\2", left) == image.sub(r"\1<image>\2", right)


def eligible(asset, style):
    """Use enabled upload lanes without changing their scheduling/selection."""
    policy = _read(Path(__file__).resolve().parents[1] / "config" / "publishing_policy.json") or {}
    style_id = {"D": "d_chart_story", "E": "e_indicator", "L": "l_forex_daily_plan", "M": "m_btcusd_h1_visual_daily"}.get(style)
    for lane in policy.get("upload_lanes", []):
        if not lane.get("enabled") or lane.get("style") != style_id:
            continue
        assets = lane.get("assets", [])
        if assets == "scheduled_forex":
            from tools import forex_daily_plan
            assets = forex_daily_plan.ASSETS
        if asset in assets or asset == "btcusd" and "btc" in assets:
            return True
    return False


def confirm_publication(store_root, revision, *, article_hash, evidence_hash, published_at, receipt, confirmed_by):
    if not re.fullmatch(r"[0-9a-f]{64}", revision):
        raise ValueError("invalid revision")
    record = _read(Path(store_root) / "candidates" / (revision + ".json"))
    if (not _verified(record) or record["article_hash"] != article_hash
            or record["evidence_hash"] != evidence_hash or not str(receipt).strip()
            or not str(confirmed_by).strip() or moment(published_at) < moment(record["cutoff"])):
        raise ValueError("publication confirmation must bind verified candidate and receipt")
    confirmation = {"article_hash": article_hash, "evidence_hash": evidence_hash,
                    "published_at": moment(published_at).isoformat(), "receipt": receipt,
                    "confirmed_by": confirmed_by}
    entry = {"record": record, "confirmation": confirmation, "confirmation_hash": digest(confirmation)}
    path = Path(store_root) / "published" / (revision + ".json")
    prior = _read(path)
    if prior is not None and prior != entry:
        raise ValueError("immutable publication collision")
    if prior is None:
        _atomic(path, entry)
    return path


STYLE_LETTERS = {
    "d_chart_story": "D",
    "e_indicator": "E",
    "l_forex_daily_plan": "L",
    "m_btcusd_h1_visual_daily": "M",
}


def record_selected_delivery(store_root, *, target_root, inventories,
                             selection_report, article_date, selected_at=None):
    """Finalize an exact, complete local handoff as the next-run baseline."""
    store_root, target_root = Path(store_root), Path(target_root)
    if not inventories or any(item.get("status") != "ready" for item in inventories):
        raise ValueError("selected delivery requires every scheduled lane to pass")
    article_day = date.fromisoformat(str(article_date))
    selection_hash = digest(selection_report)
    selected_at = moment(selected_at or datetime.now(timezone.utc)).isoformat()
    bound = []
    for item in inventories:
        style = STYLE_LETTERS.get(item.get("style"))
        if not style:
            raise ValueError(f"unsupported continuity style: {item.get('style')}")
        asset = "btcusd" if item.get("asset") == "btc" else item.get("asset")
        article = target_root / item["destination_folder"] / item["article_name"]
        if not article.is_file():
            raise ValueError(f"selected article missing: {item['article_name']}")
        article_hash = digest(article.read_text(encoding="utf-8"))
        candidates = []
        for path in (store_root / "candidates").glob("*.json"):
            candidate = _read(path)
            if (_verified(candidate) and candidate.get("asset") == asset
                    and candidate.get("style") == style
                    and candidate.get("article_hash") == article_hash
                    and moment(candidate["cutoff"]).astimezone(THAI).date() == article_day):
                candidates.append(candidate)
        if not candidates:
            # A country-first migration changes only article/image paths.  Bind
            # the exact target bytes to one verified legacy parent by semantic
            # equivalence, then write a new immutable representation candidate.
            target_markdown = article.read_text(encoding="utf-8")
            parents = []
            for path in (store_root / "candidates").glob("*.json"):
                candidate = _read(path)
                if (_verified(candidate) and candidate.get("asset") == asset
                        and candidate.get("style") == style
                        and moment(candidate["cutoff"]).astimezone(THAI).date() == article_day
                        and layout_equivalent(candidate.get("markdown", ""), target_markdown)):
                    parents.append(candidate)
            if len(parents) == 1:
                item_contract = item.get("validated_contract_name") or item.get("contract_name")
                bound_candidate = bind_layout_representation(
                    store_root, parents[0], target_markdown,
                    article_name=item["article_name"],
                    contract_name=item_contract,
                    contract_sha256=item.get("contract_sha256"),
                )
                candidates.append(bound_candidate)
        if len(candidates) != 1:
            raise ValueError(
                f"selected article must bind one verified candidate: {asset}/{style} ({len(candidates)})")
        bound.append((item, candidates[0]))
    batch_seed = {
        "schema": DELIVERY_BATCH_SCHEMA,
        "article_date": article_day.isoformat(),
        "selection_hash": selection_hash,
        "items": [{"revision": record["revision"], "article_hash": record["article_hash"],
                   "evidence_hash": record["evidence_hash"]} for _, record in bound],
    }
    batch_id = digest(batch_seed)
    manifest_path = store_root / "delivery_batches" / f"{batch_id}.json"
    existing = _read(manifest_path)
    if existing is not None:
        if (existing.get("batch_id") != batch_id
                or digest({k: v for k, v in existing.items() if k != "batch_hash"}) != existing.get("batch_hash")):
            raise ValueError("selected delivery batch integrity failure")
        return {"status": "recorded", "batch_id": batch_id,
                "revisions": existing["revisions"], "idempotent": True}
    revisions = []
    for item, record in bound:
        receipt = {
            "receipt_type": "selected_delivery", "publication_verified": False,
            "article_date": article_day.isoformat(), "selected_at": selected_at,
            "selection_hash": selection_hash, "article_hash": record["article_hash"],
            "evidence_hash": record["evidence_hash"], "lane_id": item["id"],
            "destination_folder": item["destination_folder"],
            "article_name": item["article_name"],
        }
        entry = {"schema": DELIVERY_SCHEMA, "batch_id": batch_id,
                 "record": record, "delivery": receipt,
                 "delivery_hash": digest(receipt)}
        entry_path = store_root / "deliveries" / batch_id / f"{record['revision']}.json"
        prior = _read(entry_path)
        if prior is not None:
            if (prior.get("batch_id") != batch_id
                    or prior.get("record", {}).get("revision") != record["revision"]
                    or prior.get("delivery", {}).get("selection_hash") != selection_hash):
                raise ValueError("selected delivery item integrity failure")
            selected_at = prior["delivery"]["selected_at"]
        else:
            try:
                _atomic(entry_path, entry)
            except ValueError:
                # An identical batch may win the create race with a different
                # wall-clock timestamp. Adopt the winner after validating the
                # immutable identity instead of treating this as corruption.
                prior = _read(entry_path)
                if (not prior or prior.get("batch_id") != batch_id
                        or prior.get("record", {}).get("revision") != record["revision"]
                        or prior.get("delivery", {}).get("selection_hash") != selection_hash):
                    raise
                selected_at = prior["delivery"]["selected_at"]
        revisions.append(record["revision"])
    manifest = {**batch_seed, "batch_id": batch_id, "selected_at": selected_at,
                "revisions": revisions, "finalized": True}
    manifest["batch_hash"] = digest(manifest)
    try:
        _atomic(manifest_path, manifest)
    except ValueError:
        existing = _read(manifest_path)
        if (not existing or existing.get("batch_id") != batch_id
                or digest({k: v for k, v in existing.items() if k != "batch_hash"}) != existing.get("batch_hash")):
            raise
        return {"status": "recorded", "batch_id": batch_id,
                "revisions": existing["revisions"], "idempotent": True}
    return {"status": "recorded", "batch_id": batch_id,
            "revisions": revisions, "idempotent": False}


def record_delivery_pending(store_root, *, selection_report, article_date, reason):
    """Write deterministic internal recovery evidence; never a usable baseline."""
    payload = {"schema": "p002-selected-delivery-pending/v1",
               "article_date": str(article_date),
               "selection_hash": digest(selection_report), "reason": str(reason)}
    payload["pending_hash"] = digest(payload)
    path = Path(store_root) / "delivery_pending" / f"{payload['selection_hash']}.json"
    prior = _read(path)
    if prior is None:
        _atomic(path, payload)
    return path


def main(argv=None):
    """Explicit operator confirmation, never called by daily generation."""
    import argparse
    parser = argparse.ArgumentParser(description="Record manual publication confirmation for an exact P002 candidate")
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--article-hash", required=True)
    parser.add_argument("--evidence-hash", required=True)
    parser.add_argument("--published-at", required=True)
    parser.add_argument("--receipt", required=True, help="Published URL or recorded explicit manual-upload confirmation")
    parser.add_argument("--confirmed-by", required=True)
    args = vars(parser.parse_args(argv))
    root = args.pop("store_root")
    revision = args.pop("revision")
    print(confirm_publication(root, revision, **args))


if __name__ == "__main__":
    main()
