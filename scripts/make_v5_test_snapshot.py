"""Offline synthetic fixtures for integration tests, never production data."""
import json
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'tests')]
from test_catalog_adapter import BASE,DEFS,NOW,record,put
from vps_pipeline.catalog_adapter import build_catalog
root=Path(__file__).resolve().parents[1]/'var-test-fixtures'
root.mkdir(exist_ok=True)
new=record()
for key,value in [('vcpu',2),('memory_gb',2),('disk_gb',40),('provider','SYNTHETIC'),('monthly_price',{'amount':5,'currency':'EUR'}),('geekbench_single_score',1500)]:put(new,key,value)
new['benchmark_observations']=[{'field_id':'geekbench_single_score','tool':'Geekbench','version':6,'metric':'single','score':1500,'kind':'measurement','status':'reported'}]
put(new,'routes_from_server',{'ipv4':None,'ipv6':{'telecom':'10099','unicom':None,'mobile':None}})
new['network_observations']=[{'family':'IPv6','direction':'return','operator':'电信','transport':'UDP','targetCity':'上海','reportedLabels':['10099'],'status':'reported','kind':'measurement'}]
revision=record('971510',rid='synthetic-revision')
put(revision,'memory_gb',.965,'inferred')
revision['safe_observations']=[{'field_id':'memory_gb','value':.965,'status':'inferred','original_value':965,'original_unit':'MB'}]
legacy=record('971389','legacy_imported','synthetic-legacy');legacy.pop('catalog_mapping')
files=build_catalog(BASE,[new,revision,legacy],DEFS,NOW)
files['skill-refresh.json']['pipelineIntegration']['managementPath']='/'
out=root/'synthetic-snapshot.json';out.write_text(json.dumps({'schemaVersion':'vps-catalog-snapshot/1','files':files},ensure_ascii=False)+'\n',encoding='utf-8')
