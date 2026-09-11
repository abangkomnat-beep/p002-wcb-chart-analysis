---
title: P002 Daily Unification Implementation Plan
description: แผนรวมคำสั่งรันประจำวันของ P002 ตั้งแต่ต้นฉบับไทยถึง localization และ delivery โดยคง quality gates
tags: [P002, localization, daily-run, implementation-plan]
---

# P002 — Daily Unification Implementation Plan

สถานะ: **PLAN COMPLETE WITH BLOCKERS**  
วันที่อ้างอิง: 2026-09-11  
ขอบเขต: คำสั่งรันประจำวันหนึ่งรูปแบบ, ต้นฉบับไทย, localization ต่างประเทศ 19 ประเทศ, MY/BR/NG และ 16 ประเทศที่ยัง hold

เอกสารนี้เป็นผลของขั้นที่ 2/5 เท่านั้น ยังไม่มีการแก้ source, tests, config, enrollment หรือ scheduler และยังไม่มีการรันงานผลิตจริง

## 1. หลักฐานที่ยืนยันเพิ่มจากขั้นที่ 1

### 1.1 `run_morning` และ approval gate

`tools/run_morning.py` ทำหน้าที่ normalize `--write/--watch/--exclude`, เติม `xauusd` และ `wtiusd` วันจันทร์, ตรวจ ownership และสร้าง morning plan ที่ผูกกับ `Asia/Bangkok` (`run_morning.py:36-95`, `98-135`)

หากไม่มี `--confirm` จะเป็น preview และไม่เรียกสายผลิต (`run_morning.py:239-264`) หากมี `--confirm` จะเขียน plan แบบ exclusive เพื่อกันการรันซ้ำ จากนั้นเรียก `run_daily.main()` โดยส่ง `--asset` และ `--skip-selection` (`run_morning.py:183-230`) แล้วค่อยตรวจ author ownership และเลือกใบขึ้นเว็บอีกครั้ง

ข้อสรุป: approval/plan ของ `run_morning` เป็นหน้าที่จริงที่ต้องคงไว้ แต่ปัจจุบันมี entrypoint สำหรับผู้ใช้สองตัวและ logic หลังการผลิตซ้อนกัน จึงต้องย้าย plan API ไปเป็นโมดูลร่วม แล้วให้ `run_morning` เป็น compatibility adapter

### 1.2 writer runtime ที่ติดตั้งจริง

พบ runtime ที่ `work/translation-env/Scripts/python.exe` และ package `co-op-translator==0.20.1` ตาม `requirements-translation.txt` และ `docs/translation-runtime.md`

ตรวจ module จริงแบบไม่เรียก provider พบ:

- `co_op_translator.api.start_markdown_agent_translation(document, language_code, source_path)` สร้าง Markdown chunks และ prompt สำหรับ host agent
- `co_op_translator.api.finish_markdown_agent_translation(job, translated_chunks)` ประกอบเนื้อหากลับแบบ deterministic
- upstream ระบุชัดว่า “without calling an LLM provider” และให้ host agent แปล chunks เอง

หลักฐานใน P002 อยู่ที่ `tools/translation_adapter.py:70-92` และ `:117-206` ส่วนคำสั่ง routing กำหนด `provider_calls_allowed: false` ใน `config/translation-engine-routing.json`

ข้อสรุป: runtime นี้ไม่ใช่ autonomous translator และไม่มี executable/provider call ที่ทำให้คำสั่ง CLI แปลเองครบได้ในปัจจุบัน การ patch จะต้องมี writer execution seam แบบ request/response ที่ได้รับอนุญาต หรือหยุดเป็น `WAITING_WRITER`; ห้ามอ้างว่า `co-op-translator` แปลเสร็จเอง

### 1.3 independent review และ admission

เส้นทางหลักที่มีอยู่คือ:

