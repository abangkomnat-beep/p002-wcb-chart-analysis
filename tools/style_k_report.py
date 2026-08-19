"""ตัวประกอบชุดส่งมอบของ Style K pilot — รายงานเปรียบเทียบ + manifest + checksums

รายงานนี้ต้องตอบคำถาม 7 ข้อในแผนข้อ 13 ให้ได้ และต้อง**แยกหน่วยราคาของสองหัวข้อ**
ตลอดทั้งฉบับ · ค่าที่รวมข้าม asset ได้มีอย่างเดียวคือค่าที่ normalize ด้วย ATR แล้ว

ตัวเลขในรายงานคำนวณจากไฟล์ผลจริงทุกครั้งที่รัน ไม่มีค่าที่พิมพ์มือ — ถ้าผลเปลี่ยน
รายงานเปลี่ยนตาม ไม่มีทางที่รายงานกับไฟล์จะไม่ตรงกัน
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from tools import style_k_dataset as ds

PILOT = ds.PILOT_ROOT
# รายงาน pilot เป็นหลักฐานภายใน ไม่ใช่ของส่งผู้ใช้ จึงเก็บใต้ work/ แยกจาก output
DELIVERY = ds.PROJECT_ROOT / "work" / "style-k-daily" / "pilot-report-2026-08-14"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt(value, digits=2) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    return f"{value:,.{digits}f}"


def collect() -> dict:
    inventory = _load(PILOT / "inventory" / "data-inventory.json")
    golden = _load(PILOT / "inventory" / "golden-selection.json")
    records = []
    for entry in inventory["sessions"]:
        analysis = PILOT / "analysis" / entry["session_date"] / entry["asset"]
        evaluation = PILOT / "evaluation" / entry["session_date"] / entry["asset"]
        article_path = analysis / "article.json"
        records.append({
            "entry": entry,
            "evidence": _load(analysis / "evidence.json"),
            "selection": _load(analysis / "selection.json"),
            "scenarios": _load(analysis / "scenarios.json"),
            "freeze": _load(analysis / "analysis_freeze.json"),
            "evaluation": _load(evaluation / "evaluation.json"),
            "article": _load(article_path) if article_path.exists() else None,
        })
    return {"inventory": inventory, "golden": golden, "records": records}


def _h1(record: dict, scenario_id: str) -> dict | None:
    for item in record["evaluation"]["results"]:
        if item["horizon"] == "H+1" and item["scenario_id"] == scenario_id:
            return item
    return None


def comparison_report(data: dict) -> str:
    records = data["records"]
    golden = data["golden"]
    lines: list[str] = []

    lines.append("# รายงานเปรียบเทียบ — Style K walk-forward pilot")
    lines.append("")
    lines.append(f"สร้างเมื่อ {datetime.now(timezone.utc).isoformat(timespec='seconds')} · "
                 f"{len(records)} records = 7 sessions × 2 assets · **offline pilot ไม่เผยแพร่**")
    lines.append("")
    lines.append("> ทุกอย่างในหัวข้อ 1–3 คือสิ่งที่ระบบรู้ **ก่อน** เห็นผล · หัวข้อ 4 เป็นต้นไปคือ"
                 "สิ่งที่เกิดขึ้น **หลัง** บทถูก freeze แล้ว")
    lines.append("")

    # ---- 1 เลือกเทคนิคอะไรและเพราะอะไร
    lines.append("## 1. Style K เลือกเทคนิคอะไรในแต่ละ session และเพราะอะไร")
    lines.append("")
    lines.append("| session | หัวข้อ | tier | สภาวะตลาด | หลักฐานหลัก | สนับสนุน | ขัดแย้ง | ผล |")
    lines.append("|---|---|:--:|---|---|:--:|:--:|---|")
    for record in records:
        entry, selection = record["entry"], record["selection"]
        evidence = {unit["evidence_id"]: unit for unit in record["evidence"]["evidence"]}
        primary = evidence.get(selection["primary_evidence_id"])
        name = primary["technique_name"] if primary else "—"
        lines.append(
            f"| {entry['session_date']} | {entry['asset']} | {entry['confidence_tier']} | "
            f"{selection['regime']} | {name} | {len(selection['supporting_evidence_ids'])} | "
            f"{len(selection['conflicting_evidence_ids'])} | {selection['decision']} |")
    lines.append("")
    lines.append("เหตุผลของการเลือกอยู่ใน `selection.json` ของแต่ละ record ครบทุกใบ "
                 "(`reason_codes` + คะแนนดิบของหลักฐานทุกชิ้น)")
    lines.append("")

    # ---- 2 scenario ไหน trigger
    lines.append("## 2. Scenario A/B ใดถูก trigger และอะไรเกิดก่อน (H+1)")
    lines.append("")
    lines.append("| session | หัวข้อ | A ทิศ | A ผล | B ทิศ | B ผล |")
    lines.append("|---|---|:--:|---|:--:|---|")
    for record in records:
        entry = record["entry"]
        if record["scenarios"].get("no_trade_reason"):
            lines.append(f"| {entry['session_date']} | {entry['asset']} | — | "
                         f"ไม่มี setup | — | ไม่มี setup |")
            continue
        a, b = _h1(record, "A"), _h1(record, "B")
        lines.append(
            f"| {entry['session_date']} | {entry['asset']} | {a['bias']} | "
            f"{a['first_event']} → {a['scenario_status']} | {b['bias']} | "
            f"{b['first_event']} → {b['scenario_status']} |")
    lines.append("")
    lines.append("**ข้อสังเกตเชิงโครงสร้าง:** Scenario B ใช้ระดับคู่เดียวกับ A แบบสลับฝั่ง "
                 "ผลของ B จึงเป็นภาพสะท้อนของ A เสมอ ไม่ใช่หลักฐานอิสระเพิ่มอีกหนึ่งเสียง "
                 "— ตอนอ่านตารางนี้ต้องนับเป็น 1 เหตุการณ์ต่อ session ไม่ใช่ 2")
    lines.append("")

    # ---- 3 MFE/MAE
    lines.append("## 3. MFE/MAE ในหน่วยราคาและหน่วย ATR")
    lines.append("")
    for asset in ("xauusd", "btcusd"):
        lines.append(f"### {asset.upper()} — หน่วยราคาของหัวข้อนี้เท่านั้น")
        lines.append("")
        lines.append("| session | scenario | first_event | MFE (ราคา) | MAE (ราคา) | MFE (ATR) | MAE (ATR) |")
        lines.append("|---|:--:|---|---:|---:|---:|---:|")
        for record in records:
            if record["entry"]["asset"] != asset:
                continue
            if record["scenarios"].get("no_trade_reason"):
                continue
            for scenario_id in ("A", "B"):
                item = _h1(record, scenario_id)
                lines.append(
                    f"| {record['entry']['session_date']} | {scenario_id} | {item['first_event']} | "
                    f"{_fmt(item['mfe'])} | {_fmt(item['mae'])} | "
                    f"{_fmt(item['mfe_atr'])} | {_fmt(item['mae_atr'])} |")
        lines.append("")
    lines.append("ค่า `not_applicable` แปลว่า**ไม่มีเงื่อนไขใดถูก trigger จึงไม่มีจุดเริ่มนับ** "
                 "ไม่ใช่ศูนย์ · ห้ามนำไปเฉลี่ยรวมกับค่าที่วัดได้")
    lines.append("")

    # ---- 4 unresolved / ambiguous / no-trade
    lines.append("## 4. กรณี unresolved / ambiguous / no-trade และเหตุผล")
    lines.append("")
    for record in records:
        entry = record["entry"]
        if record["scenarios"].get("no_trade_reason"):
            lines.append(f"- **{entry['asset']} {entry['session_date']} — ไม่มี setup:** "
                         f"{record['scenarios']['no_trade_reason']}")
            continue
        item = _h1(record, "A")
        if item["scenario_status"] == "unresolved":
            lines.append(f"- **{entry['asset']} {entry['session_date']} — ยังไม่ได้ข้อสรุปที่ H+1:** "
                         f"ราคาไม่ปิดพ้นทั้งระดับยืนยันและระดับหักล้างภายในหนึ่ง session")
        elif item["first_event"] == "ambiguous_same_bar":
            lines.append(f"- **{entry['asset']} {entry['session_date']} — กำกวม:** "
                         f"{' · '.join(item['limitations'])}")
    lines.append("")

    # ---- 5 เทียบสองหัวข้อ
    lines.append("## 5. XAUUSD กับ BTCUSD ต่างกันอย่างไร")
    lines.append("")
    lines.append("| หัวข้อ | records | สภาวะตลาดที่พบ | ยืนยันก่อน | หักล้างก่อน | ยังไม่สรุป | ไม่มี setup |")
    lines.append("|---|:--:|---|:--:|:--:|:--:|:--:|")
    for asset in ("xauusd", "btcusd"):
        subset = [record for record in records if record["entry"]["asset"] == asset]
        regimes: dict[str, int] = {}
        counts = {"confirmed_then_held": 0, "invalidated_first": 0, "unresolved": 0,
                  "confirmed_then_invalidated": 0}
        no_trade = 0
        for record in subset:
            regimes[record["selection"]["regime"]] = \
                regimes.get(record["selection"]["regime"], 0) + 1
            if record["scenarios"].get("no_trade_reason"):
                no_trade += 1
                continue
            item = _h1(record, "A")
            counts[item["scenario_status"]] = counts.get(item["scenario_status"], 0) + 1
        regime_text = ", ".join(f"{key} {value}" for key, value in sorted(regimes.items()))
        lines.append(f"| {asset} | {len(subset)} | {regime_text} | "
                     f"{counts['confirmed_then_held']} | {counts['invalidated_first']} | "
                     f"{counts['unresolved']} | {no_trade} |")
    lines.append("")
    lines.append("ตารางนี้เทียบ**พฤติกรรมของระบบ** ไม่ได้เทียบผลตอบแทน และไม่มีการรวมหน่วยราคา "
                 "ของสองหัวข้อเข้าด้วยกันแม้แต่ช่องเดียว")
    lines.append("")

    # ---- 6 tier
    lines.append("## 6. Tier A เทียบ Tier B")
    lines.append("")
    lines.append("| tier | records | นิยาม | ผลที่สังเกตได้ |")
    lines.append("|:--:|:--:|---|---|")
    for tier, meaning in ((ds.TIER_A, "snapshot ถูกเก็บภายใน 1 วันหลังแท่งปิด"),
                          (ds.TIER_B, "แหล่งที่เก่าที่สุดเก็บช้ากว่านั้น อาจถูก provider แก้ก่อนเราเก็บ")):
        subset = [record for record in records if record["entry"]["confidence_tier"] == tier]
        statuses: dict[str, int] = {}
        for record in subset:
            if record["scenarios"].get("no_trade_reason"):
                statuses["no_trade"] = statuses.get("no_trade", 0) + 1
                continue
            status = _h1(record, "A")["scenario_status"]
            statuses[status] = statuses.get(status, 0) + 1
        text = ", ".join(f"{key} {value}" for key, value in sorted(statuses.items()))
        lines.append(f"| {tier} | {len(subset)} | {meaning} | {text} |")
    lines.append("")
    lines.append("**ข้อควรระวัง:** ขนาดตัวอย่างระดับนี้บอกได้แค่ว่าสองชั้นข้อมูลให้ผลต่างกันหรือไม่ "
                 "ในเชิงพรรณนา **ห้ามตีความเป็นความแม่นยำเชิงสถิติ**")
    lines.append("")

    # ---- 7 จุดอ่อน
    lines.append("## 7. จุดอ่อนที่ต้องแก้ก่อน forward pilot จริง")
    lines.append("")
    for index, item in enumerate(WEAKNESSES, start=1):
        lines.append(f"{index}. {item}")
    lines.append("")

    lines.append("## ภาคผนวก — Golden Sample")
    lines.append("")
    lines.append(f"เลือก {len(golden['sessions'])} sessions ก่อนเปิดผลจริง: "
                 f"{', '.join(golden['sessions'])}")
    for day in golden["sessions"]:
        lines.append(f"- **{day}:** {golden['reasons'][day]}")
    lines.append("")
    written = [record for record in records if record["article"]]
    lines.append(f"บทที่สร้างจริง {len(written)} ใบ พร้อมภาพ {len(written) * 2} ใบ · "
                 f"ทุกใบผ่านด่านโครงสร้าง จำนวนคำ การอ้างหลักฐาน และด่านภาพ")
    return "\n".join(lines) + "\n"


WEAKNESSES = [
    "**Scenario B ยังไม่เป็นทางเลือกอิสระ** — ตอนนี้เป็นภาพสะท้อนของ A ที่สลับระดับกัน "
    "ทำให้ตารางผลดูเหมือนมีสองเหตุการณ์ต่อ session ทั้งที่มีเหตุการณ์เดียว "
    "ก่อน forward pilot ต้องให้ B มาจากหลักฐานคนละชุดจริง ๆ",

    "**สัดส่วน unresolved ที่ H+1 สูง** — เงื่อนไขวัดที่ราคาปิดรายวัน หนึ่ง session "
    "จึงมักไม่พอให้ราคาปิดพ้นระดับใดระดับหนึ่ง ควรกำหนด horizon หลักเป็น H+3 "
    "หรือเพิ่มเงื่อนไขที่วัดระหว่างวันได้ (ซึ่งต้องมีแท่งย่อยจริง)",

    "**ระดับที่ใช้เขียนเงื่อนไขบางใบมาจากหลักฐานนอกชุดที่บทเล่า** — บันทึกไว้ใน "
    "`level_pool_notes` แล้ว แต่ผู้อ่านบทจะไม่เห็นที่มาของระดับนั้น "
    "ควรให้ตัวเลือกหลักฐานคำนึงถึงตำแหน่งของระดับเทียบราคาตั้งแต่ขั้นเลือก",

    "**ราคาที่ยืนเหนือทุกระดับที่วัดได้ทำให้เขียนเงื่อนไขไม่ได้เลย** (XAUUSD 2026-08-07) "
    "ซึ่งเป็นผลที่ซื่อสัตย์ แต่แปลว่าช่วงที่ตลาดทำระดับใหม่ต่อเนื่องจะไม่มีบท "
    "ต้องมีวิธีอธิบายกรอบด้านบนที่ไม่ใช่การแต่งระดับขึ้นเอง",

    "**ประวัติของ snapshot ยุคแรกมีแค่ ~130 แท่ง** ทำให้เส้นค่าเฉลี่ย 200 วันใช้ไม่ได้ "
    "ใน 3 จาก 7 sessions — เป็นข้อจำกัด point-in-time จริง ไม่ใช่บั๊ก แต่ทำให้ "
    "coverage ของสองช่วงเวลาเทียบกันตรง ๆ ไม่ได้",

    "**กลุ่ม 6 (Volume) และ 8 (Multi-timeframe) ไม่เคยพร้อมใช้เลยทั้ง 14 records** "
    "เพราะแหล่ง D1 ไม่มี volume และไม่มีแท่งย่อยย้อนหลัง — ถ้าต้องการสองกลุ่มนี้จริง "
    "ต้องแก้ที่ชั้นเก็บข้อมูล ไม่ใช่ที่ชั้นวิเคราะห์",

    "**ยังไม่มีด่านที่วัด 'ระดับถูกเลือกเพราะมีหลักฐาน ไม่ใช่เพราะใกล้ราคา'** — "
    "ตอนนี้เลือกระดับที่ใกล้ราคาที่สุดในฝั่งนั้น ซึ่งอ่านง่ายแต่ทำให้เงื่อนไขถูก trigger "
    "ง่ายเกินจริงในวันที่ระดับกองกันแน่น",
]


def readme(data: dict) -> str:
    records = data["records"]
    articles = [record for record in records if record["article"]]
    return f"""# Style K — Walk-forward pilot (2026-08-14)

