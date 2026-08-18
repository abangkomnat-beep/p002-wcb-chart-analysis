"""ทะเบียนเทคนิค 1–8 ของ Style K — ผลิต EvidenceUnit จากแท่งที่ผ่าน dataset แล้วเท่านั้น

**ทุกฟังก์ชันในไฟล์นี้รับ `rows` ที่ถูกตัดที่ cutoff มาแล้ว** และไม่มีทางเข้าถึงแท่ง
หลังวัน D ได้เลย จุดตัดอยู่ที่ `style_k_dataset.rows_upto` ที่เดียว ไม่ใช่กระจายอยู่ในนี้

กับดักที่แต่ละกลุ่มกันไว้ตรง ๆ:

- **กลุ่ม 1** pivot ที่ยังไม่ครบ right window ไม่ใช่ pivot — ถ้านับ ก็คือมองอนาคต
  เพราะต้องรู้ว่าแท่งข้างหน้าไม่ทำ high สูงกว่า จึงตัด `right` แท่งท้ายออกจากผู้สมัคร
- **กลุ่ม 4** RSI/MACD/Stochastic เป็น `momentum` family เดียวกัน ห้ามนับเป็นสามเสียง
- **กลุ่ม 5** ความผันผวนขยายตัวไม่บอกทิศ — ห้ามแปลงเป็น bullish/bearish เอง
- **กลุ่ม 6** ไม่มี volume provenance = `unavailable` เสมอ ไม่มีทางเลือกอื่น
- **กลุ่ม 8** มี timeframe เดียว (D1) จึง `unavailable` — ห้าม resample แล้วอ้างว่าเป็นของจริง
"""

from __future__ import annotations

QUALITY_PASS = "pass"
QUALITY_LIMITED = "limited"
QUALITY_UNAVAILABLE = "unavailable"

FAMILY_STRUCTURE = "structure"
FAMILY_LIQUIDITY = "liquidity"
FAMILY_ZONE = "zone"
FAMILY_TREND = "trend"
FAMILY_MOMENTUM = "momentum"
FAMILY_VOLATILITY = "volatility"
FAMILY_FIB = "fibonacci"

GROUP_NAMES = {
    1: "Market Structure",
    2: "Liquidity / SMC",
    3: "Supply–Demand",
    4: "Trend / Momentum",
    5: "Volatility / Breakout",
    6: "Volume / Fair Value",
    7: "Fibonacci / Confluence",
    8: "Multi-timeframe",
}


def _evidence(*, asset, session_date, cutoff, group, seq, family, observation,
              interpretation, direction, certainty, level_refs=None, source_refs=None,
              quality=QUALITY_PASS, limitations=None, explainability=1.0) -> dict:
    return {
        "evidence_id": f"{session_date.replace('-', '')}-{asset.upper()}-D1-T{group}-{seq:03d}",
        "asset": asset,
        "session_date": session_date,
        "cutoff": cutoff,
        "timeframe": "D1",
        "technique_group": group,
        "technique_name": GROUP_NAMES[group],
        "independence_family": family,
        "observation": observation,
        "interpretation": interpretation,
        "direction": direction,
        "certainty": certainty,
        "level_refs": level_refs or [],
        "source_refs": source_refs or [],
        "quality": quality,
        "explainability": explainability,
        "limitations": limitations or [],
    }


def _unavailable(*, asset, session_date, cutoff, group, reason) -> dict:
    return _evidence(
        asset=asset, session_date=session_date, cutoff=cutoff, group=group, seq=999,
        family=f"group{group}", observation={"type": "unavailable"},
        interpretation=reason, direction="neutral", certainty="conditional",
        quality=QUALITY_UNAVAILABLE, limitations=[reason], explainability=0.0,
    )


# ---------------------------------------------------------------- ตัวช่วยคำนวณ

