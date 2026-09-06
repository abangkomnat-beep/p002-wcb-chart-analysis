# ความต่อเนื่องของบทและคำถามท้ายบท

โมดูล `tools.article_continuity` ต่อกับสายผลิต D/E/L/M ที่เป็นสินทรัพย์ใน upload lanes ปัจจุบัน ไม่มีการเปลี่ยนคิวเผยแพร่ สูตรแผนหรือรูปภาพ

## สิ่งที่ผู้อ่านเห็น

- หากมีฉบับเผยแพร่ครั้งก่อนที่ตรวจสอบได้: หัวข้อ `อัปเดตจากแผนครั้งก่อน` หลังบทนำ บอกวันที่จริง การเปลี่ยนกรอบ/เงื่อนไข และผลที่ข้อมูลยืนยันได้
- หากไม่มีฉบับก่อนที่ยืนยัน: ละหัวข้ออัปเดต บทปัจจุบันยังทำงานตามปกติ
- ทุกบทที่อยู่ในขอบเขตมี `คุณมองตลาดอย่างไร?` เป็นหัวข้อเนื้อหาสุดท้าย เก็บ footer ที่จำเป็นไว้ท้ายสุด
- ประวัติคำถามตรวจ 10 บทเผยแพร่และเว้น family 3 บท โดยคงประวัติคำถามแม้เปลี่ยน contract; baseline ต้องใช้ contract เดียวกัน

## หลักฐานภายในและการยืนยันอัปโหลด

ค่าเริ่มต้นเก็บใต้ `work/continuity/candidates` และ `work/continuity/published` เก็บ article/evidence และ hash ครบแยก revision การเรนเดอร์หรือคัดลอกไป output ไม่ถือว่าขึ้นเว็บแล้ว

เมื่อผู้ใช้ยืนยันอัปโหลดฉบับตรงกันจริง ผู้ดูแลใช้คำสั่งนี้ โดยคัด revision และ hash จาก candidate ที่ตรวจแล้ว:

```powershell
python -m tools.article_continuity --store-root <internal-continuity-directory> --revision <revision> --article-hash <sha256> --evidence-hash <sha256> --published-at <timestamp-with-timezone> --receipt <published-url-or-explicit-confirmation-record> --confirmed-by <operator>
```

คำสั่งนี้บันทึกหลักฐานอัปโหลดด้วยมือ ไม่ส่งข้อมูลขึ้นเว็บ ไม่ต้องรันเพื่อเตรียม preview ถ้าบทบนเว็บเปลี่ยนจากไฟล์ candidate ต้องเตรียม revision ที่ตรวจสอบใหม่ก่อนยืนยัน ห้ามยืนยันด้วย hash ของคนละฉบับ

ไฟล์ immutable ใช้ atomic create-if-absent; การยืนยันซ้ำข้อมูลเดิมปลอดภัย การเขียนทับ revision เดิมด้วยข้อมูลใหม่จะถูกปฏิเสธ ห้ามตั้ง store root ภายใน output

## ขอบเขตการประเมินย้อนหลัง

ตรวจเฉพาะข้อมูลแท่งปิดหลัง cutoff เดิมภายในอายุแผนและ cutoff ปัจจุบัน ใช้เงื่อนไข native contract ที่ adapter รองรับเท่านั้น ข้อมูลขาด ลำดับ SL/TP ในแท่งเดียวไม่ชัด หรือ contract เทียบไม่ได้ จะไม่ตัดสินผลสำเร็จ/ล้มเหลว ไม่มีการอ้างว่าผู้อ่านส่งคำสั่งหรือได้รับกำไรจริง

บท L เดิมไม่แสดงความต่อเนื่องเพราะข้อมูล state เก่าต่างรูปแบบ และไม่มีฉบับก่อนพร้อม provenance ที่ผ่าน selector เดิม จึงไม่ย้ายข้อมูลเก่ามาเป็น published baseline อัตโนมัติ

## การทดสอบและ Gate

ใช้ frozen runtime tests ของทั้งสี่ pipeline รวมหลักฐานตรงไฟล์ Markdown สุดท้าย, การไม่สร้าง sidecar, hash/receipt ผิด, same-day/future baseline, เปลี่ยน contract, ประวัติคำถาม, chronological ambiguity และผลทดสอบอิสระ

Preview ใน `work/reader-proof` เป็นไฟล์ตรวจเท่านั้น ส่วน baseline fixture ระบุชัดว่าเป็นข้อมูลทดสอบ ผู้ใช้ต้องพรูฟก่อนแทน output และ commit/push/publish ตามคำสั่งถัดไป
