"""Offline tests: all approvals TEST_ONLY, all I/O under pytest tmp_path."""
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from tools import package_localized_country as pkg
from tools import localization_config as localization_config


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = pkg._json_bytes(value) if isinstance(value, dict) else value
    path.write_bytes(data)
    return pkg.sha256_bytes(data)


@pytest.fixture
def case(tmp_path):
    run = tmp_path / 'work/localization/07-09-2026/TEST_ONLY'
    manifest_path, index_path = run / 'source-manifest.json', run / 'receipts/index.json'
    source = '---\nasset: eurusd\nslug: eurusd-day\ncountry: thailand\nlanguage: th\nstatus: draft\n---\nราคา EURUSD 1.16141 หากผ่าน 1.16206\n'
    target = '---\nasset: eurusd\nslug: eurusd-day-za\ncountry: south-africa\nlanguage: en\nstatus: draft\n---\nEURUSD 1.16141 if above 1.16206.\n![Chart](images/chart.webp)\n'
    source_hash = put(tmp_path / 'output/07-09-2026/L/source.md', source.encode())
    image_stream = io.BytesIO()
    Image.new('RGB', (12, 12), 'white').save(image_stream, format='WEBP')
    image_data = image_stream.getvalue()
    image_hash = put(tmp_path / 'output/07-09-2026/L/chart.webp', image_data)
    put(run / 'candidates/images/chart.webp', image_data)
    pack_hash = pkg.sha256_bytes(b'TEST_ONLY-pack')
    claim_hash = put(run / 'claims/a.json', {'source_sha256': source_hash, 'claims': [
        {'id': 'C1', 'source_quote': 'ราคา EURUSD 1.16141 หากผ่าน 1.16206', 'protected': [
            {'id': 'price', 'value_text': '1.16141', 'kind': 'price', 'unit': 'quote-currency', 'role': 'price'},
            {'id': 'level', 'value_text': '1.16206', 'kind': 'price', 'unit': 'quote-currency', 'role': 'level'}]}]})
    proposal = {'schema': 'p002-za-proposal/v1', 'article_id': 'a', 'source_sha256': source_hash,
                'pack_sha256': pack_hash, 'writer_execution_id': 'TEST_ONLY-writer', 'target_markdown': target,
                'alignment': [{'claim_id': 'C1', 'target_field': 'body', 'target_quote': 'EURUSD 1.16141 if above 1.16206.'}],
                'open_questions': [], 'attempt': 1}
    put(run / 'proposals/a.json', proposal)
    manifest = {'schema': 'p002-za-source/v1', 'run_id': 'TEST_ONLY', 'country_code': 'ZA', 'content_locale': 'en-ZA',
                'language_pack': 'en-001', 'pack_version': '0.1.0', 'pack_sha256': pack_hash,
                'source_business_date': '2026-09-07', 'expected_article_keys': ['L-EURUSD'], 'articles': [
                    {'article_id': 'a', 'style': 'L', 'asset': 'EURUSD', 'source_receipt_id': 'source',
                     'source_path': 'output/07-09-2026/L/source.md', 'source_sha256': source_hash,
                     'claim_map_path': 'claims/a.json', 'claim_map_sha256': claim_hash,
                     'proposal_path': 'proposals/a.json', 'candidate_path': 'candidates/a.md',
                     'images': [{'name': 'chart.webp', 'source_path': 'output/07-09-2026/L/chart.webp',
                                 'source_sha256': image_hash, 'candidate_path': 'candidates/images/chart.webp', 'target_sha256': image_hash}]}]}
    put(manifest_path, manifest)
    records = [{'receipt_id': 'source', 'gate': 'source_acceptance', 'article_id': 'a',
                'pack_sha256': pack_hash, 'claim_map_sha256': claim_hash,
                'source_sha256': source_hash, 'reviewer_execution_id': 'TEST_ONLY-lead', 'verdict': 'PASS',
                'reviewer_kind': 'AI', 'reviewed_at': '2026-09-07T10:00:00+07:00', 'findings': []}]
    for gate in ['language', 'semantic', 'visual', 'package_input']:
        records.append({'receipt_id': gate, 'gate': gate, 'article_id': 'a', 'source_sha256': source_hash,
                        'target_sha256': pkg.sha256_bytes(target.encode()), 'pack_sha256': pack_hash,
                        'claim_map_sha256': claim_hash, 'image_hashes': {'chart.webp': image_hash},
                        'reviewer_execution_id': 'TEST_ONLY-reviewer', 'reviewer_kind': 'AI',
                        'reviewed_at': '2026-09-07T10:00:00+07:00', 'verdict': 'PASS', 'findings': []})
    def index(records_to_use):
        entries = []
        for record in records_to_use:
            relative = 'receipts/' + record['receipt_id'] + '.json'
            digest = put(run / relative, record)
            entries.append({'receipt_id': record['receipt_id'], 'path': relative, 'sha256': digest})
        put(index_path, {'receipts': entries})
    index(records)
    pack = {'locale': 'en-001', 'version': '0.1.0', 'status': 'stable_locked', 'verified': True,
            'sha256': pack_hash, 'recorded_sha256': pack_hash, 'approved_by': 'TEST_ONLY', 'approved_at': '2026-09-07'}
    return dict(root=tmp_path, run=run, manifest=manifest, manifest_path=manifest_path, index_path=index_path,
                records=records, index=index, pack=pack, proposal=proposal, args=(manifest_path, index_path, tmp_path))


