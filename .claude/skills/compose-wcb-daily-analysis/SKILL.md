---
name: compose-wcb-daily-analysis
description: ประกอบและตรวจบทวิเคราะห์สินทรัพย์รายวันของโครงการ P002 จาก snapshot, Technical Sets, ข่าว และ chart spec ให้เป็นบทความภาษาไทยแบบตัวเลขนำ อธิบายกลไก แยกแนวโน้มกับจังหวะเข้า และมี Trigger, Target, Invalidation, No-trade และความเสี่ยง ใช้เมื่อร่าง แก้ หรือ QA Output สำหรับ XAU/USD, Forex และ Crypto ตาม WCB Daily Output Contract v2
---

# Compose WCB Daily Analysis

อ่าน [references/output-contract.md](references/output-contract.md) แล้วใช้เอกสาร canonical ที่ระบุในนั้น

## ลำดับทำงาน

1. ล็อก `instrument_type`, cutoff, timezone, data status, unit และ source field ก่อนเขียน
2. แยก facts, interpretations และ scenarios ห้ามเติมค่าที่ source ไม่มี
3. เลือก market state: continuation, range/wait, breakdown, event-risk หรือ cross-market divergence
4. เขียนพาดหัวด้วย ราคา/สถานะ + driver ไม่เกิน 2 เรื่อง + จุดที่ต้องจับตา
5. เขียน Lead 2–4 ประโยคให้ตอบ เกิดอะไร → เพราะอะไร → มองอย่างไร → จุดตัดสินอยู่ไหน
6. ใส่ section ตาม contract; field เฉพาะสินทรัพย์ให้แสดงเมื่อมีข้อมูลที่ตรวจสอบได้เท่านั้น
7. แยก Daily/H4 trend ออกจาก H1/M15 trigger และรายงาน conflict ของ Technical Sets
8. ทำทุก Trade Idea เป็นเงื่อนไขที่มี Trigger, Target, Invalidation และ No-trade ห้ามใช้คำสั่งซื้อขายแบบรับรองผล
9. ข่าวไม่มีใหม่ใช้หนึ่งประโยคมาตรฐาน ข่าวมีใหม่ใช้ ข่าว → กลไก → ผลต่อสินทรัพย์ → สิ่งที่เฝ้าระวัง
10. ปิดท้ายด้วย visual plan, timestamp, alt/caption และ risk warning เฉพาะภาวะตลาด

## หัวข้อฉบับเผยแพร่

ใช้หัวข้อต่อไปนี้แยกกันและเรียงตามลำดับ ห้ามรวมหัวข้อแม้เนื้อหาสั้น:

1. `## Market Snapshot`
2. `## สรุปตลาด`
3. `## ปัจจัยพื้นฐาน`
4. `## วิเคราะห์ทางเทคนิค`
5. `## ระดับตัดสินใจ`
6. `## แนวคิดการซื้อขาย`
7. `## ข่าวและสิ่งที่ต้องติดตาม`
8. `## ภาพและลิงก์ประกอบ`
9. `## คำเตือนความเสี่ยง`

หาก input gate ขาด `instrument_type`, cutoff, timezone, data status, unit หรือ source log ให้สร้างได้เฉพาะ internal draft ที่ติด `qa_status: BLOCK` และแจกแจง missing fields ห้ามระบุพร้อมเผยแพร่

## กฎรวมหลักฐาน

- เทคนิค A ของแต่ละ Set ถือ bias หลัก; B/C ยืนยัน ลดน้ำหนัก หรือเปิด conflict ไม่โหวตแบบเสียงข้างมาก
- ใช้ระดับเผยแพร่จาก source contract ที่อนุมัติ ห้ามสร้างราคาเป้าหมายจากสายตา
- ใช้ภาษาความน่าจะเป็น เช่น “ประเมิน”, “มีโอกาส”, “หาก”, “ตราบใดที่”
- จำกัด indicator 2–3 ตัวที่หน้าที่ไม่ซ้ำ และไม่เกิน 5 ตัวต่อบทความ
- ใช้ zone เมื่อ volatility สูงหรือ precision ของ source ไม่รองรับทศนิยมละเอียด
- ความยาว 450–650 คำเมื่อปัจจัยน้อย และ 700–1,200 คำเมื่อมีข่าว/กลไกสำคัญ
- ห้ามเลียนแบบถ้อยคำเฉพาะตัวของผู้เขียนต้นแบบ ใช้เฉพาะโครงสร้างและคุณลักษณะบรรณาธิการ

## ผลลัพธ์

ส่งอย่างน้อย:

- `article_draft.md`
- `article_data.json` ตาม `article-draft-v2.schema.json`
- `chart_spec.json`
- `source_log.json`
- `article_meta.json`

หาก field จำเป็นไม่มีหลักฐาน ให้ mark `unavailable` ในข้อมูลหลังบ้านและตัดข้อความอ้างค่านั้นออกจากบทความ ห้ามแทนด้วยการคำนวณหรือเดาเอง
