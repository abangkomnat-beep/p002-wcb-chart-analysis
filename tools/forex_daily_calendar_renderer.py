"""Render Style L daily economic-calendar images.

The renderer intentionally receives already-filtered events.  It owns only
deterministic wrapping, pagination, and the Style D-compatible visual surface.
"""

from __future__ import annotations

import textwrap
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tools import headline_format, image_output, visual_theme, wcb_source
from tools.chart_story_renderer import _thai_font, checked_label


DPI = 100
WIDTH_PX = 1920
MIN_HEIGHT_PX = 560
MAX_HEIGHT_PX = 1140
BASE_HEIGHT_PX = 360
ROW_HEIGHT_PX = 88
MAX_PAGE_UNITS = 8
TITLE_WRAP_WIDTH = 42
NUMBER_WRAP_WIDTH = 38
SOURCE_TEXT = "ที่มา: ปฎิทินเศรษฐกิจ World Class Broker"
WEBP_QUALITY = 84


def _english_date(value: str) -> str:
    day = datetime.strptime(value, "%Y-%m-%d")
    month = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")[day.month - 1]
    return f"{day.day} {month} {day.year}"


def _wrapped_title(event: dict, *, locale: str = "th-TH") -> str:
    if locale == "en-ZA":
        if not event.get("title_en"):
            raise ValueError("English event title required")
        return textwrap.fill(str(event["title_en"]).strip(), width=TITLE_WRAP_WIDTH,
                             break_long_words=True, break_on_hyphens=False)
    return textwrap.fill(
        str(event.get("title") or event.get("title_th") or event.get("title_en")
            or "ไม่ระบุชื่อ").strip(),
        width=TITLE_WRAP_WIDTH, break_long_words=True, break_on_hyphens=False)


def important_numbers(event: dict, *, locale: str = "th-TH") -> str:
    """Compose only numeric values present in the normalized event feed."""
    parts = []
    labels = (("actual", "Actual"), ("forecast", "Forecast"), ("previous", "Previous")) if locale == "en-ZA" else (("actual", "จริง"), ("forecast", "คาด"), ("previous", "ก่อนหน้า"))
    for key, label in labels:
        value = event.get(key)
        if value not in (None, ""):
            parts.append(f"{label} {str(value).strip()}")
    return " · ".join(parts) if parts else ("No forecast figures" if locale == "en-ZA" else "ไม่มีตัวเลขคาดการณ์")


def _wrapped_numbers(event: dict, *, locale: str = "th-TH") -> str:
    return textwrap.fill(
        important_numbers(event, locale=locale), width=NUMBER_WRAP_WIDTH,
        break_long_words=True, break_on_hyphens=False)


def event_row_units(event: dict, *, locale: str = "th-TH") -> int:
    return max(
        1,
        _wrapped_title(event, locale=locale).count("\n") + 1,
        _wrapped_numbers(event, locale=locale).count("\n") + 1,
    )


def paginate_events(events: list[dict], *, locale: str = "th-TH") -> list[list[dict]]:
    """Split rows by wrapped-line demand; order and membership are stable."""
    pages: list[list[dict]] = []
    page: list[dict] = []
    units = 0
    for event in events:
        demand = min(MAX_PAGE_UNITS, event_row_units(event, locale=locale))
        if page and units + demand > MAX_PAGE_UNITS:
            pages.append(page)
            page, units = [], 0
        page.append(event)
        units += demand
    if page:
        pages.append(page)
    return pages


def calendar_height(events: list[dict], *, locale: str = "th-TH") -> tuple[int, list[int]]:
    units = [event_row_units(event, locale=locale) for event in events]
    height = BASE_HEIGHT_PX + ROW_HEIGHT_PX * sum(units)
    return max(MIN_HEIGHT_PX, min(MAX_HEIGHT_PX, height)), units


