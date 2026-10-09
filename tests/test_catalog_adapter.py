import copy,json,unittest,os
from pathlib import Path
from vps_pipeline.catalog_adapter import build_catalog,FILES
ROOT=Path(__file__).resolve().parents[1]
PUBLIC=Path(os.environ.get('VPS_CATALOG_ROOT',ROOT/'website/dist'))
BASE={name:json.loads((PUBLIC/name).read_text(encoding='utf-8')) for name in FILES}
DEFS=json.loads(Path(os.environ.get('VPS_FIELD_DEFINITIONS',ROOT/'vps_pipeline/vendor/vps-review-analyze/references/fields.json')).read_text(encoding='utf-8-sig'))
NOW='2026-10-09T02:15:00Z'
def record(post='999991',kind='accepted',rid='synthetic-record'):
 return {'post_id':post,'source_url':f'https://www.nodeseek.com/post-{post}-1','record_id':rid,'record_kind':kind,'archive_status':'partial','analysis_version':1,'facts':{f['id']:{'value':None,'status':'unknown','projection_status':'unchanged'} for f in DEFS['fields']},'benchmark_observations':[],'network_observations':[],'catalog_mapping':{'confirmed':True,'item_id':post+'-1','post_object_count':1,'reviewed_object_count':1,'entry_kind':'measured_vps','public_label':'SYNTHETIC TEST ONLY'}}
