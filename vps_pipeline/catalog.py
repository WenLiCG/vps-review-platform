"""Connect the preserved v5 public assets to verified safe runtime records.

This module never serves the private evidence export. Static assets have a fixed
allowlist; generated JSON is an atomic facts-only snapshot, with no model calls.
"""
from pathlib import Path
import json

from .archive import _read_bytes, _json_unique
from .store import check_plain_path, now

BASELINE_JSON = ('data.json','enrichment.json','filter-spec.json','image-evidence.json',
                 'skill-refresh.json','incremental-public-provenance.json')
STATIC_ASSETS = {'index.html':'text/html; charset=utf-8','style.css':'text/css; charset=utf-8',
                 'app.js':'text/javascript; charset=utf-8','workbench.js':'text/javascript; charset=utf-8',
                 'skill-refresh.js':'text/javascript; charset=utf-8','favicon.svg':'image/svg+xml'}
MAX_PUBLIC_BYTES=32*1024*1024


def website_root():
    return Path(__file__).resolve().parents[1]/'website'/'dist'


def build_snapshot(store, root=None, local_management=False):
    from .catalog_feed import catalog_records
    from .catalog_adapter import build_catalog
    base=check_plain_path(root if root is not None else website_root())
    baseline={}
    for name in BASELINE_JSON:
        path=check_plain_path(base/name)
        data=json.loads(_read_bytes(path,MAX_PUBLIC_BYTES).decode('utf-8-sig'),object_pairs_hook=_json_unique)
        json.dumps(data,allow_nan=False)
        baseline[name]=data
    definitions=json.loads((Path(__file__).resolve().parent/'vendor/vps-review-analyze/references/fields.json').read_text(encoding='utf-8'))
    # catalog_records verifies immutable source snapshots before it emits only
    # safe facts; the v5 adapter never receives original archive text or images.
    records=catalog_records(store)
    generated=build_catalog(baseline,records,definitions,now())
    if not isinstance(generated,dict) or not set(BASELINE_JSON[:5])<=generated.keys():
        raise ValueError('Catalog adapter did not return all required public contracts')
    generated.setdefault('incremental-public-provenance.json',baseline['incremental-public-provenance.json'])
    if local_management:
        generated['skill-refresh.json'].setdefault('pipelineIntegration',{})['managementPath']='/'
    payload={'schemaVersion':'vps-catalog-snapshot/1','files':generated}
    json.dumps(payload,ensure_ascii=False,allow_nan=False)
    return payload


def export_catalog(store, output_dir, root=None):
    base=check_plain_path(root if root is not None else website_root())
    destination=check_plain_path(output_dir)
    if destination.resolve().is_relative_to(base.resolve()) or base.resolve().is_relative_to(destination.resolve()):
        raise ValueError('Catalog export must not overlap the bundled baseline website')
    if destination.resolve().is_relative_to(store.root.resolve()) or store.root.resolve().is_relative_to(destination.resolve()):
        raise ValueError('Catalog export must remain separate from the private data root')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Catalog export requires a new or empty directory')
    snapshot=build_snapshot(store,base)
    destination.mkdir(parents=True,exist_ok=True)
    for name in STATIC_ASSETS:
        source=check_plain_path(base/name)
        (destination/name).write_bytes(_read_bytes(source,MAX_PUBLIC_BYTES))
    for name,value in snapshot['files'].items():
        if name not in set(BASELINE_JSON)|{'catalog-integration.json'}:
            raise ValueError('Unexpected generated catalog asset name')
        (destination/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (destination/'catalog-snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    integration=snapshot['files'].get('catalog-integration.json',{})
    return {'status':'exported','output':str(destination),'schema_version':'vps-catalog-snapshot/1',
            'public_files':len(list(destination.iterdir())),'integration':integration,
            'private_evidence_exported':False,'website_published':False}
