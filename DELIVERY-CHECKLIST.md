# DELIVERY CHECKLIST

- [x] Data/chart/article contracts ผ่าน — change set นี้แก้ author/scoring envelope; Tester R4 ผ่าน contract regressions และไม่มี data/chart implementation delta
- [ ] N/A — Technical Set 1-3 แยกหลักคิดและใช้ snapshot เดียวกัน: ไม่ได้เปลี่ยน Technical Set หรือ snapshot ใน change set นี้
- [ ] N/A — Chart สร้างซ้ำได้และอ่านบนมือถือ: ไม่ได้เปลี่ยน chart/renderer/visual ใน change set นี้ และ Style M ถูก freeze
- [x] Article QA จับชุดข้อผิดพลาดที่ฝังไว้ครบ — Lead rerun hostile + prior regressions `202 passed, 1 skipped, 813 subtests`; รอ Tester/Release/QQ ยืนยันซ้ำก่อนส่งมอบ
- [ ] N/A — Pilot 10 บทผ่าน: rollout นี้เป็น shadow scoring core; calibration ≥12 บทเป็น gate ถัดไปและยังไม่อนุญาต activation
- [x] ไม่มี secrets และสิทธิ์ข้อมูล/ภาพชัดเจน — heuristic secret scan ของ candidate ไม่พบ match; change set ไม่เพิ่มข้อมูลหรือภาพภายนอก
- [x] **ไม่มีช่อง frontmatter แปลกปลอมในไฟล์ที่ส่งออก** — รัน `python -m tools.frontmatter_guard .`
      (และ `python -m tools.frontmatter_guard ../output` สำหรับบทความรอบที่จะส่ง) ต้องขึ้นว่า
      "สะอาด" · เครื่องมือจัดการความรู้บางตัวเฝ้าโฟลเดอร์แล้วเขียน `permalink:` แทรกกลับเข้าไฟล์
      **หลัง**สายท่อเขียนเสร็จ จึงต้องตรวจ ณ ตอนจะส่ง ไม่ใช่ตอนสร้าง (เจอจริง 2026-08-05:
      บทความ 12/12 ใบ และไฟล์ในรีโป 27 ใบ รวมถึง fixture ของเทส)
      ผล 2026-09-04: Repo `.` สะอาด และ `../../../output/03-09-2026` สะอาด
- [x] **สกิลประจำโปรเจกต์อยู่ใน `.claude/skills/` ของ Repo และถูก commit แล้ว** — `git ls-files .claude/skills` คืน tracked skill files หลายรายการ; change set นี้ไม่แก้ skill
- [x] README วิธีติดตั้ง/ใช้/ทดสอบครบ **และอธิบายว่าสกิลใน `.claude/skills/` ใช้ยังไง** — README เดิมมี project/skill usage และ corrective เพิ่มลิงก์ `docs/QUALITY-SCORING-RUNBOOK.md` สำหรับ scoring commands/rollback
- [x] QQ ผ่าน — QQ รอบ 2 วันที่ 2026-09-04 ผ่าน hostile-input, schema, batch isolation, author/scope, security, runbook และ rollback gates
- [ ] ผู้ใช้อนุมัติ publish — pending; งานนี้ไม่มี publish authority และยังคง shadow
