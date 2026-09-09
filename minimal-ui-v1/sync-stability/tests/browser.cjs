'use strict';
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_PATH || 'playwright');
const {fixture}=require('./harness.cjs');
const root=path.join(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});
 try {
  const context=await browser.newContext({serviceWorkers:'block'});
  const page=await context.newPage(); const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  let remote=fixture(), revision=10; const requests=[];
  Object.assign(remote,{tone:'direct',focusDuration:8,selectedFocusTaskId:'synthetic-task'});
  Object.assign(remote.tasks[0],{micro:'Base micro',area:'Разное',duration:8,energy:1,fear:0,priority:2,done:false});
  await page.clock.install({time:new Date('2026-01-01T12:00:00Z')});
  await context.route('**/*',async route=>{
   const url=new URL(route.request().url());
   if(url.origin!=='http://dvizh.test') return route.abort();
   if(url.pathname==='/api/state') {
    requests.push(route.request().method());
    if(route.request().method()==='PUT') { remote=route.request().postDataJSON().state; revision++; }
    return route.fulfill({json:{state:remote,revision}});
   }
   const name=path.basename(url.pathname);
   if(!['manual.html','app.js','sync.js','boot.js'].includes(name)) return route.fulfill({status:200,body:'',contentType:'text/css'});
   return route.fulfill({body:fs.readFileSync(path.join(root,['app.js','sync.js','manual.html'].includes(name)?'release':'baseline',name)),contentType:name.endsWith('.html')?'text/html':'application/javascript'});
  });
  await page.goto('http://dvizh.test/manual.html?v=20260909-sync-stability-2');
  await page.waitForFunction(()=>window.DVIZH_MANUAL_STATE && document.querySelector('#todayLabel')?.textContent);
  await page.evaluate(()=>document.querySelector('[data-nav="training"]').click());
  await page.evaluate(()=>document.querySelector('[data-action="edit-task"]')?.click());
  // Use the real delegated task editor action, independent of CSS visibility.
  await page.evaluate(()=>{
   const button=document.createElement('button');button.dataset.action='edit-task';button.dataset.taskId='synthetic-task';document.body.append(button);button.click();button.remove();
  });
  await page.clock.runFor(60);
  await page.locator('#taskTitle').fill('Local draft');
  await page.evaluate(()=>{document.querySelector('#taskTitle').blur();document.querySelector('#view-training').dataset.minimalDetails='open';});
  remote=JSON.parse(JSON.stringify(remote));remote.tasks[0].micro='Remote micro';remote.tasks[0].title='Remote title';revision++;
  await page.evaluate(()=>DVIZH_SYNC.pull());
  assert.equal(await page.locator('#taskTitle').inputValue(),'Local draft');
  assert.equal(await page.locator('#taskMicro').inputValue(),'Base micro');
  assert.equal(await page.locator('#view-training').getAttribute('class').then(x=>x.includes('is-active')),true);
  assert.equal(await page.locator('#taskModal').getAttribute('hidden'),null);
  assert.equal(await page.evaluate(()=>DVIZH_MANUAL_STATE.snapshot().tasks[0].micro),'Remote micro');
  await page.evaluate(()=>document.querySelector('#taskForm').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('dvizh-state-v1')));
  assert.equal(saved.tasks[0].title,'Local draft');assert.equal(saved.tasks[0].micro,'Remote micro');
  assert.deepEqual(errors,[]);
  console.log('PASS actual Chromium Manual/app/boot: Training route, blurred modal draft, three-way submission and live in-memory remote state');
  await context.close();
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
