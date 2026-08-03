import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).parents[2]
WORKSPACE_DIR = PROJECT_DIR.parents[1]
SKILL_DIR = WORKSPACE_DIR / ".agents" / "skills" / "compose-wcb-daily-analysis"
CONTRACT_PATH = Path(__file__).parents[1] / "docs" / "WCB-DAILY-OUTPUT-CONTRACT.md"
TEMPLATE_PATH = Path(__file__).parents[1] / "templates" / "article-draft-v2.md"


class DeepResearchOutputContractTests(unittest.TestCase):
    def test_shared_composition_skill_exists(self):
        self.assertTrue((SKILL_DIR / "SKILL.md").is_file())
        self.assertTrue((SKILL_DIR / "references" / "output-contract.md").is_file())

    def test_skill_requires_exact_separate_public_headings(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("ห้ามรวมหัวข้อ", skill)
        for heading in ("## แนวคิดการซื้อขาย", "## ข่าวและสิ่งที่ต้องติดตาม", "## ภาพและลิงก์ประกอบ", "## คำเตือนความเสี่ยง"):
            with self.subTest(heading=heading):
                self.assertIn(heading, skill)

    def test_contract_contains_required_reader_sections(self):
        self.assertTrue(CONTRACT_PATH.is_file())
        contract = CONTRACT_PATH.read_text(encoding="utf-8")
        required = (
            "Market Snapshot",
            "สรุปตลาด",
            "ปัจจัยพื้นฐาน",
            "วิเคราะห์ทางเทคนิค",
            "ระดับตัดสินใจ",
            "แนวคิดการซื้อขาย",
            "ข่าวและสิ่งที่ต้องติดตาม",
            "ภาพและลิงก์ประกอบ",
            "คำเตือนความเสี่ยง",
        )
        for section in required:
            with self.subTest(section=section):
                self.assertIn(section, contract)

    def test_contract_requires_decision_and_provenance_fields(self):
        self.assertTrue(CONTRACT_PATH.is_file())
        contract = CONTRACT_PATH.read_text(encoding="utf-8")
        for field in (
            "instrument_type",
            "cutoff_at",
            "timezone",
            "data_status",
            "Trigger",
            "Target",
            "Invalidation",
            "No-trade",
            "source_log",
        ):
            with self.subTest(field=field):
                self.assertIn(field, contract)

    def test_all_project_agents_reference_the_new_contract(self):
        agents_dir = PROJECT_DIR / "Agents"
        for agent_file in sorted(agents_dir.glob("*/AGENTS.md")):
            with self.subTest(agent=agent_file.parent.name):
                text = agent_file.read_text(encoding="utf-8")
                self.assertIn("WCB Daily Output Contract v2", text)

    def test_editor_and_qa_register_shared_skill(self):
        for agent in ("00-WCB-Chart-Editor", "05-WCB-Article-QA"):
            registry = (PROJECT_DIR / "Agents" / agent / "SKILLS.md").read_text(encoding="utf-8")
            with self.subTest(agent=agent):
                self.assertIn("compose-wcb-daily-analysis", registry)

    def test_article_template_exposes_required_decision_blocks(self):
        self.assertTrue(TEMPLATE_PATH.is_file())
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        for marker in ("## Market Snapshot", "## แนวคิดการซื้อขาย", "Trigger", "Target", "Invalidation", "No-trade"):
            with self.subTest(marker=marker):
                self.assertIn(marker, template)


if __name__ == "__main__":
    unittest.main()
