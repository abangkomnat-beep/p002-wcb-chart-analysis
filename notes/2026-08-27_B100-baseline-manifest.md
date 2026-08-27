---
title: B100 Steps 1–2 baseline manifest
description: หลักฐาน main/worktree baseline และ hash guard ก่อนออกแบบ Adaptive Stop B100
tags: [P002, BTCUSD, E-plus, adaptive-stop, B100, baseline]
---

# B100 Steps 1–2 — Baseline Manifest

วันที่ตรวจ: 2026-08-27  
สถานะ: `BASELINE_LOCKED / MAIN_UNCHANGED / WORKTREE_READY`

## Root และ Git identity

- workspace: `C:\Users\USER\Desktop\Claude\CC - ที่ปรึกษา`
- main repo: `Projects/P002-นักเขียนบทวิเคราะห์/Repo`
- main branch: `main`; HEAD=`3dbdf1f41d69fd5269d0c8204cf62f411af058eb`; upstream=`origin/main`; ahead=`5`
- main staged diff: empty
- main status ก่อนเขียน note: มีเฉพาะ research untracked 2 ไฟล์ด้านล่าง
- dedicated worktree: `Projects/P002-นักเขียนบทวิเคราะห์/work/worktrees/Repo-style-e-plus-adaptive-stop-b100-20260827`
- worktree HEAD=`3dbdf1f41d69fd5269d0c8204cf62f411af058eb`; detached; status ก่อนเขียน note=clean
- worktreeไม่มี research helper/test สองไฟล์ และไม่ได้ copy/import มาจาก main

worktree อยู่ exact committed integration base เดียวกับ main. รอบนี้ไม่สร้าง branch เพราะไม่มี branch name ในมติที่ส่งมาและห้าม commit; ก่อนเริ่ม RED/implementation ให้ Lead ล็อก branch/ref policy เพิ่มโดยไม่เปลี่ยน base

## Research untracked guard บน main

| Path | Bytes | SHA-256 |
|---|---:|---|
| `tools/style_e_plus_adaptive_stop_ab.py` | 62,632 | `EA82447F6C754710DF30E256C8F5F38A0D6B5C3F7E254859361C7F6FFB3683C0` |
| `tests/test_style_e_plus_adaptive_stop_ab.py` | 22,723 | `F46254298242228BFD4FBDB05D436BF1BA77E5A0D9FC47073471EF7E0C5DEA4E` |

Guard: ห้ามแก้, ลบ, rename, stage, commit, import หรือ copy ทั้งไฟล์. ใช้ได้เฉพาะอ่านเพื่อ trace semantics/equivalence ตามแผน

## Committed production blobs ที่ฐานนี้

| Path | Git blob OID |
|---|---|
| `tools/style_e_plus_story.py` | `f63c713d71661641431755bd8ac5d56c5811b7b6` |
| `tools/style_e_plus_writer.py` | `ecd79c614ee43dd6324e64a0c10bfb72b3ee75af` |
| `tools/style_e_plus_renderer.py` | `c9ab6837fae2e544fb66c8fd26e6c2d587affb57` |
| `tools/style_e_plus_pipeline.py` | `100449fc0fa18ade510ed52f73767f897feace22` |
| `tools/style_e_plus_daily.py` | `2907d66fb788679edfd5e2d482c1399eee573f94` |

Git-filtered hashesของ main/worktree ตรงกับ blob OID ทุกไฟล์. Raw SHA-256 บางไฟล์ต่างกันเพราะ checkout EOL normalization (`core.autocrlf=true`); integration/re-baseline จึงใช้ commit+blob OID เป็นหลักฐาน authoritative และใช้ raw SHA-256 เฉพาะ guard ไฟล์ untracked

## Scope guards

- production tracked diff ก่อน note=`0`; staged diff=`0`
- production output, `STATUS.md`, API/network, Bitstamp, credential, payment และ OOS ถูกแตะ=`0`
- commit, push, publish, promote, stash, reset, checkoutทับ main=`0`
- delta ที่อนุญาตใน Steps 1–3 นี้หลัง baseline คือเอกสารใน `notes/` ของ dedicated worktreeเท่านั้น

Post-baseline observation: ระหว่างตรวจท้ายรอบพบ `tests/test_style_e_plus_contract.py` ถูกแก้พร้อมกันหลัง initial clean check. งาน Steps 1–3 นี้ไม่ได้แก้หรือย้อนไฟล์ดังกล่าว; ให้ถือเป็น concurrent drift ที่ต้องรับ handoffและ re-baseline hash/diff ใหม่ก่อนเริ่ม RED/Builder step ถัดไป