def filenames(asset: str, article_date: str, page_count: int) -> tuple[str, ...]:
    stem = f"{asset}-forex-daily-calendar-{article_date}"
    if page_count <= 0:
        return ()
    if page_count == 1:
        return (f"{stem}.webp",)
    return tuple(
        f"{stem}-p{page:02d}-of-{page_count:02d}.webp"
        for page in range(1, page_count + 1))


def _date_time_label(event: dict, *, locale: str = "th-TH") -> str:
    raw = str(event.get("at") or "")
    try:
        local = datetime.strptime(raw, "%Y-%m-%d %H:%M")
        if locale == "en-ZA":
            return f"{_english_date(local.date().isoformat())} · {local:%H:%M}"
        date_text = headline_format.thai_date(local.date().isoformat())
        return f"{date_text} · {local:%H:%M} น."
    except ValueError:
        return "Date/time unavailable" if locale == "en-ZA" else "ไม่ระบุวันที่และเวลา"


def event_status(event: dict, cutoff: datetime, *, locale: str = "th-TH") -> str:
    """Return status at the article cutoff, never at the render wall clock."""
    try:
        event_at = datetime.fromisoformat(str(event.get("at") or ""))
    except ValueError:
        return "Awaiting release" if locale == "en-ZA" else "รอประกาศ"
    if event_at.tzinfo is None:
        event_at = event_at.replace(tzinfo=wcb_source.BANGKOK)
    else:
        event_at = event_at.astimezone(wcb_source.BANGKOK)
    cutoff_local = cutoff.astimezone(wcb_source.BANGKOK)
    if locale == "en-ZA":
        return "Released" if event_at <= cutoff_local else "Awaiting release"
    return "ประกาศแล้ว" if event_at <= cutoff_local else "รอประกาศ"


