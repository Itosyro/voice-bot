"""Execute only selected pure production functions: no module import, DB, or HTTP."""
import ast
import copy
import json
from pathlib import Path

path = Path('/opt/dvizh-jump/dvizh_jump/jump_web_bridge.py')
tree = ast.parse(path.read_text())
names = {'canonical', 'normalized', 'merge_projection'}
selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
assert {node.name for node in selected} == names
scope = {'Any': object, 'json': json, 'iso': lambda: '2026-01-01T00:01:00+00:00'}
exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), scope)
projection = {'version': 1, 'coachPacket': {'exportedAt': '2026-01-01T00:00:00+00:00', 'exercises': []}}
state = {'version': 1, 'tasks': [], 'jumpLab': copy.deepcopy(projection)}
projection['coachPacket']['exportedAt'] = '2026-01-01T00:01:00+00:00'
merged, changed = scope['merge_projection'](state, projection)
assert not changed and merged is state
print('PASS actual Jump merge_projection: exportedAt-only changed=False => sync_once skips PUT')
projection['coachPacket']['exercises'].append({'id': 'synthetic-exercise'})
merged, changed = scope['merge_projection'](state, projection)
assert changed and merged['jumpLab']['syncedAt'] == scope['iso']()
assert state['jumpLab']['coachPacket']['exercises'] == []
print('PASS actual Jump merge_projection: exercise addition changed=True, stamps syncedAt, preserves input')
print('Only selected pure source functions executed; no production modules imported, no DB/API access.')
