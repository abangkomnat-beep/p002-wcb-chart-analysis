# Agent and Skill Matrix

ใช้สกิลเท่าที่สัมพันธ์กับหน้าที่ ห้าม Agent ใช้สกิลเพื่อขยายอำนาจเกิน role ของตน

| Agent/Role | Required skills | ใช้เมื่อใด |
|---|---|---|
| Lead | `make-plan`, `cc-consult`, `product-management:sprint-planning`, `product-management:stakeholder-update` | แตกงาน คุม dependency และรายงาน CC |
| Builder | `test-driven-development`, `systematic-debugging`, `using-git-worktrees`, `data:data-visualization` | เขียนระบบ แก้บั๊ก และสร้างกราฟ |
| Tester | `verification-before-completion`, `data:validate-data`, `differential-review`, `insecure-defaults` | ตรวจหลักฐาน ข้อมูล diff และค่าเริ่มต้นไม่ปลอดภัย |
| Release | `quality-gate`, `github:yeet`, `github:github` | ตรวจส่งมอบและเผยแพร่ repository |
| WCB Chart Editor | `do-research`, `data:data-visualization`, `marketing:draft-content` | สังเคราะห์หลักฐาน วาง chart spec และร่างบท |
| Technical Set 1 | `data:statistical-analysis`, `data:data-visualization` | โครงสร้าง แนวโน้ม และ multi-timeframe |
| Technical Set 2 | `data:statistical-analysis`, `data:data-visualization` | momentum และ volatility |
| Technical Set 3 | `data:statistical-analysis`, `data:data-visualization` | ระดับราคาและ reaction zones |
| News Impact | `do-research` | ค้นข่าวหลายแหล่ง แยกข้อเท็จจริงกับการตีความ |
| WCB Article QA | `quality-gate`, `data:validate-data`, `marketing:brand-review`, `verification-before-completion` | ตรวจบท กราฟ ข่าว ตัวเลขและ Voice Spec |

## Management rules

- Skill files จริงอยู่ในระบบกลาง ห้ามคัดลอกหรือแก้ skill ใน Repo
- Agent registry ระบุเพียงสิทธิ์ใช้งานและ trigger
- สกิลใหม่ต้องผ่าน MM ก่อนติดตั้ง
- สกิลที่แก้ข้อมูลภายนอกหรือ publish ต้องผ่าน Release/CC และจุดอนุมัติผู้ใช้
