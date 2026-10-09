"""Offline archive integration/security checks. All fixture evidence is synthetic."""
import base64
import errno
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from vps_pipeline.archive import ArchiveError, ArchiveConflict, archive_from_html, verify_archive


FIXTURES = Path(__file__).parent / 'fixtures'
SOURCE_URL = 'https://www.nodeseek.com/post-900001-1'
IMAGE_URL = 'https://images.example.com/synthetic-chart.png'
REPORT_URL = 'https://nodequality.com/r/synthetic-only'
# A synthetic one-pixel PNG, encoded in the test instead of checked in as opaque binary.
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        self.page = self.inputs / 'page.html'
        shutil.copyfile(FIXTURES / 'nodeseek_first_post.html', self.page)
        (self.inputs / 'chart.png').write_bytes(PNG)
        shutil.copyfile(FIXTURES / 'synthetic-report.txt', self.inputs / 'report.txt')
        self.output = self.root / 'output'
        self.resources = {IMAGE_URL: 'chart.png', REPORT_URL: 'report.txt'}

    def archive(self, resources=None):
        return archive_from_html(self.page, SOURCE_URL, self.output, resources=resources)

    def edit_manifest(self, path, change):
        data = json.loads(path.read_text(encoding='utf-8'))
        change(data)
        path.write_text(json.dumps(data), encoding='utf-8')

    def test_complete_import_contains_only_first_post_and_discovered_resources(self):
        with patch('socket.getaddrinfo', side_effect=AssertionError('No DNS allowed')):
            manifest_path = self.archive(self.resources | {'https://images.example.com/reply.png': 'does-not-exist'})
            manifest = verify_archive(manifest_path)
        self.assertEqual(manifest['status'], 'ready')
        self.assertEqual(len(manifest['files']), 4)
        self.assertEqual(manifest['capture_metadata']['input_html_sha256'], hashlib.sha256(self.page.read_bytes()).hexdigest())
        self.assertFalse(manifest['capture_metadata']['source_document_stored'])
        self.assertEqual(manifest['capture_metadata']['visual_review'], 'not_performed')
        self.assertNotIn(str(self.root), manifest_path.read_text(encoding='utf-8'))
        for item in manifest['files']:
            if item['role'] != 'image':
                evidence = (manifest_path.parent / item['path']).read_text(encoding='utf-8')
                self.assertNotIn('REPLY_MUST_NOT_BE_ARCHIVED', evidence)
                self.assertNotIn('SIDEBAR_MUST_NOT_BE_ARCHIVED', evidence)
        self.assertEqual([x['kind'] for x in manifest['links']], ['report', 'purchase', 'other'])

    def test_missing_resources_new_snapshot_preserves_original_manifest_and_evidence(self):
        path = self.archive()
        first = verify_archive(path)
        self.assertEqual(first['status'], 'partial')
        self.assertEqual(len(first['failures']), 2)
        original_manifest = path.read_bytes()
        saved = {f['path']: (path.parent / f['path']).read_bytes() for f in first['files']}
        with self.assertRaisesRegex(ArchiveConflict, 'snapshot is immutable'):
            self.archive(self.resources)
        new_path = archive_from_html(self.page, SOURCE_URL, self.root / 'snapshot2', self.resources)
        resumed = verify_archive(new_path)
        self.assertEqual(resumed['status'], 'ready')
        self.assertEqual(path.read_bytes(), original_manifest)
        for relative, contents in saved.items():
            self.assertEqual((path.parent / relative).read_bytes(), contents)
            self.assertEqual((new_path.parent / relative).read_bytes(), contents)

    def test_identical_archive_is_byte_for_byte_idempotent(self):
        path = self.archive(self.resources)
        before = path.read_bytes()
        mtime = path.stat().st_mtime_ns
        self.archive(self.resources)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mtime_ns, mtime)

    def test_changed_first_post_and_changed_resource_do_not_overwrite(self):
        path = self.archive(self.resources)
        before = path.read_bytes()
        self.page.write_text(self.page.read_text(encoding='utf-8').replace('1 vCPU', '2 vCPU'), encoding='utf-8')
        with self.assertRaises(ArchiveConflict):
            self.archive(self.resources)
        self.assertEqual(path.read_bytes(), before)
        shutil.copyfile(FIXTURES / 'nodeseek_first_post.html', self.page)
        (self.inputs / 'report.txt').write_text('Changed synthetic report. ' * 10, encoding='utf-8')
        with self.assertRaises(ArchiveConflict):
            self.archive(self.resources)
        self.assertEqual(path.read_bytes(), before)

    def test_changed_replies_never_rewrite_first_post_evidence(self):
        path = self.archive(self.resources)
        before = path.read_bytes()
        self.page.write_bytes(self.page.read_bytes().replace(b'REPLY_MUST_NOT_BE_ARCHIVED', b'CHANGED_REPLY'))
        self.archive(self.resources)
        self.assertEqual(path.read_bytes(), before)

    def test_first_page_url_is_required(self):
        for url in ('https://www.nodeseek.com/post-900001-2', 'https://www.nodeseek.com/post-0-1',
                    'https://evil.example/post-900001-1', SOURCE_URL + '?page=2',
                    'https://www.nodeseek.com@evil.example/post-900001-1'):
            with self.subTest(url=url), self.assertRaises(ArchiveError):
                archive_from_html(self.page, url, self.output)

    def test_missing_or_ambiguous_marker_rejected_without_fallback(self):
        for fixture in ('nodeseek_no_marker.html', 'nodeseek_duplicate_marker.html'):
            with self.subTest(fixture=fixture), self.assertRaises(ArchiveError):
                archive_from_html(FIXTURES / fixture, SOURCE_URL, self.output)
        self.assertFalse(self.output.exists())

    def test_page_identity_challenge_and_nested_reply_rejected(self):
        original = self.page.read_text(encoding='utf-8')
        cases = [original.replace('post-900001-1', 'post-900002-1'),
                 original.replace('<title>Synthetic review', '<title>Just a moment'),
                 original.replace('<p>SYNTHETIC FIRST POST.', '<div id="2">Nested reply</div><p>SYNTHETIC FIRST POST.')]
        for body in cases:
            self.page.write_text(body, encoding='utf-8')
            with self.subTest(body=body[:60]), self.assertRaises(ArchiveError):
                self.archive()

    def test_paths_outside_import_root_and_traversal_are_not_read(self):
        outside = self.root / 'outside.png'
        outside.write_bytes(PNG)
        path = self.archive({IMAGE_URL: outside, REPORT_URL: '../outside.txt'})
        result = verify_archive(path)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(len(result['files']), 2)
        self.assertNotIn(str(self.root), path.read_text(encoding='utf-8'))

    def test_symlinks_are_not_followed(self):
        link = self.inputs / 'link.png'
        try:
            link.symlink_to(self.inputs / 'chart.png')
        except (OSError, NotImplementedError):
            self.skipTest('Platform/user cannot create symbolic links')
        result = verify_archive(self.archive({IMAGE_URL: 'link.png', REPORT_URL: 'report.txt'}))
        self.assertEqual(result['status'], 'partial')
        self.assertIn('Symbolic', result['failures'][0]['reason'])

    def test_fake_image_and_dynamic_report_become_partial(self):
        (self.inputs / 'chart.png').write_text('<html>Not a PNG</html>', encoding='utf-8')
        (self.inputs / 'report.txt').write_text('Access Denied ' * 20, encoding='utf-8')
        result = verify_archive(self.archive(self.resources))
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(len(result['failures']), 2)
        self.assertEqual(len(result['files']), 2)

    def test_reparse_attribute_guard_is_active_on_all_platforms(self):
        original_lstat = Path.lstat
        chart = self.inputs / 'chart.png'

        class Reparse:
            st_mode = 0o100644
            st_file_attributes = 0x400

        def lstat(path, *args, **kwargs):
            return Reparse() if path == chart else original_lstat(path, *args, **kwargs)

        with patch.object(Path, 'lstat', lstat):
            result = verify_archive(self.archive(self.resources))
        self.assertEqual(result['status'], 'partial')
        self.assertIn('reparse', result['failures'][0]['reason'])

    def test_oversized_asset_becomes_explicit_failure(self):
        with (self.inputs / 'chart.png').open('wb') as stream:
            stream.truncate(20 * 1024 * 1024 + 1)
        result = verify_archive(self.archive(self.resources))
        self.assertEqual(result['status'], 'partial')
        self.assertIn('limit', result['failures'][0]['reason'])

    def test_total_limit_bounds_reads_and_preserves_skipped_resource_failures(self):
        import vps_pipeline.archive as archive_module

        urls = [f'https://images.example.com/synthetic-{i}.png' for i in range(6)]
        self.page.write_text('<div id="0"><article class="post-content">Synthetic bounded evidence.'
                             + ''.join(f'<img src="{url}">' for url in urls)
                             + '</article></div>', encoding='utf-8')
        baseline = verify_archive(self.archive())
        budget = sum(f['bytes'] for f in baseline['files']) + 2 * len(PNG)
        original_read = archive_module._read_bytes
        read_sizes = []

        def measured_read(path, *args, **kwargs):
            data = original_read(path, *args, **kwargs)
            if path == self.inputs / 'chart.png':
                read_sizes.append(len(data))
            return data

        with patch.object(archive_module, 'MAX_TOTAL_BYTES', budget), \
                patch.object(archive_module, '_read_bytes', side_effect=measured_read):
            manifest_path = archive_from_html(self.page, SOURCE_URL, self.root / 'bounded',
                                              {url: 'chart.png' for url in urls})
            manifest = verify_archive(manifest_path)
        self.assertEqual(read_sizes, [len(PNG), len(PNG)])
        self.assertEqual(manifest['status'], 'partial')
        self.assertEqual(len(manifest['failures']), 4)
        self.assertTrue(all('remaining archive total' in f['reason'] for f in manifest['failures']))
        images = [f for f in manifest['files'] if f['role'] == 'image']
        self.assertEqual(len(images), 2)
        self.assertEqual(len({f['id'] for f in images}), 2)
        self.assertEqual(len({f['path'] for f in images}), 1)
        self.assertEqual(sum(f['bytes'] for f in manifest['files']), budget)

    def test_resource_os_errors_never_persist_absolute_paths(self):
        original_lstat = Path.lstat
        chart = self.inputs / 'chart.png'

        def failing_lstat(path, *args, **kwargs):
            if path == chart:
                raise OSError(errno.ENAMETOOLONG, 'File name too long', str(path))
            return original_lstat(path, *args, **kwargs)

        with patch.object(Path, 'lstat', failing_lstat):
            manifest_path = self.archive(self.resources)
        manifest = verify_archive(manifest_path)
        self.assertEqual(manifest['status'], 'partial')
        self.assertEqual(len(manifest['failures']), 1)
        self.assertEqual(manifest['failures'][0]['reason'], f'OSError (errno={errno.ENAMETOOLONG})')
        self.assertNotIn(str(self.root), manifest_path.read_text(encoding='utf-8'))

    def test_corrupt_file_rejected(self):
        path = self.archive(self.resources)
        manifest = verify_archive(path)
        (path.parent / manifest['files'][0]['path']).write_bytes(b'corruption')
        with self.assertRaisesRegex(ArchiveError, 'integrity'):
            verify_archive(path)

    def test_manifest_tampering_rejected(self):
        changes = {
            'path': lambda m: m['files'][0].update(path='../outside.html'),
            'role': lambda m: m['files'][0].update(role='full_page_html'),
            'mime': lambda m: m['files'][2].update(content_type='text/html'),
            'bytes': lambda m: m['files'][0].update(bytes=True),
            'source': lambda m: m['files'][2].update(source_url='https://127.0.0.1/private.png'),
            'identity': lambda m: m.update(post_id='900002'),
            'links': lambda m: m.update(links=[]),
            'status': lambda m: m.update(status='partial'),
        }
        path = self.archive(self.resources)
        original = path.read_bytes()
        for name, change in changes.items():
            path.write_bytes(original)
            self.edit_manifest(path, change)
            with self.subTest(name=name), self.assertRaises(ArchiveError):
                verify_archive(path)

    def test_protocol_directory_is_required(self):
        path = self.archive(self.resources)
        bad = self.root / 'manifest.json'
        shutil.copyfile(path, bad)
        with self.assertRaisesRegex(ArchiveError, 'protocol directory'):
            verify_archive(bad)

    def test_missing_resource_error_omits_host_paths(self):
        result = verify_archive(self.archive({IMAGE_URL: 'missing.png'}))
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(all(str(self.root) not in f['reason'] for f in result['failures']))

    def test_persistent_os_lock_file_does_not_block_later_imports(self):
        path = self.archive(self.resources)
        lock_path = path.parent / '.import.lock'
        self.assertTrue(lock_path.exists())
        self.assertEqual(self.archive(self.resources), path)

    def test_missing_resource_failure_change_requires_new_snapshot(self):
        path = self.archive()
        before = path.read_bytes()
        with self.assertRaisesRegex(ArchiveConflict, 'snapshot is immutable'):
            self.archive({IMAGE_URL: 'missing.png'})
        self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
