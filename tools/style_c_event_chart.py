"""Internal M5 candlesticks with M30 evidence anchors for Style C."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from tools import chart_renderer, image_output


def filename_for(evidence: dict) -> str:
    return f"xauusd-style-c-{evidence['event']['source_event_key']}-m5.webp"


def render(evidence: dict, output_dir: Path) -> dict:
    reaction = evidence.get("reaction") or {}
    m30_bars = reaction.get("bars") or []
    m30_slots = [bar.get("slot") for bar in m30_bars]
    if (reaction.get("status") != "complete" or not reaction.get("timezone_normalized")
            or m30_slots != ["pre", "+30", "+60", "+90", "+120"]):
        raise ValueError("chart requires exactly five ordered M30 evidence anchors")
    chart_reaction = evidence.get("chart_reaction") or {}
    bars = chart_reaction.get("bars") or []
    if (chart_reaction.get("status") != "complete"
            or not chart_reaction.get("timezone_normalized")
            or chart_reaction.get("timeframe") != "5min" or len(bars) != 27):
        raise ValueError("chart requires exactly 27 closed canonical M5 bars")
    opens_th = [datetime.fromisoformat(bar["open_at_th"]) for bar in bars]
    if any((right-left).total_seconds() != 300 for left, right in zip(opens_th, opens_th[1:])):
        raise ValueError("M5 chart bars do not have exact five-minute cadence")
    event_th = datetime.fromisoformat(evidence["event"]["event_at_th"])
    if opens_th[0] != event_th.replace(second=0, microsecond=0) - timedelta(minutes=15):
        raise ValueError("M5 chart window does not start 15 minutes before release")
    if opens_th[-1] + timedelta(minutes=5) != event_th + timedelta(minutes=120):
        raise ValueError("M5 chart window does not end 120 minutes after release")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename_for(evidence)
    x = list(range(27))
    opened_prices = [float(bar["ohlc"]["open"]) for bar in bars]
    closes = [float(bar["ohlc"]["close"]) for bar in bars]
    lows = [float(bar["ohlc"]["low"]) for bar in bars]
    highs = [float(bar["ohlc"]["high"]) for bar in bars]
    close_labels = [datetime.fromisoformat(bar["close_at_th"]).strftime("%H:%M") for bar in bars]
    chart_renderer._configure_thai_font()  # noqa: SLF001
    fig, ax = plt.subplots(figsize=(11, 5.8), facecolor="#0f172a")
    ax.set_facecolor("#111827")
    body_width = .62
    for xpos, opened, high, low, closed in zip(x, opened_prices, highs, lows, closes):
        color = "#22c55e" if closed >= opened else "#ef4444"
        ax.vlines(xpos, low, high, color=color, linewidth=1.2, alpha=.95)
        ax.add_patch(Rectangle((xpos-body_width/2, min(opened, closed)), body_width,
                               max(abs(closed-opened), .03), facecolor=color,
                               edgecolor=color, linewidth=.8, alpha=.82))

    # M30 anchors remain the numeric evidence used by the article.
    anchor_x = [2, 8, 14, 20, 26]
    anchor_closes = [float(bar["ohlc"]["close"]) for bar in m30_bars]
    ax.plot(anchor_x, anchor_closes, color="#fbbf24", marker="o", linewidth=1.8,
            markersize=5, label="จุดราคาปิด M30 ที่บทใช้ (5 จุด)")
    short_name = str(evidence["event"].get("title_raw") or "ข่าวเศรษฐกิจ")
    at_label = evidence["event"]["event_at_th"][11:16]
    ax.axvline(2.5, color="#38bdf8", linestyle="--", linewidth=2,
               label=f"{short_name} · {at_label} น.")
    tick_x = [0, 2, 5, 8, 11, 14, 17, 20, 23, 26]
    ax.set_xticks(tick_x, [close_labels[index] for index in tick_x])
    ax.set_title("XAUUSD M5 รอบเวลาประกาศข่าว", color="#f8fafc", fontsize=15)
    ax.set_xlabel("เวลาปิดแท่ง (เวลาไทย)", color="#cbd5e1")
    ax.set_ylabel("ดอลลาร์ต่อออนซ์", color="#cbd5e1")
    ax.tick_params(colors="#cbd5e1")
    ax.grid(color="#334155", alpha=.4)
    for spine in ax.spines.values():
        spine.set_color("#475569")
    legend = ax.legend(facecolor="#1e293b", edgecolor="#475569", loc="upper left",
                       bbox_to_anchor=(0, 1.15), ncol=2, fontsize=9)
    for legend_text in legend.get_texts():
        legend_text.set_color("#f8fafc")
    fig.tight_layout(rect=(0, 0, 1, .93))
    image_output.save_figure(fig, path)
    plt.close(fig)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"filename": path.name, "sha256": digest, "bytes": path.stat().st_size,
            "event_at_th": evidence["event"]["event_at_th"],
            "window": chart_reaction["window"], "timeframe": "5min",
            "cadence_minutes": 5, "close_labels_th": close_labels,
            "tick_labels_th": [close_labels[index] for index in tick_x],
            "candle_count": 27, "body_count": 27, "wick_count": 27,
            "m30_anchor_count": 5, "close_marker_count": 5,
            "body_width": body_width,
            "event_marker_label": f"{short_name} · {at_label} น.",
            "legend_placement": "outside_plot_top", "m30_slots": m30_slots,
            "series": ["m5_ohlc_candles", "m30_close_anchors"],
            "clearance": "internal-only"}
