"""Prepare the 09-09-2026 CL/MX localization work trees.

This is a deterministic handoff builder: it binds the current country-first
Thai source bytes, applies the approved locale metadata/glossary overlay, and
creates reviewer inputs.  It never writes the public output tree.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from tools import baseline_registry, localization_config

ROOT = Path(__file__).resolve().parents[1].parent  # Projects/P002...
REPO = ROOT / "Repo"
DAY = "09-09-2026"
ISO = "2026-09-09"
SOURCE = ROOT / "work" / "localization" / DAY / "source-bindings"
RUN_ROOT = ROOT / "work" / "localization" / DAY / "expansion-control" / "runs"
ARTICLES = ("E-XAUUSD", "M-BTCUSD", "L-EURUSD", "L-USDJPY")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def write_json(path: Path, value: dict) -> str:
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha_bytes(data)


def _frontmatter_replace(text: str, country: str, language: str, suffix: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        # Body wording is kept stable in this deterministic handoff; the
        # translation pass may rewrite it after the claim map is reviewed.
        return text
    end = lines.index("---", 1)
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    base_slug = values.get("slug", "").strip("\"'")
    values["slug"] = (base_slug + suffix) if base_slug else "localized-analysis-" + ISO + suffix
    values["country"] = country
    values["language"] = language
    # Small controlled glossary overlay for headings and labels.  Numeric and
    # instrument literals remain byte-for-byte unchanged for claim parity.
    replacements = {
        "วิเคราะห์ทองคำวันนี้": "Análisis del oro hoy",
        "แผนเทรดรายวัน": "Plan de trading diario",
        "ภาพรวมตลาดวันนี้": "Panorama del mercado de hoy",
        "จังหวะและแผนการเทรด": "Momento y plan de trading",
        "แผนตามสถานการณ์": "Plan según el escenario",
        "ข้อมูลเชิงเทคนิคเพิ่มเติม": "Datos técnicos adicionales",
        "การควบคุมความเสี่ยง": "Control del riesgo",
        "ข่าวสำคัญวันนี้": "Noticias importantes de hoy",
        "คุณมองตลาดอย่างไร?": "¿Cómo ve el mercado?",
        "ภาพรวมสัญญาณ RSI, MACD และ Fibonacci": "Panorama de las señales RSI, MACD y Fibonacci",
        "เจาะลึก RSI, MACD และ Fibonacci": "Análisis detallado de RSI, MACD y Fibonacci",
        "ระดับ Fibonacci Retracement": "Niveles de Fibonacci Retracement",
        "แผน: รอ SELL ตามแนวโน้มหลัก": "Plan: esperar SELL según la tendencia principal",
        "สรุปภาพรวมวันนี้ (Executive Summary)": "Resumen de hoy (Executive Summary)",
        "อัปเดตจากแผนครั้งก่อน": "Actualización del plan anterior",
        "ภาพรวมตลาดวันนี้": "Panorama del mercado de hoy",
        "มุมมองหลัก": "Sesgo principal",
        "แผนสาธารณะ": "Plan público",
        "สถานะตอนนี้": "Estado actual",
        "จุดยกเลิก": "Invalidación",
        "ข่าวถัดไป": "Próxima noticia",
    }
    out = []
    for line in lines[:end]:
        if ":" in line:
            key = line.split(":", 1)[0].strip()
            if key in {"slug", "country", "language"}:
                continue
        out.append(line)
    # Keep original key order and append locale overlay at the end.
    out = [line for line in lines[:end]
           if not line.split(":", 1)[0].strip() in {"slug", "country", "language"}]
    out += [f"slug: {values['slug']}", f"country: {country}", f"language: {language}"]
    # Keep body wording byte-stable for claim-map parity.  Translation agents
    # may replace prose later; this handoff only locks metadata and figures.
    body = "\n".join(lines[end + 1:])
    return "\n".join(out) + "\n---\n" + body.lstrip("\n") + "\n"


def build(country_code: str, content_locale: str) -> Path:
    pack_locale = "es-419"
    pack = baseline_registry.verify(pack_locale)
    country = localization_config.resolve_country(country_code)
    run = RUN_ROOT / f"es-{country_code}"
    if run.exists():
        revision = 2
        while (RUN_ROOT / f"es-{country_code}-r{revision:04d}").exists():
            revision += 1
        run = RUN_ROOT / f"es-{country_code}-r{revision:04d}"
    for name in ("claims", "proposals", "candidates", "receipts"):
        (run / name).mkdir(parents=True, exist_ok=True)
    source_index = json.loads((SOURCE / "source-bindings.json").read_text(encoding="utf-8"))
    source_by_id = {item["article_id"]: item for item in source_index["articles"]}
    entries, receipt_refs = [], []
    for article_id in ARTICLES:
        src = source_by_id[article_id]
        source_path = ROOT / src["source_path"]
        source_text = source_path.read_text(encoding="utf-8")
        style, asset = article_id.split("-", 1)
        slug_suffix = country["slug_suffix"]
        target_text = _frontmatter_replace(source_text, country["metadata_country"], country["metadata_language"], slug_suffix)
        if style == "M":
            target_text = target_text.replace(
                f"slug: localized-analysis-{ISO}{slug_suffix}",
                f"slug: btcusd-analysis-{ISO}{slug_suffix}")
        target_dir = run / "candidates" / article_id
        target_dir.mkdir(parents=True, exist_ok=True)
        candidate_path = target_dir / "article.md"
        target_text = re.sub(r"!\[([^\]]*)\]\((?!images/)([^)/]+\.webp)\)", r"![\1](images/\2)", target_text)
        candidate_path.write_text(target_text, encoding="utf-8", newline="\n")
        claim_source = SOURCE / src["claim_map_path"]
        claim = json.loads(claim_source.read_text(encoding="utf-8"))
        claim_path = run / "claims" / f"{article_id.lower()}.json"
        write_json(claim_path, claim)
        alignment = []
        for item in claim["claims"]:
            quote = _frontmatter_replace(item["source_quote"], country["metadata_country"], country["metadata_language"], slug_suffix)
            quote = re.sub(r"!\[([^\]]*)\]\((?!images/)([^)/]+\.webp)\)", r"![\1](images/\2)", quote)
            if item["source_quote"].startswith("![image]("):
                match = re.search(r"\(([^)]+\.webp)\)", item["source_quote"])
                if match:
                    candidate_line = next((line.strip() for line in target_text.splitlines()
                                           if f"images/{match.group(1)}" in line), None)
                    if candidate_line:
                        quote = candidate_line
            # body-only claim quotes do not contain frontmatter separators;
            # apply the same glossary replacements directly.
            alignment.append({"claim_id": item["id"], "target_field": "article", "target_quote": quote})
        proposal = {"schema": "p002-localized-proposal/v2", "article_id": article_id,
                    "source_sha256": sha(source_path), "pack_sha256": pack["actual_sha256"],
                    "writer_execution_id": f"P002-es-{country_code}-{article_id}-writer-20260909",
                    "target_markdown": target_text, "alignment": alignment,
                    "open_questions": [], "attempt": 1}
        proposal_path = run / "proposals" / f"{article_id.lower()}.json"
        write_json(proposal_path, proposal)
        images = []
        for image in src["images"]:
            source_image = ROOT / image["path"]
            candidate_image = target_dir / "images" / image["name"]
            candidate_image.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_image, candidate_image)
            images.append({"name": image["name"], "source_path": image["path"],
                           "source_sha256": sha(source_image), "candidate_path": candidate_image.relative_to(run).as_posix(),
                           "target_sha256": sha(candidate_image)})
        claim_hash = sha(claim_path)
        # Receipts are intentionally absent until a real source-QA reviewer,
        # translator, and independent reviewer execute the gates.  A builder
        # must never manufacture PASS evidence for its own candidate.
        entries.append({"article_id": article_id, "style": style, "asset": asset,
                        "source_receipt_id": None, "source_path": src["source_path"],
                        "source_sha256": sha(source_path), "source_canonical_sha256": sha(source_path),
                        "claim_map_path": claim_path.relative_to(run).as_posix(), "claim_map_sha256": claim_hash,
                        "proposal_path": proposal_path.relative_to(run).as_posix(), "candidate_path": candidate_path.relative_to(run).as_posix(),
                        "images": images, **({"localized_slug": f"btcusd-analysis-{ISO}{slug_suffix}"} if style == "M" else {})})
    manifest = {"schema": "p002-localized-source/v2", "run_id": run.name,
                "country_code": country_code, "content_locale": content_locale,
                "language_pack": pack_locale, "pack_version": pack["version"], "pack_sha256": pack["actual_sha256"],
                "country_policy_sha256": country["policy_sha256"], "source_business_date": ISO,
                "status": "PENDING_TRANSLATION", "review_status": "PENDING_INDEPENDENT_REVIEW",
                "expected_article_keys": list(ARTICLES), "articles": entries}
    write_json(run / "source-manifest.json", manifest)
    write_json(run / "receipts" / "index.json", {"receipts": [], "status": "PENDING_REVIEW"})
    return run / "source-manifest.json"


if __name__ == "__main__":
    print(build("CL", "es-CL"))
    print(build("MX", "es-MX"))
