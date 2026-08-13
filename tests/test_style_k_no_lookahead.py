"""เทสกันมองอนาคตของ Style K — ชุดที่สำคัญที่สุดของ pilot นี้

ถ้าชุดนี้ตก ผลเปรียบเทียบทั้งหมดใช้ไม่ได้ ไม่ว่าตัวเลขจะสวยแค่ไหน เพราะแปลว่าบทของวัน D
เห็นสิ่งที่ยังไม่เกิด · เทสจึงวัดที่ **แฮชของผลลัพธ์** ไม่ใช่วัดว่าโค้ดเรียกฟังก์ชันไหน
— วิธีเรียกเปลี่ยนได้ แต่คุณสมบัติ "เติมข้อมูลอนาคตแล้วผลไม่ขยับ" ต้องจริงเสมอ
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools import style_k_dataset as ds  # noqa: E402
from tools import style_k_scenarios as sc  # noqa: E402
from tools import style_k_selector as sel  # noqa: E402
from tools import style_k_techniques as tk  # noqa: E402


def bars(count: int, *, start: float = 100.0, step: float = 1.0,
         first_date: str = "2026-01-01") -> list[dict]:
    """แท่งเดินขึ้นสม่ำเสมอ พร้อมคลื่นเล็กเพื่อให้มีจุดกลับตัวจริง"""
    import datetime as dt
    rows = []
    day = dt.date.fromisoformat(first_date)
    for index in range(count):
        wave = 3.0 if index % 7 in (3, 4) else 0.0
        close = start + step * index + wave
        rows.append({
            "date": (day + dt.timedelta(days=index)).isoformat(),
            "open": close - step * 0.4,
            "high": close + step * 0.9,
            "low": close - step * 0.9,
            "close": close,
        })
    return rows


@pytest.fixture
def config() -> dict:
    return ds.load_config()


def make_bundle(rows: list[dict], session_date: str) -> dict:
    return {
        "asset": "xauusd",
        "session_date": session_date,
        "cutoff": f"{session_date}T23:59:59+00:00",
        "confidence_tier": "A",
        "rows": ds.rows_upto(rows, session_date),
        "source_files": [], "source_hashes": {}, "limitations": [],
    }


def test_last_row_is_always_treated_as_unclosed():
    rows = bars(5)
    assert [row["date"] for row in ds.closed_rows(rows)] == [row["date"] for row in rows[:-1]]
    assert ds.closed_rows(rows[:1]) == []


def test_future_rows_do_not_change_analysis_hash(config):
    """เติมแท่งหลังวัน D เข้าไปแล้วผลของชั้นวิเคราะห์ต้องแฮชเท่าเดิมเป๊ะ"""
    rows = bars(120)
    session_date = rows[89]["date"]

    base = tk.build_evidence(make_bundle(rows[:90], session_date), config=config)
    with_future = tk.build_evidence(make_bundle(rows, session_date), config=config)
    assert ds.hash_payload(base) == ds.hash_payload(with_future)

    base_selection = sel.select(base, config=config)
    future_selection = sel.select(with_future, config=config)
    assert ds.hash_payload(base_selection) == ds.hash_payload(future_selection)
    assert ds.hash_payload(sc.build_scenarios(base, base_selection)) == \
        ds.hash_payload(sc.build_scenarios(with_future, future_selection))


def test_extreme_future_bar_cannot_leak_into_levels(config):
    """แท่งอนาคตที่ราคาสุดโต่งต้องไม่โผล่เป็นระดับใด ๆ ในผลของวัน D"""
    rows = bars(120)
    session_date = rows[89]["date"]
    spike = dict(rows[95])
    spike.update({"high": 99999.0, "low": 98000.0, "close": 99000.0, "open": 98500.0})
    polluted = rows[:95] + [spike] + rows[96:]

    record = tk.build_evidence(make_bundle(polluted, session_date), config=config)
    for unit in record["evidence"]:
        for ref in unit.get("level_refs") or []:
            assert ref["price"] < 50000.0, f"ระดับราคาปนแท่งอนาคต: {unit['evidence_id']}"


def test_pivot_requires_confirmed_right_window():
    """จุดกลับตัวที่ยังไม่ครบหน้าต่างขวา ห้ามถูกนับ ณ cutoff"""
    rows = bars(40)
    peak = dict(rows[-1])
    peak["high"] = max(row["high"] for row in rows) + 50
    rows[-1] = peak

    highs, _ = tk.find_pivots(rows, left=3, right=3)
    assert all(point["index"] <= len(rows) - 4 for point in highs)
    assert peak["date"] not in {point["date"] for point in highs}


def test_rows_upto_is_inclusive_of_session_date():
    rows = bars(10)
    kept = ds.rows_upto(rows, rows[4]["date"])
    assert [row["date"] for row in kept] == [row["date"] for row in rows[:5]]


def test_analysis_bundle_never_returns_bars_after_cutoff(tmp_path):
    """ประตูเดียวที่ชั้นวิเคราะห์ใช้ ต้องตัดแท่งเกิน cutoff ให้เองเสมอ"""
    import json
    rows = bars(30)
    snapshot = tmp_path / "raw.snapshot.json"
    snapshot.write_text(json.dumps({"asset": "xauusd", "rows": rows}), encoding="utf-8")
    session_date = rows[9]["date"]
    entry = {
        "asset": "xauusd", "session_date": session_date,
        "cutoff": f"{session_date}T23:59:59+00:00", "confidence_tier": "A",
        "source_files": ["raw.snapshot.json"], "source_hashes": {}, "limitations": [],
    }
    bundle = ds.analysis_bundle(entry, project_root=tmp_path)
    assert bundle["rows"][-1]["date"] == session_date
    assert all(row["date"] <= session_date for row in bundle["rows"])


def test_hash_payload_ignores_key_order_and_thai_escaping():
    left = {"ก": 1, "ข": "โครงสร้าง"}
    right = {"ข": "โครงสร้าง", "ก": 1}
    assert ds.hash_payload(left) == ds.hash_payload(right)
