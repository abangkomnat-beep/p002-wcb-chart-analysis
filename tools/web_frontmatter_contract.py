"""Canonical web frontmatter enums shared by producers and release gates."""

from __future__ import annotations


WEB_TREND_CODES = ("up", "dn", "fl")
PERSONAL_AUTHOR_SLUG = "natthaphon-s"
TEAM_AUTHOR_SLUG = "worldclassbroker-team"
PERSONAL_AUTHOR_ASSETS = frozenset({"xauusd", "wtiusd"})
ASSET_ALIASES = {"btc": "btcusd"}
STYLE_L_AUTHOR_SLUG = TEAM_AUTHOR_SLUG  # compatibility name for Style L callers


def canonical_asset(asset: str) -> str:
    """Normalize public asset aliases before applying the author policy."""
    key = str(asset or "").strip().lower()
    return ASSET_ALIASES.get(key, key)


def author_slug_for(asset: str) -> str:
    """Return the only allowed web author for a canonical or aliased asset."""
    return (PERSONAL_AUTHOR_SLUG
            if canonical_asset(asset) in PERSONAL_AUTHOR_ASSETS
            else TEAM_AUTHOR_SLUG)

_DIRECTION_TO_WEB_TREND = {
    "up": "up",
    "down": "dn",
    None: "fl",
}

_PUBLIC_SIDE_TO_WEB_TREND = {
    "BUY": "up",
    "SELL": "dn",
    "OCO": "fl",
}


def trend_from_direction(direction: str | None) -> str:
    """Translate an internal market direction into the website enum."""
    try:
        return _DIRECTION_TO_WEB_TREND[direction]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"internal direction ใช้ทำ web trend ไม่ได้: {direction!r}") from exc


def trend_from_public_side(side: str) -> str:
    """Derive the website enum from a validated public-plan side."""
    try:
        return _PUBLIC_SIDE_TO_WEB_TREND[side]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"public side ใช้ทำ web trend ไม่ได้: {side!r}") from exc
