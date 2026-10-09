"""Synthetic, offline tests for the separate historical-import boundary."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vps_pipeline import archive as ar
from vps_pipeline.analysis import _load_review
from vps_pipeline.legacy import LegacyError, verify_legacy


REPORT_URL = 'https://nodequality.com/r/synthetic-legacy'
SECOND_URL = 'https://browser.geekbench.com/v5/cpu/12345678'
THIRD_URL = 'https://report.check.place/synthetic-third'
REPORT = 'Synthetic historical report. No real host or measurement. ' * 4


def _save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _metadata(manifest):
    return {k: manifest.get(k) for k in ('title', 'author', 'captured_at', 'capture_method', 'capture_note')}


def make_legacy(root, post_id='900001'):
    """Reusable synthetic legacy fixture; returns its manifest path."""
    directory = Path(root) / 'assets' / post_id
    directory.mkdir(parents=True)
    canonical = f'https://www.nodeseek.com/post-{post_id}-1'
    markup = ('<article class="post-content"><p>Synthetic legacy first post: 1 vCPU.</p>'
              f'<a href="{REPORT_URL}">Synthetic report</a></article>')
    text = ar._DOM(markup).root.text().strip()
    manifest = {'schema_version': 'vps-archive/1', 'post_id': post_id, 'source_url': canonical,
                'title': 'Synthetic archive', 'author': 'Synthetic author',
                'captured_at': '2026-01-01T00:00:00+00:00', 'capture_method': 'browser_import',
                'capture_note': 'Synthetic historical first-post article capture; no replies. Offline test only.',
                'status': 'ready', 'files': [], 'links': [{'url': REPORT_URL, 'kind': 'report'}], 'failures': []}
    for role, body, source, mime, suffix in [
        ('first_post_html', markup, canonical, 'text/html', 'html'),
        ('first_post_text', text, canonical, 'text/plain', 'txt'),
        ('report_text', REPORT, REPORT_URL, 'text/plain', 'txt'),
    ]:
        data = body.encode('utf-8')
        item = ar._file_entry(role, data, mime, suffix, source)
        manifest['files'].append(item)
        (directory / item['path']).write_bytes(data)
    analysis = _load_review().draft(manifest)
    analysis['ai_review'] = {'completed': True, 'agent': 'Synthetic historical declaration only',
                             'reviewed_files': ['manifest'] + [f['id'] for f in manifest['files']]}
    analysis['summary'] = 'Synthetic historical analysis; not a real review.'
    text_id = next(f['id'] for f in manifest['files'] if f['role'] == 'first_post_text')
    analysis['facts']['vcpu'] = {'value': 1, 'status': 'reported', 'note': 'Synthetic source statement.',
                               'evidence': [{'file_id': text_id, 'locator': 'first paragraph', 'quote': '1 vCPU'}]}
    analysis.update(sources=copy.deepcopy(manifest['files']), source_metadata=_metadata(manifest),
                    archive_status=manifest['status'], download_failures=copy.deepcopy(manifest['failures']))
    _save(directory / 'manifest.json', manifest)
    _save(directory / 'analysis.json', analysis)
    return directory / 'manifest.json'


class LegacyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = make_legacy(self.root)

    def read(self):
        return json.loads(self.path.read_text()), json.loads((self.path.parent / 'analysis.json').read_text())

    def write(self, manifest, analysis=None, bind=True):
        if analysis is None:
            analysis = self.read()[1]
        if bind:
            analysis.update(sources=copy.deepcopy(manifest['files']), source_metadata=_metadata(manifest),
                            archive_status=manifest['status'], download_failures=copy.deepcopy(manifest['failures']))
        _save(self.path, manifest)
        _save(self.path.parent / 'analysis.json', analysis)

    def replace(self, manifest, role, body):
        item = next(f for f in manifest['files'] if f['role'] == role)
        data = body.encode('utf-8')
        (self.path.parent / item['path']).write_bytes(data)
        item.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        return item

    def add_report(self, manifest, analysis, source, body, role='report_text'):
        data = body.encode('utf-8')
        item = ar._file_entry(role, data, 'text/html' if role == 'report_html' else 'text/plain',
                              'html' if role == 'report_html' else 'txt', source)
        item['path'] = item['id'] + ('.html' if role == 'report_html' else '.txt')
        (self.path.parent / item['path']).write_bytes(data)
        manifest['files'].append(item)
        manifest['links'].append({'url': source, 'kind': 'report'})
        analysis['ai_review']['reviewed_files'].append(item['id'])
        return item

    def test_original_bytes_values_and_historical_review_are_preserved(self):
        before = {p: p.read_bytes() for p in self.path.parent.iterdir()}
        m, a = self.read()
        with patch('socket.getaddrinfo', side_effect=AssertionError('No network')):
            result = verify_legacy(self.path)
        self.assertEqual(result['status'], 'legacy_imported')
        self.assertEqual(result['manifest'], m)
        self.assertEqual(result['analysis'], a)
        self.assertEqual(result['provenance']['historical_ai_review'], a['ai_review'])
        self.assertEqual(result['manifest_sha256'], hashlib.sha256(before[self.path]).hexdigest())
        original_analysis = before[self.path.parent / 'analysis.json']
        framed = (b'vps-legacy-bundle/1\0' + len(before[self.path]).to_bytes(8, 'big') + before[self.path]
                  + len(original_analysis).to_bytes(8, 'big') + original_analysis)
        self.assertEqual(result['bundle_sha256'], hashlib.sha256(framed).hexdigest())
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertEqual(before, {p: p.read_bytes() for p in self.path.parent.iterdir()})
        self.assertNotIn('observations', result['analysis'])
        self.assertNotIn('review_log', result['analysis'])
        self.assertEqual(result['validation']['missing_new_envelope_fields'], ['observations', 'review_log'])
        for flag in ('new_review_performed', 'ai_invoked', 'review_attestation_verified', 'new_analysis_accepted'):
            self.assertIs(result['validation'][flag], False)

    def test_custom_analysis_path_and_byte_sensitive_hash(self):
        alternate = self.root / 'alternate.json'
        alternate.write_bytes((self.path.parent / 'analysis.json').read_bytes() + b'\n')
        default = verify_legacy(self.path)
        other = verify_legacy(self.path, alternate)
        self.assertEqual(default['analysis'], other['analysis'])
        self.assertNotEqual(default['analysis_sha256'], other['analysis_sha256'])
        self.assertNotEqual(default['bundle_sha256'], other['bundle_sha256'])

    def test_hashed_report_second_hop_has_exact_locator(self):
        m, a = self.read()
        first = self.replace(m, 'report_text', REPORT + '\n' + SECOND_URL + '\n')
        second = self.add_report(m, a, SECOND_URL, REPORT)
        self.write(m, a)
        result = verify_legacy(self.path)
        edge = next(e for e in result['provenance']['resource_chains'] if e['depth'] == 2)
        self.assertEqual(edge['from_file_id'], first['id'])
        self.assertEqual(edge['target_file_id'], second['id'])
        self.assertEqual(edge['url'], SECOND_URL)
        self.assertEqual(edge['quote'], SECOND_URL)
        self.assertTrue(edge['locator'].startswith('text-character:'))

    def test_manifest_links_alone_cannot_authorize_resource(self):
        m, a = self.read()
        self.add_report(m, a, SECOND_URL, REPORT)
        self.write(m, a)
        with self.assertRaisesRegex(LegacyError, 'provenance chain'):
            verify_legacy(self.path)

    def test_third_hop_and_unreachable_cycles_are_rejected(self):
        m, a = self.read()
        self.replace(m, 'report_text', REPORT + '\n' + SECOND_URL)
        self.add_report(m, a, SECOND_URL, REPORT + '\n' + THIRD_URL)
        self.add_report(m, a, THIRD_URL, REPORT)
        self.write(m, a)
        with self.assertRaisesRegex(LegacyError, 'provenance chain'):
            verify_legacy(self.path)
        self.replace(m, 'report_text', REPORT)
        second = next(f for f in m['files'] if f['source_url'] == SECOND_URL)
        third = next(f for f in m['files'] if f['source_url'] == THIRD_URL)
        for entry, target in ((second, THIRD_URL), (third, SECOND_URL)):
            body = (REPORT + target).encode()
            (self.path.parent / entry['path']).write_bytes(body)
            entry.update(sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
        self.write(m, a)
        with self.assertRaisesRegex(LegacyError, 'provenance chain'):
            verify_legacy(self.path)

    def test_source_prefix_is_not_exact_second_hop_url(self):
        m, a = self.read()
        self.replace(m, 'report_text', REPORT + SECOND_URL + '999')
        self.add_report(m, a, SECOND_URL, REPORT)
        self.write(m, a)
        with self.assertRaisesRegex(LegacyError, 'provenance chain'):
            verify_legacy(self.path)

    def test_script_template_only_links_cannot_prove_second_hop(self):
        for tag in ('script', 'style', 'template', 'noscript'):
            with self.subTest(tag=tag):
                m, a = self.read()
                first = next(f for f in m['files'] if f['source_url'] == REPORT_URL)
                first.update(role='report_html', content_type='text/html', path='report.html')
                self.replace(m, 'report_html', '<html><body><p>' + REPORT + '</p>'
                             f'<{tag}><a href="{SECOND_URL}">{SECOND_URL}</a></{tag}></body></html>')
                if not any(f['source_url'] == SECOND_URL for f in m['files']):
                    self.add_report(m, a, SECOND_URL, REPORT)
                self.write(m, a)
                with self.assertRaisesRegex(LegacyError, 'provenance chain'):
                    verify_legacy(self.path)

    def test_active_html_cannot_be_disguised_as_report_text(self):
        m, a = self.read()
        self.replace(m, 'report_text', REPORT + '<script>' + SECOND_URL + '</script>')
        self.add_report(m, a, SECOND_URL, REPORT)
        self.write(m, a)
        with self.assertRaisesRegex(LegacyError, 'HTML cannot claim report_text'):
            verify_legacy(self.path)

    def test_visible_html_anchor_can_prove_second_hop(self):
        m, a = self.read()
        first = next(f for f in m['files'] if f['source_url'] == REPORT_URL)
        first.update(role='report_html', content_type='text/html', path='report.html')
        self.replace(m, 'report_html', '<html><body><p>' + REPORT + '</p>'
                     f'<a href="{SECOND_URL}">Historical result</a></body></html>')
        self.add_report(m, a, SECOND_URL, REPORT)
        self.write(m, a)
        self.assertEqual(verify_legacy(self.path)['provenance']['resource_chains'][-1]['depth'], 2)

    def test_report_host_allowlist_is_not_relaxed(self):
        m, a = self.read()
        url = 'https://unproven.example.com/arbitrary'
        self.replace(m, 'report_text', REPORT + url)
        self.add_report(m, a, url, REPORT)
        self.write(m, a)
        with self.assertRaisesRegex(LegacyError, 'host is not allowed'):
            verify_legacy(self.path)

    def test_first_post_fragment_and_reply_identity_ambiguities_rejected(self):
        original_m, original_a = self.read()
        original = (self.path.parent / original_m['files'][0]['path']).read_text()
        for markup in (
            '<div id="0">' + original + '</div>', '<html><body>' + original + '</body></html>',
            original + '<article class="post-content">Reply</article>',
            original.replace('1 vCPU.', '<div id="2">1 vCPU.</div>'),
            original.replace('1 vCPU.', '<div class="reply">1 vCPU.</div>'),
            original.replace('1 vCPU.', '<article>1 vCPU.</article>'),
            original.removesuffix('</article>'), original + '</div>',
            original.replace('</article>', '<div>Unclosed nested block</article>'),
        ):
            with self.subTest(markup=markup[:50]):
                m = copy.deepcopy(original_m)
                self.replace(m, 'first_post_html', markup)
                self.replace(m, 'first_post_text', ar._DOM(markup).root.text().strip())
                self.write(m, copy.deepcopy(original_a))
                with self.assertRaises(LegacyError):
                    verify_legacy(self.path)

    def test_script_only_first_post_link_is_not_observed(self):
        m, a = self.read()
        markup = ('<article class="post-content"><p>Synthetic legacy first post: 1 vCPU.</p>'
                  f'<template><a href="{REPORT_URL}">Report</a></template></article>')
        self.replace(m, 'first_post_html', markup)
        self.replace(m, 'first_post_text', ar._DOM(markup).root.text().strip())
        self.write(m, a)
        with self.assertRaisesRegex(LegacyError, 'provenance chain'):
            verify_legacy(self.path)

    def test_primary_text_must_match_original_fragment(self):
        m, a = self.read()
        self.replace(m, 'first_post_text', 'Unproven 1 vCPU viewport concatenation')
        self.write(m, a)
        with self.assertRaisesRegex(LegacyError, 'primary text disagree'):
            verify_legacy(self.path)

    def test_changed_hash_and_mid_validation_change_rejected(self):
        m, a = self.read()
        target = self.path.parent / m['files'][-1]['path']
        before = target.read_bytes()
        target.write_bytes(b'changed')
        with self.assertRaisesRegex(LegacyError, 'integrity'):
            verify_legacy(self.path)
        target.write_bytes(before)
        import vps_pipeline.legacy as module
        original = module._validate_analysis

        def change(*args, **kwargs):
            original(*args, **kwargs)
            target.write_bytes(b'changed after quote validation')

        with patch.object(module, '_validate_analysis', side_effect=change):
            with self.assertRaisesRegex(LegacyError, 'changed during'):
                verify_legacy(self.path)

    def test_duplicate_and_nonfinite_json_rejected_in_both_inputs(self):
        for target in (self.path, self.path.parent / 'analysis.json'):
            original = target.read_bytes()
            for extra in ('"duplicate":0,"duplicate":1', '"bad":NaN', '"bad":Infinity', '"bad":1e999'):
                with self.subTest(target=target.name, extra=extra):
                    target.write_bytes(original.rstrip()[:-1] + b',' + extra.encode() + b'}')
                    with self.assertRaises(LegacyError):
                        verify_legacy(self.path)
                    target.write_bytes(original)

    def test_traversal_reserved_metadata_case_collisions_and_zip_rejected(self):
        m, a = self.read()
        for bad in ('../outside.txt', '/outside.txt', 'C:\\outside.txt', 'a/../b.txt',
                    'manifest.json', 'ANALYSIS.JSON', 'a/manifest.json', 'report.zip', 'nul.txt'):
            changed = copy.deepcopy(m)
            changed['files'][-1]['path'] = bad
            self.write(changed, copy.deepcopy(a))
            with self.subTest(path=bad), self.assertRaises(LegacyError):
                verify_legacy(self.path)
        changed = copy.deepcopy(m)
        changed['files'][-1]['path'] = changed['files'][0]['path'].upper()
        self.write(changed, copy.deepcopy(a))
        with self.assertRaisesRegex(LegacyError, 'conflicting evidence paths'):
            verify_legacy(self.path)
        self.write(m, a)
        zip_path = self.root / 'archive.zip'
        zip_path.write_bytes(b'PK\x03\x04not extracted')
        with self.assertRaisesRegex(LegacyError, 'ZIP/archive'):
            verify_legacy(zip_path)

    def test_symlink_evidence_and_analysis_rejected(self):
        m, a = self.read()
        target = self.path.parent / m['files'][-1]['path']
        real = self.root / 'original.txt'
        real.write_bytes(target.read_bytes())
        target.unlink()
        try:
            target.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks not supported')
        with self.assertRaisesRegex(LegacyError, 'Symbolic'):
            verify_legacy(self.path)
        target.unlink()
        target.write_bytes(real.read_bytes())
        link = self.root / 'analysis-link.json'
        link.symlink_to(self.path.parent / 'analysis.json')
        with self.assertRaisesRegex(LegacyError, 'Symbolic'):
            verify_legacy(self.path, link)

    def test_limits_checked_before_evidence_read(self):
        m, a = self.read()
        m['files'][-1]['bytes'] = ar.MAX_BYTES + 1
        self.write(m, a)
        with self.assertRaisesRegex(LegacyError, 'byte length'):
            verify_legacy(self.path)
        m['files'][-1]['bytes'] = len(REPORT.encode())
        self.write(m, a)
        with patch.object(ar, 'MAX_TOTAL_BYTES', m['files'][0]['bytes']):
            with self.assertRaisesRegex(LegacyError, 'total evidence size'):
                verify_legacy(self.path)

    def test_capture_and_historical_binding_requirements(self):
        original_m, original_a = self.read()
        for change in ({'capture_method': 'saved_html_first_post_extraction'}, {'capture_note': ''},
                       {'capture_note': 'hello'}, {'capture_note': 'First-post article captured'},
                       {'source_url': 'https://www.nodeseek.com/post-900001-2'}):
            m = copy.deepcopy(original_m)
            m.update(change)
            self.write(m, copy.deepcopy(original_a))
            with self.subTest(change=change), self.assertRaises(LegacyError):
                verify_legacy(self.path)
        for key, wrong in (('sources', []), ('source_metadata', {}), ('archive_status', 'partial'),
                           ('download_failures', [{'url': 'fake', 'reason': 'fake'}])):
            a = copy.deepcopy(original_a)
            a[key] = wrong
            self.write(original_m, a, bind=False)
            with self.subTest(key=key), self.assertRaisesRegex(LegacyError, 'does not match'):
                verify_legacy(self.path)

    def test_original_61_fields_and_completed_declaration_are_required(self):
        m, a = self.read()
        for change in ('incomplete', 'missing_field', 'duplicate_review', 'normalization'):
            candidate = copy.deepcopy(a)
            if change == 'incomplete':
                candidate['ai_review']['completed'] = False
            elif change == 'missing_field':
                candidate['facts'].pop('vcpu')
            elif change == 'duplicate_review':
                candidate['ai_review']['reviewed_files'].append('manifest')
            else:
                candidate['facts']['test_time'] = {
                    'status': 'reported', 'value': {'report_times': ['2026-01-01T00:00:00+00:00'],
                    'timezone_basis': 'Synthetic'}, 'note': 'Synthetic',
                    'evidence': [{'file_id': 'manifest', 'locator': 'title', 'quote': 'Synthetic'}]}
            self.write(m, candidate)
            with self.subTest(change=change), self.assertRaises(LegacyError):
                verify_legacy(self.path)

    def test_html_quotes_cannot_use_markup_attributes_or_scripts(self):
        m, a = self.read()
        html = next(f for f in m['files'] if f['role'] == 'first_post_html')
        markup = (self.path.parent / html['path']).read_text().replace('</article>',
                  '<script>INVISIBLE_SENTINEL</script></article>')
        self.replace(m, 'first_post_html', markup)
        for quote in (REPORT_URL, '<article class="post-content">', 'INVISIBLE_SENTINEL'):
            a['facts']['vcpu']['evidence'] = [{'file_id': html['id'], 'locator': 'HTML', 'quote': quote}]
            self.write(m, a)
            with self.subTest(quote=quote), self.assertRaisesRegex(LegacyError, 'absent from readable'):
                verify_legacy(self.path)
        a['facts']['vcpu']['evidence'][0]['quote'] = '1\nvCPU'
        self.write(m, a)
        self.assertEqual(verify_legacy(self.path)['analysis'], a)

    def test_documented_existing_971510_supplement_preserves_original_roles(self):
        self.path = make_legacy(self.root / 'supplement', post_id='971510')
        m, a = self.read()
        markup = ('<article class="post-content"><p>Synthetic legacy first post: 1 vCPU.</p>'
                  f'<a href="{REPORT_URL}">Synthetic report</a>'
                  '<details><summary>Closed results</summary><p>' + REPORT + '</p></details></article>')
        self.replace(m, 'first_post_html', markup)
        visible = 'Synthetic legacy first post: 1 vCPU.Synthetic reportClosed results'
        self.replace(m, 'first_post_text', visible)
        supplement = self.add_report(m, a, m['source_url'] + '#0', ar._DOM(markup).root.text().strip() + '\n')
        m['capture_note'] += ' 首帖details追加report_text，原DOM提取，来源#0。'
        self.write(m, a)
        result = verify_legacy(self.path)
        self.assertEqual(result['analysis'], a)
        self.assertEqual(result['manifest'], m)
        self.assertEqual(result['provenance']['derived_files'][0]['derived_role'], 'first_post_supplement')
        self.assertEqual(supplement['role'], 'report_text')
        target = self.path.parent / supplement['path']
        bad = target.read_text() + 'invented extra text'
        target.write_text(bad)
        supplement.update(bytes=len(bad.encode()), sha256=hashlib.sha256(bad.encode()).hexdigest())
        self.write(m, a)
        with self.assertRaisesRegex(LegacyError, 'does not exactly match'):
            verify_legacy(self.path)

    def source_binding_fixture(self):
        m, a = self.read()
        image_url = 'https://images.example.org/synthetic-reviewed.png'
        data = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
        item = ar._file_entry('image', data, 'image/png', 'png', image_url)
        (self.path.parent / item['path']).write_bytes(data)
        m['files'].append(item)
        a['ai_review']['reviewed_files'].append(item['id'])
        html = next(f for f in m['files'] if f['role'] == 'first_post_html')
        markup = (self.path.parent / html['path']).read_text().replace('</article>',
                  '<div class="nsk-magic-tab-title">Synthetic IPv4</div>'
                  f'<img src="{image_url}"></article>')
        self.replace(m, 'first_post_html', markup)
        self.replace(m, 'first_post_text', ar._DOM(markup).root.text().strip())
        a['facts']['vcpu']['evidence'] = [
            {'file_id': item['id'], 'locator': 'Synthetic image region', 'quote': 'Synthetic historical declaration'},
            {'file_id': html['id'], 'locator': 'Synthetic source binding', 'quote': image_url},
        ]
        self.write(m, a)
        return m, a, html, item, markup

    def test_narrow_source_bindings_need_actual_dom_and_same_fact_reviewed_image(self):
        m, a, html, image, markup = self.source_binding_fixture()
        result = verify_legacy(self.path)
        self.assertEqual(result['analysis'], a)
        check = result['provenance']['quote_checks'][0]
        self.assertEqual(check['kind'], 'historical_html_source_binding')
        self.assertEqual(check['binding_type'], 'image_source_url')
        self.assertEqual(check['image_file_ids'], [image['id']])
        self.assertIs(check['measurement_verified'], False)
        a['facts']['vcpu']['evidence'][-1]['quote'] = '<div class="nsk-magic-tab-title">Synthetic IPv4</div>'
        self.write(m, a)
        self.assertEqual(verify_legacy(self.path)['provenance']['quote_checks'][0]['binding_type'], 'tab_label_dom')
        original_evidence = copy.deepcopy(a['facts']['vcpu']['evidence'])
        for quote in ('https://images.example.org/synthetic-reviewed.png?invented=1',
                      'src="https://images.example.org/synthetic-reviewed.png"',
                      '<div class="nsk-magic-tab-title" onclick="evil()">Synthetic IPv4</div>',
                      '<div class="nsk-magic-tab-title">Absent panel</div>',
                      '<div class="nsk-magic-tab-title"><b>Synthetic IPv4</b></div>'):
            a['facts']['vcpu']['evidence'][-1]['quote'] = quote
            self.write(m, a)
            with self.subTest(quote=quote), self.assertRaisesRegex(LegacyError, 'absent from readable'):
                verify_legacy(self.path)
        a['facts']['vcpu']['evidence'] = [original_evidence[-1]]
        self.write(m, a)
        with self.assertRaisesRegex(LegacyError, 'absent from readable'):
            verify_legacy(self.path)
        a['facts']['vcpu']['evidence'] = original_evidence
        a['ai_review']['reviewed_files'].remove(image['id'])
        self.write(m, a)
        with self.assertRaisesRegex(LegacyError, 'original 61-field/review protocol'):
            verify_legacy(self.path)

    def test_source_binding_ignores_script_dom_and_event_attributes(self):
        m, a, html, image, markup = self.source_binding_fixture()
        # The image remains an ordinary observed resource, but its eventful
        # element is ineligible as a narrow historical HTML source binding.
        self.replace(m, 'first_post_html', markup.replace('<img src=', '<img onerror="evil()" src='))
        self.write(m, a)
        with self.assertRaisesRegex(LegacyError, 'absent from readable'):
            verify_legacy(self.path)
        a['facts']['vcpu']['evidence'][-1]['quote'] = '<div class="nsk-magic-tab-title">Invisible panel</div>'
        self.replace(m, 'first_post_html', markup.replace('</article>',
                     '<template><div class="nsk-magic-tab-title">Invisible panel</div></template></article>'))
        self.write(m, a)
        with self.assertRaisesRegex(LegacyError, 'absent from readable'):
            verify_legacy(self.path)

    def test_legacy_bindings_do_not_relax_ordinary_new_analysis(self):
        from vps_pipeline.analysis import AnalysisError, validate_submission
        m, a, html, image, markup = self.source_binding_fixture()
        self.assertEqual(verify_legacy(self.path)['status'], 'legacy_imported')
        envelope = {'schema_version': 'vps-analysis-envelope/1',
                    'archive_sha256': hashlib.sha256(self.path.read_bytes()).hexdigest(),
                    'analysis': a, 'observations': [],
                    'review_log': [{'file_id': f['id'], 'sha256': f['sha256'],
                                    'reviewer': 'Synthetic test only', 'reviewed_at': '2026-01-01T00:00:00+00:00',
                                    'coverage': 'full', 'regions': ['Synthetic'], 'issues': []}
                                   for f in m['files']]}
        envelope['review_log'].append({'file_id': 'manifest', 'sha256': envelope['archive_sha256'],
                                      'reviewer': 'Synthetic test only', 'reviewed_at': '2026-01-01T00:00:00+00:00',
                                      'coverage': 'full', 'regions': ['Synthetic'], 'issues': []})
        with self.assertRaisesRegex(AnalysisError, 'HTML quote is absent'):
            validate_submission(self.path, envelope)
        a['facts']['vcpu']['evidence'][-1]['quote'] = 'INVENTED HTML SENTINEL'
        with self.assertRaisesRegex(AnalysisError, 'HTML quote is absent'):
            validate_submission(self.path, envelope)

    def test_partial_archive_preserves_original_failure_record(self):
        m, a = self.read()
        report = m['files'].pop()
        a['ai_review']['reviewed_files'].remove(report['id'])
        m['status'] = 'partial'
        m['failures'] = [{'url': REPORT_URL, 'reason': 'Historical unavailable report'}]
        self.write(m, a)
        result = verify_legacy(self.path)
        self.assertEqual(result['manifest']['failures'], m['failures'])
        self.assertEqual(result['analysis']['download_failures'], m['failures'])


if __name__ == '__main__':
    unittest.main()
