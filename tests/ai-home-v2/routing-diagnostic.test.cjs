'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const project = path.resolve(__dirname, '../..');
const diagnostic = path.join(project, 'diagnose-dvizh-ai-home-v2-routing.sh');

function fixture(t) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-home-v2-routing-'));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const root = path.join(temp, 'site');
  const bin = path.join(temp, 'bin');
  fs.mkdirSync(root);
  fs.mkdirSync(bin);
  const files = {
    'index.html': '<!doctype html><title>STABLE</title><script src="./app.js?v=dvizh-pre-ai-recovery-v1"></script>\n',
    'app.js': "console.log('stable');\n",
    'styles.css': 'body{background:#000}\n',
    'sw.js': '// stable worker\n',
    'ai-home-v2-preview.html': fs.readFileSync(path.join(project, 'ai-home-v2', 'index.html'), 'utf8'),
    'ai-home-v2.js': fs.readFileSync(path.join(project, 'ai-home-v2', 'ai-home-v2.js'), 'utf8'),
    'ai-home-v2.css': fs.readFileSync(path.join(project, 'ai-home-v2', 'ai-home-v2.css'), 'utf8'),
  };
  for (const [name, content] of Object.entries(files)) fs.writeFileSync(path.join(root, name), content);

  const fakeCurl = `#!/usr/bin/env bash
set -euo pipefail
headers=''; body=''; writefmt=''; url=''
while (($#)); do
  case "$1" in
    --silent|--show-error|--location) shift ;;
    --max-time|-H) shift 2 ;;
    -D) headers="$2"; shift 2 ;;
    -o) body="$2"; shift 2 ;;
    -w) writefmt="$2"; shift 2 ;;
    --*) shift ;;
    *) url="$1"; shift ;;
  esac
done
[[ -n "$headers" && -n "$body" && -n "$url" ]]
pathpart="\${url#*://}"
pathpart="/\${pathpart#*/}"
pathpart="\${pathpart%%\\?*}"
code=200
case "$pathpart" in
  /|/index.html) src="$FIXTURE_ROOT/index.html" ;;
  /ai-home-v2-preview.html) src="$FIXTURE_ROOT/ai-home-v2-preview.html" ;;
  /manual.html)
    if [[ -f "$FIXTURE_ROOT/manual.html" ]]; then src="$FIXTURE_ROOT/manual.html"; else src="$FIXTURE_ROOT/index.html"; fi ;;
  *) code=404; src='' ;;
esac
printf 'HTTP/1.1 %s Test\\r\\nContent-Type: text/html\\r\\nCache-Control: no-store\\r\\n\\r\\n' "$code" > "$headers"
if [[ -n "$src" ]]; then cat "$src" > "$body"; else printf 'not found' > "$body"; fi
if [[ -n "$writefmt" ]]; then printf '%s' "$code"; fi
`;
  fs.writeFileSync(path.join(bin, 'curl'), fakeCurl, { mode: 0o755 });

  const run = () => spawnSync('bash', [diagnostic], {
    encoding: 'utf8', timeout: 15000,
    env: {
      ...process.env,
      PATH: `${bin}:${process.env.PATH}`,
      FIXTURE_ROOT: root,
      DVIZH_AI_HOME_V2_ROOT: root,
      DVIZH_AI_HOME_V2_ROUTE_BASE_URL: 'http://fixture',
    },
  });
  return { temp, root, files, run };
}

test('read-only routing probe detects file-backed root and manual fallback without changing site files', t => {
  const h = fixture(t);
  const before = Object.fromEntries(Object.keys(h.files).map(name => [name, fs.readFileSync(path.join(h.root, name))]));
  const result = h.run();
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /index\.html <-> GET \/\s+MATCH/);
  assert.match(result.stdout, /index\.html <-> GET \/index\s+MATCH/);
  assert.match(result.stdout, /preview file <-> GET preview\s+MATCH/);
  assert.match(result.stdout, /manual file <-> GET manual\s+local=ABSENT/);
  assert.match(result.stdout, /manual_absent_http_relation=FALLBACK_TO_ROOT_INDEX/);
  assert.match(result.stdout, /RESULT: read-only probe complete; site files unchanged/);
  for (const [name, data] of Object.entries(before)) {
    assert.deepEqual(fs.readFileSync(path.join(h.root, name)), data, name);
  }
  assert.equal(fs.existsSync(path.join(h.root, 'manual.html')), false);
});

test('routing diagnostic contains no site mutation or service restart path', () => {
  const source = fs.readFileSync(diagnostic, 'utf8');
  assert.match(source, /http:\/\/127\.0\.0\.1:8000/);
  assert.match(source, /snapshot_known/);
  assert.doesNotMatch(source, /systemctl\s+(?:restart|start|stop|enable|disable|daemon-reload)/);
  assert.doesNotMatch(source, /curl[^\n]*(?:-X|--request)\s*(?:PUT|POST|PATCH|DELETE)/i);
  assert.doesNotMatch(source, /(?:cp|mv|install|tee)\s+[^\n]*\$APP_ROOT/);
  assert.doesNotMatch(source, /rm\s+-[^\n]*\$APP_ROOT/);
});
