---
name: audit-localized-financial-fidelity
description: ตรวจความตรงกันของบทวิเคราะห์ต้นฉบับและฉบับแปลตาม Claim, ตัวเลข, ทิศทาง, เงื่อนไข และระดับความมั่นใจ โดยไม่เขียนหรืออนุมัติบทเอง
---

# Audit Localized Financial Fidelity

ใช้โดย Agent 05 หรือ reviewer คนละ execution กับผู้แปลเท่านั้น

## วิธีทำงาน

1. อ่าน source และ target bytes ตาม hash ใน job; hash ไม่ตรงให้ `HOLD`
2. อ่าน Claim map จาก source และตรวจทุก Claim ID ใน target alignment
3. ตรวจตัวเลข หน่วย สัญลักษณ์ timeframe บทบาท support/resistance ทิศทาง negation certainty และ conditionality
4. ตรวจภาพที่ส่งจริงเมื่อ job ระบุ image hash; ภาพหายหรือยังมีข้อความภาษาไทยที่ไม่อยู่ใน allowlist ให้ `HOLD`
5. บันทึก `reviewer_execution_id` ที่ต่างจาก writer และออก receipt ผูก source/target/pack/claim hashes

## กติกา

- ห้ามค้นราคา ข่าว หรือเติมบริบทประเทศ
- ห้ามแก้บทแล้วออก PASS ให้ฉบับที่ตนแก้เอง
- ตัวเลขรูปแบบต่างกันตาม locale ได้เมื่อ canonical value เท่ากันและมีหลักฐานจากเครื่องมือตรวจ
- `Critical` หรือ `Major` ค้างอย่างใดอย่างหนึ่ง = `FAIL`; ขาดข้อมูลตรวจ = `HOLD`
- AI reviewer ต้องระบุเป็น AI reviewer ไม่อ้าง native-human approval

## ผลลัพธ์ขั้นต่ำ

```json
{
  "gate": "semantic",
  "verdict": "PASS|FAIL|HOLD",
  "reviewer_execution_id": "...",
  "source_sha256": "...",
  "target_sha256": "...",
  "findings": []
}
```
