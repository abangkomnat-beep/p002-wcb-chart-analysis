"""เทสชั้นฟีดตรงของสำนักข่าว (ชั้นที่ 3 ใหม่ · เพิ่ม 2026-08-04)

เหตุที่เพิ่มชั้นนี้: ชั้นสำรองเดิมพึ่ง Google News 100% ลิงก์ที่ได้จึงเป็นลิงก์เปลี่ยนทาง
ของ Google ซึ่งฝังลงบทความไม่ได้และหมดอายุได้ · ชั้นใหม่ดึงจากฟีดของสำนักข่าวตรง

สิ่งที่เทสชุดนี้ล็อกไว้:
- ลำดับชั้น: ฟีดตรงต้องมาก่อน Google News เสมอ
- **ชื่อสำนักข่าวเอาจากโดเมนของลิงก์จริง** ไม่ใช่ชื่อฟีด — กันฟีดรวมข่าวอ้างผิดตัว
- ฟีดล้มบางตัวไม่ทำให้ทั้งชั้นล้ม · ล้มครบทุกตัวจึงไหลไปชั้นถัดไป
- อ่านได้ทั้ง RSS 2.0 และ Atom
- ทะเบียนใน config ต้องสอดคล้องกันเอง (ชื่อสำนักข่าวอยู่ในทะเบียนชั้น · feed id มีจริง)
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import news_source  # noqa: E402


NOW = datetime(2026, 8, 4, 4, 0, tzinfo=timezone.utc)
REQUIRE = ["title", "source", "link", "published_at"]


def rss_bytes(entries) -> bytes:
    items = "".join(
        f"<item><title>{title}</title><link>{link}</link>"
        f"<pubDate>{(NOW - timedelta(hours=2)).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>"
        "</item>"
        for title, link in entries)
    return f"<rss version='2.0'><channel>{items}</channel></rss>".encode("utf-8")


def atom_bytes(entries) -> bytes:
    items = "".join(
        f"<entry><title>{title}</title><link href='{link}'/>"
        f"<published>{(NOW - timedelta(hours=2)).isoformat()}</published></entry>"
        for title, link in entries)
    return (f"<feed xmlns='http://www.w3.org/2005/Atom'>{items}</feed>").encode("utf-8")


SETTINGS = {
    "enabled": True,
    "language": "en",
    "feeds": {
        "good": {"url": "https://feeds.example/good", "source": "CNBC"},
        "atom": {"url": "https://feeds.example/atom", "source": "Reuters"},
        "aggregator": {"url": "https://feeds.example/agg", "source": "Yahoo Finance",
                       "syndicated": True},
        "broken": {"url": "https://feeds.example/broken", "source": "CNBC"},
    },
    "publisher_domains": {"cnbc.com": "CNBC", "reuters.com": "Reuters",
                          "fool.com": "The Motley Fool"},
}


class PublisherFromLink(unittest.TestCase):
    domains = {"cnbc.com": "CNBC", "theblock.co": "The Block"}

    def test_จับโดเมนตรงและตัด_www_ออก(self):
        self.assertEqual(
            news_source.publisher_from_link("https://www.cnbc.com/a", self.domains), "CNBC")

    def test_จับโดเมนย่อยได้(self):
        self.assertEqual(
            news_source.publisher_from_link("https://feeds.cnbc.com/a", self.domains), "CNBC")

    def test_โดเมนที่คล้ายกันแต่ไม่ใช่ต้องไม่ผ่าน(self):
        """notcnbc.com ต้องไม่ถูกอ่านเป็น cnbc.com — ไม่งั้นเว็บลอกข่าวสวมชื่อได้"""
        self.assertIsNone(news_source.publisher_from_link("https://notcnbc.com/a", self.domains))

    def test_โดเมนนอกทะเบียนคืน_None(self):
        self.assertIsNone(news_source.publisher_from_link("https://ใครก็ไม่รู้.com/a", self.domains))

    def test_ลิงก์ว่างคืน_None(self):
        self.assertIsNone(news_source.publisher_from_link("", self.domains))


class FetchDirectRss(unittest.TestCase):
    def _fetch(self, feeds, responses):
        def fake_get(url, headers=None):
            payload = responses.get(url)
            if payload is None:
                raise news_source.NewsProviderUnavailable(f"เรียก {url} ไม่สำเร็จ")
            return payload

        with mock.patch.object(news_source, "_http_get", side_effect=fake_get):
            return news_source.fetch_direct_rss(
                SETTINGS, {"direct_feeds": feeds}, require_fields=REQUIRE)

    def test_อ่าน_rss_ได้และติดป้ายสำนักข่าวจากโดเมน(self):
        items = self._fetch(["good"], {
            "https://feeds.example/good": rss_bytes([("ข่าวหนึ่ง", "https://www.cnbc.com/x")])})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "CNBC")
        self.assertEqual(items[0]["provider"], news_source.PROVIDER_RSS_DIRECT)
        self.assertEqual(items[0]["feed_id"], "good")

    def test_อ่าน_atom_ได้ด้วย(self):
        items = self._fetch(["atom"], {
            "https://feeds.example/atom": atom_bytes([("ข่าว", "https://reuters.com/y")])})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["link"], "https://reuters.com/y")
        self.assertEqual(items[0]["source"], "Reuters")

    def test_ฟีดรวมข่าวติดป้ายตามเจ้าของบทความจริงไม่ใช่ชื่อฟีด(self):
        """เจอจริง 2026-08-04 — ลิงก์ NVDA จากฟีด Yahoo ชี้ไป fool.com"""
        items = self._fetch(["aggregator"], {
            "https://feeds.example/agg": rss_bytes([("ข่าว", "https://www.fool.com/z")])})
        self.assertEqual(items[0]["source"], "The Motley Fool")

    def test_ฟีดรวมข่าวทิ้งชิ้นที่โดเมนไม่รู้จัก(self):
        """ไม่รู้ว่าใครเขียน = ทิ้ง ดีกว่าอ้างชื่อฟีดแล้วกลายเป็นอ้างผิดตัว"""
        items = self._fetch(["aggregator"], {
            "https://feeds.example/agg": rss_bytes([("ข่าว", "https://เว็บไม่รู้จัก.com/z")])})
        self.assertEqual(items, [])

    def test_ฟีดไม่รวมข่าวยังใช้ชื่อฟีดได้เมื่อโดเมนไม่อยู่ในทะเบียน(self):
        items = self._fetch(["good"], {
            "https://feeds.example/good": rss_bytes([("ข่าว", "https://cnbc.co.uk/x")])})
        self.assertEqual(items[0]["source"], "CNBC")

    def test_ฟีดล้มบางตัวไม่ทำให้ทั้งชั้นล้ม(self):
        items = self._fetch(["broken", "good"], {
            "https://feeds.example/good": rss_bytes([("ข่าว", "https://cnbc.com/x")])})
        self.assertEqual(len(items), 1)

    def test_ล้มครบทุกตัวจึงถือว่าชั้นนี้ใช้ไม่ได้(self):
        with self.assertRaises(news_source.NewsProviderUnavailable):
            self._fetch(["broken"], {})

    def test_สินทรัพย์ที่ยังไม่ตั้ง_direct_feeds_ถือว่าชั้นนี้ใช้ไม่ได้(self):
        with mock.patch.object(news_source, "_http_get"):
            with self.assertRaises(news_source.NewsProviderUnavailable):
                news_source.fetch_direct_rss(SETTINGS, {}, require_fields=REQUIRE)

    def test_xml_เสียถือว่าฟีดนั้นล้มไม่ใช่ทั้งโปรแกรมล้ม(self):
        with self.assertRaises(news_source.NewsProviderUnavailable):
            self._fetch(["good"], {"https://feeds.example/good": b"<rss><broken>"})


class LayerOrder(unittest.TestCase):
    def test_ฟีดตรงมาก่อน_google_news_เสมอ(self):
        config = news_source.load_config()
        priority = {item["id"]: item["priority"] for item in config["providers"]}
        self.assertLess(priority["direct_rss"], priority["public_rss"])

    def test_ข่าวจากฟีดตรงจัดอันดับสูงกว่าข่าวจาก_google_news(self):
        direct = {"provider": news_source.PROVIDER_RSS_DIRECT, "published_at": NOW.isoformat(),
                  "source_tier": 2}
        google = {"provider": news_source.PROVIDER_RSS, "published_at": NOW.isoformat(),
                  "source_tier": 1}
        self.assertLess(news_source._rank_key(direct), news_source._rank_key(google))


class ConfigIsSelfConsistent(unittest.TestCase):
    """ทะเบียนใน config สะกดผิดแล้วข่าวจะถูกทิ้งเงียบ ๆ — เคยเกิดมาแล้วกับชื่อหมวด worldmonitor"""

    @classmethod
    def setUpClass(cls):
        cls.config = news_source.load_config()
        cls.settings = news_source.provider_config(cls.config, "direct_rss")

    def test_ชื่อสำนักข่าวของทุกฟีดอยู่ในทะเบียนชั้นที่อ้างได้(self):
        tiers = self.config["source_tiers"]
        max_tier = self.config["policy"]["max_source_tier"]
        for feed_id, feed in self.settings["feeds"].items():
            with self.subTest(feed=feed_id):
                tier = news_source.source_tier(feed["source"], tiers)
                self.assertLessEqual(
                    tier, max_tier,
                    f"'{feed['source']}' ไม่อยู่ในทะเบียนชั้น {max_tier} — ข่าวทั้งฟีดจะถูกทิ้ง")

    def test_ชื่อในทะเบียนโดเมนก็ต้องอยู่ในทะเบียนชั้นเช่นกัน(self):
        tiers = self.config["source_tiers"]
        max_tier = self.config["policy"]["max_source_tier"]
        for domain, name in self.settings["publisher_domains"].items():
            with self.subTest(domain=domain):
                self.assertLessEqual(news_source.source_tier(name, tiers), max_tier,
                                     f"โดเมน {domain} ชี้ไปชื่อ '{name}' ที่ไม่อยู่ในทะเบียนชั้น")

    def test_ทุก_feed_id_ที่สินทรัพย์อ้างถึงมีอยู่จริงในทะเบียน(self):
        registry = self.settings["feeds"]
        for asset, asset_config in self.config["assets"].items():
            for feed_id in asset_config.get("direct_feeds") or []:
                with self.subTest(asset=asset, feed=feed_id):
                    self.assertIn(feed_id, registry,
                                  f"{asset} อ้างฟีด '{feed_id}' ที่ไม่มีในทะเบียน")

    def test_ทุกสินทรัพย์ต้องมีฟีดตรงอย่างน้อยสองตัว(self):
        """ตัวเดียวคือจุดล้มเดียว — ชั้นนี้มีไว้เลิกพึ่งแหล่งเดียวตั้งแต่แรก"""
        for asset, asset_config in self.config["assets"].items():
            with self.subTest(asset=asset):
                self.assertGreaterEqual(len(asset_config.get("direct_feeds") or []), 2)

    def test_ทุก_url_ในทะเบียนเป็น_https(self):
        for feed_id, feed in self.settings["feeds"].items():
            with self.subTest(feed=feed_id):
                self.assertTrue(feed["url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
