"""ZA changes chart presentation, never market values or chart geometry."""
from copy import deepcopy
import hashlib
import re

from PIL import Image, ImageChops
import pytest

from tools import style_m_v7_renderer as renderer
from tests.test_style_m_v7_r6_two_image import _pair


@pytest.mark.parametrize("role", ["h1_market_map", "m15_entry_plan"])
def test_za_preserves_default_and_all_market_pixels(tmp_path, role):
    built, story, facts, m15 = _pair()
    rows = built["rows"] if role == "h1_market_map" else m15
    original_inputs = deepcopy((story, rows, facts))
    source = tmp_path / "source.webp"
    meta = renderer.render_role(story, rows, source, role=role, facts=facts)
    explicit = tmp_path / "explicit.webp"
    renderer.render_role(story, rows, explicit, role=role, facts=facts, locale="th-TH")
    assert source.read_bytes() == explicit.read_bytes()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    translated = tmp_path / "za.webp"
    za = renderer.localize_rendered_time_axis(
        source, meta, translated, expected_source_sha256=digest,
        locale="en-ZA", source_timezone="+07:00")
    with Image.open(source) as before, Image.open(translated) as after:
        region = tuple(za["unchanged_pixel_region"])
        assert ImageChops.difference(before.crop(region), after.crop(region)).getbbox() is None
        assert ImageChops.difference(before, after).getbbox() is not None
    for key in ("price_ticks", "artists", "candles", "entry_bands", "execution_lines",
                "right_labels", "summary_cards", "layout", "watermark"):
        assert meta.get(key) == za.get(key)
    assert za["time_tick_overlap_count"] == 0
    assert all(t["contained_in_canvas"] for t in za["time_ticks"])
    assert all(not re.search("[\u0e00-\u0e7f]", t["label"]) for t in za["time_ticks"])
    assert [t["source_at"] for t in meta["time_ticks"]] == [t["source_at"] for t in za["time_ticks"]]
    assert (story, rows, facts) == original_inputs
    direct = renderer.render_role(story, rows, tmp_path / "direct.webp", role=role,
                                  facts=facts, locale="en-ZA", source_timezone="+07:00")
    assert direct["time_ticks"] == za["time_ticks"]
    with pytest.raises(ValueError, match="new output"):
        renderer.localize_rendered_time_axis(source, meta, translated,
            expected_source_sha256=digest, source_timezone="+07:00")
    with pytest.raises(ValueError, match="hash mismatch"):
        renderer.localize_rendered_time_axis(source, meta, tmp_path / "bad.webp",
            expected_source_sha256="0" * 64, source_timezone="+07:00")
    assert not (tmp_path / "bad.webp").exists()


def test_locale_requires_verified_source_offset_without_converting_time():
    assert renderer._time_text("2026-09-07 12:45:00") == "7 ก.ย. 12:45 น."
    assert renderer._time_text("2026-09-07 12:45:00", locale="en-ZA",
                               source_timezone="+07:00") == "7 Sep 12:45"
    with pytest.raises(ValueError, match="explicit verified"):
        renderer._time_text("2026-09-07 12:45:00", locale="en-ZA")
    with pytest.raises(ValueError, match="offset differs"):
        renderer._time_text("2026-09-07T12:45:00+02:00", locale="en-ZA",
                            source_timezone="+07:00")
    with pytest.raises(ValueError, match="unsupported"):
        renderer._time_text("2026-09-07 12:45:00", locale="xx")
