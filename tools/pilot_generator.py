from __future__ import annotations

import argparse
import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


YAHOO_ASSETS = {
    "eurusd": {
        "symbol": "EURUSD=X",
        "basename": "2026-08-03_forex-eurusd",
        "title": "EUR/USD | Daily technical map",
        "decimals": 4,
    },
    "btcusd": {
        "symbol": "BTC-USD",
        "basename": "2026-08-03_crypto-btcusd",
        "title": "BTC/USD | Daily technical map",
        "decimals": 0,
    },
}

ASSET_CONTRACT = {
    "eurusd": {"symbol": "EUR/USD", "instrument_type": "forex_spot", "unit": "USD per EUR"},
    "btcusd": {"symbol": "BTC/USD", "instrument_type": "crypto_spot", "unit": "USD per BTC"},
    "xauusd": {"symbol": "XAU/USD", "instrument_type": "spot", "unit": "USD/oz"},
}


def enrich_snapshot_contract(snapshot: dict, asset: str) -> dict:
    """Attach the provenance fields required by WCB Daily Output Contract v2."""
    if asset not in ASSET_CONTRACT:
        raise ValueError(f"unsupported asset contract: {asset}")
    contract = ASSET_CONTRACT[asset]
    generated_at = snapshot["generated_at"]
    source = snapshot.get("source_url") or snapshot.get("source_path") or snapshot.get("source")
    snapshot["instrument"] = {
        **contract,
        "cutoff_at": generated_at,
        "timezone": "Asia/Bangkok",
        "data_status": "locked_snapshot",
    }
    snapshot["approved_level_sources"] = ["technicals.pivots"]
    snapshot["source_log"] = [
        {
            "field": "quote" if "quote" in snapshot else "rows[-1]",
            "value": snapshot.get("quote", snapshot.get("rows", [None])[-1]),
            "source": source,
            "published_at": generated_at,
            "retrieved_at": generated_at,
            "reviewer": "P002-Data-Adapter",
        },
        {
            "field": "rows",
            "value": {"count": len(snapshot.get("rows", [])), "last": snapshot.get("rows", [None])[-1]},
            "source": source,
            "published_at": generated_at,
            "retrieved_at": generated_at,
            "reviewer": "P002-Data-Adapter",
        },
        {
            "field": "technicals",
            "value": snapshot.get("technicals"),
            "source": source,
            "published_at": generated_at,
            "retrieved_at": generated_at,
            "reviewer": "P002-Data-Adapter",
        },
    ]
    return snapshot


def build_quote_from_rows(rows: list[dict], symbol: str) -> dict:
    """Normalize the latest completed OHLC row to the common quote contract."""
    if len(rows) < 2:
        raise ValueError("at least two rows are required for a quote")
    previous, latest = rows[-2], rows[-1]
    price = float(latest["close"])
    prev_close = float(previous["close"])
    change = price - prev_close
    return {
        "symbol": symbol,
        "price": price,
        "prevClose": prev_close,
        "change": change,
        "percent": (change / prev_close) * 100 if prev_close else 0.0,
        "open": float(latest["open"]),
        "high": float(latest["high"]),
        "low": float(latest["low"]),
        "volume": None,
        "currency": None,
        "isMarketOpen": False,
    }


def _mean(values):
    return sum(values) / len(values) if values else None


def compute_classic_pivots(rows: list[dict]) -> dict:
    if len(rows) < 2:
        raise ValueError("at least two OHLC rows are required for pivots")
    previous = rows[-2]
    high = float(previous["high"])
    low = float(previous["low"])
    close = float(previous["close"])
    pivot = (high + low + close) / 3.0
    return {
        "p": pivot,
        "r1": (2.0 * pivot) - low,
        "r2": pivot + (high - low),
        "r3": high + (2.0 * (pivot - low)),
        "s1": (2.0 * pivot) - high,
        "s2": pivot - (high - low),
        "s3": low - (2.0 * (high - pivot)),
        "basis_date": previous["date"],
        "method": "classic",
    }


