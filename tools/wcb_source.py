"""แหล่งข้อมูลจาก snapshot API ของ WorldClassBroker — สายสาธารณะ

ต่างจากสายแท่งราคา (`tools/wcb_series_source.py`) สองเรื่องที่เปลี่ยนวิธีเขียนบทความทั้งหมด:

1. **มีหลายกรอบเวลา** — 30min/1h/4h/1day มาพร้อมกันในก้อนเดียว สายเดิมมีแต่ D1
   จึงมีกฎห้ามภาษาชี้จังหวะระหว่างวัน · สายนี้ไม่ต้องมีกฎนั้น แต่ได้กฎวินัย TF มาแทน
   (1day + 4h เป็นหลัก · 1h/30min ประกอบและต้องเขียนกำกับ · ห้ามหยิบ TF ที่เข้าทางตัวเอง)
2. **อินดิเคเตอร์กับ pivot ผู้ให้บริการคำนวณมาให้** — เราไม่คำนวณเอง ⇒ ไม่มีสิทธิ์
   แต่งเลขใหม่ในชั้นบทความเลยแม้แต่ตัวเดียว ทุกเลขต้องยกมาจากก้อนตรง ๆ

**กับดักที่โมดูลนี้กันให้:** ไฟล์ snapshot ที่เซฟผ่านเชลล์บางตัวได้ข้อความไทยเป็น
ลำดับไบต์ UTF-8 ที่ถูกตีความเป็น latin-1 (mojibake) — ตัวเลขไม่กระทบแต่ชื่อรายการ
ในปฏิทินอ่านไม่ออก · `_mend()` ซ่อมให้ตอนอ่าน ไม่ใช่ตอนเขียนบทความ เพื่อให้จุดซ่อม
อยู่ที่เดียวและบทความไม่ต้องรู้เรื่องนี้
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


BANGKOK = timezone(timedelta(hours=7))
TIMEFRAMES = ("30min", "1h", "4h", "1day")

# โฮสต์ไม่ใช่ความลับ · **รหัสเป็นความลับ** และห้ามอยู่ในไฟล์นี้หรือไฟล์ใดในรีโป
# (คำสั่งผู้ใช้ 2026-08-05: ห้ามส่งออก ห้ามขึ้น git ใช้ในเครื่องเท่านั้น)
BASE_URL = "https://worldclassbroker.worldclassbroker-com.workers.dev/api/analysis/snapshot"
KEY_ENV = "WCB_SNAPSHOT_KEY"
KEY_FILE_ENV = "WCB_SNAPSHOT_KEY_FILE"

DEFAULT_TIMEOUT = 20
MAX_ATTEMPTS = 3
RETRY_SLEEP_SECONDS = 2.0

# **ต้องส่ง User-Agent เสมอ** — ปลายทางอยู่หลัง Cloudflare ซึ่งตอบ 403 ให้กับ
# ค่าเริ่มต้นของ urllib (`Python-urllib/3.x`) · วัดจริงเมื่อ 2026-08-05:
# ไม่ส่ง header เลย → 403 · ส่งแค่ Accept → 403 · ส่ง User-Agent ด้วย → 200
# ถ้าเจอ 403 อีกในอนาคต ให้สงสัยตรงนี้ก่อนสงสัยว่ารหัสหมดอายุ
USER_AGENT = "Mozilla/5.0 (compatible; WCB-analysis-bot/1.0)"
# ก้อนที่เก่ากว่านี้ใช้เขียนบทความไม่ได้ — ราคาระหว่างวันเปลี่ยนเร็วกว่านั้นมาก
MAX_AGE_MINUTES = 90

# ชื่อหัวข้อของสายท่อ → tag ที่ WCB API รู้จัก
# อยู่ที่นี่ที่เดียวเพราะ **ทั้งสอง endpoint ของ API เจ้านี้ใช้ทะเบียนชื่อเดียวกัน**
# (snapshot ที่โมดูลนี้ยิง และ series ที่ `wcb_series_source` ยิง)
# เคยแยกกันอยู่พักหนึ่งแล้วสายสาธารณะส่งชื่อ `btcusd` เข้าไปตรง ๆ ซึ่งปลายทางไม่รู้จัก
ASSET_TAGS = {
    "eurusd": "eurusd",
    "gbpusd": "gbpusd",
    "btcusd": "btc",
    "xauusd": "xauusd",
    "nvda": "nvda",
    "usdthb": "usdthb",
    "solusd": "sol",
}


def tag_for(asset: str) -> str:
    """แปลงชื่อหัวข้อของสายท่อเป็น tag ของ API — ไม่รู้จัก = ฟ้อง ไม่ส่งชื่อดิบไปเดา"""
    try:
        return ASSET_TAGS[asset]
    except KeyError as exc:
        raise SnapshotUnusable(
            f"ยังไม่ได้แมปหัวข้อ {asset} เข้ากับ tag ของ WCB API — "
            f"tag ที่รู้จักตอนนี้: {', '.join(sorted(ASSET_TAGS.values()))}"
        ) from exc


# ทุกอย่างที่ชั้นนักเขียน **เดาจากตัวเลขไม่ได้** ต้องมาจากทะเบียนนี้
#
# เกิดจากบั๊กจริง 2026-08-05: `wcb_writers` ถูกเขียนและทดสอบกับทองคำอย่างเดียว
# แล้วชื่อสินทรัพย์กับหน่วยถูกฝังเป็นค่าคงที่ ⇒ บท EUR/USD ออกมาพาดหัวว่า
# "ทองคำโลก (XAU/USD)" และบอกราคา "ต่อออนซ์" · ด่านตรวจจับไม่ได้เพราะมันตรวจ
# แต่ตัวเลข ไม่ได้ตรวจว่าบทพูดถึงสินทรัพย์ตัวไหน
#
# `decimals` ก็เดาจากราคาไม่ได้เช่นกัน — EUR/USD ที่ 1.15403 ปัดเหลือทศนิยม 2 ตำแหน่ง
# แล้วราคาสูงสุด/ต่ำสุด/ราคาปิดของทั้งวันกลายเป็น "1.15" เท่ากันหมด บทความเลยเขียนว่า
# "ระหว่างวันขึ้นไปสูงสุด 1.15 และลงต่ำสุด 1.15" ซึ่งอ่านแล้วไม่ได้ข้อมูลอะไรเลย
#
# `levels` คือทศนิยมของเส้นในหมุดกราฟ ซึ่งหยาบกว่าราคาได้เพราะเป็นโซน ไม่ใช่จุด
# แต่ห้ามหยาบจนเส้นคนละตัวปัดมาชนกัน (ทองใช้จำนวนเต็มได้ · EUR/USD ต้องมีสี่ตำแหน่ง)
#
# `macro` คือสายส่งจากข้อมูลเศรษฐกิจสหรัฐมาถึงสินทรัพย์ตัวนั้น — **เขียนเองด้วยมือ
# เท่านั้น ห้ามใช้ข้อความของสินทรัพย์อื่นแทน** เพราะกลไกคนละตัวกันจริง ๆ
# (ทองขึ้นเมื่อดอลลาร์อ่อน · EUR/USD คือคู่ที่ดอลลาร์อยู่ในสมการโดยตรง ·
#  หุ้นเทคขึ้นกับต้นทุนเงินและรอบสินค้า ไม่ใช่ค่าเงินเป็นหลัก)
# ช่อง `seo_name` / `seo_tail` ใช้เฉพาะพาดหัว (สเปก SEO ของหัวหน้า 2026-08-10) —
# แยกจาก `thai_name`/`short_name` ที่เขียนเพื่ออ่านลื่นในเนื้อบท · ทองเป็นตัวอย่างที่ชัด:
# เนื้อบทเรียก "ทองคำโลก" แต่คนไทยค้นคำว่า "ทองคำ" · ประกอบพาดหัวที่ tools/headline_format.py
ASSET_PROFILES = {
    "xauusd": {
        "thai_name": "ทองคำโลก",
        "short_name": "ทอง",
        "seo_name": "ทองคำ",
        "seo_tail": "แนวโน้มราคาทอง XAU/USD",
        "symbol": "XAU/USD",
        "unit_phrase": "ดอลลาร์ต่อออนซ์",
        "decimals": 2,
        "levels": 0,
        "macro": ("สายส่งจากตัวเลขเหล่านี้ถึงราคาทองเดินผ่านทางเดียวคือความคาดหวังดอกเบี้ย "
                  "ข้อมูลที่อ่อนกว่าเดิมแปลว่าไม่มีเหตุผลต้องขึ้นดอกเบี้ยเพิ่ม "
                  "ผลตอบแทนพันธบัตรและดอลลาร์อ่อนลง ทองได้ประโยชน์ "
                  "ในทางกลับกันข้อมูลที่แข็งเกินคาดจะพาเรื่องดอกเบี้ยสูงยาวกลับมาและกดทองทันที"),
    },
    "eurusd": {
        "thai_name": "ยูโรเทียบดอลลาร์สหรัฐ",
        "short_name": "ยูโร",
        "seo_name": "ยูโร",
        "seo_tail": "แนวโน้มค่าเงินยูโร EUR/USD",
        "symbol": "EUR/USD",
        "unit_phrase": "ดอลลาร์ต่อยูโร",
        "decimals": 5,
        "levels": 4,
        "macro": ("สายส่งจากตัวเลขเหล่านี้ถึงคู่เงินนี้สั้นกว่าสินทรัพย์อื่น เพราะดอลลาร์อยู่ในสมการโดยตรง "
                  "ข้อมูลสหรัฐที่แข็งกว่าคาดหนุนดอลลาร์ และคู่เงินนี้ย่อลงตามทันที "
                  "ข้อมูลที่อ่อนกว่าคาดให้ผลตรงข้าม "
                  "จุดที่ต้องระวังคือฝั่งยูโรมีปฏิทินของตัวเองด้วย บทนี้อ่านได้เฉพาะฝั่งสหรัฐเท่านั้น"),
    },
    # เพิ่ม 2026-08-06 ตามคำสั่งผู้ใช้ · สายส่งมหภาคเขียนใหม่ทั้งย่อหน้า **ห้ามลอกของยูโร**
    # ตามที่ทีมเว็บกำกับมาในแม่แบบ: มุมต้องต่างจาก EUR/USD จริง (BoE ไม่ใช่ ECB)
    # และต้องมองสองฝั่งของคู่เงินเสมอ เพราะหัวใจคือส่วนต่างดอกเบี้ย ไม่ใช่ข่าวฝั่งเดียว
    "gbpusd": {
        "thai_name": "ปอนด์เทียบดอลลาร์สหรัฐ",
        "short_name": "ปอนด์",
        "seo_name": "ปอนด์",
        "seo_tail": "แนวโน้มค่าเงินปอนด์ GBP/USD",
        "symbol": "GBP/USD",
        "unit_phrase": "ดอลลาร์ต่อปอนด์",
        "decimals": 5,
        "levels": 4,
        "macro": ("สายส่งของคู่เงินนี้มีสองขาที่ต้องอ่านคู่กันเสมอ ไม่ใช่ขาเดียว "
                  "ขาสหรัฐทำงานผ่านดอลลาร์ตามปกติ ข้อมูลที่แข็งกว่าคาดหนุนดอลลาร์และกดคู่เงินนี้ลง "
                  "ส่วนขาอังกฤษเดินผ่านธนาคารกลางอังกฤษซึ่งมีวงจรดอกเบี้ยเป็นของตัวเอง "
                  "และไม่ได้ขยับพร้อมกับฝั่งยุโรปเสมอไป "
                  "สิ่งที่ขยับคู่เงินนี้จริงคือส่วนต่างของสองฝั่ง ไม่ใช่ข่าวดีหรือข่าวร้ายของฝั่งใดฝั่งหนึ่งลำพัง "
                  "ตัวเลขสหรัฐที่อ่อนลงจึงหนุนคู่เงินนี้ได้ก็ต่อเมื่อฝั่งอังกฤษไม่ได้อ่อนลงแรงกว่าในรอบเดียวกัน "
                  "ชุดข้อมูลรอบนี้ครอบคลุมเฉพาะปฏิทินฝั่งสหรัฐ บทจึงอ่านได้เฉพาะขานั้น "
                  "และต้องไม่สรุปแทนฝั่งอังกฤษที่ยังไม่มีข้อมูลบนโต๊ะ"),
    },
    "btcusd": {
        "thai_name": "บิตคอยน์",
        "short_name": "บิตคอยน์",
        "seo_name": "บิตคอยน์",
        "seo_tail": "แนวโน้มราคาบิตคอยน์ BTC/USD",
        "symbol": "BTC/USD",
        "unit_phrase": "ดอลลาร์",
        "decimals": 2,
        "levels": 0,
        "macro": ("สายส่งจากตัวเลขเหล่านี้ถึงบิตคอยน์เดินผ่านความอยากเสี่ยงของตลาดและสภาพคล่องเป็นหลัก "
                  "ไม่ใช่ผ่านมูลค่าพื้นฐานแบบสินทรัพย์ที่มีกระแสเงินสด "
                  "ข้อมูลที่ทำให้ตลาดคาดว่าดอกเบี้ยจะผ่อนลงมักหนุนสินทรัพย์เสี่ยงทั้งกลุ่มพร้อมกัน "
                  "และข้อมูลที่แข็งเกินคาดมักกดทั้งกลุ่มพร้อมกันเช่นเดียวกัน"),
    },
    "nvda": {
        # **ห้ามเรียกว่า "หุ้น"** — เป็นสัญญาซื้อขายส่วนต่าง ไม่ใช่หุ้นบนกระดาน
        # (ข้อผูกพันของผู้ใช้) · ชนิดเครื่องมือจึงไปบอกในหน่วยราคาแทนพาดหัว
        # ซึ่งอ่านลื่นกว่าและไม่ทำให้พาดหัวมีวงเล็บซ้อนวงเล็บ
        "thai_name": "เอ็นวิเดีย",
        "short_name": "เอ็นวิเดีย",
        # ⛔ ห้ามมีคำว่า "หุ้น" ในพาดหัวเช่นกัน — ข้อผูกพันของผู้ใช้ (ดูคอมเมนต์เหนือ thai_name)
        # ต่อให้เป็นคำที่คนค้นมากกว่าก็ใช้ไม่ได้ เพราะมันเรียกผิดชนิดเครื่องมือ
        "seo_name": "เอ็นวิเดีย",
        "seo_tail": "แนวโน้มราคา NVDA",
        "symbol": "NVDA",
        "unit_phrase": "ดอลลาร์ต่อหน่วย ซื้อขายผ่านสัญญาส่วนต่าง",
        "decimals": 2,
        "levels": 1,
        "macro": ("สายส่งจากตัวเลขเหล่านี้ถึงราคาเดินผ่านต้นทุนเงินเป็นหลัก "
                  "ดอกเบี้ยที่คาดว่าจะสูงยาวกดมูลค่าปัจจุบันของกำไรที่อยู่ไกลออกไป ซึ่งกระทบหุ้นกลุ่มเติบโตมากกว่ากลุ่มอื่น "
                  "แต่ตัวแปรที่ขยับราคาแรงกว่าปฏิทินมหภาคคือรอบผลประกอบการและข่าวเฉพาะตัวของบริษัท "
                  "ซึ่งไม่ได้อยู่ในชุดข้อมูลนี้"),
    },
    # เพิ่ม 2026-08-10 ตามคำสั่งผู้ใช้ · macro เขียนใหม่ทั้งย่อหน้า ห้ามลอกของ gbpusd/eurusd
    # ตรวจแล้ว 08-10: ปฏิทินที่ก้อนให้มามีแค่ AUD/CAD/CNY/GBP/JPY/USD **ไม่มี THB เลย**
    # ⇒ ต้องเขียนกำกับตรง ๆ ว่าบทนี้อ่านได้ฝั่งเดียว เหมือนกับที่ eurusd/gbpusd ทำไว้กับปฏิทินฝั่งคู่ตรงข้าม
    "usdthb": {
        "thai_name": "ดอลลาร์สหรัฐเทียบบาทไทย",
        "short_name": "ดอลลาร์-บาท",
        # คนไทยค้น "ค่าเงินบาทวันนี้" ไม่ได้ค้น "ดอลลาร์สหรัฐเทียบบาทไทย"
        "seo_name": "ค่าเงินบาท",
        "seo_tail": "แนวโน้มเงินบาท USD/THB",
        "symbol": "USD/THB",
        "unit_phrase": "บาทต่อดอลลาร์",
        "decimals": 5,
        "levels": 4,
        "macro": ("คู่เงินนี้มีขาเดียวที่ชุดข้อมูลนี้อ่านได้จริงคือฝั่งดอลลาร์ "
                  "ข้อมูลเศรษฐกิจสหรัฐที่แข็งกว่าคาดหนุนดอลลาร์และมักดันราคาคู่นี้ขึ้น "
                  "เพราะต้องใช้เงินบาทมากขึ้นเพื่อแลกดอลลาร์หนึ่งหน่วย "
                  "ข้อมูลที่อ่อนกว่าคาดให้ผลตรงข้าม "
                  "ส่วนขาฝั่งไทย — นโยบายธนาคารแห่งประเทศไทย ดุลบัญชีเดินสะพัด และเงินทุนท่องเที่ยว — "
                  "ไม่มีอยู่ในปฏิทินของชุดข้อมูลนี้ บทจึงอ่านได้เฉพาะแรงขับจากฝั่งสหรัฐเท่านั้น "
                  "และต้องไม่สรุปแทนฝั่งไทยที่ไม่มีตัวเลขรองรับ"),
    },
    # เพิ่ม 2026-08-10 ตามคำสั่งผู้ใช้ · โซลานาเป็นคริปโทเช่นเดียวกับบิตคอยน์แต่ผันผวนกว่า
    # (beta สูงกว่า) — เขียนแยกจากย่อหน้าบิตคอยน์เพื่อไม่ให้อ่านเหมือนเป็นสินทรัพย์เดียวกัน
    "solusd": {
        "thai_name": "โซลานา",
        "short_name": "โซลานา",
        "seo_name": "โซลานา",
        "seo_tail": "แนวโน้มราคาโซลานา SOL/USD",
        "symbol": "SOL/USD",
        "unit_phrase": "ดอลลาร์ต่อเหรียญ",
        "decimals": 2,
        "levels": 1,
        "macro": ("สายส่งจากตัวเลขเหล่านี้ถึงโซลานาเดินผ่านความอยากเสี่ยงของตลาดเช่นเดียวกับบิตคอยน์ "
                  "ข้อมูลที่ทำให้ตลาดคาดว่าดอกเบี้ยจะผ่อนลงมักหนุนสินทรัพย์เสี่ยงทั้งกลุ่มพร้อมกัน "
                  "แต่โซลานาเป็นเหรียญที่มีมูลค่าตลาดเล็กกว่าบิตคอยน์มาก ราคาจึงมักแกว่งแรงกว่า "
                  "ทั้งขาขึ้นและขาลงเมื่อเทียบกับการขยับของบิตคอยน์ในรอบข่าวเดียวกัน"),
    },
}


# ย้อนกลับจาก tag ของ API มาเป็นชื่อหัวข้อของสายท่อ — สร้างจากทะเบียนเดิม
# ไม่ใช่พิมพ์ซ้ำ เพราะสองใบที่ต้องตรงกันเสมอจะเริ่มไม่ตรงกันตั้งแต่ครั้งแรกที่แก้ใบเดียว
TAG_TO_ASSET = {tag: name for name, tag in ASSET_TAGS.items()}


def profile_for(asset: str) -> dict:
    """ทะเบียนหน้าตาของสินทรัพย์ — ไม่รู้จัก = หยุด ห้ามตกไปใช้ค่าของตัวอื่น

    ตกไปใช้ค่าตั้งต้นเงียบ ๆ คือวิธีที่บั๊ก "บท EUR/USD พาดหัวว่าทองคำ" เกิดขึ้นมาแล้ว
    ครั้งหนึ่ง ⇒ ที่นี่เลือกให้ล้มดัง ๆ แทน

    **จงใจไม่เรียกจาก `normalize()`** — ด่านตรวจบทความก็เรียก `normalize()` เหมือนกัน
    แต่มันต้องการแค่ค่า pivot ถ้าผูกทะเบียนไว้ตรงนั้น ก้อนพิการที่ควรได้คำตัดสิน
    "ตกด่าน" จะกลายเป็น exception กลางสายท่อแทน · จุดที่ต้องรู้จักสินทรัพย์จริง ๆ
    คือชั้นนักเขียน จึงให้ล้มที่นั่น
    """
    # ก้อนที่ปลายทางคืนมาสะท้อน **tag ที่เราขอไป** กลับมาในช่อง `asset` ไม่ใช่ชื่อหัวข้อ
    # ของสายท่อ ⇒ `btcusd` จะกลับมาเป็น `btc` · ทะเบียนคีย์ด้วยชื่อหัวข้อเป็นหลัก
    # แล้วรับ tag เป็นชื่อรองด้วย ไม่งั้นสายท่อจริงพังเฉพาะหัวข้อที่ชื่อไม่ตรงกับ tag
    name = asset if asset in ASSET_PROFILES else TAG_TO_ASSET.get(asset, asset)
    try:
        return ASSET_PROFILES[name]
    except KeyError as exc:
        raise SnapshotUnusable(
            f"ยังไม่ได้ลงทะเบียนหน้าตาของหัวข้อ {asset} ใน ASSET_PROFILES — "
            f"ต้องกรอกชื่อไทย หน่วย ทศนิยม และสายส่งมหภาคก่อนจึงจะเขียนบทได้ "
            f"(ที่ลงทะเบียนแล้ว: {', '.join(sorted(ASSET_PROFILES))})"
        ) from exc


class SnapshotUnusable(RuntimeError):
    """ก้อนข้อมูลใช้เขียนบทความไม่ได้ — ต้องหยุด ห้ามเขียนต่อจากก้อนที่ไม่ครบ"""


class SnapshotStale(RuntimeError):
    """ได้ก้อนมาแต่เก่าเกินกว่าจะใช้ตัดสินใจ — บทเรียนเดียวกับด่านความสดของสายแท่งราคา

    ดึงสำเร็จไม่เท่ากับข้อมูลสด ปลายทางที่ค้างจะคืนก้อนเดิมเรื่อย ๆ โดยไม่มี error
    ถ้าปล่อยผ่าน บทความจะอ้างราคาที่ตลาดทิ้งไปแล้วโดยไม่มีใครรู้
    """


class KeyMissing(RuntimeError):
    """ไม่มีรหัสเข้าถึง API — ต้องตั้งค่าในเครื่อง ห้ามฝังไว้ในโค้ด"""


def _resolve_key(explicit: str | None = None) -> str:
    """หารหัสจากในเครื่องเท่านั้น ตามลำดับ: อาร์กิวเมนต์ → ตัวแปรสภาพแวดล้อม → ไฟล์

    **ไม่มีค่าตั้งต้น** โดยตั้งใจ · ถ้าเผลอใส่ค่าตั้งต้นไว้สักครั้ง รหัสจะติดไปกับรีโป
    ตลอดไปแม้จะลบทีหลัง เพราะประวัติ git เก็บไว้หมด
    """
    if explicit:
        return _clean_key(explicit)
    from_env = os.environ.get(KEY_ENV)
    if from_env:
        return _clean_key(from_env)
    path = os.environ.get(KEY_FILE_ENV)
    if path and Path(path).is_file():
        return _clean_key(Path(path).read_text(encoding="utf-8"))
    raise KeyMissing(
        f"ไม่พบรหัสเข้าถึง snapshot API — ตั้งค่า {KEY_ENV} หรือชี้ {KEY_FILE_ENV} "
        "ไปที่ไฟล์รหัสในเครื่อง (ห้ามเก็บรหัสไว้ในรีโปหรือส่งออกนอกเครื่อง)")


def _clean_key(raw: str) -> str:
    """ตัดสิ่งที่ติดมากับรหัสโดยที่คนวางไฟล์มองไม่เห็น

    **BOM คือกับดักของเครื่องนี้** — Windows PowerShell 5.1 เขียนไฟล์ด้วย
    `Set-Content -Encoding utf8` แล้วได้ UTF-8 **พร้อม BOM** ⇒ อักขระ `\\ufeff`
    กลายเป็นตัวแรกของรหัส ไหลไปต่อใน query string แล้ว `urllib` โยน
    `UnicodeEncodeError: 'ascii' codec can't encode character '\\ufeff'` ลึกอยู่ใน
    `http.client` ซึ่งไม่มีคำว่า "รหัส" อยู่ในข้อความเลย (เกิดจริง 2026-08-06 —
    ไล่จาก traceback ไม่เจอต้นเหตุ ต้องนับไบต์ในไฟล์เอง)

    `.strip()` เดิมไม่ตัด BOM เพราะมันไม่ใช่ whitespace ตามนิยามของ Python
    ⇒ ตัดที่นี่ที่เดียว ก่อนที่ค่าจะไปถึงจุดใดในระบบ · เงียบได้เพราะ BOM
    ไม่มีทางเป็นส่วนของรหัสจริง ไม่ใช่การกลืนความผิดพลาด

    ส่วนอักขระนอก ASCII อื่น ๆ **ไม่กลืน** — โยนพร้อมบอกตำแหน่งและวิธีแก้ ดีกว่า
    ให้ระบบไปตายที่ชั้น http ซึ่งไม่รู้ว่ากำลังพูดถึงรหัส
    """
    key = raw.strip("﻿\r\n\t ")
    if not key.isascii():
        bad = next(ch for ch in key if not ch.isascii())
        raise KeyMissing(
            f"ไฟล์รหัสมีอักขระที่ใช้ใน URL ไม่ได้ ({bad!r} ตำแหน่งที่ {key.index(bad)}) "
            "— มักเกิดจากไฟล์ถูกบันทึกเป็น UTF-8 พร้อม BOM หรือมีข้อความอื่นปนอยู่ "
            "ให้เขียนไฟล์ใหม่ให้มีแค่ตัวรหัสบรรทัดเดียวและไม่มี BOM")
    return key


def redact(text: str, secret: str) -> str:
    """ลบรหัสออกจากข้อความก่อนแสดงผลหรือบันทึก log

    urllib ใส่ URL เต็มลงในข้อความ error เอง ⇒ ถ้าไม่กรอง รหัสจะโผล่ใน traceback
    ที่คนมักคัดลอกไปแปะถามคนอื่น ซึ่งเป็นทางหลุดที่พบบ่อยที่สุดของรหัสแบบใส่ใน query
    """
    return text.replace(secret, "***") if secret else text


def build_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})


def fetch_payload(asset: str = "xauusd", *, key: str | None = None, base_url: str = BASE_URL,
                  timeout: int = DEFAULT_TIMEOUT) -> dict:
    """คืน **ก้อนดิบ** ตามที่ปลายทางส่งมา — ยังไม่แปลงรูป

    แยกออกมาเพราะผู้เรียกที่อยากเก็บก้อนไว้ตรวจย้อนกลับต้องได้รูปเดิมเป๊ะ
    ก้อนที่แปลงแล้วเอากลับเข้า `normalize()` ไม่ได้ และด่านตรวจบทความก็อ่านไม่ออก
    (บั๊กที่เจอตอนรันจริงครั้งแรก 2026-08-05 — `--save-snapshot` เคยเก็บก้อนที่แปลงแล้ว)
    """
    secret = _resolve_key(key)
    url = f"{base_url}?asset={asset}&k={secret}"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(build_request(url), timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            message = redact(str(error), secret)
            # 4xx คือคำตอบว่า "คำขอผิด" ไม่ใช่ปัญหาชั่วคราว — ยิงซ้ำได้ผลเดิมและ
            # เป็นการรบกวนปลายทางเปล่า ๆ · ยกเว้น 429 ที่แปลว่าให้รอแล้วค่อยมาใหม่
            code = getattr(error, "code", None)
            if code and 400 <= code < 500 and code != 429:
                raise SnapshotUnusable(f"ปลายทางปฏิเสธคำขอ ({code}): {message}") from None
            if attempt == MAX_ATTEMPTS:
                raise SnapshotUnusable(
                    f"ดึง snapshot ไม่สำเร็จหลังพยายาม {MAX_ATTEMPTS} ครั้ง: {message}") from None
            time.sleep(RETRY_SLEEP_SECONDS)
    return payload


def ensure_fresh(evidence: dict, max_age_minutes: int = MAX_AGE_MINUTES) -> dict:
    """ด่านความสด — คืน evidence เดิมเมื่อผ่าน โยนเมื่อไม่ผ่าน ไม่มีทางเลือกที่สาม"""
    age = age_minutes(evidence)
    if age is not None and age > max_age_minutes:
        raise SnapshotStale(
            f"ก้อนข้อมูลเก่า {int(age)} นาที เกินเพดาน {max_age_minutes} นาที — "
            "หยุดสายท่อ ห้ามเขียนบทความจากราคาที่ตลาดทิ้งไปแล้ว")
    return evidence


class SnapshotTooCoarse(RuntimeError):
    """ก้อนมาครบและสด แต่ปลายทางปัดตัวเลขหยาบเกินกว่าจะเขียนบทเทคนิคได้

    คู่ขนานกับ `SnapshotStale` — ทั้งคู่คือ "ดึงสำเร็จไม่เท่ากับใช้ได้"
    """


# **ขั้นการปัดของปลายทางไม่ใช่ค่าคงที่อีกแล้ว** — ตั้งแต่ 2026-08-06 ทีมเว็บแก้ให้
# จำนวนทศนิยมขึ้นกับสินทรัพย์ (คู่เงินทั่วไป 5 · คู่ที่มีเยน 3 · ทอง/หุ้น 2) ตามที่ตอบ
# กลับมาในใบตอบ P002 ⇒ ด่านนี้จะเดาว่า "0.01 เสมอ" ต่อไปไม่ได้ ไม่งั้น EUR/USD กับ
# GBP/USD จะติดธง `coarse_prices` ตลอดกาลทั้งที่ก้อนละเอียดพอแล้ว
#
# ที่นี่จึงเลิกใช้ค่าคงที่แล้ว **วัดจากก้อนที่ได้มาจริง** สองทางแล้วเอาทางที่หยาบกว่า:
#
#     ที่ควรได้   จากทะเบียน `ASSET_PROFILES[...]["decimals"]` ของสินทรัพย์นั้น
#     ที่ได้จริง  นับทศนิยมสูงสุดที่ปรากฏในค่าที่เป็นราคา (SMA/EMA + pivot ทุกกรอบ)
#
# เหตุผลที่ต้องวัด "ที่ได้จริง" ด้วย ไม่ใช่เชื่อทะเบียนอย่างเดียว: อาการฝั่งปลายทาง
# **ถอยกลับได้** — ฟีดคริปโทถอยกลับเป็นจันทร์-ศุกร์สองครั้งในสองวัน (E6 → E8)
# ถ้าเชื่อทะเบียนอย่างเดียว วันที่ปลายทางถอยกลับไปปัด 2 ตำแหน่ง ด่านนี้จะเงียบสนิท
# และบทจะออกโดยมีเส้นค่าเฉลี่ยชนกันเหมือนก่อน 08-06 โดยไม่มีอะไรฟ้อง
#
# ⚠️ **เพดานด้านล่างไม่ได้ถูกผ่อน** — ยังเป็น 10% ของกรอบราคาทั้งวันเท่าเดิม
# ที่เปลี่ยนคือตัวเลข "ขั้นการปัด" ที่ป้อนเข้าสูตร ซึ่งเดิมเป็นค่าที่เดาไว้ตายตัว
LEGACY_PROVIDER_STEP = 0.01
# ขั้นการปัดต้องเล็กกว่ากรอบราคาของวันไม่น้อยกว่าสิบเท่า จึงจะแยกระดับออกจากกันได้จริง
MAX_STEP_OF_DAY_RANGE = 0.10
# ต่ำกว่านี้ถือว่าตัวอย่างน้อยเกินกว่าจะสรุปว่าปลายทางปัดกี่ตำแหน่ง — ค่าที่ลงตัวพอดี
# อย่าง 1.15 เกิดขึ้นเองได้เมื่อมีตัวอย่างไม่กี่ตัว แต่การที่ค่าราคาสิบกว่าตัวลงท้าย
# ด้วยสองตำแหน่งพร้อมกันทั้งหมดไม่ใช่เรื่องบังเอิญ
MIN_SAMPLES_TO_INFER_STEP = 8


def _decimal_places(value) -> int:
    """จำนวนทศนิยมที่ค่านั้น**ใช้จริง** — 1.15 คือ 2 · 1.15467 คือ 5 · 4262.0 คือ 0

    ใช้ `repr()` เพราะ Python 3 คืนสตริงที่สั้นที่สุดที่แปลงกลับได้ค่าเดิมเป๊ะ
    การจัดรูปแบบเป็นทศนิยมคงที่แล้วตัดศูนย์ท้ายจะได้ขยะจากความคลาดเคลื่อนของ float
    (0.1 + 0.2 กลายเป็น 17 ตำแหน่ง) ซึ่งทำให้ก้อนหยาบดูเหมือนละเอียด
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    text = repr(number)
    if "e" in text or "E" in text:   # ค่าเล็กมากจนเขียนเป็น 1e-05 — ละเอียดอยู่แล้ว
        return 10
    return len(text.partition(".")[2].rstrip("0"))


