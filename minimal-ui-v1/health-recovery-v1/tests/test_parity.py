import json
import subprocess
import unittest
from test_domain import ROOT,module

class ParityTests(unittest.TestCase):
    def test_python_browser_domain_parity(self):
        h=module(ROOT/'domain.py','health_parity')
        actions=[]
        def add(a,**p):actions.append([a,{'day':'2026-09-10','timezone':'Europe/Moscow',**p}])
        add('health_sleep',start='23:30',end='07:00',quality=4)
        add('health_sleep',quality=3)
        add('health_sleep',day='2026-09-08',durationMinutes=390)
        add('health_sleep',day='2026-09-01',durationMinutes=600)
        add('health_checkin',energy=2,note='sore legs')
        add('health_checkin',stress=4)
        add('health_supplement_schedule',id='a',name='User supplement',dose='user text',slots=[{'id':'am','time':'08:00'},{'id':'pm','time':'20:00'}],weekdays=[3],enabled=True)
        add('health_supplement_mark',scheduleId='a',slotId='am',status='taken')
        add('health_supplement_mark',scheduleId='a',slotId='am',status='taken')
        add('health_supplement_mark',scheduleId='a',slotId='pm',status='skipped')
        add('health_supplement_schedule',id='a',dose='new user text')
        add('health_checkin',mood=6)
        add('health_sleep',start='25:00',end='07:00')
        state={'version':1,'tasks':[],'healthRecovery':{'version':1,'future':{'x':42}},'trainingHub':{'readiness':{'energy':2}},'jumpLab':{'today':{'status':'unknown'}}}
        js=json.loads(subprocess.check_output(['node',str(ROOT/'tests/parity.cjs')],input=json.dumps({'state':state,'actions':actions,'day':'2026-09-10'}).encode()))
        errors=[]
        for a,p in actions:
            try:h.health_apply(state,a,p);errors.append(False)
            except ValueError:errors.append(True)
        py={'state':state,'summary':h.health_summary(state,'2026-09-10'),'errors':errors}
        def strip(v):
            if isinstance(v,dict):return {k:strip(x) for k,x in v.items() if k!='updatedAt'}
            if isinstance(v,list):return [strip(x) for x in v]
            return v
        self.assertEqual(strip(py),strip(js))
