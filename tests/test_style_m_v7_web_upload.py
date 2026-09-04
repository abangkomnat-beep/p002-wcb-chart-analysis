from pathlib import Path

import pytest

from tools import style_m_v7_web_upload as web


def _markdown():
    return """---\nasset: \"btc\"\ntitle: \"internal title\"\nexcerpt: \"internal excerpt\"\nauthor_slug: \"worldclassbroker-team\"\n---\n\n# บทความ\n\n![H1](h1.webp)\n\n![M15](m15.webp)\n"""


def test_web_upload_builds_minimal_frontmatter_and_preserves_two_images():
    result = web.build(_markdown(), image_names={"h1_market_map": "h1.webp", "m15_entry_plan": "m15.webp"}, date_iso="2026-09-04")
    assert result.startswith("---\nasset: btc\n")
    assert 'title: "Bitcoin (BTC)' in result
    assert "author_slug: worldclassbroker-team" in result
    assert "natthaphon-s" not in result
    assert result.count(".webp)") == 2


def test_web_upload_validate_rejects_unknown_key_and_wrong_author(tmp_path):
    h1 = tmp_path / "h1.webp"; m15 = tmp_path / "m15.webp"
    h1.write_bytes(b"h1"); m15.write_bytes(b"m15")
    markdown = web.build(_markdown(), image_names={"h1_market_map": h1.name, "m15_entry_plan": m15.name}, date_iso="2026-09-04")
    result = web.validate(markdown, filename="btc-daily-2026-09-04.md", image_paths={"h1_market_map": h1, "m15_entry_plan": m15}, date_iso="2026-09-04")
    assert result["ok"] is True
    assert result["frontmatter_keys"] == list(web.ALLOWED_KEYS)
    bad = markdown.replace("author_slug: worldclassbroker-team", "author_slug: wrong")
    with pytest.raises(ValueError, match="author_slug"):
        web.validate(bad, filename="btc-daily-2026-09-04.md", image_paths={"h1_market_map": h1, "m15_entry_plan": m15}, date_iso="2026-09-04")
