from datetime import datetime, timedelta

from PIL import Image

from tools import style_m_v6_renderer, style_m_v6_story


def rows_fixture(count=96):
    start = datetime(2026, 8, 27, 11, tzinfo=style_m_v6_story.BANGKOK)
    rows = []
    for index in range(count):
        price = 100 + (index % 7) * 0.15
        rows.append({"at": (start + timedelta(hours=index)).strftime("%Y-%m-%d %H:%M:%S"),
                     "open": price, "high": price + 1.2, "low": price - 1.0,
                     "close": price + 0.2})
    return rows


def test_render_is_1920x1080(tmp_path):
    prepared = style_m_v6_story.build(rows_fixture(), cutoff=datetime(2026, 8, 31, 11, tzinfo=style_m_v6_story.BANGKOK), source_label="fixture")
    target = tmp_path / "btc.webp"
    result = style_m_v6_renderer.render(prepared["story"], prepared["rows"], target)
    assert result["width"] == 1920 and result["height"] == 1080
    with Image.open(target) as image:
        assert image.size == (1920, 1080)
        assert image.format == "WEBP"
