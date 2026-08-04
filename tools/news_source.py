"""ชั้นข่าวของช่วง ② ปัจจัยจับตา — ลำดับแหล่ง เว็บ WCB มาก่อนเสมอ

ลำดับตามคำสั่งหัวหน้าผู้ใช้ 2026-08-04:

    1. wcb_site      ข่าวจากเว็บของเราเอง          — ใช้ก่อนเสมอเมื่อมีข่าวของสินทรัพย์นั้น
    2. worldmonitor  API ของ worldmonitor.app      — ใช้เมื่อเว็บเราไม่มีข่าวของสินทรัพย์นั้น
    3. public_rss    RSS สาธารณะด้วยคำค้นของเราเอง — ทางสำรองสุดท้ายเมื่อสองชั้นบนใช้ไม่ได้

ต่างจากชั้นราคาตรงที่ **ข่าวล้มไม่หยุดสายท่อ** — Voice Spec ข้อ 2 ช่วง ② กำหนดว่า
ไม่มีข่าวที่ยืนยันได้ = ตัดช่วงนั้นทิ้งเงียบ ๆ ห้ามเขียนประโยคแก้ตัว บทความยังออกได้ตามปกติ
แต่ทุกครั้งที่ตัด ต้องบันทึกเหตุผลไว้ฝั่ง internal เพื่อให้ตรวจย้อนได้ว่าเงียบเพราะอะไร

ข่าวที่ผ่านต้องมีครบ 4 อย่าง: หัวข้อ · ชื่อสำนักข่าว · ลิงก์ · เวลาเผยแพร่
ขาดข้อใดข้อหนึ่ง = ทิ้งทั้งชิ้น ไม่ใช่เติมค่าว่างแล้วปล่อยผ่าน (fail-closed เหมือนด่านอื่น)
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

CONFIG_PATH = _REPO_ROOT / "config" / "news_sources.json"

USER_AGENT = "WCB-P002-news/1.0 (+internal analysis)"
HTTP_TIMEOUT = 30

PROVIDER_WCB = "wcb_site"
PROVIDER_WORLDMONITOR = "worldmonitor"
PROVIDER_RSS = "public_rss"


class NewsProviderUnavailable(Exception):
    """แหล่งข่าวชั้นนั้นใช้ไม่ได้รอบนี้ — ไม่ใช่ข้อผิดพลาดร้ายแรง ให้ไล่ไปชั้นถัดไป"""


# ------------------------------------------------------------------ การอ่าน config

def load_config(path: Path | None = None) -> dict:
    return json.loads((path or CONFIG_PATH).read_text(encoding="utf-8"))


def provider_config(config: dict, provider_id: str) -> dict:
    for item in config["providers"]:
        if item["id"] == provider_id:
            return item
    raise KeyError(f"ไม่พบ provider '{provider_id}' ใน news_sources.json")


# ------------------------------------------------------------------ เครื่องมือร่วม

def _http_get(url: str, *, headers: dict | None = None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise NewsProviderUnavailable(f"เรียก {url} ไม่สำเร็จ — {exc}") from exc


def parse_published(value) -> datetime | None:
    """รับได้ทั้งรูป RFC 2822 (RSS) และ ISO 8601 (JSON) — อ่านไม่ออกคืน None แล้วให้ทิ้งชิ้นนั้น"""
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_title(title: str) -> str:
    """ตัดหางชื่อสำนักข่าวและช่องว่างซ้ำ เพื่อใช้เทียบว่าเป็นข่าวชิ้นเดียวกันหรือไม่"""
    text = re.sub(r"\s+", " ", title or "").strip()
    text = re.sub(r"\s+[-–—|]\s+[^-–—|]{1,40}$", "", text)
    return text.lower()


def _clean_item(raw: dict, *, provider: str, require_fields) -> dict | None:
    published = parse_published(raw.get("published_at"))
    item = {
        "title": (raw.get("title") or "").strip(),
        "source": (raw.get("source") or "").strip(),
        "link": (raw.get("link") or "").strip(),
        "published_at": published.isoformat() if published else "",
        "provider": provider,
    }
    if any(not item.get(field) for field in require_fields):
        return None
    return item


# ------------------------------------------------------------------ ชั้นที่ 1 — เว็บ WCB

def fetch_wcb(settings: dict, asset_config: dict, *, require_fields) -> list[dict]:
    """ข่าวจากเว็บของเราเอง — ลำดับ 1 เสมอ

    รับได้สองทาง: endpoint แบบ HTTP (ของจริง) หรือ local_file (ไฟล์ JSON ไว้ทดสอบ)
    รูปแบบที่รอจากทีมเว็บคือ list ของ object ที่มีคีย์ title / source / link / published_at
    หรือห่อไว้ใน {"items": [...]} ก็ได้
    """
    if not settings.get("enabled", True):
        raise NewsProviderUnavailable("ปิดใช้งานไว้ใน config")
    local_file = settings.get("local_file")
    endpoint = settings.get("endpoint")
    if local_file:
        path = Path(local_file)
        if not path.is_absolute():
            path = _REPO_ROOT / path
        if not path.exists():
            raise NewsProviderUnavailable(f"ไม่พบไฟล์ข่าวของเว็บเราที่ {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
    elif endpoint:
        payload = json.loads(_http_get(endpoint).decode("utf-8"))
    else:
        raise NewsProviderUnavailable(
            "ยังไม่ได้ตั้ง endpoint ของเว็บ WCB — รอสเปกจากทีมเว็บ")

    rows = payload.get("items", payload) if isinstance(payload, dict) else payload
    items = []
    for raw in rows or []:
        clean = _clean_item(raw, provider=PROVIDER_WCB, require_fields=require_fields)
        if clean:
            clean["language"] = raw.get("language") or settings.get("language") or "th"
            if raw.get("assets"):
                clean["assets"] = list(raw["assets"])
            items.append(clean)
    return items


# ------------------------------------------------------------------ ชั้นที่ 2 — worldmonitor

def fetch_worldmonitor(settings: dict, asset_config: dict, *, require_fields) -> list[dict]:
    """digest ข่าวจาก worldmonitor — ใช้ผ่าน API เท่านั้น ไม่ได้คัดลอกโค้ดของเขาเข้ารีโปนี้

    ชี้ base_url ไป instance ที่เรา self-host เองก็ได้ ถ้าไม่อยากพึ่งบริการของเขา
    """
    if not settings.get("enabled", True):
        raise NewsProviderUnavailable("ปิดใช้งานไว้ใน config")
    api_key = os.environ.get(settings.get("api_key_env") or "", "")
    base_url = (settings.get("base_url") or "").rstrip("/")
    if not base_url:
        raise NewsProviderUnavailable("ไม่ได้ตั้ง base_url")
    is_hosted = "worldmonitor.app" in base_url
    if is_hosted and not api_key:
        raise NewsProviderUnavailable(
            f"บริการที่โฮสต์ไว้ต้องมีคีย์ในตัวแปรสภาพแวดล้อม {settings.get('api_key_env')}")

    query = urllib.parse.urlencode({"variant": settings.get("variant") or "finance"})
    url = f"{base_url}{settings.get('rest_path') or '/api/news/v1/list-feed-digest'}?{query}"
    headers = {"X-WorldMonitor-Key": api_key} if api_key else {}
    payload = json.loads(_http_get(url, headers=headers).decode("utf-8"))

    wanted = set(asset_config.get("worldmonitor_categories") or [])
    generated_at = payload.get("generatedAt")
    items = []
    for category, bucket in (payload.get("categories") or {}).items():
        if wanted and category not in wanted:
            continue
        for entry in bucket.get("items") or []:
            clean = _clean_item(
                {
                    "title": entry.get("title"),
                    "source": entry.get("source"),
                    "link": entry.get("link"),
                    "published_at": entry.get("publishedAt") or generated_at,
                },
                provider=PROVIDER_WORLDMONITOR, require_fields=require_fields,
            )
            if clean:
                clean["language"] = settings.get("language") or "en"
                clean["category"] = category
                # คะแนนของ worldmonitor คือคุณค่าที่แท้จริงของชั้นนี้ — เก็บไว้ใช้จัดอันดับ
                clean["importance"] = entry.get("importanceScore")
                clean["corroboration"] = entry.get("corroborationCount")
                items.append(clean)
    return items


# ------------------------------------------------------------------ ชั้นที่ 3 — RSS สาธารณะ

def fetch_rss(settings: dict, asset_config: dict, *, require_fields) -> list[dict]:
    """ทางสำรองที่ไม่ต้องพึ่งใคร — คุณภาพต่ำกว่าเพราะไม่มีคะแนนความสำคัญและไม่ยุบข่าวซ้ำให้"""
    if not settings.get("enabled", True):
        raise NewsProviderUnavailable("ปิดใช้งานไว้ใน config")
    query = asset_config.get("rss_query")
    if not query:
        raise NewsProviderUnavailable("สินทรัพย์นี้ยังไม่ได้ตั้งคำค้น rss_query")
    url = ("https://news.google.com/rss/search?q="
           + urllib.parse.quote(query, safe="")
           + "&hl=en-US&gl=US&ceid=US:en")
    try:
        root = ET.fromstring(_http_get(url))
    except ET.ParseError as exc:
        raise NewsProviderUnavailable(f"อ่าน RSS ไม่ออก — {exc}") from exc

    items = []
    for node in root.findall(".//item"):
        title = node.findtext("title") or ""
        source = (node.findtext("source") or "").strip()
        if not source:
            # Google News ต่อชื่อสำนักข่าวไว้ท้ายหัวข้อด้วยขีดกลาง
            parts = re.split(r"\s+-\s+", title)
            source = parts[-1].strip() if len(parts) > 1 else ""
            title = " - ".join(parts[:-1]).strip() if len(parts) > 1 else title
        clean = _clean_item(
            {"title": title, "source": source, "link": node.findtext("link"),
             "published_at": node.findtext("pubDate")},
            provider=PROVIDER_RSS, require_fields=require_fields,
        )
        if clean:
            clean["language"] = settings.get("language") or "en"
            items.append(clean)
    return items


FETCHERS = {
    "wcb": fetch_wcb,
    "worldmonitor": fetch_worldmonitor,
    "rss": fetch_rss,
}


# ------------------------------------------------------------------ คัดกรองและจับประเด็น

def is_relevant(item: dict, asset_config: dict, asset: str | None = None) -> bool:
    """ข่าวชิ้นนี้เกี่ยวกับสินทรัพย์นี้หรือไม่

    ถ้าต้นทางติดป้ายสินทรัพย์มาให้แล้ว (เว็บเราทำได้) ให้เชื่อป้าย ไม่ต้องเดาจากคำในพาดหัว
    — แม่นกว่าและทำให้ทีมเว็บควบคุมได้เองว่าข่าวชิ้นไหนจะไปโผล่ในบทความตัวไหน
    """
    tagged = item.get("assets")
    if tagged and asset:
        return asset in tagged
    text = f"{item['title']} {item.get('source', '')}".lower()
    if any(bad.lower() in text for bad in asset_config.get("exclude") or []):
        return False
    return any(good.lower() in text for good in asset_config.get("keywords") or [])


def match_theme(item: dict, themes: list[dict], asset: str | None = None) -> dict | None:
    """จับหัวข้อข่าวเข้าประเด็นในพจนานุกรม — จับไม่ได้คืน None แล้วให้ทิ้งชิ้นนั้น

    ตั้งใจให้ deterministic: บทความพูดได้เฉพาะประเด็นที่มีอยู่ในพจนานุกรมซึ่งคนเขียนไว้แล้ว
    ไม่ใช่ให้เครื่องแต่งประโยคเองจากหัวข้อข่าวดิบ (แปลผิดหรือแต่งเกินไม่มีใครจับได้)

    เลือกประเด็นที่คำตรงอยู่ **ต้นหัวข้อที่สุด** ไม่ใช่ประเด็นแรกที่บังเอิญอยู่บนสุดของ config
    เพราะพาดหัวข่าวเอาประเด็นหลักขึ้นก่อนเสมอ ("Gold eases as markets weigh Middle East…"
    ควรได้ตะวันออกกลาง ไม่ใช่คำว่า inflation ที่อยู่ท้ายประโยค)
    """
    text = f" {item['title'].lower()} "
    best = None
    for order, theme in enumerate(themes):
        allowed = theme.get("applies_to")
        if allowed and asset and asset not in allowed:
            continue
        positions = [text.find(token.lower()) for token in theme["match"]]
        hits = [pos for pos in positions if pos >= 0]
        if not hits:
            continue
        candidate = (min(hits), order, theme)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    return best[2] if best else None


UNKNOWN_SOURCE_TIER = 3


def source_tier(source: str, tiers: dict) -> int:
    """สำนักข่าวที่ไม่อยู่ในทะเบียนได้ชั้น 3 — แปลว่า "ยังไม่มีใครตรวจ" ไม่ใช่ "แย่"

    ตั้งใจให้เข้มไว้ก่อน เพราะ RSS สาธารณะปนเว็บรวมข่าวที่ลอกต่อกันมาเยอะมาก
    ถ้าปล่อยผ่าน บทความของเราจะไปอ้างเว็บที่เราเองก็ไม่รู้ว่าใครเขียน
    """
    name = (source or "").strip().lower()
    if not name:
        return UNKNOWN_SOURCE_TIER
    for level in ("1", "2"):
        for known in tiers.get(level) or []:
            if name == known.lower():
                return int(level)
    return UNKNOWN_SOURCE_TIER


def _rank_key(item: dict):
    # ข่าวของเว็บเราเองมาก่อนเสมอ แล้วจึงเรียงตามชั้นสำนักข่าว คะแนนความสำคัญ และความสด
    provider_rank = {PROVIDER_WCB: 0, PROVIDER_WORLDMONITOR: 1, PROVIDER_RSS: 2}
    published = parse_published(item["published_at"])
    return (
        provider_rank.get(item["provider"], 9),
        item.get("source_tier", UNKNOWN_SOURCE_TIER),
        -(item.get("importance") or 0),
        -(item.get("corroboration") or 0),
        -(published.timestamp() if published else 0),
    )


def collect(asset: str, *, config: dict | None = None, now: datetime | None = None,
            fetchers: dict | None = None) -> dict:
    """ไล่แหล่งตามลำดับจนได้ข่าวที่ใช้ได้ แล้วคืนทั้งข่าวและบันทึกว่าแต่ละชั้นเกิดอะไรขึ้น

    คืน dict ที่ใช้เป็นทั้งวัตถุดิบของช่วง ② และหลักฐานฝั่ง internal ในไฟล์เดียวกัน
    """
    config = config or load_config()
    fetchers = fetchers or FETCHERS
    now = now or datetime.now(tz=timezone.utc)
    policy = config["policy"]
    asset_config = (config.get("assets") or {}).get(asset)
    attempts: list[dict] = []

    if asset_config is None:
        return {"asset": asset, "items": [], "provider_used": None,
                "attempts": [{"provider": None, "status": "unconfigured",
                              "detail": f"ยังไม่ได้ตั้งค่าข่าวของ {asset} ใน news_sources.json"}],
                "cut_reason": "asset_not_configured"}

    cutoff = now - timedelta(hours=policy["max_age_hours"])
    themes = config["themes"]
    tiers = config.get("source_tiers") or {}
    max_tier = policy.get("max_source_tier", UNKNOWN_SOURCE_TIER)
    ordered = sorted(config["providers"], key=lambda item: item["priority"])

    for settings in ordered:
        fetcher = fetchers.get(settings["kind"])
        if fetcher is None:
            attempts.append({"provider": settings["id"], "status": "no_fetcher",
                             "detail": f"ไม่รู้จักชนิด {settings['kind']}"})
            continue
        try:
            raw_items = fetcher(settings, asset_config,
                                require_fields=policy["require_fields"])
        except NewsProviderUnavailable as exc:
            attempts.append({"provider": settings["id"], "status": "unavailable",
                             "detail": str(exc)})
            continue

        fresh, seen, rejected_tier = [], set(), 0
        for item in raw_items:
            published = parse_published(item["published_at"])
            if published is None or published < cutoff:
                continue
            if not is_relevant(item, asset_config, asset):
                continue
            # ข่าวของเว็บเราเองไม่ต้องผ่านทะเบียนสำนักข่าว — เราเป็นคนเขียนเอง
            tier = 1 if item["provider"] == PROVIDER_WCB else source_tier(item["source"], tiers)
            if tier > max_tier:
                rejected_tier += 1
                continue
            theme = match_theme(item, themes, asset)
            if theme is None:
                continue
            key = normalize_title(item["title"])
            if key in seen:
                continue
            seen.add(key)
            # ประเด็นเดียวกันส่งผลกับแต่ละสินทรัพย์คนละแบบ — สงครามตะวันออกกลางเป็น
            # "ความต้องการสินทรัพย์ปลอดภัย" สำหรับทอง แต่เป็น "ผลกระทบต่อเศรษฐกิจยุโรป"
            # สำหรับยูโร ค่าเริ่มต้นใช้ signal กลาง แล้วให้ signal_overrides ทับได้รายตัว
            signal = (theme.get("signal_overrides") or {}).get(asset, theme["signal"])
            fresh.append({**item, "source_tier": tier, "theme_id": theme["id"],
                          "event": theme["event"], "signal": signal})

        attempts.append({"provider": settings["id"], "status": "ok",
                         "fetched": len(raw_items), "usable": len(fresh),
                         "rejected_untrusted_source": rejected_tier})
        if len(fresh) >= policy["min_items_to_open_section"]:
            fresh.sort(key=_rank_key)
            # ประเด็นซ้ำกันไม่ต้องเล่าสองรอบ — เก็บชิ้นที่อันดับดีที่สุดของแต่ละประเด็น
            picked, used_themes = [], set()
            for item in fresh:
                if item["theme_id"] in used_themes:
                    continue
                used_themes.add(item["theme_id"])
                picked.append(item)
                if len(picked) >= policy["max_items_in_article"]:
                    break
            return {"asset": asset, "items": picked, "provider_used": settings["id"],
                    "attempts": attempts, "cut_reason": None,
                    "candidates": len(fresh), "collected_at": now.isoformat(timespec="seconds")}

    return {"asset": asset, "items": [], "provider_used": None, "attempts": attempts,
            "cut_reason": "no_usable_news", "collected_at": now.isoformat(timespec="seconds")}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="ทดสอบชั้นข่าวของช่วง ② แยกจากสายท่อ")
    parser.add_argument("--asset", required=True)
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    print(json.dumps(collect(args.asset), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
