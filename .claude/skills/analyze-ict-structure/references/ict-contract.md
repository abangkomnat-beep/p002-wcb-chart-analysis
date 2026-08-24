# P002 ICT Evidence Contract v0.1

เอกสารนี้ล็อกความหมายเชิงปฏิบัติสำหรับ P002 เพราะคำศัพท์ ICT/SMC มีหลายสำนัก ทุกผลต้องบอก `contract_version: p002-ict-evidence-v0.1`

## 1. Causal clock

- `pivot_at`: เวลาแท่งที่เป็น swing
- `confirmed_at`: เวลาแท่งด้านขวาครบและระบบเพิ่งรู้ว่า pivot นั้นเป็น swing
- `observed_at`: เวลา event เกิดหรือถูกตรวจพบ
- `cutoff_at`: เวลาสูงสุดที่อนุญาตให้ใช้ข้อมูล

เงื่อนไขบังคับ: `pivot_at <= confirmed_at <= cutoff_at` และ event ห้ามอ้าง swing ก่อน `confirmed_at`

Prefix invariance: เมื่อวิเคราะห์ข้อมูลถึงแท่ง T แล้วนำแท่ง T+1…T+n มาเติม เหตุการณ์ที่มี `confirmed_at <= T` ต้องไม่ย้ายเวลา ราคา หรือชนิดย้อนหลัง ยกเว้นเปลี่ยน lifecycle หลัง T เช่น mitigated/filled

## 2. Confirmed swing

ใช้ fractal ซ้าย/ขวาจำนวน `k` แท่งที่ระบุใน assumptions จุดสูงต้องสูงกว่าผู้เปรียบเทียบทุกแท่ง จุดต่ำต้องต่ำกว่า หากเสมอกันให้ใช้ tie policy ที่ประกาศล่วงหน้า ห้ามเปลี่ยน `k` เพื่อให้ได้ภาพที่ต้องการ

Swing ที่ยังขาดแท่งด้านขวาเป็น `candidate` เท่านั้น ระยะ `k` ต้องวัดแยกตาม asset/timeframe ก่อน production

## 3. Market structure

- Bullish BOS: close ผ่าน confirmed swing high ขณะ state เดิม bullish
- Bearish BOS: close ต่ำกว่า confirmed swing low ขณะ state เดิม bearish
- CHoCH: close break แรกสวน state เดิม; เป็นคำเตือนการเปลี่ยน character ไม่ใช่ reversal ที่ยืนยันแล้ว
- MSS: ใช้ได้เมื่อ contract งานระบุองค์ประกอบเพิ่ม เช่น sweep + displacement + opposite structure close; หากไม่มีนิยามครบให้ `unavailable`
- Wick ผ่านแล้วปิดกลับ = sweep candidate ไม่ใช่ BOS

เริ่มต้น state เป็น `neutral`; break แรกใช้ `structure_break` หรือ CHoCH ตาม assumption ที่บันทึก ห้ามเลือกคำย้อนหลังให้เข้ากับผล

## 4. Liquidity

Liquidity pool คือ equal highs/lows ที่เข้า tolerance ซึ่งล็อกก่อนคำนวณ เช่นสัดส่วน ATR หรือ basis points และต้องมีจำนวน touch ขั้นต่ำ

- Bearish sweep: high ทะลุ confirmed high/pool แล้ว close กลับต่ำกว่าระดับ
- Bullish sweep: low หลุด confirmed low/pool แล้ว close กลับเหนือระดับ

ชื่อ buy-side/sell-side liquidity เป็นภาษาของโมเดล ไม่ใช่หลักฐานว่ามีคำสั่งสถาบันจริง

## 5. Fair Value Gap

แท่ง A-B-C ต้องปิดครบ:

- Bullish FVG: `low(C) > high(A)`; zone = `[high(A), low(C)]`
- Bearish FVG: `high(C) < low(A)`; zone = `[high(C), low(A)]`

บันทึก impulse candle B แต่ `confirmed_at` ต้องเป็นเวลาปิดของ C กติกา wick-fill, close-fill, 50%-mitigation หรือ full-fill ต้องเลือกหนึ่งแบบและใส่ assumptions ห้ามสลับระหว่างสินทรัพย์เงียบ ๆ

## 6. Displacement และ Order Block

Displacement ต้องมีเกณฑ์วัด เช่น body/ATR, range/ATR, close location และ structure break ห้ามตัดสินจากคำว่า “แท่งยาว”

Order Block เป็นแท่งตรงข้ามล่าสุดก่อน displacement ที่พาไปสู่ confirmed break เท่านั้น บันทึก zone policy (`full_range` หรือ `body`), break event, confirmed_at, mitigation rule และ invalidation แท่งตรงข้ามที่ไม่มี displacement/structure link เป็น `candidate`

## 7. Dealing range และ Premium/Discount

Range ต้องยึด confirmed swing low/high คู่เดียวกันที่มีเหตุผลตาม timeframe จุด 50% คือ equilibrium ด้านบนเป็น premium ด้านล่างเป็น discount สำหรับ range นั้นเท่านั้น การอยู่ discount ไม่ใช่เหตุผล Buy โดยลำพัง และการอยู่ premium ไม่ใช่เหตุผล Sell โดยลำพัง

## 8. Session และ Kill Zone

ใช้เมื่อ input มี timezone, DST policy และ session calendar ชัดเจน หากขาดข้อใดให้ `unavailable` ห้ามแปลงเวลาจากความจำ Kill zone เป็น filter บริบท ไม่ใช่หลักฐานทิศหรือ entry เดี่ยว

## 9. Confluence และ classification

Confluence ต้องมาจากหลักฐานคนละตระกูล ห้ามนับ swing, BOS และ OB ที่เกิดจาก break เดียวกันเป็นสามเสียงอิสระ

- `confirmed`: causal timing และ provenance ครบ
- `candidate`: รูปแบบเริ่มเกิดแต่ยังขาด confirmation
- `invalidated`: เงื่อนไขโครงสร้างเสีย
- `mitigated|filled`: zone ถูก revisit ตาม policy
- `unavailable`: input/นิยามไม่พอ

Agent 06 ใช้เฉพาะ `confirmed` ที่ผ่าน level approval; อย่างอื่นนำไปสู่ watch/no_trade Agent 07 ต้อง block เมื่อพบ future-bar leakage, level ไม่มีที่มา, threshold ไม่ versioned หรือคำอ้างเกิน OHLC

## 10. Minimum evidence fields

ทุกแถวควรมี: `id`, `concept`, `direction`, `timeframe`, `price_or_zone`, `source_indices`, `pivot_at`, `confirmed_at`, `observed_at`, `status`, `rule_version`, `assumptions`, `invalidation`, `evidence_refs`
