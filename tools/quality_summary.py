"""Render a human-readable Markdown summary from validated evaluation JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.quality_scoring import QualityScoringError, evaluate, load_config


def validate_evaluation(evaluation: dict[str, Any]) -> None:
    """Validate structural schema and deterministic status/calculation coherence."""
    schema = json.loads((ROOT / "schemas" / "quality-evaluation-v1.schema.json")
                        .read_text(encoding="utf-8"))
    try:
        jsonschema.validate(evaluation, schema, format_checker=jsonschema.FormatChecker())
    except jsonschema.ValidationError as exc:
        raise QualityScoringError(f"invalid evaluation schema: {exc.message}") from exc
    config = load_config()
    if evaluation["rubric_version"] != config["rubric_version"]:
        raise QualityScoringError("evaluation rubric version does not match active config")
    replay_input = {key: evaluation[key] for key in (
        "job_id", "article_id", "attempt", "producer", "input_hashes", "hard_gates",
        "brief_compliance", "visual_applicability", "criterion_judgments", "findings",
        "created_at")}
    replay = evaluate(replay_input, config=config,
                      expected_hashes=evaluation["input_hashes"])
    if replay != evaluation:
        raise QualityScoringError("evaluation is not semantically coherent with calculator")


def render(evaluation: dict[str, Any]) -> str:
    validate_evaluation(evaluation)
    config = load_config()
    calculation = evaluation["calculation"]
    lines = ["# P002 Quality Score", "", f"- Job: `{evaluation['job_id']}`",
             f"- Article: `{evaluation['article_id']}`", f"- Status: `{evaluation['status']}`",
             f"- Mode: `{config['mode']}`"]
    if calculation is None:
        lines += ["- Overall: not scored (hard/compliance precedence)"]
    else:
        lines += [f"- Overall: {calculation['overall_score']:.2f}%",
                  f"- Content: {calculation['content_score']:.2f}%",
                  "- Visual: " + (f"{calculation['visual_score']:.2f}%"
                                   if calculation["visual_score"] is not None else "N/A")]
    lines += ["", "## Findings", ""]
    if not evaluation["findings"]:
        lines.append("- None")
    else:
        for item in evaluation["findings"]:
            lines.append(f"- **{item['priority']} · {item['criterion']}** — {item['issue']} "
                         f"(`{item['owner']}`, {item['location']})")
    lines += ["", "## Next action", "",
              "- Shadow only; do not change release selection."
              if evaluation["status"] == "PASS_SCORE" else
              "- Route findings to their owners; Agent 05 must not edit source artifacts."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evaluation", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    value = json.loads(args.evaluation.read_text(encoding="utf-8"))
    rendered = render(value)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