def _sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _rsi14(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for previous, current in zip(closes[-(period + 1):-1], closes[-period:]):
        change = current - previous
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - (100.0 / (1.0 + rs))


def true_ranges(rows: list[dict], *, normalized: bool = False) -> list[float]:
    """ช่วงจริงต่อแท่ง · `normalized=True` คืนเป็นสัดส่วนของราคาปิด

    **ต้องใช้ฉบับ normalized เมื่อเทียบกับอดีต** — วัดจริงแล้วพบว่าถ้าเทียบช่วงจริง
    เป็นหน่วยราคาดิบ BTCUSD จะขึ้น "ความผันผวนต่ำสุดในประวัติ" เกือบทุกวัน
    (เปอร์เซ็นไทล์ 0.002) ทั้งที่ตลาดไม่ได้นิ่งขนาดนั้น สาเหตุคือประวัติย้อนไปช่วง
    ที่ราคาสูงกว่ามาก ช่วงจริงหน่วยดอลลาร์จึงใหญ่กว่าโดยอัตโนมัติ ไม่เกี่ยวกับความผันผวน
    """
    ranges = []
    for index in range(1, len(rows)):
        current, previous = rows[index], rows[index - 1]
        value = max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"]),
        )
        if normalized:
            reference = current["close"] or previous["close"]
            value = value / reference if reference else 0.0
        ranges.append(value)
    return ranges


def atr(rows: list[dict], period: int = 14) -> float | None:
    ranges = true_ranges(rows)
    if len(ranges) < period:
        return None
    return sum(ranges[-period:]) / period


def find_pivots(rows: list[dict], *, left: int, right: int) -> tuple[list[dict], list[dict]]:
    """คืน (highs, lows) ที่**ยืนยันแล้ว** เท่านั้น

    แท่ง `right` ตัวท้ายยังไม่มีทางรู้ว่าเป็น pivot จริงหรือไม่ ณ cutoff จึงไม่เข้าผู้สมัคร
    — นี่คือกฎกันมองอนาคตที่เข้มที่สุดในไฟล์นี้ ถ้าปล่อยผ่าน โครงสร้างทั้งบทจะปนอนาคต
    """
    highs: list[dict] = []
    lows: list[dict] = []
    for index in range(left, len(rows) - right):
        window = rows[index - left: index + right + 1]
        bar = rows[index]
        if bar["high"] == max(item["high"] for item in window) and \
                all(bar["high"] > item["high"] for item in window if item is not bar):
            highs.append({"index": index, "date": bar["date"], "price": bar["high"], "kind": "high"})
        if bar["low"] == min(item["low"] for item in window) and \
                all(bar["low"] < item["low"] for item in window if item is not bar):
            lows.append({"index": index, "date": bar["date"], "price": bar["low"], "kind": "low"})
    return highs, lows


def _percentile_rank(values: list[float], target: float) -> float:
    if not values:
        return 0.5
    return sum(1 for value in values if value <= target) / len(values)


# ---------------------------------------------------------------- กลุ่ม 1–8

