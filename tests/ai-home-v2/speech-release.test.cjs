const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
test('speech release invalidates immutable JS cache without changing design', () => {
  const html = fs.readFileSync(path.resolve(__dirname, '../../ai-home-v2/index.html'), 'utf8');
  const source = /src="(\/ai-home-v2\.js\?v=[^"]+)"/;
  assert.notEqual(html.match(source)[1], '/ai-home-v2.js?v=20260905-3.1-voice-20260908');
  const design = html.replace(source, 'src="SCRIPT"');
  assert.equal(createHash('sha256').update(design).digest('hex'), '9a1398c5dae03abe523f40750e8cc64d0808e1a04f9cd75a4e482b4242dc7cdd');
});
