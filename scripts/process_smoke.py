from pathlib import Path
import base64, concurrent.futures, copy, hashlib, http.client, io, json, os, platform, selectors, signal, socket, sqlite3, subprocess, sys, time, zipfile
SRC=Path(__file__).resolve().parents[1]
BASE=SRC/'var-process-tests'
BASE.mkdir(exist_ok=True)
RUN_NAME=sys.argv[1] if len(sys.argv)>1 else 'run-'+str(time.time_ns())
RUN=BASE/RUN_NAME
RUN.mkdir(exist_ok=True)
DATA=RUN/'private'
RESULTS=BASE/'results'
RESULTS.mkdir(exist_ok=True)
checks=[]; exchanges=[]; processes=[]
def check(name, condition, details=None):
    checks.append({'name':name,'passed':bool(condition),'details':details})
    if not condition: raise AssertionError(name+': '+str(details))
def cli(*args,expected=0):
    proc=subprocess.run([sys.executable,'-m','vps_pipeline','--data',str(DATA),*args],cwd=SRC,capture_output=True,text=True,timeout=30)
    check('CLI '+' '.join(args[:1])+' exit '+str(expected),proc.returncode==expected,proc.stderr[-800:] if proc.returncode!=expected else None)
    if expected: return proc
    return json.loads(proc.stdout)
