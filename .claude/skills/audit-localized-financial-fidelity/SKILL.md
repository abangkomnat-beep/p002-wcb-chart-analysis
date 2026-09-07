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
- pilot ZA คง protected literals ตามต้นฉบับ; ยังไม่รับการแปลงรูปตัวเลขหรือหน่วยโดยไม่มีตัวตรวจรองรับ
- `Critical` หรือ `Major` ค้างอย่างใดอย่างหนึ่ง = `FAIL`; ขาดข้อมูลตรวจ = `HOLD`
- AI reviewer ต้องระบุเป็น AI reviewer ไม่อ้าง native-human approval

## ผลลัพธ์ขั้นต่ำ

```json
{
  "receipt_id": "<unique-id>",
  "gate": "semantic",
  "article_id": "<job-article-id>",
  "verdict": "PASS|FAIL|HOLD",
  "reviewer_execution_id": "...",
  "reviewer_kind": "AI|human",
  "reviewed_at": "<ISO-8601 timestamp with timezone>",
  "source_sha256": "...",
  "target_sha256": "...",
  "pack_sha256": "...",
  "claim_map_sha256": "...",
  "findings": []
}
```

ใช้ค่า hash ของไฟล์ที่ตรวจจริง ส่ง receipt ให้ Lead รับเข้า `receipts/index.json`
แบบอ้างไฟล์+hash ตาม [คู่มือ ZA](../../../docs/ZA-LOCALIZATION-RUNBOOK.md)
receipt semantic ไม่ใช้แทนด่าน language/visual/package_input; ด่านภาพและแพ็กต้องเพิ่ม
`image_hashes` เป็น mapping ชื่อไฟล์ → target SHA-256 ของภาพทุกภาพที่ส่งจริง

## เมื่อต้นฉบับหรือชุดส่งมอบเปลี่ยน

- ตรวจ hash ของ source, target, image และ Locale Pack จากไฟล์ที่เปิดอ่านจริงทุกครั้ง
- hash ต้นฉบับเปลี่ยนหลัง receipt เดิม = receipt เดิมใช้ไม่ได้ (`STALE_SOURCE`), แม้
  ข้อความที่แก้ดูเป็นเพียง caption
- reviewer ตรวจ prepared tree และออก receipt ก่อน transaction เท่านั้น. ห้ามตรวจ
  public path ที่กำลังถูกสลับ หรือรับรองงานของ execution เดียวกับ Writer
- หากพบ journal ที่ไม่ `COMMITTED`, day marker/generation ไม่ตรง, หรือ reader ไม่ถือ
  lock ให้ `HOLD` และส่ง Lead ทำ recovery; ห้ามเลือกไฟล์จาก tree เก่ามาปะติดปะต่อ