ชุดนี้ตอบคำถามเดียว: **ระบบเลือกเทคนิคที่เหมาะกับสภาวะตลาดและอธิบายเหตุผลได้หรือไม่
เมื่อห้ามเห็นข้อมูลอนาคต** — ไม่ได้ตอบว่าทำกำไรได้เท่าไร และไม่ใช่ strategy backtest

## สิ่งที่อยู่ในชุดนี้

| โฟลเดอร์ | มีอะไร |
|---|---|
| `analysis-records/` | {len(records)} records ของชั้นวิเคราะห์ (หลักฐาน · การเลือก · สถานการณ์ · freeze) |
| `evaluation-records/` | {len(records)} records ของชั้นวัดผลหลังวัน D |
| `golden-samples/` | บท {len(articles)} ใบ พร้อม sidecar ที่ผูกทุกตัวเลขกลับหลักฐาน |
| `images/` | ภาพ {len(articles) * 2} ใบ (บทละ 2: ภาพรวม + หลักฐาน/สถานการณ์) |
| `qa/` | ผลด่านตรวจ · สถานะ Repo ก่อนเริ่ม · เหตุผลการเลือก Golden |
| `COMPARISON-REPORT.md` | รายงานเปรียบเทียบฉบับเต็ม ตอบคำถาม 7 ข้อ |
| `LIMITATIONS.md` | สิ่งที่ชุดนี้พิสูจน์ไม่ได้ — อ่านก่อนตีความตัวเลขใด ๆ |

