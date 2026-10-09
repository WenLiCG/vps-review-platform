"""Byte-preserving offline ingress tests. Review declarations are synthetic."""
import base64
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from vps_pipeline import archive as ar
from vps_pipeline import archive_import as ingress
from vps_pipeline.cli import main
from vps_pipeline.store import Store


URL = 'https://www.nodeseek.com/post-900001-1'
IMAGE = 'https://images.example.com/synthetic.png'
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
PAGE = f'''<html><head><title>Synthetic archive import test</title></head><body>
<div id="0"><article class="post-content"><p>SYNTHETIC TEST EVIDENCE ONLY.
No actual VPS performance or visual reading is asserted by this fixture.</p>
<img src="{IMAGE}"></article></div>
<div id="1"><article class="post-content">REPLY MUST NOT BE COPIED</article></div>
</body></html>'''


class ArchiveImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        page = self.root / 'page.html'
        page.write_text(PAGE, encoding='utf-8')
        (self.root / 'image.png').write_bytes(PNG)
        self.source = ar.archive_from_html(page, URL, self.root / 'source', {IMAGE: 'image.png'})
        self.store = Store(self.root / 'private')
        self.job = self.store.enqueue(URL)['id']

    def manifest(self):
        return json.loads(self.source.read_text(encoding='utf-8'))

    def edit_manifest(self, update):
        manifest = self.manifest()
        update(manifest)
        self.source.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')

    def row(self):
        with self.store._db() as db:
            return dict(self.store._row(db, self.job))

    def snapshots(self):
        return sorted((self.store.root / 'archives').rglob('manifest.json'))

    def assert_no_partial(self):
        self.assertEqual(list((self.store.root / 'tmp').iterdir()), [])
        for path in self.snapshots():
            ar.verify_archive(path)

    def accept_synthetic(self):
        from vps_pipeline.analysis import _load_review
        row = self.row()
        manifest = ar.verify_archive(self.store.root / row['archive_rel'])
        analysis = _load_review().draft(manifest)
        analysis['ai_review'] = {'completed': True, 'agent': 'SYNTHETIC TEST DECLARATION ONLY',
                                 'reviewed_files': [f['id'] for f in manifest['files']]}
        analysis['summary'] = 'Synthetic protocol test. No real AI or visual review.'
        envelope = {'schema_version': 'vps-analysis-envelope/1',
                    'archive_sha256': row['archive_sha256'], 'analysis': analysis,
                    'observations': [], 'review_log': [
                        {'file_id': f['id'], 'sha256': f['sha256'],
                         'reviewer': 'SYNTHETIC TEST DECLARATION ONLY',
                         'reviewed_at': '2026-10-09T00:00:00+00:00', 'coverage': 'full',
                         'regions': ['Synthetic protocol fixture'], 'issues': []}
                        for f in manifest['files']]}
        return self.store.submit(self.job, envelope)

    def test_exact_bytes_metadata_and_source_are_preserved_without_capture(self):
        self.edit_manifest(lambda m: m.update(capture_method='browser_import',
                           captured_at='2025-01-02T03:04:05+00:00',
                           capture_note='Original saved first-post declaration, unchanged.'))
        before = {p: p.read_bytes() for p in self.source.parent.iterdir() if p.is_file()}
        with (patch('socket.getaddrinfo', side_effect=AssertionError('No network')),
              patch.object(ar, 'archive_from_html', side_effect=AssertionError('No HTML wrapper')),
              patch('vps_pipeline.legacy.verify_legacy', side_effect=AssertionError('No legacy exception'))):
            result = self.store.import_archive(self.job, self.source)
        self.assertEqual(result['status'], 'awaiting_analysis')
        self.assertFalse(result['duplicate'])
        self.assertEqual(result['archive_sha256'], hashlib.sha256(before[self.source]).hexdigest())
        destination = self.store.root / self.row()['archive_rel']
        self.assertEqual(destination.read_bytes(), before[self.source])
        for record in self.manifest()['files']:
            self.assertEqual((destination.parent / record['path']).read_bytes(),
                             before[self.source.parent / record['path']])
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertFalse((destination.parent / '.import.lock').exists())
        with self.store._db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM analyses').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM legacy_records').fetchone()[0], 0)
        self.assert_no_partial()

    def test_import_can_export_fresh_pending_work_packet(self):
        self.store.import_archive(self.job, self.source)
        result = self.store.export_task(self.job, self.root / 'work.zip')
        self.assertEqual(result['status'], 'needs_ai')
        with zipfile.ZipFile(self.root / 'work.zip') as archive:
            self.assertEqual(archive.read('assets/900001/manifest.json'), self.source.read_bytes())
            envelope = json.loads(archive.read('envelope.json'))
        self.assertEqual(envelope['archive_sha256'], self.row()['archive_sha256'])
        self.assertFalse(envelope['analysis']['ai_review']['completed'])
        self.assertEqual(envelope['review_log'], [])

    def test_identical_import_makes_no_files_and_keeps_accepted_state(self):
        self.store.import_archive(self.job, self.source)
        self.accept_synthetic()
        row = self.row()
        before = {p: p.stat().st_mtime_ns for p in (self.store.root / 'archives').rglob('*')}
        with patch.object(Path, 'mkdir', side_effect=AssertionError('Duplicate must not create paths')):
            result = self.store.import_archive(self.job, self.source)
        self.assertTrue(result['duplicate'])
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['accepted_version'], 1)
        self.assertEqual(self.row()['archive_rel'], row['archive_rel'])
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in (self.store.root / 'archives').rglob('*')})
        self.assert_no_partial()

    def test_changed_manifest_preserves_old_snapshots_and_accepted_versions(self):
        self.store.import_archive(self.job, self.source)
        self.accept_synthetic()
        old = self.row()
        old_path = self.store.root / old['archive_rel']
        old_bytes = old_path.read_bytes()
        # Even metadata-only changes matter because the envelope binds exact bytes.
        self.edit_manifest(lambda m: m.update(capture_note=m['capture_note'] + ' Original metadata revision.'))
        result = self.store.import_archive(self.job, self.source)
        self.assertFalse(result['duplicate'])
        self.assertEqual(result['status'], 'awaiting_analysis')
        self.assertEqual(result['accepted_version'], 1)
        self.assertNotEqual(result['archive_sha256'], old['archive_sha256'])
        self.assertEqual(old_path.read_bytes(), old_bytes)
        self.assertEqual(len(self.snapshots()), 2)
        self.assertEqual(self.accept_synthetic()['version'], 2)
        reopened = Store(self.store.root)
        self.assertEqual(reopened.get_job(self.job)['accepted_version'], 2)
        with reopened._db() as db:
            versions = db.execute('SELECT version,archive_rel FROM analyses ORDER BY version').fetchall()
        self.assertEqual([x['version'] for x in versions], [1, 2])
        self.assertEqual(versions[0]['archive_rel'], old['archive_rel'])

    def test_different_post_identity_is_rejected_without_a_snapshot(self):
        other = self.store.enqueue(URL.replace('900001', '900002'))['id']
        with self.assertRaisesRegex(ValueError, 'identity does not match'):
            self.store.import_archive(other, self.source)
        self.assertEqual(self.store.get_job(other)['status'], 'failed')
        self.assertEqual(self.snapshots(), [])
        self.assert_no_partial()

    def test_tampered_hash_or_declared_mime_is_rejected(self):
        before = self.source.read_bytes()
        for change in [lambda m: m['files'][0].update(sha256='0' * 64),
                       lambda m: m['files'][-1].update(content_type='image/jpeg')]:
            with self.subTest(change=change):
                self.source.write_bytes(before)
                self.edit_manifest(change)
                with self.assertRaises(ValueError):
                    self.store.import_archive(self.job, self.source)
                self.assertEqual(self.row()['status'], 'failed')
                self.assertEqual(self.snapshots(), [])
                self.assert_no_partial()

    def test_unsafe_paths_and_archive_evidence_are_rejected(self):
        original = self.source.read_bytes()
        for path in ['../outside.txt', '/etc/passwd', 'C:/outside.txt', r'a\b.txt',
                     'a/./b', 'a//b', 'manifest.json', 'MANIFEST.JSON', 'con.txt',
                     'data.zip', 'a\x00b', 'data.txt ', 'data.txt.']:
            with self.subTest(path=path):
                self.source.write_bytes(original)
                self.edit_manifest(lambda m: m['files'][0].update(path=path))
                with self.assertRaises(ValueError):
                    self.store.import_archive(self.job, self.source)
                self.assertEqual(self.snapshots(), [])
        self.assert_no_partial()

    def test_zip_or_wrong_protocol_layout_is_rejected(self):
        zipped = self.root / 'untrusted.zip'
        zipped.write_bytes(b'PK\x03\x04' + b'X' * 100)
        outside = self.root / 'manifest.json'
        outside.write_bytes(self.source.read_bytes())
        for path in [zipped, outside, self.source.parent]:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'Expected assets'):
                self.store.import_archive(self.job, path)
        self.assertEqual(self.snapshots(), [])

    def test_symlinked_manifest_ancestor_and_evidence_are_rejected(self):
        link = self.root / 'linked'
        try:
            link.symlink_to(self.source.parents[2], target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('Platform/user cannot create symbolic links')
        with self.assertRaisesRegex(ValueError, '[Ss]ymlink|[Ss]ymbolic'):
            self.store.import_archive(self.job, link / 'assets/900001/manifest.json')
        record = self.manifest()['files'][0]
        evidence = self.source.parent / record['path']
        outside = self.root / 'outside.html'
        evidence.rename(outside)
        evidence.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, '[Ss]ymlink|[Ss]ymbolic'):
            self.store.import_archive(self.job, self.source)
        self.assertEqual(self.snapshots(), [])

    def test_total_budget_is_checked_before_any_evidence_read(self):
        total = sum(f['bytes'] for f in self.manifest()['files'])
        original = ar._read_bytes
        reads = []
        def tracked(path, limit=ar.MAX_BYTES):
            reads.append(Path(path))
            return original(path, limit)
        with patch.object(ar, 'MAX_TOTAL_BYTES', total - 1), patch.object(ar, '_read_bytes', side_effect=tracked):
            with self.assertRaisesRegex(ValueError, 'total evidence size limit'):
                self.store.import_archive(self.job, self.source)
        self.assertEqual(reads, [self.source])
        self.assert_no_partial()

    def test_copy_reads_are_bounded_by_expected_size_and_remaining_budget(self):
        original = ar._read_bytes
        sizes = {self.source.parent / f['path']: f['bytes'] for f in self.manifest()['files']}
        copy_reads = []
        def tracked(path, limit=ar.MAX_BYTES):
            if Path(path) in sizes and list((self.store.root / 'tmp').iterdir()):
                copy_reads.append((sizes[Path(path)], limit))
            return original(path, limit)
        with patch.object(ar, '_read_bytes', side_effect=tracked):
            self.store.import_archive(self.job, self.source)
        self.assertEqual(len(copy_reads), len(sizes))
        self.assertTrue(all(size == limit for size, limit in copy_reads))

    def test_copy_failure_preserves_pending_and_accepted_archive(self):
        self.store.import_archive(self.job, self.source)
        for accepted in [False, True]:
            if accepted:
                self.accept_synthetic()
            row = self.row()
            self.edit_manifest(lambda m: m.update(capture_note=m['capture_note'] + ' Revision.'))
            original = ingress._write_new
            def interrupted(path, payload):
                if path.name != 'manifest.json':
                    raise OSError('Synthetic interrupted copy')
                return original(path, payload)
            with patch.object(ingress, '_write_new', side_effect=interrupted):
                with self.assertRaisesRegex(OSError, 'Synthetic interrupted'):
                    self.store.import_archive(self.job, self.source)
            after = self.row()
            self.assertEqual(after['status'], row['status'])
            self.assertEqual(after['archive_rel'], row['archive_rel'])
            self.assertEqual(after['archive_sha256'], row['archive_sha256'])
            self.assertIsNone(after['lease_token'])
            self.assertEqual(len(self.snapshots()), 1)
            self.assert_no_partial()

    def test_first_copy_failure_leaves_failed_job_without_archive(self):
        with patch.object(ingress, '_write_new', side_effect=OSError('Synthetic copy failure')):
            with self.assertRaises(OSError):
                self.store.import_archive(self.job, self.source)
        self.assertEqual(self.row()['status'], 'failed')
        self.assertIsNone(self.row()['archive_rel'])
        self.assert_no_partial()

    def test_changed_source_and_tampered_copy_fail_before_commit(self):
        original = ingress._write_new
        original_source = self.source.read_bytes()
        def mutate_source(path, data):
            original(path, data)
            if path.name == 'manifest.json':
                self.source.write_bytes(original_source + b' ')
        with patch.object(ingress, '_write_new', side_effect=mutate_source):
            with self.assertRaisesRegex(ValueError, 'manifest changed during import'):
                self.store.import_archive(self.job, self.source)
        self.source.write_bytes(original_source)
        def corrupt_copy(path, data):
            original(path, data if path.name == 'manifest.json' else b'TAMPER')
        with patch.object(ingress, '_write_new', side_effect=corrupt_copy):
            with self.assertRaises(ValueError):
                self.store.import_archive(self.job, self.source)
        self.assertIsNone(self.row()['archive_rel'])
        self.assertEqual(self.snapshots(), [])
        self.assert_no_partial()

    def test_changed_or_expired_lease_cannot_commit(self):
        original = ingress._write_new
        for lost in [False, True]:
            with self.store._db() as db:
                db.execute("UPDATE jobs SET status='queued',lease_token=NULL,lease_until=NULL WHERE id=?", (self.job,))
            def lose_lease(path, data):
                original(path, data)
                if path.name == 'manifest.json':
                    with self.store._db() as db:
                        if lost:
                            db.execute("UPDATE jobs SET lease_token='new-owner',status='archiving' WHERE id=?", (self.job,))
                        else:
                            db.execute('UPDATE jobs SET lease_until=0 WHERE id=?', (self.job,))
            with patch.object(ingress, '_write_new', side_effect=lose_lease):
                with self.assertRaisesRegex(ValueError, 'lease changed or expired'):
                    self.store.import_archive(self.job, self.source)
            self.assertIsNone(self.row()['archive_rel'])
            if lost:
                self.assertEqual(self.row()['lease_token'], 'new-owner')
                self.assertEqual(self.row()['status'], 'archiving')
            else:
                self.assertEqual(self.row()['status'], 'failed')
            self.assertEqual(self.snapshots(), [])
            self.assert_no_partial()

    def test_sql_failure_leaves_only_complete_orphan_and_previous_ledger(self):
        self.store.import_archive(self.job, self.source)
        self.accept_synthetic()
        before = self.row()
        self.edit_manifest(lambda m: m.update(capture_note=m['capture_note'] + ' Revision.'))
        original = self.store._event
        def fail_commit(db, job, event, detail=None):
            if event == 'awaiting_analysis':
                raise OSError('Synthetic transaction failure')
            return original(db, job, event, detail)
        with patch.object(self.store, '_event', side_effect=fail_commit):
            with self.assertRaisesRegex(OSError, 'transaction failure'):
                self.store.import_archive(self.job, self.source)
        self.assertEqual(self.row()['archive_rel'], before['archive_rel'])
        self.assertEqual(self.row()['status'], 'accepted')
        self.assertEqual(len(self.snapshots()), 2)
        self.assert_no_partial()

    def test_network_blocked_flag_survives_success_and_failure(self):
        with self.store._db() as db:
            db.execute("UPDATE jobs SET status='blocked',network_blocked=1 WHERE id=?", (self.job,))
        result = self.store.import_archive(self.job, self.source)
        self.assertEqual(result['network_blocked'], 1)
        self.assertEqual(result['status'], 'awaiting_analysis')
        self.source.write_bytes(b'invalid')
        with self.assertRaises(ValueError):
            self.store.import_archive(self.job, self.source)
        self.assertEqual(self.row()['network_blocked'], 1)
        self.assertEqual(self.row()['status'], 'awaiting_analysis')

    def test_dedup_reverifies_private_evidence(self):
        self.store.import_archive(self.job, self.source)
        self.accept_synthetic()
        before = self.row()
        saved = self.store.root / before['archive_rel']
        record = self.manifest()['files'][0]
        (saved.parent / record['path']).write_bytes(b'TAMPER')
        with self.assertRaises(ValueError):
            self.store.import_archive(self.job, self.source)
        self.assertEqual(self.row()['status'], 'accepted')
        self.assertEqual(self.row()['archive_rel'], before['archive_rel'])
        self.assertEqual(len(self.snapshots()), 1)

    def test_unowned_staging_is_never_removed(self):
        original = self.store._claim
        sentinel = None
        def create_collision(*args, **kwargs):
            nonlocal sentinel
            row, token = original(*args, **kwargs)
            stage = self.store.root / 'tmp' / ('archive-' + token)
            stage.mkdir()
            sentinel = stage / 'keep.txt'
            sentinel.write_text('Not owned by this copy operation')
            return row, token
        with patch.object(self.store, '_claim', side_effect=create_collision):
            with self.assertRaises(FileExistsError):
                self.store.import_archive(self.job, self.source)
        self.assertEqual(sentinel.read_text(), 'Not owned by this copy operation')

    @unittest.skipUnless(os.name == 'posix', 'POSIX owner-only mode test')
    def test_snapshot_directory_is_private(self):
        self.store.import_archive(self.job, self.source)
        manifest = self.store.root / self.row()['archive_rel']
        self.assertEqual(manifest.parents[2].stat().st_mode & 0o077, 0)

    def test_cli_ingest_archive_is_explicit_and_has_no_network_switch(self):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main(['--data', str(self.store.root), 'ingest-archive', self.job, str(self.source)])
        self.assertEqual(status, 0, errors.getvalue())
        self.assertEqual(json.loads(output.getvalue())['status'], 'awaiting_analysis')
        self.assertEqual(self.row()['archive_sha256'], hashlib.sha256(self.source.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
