'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const base = 'ba8214911f5942fdbf36269e1e992eb7607b40f8';
const release = '4c74d5216e2cfcca5a14bdaf179cf520aecfd685';
const read = name => execFileSync('git', ['show', `${release}:${name}`], { cwd: root, encoding: 'utf8' });
const original = name => execFileSync('git', ['show', `${base}:${name}`], { cwd: root, encoding: 'utf8' });
test('voice promotion changes only script cache key, never home markup or CSS', () => {
  const html = read('ai-home-v2/index.html');
  assert.match(html, /ai-home-v2\.js\?v=20260905-3.1-voice-20260908/);
  assert.equal(html.replace('20260905-3.1-voice-20260908', '20260905-3.1'), original('ai-home-v2/index.html'));
  assert.equal(read('ai-home-v2/ai-home-v2.css'), original('ai-home-v2/ai-home-v2.css'));
});
test('voice promotion leaves all non-AI production sources and Manual/SW assets byte-identical', () => {
  const names = execFileSync('git', ['ls-tree', '-r', '--name-only', base], { cwd: root, encoding: 'utf8' }).trim().split('\n');
  const protectedNames = names.filter(name => !name.startsWith('tests/') && !name.startsWith('docs/') && !name.startsWith('.github/') &&
    !['ai-home-v2/ai-home-v2.js', 'ai-home-v2/index.html', 'ai-home-v2/README.md'].includes(name));
  for (const name of protectedNames) {
    const expected = execFileSync('git', ['rev-parse', `${base}:${name}`], { cwd: root, encoding: 'utf8' }).trim();
    const actual = execFileSync('git', ['rev-parse', `${release}:${name}`], { cwd: root, encoding: 'utf8' }).trim();
    assert.equal(actual, expected, name);
  }
});

// Health work starts at this immutable managed base, whose design intentionally
// differs from the installed snapshot. Never regenerate these working-tree assets.
const featureBase = 'accb555b0da3b90eed9d1708ee68a286506d4feb';
test('health feature preserves existing sources except the three authorized Hermes helpers', () => {
  const names = execFileSync('git', ['ls-tree', '-r', '--name-only', featureBase], {cwd:root,encoding:'utf8'}).trim().split('\n');
  const helpers = ['hermes-control-v1/dvizh_context.py','hermes-control-v1/dvizh_proposals.py','hermes-control-v1/dvizh_proposal_bridge.py'];
  // Exactly this test may evolve its historical assertion. No directory exclusions.
  const permitted = new Set([...helpers, 'tests/ai-home-v2/voice-isolation.test.cjs']);
  for (const name of names.filter(name => !permitted.has(name))) {
    assert.equal(execFileSync('git',['hash-object','--',name],{cwd:root,encoding:'utf8'}).trim(),
      execFileSync('git',['rev-parse',`${featureBase}:${name}`],{cwd:root,encoding:'utf8'}).trim(),name);
  }
  const manifest=JSON.parse(fs.readFileSync(path.join(root,'minimal-ui-v1/health-recovery-v1/manifests/health-recovery-privileged.json'),'utf8'));
  assert.deepEqual(manifest.operations.map(o=>o.source).sort(),helpers.sort());
  const crypto=require('node:crypto');
  for(const op of manifest.operations)assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root,op.source))).digest('hex'),op.sha256,op.source);
  const feature=path.join(root,'minimal-ui-v1/health-recovery-v1');
  const baselineSync=fs.readFileSync(path.join(feature,'baseline/static/sync.js'),'utf8');
  const start=baselineSync.indexOf('  function reconcile('),end=baselineSync.indexOf('  // One-time upgrade:',start);
  const expectedSync=(baselineSync.slice(0,start)+fs.readFileSync(path.join(feature,'sync-health.js'),'utf8')+baselineSync.slice(start,end).replaceAll('reconcile(', 'reconcileJSON(')+baselineSync.slice(end))
    .replace('    state.__sync = sync;\n    return state;', '    state.__sync = sync;\n    return normalizeHealthSleep(state);');
  assert.equal(fs.readFileSync(path.join(feature,'dist/sync.js'),'utf8'),expectedSync,'exact authorized health sync delta');
  for(const name of ['ai-home-v2.js','ai-home-v2.css','index.html','styles.css','boot.js','sw.js']) {
    const feature='minimal-ui-v1/health-recovery-v1/';
    assert.deepEqual(fs.readFileSync(path.join(root,feature+'dist/'+name)),fs.readFileSync(path.join(root,feature+'baseline/static/'+name)),name);
  }
});