def group1_structure(rows, *, asset, session_date, cutoff, config) -> list[dict]:
    need = config["minimum_bars"]["structure"]
    if len(rows) < need:
        return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=1,
                             reason=f"ต้องใช้อย่างน้อย {need} แท่งเพื่อหาโครงสร้าง มี {len(rows)}")]
    left, right = config["pivot"]["left"], config["pivot"]["right"]
    highs, lows = find_pivots(rows, left=left, right=right)
    if len(highs) < 2 or len(lows) < 2:
        return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=1,
                             reason="จุดกลับตัวที่ยืนยันแล้วไม่พอสองคู่ ตัดสินโครงสร้างไม่ได้")]

    last_highs, last_lows = highs[-2:], lows[-2:]
    higher_high = last_highs[-1]["price"] > last_highs[-2]["price"]
    higher_low = last_lows[-1]["price"] > last_lows[-2]["price"]
    if higher_high and higher_low:
        pattern, direction = "higher_high_higher_low", "bullish"
        # ⛔ **ห้ามแก้ข้อความนี้เพื่อเปลี่ยนถ้อยคำในบท** — มันถูก freeze ด้วย hash
        # ไปแล้วในทุก session ที่ผลิตไปก่อนหน้า ⇒ แก้ที่นี่ = รอบที่รันซ้ำ session เดิม
        # ตกด่าน "หลักฐานไม่ตรงกับ freeze ที่มีอยู่" ทันที (พิสูจน์แล้ว 2026-08-14)
        # เปลี่ยนถ้อยคำให้เพิ่มคู่แทนใน `APPROVED_REWORDINGS` ของ style_k_writer แทน
        # ซึ่งทำงานตอนเขียนบท หลังด่านตรวจ freeze จึงไม่แตะ hash
        text = "โครงสร้างยังยกยอดและยกฐานสูงขึ้นต่อเนื่อง"
    elif not higher_high and not higher_low:
        pattern, direction = "lower_high_lower_low", "bearish"
        text = "โครงสร้างกดยอดและกดฐานต่ำลงต่อเนื่อง"
    else:
        pattern, direction = "mixed_structure", "neutral"
        text = "ยอดกับฐานเดินคนละทาง โครงสร้างยังไม่เลือกข้าง"

    close = rows[-1]["close"]
    broke_high = close > last_highs[-1]["price"]
    broke_low = close < last_lows[-1]["price"]
    evidence = [_evidence(
        asset=asset, session_date=session_date, cutoff=cutoff, group=1, seq=1,
        family=FAMILY_STRUCTURE,
        observation={"type": pattern, "swing_highs": last_highs, "swing_lows": last_lows},
        interpretation=text, direction=direction, certainty="confirmed",
        level_refs=[{"label": "ยอดล่าสุด", "price": last_highs[-1]["price"], "date": last_highs[-1]["date"]},
                    {"label": "ฐานล่าสุด", "price": last_lows[-1]["price"], "date": last_lows[-1]["date"]}],
        source_refs=[last_highs[-1]["date"], last_lows[-1]["date"]],
    )]
    if broke_high or broke_low:
        evidence.append(_evidence(
            asset=asset, session_date=session_date, cutoff=cutoff, group=1, seq=2,
            family=FAMILY_STRUCTURE,
            observation={"type": "break_of_structure", "side": "up" if broke_high else "down",
                         "level": last_highs[-1]["price"] if broke_high else last_lows[-1]["price"]},
            interpretation=("ราคาปิดเหนือยอดที่ยืนยันแล้ว เป็นการทะลุโครงสร้างขาขึ้น"
                            if broke_high else
                            "ราคาปิดใต้ฐานที่ยืนยันแล้ว เป็นการทะลุโครงสร้างขาลง"),
            direction="bullish" if broke_high else "bearish", certainty="confirmed",
            level_refs=[{"label": "ระดับที่ถูกทะลุ",
                         "price": last_highs[-1]["price"] if broke_high else last_lows[-1]["price"]}],
            source_refs=[rows[-1]["date"]],
        ))
    return evidence


def group2_liquidity(rows, *, asset, session_date, cutoff, config) -> list[dict]:
    value = atr(rows)
    if value is None:
        return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=2,
                             reason="คำนวณ ATR ไม่ได้ จึงไม่มีหน่วยวัดความห่างของระดับที่เท่ากัน")]
    left, right = config["pivot"]["left"], config["pivot"]["right"]
    highs, lows = find_pivots(rows, left=left, right=right)
    tolerance = value * config["equal_level_tolerance_atr"]
    evidence: list[dict] = []

    def equal_cluster(points):
        if len(points) < 2:
            return None
        newest = points[-1]
        peers = [item for item in points[:-1] if abs(item["price"] - newest["price"]) <= tolerance]
        return (newest, peers[-1]) if peers else None

    for points, side, seq in ((highs, "high", 1), (lows, "low", 2)):
        pair = equal_cluster(points)
        if not pair:
            continue
        newest, peer = pair
        evidence.append(_evidence(
            asset=asset, session_date=session_date, cutoff=cutoff, group=2, seq=seq,
            family=FAMILY_LIQUIDITY,
            observation={"type": f"equal_{side}s", "prices": [peer["price"], newest["price"]],
                         "tolerance": tolerance, "tolerance_basis": "0.15 × ATR14"},
            interpretation=("มียอดสองจุดที่ระดับใกล้เคียงกัน มักเป็นบริเวณที่คำสั่งหยุดขาดทุนกระจุกตัวอยู่"
                            if side == "high" else
                            "มีฐานสองจุดที่ระดับใกล้เคียงกัน มักเป็นบริเวณที่คำสั่งหยุดขาดทุนกระจุกตัวอยู่"),
            direction="neutral", certainty="provisional",
            # ป้ายนี้ไปอยู่ทั้งบทและภาพ จึงต้องเป็นภาษาไทยตั้งแต่ evidence ต้นทาง
            # (writer ยังแปลชื่อเก่าไว้เพื่ออ่าน snapshot ย้อนหลังได้)
            level_refs=[{"label": ("ยอดราคาใกล้เคียงกัน" if side == "high"
                                   else "ฐานราคาใกล้เคียงกัน"),
                         "price": newest["price"]}],
            source_refs=[peer["date"], newest["date"]],
        ))

    sweep = _detect_sweep(rows, highs, lows)
    if sweep:
        evidence.append(_evidence(
            asset=asset, session_date=session_date, cutoff=cutoff, group=2, seq=3,
            family=FAMILY_LIQUIDITY, observation=sweep,
            interpretation=("ราคาแทงทะลุระดับเดิมระหว่างวันแล้วปิดกลับเข้ามา "
                            "เป็นรูปแบบกวาดสภาพคล่องแล้วถูกปฏิเสธ"),
            direction="bearish" if sweep["side"] == "high" else "bullish",
            certainty="confirmed",
            level_refs=[{"label": "ระดับที่ถูกกวาด", "price": sweep["level"]}],
            source_refs=[sweep["date"]],
        ))
    if not evidence:
        return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=2,
                             reason="ไม่พบระดับเท่ากันหรือการกวาดสภาพคล่องที่เข้ากฎ")]
    return evidence


