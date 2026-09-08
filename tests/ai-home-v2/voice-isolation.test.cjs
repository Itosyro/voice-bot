'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const base = 'ba8214911f5942fdbf36269e1e992eb7607b40f8';
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const original = name => execFileSync('git', ['show', `${base}:${name}`], { cwd: root, encoding: 'utf8' });
test('Quiet Signal intentionally updates isolated AI markup and CSS, retaining version lineage', () => {
  const html = read('ai-home-v2/index.html');
  assert.match(html, /ai-home-v2\.js\?v=20260905-3.1-voice-20260908-speech-1-quiet-signal-2/);
  assert.match(html, /ai-home-v2\.css\?v=20260905-3.1-quiet-signal-2/);
  for (const hook of ['aiApp','aiOrb','aiInput','aiComposer','aiSend','aiAnswer','aiStatus','aiAuth','aiAuthLink']) assert.ok(html.includes(`id="${hook}"`));
});
test('voice promotion leaves all non-AI production sources and Manual/SW assets byte-identical', () => {
  const names = execFileSync('git', ['ls-tree', '-r', '--name-only', base], { cwd: root, encoding: 'utf8' }).trim().split('\n');
  const protectedNames = names.filter(name => !name.startsWith('tests/') && !name.startsWith('docs/') && !name.startsWith('.github/') &&
    !['ai-home-v2/ai-home-v2.css', 'ai-home-v2/ai-home-v2.js', 'ai-home-v2/index.html', 'ai-home-v2/README.md'].includes(name));
  for (const name of protectedNames) {
    const expected = execFileSync('git', ['rev-parse', `${base}:${name}`], { cwd: root, encoding: 'utf8' }).trim();
    const actual = execFileSync('git', ['hash-object', '--', name], { cwd: root, encoding: 'utf8' }).trim();
    assert.equal(actual, expected, name);
  }
});
