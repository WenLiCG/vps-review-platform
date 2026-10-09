import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from vps_pipeline.store import Store

URL = 'https://www.nodeseek.com/post-913633-1'


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.store = Store(self.base / 'private')

    def tearDown(self):
        self.temp.cleanup()

    def test_enqueue_is_persistent_and_idempotent(self):
        one = self.store.enqueue(URL)
        two = Store(self.base / 'private').enqueue(URL)
        self.assertEqual(one['id'], two['id'])
        self.assertEqual(len(self.store.list_jobs()), 1)
        self.assertEqual(self.store.get_job(one['id'])['events'][0]['event'], 'queued')

    def test_only_canonical_public_first_page_allowed(self):
        for bad in ['http://127.0.0.1', URL+'?x=1', URL.replace('-1', '-2'),
                    URL.replace('www.nodeseek.com','www.nodeseek.com.evil.test'),
                    URL.replace('www.', 'user:secret@www.')]:
            with self.subTest(url=bad), self.assertRaises(ValueError):
                self.store.enqueue(bad)

    def test_cancel_and_retry_preserve_history(self):
        job = self.store.enqueue(URL)
        self.store.cancel(job['id'])
        result = self.store.retry(job['id'])
        self.assertEqual(result['status'], 'queued')
        self.assertEqual([x['event'] for x in result['events']], ['queued','cancelled','resumed'])

    def test_lease_recovery_does_not_steal_live_work(self):
        job = self.store.enqueue(URL)
        self.store._claim(job['id'], 'archiving', {'queued'})
        self.assertEqual(self.store.recover()['recovered'], [])
        with self.store._db() as db:
            db.execute('UPDATE jobs SET lease_until=0 WHERE id=?', (job['id'],))
        recovered = Store(self.base/'private').recover()
        self.assertEqual(recovered['recovered'], [job['id']])
        self.assertEqual(self.store.get_job(job['id'])['status'], 'queued')

    def test_restriction_stops_whole_batch_and_is_not_retried(self):
        from vps_pipeline.network import NetworkBlocked
        a = self.store.enqueue(URL)
        b = self.store.enqueue(URL.replace('913633','913634'))
        with patch('vps_pipeline.network.fetch_first_post', side_effect=NetworkBlocked('HTTP 403')) as fetch:
            result = self.store.collect(2)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(result[0]['status'], 'blocked')
        self.assertEqual(self.store.get_job(b['id'])['status'], 'queued')
        with self.assertRaises(ValueError):
            self.store.retry(a['id'])
        self.store.cancel(a['id'])
        with self.assertRaises(ValueError):
            self.store.retry(a['id'])
        # A bad offline import also cannot erase the permanent network stop.
        with self.assertRaises(Exception):
            self.store.import_html(a['id'], self.base/'missing.html')
        with self.assertRaises(ValueError):
            self.store.retry(a['id'])

    def test_invalid_ids_do_not_form_paths_or_sql(self):
        for value in ['../x', "' OR 1=1 --", 'a'*33]:
            with self.assertRaises(ValueError):
                self.store.get_job(value)

    def test_failed_import_keeps_reason(self):
        job = self.store.enqueue(URL)
        with self.assertRaises(Exception):
            self.store.import_html(job['id'], self.base/'missing.html')
        result = self.store.get_job(job['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['last_error'])

    def test_bounded_limit(self):
        for n in [0, -1, 101, True, 1.5]:
            with self.assertRaises(ValueError):
                self.store.collect(n)

    def test_identical_submission_committed_during_claim_window_is_idempotent(self):
        from vps_pipeline.analysis import _load_review

        page = self.base / 'synthetic.html'
        page.write_text('<div id="0"><article class="post-content">Synthetic test evidence only.</article></div>',
                        encoding='utf-8')
        job = self.store.enqueue(URL)
        self.store.import_html(job['id'], page)
        manifest_path = next((self.base / 'private' / 'archives').rglob('manifest.json'))
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        analysis = _load_review().draft(manifest)
        analysis['ai_review'] = {'completed': True, 'agent': 'SYNTHETIC TEST DECLARATION ONLY',
                                 'reviewed_files': [f['id'] for f in manifest['files']]}
        analysis['summary'] = 'Synthetic protocol test, no real review.'
        envelope = {
            'schema_version': 'vps-analysis-envelope/1',
            'archive_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            'analysis': analysis, 'observations': [],
            'review_log': [{'file_id': f['id'], 'sha256': f['sha256'],
                            'reviewer': 'SYNTHETIC TEST DECLARATION ONLY',
                            'reviewed_at': '2026-10-09T00:00:00+00:00', 'coverage': 'full',
                            'regions': ['Synthetic test fixture'], 'issues': []}
                           for f in manifest['files']],
        }
        entered, resume = threading.Event(), threading.Event()
        original_claim = self.store._claim
        outcome = {}

        def paused_claim(*args, **kwargs):
            if threading.current_thread().name == 'paused-submitter':
                entered.set()
                if not resume.wait(10):
                    raise TimeoutError('Test submission was not resumed')
            return original_claim(*args, **kwargs)

        def submit_in_thread():
            try:
                outcome['result'] = self.store.submit(job['id'], envelope)
            except Exception as exc:
                outcome['error'] = exc

        with patch.object(self.store, '_claim', side_effect=paused_claim):
            worker = threading.Thread(target=submit_in_thread, name='paused-submitter')
            worker.start()
            try:
                self.assertTrue(entered.wait(10))
                first = self.store.submit(job['id'], envelope)
            finally:
                resume.set()
                worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertNotIn('error', outcome)
        self.assertFalse(first['duplicate'])
        self.assertTrue(outcome['result']['duplicate'])
        self.assertEqual(outcome['result']['version'], first['version'])
        self.assertEqual(self.store.get_job(job['id'])['status'], 'accepted')
        self.assertIsNone(self.store.get_job(job['id'])['last_error'])
        with self.store._db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM analyses').fetchone()[0], 1)
            row = db.execute('SELECT lease_token,lease_until FROM jobs WHERE id=?', (job['id'],)).fetchone()
            self.assertIsNone(row['lease_token'])
            self.assertIsNone(row['lease_until'])


if __name__ == '__main__':
    unittest.main()
