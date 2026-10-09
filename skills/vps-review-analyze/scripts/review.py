"""Validate AI-extracted VPS facts and render local Markdown. No model/network calls."""
import argparse
import copy
import hashlib
import html
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

CATALOG = Path(__file__).resolve().parents[1] / 'references' / 'fields.json'
BEIJING = timezone(timedelta(hours=8))
STATUSES = {'reported', 'computed', 'inferred', 'official_current', 'unknown', 'conflict'}
STATUS_NAMES = dict(zip(['reported','computed','inferred','official_current','unknown','conflict'], ['报告明示','计算','推断','当前官网','未知','冲突']))
CARRIERS = {'telecom', 'unicom', 'mobile'}


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local_file(base, relative):
    require(isinstance(relative, str) and relative, '归档文件path为空')
    path = Path(relative)
    target = (base / path).resolve()
    require(not path.is_absolute() and target.is_relative_to(base.resolve()), '归档path越界')
    require('..' not in path.parts and ':' not in relative and '\\' not in relative, '归档path应为相对POSIX路径')
    return target


def manifest_at(path):
    path = Path(path).resolve()
    m = load(path)
    require(m.get('schema_version') == 'vps-archive/1', '不支持的归档版本')
    require(m.get('status') in {'ready', 'partial'}, '归档未下载成功，不可识别')
    require(re.fullmatch(r'[0-9]+', str(m.get('post_id',''))), '无效post_id')
    require(path.name == 'manifest.json' and path.parent.name == m['post_id'] and path.parent.parent.name == 'assets', '归档必须位于assets/<post_id>/manifest.json')
    require(m.get('source_url') == f"https://www.nodeseek.com/post-{m['post_id']}-1", 'source_url不匹配')
    files = m.get('files', [])
    require(isinstance(files,list) and files, '归档没有文件')
    ids = [f['id'] for f in files]
    require(len(set(ids)) == len(ids), '重复来源文件id')
    for f in files:
        source = local_file(path.parent, f['path'])
        data = source.read_bytes()
        require(hashlib.sha256(data).hexdigest() == f['sha256'] and len(data) == f['bytes'], f"来源文件校验失败：{f['path']}")
    require(any(f['role'] in {'first_post_text','first_post_html'} for f in files), '缺首帖原文')
    return path, m


def draft(m):
    return {'schema_version':'vps-analysis/1', 'post_id':m['post_id'], 'source_url':m['source_url'],
            'ai_review':{'completed':False,'agent':'','reviewed_files':[]}, 'summary':'', 'affiliate_url':None,
            'facts':{f['id']:{'value':None,'status':'unknown','evidence':[],'note':'尚未识别'} for f in load(CATALOG)['fields']}, 'latency_samples':{}}


def numeric(value):
    return isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value) and value >= 0


def finite_tree(value):
    if isinstance(value, (int,float)) and not isinstance(value,bool):
        require(numeric(value), '数值必须为有限非负数')
    elif isinstance(value, dict):
        for v in value.values():
            finite_tree(v)
    elif isinstance(value,list):
        for v in value:
            finite_tree(v)


