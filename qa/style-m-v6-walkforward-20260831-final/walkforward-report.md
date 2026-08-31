# Style M v6 — Independent Walk-forward QA (180 วัน)

## ผลสรุป

- พยายาม 180 วัน: สร้าง oracle ได้ 180 วัน; unavailable 0 วัน. แบ่ง in-sample diagnostic 60/60 วัน และ out-of-sample 120/120 วัน (พารามิเตอร์ถูกตรึงก่อนรัน ไม่มีการปรับจากผล)
- ข้อมูล BTCUSD H1 5,000 แท่ง: 2026-02-04 08:00:00 ถึง 2026-08-31 15:00:00; ใช้ forward 4,320 bar-observations.
- OCO trigger: Long 67 / Short 63; retest 101; invalidation ก่อน retest 8.
- sensitivity TP1 all-in: resolved 89, win-rate 0.41573, expectancy 0.039327R; excluded ambiguous/open 12.
- sensitivity TP2 all-in: resolved 84, win-rate 0.333333, expectancy 1e-06R; excluded ambiguous/open 17.

## แยกผลตามช่วงเวลา

- In-sample diagnostic: TP1 expectancy 0.206897R จาก 29 resolved; TP2 expectancy 0.071429R จาก 28 resolved.
- Out-of-sample: TP1 expectancy -0.041665R จาก 60 resolved; TP2 expectancy -0.035712R จาก 56 resolved.
- สรุป QA: out-of-sample เป็นลบทั้งสอง sensitivity ก่อนคิดต้นทุนธุรกรรม จึงยังไม่ผ่านเกณฑ์ integrate/promote.

## ขอบเขตและข้อจำกัด

- ระหว่าง QA พบและแก้ numerical precision ของ RR หลัง tick rounding ก่อนรัน final snapshot; final run สร้าง oracle ได้ 180/180 วัน. การแก้ต้องผ่าน test และ code review แยกต่างหาก.
- ทุกแผนสร้างจากแท่งปิดไม่เกิน cutoff เท่านั้น; แท่ง 24 ชั่วโมงถัดไปถูกใช้เฉพาะวัดผล จึงไม่มี future leakage.
- ผลกำไรเป็น sensitivity ของการถือเต็มจำนวนถึง TP1 หรือ TP2 แยกกัน ไม่ใช่ผลของการแบ่งปิดบางส่วน เพราะ v6 ยังไม่ได้ระบุกติกาจัดการ position หลัง TP1.
- H1 OHLC ระบุลำดับเมื่อ SL และ TP ถูกแตะในแท่งเดียวกันไม่ได้; บาร์ดังกล่าวถูกนับ AMBIGUOUS_BAR และตัดออกจาก expectancy/win-rate แทนการเลือกผลที่เป็นคุณต่อระบบ.
- ชุดนี้ประเมิน BTCUSD จากฟีดเดียวและช่วงเวลาหนึ่งเท่านั้น; ไม่รวมค่าธรรมเนียม, slippage, spread, latency หรือ execution จริง.

รายละเอียดตัวเลขทั้งหมดและหลักฐานรายวันอยู่ใน `walkforward-report.json`.
