"""Generate review-only copies; never register real publication or edit output."""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import re
from copy import deepcopy

from tools import article_continuity as ac


def fixture_evidence(style):
    """Tiny, explicitly synthetic examples for reviewing each narrative state."""
    old = {'plan': {'side': 'SELL', 'status': 'WAIT_TRIGGER',
                   'valid_until': '2026-09-02T09:00:00+07:00', 'plans': []}}
    current = {'plan': {'side': 'BUY', 'plans': []}}
    if style == 'D':
        return {'story': {'zones': [{'low': 90, 'high': 100}]}}, {'story': {'zones': [{'low': 92, 'high': 102}]}}
    if style == 'L':
        return old, current
    rows = [
        {'at': '2026-09-01T08:00:00+07:00', 'open': 100, 'close': 111, 'low': 100, 'high': 112},
        {'at': '2026-09-01T09:00:00+07:00', 'open': 111, 'close': 111, 'low': 109, 'high': 112},
        {'at': '2026-09-01T10:00:00+07:00', 'open': 111, 'close': 120, 'low': 111, 'high': 121}]
    if style == 'E':
        old = {'plan': {'side': 'BUY', 'status': 'WAIT_TRIGGER', 'current_close': 100,
            'cutoff_at': '2026-09-01T08:00:00+07:00', 'valid_until': '2026-09-01T11:00:00+07:00',
            'plans': [{'side': 'BUY', 'trigger': {'condition': 'closed H1 strict cross from latest closed close', 'value': 110},
                       'stop_loss': 95, 'take_profit': [120, 130],
                       'invalidation': {'condition': 'closed H1 reaches canonical SL', 'value': 95}}]}}
    else:
        old = {'story': {'contract_version': 'M-PROD/v7', 'state': 'SCENARIOS_READY',
            'cutoff': '2026-09-01T08:00:00+07:00', 'valid_until': '2026-09-01T11:00:00+07:00',
            'latest': {'close': 100}, 'false_breakout': {
                'bull_trap': 'next_closed_h1_below_short_trigger', 'bear_trap': 'next_closed_h1_above_long_trigger',
                'no_retest_tp1': 'cancel_if_tp1_reached_before_retest'},
            'scenarios': {
                'long': {'side': 'LONG', 'state': 'WAIT_TRIGGER', 'trigger_rule': 'closed_h1_strict_cross',
                         'trigger': 110, 'entry_low': 108, 'entry_high': 110, 'sl': 95, 'tp1': 120, 'tp2': 130},
                'short': {'side': 'SHORT', 'state': 'WAIT_TRIGGER', 'trigger_rule': 'closed_h1_strict_cross',
                          'trigger': 90, 'entry_low': 90, 'entry_high': 92, 'sl': 105, 'tp1': 80, 'tp2': 70}}}}
    current = deepcopy(old)
    current['rows'] = rows
    return old, current