def compute_indicators(rows: list[dict]) -> dict:
    if len(rows) < 20:
        raise ValueError("at least 20 OHLC rows are required")

    closes = [float(row["close"]) for row in rows]
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]

    sma20 = _mean(closes[-20:])
    sma50 = _mean(closes[-50:]) if len(closes) >= 50 else None

    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    recent_diffs = diffs[-14:]
    avg_gain = _mean([max(delta, 0.0) for delta in recent_diffs])
    avg_loss = _mean([max(-delta, 0.0) for delta in recent_diffs])
    if avg_loss == 0:
        rsi14 = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi14 = 100.0 - (100.0 / (1.0 + rs))

    true_ranges = []
    for index in range(1, len(rows)):
        high = highs[index]
        low = lows[index]
        previous_close = closes[index - 1]
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    atr14 = _mean(true_ranges[-14:])

    window = rows[-20:]
    support = min(float(row["low"]) for row in window)
    resistance = max(float(row["high"]) for row in window)
    price = closes[-1]
    previous = closes[-2]
    change = price - previous
    percent = (change / previous) * 100 if previous else 0.0

    if sma50 is not None and price > sma20 > sma50:
        trend = "up"
    elif sma50 is not None and price < sma20 < sma50:
        trend = "down"
    else:
        trend = "mixed"

    return {
        "points": len(rows),
        "price": price,
        "previous_close": previous,
        "change": change,
        "percent": percent,
        "sma20": float(sma20),
        "sma50": float(sma50) if sma50 is not None else None,
        "rsi14": float(rsi14),
        "atr14": float(atr14),
        "support": support,
        "resistance": resistance,
        "pivots": compute_classic_pivots(rows),
        "trend": trend,
    }


def _rolling_mean(values: list[float], period: int) -> list[float]:
    output = []
    for index in range(len(values)):
        if index + 1 < period:
            output.append(math.nan)
        else:
            output.append(_mean(values[index + 1 - period:index + 1]))
    return output


def format_volatility_metric(analysis: dict, decimals: int) -> str:
    number_format = f",.{decimals}f"
    if analysis.get("atr14") is not None:
        return f"ATR 14: {format(analysis['atr14'], number_format)}"
    if analysis.get("range5_max") is not None:
        return f"5D max range: {format(analysis['range5_max'], number_format)}"
    return "Volatility: N/A"


