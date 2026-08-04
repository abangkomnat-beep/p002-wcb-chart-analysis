---
title: README
type: note
permalink: library/projects/p002-nakekhiiynbthwiekhraaah/repo/readme
---

# P002 WCB Chart Analysis

Private source repository สำหรับระบบนักเขียนบทวิเคราะห์ WorldClassBroker ที่ใช้กราฟเป็นหลัก รองรับ XAU/USD, Forex และ Crypto ในระยะแรก

## สถานะ

อยู่ในขั้น scaffolding และออกแบบ contracts ยังไม่พร้อมสร้างคำแนะนำหรือนำบทความไปเผยแพร่จริง

## ติดตั้งและรัน

```bash
pip install -r requirements.txt          # ต้องใช้เฉพาะตอนเรนเดอร์กราฟ
python -m unittest discover -s tests     # เทสทั้งชุด
python -m tools.run_integrity_report --output-dir ../work/integrity-run   # ยิงด่านตรวจใส่ชุดข้อมูลที่มี
python -m tools.pilot_generator --asset eurusd --output-dir ../work/pilot  # สร้าง snapshot + กราฟ + ผลด่านตรวจ
```

ผลด่านตรวจอยู่ในไฟล์ `<basename>.integrity.json` อ่านที่ `publication_gate.status`
`pass` = ข้อมูลผ่านด่าน · `fail` = ห้ามนำไปเขียนบทความหรือเผยแพร่ พร้อมเหตุผลรายข้อใน `reasons`

## ชั้นตรวจสอบข้อมูล (Data Integrity)

| โมดูล | หน้าที่ |
|---|---|
| `tools/market_calendar.py` | ปฏิทินตลาดต่อชนิดสินทรัพย์ — crypto 24/7 · forex และ spot metal 24/5 พร้อมวันหยุด |
| `tools/candles.py` | ติดสถานะให้ทุกแท่ง (forming/closed, อยู่ในปฏิทินหรือไม่) และบันทึก anomaly แทนการลบทิ้ง |
| `tools/gap_detector.py` | ตรวจ session ที่หายตามปฏิทินของสินทรัพย์นั้น |
| `tools/indicators.py` | คำนวณ indicator เฉพาะเมื่อจำนวนแท่งที่ปิดแล้วถึงขั้นต่ำ — ไม่พอ = ไม่คำนวณ ไม่แสดง |
| `tools/pivots.py` | Classic Pivot จาก previous valid completed session พร้อมฐานการคำนวณครบ |
| `tools/publication_gate.py` | ด่านหยุดการเผยแพร่ ครอบคลุม fatal rule ข้อ 1-5 |
| `tools/integrity.py` | ร้อยทุกด่านเข้าด้วยกัน เรียกจุดเดียว |
| `tools/voice_rules.py` | กติกากลางตาม WCB Voice Spec v1 — กติกาปัดเลขต่อสินทรัพย์ · denylist คำ robot 20 คำ · เกณฑ์กริยาตาราง 2.6 · ตัวนับคำ deterministic · ตัวตรวจข้อความซ้ำ corpus |
| `tools/public_copy_validator.py` | ด่านตรวจบทความก่อนปล่อย — ศัพท์ระบบ · field ภายในใน frontmatter · timestamp เครื่องอ่าน · path ในเครื่อง · denylist Voice Spec · โครงสร้าง (ห้ามตาราง/หัวข้ออื่น) · เลขปัดต้อง map กลับ evidence · เพดานความยาว 350-560 คำ (v1.1) |
| `tools/article_builder.py` | ตัวประกอบบทความโครงเล่าเรื่อง 4 ช่วงตาม Voice Spec v1 (+ ส่วนขยาย v1.1) — สร้าง evidence pack (article.json) ก่อนแล้วค่อยเรนเดอร์ Markdown · ชั้น `narrative_context` คำนวณบริบทราคาย้อนหลัง/เส้นค่าเฉลี่ย/ความผันผวน/โครงสร้างระดับ ให้ย่อหน้าขยายเล่าได้โดยไม่ต้องคำนวณเอง |
| `tools/levels.py` | Level engine — previous day/week · swing · MA ที่ผ่านขั้นต่ำ · ATR projection · Pivot พร้อมรวมโซนและกติกา target |
| `tools/license_gate.py` | ด่านสิทธิ์ข้อมูล แยกจากด่านเนื้อหา — unknown = ห้ามเผยแพร่ |
| `tools/chart_renderer.py` | กราฟรุ่นใหม่ (matplotlib) 90 แท่ง · แท่งก่อตัวต่างจากแท่งปิด · ป้ายไม่ทับกัน · คำบรรยายเวลาไทย |

### กติกาที่ level engine บังคับ

