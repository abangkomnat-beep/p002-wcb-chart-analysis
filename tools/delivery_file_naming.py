"""Stable final-delivery names for P002 article packages.

Candidate work keeps its writer-oriented paths.  This module names only the
files the reader receives, so a rerun cannot depend on filesystem ordering.
"""
from __future__ import annotations

import re


_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_CODE = re.compile(r"[A-Z]{2}")
_STYLE = re.compile(r"[A-Z]")
_ASSET = re.compile(r"[A-Z][A-Z0-9_]*")
_IMAGE = re.compile(r"[A-Za-z0-9_-]+\.webp")


class DeliveryNamingError(ValueError):
    pass


def _validate(day: str, country: str, style: str, asset: str) -> tuple[str, str, str, str]:
    if not isinstance(day, str) or not _DAY.fullmatch(day):
        raise DeliveryNamingError("source_business_date must be YYYY-MM-DD")
    if not isinstance(country, str) or not _CODE.fullmatch(country.upper()):
        raise DeliveryNamingError("country must be a two-letter uppercase code")
    if not isinstance(style, str) or not _STYLE.fullmatch(style.upper()):
        raise DeliveryNamingError("style must be one uppercase letter")
    if not isinstance(asset, str) or not _ASSET.fullmatch(asset.upper()):
        raise DeliveryNamingError("asset must be a canonical uppercase symbol")
    return day.replace("-", ""), country.upper(), style.upper(), asset.upper()


def article_stem(day: str, country: str, style: str, asset: str) -> str:
    compact, country, style, asset = _validate(day, country, style, asset)
    return f"P002-{compact}-{country}-{style}-{asset}"


def article_name(day: str, country: str, style: str, asset: str) -> str:
    return article_stem(day, country, style, asset) + "-article.md"


def _role(original_name: str, asset: str) -> str:
    if not isinstance(original_name, str) or not _IMAGE.fullmatch(original_name):
        raise DeliveryNamingError("image name must be a safe WebP filename")
    role = original_name[:-5].lower()
    role = re.sub(r"(?:^|-)(?:" + re.escape(asset.lower()) + r"|btc|wti)(?:-|$)", "-", role)
    # The delivery prefix already carries the business date.  Chart source
    # names may contain one or two historical candle/calendar dates, neither
    # of which should make the final role hard to search.
    role = re.sub(r"20\d{2}-\d{2}-\d{2}", "", role)
    role = re.sub(r"-+", "-", role).strip("-")
    return role or "chart"


def image_name(day: str, country: str, style: str, asset: str, ordinal: int, original_name: str) -> str:
    if not isinstance(ordinal, int) or ordinal < 1 or ordinal > 99:
        raise DeliveryNamingError("image ordinal must be 1..99")
    stem = article_stem(day, country, style, asset)
    _, _, _, canonical_asset = _validate(day, country, style, asset)
    return f"{stem}-img{ordinal:02d}-{_role(original_name, canonical_asset)}.webp"
