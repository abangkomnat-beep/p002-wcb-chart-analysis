# P002 WCB Chart Analysis

Private source repository สำหรับระบบนักเขียนบทวิเคราะห์ WorldClassBroker ที่ใช้กราฟเป็นหลัก รองรับ XAU/USD, Forex และ Crypto ในระยะแรก

## สถานะ

ระบบเดินครบวงจรแล้ว — ดึงข้อมูล → ตรวจ → ดึงข่าว → วาดกราฟ → เขียนบทความ 3 สไตล์ → ตรวจทีละสไตล์
→ วางลงโครงที่หยิบไปอัปได้ · ชุดเทส 462 ตัว

**ยังไม่นำบทความไปเผยแพร่จริง** — ไม่ใช่เพราะระบบไม่พร้อม แต่เพราะยังไม่มีแหล่งข้อมูลที่ยืนยันสิทธิ์
เผยแพร่ได้ ด่านสิทธิ์จึงคง `approved-internal-only` ทุกครั้ง (ดูหัวข้อข้อจำกัดท้ายไฟล์)

## ข้อกำหนดก่อนรัน

แหล่งข้อมูลราคาคือ **WCB series API** (`api/md?kind=series`) เรียกผ่าน HTTP ธรรมดา
**ไม่ต้องใช้รหัสเข้าถึง ไม่ต้องติดตั้งโปรแกรมเพิ่ม และรันได้ทุกระบบปฏิบัติการ**
ครอบคลุมครบทั้งสี่หัวข้อ `xauusd` · `eurusd` · `btcusd` · `nvda`

**MetaTrader 5 ถูกถอดออกทั้งระบบเมื่อ 2026-08-05** — ไม่มี dependency ที่ผูกกับ
แพลตฟอร์มเหลืออยู่ ผู้รับ repo ไม่ต้องเปิดบัญชีโบรกและไม่ต้องอยู่บน Windows

แหล่งข้อมูลไม่พร้อมหรือข้อมูลค้างเก่า = **สายท่อหยุดสินทรัพย์นั้นและไม่เขียนบทความ**
ไม่มีการสลับไปแหล่งอื่นเองเงียบ ๆ

ชั้นตรวจข้อมูล ชั้นภาษา และชุดเทสไม่ต้องต่อเน็ต (เทสใช้ปลายทางปลอม)

## ติดตั้งและรัน

> รอบใช้งานจริงให้เริ่มจากคำสั่งเช้า (preview ก่อนเสมอ):
> [`docs/MORNING-EDITORIAL-COMMAND-SPEC.md`](docs/MORNING-EDITORIAL-COMMAND-SPEC.md)

```bash
python -m tools.run_morning --write eurusd --watch usd
python -m tools.run_morning --write eurusd --watch usd --confirm
```

คำสั่งแรกแสดงแผนโดยไม่เรียก API/เขียนไฟล์ คำสั่งที่สองยืนยันการผลิต โดยระบบเติม
`xauusd` ให้อัตโนมัติและไม่ผลิตสินทรัพย์อื่นนอก `--write`

```bash
pip install -r requirements.txt          # matplotlib/pillow สำหรับกราฟเท่านั้น
python -m pytest tests -q                # canonical full suite; ระบุ tests/ เพื่อไม่เก็บ nested worktrees
python -m tools.run_integrity_report --output-dir ../work/integrity-run   # ยิงด่านตรวจใส่ชุดข้อมูลที่มี
python -m tools.pilot_generator --asset eurusd --output-dir ../work/pilot  # สร้าง snapshot + กราฟ + ผลด่านตรวจ

# สายท่อรายวันครบสี่หัวข้อ — ดึงจาก WCB series API
python -m tools.build_daily_package --asset xauusd --asset eurusd --asset btcusd --asset nvda \
    --batch-id 2026-08-05T09-00Z-daily-market

python -m tools.news_source --asset xauusd   # ทดสอบชั้นข่าวแยกจากสายท่อ
```

### ตาราง Forex Style L — 10 บทต่อสัปดาห์

