---
name: localize-financial-analysis
description: แปลและ localize บทวิเคราะห์การเงินไปยัง locale เป้าหมายโดยคงข้อเท็จจริง ตัวเลข Claim ทิศทาง ความมั่นใจ เงื่อนไข และโครงสาระเดิมทั้งหมด ใช้เมื่อมีต้นฉบับบทวิเคราะห์ที่อนุมัติแล้วและ Locale Pack อยู่ในทะเบียน; ไม่ใช้เพื่อเขียนบทวิเคราะห์ใหม่ ค้นข้อมูล หรือสร้างมุมมองตลาด
---

# Localize Financial Analysis

ใช้กับ Agent 08 เมื่อได้รับบทวิเคราะห์ต้นทางที่ผ่านด่านสาระแล้ว งานนี้คือ
**translation + language localization** ไม่ใช่ analysis generation

> เปลี่ยนวิธีพูดให้เป็นธรรมชาติได้ แต่ห้ามเปลี่ยนสิ่งที่บทกำลังบอก

## ข้อมูลที่ต้องมี

- ต้นฉบับที่ระบุ `source_locale`, `source_sha256` และ contract version
- `target_locale` ที่มีใน `language/baseline-registry.json`
- Locale Pack เวอร์ชันที่ทะเบียนชี้
- Evidence/Claim map ที่ระบุ Protected Content

ขาดข้อใดให้หยุดด้วยสถานะที่อธิบายสาเหตุ ห้ามเดา ห้ามยืมกฎภาษาอื่น

## ทำได้

- แปลความหมายของประโยคและหัวข้อ
- เปลี่ยนลำดับคำ แบ่งหรือรวมประโยค และเลือกคำเชื่อมให้เป็นธรรมชาติ
- ใช้รูปวันที่ ตัวเลข เครื่องหมายวรรคตอน และ register ตาม Locale Pack
- เก็บชื่อสินทรัพย์ สัญลักษณ์ และศัพท์สากลตาม glossary

## ห้ามทำ

- เพิ่ม ตัด หรือสรุป Claim ใหม่
- ค้นข่าว ค้นราคา หรือเติมบริบทประเทศจากความรู้ของโมเดล
- เปลี่ยนตัวเลข หน่วย timeframe ทิศ แนวรับ/แนวต้าน หรือ indicator
- เปลี่ยนระดับ certainty, conditionality, causality หรือ scenario เป็นคำแนะนำ
- แปลคำต่อคำจนผิดธรรมชาติ หรือเขียนบทใหม่จากหัวข้อสั้น ๆ
- อนุมัติงานของ execution เดียวกัน หรือ publish

## ขั้นตอน

1. โหลด Locale Pack ด้วย `tools.locale_loader`; locale ไม่มีหรือยังไม่พร้อมให้ fail closed
2. ทำ Financial Meaning Map และผูกทุกย่อหน้ากับ Claim IDs ก่อนแปล
3. ป้องกันค่าที่ล็อกด้วย Protected tokens แล้วแปลเฉพาะชั้นภาษา
4. เปรียบเทียบ source/target ทีละ Claim: subject, value, direction, timeframe, certainty,
   condition และ causal status ต้องเท่ากัน
5. รัน mechanical guards ก่อนส่งให้ Language Reviewer คนละ execution
6. Agent 05 ตรวจบทฉบับรวมหลัง Country Overlay อีกครั้ง

Locale Pack สถานะ `draft`, `calibrating` หรือ `candidate` ใช้ได้เฉพาะ calibration/dry-run
และต้องรวมข้อเสนอเป็นชุดเดียวต่อวัน External Publish ต้องเป็นศูนย์จนผ่าน approval gate

## ผลลัพธ์ขั้นต่ำ

- localized article
- source/target locale และ pack version/hash
- Claim parity report
- Protected Content diff ซึ่งต้องเป็นศูนย์
- finding/retry status; เกิน 2 รอบให้ `HOLD` ไม่วนต่อ

