# P002 Shadow Quality Scoring Runbook

ระบบนี้รับ judgment ของ Agent 05 แล้ว validate/คำนวณคะแนนแบบ deterministic ผลลัพธ์ทั้งหมดเป็น
internal sidecar ใต้ QA root เท่านั้น ค่า `mode=shadow` หมายความว่า `PASS_SCORE`,
`REVISION_REQUIRED` และ `ESCALATE_FOR_REVIEW` **ไม่มีผลต่อ publish selector, scheduler หรือ public
output** การเปิด blocking ต้องผ่าน calibration และการอนุมัติแยก

## ติดตั้งและตรวจ environment

รองรับ Python 3.11+ และ dependency อยู่ใน `requirements.txt` รุ่นที่ยืนยันกับชุดทดสอบนี้คือ
`jsonschema 4.26.0`; manifest กำหนด floor `jsonschema>=4.26`

```bash
python -m pip install -r requirements.txt
python -c "import importlib.metadata; print(importlib.metadata.version('jsonschema'))"
```

## Input contract

หนึ่งไฟล์ JSON คือ judgment input หนึ่งบท/หนึ่ง attempt และต้องมี:

- `job_id`, `article_id`: portable single path segment ห้าม `.`, `..`, slash, backslash, drive,
  absolute/UNC และ percent-encoded path variants
- `attempt`: 1–3; `producer`: `agent-05-article-qa`
- `input_hashes`: exact lowercase SHA-256 ของ `article`, `brief`, `evidence` เท่านั้น
- `hard_gates`: `{passed, failures}` และ `brief_compliance`: `{passed, missing}`
- `visual_applicability`: `content_only`, `optional_attached`, `required_attached` หรือ
  `required_missing`
- `criterion_judgments`: criterion ตาม `config/quality_scoring.json`; แต่ละรายการมี `score`
  0–100 และ `evidence` ที่ไม่ว่าง
- `findings`: criterion ที่ต่ำกว่า 85 ต้องมี finding ซึ่งมี exact fields `priority`, `criterion`,
  `location`, `issue`, `evidence`, `why_it_matters`, `how_to_fix`, `owner`
- `created_at` ถ้าระบุ ต้องเป็น ISO 8601 date-time ที่มี timezone

Hard gate fail, brief incomplete และ required visual missing มี precedence และไม่สร้างคะแนน

## Single และ batch scoring

คำสั่งเดียวรองรับทั้งสองแบบและไม่เรียก network:

```bash
# single
python -m tools.quality_scoring qa-input/job-01.json --output-root qa/quality-score

# batch (สูงสุดที่พิสูจน์ใน rollout นี้ 50 input files ต่อ invocation)
python -m tools.quality_scoring qa-input/job-*.json --output-root qa/quality-score
```

แต่ละงานเขียนแบบ atomic ที่
`<output-root>/<job_id>/<article_id>/attempt-NN/evaluation.json` งานเสียคืนรายการ
`status=error` โดยไม่ลบงานที่ผ่าน Summary stdout มี `total`, `succeeded`, `failed`, `results`;
process exit 0 เมื่อทุก input สำเร็จ และ 1 เมื่อมี error อย่างน้อยหนึ่งงาน Duplicate identity ถูก reject
ขีดจำกัด 50 เป็นเพียง batch bound ที่ทดสอบแล้ว ไม่ใช่ production SLA

## Human-readable summary

รองรับทั้ง direct script และ module form โดย renderer validate JSON Schema และ replay calculation ก่อนแสดง:

```bash
python tools/quality_summary.py qa/quality-score/job-01/article-01/attempt-01/evaluation.json --output score.md
python -m tools.quality_summary qa/quality-score/job-01/article-01/attempt-01/evaluation.json --output score.md
```

Envelope ปลอม, score นอกช่วง หรือ status/calculation ไม่ coherent จบด้วย non-zero exception และไม่ควร
นำ Markdown ที่ค้างจากรอบก่อนมาใช้

## Revision brief และ append-only history

สองขั้นนี้เป็น library API เพื่อบังคับ hash/identity binding:

```python
import json
from pathlib import Path
from tools.quality_scoring import append_history, make_revision_brief

evaluation = json.loads(Path("evaluation.json").read_text(encoding="utf-8"))
revision = make_revision_brief(evaluation, article_hash=evaluation["input_hashes"]["article"])
history_path = Path("quality-attempt-history.json")
history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else None
updated = append_history(history, evaluation)
```

ผู้ประสานงานต้อง serialize `revision` ตาม `revision-brief-v1.schema.json` และ `updated` ตาม
`quality-attempt-history-v1.schema.json` ไปไฟล์ใหม่/atomic ในพื้นที่ QA ห้าม overwrite attempt เดิม
History ต้องคง job/article เดิม, attempt ต่อเนื่อง, article hash ใหม่ทุกครั้ง และ timestamp ที่มี timezone
Attempt ที่สี่ถูก reject; attempt สามที่ยังต่ำกว่าเกณฑ์เป็น `ESCALATE_FOR_REVIEW` Agent 05 ห้ามแก้
article/image/source เอง

## Verification และ batch-50 drill

```bash
python -m pytest -q tests/test_quality_scoring.py tests/test_quality_scoring_schemas.py \
  tests/test_quality_scoring_batch.py tests/test_quality_scoring_packaging.py \
  tests/test_run_morning.py tests/test_wcb_writers.py
python -m py_compile tools/quality_scoring.py tools/quality_summary.py
git diff --check
```

`test_fifty_jobs_are_isolated_complete_and_atomic` คือ bounded batch-50 drill: ต้องได้ 50 outputs,
50 unique identities, 0 lost/cross-job และ 0 temporary residue

## Rollback protocol

Rollback นี้ไม่ publish และไม่ลบ evidence:

### ก่อน merge/promotion

1. หยุด candidate ไว้บน branch/worktree เดิมและบันทึก `git status --short`, `git diff --name-only`
   และผล focused suite ลง release evidence
2. Mark candidate เป็น `ABANDONED_PRE_MERGE` ใน release handoff; main ไม่เคยเปลี่ยนจึงไม่มี code
   restoration
3. เก็บ worktree, test report และ QA artifacts แบบ read-only จนผู้ใช้/CC อนุมัติวิธี archive แยก
4. พิสูจน์ด้วย `git -C <main-repo> status --short` ว่า main ไม่มี candidate changes

### หลัง promotion ที่ได้รับอนุมัติ

1. ระบุ single-purpose promotion commit ด้วย `git log --oneline --decorate -n 10` และบันทึก SHA
2. สร้าง rollback commit ด้วย `git revert <promotion-sha>` บน branch ที่ได้รับอนุญาต; review diff ให้มีเฉพาะ
   quality-scoring/author change set
3. รัน focused suite ในหัวข้อ Verification และยืนยัน WTI author/publish behavior ตาม baseline ที่อนุมัติ
4. ส่ง rollback commit + test evidence ผ่าน Tester/Release/QQ ก่อนการ promote/push/publish ใด ๆ

ห้ามใช้ `git reset --hard` และห้ามลบ worktree เพื่อ rollback ขั้นตอนใด ๆ การ push, publish, scheduler
และ external action ต้องมีอำนาจ/approval แยกเสมอ