เมื่อรัน `python -m tools.run_daily` หรือ `python -m tools.run_daily --style L`
โดยไม่ระบุ `--asset` ระบบเลือกคู่เงินตามเวลา `Asia/Bangkok` และส่งสองคู่ของวันนั้นเข้า
`run_round()` เพียงครั้งเดียว:

| วัน | คู่เงินใน batch เดียวกัน |
|---|---|
| จันทร์ | EURUSD + USDJPY |
| อังคาร | GBPUSD + AUDUSD |
| พุธ | EURUSD + USDJPY |
| พฤหัสบดี | GBPUSD + USDCAD |
| ศุกร์ | EURUSD + USDJPY |

รวม 10 บทต่อสัปดาห์ โดยหนึ่ง batch ใช้ calendar request ร่วม 1 ครั้งและ market-data
request 5 ครั้งต่อคู่ รวม nominal 11 requests/วัน หรือ 55 requests/สัปดาห์
เสาร์–อาทิตย์ข้าม Style L อัตโนมัติ ส่วน `--asset` ยังใช้รันงานเฉพาะกิจตามคู่ที่ระบุได้

ตารางเป็น schema v2 แบบ fail-closed: หาก schema, timezone, วัน, จำนวนคู่ หรือลำดับคู่
ไม่ตรง contract ระบบหยุดก่อนเรียกข้อมูลตลาดและก่อนเขียน output และถ้าคู่ใดคู่หนึ่งตก QA
จะไม่มีไฟล์ของทั้ง batch เข้า web-import สำหรับวันพฤหัสบดี USDCAD ยังคงสร้างเฉพาะ
staging/evidence พร้อมสถานะ `HOLD_UNREGISTERED_ASSET`; เมื่อทั้ง batch ผ่าน มีเฉพาะ GBPUSD
ที่เข้า web-import จนกว่า WCB จะมี tag/route ของ USDCAD

ธงที่เกี่ยวกับแหล่งข้อมูลของ `build_daily_package`:

| ธง | ความหมาย |
|---|---|
| _(ไม่ระบุ)_ | WCB series API — ทางหลักของทุกหัวข้อ |
| `--source wcb` | ระบุแหล่งเดียวกันแบบชัดเจน |
| `--source yahoo` | ทางสำรอง ต้องสั่งเอง ใช้ไม่ได้กับ XAU (Yahoo มีแต่ฟิวเจอร์ส `GC=F`) |
| `--snapshot <ไฟล์>` | ป้อนข้อมูลจากไฟล์ (ใช้กับเทสและการทำซ้ำผลเก่า) |
| `--max-bar-age-days` | ผ่อนเพดานอายุแท่งของด่านความสด — ใช้เฉพาะกรณีวันหยุดยาวจริงและต้องระบุเหตุผล |
| `--no-news` | ไม่ดึงข่าว ได้บทความแบบระยะ 1 ที่ไม่มีช่วง ② ปัจจัยจับตา |
| `--no-trade-plan` | ข้ามสาขาแผนการเทรดฝั่ง internal — บทความและกราฟไม่เปลี่ยน |

## แผนการเทรดฝั่ง internal (สาขาข้าง)

`tools/trade_plan.py` ประกอบแผนจากระดับที่อนุมัติแล้ว → `tools/risk_auditor.py` ตรวจแล้วออกใบสั่งแก้

| ไฟล์ | เนื้อหา |
|---|---|
| `internal/trade-plan.json` | แผนหนึ่งชุด (schema: `schemas/trade-plan-v1.schema.json`) |
| `internal/risk-audit.json` | ผลด่านความเสี่ยง + คะแนน 1–10 + กฎที่ตรวจไม่ได้รอบนี้ |
| `internal/revision-order.json` | ใบสั่งแก้ — ทุกข้อบอก **ค่าที่ควรเป็น** ไม่ใช่แค่ว่าผิดตรงไหน |
| `internal/rejected-plan/` | แผนที่ถูก veto (`verdict: block`) — ไม่ออกจากระบบ แต่เก็บให้ตรวจย้อนได้ |

**ข้อจำกัดและกติกาที่ผูกพัน (มติผู้ใช้ 2026-08-04):**