def test_candidate_before_review_and_draft_cannot_release(case):
    case['index'](case['records'][:1])
    with patch.object(pkg, '_load_pack', return_value={**case['pack'], 'status': 'draft'}):
        staged = pkg.stage_candidates(*case['args'])
        assert staged['status'] == 'PASS'
        assert not staged['release_eligible']
        before = pkg._tree(case['root'])
        checked = pkg.check_country(*case['args'])
        assert checked['status'] == 'HOLD'
        assert checked['articles'][0]['review_status'] == 'PENDING'
        assert 'OPEN_QUESTIONS' not in {finding['code'] for finding in checked['articles'][0]['findings']}
        assert pkg._tree(case['root']) == before
        with pytest.raises(pkg.PackageError):
            pkg.commit_country(*case['args'], 'r1', 'b1')


def test_commit_has_daily_path_inventory_and_idempotent_rerun(case):
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        assert pkg.stage_candidates(*case['args'])['status'] == 'PASS'
        before = pkg._tree(case['root'])
        assert pkg.check_country(*case['args'])['status'] == 'PASS'
        assert pkg._tree(case['root']) == before
        result = pkg.commit_country(*case['args'], 'r1', 'b1')
    marker = case['root'] / 'output/07-09-2026/134-Localized/batches/b1/manifest.json'
    assert marker.is_file()
    release = Path(result['release_root'])
    assert (release / 'L/EURUSD/P002-20260907-ZA-L-EURUSD-img01-chart.webp').is_file()
    assert 'L/EURUSD/P002-20260907-ZA-L-EURUSD-img01-chart.webp' in pkg._read_json(release / 'manifest.json')['files']
    assert result['expected_articles'] == result['available_articles'] == result['ready_articles'] == 1
    assert result['missing_article_keys'] == []
    public = pkg._read_json(release / 'manifest.json')
    assert public['expected_articles'] == 1
    assert public['expected_article_keys'] == ['L-EURUSD']
    before = pkg._tree(case['root'])
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        assert pkg.commit_country(*case['args'], 'r1', 'b1')['status'] == 'PASS'
    assert pkg._tree(case['root']) == before
    (release / 'L/EURUSD/P002-20260907-ZA-L-EURUSD-article.md').write_bytes(b'corrupt')
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        with pytest.raises(pkg.OutputConflict):
            pkg.commit_country(*case['args'], 'r1', 'b1')


