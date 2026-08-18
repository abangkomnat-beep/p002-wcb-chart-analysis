"""สร้างฉบับ copy-desk จากงานจริงใน output โดยไม่แตะต้นฉบับ"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools import human_copydesk


def rewrite_tree(source: Path, target: Path) -> dict:
    if source.resolve() == target.resolve():
        raise ValueError("target must be separate from source")
    rows = []
    for article in sorted(source.rglob("*.md")):
        relative = article.relative_to(source)
        original = article.read_text(encoding="utf-8")
        revised = human_copydesk.naturalize(original)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(revised, encoding="utf-8")
        rows.append({
            "path": relative.as_posix(),
            "changed": revised != original,
            "before_findings": len(human_copydesk.findings(original)),
            "after_findings": len(human_copydesk.findings(revised)),
        })
    report = {
        "schema": "human-copydesk-real-output-v1",
        "source": str(source.resolve()),
        "target": str(target.resolve()),
        "articles": len(rows),
        "changed": sum(row["changed"] for row in rows),
        "before_findings": sum(row["before_findings"] for row in rows),
        "after_findings": sum(row["after_findings"] for row in rows),
        "rows": rows,
    }
    target.mkdir(parents=True, exist_ok=True)
    (target / "copydesk-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(rewrite_tree(args.source, args.target), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
