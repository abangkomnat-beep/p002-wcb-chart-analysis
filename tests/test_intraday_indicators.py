"""เทสเครื่องคำนวณ indicator ของสไตล์ H/I/J

ชุดนี้ตรวจ **นิยามของสูตร** และ **กติกากันมองอนาคต** ไม่ใช่ตรวจว่าค่าตรงกับ
แพลตฟอร์มไหน — เพราะแต่ละเจ้าตั้งค่าเริ่มต้นไม่เหมือนกัน สิ่งที่ต้องคงที่คือ
สูตรของเราเอง และคุณสมบัติที่บทกับภาพพึ่งพาอยู่
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools import intraday_indicators as ind  # noqa: E402


def bars(values: list[tuple[float, float, float, float]]) -> list[dict]:
    """แปลง (o,h,l,c) เป็นแท่งที่มีเวลาเรียงทีละ 15 นาที"""
    rows = []
    for index, (open_, high, low, close) in enumerate(values):
        minute = 15 * index
        rows.append({
            "date": "2026-08-13",
            "at": f"2026-08-13 {minute // 60:02d}:{minute % 60:02d}:00",
            "open": open_, "high": high, "low": low, "close": close,
        })
    return rows


def ramp(count: int, *, start: float = 100.0, step: float = 1.0,
         spread: float = 0.5) -> list[dict]:
    return bars([(start + step * i, start + step * i + spread,
                  start + step * i - spread, start + step * i + step * 0.5)
                 for i in range(count)])


class TestสัญญาของทุกตัวIndicator:
    """ข้อมูลไม่พอต้องได้สถานะ ไม่ใช่ค่าประมาณ — เป็นหัวใจของ fail-closed ทั้งสาย"""

    @pytest.mark.parametrize("compute", [
        lambda rows: ind.atr(rows, 14),
        lambda rows: ind.dmi_adx(rows, 14),
        lambda rows: ind.supertrend(rows, 10, 3.0),
        lambda rows: ind.donchian(rows, 20),
        lambda rows: ind.ichimoku(rows, 9, 26, 52),
        lambda rows: ind.choppiness(rows, 14),
    ])
    def test_แท่งไม่พอคืนสถานะไม่พร้อมและไม่มีค่า(self, compute):
        result = compute(ramp(5))
        assert result["status"] == ind.INSUFFICIENT
        assert not ind.available(result)
        assert "value" not in result or result.get("value") is None

    def test_แท่งขาดช่องราคาถือเป็นอินพุตผิดรูปไม่ใช่ข้อมูลไม่พอ(self):
        rows = ramp(60)
        del rows[-1]["high"]
        with pytest.raises(ind.IndicatorInputError):
            ind.atr(rows, 14)


class TestATR:
    def test_ATRของแท่งช่วงคงที่เท่ากับช่วงนั้น(self):
        # ทุกแท่งกว้าง 2.0 และไม่มี gap ⇒ TR = 2.0 ทุกแท่ง ⇒ ค่าเฉลี่ยแบบใดก็ได้ 2.0
        rows = bars([(100.0, 101.0, 99.0, 100.0) for _ in range(40)])
        result = ind.atr(rows, 14)
        assert result["status"] == ind.AVAILABLE
        assert result["value"] == pytest.approx(2.0)

    def test_ผลลัพธ์ไม่มีช่องบอกทิศ(self):
        """ATR ห้ามมีช่องที่ให้โค้ดอื่นถามหาทิศได้ — กันตั้งแต่ระดับโครงสร้างข้อมูล"""
        result = ind.atr(ramp(40), 14)
        assert "direction" not in result


class TestDMIADX:
    def test_ราคาขึ้นทางเดียวให้บวกDIสูงกว่าลบDI(self):
        result = ind.dmi_adx(ramp(80), 14)
        assert result["status"] == ind.AVAILABLE
        assert result["plus_di"] > result["minus_di"]
        assert result["direction"] == "up"

    def test_ราคาลงทางเดียวให้ลบDIสูงกว่าบวกDI(self):
        result = ind.dmi_adx(ramp(80, start=200.0, step=-1.0), 14)
        assert result["minus_di"] > result["plus_di"]
        assert result["direction"] == "down"

    def test_ADXอยู่ในช่วงศูนย์ถึงหนึ่งร้อย(self):
        result = ind.dmi_adx(ramp(80), 14)
        assert 0.0 <= result["adx"] <= 100.0

    def test_ทิศมาจากDIไม่ใช่ADX(self):
        """ADX เท่ากันได้ทั้งขาขึ้นและขาลง — ทิศจึงต้องมาจาก DI เท่านั้น"""
        up = ind.dmi_adx(ramp(80), 14)
        down = ind.dmi_adx(ramp(80, start=200.0, step=-1.0), 14)
        assert up["adx"] == pytest.approx(down["adx"], rel=0.05)
        assert up["direction"] != down["direction"]


class TestSupertrend:
    def test_ขาขึ้นได้ทิศขึ้นและเส้นอยู่ใต้ราคา(self):
        result = ind.supertrend(ramp(80), 10, 3.0)
        assert result["status"] == ind.AVAILABLE
        assert result["direction"] == "up"
        assert result["value"] < ramp(80)[-1]["close"]

    def test_ขาลงได้ทิศลงและเส้นอยู่เหนือราคา(self):
        rows = ramp(80, start=200.0, step=-1.0)
        result = ind.supertrend(rows, 10, 3.0)
        assert result["direction"] == "down"
        assert result["value"] > rows[-1]["close"]

    def test_ชุดเส้นยาวเท่าจำนวนแท่งเพื่อให้ตัววาดใช้ดัชนีเดียวกับราคาได้(self):
        rows = ramp(80)
        result = ind.supertrend(rows, 10, 3.0)
        assert len(result["line_series"]) == len(rows)
        assert len(result["direction_series"]) == len(rows)


class TestDonchian:
    def test_กรอบไม่นับแท่งสัญญาณเข้าไปตั้งขอบให้ตัวเอง(self):
        """แท่งสุดท้ายทำ high ใหม่สูงลิ่ว — ขอบบนต้องยังเป็นค่าของแท่งก่อนหน้า"""
        rows = bars([(100.0, 101.0, 99.0, 100.0) for _ in range(30)])
        rows[-1] = {**rows[-1], "high": 500.0, "close": 400.0}
        result = ind.donchian(rows, 20)
        assert result["upper"] == pytest.approx(101.0)
        assert result["close_above_upper"] is True
        assert result["excludes_signal_bar"] is True

    def test_ถ้านับแท่งตัวเองราคาจะทะลุกรอบไม่ได้เลย(self):
        """เทสนี้ยืนยันว่าเหตุผลของกฎข้างบนเป็นจริง ไม่ใช่ความระแวง"""
        rows = bars([(100.0, 101.0, 99.0, 100.0) for _ in range(30)])
        rows[-1] = {**rows[-1], "high": 500.0, "close": 400.0}
        including_self = max(float(row["high"]) for row in rows[-20:])
        assert float(rows[-1]["close"]) < including_self


class TestBollingerBandWidth:
    def test_เปอร์เซ็นไทล์วัดเทียบประวัติของตัวเองไม่ใช่ค่าคงที่(self):
        quiet = [(100.0, 100.2, 99.8, 100.0)] * 120
        loud = [(100.0, 115.0, 85.0, 100.0 + (5 if i % 2 else -5)) for i in range(20)]
        result = ind.bollinger_bandwidth(bars(quiet + loud), 20, 2.0, 200)
        assert result["status"] == ind.AVAILABLE
        assert result["percentile"] > 80

    def test_หน้าต่างเปอร์เซ็นไทล์ไม่กินแท่งอนาคต(self):
        """คำนวณด้วยข้อมูลถึงแท่ง N ต้องได้ค่าเดียวกับตอนมีข้อมูลถึงแท่ง N+20"""
        rows = ramp(200, spread=1.5)
        early = ind.bollinger_bandwidth(rows[:150], 20, 2.0, 200)
        late = ind.bollinger_bandwidth(rows[:170], 20, 2.0, 200)
        assert early["series"] == late["series"][:len(early["series"])]


class TestIchimoku:
    def test_เมฆที่ใช้เทียบราคาถูกคำนวณจากแท่งในอดีตไม่ใช่แท่งล่าสุด(self):
        rows = ramp(120)
        result = ind.ichimoku(rows, 9, 26, 52)
        assert result["status"] == ind.AVAILABLE
        cloud = result["cloud_now"]
        assert cloud["calculated_at"] == rows[-1 - 26]["at"]
        assert cloud["plotted_at"] == rows[-1]["at"]
        assert cloud["calculated_at"] != cloud["plotted_at"]

    def test_เมฆที่คำนวณจากแท่งล่าสุดถูกแยกไว้คนละช่องเพราะยังไม่ถึงตำแหน่ง(self):
        result = ind.ichimoku(ramp(120), 9, 26, 52)
        assert result["cloud_ahead"]["span_a"] != result["cloud_now"]["span_a"]

    def test_ขาขึ้นให้ราคาอยู่เหนือเมฆ(self):
        result = ind.ichimoku(ramp(120), 9, 26, 52)
        assert result["position"] == "above"
        assert result["tenkan_above_kijun"] is True


class TestChoppiness:
    def test_ตลาดเดินทางเดียวให้ค่าต่ำกว่าตลาดแกว่งไปมา(self):
        trending = ind.choppiness(ramp(60), 14)
        swing = ind.choppiness(bars([(100.0, 102.0, 98.0, 100.0 + (2 if i % 2 else -2))
                                     for i in range(60)]), 14)
        assert trending["value"] < swing["value"]

    def test_ค่าอยู่ในช่วงที่นิยามไว้(self):
        result = ind.choppiness(ramp(60), 14)
        assert 0.0 <= result["value"] <= 100.0
        assert not math.isnan(result["value"])
