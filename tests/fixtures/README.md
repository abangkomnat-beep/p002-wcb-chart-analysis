---
title: README
type: note
permalink: library/projects/p002-nakekhiiynbthwiekhraaah/repo/tests/fixtures/readme
---

# Fixtures สำหรับเทส P002

> ⚠️ **ข้อมูลในโฟลเดอร์นี้เป็นข้อมูลทดสอบที่สร้างขึ้น ห้ามนำไปใช้เป็นข้อมูลตลาดจริงและห้ามเผยแพร่**

| ไฟล์ | ใช้พิสูจน์อะไร |
|---|---|
| `xau_5_points_with_weekend.json` | ชุดข้อมูลแบบเดียวกับ pilot เดิม — มีแท่งเสาร์-อาทิตย์ปน และแท่งไม่พอคำนวณ SMA/ATR → ต้องถูก block |
| `xau_valid_120_sessions.json` | ชุดที่ session ครบและยาวพอ → ต้องผ่านด่าน |
| `btc_missing_one_day.json` | ตลาด 24/7 ที่ขาดไปหนึ่งวัน → ต้องถูก block |
| `eurusd_valid_sessions.json` | forex ที่ข้าม weekend ตามปกติ → ต้องไม่ถูกนับเป็น gap |