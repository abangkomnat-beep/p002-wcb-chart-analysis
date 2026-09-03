from datetime import date

from tools import trade_plan_public_adapters, trade_plan_public_contract


def test_canonical_evidence_hash_ignores_runtime_metadata_only():
    base = {"close": 100.0, "evaluated_at": "2026-09-01T00:00:00Z",
            "zones": [{"mean": 99.0, "locked_since": "2026-08-31"}]}
    changed = {"close": 100.0, "evaluated_at": "2026-09-01T00:01:00Z",
               "zones": [{"mean": 99.0, "locked_since": "2026-09-01"}]}
    assert trade_plan_public_adapters.canonical_hash(base) == \
        trade_plan_public_adapters.canonical_hash(changed)


def _scenario(side: str) -> dict:
    if side == "LONG":
        return {
            "side": side, "state": "WAIT_TRIGGER", "trigger": 101.0,
            "entry_low": 101.0, "entry_high": 102.0, "sl": 100.0,
            "tp1": 104.0, "tp2": 106.0, "rr1": 1.0, "rr2": 2.0,
            "valid_until": "2026-09-01T23:59:00+07:00",
            "trigger_rule": "closed_h1_strict_cross",
        }
    return {
        "side": side, "state": "WAIT_TRIGGER", "trigger": 97.0,
        "entry_low": 96.0, "entry_high": 97.0, "sl": 98.0,
        "tp1": 94.0, "tp2": 92.0, "rr1": 1.0, "rr2": 2.0,
        "valid_until": "2026-09-01T23:59:00+07:00",
        "trigger_rule": "closed_h1_strict_cross",
    }


def test_style_m_adapter_projects_existing_oco_facts_without_deriving_levels():
    article = ("# M\n\n## 2. แผนการเทรดรายวัน (Trade Scenarios)\n\n"
               "| รายละเอียด | แผน Long (ฝั่งซื้อ) | แผน Short (ฝั่งขาย) |\n"
               "| :--- | :--- | :--- |\n"
               "| **เงื่อนไข Trigger** | แท่ง H1 ปิดเหนือ **101** | แท่ง H1 ปิดต่ำกว่า **97** |\n"
               "| **โซน Entry (หลัง Retest)** | **101 – 102** | **96 – 97** |\n"
               "| **Stop Loss (SL)** | **100** | **98** |\n"
               "| **Target Price (TP1 / TP2)** | **104 / 106** | **94 / 92** |\n"
               "## 3. จุดสร้างสภาพคล่องและโซนกับดักราคา (Liquidity Pools & Trap Zones)\n\n"
               "RR ยังไม่หัก spread/slippage\n").encode("utf-8")
    story = {
        "latest": {"close": 99.0}, "source_sha256": "a" * 64,
        "cutoff": "2026-08-31T23:59:00+07:00",
        "scenarios": {"long": _scenario("LONG"), "short": _scenario("SHORT")},
    }
    contract = trade_plan_public_adapters.style_m_v6(
        story=story, article_name="btc.md", article_bytes=article)
    contract = trade_plan_public_adapters.bind_article(contract, article)
    report = trade_plan_public_contract.validate(
        contract, article_name="btc.md", article_bytes=article,
        style_id="m_btcusd_h1_visual_daily", asset="btc",
        publish_date=date(2026, 9, 1))
    assert report["status"] == "PASS", report["findings"]
    assert contract["plans"][0]["trigger"]["value"] == 101.0
    assert contract["plans"][1]["take_profit"] == [94.0, 92.0]


def test_style_d_adapter_uses_only_canonical_scenario_levels():
    article = "# D\n\nRR ยังไม่หัก spread/slippage\n".encode("utf-8")
    story = {
        "asset": "xauusd", "current": {"close": 100.0},
        "regime": {"down": False},
        "scenarios": {"up": {
            "trigger": 101.0, "entry_low": 101.0, "entry_high": 102.0,
            "entry_invalidation": 99.0, "targets": [103.0, 106.0],
            "condition": "D1 close above resistance",
            "invalidation": "D1 closes back below resistance",
        }, "down": None},
    }
    contract = trade_plan_public_adapters.style_d(
        story=story, cutoff_at="2026-09-01T11:00:00+07:00",
        article_name="xauusd.md", article_bytes=article)
    article = (article.decode("utf-8").rstrip() + "\n\n"
               + trade_plan_public_adapters.public_plan_block(contract) + "\n").encode("utf-8")
    contract = trade_plan_public_adapters.bind_article(contract, article)
    report = trade_plan_public_contract.validate(
        contract, article_name="xauusd.md", article_bytes=article,
        style_id="d_chart_story", asset="xauusd", publish_date=date(2026, 9, 1))
    assert report["status"] == "PASS", report["findings"]
    assert contract["plans"][0]["entry_zone"] == {"low": 101.0, "high": 102.0}
    assert contract["plans"][0]["take_profit"] == [106.0]
    assert contract["plans"][0]["risk_reward"] == [1.333333]


def test_style_e_adapter_uses_canonical_zone_edge_and_keeps_only_eligible_tp():
    article = ("# E\n\n![กราฟแผน BUY H1 50 แท่งของ XAU/USD "
               "Entry 100–102 Current 101 SL 98 TP1 103 TP2 107]"
               "(xauusd-h1-trade-plan-2026-09-01.webp)\n").encode("utf-8")
    story = {
        "asset": "xauusd", "current": {"close": 101.0},
        "scenarios": {"primary": {
            "side": "buy", "entry_low": 100.0, "entry_high": 102.0,
            "sl": 98.0, "tps": [103.0, 107.0],
            "trigger": 102.0, "trigger_condition": "closed H1 above confirmation",
            "condition": "H1 confirms from canonical Fibonacci zone",
        }, "counter": None},
    }
    contract = trade_plan_public_adapters.style_e(
        story=story, cutoff_at="2026-09-01T11:00:00+07:00",
        article_name="xauusd.md", article_bytes=article)
    contract = trade_plan_public_adapters.bind_article(contract, article)
    report = trade_plan_public_contract.validate(
        contract, article_name="xauusd.md", article_bytes=article,
        style_id="e_indicator", asset="xauusd", publish_date=date(2026, 9, 1))
    assert report["status"] == "PASS", report["findings"]
    leg = contract["plans"][0]
    assert leg["trigger"]["value"] == 102.0
    assert leg["take_profit"] == [107.0]
    assert leg["risk_reward"] == [1.25]


def test_unmapped_d_and_e_inputs_emit_explicit_data_hold_not_fake_levels():
    article = "# diagnostic\n".encode("utf-8")
    for style in ("d_chart_story", "e_indicator"):
        contract = trade_plan_public_adapters.hold(
            style_id=style, asset="xauusd", article_name="xauusd.md",
            article_bytes=article, evidence={"canonical": style},
            reasons=["CANONICAL_FIELDS_MISSING"])
        report = trade_plan_public_contract.validate(
            contract, article_name="xauusd.md", article_bytes=article,
            style_id=style, asset="xauusd", publish_date=date(2026, 9, 1))
        assert contract["qa_status"] == "DATA_HOLD"
        assert contract["plans"] == []
        assert report["status"] == "FAIL"
        assert "HOLD_STATUS_PRESENT" in {item["code"] for item in report["findings"]}
