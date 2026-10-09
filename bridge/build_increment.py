"""Build a staged incremental public catalog from explicitly selected, finalized reviews.
No networking, no publishing, and no mutations of source archives or production checkout.
"""
from __future__ import annotations
import argparse,copy,collections,hashlib,json,re
from pathlib import Path
from public_adapter import project,clean_text,number,raw_capacity_display
KINDS={'measured_vps','advertised_plan','review_configuration_version','measured_host'}

def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def known(a,id):
 f=a['facts'][id]
 return f.get('value')if f['status']in {'reported','computed'}else None

def make_item(post_id,obj,a):
 label=clean_text(obj['publicLabel'],180)
 if not label:raise ValueError('A reviewed public label is required')
 kind=obj['entryKind']
 if kind not in KINDS:raise ValueError('Unrecognized object kind')
 item_id=obj.get('itemId')
 if not item_id or not item_id.startswith(post_id+'-'):raise ValueError('Explicit post-scoped item ID required')
 url=f'https://www.nodeseek.com/post-{post_id}-1';provider=known(a,'provider');loc=known(a,'country_region')or{}
 cfg={'vcpu':known(a,'vcpu'),'cpuModel':known(a,'cpu_model'),'memoryValue':known(a,'memory_gb'),'memoryUnit':'GB'if known(a,'memory_gb')is not None else None,'diskValue':known(a,'disk_gb'),'diskUnit':'GB'if known(a,'disk_gb')is not None else None,'basis':'本次指定技能复核；推断/未知/冲突与原始单位见61字段详情。'}
 # Values standardized with an uncertain conversion are not silently made certain.
 for fid,key,unit in [('memory_gb','memoryValue','memoryUnit'),('disk_gb','diskValue','diskUnit')]:
  f=a['facts'][fid]
  raw=raw_capacity_display(f)
  if raw:cfg[key]=raw['value'];cfg[unit]=raw['unit']+('（原文）'if raw['unit']in {'G','M','T'}else'')
  elif f['status']=='inferred'and number(f['value']):cfg[key]=f['value'];cfg[unit]='GB（推断）'
 return {'itemId':item_id,'postId':post_id,'sourceUrl':url,'itemType':kind,'label':label,'vendor':provider,'product':clean_text(obj.get('product'),160),'location':{'country':loc.get('country'),'city':known(a,'city'),'region':loc.get('region'),'basis':'来源明确部署信息，IP使用地/注册地另列。'if loc or known(a,'city')else None,'note':'未确认的物理机房位置保留未知。'},'configuration':cfg,'trafficQuota':{'value':known(a,'monthly_transfer_tb'),'unit':'TB'if known(a,'monthly_transfer_tb')is not None else None,'direction':None,'period':'monthly'if known(a,'monthly_transfer_tb')is not None else None,'note':'来源未确认的配额或计费方向不补值。'},'price':{'raw':None,'amount':None,'currency':None,'billingPeriod':known(a,'billing_period'),'note':'实际周期与月均报价分开；见本次61字段复核。'},'testedAt':{'primary':{'raw':None,'timezone':None,'beijing':None,'status':'unknown'},'reports':[],'datesBeijing':[],'dateUncertain':True},'network':{'routeObservations':[],'reportedRouteTags':[],'claimedRouteTags':[],'filterRouteTags':[],'note':'本次复核的协议、方向、运营商和传输协议按观测分开；不保证未测目标。'},'bandwidthClaims':[],'summary':clean_text(a.get('summary'),700),'evidence':{'sourceUrl':url,'basis':'实际采集首帖及已取得素材，经指定分析技能完成。'},'addedOn':obj.get('addedOn')}

