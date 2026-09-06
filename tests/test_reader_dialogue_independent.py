"""Independent boundary checks against the approved reader-continuity plan."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from tools import article_continuity as ac

ARTICLE = '# บททดสอบ\n\nบทนำสำหรับทดสอบ\n\n## ภาพรวม\n\nกราฟและระดับราคา\n'


def candidate(root, cutoff, *, asset='xauusd', style='D', contract='test/v1'):
    text, record = ac.enrich(ARTICLE, asset=asset, style=style, contract=contract,
                             cutoff=cutoff, evidence={'close': 100}, store_root=root)
    ac.save_candidate(root, record, text)
    return text, record


def confirm(root, record, published):
    return ac.confirm_publication(root, record['revision'], article_hash=record['article_hash'],
        evidence_hash=record['evidence_hash'], published_at=published,
        receipt='TEST FIXTURE ONLY', confirmed_by='independent-test')


def test_output_candidate_alone_is_not_previous_publication(tmp_path):
    candidate(tmp_path, '2026-09-01T08:00:00+07:00')
    text, record = candidate(tmp_path, '2026-09-02T08:00:00+07:00')
    assert ac.UPDATE not in text
    assert record['baseline_revision'] is None


def test_same_day_confirmed_article_not_baseline(tmp_path):
    _, prior = candidate(tmp_path, '2026-09-01T08:00:00+07:00')
    confirm(tmp_path, prior, '2026-09-01T09:00:00+07:00')
    text, record = candidate(tmp_path, '2026-09-01T12:00:00+07:00')
    assert ac.UPDATE not in text


@pytest.mark.parametrize('change', [{'asset': 'wtiusd'}, {'style': 'E'}, {'contract': 'test/v2'}])
def test_baseline_cannot_cross_identity(tmp_path, change):
    _, prior = candidate(tmp_path, '2026-09-01T08:00:00+07:00')
    confirm(tmp_path, prior, '2026-09-01T09:00:00+07:00')
    text, record = candidate(tmp_path, '2026-09-02T08:00:00+07:00', **change)
    assert record['baseline_revision'] is None


def test_sort_publication_by_instant_not_offset_string(tmp_path):
    _, early = candidate(tmp_path, '2026-09-01T00:00:00+00:00')
    _, later = candidate(tmp_path, '2026-09-01T01:00:00+00:00')
    confirm(tmp_path, early, '2026-09-01T09:00:00+07:00')  # 02:00Z
    confirm(tmp_path, later, '2026-09-01T03:00:00+00:00')  # actually later
    _, record = candidate(tmp_path, '2026-09-02T08:00:00+07:00')
    assert record['baseline_revision'] == later['revision']


def test_tampered_evidence_is_not_used(tmp_path):
    _, prior = candidate(tmp_path, '2026-09-01T08:00:00+07:00')
    path = confirm(tmp_path, prior, '2026-09-01T09:00:00+07:00')
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['record']['evidence']['close'] = 9999
    path.write_text(json.dumps(payload), encoding='utf-8')
    _, record = candidate(tmp_path, '2026-09-02T08:00:00+07:00')
    assert record['baseline_revision'] is None


def test_confirmation_rejects_wrong_hash_and_pre_cutoff(tmp_path):
    _, prior = candidate(tmp_path, '2026-09-01T08:00:00+07:00')
    with pytest.raises(ValueError):
        ac.confirm_publication(tmp_path, prior['revision'], article_hash='0'*64,
            evidence_hash=prior['evidence_hash'], published_at='2026-09-01T09:00:00+07:00',
            receipt='TEST', confirmed_by='tester')
    with pytest.raises(ValueError):
        confirm(tmp_path, prior, '2026-09-01T07:00:00+07:00')


def test_rerun_preserves_question_without_consuming_history(tmp_path):
    text, record = candidate(tmp_path, '2026-09-01T08:00:00+07:00')
    again, same = candidate(tmp_path, '2026-09-01T08:00:00+07:00')
    assert text == again and record == same
    assert not list((tmp_path/'published').glob('*.json'))


def test_twenty_rounds_respect_text_semantic_and_family_windows(tmp_path):
    prior = []
    day = datetime(2026, 8, 1, 8, tzinfo=timezone(timedelta(hours=7)))
    for n in range(20):
        current = day + timedelta(days=n)
        text, record = candidate(tmp_path, current.isoformat())
        assert text.count(ac.QUESTION) == 1
        assert record['semantic_key'] not in [r['semantic_key'] for r in prior[-10:]]
        assert record['question_family'] not in [r['question_family'] for r in prior[-3:]]
        assert '?' in record['question']
        confirm(tmp_path, record, (current + timedelta(hours=1)).isoformat())
        prior.append(record)


def test_direction_change_is_not_reported_unchanged(tmp_path):
    text, record = ac.enrich(ARTICLE, asset='eurusd', style='L', contract='test/v1',
        cutoff='2026-09-01T08:00:00+07:00', evidence={'plan': {'side': 'SELL', 'plans': []}}, store_root=tmp_path)
    ac.save_candidate(tmp_path, record, text)
    confirm(tmp_path, record, '2026-09-01T09:00:00+07:00')
    text, _ = ac.enrich(ARTICLE, asset='eurusd', style='L', contract='test/v1',
        cutoff='2026-09-02T08:00:00+07:00', evidence={'plan': {'side': 'BUY', 'plans': []}}, store_root=tmp_path)
    update = text.split(ac.UPDATE)[1].split('## ภาพรวม')[0]
    assert 'ยังตรงกับรอบก่อน' not in update
    assert 'ขาลง' in update and 'ขาขึ้น' in update


def test_same_batch_six_candidates_have_distinct_questions(tmp_path):
    questions = []
    for asset, style in [('xauusd', 'D'), ('wtiusd', 'D'), ('xauusd', 'E'),
                         ('eurusd', 'L'), ('usdjpy', 'L'), ('btcusd', 'M')]:
        _, record = candidate(tmp_path, '2026-09-01T08:00:00+07:00', asset=asset, style=style)
        questions.append(ac.normalize(record['question']))
    assert len(set(questions)) == 6
