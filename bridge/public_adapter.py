"""Validate vps-analysis/1 inputs and prepare a conservative public Site projection.
This module never fetches URLs, changes Site source, executes archive content, or publishes.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, ipaddress, json, math, re
from pathlib import Path

STATUSES={'reported','computed','inferred','official_current','unknown','conflict'}
PROTOCOLS={'ipv4','ipv6'}
CARRIERS={'telecom':'电信','unicom':'联通','mobile':'移动'}
MAPPING={'test_time':'test_time_bjt','ip_usage_location':'usage_location','ip_registered_location':'registration_location','ip_organization':'organization','monthly_transfer_tb':'monthly_traffic','transfer_billing':'traffic_billing','sysbench_single_score':'sysbench_cpu_single','sysbench_multi_score':'sysbench_cpu_multi','geekbench_single_score':'geekbench_single','geekbench_multi_score':'geekbench_multi','memory_gb':'memory_capacity','memory_overcommit':'memory_overcommit_indicators','memory_read_mbps':'sysbench_memory_read','memory_write_mbps':'sysbench_memory_write','disk_gb':'disk_capacity','port_bandwidth_mbps':'port_bandwidth','ip_connectivity':'ipv4_connectivity_type','ipv6_connectivity':'ipv6_availability','routes_to_server':'outbound_routes','routes_from_server':'return_routes','ipv4_latency':'ipv4_ping','ipv6_latency':'ipv6_ping','ip_origin':'native_ip_status'}
for workload in ('rnd4k_q1','rnd4k_q32','seq1m_q1','seq1m_q8'):
 for op in ('read','write'):MAPPING[f'disk_{workload}_{op}_mbps']=f'disk_{workload}_{op}'

def number(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def clean_text(v,maxlen=600):
 if v is None:return None
 s=str(v)
 s=re.sub(r'https?://[^\s<>"\']+','[外部链接省略]',s)
 s=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[联系信息省略]',s)
 s=re.sub(r'(?:[A-Za-z]:\\|/workspace/|/Users/|/home/)[^\s,，;；]+','[本地路径省略]',s)
 def ipv4(m):
  try:ipaddress.ip_address(m.group());return '[IP已省略]'
  except ValueError:return m.group()
 s=re.sub(r'(?<![.\d])(?:\d{1,3}\.){3}\d{1,3}(?![.\d])',ipv4,s)
 def ipv6(m):
  try:
   ip=ipaddress.ip_address(m.group());return '[IP已省略]' if ip.version==6 else m.group()
  except ValueError:return m.group()
 s=re.sub(r'(?<![A-Za-z0-9:])[0-9a-fA-F:]*:[0-9a-fA-F:]+(?::[0-9a-fA-F]*)?(?![A-Za-z0-9:])',ipv6,s)
 s=re.sub(r'(?<![\d.])(?:\d{1,3}\.){1,3}(?:\*\.)*\*(?![\d.])','[脱敏IP片段省略]',s)
 s=re.sub(r'(?<![A-Za-z0-9:])(?:[0-9a-fA-F]{1,4}:){1,7}(?:\*:)*\*(?![A-Za-z0-9:])','[脱敏IP片段省略]',s)
 s=re.sub(r'<[^>]+>','',s)
 return s[:maxlen]

def clean_value(v):
 if isinstance(v,dict):return {k:clean_value(x) for k,x in v.items()}
 if isinstance(v,list):return [clean_value(x)for x in v]
 return clean_text(v,300)if isinstance(v,str)else v

def raw_capacity_display(fact):
 """Preserve one explicit primary total-capacity quotation, without normalizing units."""
 if fact.get('status')in {'unknown','conflict'}or fact.get('value')is None:return None
 for ev in fact.get('evidence',[]):
  quote=ev.get('quote','')
  match=re.search(r'总容量\s*([0-9]+(?:\.[0-9]+)?)\s*(GiB|MiB|TiB|GB|MB|TB|G|M|T)(?![A-Za-z])',quote,re.I)
  if match:
   value=float(match[1]);value=int(value)if value.is_integer()else value
   return {'value':value,'unit':match[2],'evidenceFileId':ev['file_id'],'locator':clean_text(ev['locator'],180),'displayOnly':True}
 return None

def validate_file_tree(manifest,post_dir):
 root=Path(post_dir).resolve();files={}
 for f in manifest.get('files',[]):
  if f['id']in files:raise ValueError('Duplicate archive file ID')
  rel=Path(f['path'])
  if rel.is_absolute()or'..'in rel.parts:raise ValueError('Unsafe archive path')
  p=(root/rel).resolve()
  if not p.is_relative_to(root):raise ValueError('Archive path escapes post directory')
  if not p.is_file():raise ValueError('Missing archive file')
  content=p.read_bytes()
  if len(content)!=f['bytes']or hashlib.sha256(content).hexdigest()!=f['sha256']:raise ValueError('Archive hash/size mismatch')
  if f['role']not in {'first_post_text','first_post_html','image','report_text','report_html'}:raise ValueError('Unknown archive role')
  files[f['id']]=f
 return files

def validate_fact(fid,f,definition,files,reviewed):
 if not isinstance(f,dict)or f.get('status')not in STATUSES:raise ValueError('Invalid field status: '+fid)
 v=f.get('value');status=f['status']
 if status in {'unknown','conflict'}:
  if v is not None or not f.get('note'):raise ValueError('Unknown/conflict must be null with explanation: '+fid)
  return
 if v is None:raise ValueError('Non-unknown fact cannot be null: '+fid)
 kind=definition['value_type']
 if kind=='number' and(not number(v)or v<0):raise ValueError('Expected nonnegative numeric value: '+fid)
 if kind=='string'and(not isinstance(v,str)or not v.strip()):raise ValueError('Expected string value: '+fid)
 if kind=='object'and not isinstance(v,dict):raise ValueError('Expected object value: '+fid)
 if fid in {'vcpu','ipv4_count'}and(number(v)and(int(v)!=v or(fid=='vcpu'and v<1))):raise ValueError('Invalid integer count: '+fid)
 evidence=f.get('evidence',[])
 if not evidence:raise ValueError('Missing field evidence: '+fid)
 for ev in evidence:
  id=ev.get('file_id')
  if id not in reviewed or(id!='manifest'and id not in files):raise ValueError('Unreviewed/unknown evidence file: '+fid)
  if not ev.get('locator')or not ev.get('quote'):raise ValueError('Incomplete evidence reference: '+fid)
  if id=='manifest'and ev['locator']not in {'title','author','source_url'}:raise ValueError('Invalid manifest evidence locator')
 if fid=='test_time':
  if not v.get('timezone_basis')or not isinstance(v.get('report_times'),list)or not v['report_times']:raise ValueError('Missing timezone basis')
  for value in v['report_times']:
   parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
   if parsed.tzinfo is None:raise ValueError('Ambiguous test time')
 if fid=='asn':
  if set(v)!=PROTOCOLS:raise ValueError('ASN protocols must be separate')
  if any(x is not None and not re.fullmatch(r'AS\d+',x,re.I)for x in v.values()):raise ValueError('ASN is not an AS number')
 if fid in {'ip_usage_location','ip_registered_location','ip_organization','ip_origin','ip_classifications','risk_counts','blacklist_count','flagged_count','unlock_count','native_count','smtp25_outbound','smtp25_inbound'}:
  if set(v)!=PROTOCOLS:raise ValueError('Protocol keys must be exact: '+fid)
 if fid in {'routes_to_server','routes_from_server'}:
  if set(v)!=PROTOCOLS:raise ValueError('Route protocols must be separate')
  for x in v.values():
   if x is not None and(set(x)!=set(CARRIERS)or any(y is not None and not isinstance(y,str)for y in x.values())):raise ValueError('Route carriers must be separate')
 if fid in {'ipv4_latency','ipv6_latency'}:
  if set(v)!=set(CARRIERS):raise ValueError('Latency carriers must be separate')
  for row in v.values():
   if not isinstance(row,dict)or set(row)!={'mean_ms','sample_count','method'}:raise ValueError('Latency method/count missing')
   if row['mean_ms']is not None and(not number(row['mean_ms'])or row['mean_ms']<0):raise ValueError('Invalid latency mean')
   if row['sample_count']is not None and(not isinstance(row['sample_count'],int)or isinstance(row['sample_count'],bool)or row['sample_count']<0):raise ValueError('Invalid latency sample count')
   if row['mean_ms']is not None and not row['method']:raise ValueError('Latency method missing')
 if fid=='monthly_price':
  if set(v)!={'amount','currency'}:raise ValueError('Monthly-price keys differ')
  if v['amount']is not None and(not number(v['amount'])or v['amount']<0):raise ValueError('Invalid monthly price')
  if v['currency']is not None and not re.fullmatch('[A-Z]{3}',v['currency']):raise ValueError('Invalid currency')

def exact_route_rows(analysis,manifest,post_dir):
 """Read archived, reviewed report matrices; preserve each city/transport/carrier row."""
 rows=[];reviewed=set(analysis['ai_review']['reviewed_files'])
 for file in manifest['files']:
  if file['role']not in {'report_text','first_post_text'}or file['id']not in reviewed:continue
  content=(Path(post_dir)/file['path']).read_text(encoding='utf-8-sig');family=None
  for line_number,line in enumerate(content.splitlines(),1):
   if '网络质量体检报告：'in line:
    address=line.split('网络质量体检报告：',1)[1].strip();family='IPv6'if ':'in address else'IPv4'if'.'in address else None
   match=re.match(r'^\s*(北京|上海|广州)(TCP|UDP)[：:]\s*(.+)$',line)
   if not match or not family:continue
   city,transport,body=match.groups()
   for part in body.split('||'):
    parsed=re.match(r'^\s*(电信|联通|移动)\s+(.+?)\s*$',part)
    if not parsed:continue
    carrier,label=parsed.groups();tail=re.split(r'->|→',label)[-1].strip();eligible=not bool(re.search(r'NoData|ERROR|failed|Unknown|未知|未检测|超时',tail,re.I))
    labels=[label]
    if eligible and re.fullmatch(r'163|4837|9929|10099|CMI|CMIN2|CN2\s*GIA|CN2\s*GT|CTG\s*GIA',tail,re.I):labels.append(tail)
    rows.append({'family':family,'direction':'return','operator':carrier,'targetCity':city,'transport':transport,'reportedLabels':list(dict.fromkeys(labels)),'rawLabel':clean_text(label),'filterEligible':eligible,'status':'reported','partialCoverage':bool(re.search(r'NoData|Unknown',label,re.I)),'note':'单一城市、传输协议和运营商的报告标签；不保证其他条件相同。','evidenceRefs':[{'sourceKind':file['role'],'assetId':file['id'],'sha256':file['sha256'],'locator':f'网络报告第{line_number}行'}]})
 unique={}
 for row in rows:
  key=(row['evidenceRefs'][0]['sha256'],row['family'],row['targetCity'],row['transport'],row['operator'],row['rawLabel'])
  if key not in unique:unique[key]=row
 return list(unique.values())

def project(analysis,manifest,definitions,catalog,post_dir,item_id=None):
 if analysis.get('program_version')!=1:raise ValueError('Expected finalized program_version=1')
 if analysis.get('schema_version')!='vps-analysis/1'or manifest.get('schema_version')!='vps-archive/1':raise ValueError('Unsupported schema')
 if manifest.get('status')not in {'ready','partial'}or analysis.get('archive_status')not in {'ready','partial'}:raise ValueError('Archive not captured / finalized')
 post_id=str(analysis.get('post_id'));url=f'https://www.nodeseek.com/post-{post_id}-1'
 if not re.fullmatch(r'\d+',post_id)or analysis.get('source_url')!=url or manifest.get('source_url')!=url or str(manifest.get('post_id'))!=post_id:raise ValueError('Source identity mismatch')
 post=next((p for p in catalog['posts']if p['postId']==post_id),None)
 if not post:raise ValueError('Outside authorized existing catalog')
 ids=[i['itemId']for i in post['items']]
 if item_id is None:
  if len(ids)!=1:raise ValueError('Explicit single itemId required for multi-object post')
  item_id=ids[0]
 if item_id not in ids:raise ValueError('itemId does not belong to source post')
 files=validate_file_tree(manifest,post_dir)
 review=analysis.get('ai_review',{})
 if review.get('completed')is not True:raise ValueError('AI review incomplete')
 reviewed=set(review.get('reviewed_files',[]))
 if not any(f['role']in {'first_post_text','first_post_html'}and id in reviewed for id,f in files.items()):raise ValueError('First post not reviewed')
 if any(f['role']=='image'and id not in reviewed for id,f in files.items()):raise ValueError('Not every image reviewed')
 defs={f['id']:f for f in definitions['fields']}
 if len(defs)!=61 or set(analysis.get('facts',{}))!=set(defs):raise ValueError('Expected exact 61 fixed fields')
 fields=[];routes=[];cpu=[];times=[]
 for fid,f in analysis['facts'].items():
  validate_fact(fid,f,defs[fid],files,reviewed)
  status=f['status'];value=clean_value(f['value']);note=clean_text(f.get('note'))
  refs=[]
  for ev in f.get('evidence',[]):
   file=files.get(ev.get('file_id'));refs.append({'sourceKind':'manifest'if file is None else file['role'],'assetId':clean_text(ev.get('file_id'),120),'sha256':file.get('sha256')if file else None,'locator':clean_text(ev.get('locator'),180)})
  eligible=status in {'reported','computed'}
  if fid=='monthly_price'and status=='inferred'and isinstance(value,dict)and number(value.get('amount')):
   note_raw=f.get('note','')
   if value.get('currency')=='USD'and re.search(r'默认\s*(?:USD|美元)|刀.*(?:USD|美元)',note_raw,re.I):eligible=True
   if value.get('currency')=='EUR'and re.search(r'(?:约定|识别|按).*(?:EUR|欧元)',note_raw,re.I)and re.search(r'[Oo]|欧',note_raw):eligible=True
  # Statistical/semantic compatibility still needs explicit source details.
  if fid in {'sysbench_single_score','sysbench_multi_score','memory_read_mbps','memory_write_mbps'}or fid in {'ipv4_latency','ipv6_latency','ip_origin'}:eligible=False
  comparison_key=None
  if fid.startswith('hardware_'):
   version=re.search(r'(?:HardwareQuality(?:脚本)?|HQ(?:脚本|硬件加权评分(?:原值)?[，,]\s*脚本)?)\s*(v[0-9-]+)',f.get('note',''),re.I)
   eligible=eligible and bool(version)
   if version:comparison_key='HardwareQuality:'+version[1]
  public={'skillFieldId':fid,'fieldKey':MAPPING.get(fid,fid),'label':defs[fid]['label'],'value':value,'unit':defs[fid]['unit'],'status':status,'filterEligible':bool(eligible and value is not None),'note':note,'evidenceRefs':refs,'comparisonKey':comparison_key}
  if fid.startswith('disk_')and fid.endswith('_mbps'):
   tool_note=f.get('note','')
   label='HQ Crystal'if re.search(r'HQ\s*Crystal',tool_note,re.I)else'FIO'if re.search(r'\bfio\b',tool_note,re.I)else None
   public['benchmarkContext']={'reportedToolLabel':label,'controlledComparability':False}
  if fid in {'memory_gb','disk_gb'}:
   raw_display=raw_capacity_display(f)
   if raw_display:public['rawDisplay']=raw_display
  if fid=='port_bandwidth_mbps'and number(value):public['normalizedValue']=value/1000;public['normalizedUnit']='Gbps'
  if fid in {'geekbench_single_score','geekbench_multi_score'}:
   combined=' '.join([f.get('note','')]+[e.get('quote','')for e in f.get('evidence',[])])
   match=re.search(r'\b(?:Geekbench\s*|GB\s*)([56])\b',combined,re.I)
   public['filterEligible']=eligible and bool(match)
   if match and number(value):cpu.append({'tool':'Geekbench','majorVersion':int(match[1]),'metric':'single'if'single'in fid else'multi','score':value,'unit':'score','status':status,'comparisonEligible':eligible,'evidenceRefs':refs})
  if fid in {'routes_to_server','routes_from_server'}and isinstance(value,dict)and eligible:
   for family,carriers in value.items():
    for carrier,label in(carriers or{}).items():
     if not label:continue
     without_asides=re.sub(r'[（(][^）)]*[）)]','',label)
     variants=[x.strip()for x in re.split(r'\s+/\s+|[;；]',without_asides)if x.strip()]
     valid=[x for x in variants if not re.search(r'NoData|ERROR|failed|未检测|未知|超时',re.split(r'->|→',x)[-1],re.I)]
     labels=[]
     for path in valid:
      labels.append(path)
      tail=re.split(r'->|→',path)[-1].strip()
      if re.fullmatch(r'163|4837|9929|10099|CMI|CMIN2|CN2\s*GIA|CN2\s*GT|CTG\s*GIA',tail,re.I):labels.append(tail)
     if labels:routes.append({'family':family.upper().replace('IPV','IPv'),'direction':'outbound'if fid=='routes_to_server'else'return','operator':CARRIERS[carrier],'reportedLabels':list(dict.fromkeys(labels)),'rawLabel':label,'partialCoverage':len(valid)!=len(variants)or len(variants)>1 or any(re.search(r'NoData|Unknown',x,re.I)for x in valid),'note':note,'filterEligible':True,'status':status,'evidenceRefs':refs})

  if fid=='test_time'and isinstance(value,dict)and eligible:
   for timestamp in value['report_times']:
    t=dt.datetime.fromisoformat(timestamp.replace('Z','+00:00')).astimezone(dt.timezone(dt.timedelta(hours=8)))
    times.append({'raw':timestamp,'timezoneBasis':clean_text(value['timezone_basis']),'beijing':t.isoformat(),'status':status,'evidenceRefs':refs})
  fields.append(public)
 precise=exact_route_rows(analysis,manifest,post_dir)
 if precise:routes=precise
 return {'sourceMedia':{'imagesCaptured':sum(f['role']=='image'for f in files.values()),'imagesReviewed':sum(f['role']=='image'and id in reviewed for id,f in files.items()),'textSourcesReviewed':sum(f['role']in {'first_post_text','first_post_html','report_text','report_html'}and id in reviewed for id,f in files.items())},'itemId':item_id,'postId':post_id,'sourceUrl':url,'captureStatus':manifest['status'],'capturedAt':manifest.get('captured_at'),'analyzedAt':analysis.get('generated_at'),'sourceProcedure':['vps-review-download','vps-review-analyze'],'analysisSchema':'vps-analysis/1','summary':clean_text(analysis.get('summary'),700),'missingAssetCount':len(manifest.get('failures',[])),'fieldObservations':fields,'routeObservations':routes,'cpuBenchmarks':cpu,'confirmedReportTimes':times,'limitations':['原文、原图、作者、IP地址和购买链接未包含在公开投影中。','unknown/conflict保留null；official_current单列，不覆盖历史实测。']}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--analysis',required=True);ap.add_argument('--manifest',required=True);ap.add_argument('--fields',required=True);ap.add_argument('--catalog',required=True);ap.add_argument('--item-id');ap.add_argument('--output',required=True);args=ap.parse_args()
 load=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
 data=project(load(args.analysis),load(args.manifest),load(args.fields),load(args.catalog),Path(args.manifest).parent,args.item_id)
 out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps({'schemaVersion':'nodeseek-skill-refresh/1','publicProjection':True,'entries':[data]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'output':str(out),'postId':data['postId'],'itemId':data['itemId'],'fieldCount':len(data['fieldObservations'])},ensure_ascii=False))
if __name__=='__main__':main()
