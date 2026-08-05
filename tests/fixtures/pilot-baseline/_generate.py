"""สร้างชุด fixture สังเคราะห์ให้ tests/test_pilot_outputs.py

ทำไมต้องสังเคราะห์ ไม่ใช้ผลผลิตจริง
--------------------------------------
ชุด baseline เดิมเป็นบทความจริงของวันที่ 2026-08-03 ที่วางอยู่ใน OUTPUT/ ซึ่งอยู่
นอก git จึงไม่มีประวัติกู้คืน และหายไปทั้งชุดเมื่อ 2026-08-04 โดยไม่มีใครรู้ตัว

เอาผลผลิตจริงมาเก็บในรีโปแทนก็ไม่ได้ เพราะรีโปนี้มีไว้ส่งมอบสู่ภายนอก แต่บทความ
กับ snapshot มีราคาจาก Raw Trading ที่สัญญาไม่ให้สิทธิ์เผยแพร่ (ข้อ 28.7 / 10.19)
และ git ลบย้อนหลังไม่ได้จริง ใส่ไปครั้งเดียวติดอยู่ในประวัติตลอด

เทสชุดนี้ตรวจ "รูปแบบ" ไม่ได้ตรวจว่าราคาตรงตลาด (ดูรายการ assert ในไฟล์เทส)
ตัวเลขสังเคราะห์จึงพอสำหรับสิ่งที่มันตรวจ และไม่พาข้อมูลติดสิทธิ์เข้ารีโป

ตัวเลขทุกตัวในไฟล์นี้เป็นเลขกลม ๆ ที่ไม่ใช่ราคาจริง (EUR/USD 1.2000 · BTC 50000 ·
XAU 2000) เพื่อให้ดูออกทันทีว่าไม่ใช่ข้อมูลตลาด

รันใหม่เมื่อไหร่: เมื่อ contract ของบทความเปลี่ยน แล้วเทสเรียกหาหัวข้อ/ช่องใหม่
    python tests/fixtures/pilot-baseline/_generate.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent

BASES = (
    "2026-08-03_forex-eurusd",
    "2026-08-03_crypto-btcusd",
    "2026-08-03_xauusd",
)
COMPARISON_BASES = (
    "2026-08-03_rrvv-forex-eurusd",
    "2026-08-03_rrvv-crypto-btcusd",
    "2026-08-03_rrvv-xauusd",
)

# ราคาสังเคราะห์ เลขกลมจงใจ ไม่ใช่ราคาตลาดจริง
SYNTHETIC = {
    "2026-08-03_forex-eurusd": {"label": "EUR/USD", "base": 1.2000, "step": 0.0010, "digits": 4},
    "2026-08-03_crypto-btcusd": {"label": "BTC/USD", "base": 50000.0, "step": 250.0, "digits": 2},
    "2026-08-03_xauusd": {"label": "XAU/USD", "base": 2000.0, "step": 5.0, "digits": 2},
}

IMAGE_SIZE = (1440, 1080)  # เทสตรวจขนาดนี้ตรง ๆ กับไฟล์ระดับบนสุด


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with Image.new("RGB", IMAGE_SIZE, (245, 245, 242)) as image:
        image.save(path, format="PNG")


def candles(base: str) -> list[dict]:
    """แท่งเทียนสังเคราะห์ที่สอดคล้องกันเอง low <= min(open, close) และ high >= max(open, close)"""
    spec = SYNTHETIC[base]
    rows = []
    for index in range(30):
        open_ = spec["base"] + spec["step"] * index
        close = open_ + spec["step"] * (1 if index % 2 == 0 else -1)
        rows.append(
            {
                "date": f"2026-07-{(index % 28) + 1:02d}",
                "open": round(open_, spec["digits"]),
                "high": round(max(open_, close) + spec["step"], spec["digits"]),
                "low": round(min(open_, close) - spec["step"], spec["digits"]),
                "close": round(close, spec["digits"]),
            }
        )
    return rows


def flat_article(base: str) -> str:
    """บทความระดับบนสุด: ต้องมี '\\n## ' พอดี 3 ครั้ง และมีค่า frontmatter 3 ตัวที่เทสตรวจ"""
    label = SYNTHETIC[base]["label"]
    return f"""---
