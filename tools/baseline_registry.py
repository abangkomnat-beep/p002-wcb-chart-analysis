"""ทะเบียนมาตรฐานภาษา — ตัวบังคับ governance lock เชิงกล

## ปัญหาที่เครื่องมือตัวนี้แก้

"ล็อกภาษาแล้ว" ถ้าอาศัยวินัยอย่างเดียวจะพังเงียบสองทาง:

1. **หยิบผิดเวอร์ชัน** — มีไฟล์หลายรุ่นในโฟลเดอร์แล้ว Agent เดาเอาว่า "อันล่าสุด" คืออันไหน
   จากชื่อไฟล์ ⇒ บทวันนี้กับบทเมื่อวานใช้มาตรฐานคนละชุดโดยไม่มีใครรู้
2. **แก้ของที่ล็อกแล้วโดยไม่มีใครเห็น** — Agent "เรียนรู้" จากที่ผู้ใช้อนุมัติแล้วเขียนทับกฎเดิม
   ครั้งต่อไปผู้ใช้อ่านบทแล้วรู้สึกว่าภาษาเปลี่ยนไป แต่ไม่มีร่องรอยว่าใครเปลี่ยนอะไรเมื่อไหร่

ทะเบียนนี้จึงเป็น**แหล่งเดียว**ที่บอกว่า locale ไหนใช้เวอร์ชันไหน และสถานะอะไร
ส่วนสถานะ `stable_locked` ถูกบังคับเชิงกล — เรียกเขียนทับแล้วโยน `BaselineLockedError` ทันที

## นิยามของคำว่า "ล็อก"

    Agent ใช้ได้ · ตรวจได้ · อ้างอิงได้ · เสนอให้เปลี่ยนได้
    แต่แก้ baseline ตัวจริงเองไม่ได้

สำคัญกว่าการตั้งไฟล์ read-only เพราะเป็น **governance lock** ไม่ใช่ file permission
(ไฟล์ read-only ใครก็ปลดได้ และปลดแล้วไม่มีร่องรอย)

## เรื่อง hash

`sha256` ของแต่ละเวอร์ชันคำนวณจาก **ทุกไฟล์ในแพ็กรวมกัน** (เรียงตามพาธ) ไม่ใช่ไฟล์เดียว
เพราะกฎกระจายอยู่หลายไฟล์ — แก้ `glossary.json` แล้ว `baseline.json` เหมือนเดิม
ก็ถือว่ามาตรฐานเปลี่ยนแล้ว

เวอร์ชันที่ยัง `calibrating` จะมี `sha256` เป็น `null` ได้ (แพ็กยังขยับทุกวัน)
แต่เวอร์ชันที่ **`candidate` ขึ้นไปต้องมี hash** และ hash ต้องตรงกับของจริงเสมอ
ไม่ตรง = `BaselineTamperedError` ⇒ หยุดก่อน ไม่ใช่เตือนแล้วเดินต่อ
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

LANGUAGE_DIR = _REPO_ROOT / "language"
REGISTRY_PATH = LANGUAGE_DIR / "baseline-registry.json"

LIFECYCLE = ("draft", "calibrating", "candidate", "stable_locked", "patch_candidate", "deprecated")

#: สถานะที่ถือว่า "นิ่งพอที่จะต้องมี hash กำกับ" — ต่ำกว่านี้แพ็กยังขยับได้ทุกวัน
HASH_REQUIRED_FROM = ("candidate", "stable_locked", "patch_candidate", "deprecated")

#: สถานะที่ห้ามแก้เนื้อในเวอร์ชันเดิม ต้องออกเวอร์ชันใหม่เท่านั้น
LOCKED_STATUSES = ("stable_locked", "deprecated")


class BaselineError(Exception):
    """รากของทุกข้อผิดพลาดฝั่งทะเบียน — มี code ให้ปลายทางแยกกรณีได้โดยไม่ต้องอ่านข้อความ"""

    code = "BASELINE_ERROR"


class LocaleBaselineMissing(BaselineError):
    code = "LOCALE_BASELINE_MISSING"


class BaselineLockedError(BaselineError):
    code = "BASELINE_LOCKED"


class BaselineTamperedError(BaselineError):
    code = "BASELINE_TAMPERED"


# ---------------------------------------------------------------- hash ของแพ็ก

def _canonical_bytes(path: Path) -> bytes:
    """เนื้อไฟล์ในรูปที่เทียบข้ามเครื่องได้ — ตัดความต่างของรูปแบบขึ้นบรรทัดทิ้ง

    จำเป็นเพราะ git แปลง LF ↔ CRLF ตอน checkout ตามค่า `core.autocrlf` ของแต่ละเครื่อง
    ถ้าแฮชนับ byte ดิบ แพ็กเดียวกันจะได้คนละแฮชระหว่าง Windows กับ Linux ⇒ `verify()`
    จะฟ้อง `BASELINE_TAMPERED` ทั้งที่ไม่มีใครแก้อะไร ซึ่งจะทำให้ทุกคนเลิกเชื่อด่านนี้
    ภายในสัปดาห์เดียว

    ไฟล์ที่ถอดเป็นข้อความไม่ได้ (ถ้าวันหนึ่งมีของแบบนั้นในแพ็ก) แฮชจาก byte ดิบตามเดิม
    """
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def pack_sha256(pack_dir: Path) -> str:
    """แฮชของทุกไฟล์ในแพ็กรวมกัน — เรียงตามพาธเพื่อให้ผลเท่ากันทุกเครื่องทุกระบบไฟล์

    ใส่ชื่อไฟล์ลงไปในสิ่งที่แฮชด้วย เพราะการ *เปลี่ยนชื่อ* ไฟล์ก็คือการเปลี่ยนแพ็ก
    (ถ้าแฮชแต่เนื้อ การสลับชื่อสองไฟล์จะได้แฮชเดิม)
    """
    if not pack_dir.is_dir():
        raise LocaleBaselineMissing(f"ไม่พบโฟลเดอร์แพ็ก: {pack_dir}")
    digest = hashlib.sha256()
    for path in sorted(p for p in pack_dir.rglob("*") if p.is_file()):
        digest.update(path.relative_to(pack_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_canonical_bytes(path))
        digest.update(b"\0")
    return digest.hexdigest()


# ---------------------------------------------------------------- อ่านทะเบียน

def load_registry(registry_path: Path | None = None) -> dict:
    path = Path(registry_path) if registry_path else REGISTRY_PATH
    if not path.is_file():
        raise LocaleBaselineMissing(f"ไม่พบทะเบียน: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(locale: str, version: str | None = None,
            registry_path: Path | None = None) -> dict:
    """คืนข้อมูลเวอร์ชันที่ทะเบียนชี้ พร้อมพาธเต็มของแพ็ก

    `version=None` แปลว่า "เอาตัวที่ทะเบียนตั้งเป็น default" — นี่คือทางเดียวที่ Agent ควรใช้
    การเลือกเวอร์ชันเองจากชื่อไฟล์เป็นสิ่งที่เครื่องมือนี้มีไว้เพื่อป้องกัน
    """
    path = Path(registry_path) if registry_path else REGISTRY_PATH
    registry = load_registry(path)
    entry = (registry.get("locales") or {}).get(locale)
    if not entry:
        raise LocaleBaselineMissing(
            f"locale {locale!r} ไม่มีในทะเบียน — ห้ามใช้กฎของภาษาอื่นแทนโดยเงียบ")

    resolved_version = version or entry.get("default")
    if not resolved_version:
        raise LocaleBaselineMissing(f"locale {locale!r} ยังไม่มีเวอร์ชันตั้งต้นในทะเบียน")

    record = (entry.get("versions") or {}).get(resolved_version)
    if not record:
        raise LocaleBaselineMissing(
            f"locale {locale!r} ไม่มีเวอร์ชัน {resolved_version!r} ในทะเบียน")

    pack_dir = (path.parent / record["path"]).resolve()
    return {
        "locale": locale,
        "version": resolved_version,
        "status": record.get("status", "draft"),
        "baseline_id": record.get("baseline_id"),
        "pack_dir": pack_dir,
        "recorded_sha256": record.get("sha256"),
        "approved_by": record.get("approved_by"),
        "approved_at": record.get("approved_at"),
        "parent_version": record.get("parent_version"),
        "registry_path": path,
    }


def verify(locale: str, version: str | None = None,
           registry_path: Path | None = None) -> dict:
    """resolve + ตรวจว่าแพ็กบนดิสก์ยังตรงกับ hash ที่ทะเบียนบันทึกไว้

    เวอร์ชันที่สถานะยังต่ำกว่า `candidate` และยังไม่มี hash = ผ่าน (ตั้งใจ)
    เวอร์ชันที่สถานะ >= candidate แต่ไม่มี hash = ผิด ต้องหยุด — ไม่ใช่เตือนแล้วเดินต่อ
    """
    info = resolve(locale, version, registry_path)
    actual = pack_sha256(info["pack_dir"])
    recorded = info["recorded_sha256"]

    if recorded is None:
        if info["status"] in HASH_REQUIRED_FROM:
            raise BaselineTamperedError(
                f"{locale}@{info['version']} สถานะ {info['status']} แต่ทะเบียนไม่มี hash — "
                "สถานะระดับนี้ต้องมี hash กำกับเสมอ")
    elif recorded != actual:
        raise BaselineTamperedError(
            f"{locale}@{info['version']} แพ็กบนดิสก์ไม่ตรงกับ hash ในทะเบียน\n"
            f"  ทะเบียน: {recorded}\n  ของจริง: {actual}\n"
            "ถ้าตั้งใจแก้ ให้ออกเวอร์ชันใหม่ผ่าน BASELINE_CHANGE_PROPOSAL ไม่ใช่แก้ทับของเดิม")

    info["actual_sha256"] = actual
    return info


# ---------------------------------------------------------------- เขียนทะเบียน

def _write_registry(registry: dict, path: Path) -> None:
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def refresh_hash(locale: str, version: str | None = None,
                 registry_path: Path | None = None) -> str:
    """บันทึก hash ปัจจุบันของแพ็กลงทะเบียน — ใช้ได้เฉพาะเวอร์ชันที่ยังไม่ล็อก

    เวอร์ชันที่ล็อกแล้วห้าม refresh เพราะนั่นคือการทำให้การแก้ที่ไม่ได้รับอนุมัติ
    "ถูกต้องตามทะเบียน" ย้อนหลัง — ซึ่งเป็นช่องโหว่ที่ governance lock มีไว้เพื่อปิดพอดี
    """
    info = resolve(locale, version, registry_path)
    if info["status"] in LOCKED_STATUSES:
        raise BaselineLockedError(
            f"{locale}@{info['version']} สถานะ {info['status']} — ห้ามอัปเดต hash ของเวอร์ชันที่ล็อกแล้ว "
            "ให้ออกเวอร์ชันใหม่แทน")

    path = info["registry_path"]
    registry = load_registry(path)
    actual = pack_sha256(info["pack_dir"])
    registry["locales"][locale]["versions"][info["version"]]["sha256"] = actual
    _write_registry(registry, path)
    return actual


def promote(locale: str, version: str, status: str, approved_by: str,
            approved_at: str, registry_path: Path | None = None) -> dict:
    """เลื่อนสถานะเวอร์ชัน — จุดเดียวที่ `stable_locked` เกิดขึ้นได้

    บังคับสามอย่าง:
    1. เวอร์ชันที่ล็อกแล้วเปลี่ยนสถานะไม่ได้ (ยกเว้นปลดระวางเป็น `deprecated`)
    2. `stable_locked` ต้องมีผู้อนุมัติและเวลาอนุมัติ — Agent เขียนเองไม่ได้
    3. บันทึก hash ของแพ็ก ณ ขณะ promote ⇒ หลังจากนี้แก้ไฟล์ไหนก็จะถูก `verify()` จับได้ทันที
    """
    if status not in LIFECYCLE:
        raise BaselineError(f"สถานะ {status!r} ไม่อยู่ในวงจรชีวิต {LIFECYCLE}")

    info = resolve(locale, version, registry_path)
    if info["status"] in LOCKED_STATUSES and status != "deprecated":
        raise BaselineLockedError(
            f"{locale}@{version} สถานะ {info['status']} แล้ว — เปลี่ยนสถานะเดิมไม่ได้ "
            "ต้องออกเวอร์ชันใหม่ผ่าน BASELINE_CHANGE_PROPOSAL")

    if status == "stable_locked" and not (approved_by and approved_at):
        raise BaselineError(
            "การ promote เป็น stable_locked ต้องระบุผู้อนุมัติและเวลาอนุมัติ — "
            "นี่คือจุดที่ผู้ใช้เท่านั้นตัดสินใจได้")

    path = info["registry_path"]
    registry = load_registry(path)
    record = registry["locales"][locale]["versions"][version]
    record["status"] = status
    record["approved_by"] = approved_by or None
    record["approved_at"] = approved_at or None
    record["sha256"] = pack_sha256(info["pack_dir"])
    if status == "stable_locked":
        registry["locales"][locale]["default"] = version
    _write_registry(registry, path)
    return resolve(locale, version, path)


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ทะเบียนมาตรฐานภาษา — ดูสถานะและตรวจ hash")
    parser.add_argument("--locale", default="th-TH")
    parser.add_argument("--version", default=None, help="ไม่ระบุ = ใช้ตัวที่ทะเบียนตั้งเป็น default")
    parser.add_argument("--verify", action="store_true", help="ตรวจว่าแพ็กบนดิสก์ตรงกับ hash ในทะเบียน")
    parser.add_argument("--refresh-hash", action="store_true",
                        help="บันทึก hash ปัจจุบันลงทะเบียน (ใช้ไม่ได้กับเวอร์ชันที่ล็อกแล้ว)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.refresh_hash:
            digest = refresh_hash(args.locale, args.version)
            info = resolve(args.locale, args.version)
            info["actual_sha256"] = digest
        elif args.verify:
            info = verify(args.locale, args.version)
        else:
            info = resolve(args.locale, args.version)
            info["actual_sha256"] = pack_sha256(info["pack_dir"])
    except BaselineError as exc:
        payload = {"ok": False, "code": exc.code, "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json
              else f"[{exc.code}] {exc}")
        return 1

    info["pack_dir"] = str(info["pack_dir"])
    info["registry_path"] = str(info["registry_path"])
    if args.json:
        print(json.dumps({"ok": True, **info}, ensure_ascii=False, indent=2))
    else:
        print(f"{info['locale']}@{info['version']} · สถานะ {info['status']}")
        print(f"  แพ็ก   : {info['pack_dir']}")
        print(f"  hash   : {info['actual_sha256']}")
        print(f"  ทะเบียน: {info['recorded_sha256']}")
        if info["approved_by"]:
            print(f"  อนุมัติ: {info['approved_by']} เมื่อ {info['approved_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
