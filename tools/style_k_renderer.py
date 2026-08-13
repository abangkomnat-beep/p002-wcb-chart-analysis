"""ตัววาดภาพของ Style K — สองใบต่อบท: ภาพรวม และ หลักฐาน/สถานการณ์

**ข้อห้ามที่โค้ดบังคับ ไม่ใช่แค่เตือน:**

1. **ห้ามมีแท่งหลัง cutoff บนภาพของบท** — ตัววาดรับเฉพาะแถวจาก analysis bundle
   ซึ่งถูกตัดที่ cutoff แล้ว และยังตรวจซ้ำก่อนวาดว่าไม่มีแถวไหนเกินวัน D
2. **ทุกป้ายบนภาพต้องชี้ `evidence_id`** — ป้ายที่ไม่มี evidence_id วาดไม่ได้ ไม่ใช่
   วาดแล้วค่อยไปตรวจทีหลัง กับดักเดิมคือป้ายสวย ๆ ที่ไม่มีใครรู้ว่ามาจากไหน
3. **ภาพเปรียบเทียบผลจริงอยู่คนละโฟลเดอร์ชื่อ `evaluation`** — ไม่ปนกับภาพของบท

บีบไฟล์: ลดคุณภาพก่อน ไม่ลดความละเอียด — ภาพที่เล็กลงจนอ่านป้ายไม่ออกคือภาพที่เสีย
ประโยชน์ทั้งใบ ต่อให้ผ่านเพดาน 200 KB
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from tools import image_output  # noqa: E402

WINDOW = 60
UP_COLOR = "#1a7f5a"
DOWN_COLOR = "#b3373b"
GRID_COLOR = "#dfe3e8"
TEXT_COLOR = "#20262e"
CONFIRM_COLOR = "#1668c1"
INVALID_COLOR = "#c2410c"
ZONE_COLOR = "#f0b429"


class RenderRefused(RuntimeError):
    """ปฏิเสธการวาด — ดีกว่าปล่อยภาพที่ข้อมูลไม่ตรงบทออกไป"""


def _thai_font() -> str | None:
    for name in ("Tahoma", "Leelawadee UI", "Leelawadee", "Noto Sans Thai", "Angsana New"):
        try:
            font_manager.findfont(name, fallback_to_default=False)
            return name
        except Exception:  # noqa: BLE001 — ฟอนต์ไม่มีคือเรื่องปกติข้ามเครื่อง
            continue
    return None


_FONT = _thai_font()
if _FONT:
    plt.rcParams["font.family"] = _FONT
plt.rcParams["axes.unicode_minus"] = False


def _guard(rows: list[dict], session_date: str) -> list[dict]:
    future = [row["date"] for row in rows if row["date"] > session_date]
    if future:
        raise RenderRefused(
            f"พบแท่งหลัง cutoff บนภาพของบท: {future[:3]} — ปฏิเสธการวาดทั้งใบ"
        )
    return rows[-WINDOW:]


def _candles(axis, rows: list[dict]) -> None:
    for index, row in enumerate(rows):
        rising = row["close"] >= row["open"]
        color = UP_COLOR if rising else DOWN_COLOR
        axis.vlines(index, row["low"], row["high"], color=color, linewidth=0.9)
        lower = min(row["open"], row["close"])
        height = max(abs(row["close"] - row["open"]), (row["high"] - row["low"]) * 0.02)
        axis.add_patch(plt.Rectangle((index - 0.32, lower), 0.64, height,
                                     facecolor=color, edgecolor=color, linewidth=0.4))


def _frame(axis, rows: list[dict], title: str) -> None:
    axis.set_title(title, fontsize=12, color=TEXT_COLOR, pad=10, loc="left")
    axis.grid(True, color=GRID_COLOR, linewidth=0.6, alpha=0.8)
    axis.set_axisbelow(True)
    ticks = list(range(0, len(rows), max(1, len(rows) // 6)))
    axis.set_xticks(ticks)
    axis.set_xticklabels([rows[index]["date"][5:] for index in ticks], fontsize=8)
    axis.tick_params(axis="y", labelsize=8)
    for spine in ("top", "right"):
        axis.spines[spine].set_visible(False)
    axis.set_xlim(-1, len(rows))


def _annotate_level(axis, rows, price, label, color, evidence_id, *, style="--"):
    if not evidence_id:
        raise RenderRefused(f"ป้าย '{label}' ไม่มี evidence_id — ห้ามวาดป้ายที่ไม่มีที่มา")
    axis.axhline(price, color=color, linewidth=1.2, linestyle=style, alpha=0.9)
    axis.text(len(rows) - 0.5, price, f" {label}", color=color, fontsize=8,
              va="center", ha="left")


def render_overview(*, bundle: dict, record: dict, selection: dict, output: Path,
                    display: str) -> dict:
    """ใบที่ 1 — โครงสร้างและตำแหน่งราคา ณ วัน D"""
    rows = _guard(bundle["rows"], record["session_date"])
    figure, axis = plt.subplots(figsize=(9.6, 5.2), dpi=125)
    _candles(axis, rows)

    annotations: list[dict] = []
    by_id = {unit["evidence_id"]: unit for unit in record["evidence"]}
    structure = by_id.get(selection["primary_evidence_id"])
    for evidence_id in [selection["primary_evidence_id"], *selection["supporting_evidence_ids"]]:
        unit = by_id.get(evidence_id)
        if not unit:
            continue
        for ref in (unit.get("level_refs") or [])[:2]:
            if ref.get("price") is None:
                continue
            _annotate_level(axis, rows, ref["price"], ref["label"], CONFIRM_COLOR,
                            unit["evidence_id"], style=":")
            annotations.append({"label": ref["label"], "price": ref["price"],
                                "evidence_id": unit["evidence_id"]})

    reference = record["reference_price"]
    _annotate_level(axis, rows, reference, "ราคาปิดวันวิเคราะห์", TEXT_COLOR, "reference_price",
                    style="-")
    annotations.append({"label": "ราคาปิดวันวิเคราะห์", "price": reference,
                        "evidence_id": "reference_price"})

    _frame(axis, rows, f"{display} · ภาพรวมถึงวันที่ {record['session_date']}")
    figure.tight_layout()
    size = image_output.save_figure(figure, output)
    plt.close(figure)
    return {
        "path": output.name,
        "bytes": size,
        "alt_text": (f"กราฟแท่งเทียนรายวันของ{display} ถึงวันที่ {record['session_date']} "
                     f"พร้อมเส้นระดับราคาสำคัญที่บทอ้างถึง"),
        "annotations": annotations,
        "last_bar": rows[-1]["date"],
        "structure_evidence_id": structure["evidence_id"] if structure else None,
    }


def render_scenarios(*, bundle: dict, record: dict, manifest: dict, output: Path,
                     display: str) -> dict:
    """ใบที่ 2 — หลักฐานหลัก เงื่อนไขยืนยัน เงื่อนไขหักล้าง และเส้นทาง A/B"""
    rows = _guard(bundle["rows"], record["session_date"])
    figure, axis = plt.subplots(figsize=(9.6, 5.2), dpi=125)
    _candles(axis, rows)

    annotations: list[dict] = []
    scenario_a = manifest["scenarios"][0]
    confirm = scenario_a["confirmation_rule"]
    invalidate = scenario_a["invalidation_rule"]

    _annotate_level(axis, rows, confirm["level"], f"ยืนยัน A · {confirm['level_label']}",
                    CONFIRM_COLOR, confirm["level_evidence_id"])
    annotations.append({"label": f"ยืนยัน A · {confirm['level_label']}",
                        "price": confirm["level"], "evidence_id": confirm["level_evidence_id"]})
    _annotate_level(axis, rows, invalidate["level"], f"หักล้าง A · {invalidate['level_label']}",
                    INVALID_COLOR, invalidate["level_evidence_id"])
    annotations.append({"label": f"หักล้าง A · {invalidate['level_label']}",
                        "price": invalidate["level"],
                        "evidence_id": invalidate["level_evidence_id"]})

    zone = next((unit for unit in record["evidence"]
                 if str(unit["observation"].get("type", "")).endswith("_zone")
                 and unit["quality"] != "unavailable"), None)
    if zone:
        lower = zone["observation"]["lower"]
        upper = zone["observation"]["upper"]
        axis.axhspan(lower, upper, color=ZONE_COLOR, alpha=0.18)
        axis.text(0.5, upper, f" โซนจากหลักฐาน {zone['evidence_id'][-8:]}",
                  fontsize=7.5, color="#8a6100", va="bottom")
        annotations.append({"label": "โซนอุปสงค์–อุปทาน", "price": (lower + upper) / 2,
                            "evidence_id": zone["evidence_id"]})

    axis.annotate("", xy=(len(rows) - 0.5, confirm["level"]),
                  xytext=(len(rows) - 8, record["reference_price"]),
                  arrowprops={"arrowstyle": "->", "color": CONFIRM_COLOR, "alpha": 0.75})
    axis.annotate("", xy=(len(rows) - 0.5, invalidate["level"]),
                  xytext=(len(rows) - 8, record["reference_price"]),
                  arrowprops={"arrowstyle": "->", "color": INVALID_COLOR, "alpha": 0.75})

    _frame(axis, rows, f"{display} · หลักฐานและเงื่อนไข ณ วันที่ {record['session_date']}")
    figure.tight_layout()
    size = image_output.save_figure(figure, output)
    plt.close(figure)
    return {
        "path": output.name,
        "bytes": size,
        "alt_text": (f"กราฟ{display} แสดงระดับยืนยันและระดับที่หักล้างของสถานการณ์หลัก "
                     f"พร้อมโซนหลักฐานที่บทอ้างถึง"),
        "annotations": annotations,
        "last_bar": rows[-1]["date"],
    }


def image_problems(meta: dict, *, record: dict, session_date: str, config: dict) -> list[str]:
    problems: list[str] = []
    limit = config["image"]["max_bytes"]
    if meta["bytes"] > limit:
        problems.append(f"{meta['path']}: {meta['bytes']} ไบต์ เกินเพดาน {limit}")
    if meta["last_bar"] > session_date:
        problems.append(f"{meta['path']}: มีแท่งหลัง cutoff ({meta['last_bar']})")
    if not meta.get("alt_text"):
        problems.append(f"{meta['path']}: ไม่มีคำบรรยายภาพภาษาไทย")
    ids = {unit["evidence_id"] for unit in record["evidence"]} | {"reference_price"}
    for annotation in meta["annotations"]:
        if annotation["evidence_id"] not in ids:
            problems.append(f"{meta['path']}: ป้าย '{annotation['label']}' อ้าง evidence_id ที่ไม่มี")
    return problems