title: ตัวอย่างสังเคราะห์ {label}
byline: natthaphon-s
status: pilot-not-for-publication
publication_clearance: hold-data-license-review
fixture: synthetic
---

ไฟล์นี้เป็นตัวอย่างสังเคราะห์สำหรับชุดทดสอบ ตัวเลขทุกตัวเป็นเลขสมมติ ไม่ใช่ราคาตลาดจริง
และไม่ควรนำไปใช้อ้างอิงในงานใด

## ภาพรวมราคา

ในรอบทดสอบนี้ {label} เคลื่อนไหวในกรอบแคบตามชุดข้อมูลสมมติที่สร้างขึ้น
ค่าที่ใช้ทั้งหมดมาจากสูตรคงที่ในไฟล์ตัวสร้าง จึงให้ผลเหมือนเดิมทุกครั้งที่รันใหม่

![กราฟตัวอย่าง]({base}.png)

## สิ่งที่โครงสร้างข้อมูลบอก

ชุดแท่งเทียนถูกสร้างให้สอดคล้องกันเองเสมอ คือค่าต่ำสุดไม่เกินราคาเปิดและราคาปิด
ส่วนค่าสูงสุดไม่ต่ำกว่าทั้งสองค่า เพื่อให้ตัวตรวจความสมเหตุสมผลของแท่งเทียนทำงานได้จริง

## ข้อจำกัดของไฟล์ตัวอย่าง

ไฟล์นี้ตรวจได้เฉพาะรูปแบบและโครงสร้าง ไม่ได้ยืนยันว่าสายท่อคำนวณตัวเลขถูกต้อง
การตรวจส่วนนั้นอยู่ในชุดทดสอบอื่นที่เรียกฟังก์ชันของสายท่อโดยตรง
"""


def contract_v2_article(base: str) -> str:
    """บทความ contract v2: หัวข้อ 9 อันครบและเรียงตามลำดับที่เทสกำหนด อันละครั้งเดียว"""
    label = SYNTHETIC[base]["label"]
    return f"""---
title: ตัวอย่างสังเคราะห์ contract v2 {label}
byline: natthaphon-s
status: pilot-not-for-publication
publication_clearance: hold-data-license-review
fixture: synthetic
---

## Market Snapshot

ชุดตัวเลขสมมติของ {label} สำหรับทดสอบรูปแบบเอกสารเท่านั้น ไม่ใช่ข้อมูลตลาดจริง

## สรุปตลาด

ราคาสมมติเคลื่อนไหวในกรอบตามสูตรคงที่ ไม่มีการอ้างอิงเหตุการณ์จริงใด

## ปัจจัยพื้นฐาน

ส่วนนี้เว้นไว้เป็นโครงสำหรับตรวจว่าหัวข้อครบและเรียงถูกลำดับ

## วิเคราะห์ทางเทคนิค

โครงสร้างราคาสมมติถูกสร้างให้อ่านได้เป็นกรอบแคบ เพื่อให้เนื้อหาสอดคล้องกับตัวเลข

## ระดับตัดสินใจ

Bias: กลาง
Trigger: ราคายืนเหนือกรอบบนของชุดข้อมูลสมมติ
Target: ขอบบนของกรอบสมมติถัดไป
Invalidation: ราคาหลุดขอบล่างของกรอบสมมติ
No-trade: ระหว่างที่ราคายังอยู่กลางกรอบและยังไม่มีสัญญาณ

## แนวคิดการซื้อขาย

ไฟล์ตัวอย่างไม่ให้คำแนะนำการลงทุน ข้อความส่วนนี้มีไว้ให้ตัวตรวจรูปแบบทำงานเท่านั้น

## ข่าวและสิ่งที่ต้องติดตาม