def test_partial_selected_set_can_stage_but_never_complete_country(case):
    expected = ['D-XAUUSD', 'D-WTIUSD', 'E-XAUUSD', 'M-BTCUSD', 'L-EURUSD', 'L-USDJPY']
    case['manifest']['expected_article_keys'] = expected
    put(case['manifest_path'], case['manifest'])
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        staged = pkg.stage_candidates(*case['args'])
        assert staged['status'] == 'PASS'
        assert staged['expected_articles'] == 6
        assert staged['available_articles'] == 1
        assert staged['ready_articles'] == 0
        assert staged['missing_article_keys'] == [key for key in expected if key != 'L-EURUSD']
        before = pkg._tree(case['root'])
        checked = pkg.check_country(*case['args'])
        assert checked['status'] == 'HOLD'
        assert not checked['release_eligible']
        assert checked['ready_articles'] == 1  # A valid available article cannot satisfy the whole expected set.
        assert checked['expected_articles'] == 6
        assert checked['available_articles'] == 1
        assert checked['missing_article_keys'] == staged['missing_article_keys']
        assert checked['findings'][0]['code'] == 'EXPECTED_ARTICLES_MISSING'
        with pytest.raises(pkg.PackageError, match='country HOLD'):
            pkg.commit_country(*case['args'], 'r1', 'b1')
        assert pkg._tree(case['root']) == before


@pytest.mark.parametrize('expected', [None, [], 'L-EURUSD', ['L-EURUSD', 'L-EURUSD'],
                                      ['l-eurusd'], ['L/EURUSD'], ['L-EURUSD', None],
                                      ['L-EURUSD', {}], ['L-USDJPY']])
def test_invalid_expected_keys_or_unexpected_actual_article_are_rejected(case, expected):
    case['manifest']['expected_article_keys'] = expected
    put(case['manifest_path'], case['manifest'])
    with pytest.raises(pkg.InputError):
        pkg.load_job(case['manifest_path'], case['root'])


def test_expected_article_keys_are_required_not_inferred_from_available(case):
    del case['manifest']['expected_article_keys']
    put(case['manifest_path'], case['manifest'])
    with pytest.raises(pkg.InputError):
        pkg.load_job(case['manifest_path'], case['root'])


@pytest.mark.parametrize('path', ['../escape', '/absolute', 'C:\\evil', 'x/../y', 'file:stream', 'x./a'])
def test_reject_unsafe_path(case, path):
    with pytest.raises(pkg.InputError):
        pkg.resolve_scoped_file(case['run'], path)


def test_manifest_invented_pack_ready_is_ignored(case):
    case['manifest']['pack_status'] = 'stable_locked'
    put(case['manifest_path'], case['manifest'])
    # Exercise the real approved pack while the job keeps a forged digest.
    info = pkg._load_pack(case['manifest'])
    assert info['status'] == 'stable_locked'
    assert info['sha256'] != case['manifest']['pack_sha256']
    assert pkg.stage_candidates(*case['args'])['status'] == 'HOLD'


def test_inline_receipt_and_override_are_rejected(case):
    put(case['index_path'], {'receipts': [case['records'][0]]})
    with pytest.raises(pkg.InputError):
        pkg.load_trusted_receipts(case['index_path'], case['run'])
    case['index'](case['records'])
    entry = pkg._read_json(case['index_path'])
    entry['receipts'][0]['verdict'] = 'PASS'
    put(case['index_path'], entry)
    with pytest.raises(pkg.InputError):
        pkg.load_trusted_receipts(case['index_path'], case['run'])


def test_changed_index_receipt_bytes_rejected(case):
    (case['run'] / 'receipts/source.json').write_bytes(b'{}')
    with pytest.raises(pkg.InputError):
        pkg.load_trusted_receipts(case['index_path'], case['run'])


