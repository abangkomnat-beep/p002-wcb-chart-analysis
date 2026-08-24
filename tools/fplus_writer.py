"""Single public Markdown template for all BTCUSD F+ selections."""
from __future__ import annotations

from typing import Any, Mapping


def _number(value: Any) -> str:
    number = float(value)
    return f"{number:.8f}".rstrip("0").rstrip(".")


def _yaml_text(value: Any) -> str:
    return '"' + str(value).replace('"', '\\"').replace("\n", " ") + '"'


def render_markdown(selected_plan: Mapping[str, Any]) -> str:
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
    else:
        zone = plan["entry_zone"]
        lines.extend([
            f"ระบบเลือกแผน **{selection}** ฝั่ง **{plan['direction']}** แบบมีเงื่อนไข",
            f"- เขตเข้าตามแผน: {_number(zone['low'])}–{_number(zone['high'])}",
            f"- จุดยกเลิกเชิงราคา: {_number(plan['stop_loss'])}",
            f"- เป้าหมายแรก: {_number(plan['take_profit_1'])}",
            f"- อัตราผลตอบแทนต่อความเสี่ยง: {_number(plan['rr'])}",
        ])
    lines.extend([
        "",
        "## Bias H4",
        str(plan.get("bias_h4", "รอประเมินทิศทางจากแท่งปิด")),
        "",
        "## Setup H1",
        str(plan.get("setup_h1", "ยังไม่มีโครงสร้างที่ผ่านเกณฑ์")),
        "",
        "## Evidence M30",
        str(plan.get("evidence_m30", "หลักฐานแรงและทิศยังไม่ชัดเจน")),
        "",
        "## Trigger M15",
        str(plan.get("trigger_m15", "รอแท่งปิดยืนยันใหม่")),
        "",
        "## เงื่อนไขยกเลิก",
        str(plan.get("invalidation", "ประเมินใหม่เมื่อข้อมูลเปลี่ยน")),
        "",
        "## ข่าว",
        str(plan.get("news_notice", "ตรวจปฏิทินข่าวก่อนตัดสินใจทุกครั้ง")),
        "",
        "> บทวิเคราะห์นี้เป็นแผนตามเงื่อนไข ไม่ใช่คำแนะนำให้ซื้อหรือขายสินทรัพย์",
        "",
    ])
    return "\n".join(lines)
