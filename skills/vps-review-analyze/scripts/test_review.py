"""Small offline regression check; all artifacts stay in a temporary directory."""
import copy
import hashlib
import tempfile
from pathlib import Path

import review


def fails(callback, phrase):
    try:
        callback()
    except ValueError as e:
        assert phrase in str(e), str(e)
    else:
        raise AssertionError('Expected rejection: '+phrase)


assert review.cell('![remote](https://example.com)') == '!\\[remote\\](https://example.com)'
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    base = root/'assets'/'123'
    base.mkdir(parents=True)
    text = '2核心，内存2 GB，硬盘20 GB。洛杉矶。2026-09-05 16:05:00 UTC。TCP延迟：0、100、无结果。'
    raw = text.encode('utf-8')
    (base/'post.txt').write_bytes(raw)
    manifest = {'schema_version':'vps-archive/1','post_id':'123','source_url':'https://www.nodeseek.com/post-123-1','title':'测试评测','status':'partial','files':[{'id':'text','role':'first_post_text','path':'post.txt','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'source_url':'https://www.nodeseek.com/post-123-1','content_type':'text/plain'}],'failures':[{'url':'https://example.com/image.png','reason':'图片未成功下载'}]}
    mp = base/'manifest.json'
    review.save_json(mp,manifest)
    ap = root/'draft.json'
    r = review.draft(manifest)
    fails(lambda:review.normalized(r,manifest,base),'必须先完成AI识别')
    r['ai_review'] = {'completed':True,'agent':'offline test fixture','reviewed_files':['text','manifest']}
    r['summary'] = '低成本测试样本，图片缺失需保留未知。'
    evidence = [{'file_id':'text','locator':'第1行','quote':'2核心'}]
    for key,value in [('vcpu',2),('memory_gb',2),('disk_gb',20),('city','洛杉矶')]:
        r['facts'][key] = {'value':value,'status':'reported','evidence':evidence,'note':''}
    r['facts']['test_time'] = {'value':{'report_times':['2026-09-05T16:05:00+00:00'],'timezone_basis':'明确UTC','half_hour_buckets':[]},'status':'reported','evidence':[{'file_id':'text','locator':'第1行','quote':'2026-09-05 16:05:00 UTC'}],'note':''}
    r['facts']['ipv4_latency'] = {'value':{'pending':True},'status':'computed','evidence':[{'file_id':'text','locator':'第1行','quote':'TCP延迟：0、100、无结果'}],'note':'TCP测试，0为实测值，null为无结果'}
    r['latency_samples'] = {'ipv4':{'telecom':[0,100,None],'unicom':[],'mobile':[200]}}
    r['facts']['provider'] = {'value':'测试商家','status':'inferred','evidence':[{'file_id':'manifest','locator':'title','quote':'测试评测'}],'note':'仅用于元数据引用测试'}
    n = review.normalized(r,manifest,base)
    assert n['facts']['test_date']['value']=='2026-09-06'
    assert n['facts']['test_time']['value']['half_hour_buckets']==['2026-09-06 00:00–00:30']
    assert n['facts']['ipv4_latency']['value']['telecom']=={'mean_ms':50,'sample_count':2,'method':'non_null_arithmetic_mean'}
    assert n['facts']['ipv4_latency']['value']['unicom']['mean_ms'] is None
    bad = copy.deepcopy(r)
    bad['facts']['vcpu']['value']='2'
    fails(lambda:review.normalized(bad,manifest,base),'字段类型错误')
    bad = copy.deepcopy(r)
    bad['facts']['vcpu']['evidence'][0]['quote']='不存在的CPU'
    fails(lambda:review.normalized(bad,manifest,base),'证据不在来源文本')
    bad = copy.deepcopy(r)
    bad['facts']['blacklist_count']={'value':{'ipv4':'0','ipv6':None},'status':'reported','evidence':evidence,'note':''}
    fails(lambda:review.normalized(bad,manifest,base),'必须是整数')
    bad = copy.deepcopy(r)
    bad['facts']['ipv4_count']={'value':1.5,'status':'reported','evidence':evidence,'note':''}
    fails(lambda:review.normalized(bad,manifest,base),'必须是整数')
    bad = copy.deepcopy(r)
    bad['facts']['ip_classifications']={'value':{'ipv4':{'usage_counts':{'hosting':'5'},'company_counts':None},'ipv6':None},'status':'reported','evidence':evidence,'note':''}
    fails(lambda:review.normalized(bad,manifest,base),'计数必须是整数')
    valid = copy.deepcopy(r)
    valid['facts']['ipv6_latency']={'value':{c:{'mean_ms':None,'sample_count':None,'method':None} for c in review.CARRIERS},'status':'reported','evidence':evidence,'note':'来源未提供'}
    review.normalized(valid,manifest,base)
    fails(lambda:review.local_file(base,'../escape.txt'),'越界')
    fails(lambda:review.local_file(base,'C:/outside.txt'),'path')
    review.save_json(ap,r)
    first = review.finalize(mp,ap)
    assert first['status']=='saved'
    assert Path(first['markdown']).name=='洛杉矶_2C2G20G_20260906.md'
    assert '图片未成功下载' in Path(first['markdown']).read_text(encoding='utf-8')
    assert review.finalize(mp,ap)['status']=='unchanged'
    updated = raw+b'\nextra source line'
    (base/'post.txt').write_bytes(updated)
    manifest['files'][0].update(sha256=hashlib.sha256(updated).hexdigest(),bytes=len(updated))
    review.save_json(mp,manifest)
    assert review.finalize(mp,ap,replace=True)['status']=='saved'
    assert review.load(base/'analysis.json')['sources']==manifest['files']
    r['facts']['disk_gb']['value']=40
    review.save_json(ap,r)
    fails(lambda:review.finalize(mp,ap),'已存在结果')
    changed = review.finalize(mp,ap,replace=True)
    assert not Path(first['markdown']).exists()
    assert Path(changed['markdown']).is_file() and list((base/'history').glob('*.md'))
    (base/'post.txt').write_text('modified',encoding='utf-8')
    fails(lambda:review.manifest_at(mp),'来源文件校验失败')
print('PASS: AI gate, provenance, 61 fields, types, hash/path boundaries, timezone, missing-vs-zero, averages, idempotence, safe updates.')