def put(r,key,value,status='reported',projection='unchanged'):r['facts'][key]={'value':value,'status':status,'projection_status':projection}
def run(records):return build_catalog(BASE,records,DEFS,NOW)
def current(out,item='999991-1'):return next(r for r in out['skill-refresh.json']['entries']if r['itemId']==item)
def field(out,key,item='999991-1'):return next(f for f in current(out,item)['fieldObservations']if f['skillFieldId']==key)
class CatalogTests(unittest.TestCase):
 def test_empty_preserves_baseline(self):
  out=run([]);self.assertEqual(out['data.json']['posts'],BASE['data.json']['posts']);self.assertEqual(out['skill-refresh.json']['entries'],BASE['skill-refresh.json']['entries']);self.assertEqual(out['enrichment.json'],BASE['enrichment.json'])
 def test_input_not_mutated(self):
  before=copy.deepcopy(BASE);r=record();old=copy.deepcopy(r);run([r]);self.assertEqual(BASE,before);self.assertEqual(r,old)
 def test_single_new_explicit(self):
  out=run([record()]);self.assertEqual(out['data.json']['counts']['posts'],121);self.assertEqual(out['data.json']['counts']['items'],129);self.assertEqual(len(current(out)['fieldObservations']),61)
 def test_unmapped_pending(self):
  r=record();r.pop('catalog_mapping');out=run([r]);self.assertEqual(out['data.json']['counts']['posts'],120);self.assertEqual(out['catalog-integration.json']['pendingRecords'],1)
 def test_false_confirmation_pending(self):
  r=record();r['catalog_mapping']['confirmed']=False;self.assertEqual(run([r])['catalog-integration.json']['pendingRecords'],1)
 def test_duplicate_id_pending(self):self.assertEqual(run([record(),record()])['catalog-integration.json']['pendingRecords'],1)
 def test_new_multi_cannot_manufacture(self):
  r=record();r['catalog_mapping']['post_object_count']=2;self.assertEqual(run([r])['catalog-integration.json']['pendingRecords'],1)
 def test_boolean_not_object_count(self):
  r=record();r['catalog_mapping']['post_object_count']=True;self.assertEqual(run([r])['catalog-integration.json']['pendingRecords'],1)
 def test_wrong_url_pending(self):
  r=record();r['source_url']='https://www.nodeseek.com/post-111-1';self.assertEqual(run([r])['catalog-integration.json']['pendingRecords'],1)
 def test_existing_multitarget_explicit(self):
  post=next(p for p in BASE['data.json']['posts']if len(p['items'])>1);item=post['items'][1];r=record(post['postId']);r['catalog_mapping'].update(item_id=item['itemId'],post_object_count=len(post['items']),entry_kind=item['itemType']);out=run([r]);self.assertEqual(out['data.json']['counts']['items'],128);self.assertEqual(current(out,item['itemId'])['pipelineRecordStatus'],'accepted')
 def test_existing_multiwrong_count(self):
  post=next(p for p in BASE['data.json']['posts']if len(p['items'])>1);self.assertEqual(run([record(post['postId'])])['catalog-integration.json']['pendingRecords'],1)
 def test_legacy_existing_only_annotates(self):
  r=record('971510','legacy_imported');r.pop('catalog_mapping');out=run([r]);old=next(x for x in BASE['skill-refresh.json']['entries']if x['itemId']=='971510-1');new=current(out,'971510-1');self.assertEqual(new['fieldObservations'],old['fieldObservations']);self.assertEqual(new['routeObservations'],old['routeObservations']);self.assertEqual(new['pipelineLegacyLinks'],['synthetic-record']);self.assertEqual(out['data.json']['posts'],BASE['data.json']['posts'])
 def test_legacy_cannot_replace(self):self.assertEqual(run([record('971510','legacy_imported')])['catalog-integration.json']['pendingRecords'],1)
 def test_existing_accepted_keeps_history(self):
  out=run([record('971510')]);row=current(out,'971510-1');self.assertEqual(len(row['reviewHistory']),1);self.assertEqual(row['reviewHistory'][0],next(x for x in BASE['skill-refresh.json']['entries']if x['itemId']=='971510-1'));self.assertEqual(out['data.json']['posts'],BASE['data.json']['posts'])
 def test_unknown_not_zero(self):self.assertIsNone(field(run([record()]),'vcpu')['value']);self.assertFalse(field(run([record()]),'vcpu')['filterEligible'])
 def test_inferred_capacity_not_numeric_filter(self):
  r=record();put(r,'memory_gb',.965,'inferred');self.assertFalse(field(run([r]),'memory_gb')['filterEligible'])
 def test_raw_capacity_explicit(self):
  r=record();put(r,'memory_gb',.965,'inferred');r['safe_observations']=[{'field_id':'memory_gb','value':.965,'status':'inferred','original_value':965,'original_unit':'MB'}];self.assertEqual(field(run([r]),'memory_gb')['rawDisplay']['value'],965)
 def test_redacted_fact_not_filter(self):
  r=record();put(r,'vcpu',2,projection='partial');self.assertFalse(field(run([r]),'vcpu')['filterEligible'])
 def test_unknown_nonnull_pending(self):
  r=record();put(r,'vcpu',2,'unknown');self.assertEqual(run([r])['catalog-integration.json']['pendingRecords'],1)
 def test_negative_or_bool_core_pending(self):
  for v in [-1,True,2.5]:
   r=record();put(r,'vcpu',v);self.assertEqual(run([r])['catalog-integration.json']['pendingRecords'],1)
 def test_currency_no_cycle_invention(self):
  r=record();put(r,'monthly_price',{'amount':5,'currency':'EUR'},'inferred');out=run([r]);self.assertEqual(field(out,'monthly_price')['value']['currency'],'EUR');self.assertIsNone(field(out,'billing_period')['value'])
 def test_score_requires_version(self):
  r=record();put(r,'geekbench_single_score',1000);self.assertEqual(current(run([r]))['cpuBenchmarks'],[])
 def test_gb_version_exact(self):
  r=record();put(r,'geekbench_single_score',1000);r['benchmark_observations']=[{'field_id':'geekbench_single_score','tool':'Geekbench','version':6,'metric':'single','score':1000,'kind':'measurement','status':'reported'}];self.assertEqual(current(run([r]))['cpuBenchmarks'][0]['comparisonKey'],'geekbench:6:single')
 def test_unmatched_score_not_adopted(self):
  r=record();put(r,'geekbench_single_score',1000);r['benchmark_observations']=[{'field_id':'geekbench_single_score','tool':'Geekbench','version':6,'metric':'single','score':999,'kind':'measurement','status':'reported'}];self.assertEqual(current(run([r]))['cpuBenchmarks'],[])
 def test_route_axes_and_transport_preserved(self):
  r=record();put(r,'routes_from_server',{'ipv4':None,'ipv6':{'telecom':'10099','unicom':None,'mobile':None}});r['network_observations']=[{'family':'IPv6','direction':'return','operator':'电信','transport':'UDP','targetCity':'上海','reportedLabels':['10099'],'status':'reported','kind':'measurement'}];route=current(run([r]))['routeObservations'][0];self.assertEqual((route['family'],route['direction'],route['transport'],route['operator']),('IPv6','return','UDP','电信'))
 def test_failed_route_not_positive(self):
  r=record();r['network_observations']=[{'family':'IPv6','direction':'return','operator':'电信','transport':'TCP','reportedLabels':['NoData'],'status':'reported','kind':'measurement'}];self.assertEqual(current(run([r]))['routeObservations'],[])
 def test_generic_ping_disabled(self):
  r=record();put(r,'ipv4_latency',{'telecom':{'mean_ms':0,'sample_count':1,'method':'TCP'},'unicom':None,'mobile':None},'computed');self.assertFalse(field(run([r]),'ipv4_latency')['filterEligible'])
 def test_timezone_not_guessed(self):
  r=record();put(r,'test_time',{'report_times':['2026-10-08T12:00:00'],'timezone_basis':'CST','half_hour_buckets':[]});self.assertEqual(run([r])['catalog-integration.json']['pendingRecords'],1)
 def test_confirmed_timezone_converted_once(self):
  r=record();put(r,'test_time',{'report_times':['2026-10-08T12:00:00+08:00'],'timezone_basis':'明确UTC+8','half_hour_buckets':[]});self.assertEqual(current(run([r]))['confirmedReportTimes'][0]['beijing'],'2026-10-08T12:00:00+08:00')
 def test_private_value_or_key_rejected(self):
  for value in ['192.0.2.1','https://example.com/image','/workspace/private/raw',{'author':'someone'}]:
   r=record();put(r,'cpu_model',value);out=run([r]);self.assertEqual(out['catalog-integration.json']['pendingRecords'],1);self.assertNotIn('192.0.2.1',json.dumps(out['catalog-integration.json']))
 def test_version_must_integer(self):
  r=record();r['analysis_version']={'secret':'bad'};self.assertEqual(run([r])['catalog-integration.json']['pendingRecords'],1)
 def test_route_unknown_final_fact_suppressed(self):
  r=record();r['network_observations']=[{'family':'IPv6','direction':'return','operator':'电信','transport':'UDP','reportedLabels':['10099'],'status':'reported','kind':'measurement'}];self.assertEqual(current(run([r]))['routeObservations'],[])
 def test_route_mismatched_final_fact_suppressed(self):
  r=record();put(r,'routes_from_server',{'ipv4':None,'ipv6':{'telecom':'9929','unicom':None,'mobile':None}});r['network_observations']=[{'family':'IPv6','direction':'return','operator':'电信','transport':'UDP','reportedLabels':['10099'],'status':'reported','kind':'measurement'}];self.assertEqual(current(run([r]))['routeObservations'],[])
 def test_inferred_price_without_basis_not_filterable(self):
  r=record();put(r,'monthly_price',{'amount':5,'currency':'USD'},'inferred');self.assertFalse(field(run([r]),'monthly_price')['filterEligible'])
 def test_safe_confirmed_time_metadata_after_prose_redaction(self):
  r=record();times=['2026-10-08T12:00:00+08:00'];put(r,'test_time',{'report_times':times,'timezone_basis':None,'half_hour_buckets':[]},projection='partial');r['time_observations']=[{'field_id':'test_time','status':'reported','report_times':times,'timezone_basis_declared':True}];self.assertEqual(current(run([r]))['confirmedReportTimes'][0]['beijing'],times[0])
 def test_mismatched_time_metadata_does_not_enable_filter(self):
  r=record();put(r,'test_time',{'report_times':['2026-10-08T12:00:00+08:00'],'timezone_basis':None,'half_hour_buckets':[]},projection='partial');r['time_observations']=[{'field_id':'test_time','status':'reported','report_times':['2026-10-08T00:00:00+00:00'],'timezone_basis_declared':True}];self.assertEqual(current(run([r]))['confirmedReportTimes'],[])
 def test_missing_time_declaration_does_not_enable_filter(self):
  r=record();times=['2026-10-08T12:00:00+08:00'];put(r,'test_time',{'report_times':times,'timezone_basis':None,'half_hour_buckets':[]},projection='partial');r['time_observations']=[{'field_id':'test_time','status':'reported','report_times':times,'timezone_basis_declared':False}];self.assertEqual(current(run([r]))['confirmedReportTimes'],[])
 def test_all_feed_route_labels_survive_consistent_projection(self):
  for value in ['163','4837','9929','10099','CMI','CMIN2','CN2','CN2GIA','CTGGIA']:
   with self.subTest(label=value):
    r=record();put(r,'routes_to_server',{'ipv4':{'telecom':value,'unicom':None,'mobile':None},'ipv6':None});r['network_observations']=[{'family':'IPv4','direction':'outbound','operator':'电信','transport':'TCP','reportedLabels':[value],'status':'reported','kind':'measurement'}];out=run([r]);self.assertEqual(out['catalog-integration.json']['pendingRecords'],0);rows=current(out)['routeObservations'];self.assertEqual(len(rows),1);self.assertEqual(rows[0]['reportedLabels'],[value]);self.assertEqual(rows[0]['direction'],'outbound')
if __name__=='__main__':unittest.main(verbosity=2)
