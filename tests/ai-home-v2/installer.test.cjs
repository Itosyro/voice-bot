'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const project = path.resolve(__dirname, '../..');
function fixture(t, { manual = false } = {}) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-home-v2-test-'));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const root = path.join(temp, 'site'), source = path.join(temp, 'source');
  fs.mkdirSync(root); fs.mkdirSync(source);
  const stable = {
    'index.html': '<!doctype html><title>ДВИЖ</title><main>STABLE MANUAL</main><script src="app.js"></script>',
    'app.js': "console.log('stable');\n",
    'styles.css': 'body { color: white; }\n',
    'sw.js': '// Stable worker, do not edit.\n'
  };
  if (manual) stable['manual.html'] = '<!doctype html>EXISTING MANUAL';
  for (const [name, content] of Object.entries(stable)) fs.writeFileSync(path.join(root, name), content);
  for (const name of ['index.html', 'ai-home-v2.js', 'ai-home-v2.css']) fs.copyFileSync(path.join(project, 'ai-home-v2', name), path.join(source, name));
  const run = (args = [], env = {}) => spawnSync('bash', [path.join(project, 'install-dvizh-ai-home-v2.sh'), ...args], {
    encoding: 'utf8', timeout: 15000,
    env: { ...process.env, TMPDIR: temp, DVIZH_AI_HOME_V2_ROOT: root, DVIZH_AI_HOME_V2_SOURCE_DIR: source, ...env }
  });
  const intact = () => {
    for (const [name, value] of Object.entries(stable)) assert.equal(fs.readFileSync(path.join(root, name), 'utf8'), value, name);
  };
  const ok = result => assert.equal(result.status, 0, result.stdout + result.stderr);
  const fail = result => assert.notEqual(result.status, 0, result.stdout + result.stderr);
  return { root, source, temp, stable, run, intact, ok, fail };
}
test('default mode only validates and leaves the site directory byte-for-byte unchanged', t => {
  const h = fixture(t); h.ok(h.run()); h.intact();
  assert.deepEqual(fs.readdirSync(h.root).sort(), Object.keys(h.stable).sort());
});
test('preview install creates only its own page, preserving absent manual and stable root', t => {
  const h = fixture(t); h.ok(h.run(['--install-preview'])); h.intact();
  assert.equal(fs.existsSync(path.join(h.root, 'manual.html')), false);
  assert.equal(fs.readFileSync(path.join(h.root, 'ai-home-v2-preview.html'), 'utf8'), fs.readFileSync(path.join(h.source, 'index.html'), 'utf8'));
  for (const name of ['ai-home-v2.js', 'ai-home-v2.css']) {
    assert.equal(fs.readFileSync(path.join(h.root, name), 'utf8'), fs.readFileSync(path.join(h.source, name), 'utf8'));
    assert.equal(fs.statSync(path.join(h.root, name)).mode & 0o777, 0o644);
  }
  assert.ok(!fs.readdirSync(h.root).some(name => name.startsWith('.')));
});
test('repeated preview install does not overwrite an existing manual interface', t => {
  const h = fixture(t, { manual: true }); h.ok(h.run(['--install-preview'])); h.ok(h.run(['--install-preview'])); h.intact();
});
test('missing payload fails before modifying any site files', t => {
  const h = fixture(t); fs.unlinkSync(path.join(h.source, 'ai-home-v2.css')); h.fail(h.run(['--install-preview'])); h.intact();
  assert.deepEqual(fs.readdirSync(h.root).sort(), Object.keys(h.stable).sort());
});
test('worker/cache-mutating payload is rejected', t => {
  const h = fixture(t); fs.appendFileSync(path.join(h.source, 'ai-home-v2.js'), '\nnavigator.serviceWorker.getRegistrations();');
  h.fail(h.run(['--install-preview'])); h.intact(); assert.equal(fs.existsSync(path.join(h.root, 'ai-home-v2-preview.html')), false);
});
for (const quote of ['"', "'"]) test(`old application bundle with ${quote} quotes is rejected`, t => {
  const h = fixture(t); fs.appendFileSync(path.join(h.source, 'index.html'), `<script src=${quote}/app.js${quote}></script>`);
  h.fail(h.run(['--install-preview'])); h.intact();
});
test('symlink destination is rejected and its target is untouched', t => {
  const h = fixture(t); const target = path.join(h.temp, 'outside.txt'); fs.writeFileSync(target, 'KEEP');
  fs.symlinkSync(target, path.join(h.root, 'ai-home-v2.js')); h.fail(h.run(['--install-preview']));
  assert.equal(fs.readFileSync(target, 'utf8'), 'KEEP'); h.intact();
});
test('root already replaced by AI without a manual page is refused', t => {
  const h = fixture(t); fs.writeFileSync(path.join(h.root, 'index.html'), '<script src="/ai-home-v2.js"></script>');
  h.fail(h.run(['--install-preview'])); assert.equal(fs.existsSync(path.join(h.root, 'manual.html')), false);
});
test('promotion without an installed preview and unexpected flags are refused', t => {
  const h = fixture(t); h.fail(h.run(['--promote'])); h.fail(h.run(['--install-preview', '--force'])); h.intact();
});
test('a mid-install failure restores previous preview files and does not create a manual alias', t => {
  const h = fixture(t); const before = { 'ai-home-v2.js': 'old js', 'ai-home-v2.css': 'old css', 'ai-home-v2-preview.html': 'old preview' };
  for (const [name, data] of Object.entries(before)) fs.writeFileSync(path.join(h.root, name), data);
  const bin = path.join(h.temp, 'bin'); fs.mkdirSync(bin);
  fs.writeFileSync(path.join(bin, 'mv'), '#!/bin/bash\nfor arg in "$@"; do case "$arg" in */ai-home-v2-preview.html) exit 42;; esac; done\nexec /bin/mv "$@"\n', { mode: 0o755 });
  h.fail(h.run(['--install-preview'], { PATH: `${bin}:${process.env.PATH}` })); h.intact();
  for (const [name, data] of Object.entries(before)) assert.equal(fs.readFileSync(path.join(h.root, name), 'utf8'), data);
  assert.equal(fs.existsSync(path.join(h.root, 'manual.html')), false);
  assert.ok(!fs.readdirSync(h.root).some(name => name.startsWith('.')));
});
test('installer uses a local checkout and read-only default without service changes', () => {
  const script = fs.readFileSync(path.join(project, 'install-dvizh-ai-home-v2.sh'), 'utf8');
  assert.doesNotMatch(script, /raw\.githubusercontent|systemctl\s+(?:restart|stop|start|enable|disable|daemon-reload)/);
  assert.match(script, /MODE="\$\{DVIZH_AI_HOME_V2_MODE:-check\}"/);
});