def build(base_dir,selection_path,index_path,definitions_path,out_dir):
 destination=Path(out_dir).resolve();baseline=Path(base_dir).resolve()
 if destination==baseline or destination in baseline.parents or baseline in destination.parents:raise ValueError('Output must be separate from the baseline catalog')
 base=Path(base_dir);selection=load(selection_path);index=load(index_path);defs=load(definitions_path);catalog=copy.deepcopy(load(base/'data.json'));enrichment=copy.deepcopy(load(base/'enrichment.json'));refresh=copy.deepcopy(load(base/'skill-refresh.json'))
 old_posts={p['postId']:copy.deepcopy(p)for p in catalog['posts']};old_item_ids={i['itemId']for p in catalog['posts']for i in p['items']};old_reviews={r['itemId']:copy.deepcopy(r)for r in refresh['entries']}
 allowed={str(x['post_id']):x['source_url']for section in ['initial_selected','same_page_reserves']for x in selection.get(section,[])}
 records=index.get('entries',[])
 if len(records)>selection.get('target_count',20):raise ValueError('Batch exceeds approved selected count')
 seen=set();new_posts=[];new_reviews=[];provenance=[]
 for rec in records:
  id=str(rec['postId']);url=f'https://www.nodeseek.com/post-{id}-1'
  if not re.fullmatch(r'\d+',id)or allowed.get(id)!=url:raise ValueError('Outside verified category-page selection: '+id)
  if id in old_posts or id in seen:raise ValueError('Duplicate/previously collected post: '+id)
  if rec.get('sourceUrl')!=url or rec.get('reviewComplete')is not True:raise ValueError('Entry identity/review checkpoint incomplete')
  if rec.get('entryKind')=='information_only':raise ValueError('Information-only posts need separate post-level review path; never manufacture a VPS')
  objs=rec.get('objects',[])
  if rec.get('objectCount')!=len(objs)or not objs:raise ValueError('Object count must be confirmed')
  if len(objs)>1 and rec.get('objectMappingConfirmed')is not True:raise ValueError('Multi-object mapping requires explicit evidence review')
  manifest_path=Path(rec['manifestPath']);archive=manifest_path.parent.resolve()
  if destination==archive or destination in archive.parents or archive in destination.parents:raise ValueError('Output must be separate from source archives')
  m=load(manifest_path)
  if str(m.get('post_id'))!=id or m.get('source_url')!=url:raise ValueError('Manifest identity mismatch')
  analyses=[load(o['analysisPath'])for o in objs];hashes=[sha(o['analysisPath'])for o in objs]
  if len(objs)>1 and len(set(hashes))!=len(hashes):raise ValueError('One analysis reused across multiple objects')
  items=[make_item(id,o,a)for o,a in zip(objs,analyses)]
  if len(set(i['itemId']for i in items))!=len(items)or any(i['itemId']in old_item_ids for i in items):raise ValueError('Item ID collision')
  downloaded=sum(f.get('role')=='image'for f in m.get('files',[]));missing=len(m.get('failures',[]))
  p={'postId':id,'sourceUrl':url,'category':rec.get('category','review'if len(items)==1 else'multi_vps_review'),'label':clean_text(rec['publicLabel'],180),'summary':clean_text(rec.get('summary')or analyses[0].get('summary'),700),'warnings':['新采集首帖；未取得、未读取或含义未确认的素材不算完成。'],'items':items,'evidenceAvailability':{'downloadedImageReferencesAtCollection':downloaded,'unavailableImageReferencesAtCollection':0 if m['status']=='ready'else None,'missingAssetsAtCollection':missing,'interpretationStatus':'reviewed_available_sources','imagesIncludedInPublicData':False},'addedOn':index.get('batchDate')}
  expanded={**catalog,'posts':catalog['posts']+[p]}
  for o,a,item,h in zip(objs,analyses,items,hashes):
   r=project(a,m,defs,expanded,manifest_path.parent,item['itemId']);r['analysisSha256']=h;r['sourceBatch']=index['batchId'];r['captureScope']=clean_text(rec.get('captureScope')or'仅按实际取得并审阅的来源复核；缺失项保留。',400);new_reviews.append(r)
   enrichment['entries'].append({'itemId':item['itemId'],'postId':id,'sourcePostURL':url,'itemLabel':item['label'],'priceObservations':[],'cpuBenchmarks':[]})
  provenance.append({'postId':id,'sourceUrl':url,'manifestSha256':sha(manifest_path),'analysisSha256s':hashes,'itemIds':[i['itemId']for i in items],'archiveStatus':m['status'],'capturedAt':m.get('captured_at')})
  seen.add(id);new_posts.append(p)
 catalog['posts']=new_posts+catalog['posts'];all_items=[i for p in catalog['posts']for i in p['items']];catalog['counts']={**catalog.get('counts',{}),'posts':len(catalog['posts']),'items':len(all_items),'uniqueMachines':None,'itemsNote':'对象包括不同帖子、复测、配置阶段、套餐和主机，不等于独立机器数量。','itemTypes':dict(collections.Counter(i['itemType']for i in all_items)),'categories':dict(collections.Counter(p['category']for p in catalog['posts']))};catalog['lastIncrementalUpdate']=index['batchDate']
 refresh['entries']+=new_reviews;refresh['catalogPostCount']=len(catalog['posts']);refresh['refreshedPostCount']=len(set(r['postId']for r in refresh['entries']));refresh['refreshDate']=index['batchDate'];refresh['currentBatch']={'batchId':index['batchId'],'batchDate':index['batchDate'],'newPosts':len(new_posts),'newObjects':sum(len(p['items'])for p in new_posts),'addedPostIds':[p['postId']for p in new_posts],'sourceCategory':'https://www.nodeseek.com/categories/review','captureStatuses':dict(collections.Counter(p['archiveStatus']for p in provenance)),'imagesCaptured':sum(e['sourceMedia']['imagesCaptured']for e in new_reviews),'imagesReviewed':sum(e['sourceMedia']['imagesReviewed']for e in new_reviews)};refresh['scope']='本批仅新增已完成复核的选定首帖；保留此前目录与已发布复核，未声称重新采集全部旧帖。'
 enrichment['counts']={**enrichment.get('counts',{}),'posts':len(catalog['posts']),'items':len(all_items),'note':'本文件为历史增补层；新增完整61字段事实见skill-refresh.json，页面按层合并计算覆盖。'}
 for id,p in old_posts.items():assert next(x for x in catalog['posts']if x['postId']==id)==p
 for id,r in old_reviews.items():assert next(x for x in refresh['entries']if x['itemId']==id)==r
 out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
 for name,data in [('data.json',catalog),('enrichment.json',enrichment),('skill-refresh.json',refresh)]:
  (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 report={'batchId':index['batchId'],'sourceCommit':index.get('sourceCommit'),'oldPosts':len(old_posts),'oldObjects':len(old_item_ids),'newPosts':len(new_posts),'newObjects':sum(len(p['items'])for p in new_posts),'finalPosts':len(catalog['posts']),'finalObjects':len(all_items),'retainedPreviousSkillReviews':len(old_reviews),'currentBatch':refresh['currentBatch'],'provenance':provenance,'publicFiles':{n:sha(out/n)for n in ['data.json','enrichment.json','skill-refresh.json']}}
 (out/'incremental-public-provenance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return report

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',required=True);ap.add_argument('--selection',required=True);ap.add_argument('--index',required=True);ap.add_argument('--fields',required=True);ap.add_argument('--out',required=True);args=ap.parse_args();print(json.dumps(build(args.base,args.selection,args.index,args.fields,args.out),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
