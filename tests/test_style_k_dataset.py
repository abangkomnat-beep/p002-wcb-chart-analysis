"""เทสชั้นข้อมูล — การจัดชั้นความน่าเชื่อถือ ปฏิทิน session ร่วม และเกณฑ์รับของ

บทเรียนที่ทำให้เทสชุดนี้มีอยู่: **ชื่อโฟลเดอร์ build โกหก** โฟลเดอร์
`2026-08-04T19-40Z-...` มี `cutoff_at` จริงเป็นวันที่ 5 ถ้าจัด tier จากชื่อโฟลเดอร์
จะได้ผลผิดทั้งชุดโดยไม่มีอะไรฟ้อง
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools import style_k_dataset as ds  # noqa: E402
from tests.test_style_k_no_lookahead import bars  # noqa: E402


def write_snapshot(root: Path, folder: str, asset: str, rows, cutoff_at: str) -> Path:
    path = root / folder / asset / "internal" / "raw.snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"asset": asset, "rows": rows, "cutoff_at": cutoff_at,
                                "provider": "test"}, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def config() -> dict:
    return ds.load_config()


def test_tier_uses_cutoff_at_not_the_folder_name(config, tmp_path):
    rows = bars(30, first_date="2026-07-20")
    session_date = rows[2]["date"]
    # ชื่อโฟลเดอร์บอกวันที่ 20 ก.ค. แต่ไฟล์บอกว่าเก็บจริงวันที่ 4 ส.ค. — ช้ากว่ามาก
    write_snapshot(tmp_path, "2026-07-20T00-00Z-misleading", "xauusd", rows,
                   "2026-08-04T10:40:39+00:00")
    snapshots = ds.discover_snapshots("xauusd", build_root=tmp_path)
    picked = ds.select_analysis_source("xauusd", session_date, snapshots=snapshots,
                                       config=config)
    assert picked["confidence_tier"] == ds.TIER_B
    assert picked["limitations"], "Tier B ต้องบอกเหตุผลว่าเก็บช้าไปเท่าไร"


def test_earliest_capture_wins_and_becomes_tier_a(config, tmp_path):
    rows = bars(30, first_date="2026-07-20")
    session_date = rows[-3]["date"]
    # ตั้งชื่อให้เรียงตัวอักษรสวนกับเวลาที่เก็บ เพื่อพิสูจน์ว่าเรียงตาม cutoff_at จริง
    early = write_snapshot(tmp_path, "z-early", "xauusd", rows, f"{rows[-2]['date']}T01:00:00+00:00")
    write_snapshot(tmp_path, "a-late", "xauusd", rows, "2026-09-01T01:00:00+00:00")
    snapshots = ds.discover_snapshots("xauusd", build_root=tmp_path)
    picked = ds.select_analysis_source("xauusd", session_date, snapshots=snapshots,
                                       config=config)
    assert picked["snapshot"]["path"] == early
    assert picked["confidence_tier"] == ds.TIER_A


def test_missing_closed_bar_raises_instead_of_guessing(config, tmp_path):
    rows = bars(10, first_date="2026-07-20")
    write_snapshot(tmp_path, "only", "xauusd", rows, "2026-08-01T00:00:00+00:00")
    snapshots = ds.discover_snapshots("xauusd", build_root=tmp_path)
    with pytest.raises(ds.DatasetUnusable):
        ds.select_analysis_source("xauusd", "2026-12-31", snapshots=snapshots, config=config)


def test_shared_calendar_is_the_intersection_of_assets():
    weekday = [{"date": day} for day in ("2026-08-07", "2026-08-10", "2026-08-11")]
    everyday = [{"date": day} for day in ("2026-08-07", "2026-08-08", "2026-08-09",
                                          "2026-08-10", "2026-08-11")]
    snapshots = {
        "xauusd": [{"closed_dates": {row["date"] for row in weekday}}],
        "btcusd": [{"closed_dates": {row["date"] for row in everyday}}],
    }
    calendar = ds.shared_sessions(snapshots)
    assert calendar == ["2026-08-07", "2026-08-10", "2026-08-11"]
    assert "2026-08-08" not in calendar, "เสาร์อาทิตย์ของทองต้องไม่เป็น session ร่วม"


def test_horizons_skip_weekends_and_never_extrapolate():
    calendar = ["2026-08-06", "2026-08-07", "2026-08-10", "2026-08-11", "2026-08-12"]
    assert ds.horizon_sessions(calendar, "2026-08-07", 1) == ["2026-08-10"]
    assert ds.horizon_sessions(calendar, "2026-08-07", 3) == ["2026-08-10", "2026-08-11",
                                                              "2026-08-12"]
    # ข้อมูลไม่พอต้องคืนลิสต์สั้นกว่า ไม่ใช่เติมวันขึ้นมาเอง
    assert ds.horizon_sessions(calendar, "2026-08-11", 3) == ["2026-08-12"]


def test_inventory_gate_catches_a_tampered_source(config, tmp_path, monkeypatch):
    rows = bars(30, first_date="2026-07-20")
    session_date = rows[-3]["date"]
    path = write_snapshot(tmp_path, "only", "xauusd", rows, f"{rows[-2]['date']}T01:00:00+00:00")
    monkeypatch.setattr(ds, "PROJECT_ROOT", tmp_path)
    inventory = {"sessions": [{
        "asset": "xauusd", "session_date": session_date, "cutoff": f"{session_date}T23:59:59+00:00",
        "confidence_tier": ds.TIER_A, "last_analysis_bar": session_date,
        "source_files": [str(path.relative_to(tmp_path)).replace("\\", "/")],
        "source_hashes": {str(path.relative_to(tmp_path)).replace("\\", "/"): "0" * 64},
        "horizons": {"H+1": ["x"]}, "limitations": [],
    }]}
    problems = ds.inventory_problems(inventory)
    assert any("hash ไม่ตรงไฟล์" in problem for problem in problems)


def test_evaluation_bundle_only_returns_horizon_bars(tmp_path):
    rows = bars(30, first_date="2026-07-20")
    path = tmp_path / "outcome.json"
    path.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    entry = {"asset": "xauusd", "session_date": rows[10]["date"],
             "horizons": {"H+1": [rows[11]["date"]],
                          "H+3": [rows[11]["date"], rows[12]["date"], rows[13]["date"]]}}
    bundle = ds.evaluation_bundle(entry, outcome_sources={"xauusd": path},
                                  project_root=tmp_path)
    assert [row["date"] for row in bundle["rows"]] == [rows[11]["date"], rows[12]["date"],
                                                       rows[13]["date"]]
    assert all(row["date"] > entry["session_date"] for row in bundle["rows"])