def price_scale_values(evidence: dict) -> list[float]:
    """ค่าทุกตัวในก้อนที่**อยู่ในหน่วยราคา** — ชุดที่การปัดของปลายทางทำร้ายได้

    คู่กับ `pivot_values()` แต่คนละหน้าที่: ตัวนั้นเป็นทะเบียนอนุญาตของด่านตรวจบทความ
    ตัวนี้เป็นชุดตัวอย่างสำหรับวัดความละเอียดเท่านั้น จึงรวมเส้นค่าเฉลี่ยเข้ามาด้วย
    และ**ห้าม**รวม RSI/MACD/ADX/Stochastic ที่อยู่คนละสเกลกับราคา
    """
    values = list(pivot_values(evidence))
    groups = [evidence.get("daily") or {}]
    groups += list((evidence.get("by_tf") or {}).values())
    for block in groups:
        for name, item in ((block or {}).get("indicators") or {}).items():
            if name.upper().startswith(("SMA", "EMA")) and item.get("value") is not None:
                values.append(float(item["value"]))
    return values


def provider_step(evidence: dict) -> tuple[float, str]:
    """ขั้นการปัดที่ปลายทางใช้จริงกับก้อนนี้ + คำอธิบายว่าได้มายังไง

    คืนค่าที่**หยาบกว่า**ระหว่างที่ทะเบียนคาดไว้กับที่วัดได้จริง เพราะสองอย่างนี้
    ตอบคนละคำถาม: ทะเบียนบอก "เราต้องการกี่ตำแหน่ง" ก้อนจริงบอก "ได้มากี่ตำแหน่ง"
    ค่าที่ใช้ตัดสินคุณภาพบทต้องเป็นอย่างหลังเสมอเมื่อมันแย่กว่า
    """
    try:
        wanted = int(profile_for(evidence.get("asset") or "")["decimals"])
    except (SnapshotUnusable, KeyError, TypeError, ValueError):
        # หัวข้อที่ยังไม่ลงทะเบียนไม่ควรมาถึงชั้นนี้ แต่ถ้ามาถึง ให้ถอยไปใช้ค่าที่
        # ปลายทางเคยใช้กับทุกสินทรัพย์ แทนที่จะปล่อยผ่านเพราะหาทะเบียนไม่เจอ
        return LEGACY_PROVIDER_STEP, "ไม่มีทะเบียนหน้าตาของหัวข้อนี้ ใช้ขั้นเดิมของปลายทาง"
    samples = price_scale_values(evidence)
    if len(samples) < MIN_SAMPLES_TO_INFER_STEP:
        return 10.0 ** -wanted, f"ตัวอย่างค่าราคามีแค่ {len(samples)} ตัว ใช้ทศนิยมตามทะเบียน ({wanted})"
    # **เอาอันดับสอง ไม่ใช่ค่าสูงสุด** — ค่าเดียวที่ผิดปกติต้องไม่ยกทั้งก้อนขึ้น
    # ค่าที่ผ่านการคำนวณด้วย float มาก่อน (0.1 + 0.2) มีทศนิยม 17 ตำแหน่งตามหน้าตา
    # ของมันจริง ๆ ถ้าใช้ `max()` ค่าเดียวแบบนั้นจะกลบก้อนที่ปัดหยาบทั้งก้อนได้เงียบ ๆ
    # ⇒ ต้องมีอย่างน้อยสองค่าที่ละเอียดถึงระดับนั้น จึงจะนับว่าก้อนละเอียดจริง
    ranked = sorted((_decimal_places(value) for value in samples), reverse=True)
    seen = ranked[1]
    if seen >= wanted:
        return 10.0 ** -wanted, f"ก้อนให้ทศนิยมถึง {seen} ตำแหน่ง ตรงหรือดีกว่าที่ทะเบียนต้องการ ({wanted})"
    return 10.0 ** -seen, (
        f"ก้อนให้ทศนิยมสูงสุดแค่ {seen} ตำแหน่งจาก {len(samples)} ค่าที่เป็นราคา "
        f"ขณะที่ทะเบียนของหัวข้อนี้ต้องการ {wanted}")


