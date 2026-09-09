'use strict';
// Real HTTP cache test: Playwright routing is deliberately unused because it disables cache.
const http=require('node:http');const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_PATH || 'playwright');const {fixture}=require('./harness.cjs');
const {stateServer}=require('./state-server.cjs');
const root=path.join(__dirname,'..'),version='20260909-sync-stability-2';
(async()=>{
 let released=false,oldApp=false;const requests=[];let remote=fixture();
 // A complete Manual fixture is required: the sync-only fixture has no tone.
 Object.assign(remote,{tone:'direct',focusDuration:8,selectedFocusTaskId:'synthetic-task'});
 Object.assign(remote.tasks[0],{micro:'Base micro',area:'Разное',duration:8,energy:1,fear:0,priority:2,done:false});
 remote.jumpLab.profile={age:19,heightCm:156};
 const service=stateServer(remote);remote=service.state;
 const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost');const recorded={url:req.url,released,method:req.method};requests.push(recorded);
  if(url.pathname==='/primer'){res.end('<!doctype html><title>cache primer</title>');return;}
  if(url.pathname==='/api/state'){
   let body='';req.on('data',chunk=>body+=chunk);req.on('end',()=>{
    const result=service.request(req.method,body&&JSON.parse(body));remote=service.state;
    recorded.status=result.status;
    res.statusCode=result.status;res.setHeader('Content-Type','application/json');res.end(JSON.stringify(result.body));
   });return;
  }
  const name=url.pathname.slice(1);
  if(!['manual.html','sync.js','app.js','boot.js'].includes(name)){res.end('');return;}
  res.setHeader('Cache-Control',name==='app.js'?'no-cache':'public, max-age=604800, immutable');
  res.setHeader('Content-Type',name.endsWith('.html')?'text/html':'application/javascript');
  res.end(fs.readFileSync(path.join(root,released && name!=='boot.js' && !(oldApp && name==='app.js')?'release':'baseline',name)));
 });
 let browser;
 try{
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const context=await browser.newContext({serviceWorkers:'block'});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const base=`http://127.0.0.1:${server.address().port}`;await page.goto(base+'/primer');
  await page.evaluate(async()=>{for(const file of ['manual.html','sync.js','app.js'])await (await fetch('/'+file)).text();});
  released=true;
  await page.goto(base+'/manual.html');
  await page.waitForFunction(()=>window.DVIZH_MANUAL_STATE && document.querySelector('#todayLabel')?.textContent);
  assert.equal(await page.evaluate(()=>typeof window.DVIZH_SYNC.reconcile),'undefined');
  await page.evaluate(()=>{
   document.querySelector('[data-nav="training"]').click();
   if(document.querySelector('#jumpAge').value!=='19')throw Error('Expected original age 19');
   document.querySelector('#jumpAge').value='20';
   document.querySelector('#jumpProfileForm').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
  });
  await page.waitForFunction(()=>JSON.parse(localStorage.getItem('dvizh-state-v1')).jumpLab.webCommands.at(-1)?.profile.age===20);
  await page.waitForFunction(async()=> (await(await fetch('/api/state')).json()).state.jumpLab.profile.age===20);
  assert.deepEqual(errors,[]);
  console.log('PASS Chromium mixed cache: cached OLD Manual/sync + pinned boot + revalidated NEW app saves Jump age 19 -> 20 and uploads command without crashes');
  await page.goto(base+'/manual.html?v='+version);
  await page.waitForFunction(()=>window.DVIZH_MANUAL_STATE && document.querySelector('#todayLabel')?.textContent);
  assert.ok(requests.some(r=>r.released && r.url==='/manual.html?v='+version));
  assert.ok(requests.some(r=>r.released && r.url==='/sync.js?v='+version));
  assert.ok(requests.some(r=>r.released && r.url==='/app.js'),'no-cache app must reach server again');
  const stale=await page.evaluate(async()=>({html:await(await fetch('/manual.html')).text(),sync:await(await fetch('/sync.js')).text()}));
  assert.equal(stale.html,fs.readFileSync(path.join(root,'baseline/manual.html'),'utf8'));
  assert.equal(stale.sync,fs.readFileSync(path.join(root,'baseline/sync.js'),'utf8'));
  assert.equal(requests.filter(r=>r.url==='/manual.html').length,1);
  assert.equal(requests.filter(r=>r.url==='/sync.js').length,1);
  assert.deepEqual(errors,[]);
  console.log('PASS Chromium HTTP cache: warm immutable Manual/sync remain stale; versioned Manual fetches versioned release sync; no-cache app refetches; actual generated app boots');
  await context.close(); // End all polling/debounce writers before resetting the shared scenario.
  oldApp=true;
  const reverseContext=await browser.newContext({serviceWorkers:'block'}),reverse=await reverseContext.newPage();
  reverse.on('pageerror',e=>errors.push(e.message));
  remote.jumpLab.profile={age:19,heightCm:156};service.revision++;
  const beforeReverse=requests.length;
  await reverse.goto(base+'/manual.html?v='+version);
  await reverse.waitForFunction(()=>window.DVIZH_SYNC?.protective);
  await reverse.evaluate(()=>document.querySelector('[data-nav="training"]').click());
  remote.jumpLab.profile.heightCm=160;service.revision++;
  await reverse.evaluate(()=>window.DVIZH_SYNC.pull());
  await reverse.evaluate(()=>{
   document.querySelector('#jumpAge').value='20';
   document.querySelector('#jumpProfileForm').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
   document.querySelector('#jumpAge').value='21';
  });
  await reverse.evaluate(()=>window.DVIZH_SYNC.push());
  assert.equal(remote.jumpLab.profile.heightCm,160);
  assert.equal(await reverse.evaluate(()=>window.DVIZH_SYNC.pendingLocal.jumpLab.profile.age),20);
  assert.equal(await reverse.locator('#jumpAge').inputValue(),'21');
  assert.equal(requests.slice(beforeReverse).filter(r=>r.method==='PUT').length,0);
  oldApp=false;
  reverse.once('dialog',dialog=>dialog.accept());
  await Promise.all([reverse.waitForNavigation(),reverse.locator('[data-manual-update]').click()]);
  await reverse.waitForFunction(()=>window.DVIZH_MANUAL_STATE && document.querySelector('#syncDraftRecovery'));
  await reverse.locator('#syncDraftRecovery button').click();
  const recovered=JSON.parse(await reverse.locator('#syncDraftRecovery textarea').inputValue());
  assert.equal(recovered.forms.forms.find(f=>f.id==='jumpProfileForm').fields.find(f=>f.id==='jumpAge').value,'21');
  assert.equal(recovered.quarantined.state.jumpLab.profile.age,20);
  assert.equal(remote.jumpLab.profile.heightCm,160);
  assert.deepEqual(errors,[]);
  console.log('PASS Chromium reverse cache: no stale PUT, server height160, quarantine age20, explicit versioned update and retained unsaved age21 archive');
  console.log('LIMIT: synthetic local headers and state; service workers blocked; no production/proxy verification or deployment');
 }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
