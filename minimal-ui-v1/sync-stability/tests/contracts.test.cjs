const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const crypto=require('node:crypto');
const root=path.join(__dirname,'..');const read=p=>fs.readFileSync(path.join(root,p),'utf8');const hash=s=>crypto.createHash('sha256').update(s).digest('hex');
test('release manifest pins exact baseline and only authorized app/sync/manual artifacts',()=>{
 const manifest=JSON.parse(read('release-manifest.json'));assert.equal(manifest.status,'candidate-for-independent-review');
 assert.deepEqual(Object.keys(manifest.artifacts).sort(),['app.js','manual.html','sync.js']);
 for(const [name,sha]of Object.entries(manifest.baseline))assert.equal(hash(fs.readFileSync(path.join(root,'baseline',name))),sha);
 for(const [name,sha]of Object.entries(manifest.artifacts))assert.equal(hash(read('release/'+name)),sha);
 assert.equal(manifest.contracts.bootTarget,'denied');assert.equal(fs.existsSync(path.join(root,'release/boot.js')),false);
 assert.equal(read('release/manual.html'),read('baseline/manual.html').replace('<script src="sync.js"></script>','<script src="sync.js?v=20260909-sync-stability-2"></script>'));
 const sync=read('release/sync.js');assert.doesNotMatch(sync,/location\s*\.\s*reload\s*\(/);
 assert.match(sync,/const POLL_MS = 8000;/);assert.match(sync,/const PUSH_DELAY_MS = 450;/);
 assert.equal((sync.match(/setInterval\(/g)||[]).length,(read('baseline/sync.js').match(/setInterval\(/g)||[]).length);
 const app=read('release/app.js');assert.match(app,/const DVIZH_MINIMAL_UI_V1 = true/);
 assert.equal(app.slice(app.indexOf('const DVIZH_MINIMAL_UI_V1')),read('baseline/app.js').slice(read('baseline/app.js').indexOf('const DVIZH_MINIMAL_UI_V1')));
});

test('release operations use generated files, exact static routes, and no restart',()=>{
 const proposal=JSON.parse(fs.readFileSync(path.join(root,'../../.autopilot/release.json'),'utf8'));
 assert.deepEqual(proposal,{schema:1,operations:['app.js','sync.js','manual.html'].map(name=>({source:'minimal-ui-v1/sync-stability/release/'+name,target:'/opt/dvizh/static/'+name,http_path:'/'+name})),restarts:[]});
});
test('versioned entry resolves a distinct immutable sync cache key and retains no-cache app route',()=>{
 const manifest=JSON.parse(read('release-manifest.json'));
 const entry=new URL(manifest.contracts.manualEntry,'https://dvizh.test');
 assert.equal(entry.pathname,'/manual.html');assert.equal(entry.search,'?v=20260909-sync-stability-2');
 const scripts=[...read('release/manual.html').matchAll(/<script src="([^"]+)"/g)].map(m=>new URL(m[1],entry));
 assert.deepEqual(scripts.map(u=>u.pathname+u.search),['/sync.js?v=20260909-sync-stability-2','/boot.js']);
 assert.notEqual(scripts[0].href,new URL('sync.js',entry).href);
 assert.match(read('baseline/boot.js'),/script.src = '\.\/app.js'/);
 assert.equal(new URL('./app.js',entry).pathname+new URL('./app.js',entry).search,'/app.js');
 assert.deepEqual(manifest.contracts.cacheAssumptions,{manualHtml:'public, max-age=604800, immutable',syncJs:'public, max-age=604800, immutable',appJs:'no-cache',queryKeysDistinct:true});
});
