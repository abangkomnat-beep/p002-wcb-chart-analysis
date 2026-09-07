# P002 #134 — คู่มือทำชุด South Africa

ขอบเขต: แปลทุกบทใน selected set ที่ Lead ยืนยันเป็น `ZA / en-ZA` ด้วยแพ็ก `en-001` เดิม ไม่สร้างบทตลาดใหม่ ไม่อัปโหลดเว็บ ใช้ Repo เป็น current directory แต่ระบุ P002 หลักด้วย `--project-root` เสมอ

## 1. แบ่งผู้รับผิดชอบ

1. Lead ยืนยันรายการทุกบท/วันต้นฉบับจากชุดที่เลือกจริง รับ source acceptance ของรุ่นบทปัจจุบัน และเตรียม manifest กับ receipt index
2. 09/05 เตรียม Claim map ครบ title/excerpt/body/table/caption ผูก source bytes; `source_quote` ต้องพบจริงอย่างไม่กำกวม ไม่ใช้ทั้งเอกสารเป็น Claim เดียวเพื่อหลบด่าน
3. 08 แปลและส่ง proposal; ห้ามเขียน receipt/index/registry/output เอง
4. Reviewer ต่าง execution ตรวจภาษา; 05 ตรวจสาระ; 10 ตรวจภาพ; Tester ตรวจอินพุตแพ็ก แล้วส่ง receipt ให้ Lead
5. Release เรียก check/commit เมื่อทุกบทพร้อม; CC ตรวจชุดจริงก่อนส่งให้ผู้ใช้

การตรวจ hash พิสูจน์ว่าไฟล์ตรงรุ่น แต่ไม่พิสูจน์ว่าใครเป็นผู้รับรอง Lead ต้องควบคุมการรับไฟล์เข้าดัชนีและตรวจที่มาผู้ตรวจ โปรแกรมนี้ไม่ใช่ระบบลายเซ็นหรือสิทธิ์ผู้ใช้

## 2. พื้นที่งานและไฟล์บังคับ

Run อยู่ใน `P002/work/localization/DD-MM-YYYY/<run-id>/` และมี:

- `source-manifest.json` — schema `p002-za-source/v1`; `run_id`, `source_business_date` เป็น YYYY-MM-DD, `country_code=ZA`, `content_locale=en-ZA`, `language_pack=en-001`, `pack_version`, `pack_sha256`, `articles` ที่ไม่ว่าง
- แต่ละ article: `article_id`, `style`, `asset`, `source_path` relative ต่อ P002 ภายใน output, `source_sha256`, `source_receipt_id`, `claim_map_path`, `claim_map_sha256`, `proposal_path`, `candidate_path`, `images`
- `claims/<id>.json`: `source_sha256`, `claims` แต่ละข้อมี `id`, `source_quote`, `protected` แต่ละค่ามี `id`, `kind`, `value_text`, `unit`, `role`; unit ไม่มีให้ใส่ `none` อย่างชัดเจน
- `proposals/<id>.json`: schema `p002-za-proposal/v1`; `article_id`, `source_sha256`, `pack_sha256`, `writer_execution_id`, `target_markdown`, `alignment`, `open_questions`, `attempt` 1–3
- alignment ระบุ `claim_id`, `target_field`, `target_quote` ที่อ้างข้อความจริงไม่กำกวม; ตรวจ protected literals ภายใน span ของ Claim
- `candidates/<id>.md`: เกิดจาก `--stage-candidates`; normalize newline เป็น LF ก่อนบันทึก แล้วใช้ hash ของ bytes จริงทุกด่าน
- image inventory แต่ละภาพ: `name` ชื่อ `.webp`, `source_path`, `source_sha256`, `candidate_path`, `target_sha256`; ภาพปลายทางอยู่ใน candidates; อย่านับแปล caption เป็นการตรวจข้อความในภาพ
- `receipts/<receipt-id>.json` และ `receipts/index.json`: index เป็น object ที่มี `receipts` เป็น list; แต่ละ entry มีเพียง `receipt_id`, `path` relative ต่อ run เช่น `receipts/language-a.json`, `sha256` ของไฟล์ receipt

Claim/proposal/candidate paths relative ต่อ run และอยู่ใต้ `claims/`, `proposals/`, `candidates/` ตามชนิดไฟล์ ห้าม absolute path, traversal, link/junction หรือ output override; IDs ใช้ตัวอักษรอังกฤษ ตัวเลข `_` และ `-`

Receipt บังคับ: `receipt_id`, `gate`, `article_id`, `reviewer_execution_id`, `reviewer_kind`, `reviewed_at` พร้อม timezone, `verdict`, `findings`, `source_sha256`, `pack_sha256`, `claim_map_sha256` ทุกด่าน ด่าน target เพิ่ม `target_sha256`; visual/package_input เพิ่ม `image_hashes` ของทุกภาพ Source acceptance นี้คือการรับบทเข้าสู่ ZA run/Claim map รุ่นนั้น ไม่ใช่การหยิบผล QA เก่ามาเปลี่ยน hash เอง

Gate names: `source_acceptance`, `language`, `semantic`, `visual`, `package_input` ใช้ underscore ตามนี้ ด่าน target ทั้งสี่ต้อง PASS ตรงรุ่น reviewer ต่างจาก writer; FAIL/HOLD หรือ Critical/Major ค้างปิด release อย่าเติม PASS ให้ fixture หรือเอกสารจริงที่ยังไม่ได้ตรวจ

