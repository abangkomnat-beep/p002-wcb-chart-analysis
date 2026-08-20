"""ฐานร่วมของสไตล์ระหว่างวัน H/I/J — ทะเบียน พารามิเตอร์ ความจำสถานะ และซองของ story

สามสไตล์ใหม่แชร์กันสี่อย่างเท่านั้น และทั้งสี่อยู่ในไฟล์นี้:

1. **ทะเบียนสไตล์** (`config/article_styles.json`) — โฟลเดอร์ · allowlist สินทรัพย์
2. **พารามิเตอร์** (`config/intraday_style_params.json`) — ค่าที่ต้อง calibrate
3. **ความจำสถานะรอบก่อน** — หัวใจของการผลิตแบบ state-driven และเป็นสิ่งเดียวที่ทำให้
   สถานะอย่าง `FAILED_BREAKOUT` เป็นไปได้ (มันนิยามด้วย "เคยเป็นอะไรมาก่อน")
4. **ซองมาตรฐานของ story** — ช่องที่ตัวเขียน ตัววาด และตัวเลือกบท อ่านเหมือนกันทุกสไตล์

⛔ **ที่นี่ไม่คิดแผนการเทรด** — ไม่มีจุดเข้า ไม่มี SL/TP ไม่มี RR (ข้อเสนอ §26)
H/I/J มีหน้าที่บอก *สถานะและหลักฐาน* เท่านั้น การคิดแผนเป็นของสายอื่นที่มีด่าน
ความเสี่ยงของตัวเองอยู่แล้ว — ถ้าปล่อยให้ทุกสไตล์คิดราคาเข้าเอง ระบบจะมีสูตรจุดเข้า
คนละสูตรต่อสไตล์ แล้วหน้าเว็บเดียวกันจะประกาศราคาเข้าไม่ตรงกัน
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import intraday_bars, intraday_indicators  # noqa: E402

PARAMS_PATH = _REPO_ROOT / "config" / "intraday_style_params.json"
STYLES_PATH = _REPO_ROOT / "config" / "article_styles.json"
STATE_DIR = _REPO_ROOT / "state"

STYLE_H = "h_trend_strength"
STYLE_I = "i_volatility_breakout"
STYLE_J = "j_pullback_continuation"
STYLE_IDS = (STYLE_H, STYLE_I, STYLE_J)


class StoryUnavailable(RuntimeError):
    """เขียนสไตล์นี้ในรอบนี้ไม่ได้ — หยุดเงียบ ไม่ใช่เขียนแบบอ่อนลง

    ใช้กับทุกเงื่อนไข fail-closed ของข้อเสนอ §40: indicator ไม่ครบ · แท่งไม่พอ ·
    กรอบเวลาสองชั้นไม่ตรงกัน · สินทรัพย์ไม่อยู่ใน allowlist
    """


def load_params(path: Path | None = None) -> dict:
    return json.loads((path or PARAMS_PATH).read_text(encoding="utf-8"))


def load_styles(path: Path | None = None) -> dict:
    return json.loads((path or STYLES_PATH).read_text(encoding="utf-8"))["styles"]


def style_entry(style_id: str, *, styles: dict | None = None) -> dict:
    registry = styles or load_styles()
    try:
        return registry[style_id]
    except KeyError as exc:
        raise StoryUnavailable(f"ไม่รู้จักสไตล์ '{style_id}' — มีในทะเบียน: "
                               f"{', '.join(registry)}") from exc


def params_for(style_id: str, *, params: dict | None = None) -> dict:
    payload = params or load_params()
    try:
        return payload[style_id]["common"]
    except KeyError as exc:
        raise StoryUnavailable(
            f"ไม่มีค่าพารามิเตอร์ของสไตล์ '{style_id}' ใน {PARAMS_PATH.name}") from exc


def production_styles(*, styles: dict | None = None) -> dict:
    """สไตล์ที่ธง `production` เปิดอยู่ — ตัวกรองเดียวที่รอบวันใช้ตัดสินว่าจะรันตัวไหน

    อ่านจากทะเบียนทุกครั้ง ไม่ทำสำเนาไว้ในโค้ด เพื่อให้การเปิด/ปิดสไตล์เป็นการแก้
    ไฟล์ตั้งค่าบรรทัดเดียว ไม่ใช่การแก้สายท่อ (เปิดผิดแล้วปิดกลับต้องง่ายพอ ๆ กัน)
    """
    registry = styles or load_styles()
    return {style_id: entry for style_id, entry in registry.items()
            if entry.get("production") and entry.get("adapter", "hij_intraday") == "hij_intraday"}


def production_assets(*, styles: dict | None = None) -> set[str]:
    """สินทรัพย์ที่มีอย่างน้อยหนึ่งสไตล์เปิดผลิตอยู่ — รอบวันใช้ข้ามหัวข้อที่ไม่เกี่ยว

    ถ้าไม่กรองที่นี่ รอบวันจะยิงดึงแท่ง M15/M30 ของทั้งแปดหัวข้อทุกวันเพื่อให้ทุกใบ
    ตกด่าน allowlist อยู่ดี — เปลืองโควตาปลายทางฟรี ๆ
    """
    return {asset for entry in production_styles(styles=styles).values()
            for asset in entry["assets"]}


def ensure_asset_allowed(style_id: str, asset: str, *, styles: dict | None = None) -> None:
    """⛔ allowlist ปิดตาย — มี OHLC ไม่ได้แปลว่าเปิดสไตล์นี้กับสินทรัพย์นั้นได้

    เหตุผลไม่ใช่ความระมัดระวังลอย ๆ: เกณฑ์ percentile ของ BBW และระยะ ATR ต้อง
    ปรับเทียบแยกต่อสินทรัพย์ ปล่อยสินทรัพย์ใหม่เข้ามาโดยใช้ค่าของ BTC/ทอง =
    ระบบจะประกาศ 'บีบตัว' หรือ 'เบรกเอาต์' ด้วยเกณฑ์ของสินทรัพย์อื่น
    """
    allowed = style_entry(style_id, styles=styles)["assets"]
    if asset not in allowed:
        raise StoryUnavailable(
            f"{asset}: ยังไม่เปิดสไตล์ '{style_id}' กับสินทรัพย์นี้ "
            f"(เปิดอยู่: {', '.join(allowed)}) — ต้อง calibrate ค่าพารามิเตอร์แยก"
            "สินทรัพย์ก่อน ไม่ใช่ยืมเกณฑ์ของตัวอื่นมาใช้")


# ---------------------------------------------------------------- ความจำสถานะรอบก่อน

def state_path(style_id: str, asset: str, timeframe: str, *,
               state_dir: Path | None = None) -> Path:
    return (state_dir or STATE_DIR) / f"intraday-{style_id}-{asset}-{timeframe}.json"


def read_state(style_id: str, asset: str, timeframe: str, *,
               state_dir: Path | None = None) -> dict:
    """สถานะรอบก่อน — ไม่มีไฟล์ = รอบแรกของหัวข้อนี้ ไม่ใช่ข้อผิดพลาด"""
    path = state_path(style_id, asset, timeframe, state_dir=state_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # ไฟล์ความจำพังต้องไม่พาสายผลิตล้ม — ถือว่าไม่มีความจำแล้วเดินต่อ
        # (ผลคือรอบนี้ไม่รู้จักสถานะ FAILED_* ซึ่งเป็นการถอยที่ปลอดภัยกว่าการเดา)
        return {}


def write_state(style_id: str, asset: str, timeframe: str, payload: dict, *,
                state_dir: Path | None = None) -> Path:
    path = state_path(style_id, asset, timeframe, state_dir=state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def remember(story: dict, *, state_dir: Path | None = None, published: bool = False) -> Path:
    """บันทึกสถานะของรอบนี้ลงความจำ — เรียกหลังจบรอบเสมอ ไม่ว่าจะได้บทหรือไม่

    เก็บทั้งสถานะและ **แท่งที่ตัดสิน** เพราะการเทียบว่า 'สถานะเปลี่ยนไหม' ต้องรู้ว่า
    ค่าที่จำไว้มาจากแท่งไหน ไม่งั้นรันซ้ำแท่งเดิมจะถูกนับเป็นการเปลี่ยนสถานะ
    """
    payload = {
        "schema": "intraday-state-memory-v1",
        "style": story["style"],
        "asset": story["asset"],
        "timeframe": story["timeframe"],
        "state": story["state"],
        "bar_at": story["bar_at"],
        "published": bool(published),
    }
    return write_state(story["style"], story["asset"], story["timeframe"], payload,
                       state_dir=state_dir)


# ------------------------------------------------------------------ ซองมาตรฐาน story

def require(indicator: dict, *, asset: str, style_id: str) -> dict:
    """ด่าน fail-closed ของ indicator หนึ่งตัว — ไม่ available = ทั้งสไตล์หยุด

    ข้อเสนอ §40 เขียนไว้ต่อสไตล์ แต่รูปมันเหมือนกันทั้งสามตัว: หลักฐานไม่ครบแปลว่า
    เขียนบทที่ชี้ทิศไม่ได้ ไม่ใช่เขียนบทที่ 'ระวังหน่อย'
    """
    if not intraday_indicators.available(indicator):
        raise StoryUnavailable(
            f"{asset}: สไตล์ {style_id} คำนวณ {indicator.get('indicator')} ไม่ได้ "
            f"(ต้องการ {indicator.get('required_bars')} แท่ง มี "
            f"{indicator.get('available_bars')}) — หยุดสไตล์นี้ ห้ามเขียนแบบเดา")
    return indicator


def envelope(*, schema: str, style_id: str, asset: str, timeframe: str,
             rows: list[dict], candle_basis: dict, state: str,
             previous_state: str | None, display_bars: int) -> dict:
    """ช่องที่ทุก story ของ H/I/J มีเหมือนกัน — ตัวเขียน/ตัววาด/ตัวเลือกบทอ่านชุดนี้"""
    last = rows[-1]
    bars = min(display_bars, len(rows))
    return {
        "schema": schema,
        "style": style_id,
        "asset": asset,
        "timeframe": timeframe,
        "bar_at": last["at"],
        "bar_date": last["date"],
        "close": float(last["close"]),
        "candle_basis": candle_basis,
        "state": state,
        "previous_state": previous_state,
        "state_changed": bool(previous_state is not None and previous_state != state),
        "display": {"bars": bars, "start_at": rows[-bars]["at"],
                    "start_date": rows[-bars]["date"], "end_date": last["date"]},
    }


def align_context(context_rows: list[dict], trigger_rows: list[dict], *,
                  context_timeframe: str, trigger_timeframe: str,
                  asset: str) -> tuple[list[dict], str]:
    """ด่าน `timeframe_alignment` ของสไตล์สองชั้น (J) — **ตัดให้ตรงกัน ไม่ใช่แค่ตีตก**

    กติกา: แท่งบริบท (M30) ที่ใช้ได้ต้อง **ปิดไม่ช้ากว่า** แท่งทริกเกอร์ (M15) ที่ใช้ตัดสิน

    🐞 พบตอนรันจริงรอบแรก 2026-08-13: ปลายทางส่งแท่ง M30 ที่ปิด 06:00 มาพร้อมกับแท่ง
    M15 ล่าสุดที่ปิด 05:45 (ฟีดสองกรอบไม่ได้อัปเดตพร้อมกัน) · ถ้าจับคู่ตรง ๆ บทจะอ่าน
    บริบทจากช่วงเวลาที่กินยาวกว่าที่ชั้นทริกเกอร์ครอบคลุม — คือใช้ข้อมูลของช่วง
    05:45–06:00 ที่ชั้น M15 ยังไม่มี · **นี่ไม่ใช่เหตุให้ทิ้งทั้งบท** เพราะแท่ง M30
    ที่ปิด 05:30 ยังอยู่และใช้ได้ตามกติกา ⇒ ถอยไปใช้แท่งนั้นแทน

    ตีตกทั้งใบเฉพาะเมื่อ **ไม่เหลือแท่งบริบทที่ผ่านกติกาเลย** ซึ่งแปลว่าฟีดสองกรอบ
    เหลื่อมกันมากเกินกว่าจะพูดถึงตลาดเดียวกัน

    คืน (แท่งบริบทที่ตัดแล้ว, เวลาปิดของแท่งบริบทที่เลือก)
    """
    from datetime import timedelta

    context_span = timedelta(minutes=intraday_bars.spec_for(context_timeframe)["minutes"])
    trigger_span = timedelta(minutes=intraday_bars.spec_for(trigger_timeframe)["minutes"])
    trigger_close = intraday_bars.parse_at(trigger_rows[-1]["at"]) + trigger_span

    kept = list(context_rows)
    dropped = 0
    while kept and intraday_bars.parse_at(kept[-1]["at"]) + context_span > trigger_close:
        kept.pop()
        dropped += 1
    if not kept:
        raise StoryUnavailable(
            f"{asset}: ไม่เหลือแท่ง {context_timeframe} ที่ปิดไม่ช้ากว่าแท่ง "
            f"{trigger_timeframe} ล่าสุด (ปิด {trigger_close:%Y-%m-%d %H:%M}) — "
            "ฟีดสองกรอบเหลื่อมกันเกินกว่าจะพูดถึงตลาดเดียวกัน")
    context_close = intraday_bars.parse_at(kept[-1]["at"]) + context_span
    return kept, context_close.isoformat()
