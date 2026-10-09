import concurrent.futures
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from legacy_helpers import synthetic_legacy
from vps_pipeline.store import Store
from vps_pipeline.server import create_server


class LegacyStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.manifest,self.analysis=synthetic_legacy(self.base/'source')
        self.store=Store(self.base/'private')

    def import_record(self):
        return self.store.import_legacy(self.manifest)

    def test_import_retains_original_bytes_and_historical_status(self):
        old={p.name:p.read_bytes() for p in self.manifest.parent.iterdir() if p.is_file() and p.name!='.import.lock'}
        result=self.import_record(); record=self.store.get_legacy(result['id'])
        self.assertEqual(result['status'],'legacy_imported');self.assertFalse(result['new_review_performed'])
        self.assertEqual(self.store.list_jobs(),[])
        with self.store._db() as db:self.assertEqual(db.execute('SELECT count(*) FROM analyses').fetchone()[0],0)
        self.assertEqual(record['analysis'],json.loads(self.analysis.read_text()))
        self.assertNotIn('review_log',record['analysis']);self.assertNotIn('observations',record['analysis'])
        self.assertFalse(record['validation']['new_review_performed'])
        with self.store._db() as db:relative=db.execute('SELECT archive_rel FROM legacy_records').fetchone()[0]
        copied=(self.store.root/relative).parent
        for name,data in old.items():
            self.assertEqual((copied/name).read_bytes(),data)
            self.assertEqual((self.manifest.parent/name).read_bytes(),data)

    def test_duplicate_import_is_idempotent(self):
        first=self.import_record();before=self.store.list_legacy()
        second=self.import_record()
        self.assertEqual(first['id'],second['id']);self.assertTrue(second['duplicate'])
        self.assertFalse(first['duplicate']);self.assertEqual(before,self.store.list_legacy())
        self.assertEqual(list((self.store.root/'tmp').iterdir()),[])

    @unittest.skipUnless(os.name == 'posix', 'POSIX owner-only mode test')
    def test_private_legacy_snapshot_is_owner_only(self):
        result=self.import_record()
        snapshot=self.store.root/'legacy_archives'/result['id']
        self.assertEqual(snapshot.stat().st_mode & 0o077,0)

    def test_changed_historical_analysis_creates_separate_immutable_record(self):
        first=self.import_record();old=self.store.get_legacy(first['id'])
        analysis=json.loads(self.analysis.read_text());analysis['summary']+=' Historical revision.'
        self.analysis.write_text(json.dumps(analysis))
        second=self.import_record()
        self.assertNotEqual(first['id'],second['id']);self.assertEqual(len(self.store.list_legacy()),2)
        self.assertEqual(self.store.get_legacy(first['id'])['analysis'],old['analysis'])

    def test_concurrent_identical_imports_are_atomic_and_idempotent(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.import_record(),range(8)))
        self.assertEqual(len({r['id'] for r in results}),1)
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        self.assertEqual(len(self.store.list_legacy()),1)
        self.assertEqual(list((self.store.root/'tmp').iterdir()),[])
        self.assertEqual(self.store.list_jobs(),[])

    def test_interrupted_staging_is_not_visible(self):
        original_write=Path.open
        def interrupted(path,*args,**kwargs):
            if path.name=='analysis.json' and 'legacy-' in str(path.parent) and args and args[0]=='xb':
                raise OSError('Synthetic interrupted copy')
            return original_write(path,*args,**kwargs)
        with patch.object(Path,'open',interrupted),self.assertRaisesRegex(OSError,'Synthetic interrupted'):
            self.import_record()
        self.assertEqual(self.store.list_legacy(),[])
        self.assertEqual(list((self.store.root/'tmp').iterdir()),[])
        self.assertEqual(self.import_record()['status'],'legacy_imported')

    def test_fully_copied_orphan_is_reverified_before_recovery(self):
        from vps_pipeline.legacy import verify_legacy
        verified=verify_legacy(self.manifest)
        target=self.store.root/'legacy_archives'/verified['bundle_sha256']/'assets'/verified['post_id']
        shutil.copytree(self.manifest.parent,target)
        result=self.import_record()
        self.assertFalse(result['duplicate']);self.assertEqual(len(self.store.list_legacy()),1)

    def test_tampered_private_snapshot_blocks_read_and_export(self):
        result=self.import_record()
        with self.store._db() as db:relative=db.execute('SELECT archive_rel FROM legacy_records').fetchone()[0]
        parent=(self.store.root/relative).parent
        record=json.loads((parent/'manifest.json').read_text())['files'][0]
        (parent/record['path']).write_bytes(b'tampered')
        with self.assertRaises(ValueError):self.store.get_legacy(result['id'])
        with self.assertRaises(ValueError):self.store.export_public(self.base/'public')
        self.assertFalse((self.base/'public/reviews.json').exists())

    def test_legacy_public_projection_does_not_copy_private_evidence(self):
        self.import_record();output=self.base/'public'
        result=self.store.export_public(output);payload=json.loads((output/'reviews.json').read_text())
        self.assertEqual(result['records'],0);self.assertEqual(result['legacy_records'],1)
        self.assertEqual(payload['records'],[]);self.assertEqual(len(payload['legacy_records']),1)
        record=payload['legacy_records'][0]
        self.assertEqual(record['status'],'legacy_imported');self.assertFalse(record['new_review_performed'])
        self.assertFalse((output/'evidence').exists())
        self.assertEqual(len(record['facts']),61)
        self.assertNotIn('SYNTHETIC LEGACY TEST',(output/'reviews.json').read_text())
        self.assertNotIn(str(self.base),(output/'reviews.json').read_text())

    def test_invalid_ids_and_zip_input_are_rejected(self):
        for identity in ['../manifest.json','x'*64,"' OR 1=1",'0'*63]:
            with self.subTest(identity=identity),self.assertRaises(ValueError):self.store.get_legacy(identity)
        archive=self.base/'untrusted.zip';archive.write_bytes(b'PK\x03\x04'+b'X'*100)
        with self.assertRaises(ValueError):self.store.import_legacy(archive)
        self.assertEqual(self.store.list_legacy(),[])


class LegacyHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.manifest,_=synthetic_legacy(self.base/'source')
        self.store=Store(self.base/'private');self.record=self.store.import_legacy(self.manifest)
        self.server=create_server(self.store,self.store.root,port=0)
        self.worker=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':0.01},daemon=True)
        self.worker.start();self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown();self.server.server_close();self.worker.join(2)

    def request(self,method,path,token=True):
        c=HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=5)
        try:
            c.request(method,path,headers={'X-VPS-Token':self.server.session_token} if token else {})
            r=c.getresponse();return r.status,r.read()
        finally:c.close()

    def test_historical_list_detail_require_same_management_auth(self):
        self.assertEqual(self.request('GET','/api/legacy',False)[0],401)
        status,body=self.request('GET','/api/legacy');self.assertEqual(status,200)
        self.assertEqual(json.loads(body)[0]['status'],'legacy_imported')
        status,body=self.request('GET','/api/legacy/'+self.record['id']);self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['analysis']['schema_version'],'vps-analysis/1')
        self.assertEqual(json.loads(self.request('GET','/api/jobs')[1]),[])

    def test_historical_api_is_read_only_and_cannot_serve_evidence(self):
        for method in ['POST','PUT','PATCH','DELETE']:
            with self.subTest(method=method):
                self.assertEqual(self.request(method,'/api/legacy')[0],405)
                self.assertEqual(self.request(method,'/api/legacy/'+self.record['id'])[0],405)
        self.assertEqual(self.request('GET','/api/legacy/'+self.record['id']+'/evidence')[0],404)
        self.assertEqual(self.request('GET','/api/legacy/../../analysis.json')[0],404)

    def test_management_page_contains_read_only_section_without_original_html(self):
        status,body=self.request('GET','/',False);self.assertEqual(status,200)
        self.assertIn('历史分析（只读'.encode(),body)
        self.assertIn(b'legacy_imported',body)
        self.assertNotIn(b'SYNTHETIC LEGACY TEST',body)
        self.assertIn(b'textContent=JSON.stringify',body)
