"""Display-only English labels for Style D; no market-data transformations."""
from contextvars import ContextVar
from functools import wraps
import re

ACTIVE_LOCALE = ContextVar("style_d_display_locale", default="th-TH")


def localized_render(function):
    @wraps(function)
    def wrapped(*args, locale=None, **kwargs):
        selected = ACTIVE_LOCALE.get() if locale is None else locale
        if selected not in {"th-TH", "en-ZA"}:
            raise ValueError("Style D supports th-TH and en-ZA display only")
        token = ACTIVE_LOCALE.set(selected)
        try:
            return function(*args, **kwargs)
        finally:
            ACTIVE_LOCALE.reset(token)
    return wrapped


PHRASES = {
    "ผ่านกรอบย่อยแล้ว · รอปิด D1 เหนือ ": "Minor range cleared · Await D1 close above ",
    " เพื่อยืนยันขาขึ้น": " to confirm upside",
    "ยืนยันขาขึ้น · ปิด D1 เหนือเส้น": "Bullish if D1 closes above",
    "ยืนยันขาลง · ปิด D1 ต่ำกว่าฐาน": "Bearish if D1 closes below base",
    "ยืนยันขาลง · ปิด D1 ต่ำกว่า ": "Bearish if D1 closes below ",
    "ที่มา: ปฎิทินเศรษฐกิจ World Class Broker": "Source: World Class Broker economic calendar",
    "แนวต้านยืนยัน": "Confirmation resistance",
    "ราคาปัจจุบัน": "Current price",
    "จุดสูงสุด": "Peak",
    "แนวรับระยะยาว": "Long-term support",
    "แนวรับหลัก": "Main support",
    "ฐานหลัก": "Main base",
    "รวมจุดต่ำสุด 52 สัปดาห์": "Includes 52-week low",
    "ต่ำสุด 52 สัปดาห์": "52-week low",
    "เส้นกดจากยอด (ขาลง)": "Descending resistance",
    "เส้นยกจากฐาน (ขาขึ้น)": "Ascending support",
    "โซนรับ": "Support zone",
    "แนวต้าน": "Resistance",
    "แนวรับ": "Support",
    "กึ่งกลาง": "Midpoint",
    "อ้างอิง ": "Tests: ",
    " ครั้ง": "",
    "รายวัน (D1)": "Daily (D1)",
    " แท่ง": " candles",
    "ข้อมูลถึง ": "Data through ",
    "ปิด ": "Close ",
    "มากกว่าคาดการณ์": "Above forecast",
    "น้อยกว่าคาดการณ์": "Below forecast",
    "ดอกเบี้ยขึ้น": "Rate rises",
    "ดอกเบี้ยลง": "Rate falls",
    "เข้มงวด": "Hawkish",
    "ผ่อนคลาย": "Dovish",
    "รอผลจริง": "Await actual",
    "โดยตรง": "Direct",
    "โดยอ้อม": "Indirect",
    "ปานกลาง": "Medium",
    "สูง": "High",
    "ความเกี่ยวข้อง": "Relevance",
    "เงื่อนไขขาลง": "Bearish condition",
    "เงื่อนไขขาขึ้น": "Bullish condition",
    "วันที่": "Date",
    "เวลาไทย": "UTC+07:00",
    "เหตุการณ์": "Event",
    "ระดับ": "Impact",
    " น.": "",
    "จันทร์": "Mon", "อังคาร": "Tue", "พุธ": "Wed", "พฤหัสบดี": "Thu",
    "ศุกร์": "Fri", "เสาร์": "Sat", "อาทิตย์": "Sun",
    "ม.ค.": "Jan", "ก.พ.": "Feb", "มี.ค.": "Mar", "เม.ย.": "Apr",
    "พ.ค.": "May", "มิ.ย.": "Jun", "ก.ค.": "Jul", "ส.ค.": "Aug",
    "ก.ย.": "Sep", "ต.ค.": "Oct", "พ.ย.": "Nov", "ธ.ค.": "Dec",
    "สัปดาห์นี้": "This week", "รายการ ": "Items ", " จาก ": " of ", "หน้า ": "Page ",
}


def label(text):
    if ACTIVE_LOCALE.get() != "en-ZA":
        return text
    for source in sorted(PHRASES, key=len, reverse=True):
        text = text.replace(source, PHRASES[source])
    if re.search(r"[\u0e00-\u0e7f]", text):
        raise ValueError(f"Unmapped Style D English label: {text!r}")
    return text


def calendar_title(event):
    if ACTIVE_LOCALE.get() != "en-ZA":
        return str(event.get("title") or "").strip()
    title = event.get("title_en")
    if not isinstance(title, str) or not title.strip() or re.search(r"[\u0e00-\u0e7f]", title):
        raise ValueError("English calendar title missing from source evidence")
    return title.strip()