- **ไฟล์แผนอยู่ฝั่ง internal ทั้งหมด** — ตัวเลขจุดเข้า จุดตัดขาดทุน เป้าหมาย และอัตราส่วน เล่าในบทความสไตล์ ② ได้ (ผู้ใช้ปลดมติข้อ 14ก เมื่อ 2026-08-04) · เกณฑ์ว่าแผนไหนพูดได้อยู่ที่ `writers.plan_for_public()` ที่เดียว และภาษาต้องเป็นเงื่อนไขระดับวันเท่านั้น — ดู Contract ข้อ 3ก
- **ด่านรับเฉพาะผลตรวจ `pass`** (ตั้งแต่ 2026-08-05) และ `trade_plan` เลือกจุดตัดขาดทุนกับเป้าหมายที่ผ่านเกณฑ์ตั้งแต่ต้นทาง หาไม่เจอ = `no_trade` ⇒ ที่ค่าเกณฑ์ที่ล็อกไว้ มีแผนผ่านราว **22% ของวัน** · **บทความราวสี่ในห้าฉบับจึงไม่มีหัวข้อแผน และนั่นคือพฤติกรรมที่ถูก ไม่ใช่บั๊ก**
- **แผนล้มไม่หยุดสายท่อ** เหมือนข่าว — บทความยังออกครบ เหตุผลบันทึกที่ `internal/trade-plan-error.json`
- **ข้อมูลรายวัน (D1) เท่านั้น** ⇒ ได้ `daily_scenario` ไม่ใช่ `trade_setup` · แผนเป็นเงื่อนไขระดับวัน ไม่ใช่จุดเข้า intraday
- **ค่าเกณฑ์อยู่ที่ `config/risk_thresholds.json` · ผู้ใช้ล็อกแล้ว 2026-08-05** — `minimum_rr` = **1.2** (แผนผ่านด่าน 22% ของวัน อยู่กลางกรอบเป้าหมาย 20–40%) · `minimum_stop_atr` = 1.0 · `maximum_entry_atr` = 2.0 · ทางเลือกอื่นที่วัดไว้: RR 1.0 → 27% · 1.1 → 24% · 1.3 → 20% · 1.5 → 14% · **ห้ามแก้ค่าโดยไม่ผ่านผู้ใช้ และห้ามแก้เพื่อให้แผนออกบ่อยขึ้น** · หลักฐาน: `work/phase4-measure/` · ผลวัดเต็ม: `01-CC/Output/2026-08-05_ผลวัดระยะ4-เกณฑ์ความเสี่ยง-P002.md`
- **จุดตัดขาดทุนไกลกว่าเดิมราวสามเท่า** (จาก ~0.4 เป็น ~1.2 ATR) หลังเปลี่ยนวิธีเลือกเมื่อ 2026-08-05 — ผู้ใช้รับทราบและอนุมัติแล้ว · แลกกับอัตราส่วนที่ไม่ถูกบีบด้วยจุดตัดขาดทุนที่แคบเกินจริง

## ชั้นข่าวของช่วง ② ปัจจัยจับตา

ลำดับแหล่งตั้งไว้ที่ `config/news_sources.json` — ไล่ลงจนกว่าจะได้ข่าวที่ใช้ได้:

| ลำดับ | แหล่ง | ต้องมีอะไรถึงจะใช้ได้ |
|---|---|---|
| 1 | **เว็บ WCB ของเรา** | ตั้ง `endpoint` (HTTP) หรือ `local_file` · รูปแบบดูที่ `config/samples/wcb-news-sample.json` |
| 2 | **worldmonitor** | ตัวแปรสภาพแวดล้อม `WORLDMONITOR_API_KEY` หรือชี้ `base_url` ไป instance ที่ self-host เอง |
| 3 | RSS สาธารณะ | ไม่ต้องมีอะไร — ใช้คำค้นใน `assets.<ชื่อ>.rss_query` |

**ข่าวล้มไม่หยุดสายท่อ** ต่างจากราคา — ไม่มีข่าวที่ใช้ได้ = ตัดช่วง ② ทิ้งเงียบตาม Voice Spec
บทความยังออกครบ เหตุผลที่ตัดบันทึกไว้ที่ `internal/news-log.json` ทุกครั้ง