1. `build_localized_release_handoff.build()` ตรวจ candidate/source/image hash และสร้าง handoff สถานะ `HOLD_INDEPENDENT_REVIEW` แต่ไม่สร้าง review PASS (`tools/build_localized_release_handoff.py:1-7`, `:135-257`)
2. `attach_independent_review_receipts.attach()` รับเฉพาะ receipt ที่ออกแล้ว ต้องครบ 4 gates ต่อบท (`language`, `semantic`, `visual`, `package_input`), ผูก writer/source hash และ reviewer execution ที่ต่างจาก writer (`tools/attach_independent_review_receipts.py:50-126`)
3. `package_localized_country.prepare_country()` ทำ package ที่ผ่านการตรวจลง transaction prepared tree เท่านั้น (`tools/package_localized_country.py:597-645`)
4. `localization_transaction.apply_transaction()` แลกเปลี่ยน tree และเขียน day marker เป็นขั้นปลายทาง (`tools/localization_transaction.py:prepare_transaction`, `:apply_transaction`)
5. `localization_admission.validate()` ตรวจ admission record ที่มนุษย์ออกให้แล้วเท่านั้น และไม่มีฟังก์ชันสร้าง `ADMITTED` record (`tools/localization_admission.py:1-5`, `:50-106`)

ข้อสรุป: Luna ทำ self-review ได้ แต่ไม่ถือเป็น independent review ระบบปัจจุบันไม่มีช่องทางให้ Luna สร้าง receipt อิสระหรือ admission อย่างถูกต้องเอง หากไม่มี receipt/admitter จากภายนอก ผลต้องเป็น `WAITING_REVIEW` หรือ `READY_FOR_ADMISSION` ไม่ใช่ delivery PASS

### 1.4 ผลตรวจ 23 tests

ผล `23 passed in 3.17s` มาจากคำสั่งนี้ที่รันในขั้นที่ 1:

```text
python -m pytest tests/test_localization_queue.py tests/test_normal_localization_orchestrator.py tests/test_run_daily_dispatch_integration.py tests/test_run_daily_localization_resume.py -q
```

ยังไม่มีไฟล์ evidence ที่ commit ผลชุดนี้โดยตรง จึงถือเป็นหลักฐานจาก session เท่านั้น ไม่แต่งย้อนหลังว่าเป็น live verification

## 2. As-is ที่ยืนยันแล้ว

```text
run_morning [optional preview/confirm]
  -> run_daily
     -> Thai source production / source QA
     -> country-first migration / selection / frontmatter guard
     -> localization_queue.write_receipt
        -> rollout 20 countries, excluding TH = 19 foreign targets
        -> policy enabled flag
        -> admission-index validation
     -> normal_localization_orchestrator.run
        -> frozen source binding
        -> existing delivery check
        -> existing handoff check
        -> create dispatch jobs
           -> WAITING_WRITER when no writer handoff exists
```

`normal_localization_orchestrator.py` ระบุเจตนาไม่ทำ translation/review/package/transaction/admission (`:1-6`) และ `build_dispatch()` สร้าง `WAITING_WRITER` ต่อ source article เมื่อไม่มี handoff (`:307-374`)

สถานะวันที่ 2026-09-11 ที่อ่านจาก artifacts จริง:

- source binding `SOURCE_READY`, source QA receipts 4/4 ใน `work/localization/11-09-2026/source-bindings/`
- queue selected: `MY`, `BR`, `NG`
- selected jobs: 12 jobs = 3 ประเทศ x 4 source articles, ทั้งหมด `WAITING_WRITER`
- held: 16 ประเทศ; 6 `NOT_ENROLLED`, 10 `LOCALIZATION_DISABLED`
- runtime backend: พบ project interpreter แต่ยังไม่มี writer execution ที่เรียกจาก daily orchestrator

## 3. To-be และ canonical command

### 3.1 คำสั่งหลักที่เลือก

คำสั่งหลักหลังปรับเสร็จ:

```powershell
cd C:\Users\USER\Desktop\Claude\CC - ที่ปรึกษา\Projects\P002-นักเขียนบทวิเคราะห์\Repo
python -m tools.run_daily --confirm
```

เหตุผลที่เลือก `run_daily`:

