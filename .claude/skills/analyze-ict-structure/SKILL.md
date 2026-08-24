---
name: analyze-ict-structure
description: ใช้เมื่อ P002 ต้องวิเคราะห์ ออกแบบ หรือตรวจหลักฐานตามแนว ICT/SMC จาก OHLC ที่ปิดแล้ว เช่น market structure, BOS/CHoCH/MSS, FVG, Order Block, liquidity sweep และ premium/discount; ไม่ใช้แทน risk gate หรือเป็นสัญญาณซื้อขายอัตโนมัติ
---

# Analyze ICT Structure

คุณคือกรอบวิเคราะห์หลักฐาน ICT/SMC ของ P002 เป้าหมายคือเปลี่ยนคำศัพท์ให้เป็นเหตุการณ์ที่ตรวจซ้ำได้ ไม่ใช่เพิ่มความมั่นใจจากชื่อแนวคิด

ก่อนวิเคราะห์ให้อ่าน [references/ict-contract.md](references/ict-contract.md) ทุกครั้ง เมื่อต้องแก้สูตร ติดตั้ง dependency หรืออ้างโค้ดภายนอก ให้อ่าน [references/source-audit.md](references/source-audit.md) เพิ่ม

## ข้อมูลเข้า

- ใช้ snapshot เดียวกับงาน P002 และเฉพาะแท่งที่ปิดแล้ว
- ต้องมี asset, timeframe, cutoff, timezone/session, OHLC และ source hash
- Volume ใช้ได้เมื่อมี provenance และนิยามชัดเท่านั้น; ไม่มีให้ระบุ `unavailable`
- ห้ามดึงราคาใหม่ ห้ามผสม snapshot และห้ามสร้าง timeframe ที่ input ไม่มี

## ขั้นตอน

1. ยืนยันลำดับเวลาและตัดแท่ง forming ออกก่อนคำนวณ
2. หา swing แบบ causal: pivot จะเป็น `confirmed` เมื่อแท่งด้านขวาครบเท่านั้น บันทึกทั้ง `pivot_at` และ `confirmed_at`
3. จำแนก structure จากราคาปิดที่ผ่าน swing ยืนยันแล้ว: BOS = ต่อทิศเดิม, CHoCH = break แรกสวนทิศเดิม; wick อย่างเดียวไม่ใช่ structure break
4. ตรวจ liquidity: pool ต้องมีเกณฑ์ equal-high/low ที่ประกาศไว้; sweep ต้องแทงผ่านระดับยืนยันแล้วและปิดกลับด้านเดิม
5. ตรวจ FVG จากแท่งปิดสามแท่ง; รู้ผลได้หลังแท่งที่สามปิด บันทึก creation, mitigation และ fill ตาม cutoff
6. ตรวจ Order Block เฉพาะแท่งตรงข้ามก่อน displacement ที่นำไปสู่ structure break ยืนยันแล้ว; แท่งตรงข้ามทั่วไปเป็นเพียง candidate
7. ใช้ premium/discount เมื่อ dealing range มี anchor ที่ตรวจได้เท่านั้น; midpoint 50% เป็น context ไม่ใช่ entry trigger
8. รวมหลักฐานโดยแยก `confirmed`, `candidate`, `invalidated`, `mitigated` และ `unavailable`; ความขัดแย้งต้องคงอยู่ในผลลัพธ์
9. ส่งต่อ Agent 06 เฉพาะระดับที่ผ่าน provenance/approval เดิมของ P002; หลักฐานไม่ครบให้ `no_trade`

## การแบ่งหน้าที่

- Agent 01: เป็นเจ้าของ swing, trend state, BOS/CHoCH/MSS และ structural invalidation
- Agent 03: เป็นเจ้าของ liquidity pool/sweep, FVG, OB, dealing range และสถานะ zone
- Agent 06: อ่านผลยืนยันเพื่อประกอบ confluence; ห้ามตรวจ ICT ซ้ำหรือสร้างระดับใหม่
- Agent 07: audit causal timing, provenance, invalidation, RR และ look-ahead; มีสิทธิ์ block
- Agent เขียนบท/ภาพ: ใช้เฉพาะ artifact ที่ผ่าน gate ห้ามเปลี่ยน candidate เป็นข้อเท็จจริง

## ผลลัพธ์ขั้นต่ำ

ส่ง artifact ที่มี `contract_version`, `asset`, `timeframe`, `cutoff_at`, `source_hash`, `assumptions`, `swings`, `structure_events`, `liquidity`, `fvg`, `order_blocks`, `dealing_range`, `confluence`, `conflicts`, `unavailable_checks`, `invalidation` และ `classification`

ทุก event/zone ต้องมี `observed_at`, `confirmed_at`, `source_indices`, `status` และเหตุผล หากยังพิสูจน์เวลา confirmation ไม่ได้ให้เป็น `candidate` หรือ `unavailable`

## กฎ

- ห้ามใช้แท่งอนาคตโดยไม่เลื่อน `confirmed_at`; ผล prefix ณ cutoff ต้องไม่เปลี่ยนเมื่อเติมข้อมูลอนาคต
- ห้ามเรียกทุก gap ว่า FVG ทุกแท่งสวนว่า OB หรือทุก wick ว่า liquidity sweep
- ห้ามใช้คำว่า “institutional order” เป็นข้อเท็จจริงจาก OHLC; รายงานว่าเป็นกรอบจำแนก ICT/SMC
- ห้ามลด threshold เดิม ติดตั้ง package/MCP แก้ production หรือ publish จากการใช้สกิลนี้
- ไม่มี backtest/forward test ห้ามอ้าง win rate, edge หรือความแม่นยำ
- ผล ICT เป็นหลักฐานเสริม; contract, level approval และ risk gate เดิมของ P002 มีอำนาจสูงกว่า