ข่าวจะถูกทิ้งเมื่อ: ขาด `title`/`source`/`link`/`published_at` ข้อใดข้อหนึ่ง · เก่าเกิน 48 ชั่วโมง ·
สำนักข่าวไม่อยู่ในทะเบียน `source_tiers` · จับคู่กับพจนานุกรม `themes` ไม่ได้ · พาดหัวซ้ำกับชิ้นก่อน

> ⚠️ **ไม่มีโค้ดของ worldmonitor อยู่ในรีโปนี้ และห้ามมี** — ตัวเขาเป็น AGPL-3.0 การคัดลอกเข้ามา
> จะทำให้รีโปทั้งก้อนต้องเปิดซอร์สภายใต้ AGPL **มติผู้ใช้ 2026-08-04: ใช้ทาง ก. เท่านั้น คือเรียก
> REST API ที่เขาโฮสต์ไว้** · การชี้ `base_url` ไป instance ที่ self-host เองทำได้ทางเทคนิค
> แต่ยังไม่ได้รับอนุมัติ · อย่าเผลอ vendor โค้ดเขาเข้ามาไม่ว่ากรณีใด

ผลด่านตรวจอยู่ในไฟล์ `<basename>.integrity.json` อ่านที่ `publication_gate.status`
`pass` = ข้อมูลผ่านด่าน · `fail` = ห้ามนำไปเขียนบทความหรือเผยแพร่ พร้อมเหตุผลรายข้อใน `reasons`

## ชั้นตรวจสอบข้อมูล (Data Integrity)

| โมดูล | หน้าที่ |
|---|---|
| `tools/market_calendar.py` | ปฏิทินตลาดต่อชนิดสินทรัพย์ — crypto 24/7 · forex และ spot metal 24/5 · หุ้นสหรัฐตามวันหยุดตลาด พร้อมวันหยุดรายชนิด |
| `tools/news_source.py` | ชั้นข่าวของช่วง ② — ไล่แหล่งตามลำดับ (เว็บเรา → worldmonitor → RSS) คัดกรอง fail-closed แล้วจับคู่พาดหัวเข้าพจนานุกรมประเด็น |
| `tools/candles.py` | ติดสถานะให้ทุกแท่ง (forming/closed, อยู่ในปฏิทินหรือไม่) และบันทึก anomaly แทนการลบทิ้ง |
| `tools/gap_detector.py` | ตรวจ session ที่หายตามปฏิทินของสินทรัพย์นั้น |
| `tools/indicators.py` | คำนวณ indicator เฉพาะเมื่อจำนวนแท่งที่ปิดแล้วถึงขั้นต่ำ — ไม่พอ = ไม่คำนวณ ไม่แสดง |
| `tools/pivots.py` | Classic Pivot จาก previous valid completed session พร้อมฐานการคำนวณครบ |
| `tools/publication_gate.py` | ด่านหยุดการเผยแพร่ ครอบคลุม fatal rule ข้อ 1-5 |
| `tools/integrity.py` | ร้อยทุกด่านเข้าด้วยกัน เรียกจุดเดียว |
| `tools/voice_rules.py` | กติกากลางตาม WCB Voice Spec v1 — กติกาปัดเลขต่อสินทรัพย์ · denylist คำ robot 20 คำ · เกณฑ์กริยาตาราง 2.6 · ตัวนับคำ deterministic · ตัวตรวจข้อความซ้ำ corpus |
| `tools/public_copy_validator.py` | ด่านตรวจบทความก่อนปล่อย — ศัพท์ระบบ · field ภายในใน frontmatter · timestamp เครื่องอ่าน · path ในเครื่อง · denylist Voice Spec · โครงสร้าง (ห้ามตาราง/หัวข้ออื่น) · เลขปัดต้อง map กลับ evidence · เพดานความยาว 350-560 คำ (v1.1) |
| `tools/article_builder.py` | ตัวประกอบบทความโครงเล่าเรื่อง 4 ช่วงตาม Voice Spec v1 (+ ส่วนขยาย v1.1) — สร้าง evidence pack (article.json) ก่อนแล้วค่อยเรนเดอร์ Markdown · ชั้น `narrative_context` คำนวณบริบทราคาย้อนหลัง/เส้นค่าเฉลี่ย/ความผันผวน/โครงสร้างระดับ ให้ย่อหน้าขยายเล่าได้โดยไม่ต้องคำนวณเอง |
| `tools/levels.py` | Level engine — previous day/week · swing · MA ที่ผ่านขั้นต่ำ · ATR projection · Pivot พร้อมรวมโซนและกติกา target |
| `tools/license_gate.py` | ด่านสิทธิ์ข้อมูล แยกจากด่านเนื้อหา — unknown = ห้ามเผยแพร่ |
| `tools/chart_renderer.py` | กราฟรุ่นใหม่ (matplotlib) 90 แท่ง · แท่งก่อตัวต่างจากแท่งปิด · ป้ายไม่ทับกัน · คำบรรยายเวลาไทย |

