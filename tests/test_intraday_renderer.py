"""เทสตัววาดภาพของสไตล์ H/I/J

เทสชุดนี้ไม่ตรวจว่าภาพ "สวย" — ตรวจสามข้อที่พังแล้วเสียหายจริง:

    1. ได้ภาพครบสองใบ ชื่อตรงกับที่บทอ้าง และผ่านเพดานขนาดไฟล์
    2. **ส่งแท่งผิดกรอบเวลาให้ตัววาดแล้วต้องล้ม** — บั๊กที่เจอจริง 2026-08-13
       (ภาพของ H เกือบเป็นแท่ง M15 ที่มีเส้นของ M30 ลากทับ)
    3. เส้นในภาพกับเลขในบทต้องมาจากค่าเดียวกัน
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools import image_output, intraday_renderer  # noqa: E402
from tools import intraday_breakout_writer, intraday_pullback_writer  # noqa: E402
from tools import intraday_trend_writer, intraday_writer_base  # noqa: E402
from tests.test_intraday_styles import basis_for, make_rows, quiet_then  # noqa: E402
from tools import intraday_breakout_story as I  # noqa: E402
from tools import intraday_pullback_story as J  # noqa: E402
from tools import intraday_trend_story as H  # noqa: E402

CONTEXT = "30min"
TRIGGER = "15min"


@pytest.fixture(scope="module")
def bars() -> dict:
    return {CONTEXT: make_rows(200, minutes=30),
            TRIGGER: quiet_then(400, minutes=15)}


@pytest.fixture(scope="module")
def stories(bars) -> dict:
    context, trigger = bars[CONTEXT], bars[TRIGGER]
    return {
        "h": H.build(context, asset="btcusd", timeframe=CONTEXT,
                     candle_basis=basis_for(context, CONTEXT)),
        "i": I.build(trigger, asset="btcusd", timeframe=TRIGGER,
                     candle_basis=basis_for(trigger, TRIGGER)),
        "j": J.build(context, trigger, asset="btcusd",
                     candle_basis=basis_for(trigger, TRIGGER),
                     context_basis=basis_for(context, CONTEXT)),
    }


WRITERS = {"h": intraday_trend_writer, "i": intraday_breakout_writer,
           "j": intraday_pullback_writer}


@pytest.mark.parametrize("key", ["h", "i", "j"])
def test_ได้ภาพครบสองใบชื่อตรงกับที่บทอ้างและไม่เกินเพดานขนาด(key, stories, bars, tmp_path):
    story, writer = stories[key], WRITERS[key]
    results = intraday_renderer.render(story, bars, tmp_path, writer)
    names = [Path(item["path"]).name for item in results]
    expected = [figure["name"] for figure in intraday_writer_base.figures(story, writer)]
    assert names == expected
    for item in results:
        assert Path(item["path"]).exists()
        assert item["bytes"] <= image_output.MAX_IMAGE_BYTES


def test_ภาพหลักของJเป็นกรอบบริบทไม่ใช่กรอบของบท(stories, bars, tmp_path):
    """ชื่อไฟล์ต้องบอกกรอบของ *ภาพ* ไม่ใช่กรอบของบท ไม่งั้นไฟล์โกหกเรื่องข้างในตัวเอง"""
    story = stories["j"]
    results = intraday_renderer.render(story, bars, tmp_path, intraday_pullback_writer)
    assert f"-{CONTEXT}-" in Path(results[0]["path"]).name
    assert f"-{TRIGGER}-" in Path(results[1]["path"]).name


def test_ส่งแท่งผิดกรอบเวลาให้ตัววาดแล้วต้องล้มไม่ใช่วาดออกมาเงียบ_ๆ(stories, bars, tmp_path):
    story = stories["h"]                       # story คิดจากแท่ง 30 นาที
    wrong = {CONTEXT: bars[TRIGGER], TRIGGER: bars[TRIGGER]}
    with pytest.raises(intraday_renderer.ChartMismatch):
        intraday_renderer.render(story, wrong, tmp_path, intraday_trend_writer)


def test_ไม่มีชุดแท่งของกรอบที่ภาพต้องใช้แล้วต้องล้ม(stories, bars, tmp_path):
    with pytest.raises(intraday_renderer.ChartMismatch):
        intraday_renderer.render(stories["j"], {TRIGGER: bars[TRIGGER]}, tmp_path,
                                 intraday_pullback_writer)


def test_ด่านเทียบค่าท้ายจับความต่างเล็กน้อยได้(stories):
    with pytest.raises(intraday_renderer.ChartMismatch):
        intraday_renderer._verify_tail([1.0, 2.0, 3.0], 3.5, label="ทดสอบ")
    intraday_renderer._verify_tail([1.0, 2.0, 3.0], 3.0, label="ทดสอบ")


def test_ด่านเทียบค่าท้ายจับกรณีคำนวณไม่ได้(stories):
    with pytest.raises(intraday_renderer.ChartMismatch):
        intraday_renderer._verify_tail([None], 1.0, label="ทดสอบ")