def _detect_sweep(rows, highs, lows) -> dict | None:
    """กวาดแล้วปิดกลับ: แท่งล่าสุดแทงพ้นระดับ pivot เดิม แต่ปิดกลับเข้ามาในฝั่งเดิม"""
    if not rows:
        return None
    bar = rows[-1]
    for point in reversed(highs):
        if point["index"] >= len(rows) - 1:
            continue
        if bar["high"] > point["price"] and bar["close"] < point["price"]:
            return {"type": "liquidity_sweep", "side": "high", "level": point["price"],
                    "date": bar["date"], "reclaim_rule": "close กลับใต้ระดับในแท่งเดียวกัน"}
        break
    for point in reversed(lows):
        if point["index"] >= len(rows) - 1:
            continue
        if bar["low"] < point["price"] and bar["close"] > point["price"]:
            return {"type": "liquidity_sweep", "side": "low", "level": point["price"],
                    "date": bar["date"], "reclaim_rule": "close กลับเหนือระดับในแท่งเดียวกัน"}
        break
    return None


def group3_supply_demand(rows, *, asset, session_date, cutoff, config) -> list[dict]:
    need = config["minimum_bars"]["zone"]
    value = atr(rows)
    if len(rows) < need or value is None:
        return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=3,
                             reason=f"ต้องใช้อย่างน้อย {need} แท่งและ ATR ที่คำนวณได้ เพื่อวางขอบโซน")]
    lookback = min(config["zone"]["lookback"], len(rows))
    window = rows[-lookback:]
    close = rows[-1]["close"]
    tolerance = value * config["zone"]["touch_tolerance_atr"]

    left, right = config["pivot"]["left"], config["pivot"]["right"]
    highs, lows = find_pivots(window, left=left, right=right)
    if close >= (max(bar["high"] for bar in window) + min(bar["low"] for bar in window)) / 2:
        pool, kind, kind_th = lows, "demand", "อุปสงค์"
    else:
        pool, kind, kind_th = highs, "supply", "อุปทาน"
    candidates = [point for point in pool
                  if (point["price"] < close if kind == "demand" else point["price"] > close)]
    # Pivot อยู่ถูกฝั่งไม่ได้แปลว่า "ขอบโซน" ที่สร้างจากตัวแท่งจะอยู่ถูกฝั่งด้วย
    # (เคสจริง BTC 2026-08-17: pivot high อยู่เหนือราคา แต่ body 63,200–64,200
    # อยู่ใต้ราคาปิด 64,500 ทั้งก้อน) จึงต้องคำนวณขอบของผู้สมัครทีละตัวและรับเฉพาะ
    # โซนที่ยังอยู่ฝั่งเดียวกับคำบรรยาย/หน้าที่ของมันจริง
    ordered = sorted(candidates, key=lambda point: point["price"],
                     reverse=(kind == "demand"))
    origin = None
    lower = upper = None
    for point in ordered:
        candidate_bar = window[point["index"]]
        candidate_lower = min(candidate_bar["open"], candidate_bar["close"])
        candidate_upper = max(candidate_bar["open"], candidate_bar["close"])
        if candidate_upper - candidate_lower < tolerance:
            candidate_lower, candidate_upper = candidate_bar["low"], candidate_bar["high"]
        is_on_required_side = (candidate_upper < close if kind == "demand"
                               else candidate_lower > close)
        if not is_on_required_side:
            continue
        origin = point
        lower, upper = candidate_lower, candidate_upper
        break
    if origin is None:
        return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=3,
                             reason="ไม่มีโซนจากจุดกลับตัวที่ยืนยันแล้วซึ่งยังอยู่ฝั่งที่ต้องการ")]

    assert lower is not None and upper is not None
    touches = sum(1 for item in window[origin["index"] + 1:]
                  if item["low"] <= upper + tolerance and item["high"] >= lower - tolerance)
    return [_evidence(
        asset=asset, session_date=session_date, cutoff=cutoff, group=3, seq=1,
        family=FAMILY_ZONE,
        observation={"type": f"{kind}_zone", "lower": lower, "upper": upper,
                     "origin_bar": origin["date"], "freshness": "fresh" if touches == 0 else "tested",
                     "touch_count": touches},
        interpretation=("โซนที่ราคาเคยตั้งฐานแล้วเด้งขึ้น ยังอยู่ใต้ราคาปัจจุบัน"
                        if kind == "demand" else
                        "โซนที่เคยมีแรงขายกดราคาลงมา ซึ่งยังอยู่เหนือราคาปัจจุบัน"),
        direction="bullish" if kind == "demand" else "bearish",
        certainty="provisional" if touches else "confirmed",
        # ป้ายระดับไปโผล่ในบทตรง ๆ จึงต้องเป็นภาษาไทยล้วน — เคยหลุดเป็น "ขอบล่างโซนsupply"
        level_refs=[{"label": f"ขอบล่างโซน{kind_th}", "price": lower},
                    {"label": f"ขอบบนโซน{kind_th}", "price": upper}],
        source_refs=[origin["date"]],
    )]