## 3. แปลและตรวจ

1. โหลดแพ็กจริงด้วย `tools.locale_loader` และ `tools.baseline_registry`; ใส่ version/hash จริงใน job โดยไม่แก้สถานะแพ็กเพื่อให้ผ่าน
2. แปลสาระครบ คง protected ราคา/เครื่องหมาย/หน่วย/timeframe ใน pilot ใช้ภาษาอังกฤษตามแพ็ก ห้ามใช้ตัวนับ certainty ภาษาไทยตัดสินภาษาอังกฤษ
3. Frontmatter แบบ scalar: `country: south-africa`, `language: en`, slug เดิมต่อ `-za`; เปลี่ยน title/excerpt เป็นคำแปลได้ คง metadata อื่นทั้งหมด และ style/asset ต้องตรง source เมื่อ source ระบุ
4. ใช้ image links `![caption](images/<name>.webp)` ตาม inventory ไม่ใช้ HTML/reference-style image ใน pilot; ภาพต้องเปิดได้จริงและผ่าน visual receipt
5. Stage แล้วให้ reviewer อ่านไฟล์ candidate จริง แก้ได้สองรอบหลังร่างแรก ใช้ candidate path ใหม่เมื่อ bytes เปลี่ยน ห้าม overwrite ร่างที่ตรวจแล้ว; เกิน attempt 3 ส่ง CC พร้อมปัญหา

## 4. คำสั่ง

จาก Repo ที่ CC มอบหมาย:

```powershell
$taskProject = 'C:\Users\USER\Desktop\Claude\CC - ที่ปรึกษา\Projects\P002-นักเขียนบทวิเคราะห์'
$taskRun = Join-Path $taskProject 'work/localization/07-09-2026/za-20260907-r1'
$taskManifest = Join-Path $taskRun 'source-manifest.json'
$taskReceipts = Join-Path $taskRun 'receipts/index.json'
python -B -m tools.package_localized_country --project-root $taskProject --manifest $taskManifest --receipt-index $taskReceipts --stage-candidates
python -B -m tools.package_localized_country --project-root $taskProject --manifest $taskManifest --receipt-index $taskReceipts --check
```

Stage PASS คือเก็บ candidate ได้และยัง `release_eligible=false` เสมอ Check อ่านอย่างเดียวและส่ง JSON ทาง stdout; exit 0 คือผ่าน, 1 คือ HOLD, 2 คือ input contract/path ผิด ตรวจ findings และส่งเจ้าของด่านแก้ ไม่แก้ output ด้วยมือ

เมื่อ check พร้อมทั้งชุด และ Release ได้รับมอบหมายให้สร้างชุด local แล้ว:

```powershell
python -B -m tools.package_localized_country --project-root $taskProject --manifest $taskManifest --receipt-index $taskReceipts --release-id r0001 --batch-id b0001 --commit
```

Commit ตรวจใหม่ใน invocation เดียวกัน ไม่ใช้ผลเก่ารับรอง; output ยึดวันต้นฉบับ:

```text
P002/output/07-09-2026/134-Localized/
  batches/b0001/manifest.json
  ZA-South-Africa/en-ZA/releases/r0001/
    manifest.json
    README.md
    L-EURUSD/article.md
    L-EURUSD/images/<name>.webp
```

เปิดเฉพาะ release ที่ batch manifest อ้างถึง ห้ามเลือกโฟลเดอร์ล่าสุดเอง Metadata ของ release ผูก manifest/index/pack/claim/source/image hashes; QA logs และ proposals อยู่ใน work เท่านั้น

## 5. รันซ้ำและกู้จากการหยุดกลางทาง

- Job, approvals และไฟล์เหมือนเดิมทุก bytes: รัน release/batch ID เดิมได้โดยไม่เขียนทับ
- ถ้ามีการเปลี่ยนบท/ภาพ/แพ็ก/manifest/index: ใช้ run/revision/receipt รุ่นใหม่ และ release/batch ใหม่หลังตรวจครบ
- ล้มก่อน batch marker: staging หรือ release ที่ยังไม่มี marker ไม่ถือว่าพร้อมส่ง รันคำสั่งเดิมต่อได้หากข้อมูลยังตรง ตรวจ findings ก่อน; เครื่องมือไม่ลบข้อมูลค้างอัตโนมัติ
- ห้ามแก้ release เดิมให้ตรง manifest เพื่อหลบ conflict; ให้ CC ตรวจ evidence แล้วออก revision ใหม่
- Work กับ output ต้องอยู่ filesystem/volume เดียวกันสำหรับ atomic rename/hardlink ตาม pilot Windows นี้

## 6. สิ่งที่เครื่องมือยังตัดสินแทนคนไม่ได้

Selected set ต้องครบจาก Lead, Claim map ต้องครอบคลุมสาระจริง, ความหมาย/ความเป็นธรรมชาติและข้อความในภาพต้องมีผู้ตรวจ และแพ็กต้องมีการรับรองจริงพร้อมสถานะ `stable_locked` ก่อนส่งประเทศ แพ็ก draft ใช้ calibration ได้เมื่อ source acceptance ครบ แต่ไม่ถือว่าได้ประเทศแล้ว ไม่มี scheduler/queue/33-country automation ใน pilot นี้