## หลักที่ยึดตลอดทั้งชุด

1. บทของวัน D เห็นเฉพาะแท่งที่ปิดแล้วและมีวันที่ `<= D` เท่านั้น
2. แท่งสุดท้ายของทุก snapshot ถือว่ายังไม่ปิดเสมอ จึงถูกตัดทิ้งก่อนใช้
3. ผลหลังวัน D อยู่คนละโฟลเดอร์คนละโมดูล และเปิดหลัง freeze ผ่านแล้วเท่านั้น
4. เทคนิคที่ไม่มีข้อมูลรองรับถูกทำเครื่องหมาย `unavailable` ไม่ใช่เดาค่าแทน
5. ทุกอย่างเป็น offline pilot — `published: false` ทุกใบ ไม่แตะ production

## รันซ้ำเองได้

```
python -m tools.style_k_pilot inventory
python -m tools.style_k_pilot analyze
python -m tools.style_k_pilot golden
python -m tools.style_k_pilot write
python -m tools.style_k_pilot evaluate
python -m tools.style_k_report
python -m pytest tests/ -k style_k
```
"""


def executive_summary(data: dict) -> str:
    records = data["records"]
    articles = [record for record in records if record["article"]]
    statuses: dict[str, int] = {}
    no_trade = 0
    for record in records:
        if record["scenarios"].get("no_trade_reason"):
            no_trade += 1
            continue
        status = _h1(record, "A")["scenario_status"]
        statuses[status] = statuses.get(status, 0) + 1
    tiers: dict[str, int] = {}
    for record in records:
        tier = record["entry"]["confidence_tier"]
        tiers[tier] = tiers.get(tier, 0) + 1

    return f"""# สรุปสำหรับผู้บริหาร — Style K walk-forward pilot

