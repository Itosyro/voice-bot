'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');

const project = path.resolve(__dirname, '../..');
const bootstrap = path.join(project, 'install-dvizh-ai-home-v2-preview-from-github.sh');

function makeRoot(t) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-home-v2-bootstrap-'));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const root = path.join(temp, 'site');
  fs.mkdirSync(root);
  const stable = {
    'index.html': '<!doctype html><title>STABLE ROOT</title><script src="app.js"></script>',
    'app.js': "console.log('stable app');\n",
    'styles.css': 'body{background:#000}\n',
    'sw.js': '// stable worker\n',
  };
  for (const [name, content] of Object.entries(stable)) fs.writeFileSync(path.join(root, name), content);
  const intact = () => {
    for (const [name, content] of Object.entries(stable)) {
      assert.equal(fs.readFileSync(path.join(root, name), 'utf8'), content, name);
    }
  };
  return { temp, root, stable, intact };
}

function run(root, baseUrl, args = []) {
  return spawnSync('bash', [bootstrap, ...args], {
    encoding: 'utf8', timeout: 30000,
    env: {
      ...process.env,
      DVIZH_AI_HOME_V2_ROOT: root,
      DVIZH_AI_HOME_V2_BOOTSTRAP_BASE_URL: baseUrl,
    },
  });
}

function fileUrl(dir) {
  return new URL(`file://${path.resolve(dir).replaceAll('\\', '/')}/`).href.replace(/\/$/, '');
}

test('immutable bootstrap installs only the preview from the pinned release payload', t => {
  const h = makeRoot(t);
  const result = run(h.root, fileUrl(project));
  assert.equal(result.status, 0, result.stdout + result.stderr);
  h.intact();
  assert.equal(fs.existsSync(path.join(h.root, 'manual.html')), false);
  assert.equal(
    fs.readFileSync(path.join(h.root, 'ai-home-v2-preview.html'), 'utf8'),
    fs.readFileSync(path.join(project, 'ai-home-v2', 'index.html'), 'utf8'),
  );
  for (const name of ['ai-home-v2.js', 'ai-home-v2.css']) {
    assert.equal(
      fs.readFileSync(path.join(h.root, name), 'utf8'),
      fs.readFileSync(path.join(project, 'ai-home-v2', name), 'utf8'),
      name,
    );
  }
});

test('bootstrap refuses a payload whose Git blob does not match the pinned release', t => {
  const h = makeRoot(t);
  const release = path.join(h.temp, 'release');
  fs.mkdirSync(path.join(release, 'ai-home-v2'), { recursive: true });
  fs.copyFileSync(path.join(project, 'install-dvizh-ai-home-v2.sh'), path.join(release, 'install-dvizh-ai-home-v2.sh'));
  for (const name of ['index.html', 'ai-home-v2.js', 'ai-home-v2.css']) {
    fs.copyFileSync(path.join(project, 'ai-home-v2', name), path.join(release, 'ai-home-v2', name));
  }
  fs.appendFileSync(path.join(release, 'ai-home-v2', 'ai-home-v2.js'), '\n// tampered\n');
  const result = run(h.root, fileUrl(release));
  assert.notEqual(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /immutable payload/);
  h.intact();
  assert.equal(fs.existsSync(path.join(h.root, 'ai-home-v2-preview.html')), false);
});

test('bootstrap cannot be used as a promotion entry point', t => {
  const h = makeRoot(t);
  const result = run(h.root, fileUrl(project), ['--promote']);
  assert.notEqual(result.status, 0);
  h.intact();
  assert.equal(fs.existsSync(path.join(h.root, 'ai-home-v2-preview.html')), false);
});

test('bootstrap release source and blob identities are immutable', () => {
  const script = fs.readFileSync(bootstrap, 'utf8');
  assert.match(script, /RELEASE_COMMIT="aac4a406ff5c30e7daf206bec65df93d2279ac8d"/);
  for (const sha of [
    '88ad4b9f4db39614ccc1ba4c70b256f4a3c4d2b0',
    '48c5f992bf1dce753575a4fb9fcc2f1f77160a76',
    'a928cd3fb2d7e46485c16387cf10f829b43a43c5',
    '273934a33d7913c45f4b7656315aeedfd6e4e813',
  ]) assert.match(script, new RegExp(sha));
  assert.doesNotMatch(script, /install-dvizh-ai-home-v2\.sh" --promote/);
  assert.doesNotMatch(script, /systemctl\s+(?:restart|start|stop|enable|disable|daemon-reload)/);
});
