"""เทสสไตล์ระหว่างวัน H/I/J — ตัวตัดสินสถานะ ด่านของบท และตัวเลือกบท

แบ่งเป็นสามชั้นตามที่โค้ดแบ่งไว้ และเทสแต่ละชั้นด้วยวิธีที่เหมาะกับชั้นนั้น:

    ชั้นตัดสินสถานะ  `classify()` เป็นฟังก์ชันบริสุทธิ์ ⇒ ป้อนค่าตรง ๆ ครบทุกสาขา
    ชั้นบทความ       ต้องมี story จริง ⇒ สร้างจากแท่งสังเคราะห์ที่ควบคุมรูปได้
    ชั้นเลือกบท      ป้อน story ปลอมที่มีแค่ช่องที่ตัวเลือกใช้

⚠️ วันที่ของแท่งสังเคราะห์ต้องเป็น **อดีต** เสมอ เพราะด่านแท่งปิดพิสูจน์ใหม่จากนาฬิกาจริง
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools import headline_format  # noqa: E402
from tools import intraday_article_selector as selector  # noqa: E402
from tools import intraday_bars, intraday_breakout_story, intraday_breakout_writer  # noqa: E402
from tools import intraday_pipeline  # noqa: E402
from tools import intraday_pullback_story, intraday_pullback_writer  # noqa: E402
from tools import intraday_story, intraday_trend_story, intraday_trend_writer  # noqa: E402
from tools import intraday_writer_base as base  # noqa: E402

H, I, J = intraday_trend_story, intraday_breakout_story, intraday_pullback_story

START = datetime(2026, 8, 1, 0, 0)


def make_rows(count: int, *, minutes: int, shape=None) -> list[dict]:
    """แท่งสังเคราะห์ที่ควบคุมรูปได้ — `shape(i)` คืน (open, high, low, close)"""
    shape = shape or (lambda i: (100.0 + i, 100.5 + i, 99.5 + i, 100.5 + i))
    rows = []
    for index in range(count):
        moment = START + timedelta(minutes=minutes * index)
        open_, high, low, close = shape(index)
        rows.append({"date": moment.strftime("%Y-%m-%d"),
                     "at": moment.strftime("%Y-%m-%d %H:%M:%S"),
                     "open": open_, "high": high, "low": low, "close": close})
    return rows


def basis_for(rows: list[dict], timeframe: str, asset: str = "btcusd") -> dict:
    return intraday_bars.basis_for(asset, rows[-1]["at"], timeframe=timeframe,
                                   now=datetime.now().astimezone())


def quiet_then(count: int, *, minutes: int, tail=None) -> list[dict]:
    """ช่วงเงียบยาว ๆ แล้วต่อท้ายด้วยแท่งที่กำหนดเอง — ใช้ปั้นสถานะบีบตัว/เบรก"""
    rows = make_rows(count, minutes=minutes,
                     shape=lambda i: (100.0, 100.3, 99.7, 100.0 + (0.1 if i % 2 else -0.1)))
    for index, candle in enumerate(tail or []):
        moment = START + timedelta(minutes=minutes * (count + index))
        open_, high, low, close = candle
        rows.append({"date": moment.strftime("%Y-%m-%d"),
                     "at": moment.strftime("%Y-%m-%d %H:%M:%S"),
                     "open": open_, "high": high, "low": low, "close": close})
    return rows


# =============================================================== ชั้นตัดสินสถานะ H

class TestตัวตัดสินสถานะH:
    BASE = {"plus_di": 30.0, "minus_di": 15.0, "adx": 30.0, "close": 110.0,
            "supertrend_value": 100.0, "adx_trend": 25.0, "adx_no_trend": 20.0}

    def สถานะ(self, **override):
        return H.classify(**{**self.BASE, **override})

    def test_ครบเงื่อนไขฝั่งขึ้นได้เทรนด์ขาขึ้น(self):
        assert self.สถานะ() == H.BULL_TREND

    def test_ครบเงื่อนไขฝั่งลงได้เทรนด์ขาลง(self):
        assert self.สถานะ(plus_di=15.0, minus_di=30.0, close=90.0) == H.BEAR_TREND

    def test_แรงยังไม่ถึงเกณฑ์เทรนด์ได้สถานะเริ่มต้น(self):
        assert self.สถานะ(adx=22.0) == H.EARLY_BULL
        assert self.สถานะ(adx=22.0, plus_di=15.0, minus_di=30.0,
                          close=90.0) == H.EARLY_BEAR

    def test_แรงต่ำกว่าเกณฑ์ล่างได้ไร้เทรนด์แม้DIจะชี้ชัด(self):
        """ADX ต่ำต้องตัดสินก่อนเสมอ — คำถามเรื่องทิศยังไม่ควรถูกถามด้วยซ้ำ"""
        assert self.สถานะ(adx=10.0, plus_di=40.0, minus_di=5.0) == H.NO_TREND

    def test_DIกับSupertrendขัดกันได้ช่วงเปลี่ยนผ่าน(self):
        assert self.สถานะ(close=90.0) == H.TRANSITION
        assert self.สถานะ(plus_di=15.0, minus_di=30.0, close=110.0) == H.TRANSITION

    def test_ทุกสถานะที่ตัวตัดสินคืนอยู่ในทะเบียน(self):
        for state in (self.สถานะ(), self.สถานะ(adx=10.0), self.สถานะ(close=90.0)):
            assert state in H.STATES


# =============================================================== ชั้นตัดสินสถานะ I

class TestตัวตัดสินสถานะI:
    BASE = {"previous_state": I.NORMAL, "close": 100.0, "upper": 110.0, "lower": 90.0,
            "bbw_percentile": 50.0, "bbw_rising": True, "bar_true_range": 3.0,
            "atr_value": 2.0, "compression_percentile": 20.0,
            "expansion_percentile": 80.0, "armed_distance_atr": 0.5,
            "breakout_tr_atr": 1.2}

    def สถานะ(self, **override):
        return I.classify(**{**self.BASE, **override})

    def test_ปกติเมื่อไม่เข้าเงื่อนไขใด(self):
        assert self.สถานะ() == I.NORMAL

    def test_บีบตัวเมื่ออันดับความกว้างต่ำและราคาห่างขอบ(self):
        assert self.สถานะ(bbw_percentile=10.0) == I.COMPRESSION

    def test_ง้างรอเมื่อบีบตัวและราคาเข้าใกล้ขอบ(self):
        assert self.สถานะ(bbw_percentile=10.0, close=109.5) == I.ARMED

    def test_เบรกขึ้นต้องปิดพ้นขอบพร้อมแรงขยาย(self):
        assert self.สถานะ(close=111.0) == I.BREAKOUT_UP
        # ปิดพ้นขอบแต่แท่งแคบ = ยังไม่ใช่การเบรกที่มีแรง
        assert self.สถานะ(close=111.0, bar_true_range=1.0) != I.BREAKOUT_UP
        # ปิดพ้นขอบแต่แถบหดขณะทะลุ = ยังไม่ใช่เช่นกัน
        assert self.สถานะ(close=111.0, bbw_rising=False) != I.BREAKOUT_UP

    def test_เบรกลงเป็นภาพกลับด้าน(self):
        assert self.สถานะ(close=89.0) == I.BREAKOUT_DOWN

    def test_เบรกล้มเหลวต้องอาศัยความจำรอบก่อน(self):
        assert self.สถานะ(previous_state=I.BREAKOUT_UP, close=100.0) == I.FAILED_BREAKOUT_UP
        assert self.สถานะ(previous_state=I.BREAKOUT_DOWN, close=100.0) == I.FAILED_BREAKOUT_DOWN
        # ไม่มีความจำ = สถานะนี้เกิดไม่ได้เลย ซึ่งเป็นพฤติกรรมที่ตั้งใจ
        assert self.สถานะ(previous_state=None, close=100.0) == I.NORMAL

    def test_เบรกที่ยังยืนอยู่นอกกรอบไม่ใช่การล้มเหลว(self):
        assert self.สถานะ(previous_state=I.BREAKOUT_UP, close=111.0) == I.BREAKOUT_UP

    def test_กางออกเมื่ออันดับความกว้างสูง(self):
        assert self.สถานะ(bbw_percentile=90.0) == I.EXPANSION


# =============================================================== ชั้นตัดสินสถานะ J

class TestตัวตัดสินสถานะJ:
    BASE = {"previous_state": J.M30_BULL_CONTEXT, "bias": "up", "close": 105.0,
            "tenkan": 100.0, "kijun": 95.0, "chop": 40.0, "chop_previous": 50.0,
            "chop_choppy": 61.8, "extreme": 110.0}

    def สถานะ(self, **override):
        return J.classify(**{**self.BASE, **override})

    def test_ไม่มีทิศหลักเมื่อบริบทว่าง(self):
        assert self.สถานะ(bias=None, previous_state=None) == J.NO_M30_BIAS

    def test_บริบทหายระหว่างย่อถือว่าย่อล้มเหลว(self):
        assert self.สถานะ(bias=None, previous_state=J.PULLBACK_FORMING) == J.PULLBACK_FAILED

    def test_อยู่ในโซนอ้างอิงคือกำลังย่อ(self):
        assert self.สถานะ(close=98.0) == J.PULLBACK_FORMING

    def test_ยืนยันเมื่อปิดกลับตามทิศและออกจากช่วงสับ(self):
        assert self.สถานะ(previous_state=J.PULLBACK_FORMING, close=105.0) == J.PULLBACK_CONFIRMED

    def test_ยังไม่ยืนยันถ้าตลาดยังสับ(self):
        assert self.สถานะ(previous_state=J.PULLBACK_FORMING, close=105.0,
                          chop=70.0, chop_previous=65.0) == J.M30_BULL_CONTEXT

    def test_หลุดเส้นอ้างอิงสวนทิศคือเสียโครง(self):
        assert self.สถานะ(previous_state=J.PULLBACK_FORMING, close=90.0) == J.PULLBACK_FAILED

    def test_ทำจุดสุดขั้วใหม่ต่อจากที่ยืนยันแล้วคือเทรนด์กลับมาเดิน(self):
        assert self.สถานะ(previous_state=J.PULLBACK_CONFIRMED, close=115.0) == J.TREND_RESUMED

    def test_ฝั่งลงเป็นภาพกลับด้านทุกข้อ(self):
        down = {"bias": "down", "tenkan": 100.0, "kijun": 105.0, "extreme": 90.0}
        assert self.สถานะ(**down, close=102.0) == J.PULLBACK_FORMING
        assert self.สถานะ(**down, close=110.0,
                          previous_state=J.PULLBACK_FORMING) == J.PULLBACK_FAILED
        assert self.สถานะ(**down, close=85.0,
                          previous_state=J.PULLBACK_CONFIRMED) == J.TREND_RESUMED


# ==================================================================== ด่าน fail-closed

class Testด่านหยุดสายเมื่อหลักฐานไม่ครบ:
    def test_สินทรัพย์นอกทะเบียนถูกปฏิเสธก่อนคำนวณอะไรทั้งนั้น(self):
        rows = make_rows(300, minutes=30)
        with pytest.raises(intraday_story.StoryUnavailable, match="ยังไม่เปิดสไตล์"):
            H.build(rows, asset="eurusd", timeframe="30min",
                    candle_basis=basis_for(rows, "30min", "eurusd"))

    def test_แท่งไม่พอทำให้ทั้งสไตล์หยุดไม่ใช่เขียนแบบเดา(self):
        rows = make_rows(20, minutes=30)
        with pytest.raises(intraday_story.StoryUnavailable):
            H.build(rows, asset="btcusd", timeframe="30min",
                    candle_basis=basis_for(rows, "30min"))

    def test_ประวัติสั้นเกินทำให้เปอร์เซ็นไทล์ไร้ความหมายและถูกตีตก(self):
        rows = make_rows(45, minutes=15)
        with pytest.raises(intraday_story.StoryUnavailable, match="เปอร์เซ็นไทล์"):
            I.build(rows, asset="btcusd", timeframe="15min",
                    candle_basis=basis_for(rows, "15min"))


class Testการจัดแถวกรอบเวลาสองชั้น:
    def test_แท่งบริบทที่ปิดช้ากว่าถูกตัดออกไม่ใช่ตีตกทั้งใบ(self):
        context = make_rows(200, minutes=30)      # แท่งท้ายปิดที่ 99:30 + 30 นาที
        trigger = make_rows(399, minutes=15)      # แท่งท้ายปิดก่อนหน้านั้น 15 นาที
        kept, close_at = intraday_story.align_context(
            context, trigger, context_timeframe="30min", trigger_timeframe="15min",
            asset="btcusd")
        assert len(kept) == len(context) - 1
        assert kept[-1]["at"] == context[-2]["at"]
        assert close_at.startswith(kept[-1]["at"][:10])

    def test_ไม่เหลือแท่งบริบทที่ใช้ได้เลยจึงตีตกทั้งใบ(self):
        context = make_rows(3, minutes=30)
        trigger = make_rows(1, minutes=15)
        with pytest.raises(intraday_story.StoryUnavailable, match="เหลื่อมกัน"):
            intraday_story.align_context(context, trigger, context_timeframe="30min",
                                         trigger_timeframe="15min", asset="btcusd")


class Testความจำสถานะ:
    def test_เขียนแล้วอ่านกลับได้ครบและรอบแรกไม่ถือเป็นข้อผิดพลาด(self, tmp_path):
        assert intraday_story.read_state("h_trend_strength", "btcusd", "30min",
                                         state_dir=tmp_path) == {}
        story = {"style": "h_trend_strength", "asset": "btcusd", "timeframe": "30min",
                 "state": "BULL_TREND", "bar_at": "2026-08-01 00:00:00"}
        intraday_story.remember(story, state_dir=tmp_path, published=True)
        memory = intraday_story.read_state("h_trend_strength", "btcusd", "30min",
                                           state_dir=tmp_path)
        assert memory["state"] == "BULL_TREND"
        assert memory["published"] is True

    def test_ไฟล์ความจำพังต้องไม่พาสายผลิตล้ม(self, tmp_path):
        path = intraday_story.state_path("h_trend_strength", "btcusd", "30min",
                                         state_dir=tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ พัง", encoding="utf-8")
        assert intraday_story.read_state("h_trend_strength", "btcusd", "30min",
                                         state_dir=tmp_path) == {}


# ======================================================================= ชั้นบทความ

@pytest.fixture(scope="module")
def trend_story() -> dict:
    rows = make_rows(300, minutes=30)
    return H.build(rows, asset="btcusd", timeframe="30min",
                   candle_basis=basis_for(rows, "30min"))


@pytest.fixture(scope="module")
def breakout_story() -> dict:
    rows = quiet_then(300, minutes=15)
    return I.build(rows, asset="btcusd", timeframe="15min",
                   candle_basis=basis_for(rows, "15min"))


@pytest.fixture(scope="module")
def pullback_story() -> dict:
    context = make_rows(200, minutes=30)
    trigger = make_rows(401, minutes=15)
    return J.build(context, trigger, asset="btcusd", candle_basis=basis_for(trigger, "15min"),
                   context_basis=basis_for(context, "30min"))


ALL_STYLES = [
    ("trend_story", intraday_trend_writer),
    ("breakout_story", intraday_breakout_writer),
    ("pullback_story", intraday_pullback_writer),
]


@pytest.mark.parametrize("fixture_name,writer", ALL_STYLES)
class Testบทของทุกสไตล์ผ่านด่านของตัวเอง:
    def test_บทที่ระบบเขียนเองผ่านด่านทุกข้อ(self, fixture_name, writer, request):
        story = request.getfixturevalue(fixture_name)
        result = writer.validate(writer.render_article(story), story)
        assert result["ok"], [item["message"] for item in result["findings"]]

    def test_บทมีภาพสองใบและอ้างถึงทั้งคู่(self, fixture_name, writer, request):
        story = request.getfixturevalue(fixture_name)
        markdown = writer.render_article(story)
        from tools import intraday_writer_base as base
        pictures = base.figures(story, writer)
        assert len(pictures) == 2
        for picture in pictures:
            assert f"({picture['name']})" in markdown
            assert picture["caption"] in markdown

    def test_บทไม่มีแผนการเทรด(self, fixture_name, writer, request):
        """§26 — H/I/J บอกสถานะและหลักฐาน ไม่คิดจุดเข้า/จุดตัดขาดทุน"""
        story = request.getfixturevalue(fixture_name)
        markdown = writer.render_article(story)
        for word in ("จุดเข้าเทรด", "Stoploss", "Take Profit"):
            assert word not in markdown

    def test_หัวข้อเงื่อนไขผิดคาดใช้ถ้อยคำไทยที่ผู้ใช้อนุมัติ(self, fixture_name, writer,
                                                               request):
        """มติผู้ใช้ 2026-08-13 — ห้ามถ้อยคำแปลตรงตัวกลับมา

        หัวข้อกับกล่องอ่านจาก **ตัวสไตล์เอง** ไม่ฝังสตริงไว้ในเทส — H เปลี่ยนทั้งระดับ
        หัวข้อและถ้อยคำกล่องตามใบผู้ใช้ 08-14 ส่วน I/J ยังเป็นของกลาง
        """
        story = request.getfixturevalue(fixture_name)
        markdown = writer.render_article(story)
        prefix = getattr(writer, "SECTION_PREFIX", "##")
        head = base._spec_text(writer, "h2_invalidation", story, base.H2_INVALIDATION)
        assert f"{prefix} 4. {head}" in markdown
        assert "อะไรทำให้มุมมองนี้เสีย" not in markdown
        for line in base._spec_text(writer, "box_lines", story,
                                    base.box_lines(story, writer)):
            assert line in markdown

    def test_บทไม่มีหัวข้ออธิบายศัพท์(self, fixture_name, writer, request):
        """มติผู้ใช้ 08-14 — บทไม่อธิบายคำ หัวข้อศัพท์ถูกถอดจากโครง H/I/J ทั้งชุด"""
        story = request.getfixturevalue(fixture_name)
        markdown = writer.render_article(story)
        assert "อ่านศัพท์ในบทนี้แบบเข้าใจง่าย" not in markdown
        assert "ในที่นี้หมายถึง" not in markdown
        # สรุปเลื่อนขึ้นมาเป็นหัวที่ 5 — เว้นสไตล์ที่ตั้งหัวข้อสรุปของตัวเอง (H)
        summary = getattr(writer, "SUMMARY_HEAD", None) or "## 5. สรุปแนวโน้มรอบนี้"
        assert summary in markdown

    def test_เติมคำที่ให้ตัวชี้วัดไร้ทิศบอกทิศแล้วบทต้องตก(self, fixture_name, writer,
                                                              request):
        story = request.getfixturevalue(fixture_name)
        markdown = writer.render_article(story) + "\nสรุปคือ ATR เป็นขาขึ้นแล้ว\n"
        result = writer.validate(markdown, story)
        assert not result["ok"]
        assert any(item["rule"] == "indicator_direction_abuse"
                   for item in result["findings"])

    def test_เติมคำโอ้อวดผลงานแล้วบทต้องตก(self, fixture_name, writer, request):
        story = request.getfixturevalue(fixture_name)
        markdown = writer.render_article(story) + "\nระบบนี้แม่นยำมาก\n"
        result = writer.validate(markdown, story)
        assert any(item["rule"] == "performance_claim_forbidden"
                   for item in result["findings"])

    def test_เลขนอกทะเบียนทำให้บทตก(self, fixture_name, writer, request):
        story = request.getfixturevalue(fixture_name)
        markdown = writer.render_article(story) + "\nแนวรับถัดไปอยู่ที่ 12,345.67\n"
        result = writer.validate(markdown, story)
        assert any(item["rule"] == "number_not_in_story" for item in result["findings"])

    def test_พาดหัวที่ไม่ตรงสถานะทำให้บทตก(self, fixture_name, writer, request):
        """แก้เฉพาะบรรทัด H1 — คำประจำสถานะโผล่ในหัวไฟล์ด้วย ถ้าแทนที่ทั้งใบจะไม่ได้
        ทดสอบด่านนี้จริง (แทนที่ตัวแรกไปโดนช่อง title แทน)"""
        story = request.getfixturevalue(fixture_name)
        keyword = writer.headline_keyword(story)
        lines = writer.render_article(story).splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith("# "))
        assert keyword in lines[index]
        lines[index] = lines[index].replace(keyword, "อะไรก็ไม่รู้")
        result = writer.validate("\n".join(lines) + "\n", story)
        assert any(item["rule"] == "headline_matches_state" for item in result["findings"])


class Testรายละเอียดเฉพาะสไตล์:
    def test_Hชี้ระดับที่ทำให้มุมมองเสียไปที่เส้นSupertrendเสมอ(self, trend_story):
        assert trend_story["invalidation"]["kind"] == "supertrend"
        assert trend_story["invalidation"]["level"] == trend_story["supertrend"]["value"]

    def test_Iบันทึกว่ากรอบไม่นับแท่งสัญญาณ(self, breakout_story):
        assert breakout_story["donchian"]["excludes_signal_bar"] is True

    def test_Jเก็บหลักฐานการเลื่อนเมฆไว้ให้ตรวจย้อนได้(self, pullback_story):
        cloud = pullback_story["ichimoku"]["cloud_now"]
        assert cloud["calculated_at"] != cloud["plotted_at"]

    @pytest.mark.parametrize("state", list(H.STATES))
    def test_Hเขียนได้ครบทุกสถานะและผ่านด่านทุกสถานะ(self, trend_story, state):
        """โครงใหม่ 08-14 แตกถ้อยคำตามสถานะหลายจุด — ต้องไม่มีสถานะไหนพังเงียบ

        แท่งจริงที่ให้ทั้งหกสถานะในเทสเดียวสร้างยาก ⇒ สวมสถานะลงบน story จริง
        (เลขทุกตัวยังเป็นชุดเดิม ทะเบียนเลขจึงยังตรง) แล้วให้ด่านตรวจทั้งใบ
        """
        story = dict(trend_story, state=state, direction=H.DIRECTIONAL.get(state))
        markdown = intraday_trend_writer.render_article(story)
        result = intraday_trend_writer.validate(markdown, story)
        assert result["ok"], [item["message"] for item in result["findings"]]

    def test_Hใช้รูปบทตามใบผู้ใช้08_14(self, trend_story):
        """หกจุดที่ผู้ใช้สั่งเปลี่ยน — ล็อกไว้ทีละข้อ ไม่ให้ใครแก้กลับเงียบ ๆ"""
        markdown = intraday_trend_writer.render_article(trend_story)
        lines = markdown.splitlines()
        h1 = next(line for line in lines if line.startswith("# "))
        assert f"({headline_format.thai_date(trend_story['bar_date'])})" in h1
        assert "## 📌 สรุปภาพรวมตลาด" in markdown
        assert "### 1. ภาพรวมโครงสร้างราคาและโมเมนตัม (M30)" in markdown
        assert "### 💡 บทสรุปการเทรด (Executive Summary)" in markdown
        assert "## 5. สรุปแนวโน้มรอบนี้" not in markdown
        expected_level = ("แนวต้านเปลี่ยนเทรนด์" if trend_story["direction"] == "down"
                          else "แนวรับเปลี่ยนเทรนด์")
        assert f"* **{expected_level}:**" in markdown
        assert "จุดยกเลิกมุมมอง" not in markdown
        # ถอดย่อหน้าเชื่อมภาพ ⇒ บรรทัดถัดจากคำบรรยายภาพต้องเป็นเส้นคั่นหรือหัวข้อ
        for index, line in enumerate(lines):
            if line.startswith("*ภาพที่ "):
                assert lines[index + 2] in ("---", ""), lines[index + 2]

    def test_สถานะที่ไม่ชี้ทิศต้องไม่มีทิศติดมาด้วย(self):
        rows = make_rows(300, minutes=30,
                         shape=lambda i: (100.0, 100.4, 99.6, 100.0 + (0.2 if i % 2 else -0.2)))
        story = H.build(rows, asset="btcusd", timeframe="30min",
                        candle_basis=basis_for(rows, "30min"))
        assert story["state"] in (H.NO_TREND, H.TRANSITION)
        assert story["direction"] is None
        markdown = intraday_trend_writer.render_article(story)
        h1 = next(line for line in markdown.splitlines() if line.startswith("# "))
        assert "ขาขึ้น" not in h1 and "ขาลง" not in h1


# ======================================================================= ตัวเลือกบท

def fake_story(style: str, state: str, *, previous: str | None) -> dict:
    return {"style": style, "state": state, "previous_state": previous,
            "state_changed": previous is not None and previous != state, "triggers": []}


class Testตัวเลือกบทระหว่างวัน:
    def test_ไม่มีสถานะใดเปลี่ยนจึงไม่ผลิต(self):
        decision = selector.select([
            fake_story(H.STYLE_ID, H.BULL_TREND, previous=H.BULL_TREND),
            fake_story(I.STYLE_ID, I.COMPRESSION, previous=I.COMPRESSION),
        ])
        assert decision["publish"] is False

    def test_รอบแรกของหัวข้อผลิตได้แม้ไม่มีอะไรให้เทียบ(self):
        decision = selector.select([fake_story(H.STYLE_ID, H.BULL_TREND, previous=None)])
        assert decision["publish"] is True
        assert decision["style"] == H.STYLE_ID

    def test_สถานะที่ไม่มีเรื่องให้เขียนไม่ถูกผลิตแม้เพิ่งเปลี่ยนมา(self):
        decision = selector.select([
            fake_story(I.STYLE_ID, I.NORMAL, previous=I.COMPRESSION),
            fake_story(J.STYLE_ID, J.NO_M30_BIAS, previous=J.M30_BULL_CONTEXT),
        ])
        assert decision["publish"] is False

    def test_เลือกใบที่มีเรื่องเล่าใหญ่สุดและกลั้นที่เหลือไว้(self):
        decision = selector.select([
            fake_story(H.STYLE_ID, H.EARLY_BULL, previous=H.NO_TREND),
            fake_story(I.STYLE_ID, I.BREAKOUT_UP, previous=I.ARMED),
            fake_story(J.STYLE_ID, J.PULLBACK_FORMING, previous=J.M30_BULL_CONTEXT),
        ])
        assert decision["style"] == I.STYLE_ID
        assert set(decision["suppressed"]) == {H.STYLE_ID, J.STYLE_ID}

    def test_การเบรกที่ล้มเหลวมีค่าพอ_ๆ_กับการเบรกสำเร็จ(self):
        """สถานะล้มเหลวคือเรื่องที่คนอ่านได้ประโยชน์ ไม่ใช่ความว่างเปล่า"""
        assert selector.WORTH[I.STYLE_ID][I.FAILED_BREAKOUT_UP] >= 9

    def test_ไม่ปล่อยซ้ำเรื่องเดิมกับใบที่เพิ่งเผยแพร่(self):
        stories = [fake_story(H.STYLE_ID, H.BULL_TREND, previous=H.EARLY_BULL)]
        decision = selector.select(stories,
                                   last_published_state={H.STYLE_ID: H.BULL_TREND})
        assert decision["publish"] is False

    def test_ผลลัพธ์ทำซ้ำได้เมื่อคะแนนเท่ากัน(self):
        stories = [fake_story(H.STYLE_ID, H.BULL_TREND, previous=H.NO_TREND),
                   fake_story(I.STYLE_ID, I.ARMED, previous=I.COMPRESSION)]
        first = selector.select(stories)
        assert first["style"] == selector.select(list(reversed(stories)))["style"]


class Testรอบวันปล่อยได้หลายใบ:
    """`select_all` ผ่อนเฉพาะจำนวนใบต่อรอบ — เกณฑ์ 'มีเรื่องให้เขียน' ต้องเท่าเดิมทุกข้อ"""

    def test_ปล่อยทุกใบที่มีเรื่องให้เขียนไม่ใช่ใบเดียว(self):
        decision = selector.select_all([
            fake_story(H.STYLE_ID, H.EARLY_BULL, previous=H.NO_TREND),
            fake_story(I.STYLE_ID, I.BREAKOUT_UP, previous=I.ARMED),
            fake_story(J.STYLE_ID, J.PULLBACK_FORMING, previous=J.M30_BULL_CONTEXT),
        ])
        assert decision["publish"] is True
        assert set(decision["styles"]) == {H.STYLE_ID, I.STYLE_ID, J.STYLE_ID}

    def test_เรียงจากเรื่องใหญ่สุดลงมาเสมอ(self):
        decision = selector.select_all([
            fake_story(H.STYLE_ID, H.EARLY_BULL, previous=H.NO_TREND),
            fake_story(I.STYLE_ID, I.BREAKOUT_UP, previous=I.ARMED),
        ])
        assert decision["styles"] == [I.STYLE_ID, H.STYLE_ID]

    def test_สถานะที่ไม่มีเรื่องให้เขียนยังถูกกันเหมือนเดิม(self):
        """ผ่อนจำนวนใบไม่ใช่ผ่อนเกณฑ์ — NORMAL/NO_M30_BIAS ต้องไม่หลุดเข้ามา"""
        decision = selector.select_all([
            fake_story(I.STYLE_ID, I.NORMAL, previous=I.COMPRESSION),
            fake_story(J.STYLE_ID, J.NO_M30_BIAS, previous=J.M30_BULL_CONTEXT),
            fake_story(H.STYLE_ID, H.BULL_TREND, previous=H.BULL_TREND),
        ])
        assert decision["publish"] is False
        assert decision["styles"] == []

    def test_ใบที่ซ้ำกับของที่เพิ่งเผยแพร่ถูกกันแต่ใบอื่นยังออกได้(self):
        decision = selector.select_all(
            [fake_story(H.STYLE_ID, H.BULL_TREND, previous=H.EARLY_BULL),
             fake_story(I.STYLE_ID, I.ARMED, previous=I.NORMAL)],
            last_published_state={H.STYLE_ID: H.BULL_TREND})
        assert decision["styles"] == [I.STYLE_ID]


class Testทะเบียนเขตเวลาจริงครบทุกหัวข้อที่ผลิต:
    def test_ทุกหัวข้อในสายผลิตต้องมีเขตเวลาลงทะเบียนไว้(self):
        """F/G รันครบทุกหัวข้อ ⇒ ขาดตัวใดตัวหนึ่ง = สไตล์นั้นล้มทั้งหัวข้อตอนรันจริง

        เทสนี้เกิดจากของจริง: รอบแรกที่แก้เขตเวลา ลงทะเบียนแค่ btcusd/xauusd
        แล้วอีกหกหัวข้อจะล้มทันทีที่รอบวันเรียก — เทสสังเคราะห์จับไม่ได้เพราะไม่ได้ยิงจริง
        """
        from tools import build_daily_package
        for asset in sorted(build_daily_package.ASSETS):
            assert intraday_bars.feed_zone(asset) is not None, asset


class Testธงเข้ารอบผลิต:
    def test_ทะเบียนจริงเปิดครบสามสไตล์(self):
        """ผู้ใช้สั่งเปิดทั้งสามเมื่อ 2026-08-13 — เทสนี้จะดังถ้ามีใครปิดโดยไม่ตั้งใจ"""
        assert set(intraday_story.production_styles()) == {
            H.STYLE_ID, I.STYLE_ID, J.STYLE_ID}

    def test_หัวข้อที่เข้ารอบมาจากทะเบียนไม่ใช่รายชื่อในโค้ด(self):
        assert intraday_story.production_assets() == {"btcusd", "xauusd"}

    def test_ปิดธงแล้วสไตล์นั้นหลุดจากรอบทันที(self):
        registry = {H.STYLE_ID: {"assets": ["btcusd"], "production": False},
                    I.STYLE_ID: {"assets": ["xauusd"], "production": True}}
        assert set(intraday_story.production_styles(styles=registry)) == {I.STYLE_ID}
        assert intraday_story.production_assets(styles=registry) == {"xauusd"}


# ============================================== เขตเวลาของป้ายเวลาที่ปลายทางส่งมา

REGISTRY = {
    "assets": {"btcusd": {"offset_minutes": 0}, "xauusd": {"offset_minutes": 600},
               "nvda": {"timezone": "America/New_York"}},
    "default_offset_minutes": None,
    "verification": {"tolerance_spans": 1, "plausible_range_minutes": [-720, 840],
                     "on_mismatch": "raise"},
}


def candle(raw_at: str) -> dict:
    return {"t": raw_at, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5}


class Testเขตเวลาป้ายแท่ง:
    """หัวใจของบั๊ก 2026-08-13 — ป้ายเวลาสองหัวข้อมาจากนาฬิกาคนละเรือน"""

    def test_แปลงป้ายดิบเป็นเวลาไทยตามหัวข้อ(self):
        """เวลาเดียวกันในโลกจริง เขียนป้ายต่างกัน 10 ชม. ⇒ แปลงแล้วต้องได้เวลาไทยเท่ากัน"""
        btc = intraday_bars.rows_from_candles(
            [candle("2026-08-13 06:30:00")], timeframe="15min",
            asset="btcusd", registry=REGISTRY)
        gold = intraday_bars.rows_from_candles(
            [candle("2026-08-13 16:30:00")], timeframe="15min",
            asset="xauusd", registry=REGISTRY)
        assert btc[0]["at"] == "2026-08-13 13:30:00"
        assert gold[0]["at"] == btc[0]["at"]

    def test_เก็บป้ายดิบไว้ให้ตรวจย้อนได้(self):
        rows = intraday_bars.rows_from_candles(
            [candle("2026-08-13 16:30:00")], timeframe="15min",
            asset="xauusd", registry=REGISTRY)
        assert rows[0]["at_feed"] == "2026-08-13 16:30:00"

    def test_วันเปลี่ยนตามเวลาไทยจริงไม่ใช่ตามป้ายดิบ(self):
        """ป้ายดิบของทองข้ามวันก่อนเวลาไทย 3 ชม. ⇒ ช่อง date ต้องยึดเวลาไทย"""
        rows = intraday_bars.rows_from_candles(
            [candle("2026-08-14 01:00:00")], timeframe="1h",
            asset="xauusd", registry=REGISTRY)
        assert rows[0]["date"] == "2026-08-13"
        assert rows[0]["at"] == "2026-08-13 22:00:00"

    def test_เขตเวลาที่มี_DST_ต้องคิดตามฤดูไม่ใช่ค่าตายตัว(self):
        """NVDA ป้ายเป็นเวลานิวยอร์ก — ตัวเลขตายตัวจะถูกครึ่งปีผิดครึ่งปีแบบเงียบ ๆ"""
        summer = intraday_bars.rows_from_candles(
            [candle("2026-08-12 15:30:00")], timeframe="1h",
            asset="nvda", registry=REGISTRY)
        winter = intraday_bars.rows_from_candles(
            [candle("2026-01-12 15:30:00")], timeframe="1h",
            asset="nvda", registry=REGISTRY)
        assert summer[0]["at"] == "2026-08-13 02:30:00"   # EDT = UTC−4
        assert winter[0]["at"] == "2026-01-13 03:30:00"   # EST = UTC−5

    def test_offset_ของเขตเวลามี_DST_ผูกกับเวลาที่ถาม(self):
        assert intraday_bars.feed_offset(
            "nvda", raw_at="2026-08-12 15:30:00", registry=REGISTRY) == timedelta(hours=-4)
        assert intraday_bars.feed_offset(
            "nvda", raw_at="2026-01-12 15:30:00", registry=REGISTRY) == timedelta(hours=-5)

    def test_หัวข้อที่ไม่อยู่ในทะเบียนต้องหยุด_ห้ามเดาว่าเป็นเวลาไทย(self):
        with pytest.raises(intraday_bars.FeedTimezoneUnknown):
            intraday_bars.rows_from_candles(
                [candle("2026-08-13 06:30:00")], timeframe="15min",
                asset="eurusd", registry=REGISTRY)

    def test_วัด_offset_สดได้ตรงกับที่วัดจริงเมื่อ_08_13(self):
        now = datetime(2026, 8, 13, 6, 34, 33, tzinfo=timezone.utc)
        btc = intraday_bars.measure_offset("2026-08-13 06:30:00",
                                           timeframe="15min", now=now)
        gold = intraday_bars.measure_offset("2026-08-13 16:30:00",
                                            timeframe="15min", now=now)
        assert btc == timedelta(0)
        assert gold == timedelta(hours=10)

    def test_ปลายทางขยับฐานเวลาแล้วต้องล้ม_ไม่ใช่เขียนบทด้วยเวลาที่ผิด(self):
        now = datetime(2026, 8, 13, 6, 34, 33, tzinfo=timezone.utc)
        with pytest.raises(intraday_bars.FeedTimezoneDrift):
            intraday_bars.verify_offset("2026-08-13 09:30:00", asset="btcusd",
                                        timeframe="15min", now=now, registry=REGISTRY)

    def test_ปลายทางเผยแพร่ช้าไม่เกินหนึ่งช่วงแท่งยังถือว่าปกติ(self):
        """แท่ง 06:30 โผล่ตอน 06:34 — บางจังหวะแท่งใหม่สุดยังเป็นตัวก่อนหน้าอยู่"""
        now = datetime(2026, 8, 13, 6, 31, tzinfo=timezone.utc)
        check = intraday_bars.verify_offset("2026-08-13 06:15:00", asset="btcusd",
                                            timeframe="15min", now=now, registry=REGISTRY)
        assert check["verified"] is True

    def test_ตลาดปิดวัดไม่ได้จึงใช้ค่าทะเบียนต่อ_ไม่ใช่ล้ม(self):
        """เสาร์-อาทิตย์ของทอง แท่งใหม่สุดคือของวันศุกร์ ⇒ ค่าที่คำนวณได้ผิดมหาศาล"""
        now = datetime(2026, 8, 9, 6, 0, tzinfo=timezone.utc)
        check = intraday_bars.verify_offset("2026-08-07 23:45:00", asset="xauusd",
                                            timeframe="15min", now=now, registry=REGISTRY)
        assert check["verified"] is False
        assert check["measured_offset_minutes"] is None

    def test_ด่านแท่งปิดตัดสินถูกหลังแปลงเวลา(self):
        """บั๊กตัวจริง: แท่งที่ยังก่อตัวเคยถูกนับว่าปิดแล้วเพราะอ่านป้ายผิดเขตเวลา"""
        now = datetime(2026, 8, 13, 6, 34, tzinfo=timezone.utc)
        rows = intraday_bars.rows_from_candles(
            [candle("2026-08-13 06:00:00"), candle("2026-08-13 06:15:00"),
             candle("2026-08-13 06:30:00")],
            timeframe="15min", asset="btcusd", registry=REGISTRY)
        kept, dropped = intraday_bars.trim_to_closed(rows, timeframe="15min", now=now)
        assert kept[-1]["at"] == "2026-08-13 13:15:00"   # 06:15 UTC ปิดแล้ว
        assert dropped == ["2026-08-13 13:30:00"]         # 06:30 UTC ยังก่อตัว

    def test_ธงformingจากปลายทางตัดแท่งแม้สูตรเวลาบอกว่าปิดแล้ว(self):
        """ธง forming (ปลายทางเพิ่มให้ 2026-08-13) ชนะการคำนวณเวลาของเรา —
        เจ้าของข้อมูลบอกเองว่าแท่งยังไม่จบ เช่นจังหวะตลาดเปิด/ปิดพิเศษที่สูตรไม่รู้"""
        now = datetime(2026, 8, 13, 7, 0, tzinfo=timezone.utc)   # 06:30 ปิดไปแล้วตามสูตร
        rows = intraday_bars.rows_from_candles(
            [candle("2026-08-13 06:00:00"), candle("2026-08-13 06:15:00"),
             {**candle("2026-08-13 06:30:00"), "forming": True}],
            timeframe="15min", asset="btcusd", registry=REGISTRY)
        kept, dropped = intraday_bars.trim_to_closed(rows, timeframe="15min", now=now)
        assert kept[-1]["at"] == "2026-08-13 13:15:00"
        assert dropped == ["2026-08-13 13:30:00"]

    def test_แถวพกธงformingและไม่มีธงคือปิดแล้ว(self):
        rows = intraday_bars.rows_from_candles(
            [candle("2026-08-13 06:15:00"),
             {**candle("2026-08-13 06:30:00"), "forming": True}],
            timeframe="15min", asset="btcusd", registry=REGISTRY)
        assert rows[0]["forming"] is False
        assert rows[1]["forming"] is True

    def test_ไม่มีแท่งformingในชุด_ค่าคลาดเกินบันทึกแต่ไม่ล้ม(self):
        """wtiusd 08-13: แท่งใหม่สุดตามหลัง 75 นาทีโดยทั้งชุดไม่มีธง forming เลย
        — วัดจากแท่งปิดแล้วแยกไม่ออกว่าฐานเวลาขยับหรือฟีดตามหลัง จึงห้ามหยุดสาย"""
        now = datetime(2026, 8, 13, 15, 42, tzinfo=timezone.utc)
        check = intraday_bars.verify_offset(
            "2026-08-13 14:15:00", asset="btcusd", timeframe="15min",
            now=now, registry=REGISTRY, forming=False)
        assert check["verified"] is False
        assert check["measured_offset_minutes"] == -75

    def test_มีแท่งformingค่าคลาดเกินต้องล้มเหมือนเดิม(self):
        """ธง forming ยืนยันว่าแท่งที่วัดคือช่องปัจจุบันจริง — คลาดเกิน = ฐานเวลาขยับจริง"""
        now = datetime(2026, 8, 13, 15, 42, tzinfo=timezone.utc)
        with pytest.raises(intraday_bars.FeedTimezoneDrift):
            intraday_bars.verify_offset(
                "2026-08-13 14:15:00", asset="btcusd", timeframe="15min",
                now=now, registry=REGISTRY, forming=True)


# =================================================================== รอบวันของสายท่อ

def fake_feed(rows_by_timeframe: dict[str, list[dict]]):
    """ปลายทางปลอมที่คืนแท่งสังเคราะห์ — รูปคืนค่าตรงกับ `intraday_bars.fetch_rows`"""
    def fetch(asset, *, timeframe, outputsize):
        rows = rows_by_timeframe[timeframe]
        return ({"asset": asset, "timeframe": timeframe, "count": len(rows)},
                [dict(row) for row in rows], f"แท่งสังเคราะห์ · {timeframe}")
    return fetch


@pytest.fixture(scope="module")
def round_feed():
    # แท่ง M30 ปิด 150:00 และ M15 ปิด 150:15 ⇒ บริบทปิดไม่ช้ากว่าทริกเกอร์ (กติกาของ J)
    return fake_feed({"30min": make_rows(300, minutes=30),
                      "15min": make_rows(601, minutes=15)})


class Testรอบวันของสายท่อ:
    def test_ปล่อยได้หลายสไตล์ในรอบเดียวและจำสถานะครบทุกตัว(self, round_feed, tmp_path):
        result = intraday_pipeline.run_round(
            asset="btcusd", state_dir=tmp_path, dry_run=True, fetcher=round_feed)
        assert result["ok"], result
        assert len(result["states"]) == 3
        # ทุกสไตล์ที่คิดได้ต้องถูกจำ ไม่ใช่เฉพาะใบที่ออก — ไม่งั้นรอบหน้าจะเห็นเป็น
        # "รอบแรก" แล้วปล่อยบทซ้ำเรื่องเดิม
        for style_id in result["states"]:
            assert list(tmp_path.glob(f"intraday-{style_id}-btcusd-*.json"))
        assert len(result["articles"]) == len(result["decision"]["styles"])

    def test_รันซ้ำแท่งเดิมไม่ผลิตอะไรเพิ่ม(self, round_feed, tmp_path):
        """กันบทซ้ำเมื่อรอบวันถูกสั่งสองครั้ง — ความจำต้องกันได้เอง ไม่ใช่ให้คนจำ"""
        first = intraday_pipeline.run_round(
            asset="btcusd", state_dir=tmp_path, dry_run=True, fetcher=round_feed)
        second = intraday_pipeline.run_round(
            asset="btcusd", state_dir=tmp_path, dry_run=True, fetcher=round_feed)
        assert second["decision"]["publish"] is False
        assert second["articles"] == []
        assert first["states"] == second["states"]

    def test_สไตล์ที่ธงปิดไม่เข้ารอบและถูกรายงานว่าข้าม(self, round_feed, tmp_path):
        registry = {
            H.STYLE_ID: {"assets": ["btcusd"], "production": True,
                         "folder": "H-แรงเทรนด์-M30"},
            I.STYLE_ID: {"assets": ["btcusd"], "production": False,
                         "folder": "I-เบรกเอาต์-M15"},
            J.STYLE_ID: {"assets": ["btcusd"], "production": False,
                         "folder": "J-ย่อแล้วไปต่อ"},
        }
        result = intraday_pipeline.run_round(
            asset="btcusd", state_dir=tmp_path, dry_run=True, fetcher=round_feed,
            styles=registry)
        assert result["decision"]["styles"] in ([], [H.STYLE_ID])
        off = {item["style"] for item in result["skipped"]
               if "production" in item["reason"]}
        assert off == {I.STYLE_ID, J.STYLE_ID}

    def test_สั่งมือด้วย_run_ยังได้ใบเดียวตามเดิม(self, round_feed, tmp_path):
        """ทางเข้าสองทางต้องไม่กลายเป็นทางเดียวกัน — การยิงถี่ยังต้องได้ใบเดียว"""
        result = intraday_pipeline.run(
            asset="btcusd", state_dir=tmp_path, dry_run=True, fetcher=round_feed)
        assert "articles" not in result
        assert result["decision"]["style"] is not None or not result["decision"]["publish"]
