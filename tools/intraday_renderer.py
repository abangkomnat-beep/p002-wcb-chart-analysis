"""ตัววาดภาพประกอบของสไตล์ H/I/J — สองใบต่อบท (ภาพหลัก + แผงหลักฐาน)

ข้อเสนอ §58 ยืนยันว่าภาพเป็น **ภาคบังคับ** ของสามสไตล์นี้ ไม่ใช่ของเสริม —
และ §74 แยกสองชั้นไว้ถูกต้อง: ชั้นข้อเท็จจริงต้องถูกคุมด้วยโค้ด ส่วนชั้นจัดวางสวยงาม
ห้ามบิดข้อมูล ⇒ ที่นี่วาด **ชั้นข้อเท็จจริง** ทั้งหมดจากแท่งจริงและ indicator จริง
ป้ายและกล่องสรุปบนภาพหยิบข้อความมาจาก story เท่านั้น ไม่มีการตีความใหม่บนภาพ

🔒 **ด่านสำคัญที่สุดของไฟล์นี้: `_verify_tail`**

ตัววาดต้องคำนวณ indicator เป็น *ชุดตลอดหน้าต่าง* ถึงจะลากเส้นได้ ขณะที่บทอ้าง
*ค่าจุดเดียว* จาก story ⇒ มีโอกาสที่เส้นในภาพกับเลขในบทมาจากคนละสูตรโดยไม่มีใครรู้
(กับดักเดียวกับที่เคยทำให้บท G เขียนว่า Sideway-Down ขณะที่ภาพเป็นช่องขาขึ้น)
⇒ ทุกชุดที่คำนวณที่นี่ **ต้องเทียบค่าตัวสุดท้ายกับค่าใน story ก่อนวาด** ไม่ตรง = โยนทั้งใบ

การคำนวณแบบ 'หน้าต่างขยาย' (`rows[:k]`) ให้ค่าตรงกับการคำนวณครั้งเดียวเสมอ เพราะ
ค่าเฉลี่ยแบบ Wilder เดินจากต้นอาเรย์เหมือนกันทั้งสองทาง — จุดเริ่มเดียวกัน ผลลัพธ์เดียวกัน
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import consistency_gate, image_output, intraday_indicators  # noqa: E402
from tools import intraday_writer_base as base  # noqa: E402
from tools import wcb_source  # noqa: E402
from tools.chart_renderer import THAI_MONTHS  # noqa: E402
from tools.chart_story_renderer import _thai_font, thai_date  # noqa: E402

FIGURE_SIZE = (10.40, 7.00)
EVIDENCE_SIZE = (10.40, 6.20)
DPI = 100
RIGHT_PAD_FRACTION = 0.18
# ที่ว่างขวามือของแผงหลักฐาน — **ที่จอดของป้ายเกณฑ์เท่านั้น** ไม่ใช่การตกแต่ง
# เดิมป้าย "เกณฑ์ 25/20" วางที่ขอบขวาของกรอบพอดี แล้วมันไปนั่งทับเส้น ADX ซึ่งวิ่ง
# แถวนั้นบ่อยที่สุด (ผู้ใช้ตีกลับ 08-14) ⇒ ดันขอบขวาออกไปแล้ววางป้ายในที่ว่างแทน
PANEL_PAD_FRACTION = 0.085

# ขนาดตัวอักษรของชิปหลักฐานบนหัวการ์ด — ตัวเลขต้องอ่านออกจากภาพย่อบนหน้าเว็บ
# (ผู้ใช้สั่งขยาย 08-14) · ความกว้างชิปใน `_header` คิดจากสองค่านี้ ปรับแล้วต้องดูคู่กัน
CHIP_CAPTION_SIZE = 12.5
CHIP_VALUE_SIZE = 18.0

# ความคลาดเคลื่อนที่ยอมให้ระหว่างค่าที่ตัววาดคำนวณกับค่าใน story — เผื่อเลขทศนิยม
# ลอยตัวเท่านั้น ไม่ได้เผื่อ "สูตรต่างกันนิดหน่อย"
TAIL_TOLERANCE = 1e-6

COLORS = {
    "card": "#12233b",
    "panel": "#ffffff",
    "grid": "#eef1f5",
    "axis": "#787b86",
    "text": "#131722",
    "up": "#26a69a",
    "down": "#ef5350",
    "trend_up": "#1e9e83",
    "trend_down": "#e5484d",
    "level": "#101418",
    "zone": "#f0a02a",
    "plus_di": "#1e9e83",
    "minus_di": "#e5484d",
    "adx": "#3949ab",
    "atr": "#6a7383",
    "bbw": "#8e44ad",
    "chop": "#3949ab",
    "cloud_up": "#1e9e83",
    "cloud_down": "#e5484d",
    "chip_state": "#12233b",
    "chip_value": "#1e9e83",
    "chip_level": "#f0a02a",
}


class ChartMismatch(RuntimeError):
    """เส้นในภาพกับเลขในบทมาจากคนละค่า — ห้ามปล่อยภาพออกไป"""


def checked(text: str) -> str:
    findings = consistency_gate.check_labels([text])
    if findings:
        raise ValueError(f"ป้ายภาพไม่ผ่านด่านความสอดคล้อง: {findings[0]['message']}")
    return text


# ------------------------------------------------------------------ ชุดค่า indicator

def series_tail(rows: list[dict], bars: int, compute, key) -> list[float | None]:
    """ค่าของ indicator ตลอดหน้าต่างท้าย `bars` แท่ง — `None` ในช่วงที่ยังคำนวณไม่ได้"""
    out: list[float | None] = []
    for end in range(len(rows) - bars + 1, len(rows) + 1):
        result = compute(rows[:end])
        out.append(key(result) if intraday_indicators.available(result) else None)
    return out


def _verify_tail(series: list[float | None], expected: float, *, label: str) -> None:
    if not series or series[-1] is None:
        raise ChartMismatch(f"{label}: ตัววาดคำนวณค่าท้ายไม่ได้ แต่บทอ้างค่านี้อยู่")
    gap = abs(series[-1] - expected)
    scale = max(1.0, abs(expected))
    if gap / scale > TAIL_TOLERANCE:
        raise ChartMismatch(
            f"{label}: ค่าท้ายที่ตัววาดคำนวณได้ ({series[-1]!r}) ไม่ตรงกับค่าในบท "
            f"({expected!r}) — ภาพกับข้อความจะเล่าคนละเลข")


# ---------------------------------------------------------------------- โครงการ์ด

def _card(figure, Rectangle) -> None:
    figure.patch.set_facecolor(COLORS["card"])
    figure.add_artist(Rectangle((0.022, 0.030), 0.956, 0.940, transform=figure.transFigure,
                                facecolor=COLORS["panel"], edgecolor="none", zorder=0))


def _chip(figure, x: float, width: float, color: str, caption: str, value: str,
          *, y: float = 0.845) -> None:
    from matplotlib.patches import FancyBboxPatch

    figure.add_artist(FancyBboxPatch((x, y), width, 0.052,
                                     boxstyle="round,pad=0.006,rounding_size=0.012",
                                     transform=figure.transFigure, facecolor=color,
                                     edgecolor="none", zorder=3))
    figure.text(x + width / 2, y + 0.026, checked(caption), transform=figure.transFigure,
                ha="center", va="center", color="#ffffff", fontsize=CHIP_CAPTION_SIZE,
                fontweight="bold", zorder=4)
    figure.text(x + width / 2, y - 0.042, checked(value), transform=figure.transFigure,
                ha="center", va="center", color=COLORS["text"], fontsize=CHIP_VALUE_SIZE,
                fontweight="bold", zorder=4)


def _header(figure, story: dict, chips: list[tuple[str, str, str]]) -> None:
    """แถบหัวการ์ด — ชิปหลักฐานฝั่งซ้าย ชื่อคู่เงินฝั่งขวา"""
    x = 0.052
    for color, caption, value in chips:
        # ความกว้างต้องพอทั้ง**ค่า**และ**คำกำกับ** — เดิมคิดจากค่าอย่างเดียว แล้วชิปที่
        # ค่าสั้นแต่คำกำกับยาว ("อันดับ BandWidth" คู่กับ "80") มีตัวหนังสือล้นออกนอกกล่อง
        # ตัวคูณผูกกับขนาดตัวอักษรจริง ⇒ ขยายฟอนต์แล้วกล่องขยายตาม ไม่ต้องจูนมือ
        width = max(0.115, 0.032 + max(0.0011 * CHIP_VALUE_SIZE * len(value),
                                       0.0010 * CHIP_CAPTION_SIZE * len(caption)))
        _chip(figure, x, width, color, caption, value)
        x += width + 0.016
    symbol = wcb_source.profile_for(story["asset"])["symbol"]
    figure.text(0.960, 0.848, checked(f"แนวโน้มราคา {symbol}"),
                transform=figure.transFigure, ha="right", va="center",
                color=COLORS["text"], fontsize=25, fontweight="bold", zorder=4)


def _footer(figure, story: dict, tail: str) -> None:
    figure.text(0.5, 0.055, checked(tail), transform=figure.transFigure, ha="center",
                va="center", color=COLORS["axis"], fontsize=10.5, zorder=4)


def _style_axes(axes, *, labels: bool = True) -> None:
    axes.set_facecolor(COLORS["panel"])
    for spine in axes.spines.values():
        spine.set_color("#d1d4dc")
    axes.tick_params(colors=COLORS["axis"], labelsize=9.5)
    axes.grid(True, color=COLORS["grid"], linewidth=0.8)
    axes.yaxis.tick_right()
    axes.set_axisbelow(True)
    if not labels:
        axes.set_xticklabels([])


def _draw_candles(axes, view: list[dict], Rectangle) -> None:
    width = 0.62
    for index, row in enumerate(view):
        rising = row["close"] >= row["open"]
        color = COLORS["up"] if rising else COLORS["down"]
        axes.plot([index, index], [row["low"], row["high"]], color=color,
                  linewidth=0.9, zorder=3)
        body_low = min(row["open"], row["close"])
        height = abs(row["close"] - row["open"]) or (row["high"] - row["low"]) * 0.02 or 1e-9
        axes.add_patch(Rectangle((index - width / 2, body_low), width, height,
                                 facecolor=color, edgecolor=color, linewidth=0.5, zorder=3))


def _tick_labels(view: list[dict]) -> tuple[list[int], list[str]]:
    """ป้ายแกนเวลาของกรอบระหว่างวัน — เดินทีละวัน ไม่ใช่ทีละเดือน

    หน้าต่างของ M15/M30 กินเวลาไม่กี่วัน ถ้าใช้ป้ายรายเดือนจะได้ป้ายเดียวทั้งภาพ
    """
    positions, labels, seen = [], [], None
    for index, row in enumerate(view):
        if row["date"] == seen:
            continue
        seen = row["date"]
        day, month = int(row["date"][8:10]), int(row["date"][5:7])
        positions.append(index)
        labels.append(f"{day} {THAI_MONTHS[month - 1]}")
    return positions, labels


def _state_badge(axes, story: dict, spec=None) -> None:
    """ป้ายสถานะบนภาพ — **ยกมาจาก story ตรง ๆ** ไม่ตีความใหม่บนภาพ

    สไตล์ที่ประกาศ `badge_text(story)` ได้ข้อความไทยของตัวเอง (H ทำแล้ว 08-14 —
    `BEAR_TREND` ตัวพิมพ์ใหญ่ติดขีดล่างอ่านเหมือนชื่อตัวแปรในโค้ด) · ข้อความนั้นต้อง
    มาจากทะเบียนคำประจำสถานะของสไตล์ ไม่ใช่คำที่ตัววาดคิดเอง หลัก "ไม่ตีความบนภาพ"
    จึงยังอยู่ครบ · สไตล์ที่ไม่ประกาศ ได้รหัสสถานะดิบเหมือนเดิม
    """
    label = getattr(spec, "badge_text", None)
    axes.text(0.012, 0.955, checked(label(story) if label else story["state"]),
              transform=axes.transAxes, ha="left", va="top", fontsize=13,
              fontweight="bold", color="#ffffff", zorder=8,
              bbox={"facecolor": COLORS["chip_state"], "edgecolor": "none",
                    "boxstyle": "round,pad=0.35"})


def _level_line(axes, value: float, x_right: float, text: str, color: str) -> None:
    """เส้นระดับ + ป้ายกำกับ **บนเส้น** ด้วยพื้นทึบสีเข้ม

    เดิมป้ายเป็นตัวหนังสือสีเข้มบนพื้นขาวโปร่ง 85% วางคาบเส้น ⇒ ตัวอักษรไปซ้อนกับ
    แท่งเทียนแถวขอบขวาจนอ่านไม่ออก (ผู้ใช้ตีกลับ 08-14) · พื้นทึบสีเข้มกับตัวอักษรขาว
    อ่านออกไม่ว่าอะไรอยู่ข้างหลัง และ `va="bottom"` ยกป้ายขึ้นไปอยู่เหนือเส้น ไม่คาบเส้น
    """
    axes.plot([-0.5, x_right], [value, value], color=color, linewidth=1.5,
              linestyle=(0, (5, 4)), zorder=5)
    axes.text(x_right, value, checked(text), ha="right", va="bottom", fontsize=10.5,
              fontweight="bold", color="#ffffff", zorder=8,
              bbox={"facecolor": COLORS["level"], "edgecolor": "none",
                    "boxstyle": "round,pad=0.32"})


def _finish_price_axes(axes, view: list[dict], extra: list[float], x_right: float,
                       *, labels: bool = True) -> None:
    lows = [row["low"] for row in view] + list(extra)
    highs = [row["high"] for row in view] + list(extra)
    pad = (max(highs) - min(lows)) * 0.09 or 1.0
    axes.set_xlim(-0.5, x_right)
    axes.set_ylim(min(lows) - pad, max(highs) + pad)
    positions, tick_labels = _tick_labels(view)
    axes.set_xticks(positions)
    axes.set_xticklabels([checked(label) for label in tick_labels] if labels else [])


def _save(figure, output_path: Path, story: dict, slot: str) -> dict:
    size = image_output.save_figure(figure, Path(output_path),
                                    facecolor=figure.get_facecolor())
    return {"path": str(output_path), "bytes": size, "kb": image_output.kb(size),
            "style": story["style"], "slot": slot}


def _footer_text(story: dict, extra: str) -> str:
    profile = wcb_source.profile_for(story["asset"])
    words = base.tf_words(story)
    return (f"{profile['symbol']} · {words['bar']} · ช่วงที่แสดง "
            f"{thai_date(story['display']['start_date'])} ถึง "
            f"{thai_date(story['display']['end_date'])} · {extra}")


# ------------------------------------------------------------------------- สไตล์ H

def _render_trend_hero(story: dict, rows: list[dict], output_path: Path, spec) -> dict:
    from matplotlib import pyplot
    from matplotlib.patches import Rectangle

    money = base.money_for(story)
    bars = story["display"]["bars"]
    view = rows[-bars:]
    line = story["supertrend"]["line_series"][-bars:]
    if line[-1] is None or abs(line[-1] - story["supertrend"]["value"]) > TAIL_TOLERANCE:
        raise ChartMismatch("Supertrend: ค่าท้ายของเส้นในภาพไม่ตรงกับค่าในบท")
    direction = story["supertrend"]["direction_series"][-bars:]

    figure = pyplot.figure(figsize=FIGURE_SIZE, dpi=DPI)
    try:
        _card(figure, Rectangle)
        axes = figure.add_axes((0.055, 0.130, 0.845, 0.630))
        _style_axes(axes)
        _draw_candles(axes, view, Rectangle)
        # เส้น Supertrend แยกสีตามทิศ ณ แต่ละแท่ง — ตัดเส้นตรงจุดที่พลิกทิศ
        # ไม่งั้นจะมีเส้นเฉียงยาวลากข้ามราคาในแท่งที่พลิก ซึ่งไม่มีอยู่จริง
        start = 0
        for index in range(1, bars + 1):
            if index == bars or direction[index] != direction[start]:
                xs = [i for i in range(start, index) if line[i] is not None]
                if len(xs) >= 2:
                    axes.plot(xs, [line[i] for i in xs],
                              color=COLORS["trend_up"] if direction[start] == "up"
                              else COLORS["trend_down"], linewidth=2.0, zorder=5)
                start = index
        x_right = bars - 1 + bars * RIGHT_PAD_FRACTION
        # ใช้ชื่อระดับจากสไตล์เดียวกับเนื้อบท: ขาลงเป็นแนวต้าน ขาขึ้นเป็นแนวรับ
        # เพื่อให้บทบาทของเส้นชัดกว่าศัพท์ระบบ "invalidation"
        label = getattr(spec, "invalidation_label", lambda _story: "ระดับเปลี่ยนเทรนด์")
        _level_line(axes, story["invalidation"]["level"], x_right,
                    f"{label(story)} {money(story['invalidation']['level'])}",
                    COLORS["level"])
        _state_badge(axes, story, spec)
        _finish_price_axes(axes, view, [story["invalidation"]["level"]], x_right)
        _header(figure, story, [
            (COLORS["chip_value"], "ราคาปิด", money(story["close"])),
            (COLORS["chip_level"], "ADX", base.one(story["dmi"]["adx"]))])
        _footer(figure, story, _footer_text(story, base.STYLE_FOOTER["H"]))
        return _save(figure, output_path, story, "hero")
    finally:
        pyplot.close(figure)


def _render_trend_evidence(story: dict, rows: list[dict], output_path: Path, spec) -> dict:
    from matplotlib import pyplot
    from matplotlib.patches import Rectangle

    money = base.money_for(story)
    bars = story["display"]["bars"]
    view = rows[-bars:]
    length = story["dmi"]["length"]
    plus = series_tail(rows, bars, lambda r: intraday_indicators.dmi_adx(r, length),
                       lambda x: x["plus_di"])
    minus = series_tail(rows, bars, lambda r: intraday_indicators.dmi_adx(r, length),
                        lambda x: x["minus_di"])
    adx = series_tail(rows, bars, lambda r: intraday_indicators.dmi_adx(r, length),
                      lambda x: x["adx"])
    atr_length = story["atr"]["length"]
    atr = series_tail(rows, bars, lambda r: intraday_indicators.atr(r, atr_length),
                      lambda x: x["value"])
    _verify_tail(plus, story["dmi"]["plus_di"], label="+DI")
    _verify_tail(minus, story["dmi"]["minus_di"], label="-DI")
    _verify_tail(adx, story["dmi"]["adx"], label="ADX")
    _verify_tail(atr, story["atr"]["value"], label="ATR")

    figure = pyplot.figure(figsize=EVIDENCE_SIZE, dpi=DPI)
    try:
        _card(figure, Rectangle)
        top = figure.add_axes((0.055, 0.395, 0.845, 0.360))
        bottom = figure.add_axes((0.055, 0.130, 0.845, 0.215))
        _style_axes(top, labels=False)
        _style_axes(bottom)
        xs = list(range(bars))
        # คู่เส้น DI หนากว่าเส้น ADX โดยเจตนา (ผู้ใช้สั่ง 08-14) — สามเส้นหนาเท่ากัน
        # ในแผงเดียวทำให้ต้องไล่สีก่อนจะรู้ว่าเส้นไหนตอบคำถามไหน · DI ตอบเรื่องทิศ
        # ซึ่งเป็นคำถามแรกที่คนอ่านถาม จึงให้มันเด่นกว่าเส้นความแข็งแรง
        for values, color, label, width in ((plus, COLORS["plus_di"], "+DI", 2.4),
                                            (minus, COLORS["minus_di"], "-DI", 2.4),
                                            (adx, COLORS["adx"], "ADX", 1.7)):
            points = [(x, value) for x, value in zip(xs, values) if value is not None]
            top.plot([p[0] for p in points], [p[1] for p in points], color=color,
                     linewidth=width, zorder=4, label=checked(label))
        # ป้ายเกณฑ์ไปอยู่ในที่ว่างขวามือ **นอกช่วงที่มีเส้น** ไม่ใช่ที่ขอบขวาของกรอบ
        panel_right = bars - 1 + bars * PANEL_PAD_FRACTION
        for level, color in ((story["thresholds"]["no_trend"], COLORS["axis"]),
                             (story["thresholds"]["trend"], COLORS["level"])):
            top.axhline(level, color=color, linewidth=1.2, linestyle=(0, (4, 4)), zorder=3)
            top.text(panel_right, level, checked(f"เกณฑ์ {base.plain(level)}"), ha="right",
                     va="center", fontsize=10, color=COLORS["text"], zorder=6,
                     bbox={"facecolor": COLORS["panel"], "edgecolor": "none", "pad": 1.5})
        top.legend(loc="upper left", fontsize=10, framealpha=0.9)
        top.set_xlim(-0.5, panel_right)

        points = [(x, value) for x, value in zip(xs, atr) if value is not None]
        bottom.plot([p[0] for p in points], [p[1] for p in points], color=COLORS["atr"],
                    linewidth=1.9, zorder=4)
        bottom.fill_between([p[0] for p in points], 0, [p[1] for p in points],
                            color=COLORS["atr"], alpha=0.12, zorder=2)
        # แผงล่างต้องกว้างเท่าแผงบนเป๊ะ ไม่งั้นแกนเวลาสองแผงเลื่อนจากกันทั้งภาพ
        bottom.set_xlim(-0.5, panel_right)
        bottom.set_ylim(0, max(p[1] for p in points) * 1.25)
        positions, tick_labels = _tick_labels(view)
        bottom.set_xticks(positions)
        bottom.set_xticklabels([checked(label) for label in tick_labels])
        bottom.text(0.012, 0.90, checked(f"ATR {base.plain(atr_length)} — ความกว้าง"
                                         f"การแกว่งต่อแท่ง"),
                    transform=bottom.transAxes, ha="left", va="top", fontsize=10.5,
                    color=COLORS["text"], zorder=6)

        # ชิป DI แยกเป็นสองใบ **สีเดียวกับเส้นในแผง** (ผู้ใช้สั่ง 08-14) — ใบรวม
        # "+DI เทียบ -DI  10.7 / 37.7" ใช้สีเดียว คนอ่านต้องเดาว่าเลขไหนเป็นของเส้นไหน
        _header(figure, story, [
            (COLORS["plus_di"], "+DI", base.one(story["dmi"]["plus_di"])),
            (COLORS["minus_di"], "-DI", base.one(story["dmi"]["minus_di"])),
            (COLORS["chip_level"], "ATR", money(story["atr"]["value"]))])
        _footer(figure, story, _footer_text(story, "แผงหลักฐาน DMI ADX และ ATR"))
        return _save(figure, output_path, story, "evidence")
    finally:
        pyplot.close(figure)


# ------------------------------------------------------------------------- สไตล์ I

def _render_breakout_hero(story: dict, rows: list[dict], output_path: Path, spec) -> dict:
    from matplotlib import pyplot
    from matplotlib.patches import Rectangle

    money = base.money_for(story)
    bars = story["display"]["bars"]
    view = rows[-bars:]
    length = story["donchian"]["length"]
    upper = series_tail(rows, bars, lambda r: intraday_indicators.donchian(r, length),
                        lambda x: x["upper"])
    lower = series_tail(rows, bars, lambda r: intraday_indicators.donchian(r, length),
                        lambda x: x["lower"])
    _verify_tail(upper, story["donchian"]["upper"], label="ขอบบน Donchian")
    _verify_tail(lower, story["donchian"]["lower"], label="ขอบล่าง Donchian")

    figure = pyplot.figure(figsize=FIGURE_SIZE, dpi=DPI)
    try:
        _card(figure, Rectangle)
        axes = figure.add_axes((0.055, 0.130, 0.845, 0.630))
        _style_axes(axes)
        xs = list(range(bars))
        # ขอบกรอบเป็นเส้นขั้นบันได (step) ไม่ใช่เส้นเฉียง — เพราะค่ามันคงที่ตลอดแท่ง
        # แล้วกระโดดเมื่อหน้าต่างเลื่อน การลากเฉียงจะให้ภาพว่าขอบขยับทีละนิด ซึ่งไม่จริง
        for values, color in ((upper, COLORS["zone"]), (lower, COLORS["zone"])):
            points = [(x, value) for x, value in zip(xs, values) if value is not None]
            axes.step([p[0] for p in points], [p[1] for p in points], where="post",
                      color=color, linewidth=1.9, zorder=5)
        band = [(x, u, l) for x, u, l in zip(xs, upper, lower)
                if u is not None and l is not None]
        axes.fill_between([p[0] for p in band], [p[2] for p in band], [p[1] for p in band],
                          color=COLORS["zone"], alpha=0.08, step="post", zorder=2)
        _draw_candles(axes, view, Rectangle)
        # ไฮไลต์แท่งล่าสุด — แท่งที่ระบบใช้ตัดสินสถานะรอบนี้
        last = view[-1]
        axes.add_patch(Rectangle((bars - 1 - 0.5, last["low"]), 1.0,
                                 last["high"] - last["low"], facecolor="none",
                                 edgecolor=COLORS["level"], linewidth=1.6,
                                 linestyle=(0, (3, 2)), zorder=6))
        x_right = bars - 1 + bars * RIGHT_PAD_FRACTION
        _level_line(axes, story["invalidation"]["level"], x_right,
                    f"ขอบที่ใช้ตัดสิน {money(story['invalidation']['level'])}",
                    COLORS["level"])
        _state_badge(axes, story, spec)
        _finish_price_axes(axes, view, [story["donchian"]["upper"],
                                        story["donchian"]["lower"]], x_right)
        _header(figure, story, [
            (COLORS["chip_value"], "ราคาปิด", money(story["close"])),
            (COLORS["chip_level"], "อันดับ BandWidth",
             base.whole(story["bbw"]["percentile"]))])
        _footer(figure, story, _footer_text(story, base.STYLE_FOOTER["I"]))
        return _save(figure, output_path, story, "hero")
    finally:
        pyplot.close(figure)


def _render_breakout_evidence(story: dict, rows: list[dict], output_path: Path,
                              spec) -> dict:
    from matplotlib import pyplot
    from matplotlib.patches import Rectangle

    money = base.money_for(story)
    bars = story["display"]["bars"]
    view = rows[-bars:]
    # ชุด BandWidth เริ่มช้ากว่าแท่งแรกของหน้าต่างได้ (ต้องอุ่นเครื่องตามความยาวแถบ)
    # ⇒ เติมช่องว่างด้านหน้าให้ยาวเท่าหน้าต่างเสมอ ไม่งั้นดัชนีแกน x จะเลื่อนทั้งเส้น
    full = story["bbw"]["series"]
    bbw: list[float | None] = [None] * max(0, bars - len(full)) + list(full[-bars:])
    if bbw[-1] is None or abs(bbw[-1] - story["bbw"]["value"]) > TAIL_TOLERANCE:
        raise ChartMismatch("BandWidth: ค่าท้ายของเส้นในภาพไม่ตรงกับค่าในบท")
    atr_length = story["atr"]["length"]
    atr = series_tail(rows, bars, lambda r: intraday_indicators.atr(r, atr_length),
                      lambda x: x["value"])
    _verify_tail(atr, story["atr"]["value"], label="ATR")

    figure = pyplot.figure(figsize=EVIDENCE_SIZE, dpi=DPI)
    try:
        _card(figure, Rectangle)
        top = figure.add_axes((0.055, 0.395, 0.845, 0.360))
        bottom = figure.add_axes((0.055, 0.130, 0.845, 0.215))
        _style_axes(top, labels=False)
        _style_axes(bottom)
        xs = list(range(bars))
        drawn = [(x, value) for x, value in zip(xs, bbw) if value is not None]
        top.plot([p[0] for p in drawn], [p[1] for p in drawn], color=COLORS["bbw"],
                 linewidth=1.9, zorder=4)
        top.fill_between([p[0] for p in drawn], 0, [p[1] for p in drawn],
                         color=COLORS["bbw"], alpha=0.10, zorder=2)
        # เส้นเกณฑ์บีบตัวคิดจาก **ประวัติของหัวข้อนี้เอง** — ค่าที่อันดับเปอร์เซ็นไทล์
        # ที่กำหนด ไม่ใช่ตัวเลข BandWidth คงที่ (ค่าคงที่เทียบข้ามสินทรัพย์ไม่ได้)
        history = sorted(story["bbw"]["series"][-story["bbw"]["samples"]:])
        cut_index = max(0, min(len(history) - 1,
                               int(len(history) * story["thresholds"]
                                   ["compression_percentile"] / 100) - 1))
        top.axhline(history[cut_index], color=COLORS["level"], linewidth=1.2,
                    linestyle=(0, (4, 4)), zorder=3)
        top.text(bars - 1, history[cut_index],
                 checked(f"เกณฑ์บีบตัว อันดับที่ "
                         f"{base.plain(story['thresholds']['compression_percentile'])}"),
                 ha="right", va="bottom", fontsize=10, color=COLORS["text"], zorder=6)
        top.text(0.012, 0.94, checked("BandWidth — ความกว้างของแถบเทียบราคากลาง"),
                 transform=top.transAxes, ha="left", va="top", fontsize=10.5,
                 color=COLORS["text"], zorder=6)
        top.set_xlim(-0.5, bars - 1)
        top.set_ylim(0, max(p[1] for p in drawn) * 1.25)

        points = [(x, value) for x, value in zip(xs, atr) if value is not None]
        bottom.plot([p[0] for p in points], [p[1] for p in points], color=COLORS["atr"],
                    linewidth=1.9, zorder=4)
        bottom.bar(bars - 1, story["atr"]["bar_true_range"], width=0.8,
                   color=COLORS["zone"], alpha=0.75, zorder=3)
        bottom.set_xlim(-0.5, bars - 1)
        bottom.set_ylim(0, max(max(p[1] for p in points),
                               story["atr"]["bar_true_range"]) * 1.25)
        positions, tick_labels = _tick_labels(view)
        bottom.set_xticks(positions)
        bottom.set_xticklabels([checked(label) for label in tick_labels])
        bottom.text(0.012, 0.90, checked("ATR และช่วงจริงของแท่งล่าสุด"),
                    transform=bottom.transAxes, ha="left", va="top", fontsize=10.5,
                    color=COLORS["text"], zorder=6)

        _header(figure, story, [
            (COLORS["chip_value"], "อันดับ BandWidth",
             base.whole(story["bbw"]["percentile"])),
            (COLORS["chip_level"], "ATR", money(story["atr"]["value"]))])
        _footer(figure, story, _footer_text(story, "แผงหลักฐาน BandWidth และ ATR"))
        return _save(figure, output_path, story, "evidence")
    finally:
        pyplot.close(figure)


# ------------------------------------------------------------------------- สไตล์ J

def _render_pullback_hero(story: dict, context_rows: list[dict], output_path: Path,
                          spec) -> dict:
    """ภาพชั้นบริบท — แท่ง M30 พร้อมเมฆ Ichimoku ที่วางถูกตำแหน่งตาม displacement"""
    from matplotlib import pyplot
    from matplotlib.patches import Rectangle

    # ชุดที่ได้รับถูกตัดให้จบที่ `context_bar_at` มาแล้วจาก `_rows_for`
    money = base.money_for(story)
    bars = story["context_display"]["bars"]
    view = context_rows[-bars:]
    cloud = story["ichimoku"]
    length = (cloud["conversion"], cloud["base"], cloud["span_b_length"])

    def compute(rows):
        return intraday_indicators.ichimoku(rows, *length)

    tenkan = series_tail(context_rows, bars, compute, lambda x: x["tenkan"])
    kijun = series_tail(context_rows, bars, compute, lambda x: x["kijun"])
    span_a = series_tail(context_rows, bars, compute, lambda x: x["cloud_now"]["span_a"])
    span_b = series_tail(context_rows, bars, compute, lambda x: x["cloud_now"]["span_b"])
    _verify_tail(tenkan, cloud["tenkan"], label="Tenkan")
    _verify_tail(kijun, cloud["kijun"], label="Kijun")
    _verify_tail(span_a, cloud["cloud_now"]["span_a"], label="Span A")
    _verify_tail(span_b, cloud["cloud_now"]["span_b"], label="Span B")

    figure = pyplot.figure(figsize=FIGURE_SIZE, dpi=DPI)
    try:
        _card(figure, Rectangle)
        axes = figure.add_axes((0.055, 0.130, 0.845, 0.630))
        _style_axes(axes)
        xs = list(range(bars))
        band = [(x, a, b) for x, a, b in zip(xs, span_a, span_b)
                if a is not None and b is not None]
        axes.fill_between([p[0] for p in band], [p[1] for p in band], [p[2] for p in band],
                          where=[p[1] >= p[2] for p in band], color=COLORS["cloud_up"],
                          alpha=0.16, zorder=2, interpolate=True)
        axes.fill_between([p[0] for p in band], [p[1] for p in band], [p[2] for p in band],
                          where=[p[1] < p[2] for p in band], color=COLORS["cloud_down"],
                          alpha=0.16, zorder=2, interpolate=True)
        _draw_candles(axes, view, Rectangle)
        for values, color, width in ((tenkan, COLORS["adx"], 1.7),
                                     (kijun, COLORS["level"], 1.7)):
            points = [(x, value) for x, value in zip(xs, values) if value is not None]
            axes.plot([p[0] for p in points], [p[1] for p in points], color=color,
                      linewidth=width, zorder=5)
        x_right = bars - 1 + bars * RIGHT_PAD_FRACTION
        _level_line(axes, cloud["kijun"], x_right,
                    f"เส้น Kijun {money(cloud['kijun'])}", COLORS["level"])
        _state_badge(axes, story, spec)
        _finish_price_axes(axes, view, [cloud["cloud_now"]["top"],
                                        cloud["cloud_now"]["bottom"]], x_right)
        context_words = base.tf_words(story, story["context_timeframe"])
        _header(figure, story, [
            (COLORS["chip_value"], "Tenkan", money(cloud["tenkan"])),
            (COLORS["chip_level"], "Kijun", money(cloud["kijun"]))])
        profile = wcb_source.profile_for(story["asset"])
        _footer(figure, story,
                f"{profile['symbol']} · {context_words['bar']} · ช่วงที่แสดง "
                f"{thai_date(story['context_display']['start_date'])} ถึง "
                f"{thai_date(story['context_display']['end_date'])} · "
                f"ชั้นบริบท Ichimoku")
        return _save(figure, output_path, story, "hero")
    finally:
        pyplot.close(figure)


def _render_pullback_evidence(story: dict, trigger_rows: list[dict],
                              output_path: Path, spec) -> dict:
    """ภาพชั้นจังหวะ — แท่ง M15 พร้อมโซนย่อที่ยกมาจากกรอบใหญ่ และแผง CHOP"""
    from matplotlib import pyplot
    from matplotlib.patches import Rectangle

    money = base.money_for(story)
    bars = story["display"]["bars"]
    view = trigger_rows[-bars:]
    chop_length = story["chop"]["length"]
    chop = series_tail(trigger_rows, bars,
                       lambda r: intraday_indicators.choppiness(r, chop_length),
                       lambda x: x["value"])
    _verify_tail(chop, story["chop"]["value"], label="CHOP")
    zone = story["pullback_zone"]

    figure = pyplot.figure(figsize=FIGURE_SIZE, dpi=DPI)
    try:
        _card(figure, Rectangle)
        top = figure.add_axes((0.055, 0.360, 0.845, 0.420))
        bottom = figure.add_axes((0.055, 0.130, 0.845, 0.190))
        _style_axes(top, labels=False)
        _style_axes(bottom)
        top.add_patch(Rectangle((-0.5, zone["low"]), bars + 0.5,
                                zone["high"] - zone["low"], facecolor=COLORS["zone"],
                                edgecolor=COLORS["zone"], alpha=0.14, linewidth=1.6,
                                zorder=2))
        _draw_candles(top, view, Rectangle)
        x_right = bars - 1 + bars * RIGHT_PAD_FRACTION
        _level_line(top, story["invalidation"]["level"], x_right,
                    f"เส้นที่ทำให้มุมมองเสีย {money(story['invalidation']['level'])}",
                    COLORS["level"])
        _state_badge(top, story, spec)
        _finish_price_axes(top, view, [zone["low"], zone["high"]], x_right, labels=False)

        xs = list(range(bars))
        points = [(x, value) for x, value in zip(xs, chop) if value is not None]
        bottom.plot([p[0] for p in points], [p[1] for p in points], color=COLORS["chop"],
                    linewidth=1.9, zorder=4)
        for level in (story["thresholds"]["chop_trending"],
                      story["thresholds"]["chop_choppy"]):
            bottom.axhline(level, color=COLORS["axis"], linewidth=1.1,
                           linestyle=(0, (4, 4)), zorder=3)
            bottom.text(bars - 1, level, checked(f"เกณฑ์ {base.plain(level)}"),
                        ha="right", va="bottom", fontsize=9.5, color=COLORS["text"],
                        zorder=6)
        bottom.set_xlim(-0.5, bars - 1)
        positions, tick_labels = _tick_labels(view)
        bottom.set_xticks(positions)
        bottom.set_xticklabels([checked(label) for label in tick_labels])

        _header(figure, story, [
            (COLORS["chip_value"], "ราคาปิด", money(story["close"])),
            (COLORS["chip_level"], "CHOP", base.one(story["chop"]["value"]))])
        _footer(figure, story, _footer_text(story, "ชั้นจังหวะ โซนย่อและค่า CHOP"))
        return _save(figure, output_path, story, "evidence")
    finally:
        pyplot.close(figure)


# --------------------------------------------------------------------------- ทางเข้า

RENDERERS = {
    "intraday-trend-story-v1": (_render_trend_hero, _render_trend_evidence),
    "intraday-breakout-story-v1": (_render_breakout_hero, _render_breakout_evidence),
    "intraday-pullback-story-v1": (_render_pullback_hero, _render_pullback_evidence),
}


def _rows_for(rows_by_timeframe: dict[str, list[dict]], timeframe: str,
              expected_bar_at: str) -> list[dict]:
    """หยิบชุดแท่งของกรอบเวลาที่ภาพใบนั้นต้องใช้ — พร้อมตรวจว่าเป็นชุดเดียวกับที่บทอ้าง

    🐞 **พบตอนรันจริงรอบแรก 2026-08-13 และเป็นบั๊กที่อันตรายที่สุดเท่าที่เจอในรอบนี้:**
    สายผลิตส่งแท่ง M15 ชุดเดียวให้ตัววาดทุกสไตล์ แต่ story ของสไตล์ H คิดจากแท่ง M30
    ⇒ ภาพหลักของ H จะเป็น **แท่ง M15 ที่มีเส้น Supertrend ของ M30 ลากทับ** ซึ่งดูสมเหตุผล
    ทุกประการด้วยตาเปล่า · ด่าน `_verify_tail` จับได้ที่แผงหลักฐาน แต่ภาพหลักรอดไปได้
    เพราะมันใช้เส้นสำเร็จรูปจาก story
    ⇒ แก้ที่ต้นเหตุ: **ตัววาดรับแท่งเป็น dict ต่อกรอบเวลา ไม่ใช่ลิสต์เดียว** แล้วเลือกเอง
    ตามกรอบของภาพใบนั้น พร้อมตรวจว่าแท่งท้ายตรงกับที่บทอ้างจริง
    """
    try:
        rows = rows_by_timeframe[timeframe]
    except KeyError as exc:
        raise ChartMismatch(
            f"ไม่มีชุดแท่งของกรอบ {timeframe} ให้ตัววาด — ภาพใบนี้วาดไม่ได้") from exc
    # ตัดท้ายจนถึงแท่งที่บทอ้าง — จำเป็นกับสไตล์ J ซึ่งชั้นบริบทถูกตัดให้ตรงกับชั้น
    # ทริกเกอร์ตอนคิด story (ดู `intraday_story.align_context`) สายผลิตจึงส่งชุดดิบมา
    kept = list(rows)
    while kept and kept[-1]["at"] != expected_bar_at:
        kept.pop()
    if not kept:
        raise ChartMismatch(
            f"ชุดแท่งกรอบ {timeframe} ไม่มีแท่ง {expected_bar_at} ที่บทอ้างอยู่ "
            "— ภาพจะเป็นคนละช่วงเวลากับบท")
    return kept


def render(story: dict, rows_by_timeframe: dict[str, list[dict]], folder: Path,
           spec) -> list[dict]:
    """วาดภาพครบชุดของบทหนึ่งใบ — คืนสรุปเรียงตามลำดับภาพในบท

    `rows_by_timeframe` = {"15min": [...], "30min": [...]} — ตัววาดเลือกชุดที่ถูกเอง
    ตามกรอบเวลาของภาพแต่ละใบ (ดูเหตุผลใน `_rows_for`)
    """
    import matplotlib
    matplotlib.use("Agg")
    _thai_font()

    hero_fn, evidence_fn = RENDERERS[story["schema"]]
    picture = base.figures(story, spec)
    results = []
    for figure, draw in ((picture[0], hero_fn), (picture[1], evidence_fn)):
        timeframe = figure.get("timeframe") or story["timeframe"]
        expected = (story["context_bar_at"] if timeframe == story.get("context_timeframe")
                    and timeframe != story["timeframe"] else story["bar_at"])
        rows = _rows_for(rows_by_timeframe, timeframe, expected)
        results.append(draw(story, rows, folder / figure["name"], spec))
    return results
