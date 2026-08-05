---
name: analyze-level-reaction
description: วิเคราะห์จุดตัดสินใจด้วย Pivot/ระดับราคาเป็นเทคนิคหลัก และใช้ price-action reaction กับ VWAP/volume-profile confluence เป็นตัวยืนยัน ใช้กับ Technical Levels Agent เมื่อต้องสร้างแผนขึ้น ลง พัก และจุดยกเลิกจากระดับที่ตรวจย้อนกลับได้
---

# Analyze Level Reaction

ใช้ snapshot ที่ล็อกแล้วเท่านั้น ห้ามสร้างระดับด้วยสายตาหรือเปลี่ยน anchor เพื่อให้เข้ากับราคา

## เทคนิคใน Set

### A หลัก: Locked Decision Levels

ภายใต้ WCB Daily Output Contract v3.2 ระดับเผยแพร่ต้องมาจาก `approved_level_sources` ที่ Data Adapter ระบุแบบ versioned ได้แก่ `technicals.pivots`, `technicals.swing_zones`, `technicals.session_levels` หรือ `technicals.ma_levels` จำกัดเฉพาะระดับที่มีผลต่อการตัดสินใจ ระบุสถานะราคาเป็น above, below, testing หรือ between และสร้างแผนขึ้น/ลง/พัก

ทุกแหล่งต้องมีสูตร/วิธี anchor, timeframe และ timestamp แนวรับ/แนวต้านหรือ high-low จาก field อื่นจัดเป็น `context_only` ห้ามสร้างระดับด้วยสายตา ห้ามเปลี่ยน anchor และห้ามใช้ระดับที่ไม่อยู่ใน `approved_level_sources` เป็น Trigger, Target หรือ Invalidation

### B ยืนยัน: Price-action Reaction

ตรวจ close-through, rejection wick, breakout-retest หรือ failed break ที่ระดับ A ต้องมีแท่งปิดหรือ reaction ตาม timeframe ที่กำหนด ห้ามใช้การแตะระดับเพียงครั้งเดียวเป็นการยืนยัน

### C ยืนยัน: VWAP/Volume Confluence

ใช้ VWAP หรือ volume profile เฉพาะเมื่อ snapshot มี volume ที่เชื่อถือได้และ session/timezone ชัดเจน หากไม่มี ให้ตอบ `unavailable` ห้ามใช้ tick volume หรือประมาณค่าแทนโดยไม่ระบุข้อจำกัด

## การรวมผล

- A level + B reaction + C confluence: confidence สูงภายในโมเดล
- A + B ยืนยัน แต่ C ไม่มีข้อมูล: confidence กลาง
- A ถูกแตะโดยไม่มี B: แผนพักและ confidence ต่ำ
- B/C ขัดกับ A: รายงาน conflict ห้ามย้ายระดับเพื่อบังคับให้ตรงกัน

ระดับราคาคือ zone สำหรับตัดสินใจ ไม่ใช่คำทำนายหรือเป้ารับประกัน

## ผลลัพธ์ขั้นต่ำ

ส่ง `set3_levels.json` พร้อม:

```json
{
  "primary": {"technique": "locked_levels", "publication_levels": [], "context_only": [], "state": "", "evidence": []},
  "confirm_b": {"technique": "price_reaction", "state": "confirm|reject|pending|unavailable", "evidence": []},
  "confirm_c": {"technique": "volume_confluence", "state": "confirm|conflict|neutral|unavailable", "evidence": []},
  "scenario_up": {"bias": "", "entry_zone": "", "trigger": "", "target": [], "invalidation": "", "no_trade": ""},
  "scenario_down": {"bias": "", "entry_zone": "", "trigger": "", "target": [], "invalidation": "", "no_trade": ""},
  "scenario_pause": {"bias": "wait", "trigger": "", "target": [], "invalidation": "", "no_trade": ""},
  "confidence": "high|medium|low|insufficient",
  "conflicts": [],
  "plain_thai": ""
}
```

ทุกระดับใน scenario ต้องอ้าง field ใน `approved_level_sources` พร้อม timeframe และ timestamp ห้ามตั้งราคาเป้าหมายเอง ระดับจาก field อื่นต้องอยู่ใน `context_only` เท่านั้น ใช้ zone เมื่อ precision หรือ volatility ไม่รองรับตัวเลขจุดเดียว
