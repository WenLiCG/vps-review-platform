"""End-to-end offline integration. Review declarations are synthetic tests only."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from vps_pipeline.store import Store

URL = 'https://www.nodeseek.com/post-913633-1'
PAGE = '''<html><head><title>Synthetic integration fixture</title>
<link rel="canonical" href="https://www.nodeseek.com/post-913633-1"></head><body>
<div id="0"><article class="post-content"><p>SYNTHETIC TEST EVIDENCE ONLY.
The quoted configuration is 2 vCPU and measured memory 1024 MiB.
No actual VPS performance or AI visual review is asserted by this fixture.</p></article></div>
<div id="1"><article class="post-content">REPLY NEVER ARCHIVE ME</article></div>
</body></html>'''


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.html = self.base/'fixture.html'
        self.html.write_text(PAGE, encoding='utf-8')
        self.store = Store(self.base/'private')
        self.job = self.store.enqueue(URL)
        self.store.import_html(self.job['id'], self.html)

    def tearDown(self):
        self.temp.cleanup()

    def task(self, name='work.zip'):
        path = self.base/name
        self.store.export_task(self.job['id'], path)
        with zipfile.ZipFile(path) as z:
            envelope = json.loads(z.read('envelope.json'))
            manifest = json.loads(z.read('assets/913633/manifest.json'))
        return envelope, manifest

    def synthetic_submission(self, name='work.zip'):
        envelope, m = self.task(name)
        envelope['test_fixture'] = True
        envelope['analysis']['ai_review'] = {
            'completed': True, 'agent': 'SYNTHETIC TEST DECLARATION ONLY',
            'reviewed_files': [f['id'] for f in m['files']]}
        envelope['analysis']['summary'] = 'Synthetic protocol validation only; no real AI review.'
        envelope['review_log'] = [
            {'file_id': f['id'], 'sha256': f['sha256'], 'reviewer': 'SYNTHETIC TEST DECLARATION ONLY',
             'reviewed_at': '2026-10-09T00:00:00+00:00', 'coverage': 'full',
             'regions': ['Synthetic fixture, not a real reading claim'], 'issues': []}
            for f in m['files']]
        return envelope, m

    def test_queue_archive_pending_package_validate_export(self):
        state = self.store.get_job(self.job['id'])
        self.assertEqual(state['status'], 'awaiting_analysis')
        pending, _ = self.task('pending.zip')
        self.assertFalse(pending['analysis']['ai_review']['completed'])
        with self.assertRaises(ValueError):
            self.store.submit(self.job['id'], pending)
        self.assertEqual(self.store.get_job(self.job['id'])['status'], 'awaiting_analysis')
        envelope, m = self.synthetic_submission()
        accepted = self.store.submit(self.job['id'], envelope)
        self.assertEqual(accepted['version'], 1)
        self.assertTrue(self.store.submit(self.job['id'], envelope)['duplicate'])
        self.store.export_public(self.base/'public')
        public = json.loads((self.base/'public'/'reviews.json').read_text(encoding='utf-8'))
        self.assertEqual(public['v5_ui_integration'], 'use_safe_catalog_export')
        self.assertEqual(len(public['records']), 1)
        r = public['records'][0]
        self.assertEqual(len(r['analysis']['facts']), 61)
        self.assertTrue(all(f['value'] is None for f in r['analysis']['facts'].values()))
        self.assertFalse(r['validation']['ai_invoked'])
        self.assertNotIn('pipeline.sqlite3', [p.name for p in (self.base/'public').rglob('*')])
        for f in r['public_evidence']:
            data = (self.base/'public'/f['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), f['sha256'])
            self.assertNotIn(b'REPLY NEVER ARCHIVE ME', data)

    def test_versions_and_failed_revisions_keep_accepted_result(self):
        e, _ = self.synthetic_submission()
        self.store.submit(self.job['id'], e)
        invalid = copy.deepcopy(e)
        invalid['analysis']['ai_review']['completed'] = False
        with self.assertRaises(ValueError):
            self.store.submit(self.job['id'], invalid)
        self.assertEqual(self.store.get_job(self.job['id'])['status'], 'accepted')
        e['analysis']['summary'] += ' Revised synthetic summary.'
        self.assertEqual(self.store.submit(self.job['id'], e)['version'], 2)
        with self.store._db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM analyses').fetchone()[0], 2)

    def test_new_snapshot_does_not_destroy_old_accepted_evidence(self):
        old, _ = self.synthetic_submission()
        self.store.submit(self.job['id'], old)
        before = {str(p):p.read_bytes() for p in (self.base/'private'/'archives').rglob('manifest.json')}
        self.html.write_text(PAGE.replace('2 vCPU','4 vCPU'), encoding='utf-8')
        self.store.import_html(self.job['id'], self.html)
        self.assertEqual(self.store.get_job(self.job['id'])['status'], 'awaiting_analysis')
        for p, data in before.items():
            self.assertEqual(Path(p).read_bytes(), data)
        with self.assertRaises(ValueError):
            self.store.submit(self.job['id'], old)
        self.store.export_public(self.base/'public-old')
        public = json.loads((self.base/'public-old'/'reviews.json').read_text(encoding='utf-8'))
        self.assertEqual(public['records'][0]['archive_sha256'], old['archive_sha256'])
        new, _ = self.synthetic_submission('new.zip')
        self.assertNotEqual(new['archive_sha256'], old['archive_sha256'])
        self.assertEqual(self.store.submit(self.job['id'], new)['version'], 2)

    def test_identical_reingest_keeps_current_accepted_snapshot(self):
        envelope, _ = self.synthetic_submission()
        self.store.submit(self.job['id'], envelope)
        old_hash = self.store.get_job(self.job['id'])['archive_sha256']
        self.store.import_html(self.job['id'], self.html)
        state = self.store.get_job(self.job['id'])
        self.assertEqual(state['status'], 'accepted')
        self.assertEqual(state['archive_sha256'], old_hash)
        self.assertEqual(len(list((self.base/'private'/'archives').rglob('manifest.json'))), 1)

    def test_tamper_rejected_on_duplicate_submission_and_public_export(self):
        envelope, _ = self.synthetic_submission()
        self.store.submit(self.job['id'], envelope)
        with self.store._db() as db:
            row = dict(db.execute('SELECT * FROM jobs').fetchone())
        manifest_path = self.base/'private'/row['archive_rel']
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        f = next(f for f in manifest['files'] if f['role']=='first_post_text')
        (manifest_path.parent/f['path']).write_bytes(b'tamper')
        with self.assertRaises(ValueError):
            self.store.submit(self.job['id'], envelope)
        with self.assertRaises(ValueError):
            self.store.export_public(self.base/'public-bad')

    def test_interrupted_validation_retains_current_accepted_snapshot(self):
        envelope, _ = self.synthetic_submission()
        self.store.submit(self.job['id'], envelope)
        self.store._claim(self.job['id'], 'validating', {'accepted'})
        with self.store._db() as db:
            db.execute('UPDATE jobs SET lease_until=0 WHERE id=?', (self.job['id'],))
        self.store.recover()
        self.assertEqual(self.store.get_job(self.job['id'])['status'], 'accepted')


if __name__ == '__main__':
    unittest.main()
