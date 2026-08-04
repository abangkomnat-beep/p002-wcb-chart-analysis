---
name: analyze-trend-confluence
description: วิเคราะห์แนวโน้มตลาดด้วยโครงสร้างราคาเป็นเทคนิคหลัก และใช้ moving-average regime กับ ADX/multi-timeframe เป็นตัวยืนยัน ใช้กับ Technical Trend Agent เมื่อต้องสร้าง bias, confidence, conflict และ invalidation จาก snapshot เดียวโดยไม่โหวต indicator แบบนับเสียง
---

# Analyze Trend Confluence

ใช้ข้อมูลจาก snapshot ที่ล็อกแล้วเท่านั้น ห้ามดึงราคาเพิ่มและห้ามเห็นผล Set อื่นก่อนส่งผล

## เทคนิคใน Set

### A หลัก: Market Structure

1. ระบุ swing high/low ที่ยืนยันแล้ว
2. จำแนก HH-HL, LH-LL หรือ range แยกตาม timeframe
3. ให้ `primary_bias`: up, down, range หรือ insufficient
4. ระบุระดับที่ทำให้โครงสร้างเสียเป็น `invalidation`

เทคนิค A เป็นเจ้าของ bias ห้ามให้ B หรือ C กลับทิศ bias เองหาก A ยังไม่ถูก invalidate

### B ยืนยัน: Moving-average Regime

ตรวจตำแหน่งราคา ลำดับ และความชันของ EMA/SMA ที่มีใน snapshot ใช้เพื่อ `confirm`, `weaken` หรือ `unavailable` เท่านั้น อย่านับเส้นค่าเฉลี่ยหลายเส้นเป็นหลายเสียง เพราะเป็นหลักฐานตระกูลเดียวกัน

### C ยืนยัน: Trend Strength + Multi-timeframe

ใช้ ADX เพื่อวัดความแรง ไม่ใช้ ADX บอกทิศทาง หากมีหลาย timeframe ให้ตรวจว่าภาพย่อยสอดคล้องกับภาพใหญ่หรือเป็นเพียง counter-trend ถ้าข้อมูล ADX หรือ timeframe ไม่ครบ ให้ตอบ `unavailable`

## การรวมผล

- A valid + B/C ยืนยันทั้งคู่: confidence สูงภายในโมเดล
- A valid + ยืนยันหนึ่งตัว อีกตัวเป็นกลาง/ไม่มีข้อมูล: confidence กลาง
- A valid + B/C ขัดทั้งคู่: confidence ต่ำและใช้แผนรอ
- A ไม่ชัด: bias เป็น range/insufficient แม้ B/C เห็นตรงกัน

คำว่า confidence วัดความสอดคล้องของหลักฐาน ไม่ใช่อัตราความแม่นยำ ห้ามใช้คำว่าแม่นยำที่สุดจนกว่าจะมี backtest นอกตัวอย่าง

## ผลลัพธ์ขั้นต่ำ

ส่ง `set1_trend.json` พร้อม:

```json
{
  "primary": {"technique": "market_structure", "state": "", "evidence": [], "invalidation": null},
  "confirm_b": {"technique": "ma_regime", "state": "confirm|weaken|neutral|unavailable", "evidence": []},
  "confirm_c": {"technique": "adx_mtf", "state": "confirm|weaken|neutral|unavailable", "evidence": []},
  "bias": "up|down|range|insufficient",
  "daily_bias": {"state": "", "evidence": [], "invalidation": null},
  "h4_structure": {"state": "", "evidence": []},
  "trigger_timeframe": {"timeframe": "H1|M15|unavailable", "role": "trigger_only", "evidence": []},
  "confidence": "high|medium|low|insufficient",
  "conflicts": [],
  "plain_thai": ""
}
```

ทุก evidence ต้องอ้าง field, timeframe และ timestamp ต้นทาง ห้ามคำนวณค่าที่ input ไม่รองรับ

สำหรับ WCB Daily Output Contract v2 ให้ Daily เป็นเจ้าของแนวโน้มหลัก, H4 เป็นโครงสร้างจังหวะ และ H1/M15 เป็น trigger เท่านั้น หากมี timeframe เดียวให้ระบุข้อจำกัดและห้ามสร้างภาพหลาย timeframe เอง
