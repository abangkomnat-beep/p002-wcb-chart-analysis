# Agent and Skill Matrix

ใช้สกิลเท่าที่สัมพันธ์กับหน้าที่ ห้าม Agent ใช้สกิลเพื่อขยายอำนาจเกิน role ของตน

| Agent/Role | Required skills | ใช้เมื่อใด |
|---|---|---|
| Lead | `make-plan`, `cc-consult`, `product-management:sprint-planning`, `product-management:stakeholder-update` | แตกงาน คุม dependency และรายงาน CC |
| Builder | `test-driven-development`, `systematic-debugging`, `using-git-worktrees`, `data:data-visualization` | เขียนระบบ แก้บั๊ก และสร้างกราฟ |
| Tester | `verification-before-completion`, `data:validate-data`, `differential-review`, `insecure-defaults` | ตรวจหลักฐาน ข้อมูล diff และค่าเริ่มต้นไม่ปลอดภัย |
| Release | `quality-gate`, `github:yeet`, `github:github` | ตรวจส่งมอบและเผยแพร่ repository |
| WCB Chart Editor | `compose-wcb-daily-analysis`, `do-research`, `data:data-visualization`, `marketing:draft-content` | ประกอบบทตาม WCB Daily Output Contract v3.2 (โครง 4 ช่วง) วาง chart spec และร่างบท |
| Technical Set 1 | `analyze-trend-confluence`, `data:statistical-analysis`, `data:data-visualization` | A Market Structure + B MA Regime + C ADX/Multi-timeframe |
| Technical Set 2 | `analyze-momentum-confluence`, `data:statistical-analysis`, `data:data-visualization` | A RSI Regime + B MACD + C ATR/Bollinger regime |
| Technical Set 3 | `analyze-level-reaction`, `data:statistical-analysis`, `data:data-visualization` | A Locked Levels + B Price Reaction + C VWAP/Volume confluence |
| News Impact | `do-research` | ค้นข่าวหลายแหล่ง แยกข้อเท็จจริงกับการตีความ |
| WCB Article QA | `compose-wcb-daily-analysis`, `quality-gate`, `data:validate-data`, `marketing:brand-review`, `verification-before-completion` | ตรวจบท กราฟ ข่าว ตัวเลขและ WCB Daily Output Contract v3.2 |
| Trade Setup Analyst (06) | `analyze-level-reaction`, `analyze-trend-confluence`, `verification-before-completion` | ประกอบแผนการเทรดฝั่ง internal จากระดับที่อนุมัติแล้ว (`tools/trade_plan.py`) |
| Risk & Logic Auditor (07) | `audit-trade-logic` (**MM ติดตั้งแล้ว 2026-08-05**), `verification-before-completion`, `differential-review`, `systematic-debugging` | ตรวจตรรกะและความเสี่ยงของแผน แล้วออกใบสั่งแก้ (`tools/risk_auditor.py` = ด่านกล · สกิล = ด่านวิจารณญาณ) — **สั่งแก้อย่างเดียว ห้ามแก้เอง** · สกิลไม่มีผลต่อสายท่ออัตโนมัติ คำตัดสินต้องผ่าน CC |
| Language Editorial (08) | `edit-financial-language` (core), `locale-th-TH-financial-editorial` (pack) — **ยังไม่ติดตั้ง: รอร่าง + MM ตรวจ (แผนขั้น 4)**, `verification-before-completion` | ปรับภาษา/บรรณาธิการตาม Language Baseline (`language/baseline-registry.yaml`) — แก้ได้เฉพาะ "วิธีพูด" ห้ามแตะ Protected Content · Calibration ถามผู้ใช้เป็นชุด 1 ครั้ง/วัน (มติผู้ใช้ 08-13) · **ไม่ใช่ final QA** — Agent 05 ตรวจอิสระต่อเสมอ · แก้ baseline เองไม่ได้ทุกกรณี ต้องผ่าน `BASELINE_CHANGE_PROPOSAL` + ผู้ใช้อนุมัติ |

## Management rules

- Skill files จริงอยู่ในระบบกลาง ห้ามคัดลอกหรือแก้ skill ใน Repo
- Agent registry ระบุเพียงสิทธิ์ใช้งานและ trigger
- สกิลใหม่ต้องผ่าน MM ก่อนติดตั้ง
- สกิลที่แก้ข้อมูลภายนอกหรือ publish ต้องผ่าน Release/CC และจุดอนุมัติผู้ใช้