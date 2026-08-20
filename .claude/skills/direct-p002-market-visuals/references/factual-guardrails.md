---
title: Factual Guardrails — P002 Market Visuals
description: กฎคุ้มครองข้อเท็จจริงสำหรับภาพตลาดที่ Agent 10 สร้างหรือแก้
tags:
  - P002
  - visual
  - factual-safety
---

# Factual guardrails

## ลำดับอำนาจ

Evidence และ brief ที่อนุมัติ > factual layer จาก renderer > visual reference > รสนิยม

ภาพอ้างอิงใช้ยืม visual language ได้ แต่ห้ามยืมราคา ระดับ วันที่ เหตุการณ์ หรือข้อสรุปข้ามรอบ

## Protected by default

- สินทรัพย์ timeframe จำนวนแท่ง cutoff และ timezone
- candlestick, axes, price labels, levels, zones และ Fibonacci
- MA, RSI, MACD และ indicator ทุกชนิด
- วันที่ เวลา เหตุการณ์ ระดับความสำคัญ ความเกี่ยวข้อง และทิศทางต่อสินทรัพย์
- ข้อความที่มีตัวเลข ที่มา เงื่อนไข หรือ claim เกี่ยวกับตลาด

เครื่องมือ generative ห้ามวาด แทนที่ หรืออ่านข้อความเหล่านี้แล้วสร้างกลับเอง ให้ Builder/renderer
ส่ง factual layer ที่ล็อกแล้ว และวางข้อความ approved แบบ deterministic หลังงาน art direction

## Required checks

1. source/evidence ต้องเป็นรอบเดียวกับ job และตรวจย้อนกลับได้
2. บันทึกว่าปรับส่วนใด คงส่วนใด และใช้ reference ใดเพื่อสไตล์เท่านั้น
3. ข้อความ exact ต้องคัดจาก brief/evidence ไม่พิมพ์ใหม่จากความจำ
4. source ต้องไม่ถูกเขียนทับ; preview ต้องอยู่เฉพาะพื้นที่ที่ Lead อนุญาต
5. factual mismatch แม้หนึ่งจุดให้ตกทั้งภาพ ความสวยชดเชยไม่ได้
6. ลูกศร สี และคำกำกับต้องไม่ทำเงื่อนไขสมมุติให้ดูเป็นคำทำนายหรือคำรับรองผล

หยุดเมื่อ evidence ไม่ครบ, source คนละรอบ, brief ขัดกัน, ต้องสร้าง facts ใหม่ หรือจำเป็นต้องแก้
protected layer โดยไม่มี Builder รองรับ ส่งปัญหากลับ Lead/CC แทนการเดา
