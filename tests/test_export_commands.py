import contextlib
import io
import json
from pathlib import Path
import unittest
import test_pipeline
from vps_pipeline.cli import main


class SafeExportCommandTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_pipeline.PipelineTests();self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        self.fixture.html.write_text(test_pipeline.PAGE.replace('SYNTHETIC TEST EVIDENCE ONLY.','SYNTHETIC TEST EVIDENCE ONLY. PRIVATE_SENTINEL 203.0.113.9 /home/private/report'),encoding='utf-8')
        self.fixture.store.import_html(self.fixture.job['id'],self.fixture.html)
        envelope,_=self.fixture.synthetic_submission()
        envelope['catalog_mapping']={'confirmed':True,'item_id':'913633-1','post_object_count':1,'reviewed_object_count':1,'entry_kind':'measured_vps','public_label':'Synthetic catalog verification'}
        self.fixture.store.submit(self.fixture.job['id'],envelope)
    def run_cli(self,command,out):
        stdout,stderr=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
            code=main(['--data',str(self.fixture.store.root),command,str(out)])
        self.assertEqual(code,0,stderr.getvalue())
        return json.loads(stdout.getvalue())
    def test_public_and_v5_aliases_export_only_safe_website(self):
        for command in ['export-public','export-v5']:
            with self.subTest(command=command):
                out=self.fixture.base/command;result=self.run_cli(command,out)
                self.assertFalse(result['private_evidence_exported']);self.assertFalse(result['website_published'])
                self.assertTrue((out/'index.html').exists());self.assertTrue((out/'catalog-snapshot.json').exists())
                self.assertFalse((out/'evidence').exists())
                for p in out.iterdir():
                    self.assertNotIn(p.suffix,{'.bin','.png','.sqlite3','.db','.txt'})
                    raw=p.read_bytes()
                    for secret in [b'PRIVATE_SENTINEL',b'203.0.113.9',b'/home/private/report']:
                        self.assertNotIn(secret,raw)
    def test_evidence_dump_is_explicitly_private_and_never_aliases_public(self):
        out=self.fixture.base/'private-evidence';result=self.run_cli('export-evidence',out)
        self.assertEqual(result['visibility'],'private_evidence');self.assertFalse(result['publish_safe'])
        self.assertIn('DO NOT PUBLISH',(out/'README.txt').read_text())
        self.assertTrue((out/'evidence').is_dir())
        self.assertTrue(any(b'PRIVATE_SENTINEL' in p.read_bytes() for p in (out/'evidence').rglob('*') if p.is_file()))
        self.assertFalse((out/'index.html').exists())
