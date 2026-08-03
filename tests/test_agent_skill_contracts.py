import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).parents[2]
WORKSPACE_DIR = PROJECT_DIR.parents[1]


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
                skill_file = WORKSPACE_DIR / ".agents" / "skills" / skill / "SKILL.md"
                self.assertIn(skill, registry)
                self.assertTrue(skill_file.is_file())

    def test_momentum_skill_forbids_ad_hoc_indicator_calculation(self):
        skill = (
            WORKSPACE_DIR
            / ".agents"
            / "skills"
            / "analyze-momentum-confluence"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("ห้ามคำนวณ RSI history, MACD, Bollinger Bands, percentile", skill)
        self.assertIn("การไม่มี field เท่ากับ `unavailable`", skill)

    def test_level_skill_limits_publication_levels_to_pivots(self):
        skill = (
            WORKSPACE_DIR
            / ".agents"
            / "skills"
            / "analyze-level-reaction"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("ต้องมาจาก `technicals.pivots` เท่านั้น", skill)
        self.assertIn('"publication_levels"', skill)
        self.assertIn('"context_only"', skill)


if __name__ == "__main__":
    unittest.main()