def generate(source_root: Path, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    pairs = [('D', 'xauusd', 'D-โครงสร้างกราฟ/xauusd.md'),
             ('D', 'wtiusd', 'D-โครงสร้างกราฟ/wtiusd.md'),
             ('E', 'xauusd', 'E-อินดิเคเตอร์/xauusd.md'),
             ('L', 'eurusd', 'L-Forex-Daily/eurusd.md'),
             ('M', 'btcusd', 'M-BTCUSD-H1-Visual-Daily/btc-daily-2026-09-04.md')]
    index = ['# ตัวอย่างพรูฟ — ความต่อเนื่องและคำถามท้ายบท', '',
             'ชุดนี้เป็นสำเนาสำหรับตรวจน้ำเสียง ไม่ได้แทน output หรือขึ้นเว็บ', '',
             '## บทจริงที่เพิ่มคำถามท้ายบท', '',
             'ใช้ข้อความต้นฉบับวันที่ 04-09-2026 โดยไม่อ้างว่ามีบทก่อนที่ยืนยันการเผยแพร่แล้ว ภาพอ้างกลับไฟล์ต้นฉบับ', '']
    inventory = []
    for style, asset, relative in pairs:
        source = source_root / relative
        original = source.read_text(encoding='utf-8')
        evidence = {'preview_source_hash': ac.digest(original), 'preview_only': True}
        rendered, record = ac.enrich(original, asset=asset, style=style,
            contract='proof-only/v1', cutoff='2026-09-04T16:00:00+07:00',
            evidence=evidence, store_root=destination/'internal'/'no-publication')
        ac.save_candidate(destination/'internal'/'no-publication', record, rendered)
        # Rendering a link to the original image does not modify that image.
        rendered = re.sub(r'(!\[[^\]]*\]\()([^<>\n)]+\.webp)(\))',
            lambda m: m[1] + '<' + (source.parent/m[2]).resolve().as_posix() + '>' + m[3], rendered)
        name = f'{style}-{asset}-คำถามท้ายบท.md'
        (destination/name).write_text(rendered, encoding='utf-8')
        index.append(f'- [{style} — {asset}]({name})')
        inventory.append({'source': str(source), 'source_hash': ac.digest(original),
                          'preview': name, 'baseline': None, 'question': record['question']})
    index += ['', '## ตัวอย่างการต่อเรื่องจากฐานอัตโนมัติ — ข้อมูลสมมติ', '',
              'ใช้ fixture สองรอบและ receipt แบบ selected_delivery แยกจากประวัติจริง ไม่ได้เรียก manual confirmation และไม่ได้ยืนยันว่าบทจริงขึ้นเว็บแล้ว', '']
    fixture_article = '# ตัวอย่างสมมติสำหรับพรูฟ\n\nบทนำตัวอย่าง\n\n## ภาพรวมวันนี้\n\nติดตามเงื่อนไขจากกราฟ\n'
    style_ids = {'D': 'd_chart_story', 'E': 'e_indicator',
                 'L': 'l_forex_daily_plan', 'M': 'm_btcusd_h1_visual_daily'}
    for style, asset in [('D', 'xauusd'), ('E', 'xauusd'), ('L', 'eurusd'), ('M', 'btcusd')]:
        store = destination/'internal'/'fixture-only'/style
        old_evidence, current_evidence = fixture_evidence(style)
        first, prior = ac.enrich(fixture_article, asset=asset, style=style, contract='fixture/v1',
            cutoff='2026-09-01T08:00:00+07:00', evidence=old_evidence, store_root=store)
        ac.save_candidate(store, prior, first)
        handoff = store/'fixture-handoff'/style
        handoff.mkdir(parents=True, exist_ok=True)
        (handoff/'article.md').write_text(first, encoding='utf-8')
        ac.record_selected_delivery(
            store, target_root=store/'fixture-handoff', article_date='2026-09-01',
            selected_at='2026-09-01T09:00:00+07:00',
            selection_report={'status': 'PASS', 'fixture': True, 'style': style},
            inventories=[{'id': f'fixture-{style}', 'asset': 'btc' if asset == 'btcusd' else asset,
                          'style': style_ids[style], 'status': 'ready',
                          'destination_folder': style, 'article_name': 'article.md'}])
        current, record = ac.enrich(fixture_article, asset=asset, style=style, contract='fixture/v1',
            cutoff='2026-09-03T08:00:00+07:00', evidence=current_evidence, store_root=store)
        name = f'{style}-{asset}-ตัวอย่างสมมติการต่อเรื่อง.md'
        (destination/name).write_text('> ข้อมูลสมมติสำหรับพรูฟภาษาเท่านั้น\n\n'+current, encoding='utf-8')
        index.append(f'- [{style} — ตัวอย่างสมมติ]({name})')
    (destination/'README.md').write_text('\n'.join(index)+'\n', encoding='utf-8')
    (destination/'internal').mkdir(exist_ok=True)
    (destination/'internal'/'source-inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')
    return destination/'README.md'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    print(generate(args.source_root.resolve(), args.destination.resolve()))