- เป็น dispatcher ที่มีอยู่แล้วและเป็นจุดเดียวที่รวม source production, route, guard, selection และ localization dispatch
- ทำให้ผู้ใช้ไม่ต้องเลือกระหว่าง `run_morning` กับ `run_daily` ในคู่มือประจำวัน
- คง `run_morning` ไว้เป็น compatibility/preview adapter โดยให้เรียก shared morning-plan API ไม่ทำ business logic ซ้ำ
- `--confirm` จะเป็น approval gate ของคำสั่งหลักที่ต้องเพิ่มในขั้นที่ 3 โดยต้องคงพฤติกรรม preview แบบไม่เรียก network/ไม่เขียน production เมื่อไม่ยืนยัน

`--write/--watch/--exclude` และ `--date` ของ `run_morning` จะถูกย้ายมาเป็น shared plan input หรือ compatibility flags ตามผลกระทบที่ทดสอบได้ ส่วน source-only และ country-selection flags เดิมต้องคงไว้แบบ explicit สำหรับ developer/test callers และไม่กลายเป็น dependency ของรอบปกติ

หมายเหตุสำคัญ: คำสั่งนี้จะเรียกครบทุก gate ที่มี evidence พร้อมได้ แต่จะรายงาน `PARTIAL`, `WAITING_REVIEW` หรือ `READY_FOR_ADMISSION` เมื่อขาด independent review/admission ที่ถูกต้อง ไม่ลด gate เพื่อบังคับให้ exit 0

### 3.2 Workflow ที่เสนอ

```text
run_daily --confirm
  -> resolve Bangkok business date + run identity
  -> reuse/create approved morning plan
  -> reuse fresh SOURCE_READY binding หรือผลิต Thai source
  -> calculate expected targets from rollout registry (ไม่ hardcode)
  -> for each eligible country/article:
       verify locked pack + source/image/claim hashes
       prepare writer job
       execute only the authorized request/response writer seam
       persist candidate/proposal with writer execution id
       consume existing independent review receipts only
       package verified country
       prepare/apply transaction with lock and recovery journal
       validate human-issued admission
  -> aggregate source/localization/delivery status separately
  -> write country report and run report
```

สิ่งที่ยัง blocked โดยข้อจำกัดปัจจุบัน:

- `co-op-translator` ไม่ทำ translation เองและ config ปิด provider calls
- Luna ตัวเดียวไม่สามารถออก independent semantic/visual review ที่เป็นอิสระจากตนเอง
- admission validator ไม่สร้าง admission record และไม่ควรให้ daily runner เปลี่ยน authority เป็น Luna เอง

ดังนั้น “คำสั่งเดียวจบถึง Output” จะถือว่าผ่านได้ต่อเมื่อมี runtime/reviewer/admitter path ที่ได้รับอนุญาตและมีหลักฐานจริงครบเท่านั้น

## 4. Readiness matrix รายประเทศ

Baseline/pack status อ้างจาก `language/baseline-registry.json` และ routing/policy อ้างจาก registry จริง ไม่ถือว่า locale มีอยู่แล้วแปลว่าพร้อมผลิต

