import copy
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from test_domain import ROOT, module

REPO=ROOT.parents[1]
class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.context=module(REPO/'hermes-control-v1/dvizh_context.py','context_test')
        self.proposals=module(REPO/'hermes-control-v1/dvizh_proposals.py','proposals_test')
        self.bridge=module(REPO/'hermes-control-v1/dvizh_proposal_bridge.py','bridge_test')
        server=module(ROOT/'baseline/helpers/server.py','state_server')
        self.tmp=tempfile.TemporaryDirectory()
        self.directory=Path(self.tmp.name)
        self.server=server.DVIZHServer(('127.0.0.1',0),server.Handler,store=server.StateStore(self.directory/'state.db'),static_dir=ROOT/'baseline/static')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.bridge.WEB_API=f'http://127.0.0.1:{self.server.server_port}'
        self.client=self.bridge.WebClient('test-user','test@example.invalid')
        self.state={'version':1,'tasks':[],'trainingHub':{'today':{'readiness':{'score':2}}},'unknown':{'keep':42},'aiProposalUiToken':'x'*32,'aiProposalCommands':[]}
        self.client.put_state(0,self.state)
        self.proposals.STORE_DIR=self.directory
        self.proposals.STORE=self.directory/'proposals.json'; self.proposals.LOCK=self.directory/'.lock'
        self.bridge.PROPOSAL_DIR=self.directory; self.bridge.PROPOSAL_STORE=self.proposals.STORE; self.bridge.PROPOSAL_LOCK=self.proposals.LOCK
        # Fail hard if a test accidentally touches production identity, DB, or status.
        self.bridge.TELEGRAM_DB=self.directory/'no-db'
        self.bridge.IDENTITY_PATH=self.directory/'no-identity'
        self.context.DB_PATH=self.directory/'no-db'; self.context.IDENTITY_PATH=self.directory/'no-identity'
        self.context.STATUS_FILES={k:self.directory/('no-'+k) for k in self.context.STATUS_FILES}
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()
    def proposal(self,action='health_sleep',**fields):
        return self.proposals.create(action,'Record requested health data',{'day':'2026-09-10','timezone':'Europe/Moscow',**fields})
    def approve(self,p,token='x'*32):
        self.bridge.publish_only(self.client,self.bridge.queue_snapshot())
        revision,state=self.client.get_state()
        state['aiProposalCommands']=[{'id':'cmd-'+p['id'],'proposalId':p['id'],'decision':'approve','token':token,'healthVersion':1}]
        self.client.put_state(revision,state)
        self.bridge.process_one_command(self.client,self.bridge.queue_snapshot())
        return self.client.get_state()[1]
    def test_inert_proposal_approval_context_and_replay(self):
        p=self.proposal(start='23:30',end='07:00',quality=4)
        self.assertNotIn('healthRecovery',self.client.get_state()[1])
        state=self.approve(p)
        self.assertEqual(state['healthRecovery']['sleep']['2026-09-10']['durationMinutes'],450)
        self.assertEqual(state['unknown'],{'keep':42})
        for view in ('today','week','health','full'):
            selected=self.context.selected_web_state(state,view,'2026-09-10')
            self.assertEqual(selected['healthRecovery'],state['healthRecovery'])
        self.assertEqual(self.proposals.list_rows('applied')[0]['id'],p['id'])
        before=copy.deepcopy(state['healthRecovery']); self.approve(p)
        self.assertEqual(self.client.get_state()[1]['healthRecovery'],before)
    def test_bad_token_and_cas_and_auth(self):
        p=self.proposal(durationMinutes=420)
        self.assertNotIn('healthRecovery',self.approve(p,token='bad'*10))
        with self.assertRaises(self.bridge.RevisionConflict): self.client.put_state(0,self.state)
        with self.assertRaises(urllib.error.HTTPError) as cm: urllib.request.urlopen(self.bridge.WEB_API+'/api/state')
        self.assertEqual(cm.exception.code,401)
    def test_checkin_and_schedule_approval_and_conflict_retry(self):
        self.approve(self.proposal('health_checkin',energy=2,note='sore legs'))
        self.approve(self.proposal('health_checkin',stress=4))
        self.approve(self.proposal('health_supplement_schedule',id='user-s',name='User supplement',dose='one user scoop',slots=[{'id':'am','time':'08:00'},{'id':'pm','time':'20:00'}],weekdays=[3],enabled=True))
        original=self.client.put_state
        conflict=[True]
        def put(rev,state):
            if 'intakes' in state.get('healthRecovery',{}) and conflict[0]:
                conflict[0]=False
                r,other=self.client.get_state(); other['unknown']['remote']=123; original(r,other)
            return original(rev,state)
        self.client.put_state=put
        state=self.approve(self.proposal('health_supplement_mark',scheduleId='user-s',slotId='am',status='taken'))
        self.assertEqual(state['unknown']['remote'],123)
        self.assertNotIn('soreness',state['healthRecovery']['checkins']['2026-09-10'])
        self.assertEqual(len(state['healthRecovery']['intakes']),1)
    def test_invalid_proposals_rejected_before_spool(self):
        for fields in ({'quality':9},{'start':'evening','end':'morning'}):
            with self.assertRaises(SystemExit): self.proposal(**fields)
    def test_context_build_keeps_contracts(self):
        state=self.approve(self.proposal(durationMinutes=400))
        self.context.database_snapshot=lambda view:{'ok':True,'today':'2026-09-10','timezone':'Europe/Moscow','tables':{}}
        from datetime import datetime, timezone
        class FixedDatetime(datetime):
            @classmethod
            def now(cls,tz=None): return datetime(2026,9,10,12,tzinfo=timezone.utc)
        self.context.datetime=FixedDatetime
        self.context.web_state=lambda:{'ok':True,'state':state,'revision':2}
        for view in ('today','week','health','full'):
            result=self.context.build(view)
            self.assertTrue(result['read_only'])
            self.assertEqual(result['health']['sleep']['mean7Minutes'],400)
            self.assertEqual(result['web']['state']['trainingHub'],state['trainingHub'])

    def test_schedule_add_must_be_complete_before_proposal(self):
        for p in [{'id':'new','name':'magnesium'}, {'id':'new','name':'magnesium','dose':'user dose'}, {'id':'new','name':'magnesium','dose':'user dose','slots':[{'id':'am','time':'morning'}],'weekdays':[0],'enabled':True}]:
            with self.assertRaises(SystemExit): self.proposal('health_supplement_schedule',**p)
    def test_old_new_helpers_wait_safely_and_legacy_tasks_apply(self):
        old_proposals=module(ROOT/'baseline/helpers/proposals.py','old_proposals')
        old_bridge=module(ROOT/'baseline/helpers/proposal_bridge.py','old_bridge')
        with self.assertRaises(SystemExit): old_proposals.validate('health_checkin',{'energy':2})
        p=self.proposal('health_checkin',energy=2)
        self.assertEqual(old_bridge.pending_proposals([p]),[])
        self.assertEqual(self.bridge.pending_proposals([p])[0]['id'],p['id'])
        old_proposals.STORE_DIR=self.directory;old_proposals.STORE=self.proposals.STORE;old_proposals.LOCK=self.proposals.LOCK
        legacy=old_proposals.create('task_create','Add task',{'title':'legacy task','due_date':'2026-09-10'})
        state=self.approve(legacy)
        self.assertEqual(state['tasks'][0]['title'],'legacy task')
        self.assertNotIn('healthRecovery',state)

    def test_schedule_partial_proposal_update_and_user_isolation(self):
        self.approve(self.proposal('health_supplement_schedule',id='s',name='Name',dose='user text',slots=[{'id':'am','time':'08:00'}],weekdays=[3],enabled=True))
        state=self.approve(self.proposal('health_supplement_schedule',id='s',update=True,enabled=False))
        self.assertEqual(state['healthRecovery']['schedules']['s']['dose'],'user text')
        self.assertFalse(state['healthRecovery']['schedules']['s']['enabled'])
        other=self.bridge.WebClient('other-user','other@example.invalid')
        self.assertIsNone(other.request('/api/state')['state'])
        self.assertEqual(other.request('/api/state')['revision'],0)

    def test_old_ui_cannot_approve_health_without_exact_field_confirmation(self):
        p=self.proposal(durationMinutes=420)
        self.bridge.publish_only(self.client,self.bridge.queue_snapshot())
        revision,state=self.client.get_state()
        state['aiProposalCommands']=[{'id':'old-ui','proposalId':p['id'],'decision':'approve','token':'x'*32}]
        self.client.put_state(revision,state)
        self.bridge.process_one_command(self.client,self.bridge.queue_snapshot())
        state=self.client.get_state()[1]
        self.assertNotIn('healthRecovery',state)
        self.assertFalse(state['aiProposalLastResult']['ok'])
        self.assertEqual(self.proposals.list_rows(None)[0]['status'],'pending')

    def test_boolean_health_capability_cannot_approve(self):
        p=self.proposal(durationMinutes=420)
        self.bridge.publish_only(self.client,self.bridge.queue_snapshot())
        revision,state=self.client.get_state()
        state['aiProposalCommands']=[{'id':'bool-command','proposalId':p['id'],'decision':'approve','token':'x'*32,'healthVersion':True}]
        self.client.put_state(revision,state)
        self.bridge.process_one_command(self.client,self.bridge.queue_snapshot())
        self.assertNotIn('healthRecovery',self.client.get_state()[1])

    def test_legacy_task_complete_and_day_plan_approval(self):
        created=self.proposals.create('task_create','Legacy task',{'title':'Legacy task'})
        state=self.approve(created)
        completed=self.proposals.create('task_complete','Complete legacy task',{'task_id':state['tasks'][0]['id']})
        state=self.approve(completed)
        self.assertTrue(state['tasks'][0]['done'])
        plan=self.proposals.create('day_plan','Legacy day plan',{'blocks':[{'title':'User block','start':'09:00'}]})
        state=self.approve(plan)
        self.assertEqual(state['aiDayPlan']['blocks'],plan['payload']['blocks'])
        self.assertEqual(state['unknown'],{'keep':42})
        self.assertNotIn('healthRecovery',state)
