import unittest
from test_domain import ROOT, module

class NaturalInputBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.ai=module(ROOT.parents[1]/'ai-home-v2/ai_home_bridge.py','health_ai_home')
    def test_real_hermes_boundary_preserves_natural_inputs(self):
        # These are transport/prompt contracts, not a claim of live model evaluation.
        for utterance in ['I slept 23:30 to 07:00, quality 4','Slept 7 hours','How was my sleep this week?', 'Took my morning magnesium', 'Skip the evening slot', 'What supplements remain?', 'Add magnesium in the evening', 'energy 2, sore legs', 'feels great', 'stress 4', 'Readiness today?', 'Summarize today']:
            messages=self.ai.hermes_messages({'aiHomeMessages':[]},{'text':utterance})
            self.assertEqual(messages[-1]['content'],utterance)
            prompt=messages[0]['content']
            for word in ['health_sleep','health_checkin','health_supplement_schedule','health_supplement_mark','dvizhctl context','dvizhctl propose','durationMinutes','slotId','1–5','0–3']:
                self.assertIn(word,prompt)
            self.assertIn('sore legs',prompt)
            self.assertIn('не выдумывай',prompt)
    def test_voice_and_history_boundary_unchanged(self):
        baseline=module(ROOT/'baseline/helpers/ai_home_bridge.py','old_ai_home')
        state={'aiHomeMessages':[{'role':'user','content':'earlier'},{'role':'assistant','content':'reply'}]}
        request={'text':'voice transcribed request'}
        self.assertEqual(self.ai.hermes_messages(state,request)[1:],baseline.hermes_messages(state,request)[1:])
