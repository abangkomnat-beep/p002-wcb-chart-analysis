import unittest

from tools.language_regression import analyze_corpus


class LanguageRegressionTests(unittest.TestCase):
    def test_clean_corpus_passes(self):
        result = analyze_corpus([
            {"id": "a", "style_profile": "A", "text": "ตลาดเปิดด้วยแรงซื้อ\nแนวรับยังอยู่ในกรอบ"},
            {"id": "b", "style_profile": "D", "text": "ราคาทดสอบแนวต้าน\nแรงขายยังไม่ชัดเจน"},
        ])
        self.assertTrue(result["passed"])
        self.assertEqual(result["findings"], [])

    def test_repeated_opening_and_robotic_phrase_fail(self):
        text = "ตลาดยังทรงตัว\nจากข้อมูลดังกล่าว แนวโน้มยังต้องติดตาม"
        result = analyze_corpus([{"id": str(i), "text": text} for i in range(4)])
        codes = {item["code"] for item in result["findings"]}
        self.assertFalse(result["passed"])
        self.assertIn("OPENING_REPETITION", codes)
        self.assertIn("ROBOTIC_PHRASE", codes)

    def test_connector_density_is_explainable(self):
        text = " ".join(["อย่างไรก็ตาม"] * 20)
        result = analyze_corpus([{"id": "a", "text": text}], max_connector_rate_per_1000=1)
        finding = next(item for item in result["findings"] if item["code"] == "CONNECTOR_DENSITY")
        self.assertEqual(finding["count"], 20)
        self.assertGreater(finding["rate_per_1000_words"], 1)

    def test_bad_input_fails_closed(self):
        with self.assertRaises(ValueError):
            analyze_corpus([{"id": "missing-text"}])


if __name__ == "__main__":
    unittest.main()
