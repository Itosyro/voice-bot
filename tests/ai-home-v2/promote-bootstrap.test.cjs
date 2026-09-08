'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const project = path.resolve(__dirname, '../..');
const pinnedRelease = require('./pinned-release.cjs');
const installer = path.join(project, 'install-dvizh-ai-home-v2.sh');
const bootstrap = path.join(project, 'promote-dvizh-ai-home-v2-from-github.sh');

function fileUrl(dir) {
  return new URL(`file://${path.resolve(dir).replaceAll('\\', '/')}/`).href.replace(/\/$/, '');
}

function fixture(t) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-home-v2-promote-bootstrap-'));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const release = pinnedRelease(temp);
  const root = path.join(temp, 'site');
  fs.mkdirSync(root);
  const stable = {
    'index.html': '<!doctype html><title>STABLE ROOT</title><main>MANUAL</main><script src="app.js"></script>',
    'app.js': "console.log('stable app');\n",
    'styles.css': 'body{background:#000}\n',
    'sw.js': '// stable worker\n',
  };
  for (const [name, content] of Object.entries(stable)) fs.writeFileSync(path.join(root, name), content);

  const preview = spawnSync('bash', [installer, '--install-preview'], {
    encoding: 'utf8', timeout: 15000,
    env: {
      ...process.env,
      TMPDIR: temp,
      DVIZH_AI_HOME_V2_ROOT: root,
      DVIZH_AI_HOME_V2_SOURCE_DIR: path.join(release, 'ai-home-v2'),
    },
  });
  assert.equal(preview.status, 0, preview.stdout + preview.stderr);

  const run = (args = [], extra = {}) => spawnSync('bash', [bootstrap, ...args], {
    encoding: 'utf8', timeout: 30000,
    env: {
      ...process.env,
      TMPDIR: temp,
      DVIZH_AI_HOME_V2_ROOT: root,
      DVIZH_AI_HOME_V2_PROMOTE_BASE_URL: fileUrl(release),
      ...extra,
    },
  });
  const assertStableRuntime = () => {
    for (const name of ['app.js', 'styles.css', 'sw.js']) {
      assert.equal(fs.readFileSync(path.join(root, name), 'utf8'), stable[name], name);
    }
  };
  return { temp, root, stable, run, assertStableRuntime };
}

test('promotion bootstrap publishes AI root and preserves the old root as manual', t => {
  const h = fixture(t);
  const result = h.run();
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(fs.readFileSync(path.join(h.root, 'index.html'), 'utf8'), /ai-home-v2\.js/);
  assert.equal(fs.readFileSync(path.join(h.root, 'manual.html'), 'utf8'), h.stable['index.html']);
  h.assertStableRuntime();
  assert.match(result.stdout, /promotion подтверждён/);
});

test('failure after promote automatically restores the previous root and removes newly-created manual', t => {
  const h = fixture(t);
  const result = h.run([], { DVIZH_AI_HOME_V2_TEST_FAIL_AFTER_PROMOTE: '1' });
  assert.notEqual(result.status, 0, result.stdout + result.stderr);
  assert.equal(fs.readFileSync(path.join(h.root, 'index.html'), 'utf8'), h.stable['index.html']);
  assert.equal(fs.existsSync(path.join(h.root, 'manual.html')), false);
  h.assertStableRuntime();
  assert.match(result.stderr, /rollback завершён/);
});

test('changed preview is refused before the stable root can be replaced', t => {
  const h = fixture(t);
  fs.appendFileSync(path.join(h.root, 'ai-home-v2.js'), '\n// changed after phone test\n');
  const result = h.run();
  assert.notEqual(result.status, 0, result.stdout + result.stderr);
  assert.equal(fs.readFileSync(path.join(h.root, 'index.html'), 'utf8'), h.stable['index.html']);
  assert.equal(fs.existsSync(path.join(h.root, 'manual.html')), false);
  h.assertStableRuntime();
});

test('promotion bootstrap is idempotent after a successful promote', t => {
  const h = fixture(t);
  let result = h.run();
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const manual = fs.readFileSync(path.join(h.root, 'manual.html'), 'utf8');
  result = h.run();
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(fs.readFileSync(path.join(h.root, 'manual.html'), 'utf8'), manual);
  assert.match(fs.readFileSync(path.join(h.root, 'index.html'), 'utf8'), /ai-home-v2\.js/);
  h.assertStableRuntime();
});

test('promotion bootstrap accepts no flags and cannot float to an unverified release', t => {
  const h = fixture(t);
  const result = h.run(['--force']);
  assert.notEqual(result.status, 0);
  assert.equal(fs.readFileSync(path.join(h.root, 'index.html'), 'utf8'), h.stable['index.html']);
  assert.equal(fs.existsSync(path.join(h.root, 'manual.html')), false);

  const source = fs.readFileSync(bootstrap, 'utf8');
  assert.match(source, /RELEASE_COMMIT="d6418224eae292417a645b2a73da157d939526b9"/);
  for (const sha of [
    '88ad4b9f4db39614ccc1ba4c70b256f4a3c4d2b0',
    '2a703fbc0ca731ae68cf733c0ce6fb9552fceb2e',
    '95b1ce6a09341840802efebb958f41441cc43560',
    '273934a33d7913c45f4b7656315aeedfd6e4e813',
  ]) assert.match(source, new RegExp(sha));
  assert.match(source, /--promote/);
  assert.doesNotMatch(source, /systemctl\s+(?:restart|start|stop|enable|disable|daemon-reload)/);
  assert.doesNotMatch(source, /serviceWorker|caches\s*\./);
});
