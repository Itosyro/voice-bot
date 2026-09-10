import copy
import json
import subprocess
import unittest
from test_domain import ROOT, module
from unittest.mock import patch

DAY='2026-09-10'
class FindingsTests(unittest.TestCase):
    def setUp(self): self.h=module(ROOT/'domain.py','findings_domain')
    def test_recursive_keys_and_strict_values(self):
        cases=[]
        for key in ('__proto__','constructor','prototype'):
            cases.append(({},'health_supplement_schedule',dict(id='s',name='Name',dose='user dose',slots=[{'id':'am','time':'08:00','future':[{'nested':{key:{'polluted':True}}}]}],weekdays=[3],enabled=True)))
        for key in ('source','timezone'):
            for value in ('',None,False): cases.append(({'healthRecovery':{'version':1,'timezone':'UTC'}},'health_checkin',{key:value,'energy':3}))
        for version in (True,False,'1',2,None): cases.append(({'healthRecovery':{'version':version}},'health_checkin',{'energy':3}))
        for state,action,fields in cases:
            with self.subTest(fields=fields,state=state):
                p={'day':DAY,'timezone':'UTC',**fields}; before=copy.deepcopy(state)
                with self.assertRaises(ValueError): self.h.health_apply(state,action,p)
                self.assertEqual(state,before)
                script="const fs=require('fs'),vm=require('vm');global.window={};vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));const x=JSON.parse(fs.readFileSync(0,'utf8'));try{window.DVIZH_HEALTH.apply(...x);console.log('accepted')}catch{console.log('rejected')}"
                result=subprocess.check_output(['node','-e',script,str(ROOT/'domain.js')],input=json.dumps([state,action,p]).encode()).decode().strip()
                self.assertEqual(result,'rejected')
    def test_sanitized_context_all_views_and_malformed_future(self):
        c=module(ROOT.parents[1]/'hermes-control-v1/dvizh_context.py','findings_context')
        h={'version':1,'timezone':'Not/AZone','schedules':{'secret-s':{'name':'do not leak'},'bad':None},'sleep':{'invalid':{},DAY:{'durationMinutes':'[redacted]','quality':{}},'2026-09-11':{'durationMinutes':500}},'checkins':{DAY:{'energy':'[redacted]','stress':[]}},'intakes':{'secret-s':'[redacted]','bad':None,'future':{'id':'future','day':'2026-09-11'}}}
        state=c.sanitize({'healthRecovery':h,'trainingHub':{'readiness':'[redacted]'},'jumpLab':{'today':[]}})
        self.assertIsInstance(state['healthRecovery']['schedules']['secret-s'],str)
        with patch.object(c,'database_snapshot',return_value={'today':DAY,'timezone':'UTC'}),patch.object(c,'web_state',return_value={'ok':True,'state':state}),patch.object(c,'status_snapshot',return_value={}):
            for view in ('today','week','health','full'):
                with self.subTest(view=view):
                    result=c.build(view)
                    self.assertEqual(result['health']['readiness']['level'],'insufficient_data')
                    self.assertEqual(result['health']['sleep']['recordedDays'],0)
                    self.assertEqual(result['health']['supplements']['today'],[])
                    self.assertNotIn('do not leak',json.dumps(result))
        self.assertEqual(state['healthRecovery']['schedules']['secret-s'],'[REDACTED]')
        for domain in (None,[], 'redacted',{'version':2,'schedules':{'x':42}}, {'sleep':[], 'checkins':False,'intakes':42,'schedules':True}):
            self.h.health_summary({'healthRecovery':domain},DAY)
    def test_malformed_summary_python_js_parity(self):
        for domain in (None,[], 'redacted',{'version':2,'schedules':{'x':42}}, {'sleep':[], 'checkins':False,'intakes':42,'schedules':True}, {'version':1,'timezone':'UTC','sleep':{'secret-s':'[redacted]','bad-day':{},DAY:{'durationMinutes':'[redacted]'}},'checkins':{DAY:{'energy':'[redacted]'}},'schedules':{'secret-s':'[redacted]'},'intakes':{'secret-s':'[redacted]'}}):
            with self.subTest(domain=domain):
                state={'healthRecovery':domain}
                js=json.loads(subprocess.check_output(['node',str(ROOT/'tests/parity.cjs')],input=json.dumps({'state':state,'actions':[],'day':DAY}).encode()))
                self.assertEqual(self.h.health_summary(state,DAY),js['summary'])
    def test_legacy_proposal_status_contract(self):
        p=module(ROOT.parents[1]/'hermes-control-v1/dvizh_proposals.py','legacy_status_findings')
        self.assertEqual(p.VISIBLE_STATUSES,{'pending','rejected','superseded','applied','failed'})
        for status in ('applied','failed'):
            with self.assertRaises(SystemExit): p.resolve('synthetic',status)
    def test_context_malformed_web_state_retains_legacy_unavailable_contract(self):
        c=module(ROOT.parents[1]/'hermes-control-v1/dvizh_context.py','malformed_web_findings')
        with patch.object(c,'database_snapshot',return_value={'today':DAY,'timezone':'UTC'}),patch.object(c,'status_snapshot',return_value={}):
            for state in (None, [], '[REDACTED]'):
                with self.subTest(state=state),patch.object(c,'web_state',return_value={'ok':True,'state':state}):
                    self.assertNotIn('health',c.build('today'))