def write_chart(
    *,
    rows: list[dict],
    analysis: dict,
    output_dir: Path,
    basename: str,
    title: str,
    source: str,
    decimals: int,
    contract_metadata: dict,
) -> dict:
    from PIL import Image, ImageDraw, ImageFont

    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / f"{basename}.png"
    metadata_path = output_dir / f"{basename}.chart.json"

    closes = [float(row["close"]) for row in rows]
    sma20 = _rolling_mean(closes, 20)
    sma50 = _rolling_mean(closes, 50)
    if all(math.isnan(value) for value in sma20) and analysis.get("sma20") is not None:
        sma20 = [float(analysis["sma20"])] * len(rows)
    if all(math.isnan(value) for value in sma50) and analysis.get("sma50") is not None:
        sma50 = [float(analysis["sma50"])] * len(rows)
    width_px, height_px = 1440, 1080
    left, right, top, bottom = 105, 165, 170, 125
    plot_left, plot_right = left, width_px - right
    plot_top, plot_bottom = top, height_px - bottom
    plot_width, plot_height = plot_right - plot_left, plot_bottom - plot_top

    background = "#0f172a"
    panel = "#111827"
    grid = "#334155"
    muted = "#94a3b8"
    foreground = "#f8fafc"
    image = Image.new("RGB", (width_px, height_px), background)
    draw = ImageDraw.Draw(image)
    draw.rectangle((plot_left, plot_top, plot_right, plot_bottom), fill=panel)

    font_regular_path = Path("C:/Windows/Fonts/arial.ttf")
    font_bold_path = Path("C:/Windows/Fonts/arialbd.ttf")
    font_regular = ImageFont.truetype(str(font_regular_path), 36)
    font_small = ImageFont.truetype(str(font_regular_path), 30)
    font_bold = ImageFont.truetype(str(font_bold_path), 56)
    font_label = ImageFont.truetype(str(font_bold_path), 30)

    all_values = []
    for row in rows:
        all_values.extend([float(row["high"]), float(row["low"])])
    all_values.extend(value for value in sma20 + sma50 if not math.isnan(value))
    all_values.extend([float(analysis["pivots"]["s1"]), float(analysis["pivots"]["r1"])])
    price_min, price_max = min(all_values), max(all_values)
    padding = max((price_max - price_min) * 0.08, abs(price_max) * 0.002)
    price_min -= padding
    price_max += padding

    def x_at(index: int) -> float:
        if len(rows) == 1:
            return plot_left + plot_width / 2
        return plot_left + index * plot_width / (len(rows) - 1)

    def y_at(value: float) -> float:
        return plot_bottom - ((value - price_min) / (price_max - price_min)) * plot_height

    number_format = f",.{decimals}f"
    for step in range(6):
        ratio = step / 5
        y_value = plot_top + ratio * plot_height
        price_value = price_max - ratio * (price_max - price_min)
        draw.line((plot_left, y_value, plot_right, y_value), fill=grid, width=1)
        draw.text((plot_right + 18, y_value - 13), format(price_value, number_format),
                  font=font_small, fill=muted)

    tick_count = min(7, len(rows))
    tick_indexes = sorted(set(round(i * (len(rows) - 1) / max(tick_count - 1, 1)) for i in range(tick_count)))
    for index in tick_indexes:
        x_value = x_at(index)
        draw.line((x_value, plot_top, x_value, plot_bottom), fill=grid, width=1)
        date_label = datetime.fromisoformat(rows[index]["date"]).strftime("%d %b")
        box = draw.textbbox((0, 0), date_label, font=font_small)
        draw.text((x_value - (box[2] - box[0]) / 2, plot_bottom + 22), date_label,
                  font=font_small, fill=muted)

    candle_width = max(5, min(18, int(plot_width / max(len(rows), 1) * 0.58)))
    for index, row in enumerate(rows):
        x_value = x_at(index)
        open_value = float(row["open"])
        high_value = float(row["high"])
        low_value = float(row["low"])
        close_value = float(row["close"])
        color = "#38bdf8" if close_value >= open_value else "#fb7185"
        draw.line((x_value, y_at(high_value), x_value, y_at(low_value)), fill=color, width=2)
        body_top = min(y_at(open_value), y_at(close_value))
        body_bottom = max(y_at(open_value), y_at(close_value))
        if body_bottom - body_top < 2:
            body_bottom = body_top + 2
        draw.rectangle((x_value - candle_width / 2, body_top,
                        x_value + candle_width / 2, body_bottom), fill=color, outline=color)

    def draw_series(values: list[float], color: str, line_width: int):
        points = [(x_at(index), y_at(value)) for index, value in enumerate(values) if not math.isnan(value)]
        if len(points) >= 2:
            draw.line(points, fill=color, width=line_width, joint="curve")

    draw_series(sma20, "#fbbf24", 4)
    draw_series(sma50, "#a78bfa", 4)

    support = analysis["pivots"]["s3"]
    pivot = analysis["pivots"]["p"]
    resistance = analysis["pivots"]["r3"]
    level_specs = (
        (support, "#34d399", "Pivot S3", 18),
        (pivot, "#60a5fa", "Pivot P", -22),
        (resistance, "#f87171", "Pivot R3", -62),
    )
    for value, color, label, label_offset in level_specs:
        y_value = y_at(value)
        dash = 18
        for x_value in range(plot_left, plot_right, dash * 2):
            draw.line((x_value, y_value, min(x_value + dash, plot_right), y_value), fill=color, width=2)
        text = f"{label} {format(value, number_format)}"
        text_box = draw.textbbox((0, 0), text, font=font_label)
        label_y = y_value + label_offset
        draw.rectangle((plot_right - (text_box[2] - text_box[0]) - 22, label_y - 2,
                        plot_right, label_y + (text_box[3] - text_box[1]) + 4), fill=panel)
        draw.text((plot_right - (text_box[2] - text_box[0]) - 12, label_y),
                  text, font=font_label, fill=color)

    last_price = analysis["price"]
    last_x, last_y = x_at(len(rows) - 1), y_at(last_price)
    draw.ellipse((last_x - 7, last_y - 7, last_x + 7, last_y + 7), fill=foreground)
    volatility_text = format_volatility_metric(analysis, decimals)
    info_text = f"Last {format(last_price, number_format)} | RSI 14: {analysis['rsi14']:.1f} | {volatility_text}"
    info_box = draw.textbbox((0, 0), info_text, font=font_label)
    info_x, info_y = plot_left + 20, plot_top + 22
    draw.rounded_rectangle((info_x - 12, info_y - 10, info_x + (info_box[2] - info_box[0]) + 12,
                            info_y + (info_box[3] - info_box[1]) + 12), radius=10,
                           fill="#1e293b", outline="#475569", width=2)
    draw.text((info_x, info_y), info_text, font=font_label, fill=foreground)

    draw.text((plot_left, 38), title, font=font_bold, fill=foreground)
    draw.text((plot_left, 110),
              f"Cutoff: {contract_metadata['cutoff_at']} | {contract_metadata['timezone']} | {contract_metadata['data_status']}",
              font=font_small, fill=muted)
    legend_y = height_px - 55
    draw.line((plot_left, legend_y, plot_left + 50, legend_y), fill="#fbbf24", width=5)
    draw.text((plot_left + 62, legend_y - 15), "SMA 20", font=font_small, fill=foreground)
    draw.line((plot_left + 235, legend_y, plot_left + 285, legend_y), fill="#a78bfa", width=5)
    draw.text((plot_left + 300, legend_y - 20), "SMA 50", font=font_small, fill=foreground)
    draw.text((plot_right - 190, legend_y - 20), "Price (USD)", font=font_small, fill=muted)
    image.save(image_path, format="PNG", optimize=True)

    metadata = {
        "basename": basename,
        "source": source,
        "cutoff": contract_metadata["cutoff_at"],
        "symbol": contract_metadata["symbol"],
        "instrument_type": contract_metadata["instrument_type"],
        "timeframe": "1d",
        "timezone": contract_metadata["timezone"],
        "data_status": contract_metadata["data_status"],
        "unit": contract_metadata["unit"],
        "caption": f"{contract_metadata['symbol']} daily technical map with locked decision levels",
        "alt_text": f"Daily chart of {contract_metadata['symbol']} through {contract_metadata['cutoff_at']}",
        "points": len(rows),
        "annotations": {
            "last": last_price,
            "s1": analysis["pivots"]["s1"],
            "r1": analysis["pivots"]["r1"],
            "p": pivot,
            "s3": support,
            "r3": resistance,
            "sma20": analysis["sma20"],
            "sma50": analysis["sma50"],
            "rsi14": analysis["rsi14"],
            "atr14": analysis.get("atr14"),
            "range5_max": analysis.get("range5_max"),
        },
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"image": image_path, "metadata": metadata_path}


