"""เทสบทและภาพของ Style K

จุดที่เทสจับ: โครง 6 ส่วน · กรอบจำนวนคำที่วัดด้วยตัวนับคำไทยตัวจริง ·
ตัวเลขทุกตัวย้อนกลับถึงหลักฐานได้ · และภาพไม่มีแท่งหลัง cutoff
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools import style_k_dataset as ds  # noqa: E402
from tools import style_k_renderer as rd  # noqa: E402
from tools import style_k_scenarios as sc  # noqa: E402
from tools import style_k_selector as sel  # noqa: E402
from tools import style_k_techniques as tk  # noqa: E402
from tools import style_k_writer as wr  # noqa: E402
from tools import voice_rules  # noqa: E402
from tools import language_review, locale_loader  # noqa: E402
from tests.test_style_k_no_lookahead import bars, make_bundle  # noqa: E402


@pytest.fixture
def config() -> dict:
    return ds.load_config()


@pytest.fixture
def built(config):
    import datetime as dt
    rows = bars(300)
    last = rows[-1]
    day = dt.date.fromisoformat(last["date"])
    for step in range(1, 6):
        close = last["close"] - 4.0 * step
        rows.append({"date": (day + dt.timedelta(days=step)).isoformat(),
                     "open": close + 1.5, "high": close + 2.5,
                     "low": close - 2.5, "close": close})
    session_date = rows[-1]["date"]
    bundle = make_bundle(rows, session_date)
    record = tk.build_evidence(bundle, config=config)
    selection = sel.select(record, config=config)
    manifest = sc.build_scenarios(record, selection)
    entry = {"asset": "xauusd", "session_date": session_date,
             "cutoff": bundle["cutoff"], "limitations": []}
    markdown, sidecar = wr.build_article(record=record, selection=selection,
                                         manifest=manifest, config=config, entry=entry)
    return {"record": record, "selection": selection, "manifest": manifest,
            "bundle": bundle, "markdown": markdown, "sidecar": sidecar,
            "entry": entry, "config": config}


def test_article_passes_its_own_gate(built):
    assert wr.article_problems(built["markdown"], built["sidecar"],
                               config=built["config"], record=built["record"]) == []


def test_sections_are_complete_and_in_order(built):
    positions = [built["markdown"].find(f"## {heading}") for heading in wr.SECTIONS]
    assert all(position >= 0 for position in positions)
    assert positions == sorted(positions)


def test_word_count_uses_the_thai_aware_counter(built):
    """กรอบ 350–560 ต้องวัดด้วย `count_public_words` ไม่ใช่ len() หรือนับช่องว่าง"""
    count = voice_rules.count_public_words(built["markdown"])
    assert built["sidecar"]["word_count"] == count
    assert 350 <= count <= 560
    naive = len(built["markdown"].split())
    assert naive < count, "การนับด้วยช่องว่างให้ค่าต่ำกว่าจริงในภาษาไทย — ห้ามใช้"


def test_every_number_maps_back_to_evidence(built):
    ids = {unit["evidence_id"] for unit in built["record"]["evidence"]} | {"reference_price"}
    assert built["sidecar"]["number_refs"]
    for ref in built["sidecar"]["number_refs"]:
        assert ref["evidence_id"] in ids
        assert ref["role"]


def test_article_never_cites_unavailable_techniques(built):
    by_id = {unit["evidence_id"]: unit for unit in built["record"]["evidence"]}
    for evidence_id in built["sidecar"]["evidence_used"]:
        assert by_id[evidence_id]["quality"] != tk.QUALITY_UNAVAILABLE


def test_author_routing_follows_the_asset(config):
    assert config["assets"]["xauusd"]["author_slug"] == "natthaphon-s"
    assert config["assets"]["btcusd"]["author_slug"] == "world-class-broker-team"


def test_frontmatter_marks_the_pilot_as_unpublished(built):
    head = built["markdown"].split("---")[1]
    assert "published: false" in head
    assert "status: pilot_only" in head
    assert "style: K" in head


def test_no_term_explanations_in_body(built):
    """มติผู้ใช้ 08-14: Style K ไม่อธิบายศัพท์ — ห้ามมีประโยคขยาย 'ในที่นี้หมายถึง' ในบท"""
    body = built["markdown"]
    assert "ในที่นี้หมายถึง" not in body, "พบประโยคอธิบายศัพท์ ทั้งที่กลไก GLOSS ถูกถอดแล้ว"


def test_no_latin_word_is_glued_to_thai_text(built):
    """คำอังกฤษต้องไม่ติดกับอักษรไทยโดยไม่มีตัวคั่น — เคยหลุด 'ขอบล่างโซนsupply' มาแล้ว"""
    import re
    glued = re.findall(r"[ก-๙][A-Za-z]{2,}|[A-Za-z]{2,}[ก-๙]", built["markdown"])
    assert not glued, f"พบคำอังกฤษติดคำไทย: {glued}"


def test_editorial_language_uses_reader_facing_thai(built):
    """มติผู้ใช้ 08-18: เกลาภาษาแม่แบบ K โดยไม่แตะสาระและไม่ปล่อยศัพท์ภายใน"""
    body = built["markdown"]
    awkward_or_internal = (
        "ตลาดอยู่ในช่วงที่ช่วงแกว่ง",
        "ภาพยังไม่ใช่ทางเดียวชัดเจน",
        "ซึ่งบทไม่ได้เล่าข้างต้น",
        "ระดับ equal high",
        "ระดับ equal low",
        "แต่ตัวมันเองไม่ได้บอก",
        "อันดับแรกคือระดับ",
    )
    for phrase in awkward_or_internal:
        assert phrase not in body

    assert "โดยน้ำหนักจากกราฟตอนนี้เอียงไป" in body
    assert "รอให้เงื่อนไขเกิดก่อนจึงค่อยตัดสินใจ" in body


def test_public_level_labels_translate_only_internal_equal_labels():
    assert wr._public_level_label("ระดับ equal high") == "ยอดราคาใกล้เคียงกัน"
    assert wr._public_level_label("ระดับ equal low") == "ฐานราคาใกล้เคียงกัน"
    assert wr._public_level_label("เส้นค่าเฉลี่ย 20 วัน") == "เส้นค่าเฉลี่ย 20 วัน"


def test_editorial_copy_keeps_scenario_conditions_and_certainty(built):
    """ด่านกันงานภาษาเปลี่ยน trigger/ทิศ/ระดับ/การยืนยันของสถานการณ์"""
    markdown = built["markdown"]
    instrument = built["config"]["assets"][built["record"]["asset"]]["instrument_type"]
    for scenario in built["manifest"]["scenarios"]:
        rule = scenario["confirmation_rule"]
        side = "เหนือ" if rule["comparison"] == "gt" else "ใต้"
        shown_level = voice_rules.format_price(rule["level"], instrument)
        assert f"ถ้าราคาปิดรายวัน{side}ระดับ {shown_level}" in markdown
        assert "ถือว่าสถานการณ์นี้ถูกยืนยัน" in markdown

    invalidate = built["manifest"]["scenarios"][0]["invalidation_rule"]
    invalidate_side = "ใต้" if invalidate["comparison"] == "lt" else "เหนือ"
    shown_invalidate = voice_rules.format_price(invalidate["level"], instrument)
    assert f"ถ้าราคาปิดรายวัน{invalidate_side}ระดับ {shown_invalidate}" in markdown
    assert "ให้ถือว่ามุมมองหลักของวันนี้ไม่เป็นไปตามคาด" in markdown


def test_generated_article_passes_mechanical_language_review(built):
    pack = locale_loader.load_locale("th-TH")
    review = language_review.review_text(
        built["markdown"], pack, review_id="LANG-th-TH-style-k-writer-test"
    )
    assert review["summary"]["total"] == 0, review["revisions"]


def test_images_carry_alt_text_and_no_future_candles(built, tmp_path):
    display = built["config"]["assets"]["xauusd"]["display"]
    session_date = built["entry"]["session_date"]
    overview = rd.render_overview(bundle=built["bundle"], record=built["record"],
                                  selection=built["selection"],
                                  output=tmp_path / "overview.webp", display=display)
    scenarios = rd.render_scenarios(bundle=built["bundle"], record=built["record"],
                                    manifest=built["manifest"],
                                    output=tmp_path / "evidence-scenarios.webp",
                                    display=display)
    for meta in (overview, scenarios):
        assert rd.image_problems(meta, record=built["record"], session_date=session_date,
                                 config=built["config"]) == []
        assert meta["last_bar"] <= session_date
        assert meta["alt_text"]
        assert meta["bytes"] <= built["config"]["image"]["max_bytes"]
    if any(str(unit["observation"].get("type", "")).endswith("_zone")
           and unit["quality"] != "unavailable" for unit in built["record"]["evidence"]):
        zone_labels = {item["label"] for item in scenarios["annotations"]}
        assert zone_labels & {"โซนอุปสงค์", "โซนอุปทาน"}


def test_renderer_refuses_bars_after_cutoff(built, tmp_path):
    import datetime as dt
    polluted = dict(built["bundle"])
    last = built["bundle"]["rows"][-1]
    day = dt.date.fromisoformat(last["date"]) + dt.timedelta(days=1)
    polluted["rows"] = built["bundle"]["rows"] + [{**last, "date": day.isoformat()}]
    with pytest.raises(rd.RenderRefused):
        rd.render_overview(bundle=polluted, record=built["record"],
                           selection=built["selection"], output=tmp_path / "x.webp",
                           display="ทดสอบ")


def test_annotation_without_evidence_id_is_refused(built, tmp_path):
    figure, axis = rd.plt.subplots()
    with pytest.raises(rd.RenderRefused):
        rd._annotate_level(axis, built["bundle"]["rows"], 100.0, "ป้ายลอย", "#000", None)
    rd.plt.close(figure)