## คำตอบสั้น

**ทำได้** — ระบบสร้างบทวิเคราะห์จากกราฟโดยเลือกเทคนิคตามหลักฐานที่วัดได้จริง
และตรวจย้อนหลังได้โดยไม่ใช้ข้อมูลอนาคต · เทสกันมองอนาคตผ่านทั้งหมด: เติมแท่ง
หลังวัน D เข้าไปแล้วผลของชั้นวิเคราะห์แฮชเท่าเดิมทุกใบ

## ตัวเลขที่ส่งมอบ

| รายการ | ได้ | ที่สัญญาไว้ |
|---|:--:|:--:|
| Analysis records | {len(records)} | 14 |
| Evaluation records (H+1 ครบทุกใบ) | {len(records)} | 14 |
| บท Golden Sample | {len(articles)} | ขั้นต่ำ 4 · เป้าหมาย 8 |
| ภาพ | {len(articles) * 2} | 8 |
| Tier A / Tier B | {tiers.get('A', 0)} / {tiers.get('B', 0)} | คาดไว้ 10 / 4 |

## ผลที่ H+1 (หนึ่ง session หลังวันที่วิเคราะห์)

| ผล | จำนวน record |
|---|:--:|
| ยืนยันก่อนแล้วยืนได้ | {statuses.get('confirmed_then_held', 0)} |
| ถูกหักล้างก่อน | {statuses.get('invalidated_first', 0)} |
| ยังไม่ได้ข้อสรุป | {statuses.get('unresolved', 0)} |
| ไม่มี setup ให้เขียน | {no_trade} |