def ensure_resolution(evidence: dict, *, strict: bool = False) -> dict:
    """ด่านความละเอียด — วัดว่าค่า**ที่เป็นราคา**หยาบเกินกว่าจะแยกออกจากกันไหม

    **การปัดของปลายทางไม่ได้กระทบทุกค่าเท่ากัน** (วัดจริง 2026-08-05):

        พังเมื่อราคาต่ำ   SMA/EMA · pivot ทุกกรอบ — เป็นค่าที่อยู่ในหน่วยราคา
        ไม่พังเลย        RSI · Stochastic · CCI · ADX (สเกล 0-100 คนละหน่วยกับราคา)
                        สัญญาณรวมและคะแนนรายกรอบ (เป็นหมวด ไม่ใช่ตัวเลขราคา)
                        ราคาสด สูงสุด ต่ำสุด กรอบ 52 สัปดาห์ ผลตอบแทน ปฏิทิน (ช่อง quote
                        กับ performance ยังเต็มความละเอียด)

    ⚠️ **MACD กับ Momentum เคยอยู่ในกลุ่ม "ไม่พัง" ซึ่งผิด** — สองตัวนี้อยู่ในสเกลราคา
    ไม่ใช่ 0-100 ⇒ MACD ของ EUR/USD เคยถูกปัดเป็น `0.00` (ทีมเว็บยืนยันและแก้ให้แล้ว
    2026-08-06 · ได้ `0.00314` กลับมา) · ด่านนี้ไม่ได้ใช้สองตัวนั้นวัด เพราะค่าใกล้ศูนย์
    ทำให้จำนวนทศนิยมอ่านออกมาสูงกว่าความจริง แต่บันทึกไว้กันวินิจฉัยผิดในอนาคต

    ⇒ ก้อนที่หยาบยัง**เขียนบทได้จริง** แค่ต้องไม่เอาค่าที่ปัดมาชนกันไปแสดงเป็นคนละเส้น
    ตัวเขียนจึงยุบเส้นค่าเฉลี่ยที่ค่าตรงกันให้เหลือบรรทัดเดียว และตารางระดับก็ยุบซ้ำอยู่แล้ว
    ซึ่งตรงกับกติกาแกน "evidence ไม่พอ = ตัดประโยคนั้นเงียบ" มากกว่าการทิ้งทั้งหัวข้อ

    `strict=True` ไว้ให้คนที่อยากได้พฤติกรรมหยุดสายท่อแบบเดิม (เช่นตอนตรวจคุณภาพ)
    ค่าตั้งต้นคือ **เขียนต่อแล้วติดธงไว้** ตามที่ผู้ใช้สั่ง 2026-08-05
    """
    evidence["coarse_prices"] = False
    quote = evidence.get("quote") or {}
    high, low = quote.get("high"), quote.get("low")
    if high is None or low is None:
        return evidence
    day_range = abs(float(high) - float(low))
    if day_range <= 0:
        return evidence
    step, how = provider_step(evidence)
    evidence["provider_step"] = step
    ratio = step / day_range
    if ratio <= MAX_STEP_OF_DAY_RANGE:
        return evidence

    evidence["coarse_prices"] = True
    evidence["coarse_note"] = (
        f"ค่าที่เป็นราคาถูกปัดเป็นขั้นละ {step:g} ({how}) "
        f"ซึ่งกว้าง {ratio * 100:.0f}% ของกรอบราคาทั้งวัน ({day_range:.5f}) "
        f"⇒ เส้นค่าเฉลี่ยและจุดหมุนของ {evidence.get('asset')} บางเส้นปัดมาชนกัน "
        "ตัวเขียนยุบเส้นที่ค่าตรงกันให้เหลือบรรทัดเดียวแล้ว "
        "· ค่าที่ไม่ใช่ราคา (RSI/Stochastic/CCI/ADX/สัญญาณรวม) กับราคาสดไม่กระทบ "
        "· ทีมเว็บแก้ทศนิยมตามสินทรัพย์ให้แล้ว 2026-08-06 (E7) "
        "⇒ เจอธงนี้อีกแปลว่าปลายทาง**ถอยกลับ** ต้องแจ้งทีมเว็บ ห้ามปัดคืนเอง")
    if strict:
        raise SnapshotTooCoarse(evidence["coarse_note"])
    return evidence


