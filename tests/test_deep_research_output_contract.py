import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).parents[2]
WORKSPACE_DIR = PROJECT_DIR.parents[1]
SKILL_DIR = WORKSPACE_DIR / ".agents" / "skills" / "compose-wcb-daily-analysis"
CONTRACT_PATH = Path(__file__).parents[1] / "docs" / "WCB-DAILY-OUTPUT-CONTRACT.md"
TEMPLATE_PATH = Path(__file__).parents[1] / "templates" / "article-voice-v1.md"
LEGACY_TEMPLATE_PATH = Path(__file__).parents[1] / "templates" / "article-draft-v2.md"


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

    def test_contract_describes_the_voice_v1_story_structure(self):
        """contract v3.1 ต้องยึดโครงเล่าเรื่อง 4 ช่วงของ Voice Spec — ไม่ใช่ชุดหัวข้อเดิม"""
        self.assertTrue(CONTRACT_PATH.is_file())
        contract = CONTRACT_PATH.read_text(encoding="utf-8")
        required = (
            "WCB Voice Spec v1",
            "ข้อมูลเทคนิค (Technical Analysis)",
            "เปิดตลาดที่ระดับ",
            "แนวรับ {s1} / {s2} / {s3}",
            "หมายเหตุ",
            "round_half_up",
            "250–450 คำ",
            "denylist",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, contract)
        # ชุดหัวข้อเดิมต้องถูกประกาศเลิกใช้ ไม่ใช่ยังเป็นข้อบังคับ
        self.assertIn("เลิกใช้แล้ว", contract)

    def test_contract_requires_provenance_fields(self):
        self.assertTrue(CONTRACT_PATH.is_file())
        contract = CONTRACT_PATH.read_text(encoding="utf-8")
        for field in (
            "instrument_type",
            "cutoff_at",
            "timezone",
            "data_status",
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

    def test_voice_template_exposes_the_four_part_story(self):
        self.assertTrue(TEMPLATE_PATH.is_file())
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        for marker in (
            "WCB Voice Spec v1",
            "ข้อมูลเทคนิค (Technical Analysis)",
            "วันนี้ ( [D เดือนย่อ ปี] )",
            "เปิดตลาดที่ระดับ",
            "แนวรับ [s1] / [s2] / [s3]",
            "แนวต้าน [r1] / [r2] / [r3]",
            "caption ภาษาคน 1 บรรทัด",
            "350-560 คำ",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, template)
        # แม่แบบต้องไม่มีหัวข้อย่อยและตาราง — ตรงกติกาโครงสร้างของ validator
        body = template.split("-->", 1)[1]
        self.assertNotIn("\n## ", body)
        self.assertNotIn("|", body.split("---", 1)[0])

    def test_voice_template_dropped_the_note_and_disclaimer_lines(self):
        """v1.1: ตัวบทของแม่แบบต้องไม่มีบรรทัดหมายเหตุและ disclaimer อีกต่อไป"""
        body = TEMPLATE_PATH.read_text(encoding="utf-8").split("-->", 1)[1]
        self.assertNotIn("หมายเหตุ", body)
        self.assertNotIn("บทวิเคราะห์นี้จัดทำเพื่อการศึกษา", body)
        # แต่ยังต้องมีย่อหน้าขยายของ v1.1 ครบทั้งสองช่วง
        for marker in ("วันทำการล่าสุด", "ด้านความผันผวน", "ในเชิงโครงสร้างระดับ",
                       "ในเชิงกลยุทธ์"):
            with self.subTest(marker=marker):
                self.assertIn(marker, body)

    def test_legacy_template_is_kept_for_frozen_baselines_only(self):
        # ชุด v2 แช่แข็งไว้อ่านผลงานเก่าใน OUTPUT/ — ห้ามลบจนกว่าจะเลิกอ้างอิง baseline
        self.assertTrue(LEGACY_TEMPLATE_PATH.is_file())


if __name__ == "__main__":
    unittest.main()