def normalized(result, m, base):
    r = copy.deepcopy(result)
    require(r.get('schema_version') == 'vps-analysis/1', '不支持的识别版本')
    require(r.get('post_id') == m['post_id'] and r.get('source_url') == m['source_url'], '识别结果串帖')
    catalog = load(CATALOG)['fields']
    require(set(r.get('facts',{})) == {f['id'] for f in catalog}, '识别字段必须与61字段目录一致')
    files = {f['id']:f for f in m['files']}
    require('manifest' not in files, 'manifest为保留的元数据来源id')
    files['manifest'] = {'role':'manifest'}
    ai = r.get('ai_review',{})
    reviewed = set(ai.get('reviewed_files',[]))
    require(ai.get('completed') is True and isinstance(ai.get('agent'),str) and ai['agent'].strip(), '必须先完成AI识别，不能把空模板当结果')
    require(reviewed <= files.keys(), 'AI阅读记录含不存在的文件')
    require(any(files[i]['role'] in {'first_post_text','first_post_html'} for i in reviewed), 'AI未记录读取首帖')
    require({i for i,f in files.items() if f['role']=='image'} <= reviewed, '本帖图片尚未全部核对')
    require(isinstance(r.get('summary'),str) and r['summary'].strip(), '缺少AI简评')
    aff = r.get('affiliate_url')
    if aff is not None:
        u = urlsplit(aff)
        require(u.scheme in {'https','http'} and u.hostname and not u.username and not u.password and not re.search(r'[\s<>]',aff), 'aff链接无效')
    for spec in catalog:
        fact = r['facts'][spec['id']]
        value, status = fact.get('value'), fact.get('status')
        require(status in STATUSES, f"无效字段状态：{spec['id']}")
        evidence = fact.get('evidence')
        require(isinstance(evidence,list) and isinstance(fact.get('note'),str), f"字段缺少证据/说明：{spec['id']}")
        if status in {'unknown','conflict'}:
            require(value is None and fact['note'].strip(), f"未知或冲突应为null且注明原因：{spec['id']}")
        else:
            require(value is not None and evidence, f"字段无值或无证据：{spec['id']}")
            kind = spec['value_type']
            require((kind=='number' and numeric(value)) or (kind=='string' and isinstance(value,str) and bool(value.strip())) or (kind=='object' and isinstance(value,dict) and bool(value)), f"字段类型错误：{spec['id']}")
            finite_tree(value)
        for e in evidence:
            require(e.get('file_id') in reviewed and isinstance(e.get('locator'),str) and e['locator'].strip() and isinstance(e.get('quote'),str) and e['quote'].strip(), f"证据无已读来源/位置/原文：{spec['id']}")
            f = files[e['file_id']]
            if f['role']=='manifest':
                require(e['locator'] in {'title','author','source_url'} and isinstance(m.get(e['locator']),str) and ''.join(e['quote'].split()) in ''.join(m[e['locator']].split()), f"元数据证据不匹配：{spec['id']}")
            if f['role'] in {'first_post_text','report_text'}:
                text = local_file(base,f['path']).read_text(encoding='utf-8-sig')
                require(''.join(e['quote'].split()) in ''.join(text.split()), f"证据不在来源文本内：{spec['id']}")
    facts = r['facts']
    for key in ['ip_usage_location','ip_registered_location','asn','ip_organization','ip_origin','ip_classifications','risk_counts','blacklist_count','flagged_count','unlock_count','native_count','smtp25_outbound','smtp25_inbound']:
        value = facts[key]['value']
        if value is not None:
            require(set(value)=={'ipv4','ipv6'}, f'{key}必须分ipv4/ipv6，未知用null')
    def count(value):
        return value is None or (type(value) is int and value>=0)
    for key in ['blacklist_count','flagged_count','unlock_count','native_count']:
        value = facts[key]['value']
        require(value is None or all(count(v) for v in value.values()), f'{key}必须是整数/null')
    for key in ['vcpu','ipv4_count']:
        require(count(facts[key]['value']), f'{key}必须是整数/null')
    classifications = facts['ip_classifications']['value']
    if classifications is not None:
        for group in classifications.values():
            require(group is None or (isinstance(group,dict) and set(group)=={'usage_counts','company_counts'}), 'IP分类缺少usage_counts/company_counts')
            if group is not None:
                require(all(c is None or (isinstance(c,dict) and all(count(n) for n in c.values())) for c in group.values()), 'IP分类计数必须是整数/null')
    risks = facts['risk_counts']['value']
    if risks is not None:
        for value in risks.values():
            require(value is None or (isinstance(value,dict) and set(value)=={'very_low','low','medium','high','very_high','suspicious'} and all(count(v) for v in value.values())), 'risk_counts风险等级或计数错误')
    for key,allowed in [('ip_origin',{'native','broadcast'}),('smtp25_inbound',{'available','blocked'}),('smtp25_outbound',{'available','blocked'})]:
        value = facts[key]['value']
        require(value is None or all(v is None or v in allowed for v in value.values()), f'{key}分类错误')
    overcommit = facts['memory_overcommit']['value']
    require(overcommit is None or (set(overcommit)=={'balloon','ksm'} and all(v in {'detected','not_detected',None} for v in overcommit.values())), 'memory_overcommit结构错误')
    for key in ['routes_to_server','routes_from_server']:
        value = facts[key]['value']
        if value is not None:
            require(set(value)=={'ipv4','ipv6'}, f'{key}缺协议分组')
            for group in value.values():
                require(group is None or (isinstance(group,dict) and set(group)==CARRIERS), f'{key}缺三网分组')
                require(group is None or all(v is None or isinstance(v,str) for v in group.values()), f'{key}线路应为字符串/null')
    price = facts['monthly_price']['value']
    if price is not None:
        require(set(price)=={'amount','currency'} and (price['amount'] is None or numeric(price['amount'])) and (price['currency'] is None or (isinstance(price['currency'],str) and re.fullmatch('[A-Z]{3}',price['currency']))), '月价需要amount及三位货币代码')
    for protocol in ['ipv4','ipv6']:
        fact = facts[f'{protocol}_latency']
        if fact['status']=='computed':
            samples = r.get('latency_samples',{}).get(protocol)
            require(isinstance(samples,dict) and set(samples)==CARRIERS, '计算均值须提供三网原始样本')
            value = {}
            for carrier, samples_for_carrier in samples.items():
                require(isinstance(samples_for_carrier,list) and all(x is None or numeric(x) for x in samples_for_carrier), '延迟样本须为数字/null数组')
                valid = [x for x in samples_for_carrier if x is not None]
                value[carrier] = {'mean_ms':round(sum(valid)/len(valid),2) if valid else None,'sample_count':len(valid),'method':'non_null_arithmetic_mean'}
            fact['value'] = value
        value = fact['value']
        if value is not None:
            require(set(value)==CARRIERS, f'{protocol}延迟缺三网分组')
            for v in value.values():
                require(v is None or (isinstance(v,dict) and set(v)=={'mean_ms','sample_count','method'} and (v['mean_ms'] is None or numeric(v['mean_ms'])) and (v['sample_count'] is None or (type(v['sample_count']) is int and v['sample_count']>=0)) and (v['method'] is None or (isinstance(v['method'],str) and v['method']))), '延迟对象结构错误')
    time_fact = facts['test_time']
    if time_fact['value'] is not None:
        value = time_fact['value']
        require(isinstance(value.get('report_times'),list) and value['report_times'] and isinstance(value.get('timezone_basis'),str) and value['timezone_basis'].strip(), '测试时间缺原时区依据')
        times = [datetime.fromisoformat(x.replace('Z','+00:00')) for x in value['report_times']]
        require(all(t.utcoffset() is not None for t in times), '测试时间必须有UTC偏移')
        times = sorted(t.astimezone(BEIJING) for t in times)
        value['report_times'] = [t.isoformat() for t in times]
        buckets = []
        for t in times:
            start = t.replace(minute=(t.minute//30)*30,second=0,microsecond=0)
            end = start+timedelta(minutes=30)
            label = start.strftime('%Y-%m-%d %H:%M')+'–'+end.strftime('%H:%M' if end.date()==start.date() else '%Y-%m-%d %H:%M')
            if label not in buckets:
                buckets.append(label)
        value['half_hour_buckets'] = buckets
        date_fact = facts['test_date']
        earliest = times[0].strftime('%Y-%m-%d')
        require(date_fact['value'] is None or date_fact['value']==earliest, '测试日期与北京时间不一致')
        if date_fact['status']=='unknown':
            date_fact.update(value=earliest,status='computed',evidence=copy.deepcopy(time_fact['evidence']),note='由最早报告时间换算北京时间日期')
    date = facts['test_date']['value']
    if date is not None:
        require(re.fullmatch(r'\d{4}-\d{2}-\d{2}',date), '日期必须为YYYY-MM-DD')
        datetime.strptime(date,'%Y-%m-%d')
    return r


def confirmed(r, field):
    f = r['facts'][field]
    return None if f['status'] in {'unknown','conflict','official_current'} else f['value']


def safe_name(value):
    text = str(value) if value is not None else '未知'
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',text).strip(' .')[:60] or '未知'


def filename(r):
    parts = [confirmed(r,key) for key in ['city','vcpu','memory_gb','disk_gb','test_date']]
    city,cpu,memory,disk,date = [safe_name(x if not isinstance(x,float) else format(x,'g')) for x in parts]
    return f'{city}_{cpu}C{memory}G{disk}G_{date.replace("-","")}.md'


def cell(value):
    text = '未知' if value is None else json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else str(value)
    text = re.sub(r'([\\`*_\[\]{}])',r'\\\1',html.escape(text))
    return text.replace('|','&#124;').replace('\n','<br>')


def render(r,m):
    lines = ['---']
    for key,value in {'schema_version':'vps-analysis/1','post_id':r['post_id'],'source_url':r['source_url'],'city':confirmed(r,'city'),'vcpu':confirmed(r,'vcpu'),'memory_gb':confirmed(r,'memory_gb'),'disk_gb':confirmed(r,'disk_gb'),'test_date':confirmed(r,'test_date'),'affiliate_url':r['affiliate_url']}.items():
        lines.append(f'{key}: {json.dumps(value,ensure_ascii=False)}')
    lines += ['---','',f"# {cell(m.get('title') or 'VPS评测 '+r['post_id'])}",'',f"来源：[首帖]({r['source_url']})。归档状态：{m['status']}。仅整理首帖。",'']
    if m.get('capture_note'):
        lines += ['采集说明：'+cell(m['capture_note']),'']
    lines += ['## 简评','',cell(r['summary']),'','## 数据','', '| 类别 | 字段 | 值 | 口径 | 说明 |','| --- | --- | --- | --- | --- |']
    for spec in load(CATALOG)['fields']:
        f = r['facts'][spec['id']]
        unit = f" {spec['unit']}" if spec.get('unit') and isinstance(f['value'],(int,float)) else ''
        lines.append(f"| {cell(spec['group'])} | {cell(spec['label'])} | {cell(f['value'])}{unit} | {STATUS_NAMES[f['status']]} | {cell(f['note'])} |")
    lines += ['','## 原始材料','']
    for f in m['files']:
        link = quote(f"assets/{m['post_id']}/{f['path']}",safe='/')
        prefix = '!' if f['role']=='image' else ''
        lines += [f"{prefix}[{cell(f['id'])}]({link})",'']
    if m.get('failures'):
        lines += ['## 下载缺失','']+[f"- {cell(x['url'])}：{cell(x['reason'])}" for x in m['failures']]+['']
    lines += [f"字段证据：[结构化结果](assets/{m['post_id']}/analysis.json)，[归档清单](assets/{m['post_id']}/manifest.json)。",'','## 购买链接','']
    if r['affiliate_url']:
        lines += [f"[商家购买链接]({quote(r['affiliate_url'],safe=':/?=&%#+@;,$!~*-._')})",'','此链接为推广链接，通过该链接购买可能产生佣金。']
    else:
        lines += ['未提供用户自己的推广链接。']
    return '\n'.join(lines)+'\n'


def save_json(path,value):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temp.replace(path)


def finalize(manifest_path, analysis_path, replace=False):
    path,m = manifest_at(manifest_path)
    r = normalized(load(analysis_path),m,path.parent)
    root = path.parent.parent.parent
    dest = root/filename(r)
    def owned(target):
        sections = target.read_text(encoding='utf-8').split('---',2)
        return len(sections)==3 and f'\npost_id: "{m["post_id"]}"\n' in sections[1]
    if dest.exists() and not owned(dest):
        dest = dest.with_name(dest.stem+f'_post-{m["post_id"]}.md')
    require(not dest.exists() or owned(dest), '同名文件属于其他内容，不覆盖')
    result_path = path.parent/'analysis.json'
    previous = load(result_path) if result_path.exists() else None
    metadata = {k:m.get(k) for k in ['title','author','captured_at','capture_method','capture_note']}
    if previous and all(previous.get(k)==v for k,v in r.items()) and previous.get('sources')==m['files'] and previous.get('source_metadata')==metadata and previous.get('archive_status')==m['status'] and previous.get('download_failures')==m.get('failures',[]) and dest.exists() and dest.read_text(encoding='utf-8')==render(r,m):
        return {'status':'unchanged','markdown':str(dest),'analysis':str(result_path)}
    old_md = local_file(root,previous['markdown_path']) if previous else None
    require(old_md is None or (old_md.parent==root and old_md.suffix=='.md'), '旧结果路径不是根目录Markdown')
    require(old_md is None or not old_md.exists() or owned(old_md), '旧Markdown不属于本帖，停止替换')
    existing_paths = {p for p in [dest,result_path,old_md] if p is not None and p.exists()}
    require(not existing_paths or replace, '已存在结果，更新需--replace；旧结果将备份')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for existing in existing_paths:
        backup = path.parent/'history'/f'{stamp}-{existing.name}'
        backup.parent.mkdir(exist_ok=True)
        backup.write_bytes(existing.read_bytes())
    content = render(r,m)
    r.update(archive_status=m['status'],download_failures=m.get('failures',[]),generated_at=datetime.now(timezone.utc).isoformat(),markdown_path=dest.name,sources=m['files'],source_metadata=metadata,program_version=1)
    save_json(result_path,r)
    temp = dest.with_suffix('.md.tmp')
    temp.write_text(content,encoding='utf-8')
    temp.replace(dest)
    if old_md is not None and old_md!=dest and old_md.exists():
        old_md.unlink()  # Old generated filename has a recoverable history copy.
    return {'status':'saved','markdown':str(dest),'analysis':str(result_path)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['init','finalize'])
    p.add_argument('manifest')
    p.add_argument('--output')
    p.add_argument('--analysis')
    p.add_argument('--replace',action='store_true')
    args = p.parse_args()
    try:
        if args.command=='init':
            require(args.output and not Path(args.output).exists(), 'init需要不存在的--output路径')
            _,m = manifest_at(args.manifest)
            save_json(args.output,draft(m))
            print(json.dumps({'status':'needs_ai','draft':args.output},ensure_ascii=False))
        else:
            require(args.analysis, 'finalize需要--analysis')
            print(json.dumps(finalize(args.manifest,args.analysis,args.replace),ensure_ascii=False))
    except (ValueError,KeyError,TypeError,OSError) as e:
        p.exit(1,f'Error: {e}\n')


if __name__=='__main__':
    main()