### กติกาที่ level engine บังคับ

- Pivot ไม่ใช่แหล่งระดับเดียวอีกต่อไป — ระดับทุกตัวต้องมี `source_field`, `calculation_method` และ `basis_timestamp`
- ระดับที่ชิดกันถูกรวมเป็นโซน และคุมความกว้างไม่ให้ต่อกันเป็นลูกโซ่จนกลายเป็นโซนกว้างเกินจริง
- `target` ต้องตรงกับระดับที่อนุมัติแล้ว — ข้อความลอยอย่าง `follow-through above R3` ไม่ผ่าน
- ไม่มี target หรือไม่มี invalidation → `watchlist` และ `executable=false`
- ไม่มีข้อมูล intraday → `daily_scenario` เท่านั้น ห้ามใช้ถ้อยคำแบบสั่งเข้าออเดอร์

### ด่านสิทธิ์ข้อมูล

`config/provider_license_registry.json` เก็บสิทธิ์ของแต่ละ provider ค่าเริ่มต้นเป็น `unknown` ทั้งหมด
ซึ่งแปลว่า **ห้ามเผยแพร่** จนกว่าจะมีคนอ่านสัญญาฉบับจริงแล้วมาแก้ไฟล์นี้พร้อมลงวันที่ตรวจ

สถานะที่เป็นไปได้: `hold-data-license-review` · `hold-data-quality` · `hold-content-qa` ·
`approved-internal-only` · `approved-for-publication`

ตรวจบทความก่อนส่ง QA:

```bash
python -m tools.public_copy_validator บทความ.md --evidence บทความ.article-data.json --json
```

ออกรหัส 1 เมื่อไม่ผ่าน — Agent 05 (Article QA) ต้องแนบผลรันนี้ทุกครั้ง ไม่มีผลรัน = ไม่ผ่าน

ค่าตั้งอยู่ที่ `config/market_calendar.json` และ `config/minimum_bars.json`

### วิธีนับคำของเพดาน 350-560 คำ (คำตัดสิน CC ข้อ 5 — 2026-08-03 · เพดานปรับเป็น v1.1 เมื่อ 2026-08-04)

เครื่องที่รันไม่มี PyThaiNLP และห้ามเพิ่ม dependency ใหม่ จึงใช้ตัวนับ deterministic ใน
`tools/voice_rules.py` (`count_public_words`) แทนตัวตัดคำจริง:

- token ละติน 1 ก้อน = 1 คำ · ตัวเลข 1 ก้อน (รวม `,` `.` `:` `%`) = 1 คำ
- อักษรไทยประมาณจากความยาวอักขระ ÷ 4.5 (ปัดครึ่งขึ้น)
- ไม่นับ frontmatter และบรรทัด markup ภาพ (`![`)

ค่า 4.5 สอบเทียบกับ reference corpus 4 ชิ้น (สเกล ~250-450 คำต่อชิ้น) และถูกล็อกด้วยเทส
`tests/test_voice_rules.py` — เปลี่ยนสูตรนับ = เปลี่ยนมาตรฐาน ต้องแจ้ง CC ก่อน

