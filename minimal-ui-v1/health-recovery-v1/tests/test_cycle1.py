import copy
import json
import subprocess
import unittest
from test_domain import ROOT, module

# Frozen union of Python and ECMAScript whitespace; no runtime category lookup.
WHITESPACE = list(range(0x09, 0x0e)) + list(range(0x1c, 0x21)) + [0x85, 0xa0, 0x1680] + list(range(0x2000, 0x200b)) + [0x2028, 0x2029, 0x202f, 0x205f, 0x3000, 0xfeff]
DAY = '2026-09-10'

class Cycle1Tests(unittest.TestCase):
    def test_explicit_whitespace_differential(self):
        h = module(ROOT/'domain.py', 'cycle1_domain')
        for cp in WHITESPACE + [0x180e, 0x200b, 0x2060]:
            char = chr(cp)
            for field in ['name', 'dose', 'note']:
                for value in [char, char+'A'+char+'B'+char]:
                    with self.subTest(cp=hex(cp), field=field, value=repr(value)):
                        expected = value.strip(''.join(map(chr, WHITESPACE)))
                        p = dict(day=DAY, timezone='UTC', id='s', name='name', dose='dose', slots=[dict(id='am', time='08:00')], weekdays=[3], enabled=True)
                        p[field] = value
                        action = 'health_supplement_schedule'
                        state = {}; before = copy.deepcopy(state)
                        js = json.loads(subprocess.check_output(['node', str(ROOT/'tests/parity.cjs')], input=json.dumps(dict(state=state, actions=[[action,p]], day=DAY)).encode()))
                        accepted = field == 'note' or bool(expected)
                        try: h.health_apply(state, action, p); ok = True
                        except ValueError: ok = False
                        self.assertEqual(ok, accepted, 'Python acceptance')
                        self.assertEqual(js['errors'], [not accepted], 'JS acceptance')
                        if accepted:
                            self.assertEqual(state['healthRecovery']['schedules']['s'][field], expected)
                            self.assertEqual(js['state']['healthRecovery']['schedules']['s'][field], expected)
                        else:
                            self.assertEqual(state, before)
                            self.assertEqual(js['state'], before)

    def test_note_only_prompt_contract(self):
        # Prompt boundary only; actual inference is scored separately, unchanged.
        import ast
        tree = ast.parse((ROOT.parents[1]/'ai-home-v2/ai_home_bridge.py').read_text())
        nodes = [n for n in tree.body if isinstance(n, (ast.Assign, ast.AugAssign)) and isinstance(n.targets[0] if isinstance(n, ast.Assign) else n.target, ast.Name) and (n.targets[0] if isinstance(n, ast.Assign) else n.target).id == 'SYSTEM_PROMPT']
        ns = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<prompt only>', 'exec'), ns)
        prompt = ns['SYSTEM_PROMPT']
        self.assertIn('Передавай только поля, которые пользователь явно изменил в текущем сообщении; не повторяй существующие структурированные поля из context.', prompt)
        self.assertIn('«feels great» при сохранённом energy:3 → {day, timezone, note}, без energy и любых других численных оценок.', prompt)
