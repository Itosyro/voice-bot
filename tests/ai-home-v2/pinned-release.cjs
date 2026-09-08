'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

// Historical immutable bootstraps must test their actual pinned payload,
// not the changing working tree. Keep their production pins untouched.
module.exports = function pinnedRelease(temp) {
  const root = path.join(temp, 'pinned-release');
  const project = path.resolve(__dirname, '../..');
  const commit = 'd6418224eae292417a645b2a73da157d939526b9';
  for (const name of ['install-dvizh-ai-home-v2.sh', 'ai-home-v2/index.html', 'ai-home-v2/ai-home-v2.js', 'ai-home-v2/ai-home-v2.css']) {
    const target = path.join(root, name);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, execFileSync('git', ['show', `${commit}:${name}`], { cwd: project }));
  }
  return root;
};