def group4_trend_momentum(rows, *, asset, session_date, cutoff, config) -> list[dict]:
    closes = [row["close"] for row in rows]
    evidence: list[dict] = []
    ma20, ma50, ma200 = _sma(closes, 20), _sma(closes, 50), _sma(closes, 200)
    close = closes[-1]

    if ma20 is not None and ma50 is not None:
        above = close > ma20 and close > ma50
        below = close < ma20 and close < ma50
        direction = "bullish" if above else "bearish" if below else "neutral"
        evidence.append(_evidence(
            asset=asset, session_date=session_date, cutoff=cutoff, group=4, seq=1,
            family=FAMILY_TREND,
            observation={"type": "price_vs_moving_averages", "close": close,
                         "ma20": ma20, "ma50": ma50, "ma200": ma200},
            interpretation=("ราคายืนเหนือเส้นค่าเฉลี่ยทั้งสองเส้น แนวโน้มระยะกลางยังเป็นขาขึ้น"
                            if above else
                            "ราคาอยู่ใต้เส้นค่าเฉลี่ยทั้งสองเส้น แนวโน้มระยะกลางยังเป็นขาลง"
                            if below else
                            "ราคาแทรกอยู่ระหว่างเส้นค่าเฉลี่ย แนวโน้มระยะกลางยังไม่ชัด"),
            direction=direction, certainty="confirmed",
            level_refs=[{"label": "เส้นค่าเฉลี่ย 20 วัน", "price": ma20},
                        {"label": "เส้นค่าเฉลี่ย 50 วัน", "price": ma50}],
            source_refs=[rows[-1]["date"]],
            limitations=[] if ma200 is not None else
            ["ประวัติไม่ถึง 200 แท่ง ณ วันนั้น จึงไม่มีเส้นค่าเฉลี่ย 200 วันมาประกอบ"],
        ))
    rsi = _rsi14(closes)
    if rsi is not None:
        if rsi >= 70:
            zone, direction = "ซื้อมากเกินไป", "bearish"
        elif rsi <= 30:
            zone, direction = "ขายมากเกินไป", "bullish"
        elif rsi >= 55:
            zone, direction = "แรงส่งเอียงขึ้น", "bullish"
        elif rsi <= 45:
            zone, direction = "แรงส่งเอียงลง", "bearish"
        else:
            zone, direction = "แรงส่งเป็นกลาง", "neutral"
        evidence.append(_evidence(
            asset=asset, session_date=session_date, cutoff=cutoff, group=4, seq=2,
            family=FAMILY_MOMENTUM,
            observation={"type": "rsi14", "value": rsi, "zone": zone},
            interpretation=f"ดัชนีแรงสัมพัทธ์ 14 วันอยู่ที่ระดับ{zone}",
            direction=direction, certainty="provisional",
            source_refs=[rows[-1]["date"]],
        ))
    if not evidence:
        return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=4,
                             reason="แท่งไม่พอคำนวณทั้งเส้นค่าเฉลี่ยและดัชนีแรงสัมพัทธ์")]
    return evidence


