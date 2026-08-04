---
name: analyze-momentum-confluence
description: วิเคราะห์โมเมนตัมด้วย RSI regime เป็นเทคนิคหลัก และใช้ MACD กับ ATR/Bollinger volatility regime เป็นตัวยืนยัน ใช้กับ Technical Momentum Agent เมื่อต้องแยกแรงไปต่อ พักฐาน ภาวะยืด และความเสี่ยงไล่ราคาโดยไม่ซ้ำสัญญาณ
---

# Analyze Momentum Confluence

ใช้ snapshot เดียวที่ล็อกไว้ ห้ามดึงข้อมูลใหม่หรือปรับ indicator ให้เข้ากับข้อสรุปที่ต้องการ

## เทคนิคใน Set

### A หลัก: RSI Regime

อ่าน RSI เป็น regime และทิศการเปลี่ยนแปลง ไม่สรุปว่า overbought ต้องลงหรือ oversold ต้องขึ้น ตรวจ bullish/bearish divergence เฉพาะเมื่อมี swing ของราคาและ RSI ที่ยืนยันคู่กัน

อ่านทิศทาง RSI หรือ divergence ได้ต่อเมื่อ snapshot มี RSI series ที่ระบุสูตร เวอร์ชัน และ timeframe ไว้แล้ว หากมีเพียงค่า RSI ปัจจุบัน ให้ใช้ได้เฉพาะการบอก regime ปัจจุบันและระบุข้อจำกัด

ให้ `primary_state`: accelerating, fading, neutral, stretched หรือ insufficient พร้อม warning และจุดที่ทำให้ข้อสรุปใช้ไม่ได้

### B ยืนยัน: MACD Structure

ใช้ตำแหน่ง MACD เทียบ signal/zero line และการเร่งหรือชะลอของ histogram เพื่อ `confirm`, `weaken`, `neutral` หรือ `unavailable` ห้ามนับ cross กับ histogram เป็นสองเสียงแยกกัน

ใช้ได้เฉพาะค่า/series MACD ที่ Data Adapter คำนวณและระบุสูตร เวอร์ชัน และ timeframe ใน snapshot แล้ว หากไม่มีให้ตอบ `unavailable`

### C ยืนยัน: Volatility Regime

ใช้ ATR และ Bollinger Band width/position เมื่อ snapshot รองรับ แยก expansion, contraction และ normal regime เทคนิค C บอกสภาพการเคลื่อนไหว ไม่ใช่ทิศทาง หากมีเพียงช่วงกว้าง 5 วัน ห้ามเรียก ATR14

ใช้ได้เฉพาะค่า/series ATR หรือ Bollinger ที่ Data Adapter คำนวณและระบุสูตร เวอร์ชัน และ timeframe แล้ว หากข้อมูลไม่ครบให้ตอบ `unavailable`

## กฎข้อมูลคำนวณ

Agent ห้ามคำนวณ RSI history, MACD, Bollinger Bands, percentile หรือ indicator อื่นแบบ ad hoc จาก OHLC ภายในงานวิเคราะห์ Data Adapter ต้องเป็นผู้สร้าง field แบบ versioned ก่อนส่งเข้า snapshot การไม่มี field เท่ากับ `unavailable` ไม่ใช่คำเชิญให้คำนวณแทน

## การรวมผล

- A + B เห็นแรงทิศเดียวกัน และ C รองรับ expansion: confidence สูงภายในโมเดล
- A ชัดแต่ B หรือ C ไม่ครบ: confidence กลาง
- A/B ขัดกันหรือ C เตือนการยืด: confidence ต่ำ พร้อม `chase_risk`
- A ไม่มีข้อมูล: insufficient ห้ามให้ B/C แทนเทคนิคหลัก

หลีกเลี่ยงการนับหลักฐานซ้ำ เช่น RSI overbought และ Stochastic overbought ไม่ใช่สองหลักฐานอิสระ

## ผลลัพธ์ขั้นต่ำ

ส่ง `set2_momentum.json` พร้อม:

```json
{
  "primary": {"technique": "rsi_regime", "state": "", "evidence": [], "invalidation": null},
  "confirm_b": {"technique": "macd_structure", "state": "confirm|weaken|neutral|unavailable", "evidence": []},
  "confirm_c": {"technique": "volatility_regime", "state": "confirm|weaken|neutral|unavailable", "evidence": []},
  "momentum": "accelerating|fading|neutral|stretched|insufficient",
  "entry_quality": "favorable|conditional|poor|unknown",
  "volatility_regime": "expansion|contraction|normal|unavailable",
  "confidence": "high|medium|low|insufficient",
  "chase_risk": "high|medium|low|unknown",
  "event_risk_adjustment": "reduce_size|wait|normal|unknown",
  "conflicts": [],
  "plain_thai": ""
}
```

ทุกค่าต้องย้อนกลับ snapshot ได้ และ confidence ไม่ใช่คำรับรองความแม่นยำ

สำหรับ WCB Daily Output Contract v2 ให้แยกทิศแนวโน้มออกจากคุณภาพตำแหน่งเข้า เช่น แนวโน้มลงแต่ `entry_quality=poor` เมื่อราคายืดลงมากแล้ว จำกัด indicator ที่เสนอเผยแพร่ 2–3 ตัวที่หน้าที่ไม่ซ้ำ และรวมทั้งบทไม่เกิน 5 ตัว