@pytest.mark.parametrize('mutation', ['image', 'claim', 'source', 'candidate'])
def test_changed_bytes_hold_and_check_does_not_write(case, mutation):
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        pkg.stage_candidates(*case['args'])
        paths = {'image': case['run'] / 'candidates/images/chart.webp', 'claim': case['run'] / 'claims/a.json',
                 'source': case['root'] / 'output/07-09-2026/L/source.md', 'candidate': case['run'] / 'candidates/a.md'}
        paths[mutation].write_bytes(paths[mutation].read_bytes() + b' ')
        before = pkg._tree(case['root'])
        assert pkg.check_country(*case['args'])['status'] == 'HOLD'
        assert pkg._tree(case['root']) == before


def test_duplicate_articles_and_output_override_rejected(case):
    case['manifest']['articles'] *= 2
    put(case['manifest_path'], case['manifest'])
    with pytest.raises(pkg.InputError):
        pkg.load_job(case['manifest_path'], case['root'])
    case['manifest']['articles'] = case['manifest']['articles'][:1]
    case['manifest']['output_root'] = 'Repo'
    put(case['manifest_path'], case['manifest'])
    with pytest.raises(pkg.InputError):
        pkg.load_job(case['manifest_path'], case['root'])


def test_failure_during_staging_never_creates_batch_and_retry_works(case):
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        pkg.stage_candidates(*case['args'])
        original = pkg._write_new
        def interrupt(path, data):
            original(path, data)
            if path.name.endswith('-article.md'):
                raise OSError('TEST_ONLY crash')
        with patch.object(pkg, '_write_new', side_effect=interrupt), pytest.raises(OSError):
            pkg.commit_country(*case['args'], 'r1', 'b1')
        assert not list((case['root'] / 'output').rglob('batches/*/manifest.json'))
        assert pkg.commit_country(*case['args'], 'r1', 'b1')['status'] == 'PASS'


def test_input_changes_during_commit_no_marker(case):
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        pkg.stage_candidates(*case['args'])
        original = pkg._write_new
        def mutate(path, data):
            original(path, data)
            if path.name.endswith('-article.md'):
                source = case['root'] / 'output/07-09-2026/L/source.md'
                source.write_bytes(source.read_bytes() + b'changed')
        with patch.object(pkg, '_write_new', side_effect=mutate), pytest.raises(pkg.PackageError):
            pkg.commit_country(*case['args'], 'r1', 'b1')
        assert not list((case['root'] / 'output').rglob('batches/*/manifest.json'))


def test_stage_cli_present_and_missing_inputs_structured(case, capsys):
    assert pkg.main(['--project-root', str(case['root']), '--manifest', str(case['manifest_path']),
                     '--receipt-index', str(case['index_path']), '--stage-candidates']) == 1
    assert json.loads(capsys.readouterr().out)['mode'] == 'stage-candidates'


def test_reusing_release_after_receipt_binding_change_conflicts(case):
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        pkg.stage_candidates(*case['args'])
        pkg.commit_country(*case['args'], 'r1', 'b1')
        records = [dict(r) for r in case['records']]
        records[1]['reviewer_execution_id'] = 'TEST_ONLY-new-reviewer'
        case['index'](records)
        with pytest.raises(pkg.OutputConflict):
            pkg.commit_country(*case['args'], 'r1', 'b1')


def test_manifest_change_after_first_evaluation_never_publishes(case):
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        pkg.stage_candidates(*case['args'])
        original = pkg._evaluate
        calls = 0
        def mutate_after_evaluation(*args, **kwargs):
            nonlocal calls
            evaluated = original(*args, **kwargs)
            calls += 1
            if calls == 1:
                # Mutation after evaluation but before the old implementation's
                # run-root snapshot: both evaluations still independently pass.
                manifest = pkg._read_json(case['manifest_path'])
                manifest['run_id'] = 'TEST_ONLY-changed'
                put(case['manifest_path'], manifest)
            return evaluated
        with patch.object(pkg, '_evaluate', side_effect=mutate_after_evaluation), pytest.raises(pkg.PackageError):
            pkg.commit_country(*case['args'], 'r1', 'b1')
        assert not list((case['root'] / 'output').rglob('batches/*/manifest.json'))