| ประเทศ | locale / pack | baseline | policy / enrollment | writer / reviewer ตอนนี้ | ก่อนเปิดใช้งาน |
|---|---|---|---|---|---|
| MY | `ms-MY` / `ms-MY@0.1.2` | stable_locked | enabled / admitted | writer ใหม่ของรอบ 11 ยังไม่เริ่ม; reviewer รอ writer | run writer + 4-gate independent review |
| BR | `pt-BR` / `pt-BR@0.1.2` | stable_locked | enabled / admitted | writer ใหม่ของรอบ 11 ยังไม่เริ่ม; reviewer รอ writer | run writer + 4-gate independent review |
| NG | `en-NG` / `en-001@0.1.0` | stable_locked | enabled / admitted | writer ใหม่ของรอบ 11 ยังไม่เริ่ม; reviewer รอ writer | run writer + 4-gate independent review |
| AR | `es-AR` / `es-419@0.1.2` | stable_locked | enabled / NOT_ENROLLED | blocked by admission | issue current admission and verify source readiness |
| CL | `es-CL` / `es-419@0.1.2` | stable_locked | enabled / NOT_ENROLLED | blocked by admission | issue current admission and verify source readiness |
| RU | `ru-RU` / `ru-RU@0.2.0` | stable_locked | enabled / NOT_ENROLLED | blocked by admission | issue current admission and verify source readiness |
| MX | `es-MX` / `es-419@0.1.2` | stable_locked | enabled / NOT_ENROLLED | blocked by admission | issue current admission and verify source readiness |
| ZA | `en-ZA` / `en-001@0.1.0` | stable_locked | enabled / NOT_ENROLLED | blocked by current index despite historical complete status | reconcile current admission/index before dispatch |
| SG | `en-SG` / `en-001@0.1.0` | stable_locked | enabled / NOT_ENROLLED | blocked by admission | issue current admission and verify source readiness |
| SA | `ar-SA` / `ar-001@0.1.1` | stable_locked | disabled / NOT_ENROLLED | blocked by policy | user-approved policy enablement, then admission |
| AE | `ar-AE` / `ar-001@0.1.1` | stable_locked | disabled / NOT_ENROLLED | blocked by policy | user-approved policy enablement, then admission |
| CO | `es-CO` / `es-419@0.1.2` | stable_locked | disabled / NOT_ENROLLED | blocked by policy | user-approved policy enablement, then admission |
| KE | `sw-KE` / `sw-KE@0.1.0` | draft | disabled / NOT_ENROLLED | blocked by policy and pack | approve/lock baseline, then policy and admission |
| PH | `fil-PH` / `fil-PH@0.1.0` | draft | disabled / NOT_ENROLLED | blocked by policy and pack | approve/lock baseline, then policy and admission |
| KR | `ko-KR` / `ko-KR@0.1.0` | draft | disabled / NOT_ENROLLED | blocked by policy and pack | approve/lock baseline, then policy and admission |
| IN | `hi-IN` / `hi-IN@0.1.0` | draft | disabled / NOT_ENROLLED | blocked by policy and pack | approve/lock baseline, then policy and admission |
| TR | `tr-TR` / `tr-TR@0.1.0` | draft | disabled / NOT_ENROLLED | blocked by policy and pack | approve/lock baseline, then policy and admission |
| PK | `ur-PK` / `ur-PK@0.1.0` | draft | disabled / NOT_ENROLLED | blocked by policy and pack | approve/lock baseline, then policy and admission |
| BD | `bn-BD` / `bn-BD@0.1.0` | draft | disabled / NOT_ENROLLED | blocked by policy and pack | approve/lock baseline, then policy and admission |

The target remains all 19 foreign countries. Held countries must stay in `expected/held`; they must not be removed to make coverage appear complete. No country is opened by this plan alone.

## 5. Runtime and evidence contract

### Writer

Reuse:

- `tools.translation_adapter.route_for()` for country/language/direction
- `tools.translation_adapter.prepare_markdown_job()` for locked pack, source binding, protected literals and source QA
- `tools.translation_adapter.finish_markdown_job()` for complete chunk set, reconstruction and protected-literal verification
- `tools.translation_job_store.write_prepared_job()` for immutable cache identity and exclusive job lock

The planned writer seam must receive `(country, article, source bytes, source hash, claim/image bindings, pack identity, attempt)` and emit a `p002-localized-writer-production/v1` candidate manifest, candidate Markdown/images and writer proposal with a distinct `writer_execution_id`. A missing callback/runtime must produce `WAITING_WRITER`, not a stub candidate.

No new autonomous agent, background agent, reviewer agent or renamed worker/session is allowed. A request/response provider may be used only if it is already authorized and proven to be non-autonomous; the current routing explicitly does not authorize provider calls.

### Review

Reuse `build_localized_release_handoff.py` and `attach_independent_review_receipts.py`. The runner may collect/verify already-issued receipts, but must not create reviewer identity, PASS receipt, or semantic/visual verdict itself. Required binding is:

```text
source_sha256 + claim_map_sha256 + source image hashes
  -> writer candidate/proposal hash
  -> 4 independent PASS receipts per article
  -> receipt index READY_FOR_PACKAGE_INPUT_REVIEW
```

Self-review and deterministic tests remain separate from independent review.

### Package, transaction and admission

Only reviewed handoffs enter `normal_localization_orchestrator.prepare_verified()` → `update_localized_outputs.prepare_countries_for_delivery()` → `package_localized_country.prepare_country()` → `localization_transaction.apply_transaction()`.

