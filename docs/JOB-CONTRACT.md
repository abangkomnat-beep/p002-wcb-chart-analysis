# P002 Job Contract v1

งานทุกสายต้องส่งต่อด้วย `analysis-job-v1` และ artifact reference ที่มี SHA-256. Agent 09 ทำ semantic editorial review ก่อน Agent 08 ตรวจภาษา/locale; Agent 04 เป็น QA อิสระ.

กฎสำคัญ: snapshot เปลี่ยนต้องสร้าง revision ใหม่, stale hash ต้องหยุด, และ `passed` ต้องมี gate ครบ. Pilot แรกเป็น fixture/synthetic + shadow เท่านั้น ไม่ apply และไม่ publish.
