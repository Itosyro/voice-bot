import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import threading
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fixture_server',ROOT/'baseline/helpers/server.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
with tempfile.TemporaryDirectory(prefix='dvizh-health-') as tmp:
    store=m.StateStore(Path(tmp)/'state.db')
    store.put('browser-test','browser@example.invalid',{'version':1,'tasks':[],'hasSeenIntro':True,'tone':'direct','selectedFocusTaskId':'test','future':{'keep':True},'trainingHub':{'today':{'readiness':{'score':2}}}},0)
    server=m.DVIZHServer(('127.0.0.1',0),m.Handler,store=store,static_dir=ROOT/'dist')
    if '--approval' in sys.argv:
        def load(name,path):
            spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
        bridge=load('fixture_bridge',ROOT.parents[1]/'hermes-control-v1/dvizh_proposal_bridge.py')
        proposals=load('fixture_proposals',ROOT.parents[1]/'hermes-control-v1/dvizh_proposals.py')
        proposals.STORE_DIR=Path(tmp);proposals.STORE=Path(tmp)/'proposals.json';proposals.LOCK=Path(tmp)/'.lock'
        bridge.PROPOSAL_DIR=Path(tmp);bridge.PROPOSAL_STORE=proposals.STORE;bridge.PROPOSAL_LOCK=proposals.LOCK
        bridge.TELEGRAM_DB=Path(tmp)/'no-db';bridge.IDENTITY_PATH=Path(tmp)/'no-identity'
        p=proposals.create('health_supplement_schedule','Add requested schedule',{'day':'2026-09-10','timezone':'Europe/Moscow','id':'ai_schedule','name':'User supplement','dose':'one exact user scoop','slots':[{'id':'am','time':'08:00'},{'id':'pm','time':'20:00'}],'weekdays':[0,1,2,3,4,5,6],'enabled':True})
        row=store.get('browser-test');state=row['state'];state['aiProposals']=bridge.pending_proposals([p]);state['aiProposalUiToken']='test-token-'*4;state['aiProposalCommands']=[]
        store.put('browser-test','browser@example.invalid',state,row['revision'])
        bridge.WEB_API=f'http://127.0.0.1:{server.server_port}'
    print(json.dumps({'port':server.server_port}),flush=True)
    if '--approval' in sys.argv:
        threading.Thread(target=server.serve_forever,daemon=True).start()
        for line in sys.stdin:
            if line.strip()=='process':
                client=bridge.WebClient('browser-test','browser@example.invalid')
                bridge.process_one_command(client,bridge.queue_snapshot())
                print(json.dumps({'applied':proposals.list_rows(None)[0]['status']=='applied'}),flush=True)
    else:
        server.serve_forever()