def test_second_evaluation_extra_file_never_publishes(case):
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        pkg.stage_candidates(*case['args'])
        original = pkg._evaluate
        calls = 0
        def extra_file(*args, **kwargs):
            nonlocal calls
            evaluated = original(*args, **kwargs)
            calls += 1
            if calls == 2:
                evaluated[4]['L-SECOND/article.md'] = b'newly selected article'
            return evaluated
        with patch.object(pkg, '_evaluate', side_effect=extra_file), pytest.raises(pkg.PackageError):
            pkg.commit_country(*case['args'], 'r1', 'b1')
        assert not list((case['root'] / 'output').rglob('batches/*/manifest.json'))


def test_webp_magic_without_decodable_image_is_rejected(case):
    data = b'RIFF\x04\x00\x00\x00WEBP'
    bad_hash = put(case['run'] / 'candidates/images/chart.webp', data)
    case['manifest']['articles'][0]['images'][0]['target_sha256'] = bad_hash
    put(case['manifest_path'], case['manifest'])
    records = [dict(r) for r in case['records']]
    for record in records:
        if record['gate'] in {'visual', 'package_input'}:
            record['image_hashes'] = {'chart.webp': bad_hash}
    case['index'](records)
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        pkg.stage_candidates(*case['args'])
        report = pkg.check_country(*case['args'])
        assert report['status'] == 'HOLD'
        with pytest.raises(pkg.PackageError):
            pkg.commit_country(*case['args'], 'r1', 'b1')


def test_manifest_asset_cannot_mislabel_source_folder(case):
    case['manifest']['articles'][0]['asset'] = 'BTCUSD'
    case['manifest']['expected_article_keys'] = ['L-BTCUSD']
    put(case['manifest_path'], case['manifest'])
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        pkg.stage_candidates(*case['args'])
        assert pkg.check_country(*case['args'])['status'] == 'HOLD'
        with pytest.raises(pkg.PackageError):
            pkg.commit_country(*case['args'], 'r1', 'b1')


@pytest.mark.parametrize('source_asset,manifest_asset,passes', [('btc', 'BTCUSD', True),
                                                               ('wti', 'WTIUSD', True),
                                                               ('oil', 'WTIUSD', False),
                                                               ('btc', 'btc', True),
                                                               ('bitcoin', 'BTCUSD', False)])
def test_only_explicit_public_asset_aliases_are_accepted(case, source_asset, manifest_asset, passes):
    article = case['manifest']['articles'][0]
    source_path = case['root'] / article['source_path']
    source = source_path.read_text(encoding='utf-8').replace('asset: eurusd', 'asset: ' + source_asset)
    source_hash = put(source_path, source.encode())
    claims = pkg._read_json(case['run'] / article['claim_map_path'])
    claims['source_sha256'] = source_hash
    claim_hash = put(case['run'] / article['claim_map_path'], claims)
    proposal = dict(case['proposal'])
    proposal['source_sha256'] = source_hash
    proposal['target_markdown'] = proposal['target_markdown'].replace('asset: eurusd', 'asset: ' + source_asset)
    target_hash = pkg.sha256_bytes(proposal['target_markdown'].encode())
    put(case['run'] / article['proposal_path'], proposal)
    article.update(style='M', asset=manifest_asset, source_sha256=source_hash, claim_map_sha256=claim_hash)
    case['manifest']['expected_article_keys'] = ['M-' + ('BTCUSD' if manifest_asset.upper() == 'BTC' else manifest_asset.upper())]
    put(case['manifest_path'], case['manifest'])
    records = [{**r, 'source_sha256': source_hash, 'claim_map_sha256': claim_hash,
                **({'target_sha256': target_hash} if r['gate'] != 'source_acceptance' else {})}
               for r in case['records']]
    case['index'](records)
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        pkg.stage_candidates(*case['args'])
        result = pkg.check_country(*case['args'])
        assert result['release_eligible'] is passes
        assert result['missing_article_keys'] == []
        if not passes:
            assert any(f['code'] == 'SOURCE_IDENTITY_MISMATCH' for a in result['articles'] for f in a['findings'])


