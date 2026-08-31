from datetime import datetime, timedelta

from tools import style_m_v6_daily, style_m_v6_story


def rows_fixture(count=96):
    start = datetime(2026, 8, 27, 11, tzinfo=style_m_v6_story.BANGKOK)
    rows = []
    for index in range(count):
        price = 100 + (index % 7) * 0.15
        rows.append({"at": (start + timedelta(hours=index)).strftime("%Y-%m-%d %H:%M:%S"),
                     "open": price, "high": price + 1.2, "low": price - 1.0,
                     "close": price + 0.2})
    return rows


def fake_fetcher(asset, *, timeframe, outputsize):
    return {"asset": asset, "timeframe": timeframe}, rows_fixture(), "fixture"


def test_shadow_runner_never_publishes(tmp_path):
    result = style_m_v6_daily.run_shadow(
        root=tmp_path, cutoff_at="2026-08-31T11:00:00+07:00", fetcher=fake_fetcher)
    assert result["published"] is False
    assert result["state"] == "SCENARIOS_READY"
    assert set(result["scenario_states"]) == {"long", "short"}


def test_shadow_rerun_is_idempotent(tmp_path):
    first = style_m_v6_daily.run_shadow(
        root=tmp_path, cutoff_at="2026-08-31T11:00:00+07:00", fetcher=fake_fetcher)
    second = style_m_v6_daily.run_shadow(
        root=tmp_path, cutoff_at="2026-08-31T11:00:00+07:00", fetcher=fake_fetcher)
    assert first["shadow"] == second["shadow"]
    assert second["idempotent"] is True
