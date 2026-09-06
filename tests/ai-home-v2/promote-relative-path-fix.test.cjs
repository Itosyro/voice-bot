'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const project = path.resolve(__dirname, '../..');
const installer = path.join(project, 'install-dvizh-ai-home-v2.sh');
const basePromote = path.join(project, 'promote-dvizh-ai-home-v2-from-github.sh');
const wrapper = path.join(project, 'promote-dvizh-ai-home-v2-relative-fix.sh');

function fileUrl(fileOrDir) {
  return new URL(`file://${path.resolve(fileOrDir).replaceAll('\\', '/')}`).href.replace(/\/$/, '');
}

function fixture(t) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-home-v2-relative-promote-'));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const root = path.join(temp, 'site');
  fs.mkdirSync(root);
  const stable = {
    'index.html': '<!doctype html><title>ДВИЖ</title><main>STABLE MANUAL</main><script src="./app.js?v=dvizh-pre-ai-recovery-v1"></script>',
    'app.js': "console.log('stable app');\n",
    'styles.css': 'body{background:#000}\n',
    'sw.js': '// DVIZH_PRE_AI_RECOVERY_NETWORK_ONLY_SW_V1\n',
  };
  for (const [name, content] of Object.entries(stable)) fs.writeFileSync(path.join(root, name), content);

  const preview = spawnSync('bash', [installer, '--install-preview'], {
    encoding: 'utf8', timeout: 15000,
    env: {
      ...process.env,
      TMPDIR: temp,
      DVIZH_AI_HOME_V2_ROOT: root,
      DVIZH_AI_HOME_V2_SOURCE_DIR: path.join(project, 'ai-home-v2'),
    },
  });
  assert.equal(preview.status, 0, preview.stdout + preview.stderr);

  const run = (extra = {}, args = []) => spawnSync('bash', [wrapper, ...args], {
    encoding: 'utf8', timeout: 30000,
    env: {
      ...process.env,
      TMPDIR: temp,
      DVIZH_AI_HOME_V2_ROOT: root,
      DVIZH_AI_HOME_V2_PATCH_SOURCE_URL: fileUrl(basePromote),
      DVIZH_AI_HOME_V2_PROMOTE_BASE_URL: fileUrl(project),
      ...extra,
    },
  });
  return { temp, root, stable, run };
}

test('recovered relative ./app.js manual promotes successfully', t => {
  const h = fixture(t);
  const result = h.run();
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /compatibility-fix/);
  assert.match(result.stdout, /promotion подтверждён/);
  assert.match(fs.readFileSync(path.join(h.root, 'index.html'), 'utf8'), /ai-home-v2\.js/);
  assert.equal(fs.readFileSync(path.join(h.root, 'manual.html'), 'utf8'), h.stable['index.html']);
  assert.match(fs.readFileSync(path.join(h.root, 'manual.html'), 'utf8'), /src="\.\/app\.js\?v=dvizh-pre-ai-recovery-v1"/);
  for (const name of ['app.js', 'styles.css', 'sw.js']) {
    assert.equal(fs.readFileSync(path.join(h.root, name), 'utf8'), h.stable[name], name);
  }
});

test('relative-path compatibility fix keeps automatic rollback', t => {
  const h = fixture(t);
  const result = h.run({ DVIZH_AI_HOME_V2_TEST_FAIL_AFTER_PROMOTE: '1' });
  assert.notEqual(result.status, 0, result.stdout + result.stderr);
  assert.equal(fs.readFileSync(path.join(h.root, 'index.html'), 'utf8'), h.stable['index.html']);
  assert.equal(fs.existsSync(path.join(h.root, 'manual.html')), false);
  assert.match(result.stderr, /rollback завершён/);
});

test('compatibility wrapper is pinned and only patches the four legacy app.js checks', t => {
  const h = fixture(t);
  const result = h.run({}, ['--force']);
  assert.notEqual(result.status, 0);
  assert.equal(fs.readFileSync(path.join(h.root, 'index.html'), 'utf8'), h.stable['index.html']);

  const source = fs.readFileSync(wrapper, 'utf8');
  assert.match(source, /BASE_PROMOTE_COMMIT="575e174e9b2c1ad06c35fa2c428314f9ffaa2fa6"/);
  assert.match(source, /BASE_PROMOTE_BLOB="81d8cbdaa351991f9e8bf0bd26ccac93b4a098d1"/);
  assert.match(source, /count != 4/);
  assert.match(source, /\(\\\\\.\/\|\/\)\?app/);
  assert.doesNotMatch(source, /systemctl\s+(?:restart|start|stop|enable|disable|daemon-reload)/);
  assert.doesNotMatch(source, /serviceWorker|caches\s*\./);
});
