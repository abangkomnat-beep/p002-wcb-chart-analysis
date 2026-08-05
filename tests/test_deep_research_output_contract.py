import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).parents[2]
REPO_DIR = Path(__file__).parents[1]
# สกิลประจำโปรเจกต์อยู่ใน Repo เพื่อให้ติดไปกับการส่งมอบ (ผู้ใช้อนุมัติ 2026-08-04)
# เดิมชี้ไป <workspace>/.agents/skills/ ซึ่งปลดระวางเข้า Projects/_Archive/ แล้ว
SKILL_DIR = REPO_DIR / ".claude" / "skills" / "compose-wcb-daily-analysis"
CONTRACT_PATH = Path(__file__).parents[1] / "docs" / "WCB-DAILY-OUTPUT-CONTRACT.md"
TEMPLATE_PATH = Path(__file__).parents[1] / "templates" / "article-voice-v1.md"
LEGACY_TEMPLATE_PATH = Path(__file__).parents[1] / "templates" / "article-draft-v2.md"


class DeepResearchOutputContractTests(unittest.TestCase):
    def test_shared_composition_skill_exists(self):
        self.assertTrue((SKILL_DIR / "SKILL.md").is_file())
        self.assertTrue((SKILL_DIR / "references" / "output-contract.md").is_file())

    def test_skill_teaches_the_four_part_story_structure(self):
        """สกิลต้องสอนโครง 4 ช่วงของ v3.2

        รุ่นก่อนหน้าเทสนี้บังคับให้สกิลมีชุดหัวข้อ 9 ข้อของ v2 (`## แนวคิดการซื้อขาย` ฯลฯ)
        ซึ่งเลิกใช้ตั้งแต่ v3.1 — เทสจึงกลายเป็นตัวล็อกให้เอกสารค้างรุ่นเก่าเสียเอง
        """
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        for marker in (
            "Contract v3.2",
            "ข้อมูลเทคนิค (Technical Analysis)",
            "เปิดตลาดที่ระดับ",
            "แนวรับ {s1} / {s2} / {s3}",
            "350–560 คำ",
            "ตัดทั้งช่วงแบบเงียบ",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, skill)
        # ชุดหัวข้อเดิมต้องถูกประกาศเลิกใช้ ไม่ใช่ยังเป็นข้อบังคับ
        self.assertIn("เลิกใช้แล้ว", skill)
        self.assertNotIn("ใช้หัวข้อต่อไปนี้แยกกันและเรียงตามลำดับ", skill)

    def test_contract_describes_the_voice_v1_story_structure(self):
        """contract v3.1 ต้องยึดโครงเล่าเรื่อง 4 ช่วงของ Voice Spec — ไม่ใช่ชุดหัวข้อเดิม"""
        self.assertTrue(CONTRACT_PATH.is_file())
        contract = CONTRACT_PATH.read_text(encoding="utf-8")
        required = (
            "WCB Voice Spec v1",
            "ข้อมูลเทคนิค (Technical Analysis)",
            "เปิดตลาดที่ระดับ",
            "แนวรับ {s1} / {s2} / {s3}",
            "round_half_up",
            "350–560 คำ",
            "denylist",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, contract)
        # v1.1: contract ต้องบอกว่าหมายเหตุ/disclaimer ถูกย้ายไป internal แล้ว
        self.assertIn("omitted_public_lines", contract)
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

    def test_all_project_agents_reference_the_current_contract(self):
        """ทุก AGENTS.md ต้องชี้ contract รุ่นที่ใช้จริง ไม่ใช่รุ่นที่เลิกใช้แล้ว

        เทสนี้เคยล็อกค่าไว้ที่ v2 ทำให้เอกสารของ Agent ทั้ง 6 ตัวค้างรุ่นอยู่ข้ามรุ่น
        v3.1 และ v3.2 โดยชุดเทสยังเขียว — แก้เป็นรุ่นปัจจุบันเมื่อ 2026-08-04
        """
        agents_dir = PROJECT_DIR / "Agents"
        agent_files = sorted(agents_dir.glob("*/AGENTS.md"))
        # กันเทสผ่านแบบหลอกเมื่อโฟลเดอร์ถูกย้ายหรือเปลี่ยนชื่อ
        self.assertTrue(agent_files, "ไม่พบ AGENTS.md ของ Agent ใดเลย")
        for agent_file in agent_files:
            with self.subTest(agent=agent_file.parent.name):
                text = agent_file.read_text(encoding="utf-8")
                self.assertIn("WCB Daily Output Contract v3.2", text)
                self.assertNotIn("Contract v2", text)

    def test_daily_only_limitation_is_documented_for_analysts(self):
        """ข้อจำกัด D1 ต้องเขียนกำกับไว้ในเอกสารที่นักวิเคราะห์อ่าน

        มติผู้ใช้ 2026-08-04: ยอมรับข้อจำกัดนี้และห้ามเพิ่ม H4/H1 เข้าโปรเจกต์นี้
        ถ้าวันหนึ่งเปิด intraday จริง เทสนี้จะเป็นจุดที่บังคับให้กลับมาแก้เอกสารทุกใบ
        """
        for name in ("01-Technical-Trend", "02-Technical-Momentum", "03-Technical-Levels"):
            with self.subTest(agent=name):
                text = (PROJECT_DIR / "Agents" / name / "AGENTS.md").read_text(encoding="utf-8")
                self.assertIn("D1", text)
        readme = (PROJECT_DIR / "Agents" / "README.md").read_text(encoding="utf-8")
        self.assertIn("D1", readme)

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
