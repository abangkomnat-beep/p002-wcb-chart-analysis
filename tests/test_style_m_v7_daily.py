import json
import hashlib
from pathlib import Path

from tools import style_m_v7_daily as daily
from tests.test_style_m_v7_adr14 import rows_fixture


def fetch(asset, *, timeframe, outputsize):
    return {"asset": asset, "timeframe": timeframe}, rows_fixture(), "fixed-2026-09-03"


def test_v7_shadow_is_local_and_carries_canonical_manifest(tmp_path):
    result = daily.run_shadow(root=tmp_path, cutoff_at="2026-08-30T00:00:00+07:00", fetcher=fetch)
    assert result["published"] is False
    manifest = Path(result["shadow"]) / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["contract_version"] == "M-PROD/v7"
    assert payload["policy_id"] == "ADR14_F0.50_C1.00_E0.10_R1.50_R2.00"
    assert payload["production_write"] is False
    assert payload["external_publish"] is False
    assert payload["claim_parity"]["contract_version"] == "M-PROD/v7"
    article = Path(result["web_upload"]["path"]) / result["web_upload"]["article"]
    markdown = article.read_text(encoding="utf-8")
    assert markdown.count("## คุณมองตลาดอย่างไร?") == 1
    assert "## อัปเดตจากแผนครั้งก่อน" not in markdown
    candidates = list((tmp_path.parent / "continuity" / "candidates").glob("*.json"))
    matching = [json.loads(path.read_text(encoding="utf-8")) for path in candidates]
    assert any(item["article_hash"] == hashlib.sha256(article.read_bytes()).hexdigest() for item in matching)


def test_v7_shadow_is_deterministic(tmp_path):
    first = daily.run_shadow(root=tmp_path, cutoff_at="2026-08-30T00:00:00+07:00", fetcher=fetch)
    second = daily.run_shadow(root=tmp_path, cutoff_at="2026-08-30T00:00:00+07:00", fetcher=fetch)
    assert first["shadow"] == second["shadow"]
    assert second["idempotent"] is True


def test_v7_preview_decodes_and_has_no_label_overlap(tmp_path):
    result = daily.run_shadow(root=tmp_path, cutoff_at="2026-08-30T00:00:00+07:00", fetcher=fetch)
    image = Path(result["image"])
    from PIL import Image
    with Image.open(image) as decoded:
        assert decoded.size == (1920, 1080)
        decoded.load()
    manifest = json.loads((Path(result["shadow"]) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["renderer"]["label_overlap_count"] == 0
    assert hashlib.sha256(image.read_bytes()).hexdigest() == manifest["files"][image.name]


def test_v7_plan_cards_show_all_canonical_targets(tmp_path):
    result = daily.run_shadow(root=tmp_path, cutoff_at="2026-08-30T00:00:00+07:00", fetcher=fetch)
    manifest = json.loads((Path(result["shadow"]) / "manifest.json").read_text(encoding="utf-8"))
    for card, plan in zip(manifest["renderer"]["plan_cards"], manifest["story"]["scenarios"].values()):
        assert card["tp1"] == plan["tp1"] and card["tp2"] == plan["tp2"]
        if plan["state"] != "NO_PLAN":
            assert any(f"TP1 {plan['tp1']:,.0f}" in text for text in card["visible_text"])
            assert any(f"TP2 {plan['tp2']:,.0f}" in text for text in card["visible_text"])


def test_v7_normal_plan_card_text_is_complete_and_canonical(tmp_path):
    from datetime import datetime
    from tools import style_m_v7_renderer, style_m_v7_risk, style_m_v7_story
    rows = rows_fixture()
    built = style_m_v7_story.build(rows, cutoff=datetime.fromisoformat("2026-08-30T00:00:00+07:00"), source_label="card")
    built["story"]["pivots"] = {"lows": [{"price": 1100}], "highs": [{"price": 930}]}
    migrated = style_m_v7_risk.apply_policy(built["story"], volatility=style_m_v7_risk.adr14(rows, cutoff=datetime.fromisoformat("2026-08-30T00:00:00+07:00")))
    render = style_m_v7_renderer.render(migrated, built["rows"], tmp_path / "card.webp")
    for card, plan in zip(render["plan_cards"], migrated["scenarios"].values()):
        assert plan["state"] != "NO_PLAN"
        assert card["visible_text"] == [
            f"{'BUY' if plan['side'] == 'LONG' else 'SELL'} · Entry {plan['entry_low']:,.0f}–{plan['entry_high']:,.0f}",
            f"SL {plan['sl']:,.0f} · TP1 {plan['tp1']:,.0f} · TP2 {plan['tp2']:,.0f}",
        ]


def test_v7_preserves_v6_editorial_seo_and_exact_chart_header(tmp_path):
    from datetime import datetime
    import re
    from tools import style_m_v7_contract, style_m_v7_renderer, style_m_v7_risk
    from tools import style_m_v7_story, style_m_v7_writer

    rows = rows_fixture()
    cutoff = datetime.fromisoformat("2026-08-30T00:00:00+07:00")
    built = style_m_v7_story.build(rows, cutoff=cutoff, source_label="editorial")
    built["story"]["pivots"] = {"lows": [{"price": 1100}], "highs": [{"price": 930}]}
    story = style_m_v7_risk.apply_policy(
        built["story"], volatility=style_m_v7_risk.adr14(rows, cutoff=cutoff))
    facts = style_m_v7_contract.build(story, built["rows"])
    article = style_m_v7_writer.compose({"story": story, "facts": facts})

    assert re.findall(r"^## (.+)$", article, flags=re.MULTILINE) == list(style_m_v7_writer.H2)
    frontmatter = article.split("---", 2)[1]
    for field in ("excerpt", "author_slug", "country", "language", "asset", "slug"):
        assert re.search(rf"(?m)^{field}:\s*", frontmatter)
    assert "บริบทราคาและอินดิเคเตอร์ชี้วัด" in article
    assert "Liquidity Pools & Trap Zones" not in article
    assert "แผนสำรองกรณีเกิด False Breakout" in article
    assert "OCO" in article
    assert "False Breakout" in article and "ADR14" in article
    assert "H1 ATR" not in article
    assert "ENTRY_ZONE_ATR" not in article and "STOP_BUFFER_ATR" not in article

    render = style_m_v7_renderer.render_role(story, built["rows"], tmp_path / "header.webp",
                                              role="h1_market_map", facts=facts)
    assert render["header_title"] == "BTCUSD · H1 MARKET MAP"
