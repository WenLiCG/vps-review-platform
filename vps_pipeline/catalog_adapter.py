"""Pure v5 adapter for pre-sanitized pipeline records; no I/O or networking.

Inputs are public facts only. This module never accepts archives or evidence.
The caller remains responsible for upstream allowlist projection and mapping.
"""
from __future__ import annotations
import copy
from collections import Counter
import datetime as dt
import math
import re

FILES = ('data.json', 'enrichment.json', 'skill-refresh.json', 'image-evidence.json', 'filter-spec.json')
STATUSES = {'reported','computed','inferred','official_current','unknown','conflict'}
KINDS = {'measured_vps','advertised_plan','review_configuration_version','measured_host'}
MAPPING = {'test_time':'test_time_bjt','ip_usage_location':'usage_location','ip_registered_location':'registration_location','ip_organization':'organization','monthly_transfer_tb':'monthly_traffic','transfer_billing':'traffic_billing','sysbench_single_score':'sysbench_cpu_single','sysbench_multi_score':'sysbench_cpu_multi','geekbench_single_score':'geekbench_single','geekbench_multi_score':'geekbench_multi','memory_gb':'memory_capacity','memory_overcommit':'memory_overcommit_indicators','memory_read_mbps':'sysbench_memory_read','memory_write_mbps':'sysbench_memory_write','disk_gb':'disk_capacity','port_bandwidth_mbps':'port_bandwidth','ip_connectivity':'ipv4_connectivity_type','ipv6_connectivity':'ipv6_availability','routes_to_server':'outbound_routes','routes_from_server':'return_routes','ipv4_latency':'ipv4_ping','ipv6_latency':'ipv6_ping','ip_origin':'native_ip_status'}
for workload in ('rnd4k_q1','rnd4k_q32','seq1m_q1','seq1m_q8'):
    for operation in ('read','write'):
        MAPPING[f'disk_{workload}_{operation}_mbps'] = f'disk_{workload}_{operation}'
NESTED_KEYS = set('ipv4 ipv6 telecom unicom mobile amount currency country continent region report_times timezone_basis half_hour_buckets balloon ksm mean_ms sample_count method usage_counts company_counts hosting business residential education government organization isp other unknown very_low low medium high very_high suspicious'.split())
BAD_TEXT = re.compile(r'https?://|www\.|mailto:|data:|javascript:|<|>|[/\\](?:workspace|home|Users|tmp)[/\\]|[A-Za-z]:\\|\b(?:password|passwd|secret|token|api.key|bearer|cookie)\b|\b(?:\d{1,3}\.){3}\d{1,3}\b|[^\s@]+@[^\s@]+\.[^\s@]+',re.I)
ID = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')


def number(value):
    return type(value) in (int,float) and math.isfinite(value) and value >= 0


def label(value,limit=180):
    if not isinstance(value,str) or not value.strip() or len(value)>limit or BAD_TEXT.search(value):
        raise ValueError('unsafe_public_label')
    # Reject IPv6 literal-like strings; timestamps and ordinary model punctuation remain allowed.
    if re.search(r'(?:[a-fA-F0-9]{0,4}:){2,}[a-fA-F0-9:]{0,4}',value):
        raise ValueError('unsafe_public_label')
    return value.strip()


def safe_value(value,depth=0):
    if depth>5: raise ValueError('nested_public_value')
    if value is None or type(value) is bool: return value
    if type(value) in (int,float):
        if not math.isfinite(value): raise ValueError('nonfinite_public_value')
        return value
    if isinstance(value,str):
        # ISO report times are allowed only in offset form; validate later as well.
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})',value): return value
        return label(value,300)
    if isinstance(value,list):
        if len(value)>100: raise ValueError('oversize_public_value')
        return [safe_value(v,depth+1) for v in value]
    if isinstance(value,dict):
        if set(value)-NESTED_KEYS: raise ValueError('unexpected_public_value_key')
        return {k:safe_value(v,depth+1) for k,v in value.items()}
    raise ValueError('invalid_public_value')


