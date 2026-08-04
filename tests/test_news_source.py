"""เทสชั้นข่าวของช่วง ② และหัวข้อหุ้นรายตัว (ระยะ 3a — คำสั่งผู้ใช้ 2026-08-04)

สิ่งที่เทสชุดนี้ล็อกไว้:
- ลำดับแหล่ง: เว็บ WCB มาก่อน worldmonitor เสมอ · worldmonitor มาก่อน RSS สาธารณะ
- fail-closed: ข่าวที่ขาด field / เก่าเกิน / สำนักข่าวไม่อยู่ในทะเบียน = ทิ้ง ไม่ใช่ปล่อยผ่าน
- ไม่มีข่าว = ตัดช่วง ② เงียบ บทความยังออกได้ (ต่างจากราคาที่ล้มแล้วต้องหยุดสายท่อ)
- ช่วง ② ห้ามมีตัวเลข เพราะเลขทุกตัวในบทความต้องชี้กลับค่าใน evidence ได้
- หุ้นรายตัว: ปฏิทินตลาดสหรัฐ · เกณฑ์กริยา "แรง" คนละชุดกับ forex · วันที่ในประโยคเปิด
  ต้องเป็นวันของแท่ง ไม่ใช่วันที่รันสายท่อ
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import article_builder, build_daily_package, market_calendar  # noqa: E402
from tools import news_source, voice_rules  # noqa: E402


NOW = datetime(2026, 8, 4, 4, 0, tzinfo=timezone.utc)


def item(title, source="Reuters", hours_ago=3, link="https://example.com/a"):
    published = (NOW - timedelta(hours=hours_ago)).isoformat()
    return {"title": title, "source": source, "link": link, "published_at": published}


def tiny_config(**overrides) -> dict:
    """config ย่อส่วนที่ควบคุมได้ทุกตัวแปร — ไม่แตะไฟล์จริงเพื่อให้เทสไม่ผูกกับเนื้อหา config"""
    config = {
        "policy": {"max_age_hours": 48, "max_items_in_article": 2,
                   "min_items_to_open_section": 1, "max_source_tier": 2,
                   "require_fields": ["title", "source", "link", "published_at"]},
        "source_tiers": {"1": ["Reuters"], "2": ["FXStreet"]},
        "providers": [
            {"id": "wcb_site", "priority": 1, "kind": "wcb", "enabled": True},
            {"id": "worldmonitor", "priority": 2, "kind": "worldmonitor", "enabled": True},
            {"id": "public_rss", "priority": 3, "kind": "rss", "enabled": True},
        ],
        "assets": {"xauusd": {"keywords": ["gold"], "exclude": ["gold medal"]},
                   "nvda": {"keywords": ["nvidia"], "exclude": []}},
        "themes": [
            {"id": "us_inflation", "match": ["inflation"],
             "event": "ตัวเลขเงินเฟ้อฝั่งสหรัฐ", "signal": "จังหวะการปรับดอกเบี้ยรอบถัดไป"},
            {"id": "middle_east", "match": ["iran"],
             "event": "สถานการณ์ตึงเครียดในตะวันออกกลาง", "signal": "ความต้องการสินทรัพย์ปลอดภัย",
             "signal_overrides": {"nvda": "ความกล้าเสี่ยงของตลาด"}},
            {"id": "big_tech_earnings", "match": ["earnings"], "applies_to": ["nvda"],
             "event": "ผลประกอบการของกลุ่มเทคโนโลยีขนาดใหญ่", "signal": "เม็ดเงินลงทุน"},
        ],
    }
    config.update(overrides)
    return config


def fetchers(*, wcb=None, worldmonitor=None, rss=None):
    """สร้างชุด fetcher ปลอม — ส่ง None แปลว่าแหล่งนั้นใช้ไม่ได้รอบนี้"""
    def make(rows):
        if rows is None:
            def unavailable(settings, asset_config, *, require_fields):
                raise news_source.NewsProviderUnavailable("ทดสอบ: ใช้ไม่ได้")
            return unavailable

        def ok(settings, asset_config, *, require_fields, _rows=rows, _kind=None):
            provider = settings["id"]
            cleaned = []
            for raw in _rows:
                clean = news_source._clean_item(
                    raw, provider=provider, require_fields=require_fields)
                if clean:
                    cleaned.append(clean)
            return cleaned
        return ok

    return {"wcb": make(wcb), "worldmonitor": make(worldmonitor), "rss": make(rss)}


class ProviderOrderTests(unittest.TestCase):
    """ลำดับแหล่งคือคำสั่งจากหัวหน้าผู้ใช้ ไม่ใช่รายละเอียดที่แก้ตามใจได้"""

    def test_เว็บเรามีข่าวแล้วไม่ต้องไปแตะแหล่งอื่น(self):
        result = news_source.collect(
            "xauusd", config=tiny_config(), now=NOW,
            fetchers=fetchers(wcb=[item("Gold rises as inflation cools")],
                              worldmonitor=[item("Gold and Iran talks")],
                              rss=[item("Gold and Iran talks")]))
        self.assertEqual(result["provider_used"], "wcb_site")
        self.assertEqual([a["provider"] for a in result["attempts"]], ["wcb_site"])

    def test_เว็บเราไม่มีข่าวจึงตกไป_worldmonitor(self):
        result = news_source.collect(
            "xauusd", config=tiny_config(), now=NOW,
            fetchers=fetchers(wcb=None,
                              worldmonitor=[item("Gold slips on Iran headlines")],
                              rss=[item("Gold and inflation")]))
        self.assertEqual(result["provider_used"], "worldmonitor")

    def test_สองชั้นบนใช้ไม่ได้จึงตกมาที่_rss(self):
        result = news_source.collect(
            "xauusd", config=tiny_config(), now=NOW,
            fetchers=fetchers(wcb=None, worldmonitor=None,
                              rss=[item("Gold and inflation")]))
        self.assertEqual(result["provider_used"], "public_rss")
        self.assertEqual(len(result["attempts"]), 3)

    def test_เว็บเราส่งข่าวมาแต่ไม่เกี่ยวกับสินทรัพย์นั้นก็ต้องไปต่อ(self):
        # มีข่าวจริงแต่ไม่ใช่เรื่องทอง — ถือว่าชั้นนี้ไม่มีของ ต้องไล่ไปชั้นถัดไป
        result = news_source.collect(
            "xauusd", config=tiny_config(), now=NOW,
            fetchers=fetchers(wcb=[item("Nvidia earnings beat")],
                              worldmonitor=[item("Gold and inflation")]))
        self.assertEqual(result["provider_used"], "worldmonitor")


class FailClosedTests(unittest.TestCase):
    """ข่าวที่ตรวจไม่ได้ต้องหายไป ไม่ใช่ถูกเติมค่าว่างแล้วขึ้นหน้าเว็บ"""

    def test_ข่าวขาดลิงก์ถูกทิ้งทั้งชิ้น(self):
        broken = {**item("Gold up on inflation"), "link": ""}
        result = news_source.collect(
            "xauusd", config=tiny_config(), now=NOW,
            fetchers=fetchers(wcb=[broken], worldmonitor=None, rss=None))
        self.assertEqual(result["items"], [])
        self.assertEqual(result["cut_reason"], "no_usable_news")

    def test_ข่าวเก่าเกินเพดานถูกทิ้ง(self):
        result = news_source.collect(
            "xauusd", config=tiny_config(), now=NOW,
            fetchers=fetchers(wcb=[item("Gold up on inflation", hours_ago=100)],
                              worldmonitor=None, rss=None))
        self.assertEqual(result["items"], [])

    def test_สำนักข่าวนอกทะเบียนถูกทิ้งและถูกนับไว้(self):
        result = news_source.collect(
            "xauusd", config=tiny_config(), now=NOW,
            fetchers=fetchers(wcb=None, worldmonitor=None,
                              rss=[item("Gold up on inflation", source="ไม่รู้จักสำนักนี้")]))
        self.assertEqual(result["items"], [])
        rss_attempt = [a for a in result["attempts"] if a["provider"] == "public_rss"][0]
        self.assertEqual(rss_attempt["rejected_untrusted_source"], 1)

    def test_ข่าวของเว็บเราไม่ต้องผ่านทะเบียนสำนักข่าว(self):
        # เราเป็นคนเขียนเอง จะให้ไปเช็คทะเบียนสำนักข่าวภายนอกก็ไม่มีเหตุผล
        result = news_source.collect(
            "xauusd", config=tiny_config(), now=NOW,
            fetchers=fetchers(wcb=[item("Gold up on inflation", source="WCB Newsroom")]))
        self.assertEqual(result["provider_used"], "wcb_site")
        self.assertEqual(result["items"][0]["source_tier"], 1)

    def test_ข่าวที่จับประเด็นไม่ได้ถูกทิ้ง(self):
        # กันเครื่องแต่งประโยคเองจากพาดหัวที่พจนานุกรมไม่รู้จัก
        result = news_source.collect(
            "xauusd", config=tiny_config(), now=NOW,
            fetchers=fetchers(wcb=[item("Gold shop opens in Bangkok")],
                              worldmonitor=None, rss=None))
        self.assertEqual(result["items"], [])

    def test_สินทรัพย์ที่ยังไม่ได้ตั้งค่าไม่ทำให้ระบบล้ม(self):
        result = news_source.collect("ยังไม่มีตัวนี้", config=tiny_config(), now=NOW,
                                     fetchers=fetchers())
        self.assertEqual(result["cut_reason"], "asset_not_configured")
        self.assertEqual(result["items"], [])


class ThemeMatchingTests(unittest.TestCase):

    def test_ประเด็นที่จำกัดสินทรัพย์ไม่ข้ามไปตัวอื่น(self):
        # "ผลประกอบการกลุ่มเทคโนโลยี" ต้องไม่ถูกเอาไปเล่าในบทความทอง
        config = tiny_config()
        gold = news_source.match_theme({"title": "Gold miner earnings beat"},
                                       config["themes"], "xauusd")
        stock = news_source.match_theme({"title": "Nvidia earnings beat"},
                                        config["themes"], "nvda")
        self.assertIsNone(gold)
        self.assertEqual(stock["id"], "big_tech_earnings")

    def test_เลือกประเด็นที่อยู่ต้นพาดหัวก่อน(self):
        config = tiny_config()
        theme = news_source.match_theme(
            {"title": "Iran talks stall as inflation risks build"}, config["themes"], "xauusd")
        self.assertEqual(theme["id"], "middle_east")

    def test_ผลของประเด็นเดียวกันเปลี่ยนตามสินทรัพย์(self):
        result = news_source.collect(
            "nvda", config=tiny_config(), now=NOW,
            fetchers=fetchers(wcb=[item("Nvidia slips on Iran headlines")]))
        self.assertEqual(result["items"][0]["signal"], "ความกล้าเสี่ยงของตลาด")

    def test_ประเด็นซ้ำเล่าครั้งเดียวและไม่เกินเพดาน(self):
        rows = [item("Gold and inflation one", link="https://a"),
                item("Gold and inflation two", link="https://b"),
                item("Gold and Iran", link="https://c")]
        result = news_source.collect(
            "xauusd", config=tiny_config(), now=NOW, fetchers=fetchers(wcb=rows))
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual({i["theme_id"] for i in result["items"]},
                         {"us_inflation", "middle_east"})

    def test_พาดหัวเดียวกันคนละสำนักนับเป็นชิ้นเดียว(self):
        rows = [item("Gold rises as inflation cools - Reuters", link="https://a"),
                item("Gold rises as inflation cools - FXStreet", source="FXStreet",
                     link="https://b")]
        result = news_source.collect(
            "xauusd", config=tiny_config(), now=NOW, fetchers=fetchers(wcb=rows))
        self.assertEqual(len(result["items"]), 1)


class WatchParagraphTests(unittest.TestCase):
    """ช่วง ② ที่เรนเดอร์ออกมา"""

    @staticmethod
    def paragraph(items):
        return article_builder._watch_paragraph({"drivers": {"verified_news": items}})

    def test_ไม่มีข่าวคือย่อหน้าว่างไม่ใช่ประโยคแก้ตัว(self):
        self.assertEqual(self.paragraph([]), "")

    def test_ข่าวชิ้นเดียวใช้สูตรประโยคของ_spec(self):
        text = self.paragraph([{"event": "ตัวเลขเงินเฟ้อฝั่งสหรัฐ",
                                "signal": "จังหวะการปรับดอกเบี้ย", "source": "Reuters"}])
        self.assertTrue(text.startswith("สำหรับช่วงนี้ นักลงทุนจับตา"))
        self.assertIn("เพื่อหาสัญญาณ", text)
        self.assertIn("Reuters", text)

    def test_ช่วงนี้ห้ามมีตัวเลขเด็ดขาด(self):
        # เลขทุกตัวในบทความต้องชี้กลับค่าใน evidence ได้ แต่ข่าวไม่ได้อยู่ในชุดนั้น
        text = self.paragraph([
            {"event": "ตัวเลขเงินเฟ้อฝั่งสหรัฐ", "signal": "ก", "source": "Channel 24"},
            {"event": "สถานการณ์ตึงเครียด", "signal": "ข", "source": "Reuters"}])
        self.assertFalse(any(character.isdigit() for character in text))
        self.assertNotIn("Channel", text)

    def test_ชื่อสำนักที่มีคำต้องห้ามไม่ถูกเอ่ย(self):
        text = self.paragraph([{"event": "ประเด็นหนึ่ง", "signal": "ผลหนึ่ง",
                                "source": "Pivot Media"}])
        self.assertNotIn("Pivot", text)

    def test_ไม่มีคำ_denylist_หลุดเข้าย่อหน้า(self):
        text = self.paragraph([
            {"event": "ตัวเลขเงินเฟ้อฝั่งสหรัฐ", "signal": "จังหวะดอกเบี้ย", "source": "Reuters"},
            {"event": "สถานการณ์ตึงเครียด", "signal": "สินทรัพย์ปลอดภัย", "source": "FXStreet"}])
        for term in voice_rules.VOICE_DENYLIST:
            self.assertNotIn(term, text.lower())


class StockAssetTests(unittest.TestCase):
    """หัวข้อที่สี่ — หุ้นรายตัว"""

    def test_ลงทะเบียนครบทั้งสามไฟล์(self):
        self.assertIn("nvda", build_daily_package.ASSETS)
        calendar = market_calendar.for_asset("nvda")
        self.assertEqual(calendar.asset_class, "stock_cfd")
        registry = json.loads(
            (REPO_ROOT / "config" / "provider_license_registry.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["asset_providers"]["nvda"], ["mt5_raw_trading"])

    def test_ปฏิทินตลาดหุ้นสหรัฐปิดวันหยุดที่ตลาดค่าเงินยังเปิด(self):
        stock = market_calendar.for_asset("nvda")
        forex = market_calendar.for_asset("eurusd")
        # 19 ม.ค. 2026 วันมาร์ติน ลูเทอร์ คิง — ตลาดหุ้นปิด ตลาดค่าเงินเปิด
        self.assertEqual(stock.classify("2026-01-19"), "holiday")
        self.assertEqual(forex.classify("2026-01-19"), "expected")
        # เสาร์อาทิตย์ปิดเหมือนกัน
        self.assertEqual(stock.classify("2026-08-01"), "weekend")

    def test_เกณฑ์กริยาแรงของหุ้นไม่ใช่ชุดเดียวกับ_forex(self):
        # 2% ในหุ้นรายตัวคือวันปกติ แต่ในค่าเงินคือวันที่ต้องใช้คำว่า "แรง"
        self.assertEqual(voice_rules.classify_move(2.0, "stock_cfd"), voice_rules.MOVE_NORMAL)
        self.assertEqual(voice_rules.classify_move(2.0, "forex_spot"), voice_rules.MOVE_STRONG)
        self.assertEqual(voice_rules.classify_move(3.5, "stock_cfd"), voice_rules.MOVE_STRONG)
        self.assertEqual(voice_rules.classify_move(0.5, "stock_cfd"), voice_rules.MOVE_QUIET)

    def test_ราคาหุ้นแสดงทศนิยมสองตำแหน่งไม่มีตัวคั่นหลักพัน(self):
        self.assertEqual(voice_rules.format_price(206.185, "stock_cfd"), "206.19")
        self.assertEqual(voice_rules.format_price(1206.1, "stock_cfd"), "1206.10")

    def test_ชื่อชนิดสินทรัพย์บอกว่าเป็นสัญญาอ้างอิงไม่ใช่ตัวหุ้น(self):
        label = article_builder.INSTRUMENT_LABEL["stock_cfd"]
        self.assertIn("สัญญาอ้างอิง", label)


class OpeningDateTests(unittest.TestCase):
    """วันที่ในประโยคเปิดต้องเป็นวันของแท่ง ไม่ใช่วันที่รันสายท่อ"""

    @staticmethod
    def opening(trading_date, cutoff):
        data = {
            "instrument": {"instrument_type": "stock_cfd", "unit": "ดอลลาร์ต่อหุ้น",
                           "symbol": "NVDA", "cutoff_at": cutoff},
            "snapshot": {"open": 199.46, "price": 206.19, "high": 208.72, "low": 198.10,
                         "trading_date": trading_date, "percent_magnitude": None,
                         "previous_close": None},
            "move": {"direction": "up", "class": voice_rules.MOVE_NORMAL},
        }
        return article_builder._opening_paragraph(data)

    def test_แท่งของวันเดียวกับที่รันใช้คำว่าวันนี้(self):
        text = self.opening("2026-08-04", "2026-08-04T04:00:00+00:00")
        self.assertTrue(text.startswith("วันนี้ ( 4 ส.ค. 2026 )"))

    def test_แท่งของเมื่อวานห้ามเรียกว่าวันนี้(self):
        # เช้าไทย ตลาดหุ้นสหรัฐยังไม่เปิด แท่งล่าสุดคือรอบเมื่อวาน
        text = self.opening("2026-08-03", "2026-08-04T04:00:00+00:00")
        self.assertTrue(text.startswith("ในรอบการซื้อขายล่าสุด ( 3 ส.ค. 2026 )"))
        self.assertNotIn("วันนี้", text)


class RenderedArticleTests(unittest.TestCase):
    """บทความเต็มฉบับที่มีช่วง ② ต้องยังผ่านด่านของตัวเองทุกข้อ"""

    NEWS = [{"event": "ตัวเลขเงินเฟ้อฝั่งสหรัฐ", "signal": "จังหวะการปรับดอกเบี้ยรอบถัดไป",
             "source": "Reuters", "link": "https://example.com/a",
             "published_at": "2026-08-03T01:00:00+00:00", "theme_id": "us_inflation"},
            {"event": "สถานการณ์ตึงเครียดในตะวันออกกลาง", "signal": "ความต้องการสินทรัพย์ปลอดภัย",
             "source": "FXStreet", "link": "https://example.com/b",
             "published_at": "2026-08-03T02:00:00+00:00", "theme_id": "middle_east"}]

    @classmethod
    def setUpClass(cls):
        from tests.test_article_builder import build_sample  # นำสายท่อจริงมาใช้ซ้ำ

        cls.tmp = tempfile.TemporaryDirectory()
        cls.without_news = build_sample(Path(cls.tmp.name))[1]
        cls.build_sample = staticmethod(build_sample)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def render_with_news(self):
        from tools import (chart_renderer, integrity, levels as level_engine,
                           license_gate)

        fixtures = REPO_ROOT / "tests" / "fixtures"
        rows = json.loads(
            (fixtures / "xau_valid_120_sessions.json").read_text(encoding="utf-8"))["rows"]
        cutoff = "2026-08-03T07:00:00+00:00"
        report = integrity.assess(rows, "xauusd", calculated_at=cutoff)
        level_map = level_engine.build_level_map(report)
        chart_levels, _ = article_builder.public_level_views(
            level_map["zones"], float(report["candles"][-1]["close"]))
        chart_metadata = chart_renderer.render_daily_chart(
            candles=report["candles"], output_path=Path(self.tmp.name) / "chart-news.png",
            symbol="XAU/USD", cutoff_at=cutoff, levels=chart_levels,
            indicator_series={"sma20": chart_renderer.rolling_mean_series(report["candles"], 20)},
            decimals=2,
            price_text=lambda value: voice_rules.format_price(value, "spot_metal"))
        data = article_builder.build_article_data(
            report=report, level_map=level_map, chart_metadata=chart_metadata,
            license_result=license_gate.evaluate("xauusd"), symbol="XAU/USD",
            instrument_type="spot_metal", unit="ดอลลาร์ต่อออนซ์", decimals=2,
            cutoff_at=cutoff, batch_id="2026-08-03T07-00Z-news",
            verified_news=self.NEWS)
        return data, article_builder.render_markdown(data)

    def test_ช่วงสองแทรกอยู่ระหว่างช่วงหนึ่งกับหัวข้อเทคนิค(self):
        _, markdown = self.render_with_news()
        watch = markdown.index("สำหรับช่วงนี้ นักลงทุนจับตา")
        heading = markdown.index(voice_rules.TECHNICAL_HEADING)
        opening = markdown.index("เปิดตลาดที่ระดับ")
        self.assertLess(opening, watch)
        self.assertLess(watch, heading)

    def test_ไม่มีข่าวแล้วบทความไม่มีช่วงสองและไม่มีหัวข้อว่าง(self):
        self.assertNotIn("สำหรับช่วงนี้ นักลงทุนจับตา", self.without_news)
        self.assertNotIn("ปัจจัยจับตา", self.without_news)

    def test_บทความที่มีช่วงสองยังผ่านด่านบทความ(self):
        from tools import public_copy_validator

        data, markdown = self.render_with_news()
        result = public_copy_validator.validate(
            markdown, evidence={"article": data}, instrument_type="spot_metal")
        self.assertEqual(result["fatal_count"], 0, result["findings"])
        self.assertLessEqual(result["word_count"], voice_rules.WORD_MAX)
        self.assertGreaterEqual(result["word_count"], voice_rules.WORD_MIN)

    def test_ลิงก์ข่าวถูกเก็บไว้ในหลักฐานฝั่ง_json_แต่ไม่โผล่ในเนื้อบทความ(self):
        # ระยะ 2 (ฝังลิงก์) จะหยิบไปใช้ต่อ — ระยะนี้เนื้อบทความยังเป็นร้อยแก้วล้วน
        data, markdown = self.render_with_news()
        self.assertEqual([n["link"] for n in data["drivers"]["verified_news"]],
                         ["https://example.com/a", "https://example.com/b"])
        self.assertNotIn("https://", markdown.split("![")[0])


class ConfigContractTests(unittest.TestCase):
    """ไฟล์ config จริงต้องคงสัญญาที่โค้ดพึ่งพา"""

    @classmethod
    def setUpClass(cls):
        cls.config = news_source.load_config()

    def test_เว็บเราอยู่ลำดับหนึ่งเสมอ(self):
        ordered = sorted(self.config["providers"], key=lambda p: p["priority"])
        self.assertEqual(ordered[0]["id"], "wcb_site")
        self.assertEqual(ordered[1]["id"], "worldmonitor")

    def test_ทุกสินทรัพย์ในสายท่อมีคำค้นข่าวของตัวเอง(self):
        for asset in build_daily_package.ASSETS:
            self.assertIn(asset, self.config["assets"], f"{asset} ยังไม่มีค่าข่าว")
            self.assertTrue(self.config["assets"][asset].get("rss_query"))

    def test_ทุกประเด็นมีทั้งเหตุการณ์และผล(self):
        for theme in self.config["themes"]:
            self.assertTrue(theme.get("event"))
            self.assertTrue(theme.get("signal"))
            self.assertTrue(theme.get("match"))

    def test_ทุกประเด็นจับได้ทั้งพาดหัวไทยและอังกฤษ(self):
        # แหล่งลำดับ 1 คือเว็บเราซึ่งพาดหัวเป็นภาษาไทย ถ้าพจนานุกรมมีแต่คำอังกฤษ
        # ข่าวของเราเองจะถูกทิ้งทั้งหมดแล้วระบบไหลไปใช้แหล่งสำรองแบบเงียบ ๆ
        for theme in self.config["themes"]:
            has_thai = any(any("฀" <= ch <= "๿" for ch in token)
                           for token in theme["match"])
            has_latin = any(any("a" <= ch.lower() <= "z" for ch in token)
                            for token in theme["match"])
            self.assertTrue(has_thai, f"ประเด็น {theme['id']} ยังไม่มีคำจับภาษาไทย")
            self.assertTrue(has_latin, f"ประเด็น {theme['id']} ยังไม่มีคำจับภาษาอังกฤษ")

    def test_ไฟล์ตัวอย่างข่าวของเว็บเราใช้ได้จริงทั้งสี่หัวข้อ(self):
        import copy

        config = copy.deepcopy(self.config)
        for provider in config["providers"]:
            if provider["id"] == "wcb_site":
                provider["local_file"] = "config/samples/wcb-news-sample.json"
        for asset in build_daily_package.ASSETS:
            result = news_source.collect(
                asset, config=copy.deepcopy(config),
                now=datetime(2026, 8, 4, 4, 0, tzinfo=timezone.utc))
            self.assertEqual(result["provider_used"], "wcb_site",
                             f"{asset} ไม่ได้ใช้ข่าวของเว็บเราทั้งที่มีให้")
            self.assertTrue(result["items"])

    def test_ป้ายสินทรัพย์ของต้นทางมีอำนาจเหนือการเดาจากพาดหัว(self):
        config = tiny_config()
        tagged = {**item("Gold rises on inflation"), "assets": ["nvda"]}
        self.assertFalse(news_source.is_relevant(tagged, config["assets"]["xauusd"], "xauusd"))
        self.assertTrue(news_source.is_relevant(tagged, config["assets"]["nvda"], "nvda"))

    def test_ข้อความประเด็นไม่มีตัวเลขและไม่มีคำ_denylist(self):
        for theme in self.config["themes"]:
            texts = [theme["event"], theme["signal"]]
            texts += list((theme.get("signal_overrides") or {}).values())
            for text in texts:
                self.assertFalse(any(ch.isdigit() for ch in text), text)
                for term in voice_rules.VOICE_DENYLIST:
                    self.assertNotIn(term, text.lower(), f"{text} มีคำต้องห้าม {term}")


if __name__ == "__main__":
    unittest.main()
