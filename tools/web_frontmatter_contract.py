"""Canonical web frontmatter enums shared by producers and release gates."""

from __future__ import annotations


WEB_TREND_CODES = ("up", "dn", "fl")
STYLE_L_AUTHOR_SLUG = "worldclassbroker-team"

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
