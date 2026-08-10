"""ชั้นคิดของบทสั้นตอนเช้า (สไตล์ F/G) — artifact กลางที่ทั้งนักเขียนและตัววาดอ่าน

ที่มา: ผู้ใช้สั่ง 2026-08-10 ให้แกะบทจริงของ InterGold สองใบมาเป็นสไตล์ใหม่
สเปกฉบับแกะ: `01-CC/Output/2026-08-10_แกะสไตล์-F-G-จากบทจริง-InterGold.md`

    F = บทกรอบ        · วันที่ไม่มีเหตุการณ์ใหญ่รอ → เล่ากรอบราคา แล้วให้แผนในกรอบ
    G = บทรอเหตุการณ์ · วันที่มีตัวเลขใหญ่รออยู่   → เล่าว่าตลาดหยุดรอ แล้วจบด้วยฉากทัศน์คู่

**ไม่คำนวณระดับเอง** — แนวรับ/แนวต้าน/กรอบแนวโน้ม ยกมาจาก `chart_story.build_story`
ทั้งชุด เพื่อให้บทเช้ากับบท D/E ของวันเดียวกันพูดเลขชุดเดียวกัน ถ้าแยกคิดเองเมื่อไหร่
สองสไตล์จะประกาศแนวรับคนละค่าในหน้าเว็บเดียวกัน (บทเรียน B-3.3)

สิ่งที่ชั้นนี้เพิ่มขึ้นมาจริง ๆ มีสามอย่าง:

1. **กล่องกรอบล่าสุด** (`range_box`) — สูง/ต่ำของ N แท่งท้าย + ความเอียงของกรอบ
   ⇒ ใช้ทั้งวาดกล่องเขียวในภาพ F และเลือกคำว่า Sideway / Sideway-Up / Sideway-Down
2. **จุดสัมผัสของช่องแนวโน้ม** (`channel.touches`) — แท่งที่เคยแตะเส้นบน/ล่างจริง
   ⇒ วงรีในภาพ G · **ไม่ถึง 2 จุดต่อเส้น = ไม่ใช่ช่องที่พิสูจน์ได้ ⇒ ห้ามใช้ G**
3. **เหตุการณ์ที่รออยู่** (`event`) — ตัวตัดสินว่าวันนี้เป็น F หรือ G

⚠️ **ไม่มีราคาทองไทย (บาท) ในระบบ** — ต้นแบบพิมพ์คู่ `$3,960 , 63,100 บาท` แต่วัดจาก
ต้นแบบเองแล้วอัตราแปลงไม่คงที่ (15.93 กับ 15.75 ในบทคนละใบ) แปลว่าเป็นราคาหน้าร้าน
ในประเทศที่มีพรีเมียมของตัวเอง คำนวณจากสปอตไม่ได้ ⇒ **บทของเราพิมพ์ดอลลาร์อย่างเดียว**
ตามหลัก fail-closed เดิม (ไม่มีข้อมูล = ตัดทิ้งเงียบ ไม่ใช่เดา)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import chart_story  # noqa: E402

SCHEMA = "brief-story-v1"

STYLE_F = "f"
STYLE_G = "g"

# หน้าต่างภาพของบทเช้า แยกตามกรอบเวลา — `None` = แท่งรายวัน (เส้นทางเดิม)
#
# ตัวเลขมาจากช่วงเวลาจริงที่อยากให้คนอ่านเห็น ไม่ใช่จำนวนแท่งลอย ๆ:
#   1h × 120 ≈ 5 วันทำการ · 4h × 90 ≈ 15 วันทำการ · 1วัน × 90 ≈ 4 เดือน
# เพดานบนถูกคุมด้วยจำนวนแท่งที่ปลายทางให้ (วัดจริง 08-10: 1h = 339 · 4h = 356)
# ลบด้วย 200 แท่งที่ SMA200 กินไป
BRIEF_BARS_BY_TF = {None: 90, "1h": 120, "4h": 90}

# กล่องกรอบล่าสุด คิดเป็นสัดส่วนของหน้าต่าง — ต้นแบบครอบราวหนึ่งในสามขวาของภาพ
BOX_FRACTION = 1 / 3


def bars_for(timeframe: str | None) -> int:
    return BRIEF_BARS_BY_TF.get(timeframe, BRIEF_BARS_BY_TF[None])

# ความเอียงของกรอบที่ยังเรียกว่า "แกว่งแนวนอน" ได้ คิดเป็นเท่าของ ATR ต่อแท่ง
# เกินกว่านี้ = กรอบเอียงจริง ต้องเติมคำว่า Up/Down ต่อท้าย ไม่ใช่เรียก Sideway เฉย ๆ
FLAT_SLOPE_ATR = 0.04

# เส้นช่องแนวโน้มหนึ่งเส้นต้องมีจุดแตะกี่จุดจึงจะวาดได้
# — เส้นที่ไม่มีจุดแตะกำกับคือเส้นที่ลากตามใจ (หัวใจของสไตล์ G ตามสเปกข้อ 3.4)
CHANNEL_TOUCH_MIN = 2
# ระยะที่ยังนับว่า "แตะเส้น" คิดเป็นเท่าของ ATR
TOUCH_BAND_ATR = 0.45

# หน้าต่างที่ถือว่าเหตุการณ์ "กำลังรออยู่" — ต้นแบบ G เขียนตอนเช้าวันอังคารถึงตัวเลข
# คืนวันศุกร์ ⇒ กว้างพอสำหรับสัปดาห์ทำการเดียว
EVENT_WINDOW_DAYS = 4
# ประเทศเดียวที่นับเป็น "สิ่งที่ตลาดรอ" — เจตนาเดียวกับ `wcb_writers._calendar_events`
EVENT_COUNTRY = "USD"


class BriefUnavailable(RuntimeError):
    """ข้อมูลไม่พอเขียนบทเช้า — หยุดสาย F/G ห้ามเดาต่อ"""


def _slope_per_bar(rows: list[dict]) -> float:
    """ความชันของราคาปิดในกล่อง (หน่วยราคาต่อแท่ง) — least squares ตัวเดียวกับ D"""
    slope, _intercept = chart_story.fit_line(
        [(index, row["close"]) for index, row in enumerate(rows)])
    return slope


def build_range_box(view: list[dict], atr: float, *, box_bars: int | None = None) -> dict:
    """กล่องกรอบล่าสุด — สูง/ต่ำจริงของ N แท่งท้าย ไม่ปัด ไม่ขยับให้สวย

    `bias` เป็นคำที่บทจะใช้เรียกกรอบ: `sideway` / `sideway_up` / `sideway_down`
    ตัดสินจากความชันเทียบ ATR ไม่ใช่จากสายตา — เกณฑ์เดียว ใช้ได้ทุกสินทรัพย์
    """
    box_bars = box_bars or max(5, round(len(view) * BOX_FRACTION))
    box = view[-min(box_bars, len(view)):]
    if len(box) < 5:
        raise BriefUnavailable(f"แท่งในกล่องมี {len(box)} ตัว ไม่พอตีกรอบ")
    slope = _slope_per_bar(box)
    flat_cut = FLAT_SLOPE_ATR * atr
    if abs(slope) <= flat_cut:
        bias = "sideway"
    elif slope > 0:
        bias = "sideway_up"
    else:
        bias = "sideway_down"
    return {
        "bars": len(box),
        "start_index": len(view) - len(box),
        "start_date": box[0]["date"],
        "end_date": box[-1]["date"],
        "low": min(row["low"] for row in box),
        "high": max(row["high"] for row in box),
        "slope_per_bar": slope,
        "bias": bias,
    }


def channel_touches(view: list[dict], channel: dict | None, atr: float) -> dict | None:
    """จุดที่ราคาแตะเส้นบน/ล่างของช่องแนวโน้มจริง — วงรีในภาพ G วาดจากชุดนี้

    วัดที่ `high` สำหรับเส้นบน และ `low` สำหรับเส้นล่าง (ไม่ใช่ราคาปิด) เพราะการ
    "แตะแล้วเด้ง" เกิดที่ไส้เทียน · คืน None เมื่อยังพิสูจน์เส้นไม่ได้ ⇒ ผู้เรียก
    ต้องตกไปใช้สไตล์ F ห้ามวาดช่องที่ไม่มีหลักฐาน
    """
    if not channel:
        return None
    origin = channel["start"]
    band = TOUCH_BAND_ATR * atr

    def line_at(index: int) -> float:
        return channel["slope"] * (index - origin) + channel["intercept"]

    upper_is_main = channel["main_is_upper"]
    upper, lower = [], []
    for index in range(origin, len(view)):
        main = line_at(index)
        parallel = main + channel["offset"]
        upper_y, lower_y = (main, parallel) if upper_is_main else (parallel, main)
        row = view[index]
        if abs(row["high"] - upper_y) <= band:
            upper.append({"index": index, "date": row["date"], "price": row["high"],
                          "edge": "upper"})
        if abs(row["low"] - lower_y) <= band:
            lower.append({"index": index, "date": row["date"], "price": row["low"],
                          "edge": "lower"})

    def thin(points: list[dict]) -> list[dict]:
        """แตะติดกันหลายแท่งนับเป็นครั้งเดียว — ไม่งั้นแท่งข้าง ๆ กันบวมเป็น 5 วง"""
        kept: list[dict] = []
        for point in points:
            if kept and point["index"] - kept[-1]["index"] < chart_story.SWING_WINDOW:
                continue
            kept.append(point)
        return kept

    upper, lower = thin(upper), thin(lower)
    if len(upper) < CHANNEL_TOUCH_MIN or len(lower) < CHANNEL_TOUCH_MIN:
        return None
    return {"upper": upper, "lower": lower, "count": len(upper) + len(lower)}


def pending_event(calendar: dict | list | None, *, local_date: str | None = None,
                  window_days: int = EVENT_WINDOW_DAYS) -> dict | None:
    """เหตุการณ์แรงที่ยังไม่ประกาศและอยู่ในหน้าต่าง — ตัวตัดสิน F ↔ G

    รับได้ทั้ง pseudo-evidence แบบ `{"calendar": [...], "local_date": ...}` และลิสต์
    รายการตรง ๆ (รูปเดียวกับที่ `calendar_feed.to_calendar_events` คืน) — รับทั้งสอง
    ที่นี่ที่เดียว ดีกว่าให้ผู้เรียกแต่ละสายจำเอง

    เกณฑ์สี่ชั้น เรียงจากแข็งไปหลวม:

    1. **สหรัฐเท่านั้น** (`country == "USD"`) — เจตนาเดียวกับ `wcb_writers._calendar_events`
       🐞 พบตอนรันจริงรอบแรก 2026-08-10: ไม่กรองประเทศ แล้วบทเขียนว่าตลาดทองหยุดรอ
       "ความเชื่อมั่นภาคธุรกิจ (NAB ออสเตรเลีย)" ซึ่งไม่จริง — ย่อหน้าสายส่งมหภาคของ
       ทุกสินทรัพย์อ่านได้เฉพาะฝั่งสหรัฐ การหยิบประเทศอื่นมาเป็น "สิ่งที่ตลาดรอ"
       คือการอธิบายตัวเลขของประเทศหนึ่งด้วยกลไกของอีกประเทศ
    2. **ผลกระทบสูงเท่านั้น** (`impact == "High"`) — Medium ตลาดไม่หยุดรอ
    3. **ยังไม่ประกาศ** (ช่อง `actual` ว่าง) — ที่ประกาศแล้วเป็นวัตถุดิบของย่อหน้า
       ที่สอง ("ข้อมูลล่าสุดออกมาแล้ว...") ไม่ใช่สิ่งที่ตลาดรอ
    4. **อยู่ในหน้าต่าง** `window_days` วันนับจากวันนี้ — ตัวเลขของสัปดาห์หน้า
       ไม่ทำให้ตลาดเช้านี้หยุดรอ

    คืนรายการที่**ใกล้ที่สุด**ในกลุ่มที่ผ่านเกณฑ์ (ไม่ใช่รายการแรกของฟีด) เพราะ
    บทเช้าพูดถึงสิ่งที่จะเกิดก่อน
    """
    if isinstance(calendar, dict):
        events = calendar.get("calendar") or calendar.get("events") or []
        local_date = local_date or calendar.get("local_date")
    else:
        events = calendar or []
    if not events:
        return None
    if not local_date:
        return None

    limit_date = _date_plus(local_date, window_days)
    chosen = None
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("country") != EVENT_COUNTRY:
            continue
        if event.get("impact") != "High":
            continue
        if event.get("actual") not in (None, "", "-"):
            continue
        at = str(event.get("at") or "")
        if not (local_date <= at[:10] <= limit_date):
            continue
        if chosen is None or at < str(chosen.get("at") or ""):
            chosen = event
    if chosen is None:
        return None
    return {
        "title": str(chosen.get("title") or "").strip(),
        "at": chosen.get("at"),
        "country": chosen.get("country"),
        "impact": chosen.get("impact"),
        "previous": chosen.get("previous"),
        "forecast": chosen.get("forecast"),
    }


def _date_plus(date_text: str, days: int) -> str:
    from datetime import date, timedelta

    year, month, day = (int(part) for part in date_text[:10].split("-"))
    return (date(year, month, day) + timedelta(days=days)).isoformat()


def channel_edges(channel: dict | None, view: list[dict]) -> tuple[float, float] | None:
    """ขอบล่าง/บนของช่องแนวโน้ม ณ แท่งล่าสุด — None เมื่อไม่มีช่อง"""
    if not channel:
        return None
    last = len(view) - 1
    main = channel["slope"] * (last - channel["start"]) + channel["intercept"]
    parallel = main + channel["offset"]
    return min(main, parallel), max(main, parallel)


def channel_bias(channel: dict | None, atr: float) -> str:
    """ทิศของช่องแนวโน้ม — คำที่บทสไตล์ G ใช้เรียกกรอบ

    🐞 พบตอนตรวจใบตัวอย่างก่อนส่งหัวหน้า 2026-08-10: บท G ของ SOL เขียนว่า
    "เคลื่อนไหวในกรอบ Sideway-Down" ขณะที่ภาพเป็น**ช่องขาขึ้น**ชัด ๆ — เพราะ
    ตัวเขียนหยิบ `range_box["bias"]` (30 แท่งท้าย) มาใช้กับทุกสไตล์
    ⇒ **สไตล์ G ต้องเรียกกรอบตามช่อง เพราะช่องคือสิ่งที่วาดลงภาพ** ส่วนกล่องกรอบ
    เป็นของสไตล์ F · เกณฑ์ "แบน" ใช้ตัวเดียวกับกล่อง (FLAT_SLOPE_ATR) ไม่ตั้งใหม่
    """
    if not channel:
        return "sideway"
    slope = channel["slope"]
    if abs(slope) <= FLAT_SLOPE_ATR * atr:
        return "sideway"
    return "sideway_up" if slope > 0 else "sideway_down"


def channel_holds(channel: dict | None, view: list[dict]) -> bool:
    """ราคาล่าสุดยังอยู่ในช่องไหม — เงื่อนไขบังคับของสไตล์ G

    🐞 พบตอนดูภาพที่วาดออกมารอบแรก 2026-08-10: ช่องพิสูจน์ได้ (จุดแตะครบ) แต่ราคา
    ปิดทะลุขึ้นเหนือขอบบนไปแล้ว ⇒ บทเขียนว่า "แกว่งตัวในกรอบ" ขณะที่ภาพแสดงการทะลุ
    ออกนอกกรอบชัด ๆ **ภาพกับบทเล่าคนละเรื่องในหน้าเดียวกัน**
    ⇒ ราคาอยู่นอกช่อง = ไม่ใช่วันของ G ให้ตกไปใช้ F ซึ่งเล่ากรอบตรงตามที่เห็น
    """
    edges = channel_edges(channel, view)
    if edges is None:
        return False
    lower, upper = edges
    return lower < view[-1]["close"] < upper


def _levels_for(style: str, box: dict, channel: dict | None, view: list[dict],
                atr: float) -> tuple[float, float]:
    """แนวรับ/แนวต้านของบทเช้า — **ขอบกรอบ ไม่ใช่ระดับโครงสร้างของสไตล์ D**

    🐞 พบตอนรันจริงรอบแรก 2026-08-10: หยิบ `story["zones"][0]` / `story["resistance"][0]`
    มาใช้ตรง ๆ แล้วได้แนวรับห่างราคา 9.04% กับแนวต้านห่าง 9.9% — ระดับชุดนั้นถูก
    ออกแบบมาสำหรับ**แผนรายวันของบทยาว** (เพดาน `ENTRY_MAX_DISTANCE_ATR` = 10×ATR)
    เอามาเขียนว่า "รอย่อเข้าหาแนวรับ" ในบทเช้าไม่ได้ ราคาต้องร่วง 9% ก่อนถึงจะทำตามได้

    ต้นแบบใช้ขอบกรอบจริง ๆ — วัดจากภาพ: กล่องเขียวของใบ 21 ก.ค. กินพอดีระหว่าง
    เส้น $3,960 กับ $4,090 ซึ่งเป็นเลขเดียวกับกล่อง "แนวรับ/แนวต้าน" ในบท
    ⇒ **F ใช้ขอบกล่องกรอบ · G ใช้ขอบช่องแนวโน้ม ณ แท่งล่าสุด**

    ทั้งสองค่ายังเป็นค่าที่คำนวณจากแท่งจริงล้วน ๆ ไม่ได้ปัดให้สวยแบบต้นแบบ
    (ต้นแบบปัดเป็นหลักสิบ — เราปัดไม่ได้เพราะเลขทุกตัวต้องชี้กลับหลักฐานได้)
    """
    close = view[-1]["close"]
    if style == STYLE_G:
        # สไตล์ G ผ่าน `channel_holds` มาแล้วเสมอ (บังคับใน `build_brief`)
        # ⇒ ขอบช่องคร่อมราคาแน่นอน ใช้เป็นแนวรับ/แนวต้านได้ตรง ๆ
        return channel_edges(channel, view)
    return min(box["low"], close - 0.1 * atr), max(box["high"], close + 0.1 * atr)


def build_brief(rows: list[dict], *, asset: str, style: str | None = None,
                calendar: dict | list | None = None,
                calendar_sentences: list[str] | None = None,
                local_date: str | None = None,
                candle_basis: dict | None = None,
                timeframe: str | None = None,
                display_bars: int | None = None) -> dict:
    """artifact กลางของบทเช้า — เลือกสไตล์เอง เว้นแต่ผู้เรียกบังคับด้วย `style`

    กติกาเลือกอัตโนมัติ (เรียงตามลำดับ ตัดสินได้ก็หยุด):

        มีเหตุการณ์แรงรออยู่ **และ** ช่องแนวโน้มพิสูจน์ได้ ⇒ G
        นอกนั้น                                          ⇒ F

    บังคับ `style="g"` ทั้งที่พิสูจน์ช่องไม่ได้ = ยก `BriefUnavailable` ไม่ใช่วาดมั่ว
    """
    display_bars = display_bars or bars_for(timeframe)
    # ตัดแท่งที่ยังไม่ปิดที่นี่ก่อน แล้วส่งชุดเดียวกันเข้า build_story (A-1) —
    # ถ้าปล่อยให้ build_story ตัดเอง `view` ที่คำนวณข้างล่างจะเหลื่อมกับ view ของ story
    # หนึ่งแท่ง แล้วดัชนีจุดแตะ/กล่องกรอบจะชี้แท่งผิดตัวแบบเงียบ ๆ
    #
    # เส้นทาง intraday **ต้องส่ง basis มาจากสายผลิตเสมอ** — ที่นี่ไม่ตัดเอง เพราะ
    # กติกาแท่งปิดของ intraday อยู่ที่ `intraday_bars` คนละเส้นกับปฏิทินตลาดรายวัน
    if candle_basis is None:
        if timeframe is not None:
            raise BriefUnavailable(
                f"{asset}: กรอบเวลา {timeframe} ต้องส่งก้อนหลักฐานแท่งปิดมาด้วย "
                "(intraday_bars.evaluate) — ที่นี่ไม่ตัดแท่งเองเพื่อไม่ให้มีกติกาสองชุด")
        rows, candle_basis = chart_story.candle_close.evaluate(rows, asset=asset)
    story = chart_story.build_story(rows, asset=asset, display_bars=display_bars,
                                    zoom_bars=display_bars, calendar=None,
                                    candle_basis=candle_basis)
    view = rows[-story["display"]["bars"]:]
    atr = story["atr14"]

    box = build_range_box(view, atr)
    touches = channel_touches(view, story["channel"], atr)
    event = pending_event(calendar, local_date=local_date)

    holds = channel_holds(story["channel"], view)
    if style is None:
        style = STYLE_G if (event and touches and holds) else STYLE_F
    if style not in (STYLE_F, STYLE_G):
        raise BriefUnavailable(f"ไม่รู้จักสไตล์ '{style}' — มีแค่ f กับ g")
    if style == STYLE_G and not holds:
        raise BriefUnavailable(
            f"{asset}: ราคาปิดอยู่นอกช่องแนวโน้มแล้ว — สไตล์ G จะเขียนว่า 'แกว่งในกรอบ' "
            "ขณะที่ภาพแสดงการทะลุออก ให้ใช้ F แทน")
    if style == STYLE_G and not touches:
        raise BriefUnavailable(
            f"{asset}: ช่องแนวโน้มมีจุดแตะไม่ครบ {CHANNEL_TOUCH_MIN} จุดต่อเส้น "
            "— สไตล์ G วาดช่องที่พิสูจน์ไม่ได้ไม่ได้ ให้ใช้ F แทน")
    if style == STYLE_G and not event:
        raise BriefUnavailable(
            f"{asset}: ไม่มีเหตุการณ์แรงที่ยังไม่ประกาศในหน้าต่าง {EVENT_WINDOW_DAYS} วัน "
            "— สไตล์ G ต้องมีสิ่งที่ตลาดรอ ให้ใช้ F แทน")

    support, resistance = _levels_for(style, box, story["channel"], view, atr)

    return {
        "schema": SCHEMA,
        "style": style,
        "asset": asset,
        "timeframe": timeframe,
        "symbol": story["symbol"],
        # `at` มีเฉพาะเส้นทาง intraday — ตัวเขียนกับด่านตรวจใช้ค่านี้พิสูจน์แท่งปิด
        "current": {**story["current"], **({"at": view[-1]["at"]} if timeframe else {})},
        "candle_basis": story["candle_basis"],
        "atr14": atr,
        "sma50_last": story["sma50_last"],
        "regime": story["regime"],
        "display": story["display"],
        "support": support,
        "resistance": resistance,
        "range_box": box,
        "channel": story["channel"],
        "channel_touches": touches,
        "event": event,
        # ประโยคปฏิทินสำเร็จรูปจาก `wcb_writers._calendar_sentences` — บทเช้าไม่มี
        # แหล่งข่าวของตัวเอง ย่อหน้า "ปัจจัย" จึงพูดจากปฏิทินเท่านั้น · ไม่มี = ตัดเงียบ
        "calendar_sentences": list(calendar_sentences or []),
        # เก็บ story ทั้งก้อนไว้ให้ตัววาดใช้ต่อ (แท่ง/SMA/โซน) โดยไม่ต้องคำนวณซ้ำ
        "story": story,
    }