def render_page(*, asset: str, symbol: str, article_date: str,
                events: list[dict], output_path: Path,
                page_number: int, page_count: int, cutoff: datetime, locale: str = "th-TH") -> dict:
    if locale not in {"th-TH", "en-ZA"}:
        raise ValueError("unsupported calendar locale")
    english = locale == "en-ZA"
    if not events:
        raise ValueError("Style L daily calendar ห้ามสร้างภาพว่าง")
    height_px, row_units = calendar_height(events, locale=locale)
    font = _thai_font()
    green = visual_theme.BRAND["deep_green"]
    header_green = visual_theme.BRAND["header_green"]
    gold = visual_theme.BRAND["gold"]
    cream = "#F4EBC9"
    row_cream = "#FFF9E8"
    row_green = "#EDF4EC"
    row_high = "#FFF1C2"

    figure, axes = plt.subplots(figsize=(WIDTH_PX / DPI, height_px / DPI), dpi=DPI)
    figure.patch.set_facecolor(green)
    axes.set_axis_off()
    axes.set_facecolor(green)
    header_height = 0.115
    header_bottom = 1.0 - header_height
    footer_px = 54
    table_bottom = footer_px / height_px
    table_top = header_bottom - 22 / height_px
    axes.set_position([0.01, table_bottom, 0.98, table_top - table_bottom])
    header = figure.add_axes([0.0, header_bottom, 1.0, header_height])
    title_artist, _, underline = visual_theme.draw_edge_to_edge_header(
        figure, header, axes, checked_label(f"{symbol} · {'Today’s key events' if english else 'ข่าวสำคัญวันนี้'}"),
        visual_theme.for_premium_chart(), underline_height_px=4.0)
    header_layout = visual_theme.edge_to_edge_header_layout(
        figure, header, axes, title_artist, underline)

    rows = []
    impacts = []
    for event in events:
        impact = str(event.get("impact") or "").title()
        impacts.append(impact)
        rows.append([
            _date_time_label(event, locale=locale),
            str(event.get("country") or "—").upper(),
            ("High" if impact == "High" else "Medium") if english else ("สูง" if impact == "High" else "ปานกลาง"),
            _wrapped_title(event, locale=locale),
            event_status(event, cutoff, locale=locale),
            _wrapped_numbers(event, locale=locale),
        ])
    columns = [
        "วันที่และเวลาไทย", "สกุลเงิน", "ระดับ", "ข่าว", "สถานะ",
        "ตัวเลขสำคัญ",
    ]
    if english:
        columns = ["Date/time (UTC+07:00)", "Currency", "Impact", "Event", "Status", "Key figures"]
    table = axes.table(
        cellText=[[checked_label(value) for value in row] for row in rows],
        colLabels=[checked_label(value) for value in columns],
        colWidths=[0.18, 0.075, 0.085, 0.34, 0.10, 0.22],
        cellLoc="center", colLoc="center", bbox=[0.0, 0.0, 1.0, 1.0])
    table.auto_set_font_size(False)
    total_units = max(1, sum(row_units))
    cell_mathtext_disabled = True
    for (row_index, column_index), cell in table.get_celld().items():
        cell.set_edgecolor(gold)
        cell.set_linewidth(1.2)
        cell.PAD = 0.035
        text = cell.get_text()
        # Feed units can legitimately contain "$" (for example C$).  Matplotlib
        # otherwise interprets pairs of dollar signs as mathtext and corrupts the
        # glyph run inside the table cell.
        text.set_parse_math(False)
        text.set_fontfamily(font)
        if row_index == 0:
            cell.set_height(0.075)
            cell.set_facecolor(header_green)
            text.set_color(cream)
            text.set_fontsize(14.0)
            text.set_fontweight("bold")
        else:
            cell.set_height(0.91 * row_units[row_index - 1] / total_units)
            high = impacts[row_index - 1] == "High"
            cell.set_facecolor(row_high if high else (row_green if row_index % 2 else row_cream))
            text.set_color(green)
            text.set_fontsize(12.5)
            if column_index in {3, 5}:
                text.set_ha("left")
            if column_index in {1, 2}:
                text.set_fontweight("bold")

    watermark = visual_theme.draw_matplotlib_watermark(
        figure, axes, surface="calendar", zorder=2.25)
    figure.text(
        0.018, table_bottom / 2,
        checked_label(f"{_english_date(article_date)} · Page {page_number}/{page_count}" if english else f"{headline_format.thai_date(article_date)} · หน้า {page_number}/{page_count}"),
        color=cream, fontsize=12.5, va="center")
    figure.text(0.982, table_bottom / 2, checked_label("Source: World Class Broker economic calendar" if english else SOURCE_TEXT),
                color=cream, fontsize=12.5, ha="right", va="center")
    try:
        size = image_output.save_figure(
            figure, output_path, facecolor=green, webp_quality=WEBP_QUALITY)
    finally:
        plt.close(figure)
    return {
        "path": str(output_path), "bytes": size, "kb": image_output.kb(size),
        "rows": len(events), "row_units": row_units,
        "canvas": [WIDTH_PX, height_px], "page": page_number, "pages": page_count,
        "columns": columns, "display_rows": rows, "header": header_layout,
        "cell_mathtext_disabled": cell_mathtext_disabled,
        "date_time_one_line": all("\n" not in row[0] for row in rows),
        "clipped": False, "watermark": watermark,
    }


def render_daily_calendar(*, asset: str, symbol: str, article_date: str,
                          events: list[dict], output_dir: Path,
                          cutoff: datetime, locale: str = "th-TH") -> list[dict]:
    if locale not in {"th-TH", "en-ZA"}:
        raise ValueError("unsupported calendar locale")
    pages = paginate_events(events, locale=locale)
    names = filenames(asset, article_date, len(pages))
    return [
        render_page(
            asset=asset, symbol=symbol, article_date=article_date, events=page,
            output_path=output_dir / name, page_number=index,
            page_count=len(pages), cutoff=cutoff, locale=locale)
        for index, (name, page) in enumerate(zip(names, pages), 1)
    ]
