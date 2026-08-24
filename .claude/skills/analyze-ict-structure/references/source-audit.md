# Source Audit — analyze-ict-structure

ตรวจเมื่อ 2026-08-24 สกิลนี้เขียนใหม่สำหรับ P002 และไม่คัดลอก production code จากแหล่งภายนอก

## แหล่งอ้างอิงที่อนุมัติให้ศึกษา

### joshyattridge/smart-money-concepts

- URL: https://github.com/joshyattridge/smart-money-concepts
- Commit ที่ตรวจ: `1b62fd6c41e1f508e7ed76831a039fa4c82d42f6`
- License: MIT
- ใช้ศึกษา: API/fixture ของ FVG, swings, BOS/CHoCH, OB, liquidity, sessions, retracements
- ข้อจำกัด: centered swing และ FVG อ้างแท่งอนาคตเทียบกับตำแหน่งที่ติดป้าย ต้องเลื่อน `confirmed_at`; ห้ามใช้ output ย้อนหลังเป็น live signal

### AkhileshSelvan/smc-mcp

- URL: https://github.com/AkhileshSelvan/smc-mcp
- Commit ที่ตรวจ: `719862b404ec4bd4d52b3bfa4c39ef0c034bb654`
- License: MIT
- ใช้ศึกษา: pure-Python structure event และ unit tests สังเคราะห์
- ข้อจำกัด: structure detector เลื่อน swing confirmation ถูกต้อง แต่ liquidity detector ยังใช้ swing ก่อนครบ right bars ได้; OB ไม่มี quantitative displacement threshold; multi-timeframe/premium-discount ยังไม่ครบ

## แหล่งที่ตรวจแต่ไม่ติดตั้งตรง

### longbridge/skills — longbridge-technical

- URL: https://github.com/longbridge/skills/tree/main/skills/longbridge-technical
- License metadata: MIT
- เหตุผลไม่ติดตั้ง: ผูก Longbridge CLI/data source, มีหลาย framework ที่ไม่เกี่ยวกับ P002 และตัวอย่าง SMC เรียก API `smartmoneyconcepts` ไม่ตรงต้นฉบับบางจุด

## Supply-chain decision

- ไม่เพิ่ม package ใน `requirements.txt`
- ไม่ติดตั้ง MCP/CLI และไม่เพิ่ม network/data source
- ไม่ vendor โค้ดภายนอกเข้า Repo
- ถ้าจะนำ detector มาใช้จริง ต้อง pin commit/version, review license, เขียน prefix/look-ahead tests, backtest และ forward test ก่อนขออนุมัติ production
