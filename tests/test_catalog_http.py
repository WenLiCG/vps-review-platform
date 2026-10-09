from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest

from vps_pipeline.catalog import build_snapshot,export_catalog,website_root,BASELINE_JSON
from vps_pipeline.server import create_server
from vps_pipeline.store import Store


class CatalogHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=Store(self.root/'private')
        self.server=create_server(self.store,self.store.root,port=0)
        self.worker=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
        self.worker.start();self.addCleanup(self.stop)
    def stop(self):
        self.server.shutdown();self.server.server_close();self.worker.join(2)
    def request(self,path,method='GET',headers=None):
        c=HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=15)
        try:
            c.request(method,path,headers=headers or {});r=c.getresponse();return r.status,dict(r.getheaders()),r.read()
        finally:c.close()
    def test_public_catalog_and_atomic_snapshot_are_local_read_only(self):
        status,headers,page=self.request('/catalog/');self.assertEqual(status,200)
        self.assertIn('VPS 测评索引'.encode(),page)
        self.assertIn("script-src 'self';",headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        self.assertNotIn(self.server.session_token.encode(),page)
        status,headers,payload=self.request('/catalog/catalog-snapshot.json');self.assertEqual(status,200)
        snapshot=json.loads(payload);self.assertEqual(snapshot['schemaVersion'],'vps-catalog-snapshot/1')
        data=snapshot['files']['data.json'];self.assertEqual(len(data['posts']),120)
        self.assertEqual(sum(len(p['items']) for p in data['posts']),128)
        self.assertEqual(len(snapshot['files']['skill-refresh.json']['entries']),22)
        self.assertEqual(snapshot['files']['skill-refresh.json']['pipelineIntegration']['managementPath'],'/')
        self.assertNotIn(self.server.session_token.encode(),payload)
        self.assertEqual(self.request('/api/jobs')[0],401)
    def test_catalog_assets_are_allowlisted_and_private_paths_unreachable(self):
        for name in ['app.js','workbench.js','skill-refresh.js','style.css','favicon.svg']:
            with self.subTest(name=name):self.assertEqual(self.request('/catalog/'+name)[0],200)
        for name in ['pipeline.sqlite3','manifest.json','../var/pipeline.sqlite3','assets/971353/analysis.json','api/jobs']:
            with self.subTest(name=name):self.assertEqual(self.request('/catalog/'+name)[0],404)
        self.assertEqual(self.request('/catalog/%2e%2e/manifest.json')[0],400)
        self.assertEqual(self.request('/catalog/catalog-snapshot.json?token=unsafe')[0],400)
    def test_catalog_guard_and_methods_cannot_mutate_ledger(self):
        self.assertEqual(self.request('/catalog/catalog-snapshot.json',headers={'Host':'evil.test'})[0],403)
        self.assertEqual(self.request('/catalog/catalog-snapshot.json',headers={'Origin':'https://evil.test'})[0],403)
        for method in ['POST','PUT','PATCH','DELETE']:
            with self.subTest(method=method):self.assertEqual(self.request('/catalog/catalog-snapshot.json',method)[0],405)
        self.assertEqual(self.store.list_jobs(),[])
    def test_static_export_contains_compatible_website_not_private_evidence(self):
        out=self.root/'public';result=export_catalog(self.store,out)
        self.assertFalse(result['private_evidence_exported']);self.assertFalse(result['website_published'])
        self.assertTrue((out/'index.html').is_file());self.assertTrue((out/'catalog-snapshot.json').is_file())
        snapshot=json.loads((out/'catalog-snapshot.json').read_text())
        self.assertNotIn('managementPath',snapshot['files']['skill-refresh.json']['pipelineIntegration'])
        self.assertFalse((out/'evidence').exists())
        self.assertFalse(any(p.name.endswith(('.sqlite3','.db','.zip')) for p in out.iterdir()))
        for filename in BASELINE_JSON:
            if filename not in ('data.json','skill-refresh.json'):
                self.assertEqual(json.loads((out/filename).read_text()),json.loads((website_root()/filename).read_text()))
    def test_export_rejects_private_baseline_and_nonempty_destinations(self):
        for destination in [self.store.root,self.store.root/'public',website_root(),website_root()/'out']:
            with self.subTest(path=str(destination)),self.assertRaises(ValueError):export_catalog(self.store,destination)
        out=self.root/'occupied';out.mkdir();(out/'keep.txt').write_text('keep')
        with self.assertRaises(ValueError):export_catalog(self.store,out)
        self.assertEqual((out/'keep.txt').read_text(),'keep')