def identity(record):
    post=str(record.get('post_id',''))
    if not re.fullmatch(r'[1-9][0-9]{0,19}',post): raise ValueError('invalid_post_id')
    url=f'https://www.nodeseek.com/post-{post}-1'
    if record.get('source_url')!=url: raise ValueError('source_identity_mismatch')
    rid=record.get('record_id')
    if not isinstance(rid,str) or not ID.fullmatch(rid): raise ValueError('invalid_record_id')
    if record.get('record_kind') not in {'accepted','legacy_imported'}: raise ValueError('invalid_record_kind')
    if record.get('archive_status') not in {'ready','partial'}: raise ValueError('invalid_archive_status')
    return post,url,rid


def review_row(record,item_id,definitions):
    post,url,rid=identity(record)
    defs={f['id']:f for f in definitions['fields']}
    facts=record.get('facts')
    if not isinstance(facts,dict) or set(facts)!=set(defs) or len(defs)!=61: raise ValueError('expected_61_fields')
    rows=[];by_field={};cpu=[];routes=[];times=[]
    for fid,definition in defs.items():
        f=facts[fid]
        if not isinstance(f,dict) or f.get('status') not in STATUSES: raise ValueError('invalid_fact_status')
        status=f['status'];projection=f.get('projection_status')
        if projection not in {'unchanged','partial','redacted'}: raise ValueError('invalid_projection_status')
        value=safe_value(f.get('value'))
        if status in {'unknown','conflict'} and value is not None: raise ValueError('unknown_conflict_nonnull')
        if value is not None:
            t=definition['value_type']
            if t=='number' and not number(value): raise ValueError('invalid_number')
            if t=='string' and not isinstance(value,str): raise ValueError('invalid_string')
            if t=='object' and not isinstance(value,dict): raise ValueError('invalid_object')
        eligible=value is not None and projection=='unchanged' and status in {'reported','computed'}
        if fid in {'vcpu','ipv4_count'} and value is not None and (not number(value) or value!=int(value) or (fid=='vcpu' and value<1)):raise ValueError('invalid_integer')
        if fid=='monthly_price' and value is not None:
            if not number(value.get('amount')) or value.get('currency') not in {'USD','EUR','CNY','CAD','JPY','GBP','AUD','HKD'}:raise ValueError('invalid_monthly_price')
            eligible=projection=='unchanged' and status in {'reported','computed'}
        if fid in {'sysbench_single_score','sysbench_multi_score','memory_read_mbps','memory_write_mbps','ipv4_latency','ipv6_latency','ip_origin','geekbench_single_score','geekbench_multi_score','routes_to_server','routes_from_server'} or fid.startswith('hardware_') or (fid.startswith('disk_') and fid.endswith('_mbps')):eligible=False
        note='已接受分析的安全字段投影；核读声明不等于独立验证。' if record['record_kind']=='accepted' else '历史分析安全投影；未在迁移时重新核读。'
        if projection!='unchanged':note+='部分内容因公开投影被保留或遮蔽，不用于该字段筛选。'
        row={'skillFieldId':fid,'fieldKey':MAPPING.get(fid,fid),'label':definition['label'],'value':value,'unit':definition['unit'],'status':status,'projectionStatus':projection,'filterEligible':eligible,'note':note,'evidenceRefs':[],'comparisonKey':None}
        if fid=='port_bandwidth_mbps' and number(value):row.update(normalizedValue=value/1000,normalizedUnit='Gbps')
        rows.append(row);by_field[fid]=row
    for obs in record.get('safe_observations',[]):
        fid=obs.get('field_id');f=by_field.get(fid)
        if fid not in {'memory_gb','disk_gb'} or not f or f['status'] in {'unknown','conflict'}:continue
        raw=obs.get('original_value');unit=obs.get('original_unit')
        if obs.get('value')==f['value'] and obs.get('status')==f['status'] and number(raw) and unit in {'GB','GiB','MB','MiB','TB','TiB','G','M','T'}:
            f['rawDisplay']={'value':raw,'unit':unit,'displayOnly':True}
    for obs in record.get('benchmark_observations',[]):
        fid=obs.get('field_id');f=by_field.get(fid)
        if not f or f['projectionStatus']!='unchanged' or f['status'] not in {'reported','computed'}:continue
        if obs.get('kind')!='measurement' or obs.get('status') not in {'reported','computed'} or obs.get('score')!=f['value'] or not number(obs.get('score')):continue
        version=str(obs.get('version',''));tool=obs.get('tool')
        if tool=='Geekbench' and version in {'5','6'} and fid in {'geekbench_single_score','geekbench_multi_score'}:
            metric='single' if fid=='geekbench_single_score' else 'multi'
            if obs.get('metric')!=metric:continue
            key=f'geekbench:{version}:{metric}'
            cpu.append({'tool':'Geekbench','majorVersion':int(version),'metric':metric,'score':obs['score'],'unit':'score','status':f['status'],'comparisonEligible':True,'comparisonKey':key,'evidenceRefs':[]})
            f.update(filterEligible=True,comparisonKey=key)
        elif tool=='HardwareQuality' and obs.get('metric')==fid.removeprefix('hardware_').removesuffix('_score') and re.fullmatch(r'v\d{4}-\d{2}-\d{2}',version) and fid.startswith('hardware_'):
            f.update(filterEligible=True,comparisonKey=f'HardwareQuality:{version}')
    # Only explicit scoped observations can become route filter rows; aggregate fact text cannot.
    for obs in record.get('network_observations',[]):
        family=obs.get('family');direction=obs.get('direction');operator=obs.get('operator');transport=obs.get('transport')
        if obs.get('kind')!='measurement' or obs.get('status') not in {'reported','computed'}:continue
        if family not in {'IPv4','IPv6'} or direction not in {'return','outbound'} or operator not in {'电信','联通','移动'} or transport not in {'TCP','UDP','ICMP',None}:continue
        labels=obs.get('reportedLabels')
        if not isinstance(labels,list) or not labels:continue
        if any(not isinstance(x,str) or not re.fullmatch(r'163|4837|9929|10099|CMI|CMIN2|CN2|CN2\s?GIA|CN2\s?GT|CTG\s?GIA',x,re.I) for x in labels):continue
        route_fact=by_field['routes_from_server' if direction=='return' else 'routes_to_server']
        if route_fact['status'] not in {'reported','computed'} or route_fact['projectionStatus']!='unchanged' or not isinstance(route_fact['value'],dict):continue
        carrier_key={'电信':'telecom','联通':'unicom','移动':'mobile'}[operator]
        carrier_values=route_fact['value'].get(family.lower())
        expected=carrier_values.get(carrier_key) if isinstance(carrier_values,dict) else None
        canonical=lambda text:re.sub(r'\s+','',text).upper()
        if not isinstance(expected,str) or any(canonical(value)!=canonical(expected) for value in labels):continue
        city=label(obs['targetCity']) if obs.get('targetCity') else None
        routes.append({'family':family,'direction':direction,'operator':operator,'transport':transport,'targetCity':city,'reportedLabels':list(dict.fromkeys(labels)),'rawLabel':' / '.join(labels),'filterEligible':True,'partialCoverage':True,'status':obs['status'],'evidenceRefs':[]})
    time=by_field['test_time']
    if time['filterEligible']:
        value=time['value']
        if not value.get('timezone_basis') or not isinstance(value.get('report_times'),list):raise ValueError('unproven_timezone')
        for raw in value['report_times']:
            t=dt.datetime.fromisoformat(raw.replace('Z','+00:00'))
            if t.tzinfo is None:raise ValueError('naive_timestamp')
            times.append({'raw':raw,'beijing':t.astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat(),'timezoneBasis':value['timezone_basis'],'status':time['status'],'evidenceRefs':[]})
    if not times and time['status'] in {'reported','computed'} and time['projectionStatus']!='redacted' and isinstance(time['value'],dict):
        declared_times=time['value'].get('report_times')
        for observation in record.get('time_observations',[]):
            if observation.get('field_id')!='test_time' or observation.get('status')!=time['status'] or observation.get('timezone_basis_declared') is not True:continue
            if not isinstance(declared_times,list) or not declared_times or observation.get('report_times')!=declared_times:continue
            for raw in declared_times:
                t=dt.datetime.fromisoformat(raw.replace('Z','+00:00'))
                if t.tzinfo is None:raise ValueError('naive_timestamp')
                if any(previous['raw']==raw for previous in times):continue
                times.append({'raw':raw,'beijing':t.astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat(),'timezoneBasis':'来源提供带偏移时间；时区判断属于提交者声明。','status':time['status'],'evidenceRefs':[]})
    version=record.get('analysis_version')
    if version is not None and (type(version) is not int or version<1):raise ValueError('invalid_analysis_version')
    return {'itemId':item_id,'postId':post,'sourceUrl':url,'pipelineRecordStatus':record['record_kind'],'pipelineRecordId':rid,'pipelineAnalysisVersion':version,'captureStatus':record['archive_status'],'analyzedAt':None,'missingAssetCount':None,'summary':'已入库结构化分析；原始素材与核读记录保存在本机私有归档。','fieldObservations':rows,'cpuBenchmarks':cpu,'routeObservations':routes,'confirmedReportTimes':times}


