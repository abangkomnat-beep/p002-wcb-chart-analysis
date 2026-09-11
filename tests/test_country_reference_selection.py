import json
from tools import publish_selection as selector


def test_reference_selection_preserves_country_bytes_and_writes_only_work(tmp_path):
    day = tmp_path / 'output/09-09-2026'
    lane = day / 'TH-Thailand/E/XAUUSD'
    lane.mkdir(parents=True)
    article = lane / 'article.md'
    article.write_text('unchanged', encoding='utf-8')
    item = {'status': 'ready', 'source_layout': 'country_first',
            'source_folder': 'TH-Thailand/E/XAUUSD', 'article_name': article.name}
    from unittest.mock import patch
    with patch.object(selector, '_public_selection_report', return_value={'status': 'PASS'}):
        result = selector._select_country_references(day, [item], '2026-09-09', record_continuity=False)
    assert result['directory'] == str(day)
    assert result['status'] == 'ready'
    assert not (day / '0-ขึ้นเว็บวันนี้').exists()
    assert article.read_text(encoding='utf-8') == 'unchanged'
    assert item['destination_folder'] == 'TH-Thailand/E/XAUUSD'
    assert json.loads((tmp_path / 'work/selection/09-09-2026/selection-report.json').read_text())['status'] == 'PASS'


def test_reference_mode_rejects_legacy_inventory(tmp_path):
    from unittest.mock import patch
    day = tmp_path / 'output/09-09-2026'
    with patch.object(selector, '_public_selection_report', return_value={'status': 'FAIL'}):
        result = selector._select_country_references(day, [{'status': 'ready', 'source_layout': 'legacy'}],
                                                     '2026-09-09', record_continuity=False)
    assert result['status'] == 'unavailable'
    assert result['lanes'][0]['reason'] == 'COUNTRY_LAYOUT_REQUIRED'