def start():
    proc=subprocess.Popen([sys.executable,'-m','vps_pipeline','--data',str(DATA),'serve','--host','127.0.0.1','--port','0'],cwd=SRC,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    processes.append(proc)
    # stdout startup lines only; token is retained in memory and never recorded.
    sel=selectors.DefaultSelector(); sel.register(proc.stdout,selectors.EVENT_READ)
    if not sel.select(10): raise RuntimeError('Server did not print startup within 10s')
    url=proc.stdout.readline().strip().split(': ',1)[1]
    token=proc.stdout.readline().strip().split(': ',1)[1]
    proc.stdout.readline(); sel.close()
    from urllib.parse import urlsplit
    port=urlsplit(url).port
    check('CLI serves loopback',url.startswith('http://127.0.0.1:') and proc.poll() is None)
    return proc,port,token

def stop(proc):
    proc.send_signal(signal.SIGINT); proc.wait(timeout=10)
    check('Server SIGINT clean exit',proc.returncode==0)
    err=proc.stderr.read();check('No server traceback',not err,err[-800:])
def request(port,token,method,path,payload=None,status=200,extra=None,authenticated=True):
    headers={'X-VPS-Token':token} if authenticated else {}
    body=None
    if payload is not None:
        headers['Content-Type']='application/json'
        body=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode()
    headers.update(extra or {})
    c=http.client.HTTPConnection('127.0.0.1',port,timeout=10)
    try:
        c.request(method,path,body=body,headers=headers)
        r=c.getresponse();raw=r.read(); rh=dict(r.getheaders())
    finally:c.close()
    exchanges.append({'method':method,'path':path,'status':r.status,'expected':status,'bytes':len(raw),'headers':{k:v for k,v in rh.items() if k in ['Content-Type','Cache-Control','X-Content-Type-Options','Content-Disposition']}})
    check(method+' '+path+' HTTP '+str(status),r.status==status,raw[:400].decode(errors='replace') if r.status!=status else None)
    if rh.get('Content-Type','').startswith('application/json'):return json.loads(raw),rh
    return raw,rh

def package(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        metadata=json.loads(z.read('package.json'));e=json.loads(z.read('envelope.json'));m=json.loads(z.read(metadata['manifest']))
        check('Manifest hash matches package',hashlib.sha256(z.read(metadata['manifest'])).hexdigest()==e['archive_sha256'])
        check('61 facts in work package',len(e['analysis']['facts'])==61)
        check('Work package is honestly pending AI',metadata['status']=='needs_ai' and e['analysis']['ai_review']['completed'] is False)
        for f in m['files']:
            raw=z.read('assets/'+m['post_id']+'/'+f['path'])
            check('Evidence SHA-256 '+f['id'],hashlib.sha256(raw).hexdigest()==f['sha256'])
            check('No replies/sidebar '+f['id'],b'REPLY_MUST_NOT_BE_ARCHIVED' not in raw and b'SIDEBAR_MUST_NOT_BE_ARCHIVED' not in raw)
    return e,m,metadata

def synthetic(e,m):
    e=copy.deepcopy(e); declaration='SYNTHETIC PROCESS TEST; NO REAL AI OR IMAGE REVIEW'
    e['test_fixture']=True;e['analysis']['summary']=declaration
    e['analysis']['ai_review']={'completed':True,'agent':declaration,'reviewed_files':[f['id'] for f in m['files']]}
    e['review_log']=[{'file_id':f['id'],'sha256':f['sha256'],'reviewer':declaration,'reviewed_at':'2026-10-09T01:00:00+00:00','coverage':'full','regions':['Synthetic protocol declaration only'],'issues':['No actual review performed.']} for f in m['files']]
    return e

try:
    check('init ready',cli('init')['status']=='ready')
    proc,port,token=start()
    page,headers=request(port,token,'GET','/',authenticated=False)
    check('Management HTML loads with no token leakage',b'VPS' in page and token.encode() not in page)
    check('Management no-store/nosniff',headers['Cache-Control']=='no-store' and headers['X-Content-Type-Options']=='nosniff')
    request(port,token,'GET','/api/jobs',status=401,authenticated=False)
    request(port,'invalid','GET','/api/jobs',status=401)
    request(port,token,'GET','/api/jobs',status=403,extra={'Host':'attacker.invalid'})
    request(port,token,'GET','/api/jobs',status=403,extra={'Origin':'https://attacker.invalid'})
    request(port,token,'GET','/api/jobs?token=not-a-real-token',status=400)
    request(port,token,'POST','/api/collect',{},status=404)
    job,_=request(port,token,'POST','/api/jobs',{'source_url':'https://www.nodeseek.com/post-900001-1'},201)
    jid=job['id'];route='/api/jobs/'+jid
    duplicate,_=request(port,token,'POST','/api/jobs',{'source_url':job['source_url']},201)
    check('URL enqueue is idempotent',duplicate['id']==jid)
    page=(SRC/'tests/fixtures/nodeseek_first_post.html').read_text()
    ingested,_=request(port,token,'POST',route+'/ingest',{'html':page})
    check('HTML archived pending analysis',ingested['status']=='awaiting_analysis')
    raw,headers=request(port,token,'GET',route+'/task')
    (RUN/'partial-task.zip').write_bytes(raw)
    draft,manifest,metadata=package(raw)
    check('Missing resources retained explicitly',manifest['status']=='partial' and len(manifest['failures'])==2)
    request(port,token,'POST',route+'/submit',{'envelope':draft},400)
    check('Invalid draft retains pending state',request(port,token,'GET',route)[0]['status']=='awaiting_analysis')
    first=synthetic(draft,manifest)
    accepted,_=request(port,token,'POST',route+'/submit',{'envelope':first})
    check('Synthetic submission v1 accepted',accepted['version']==1 and accepted['duplicate'] is False)
    repeated,_=request(port,token,'POST',route+'/submit',{'envelope':first})
    check('Submission idempotent',repeated['version']==1 and repeated['duplicate'] is True)
    request(port,token,'POST',route+'/cancel',{},400)
    check('Accepted record cannot cancel',request(port,token,'GET',route)[0]['status']=='accepted')
    old_token=token; old_hash=ingested['archive_sha256'];stop(proc)
    proc,port,token=start()
    check('Restart rotates token',token!=old_token)
    request(port,old_token,'GET','/api/jobs',status=401)
    resumed,_=request(port,token,'GET',route)
    check('Process restart retains accepted v1 and archive',resumed['status']=='accepted' and resumed['accepted_version']==1 and resumed['archive_sha256']==old_hash)
    # Simultaneous authenticated enqueues hit real HTTP worker threads / SQLite.
    concurrent_url='https://www.nodeseek.com/post-900002-1'
    def add(_):return request(port,token,'POST','/api/jobs',{'source_url':concurrent_url},201)[0]['id']
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex: ids=list(ex.map(add,range(16)))
    check('16 concurrent enqueues create exactly one job',len(set(ids))==1)
    count_before=len(request(port,token,'GET','/api/jobs')[0]); check('Exactly two current jobs',count_before==2)
    route2='/api/jobs/'+ids[0]
    check('Cancel works',request(port,token,'POST',route2+'/cancel',{})[0]['status']=='cancelled')
    check('Retry resumes queued',request(port,token,'POST',route2+'/retry',{})[0]['status']=='queued')
    # CLI resource import while HTTP server remains live.
    captured=RUN/'capture';captured.mkdir(exist_ok=True)
    (captured/'page.html').write_text(page)
    (captured/'chart.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='))
    (captured/'report.txt').write_bytes((SRC/'tests/fixtures/synthetic-report.txt').read_bytes())
    resources={'https://images.example.com/synthetic-chart.png':'chart.png','https://nodequality.com/r/synthetic-only':'report.txt'}
    (captured/'resources.json').write_text(json.dumps(resources))
    old_manifests={str(p):p.read_bytes() for p in (DATA/'archives'/jid).rglob('manifest.json')}
    enriched=cli('ingest',jid,str(captured/'page.html'),'--resources',str(captured/'resources.json'))
    check('Resource supplement creates new pending snapshot',enriched['status']=='awaiting_analysis' and enriched['archive_sha256']!=old_hash)
    check('Old manifests remain immutable',all(Path(p).read_bytes()==b for p,b in old_manifests.items()))
    request(port,token,'POST',route+'/submit',{'envelope':first},400)
    exported=cli('export-evidence',str(RUN/'public-before-new-analysis'))
    projection=json.loads((RUN/'public-before-new-analysis/reviews.json').read_text())
    check('Pending new archive exports old accepted snapshot',projection['records'][0]['archive_sha256']==old_hash)
    raw,headers=request(port,token,'GET',route+'/task'); (RUN/'complete-task.zip').write_bytes(raw)
    draft2,manifest2,metadata2=package(raw)
    check('Complete archive includes image and report',manifest2['status']=='ready' and len(manifest2['files'])==4 and manifest2['failures']==[])
    second=synthetic(draft2,manifest2)
    complete=RUN/'synthetic-envelope.json';complete.write_text(json.dumps(second,ensure_ascii=False))
    check('CLI import accepts new snapshot as v2',cli('submit',jid,str(complete))['version']==2)
    check('HTTP sees CLI persisted v2',request(port,token,'GET',route)[0]['accepted_version']==2)
    check('Same reingest preserves accepted state',cli('ingest',jid,str(captured/'page.html'),'--resources',str(captured/'resources.json'))['status']=='accepted')
    check('Export count one',cli('export-evidence',str(RUN/'public-final'))['records']==1)
    public=json.loads((RUN/'public-final/reviews.json').read_text()); record=public['records'][0]
    check('Private evidence dump explicitly unsafe to publish',public['v5_ui_integration']=='use_safe_catalog_export' and public['publish_safe'] is False)
    check('61 unknown facts not invented',len(record['analysis']['facts'])==61 and all(f['value'] is None for f in record['analysis']['facts'].values()))
    check('No AI/vision verification falsely claimed',record['validation']['ai_invoked'] is False and record['validation']['review_attestation_verified'] is False)
    for f in record['public_evidence']:
        p=RUN/'public-final'/f['path'];check('Public evidence hash '+f['id'],hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256'])
        check('Public evidence inert suffix '+f['id'],p.suffix in {'.txt','.bin'})
    files=list((RUN/'public-final').rglob('*'))
    check('No private DB/token in public export',not any(p.name.endswith(('.sqlite3','-wal','-shm')) for p in files) and not any(token.encode() in p.read_bytes() or old_token.encode() in p.read_bytes() for p in files if p.is_file()))
    cli('export-evidence',str(RUN/'public-final'),expected=2)
    stop(proc)
    # Emulate a dead process's lease in this disposable DB, then use actual CLI recover.
    conn=sqlite3.connect(DATA/'pipeline.sqlite3');conn.execute("UPDATE jobs SET status='archiving',lease_token='synthetic-dead-process',lease_until=? WHERE id=?",(time.time()-1,ids[0]));conn.commit();conn.close()
    check('Expired lease recovered by CLI',ids[0] in cli('recover')['recovered'])
    check('Recovered queue visible in CLI',cli('show',ids[0])['status']=='queued')
    proc,port,token=start()
    check('Second restart retains latest accepted v2',request(port,token,'GET',route)[0]['accepted_version']==2)
    stop(proc)
    outcome={'status':'pass','checks_passed':len(checks),'checks_failed':0,'http_requests':len(exchanges),'python':sys.version.split()[0],'platform':platform.platform(),'external_network_requests':0,'data':'Synthetic fixtures only; no actual AI or image review asserted.','checks':checks,'http':exchanges}
except BaseException as e:
    outcome={'status':'fail','exception':repr(e),'checks':checks,'http':exchanges}
    raise
finally:
    for p in processes:
        if p.poll() is None:p.kill();p.wait(timeout=5)
    (RESULTS/(RUN_NAME+'.json')).write_text(json.dumps(outcome,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in outcome.items() if k not in ('checks','http')},indent=2))
