# P002 WCB Chart Analysis

Private source repository สำหรับระบบนักเขียนบทวิเคราะห์ WorldClassBroker ที่ใช้กราฟเป็นหลัก รองรับ XAU/USD, Forex และ Crypto ในระยะแรก

## สถานะ

อยู่ในขั้น scaffolding และออกแบบ contracts ยังไม่พร้อมสร้างคำแนะนำหรือนำบทความไปเผยแพร่จริง

## Architecture

`Market Snapshot → Technical 3 Sets + News Impact → Chart Editor → Chart/Article → Article QA → User Approval → Publish/Verify`

- Technical Set 1: Trend & Market Structure
- Technical Set 2: Momentum & Volatility
- Technical Set 3: Price Levels & Reaction
- WCB Article QA: ด่านตรวจอิสระแบบ fail-closed

ดู [Agent and skill matrix](docs/AGENT-SKILL-MATRIX.md), [governance](GOVERNANCE.md) และ [delivery checklist](DELIVERY-CHECKLIST.md)

## Security

ห้าม commit API keys, market-data credentials, unpublished articles หรือข้อมูลลูกค้า ใช้ `.env.example` เท่านั้น
