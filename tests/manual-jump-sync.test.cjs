'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { test } = require('node:test');

const repo = path.resolve(__dirname, '..');
const installer = path.join(repo, 'install-dvizh-manual-jump-fix.sh');
const pullLatest = `  async function pullLatest({ manual = false } = {}) {
    if (!ready || inFlight || document.visibilityState === 'hidden') return;
    if (manual) setStatus('syncing', 'Проверяю сервер…');
    try {
      const remote = await requestState();
      if (!remote.state) return;
      const remoteRevision = Number(remote.revision) || 0;
      if (remoteRevision <= meta.revision) return;
      const local = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY)));
      const merged = queued ? mergeStates(local, remote.state) : normalizeState(remote.state);
      nativeSet.call(localStorage, STATE_KEY, JSON.stringify(merged));
      meta.revision = remoteRevision;
      meta.lastSyncedAt = remote.updatedAt || isoNow();
      persistMeta();
      if (queued) {
        queuePush();
        reloadAfterSync = appLoaded;
      } else if (appLoaded) {
        window.setTimeout(() => location.reload(), 120);
      }
    } catch (error) {}
  }
`;

test('installer ignores coach export timestamps but reloads on training changes', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'dvizh-manual-jump-'));
  try {
    const sync = path.join(root, 'sync.js');
    fs.writeFileSync(sync, `(() => {\n${pullLatest}\n})();\n`);
    execFileSync('bash', [installer], {
      cwd: repo,
      env: { ...process.env, DVIZH_MANUAL_JUMP_ROOT: root },
      stdio: 'pipe'
    });
    const patched = fs.readFileSync(sync, 'utf8');
    assert.match(patched, /function manualJumpRenderState/);
    assert.match(patched, /manualJumpRenderState\(local\).*manualJumpRenderState\(merged\)/);

    const project = value => JSON.parse(JSON.stringify(value));
    const stable = { jumpLab: { coachPacket: { title: 'План', exportedAt: '2026-09-06T13:00:00.000Z' } } };
    const timestampOnly = { jumpLab: { coachPacket: { title: 'План', exportedAt: '2026-09-06T13:00:05.000Z' } } };
    const changedPlan = { jumpLab: { coachPacket: { title: 'Новый план', exportedAt: '2026-09-06T13:00:05.000Z' } } };
    const helper = patched.match(/function manualJumpRenderState[\s\S]*?\n  }\n\n  async function pullLatest/)[0]
      .replace(/\n\n  async function pullLatest[\s\S]*/, '');
    const renderState = Function('clone', `${helper}; return manualJumpRenderState;`)(project);
    assert.deepEqual(renderState(stable), renderState(timestampOnly));
    assert.notDeepEqual(renderState(stable), renderState(changedPlan));
    assert.deepEqual(stable, project(stable));
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
