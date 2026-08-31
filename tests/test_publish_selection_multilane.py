import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import publish_selection  # noqa: E402


class MultiLaneSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.day = Path(self.tmp.name) / "31-08-2026"
        self.policy = publish_selection.load_policy()
        self._article("D-โครงสร้างกราฟ", "xauusd.md", "xauusd-levels-2026-08-31",
                      ["xauusd-d1-structure-2026-08-28.webp",
                       "xauusd-d1-levels-2026-08-28.webp"])
        self._article("E-อินดิเคเตอร์", "xauusd.md", "xauusd-signals-2026-08-31",
                      ["xauusd-h1-indicators-2026-08-31.webp"])
        self._article("M-BTCUSD-H1-Visual-Daily", "btc.md",
                      "btcusd-levels-2026-08-31",
                      ["btcusd-style-m-h1-2026-08-31.webp"])
        for asset in ("eurusd", "usdjpy"):
            self._article("L-Forex-Daily", f"{asset}.md",
                          f"{asset}-forex-daily-plan-2026-08-31",
                          [f"{asset}-forex-daily-h1-plan.webp",
                           f"{asset}-forex-daily-m15-trigger.webp"])

    def _article(self, folder: str, name: str, slug: str, images: list[str]) -> None:
        target = self.day / folder
        target.mkdir(parents=True, exist_ok=True)
        refs = "\n".join(f"![chart]({image})" for image in images)
        extra_meta = ("cutoff: 2026-08-31T11:00:00+07:00\n"
                      if folder == "M-BTCUSD-H1-Visual-Daily" else "")
        footer = ("\n*หลักฐาน: ตัดข้อมูลเมื่อ 31/08/2026 11:34 น. เวลาไทย*\n"
                  if folder == "L-Forex-Daily" else "")
        (target / name).write_text(
            f"---\nslug: {slug}\n{extra_meta}---\n\n# test\n\n{refs}\n{footer}",
            encoding="utf-8")
        for image in images:
            Image.new("RGB", (120, 80), "white").save(target / image, format="WEBP")

    def test_monday_has_five_articles(self):
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "ready")
        self.assertEqual((result["ready_count"], result["expected_count"]), (5, 5))
        root = Path(result["directory"])
        self.assertEqual(len(list(root.rglob("*.md"))), 5)
        self.assertEqual(len(list((root / "04-Forex-Style-L").glob("*.md"))), 2)
        self.assertFalse(any(path.name == "อ่านก่อน.md" for path in root.rglob("*")))

    def test_missing_one_forex_article_is_partial_and_stale_root_is_removed(self):
        stale = self.day / self.policy["selection_folder"] / "stale.txt"
        stale.parent.mkdir(parents=True)
        stale.write_text("old", encoding="utf-8")
        (self.day / "L-Forex-Daily" / "eurusd.md").unlink()
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "partial")
        self.assertEqual((result["ready_count"], result["expected_count"]), (4, 5))
        self.assertFalse(stale.exists())

    def test_policy_is_local_only(self):
        self.assertEqual(self.policy["schema_version"], 2)
        self.assertTrue(self.policy["manual_only"])
        self.assertFalse(self.policy["external_publish"])
        self.assertEqual(self.policy["network_authority"], "none")
        forex = next(lane for lane in self.policy["upload_lanes"] if lane["id"] == "forex_l")
        self.assertEqual(forex["max_articles"], 2)

    def test_stale_chart_fails_only_its_lane(self):
        folder = self.day / "E-อินดิเคเตอร์"
        current = folder / "xauusd-h1-indicators-2026-08-31.webp"
        stale = folder / "xauusd-h1-indicators-2026-08-20.webp"
        current.rename(stale)
        article = folder / "xauusd.md"
        article.write_text(article.read_text(encoding="utf-8").replace(current.name, stale.name),
                           encoding="utf-8")
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "partial")
        self.assertEqual((result["ready_count"], result["expected_count"]), (4, 5))
        failed = next(item for item in result["lanes"] if item["id"] == "gold_e")
        self.assertIn("stale", failed["reason"])


if __name__ == "__main__":
    unittest.main()
