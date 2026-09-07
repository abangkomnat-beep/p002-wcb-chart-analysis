# ความต่อเนื่องของบทและคำถามท้ายบท

โมดูล `tools.article_continuity` ต่อกับสายผลิต D/E/L/M ที่เป็นสินทรัพย์ใน upload lanes ปัจจุบัน ไม่มีการเปลี่ยนคิวเผยแพร่ สูตรแผนหรือรูปภาพ

## สิ่งที่ผู้อ่านเห็น

- หากมีฉบับส่งมอบครั้งก่อนที่ตรวจสอบได้: หัวข้อ `อัปเดตจากแผนครั้งก่อน` หลังบทนำ บอกวันที่จริง การเปลี่ยนกรอบ/เงื่อนไข และผลที่ข้อมูลยืนยันได้
- หากไม่มีฉบับส่งมอบก่อนหน้าที่ตรวจสอบได้: ละหัวข้ออัปเดต บทปัจจุบันยังทำงานตามปกติ
- ทุกบทที่อยู่ในขอบเขตมี `คุณมองตลาดอย่างไร?` เป็นหัวข้อเนื้อหาสุดท้าย เก็บ footer ที่จำเป็นไว้ท้ายสุด
- ประวัติคำถามตรวจ 10 ฉบับส่งมอบและเว้น family 3 ฉบับ โดยคงประวัติคำถามแม้เปลี่ยน contract; baseline ต้องใช้ contract เดียวกัน

## หลักฐานภายในและฐานอัตโนมัติ

ค่าเริ่มต้นเก็บ candidate, delivery receipt และ batch manifest ใต้ `work/continuity` เท่านั้น เก็บ article/evidence และ hash ครบแยก revision หลัง selector จัดชุด `0-ขึ้นเว็บวันนี้` สำเร็จครบทุก lane ระบบเทียบ Markdown ปลายทางกับ candidate ที่ผ่าน QC แล้ว finalize receipt ชนิด `selected_delivery` อัตโนมัติ รอบถัดไปจึงเขียนต่อจากฉบับนี้โดยไม่ต้องรอผู้ใช้ยืนยันรายวัน

receipt อัตโนมัติมี `publication_verified=false` เสมอ หมายถึง “ฉบับส่งมอบที่เลือกขึ้นเว็บ” ไม่ใช่หลักฐานว่าเว็บเผยแพร่จริง รอบที่ partial, candidate/evidence/hash ไม่ตรง, preview หรือ selector ล้มเหลวจะไม่เลื่อน baseline และเขียนสถานะ recovery ไว้ภายในเท่านั้น การรันซ้ำชุดเดิมเป็น idempotent; หลาย revision ในวันเดียวกันเก็บ audit ครบแต่รอบถัดไปใช้ฉบับส่งมอบสำเร็จล่าสุดเพียงฉบับเดียว

ไม่มี delivery receipt, batch manifest หรือ sidecar ใดถูกวางใน output

## หลักฐานเผยแพร่จริงแบบ manual (ทางเลือก)

เมื่อผู้ใช้ยืนยันอัปโหลดฉบับตรงกันจริง ผู้ดูแลใช้คำสั่งนี้ โดยคัด revision และ hash จาก candidate ที่ตรวจแล้ว:

```powershell
python -m tools.article_continuity --store-root <internal-continuity-directory> --revision <revision> --article-hash <sha256> --evidence-hash <sha256> --published-at <timestamp-with-timezone> --receipt <published-url-or-explicit-confirmation-record> --confirmed-by <operator>
```

คำสั่งนี้เป็น audit เพิ่มเติมสำหรับหลักฐานเผยแพร่จริง ไม่ใช่เงื่อนไขของ baseline อัตโนมัติ และไม่ส่งข้อมูลขึ้นเว็บ ถ้าบทบนเว็บเปลี่ยนจากไฟล์ candidate ต้องเตรียม revision ที่ตรวจสอบใหม่ก่อนยืนยัน ห้ามยืนยันด้วย hash ของคนละฉบับ

ไฟล์ immutable ใช้ atomic create-if-absent; การยืนยันซ้ำข้อมูลเดิมปลอดภัย การเขียนทับ revision เดิมด้วยข้อมูลใหม่จะถูกปฏิเสธ ห้ามตั้ง store root ภายใน output

## ขอบเขตการประเมินย้อนหลัง

ตรวจเฉพาะข้อมูลแท่งปิดหลัง cutoff เดิมภายในอายุแผนและ cutoff ปัจจุบัน ใช้เงื่อนไข native contract ที่ adapter รองรับเท่านั้น ข้อมูลขาด ลำดับ SL/TP ในแท่งเดียวไม่ชัด หรือ contract เทียบไม่ได้ จะไม่ตัดสินผลสำเร็จ/ล้มเหลว ไม่มีการอ้างว่าผู้อ่านส่งคำสั่งหรือได้รับกำไรจริง

บทเก่าที่ไม่มี candidate/evidence ครบจะไม่ถูกย้อนเติมเป็น baseline ระบบเริ่มเก็บอัตโนมัติจากชุดส่งมอบใหม่ที่ผ่านเงื่อนไขเท่านั้น

## การทดสอบและ Gate

ใช้ frozen runtime tests ของทั้งสี่ pipeline รวมหลักฐานตรงไฟล์ Markdown สุดท้าย, การไม่สร้าง sidecar, hash/receipt ผิด, same-day/future baseline, เปลี่ยน contract, ประวัติคำถาม, chronological ambiguity และผลทดสอบอิสระ

Preview ใน `work/reader-proof` เป็นไฟล์ตรวจเท่านั้น ส่วน baseline fixture ระบุชัดว่าเป็นข้อมูลทดสอบ ผู้ใช้ต้องพรูฟก่อนแทน output และ commit/push/publish ตามคำสั่งถัดไป