def test_symlink_component_is_rejected(case):
    import errno
    import stat
    from types import SimpleNamespace
    outside = case['root'] / 'outside'
    outside.mkdir()
    link = case['run'] / 'linked'
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        if exc.errno in {errno.EPERM, errno.EACCES, errno.ENOTSUP} or getattr(exc, 'winerror', None) == 1314:
            # Exercise the real resolver with a synthetic lstat result when
            # Windows cannot create a symlink. The separate junction test
            # still exercises a real NTFS reparse point without privileges.
            original_lstat = Path.lstat

            def lstat_with_link(path, *args, **kwargs):
                if path == link:
                    return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777,
                                           st_file_attributes=0)
                return original_lstat(path, *args, **kwargs)

            with patch.object(Path, 'lstat', lstat_with_link):
                with pytest.raises(pkg.InputError, match='link/reparse point forbidden'):
                    pkg.resolve_scoped_file(case['run'], 'linked/new.md')
            return
        raise
    with pytest.raises(pkg.InputError, match='link/reparse point forbidden'):
        pkg.resolve_scoped_file(case['run'], 'linked/new.md')


def test_stage_never_advertises_release_readiness(case):
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        report = pkg.stage_candidates(*case['args'])
        assert report['status'] == 'PASS'
        assert report['ready_articles'] == 0
        assert all(a['status'] == 'CANDIDATE' and not a['release_eligible'] for a in report['articles'])
        assert report['release_eligible'] is False


def test_windows_junction_component_is_rejected(case):
    import os
    import subprocess
    if os.name != 'nt':
        pytest.skip('NTFS junction test requires Windows')
    target = case['root'] / 'junction-target'
    target.mkdir()
    link = case['run'] / 'junction'
    env = {**os.environ, 'P002_TEST_JUNCTION': str(link), 'P002_TEST_TARGET': str(target)}
    created = subprocess.run(
        ['powershell', '-NoProfile', '-NonInteractive', '-Command',
         '$ErrorActionPreference = "Stop"; New-Item -ItemType Junction -Path $env:P002_TEST_JUNCTION -Target $env:P002_TEST_TARGET | Out-Null'],
        env=env, capture_output=True, text=True)
    assert created.returncode == 0, created.stderr
    with pytest.raises(pkg.InputError):
        pkg.resolve_scoped_file(case['run'], 'junction/new.md')


def test_marker_temporary_files_stay_out_of_output(case):
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        pkg.stage_candidates(*case['args'])
        pkg.commit_country(*case['args'], 'r1', 'b1')
    assert not list((case['root'] / 'output').rglob('*.tmp'))


def test_v2_delivery_uses_the_single_country_folder_with_nested_style_asset(case):
    country = localization_config.resolve_country('ZA')
    case['manifest'].update(schema='p002-localized-source/v2',
                            country_policy_sha256=country['policy_sha256'])
    case['proposal']['schema'] = 'p002-localized-proposal/v2'
    put(case['run'] / case['manifest']['articles'][0]['proposal_path'], case['proposal'])
    put(case['manifest_path'], case['manifest'])
    with patch.object(pkg, '_load_pack', return_value=case['pack']):
        assert pkg.stage_candidates(*case['args'])['status'] == 'PASS'
        result = pkg.commit_country(*case['args'], 'ignored-by-v2', 'b0001')
    expected = case['root'] / 'output/07-09-2026/ZA-South-Africa'
    assert Path(result['release_root']) == expected
    assert (expected / 'manifest.json').is_file()
    assert (expected / 'L/EURUSD/P002-20260907-ZA-L-EURUSD-article.md').is_file()
    assert (expected.parent / 'manifest.json').is_file()