def fetch(asset: str = "xauusd", *, key: str | None = None, base_url: str = BASE_URL,
          timeout: int = DEFAULT_TIMEOUT, max_age_minutes: int = MAX_AGE_MINUTES) -> dict:
    """ดึงสดแล้วคืน evidence pack ที่ผ่านด่านความสดแล้ว — ทางที่ผู้เรียกทั่วไปควรใช้"""
    payload = fetch_payload(asset, key=key, base_url=base_url, timeout=timeout)
    return ensure_fresh(normalize(payload), max_age_minutes)


def age_minutes(evidence: dict) -> float | None:
    stamp = evidence.get("generated_at")
    if not stamp:
        return None
    generated = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - generated).total_seconds() / 60


def _mend(value):
    """ซ่อมข้อความไทยที่ถูกบันทึกเป็น latin-1 ของไบต์ UTF-8"""
    if not isinstance(value, str):
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _indicators(block: dict) -> dict:
    """แปลงลิสต์อินดิเคเตอร์เป็น dict คีย์ตามชื่อ เพื่อให้ชั้นบทความหยิบตรงตัวได้"""
    result = {}
    for item in (block or {}).get("indicators") or []:
        name = item.get("name")
        if name:
            result[name] = {"signal": item.get("signal"), "value": item.get("value")}
    return result


