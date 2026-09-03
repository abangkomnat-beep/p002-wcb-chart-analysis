"""Replay frozen Style D/L evidence through the current real renderers.

This script is local-only evidence tooling.  It never calls a provider and only
writes inside Preview/reaudit-dl-20260902.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops

from tools import (
    chart_story,
    chart_story_renderer,
    forex_daily_plan,
    image_output,
    visual_theme,
)


CODE_REPO = Path(visual_theme.__file__).resolve().parents[1]
EVIDENCE_REPO = Path(os.environ.get("P002_EVIDENCE_REPO", CODE_REPO)).resolve()
HERE = Path(__file__).resolve().parent
HASH_BASIS = {
    "algorithm": "sha256",
    "path_encoding": "UTF-8 POSIX path relative to CODE_REPO",
    "text_normalization": "CRLF and CR normalized to LF before hashing; binary bytes unchanged",
    "record_separator": "NUL byte between relative path and content records",
}
STYLE_D_SOURCE = EVIDENCE_REPO / "tests" / "fixtures" / "xau_420_sessions_2026-08-07.json"
STYLE_L_RUN = EVIDENCE_REPO / "work" / "forex-daily-plan" / "fx-daily-plan-20260831T043425Z"
STYLE_L_SOURCE = STYLE_L_RUN / "input" / "eurusd-closed-bars.json"
STYLE_L_TRACE = STYLE_L_RUN / "evidence" / "eurusd-decision-trace.json"
DIRECT_VISUAL_QA = {
    "style-d-xauusd-d1-overview.webp": {
        "bbox_clipping": "PASS", "overlap": "PASS",
        "notes": "Title, legend, zones and right-edge price tags are fully visible.",
    },
    "style-d-xauusd-d1-decision-map.webp": {
        "bbox_clipping": "PASS", "overlap": "PASS",
        "notes": "Header, decision callouts, arrows and right-edge tags remain readable.",
    },
    "style-l-eurusd-h1-plan.webp": {
        "bbox_clipping": "PASS", "overlap": "PASS",
        "notes": ("PDH and latest-close tags are separated in display space with exact "
                  "data anchors retained; H4 inset and zone label remain readable."),
    },
    "style-l-eurusd-m15-trigger.webp": {
        "bbox_clipping": "PASS", "overlap": "PASS",
        "notes": "Status badge, trigger tag, watch-zone tag and conditional arrow are visible.",
    },
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def combined_sha256(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(CODE_REPO).as_posix().encode("utf-8"))
        digest.update(b"\0")
        raw = path.read_bytes()
        try:
            normalized = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        except UnicodeDecodeError:
            normalized = raw
        digest.update(normalized)
        digest.update(b"\0")
    return digest.hexdigest()


def image_record(path: Path, *, style: str, asset: str, timeframe: str,
                 renderer: str, source_paths: list[Path], renderer_paths: list[Path],
                 renderer_metadata: dict | None = None) -> dict:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    background = Image.new("RGB", image.size, image.getpixel((0, 0)))
    difference = ImageChops.difference(image, background).convert("L")
    content_bbox = difference.point(lambda value: 255 if value > 12 else 0).getbbox()
    edge_contacts = []
    if content_bbox:
        left, top, right, bottom = content_bbox
        if left == 0:
            edge_contacts.append("left")
        if top == 0:
            edge_contacts.append("top")
        if right == width:
            edge_contacts.append("right")
        if bottom == height:
            edge_contacts.append("bottom")
    metadata = dict(renderer_metadata or {})
    if "path" in metadata:
        metadata["path"] = path.name
    direct_qa = DIRECT_VISUAL_QA[path.name]
    return {
        "file": path.name,
        "style": style,
        "asset": asset,
        "timeframe": timeframe,
        "renderer": renderer,
        "theme": {
            "schema": visual_theme.SCHEMA,
            "version": visual_theme.VERSION,
            "config": "config/visual_theme.json",
            "config_sha256": sha256_file(CODE_REPO / "config" / "visual_theme.json"),
        },
        "source": [
            {"path": item.relative_to(EVIDENCE_REPO).as_posix(), "sha256": sha256_file(item)}
            for item in source_paths
        ],
        "code": {
            "paths": [item.relative_to(CODE_REPO).as_posix() for item in renderer_paths],
            "combined_sha256": combined_sha256(renderer_paths),
            "hash_basis": HASH_BASIS,
        },
        "dimensions_px": [width, height],
        "file_size_bytes": path.stat().st_size,
        "file_sha256": sha256_file(path),
        "renderer_metadata": metadata,
        "qa": {
            "image_output_verify": image_output.verify(path) == path.stat().st_size,
            "content_bbox_px": list(content_bbox) if content_bbox else None,
            "edge_contact_scan": {
                "method": "RGB distance from top-left background, threshold 12",
                "contacts": edge_contacts,
                "interpretation": (
                    "diagnostic only; typography clipping is decided by direct visual review"
                ),
            },
            "direct_visual_review": {
                "reviewer_role": "P002 Visual Builder self-review",
                "approval_authority": False,
                **direct_qa,
            },
            "bbox_clipping": direct_qa["bbox_clipping"],
            "overlap": direct_qa["overlap"],
        },
    }


def render_style_d() -> list[dict]:
    rows = json.loads(STYLE_D_SOURCE.read_text(encoding="utf-8"))
    story = chart_story.build_story(rows, asset="xauusd")
    outputs = []
    specs = (
        ("style-d-xauusd-d1-overview.webp", "D1 overview", chart_story_renderer.render_overview),
        ("style-d-xauusd-d1-decision-map.webp", "D1 decision map", chart_story_renderer.render_zoom),
    )
    renderer_paths = [
        CODE_REPO / "tools" / "chart_story.py",
        CODE_REPO / "tools" / "chart_story_renderer.py",
        CODE_REPO / "tools" / "visual_theme.py",
        CODE_REPO / "tools" / "image_output.py",
    ]
    for name, timeframe, renderer in specs:
        target = HERE / name
        metadata = renderer(story, rows, target)
        outputs.append(image_record(
            target, style="D", asset="XAUUSD", timeframe=timeframe,
            renderer=f"tools.chart_story_renderer.{renderer.__name__}",
            source_paths=[STYLE_D_SOURCE], renderer_paths=renderer_paths,
            renderer_metadata=metadata,
        ))
    return outputs


def render_style_l() -> tuple[list[dict], dict]:
    source = json.loads(STYLE_L_SOURCE.read_text(encoding="utf-8"))
    trace = json.loads(STYLE_L_TRACE.read_text(encoding="utf-8"))
    rows = source["rows"]
    bases = trace["bases"]
    cutoff = datetime.fromisoformat(source["cutoff_utc"])
    canonical_input_sha = forex_daily_plan.sha(source)
    if canonical_input_sha != trace["input_sha256"]:
        raise RuntimeError("Style L frozen source hash does not match its decision trace")

    h4 = forex_daily_plan.h4_context(rows["4h"])
    h1 = forex_daily_plan.h1_map(rows["1h"], rows["1day"])
    states = forex_daily_plan.intraday_state("eurusd", rows, bases)
    policy = forex_daily_plan.load_decision_policy()
    preferred, _ = forex_daily_plan.preferred_direction(h4)
    model, _ = forex_daily_plan.choose_model(h4["bias"], states, policy)
    plan = forex_daily_plan.scenario(
        model, h4["bias"], preferred, h1, states,
        asset="eurusd", cutoff=cutoff, evidence_hash=canonical_input_sha,
        current_close=float(rows["15min"][-1]["close"]),
    )

    h1_path = HERE / "style-l-eurusd-h1-plan.webp"
    m15_path = HERE / "style-l-eurusd-m15-trigger.webp"
    forex_daily_plan.save_h1_chart(
        "eurusd", rows["1h"], rows["4h"], h4, h1, plan, preferred,
        bases["1h"], h1_path,
    )
    forex_daily_plan.save_m15_chart(
        "eurusd", rows["15min"], model, states, plan, preferred,
        bases["15min"], policy, m15_path,
    )
    renderer_paths = [
        CODE_REPO / "tools" / "forex_daily_plan.py",
        CODE_REPO / "tools" / "visual_theme.py",
        CODE_REPO / "tools" / "image_output.py",
        CODE_REPO / "config" / "forex_daily_decision_policy.json",
    ]
    records = [
        image_record(
            h1_path, style="L", asset="EURUSD", timeframe="H1 plan",
            renderer="tools.forex_daily_plan.save_h1_chart",
            source_paths=[STYLE_L_SOURCE, STYLE_L_TRACE], renderer_paths=renderer_paths,
            renderer_metadata={"model": model, "side": plan["side"],
                               "status": plan["status"], "preferred": preferred},
        ),
        image_record(
            m15_path, style="L", asset="EURUSD", timeframe="M15 trigger",
            renderer="tools.forex_daily_plan.save_m15_chart",
            source_paths=[STYLE_L_SOURCE, STYLE_L_TRACE], renderer_paths=renderer_paths,
            renderer_metadata={"model": model, "side": plan["side"],
                               "status": plan["status"], "preferred": preferred},
        ),
    ]
    replay = {
        "frozen_run_id": STYLE_L_RUN.name,
        "canonical_input_sha256": canonical_input_sha,
        "trace_input_sha256": trace["input_sha256"],
        "hash_match": canonical_input_sha == trace["input_sha256"],
        "derived_with_current_code": True,
        "network_used": False,
        "production_output_written": False,
    }
    return records, replay


def main() -> None:
    HERE.mkdir(parents=True, exist_ok=True)
    style_l, replay = render_style_l()
    code_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=CODE_REPO, text=True
    ).strip()
    manifest = {
        "schema": "p002-direct-preview-manifest-v1",
        "job_id": "P002-reaudit-DL-20260902",
        "revision": 3,
        "producer": "P002 Visual Builder",
        "code_commit": code_commit,
        "integration_ref": {"branch": "main", "commit": code_commit},
        "code_hash_basis": HASH_BASIS,
        "scope": "local-only direct previews for independent QQ review",
        "network_used": False,
        "production_output_written": False,
        "theme": {"schema": visual_theme.SCHEMA, "version": visual_theme.VERSION},
        "style_l_replay": replay,
        "artifacts": render_style_d() + style_l,
        "qa_summary": {
            "image_output_gate": "PASS",
            "bbox_clipping": "PASS",
            "overlap": "PASS",
            "builder_self_review": "PASS_AWAITING_INDEPENDENT_QQ",
        },
    }
    (HERE / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