def _recovery_bundle_for_case(case, *, wrong_hash=False):
    """Build a hash-bound source bundle entirely inside the pytest root."""
    article = case['manifest']['articles'][0]
    source_path = case['root'] / article['source_path']
    image = article['images'][0]
    image_path = case['root'] / image['source_path']
    binding_root = case['root'] / 'work/localization/07-09-2026/source-bindings-r0003'
    canonical_images = [{'name': image['name'], 'path': image['source_path'], 'sha256': image['source_sha256']}]
    inventory = pkg.sha256_bytes(f"{image['name']}:{image['source_sha256']}".encode())
    canonical = {'article_id': article['article_id'], 'source_path': article['source_path'],
                 'source_sha256': article['source_sha256'], 'images': canonical_images,
                 'source_images_sha256': inventory, 'claim_map_path': article['claim_map_path'],
                 'claim_map_sha256': article['claim_map_sha256']}
    binding = {'schema': 'p002-source-bindings/v2', 'status': 'SOURCE_READY',
               'source_business_date': '2026-09-07', 'articles': [canonical]}
    binding_path = binding_root / 'source-bindings.json'
    binding_hash = put(binding_path, binding)
    put(binding_root / 'receipts/a.json', {'fixture': 'source QA is validated separately'})
    stage = case['root'] / 'work/localization/07-09-2026/recovery/a'
    staged_article_hash = put(stage / 'article.md', source_path.read_bytes())
    staged_image_hash = put(stage / 'chart.webp', image_path.read_bytes())
    bundle = {'schema': 'p002-source-recovery-bundle/v1', 'article_id': 'a',
              'source_business_date': '2026-09-07',
              'binding_manifest_path': 'work/localization/07-09-2026/source-bindings-r0003/source-bindings.json',
              'binding_manifest_sha256': binding_hash,
              'binding_target_paths': {'article': article['source_path'], 'images': [image['source_path']]},
              'files': [{'role': 'article', 'staged_path': 'article.md', 'sha256': staged_article_hash},
                        {'role': 'image', 'staged_path': 'chart.webp',
                         'sha256': ('0' * 64 if wrong_hash else staged_image_hash)}]}
    bundle_path = stage / 'recovery-bundle.json'
    put(bundle_path, bundle)
    return bundle_path, source_path, image_path


def test_explicit_recovery_bundle_package_loads_missing_canonical_source(case):
    bundle, source_path, image_path = _recovery_bundle_for_case(case)
    source_path.unlink()
    image_path.unlink()
    with patch.object(pkg, '_load_pack', return_value=case['pack']), \
         patch.object(pkg.source_qa_acceptance, 'validate_source_acceptance', return_value={}):
        assert pkg.stage_candidates(*case['args'], recovery_bundle_path=bundle)['status'] == 'PASS'
        report = pkg.check_country(*case['args'], recovery_bundle_path=bundle)
    assert report['status'] == 'PASS', report['articles'][0]['findings']
    assert report['release_eligible'] is True


def test_explicit_recovery_bundle_rejects_wrong_staged_hash(case):
    bundle, _, _ = _recovery_bundle_for_case(case, wrong_hash=True)
    with pytest.raises(pkg.InputError, match='staged hash differs'):
        pkg.check_country(*case['args'], recovery_bundle_path=bundle)


def test_final_delivery_rewrites_inventory_bound_bare_image_filename(case):
    manifest = dict(case['manifest'])
    manifest['_run_root'] = str(case['run'])
    article = manifest['articles'][0]
    target = case['proposal']['target_markdown'].replace('images/chart.webp', 'chart.webp').encode('utf-8')
    files = pkg._final_delivery_files(manifest, article, target)
    delivered_article = next(data for path, data in files.items() if path.endswith('-article.md')).decode('utf-8')
    assert '](chart.webp)' not in delivered_article
    assert '](P002-20260907-ZA-L-EURUSD-img01-chart.webp)' in delivered_article


def test_final_delivery_rejects_bare_filename_outside_image_inventory(case):
    manifest = dict(case['manifest'])
    manifest['_run_root'] = str(case['run'])
    article = manifest['articles'][0]
    target = case['proposal']['target_markdown'].replace('images/chart.webp', 'unbound.webp').encode('utf-8')
    with pytest.raises(pkg.InputError, match='final image link mapping is incomplete'):
        pkg._final_delivery_files(manifest, article, target)
