import copy
import json
import subprocess
import unittest
from test_domain import ROOT, module

DAY='2026-09-10'
class Round2Tests(unittest.TestCase):
    def test_differential_input_policy(self):
        h=module(ROOT/'domain.py','round2')
        cases=[('health_sleep',{'start':None,'end':'08:00'},False),
               ('health_checkin',{'energy':3.0},True),
               ('health_sleep',{'durationMinutes':400.0},True),
               ('health_sleep',{'durationMinutes':400.5},True),
               ('health_sleep',{'quality':3.0},True),
               ('health_sleep',{'start':'23:٠٠','end':'07:00'},False),
               ('health_checkin',{'note':'😀'*1000},True),
               ('health_checkin',{'note':'😀'*600},True),
               ('health_checkin',{'note':'😀'*1001},False)]
        for zone in ['UTC','utc','Europe/Moscow','europe/moscow','America/New_York','america/new_york','Asia/Kolkata','Asia/Kathmandu','Australia/Lord_Howe','Pacific/Chatham','Etc/GMT+5','not/a_zone','+01:00','Factory','localtime']:
            cases.append(('health_checkin',{'timezone':zone,'energy':3},zone not in ('not/a_zone','+01:00','Factory','localtime')))
        for key in ['energy','note','timezone','source']:
            cases.append(('health_checkin',{key:None},False))
        for n in [True,False,3.5,'3',0,6]: cases.append(('health_checkin',{'energy':n},False))
        for n,ok in [(3.0,True),(3.5,False),(True,False)]:
            cases.append(('health_supplement_schedule',{'id':'s','name':'😀'*240,'dose':'x','slots':[{'id':'am','time':'08:00'}],'weekdays':[n],'enabled':True},ok))
        for action,fields,accepted in cases:
            with self.subTest(fields=fields):
                state={'healthRecovery':{'version':1,'timezone':'UTC','sleep':{DAY:{'day':DAY,'start':'23:00','end':'07:00','durationMinutes':480,'durationKind':'clock'}}}}
                before=copy.deepcopy(state);p={'day':DAY,'timezone':'UTC',**fields}
                js=json.loads(subprocess.check_output(['node',str(ROOT/'tests/parity.cjs')],input=json.dumps({'state':state,'actions':[[action,p]],'day':DAY}).encode()))
                try: h.health_apply(state,action,p);ok=True
                except ValueError: ok=False
                self.assertEqual(ok,accepted,'Python acceptance');self.assertEqual(js['errors'],[not accepted],'JS acceptance')
                def strip(v):
                    if isinstance(v,dict): return {k:strip(x) for k,x in v.items() if k!='updatedAt'}
                    if isinstance(v,list): return [strip(x) for x in v]
                    return v
                self.assertEqual(strip(js['state']),strip(state))
                self.assertEqual(strip(js['summary']),strip(h.health_summary(state,DAY)))
                if not accepted:self.assertEqual(state,before)
    def test_old_client_stale_clock_summary(self):
        h=module(ROOT/'domain.py','round2_summary')
        for kind in ['clock',None]:
            row={'day':DAY,'start':'22:00','end':'08:00','durationMinutes':540,'startDay':DAY,'note':'keep','source':'manual','future':42}
            if kind:row['durationKind']=kind
            state={'healthRecovery':{'version':1,'sleep':{DAY:row}}};before=copy.deepcopy(state)
            summary=h.health_summary(state,DAY)
            self.assertEqual(summary['sleep']['last']['durationMinutes'],600)
            self.assertEqual(summary['sleep']['last']['startDay'],'2026-09-09')
            self.assertEqual(state,before)
            js=json.loads(subprocess.check_output(['node',str(ROOT/'tests/parity.cjs')],input=json.dumps({'state':state,'actions':[],'day':DAY}).encode()))
            self.assertEqual(summary,js['summary'])
