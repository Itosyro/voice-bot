'use strict';
// Real Manual + AI HTML/app/boot/sync, native browser storage and actual HTTP/CAS.
// All identities/state belong to a temporary loopback SQLite fixture.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const KEY = '20260913-daily-stability-1';
const dir = process.argv[2];
assert.ok(dir && path.isAbsolute(dir), 'test static directory is required');
const results=[];
const task = (id, title) => ({id, title, micro:'Open one page', area:'Разное', duration:8, energy:1, fear:0, priority:2, done:false, createdAt:'2026-09-13T12:00:00Z'});
(async()=>{
 const server=spawn('python3',[path.join(__dirname,'serve_daily_fixture.py'),dir],{stdio:['pipe','pipe','pipe']});
 let stderr='';server.stderr.on('data',b=>{stderr+=b;});
 const exited=once(server,'exit');
 let browser;
 try {
 const port=await new Promise((resolve,reject)=>{
   let output='';const timer=setTimeout(()=>reject(Error('fixture startup timeout '+stderr)),10000);
   server.once('error',e=>{clearTimeout(timer);reject(e);});
   server.once('exit',c=>{clearTimeout(timer);reject(Error('fixture exit '+c+' '+stderr));});
   server.stdout.on('data',b=>{output+=b;if(output.includes('\n')){clearTimeout(timer);resolve(JSON.parse(output.split('\n')[0]).port);}});
 });
 assert.ok(Number.isInteger(port)&&port>0&&port<65536);
 const origin=`http://127.0.0.1:${port}`;
 browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,headless:true,args:['--no-sandbox']});
 async function api(user, state, revision){
   const r=await fetch(origin+'/api/state',{method:state?'PUT':'GET',headers:{'X-ExeDev-UserID':user,'X-ExeDev-Email':'browser@example.invalid','Content-Type':'application/json'},
     ...(state?{body:JSON.stringify({state,baseRevision:revision})}:{}),signal:AbortSignal.timeout(8000)});
   assert.equal(r.status,200);return r.json();
 }
 async function until(fn){const end=Date.now()+12000;while(!(await fn())){if(Date.now()>end)throw Error('condition timed out');await new Promise(r=>setTimeout(r,50));}}
 async function one(name, fn){
   const number=results.length+1,user=`daily-browser-${number}`;
   const ctx=await browser.newContext({viewport:{width:390,height:844},extraHTTPHeaders:{'X-ExeDev-UserID':user,'X-ExeDev-Email':'browser@example.invalid'},serviceWorkers:'block'});
   const p=await ctx.newPage();p.setDefaultTimeout(6000);p.setDefaultNavigationTimeout(10000);
   await p.clock.setFixedTime(new Date('2026-09-13T12:00:00Z'));
   const errors=[];p.on('pageerror',e=>errors.push(e.message));
   const env={ctx,p,user,get:()=>api(user),put:(s,r)=>api(user,s,r),until,
     async manual(){await p.goto(origin+'/manual.html?v='+KEY);await p.waitForFunction(()=>window.DVIZH_MANUAL_STATE);},
     async ai(){await p.goto(origin+'/');await p.waitForFunction(()=>!document.querySelector('#aiInput').disabled);},
     async tasks(){await p.locator('.health-more summary').click();await p.locator('.health-more [data-nav=tasks]').click();},
     async newTask(title){await env.tasks();await p.locator('#view-tasks [data-action=new-task]').click();await p.locator('#taskTitle').fill(title);await p.locator('#taskMicro').fill('One manageable step');await p.locator('#taskForm [type=submit]').click();},
     async synced(title){await until(async()=> (await api(user)).state.tasks.some(t=>t.title===title));}
   };
   try {await fn(env);assert.deepEqual(errors,[],'no browser runtime errors');results.push({name,ok:true});console.log('PASS '+name);}
   catch(e){results.push({name,ok:false,error:String(e.stack||e)});console.error('FAIL '+name+'\n'+e.stack);await p.screenshot({path:path.join(__dirname,`daily-${number}-failed.png`),fullPage:true}).catch(()=>{});}
   finally {await ctx.close();}
 }
 await one('AI draft: actual reload and AI/Manual round-trip with native sessionStorage',async({p,ai,get})=>{
   const urls=[];p.on('request',r=>urls.push(r.url()));
   await ai();await p.locator('#aiInput').fill('Keep my next small step');await p.reload();
   await p.waitForFunction(()=>document.querySelector('#aiInput').value==='Keep my next small step');
   await p.locator('#aiManual').click();await p.waitForFunction(()=>window.DVIZH_MANUAL_STATE);
   await p.locator('.qs-modes a[href="/"]').click();
   await p.waitForFunction(()=>document.querySelector('#aiInput').value==='Keep my next small step');
   assert.equal(((await get()).state.aiHomeRequests||[]).length,0);
   assert.ok(urls.some(u=>u.includes('/ai-home-v2.js?v='+KEY)));
   assert.ok(urls.some(u=>u.includes('/sync.js?v='+KEY)));
 });
 await one('Manual: create, reload, complete, verify in a second native browser tab',async({ctx,p,manual,newTask,synced,get,until})=>{
   await manual();await newTask('My real-form fixture task');await synced('My real-form fixture task');
   let row=(await get()).state.tasks.find(t=>t.title==='My real-form fixture task');
   await p.reload();await p.waitForFunction(()=>window.DVIZH_MANUAL_STATE);
   assert.equal(await p.evaluate(id=>DVIZH_MANUAL_STATE.snapshot().tasks.find(t=>t.id===id).title,row.id),row.title);
   await p.locator('.health-more summary').click();await p.locator('.health-more [data-nav=tasks]').click();
   await p.locator(`#taskList [data-action=toggle-task][data-task-id="${row.id}"]`).click();
   await until(async()=> (await get()).state.tasks.find(t=>t.id===row.id).done===true);
   const second=await ctx.newPage();await second.goto(p.url());await second.waitForFunction(()=>window.DVIZH_MANUAL_STATE);
   assert.equal(await second.evaluate(id=>DVIZH_MANUAL_STATE.snapshot().tasks.find(t=>t.id===id).done,row.id),true);
   assert.deepEqual((await get()).state.future,{keep:true});await second.close();
 });
 await one('Manual: offline task creation on open page persists through reconnect once',async({ctx,p,manual,get,until})=>{
   await manual();await ctx.setOffline(true);await p.locator('#quickAddInput').fill('Offline next step');await p.locator('#quickAddForm [type=submit]').click();
   assert.equal(await p.evaluate(()=>DVIZH_MANUAL_STATE.snapshot().tasks.filter(t=>t.title==='Offline next step').length),1);
   assert.equal((await get()).state.tasks.filter(t=>t.title==='Offline next step').length,0);
   await ctx.setOffline(false);await p.evaluate(()=>DVIZH_SYNC.push());
   await until(async()=> (await get()).state.tasks.some(t=>t.title==='Offline next step'));
   await p.reload();await p.waitForFunction(()=>window.DVIZH_MANUAL_STATE);
   assert.equal(await p.evaluate(()=>DVIZH_MANUAL_STATE.snapshot().tasks.filter(t=>t.title==='Offline next step').length),1);
 });
 await one('Manual: false HTTP 200 keeps local task until an actual save receipt',async({p,manual,get,until})=>{
   await manual();let faulty=true;
   await p.route('**/api/state',route=>route.request().method()==='PUT'&&faulty?route.fulfill({status:200,contentType:'application/json',body:'{"ok":true}'}):route.continue());
   await p.locator('#quickAddInput').fill('Unconfirmed task');await p.locator('#quickAddForm [type=submit]').click();
   await p.evaluate(()=>DVIZH_SYNC.push());await p.evaluate(()=>DVIZH_SYNC.pull());
   assert.equal(await p.evaluate(()=>JSON.parse(localStorage.getItem('dvizh-state-v1')).tasks.filter(t=>t.title==='Unconfirmed task').length),1);
   assert.notEqual(await p.locator('#syncStatusDot').getAttribute('data-sync'),'ok');
   assert.equal((await get()).state.tasks.filter(t=>t.title==='Unconfirmed task').length,0);
   faulty=false;await p.evaluate(()=>DVIZH_SYNC.push());
   await until(async()=> (await get()).state.tasks.filter(t=>t.title==='Unconfirmed task').length===1);
 });
 await one('Manual: focused edit survives remote sync and preserves concurrently changed field',async({p,manual,tasks,get,put,until})=>{
   let snap=await get();snap.state.tasks=[task('edit-task','Original title')];await put(snap.state,snap.revision);
   await manual();await tasks();await p.locator('#taskList [data-action=edit-task][data-task-id="edit-task"]').click();
   await p.locator('#taskTitle').fill('My changed title');
   snap=await get();snap.state.tasks[0].micro='Remote micro step';snap.state.future.concurrent=true;await put(snap.state,snap.revision);
   await p.evaluate(()=>DVIZH_SYNC.pull());assert.equal(await p.locator('#taskTitle').inputValue(),'My changed title');
   assert.equal(await p.locator('#taskModal').getAttribute('hidden'),null);
   await p.locator('#taskForm [type=submit]').click();await p.evaluate(()=>DVIZH_SYNC.push());
   await until(async()=> (await get()).state.tasks[0].title==='My changed title');
   assert.equal((await get()).state.tasks[0].micro,'Remote micro step');assert.equal((await get()).state.future.concurrent,true);
 });
 await one('AI: false HTTP success does not clear input or fabricate a queued request',async({p,ai,get})=>{
   await ai();await p.route('**/api/state',r=>r.request().method()==='PUT'?r.fulfill({status:200,contentType:'application/json',body:'{"ok":true}'}):r.continue());
   await p.locator('#aiInput').fill('This must not disappear');await p.locator('#aiSend').click();
   await p.waitForFunction(()=>!document.querySelector('#aiInput').disabled);
   assert.equal(await p.locator('#aiInput').inputValue(),'This must not disappear');
   assert.equal(((await get()).state.aiHomeRequests||[]).length,0);
 });
 await one('AI: failed preflight read preserves draft across actual reload without sending',async({p,ai,get})=>{
   await ai();let fails=true;await p.route('**/api/state',r=>fails?r.abort('failed'):r.continue());
   await p.locator('#aiInput').fill('Safe unsent thought');await p.locator('#aiSend').click();
   await p.waitForFunction(()=>!document.querySelector('#aiInput').disabled);fails=false;await p.reload();
   await p.waitForFunction(()=>document.querySelector('#aiInput').value==='Safe unsent thought');
   assert.equal(((await get()).state.aiHomeRequests||[]).length,0);
 });
 await one('Manual: native metadata quota failure does not delete later remote tasks',async({p,manual,get,put})=>{
   await p.addInitScript(()=>{const set=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(window.failDailyMeta&&k==='dvizh-sync-meta-v1'){window.failDailyMeta=false;throw new DOMException('Fixture quota','QuotaExceededError');}return set.call(this,k,v);};});
   await manual();let snap=await get();snap.state.tasks.push(task('remote-b','Remote B'));await put(snap.state,snap.revision);
   await p.evaluate(()=>{window.failDailyMeta=true;});await p.evaluate(()=>DVIZH_SYNC.pull());
   snap=await get();snap.state.tasks.push(task('remote-c','Remote C'));await put(snap.state,snap.revision);
   await p.evaluate(()=>DVIZH_SYNC.pull());await p.evaluate(()=>DVIZH_SYNC.push());
   assert.deepEqual((await get()).state.tasks.map(t=>t.id).sort(),['remote-b','remote-c']);
   await p.reload();await p.waitForFunction(()=>window.DVIZH_MANUAL_STATE);
   assert.deepEqual(await p.evaluate(()=>DVIZH_MANUAL_STATE.snapshot().tasks.map(t=>t.id).sort()),['remote-b','remote-c']);
 });
 console.log(JSON.stringify({suite:'daily-native-browser-http',passed:results.filter(r=>r.ok).length,total:results.length,results},null,2));
 if(results.some(r=>!r.ok))process.exitCode=1;
 } finally {
   if(browser)await browser.close();
   if(server.exitCode===null){server.stdin.end('stop\n');const t=setTimeout(()=>server.kill('SIGKILL'),5000);await exited;clearTimeout(t);}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