- Pivot ไม่ใช่แหล่งระดับเดียวอีกต่อไป — ระดับทุกตัวต้องมี `source_field`, `calculation_method` และ `basis_timestamp`
- ระดับที่ชิดกันถูกรวมเป็นโซน และคุมความกว้างไม่ให้ต่อกันเป็นลูกโซ่จนกลายเป็นโซนกว้างเกินจริง
- `target` ต้องตรงกับระดับที่อนุมัติแล้ว — ข้อความลอยอย่าง `follow-through above R3` ไม่ผ่าน
- ไม่มี target หรือไม่มี invalidation → `watchlist` และ `executable=false`
- ไม่มีข้อมูล intraday → `daily_scenario` เท่านั้น ห้ามใช้ถ้อยคำแบบสั่งเข้าออเดอร์

### ด่านสิทธิ์ข้อมูล

`config/provider_license_registry.json` เก็บสิทธิ์ของแต่ละ provider ค่าเริ่มต้นเป็น `unknown` ทั้งหมด
ซึ่งแปลว่า **ห้ามเผยแพร่** จนกว่าจะมีคนอ่านสัญญาฉบับจริงแล้วมาแก้ไฟล์นี้พร้อมลงวันที่ตรวจ

สถานะที่เป็นไปได้: `hold-data-license-review` · `hold-data-quality` · `hold-content-qa` ·
`approved-internal-only` · `approved-for-publication`

ตรวจบทความก่อนส่ง QA:

```bash
python -m tools.public_copy_validator บทความ.md --evidence บทความ.article-data.json --json
```

ออกรหัส 1 เมื่อไม่ผ่าน — Agent 05 (Article QA) ต้องแนบผลรันนี้ทุกครั้ง ไม่มีผลรัน = ไม่ผ่าน

ค่าตั้งอยู่ที่ `config/market_calendar.json` และ `config/minimum_bars.json`

### วิธีนับคำของเพดาน 350-560 คำ (คำตัดสิน CC ข้อ 5 — 2026-08-03 · เพดานปรับเป็น v1.1 เมื่อ 2026-08-04)

เครื่องที่รันไม่มี PyThaiNLP และห้ามเพิ่ม dependency ใหม่ จึงใช้ตัวนับ deterministic ใน
`tools/voice_rules.py` (`count_public_words`) แทนตัวตัดคำจริง:

- token ละติน 1 ก้อน = 1 คำ · ตัวเลข 1 ก้อน (รวม `,` `.` `:` `%`) = 1 คำ
- อักษรไทยประมาณจากความยาวอักขระ ÷ 4.5 (ปัดครึ่งขึ้น)
- ไม่นับ frontmatter และบรรทัด markup ภาพ (`![`)

ค่า 4.5 สอบเทียบกับ reference corpus 4 ชิ้น (สเกล ~250-450 คำต่อชิ้น) และถูกล็อกด้วยเทส
`tests/test_voice_rules.py` — เปลี่ยนสูตรนับ = เปลี่ยนมาตรฐาน ต้องแจ้ง CC ก่อน

เพดานเดิม 250-450 คำถูกยกเป็น **350-560 คำ** ตามคำสั่งผู้ใช้ 2026-08-04 ("ต้องขยายความ
เนื้อหาให้มากกว่านี้") — ต่ำกว่า 350 คำถือว่าเนื้อหาน้อยเกินไปและด่านตีตกเอง

## ข้อจำกัดที่ต้องรู้

- **ใช้แหล่งข้อมูลเดียว** — ยังไม่มี cross-provider verification (fatal rule ข้อ 6) ตามการตัดสินของผู้ใช้ 2026-08-03 ตัวเลขจึงยืนยันได้เท่าที่ provider เดียวรายงาน
- **สิทธิ์เผยแพร่ข้อมูลยังไม่เคลียร์** — ทุก output ถือเป็น internal จนกว่าจะตรวจสิทธิ์ Yahoo Finance / Twelve Data เสร็จ
- ยังไม่มี H4/H1/M15 จึงเขียนได้เฉพาะมุมมองระดับ Daily
- XAU/USD ยังรับข้อมูลผ่าน snapshot ที่ป้อนมือ ไม่ได้ดึงเอง

## Architecture

`Market Snapshot → Technical 3 Sets + News Impact → Chart Editor → Chart/Article → Article QA → User Approval → Publish/Verify`

- Technical Set 1: Trend & Market Structure
- Technical Set 2: Momentum & Volatility
- Technical Set 3: Price Levels & Reaction
- WCB Article QA: ด่านตรวจอิสระแบบ fail-closed

ดู [Agent and skill matrix](docs/AGENT-SKILL-MATRIX.md), [governance](GOVERNANCE.md) และ [delivery checklist](DELIVERY-CHECKLIST.md)

## Security

ห้าม commit API keys, market-data credentials, unpublished articles หรือข้อมูลลูกค้า ใช้ `.env.example` เท่านั้น