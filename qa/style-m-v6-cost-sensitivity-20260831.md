# Style M v6 — Cost assumptions and sensitivity (independent QA)

วันที่ตรวจ: 2026-08-31  
ฐานข้อมูล: `qa/style-m-v6-walkforward-20260831-independent-rerun/walkforward-report.json` และ source snapshot เดียวกัน  
สถานะ: QA analysis เท่านั้น; ไม่ใช่ venue quote และไม่แก้ production/v5

## ตรวจ baseline

Config `config/style_m_v6_execution_costs.json` กำหนดต้นทุนต่อขา:

| รายการ | bps/ขา | bps/ไปกลับ | median R ต่อ trade* |
|---|---:|---:|---:|
| fee | 5.0 | 10.0 | 0.1855R |
| spread | 1.0 | 2.0 | 0.0371R |
| slippage | 3.0 | 6.0 | 0.1113R |
| latency uncertainty | 3.0 | 6.0 | 0.1113R |
| **รวม** | **12.0** | **24.0** | **0.4451R** |

\* คำนวณจาก entry fill และ risk ของ 108 retest entries ใน snapshot; ค่า median ของส่วนประกอบรวมกันตรงกับ median baseline โดยประมาณ แต่ค่าเฉลี่ย R ขึ้นกับความเสี่ยงของแต่ละแผน

Baseline สอดคล้องกับสูตรใน harness: `round_trip_bps = 2 × (5+1+3+3) = 24 bps` และ `price_cost = fill × 24/10,000`; จากนั้นหารด้วย plan risk เพื่อได้ cost เป็น R

การกระจาย baseline cost รวมต่อ entry: mean `0.4906R`, median `0.4451R`, p90 `0.7467R`, range `0.2212–1.7729R`. ใน resolved TP1/TP2 records ค่าเฉลี่ยอยู่ที่ `0.5049R`/`0.5087R`; OOS อยู่ที่ `0.5560R`/`0.5623R`

## Sensitivity grid (ต่อขา)

แต่ละแถวเป็นชุดสมมติฐานที่ประกาศล่วงหน้า ไม่ได้ปรับตามผลลัพธ์:

| Scenario | fee | spread | slippage | latency | รวม/ขา | RT | TP1 OOS after-cost | TP2 OOS after-cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Zero friction | 0 | 0 | 0 | 0 | 0 | 0 | -0.134615R | -0.105263R |
| Low QA | 2 | 0.5 | 1 | 0 | 3.5 | 7 | -0.296790R | -0.269260R |
| No-latency baseline | 5 | 1 | 3 | 0 | 9 | 18 | -0.551635R | -0.526970R |
| **Baseline** | **5** | **1** | **3** | **3** | **12** | **24** | **-0.690642R** | **-0.667538R** |
| Stress QA | 10 | 2 | 5 | 5 | 22 | 44 | -1.153997R | -1.136101R |

Combined 180-day after-cost expectancy at zero/low/baseline/stress is respectively TP1 `-0.166667/-0.313923/-0.671547/-1.092280R` and TP2 `-0.142856/-0.291229/-0.651562/-1.075484R`. ดังนั้นแม้ frictionless raw OOS ยังติดลบ; baseline cost ไม่ใช่สาเหตุเดียวของผลลบ

## ข้อเสนอ config ที่โปร่งใส

1. คงตัวเลข 5/1/3/3 ไว้เป็น `qa_baseline` เท่านั้น และแสดงชื่อ scenario, unit `bps/ขา`, และสูตร RT ใน report ทุกครั้ง
2. อย่าใช้ baseline นี้เป็น production execution quote: fee ต้องผูกกับ venue/tier จริง, spread ควรมาจาก bid/ask ตามช่วงเวลา, slippage และ latency ควร fit จาก execution telemetry
3. ก่อน promote ให้ rerun อย่างน้อย `low_qa`, `qa_baseline`, และ `stress_qa` ด้วย source snapshot เดียวกัน; ใช้ after-cost OOS เป็นเกณฑ์หลัก และห้ามปรับ config เพื่อให้ผลบวก
4. ปัจจุบันผลไม่ผ่านทุก scenario เพราะ raw OOS เป็นลบอยู่แล้ว จึงควร HOLD v6 และคง v5 production

ข้อจำกัด: cost model เป็น deterministic percentage ของ entry price และคิดต้นทุนครบไปกลับเฉพาะรายการที่ exit model resolved; open/ambiguous ถูกแยกออกจาก expectancy จึงยังไม่ใช่การประมาณ P&L execution จริง
