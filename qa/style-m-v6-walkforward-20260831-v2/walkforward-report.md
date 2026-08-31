# Style M v6 — Independent Walk-forward QA (180 วัน)

## ผลสรุป

- พยายาม 180 วัน: สร้าง oracle ได้ 180 วัน; unavailable 0 วัน. แบ่ง in-sample diagnostic 60/60 วัน และ out-of-sample 120/120 วัน (พารามิเตอร์ถูกตรึงก่อนรัน ไม่มีการปรับจากผล)
- ข้อมูล BTCUSD H1 5,000 แท่ง: 2026-02-04 08:00:00 ถึง 2026-08-31 15:00:00; ใช้ forward 4,320 bar-observations.
- OCO trigger: Long 72 / Short 62; retest 108; invalidation ก่อน retest 4.
- TP1 all-in: resolved 84; raw win-rate 0.333333, expectancy -0.166667R; after-cost win-rate 0.333333, expectancy -0.671547R.
- TP2 all-in: resolved 91; raw win-rate 0.285714, expectancy -0.142856R; after-cost win-rate 0.285714, expectancy -0.651562R.
- Cost baseline ต่อขา: fee 5.0 bps + spread 1.0 bps + slippage 3.0 bps + latency uncertainty 3.0 bps.

## แยกผลตามช่วงเวลา

- In-sample diagnostic: TP1 raw/after-cost -0.21875R / -0.640517R จาก 32 resolved; TP2 raw/after-cost -0.205879R / -0.624779R.
- Out-of-sample: TP1 raw/after-cost -0.134615R / -0.690642R จาก 52 resolved; TP2 raw/after-cost -0.105263R / -0.667538R.
- สรุป QA: ใช้ผล after-cost เป็นหลัก; หาก out-of-sample ไม่เป็นบวกอย่างมี margin จะไม่ผ่านเกณฑ์ integrate/promote.

## ขอบเขตและข้อจำกัด

- ระหว่าง QA พบและแก้ numerical precision ของ RR หลัง tick rounding ก่อนรัน final snapshot; final run สร้าง oracle ได้ 180/180 วัน. การแก้ต้องผ่าน test และ code review แยกต่างหาก.
- ทุกแผนสร้างจากแท่งปิดไม่เกิน cutoff เท่านั้น; แท่ง 24 ชั่วโมงถัดไปถูกใช้เฉพาะวัดผล จึงไม่มี future leakage.
- ผลกำไรเป็น sensitivity ของการถือเต็มจำนวนถึง TP1 หรือ TP2 แยกกัน ไม่ใช่ผลของการแบ่งปิดบางส่วน เพราะ v6 ยังไม่ได้ระบุกติกาจัดการ position หลัง TP1.
- H1 OHLC ระบุลำดับเมื่อ SL และ TP ถูกแตะในแท่งเดียวกันไม่ได้; บาร์ดังกล่าวถูก book เป็น STOP_AMBIGUOUS_BAR เพื่อไม่เลือกผลที่เป็นคุณต่อระบบ. Retest+target ในแท่งเดียวกันเป็น AMBIGUOUS_ENTRY_TARGET และไม่เข้า expectancy.
- Cost baseline เป็นสมมติฐาน QA ที่ประกาศไว้ ไม่ใช่ quote ของ venue; ยังต้องทดสอบกับ fee tier, spread, slippage และ latency จริงก่อนใช้งานจริง.

รายละเอียดตัวเลขทั้งหมดและหลักฐานรายวันอยู่ใน `walkforward-report.json`.