function promote(h) { return h.run(['--promote']); }
test('explicit legacy preview environment mode is preserved', t => {
  const h = fixture(t); h.ok(h.run([], { DVIZH_AI_HOME_V2_MODE: 'preview' })); h.intact();
  assert.ok(fs.existsSync(path.join(h.root, 'ai-home-v2-preview.html')));
});
test('explicit promote preserves stable root as manual and repeated promote is safe', t => {
  const h = fixture(t); h.ok(h.run(['--install-preview'])); h.ok(promote(h));
  assert.equal(fs.readFileSync(path.join(h.root, 'manual.html'), 'utf8'), h.stable['index.html']);
  assert.equal(fs.readFileSync(path.join(h.root, 'index.html'), 'utf8'), fs.readFileSync(path.join(h.source, 'index.html'), 'utf8'));
  h.ok(promote(h));
  assert.equal(fs.readFileSync(path.join(h.root, 'manual.html'), 'utf8'), h.stable['index.html']);
  for (const name of ['app.js', 'styles.css', 'sw.js']) assert.equal(fs.readFileSync(path.join(h.root, name), 'utf8'), h.stable[name]);
});
test('promote cannot replace a different existing manual or promote changed assets', t => {
  const h = fixture(t, { manual: true }); h.ok(h.run(['--install-preview'])); h.fail(promote(h)); h.intact();
  fs.unlinkSync(path.join(h.root, 'manual.html')); fs.appendFileSync(path.join(h.root, 'ai-home-v2.js'), '\n// changed');
  h.fail(promote(h)); assert.equal(fs.readFileSync(path.join(h.root, 'index.html'), 'utf8'), h.stable['index.html']);
});
test('preview after promotion cannot silently update assets used by the main page', t => {
  const h = fixture(t); h.ok(h.run(['--install-preview'])); h.ok(promote(h));
  const before = fs.readFileSync(path.join(h.root, 'ai-home-v2.js'), 'utf8');
  fs.appendFileSync(path.join(h.source, 'ai-home-v2.js'), '\n// next release'); h.fail(h.run(['--install-preview']));
  assert.equal(fs.readFileSync(path.join(h.root, 'ai-home-v2.js'), 'utf8'), before);
});
