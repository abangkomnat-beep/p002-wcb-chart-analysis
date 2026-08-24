"""Single public Markdown template for all BTCUSD F+ selections."""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping


_CANDIDATE_ORDER = ("J", "I", "E_LOGIC", "F")

# These are presentation labels only.  Router reason codes deliberately never
# cross the public-copy boundary.
_REASON_TEXT = {
    "J_CONTRACT_NOT_CONFIRMED": "สัญญาณของ J ยังไม่ยืนยัน",
    "I_BREAKOUT_NOT_CONFIRMED": "การเบรกเอาต์ของ I ยังไม่ยืนยัน",
    "E_LOGIC_NOT_CONFIRMED": "ตรรกะของ E ยังไม่ยืนยัน",
    "F_RANGE_EDGE_NOT_CONFIRMED": "ขอบช่วงของ F ยังไม่ยืนยัน",
    "ENTRY_TOO_FAR_ATR": "ระยะห่างจากจุดยืนยันยังไม่เหมาะสม",
    "RR_BELOW_MINIMUM": "อัตราส่วนความเสี่ยงยังไม่ผ่านเกณฑ์",
    "NEWS_GATE_UNPROVEN": "ปฏิทินข่าวยังยืนยันไม่ได้",
    "DATA_GATE_UNPROVEN": "ข้อมูลตลาดยังยืนยันไม่ได้",
}

_WAIT_TEXT = {
    "J": "รอการยืนยันสัญญาณของ J จากแท่งปิดรอบใหม่",
    "I": "รอการยืนยันการเบรกเอาต์ของ I จากแท่งปิดรอบใหม่",
    "E_LOGIC": "รอการยืนยันตรรกะของ E จากหลักฐานรอบใหม่",
    "F": "รอการยืนยันขอบช่วงของ F จากข้อมูลรอบใหม่",
}

_FORBIDDEN_PUBLIC = re.compile(
    r"\b(?:Entry|SL|TP1?|Stop Loss|Take Profit|price|RR)\b|ราคา",
    re.IGNORECASE,
)
_INTERNAL_CODE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){2,}\b")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _public_text(value: Any, fallback: str = "ข้อมูลไม่พอสำหรับรายละเอียด") -> str:
    """Return safe presentation text without exposing codes or trade levels."""
    text = str(value).strip() if value is not None else ""
    if not text:
        return fallback
    for code, label in _REASON_TEXT.items():
        text = text.replace(code, label)
    text = _INTERNAL_CODE.sub("ข้อมูลเฉพาะ", text)
    text = _FORBIDDEN_PUBLIC.sub("ข้อมูลระดับที่จำเป็น", text)
    return text


def _without_leading_phrase(text: str, *phrases: str) -> str:
    value = text.strip()
    for phrase in phrases:
        if value.startswith(phrase):
            value = value[len(phrase):].lstrip(" :：-")
            break
    return value or text


def _gate_label(value: Any, missing: str = "ไม่พบผล gate/risk เฉพาะ") -> str:
    if value is None or value == "":
        return missing
    if isinstance(value, bool):
        return "ผ่าน" if value else "ไม่ผ่าน"
    status = str(value).lower()
    return {
        "pass": "ผ่าน",
        "passed": "ผ่าน",
        "true": "ผ่าน",
        "fail": "ไม่ผ่าน",
        "failed": "ไม่ผ่าน",
        "false": "ไม่ผ่าน",
        "blackout": "อยู่ในช่วงเฝ้าระวังข่าว",
        "unproven": "ยังยืนยันไม่ได้",
    }.get(status, "ยังยืนยันไม่ได้")


def _data_gate_status(data: Mapping[str, Any]) -> Any:
    """Read both the presentation shape and the actual pipeline data shape."""
    return data.get("status", data.get("price_data_status"))


