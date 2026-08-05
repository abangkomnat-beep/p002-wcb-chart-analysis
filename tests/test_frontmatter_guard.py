"""ยาม frontmatter — กันของที่เครื่องมือภายนอกแทรกไม่ให้ติดไปกับไฟล์ที่ส่งมอบ

เหตุที่ต้องมีชุดนี้: 2026-08-05 พบว่าบทความที่ส่งมอบ 12/12 ใบ และไฟล์ในรีโปอีก 27 ใบ
มีช่อง `permalink` ของ basic-memory ติดอยู่ โดยไม่มีด่านไหนในระบบเห็นเลย
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import frontmatter_guard  # noqa: E402


ARTICLE = """---
title: 'XAU/USD แกว่งระหว่างเส้นค่าเฉลี่ย'
symbol: XAU/USD
instrument_type: spot_metal
cutoff_at: '2026-08-05T09:29:46+00:00'
timezone: Asia/Bangkok
permalink: library/projects/p002/output/05-082026/1-nthaar/xauusd
---

# XAU/USD แกว่งระหว่างเส้นค่าเฉลี่ย

เนื้อบทความ
"""

WHOLE_BLOCK_INJECTED = """---
title: README
type: note
permalink: library/projects/p002/repo/readme
---

# P002 WCB Chart Analysis
"""


class ลบเฉพาะของที่พิสูจน์ได้ว่าเป็นของเครื่องมือ(unittest.TestCase):

    def test_ช่อง_permalink_ถูกลบ_ช่องของบทความอยู่ครบ(self):
        cleaned, removed = frontmatter_guard.clean(ARTICLE)
        self.assertEqual(removed, ["permalink"])
        self.assertNotIn("permalink", cleaned)
        for key in frontmatter_guard.ARTICLE_KEYS:
            self.assertIn(f"{key}:", cleaned)
        self.assertIn("# XAU/USD แกว่งระหว่างเส้นค่าเฉลี่ย", cleaned)

    def test_เนื้อบทความไม่ถูกแตะ(self):
        cleaned, _ = frontmatter_guard.clean(ARTICLE)
        self.assertEqual(cleaned.split("---\n")[-1], ARTICLE.split("---\n")[-1])

    def test_บล็อกที่เป็นของเครื่องมือล้วนถูกถอดทั้งก้อน(self):
        """ไฟล์ที่เดิมไม่มี frontmatter ต้องกลับไปไม่มีเหมือนเดิม ไม่ใช่เหลือบล็อกเปล่า"""
        cleaned, removed = frontmatter_guard.clean(WHOLE_BLOCK_INJECTED)
        self.assertEqual(removed, ["permalink", "title", "type"])
        self.assertTrue(cleaned.startswith("# P002"))
        self.assertNotIn("---", cleaned)

    def test_ไฟล์สะอาดต้องไม่ถูกแก้แม้แต่ไบต์เดียว(self):
        clean_text = "---\ntitle: A\nsymbol: B\n---\n\nเนื้อหา\n"
        cleaned, removed = frontmatter_guard.clean(clean_text)
        self.assertEqual(removed, [])
        self.assertEqual(cleaned, clean_text)

    def test_ไฟล์ที่ไม่มี_frontmatter_เลยไม่ถูกแตะ(self):
        text = "# หัวข้อ\n\nเนื้อหา\n"
        self.assertEqual(frontmatter_guard.clean(text), (text, []))

    def test_บล็อกที่เปิดแล้วไม่ปิดถือว่าไม่ใช่_frontmatter(self):
        """กันตัวยามไปตัดเนื้อไฟล์ที่บังเอิญขึ้นต้นด้วยเส้นคั่น"""
        text = "---\nนี่คือเส้นคั่นในเนื้อหา ไม่ใช่ frontmatter\n"
        self.assertEqual(frontmatter_guard.clean(text), (text, []))

    def test_ช่องแปลกอื่นถูกรายงานแต่ไม่ถูกลบ(self):
        """ของที่เราไม่แน่ใจว่าใครใส่ ปล่อยให้คนเห็น ดีกว่าลบเงียบ"""
        text = "---\ntitle: A\nbyline: someone\n---\n\nเนื้อหา\n"
        self.assertEqual(frontmatter_guard.foreign_keys(text), ["byline"])
        self.assertEqual(frontmatter_guard.clean(text)[1], [])


class ไล่ทั้งโฟลเดอร์(unittest.TestCase):

    def test_scan_รายงานแล้วแก้ได้จริง(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "ลึก").mkdir()
            dirty = root / "ลึก" / "xauusd.md"
            dirty.write_text(ARTICLE, encoding="utf-8")
            (root / "ok.md").write_text("# ปกติ\n", encoding="utf-8")

            found = frontmatter_guard.scan(root)
            self.assertEqual(len(found), 1)
            self.assertIn("permalink", dirty.read_text(encoding="utf-8"))

            frontmatter_guard.scan(root, fix=True)
            self.assertNotIn("permalink", dirty.read_text(encoding="utf-8"))
            self.assertEqual(frontmatter_guard.scan(root), [])

    def test_คำสั่งบรรทัดคำสั่งตกเมื่อเจอของแปลกและยังไม่แก้(self):
        """ขั้นตรวจก่อนส่งต้องสะดุดตรงนี้ ไม่ใช่ผ่านไปแล้วค่อยรู้ทีหลัง"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "a.md").write_text(ARTICLE, encoding="utf-8")
            self.assertEqual(frontmatter_guard.main([str(root)]), 1)
            self.assertEqual(frontmatter_guard.main([str(root), "--fix"]), 0)
            self.assertEqual(frontmatter_guard.main([str(root)]), 0)


class ไฟล์ของรีโปเองต้องสะอาด(unittest.TestCase):
    """ด่านที่ขาดไปตอนนั้น — ถ้ามีตัวนี้ตั้งแต่แรก เรื่อง 2026-08-05 จะถูกจับได้ในรอบเทส

    ที่อันตรายที่สุดคือ `tests/fixtures/` — เทสหลายชุดเทียบผลกับไฟล์พวกนี้
    ของนอกระบบแก้ fixture ได้เท่ากับแก้เฉลยของเทส โดยไม่มีอะไรฟ้อง
    """

    def test_ไม่มีช่องแปลกปลอมในไฟล์_md_ของรีโป(self):
        repo = Path(__file__).resolve().parents[1]
        dirty = []
        for path in sorted(repo.rglob("*.md")):
            if ".claude" in path.parts:  # worktree ชั่วคราว ไม่ใช่ของที่ส่งมอบ
                continue
            removed = frontmatter_guard.clean(path.read_text(encoding="utf-8"))[1]
            if removed:
                dirty.append(f"{path.relative_to(repo)} · {', '.join(removed)}")
        self.assertEqual(dirty, [], "มีเครื่องมือภายนอกเขียนแทรกในไฟล์ของรีโป — "
                                    "ล้างด้วย python -m tools.frontmatter_guard . --fix "
                                    "แล้วหาว่าใครเป็นคนเขียน")


if __name__ == "__main__":
    unittest.main()