ยังไม่มีข่าวอัปเดตในชุดตัวอย่างสังเคราะห์

## ภาพและลิงก์ประกอบ

![กราฟตัวอย่าง]({base}.png)

## คำเตือนความเสี่ยง

เนื้อหาทั้งหมดเป็นข้อมูลสมมติเพื่อการทดสอบระบบ ไม่ใช่คำแนะนำการลงทุน
"""


def comparison_article(base: str) -> str:
    """บทความชุดเปรียบเทียบ: ต้องมีป้ายตัวหนา 5 ตัว และเนื้อข่าวสั้นไม่เกิน 20 คำ"""
    return f"""---
title: ตัวอย่างสังเคราะห์ชุดเปรียบเทียบ
byline: natthaphon-s
comparison_group: B-rrvv
fixture: synthetic
---

## กราฟบอกอะไร

ชุดข้อมูลสมมติสำหรับทดสอบรูปแบบเอกสาร ไม่ใช่ข้อมูลตลาดจริง

![กราฟตัวอย่าง]({base}.png)

## แผนขึ้น แผนลง และแผนพัก

**Bias:** กลาง
**Action:** รอสัญญาณ
**Trigger:** ราคายืนเหนือกรอบบนของชุดข้อมูลสมมติ
**Invalidation:** ราคาหลุดขอบล่างของกรอบสมมติ
**Next event:** ไม่มีในชุดตัวอย่าง

## ข่าวและสิ่งที่ต้องติดตาม

ยังไม่มีข่าวอัปเดต

## กรอบตัดสินใจวันนี้

ไฟล์ตัวอย่างไม่ให้คำแนะนำการลงทุน มีไว้ให้ตัวตรวจรูปแบบทำงานเท่านั้น
"""


def source_log(base: str) -> dict:
    spec = SYNTHETIC[base]
    return {
        "asset": base,
        "note": "ค่าสังเคราะห์เพื่อทดสอบรูปแบบ ไม่ใช่ข้อมูลตลาดจริง",
        "entries": [
            {"field": "quote.last", "value": spec["base"], "published_at": "2026-08-03T00:00:00+00:00"},
            {"field": "quote.change", "value": spec["step"], "published_at": "2026-08-03T00:00:00+00:00"},
            {"field": "quote.percent", "value": 0.25, "published_at": "2026-08-03T00:00:00+00:00"},
        ],
    }


def main() -> None:
    for base in BASES:
        write(HERE / f"{base}.md", flat_article(base))
        write_png(HERE / f"{base}.png")
        write_json(
            HERE / f"{base}.snapshot.json",
            {
                "asset": base,
                "note": "แท่งเทียนสังเคราะห์ ไม่ใช่ข้อมูลตลาดจริง",
                "rows": candles(base),
            },
        )

    contract_dir = HERE / "contract-v2-pilot"
    for base in BASES:
        write(contract_dir / f"{base}.md", contract_v2_article(base))
        write_png(contract_dir / f"{base}.png")
        write_json(contract_dir / f"{base}.snapshot.json", {"asset": base, "rows": candles(base)})
        write_json(contract_dir / f"{base}.chart.json", {"asset": base, "series": "synthetic"})
        write_json(contract_dir / f"{base}.article-data.json", {"asset": base, "sections": 9})
        write_json(contract_dir / f"{base}.source-log.json", source_log(base))
        # เทสตรวจแค่ช่วง 450-650 ค่าที่ใส่จึงเป็นค่าสมมติในกรอบนั้น ไม่ได้นับจากบทความจริง
        write_json(contract_dir / f"{base}.meta.json", {"asset": base, "word_count": 520, "fixture": True})

    comparison_dir = HERE / "comparison-v2-rrvv"
    for base in COMPARISON_BASES:
        write(comparison_dir / f"{base}.md", comparison_article(base))
        write_png(comparison_dir / f"{base}.png")

    print(f"สร้าง fixture เสร็จที่ {HERE}")


if __name__ == "__main__":
    main()
