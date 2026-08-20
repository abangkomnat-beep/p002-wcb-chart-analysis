---
name: direct-p002-market-visuals
description: กำกับ สร้าง หรือแก้ภาพตลาดของ P002 เมื่อคุณภาพด้าน art direction, composition, typography และ visual hierarchy สำคัญ โดยรักษาข้อมูลการเงินจาก evidence และส่งเฉพาะ preview เข้าด่านตรวจ
---

# Direct P002 Market Visuals

สร้างภาพที่สวย อ่านง่าย และตรงกับ visual reference โดยไม่เปลี่ยนสารหรือข้อเท็จจริงของ P002

ก่อนทำงาน อ่าน [Identity ของ Agent 10](references/identity.md)
ซึ่งเป็นส่วนหนึ่งของ project skill ภายใน Repo นี้

## สิ่งที่ต้องมี

รับ brief ที่อนุมัติ, source image/data, visual reference และ evidence จาก Lead/Builder แยก
reference ที่ใช้ดูสไตล์ออกจาก source ที่ใช้ยืนยันข้อเท็จจริง หากขาดข้อมูลที่มีผลต่อราคา ระดับ
indicator เหตุการณ์ วันที่ เวลา timeframe จำนวนแท่ง cutoff หรือข้อความ ให้หยุดและคืนงาน

อ่าน [factual guardrails](references/factual-guardrails.md) ทุกงานภาพตลาด และอ่าน
[visual rubric](references/visual-rubric.md) ก่อน self-review หรือเตรียมส่ง QQ

## วิธีทำงาน

1. ระบุสารหลัก ลำดับสายตา grid, typography, semantic colors, protected factual layer และพื้นที่ที่แก้ได้
2. ใช้เครื่องมือสร้าง/แก้ภาพที่มีอยู่เพื่อทำ art direction, composition หรือ decorative treatment โดยไม่ให้เครื่องมือ generative เปลี่ยน factual layer
3. ให้ราคา แท่งเทียน เส้น indicator ระดับ วันที่ เวลา เหตุการณ์ ทิศทาง และข้อความ factual มาจาก evidence/renderer เดิม แล้วประกอบกลับแบบ deterministic
4. ตรวจงานทั้งขนาดจริงและ preview ย่อ แก้ spacing, overlap, contrast, Thai typography, crop และ artifact
5. export ผ่านมาตรฐาน `tools/image_output.py` และส่งเป็น preview พร้อมรายการสิ่งที่เปลี่ยน สิ่งที่คงไว้ แหล่ง evidence และ route ที่ใช้

## ขอบเขต

- เขียนเฉพาะพื้นที่งานหรือ Preview ที่ Lead อนุญาต ห้ามเขียนทับ production `output` หรือ publish
- ห้ามคำนวณหรือแต่งข้อมูลตลาด ห้ามแก้ renderer/data logic และห้ามตีความเงื่อนไขสมมุติเป็นคำทำนาย
- Agent 10 self-review ได้แต่อนุมัติงานตัวเองไม่ได้ สายส่งต่อคือ **Tester → QQ → CC/ผู้ใช้ → Release**
- ใช้ relative paths ภายใน P002/Repo ห้ามพึ่ง absolute path, secret, provider หรือ model ID

## Fallback

ถ้าไม่มี image capability ให้ใช้ approved reference, renderer, `tools/image_output.py` และ font
ใน Repo จัดองค์ประกอบแบบ reference-driven โดยคง factual layer เดิม หากยังไม่ถึง rubric ให้หยุด
และรายงาน `BLOCKED_VISUAL_CAPABILITY`; ห้ามลดเกณฑ์หรือเพิ่มบริการเสียเงินเอง
