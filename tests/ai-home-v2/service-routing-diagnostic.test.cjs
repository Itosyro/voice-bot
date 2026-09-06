'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const project = path.resolve(__dirname, '../..');
const probe = path.join(project, 'diagnose-dvizh-service-routing.sh');
const source = fs.readFileSync(probe, 'utf8');

test('live dvizh service routing probe is read-only and does not inspect process environment', () => {
  assert.match(source, /systemctl show dvizh\.service/);
  assert.match(source, /\/proc\/\{pid\}\/cmdline/);
  assert.doesNotMatch(source, /\/proc\/[^\n]*\/environ/);
  assert.doesNotMatch(source, /\bprintenv\b/);
  assert.doesNotMatch(source, /-p ExecStart/);
  assert.doesNotMatch(source, /systemctl\s+(?:restart|start|stop|enable|disable|daemon-reload)/);
  assert.doesNotMatch(source, /\b(?:cp|mv|rm|install|chmod|chown|touch|truncate|tee)\b/);
});

test('probe snapshots site files and redacts common secret-shaped argv/source values', () => {
  assert.match(source, /snapshot_site/);
  assert.match(source, /BEFORE="\$\(snapshot_site\)"/);
  assert.match(source, /AFTER="\$\(snapshot_site\)"/);
  assert.match(source, /site-file snapshot changed/);
  assert.match(source, /token\|secret\|password/);
  assert.match(source, /credential/);
  assert.match(source, /<redacted>/);
  assert.match(source, /RESULT: read-only service routing probe complete; site files unchanged\./);
});

test('probe focuses source inspection on routing and excludes static, backups and virtualenvs', () => {
  for (const marker of ['manual\\.html', 'index\\.html', 'FileResponse', 'StaticFiles', '/api/health']) {
    assert.ok(source.includes(marker), marker);
  }
  assert.match(source, /skip_parts=.*static/);
  assert.match(source, /backups/);
  assert.match(source, /\.venv/);
  assert.match(source, /routing output capped at 250 matches/);
});