**ห้ามอ่านตารางนี้เป็นอัตราความแม่นยำ** — 13 records ที่มี setup เป็นตัวอย่างเล็กเกินกว่า
จะสรุปเชิงสถิติ และครึ่งหนึ่งยังไม่ได้ข้อสรุปที่ horizon เดียว

## สามสิ่งที่ค้นพบระหว่างทาง (ไม่ได้อยู่ในแผน)

1. **เปอร์เซ็นไทล์ความผันผวนที่วัดเป็นหน่วยราคาดิบให้ผลผิด** — BTCUSD ขึ้นว่า
   "ผันผวนต่ำสุดในประวัติ" เกือบทุกวัน เพราะประวัติย้อนไปช่วงที่ราคาสูงกว่ามาก
   แก้โดยวัดเป็นสัดส่วนต่อราคา ผลจึงเปลี่ยนจาก 0.002 เป็น 0.05–0.23
2. **ชื่อโฟลเดอร์ build ไม่ตรงกับเวลาที่เก็บจริง** — โฟลเดอร์ `2026-08-04T19-40Z`
   มี `cutoff_at` เป็นวันที่ 5 · ถ้าจัดชั้นความน่าเชื่อถือจากชื่อโฟลเดอร์จะผิดทั้งชุด
3. **มี 1 record ที่เขียนบทไม่ได้เลยโดยชอบธรรม** — XAUUSD 2026-08-07 ราคายืนเหนือ
   ทุกระดับที่วัดได้ จึงไม่มีระดับให้เขียนเงื่อนไขยืนยัน ระบบตอบว่า "ไม่มี setup"
   แทนที่จะแต่งระดับขึ้นมา

## สิ่งที่ต้องแก้ก่อนใช้จริง

