---
title: B100 Step 3 production contract design
description: ล็อก module boundary, adaptive_context 23-row canonical hash, B semantics และ schema v4 migration
tags: [P002, BTCUSD, E-plus, adaptive-stop, B100, contract-gate]
---

# B100 Step 3 — Production Contract Design

วันที่: 2026-08-27  
ฐานออกแบบ: `3dbdf1f41d69fd5269d0c8204cf62f411af058eb`  
สถานะ: `CONTRACT_DESIGN_LOCKED / CODE_NOT_STARTED / PRODUCTION_UNCHANGED`

## 1. Module boundary ที่เลือก

เลือกสร้าง production-owned pure helper **หนึ่งไฟล์**:

`tools/style_e_plus_adaptive_stop.py`

ขอบเขตของ helper:

- standard-library only; ไม่มี I/O, network, clock, renderer, pipeline, broker หรือ output side effect
- ไม่ import และไม่ copy ทั้งไฟล์ `style_e_plus_adaptive_stop_ab.py`
- เป็นเจ้าของ constants/geometry B, canonical context validation/hash และ sizing multiplier
- รับข้อมูล explicit แล้วคืน deterministic dict; exception เป็น contract error ไม่ fallback A
- `style_e_plus_story.build()` สร้าง contextและเรียก helper
- `style_e_plus_story.validate_story()` ตรวจ context/hashแล้วเรียก helperซ้ำจาก context จากนั้นเทียบ derived fieldsทั้งหมด
- writer/renderer/pipeline/daily ห้ามคำนวณ pivot, Donchian, Stop, TP, reason หรือ sizing ใหม่; ต้องเรียก `validate_story()` แล้วอ่านค่าที่ผ่านเท่านั้น

เหตุผล: แยก pure geometry ออกจาก orchestration/schema ทำให้ build+validatorใช้ implementationเดียวกัน, unit/equivalence testได้ตรงจุด และตัด dependencyจาก research plotting/replay codeโดยเด็ดขาด

## 2. Canonical `adaptive_context`

Story v4 ต้องมี object นี้ทุก state เพื่อให้ validatorพิสูจน์ decision prefixได้:

```json
{
  "schema": "style-e-plus-adaptive-context/v1",
  "timeframe": "15min",
  "candle_state": "closed",
  "count": 23,
  "window": {
    "start_at": "<UTC decision-22>",
    "decision_at": "<UTC decision>"
  },
  "rows": [
    {"at": "<UTC>", "open": "<decimal>", "high": "<decimal>", "low": "<decimal>", "close": "<decimal>"}
  ],
  "sha256": "<64 lowercase hex>"
}
```

Contract:

- rows exactly 23: source indices `decision−22..decision`; rowสุดท้ายตรง `story.m15_bar_at`
- timestamps UTC `YYYY-MM-DDTHH:MM:SSZ`, ascending, unique, ห่างกัน exactly 900 seconds
- OHLC only; ไม่มี volume, forming/future row, absolute path, source secret หรือ OOS field
- numeric fieldsเป็น canonical decimal strings: `Decimal(str(value))`, finiteเท่านั้น, `-0`→`0`, fixed-point, ตัด trailing zerosและจุดท้าย; ห้าม JSON float/NaN/Infinity
- exact object keysเท่าที่ระบุ; unknown/missing key fail closed
- `count` ต้องเท่ากับ `len(rows)`; `window.start_at=rows[0].at`; `window.decision_at=rows[22].at`
- `candle_basis.m15` ต้องพิสูจน์ว่า decision rowปิดแล้ว; เมื่อ last rowปิด rowsก่อนหน้าจึงเป็น closed prefix

Hash scope คือทุก fieldของ `adaptive_context` ยกเว้น `sha256`:

```text
payload = {schema,timeframe,candle_state,count,window,rows}
bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":"), allow_nan=False).encode("utf-8")
sha256 = hashlib.sha256(bytes).hexdigest()
```

validatorต้อง canonicalizeจากค่าที่ได้รับแล้วเทียบ exact representationก่อน hash; ห้าม hashเฉพาะ derived values. การแก้ row/order/count/window/hashหนึ่งจุดต้อง failก่อน writer/renderer/package

## 3. Exact B semantics

Constants:

```text
pivot_left=2; pivot_right=2; pivot_lookback=20
structure_buffer_atr=0.25
risk_floor_atr=2.0; risk_cap_atr=3.0
donchian_length=20; target_space_min_r=1.5
tp1_r=1.5; tp2_r=2.0
baseline_max_risk_atr=1.5; tolerance=1e-12
```

Pseudocode บน context indices `0..22`, decision=`22`:

```text
if H1 side is None: NO_PLAN, adaptive evaluated=false, reason_code=null
derive unchanged EMA20 trigger/entry zone
if close already beyond entry zone: NO_CHASE, no plan, adaptive evaluated=false

candidate indices = 20,19,...,2  # decision-2 latest through decision-20 inclusive
BUY pivot: low[i] strictly lower than low[i-2],low[i-1],low[i+1],low[i+2]
SELL pivot: high[i] strictly higher than the four neighbors
ties are never pivots; first candidate found is the confirmed pivot
if none: NO_PLAN + NO_CONFIRMED_SWING

entry = zone_high for BUY, zone_low for SELL  # disadvantaged edge
raw_stop = pivot.low - 0.25*ATR for BUY; pivot.high + 0.25*ATR for SELL
raw_risk = entry-raw_stop for BUY; raw_stop-entry for SELL
if raw_risk <= 0: NO_PLAN + NO_CONFIRMED_SWING
raw_risk_atr = raw_risk/ATR
if raw_risk_atr > 3.0 + tolerance: NO_PLAN + STOP_GT_3ATR
if abs(raw_risk_atr-2.0) <= tolerance: risk_atr=2.0
elif abs(raw_risk_atr-3.0) <= tolerance: risk_atr=3.0
else: risk_atr=max(raw_risk_atr,2.0)
floor_applied = raw_risk_atr < 2.0
risk = risk_atr*ATR
stop = entry-risk for BUY; entry+risk for SELL

donchian rows = indices 2..21  # decision-20..decision-1, exactly 20, decision excluded
boundary = max(high) for BUY; min(low) for SELL
space = boundary-entry for BUY; entry-boundary for SELL
if space + tolerance < 1.5*risk: NO_PLAN + TARGET_SPACE_LT_1_5R

if current close crosses accepted B pre-entry invalidation: NO_PLAN, plan=null
otherwise state = ENTRY_READY when close confirms unchanged EMA20 rule, else WAIT_TRIGGER
tp1 = entry +/- 1.5*risk; tp2 = entry +/- 2.0*risk
sizing_multiplier = 1.5/risk_atr
normalized_risk_ratio = sizing_multiplier*risk_atr/1.5
```

ทุก accepted planต้องมี `2.0<=risk_atr<=3.0`, multiplier `0.50..0.75` และ normalized ratio `<=1.0+tolerance`. multiplierเป็น dimensionless fractionของ baseline reference sizeเท่านั้น; ห้าม BTC/lot/USD/% quantity และห้ามสื่อว่าเกิด Fill/Position/active Stop

Machine reason fieldเดียวคือ `adaptive_reason_code` มีค่า `null`, `NO_CONFIRMED_SWING`, `STOP_GT_3ATR` หรือ `TARGET_SPACE_LT_1_5R`. Adaptive rejectบังคับ `state=NO_PLAN`, `plan=null`; ไม่มี A fallback/feature flag/traffic split

## 4. Story v4 fields และ recomputation

Schema IDs ที่ล็อก:

- story=`style-e-plus-story/v4`
- manifest=`style-e-plus-manifest/v4`
- source snapshot=`style-e-plus-source-snapshot/v2`
- adaptive context=`style-e-plus-adaptive-context/v1`

Story v4 เพิ่ม:

- `adaptive_context` ตามหัวข้อ 2
- `adaptive_reason_code`
- `adaptive_stop`: `evaluated`, `accepted`, pivot index/time/price, raw stop/risk ATR, final stop/risk ATR, floor flag, Donchian boundary/space R, constants version
- accepted `plan`: `variant=B`, final Stop/TP, `sizing_multiplier`, `normalized_risk_ratio`, `sizing_basis=baseline_reference_size`, `manual_only=true`

validator recomputeตามลำดับ: context shape→canonical/hash→H1 side/entry zone→B geometry/reason→state/lifecycle→plan/Stop/TP/sizing. ทุก numeric compareใช้ `rel_tol=0`, `abs_tol=1e-12`; context string/hash compare exact. derived-only v4, missing context, tamper, future row หรือ A-shaped planต้อง fail closed

Pipeline snapshot v2 เก็บ source rowsเดิมแบบ closed-onlyพร้อม `adaptive_context_sha256`, count/window และ B parameter contract. Manifest v4 เก็บ story/snapshot schema IDs, context SHA-256, policy=`adaptive-stop-b100-no-fallback`, runtime commit และ file hashes. Source snapshotยังเป็น input replay; contextใน rebuilt storyต้อง hashตรง manifest

## 5. v4 migration และ pinned-v3 replay policy

- v4 runtimeสร้าง/รับเฉพาะ story v4 + snapshot v2 + manifest v4; ห้าม auto-upgradeหรือ rewrite v3 artifact
- v3 packageทั้งหมด immutable และ current v4 runtimeต้อง rejectด้วยคำอธิบายให้ใช้ pinned runtime
- pinned A/v3 runtime commit=`3dbdf1f41d69fd5269d0c8204cf62f411af058eb`
- replay v3 ต้องใช้ detached read-only worktreeจาก commitนี้และ generic offline reproduce commandของ commitนั้น; network/output productionยังปิดและ output pathต้องเป็น quarantine/tempที่ได้รับอนุมัติ
- migration manifest v4 ต้องบันทึก `previous_schema=v3`, pinned commit, reproduce command และ baseline blob OIDsจาก baseline note
- ไม่มี dual A/B runtimeและไม่มี fallback: artifact versionเลือก runtimeเพื่อ auditเท่านั้น ไม่เลือก production behavior

## 6. File boundary และ Gate

Expected production diffภายหลัง Contract Gate:

- new `tools/style_e_plus_adaptive_stop.py`
- `tools/style_e_plus_story.py`
- `tools/style_e_plus_writer.py`
- `tools/style_e_plus_renderer.py`
- `tools/style_e_plus_pipeline.py`
- `tools/style_e_plus_daily.py` เฉพาะ propagationที่ testsพิสูจน์ว่าจำเป็น
- focused testsตาม allowlistและ helper testใหม่

ห้ามแตะ research untracked, `run_daily.py`, publish selection, style registry, XAUUSD/USDJPY/Style D, production output, `STATUS.md`, API/OOS หรือ external systems. เอกสารนี้ยังไม่อนุญาต code/test implementation; ขั้นถัดไปต้องเริ่ม RED testsตาม Step 4–6 และผ่าน Contract Gate handoffก่อน Builderแก้ production