def _reason_label(decision: Mapping[str, Any]) -> str:
    labels: list[str] = []
    seen: set[str] = set()
    for code in decision.get("reason_codes", []) or []:
        label = _REASON_TEXT.get(str(code))
        if label and label not in seen:
            labels.append(label)
            seen.add(label)
    return "; ".join(labels) if labels else "ไม่พบเหตุผลเฉพาะใน snapshot นี้"


def _candidate_decision_map(candidate_decisions: Iterable[Mapping[str, Any]] | None) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in candidate_decisions or ():
        if not isinstance(item, Mapping):
            continue
        candidate = str(item.get("candidate", ""))
        if candidate in _CANDIDATE_ORDER and candidate not in result:
            result[candidate] = item
    return result


def _no_trade_explanation(
    selected_plan: Mapping[str, Any],
    candidate_decisions: Iterable[Mapping[str, Any]] | None,
    gate_report: Mapping[str, Any] | None,
) -> list[str]:
    decisions = _candidate_decision_map(candidate_decisions)
    gates = _mapping(gate_report)
    lines = ["", "## เหตุผลราย candidate"]
    waits: list[str] = []
    for candidate in _CANDIDATE_ORDER:
        decision = _mapping(decisions.get(candidate))
        reason = _reason_label(decision)
        has_reason = bool(decision.get("reason_codes"))
        refs = decision.get("evidence_refs")
        has_evidence = isinstance(refs, (list, tuple)) and bool(refs)
        if not has_reason and not has_evidence:
            reason = "ไม่พบเหตุผลเฉพาะใน snapshot นี้"
        candidate_gate = _gate_label(
            _mapping(decision.get("gate_results")).get("candidate"),
        )
        risk_gate = _gate_label(_mapping(decision.get("gate_results")).get("risk"))
        lines.extend([
            f"### {candidate}",
            "- สถานะ: ยังไม่ยืนยัน" if not decision.get("eligible") else "- สถานะ: ผ่าน",
            f"- เหตุผล: {_public_text(reason)}",
            f"- candidate gate: {candidate_gate}",
            f"- risk gate: {risk_gate}",
        ])
        if has_evidence:
            safe_refs = ", ".join(_public_text(ref, "ข้อมูลอ้างอิงไม่พร้อม") for ref in refs)
            lines.append(f"- หลักฐานอ้างอิง: {safe_refs}")
        if not decision.get("eligible") or not decision:
            waits.append(
                f"- {candidate}: {_WAIT_TEXT[candidate] if has_reason else 'ข้อมูลไม่พอสำหรับรายละเอียด'}"
            )

    lines.extend([
        "",
        "## สรุป risk/gate",
    ])
    data_report = _mapping(gates.get("data"))
    news_report = _mapping(gates.get("news"))
    if not data_report and not news_report:
        lines.append("- ไม่พบผล gate/risk เฉพาะ — คงสถานะ No-trade เพื่อความปลอดภัย")
    else:
        lines.extend([
            f"- data gate: {_gate_label(_data_gate_status(data_report))}",
            f"- news gate: {_gate_label(news_report.get('status'))}",
        ])
        if not data_report or not news_report:
            lines.append("- ไม่พบผล gate/risk เฉพาะ — คงสถานะ No-trade เพื่อความปลอดภัย")

    lines.extend(["", "## สิ่งที่ต้องรอยืนยัน"])
    lines.extend(waits or ["- ข้อมูลไม่พอสำหรับรายละเอียด — รอการยืนยันจาก snapshot รอบใหม่"])
    plan_trigger = _public_text(selected_plan.get("trigger_m15"), "ข้อมูลไม่พอสำหรับรายละเอียด")
    plan_invalidation = _public_text(selected_plan.get("invalidation"), "ข้อมูลไม่พอสำหรับรายละเอียด")
    plan_invalidation = _without_leading_phrase(
        plan_invalidation, "ประเมินใหม่เมื่อ", "ประเมินใหม่",
    )
    lines.extend([
        "",
        "## เงื่อนไขประเมินใหม่",
        f"- Trigger M15: {plan_trigger}",
        f"- ประเมินใหม่เมื่อ: {plan_invalidation}",
    ])
    if not decisions:
        lines.append("- ข้อมูลไม่พอสำหรับรายละเอียด — ไม่มี candidate decision ใน snapshot นี้")
    return lines


