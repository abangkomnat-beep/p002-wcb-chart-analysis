from tools import human_copydesk


def test_removes_bilingual_translation_but_keeps_indicator_and_source():
    text = ("## ระดับสำคัญ (Key Levels)\n"
            "RSI(14) อยู่ที่ 55 และทองคำ (XAU/USD) ยังแข็ง\n"
            "(ที่มา: WorldClassBroker)\n")
    result = human_copydesk.naturalize(text)
    assert "(Key Levels)" not in result
    assert "RSI(14)" in result
    assert "(XAU/USD)" in result
    assert "(ที่มา: WorldClassBroker)" in result


def test_rewrites_internal_state_and_system_voice():
    result = human_copydesk.naturalize(
        "* **สถานะที่ระบบจัดให้:** `EXPANSION`\nระบบจัดสถานะรอบนี้เป็นช่วงกางออก")
    assert "ระบบจัด" not in result
    assert "EXPANSION" not in result
    assert "ช่วงแกว่งกว้างกว่าปกติ" in result
    assert human_copydesk.findings(result) == []


def test_preserves_markdown_image_target():
    text = "![กราฟ XAU/USD](xauusd-d1-2026-08-17.webp)"
    assert human_copydesk.naturalize(text) == text
