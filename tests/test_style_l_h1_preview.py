from __future__ import annotations

from tests.test_style_l_h1_engine import _buy_fixture
from tools import style_l_h1_preview


def test_preview_adapter_is_explicitly_non_production():
    preview = style_l_h1_preview.build_preview({
        "asset": "eurusd",
        "h4_bias": "up",
        "decision_at": "2026-09-05T00:00:00+00:00",
        "atr14": 0.01,
        "h1_rows": _buy_fixture(),
        "h4_rows": [],
    })
    assert preview["phase"] == "PHASE_1_CONTRACT_PROTOTYPE"
    assert preview["production_wired"] is False
    assert preview["visual_status"] == "PLACEHOLDER_HOLD_NOT_B3"
    assert preview["plan"]["public_timeframe"] == "H4-H1"
    assert len(preview["visual_contract"]["panels"]) == 2
    assert "<table>" in preview["public_table"]
    assert preview["public_table"].count("<th>") == 6
    html = style_l_h1_preview.render_review_html(preview)
    assert "H1 Context" in html and "H1 Execution Zoom" in html
    assert "overflow-x:auto" in html and "min-width:760px" in html
    assert "production_wired=false" in html and "HOLD_DATA_COVERAGE" in html
    assert "PLACEHOLDER_HOLD_NOT_B3" in html
