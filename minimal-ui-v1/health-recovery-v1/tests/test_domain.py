import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class SleepTests(unittest.TestCase):
    def setUp(self):
        self.h = module(ROOT / 'domain.py', 'health_domain')
        self.state = {'version': 1, 'tasks': [], 'trainingHub': {'readiness': {'score': 2}}, 'future': {'x': 1}}
    def apply(self, action, **payload):
        return self.h.health_apply(self.state, action, {'day': '2026-09-10', 'timezone': 'Europe/Moscow', **payload})
    def test_midnight_update_and_recorded_days_mean(self):
        self.apply('health_sleep', start='23:30', end='07:00', quality=4, note='rested', source='manual')
        row=self.state['healthRecovery']['sleep']['2026-09-10']
        self.assertEqual(row['durationMinutes'], 450)
        self.assertEqual(row['startDay'], '2026-09-09')
        self.apply('health_sleep', quality=3)
        self.assertEqual(row['quality'], 4) # immutable replacement
        self.assertEqual(self.state['healthRecovery']['sleep']['2026-09-10']['durationMinutes'],450)
        self.apply('health_sleep', day='2026-09-08', durationMinutes=390)
        self.apply('health_sleep', day='2026-09-01', durationMinutes=800)
        summary=self.h.health_summary(self.state, '2026-09-10')
        self.assertEqual(summary['sleep']['mean7Minutes'], 420)
        self.assertEqual(summary['sleep']['recordedDays'], 2)
        self.assertEqual(self.state['trainingHub']['readiness']['score'],2)
        self.assertEqual(self.state['future'], {'x':1})
    def test_no_data_and_timezone(self):
        self.assertIsNone(self.h.health_summary(self.state,'2026-09-10')['sleep']['mean7Minutes'])
        self.assertEqual(self.h.health_summary(self.state,'2026-09-10')['readiness']['level'],'insufficient_data')
        self.apply('health_sleep',start='01:00',end='07:00',timezone='America/Los_Angeles')
        self.assertEqual(self.state['healthRecovery']['sleep']['2026-09-10']['startDay'],'2026-09-10')
    def test_invalid_does_not_mutate(self):
        for payload in [{'quality':6},{'durationMinutes':-1},{'start':'23:00'}, {'start':'29:00','end':'07:00'}, {'durationMinutes':True}, {'timezone':'not/a-zone','durationMinutes':400}, {'day':'2026-02-30','durationMinutes':400}]:
            before=copy.deepcopy(self.state)
            with self.assertRaises(ValueError): self.apply('health_sleep',**payload)
            self.assertEqual(self.state,before)

if __name__ == '__main__': unittest.main()

class SupplementCheckinTests(SleepTests):
    def schedule(self, **kw):
        self.apply('health_supplement_schedule',id='mag',name='Magnesium',dose='my scoop',slots=[{'id':'am','time':'08:00'},{'id':'pm','time':'20:00'}],weekdays=[0,1,2,3,4,5,6],enabled=True,**kw)
    def test_slots_snapshots_duplicate_skip_disabled(self):
        self.schedule()
        self.assertEqual(len(self.h.health_summary(self.state,'2026-09-10')['supplements']['remaining']),2)
        self.apply('health_supplement_mark',scheduleId='mag',slotId='am',status='taken')
        first=copy.deepcopy(self.state['healthRecovery']['intakes'])
        self.apply('health_supplement_mark',scheduleId='mag',slotId='am',status='taken')
        self.assertEqual(first,self.state['healthRecovery']['intakes'])
        self.apply('health_supplement_mark',scheduleId='mag',slotId='pm',status='skipped')
        self.apply('health_supplement_schedule',id='mag',dose='user new dose',enabled=False)
        self.assertEqual(self.h.health_summary(self.state,'2026-09-10')['supplements']['today'],[])
        self.assertEqual(next(iter(self.state['healthRecovery']['intakes'].values()))['snapshot']['dose'],'my scoop')
        with self.assertRaises(ValueError): self.apply('health_supplement_mark',scheduleId='mag',slotId='am',status='taken')
    def test_schedule_requires_explicit_user_dose_slots_and_days(self):
        for patch in [{},{'dose':'5mg'},{'dose':'5mg','slots':[{'id':'x','time':'morning'}]}]:
            with self.assertRaises(ValueError): self.apply('health_supplement_schedule',id='s',name='D',**patch)
        self.schedule()
        with self.assertRaises(ValueError): self.apply('health_supplement_mark',scheduleId='mag',slotId='no',status='taken')
        self.apply('health_supplement_schedule',id='mag',weekdays=[0])
        self.assertEqual(self.h.health_summary(self.state,'2026-09-10')['supplements']['today'],[])
    def test_partial_checkin_readiness_legacy_preserved(self):
        self.apply('health_checkin',energy=2,note='sore legs')
        self.apply('health_checkin',stress=4)
        row=self.state['healthRecovery']['checkins']['2026-09-10']
        self.assertEqual((row['energy'],row['stress'],row['note']),(2,4,'sore legs'))
        self.assertNotIn('soreness',row)
        self.apply('health_sleep',durationMinutes=480)
        summary=self.h.health_summary(self.state,'2026-09-10')
        self.assertEqual(summary['readiness']['level'],'low')
        self.assertEqual(summary['readiness']['trainingReference'],self.state['trainingHub'])
        self.assertEqual(self.h.health_summary(self.state,'2026-09-11')['readiness']['level'],'insufficient_data')
        self.apply('health_checkin',energy=5,stress=1,wellbeing=5)
        self.assertEqual(self.h.health_summary(self.state,'2026-09-10')['readiness']['level'],'high')
        for value in [0,6,1.5,True,'2']:
            with self.assertRaises(ValueError): self.apply('health_checkin',mood=value)
    def test_unknown_fields_future_versions_and_note_only(self):
        self.state['healthRecovery']={'version':1,'future':{'keep':42},'checkins':{'2026-09-10':{'future':'keep'}}}
        self.apply('health_checkin',note='feels great')
        self.assertEqual(self.state['healthRecovery']['checkins']['2026-09-10']['future'],'keep')
        self.assertEqual(self.state['healthRecovery']['future'],{'keep':42})
        self.state['healthRecovery']['version']=2
        with self.assertRaises(ValueError): self.apply('health_checkin',energy=4)

class DomainBoundaryTests(SleepTests):
    def test_reserved_ids_rejected(self):
        for ident in ['__proto__','constructor','prototype']:
            with self.assertRaises(ValueError):
                self.apply('health_supplement_schedule',id=ident,name='name',dose='user text',slots=[{'id':'am','time':'08:00'}],weekdays=[3],enabled=True)
    def test_readiness_references_identify_missing_and_stale_projections(self):
        self.apply('health_sleep',durationMinutes=480)
        self.apply('health_checkin',energy=4,wellbeing=4)
        self.state['trainingHub']={'readiness':{'localDate':'2026-09-09','result':{'status':'red','score':12}}}
        self.state['jumpLab']={'today':{'readiness':{'status':'yellow','score':45}}}
        summary=self.h.health_summary(self.state,'2026-09-10')
        refs=summary['readiness']['context']
        self.assertEqual(refs['training']['freshness'],'stale')
        self.assertEqual(refs['training']['readiness'],self.state['trainingHub']['readiness'])
        self.assertEqual(refs['jump']['freshness'],'undated')
        self.assertEqual(summary['readiness']['level'],'high') # separate recovery estimate, never replaces red training signal