Admission remains a separate authority gate. The runner can validate an existing admission with `localization_admission.validate()`, but cannot create one without an authorized admitter execution. This is a blocker to claiming fully automatic delivery under the current contract.

## 6. Run identity, resume and reporting

The implementation will use:

- `source_business_date`: `Asia/Bangkok` business date, not the destination country date
- `run_id`: immutable invocation identity tied to date, source-binding hash and plan hash
- `source_bindings_sha256`: required for source freshness and candidate reuse
- `candidate_sha256`, `pack_sha256`, `review_receipt_sha256`, `delivery_manifest_sha256`: required at each gate
- `work/localization/DD-MM-YYYY/checkpoints/`: durable state with per-country/per-article states
- OS lock for the daily run plus existing job/transaction locks
- bounded attempts, preserving attempt count across repeated invocations; writer proposal already limits attempts to 1..3
- same command rerun: resume only missing/failed eligible work; do not rewrite completed delivery
- source change: create a new source-binding identity and invalidate candidate/review reuse from the old hash
- process interruption: recover from checkpoint/journal; never infer completion from a partial tree
- concurrent invocation: one claims the run; the other reports busy/resume state

The report must keep these dimensions separate:

```text
source: READY / FAILED / HELD
localization: expected / eligible / writer / review / package
delivery: prepared / committed / admitted / held / failed / pending
```

For 4 source articles and 19 foreign targets, expected count is derived at runtime as `len(source_articles) x len(target_countries)`, not hardcoded. On 2026-09-11 the observed target would be 76 foreign article jobs, with 12 selected and 64 held, but that number is evidence for the report only, not an implementation constant.

## 7. Patch plan

| ลำดับ | ไฟล์:function | สิ่งที่จะเปลี่ยน | dependency / ผลกระทบ | tests | rollback |
|---|---|---|---|---|---|
| P0 | `tools/morning_plan.py` ใหม่; `run_morning.py`, `run_daily.py` callers | แยก plan/confirm/ownership เป็น API ร่วม; `run_daily --confirm` เป็น canonical; `run_morning` เป็น adapter | ย้าย logic โดยคง schema/preview/approval เดิม | morning parser/approval/caller regression | restore only these files and keep plan artifacts |
| P1 | `tools/run_daily.py:main` และ dispatch boundary | เพิ่ม phase/state orchestration และ aggregate reporting; ไม่ให้ success จบที่ queue | กระทบ exit code และ legacy flags | run_daily contract, source-only, selection, dry-run | revert P1 patch; existing tools remain usable |
| P2 | `tools/normal_localization_orchestrator.py` | เปลี่ยนจาก dispatch-only เป็น resumable coordinator ที่เรียกเฉพาะ runtime ที่มีสิทธิ์; คง hold states | ใช้ queue/source binding/handoff เดิม; ห้าม bypass gates | waiting, resume, source hash, concurrency, partial country failure | disable coordinator flag and use old dispatch receipt path |
| P3 | `tools/localization_writer_runtime.py` ใหม่; `translation_adapter.py`, `translation_job_store.py` | ทำ writer request/response seam, candidate manifest/proposal และ bounded retry; ไม่สร้าง autonomous agent | ต้องมี authorized callback/runtime; ถ้าไม่มีให้ HOLD | fixture writer, literal/image/hash mismatch, retry exhaustion, idempotency | remove new runtime registration; preserve prepared jobs |
| P4 | `build_localized_release_handoff.py`, `attach_independent_review_receipts.py` | เชื่อม handoff/review receipt ที่ออกแล้วเข้ากับ state machine; ไม่สร้าง PASS | reviewer evidence ต้องเป็น external/distinct | receipt coverage, stale hash, self-review rejection | stop at HOLD and retain handoff bytes |
| P5 | `update_localized_outputs.py`, `package_localized_country.py`, `localization_transaction.py`, `localization_admission.py` | เรียก package/prepare/apply อย่างมี lock; validate admission; เพิ่ม explicit `READY_FOR_ADMISSION` | ห้าม auto-author admission โดยไม่มี authority | transaction recovery, duplicate apply, marker/hash, output conflict | transaction recovery using journal; no deletion |
| P6 | reporting module/schema and docs | สร้าง per-country report, expected count, blocker, implemented/tested/live separation; อัปเดต README/command guide | ผู้ใช้เห็น partial จริง ไม่ถูกนับ held เป็น complete | report schema and exit-code matrix | docs-only rollback |

