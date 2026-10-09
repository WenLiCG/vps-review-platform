"""SYNTHETIC ONLY: tests incremental invariants; no production inputs are modified."""
import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from build_increment import build

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'website/dist'
DEFS=ROOT/'skills/vps-review-analyze/references/fields.json'
class IncrementalTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='vps-increment-synthetic-');self.root=Path(self.tmp.name);self.p=self.root/'assets'/'999901';self.p.mkdir(parents=True)
  source=b'SYNTHETIC SCHEMA TEST. NOT A REAL REVIEW.';(self.p/'source.txt').write_bytes(source)
  self.m={'schema_version':'vps-archive/1','post_id':'999901','source_url':'https://www.nodeseek.com/post-999901-1','status':'partial','captured_at':'2026-10-08T16:00:00+00:00','files':[{'id':'first-text','role':'first_post_text','path':'source.txt','bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()}],'failures':[{'reason':'SYNTHETIC missing image'}]}
  fields=json.loads(DEFS.read_text(encoding='utf-8-sig'))['fields'];self.a={'schema_version':'vps-analysis/1','program_version':1,'archive_status':'partial','post_id':'999901','source_url':self.m['source_url'],'generated_at':'2026-10-08T16:00:01+00:00','ai_review':{'completed':True,'agent':'SYNTHETIC TEST ONLY','reviewed_files':['first-text']},'facts':{f['id']:{'value':None,'status':'unknown','evidence':[],'note':'SYNTHETIC UNKNOWN'}for f in fields},'summary':'SYNTHETIC TEST: no measured data.'}
  self.selection={'target_count':20,'initial_selected':[{'post_id':'999901','source_url':self.m['source_url']}],'same_page_reserves':[]}
  self.rec={'postId':'999901','sourceUrl':self.m['source_url'],'reviewComplete':True,'objectCount':1,'manifestPath':str(self.p/'manifest.json'),'publicLabel':'SYNTHETIC RECORD','objects':[{'itemId':'999901-1','entryKind':'measured_vps','publicLabel':'SYNTHETIC OBJECT','analysisPath':str(self.p/'analysis.json')}]}
  self.idx={'batchId':'SYNTHETIC-DO-NOT-PUBLISH','batchDate':'2026-10-08','sourceCommit':'synthetic','entries':[self.rec]}
 def tearDown(self):self.tmp.cleanup()
 def write(self):
  for path,data in [(self.p/'manifest.json',self.m),(self.p/'analysis.json',self.a),(self.root/'selection.json',self.selection),(self.root/'index.json',self.idx)]:path.write_text(json.dumps(data),encoding='utf-8')
 def run_build(self,base=BASE):
  self.write();return build(base,self.root/'selection.json',self.root/'index.json',DEFS,self.root/'stage')
 def test_preserve_baseline_and_increment(self):
  r=self.run_build();self.assertEqual((r['oldPosts'],r['oldObjects'],r['newPosts'],r['newObjects'],r['finalPosts'],r['finalObjects']),(120,128,1,1,121,129));self.assertEqual(r['retainedPreviousSkillReviews'],22)
  old=json.loads((BASE/'data.json').read_text(encoding='utf-8'));new=json.loads((self.root/'stage/data.json').read_text(encoding='utf-8'));self.assertEqual(new['posts'][1:],old['posts']);self.assertIsNone(new['posts'][0]['items'][0]['configuration']['vcpu']);self.assertEqual(new['counts']['uniqueMachines'],None)
 def test_idempotent_reimport_rejected(self):
  self.run_build();self.assertRaises(ValueError,self.run_build,self.root/'stage')
 def test_old_id_rejected(self):
  self.rec['postId']='913633';self.rec['sourceUrl']='https://www.nodeseek.com/post-913633-1';self.selection['initial_selected']=[{'post_id':'913633','source_url':self.rec['sourceUrl']}];self.assertRaises(ValueError,self.run_build)
 def test_outside_selection_rejected(self):
  self.selection['initial_selected']=[];self.assertRaises(ValueError,self.run_build)
 def test_unknown_object_count_rejected(self):
  self.rec['objectCount']=None;self.assertRaises(ValueError,self.run_build)
 def test_info_post_not_fake_vps(self):
  self.rec['entryKind']='information_only';self.assertRaises(ValueError,self.run_build)
 def test_same_analysis_not_two_machines(self):
  self.rec['objectCount']=2;self.rec['objectMappingConfirmed']=True;self.rec['objects'].append({**self.rec['objects'][0],'itemId':'999901-2'});self.assertRaises(ValueError,self.run_build)
 def test_wrong_item_scope_rejected(self):
  self.rec['objects'][0]['itemId']='12345-1';self.assertRaises(ValueError,self.run_build)
 def test_blocked_capture_not_published(self):
  self.m['status']='blocked';self.assertRaises(ValueError,self.run_build)
 def test_review_checkpoint_required(self):
  self.rec['reviewComplete']=False;self.assertRaises(ValueError,self.run_build)
 def test_limit_exceeded_rejected(self):
  self.idx['entries']=[self.rec]*21;self.assertRaises(ValueError,self.run_build)
 def test_source_files_unchanged(self):
  self.write();before=(self.p/'source.txt').read_bytes();self.run_build();self.assertEqual((self.p/'source.txt').read_bytes(),before)
 def test_baseline_output_rejected(self):
  self.write();self.assertRaises(ValueError,build,BASE,self.root/'selection.json',self.root/'index.json',DEFS,BASE)
 def test_archive_output_rejected(self):
  self.write();self.assertRaises(ValueError,build,BASE,self.root/'selection.json',self.root/'index.json',DEFS,self.p/'public')
if __name__=='__main__':unittest.main(verbosity=2)