def load(path: Path | str) -> dict:
    """อ่านไฟล์ snapshot แล้วคืน evidence pack ที่ชั้นนักเขียนใช้ได้ทันที"""
    raw = Path(path).read_text(encoding="utf-8-sig")
    return normalize(json.loads(raw))


def normalize(payload: dict) -> dict:
    if not payload.get("ok"):
        raise SnapshotUnusable("snapshot ตอบ ok:false — ห้ามเขียนบทความจากก้อนนี้")
    quote = payload.get("quote") or {}
    if quote.get("price") is None:
        raise SnapshotUnusable("snapshot ไม่มีราคาล่าสุด — ห้ามเขียนบทความจากก้อนนี้")

    generated = payload.get("generatedAt") or ""
    local = None
    if generated:
        stamp = datetime.fromisoformat(generated.replace("Z", "+00:00"))
        local = stamp.astimezone(BANGKOK)

    by_tf = {}
    for name in TIMEFRAMES:
        block = (payload.get("technicalsByTf") or {}).get(name) or {}
        if block:
            by_tf[name] = {
                "summary": block.get("summary"),
                "counts": block.get("counts") or {},
                "indicators": _indicators(block),
                "pivots": block.get("pivots") or {},
                "price": block.get("price"),
            }

    daily = payload.get("technicals") or {}
    calendar = []
    for event in ((payload.get("calendar") or {}).get("events") or []):
        calendar.append({
            "at": event.get("at"),
            "country": event.get("country"),
            "impact": event.get("impact"),
            "title": _mend(event.get("title") or ""),
            "previous": event.get("previous"),
            "forecast": event.get("forecast"),
            "actual": event.get("actual"),
        })

    news = _news_items(payload.get("news"), channel="news")
    # `macroNews` = ข่าวที่เว็บคัดมาแล้วว่าเป็น**ตัวขับของสินทรัพย์นั้น** (ขึ้นจริง 2026-08-06)
    # ต่างจาก `news` ที่คัดด้วยป้ายสินทรัพย์ตรง ๆ ⇒ สองช่องนี้ทับกันได้ ยุบซ้ำด้านล่าง
    macro_news = _news_items(payload.get("macroNews"), channel="macro")

    return {
        "asset": payload.get("asset"),
        "generated_at": generated,
        "local_time": local.strftime("%H:%M") if local else None,
        "local_date": local.strftime("%Y-%m-%d") if local else None,
        "quote": quote,
        "performance": payload.get("performance") or {},
        "daily": {
            "summary": daily.get("summary"),
            "counts": daily.get("counts") or {},
            "indicators": _indicators(daily),
            "pivots": daily.get("pivots") or {},
        },
        "by_tf": by_tf,
        "recent_daily": payload.get("recentDaily") or [],
        "recent_by_tf": payload.get("recentByTf") or {},
        "news": news,
        "macro_news": macro_news,
        "headlines": _merge_headlines(news, macro_news),
        "calendar": calendar,
    }


