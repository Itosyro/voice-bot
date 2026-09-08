'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=name=>fs.readFileSync(path.join(__dirname,'../../ai-home-v2',name),'utf8');
test('Quiet Signal shell exposes brand, semantic modes and real mic in composer',()=>{
 const html=read('index.html');
 assert.match(html,/<header[\s\S]*ДВИЖ[\s\S]*<\/header>/);
 assert.match(html,/<a[^>]*id="aiManual"[^>]*href="\/manual.html\?v=20260908-quiet-signal-2"/);
 assert.match(html,/aria-current="page">ИИ/);
 assert.match(html,/<form[\s\S]*id="aiOrb"[\s\S]*<\/form>/);
 assert.match(html,/id="aiRibbonMesh"/);
 assert.doesNotMatch(html,/data-state=|демо|имитаци|Макет/);
 for(const asset of ['css','js']) assert.match(html,new RegExp('ai-home-v2\\.'+asset+'\\?v=20260905-3[^" ]*quiet-signal-2'));
});
test('layout retains readable answer space, keyboard offset and 44px controls',()=>{
 const css=read('ai-home-v2.css');
 assert.match(css,/--ai-top/);assert.match(css,/min-height: 44px/);
 assert.match(css,/\.ai-core\s*\{[^}]*overflow-y: auto/);
 assert.match(css,/prefers-reduced-motion/);
 assert.doesNotMatch(css,/ai-breathe/);
});

test('static ribbon is hidden only after successful geometry',()=>{
 const css=read('ai-home-v2.css');
 assert.doesNotMatch(css,/\.ai-ribbon:has\(path:nth-child\(2\)\)/);
 assert.match(css,/#aiRibbonMesh\[data-ready="true"\] > path:first-child\[fill\]/);
 assert.match(css,/#aiRibbonMesh\[data-ready="false"\] > path:not\(:first-child\)/);
});