def _number(value: Any) -> str:
    number = float(value)
    return f"{number:.8f}".rstrip("0").rstrip(".")


def _yaml_text(value: Any) -> str:
    return '"' + str(value).replace('"', '\\"').replace("\n", " ") + '"'


def render_markdown(
    selected_plan: Mapping[str, Any], *,
    candidate_decisions: Iterable[Mapping[str, Any]] | None = None,
    gate_report: Mapping[str, Any] | None = None,
) -> str:
    plan = dict(selected_plan)
    selection = plan["selection"]
    no_trade = selection == "NO_TRADE"
    trend = "neutral" if no_trade else plan.get("direction", "neutral")
    title = "BTCUSD F+ — แผนระยะสั้นประจำวัน"
    excerpt = "งดเทรดระหว่างรอข้อมูลยืนยันรอบใหม่" if no_trade else f"แผน {selection} แบบมีเงื่อนไขจากแท่งปิดหลายกรอบเวลา"
    lines = [
        "---",
        "asset: btcusd",
        f"title: {_yaml_text(title)}",
        f"excerpt: {_yaml_text(excerpt)}",
        "author: CC Research Team",
        f"trade_date: {plan['trade_date_bangkok']}",
        f"cutoff: {plan['cutoff_at_utc']}",
        'timeframe_set: "H4/H1/M30/M15"',
        f"trend: {trend}",
        "---",
        "",
        f"# {title}",
        "",
        "## สรุปแผนวันนี้",
    ]
    if no_trade:
        lines.extend([
            "สถานะ **No-trade (งดเทรด)** เพราะเงื่อนไขยังไม่ครบตามระบบ F+",
            "ให้รอแท่งปิดยืนยันใหม่ก่อนประเมินอีกครั้ง",
        ])
        lines.extend(_no_trade_explanation(plan, candidate_decisions, gate_report))
    else:
        zone = plan["entry_zone"]
        lines.extend([
            f"ระบบเลือกแผน **{selection}** ฝั่ง **{plan['direction']}** แบบมีเงื่อนไข",
            f"- เขตเข้าตามแผน: {_number(zone['low'])}–{_number(zone['high'])}",
            f"- จุดยกเลิกเชิงราคา: {_number(plan['stop_loss'])}",
            f"- เป้าหมายแรก: {_number(plan['take_profit_1'])}",
            f"- อัตราผลตอบแทนต่อความเสี่ยง: {_number(plan['rr'])}",
        ])
    def display_text(value: Any, fallback: str) -> str:
        if no_trade:
            return _public_text(value, fallback)
        return str(value) if value is not None else fallback

    lines.extend([
        "",
        "## Bias H4",
        display_text(plan.get("bias_h4"), "รอประเมินทิศทางจากแท่งปิด"),
        "",
        "## Setup H1",
        display_text(plan.get("setup_h1"), "ยังไม่มีโครงสร้างที่ผ่านเกณฑ์"),
        "",
        "## Evidence M30",
        display_text(plan.get("evidence_m30"), "หลักฐานแรงและทิศยังไม่ชัดเจน"),
        "",
        "## Trigger M15",
        display_text(plan.get("trigger_m15"), "รอแท่งปิดยืนยันใหม่"),
        "",
        "## เงื่อนไขยกเลิก",
        display_text(plan.get("invalidation"), "ประเมินใหม่เมื่อข้อมูลเปลี่ยน"),
        "",
        "## ข่าว",
        display_text(plan.get("news_notice"), "ตรวจปฏิทินข่าวก่อนตัดสินใจทุกครั้ง"),
        "",
        "> บทวิเคราะห์นี้เป็นแผนตามเงื่อนไข ไม่ใช่คำแนะนำให้ซื้อหรือขายสินทรัพย์",
        "",
    ])
    return "\n".join(lines)
