import argparse,json,hashlib
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('checkpoint');ap.add_argument('output');ap.add_argument('--batch-id',required=True);ap.add_argument('--batch-date',required=True);ap.add_argument('--source-commit',required=True);a=ap.parse_args();c=json.loads(Path(a.checkpoint).read_text(encoding='utf-8'));entries=[]
for row in c['posts']:
 analysis=Path(row['analysis_path']);manifest=Path(row['manifest_path']);actual=hashlib.sha256(analysis.read_bytes()).hexdigest()
 if actual!=row['analysis_sha256']:raise ValueError('Checkpoint hash drift: '+row['post_id'])
 if row['object_count']!=1:raise ValueError('Manual multi-object mapping required')
 if row['entry_kind']not in ['review','network_review']:raise ValueError('Explicit type mapping required: '+row['entry_kind'])
 entries.append({'postId':row['post_id'],'sourceUrl':row['source_url'],'reviewComplete':True,'objectCount':1,'manifestPath':str(manifest),'publicLabel':row['public_label'],'category':'review'if row['entry_kind']=='review'else'network_followup','captureScope':'本批实际采集并完成61字段分析；图片/报告阅读范围与缺失状态按实际归档保留。','objects':[{'itemId':row['post_id']+'-1','entryKind':'measured_vps','publicLabel':row['public_label'],'analysisPath':str(analysis)}]})
result={'batchId':a.batch_id,'batchDate':a.batch_date,'sourceCommit':a.source_commit,'checkpointSha256':hashlib.sha256(Path(a.checkpoint).read_bytes()).hexdigest(),'entries':entries};Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'entries':len(entries),'checkpointSha256':result['checkpointSha256']}))