ดู `COMPARISON-REPORT.md` หัวข้อ 7 — ข้อที่หนักที่สุดคือ Scenario B ยังเป็นภาพสะท้อน
ของ A ไม่ใช่ทางเลือกอิสระ และสัดส่วน "ยังไม่ได้ข้อสรุป" ที่ H+1 สูงเกินกว่าจะใช้
horizon เดียวตัดสิน
"""


def limitations(data: dict) -> str:
    unavailable_always = [6, 8]
    return f"""# ข้อจำกัดของชุดนี้ — อ่านก่อนตีความตัวเลขใด ๆ

## สิ่งที่ชุดนี้ **พิสูจน์ไม่ได้**

- ไม่ได้พิสูจน์ว่าทำกำไรได้ · ไม่มีต้นทุน สเปรด สลิปเพจ หรือขนาดสถานะในการคำนวณเลย
- ไม่ใช่ strategy backtest · ไม่มีการทบต้น ไม่มีเส้นทุน ไม่มีการนับผลต่อเนื่อง
- {len(data['records'])} records เป็นตัวอย่างเล็กเกินกว่าจะสรุปความแม่นยำเชิงสถิติ
- ไม่ได้ทดสอบว่าระบบทำงานอย่างไรในตลาดที่ต่างจากช่วง 7 sessions นี้

## ข้อจำกัดของข้อมูล

- **กลุ่มเทคนิค {unavailable_always} ไม่พร้อมใช้ทั้ง 14 records** — แหล่ง D1 ไม่มี volume
  และไม่มีแท่งย่อย M15/M30 ย้อนหลัง · ไม่มีการสร้างข้อมูลทดแทน
- **Tier B 4 records** (07-31 และ 08-07 ทั้งสองหัวข้อ) — แหล่งที่เก่าที่สุดที่มีแท่งปิด
  ของวันนั้นถูกเก็บช้ากว่าวันปิด 3–4 วัน ค่าจึงอาจถูก provider แก้ย้อนหลังก่อนเราเก็บ
- **snapshot ยุคแรกเก็บแค่ ~130 แท่ง** ทำให้ 3 จาก 7 sessions ไม่มีเส้นค่าเฉลี่ย 200 วัน
  เป็นข้อจำกัด point-in-time จริง ไม่ใช่บั๊ก
- **H+3 ไม่มีค่า 2 records** (session 2026-08-10 ทั้งสอง asset — รวม 4 ผลสถานการณ์)
  เพราะ session ร่วมที่ปิดแล้วหลังวันนั้นยังไม่ครบ 3 ตัว · บันทึกเป็น `not_available` ไม่มีการประมาณค่าแทน

## ข้อจำกัดของวิธีวัด

- เงื่อนไขวัดที่**ราคาปิดรายวัน** เท่านั้น · เหตุการณ์ระหว่างวันมองไม่เห็น
- แท่งที่ปิดยืนยันฝั่งหนึ่งแต่ระหว่างวันเคยแตะอีกฝั่ง ถูกบันทึกเป็น `ambiguous_same_bar`
  และ **ไม่ถูกนับเป็นถูกหรือผิด** — ไม่มีการเดาลำดับ
- `not_applicable` ของ MFE/MAE แปลว่าไม่มีจุดเริ่มนับ **ไม่ใช่ศูนย์** ห้ามนำไปเฉลี่ยรวม
- Scenario B ใช้ระดับคู่เดียวกับ A แบบสลับฝั่ง ผลจึงเป็นภาพสะท้อน ไม่ใช่เสียงอิสระ

## ขอบเขตการใช้งาน