def group5_volatility(rows, *, asset, session_date, cutoff, config) -> list[dict]:
    need = config["minimum_bars"]["atr"]
    if len(rows) < need + 20:
        return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=5,
                             reason=f"ต้องใช้อย่างน้อย {need + 20} แท่งเพื่อเทียบความผันผวนกับอดีต")]
    # เทียบกับอดีตด้วยสัดส่วนต่อราคา ไม่ใช่หน่วยราคาดิบ — ดูเหตุผลที่ `true_ranges`
    ranges = true_ranges(rows, normalized=True)
    current = sum(ranges[-14:]) / 14
    history = [sum(ranges[index - 14:index]) / 14 for index in range(14, len(ranges) + 1)]
    rank = _percentile_rank(history, current)
    atr_absolute = atr(rows)
    if rank >= config["regime"]["expansion_percentile"]:
        state, text = "expansion", "ช่วงแกว่งกว้างกว่าปกติ ความผันผวนกำลังขยายตัว"
    elif rank <= config["regime"]["compression_percentile"]:
        state, text = "compression", "ช่วงแกว่งแคบกว่าปกติ ความผันผวนกำลังบีบตัว"
    else:
        state, text = "normal", "ช่วงแกว่งอยู่ในระดับปกติเทียบกับช่วงที่ผ่านมา"
    return [_evidence(
        asset=asset, session_date=session_date, cutoff=cutoff, group=5, seq=1,
        family=FAMILY_VOLATILITY,
        observation={"type": "atr_percentile", "atr14": atr_absolute,
                     "atr14_pct_of_price": current, "percentile": rank,
                     "percentile_basis": "ช่วงจริงเฉลี่ย 14 แท่ง หารด้วยราคาปิด เทียบกับทุกช่วง 14 แท่งในประวัติที่มี",
                     "state": state},
        interpretation=text,
        direction="neutral",  # ความผันผวนไม่บอกทิศ — กติกาข้อ 5 ที่หัวไฟล์
        certainty="confirmed", source_refs=[rows[-1]["date"]],
        limitations=["ความผันผวนบอกขนาดการเคลื่อนไหว ไม่ได้บอกทิศทาง"],
    )]


def group6_volume(rows, *, asset, session_date, cutoff, config) -> list[dict]:
    has_volume = any("volume" in row for row in rows)
    if not has_volume:
        return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=6,
                             reason=config["unavailable_reason"]["6"])]
    return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=6,
                         reason="พบ field volume แต่ยังไม่มีทะเบียน provenance ที่บอกชนิด volume")]


