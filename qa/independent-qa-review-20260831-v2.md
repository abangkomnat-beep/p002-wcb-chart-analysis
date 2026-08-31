# Style M v6 — Independent QA review v2

วันที่ตรวจ: 2026-08-31  
ขอบเขต: prototype branch `p002/style-m-v6-20260831b`; ไม่แก้ v5/production และไม่ promote

## ผลตรวจ

- Cutoff 11:00 BKK และ source bar 10:00 ถูกต้องครบ 180/180 วัน
- Forward window 24 H1 bars ถูกต้องครบ 180/180 วัน
- Signal-bar trigger ถูกนับ 8 กรณี และ retest เกิดหลัง trigger เท่านั้น
- Retest bar รวมใน exit model; same-bar ambiguity ถูกจัดการแบบ conservative
- Cost model ผูกกับ config และมี `cost_r`/`after_cost_r` ครบ 216 exit records
- Leakage spot-check 10/10 ผ่าน
- Targeted v6 tests `19 passed`
- Shadow artifact parity `PASS`, ไม่มี EMA, `production_write=false`, `external_publish=false`, renderer 1920×1080

## Walk-forward 180 วัน

- ข้อมูล BTCUSD H1 5,000 แท่ง; แบ่ง 60 วัน in-sample diagnostic และ 120 วัน out-of-sample
- ใช้ forward observations 4,320 แท่ง; clock/leakage violations = 0
- Cost baseline ต่อขา: fee 5 bps + spread 1 bps + slippage 3 bps + latency uncertainty 3 bps (รวม 24 bps round-trip)
- TP1: raw expectancy `-0.166667R`, after-cost `-0.671547R`
- TP2: raw expectancy `-0.142856R`, after-cost `-0.651562R`
- ต้นทุนเป็นสมมติฐาน QA ไม่ใช่ quote ของ venue จริง

## QA decision

**HOLD — ยังไม่ผ่าน gate สำหรับ integrate/promote** เพราะ OOS after-cost ติดลบทั้ง TP1 และ TP2 แม้ methodology/lifecycle และ technical checks จะผ่านแล้ว