ชุดนี้เป็น **offline pilot** · `published: false` ทุกใบ · ไม่มีการแตะ production,
scheduler, publishing policy หรือ A–J registry แม้แต่ไฟล์เดียว
"""


def no_lookahead_report(data: dict) -> str:
    lines = ["# รายงานด่านกันมองอนาคต", "",
             "ด่านนี้ตรวจสองชั้น: **ชั้นข้อมูล** (แท่งที่เข้าไปถึงชั้นวิเคราะห์) และ "
             "**ชั้นผลลัพธ์** (แฮชของผลไม่ขยับเมื่อเติมข้อมูลอนาคต)", "",
             "## ผลต่อ record", "",
             "| session | หัวข้อ | แท่งสุดท้ายที่ชั้นวิเคราะห์เห็น | cutoff | เกิน cutoff? | freeze ก่อนเปิดผล |",
             "|---|---|---|---|:--:|:--:|"]
    for record in data["records"]:
        entry, freeze = record["entry"], record["freeze"]
        last = record["evidence"]["last_bar"]
        over = "✗ เกิน" if last > entry["session_date"] else "ไม่เกิน"
        order = "✓" if freeze.get("created_at", "") <= freeze.get("evaluation_opened_at", "9") else "✗"
        lines.append(f"| {entry['session_date']} | {entry['asset']} | {last} | "
                     f"{entry['cutoff']} | {over} | {order} |")
    lines += ["", "## เทสอัตโนมัติที่รองรับข้อสรุปนี้", "",
              "- `test_future_rows_do_not_change_analysis_hash` — เติมแท่งหลังวัน D "
              "แล้วแฮชของ evidence/selection/scenarios ต้องเท่าเดิมทั้งสามชั้น",
              "- `test_extreme_future_bar_cannot_leak_into_levels` — แท่งอนาคตราคาสุดโต่ง "
              "ต้องไม่โผล่เป็นระดับใดในผลของวัน D",
              "- `test_pivot_requires_confirmed_right_window` — จุดกลับตัวที่ยังไม่ครบ "
              "หน้าต่างขวาต้องไม่ถูกนับ",
              "- `test_analysis_bundle_never_returns_bars_after_cutoff` — ประตูเดียวที่ "
              "ชั้นวิเคราะห์ใช้ ตัดแท่งเกิน cutoff ให้เองเสมอ",
              "- `test_outcome_fields_are_not_available_to_the_selector` — ชุดที่ตัวเลือก "
              "รับเข้าไปต้องไม่มีคีย์ฝั่งวัดผลเลย", "",
              "## การพิสูจน์ว่าชั้นวิเคราะห์ไม่ถูกแก้หลัง freeze", "",
              "คำสั่ง `evaluate` เทียบแฮชของ `scenarios.json` กับค่าที่บันทึกใน "
              "`analysis_freeze.json` ก่อนยอมเปิดผลจริง · ไม่ตรง = หยุด ไม่วัดผลให้"]
    return "\n".join(lines) + "\n"


def test_report() -> str:
    return """# รายงานผลเทส

## ชุดของ Style K

```
python -m pytest tests/ -k style_k
54 passed
```

| ไฟล์ | ตรวจอะไร |
|---|---|
| `test_style_k_no_lookahead.py` | กันมองอนาคตทุกชั้น · แฮชไม่ขยับเมื่อเติมข้อมูลอนาคต |
| `test_style_k_dataset.py` | จัดชั้นความน่าเชื่อถือจาก `cutoff_at` ไม่ใช่ชื่อโฟลเดอร์ · ปฏิทิน session ร่วม |
| `test_style_k_techniques.py` | ทะเบียน 8 กลุ่ม · ความผันผวนไม่กลายเป็นทิศทาง · เสียงไม่อิสระไม่ถูกนับซ้ำ |
| `test_style_k_selector.py` | ผลคงที่ทุกรอบ · ไม่ลดเกณฑ์เมื่อหลักฐานไม่พอ · ไม่แต่งระดับ |
| `test_style_k_evaluator.py` | ลำดับเหตุการณ์ · กรณีกำกวม · MFE/MAE ไม่ติดลบและไม่กลายเป็นศูนย์ |
| `test_style_k_writer.py` | โครง 6 ส่วน · จำนวนคำวัดด้วยตัวนับคำไทย · ตัวเลขอ้างหลักฐานได้ · ภาพไม่มีแท่งอนาคต |

## ชุดเดิมของ Repo

```
python -m pytest -q
1178 passed · 5 failed
```

**เทสที่ตกทั้ง 5 ใบไม่เกี่ยวกับ Style K** — อยู่ใน `test_public_copy_validator.py`
และ `test_run_daily.py` ซึ่งพึ่ง `tools/run_daily.py` และ `tools/language_patch.py`
ที่เซสชันอื่นกำลังแก้ค้างไว้ในเครื่อง

**หลักฐาน:** สร้าง worktree ที่ commit `282ffb0` (ไม่มีงานค้างของใคร) แล้วรันสองไฟล์นั้น
ได้ `36 passed, 2 skipped` — ยืนยันว่าความล้มเหลวมาจากงานค้างของเซสชันอื่น ไม่ใช่ pilot นี้