def _news_items(rows, *, channel: str) -> list[dict]:
    """แปลงรายการข่าวจากก้อน — เก็บ `url`/`slug`/`category`/`subcat` ที่เพิ่มมา 2026-08-06

    🪤 **ทั้งสองช่องให้แค่พาดหัวกับลิงก์ ไม่มีเนื้อข่าว** (ทีมเว็บกำกับมาในใบตอบ E3)
    ⇒ ห้ามสรุปว่าข่าวชิ้นนั้นเขียนว่าอะไรจากพาดหัวอย่างเดียว · ที่นี่จึงเก็บ `url` ไว้
    เพื่อให้คนตามอ่านต่อได้ ไม่ใช่เพื่อให้ชั้นบทความเดาเนื้อหาแทน
    """
    items = []
    for item in rows or []:
        title = _mend(item.get("title") or "")
        if not title:
            continue
        items.append({
            "title": title,
            "published_at": item.get("published_at"),
            "slug": item.get("slug"),
            "url": item.get("url"),
            "category": item.get("category"),
            "subcat": item.get("subcat"),
            "channel": channel,
        })
    return items


def _merge_headlines(news: list[dict], macro_news: list[dict]) -> list[dict]:
    """ชุดพาดหัวที่ชั้นบทความใช้ — `news` ก่อน แล้วต่อด้วย `macroNews` ที่ยังไม่ซ้ำ

    ยุบซ้ำด้วย `slug` ก่อน แล้วค่อยถอยไปใช้พาดหัว เพราะ slug คือกุญแจจริงของเว็บ
    ส่วนพาดหัวเป็นตาข่ายรองสำหรับก้อนเก่าที่ยังไม่มี slug

    ลำดับสำคัญ: `news` ติดป้ายสินทรัพย์ตรง ๆ จึงเกี่ยวข้องกว่า `macroNews` ที่คัดมาจาก
    ตัวขับระดับมหภาค · **ห้ามสลับลำดับเพื่อให้บทมีข่าวเยอะขึ้น**
    """
    merged, seen = [], set()
    for item in list(news) + list(macro_news):
        key = item.get("slug") or item.get("title")
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


