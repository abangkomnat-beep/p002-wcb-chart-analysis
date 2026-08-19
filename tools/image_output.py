"""มาตรฐานไฟล์ภาพที่ส่งขึ้นเว็บ WCB — จุดเดียวที่กำหนดนามสกุล คุณภาพ และเพดานขนาด

กติกาที่หัวหน้าเคาะ 2026-08-09 (ผลตรวจทีมเว็บ ข้อ A-2):

    นามสกุล `.webp` เท่านั้น · ไม่เกิน 200 KB ต่อรูป · ขนาดภาพ (พิกเซล) ไม่บังคับ

**เว็บไม่แปลงไฟล์ให้ และไม่บีบให้** — ส่ง `.png`/`.jpg` ไป หรือเกินเพดาน = ตีกลับทั้งใบ
ทั้งบทความ ไม่ใช่แค่รูปใบนั้น ⇒ ด่านนี้เป็น fail-closed แบบเดียวกับด่านอื่นในระบบ
(ดู `docs/QC-GATES.md`): ตกแล้วไฟล์ต้องไม่ออก ไม่ใช่ออกไปพร้อมป้ายเตือน

เหตุผลที่ต้อง**วัดไฟล์จริงหลังเซฟ** ไม่ใช่เชื่อค่าคุณภาพที่ตั้งไว้: ขนาดไฟล์ขึ้นกับ
ความรกของกราฟในแต่ละวัน (จำนวนแนวต้าน โซน ป้ายฉากทัศน์ที่ผ่านเกณฑ์ไม่เท่ากันทุกวัน)
วันที่กราฟเส้นเยอะกว่าปกติจึงทะลุเพดานได้โดยที่ค่าคุณภาพไม่ได้เปลี่ยนเลย

ค่าคุณภาพเป็นค่าคงที่ตัวเดียวของทั้งระบบโดยตั้งใจ — ห้ามฮาร์ดโค้ดซ้ำในตัววาดแต่ละตัว
เพราะเวลาต้องไล่ลงเพื่อหนีเพดาน จะได้แก้ที่เดียวแล้วมีผลทุกสาย
"""

from __future__ import annotations

from pathlib import Path

IMAGE_SUFFIX = ".webp"
IMAGE_FORMAT = "webp"
# คุณภาพ 90 — ทีมเว็บวัดให้แล้วว่ารูปหนักสุดของเรา (indicators 1920×1260) ได้ 138 KB
# ที่คุณภาพนี้ คือยังห่างเพดาน 200 KB พอให้กราฟวันที่รกกว่าปกติมีที่หายใจ
# ต้องลง = แก้ตรงนี้ตัวเดียว (ห้ามลดความละเอียดภาพก่อน — ลดคุณภาพการบีบก่อนเสมอ)
WEBP_QUALITY = 90
MIN_WEBP_QUALITY = 80   # ตัวอักษรไทย/เส้นกราฟเริ่มเห็นรอยบีบชัดเมื่อต่ำกว่านี้
WEBP_METHOD = 6          # 0–6 · ยิ่งสูงยิ่งบีบแน่น แลกกับเวลาเซฟ (วันละไม่กี่ใบ คุ้ม)
MAX_IMAGE_BYTES = 200 * 1024


class ImageGateError(RuntimeError):
    """ไฟล์ภาพไม่ผ่านกติกาของเว็บ — ห้ามปล่อยผ่าน ห้ามผ่อนเกณฑ์เพื่อให้ของออก"""


def kb(size_bytes: int) -> float:
    return round(size_bytes / 1024, 1)


def is_web_image(path: Path) -> bool:
    """ไฟล์นี้เป็น 'ภาพที่จะขึ้นเว็บ' ไหม — ใช้กวาดโฟลเดอร์ที่มี .md ปนอยู่"""
    return path.is_file() and path.suffix.lower() not in {".md", ".json", ".txt"}


def verify(path: Path) -> int:
    """ตรวจไฟล์ภาพหนึ่งใบตามกติกาเว็บ — คืนขนาดเป็นไบต์ ตกแล้วยก ImageGateError"""
    if not path.is_file():
        raise ImageGateError(f"ไม่มีไฟล์ภาพให้ตรวจ: {path.name}")
    if path.suffix.lower() != IMAGE_SUFFIX:
        raise ImageGateError(
            f"{path.name}: เว็บรับเฉพาะ {IMAGE_SUFFIX} — ไฟล์นี้เป็น {path.suffix or 'ไม่มีนามสกุล'}")
    size = path.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise ImageGateError(
            f"{path.name}: {kb(size)} KB เกินเพดาน {kb(MAX_IMAGE_BYTES)} KB — "
            f"ลดค่า WEBP_QUALITY (ตอนนี้ {WEBP_QUALITY}) ห้ามปล่อยขึ้นเว็บ")
    return size


def verify_folder(folder: Path) -> dict[str, int]:
    """ตรวจภาพทุกใบในโฟลเดอร์ที่จะส่งขึ้นเว็บ — คืน {ชื่อไฟล์: ไบต์}"""
    return {path.name: verify(path) for path in sorted(folder.iterdir()) if is_web_image(path)}


def save_figure(figure, output_path: Path, *, webp_quality: int | None = None,
                **savefig_kwargs) -> int:
    """เซฟ figure ของ matplotlib เป็น .webp แล้วตรวจไฟล์จริงทันที — คืนขนาดเป็นไบต์

    ตกด่าน = **ลบไฟล์ทิ้งแล้วยก ImageGateError** ไม่ปล่อยให้ไฟล์เกินเพดานนอนอยู่
    ในโฟลเดอร์ให้คนหยิบไปอัปโดยไม่รู้ตัว (สายผลิตข้างบนจะกวาดชุดที่เหลือทิ้งเอง)
    """
    output_path = Path(output_path)
    if output_path.suffix.lower() != IMAGE_SUFFIX:
        raise ImageGateError(f"พาธปลายทางต้องลงท้าย {IMAGE_SUFFIX}: {output_path.name}")
    quality = WEBP_QUALITY if webp_quality is None else int(webp_quality)
    if not MIN_WEBP_QUALITY <= quality <= 100:
        raise ImageGateError(
            f"คุณภาพ WebP ต้องอยู่ระหว่าง {MIN_WEBP_QUALITY}–100: {quality}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, format=IMAGE_FORMAT,
                   pil_kwargs={"quality": quality, "method": WEBP_METHOD},
                   **savefig_kwargs)
    try:
        return verify(output_path)
    except ImageGateError:
        output_path.unlink(missing_ok=True)
        raise
