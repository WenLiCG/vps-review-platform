"""Run source-package offline regression checks without crawling or model calls."""
from pathlib import Path
import json,os,shutil,subprocess,sys

root=Path(__file__).resolve().parents[1]
node=shutil.which('node')
if not node:raise SystemExit('Node.js 18+ is required only for the browser-logic tests; normal program runtime needs Python only.')
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
commands=[
 ([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],root),
 ([sys.executable,'-B','test_download.py'],root/'skills/vps-review-download/scripts'),
 ([sys.executable,'-B','test_review.py'],root/'skills/vps-review-analyze/scripts'),
 ([sys.executable,'-B','-m','unittest','test_public_adapter.py','test_increment.py','-q'],root/'bridge'),
 *[([node,'--check',str(root/'website/dist'/name)],root) for name in ['app.js','workbench.js','skill-refresh.js']],
 ([node,'tests/v5_runtime.cjs'],root),
 ([sys.executable,'-B','scripts/make_v5_test_snapshot.py'],root),
 ([node,'tests/v5_integration_runtime.cjs'],root),
 ([node,'tests/v5_route_direction_tests.cjs'],root),
 ([sys.executable,'-B','scripts/process_smoke.py'],root),
]
for command,cwd in commands:
 print('CHECK:', ' '.join(command),flush=True)
 subprocess.run(command,cwd=cwd,env=env,check=True)
print(json.dumps({'status':'pass','commands':len(commands),'network_collection':False,'model_api_calls':False,'actual_browser_visual_qa':False}))
