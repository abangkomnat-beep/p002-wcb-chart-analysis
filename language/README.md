# Language Baseline — มาตรฐานภาษาที่กำกับด้วยเวอร์ชัน

ที่นี่เก็บ **"มาตรฐานภาษา" ไม่ใช่ "บทความตัวอย่าง"** — สิ่งที่ถูกล็อกคือกฎว่าจะพูดอย่างไร
ไม่ใช่ประโยคสำเร็จรูปให้คัดลอก (บทความที่ล็อกเป็นแม่แบบทำให้ทุกบทเสียงเหมือนกันและสไตล์ A–G หายไป)

## หลักเดียวที่ครอบทุกอย่าง

> เปลี่ยน "วิธีพูด" ได้ แต่ห้ามเปลี่ยน "สิ่งที่บทความกำลังบอก"

เนื้อหาแบ่งสองชั้น — **ชั้นสาระ** (ตัวเลข ระดับราคา ข้อสรุปเทคนิค ข่าว ทิศ ความมั่นใจ เงื่อนไข)
ห้ามภาษาแตะ · **ชั้นภาษา** (เรียงประโยค คำเชื่อม ความยาว คำซ้ำ ศัพท์ระบบ) แก้ได้

## ทำไมเป็น JSON ไม่ใช่ YAML

ข้อเสนอต้นทางเขียนตัวอย่างเป็น YAML แต่รีโปนี้**ไม่มี PyYAML และตั้งใจใช้ stdlib ล้วน**
(ดูหมายเหตุใน `requirements.txt`) ส่วน `config/` ทั้งโฟลเดอร์เป็น JSON อยู่แล้ว
การเพิ่ม dependency เพื่อรูปแบบไฟล์อย่างเดียวเป็นภาระของคนที่รับรีโปไปใช้โดยไม่ได้อะไรกลับมา
— **กลไกกำกับ (registry · version · hash · governance lock) เหมือนข้อเสนอทุกข้อ** ต่างแค่นามสกุลไฟล์

## โครง

```
language/
├── baseline-registry.json          ← ทะเบียนกลาง: locale ไหนใช้ version ไหน สถานะอะไร
├── core/
│   └── financial-editorial-core-v1.json   ← กฎที่ไม่ผูกภาษา (ใช้ร่วมทุก locale)
└── locales/
    └── th-TH/
        ├── baseline.json           ← กฎหลักของภาษานี้ + reader profile
        ├── glossary.json           ← ศัพท์กลาง (preferred / allowed / avoid)
        ├── preferred-phrases.json  ← รูปประโยคที่ผู้ใช้อนุมัติแล้ว (เป็น pattern ไม่ใช่ประโยคคัดลอก)
        ├── avoid-phrases.json      ← คำที่เลี่ยง + เหตุผล (อ้างโยง VOICE_DENYLIST ไม่คัดลอกซ้ำ)
        ├── sentence-patterns.json  ← เกณฑ์เชิงโครงสร้าง (ความยาว คำเชื่อม)
        ├── approved-examples.md    ← Before → After ที่ผู้ใช้อนุมัติ (copy_allowed: false)
        ├── rejected-examples.md    ← ข้อเสนอที่ผู้ใช้ปฏิเสธ พร้อมเหตุผล
        ├── regression-cases.json   ← เคสที่ต้องผ่านทุกครั้งที่แก้กฎ
        └── CHANGELOG.md
```

## แหล่งความจริงเมื่อขัดกัน

1. **`tools/voice_rules.py` (`VOICE_DENYLIST`) คือทะเบียนคำต้องห้ามตัวจริง** — `avoid-phrases.json`
   **อ้างโยง** ไม่คัดลอกซ้ำ มีเทสบังคับว่าห้ามซ้ำกัน สองที่ขัดกันเมื่อไหร่ = บั๊ก แก้ที่ `voice_rules`
2. โค้ดชนะเอกสารเสมอ (กติกาเดิมของ P002)
3. registry ชี้ version ไหน ใช้ version นั้น — **ห้ามเลือก "ล่าสุด" จากชื่อไฟล์เอง**

## วงจรชีวิตและ governance lock

```
draft → calibrating → candidate → stable_locked → (patch_candidate) → deprecated
```

`stable_locked` **ไม่ได้แปลว่าไฟล์ read-only** แต่แปลว่า:

> Agent ใช้ได้ · ตรวจได้ · อ้างอิงได้ · **เสนอให้เปลี่ยนได้** — แต่แก้ baseline ตัวจริงเองไม่ได้

การเปลี่ยนกฎที่ล็อกแล้วต้องผ่าน `BASELINE_CHANGE_PROPOSAL` → ผู้ใช้อนุมัติ → regression ผ่าน → bump version
`tools/baseline_registry.py` บังคับข้อนี้เชิงกล (`BaselineLockedError`) ไม่ได้อาศัยวินัยอย่างเดียว

## จังหวะถามผู้ใช้ (มติผู้ใช้ 2026-08-13)

ช่วง calibrating ระบบ **รวมข้อเสนอทุกบทของวันเป็นชุดเดียว ถามครั้งเดียวต่อวัน**
ในชุดตอบรายข้อได้ (อนุมัติทั้งหมด / ยกเว้นบางข้อ / ปฏิเสธทั้งหมด) — **ห้ามถามทีละข้อ**
วันที่ไม่มีคำตอบ บทเดินต่อแบบไม่แก้ภาษา **ห้าม block การผลิต**

## เครื่องมือ

| เครื่องมือ | หน้าที่ |
|---|---|
| `tools/baseline_registry.py` | อ่าน registry · แก้ hash ตามจริง · บังคับ governance lock · promote version |
| `tools/locale_loader.py` | โหลด locale pack ที่ registry ชี้ · ไม่มี = `LOCALE_BASELINE_MISSING` |
| `tools/language_review.py` | ตรวจเชิงกลก่อนถึง LLM → `review.json` · รวมเป็นชุดต่อวัน |
| `tools/language_patch.py` | apply เฉพาะข้อที่อนุมัติแบบ surgical · ตรวจ 2 hash · ด่าน integrity |
