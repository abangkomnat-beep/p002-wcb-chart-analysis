"""Single source of truth for the P002 daily source lanes.

The selector is read-only.  It describes which source articles must exist for
a Bangkok business date; callers still perform source and delivery gates.
"""
from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

TIMEZONE = "Asia/Bangkok"

# style, asset, country-first source folder, final article filename template
_COUNTRY_LANES = {
    ("D", "XAUUSD"): ("TH-Thailand/D/XAUUSD", "P002-{datecompact}-TH-D-XAUUSD-article.md"),
    ("D", "WTIUSD"): ("TH-Thailand/D/WTIUSD", "P002-{datecompact}-TH-D-WTIUSD-article.md"),
    ("E", "XAUUSD"): ("TH-Thailand/E/XAUUSD", "P002-{datecompact}-TH-E-XAUUSD-article.md"),
    ("L", "EURUSD"): ("TH-Thailand/L/EURUSD", "P002-{datecompact}-TH-L-EURUSD-article.md"),
    ("L", "USDJPY"): ("TH-Thailand/L/USDJPY", "P002-{datecompact}-TH-L-USDJPY-article.md"),
    ("L", "GBPUSD"): ("TH-Thailand/L/GBPUSD", "P002-{datecompact}-TH-L-GBPUSD-article.md"),
    ("L", "AUDUSD"): ("TH-Thailand/L/AUDUSD", "P002-{datecompact}-TH-L-AUDUSD-article.md"),
    ("L", "USDCAD"): ("TH-Thailand/L/USDCAD", "P002-{datecompact}-TH-L-USDCAD-article.md"),
    ("M", "BTCUSD"): ("TH-Thailand/M/BTCUSD", "P002-{datecompact}-TH-M-BTCUSD-article.md"),
}

# Kept only for the one-off historical migration tool.  New production and
# source-QA callers must use the country-first mapping above.
_LEGACY_LANES = {
    ("D", "XAUUSD"): ("D-โครงสร้างกราฟ", "xauusd.md"),
    ("D", "WTIUSD"): ("D-โครงสร้างกราฟ", "wtiusd.md"),
    ("E", "XAUUSD"): ("E-อินดิเคเตอร์", "xauusd.md"),
    ("L", "EURUSD"): ("L-Forex-Daily", "eurusd.md"),
    ("L", "USDJPY"): ("L-Forex-Daily", "usdjpy.md"),
    ("L", "GBPUSD"): ("L-Forex-Daily", "gbpusd.md"),
    ("L", "AUDUSD"): ("L-Forex-Daily", "audusd.md"),
    ("L", "USDCAD"): ("L-Forex-Daily", "usdcad.md"),
    ("M", "BTCUSD"): ("M-BTCUSD-H1-Visual-Daily", "btc-daily-{date}.md"),
}

_NON_FOREX = {
    0: (("D", "XAUUSD"), ("D", "WTIUSD"), ("E", "XAUUSD"), ("M", "BTCUSD")),
    1: (("E", "XAUUSD"), ("M", "BTCUSD")),
    2: (("E", "XAUUSD"), ("M", "BTCUSD")),
    3: (("E", "XAUUSD"), ("M", "BTCUSD")),
    4: (("E", "XAUUSD"), ("M", "BTCUSD")),
}
_SCHEDULE_PATH = Path(__file__).resolve().parents[1] / "config" / "forex_daily_schedule.json"
_FOREX_ASSETS = frozenset({"EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD"})


def _forex_keys(schedule_path: Path = _SCHEDULE_PATH) -> dict[int, tuple[tuple[str, str], ...]]:
    try:
        raw = json.loads(Path(schedule_path).read_text(encoding="utf-8"))
        if raw.get("timezone") != TIMEZONE or raw.get("weekend_policy") != "skip":
            raise ValueError("Forex schedule timezone/weekend policy is invalid")
        batches = raw["weekday_asset_batches"]
        if not isinstance(batches, dict) or set(batches) != {str(day) for day in range(5)}:
            raise ValueError("Forex schedule must define exactly Monday through Friday")
        result = {}
        for weekday in range(5):
            assets = batches[str(weekday)]
            if (not isinstance(assets, list) or len(assets) != 2
                    or any(not isinstance(asset, str) for asset in assets)):
                raise ValueError("Forex schedule must contain exactly two string assets per weekday")
            normalized = tuple(asset.upper() for asset in assets)
            if len(set(normalized)) != 2 or any(asset not in _FOREX_ASSETS for asset in normalized):
                raise ValueError("Forex schedule contains duplicate or unsupported assets")
            result[weekday] = tuple(("L", asset) for asset in normalized)
        return result
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SourceSelectorError(f"cannot load Forex schedule: {exc}") from exc


class SourceSelectorError(ValueError):
    pass


def _parse(day: str) -> date:
    try:
        return date.fromisoformat(day)
    except (TypeError, ValueError) as exc:
        raise SourceSelectorError("date must be YYYY-MM-DD") from exc


def source_keys_for_date(source_business_date: str) -> tuple[tuple[str, str], ...]:
    """Return exact expected (style, asset) keys; weekends return no lanes."""
    weekday = _parse(source_business_date).weekday()
    if weekday >= 5:
        return ()
    return _NON_FOREX[weekday] + _forex_keys()[weekday]


def lanes_for_date(source_business_date: str) -> tuple[tuple[str, str, str, str], ...]:
    """Return the country-first source mapping used by production and source QA."""
    compact = _parse(source_business_date).strftime("%Y%m%d")
    return tuple((style, asset, _COUNTRY_LANES[(style, asset)][0],
                  _COUNTRY_LANES[(style, asset)][1].format(datecompact=compact))
                 for style, asset in source_keys_for_date(source_business_date))


def legacy_lanes_for_date(source_business_date: str) -> tuple[tuple[str, str, str, str], ...]:
    """Return pre-country paths only when importing a historical delivery."""
    return tuple((style, asset, *_LEGACY_LANES[(style, asset)])
                 for style, asset in source_keys_for_date(source_business_date))


def expected_count(source_business_date: str) -> int:
    return len(source_keys_for_date(source_business_date))


def is_weekend(source_business_date: str) -> bool:
    return _parse(source_business_date).weekday() >= 5


def bangkok_business_date(moment: datetime | None = None) -> str:
    """Resolve the orchestration date at the one supported time-zone boundary."""
    if moment is None:
        moment = datetime.now(ZoneInfo(TIMEZONE))
    elif moment.tzinfo is None:
        raise SourceSelectorError("orchestration datetime must be timezone-aware")
    return moment.astimezone(ZoneInfo(TIMEZONE)).date().isoformat()


def source_keys_for_moment(moment: datetime | None = None) -> tuple[tuple[str, str], ...]:
    return source_keys_for_date(bangkok_business_date(moment))