def empty_item(post,url,item_id,kind,title):
    return {'itemId':item_id,'postId':post,'sourceUrl':url,'itemType':kind,'label':title,'product':None,'vendor':None,'location':{'country':None,'city':None,'region':None},'configuration':{'vcpu':None,'cpuModel':None,'memoryValue':None,'memoryUnit':None,'diskValue':None,'diskUnit':None},'trafficQuota':{'value':None,'unit':None,'period':None,'direction':None},'price':{'raw':None,'amount':None,'currency':None,'billingPeriod':None},'testedAt':{'primary':{'raw':None,'timezone':None,'beijing':None,'status':'unknown'},'reports':[],'datesBeijing':[],'dateUncertain':True},'network':{'routeObservations':[],'reportedRouteTags':[],'claimedRouteTags':[],'filterRouteTags':[]},'bandwidthClaims':[],'summary':'结构化分析记录；未知与缺失项保留。','evidence':{'sourceUrl':url,'basis':'已接受分析的安全投影。'}}


def build_catalog(baseline,records,definitions,exported_at):
    """Return the five v5 data payloads plus facts-only catalog-integration.json.

    The caller copies unchanged UI assets separately. Baseline objects are never
    mutated, and records without a confirmed unambiguous mapping are pending.
    """
    if not isinstance(exported_at,str) or dt.datetime.fromisoformat(exported_at.replace('Z','+00:00')).tzinfo is None:raise ValueError('export_time_requires_offset')
    result={name:copy.deepcopy(baseline[name]) for name in FILES}
    data=result['data.json'];refresh=result['skill-refresh.json'];extra=result['enrichment.json']
    posts={p['postId']:p for p in data['posts']};items={i['itemId']:i for p in data['posts'] for i in p['items']}
    review_index={r['itemId']:n for n,r in enumerate(refresh['entries'])}
    baseline_posts=len(posts);baseline_objects=len(items);pending=[];linked=[];seen=set();accepted=set();legacy=set()
    for record in records:
        try:
            post,url,rid=identity(record)
            if rid in seen:raise ValueError('duplicate_record_id')
            seen.add(rid)
            previous_post=posts.get(post);mapping=record.get('catalog_mapping')
            # Historical overlap is an annotation only. Do not replace richer old public facts.
            if record['record_kind']=='legacy_imported' and previous_post and not mapping:
                if len(previous_post['items'])!=1:raise ValueError('mapping_required_for_multiple_objects')
                item_id=previous_post['items'][0]['itemId'];review_row(record,item_id,definitions);index=review_index.get(item_id)
                if index is not None:
                    row=refresh['entries'][index]
                    row.setdefault('pipelineLegacyLinks',[])
                    if rid not in row['pipelineLegacyLinks']:row['pipelineLegacyLinks'].append(rid)
                legacy.add(post);linked.append({'postId':post,'itemId':item_id,'recordId':rid,'recordKind':'legacy_imported','action':'annotated_baseline'})
                continue
            if not isinstance(mapping,dict) or mapping.get('confirmed') is not True:raise ValueError('confirmed_mapping_required')
            item_id=mapping.get('item_id');count=mapping.get('post_object_count');kind=mapping.get('entry_kind')
            if type(mapping.get('reviewed_object_count')) is not int or mapping.get('reviewed_object_count')!=1 or type(count) is not int or kind not in KINDS:raise ValueError('invalid_object_mapping')
            if previous_post:
                if count!=len(previous_post['items']) or item_id not in {i['itemId'] for i in previous_post['items']}:raise ValueError('mapping_identity_mismatch')
                if record['record_kind']=='legacy_imported':raise ValueError('historical_overwrite_not_allowed')
                if items[item_id]['itemType']!=kind:raise ValueError('mapping_kind_mismatch')
            elif count!=1 or item_id!=post+'-1':raise ValueError('new_post_requires_single_explicit_object')
            row=review_row(record,item_id,definitions)
            title=label(mapping.get('public_label'))
            if not previous_post:
                item=empty_item(post,url,item_id,kind,title)
                newpost={'postId':post,'sourceUrl':url,'category':'review','label':title,'summary':item['summary'],'warnings':[],'items':[item],'evidenceAvailability':{'downloadedImageReferencesAtCollection':None,'unavailableImageReferencesAtCollection':None,'interpretationStatus':'submitted_analysis','imagesIncludedInPublicData':False},'addedOn':str(exported_at)[:10]}
                data['posts'].append(newpost);posts[post]=newpost;items[item_id]=item
                extra['entries'].append({'itemId':item_id,'postId':post,'sourcePostURL':url,'priceObservations':[],'cpuBenchmarks':[]})
            index=review_index.get(item_id)
            if index is not None:
                old=refresh['entries'][index]
                if old.get('pipelineRecordId')==rid:
                    linked.append({'postId':post,'itemId':item_id,'recordId':rid,'recordKind':record['record_kind'],'action':'unchanged'})
                else:
                    oldcopy=copy.deepcopy(old);history=oldcopy.pop('reviewHistory',[])
                    row['reviewHistory']=history+[oldcopy]
                    refresh['entries'][index]=row
            else:
                review_index[item_id]=len(refresh['entries']);refresh['entries'].append(row)
            (accepted if record['record_kind']=='accepted' else legacy).add(post)
            linked.append({'postId':post,'itemId':item_id,'recordId':rid,'recordKind':record['record_kind'],'action':'current_overlay'})
        except (ValueError,TypeError,KeyError,AttributeError) as error:
            # Expose stable reason codes only; never echo potentially private input.
            reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[a-z_]+',str(error)) else 'invalid_public_record'
            rid=record.get('record_id') if isinstance(record,dict) else None
            pending.append({'recordId':rid if isinstance(rid,str) and ID.fullmatch(rid) else None,'reason':reason,'status':'pending_catalog'})
    meta={'schemaVersion':'vps-pipeline-catalog/1','baselinePosts':baseline_posts,'baselineObjects':baseline_objects,'acceptedPosts':len(accepted),'legacyImportedPosts':len(legacy),'pendingRecords':len(pending),'exportedAt':exported_at}
    refresh['pipelineIntegration']=meta
    data['counts']['posts']=len(posts);data['counts']['items']=len(items);data['counts']['uniqueMachines']=None
    data['counts']['itemTypes']=dict(Counter(i['itemType']for i in items.values()));data['counts']['categories']=dict(Counter(p['category']for p in posts.values()))
    if len(posts)!=baseline_posts:extra['counts']={**extra.get('counts',{}),'posts':len(posts),'items':len(items)}
    refresh['catalogPostCount']=len(posts);refresh['refreshedPostCount']=len({r['postId'] for r in refresh['entries']})
    result['catalog-integration.json']={**meta,'linkedRecords':linked,'pendingRecordsDetail':pending}
    return result
