"""Deliberately synthetic historical fixtures, never genuine review attestations."""
import json
from pathlib import Path
from vps_pipeline.analysis import _load_review
from vps_pipeline.archive import archive_from_html


def synthetic_legacy(base, post_id='900001'):
    base=Path(base)
    capture=base/'capture';capture.mkdir(parents=True)
    page=capture/'page.html'
    page.write_text('<div id="0"><article class="post-content"><p>SYNTHETIC LEGACY TEST ONLY. No real AI review occurred.</p></article></div>',encoding='utf-8')
    manifest_path=archive_from_html(page,'https://www.nodeseek.com/post-'+post_id+'-1',base/'original')
    manifest=json.loads(manifest_path.read_text())
    manifest['capture_method']='browser_import'
    manifest['capture_note']='SYNTHETIC TEST ONLY: 逐页签读取#0首帖，非回复。This is a synthetic historical capture declaration, not actual reading.'
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    analysis=_load_review().draft(manifest)
    analysis['summary']='SYNTHETIC LEGACY TEST. Historical contract only, no real review.'
    analysis['ai_review']={'completed':True,'agent':'SYNTHETIC TEST DECLARATION ONLY','reviewed_files':['manifest']+[f['id'] for f in manifest['files']]}
    analysis.update(sources=manifest['files'],source_metadata={k:manifest.get(k) for k in ['title','author','captured_at','capture_method','capture_note']},archive_status=manifest['status'],download_failures=manifest.get('failures',[]),generated_at='2026-10-08T01:00:00+00:00',program_version=1,markdown_path='synthetic.md')
    analysis_path=manifest_path.parent/'analysis.json'
    analysis_path.write_text(json.dumps(analysis,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest_path,analysis_path
