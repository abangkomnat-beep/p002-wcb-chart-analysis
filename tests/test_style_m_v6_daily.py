from datetime import datetime, timedelta
import json
import re
from pathlib import Path

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


def fake_news(asset, *, now):
    return {"asset": asset, "provider_status": "ok", "collected_at": now.isoformat(),
            "items": [{"title": "ดัชนี CPI อยู่ที่ 3.2%",
                       "link": "https://example.test/official-cpi",
                       "published_at": "2026-08-31T01:30:00+00:00",
                       "source_tier": 1, "source": "Official"}]}


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


def test_production_prepare_keeps_news_decimal_only(tmp_path):
    prepared = style_m_v6_daily.prepare(
        cutoff_at="2026-08-31T11:00:00+07:00", fetcher=fake_fetcher,
        news_collector=fake_news)
    assert "3.2%" in prepared["markdown"]
    technical = "\n".join(line for line in prepared["markdown"].splitlines()
                            if not line.startswith("**ข่าวที่ต้องติดตาม:**"))
    assert not re.search(r"(?<![A-Za-z0-9])\d[\d,]*\.\d+", technical)
    assert prepared["parity"]["status"] == "PASS"


def test_v6_run_round_writes_atomic_local_production_package(tmp_path):
    publish_root, work_root = tmp_path / "output", tmp_path / "work"
    kwargs = {"asset": "btcusd", "publish_root": publish_root,
              "work_root": work_root, "cutoff_at": "2026-08-31T11:00:00+07:00",
              "fetcher": fake_fetcher, "news_collector": fake_news, "publish": True}
    first = style_m_v6_daily.run_round(**kwargs)
    second = style_m_v6_daily.run_round(**kwargs)
    assert first["published"] is True and first["idempotent"] is False
    assert second["published"] is True and second["idempotent"] is True
    article = Path(first["article"])
    assert article.is_file()
    assert "3.2%" in article.read_text(encoding="utf-8")
    manifest = work_root / "31-08-2026" / "btcusd" / "internal" / "style-m-v6" / "manifest.json"
    evidence = json.loads(manifest.read_text(encoding="utf-8"))
    assert evidence["contract_version"] == "M-PROD/v6"
    assert evidence["production_write"] is True
    assert evidence["external_publish"] is False


def test_v6_same_day_rerun_replaces_stale_public_package(tmp_path):
    publish_root, work_root = tmp_path / "output", tmp_path / "work"
    kwargs = {"asset": "btcusd", "publish_root": publish_root,
              "work_root": work_root, "cutoff_at": "2026-08-31T11:00:00+07:00",
              "fetcher": fake_fetcher, "news_collector": fake_news, "publish": True}
    first = style_m_v6_daily.run_round(**kwargs)
    article = Path(first["article"])
    article.write_text("stale rerun content\n", encoding="utf-8")
    second = style_m_v6_daily.run_round(**kwargs)
    assert second["status"] == "pass"
    assert second["idempotent"] is False
    assert second["replaced_existing"] is True
    assert "stale rerun content" not in article.read_text(encoding="utf-8")
    assert (Path(second["directory"]) / "btc.trade-plan-public.json").is_file()