เพดานเดิม 250-450 คำถูกยกเป็น **350-560 คำ** ตามคำสั่งผู้ใช้ 2026-08-04 ("ต้องขยายความ
เนื้อหาให้มากกว่านี้") — ต่ำกว่า 350 คำถือว่าเนื้อหาน้อยเกินไปและด่านตีตกเอง

## ข้อจำกัดที่ต้องรู้

- **หนึ่งรอบใช้แหล่งเดียว** — ยังไม่มี cross-provider verification อัตโนมัติในสายท่อ (fatal rule ข้อ 6) ตามการตัดสินของผู้ใช้ 2026-08-03 ตัวเลขในบทความจึงยืนยันได้เท่าที่แหล่งเดียวรายงาน
  เคยทานสอบกับ MetaTrader 5 ครั้งหนึ่งก่อนถอดออก (2026-08-05 · ทองคำ 130 แท่ง):
  ชุดวันที่ตรงกันทั้งหมด · ส่วนต่างราคาปิดมัธยฐาน 0.015% · Pivot ต่างไม่เกิน 0.28 ดอลลาร์
  ⇒ ยืนยันว่าย้ายแหล่งแล้วตัวเลขไม่เพี้ยน แต่ตอนนี้ไม่มีแหล่งที่สองให้ทานสอบซ้ำแล้ว
- **ราคาต่างแหล่งต่างธรรมเนียม** — เวลาปิดแท่งและ spread ของแต่ละแหล่งไม่เหมือนกัน ตัวเลขจึงต่างกันได้เล็กน้อย
  บทความต้องระบุที่มาเสมอ · แท่งที่ตกวันหยุดตามปฏิทินของสายท่อถูกคัดออกและบันทึกไว้ใน `provider_meta`
- 🔒 **ระบบนี้เดินในโหมดใช้ภายในเท่านั้น (by design)** — ด่านสิทธิ์คง `approved-internal-only` ทุกครั้ง ด้วยเหตุผลคนละข้อของสองแหล่ง:
  - `wcb_series_api` — ยังไม่รู้ว่าข้อมูลต้นทางมาจากผู้ให้บริการเจ้าไหนและมีสิทธิ์เผยแพร่แค่ไหน ทะเบียนจึงเป็น `unknown` ซึ่ง**กั้นการเผยแพร่ไว้ก่อน** ตามกติกา fail-closed ⇒ **รอคำตอบ ไม่ใช่ห้ามถาวร**

  **นี่คือสถานะที่ตั้งใจ ไม่ใช่ข้อบกพร่องที่รอแก้** — การเปลี่ยนค่าในทะเบียนให้ผ่านโดยไม่มีสิทธิ์จริงคือการทำให้ระบบโกหกตัวเอง
  การเผยแพร่จะทำได้เมื่อเจ้าของข้อมูลยืนยันสิทธิ์ แล้วแก้ `config/provider_license_registry.json` ตามคำตอบจริง
- **ข้อควรระวังเรื่องกราฟ** — กราฟที่ระบบวาดเองก็ถือเป็นการทำซ้ำชุดข้อมูลจำนวนมาก จึงอยู่ใต้ข้อจำกัดเดียวกับตัวเลขดิบ ไม่ใช่ทางเลี่ยง
- ยังไม่มี H4/H1/M15 จึงเขียนได้เฉพาะมุมมองระดับ Daily

## Architecture

`Market Snapshot → Technical 3 Sets + News Impact → Chart Editor → Chart/Article → Article QA → User Approval → Publish/Verify`

- Technical Set 1: Trend & Market Structure
- Technical Set 2: Momentum & Volatility
- Technical Set 3: Price Levels & Reaction
- WCB Article QA: ด่านตรวจอิสระแบบ fail-closed

ดู [Agent and skill matrix](docs/AGENT-SKILL-MATRIX.md), [governance](GOVERNANCE.md) และ [delivery checklist](DELIVERY-CHECKLIST.md)

## Security

ห้าม commit API keys, market-data credentials, unpublished articles หรือข้อมูลลูกค้า ใช้ `.env.example` เท่านั้น