def group7_fibonacci(rows, *, asset, session_date, cutoff, config) -> list[dict]:
    need = config["minimum_bars"]["fib"]
    if len(rows) < need:
        return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=7,
                             reason=f"ต้องใช้อย่างน้อย {need} แท่งเพื่อวางจุดยึด")]
    left, right = config["pivot"]["left"], config["pivot"]["right"]
    highs, lows = find_pivots(rows, left=left, right=right)
    if not highs or not lows:
        return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=7,
                             reason="ไม่มีจุดกลับตัวที่ยืนยันแล้วครบทั้งยอดและฐาน")]
    anchor_high, anchor_low = highs[-1], lows[-1]
    if anchor_high["index"] == anchor_low["index"]:
        return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=7,
                             reason="จุดยึดยอดกับฐานเป็นแท่งเดียวกัน วัดสัดส่วนไม่ได้")]
    span = anchor_high["price"] - anchor_low["price"]
    if span <= 0:
        return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=7,
                             reason="ระยะระหว่างจุดยึดเป็นศูนย์หรือติดลบ")]
    upswing = anchor_high["index"] > anchor_low["index"]
    levels = []
    for ratio in config["fib"]["ratios"]:
        price = anchor_high["price"] - span * ratio if upswing else anchor_low["price"] + span * ratio
        levels.append({"ratio": ratio, "price": price})
    close = rows[-1]["close"]
    nearest = min(levels, key=lambda item: abs(item["price"] - close))
    return [_evidence(
        asset=asset, session_date=session_date, cutoff=cutoff, group=7, seq=1,
        family=FAMILY_FIB,
        observation={"type": "fib_retracement", "direction": "up" if upswing else "down",
                     "anchor_high": anchor_high, "anchor_low": anchor_low,
                     "levels": levels, "nearest": nearest},
        interpretation=(f"ระดับย่อตัว {nearest['ratio']:.3f} ของช่วงล่าสุด "
                        "เป็นบริเวณที่ราคามักหยุดพักหรือกลับตัว"),
        direction="neutral", certainty="conditional",
        level_refs=[{"label": f"ระดับย่อ {item['ratio']:.3f}", "price": item["price"]}
                    for item in levels],
        source_refs=[anchor_low["date"], anchor_high["date"]],
        limitations=["จุดยึดมาจากช่วงเดียว ระดับที่ได้จึงไม่ใช่เสียงยืนยันอิสระจากโครงสร้าง"],
    )]


def group8_multi_timeframe(rows, *, asset, session_date, cutoff, config) -> list[dict]:
    return [_unavailable(asset=asset, session_date=session_date, cutoff=cutoff, group=8,
                         reason=config["unavailable_reason"]["8"])]


BUILDERS = {
    1: group1_structure,
    2: group2_liquidity,
    3: group3_supply_demand,
    4: group4_trend_momentum,
    5: group5_volatility,
    6: group6_volume,
    7: group7_fibonacci,
    8: group8_multi_timeframe,
}


def build_evidence(bundle: dict, *, config: dict) -> dict:
    """สร้าง EvidenceUnit ครบทั้ง 8 กลุ่มจาก analysis bundle เดียว

    กลุ่มที่ทำไม่ได้จะมี unit สถานะ `unavailable` เสมอ ไม่ใช่หายไปเงียบ ๆ —
    รายงาน coverage ต้องบอกได้ว่าอะไรไม่มีและเพราะอะไร
    """
    rows = bundle["rows"]
    kwargs = {"asset": bundle["asset"], "session_date": bundle["session_date"],
              "cutoff": bundle["cutoff"], "config": config}
    units: list[dict] = []
    readiness: dict[str, str] = {}
    for group in sorted(BUILDERS):
        produced = BUILDERS[group](rows, **kwargs)
        units.extend(produced)
        usable = [unit for unit in produced if unit["quality"] != QUALITY_UNAVAILABLE]
        readiness[str(group)] = "ready" if usable else "unavailable"
    return {
        "asset": bundle["asset"],
        "session_date": bundle["session_date"],
        "cutoff": bundle["cutoff"],
        "confidence_tier": bundle["confidence_tier"],
        "bar_count": len(rows),
        "last_bar": rows[-1]["date"] if rows else None,
        "reference_price": rows[-1]["close"] if rows else None,
        "atr14": atr(rows),
        "readiness": readiness,
        "unavailable_groups": [int(key) for key, value in readiness.items() if value == "unavailable"],
        "evidence": units,
    }