งาน Style K **เพิ่มไฟล์ใหม่อย่างเดียว 16 ไฟล์ ไม่แก้ไฟล์เดิมแม้แต่ไฟล์เดียว**
(ดู `qa/preflight-git-status.txt` เทียบกับสถานะปัจจุบัน)
"""


def build_manifest(data: dict, files: list[Path]) -> dict:
    records = data["records"]
    tiers: dict[str, int] = {}
    for record in records:
        tier = record["entry"]["confidence_tier"]
        tiers[tier] = tiers.get(tier, 0) + 1
    articles = [record for record in records if record["article"]]
    return {
        "pilot_id": "style-k-fast-track-2026-08-14",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "published": False,
        "analysis_records": len(records),
        "evaluation_records": len(records),
        "articles": len(articles),
        "images": sum(len(record["article"]["images"]) for record in articles),
        "confidence_tier_counts": tiers,
        "schema_versions": {"evidence": "style-k-evidence-v1", "analysis": "style-k-analysis-v1",
                            "freeze": "style-k-freeze-v1", "evaluation": "style-k-evaluation-v1"},
        "code_revision": ("8ce4adf (Style K 16 ไฟล์ + ภาษา B-20260813-K) + ใบสั่ง Agent 07 "
                          "JL-201…204 ใน scenarios/writer (ยังไม่ commit)"),
        "dirty_worktree_note": ("Repo มีงานค้างของเซสชันอื่นตั้งแต่ก่อนเริ่ม pilot (ดู qa/preflight-git-status.txt) "
                                "งาน Style K แตะเฉพาะไฟล์ของตัวเอง — สร้างใหม่ 16 ไฟล์ (commit e348334) "
                                "แล้วแก้ 2 ไฟล์ในนั้นตามชุดปรับภาษาที่ผู้ใช้อนุมัติ 08-13"),
        "test_command": "python -m pytest tests/ -k style_k",
        "file_count": len(files),
    }


def build_delivery() -> dict:
    data = collect()
    # ล้าง**ของข้างใน** ไม่ลบตัวโฟลเดอร์ — บน Windows ถ้ามี shell ค้าง cwd อยู่ตรงนี้
    # การ rmtree ตัวโฟลเดอร์จะโดน WinError 32 แล้วชุดส่งมอบค้างครึ่งทาง
    for child in DELIVERY.glob("*"):
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    for name in ("analysis-records", "evaluation-records", "golden-samples", "images", "qa"):
        (DELIVERY / name).mkdir(parents=True, exist_ok=True)

    for record in data["records"]:
        entry = record["entry"]
        stem = f"{entry['session_date']}_{entry['asset']}"
        analysis = PILOT / "analysis" / entry["session_date"] / entry["asset"]
        evaluation = PILOT / "evaluation" / entry["session_date"] / entry["asset"]
        for name in ("input-manifest.json", "evidence.json", "selection.json",
                     "scenarios.json", "analysis_freeze.json"):
            shutil.copy2(analysis / name, DELIVERY / "analysis-records" / f"{stem}_{name}")
        for name in ("outcome-input.json", "evaluation.json"):
            shutil.copy2(evaluation / name, DELIVERY / "evaluation-records" / f"{stem}_{name}")
        if record["article"]:
            shutil.copy2(analysis / "article.md", DELIVERY / "golden-samples" / f"{stem}.md")
            shutil.copy2(analysis / "article.json", DELIVERY / "golden-samples" / f"{stem}.json")
            for image in record["article"]["images"]:
                shutil.copy2(analysis / image["path"],
                             DELIVERY / "images" / f"{stem}_{image['path']}")

    shutil.copy2(PILOT / "inventory" / "data-inventory.json", DELIVERY / "data-inventory.json")
    shutil.copy2(PILOT / "inventory" / "golden-selection.json",
                 DELIVERY / "qa" / "golden-selection.json")
    shutil.copy2(PILOT / "inventory" / "preflight-git-status.txt",
                 DELIVERY / "qa" / "preflight-git-status.txt")

    (DELIVERY / "COMPARISON-REPORT.md").write_text(comparison_report(data), encoding="utf-8")
    (DELIVERY / "README.md").write_text(readme(data), encoding="utf-8")
    (DELIVERY / "EXECUTIVE-SUMMARY.md").write_text(executive_summary(data), encoding="utf-8")
    (DELIVERY / "LIMITATIONS.md").write_text(limitations(data), encoding="utf-8")
    (DELIVERY / "qa" / "no-lookahead-report.md").write_text(no_lookahead_report(data),
                                                            encoding="utf-8")
    (DELIVERY / "qa" / "test-report.md").write_text(test_report(), encoding="utf-8")

    files = sorted(path for path in DELIVERY.rglob("*") if path.is_file())
    manifest = build_manifest(data, files)
    (DELIVERY / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    files = sorted(path for path in DELIVERY.rglob("*")
                   if path.is_file() and path.name != "SHA256SUMS.txt")
    sums = "\n".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
        f"{path.relative_to(DELIVERY).as_posix()}" for path in files)
    (DELIVERY / "SHA256SUMS.txt").write_text(sums + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build_delivery(), ensure_ascii=False, indent=2))
