"""Synthetic schema/guard tests only. These fixtures must never be published or called measurements."""
import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from public_adapter import project,clean_text
ROOT=Path(__file__).resolve().parents[1]
FIELDS=ROOT/'skills/vps-review-analyze/references/fields.json'
CATALOG=ROOT/'website/dist/data.json'
class AdapterTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='vps-synthetic-');self.root=Path(self.tmp.name);self.defs=json.loads(FIELDS.read_text(encoding='utf-8-sig'));self.catalog=json.loads(CATALOG.read_text(encoding='utf-8'))
  raw=b'SYNTHETIC UNIT TEST ONLY: 2 vCPU; Geekbench 5 single 1000; 2026-10-08T05:00:00+00:00.';im=b'SYNTHETIC IMAGE FILE, NOT A REAL PICTURE'
  (self.root/'text.txt').write_bytes(raw);(self.root/'image.bin').write_bytes(im)
  self.manifest={'schema_version':'vps-archive/1','post_id':'913633','source_url':'https://www.nodeseek.com/post-913633-1','status':'partial','captured_at':'2026-10-08T13:00:00+00:00','files':[{'id':id,'role':role,'path':path,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}for id,role,path,data in [('first-text','first_post_text','text.txt',raw),('image-1','image','image.bin',im)]],'failures':[{'reason':'SYNTHETIC'}]}
  self.analysis={'program_version':1,'schema_version':'vps-analysis/1','post_id':'913633','source_url':self.manifest['source_url'],'archive_status':'partial','generated_at':'2026-10-08T13:00:01+00:00','summary':'SYNTHETIC TEST. IP 192.0.2.9; IPv6 2001:db8::1; URL https://private.invalid/image.png; person@example.com','ai_review':{'completed':True,'agent':'SYNTHETIC TEST ONLY','reviewed_files':['first-text','image-1']},'facts':{f['id']:{'value':None,'status':'unknown','evidence':[],'note':'SYNTHETIC UNKNOWN'}for f in self.defs['fields']}}
 def tearDown(self):self.tmp.cleanup()
 def fact(self,id,value,status='reported',note='SYNTHETIC TEST',quote='2 vCPU'):
  self.analysis['facts'][id]={'value':value,'status':status,'note':note,'evidence':[{'file_id':'first-text','locator':'SYNTHETIC line 1','quote':quote}]}
 def run_project(self):return project(self.analysis,self.manifest,self.defs,self.catalog,self.root)
 def test_exact61_and_no_raw_fields(self):
  self.fact('vcpu',2);out=self.run_project();self.assertEqual(len(out['fieldObservations']),61);self.assertEqual(out['itemId'],'913633-1');self.assertNotIn('192.0.2.9',json.dumps(out));self.assertNotIn('2001:db8::1',json.dumps(out));self.assertNotIn('person@example.com',json.dumps(out));self.assertNotIn('private.invalid',json.dumps(out));self.assertNotIn('quote',json.dumps(out));self.assertNotIn('author',out)
 def test_unknown_remains_null(self):
  out=self.run_project();self.assertTrue(all(x['value']is None and not x['filterEligible']for x in out['fieldObservations']))
 def test_conflict_nonnull_rejected(self):
  self.fact('vcpu',2,status='conflict');self.assertRaises(ValueError,self.run_project)
 def test_conflict_null_kept(self):
  self.analysis['facts']['vcpu']={'value':None,'status':'conflict','evidence':[],'note':'SYNTHETIC conflicting candidates'};self.assertEqual(self.run_project()['fieldObservations'][17]['status'],'conflict')
 def test_unknown_nonnull_rejected(self):
  self.fact('vcpu',2,status='unknown');self.assertRaises(ValueError,self.run_project)
 def test_official_not_filter_eligible(self):
  self.fact('vcpu',64,status='official_current');out=self.run_project();row=next(x for x in out['fieldObservations']if x['skillFieldId']=='vcpu');self.assertEqual(row['value'],64);self.assertFalse(row['filterEligible'])
 def test_missing_currency_is_not_defaulted_to_usd(self):
  self.fact('monthly_price',{'amount':0.99,'currency':'USD'},status='inferred',note='未写币种，按模板约定默认USD')
  row=next(x for x in self.run_project()['fieldObservations']if x['skillFieldId']=='monthly_price')
  self.assertIsNone(row['value']['currency']);self.assertEqual(row['value']['amount'],0.99);self.assertFalse(row['filterEligible']);self.assertEqual(row['status'],'unknown')
 def test_price_no_fx_or_cycle_invention(self):
  self.fact('monthly_price',{'amount':5,'currency':'EUR'},status='computed');out=self.run_project();row=next(x for x in out['fieldObservations']if x['skillFieldId']=='monthly_price');self.assertEqual(row['value'],{'amount':5,'currency':'EUR'});self.assertIsNone(next(x for x in out['fieldObservations']if x['skillFieldId']=='billing_period')['value'])
 def test_gb_versions_separate(self):
  self.fact('geekbench_single_score',1000,note='Geekbench 5 SYNTHETIC');self.fact('geekbench_multi_score',2000,note='Geekbench 6 SYNTHETIC');scores=self.run_project()['cpuBenchmarks'];self.assertEqual([x['majorVersion']for x in scores],[5,6])
 def test_unknown_benchmark_version_not_eligible(self):
  self.fact('geekbench_single_score',1000);out=self.run_project();self.assertEqual(out['cpuBenchmarks'],[])
 def test_sysbench_not_comparable_without_parameters(self):
  self.fact('sysbench_single_score',1000);row=next(x for x in self.run_project()['fieldObservations']if x['skillFieldId']=='sysbench_single_score');self.assertFalse(row['filterEligible'])
 def test_direction_family_carrier_exact(self):
  self.fact('routes_from_server',{'ipv4':{'telecom':'CN2 GIA','unicom':None,'mobile':'NoData'},'ipv6':None});r=self.run_project()['routeObservations'];self.assertEqual(len(r),1);self.assertEqual((r[0]['direction'],r[0]['family'],r[0]['operator']),('return','IPv4','电信'))
 def test_unknown_upstream_keeps_known_downstream(self):
  self.fact('routes_from_server',{'ipv4':None,'ipv6':{'telecom':'TCP: NoData->9929; UDP: NoData->10099','unicom':None,'mobile':'Unknown->NoData'}});rows=self.run_project()['routeObservations'];self.assertEqual(len(rows),1);self.assertIn('9929',rows[0]['reportedLabels']);self.assertTrue(rows[0]['partialCoverage'])
 def test_timezone_conversion_once(self):
  self.fact('test_time',{'report_times':['2026-10-08T13:00:00+08:00','2026-10-08T05:00:00+00:00'],'timezone_basis':'SYNTHETIC explicit UTC offset','half_hour_buckets':[]});times=self.run_project()['confirmedReportTimes'];self.assertEqual([x['beijing']for x in times],['2026-10-08T13:00:00+08:00']*2)
 def test_naive_time_rejected(self):
  self.fact('test_time',{'report_times':['2026-10-08T13:00:00'],'timezone_basis':'CST','half_hour_buckets':[]});self.assertRaises(ValueError,self.run_project)
 def test_unreviewed_image_blocks(self):
  self.analysis['ai_review']['reviewed_files']=['first-text'];self.assertRaises(ValueError,self.run_project)
 def test_failed_capture_blocks(self):
  self.manifest['status']='blocked';self.assertRaises(ValueError,self.run_project)
 def test_bad_hash_blocks(self):
  (self.root/'text.txt').write_text('modified',encoding='utf-8');self.assertRaises(ValueError,self.run_project)
 def test_traversal_blocks(self):
  self.manifest['files'][0]['path']='../text.txt';self.assertRaises(ValueError,self.run_project)
 def test_multi_object_requires_mapping(self):
  self.manifest['post_id']=self.analysis['post_id']='873214';self.manifest['source_url']=self.analysis['source_url']='https://www.nodeseek.com/post-873214-1';self.assertRaises(ValueError,self.run_project)
 def test_incorrect_fields_rejected(self):
  self.analysis['facts']['other']={'value':1,'status':'reported'};self.assertRaises(ValueError,self.run_project)
 def test_asn_not_hosting(self):
  self.fact('asn',{'ipv4':'Hosting','ipv6':None});self.assertRaises(ValueError,self.run_project)
 def test_fractional_core_invalid(self):
  self.fact('vcpu',2.5);self.assertRaises(ValueError,self.run_project)
 def test_bool_not_score(self):
  self.fact('vcpu',True);self.assertRaises(ValueError,self.run_project)
 def test_latency_not_generic_ping(self):
  value={c:{'mean_ms':100,'sample_count':1,'method':'TCP report SYNTHETIC'}for c in ['telecom','unicom','mobile']};self.fact('ipv4_latency',value,status='computed');row=next(x for x in self.run_project()['fieldObservations']if x['skillFieldId']=='ipv4_latency');self.assertFalse(row['filterEligible'])
 def test_missing_latency_method_rejected(self):
  value={c:{'mean_ms':0,'sample_count':1,'method':None}for c in ['telecom','unicom','mobile']};self.fact('ipv4_latency',value,status='computed');self.assertRaises(ValueError,self.run_project)
 def test_hq_version_aliases_bounded(self):
  for note in ['HQ v2026-05-21', 'HQ脚本v2026-05-21硬件加权分数', 'HQ硬件加权评分原值，脚本v2026-05-21']:
   self.fact('hardware_total_score',100,note=note)
   f=next(x for x in self.run_project()['fieldObservations'] if x['skillFieldId']=='hardware_total_score')
   self.assertTrue(f['filterEligible']);self.assertEqual(f['comparisonKey'],'HardwareQuality:v2026-05-21')
  self.fact('hardware_total_score',100,note='HQ score and other benchmark v2026-05-21')
  self.assertFalse(next(x for x in self.run_project()['fieldObservations'] if x['skillFieldId']=='hardware_total_score')['filterEligible'])
if __name__=='__main__':unittest.main(verbosity=2)