Luna จะทำทีละ P0→P6 และตรวจผลย่อยหลังแต่ละ patch ไม่แตก Sub Agent และไม่ใช้ parallel worktree

## 8. Test matrix และ acceptance criteria

### Unit/static

- registry exact 20 / foreign 19 / policy mapping / locale-pack identity
- `run_daily --confirm` และ preview ไม่เรียก production เมื่อไม่ confirm
- source freshness, source hash change, protected literals, images and claim maps
- retry budget, attempt persistence, lock/double invocation and immutable dispatch
- held countries remain in expected and reports

### Mock/fixture integration

- fake writer request/response produces candidate only with complete chunks
- independent fixture receipts are consumed only when writer/source/candidate hashes match
- review missing, review self-issued, wrong gate, stale receipt and incomplete image coverage remain HOLD
- package → transaction prepare/apply/recover; duplicate apply is idempotent
- one country failure does not hide or remove other countries
- Thai and MY/BR/NG backward compatibility

Fixture results must be labeled mock/fixture and cannot be reported as independent live review.

### Non-publishing live verification (ขั้นที่ 4 เท่านั้น)

- use the existing locked P002 translation environment only
- verify provider-free chunking/reconstruction without production publish
- run only countries/runtime/credentials explicitly available within existing authority and budget
- verify real writer/reviewer evidence separately; if unavailable, report UNVERIFIED
- never upload CMS/social, provision service, or expose secrets

### Acceptance criteria

1. One documented daily command maps to one workflow and runs from the documented Repo directory.
2. Normal invocation does not stop at `WAITING_WRITER` when an authorized writer path is actually available.
3. No translation/review/package/admission PASS is fabricated by Luna or a deterministic wrapper.
4. Source/candidate/pack/review/image hashes remain bound through delivery.
5. Repeated/concurrent invocation does not duplicate writer, package or admission.
6. `expected`, `eligible`, `held`, `completed`, `failed`, and `pending` remain distinct.
7. Thai behavior and existing MY/BR/NG behavior are preserved.
8. Full “single command to completed delivery” is marked **BLOCKED/PARTIAL** unless independent review and admission evidence are genuinely available.

## 9. Rollback and safety

- Do not use `git reset`, `clean`, `stash` or broad delete; current 95 dirty files remain user-owned.
- Keep a patch manifest listing only files changed by this implementation.
- Roll back only the patch files after user/CC approval; do not overwrite unrelated dirty changes.
- For an interrupted delivery, use `localization_transaction.recover_transaction()` and journal evidence; do not delete existing Output.
- Preserve prior Output, receipts, source bindings and transaction backups. Rollback of code/config must not erase delivered artifacts.
- External publishing remains disabled (`publishing_policy.json`: `manual_only: true`, `external_publish: false`).

## 10. Blockers and decision boundary

The implementation can safely begin with P0/P1 state/reporting work and fixture tests. Full automatic completion is blocked until the user/authorized system supplies or approves:

1. an actual writer execution path that can produce translations under the provider-free/no-subagent rule;
2. an independent reviewer path that issues valid receipts distinct from Luna/writer;
3. an authorized admission actor or an explicit decision to keep admission manual;
4. policy/enrollment and locked baseline approvals for the 16 held countries.

No patch in the next step may silently treat these blockers as resolved. The status must remain `PARTIAL` or `BLOCKED` when evidence is absent.

## 11. Readiness for step 3

เริ่มได้ที่ P0 และ P1: shared morning plan, canonical command contract, run identity/state/report schema และ regression tests โดยยังไม่เปิดประเทศ ไม่เรียก provider และไม่สร้าง Output ใหม่

P2–P5 ต้องทำแบบ fail-closed ตาม blocker ข้างต้น ส่วนการทดสอบ live/non-publishing และการสรุปส่งมอบเป็นงานขั้นที่ 4–5 ตามลำดับ

การใช้ agent: **Luna ตัวเดียว / Sub Agent ที่เรียก: 0**
