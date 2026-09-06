'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { test } = require('node:test');

const repo = path.resolve(__dirname, '..');
const installer = path.join(repo, 'install-dvizh-jump-sync-stability-fix.sh');

const bridgeSource = `
import json

def canonical(value):
    return json.dumps(value, sort_keys=True)

def iso():
    return 'volatile-sync-time'

def normalized(value):
    if not isinstance(value, dict):
        return None
    result = dict(value)
    for key in ("syncedAt", "optimisticProfile", "optimisticMeasurements", "selectedDay"):
        result.pop(key, None)
    return result

def merge_projection(state, projection):
    current = state.get("jumpLab")
    if canonical(normalized(current)) == canonical(normalized(projection)):
        return state, False
    merged = json.loads(canonical(state))
    payload = dict(projection)
    payload["syncedAt"] = iso()
    merged["jumpLab"] = payload
    return merged, True
`;

test('installer makes timestamp-only Jump Lab projections stable', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'dvizh-jump-sync-'));
  try {
    const target = path.join(root, 'jump_web_bridge.py');
    fs.writeFileSync(target, bridgeSource);
    execFileSync('bash', [installer], {
      cwd: repo,
      env: { ...process.env, DVIZH_JUMP_BRIDGE_PATH: target },
      stdio: 'pipe'
    });
    const patched = fs.readFileSync(target, 'utf8');
    assert.match(patched, /packet = result\.get\("coachPacket"\)/);
    assert.match(patched, /packet\.pop\("exportedAt", None\)/);

    const module = {};
    const python = `
import importlib.util, json
spec = importlib.util.spec_from_file_location('bridge', ${JSON.stringify(target)})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
state = {'jumpLab': {'coachPacket': {'title': 'Plan', 'exportedAt': 'old'}, 'syncedAt': 'old-sync', 'webCommands': []}}
projection = {'coachPacket': {'title': 'Plan', 'exportedAt': 'new'}, 'webCommands': []}
merged, changed = module.merge_projection(state, projection)
print(json.dumps({'changed': changed, 'same_object': merged == state}))
`;
    const result = JSON.parse(execFileSync('python3', ['-c', python], { encoding: 'utf8' }));
    assert.deepEqual(result, { changed: false, same_object: true });
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