PIVOT_KEYS = ("p", "r1", "r2", "r3", "s1", "s2", "s3")


def pivot_values(evidence: dict) -> list[float]:
    """ค่า pivot ทุกตัวทุกกรอบเวลา — **ทะเบียนอนุญาต** ของด่านตรวจและหมุดกราฟ

    ชุดนี้คือ "ค่าไหนมีสิทธิ์ถูกอ้างถึงได้" ไม่ใช่ "ค่าไหนควรขึ้นบท" — ตัวเขียนบท
    เลือกใช้เพียงบางกรอบเวลาจากชุดนี้ (ดู `wcb_writers._levels_by_frame`) เพราะการ
    เทจุดหมุนทุกกรอบรวมกองเดียวแล้วหยิบตัวใกล้ราคาที่สุด ทำให้จุดหมุนกรอบ 30 นาที
    ชนะจุดหมุนรายวันทุกครั้ง ⇒ บทรายวันได้ด่านที่แคบกว่าที่ราคาเดินจริงหลายสิบเท่า
    (ทอง 2026-08-05: หกด่านกินช่วง 0.53% ขณะราคาแกว่งจริง 3.48%)

    **ห้ามตัดกรอบเวลาออกจากฟังก์ชันนี้** — ทำแล้วด่านตรวจจะเข้มขึ้นโดยไม่ได้ตั้งใจ
    และปฏิเสธเส้นที่ปลายทางส่งมาจริง การเลือกชุดเป็นหน้าที่ของชั้นตัวเขียน
    """
    values: list[float] = []
    groups = [evidence["daily"]["pivots"]]
    groups += [block["pivots"] for block in evidence["by_tf"].values()]
    for group in groups:
        for key in PIVOT_KEYS:
            if (group or {}).get(key) is not None:
                values.append(float(group[key]))
    return values


def upcoming(evidence: dict, *, impacts=("High", "Medium"), limit: int | None = None) -> list[dict]:
    """รายการปฏิทินที่ยังไม่ถึง เรียงตามเวลา — ฐานของหัวข้อปัจจัยพื้นฐานทุกสไตล์"""
    cutoff = evidence.get("local_date") or ""
    items = [event for event in evidence["calendar"]
             if event["impact"] in impacts and str(event["at"] or "")[:10] >= cutoff]
    items.sort(key=lambda event: str(event["at"] or ""))
    return items[:limit] if limit else items
