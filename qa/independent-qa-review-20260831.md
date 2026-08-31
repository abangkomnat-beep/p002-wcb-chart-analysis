# Style M v6 — Independent QA review

วันที่ตรวจ: 2026-08-31  
ขอบเขต: prototype branch `p002/style-m-v6-20260831b` เท่านั้น; ไม่แก้ v5, production, integration หรือ external publish

## หลักฐานที่ตรวจ

- Source snapshot: `qa/style-m-v6-walkforward-20260831-final/source-btcusd-h1.json`
- Walk-forward report: `qa/style-m-v6-walkforward-20260831-final/walkforward-report.json`
- Human-readable report: `qa/style-m-v6-walkforward-20260831-final/walkforward-report.md`
- Latest shadow manifest: `work/normal-runs/style-m-v6-20260831-163500/31-08-2026/btcusd/internal/style-m-v6-shadow-1a460326ecd2/manifest.json`

## ผลตรวจที่ผ่าน

- ข้อมูล BTCUSD H1 มี 5,000 แท่ง ครอบคลุม 2026-02-04 08:00 ถึง 2026-08-31 15:00; ตรวจ continuity และ OHLC envelope ไม่พบข้อผิดพลาด; timezone check ของ feed ผ่าน
- Independent reference implementation ตรงกับ ATR14 และ ADX14 ของ oracle ใน 180 cutoff ที่ใช้ decision clock 11:00 กรุงเทพฯ ภายใน tolerance 0.00005; geometry Long/Short ผ่านครบ
- หลัง Decimal tick-rounding fix, walk-forward harness สร้าง oracle ได้ 180/180 วัน แบ่ง diagnostic 60 วัน + OOS 120 วัน และใช้ forward 24 H1 bars รวม 4,320 observations
- Donchian ใช้ 24 แท่งก่อน signal bar; มี Long/Short ครบ; trigger เป็น strict close cross; OCO ยกเลิกอีกฝั่งเมื่อเกิด trigger; ไม่พบ EMA ใน v6 public copy/facts
- Leakage spot-check 10/10: story ที่สร้างจาก prefix เทียบกับ full source ณ cutoff ให้ source hash และ scenario levels ตรงกัน
- Shadow manifest ยืนยัน `contract_version=M-PROD/v6`, `production_write=false`, `external_publish=false`; claim parity เป็น PASS; renderer เป็น 1920×1080 WebP

## ผล walk-forward (จาก harness รอบล่าสุด)

- Trigger: Long 67, Short 63; retest 101; invalidation ก่อน retest 8
- TP1 all-in sensitivity: resolved 89, win rate 41.573%, expectancy +0.039327R (ยังไม่หักต้นทุน)
- TP2 all-in sensitivity: resolved 84, win rate 33.333%, expectancy ~0R (ยังไม่หักต้นทุน)
- ตัวเลขนี้เป็น sensitivity ไม่ใช่ผล execution จริง และต้องไม่อ่านเป็นคำแนะนำลงทุน

## Blockers / ต้องแก้ก่อน integrate หรือ promote

1. **Decision clock ไม่ตรง approved spec (สำคัญ):** แผนอนุมัติใช้ cutoff 11:00 กรุงเทพฯ แต่ harness `style_m_v6_walkforward.py` ระบุและใช้ cutoff เที่ยงคืนหลังแท่ง 23:00 จึงเป็นผลของคนละรอบตัดสิน ต้องเลือก/ล็อกให้ตรงกันแล้ว rerun 180 วัน
2. **Signal-bar trigger ถูกละเลย:** `simulate()` เริ่มตรวจ trigger จาก forward bars เท่านั้น ไม่รับกรณี latest signal bar ณ cutoff ปิดทะลุ trigger แล้ว ซึ่งทำให้ lifecycle/retest และ metrics คลาดจาก semantics ของ oracle
3. **Retest-bar exit ถูกตัดออก:** exit model เริ่มจาก bar หลัง retest ทั้งที่ fill ใช้ boundary ของ retest zone; การตรวจ source snapshot พบ 13/101 retest bars แตะ SL หรือ TP1/TP2 อย่างน้อยหนึ่งระดับ จึงอาจทำให้ metrics optimistic/ไม่สอดคล้องกับ lifecycle
4. **ต้องรายงานต้นทุนจริง:** แผนอนุมัติกำหนด spread/slippage แต่ report รอบนี้ยังไม่รวมค่าธรรมเนียม, spread, slippage, latency หรือ execution uncertainty
5. **รายงานรอบเก่ามี caveat ค้าง (ปิดแล้ว):** รอบ r2 เคยพิมพ์ว่า oracle unavailable จาก float precision ทั้งที่ JSON ระบุ `story_unavailable_days=0`; final report ถูก regenerate แล้วและระบุชัดว่าแก้ defect ก่อน rerun จึงไม่ค้างเป็น blocker ของ final evidence

## Independent conservative sensitivity

เมื่อจำลองให้รับ signal-bar trigger และรวม retest bar ใน exit model แบบ stop/target same-bar เป็น ambiguous ผลรวม 180 แผนจาก snapshot เดียวกันเปลี่ยนเป็น:

- TP1: resolved 89, wins 35, losses 54, win rate 39.326%, expectancy -0.016854R
- TP2: resolved 84, wins 25, losses 59, win rate 29.762%, expectancy -0.107143R

นี่เป็น diagnostic ที่ชี้ว่าตัวเลขจาก harness ปัจจุบันยังไม่ใช่ฐานอนุมัติ promote; ไม่ได้แก้ไฟล์ production และควร rerun หลังแก้ semantics ให้ตรง approved cutoff/lifecycle ก่อน

## QA decision

**HOLD — ไม่ผ่าน independent QA gate สำหรับ integrate/promote ณ รอบนี้**

Prototype มีองค์ประกอบและสูตรหลักที่ตรวจซ้ำได้ แต่ยังต้องแก้สาม blocker ด้าน methodology/lifecycle และ rerun 180 วันพร้อมต้นทุนการเทรดก่อนเสนอผู้ใช้อนุมัติขั้นถัดไป
