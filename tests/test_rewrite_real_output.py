from pathlib import Path

from tools.rewrite_real_output import rewrite_tree


def test_rewrites_real_files_without_touching_source(tmp_path: Path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    article = source / "a.md"
    article.write_text("## สรุป (Executive Summary)\nระบบจัดสถานะเป็น `EXPANSION`\n",
                       encoding="utf-8")
    report = rewrite_tree(source, target)
    assert article.read_text(encoding="utf-8").startswith("## สรุป (Executive Summary)")
    revised = (target / "a.md").read_text(encoding="utf-8")
    assert "Executive Summary" not in revised
    assert "ระบบจัด" not in revised
    assert report["articles"] == 1
    assert report["after_findings"] == 0
