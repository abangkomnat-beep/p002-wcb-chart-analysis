import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).parents[2]
REPO_DIR = Path(__file__).parents[1]
# สกิลประจำโปรเจกต์อยู่ใน Repo เพื่อให้ติดไปกับการส่งมอบ (ผู้ใช้อนุมัติ 2026-08-04)
# เดิมชี้ไป <workspace>/.agents/skills/ ซึ่งปลดระวางเข้า Projects/_Archive/ แล้ว
SKILLS_DIR = REPO_DIR / ".claude" / "skills"


class AgentSkillContractTests(unittest.TestCase):
    def test_each_technical_agent_registers_its_confluence_skill(self):
        contracts = (
            ("01-Technical-Trend", "analyze-trend-confluence"),
            ("02-Technical-Momentum", "analyze-momentum-confluence"),
            ("03-Technical-Levels", "analyze-level-reaction"),
        )
        for agent, skill in contracts:
            with self.subTest(agent=agent):
                registry = (PROJECT_DIR / "Agents" / agent / "SKILLS.md").read_text(encoding="utf-8")
                skill_file = SKILLS_DIR / skill / "SKILL.md"
                self.assertIn(skill, registry)
                self.assertTrue(skill_file.is_file())

    def test_momentum_skill_forbids_ad_hoc_indicator_calculation(self):
        skill = (
            SKILLS_DIR / "analyze-momentum-confluence" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("ห้ามคำนวณ RSI history, MACD, Bollinger Bands, percentile", skill)
        self.assertIn("การไม่มี field เท่ากับ `unavailable`", skill)

    def test_level_skill_limits_publication_levels_to_approved_versioned_sources(self):
        skill = (
            SKILLS_DIR / "analyze-level-reaction" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("approved_level_sources", skill)
        self.assertIn("technicals.swing_zones", skill)
        self.assertIn("ห้ามสร้างระดับด้วยสายตา", skill)
        self.assertIn('"publication_levels"', skill)
        self.assertIn('"context_only"', skill)


if __name__ == "__main__":
    unittest.main()
