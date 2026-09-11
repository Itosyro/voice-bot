#!/usr/bin/env python3
"""Run fixed health-commit regression in a temporary archive, never the live app."""
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import tarfile
import tempfile

SHA = '9d492693de2c7cf66350293afcf42b74edeebaef'


def main():
    repo = Path(__file__).resolve().parents[1]
    root = Path(tempfile.mkdtemp(prefix='dvizh-v23-regression-'))
    archive = root/'archive'; archive.mkdir()
    raw = subprocess.check_output(['git','archive',SHA,'minimal-ui-v1','ai-home-v2','hermes-control-v1','tests/ai-home-v2'],cwd=repo)
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        tar.extractall(archive, filter='data')
    hooks = root/'hooks'; hooks.mkdir()
    # Archive bytes stay intact. Redirect hardcoded runtime defaults during Python
    # compilation, before module execution; subprocesses inherit these guards.
    (hooks/'sitecustomize.py').write_text('''import importlib.machinery, os, sys
from pathlib import Path
base=Path(os.environ['DVIZH_REGRESSION_ROOT'])
original=importlib.machinery.SourceFileLoader.source_to_code
def compile_fixture(self, data, path, *, _optimize=-1):
    if str(path).startswith(str(base/'archive')) and Path(path).name in {'dvizh_context.py','dvizh_proposals.py','dvizh_proposal_bridge.py','dvizh_ai_home_bridge.py','ai_home_bridge.py','context.py','proposals.py','proposal_bridge.py','server.py'}:
        if isinstance(data,bytes): data=data.decode('utf-8')
        data=data.replace('/var/lib/dvizh',str(base/'runtime')).replace('/opt/dvizh',str(base/'runtime-opt'))
        data=data.replace('http://127.0.0.1:8000','http://127.0.0.1:1').replace('http://127.0.0.1:8642','http://127.0.0.1:1')
    return original(self,data,path,_optimize=_optimize)
importlib.machinery.SourceFileLoader.source_to_code=compile_fixture
def audit(event,args):
    if event=='open' and isinstance(args[0],(str,bytes)):
        name=os.fsdecode(args[0])
        if name.startswith(('/var/lib/','/opt/dvizh','/etc/sudoers','/root/.ssh')):
            raise RuntimeError('production read/write denied by fixture guard')
    if event=='socket.connect' and isinstance(args[1],tuple):
        host,port=args[1][:2]
        if host not in ('127.0.0.1','::1','localhost') or port in (8000,8642):
            raise RuntimeError('nonfixture network denied')
sys.addaudithook(audit)
''')
    env = {'PATH':os.defpath+':/usr/local/bin:'+str(Path(shutil.which('node') or '/nonexistent/node').parent),'PYTHONPATH':str(hooks),'PYTHONDONTWRITEBYTECODE':'1',
           'DVIZH_REGRESSION_ROOT':str(root),'DVIZH_PROPOSAL_DIR':str(root/'runtime/proposals'),
           'DVIZH_WEB_API':'http://127.0.0.1:1','HERMES_API_URL':'http://127.0.0.1:1',
           'HERMES_API_KEY':'','PLAYWRIGHT_MODULE':'/home/exedev/.hermes/dev/dvizh/browser-tools-sync-stability/node_modules/playwright',
           'CHROMIUM_PATH':'/home/exedev/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome'}
    cases = [
        ('health-full',['bash','minimal-ui-v1/health-recovery-v1/tests/run.sh']),
        ('ai-home-contracts',['bash','-c','node --test tests/ai-home-v2/*.test.cjs']),
        ('ai-home-bridge',['python3','tests/ai-home-v2/bridge_contract_test.py']),
    ]
    results=[]
    for label, argv in cases:
        log=root/(label+'.log')
        try:
            with log.open('wb') as out:
                cp=subprocess.run(argv,cwd=archive,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=300)
            result=dict(case=label,exit=cp.returncode,log=str(log))
        except subprocess.TimeoutExpired:
            result=dict(case=label,exit='timeout',log=str(log))
        results.append(result)
        print(json.dumps(result),flush=True)
    report=dict(commit=SHA,temporary_archive=str(archive),results=results,
                production='untouched',audible_device_speech='NOT VERIFIED')
    (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return int(any(r['exit']!=0 for r in results))


if __name__=='__main__':
    raise SystemExit(main())