def normalize_ohlc(row: dict) -> dict:
    """Ensure asynchronous quote updates cannot place open/close outside the candle."""
    normalized = dict(row)
    normalized["high"] = max(float(row["high"]), float(row["open"]), float(row["close"]))
    normalized["low"] = min(float(row["low"]), float(row["open"]), float(row["close"]))
    return normalized


def fetch_yahoo_rows(symbol: str) -> tuple[dict, list[dict], str]:
    encoded_symbol = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range=3mo&interval=1d&includePrePost=false"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 P002-pilot/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    result = payload["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    rows = []
    for index, timestamp in enumerate(result["timestamp"]):
        values = {key: quote[key][index] for key in ("open", "high", "low", "close")}
        if any(value is None for value in values.values()):
            continue
        rows.append(normalize_ohlc({
            "date": datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat(),
            **{key: float(value) for key, value in values.items()},
        }))
    return result["meta"], rows, url


def load_xau_rows(path: Path) -> tuple[dict, list[dict], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = [normalize_ohlc({
        "date": row["t"],
        "open": float(row["o"]),
        "high": float(row["h"]),
        "low": float(row["l"]),
        "close": float(row["c"]),
    }) for row in payload["recentDaily"]]
    return payload, rows, str(path)


def generate_asset(asset: str, output_dir: Path, xau_snapshot: Path | None = None) -> dict:
    if asset in YAHOO_ASSETS:
        config = YAHOO_ASSETS[asset]
        source_meta, rows, source = fetch_yahoo_rows(config["symbol"])
        analysis = compute_indicators(rows)
        snapshot = {
            "asset": asset,
            "source": "Yahoo Finance chart API",
            "source_url": source,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "source_meta": source_meta,
            "quote": build_quote_from_rows(rows, source_meta.get("symbol", config["symbol"])),
            "rows": rows,
            "technicals": analysis,
        }
        basename = config["basename"]
        title = config["title"]
        decimals = config["decimals"]
        source_label = "Yahoo Finance"
    elif asset == "xauusd":
        if xau_snapshot is None:
            raise ValueError("--xau-snapshot is required for xauusd")
        source_payload, rows, source = load_xau_rows(xau_snapshot)
        provided = source_payload["technicals"]
        analysis = {
            "points": len(rows),
            "price": float(source_payload["quote"]["price"]),
            "previous_close": float(source_payload["quote"]["prevClose"]),
            "change": float(source_payload["quote"]["change"]),
            "percent": float(source_payload["quote"]["percent"]),
            "sma20": float(provided["values"]["sma20"]),
            "sma50": float(provided["values"]["sma50"]),
            "rsi14": float(provided["values"]["rsi"]),
            "atr14": None,
            "range5_max": max(float(row["high"]) - float(row["low"]) for row in rows),
            "support": min(float(row["low"]) for row in rows),
            "resistance": max(float(row["high"]) for row in rows),
            "pivots": provided["pivots"],
            "trend": provided["summary"],
        }
        snapshot = {
            "asset": asset,
            "source": "WCB/Twelve Data snapshot supplied for pilot",
            "source_path": source,
            "generated_at": source_payload["generatedAt"],
            "quote": source_payload["quote"],
            "performance": source_payload["performance"],
            "rows": rows,
            "technicals": analysis,
            "provided_technicals": provided,
        }
        basename = "2026-08-03_xauusd"
        title = "XAU/USD Spot | 5-day technical map"
        decimals = 2
        source_label = "WCB / Twelve Data snapshot"
    else:
        raise ValueError(f"unsupported asset: {asset}")

    snapshot = enrich_snapshot_contract(snapshot, asset)
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_dir / f"{basename}.snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    chart = write_chart(
        rows=rows,
        analysis=analysis,
        output_dir=output_dir,
        basename=basename,
        title=title,
        source=source_label,
        decimals=decimals,
        contract_metadata=snapshot["instrument"],
    )
    return {"snapshot": snapshot_path, **chart, "analysis": analysis, "rows": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", required=True, choices=["eurusd", "btcusd", "xauusd"])
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--xau-snapshot", type=Path)
    args = parser.parse_args()
    result = generate_asset(args.asset, args.output_dir, args.xau_snapshot)
    print(json.dumps({key: str(value) for key, value in result.items() if key not in {"analysis", "rows"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
