'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { test } = require('node:test');

const repo = path.resolve(__dirname, '..');
const installer = path.join(repo, 'install-dvizh-microphone-permissions-policy-fix.sh');

const serverSource = `
class Handler:
    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")

    def static_response(self, asset):
        self._security_headers()
        return "text/html" if asset.endswith(".html") else "application/javascript"

    def json_response(self):
        self._security_headers()
        return "application/json"

ROUTES = {"/api/state": "state", "/auth/login": "auth is external"}
`;

test('installer permits same-origin microphone without relaxing other policies or routes', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'dvizh-mic-policy-'));
  try {
    const target = path.join(root, 'server.py');
    fs.writeFileSync(target, serverSource);
    execFileSync('bash', [installer], {
      cwd: repo,
      env: { ...process.env, DVIZH_SERVER_PATH: target },
      stdio: 'pipe'
    });
    const patched = fs.readFileSync(target, 'utf8');
    assert.doesNotMatch(patched, /microphone=\(\)/);
    assert.match(patched, /microphone=\(self\)/);
    assert.match(patched, /camera=\(\)/);
    assert.match(patched, /geolocation=\(\)/);
    assert.match(patched, /payment=\(\)/);
    assert.match(patched, /"\/api\/state": "state"/);
    assert.match(patched, /"\/auth\/login": "auth is external"/);

    const probe = `
import importlib.util, json
spec = importlib.util.spec_from_file_location('server', ${JSON.stringify(target)})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
class Probe(module.Handler):
    def __init__(self): self.headers = []
    def send_header(self, key, value): self.headers.append((key, value))
def headers_for(method, arg=None):
    probe = Probe()
    result = getattr(probe, method)(arg) if arg else getattr(probe, method)()
    return result, dict(probe.headers)
html, html_headers = headers_for('static_response', 'voice.html')
js, js_headers = headers_for('static_response', 'voice.js')
state, state_headers = headers_for('json_response')
print(json.dumps({'html': [html, html_headers], 'js': [js, js_headers], 'state': [state, state_headers], 'routes': module.ROUTES}))
`;
    const result = JSON.parse(execFileSync('python3', ['-c', probe], { encoding: 'utf8' }));
    for (const headers of [result.html[1], result.js[1], result.state[1]]) {
      assert.equal(headers['Permissions-Policy'], 'camera=(), microphone=(self), geolocation=(), payment=()');
    }
    assert.equal(result.html[0], 'text/html');
    assert.equal(result.js[0], 'application/javascript');
    assert.equal(result.state[0], 'application/json');
    assert.deepEqual(result.routes, { '/api/state': 'state', '/auth/login': 'auth is external' });
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
