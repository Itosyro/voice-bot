'use strict';
// Real Chromium, shipped HTML/boot/app/sync, actual temporary HTTP/SQLite backend.
// No real model, microphone, user identity, external API, or production writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const ROOT = path.resolve(__dirname, '..');
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const seed = () => ({version:1,tasks:[],hasSeenIntro:true,createdAt:'2026-09-13T10:00:00.000Z',future:{keep:true},
  healthRecovery:{version:1,timezone:'Europe/Moscow',sleep:{'2026-09-13':{durationKind:'reported',durationMinutes:420,source:'manual',timezone:'Europe/Moscow'}}}});
const headers = user => ({'X-ExeDev-UserID':user,'X-ExeDev-Email':`${user}@example.invalid`});
let server, browser, origin;
const results = [];
// Retain partial results on failure, rather than silently discarding passing flows.
function recordResults() {fs.writeFileSync(path.join(__dirname,'browser-results.json'),JSON.stringify({environment:'isolated Chromium + temporary SQLite; no live AI/microphone',results},null,2)+'\n');}
async function until(fn, description, timeout=10000) {
  const end = Date.now()+timeout;
  while(Date.now()<end) { if(await fn()) return; await wait(40); }
  throw Error(`Timeout: ${description}`);
}
async function api(user, method='GET', payload) {
  const response=await fetch(origin+'/api/state',{method,headers:{...headers(user),'Content-Type':'application/json'},
    ...(payload?{body:JSON.stringify(payload)}:{}),signal:AbortSignal.timeout(5000)});
  assert.equal(response.status,200,`fixture API ${method}`);return response.json();
}
async function fresh(user) {
  await api(user,'PUT',{baseRevision:0,state:seed()});
  const ctx=await browser.newContext({viewport:{width:390,height:844},extraHTTPHeaders:headers(user),serviceWorkers:'block',reducedMotion:'reduce'});
  const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  page.setDefaultTimeout(6000);
  return {ctx,page,errors,user};
}
async function manual(f) {
  await f.page.goto(origin+'/manual.html');
  await until(()=>f.page.evaluate(()=>Boolean(window.DVIZH_MANUAL_STATE)), 'Manual app boot');
}
async function nav(page,name) {
  if(!await page.locator('.health-more').evaluate(e=>e.open))await page.locator('.health-more summary').click();
  await page.locator(`.health-more [data-nav="${name}"]`).click();
  assert.ok(await page.locator(`#view-${name}`).evaluate(e=>e.classList.contains('is-active')));
}
async function create(page,title) {
  await page.locator('[data-action="new-task"]:visible').first().click();
  await page.locator('#taskTitle').fill(title);
  await page.locator('#taskMicro').fill('Открыть нужную страницу и начать с двух минут');
  await page.locator('#taskForm button[type=submit]').click();
}
async function saved(f,count) {
  await f.page.evaluate(()=>window.DVIZH_SYNC.push());
  await until(async()=>((await api(f.user)).state.tasks.length===count),'saved task count');
  await until(()=>f.page.evaluate(()=>document.getElementById('syncStatusDot')?.dataset.sync==='ok'),'confirmed sync');
}
async function run(name,fn) {
  try {await fn();results.push({name,status:'PASS'});console.log('PASS browser:',name);}
  catch(error){results.push({name,status:'FAIL',error:String(error)});throw error;}
  finally {recordResults();}
}
(async()=>{
  server=spawn(process.env.PYTHON || 'python3',[path.join(__dirname,'browser_server.py')],{stdio:['pipe','pipe','pipe']});
  let stderr='';server.stderr.on('data',b=>stderr+=b.toString());
  const port=await new Promise((resolve,reject)=>{
    let text='';const timer=setTimeout(()=>reject(Error('fixture startup '+stderr)),5000);
    server.on('error',reject);server.once('exit',code=>{clearTimeout(timer);reject(Error('fixture exit '+code+' '+stderr));});
    server.stdout.on('data',b=>{text+=b;if(text.includes('\n')){clearTimeout(timer);resolve(JSON.parse(text.split('\n')[0]).port);}});
  });
  origin=`http://127.0.0.1:${port}`;
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,headless:true,args:['--no-sandbox']});
  await run('create -> reload -> complete -> fresh browser context',async()=>{
    const f=await fresh('daily-lifecycle');
    try {
      await manual(f);await nav(f.page,'tasks');await create(f.page,'Прогулка после учёбы');await saved(f,1);
      await f.page.reload();await until(()=>f.page.evaluate(()=>Boolean(window.DVIZH_MANUAL_STATE)),'reload');await nav(f.page,'tasks');
      await f.page.locator('[data-action="toggle-task"]').first().click();
      await f.page.evaluate(()=>window.DVIZH_SYNC.push());
      await until(async()=>(await api(f.user)).state.tasks[0].done===true,'completion persisted');
      const other=await browser.newContext({viewport:{width:390,height:844},extraHTTPHeaders:headers(f.user),serviceWorkers:'block',reducedMotion:'reduce'});
      try {const p=await other.newPage();await p.goto(origin+'/manual.html');await until(()=>p.evaluate(()=>Boolean(window.DVIZH_MANUAL_STATE)),'other client');
        assert.equal(await p.evaluate(()=>window.DVIZH_MANUAL_STATE.snapshot().tasks[0].done),true);
        assert.equal(await p.evaluate(()=>window.DVIZH_MANUAL_STATE.snapshot().future.keep),true);
      } finally {await other.close();}
      assert.deepEqual(f.errors,[]);await f.page.screenshot({path:path.join(__dirname,'daily-tasks.png')});
    } finally {await f.ctx.close();}
  });
  await run('API offline -> task -> reload -> reconnect; local outbox survives',async()=>{
    const f=await fresh('daily-offline');
    try {
      await manual(f);await nav(f.page,'tasks');
      await f.ctx.route('**/api/state',r=>r.abort('internetdisconnected'));
      await create(f.page,'Сохранить мысль при пропавшей связи');await f.page.evaluate(()=>window.DVIZH_SYNC.push());
      assert.equal((await api(f.user)).state.tasks.length,0);
      // Only the API is unavailable; this is NOT a claim of a cold offline PWA boot.
      await f.page.reload();await until(()=>f.page.evaluate(()=>Boolean(window.DVIZH_MANUAL_STATE)),'offline API reload');
      assert.equal(await f.page.evaluate(()=>window.DVIZH_MANUAL_STATE.snapshot().tasks.length),1);
      await f.ctx.unroute('**/api/state');await saved(f,1);assert.deepEqual(f.errors,[]);
    } finally {await f.ctx.close();}
  });
  await run('focused task form survives a remote update and retains unrelated health data',async()=>{
    const f=await fresh('daily-form');
    try {
      await manual(f);await nav(f.page,'tasks');await f.page.locator('[data-action="new-task"]:visible').first().click();
      await f.page.locator('#taskTitle').fill('Не потерять открытый черновик');await f.page.locator('#taskMicro').fill('Первый маленький шаг');
      await f.page.locator('#taskTitle').focus();await f.page.evaluate(()=>{window.__formNode=document.getElementById('taskTitle');});
      const snapshot=await api(f.user);snapshot.state.future.extra='arrived remotely';
      await api(f.user,'PUT',{baseRevision:snapshot.revision,state:snapshot.state});await f.page.evaluate(()=>window.DVIZH_SYNC.pull());
      assert.equal(await f.page.locator('#taskTitle').inputValue(),'Не потерять открытый черновик');
      assert.ok(await f.page.evaluate(()=>document.activeElement===window.__formNode && window.__formNode===document.getElementById('taskTitle')));
      await f.page.locator('#taskForm button[type=submit]').click();await saved(f,1);
      const stored=(await api(f.user)).state;assert.equal(stored.future.extra,'arrived remotely');assert.equal(stored.healthRecovery.sleep['2026-09-13'].durationMinutes,420);
      assert.deepEqual(f.errors,[]);
    } finally {await f.ctx.close();}
  });
  await run('two real browser contexts: edit title + completion survive one CAS conflict',async()=>{
    const f=await fresh('daily-conflict');let other;
    try {
      await manual(f);await nav(f.page,'tasks');await create(f.page,'Исходное название');await saved(f,1);
      other=await browser.newContext({viewport:{width:390,height:844},extraHTTPHeaders:headers(f.user),serviceWorkers:'block',reducedMotion:'reduce'});
      const p=await other.newPage();p.on('pageerror',e=>f.errors.push(e.message));
      await p.goto(origin+'/manual.html');await until(()=>p.evaluate(()=>Boolean(window.DVIZH_MANUAL_STATE)),'second client');await nav(p,'tasks');
      await f.page.locator('#view-tasks [data-action="edit-task"]:visible').first().click();await f.page.locator('#taskTitle').fill('Уточнённое название');
      await until(()=>p.evaluate(()=>document.getElementById('syncStatusDot')?.dataset.sync==='ok'),'second client settled');
      let count=0,conflicts=0,release;const revisions=[];
      const gate=new Promise(resolve=>release=resolve);
      const timer=setTimeout(release,5000);
      for(const page of [f.page,p]) {
        page.on('response',r=>{if(r.url().endsWith('/api/state')&&r.status()===409)conflicts++;});
        await page.route('**/api/state',async route=>{
          if(route.request().method()==='PUT'&&count<2){revisions.push(route.request().postDataJSON().baseRevision);if(++count===2)release();await gate;}
          await route.continue();
        });
      }
      try {
        await Promise.all([
          (async()=>{await f.page.locator('#taskForm button[type=submit]').click();await f.page.evaluate(()=>window.DVIZH_SYNC.push());})(),
          (async()=>{await p.locator('[data-action="toggle-task"]').first().click();await p.evaluate(()=>window.DVIZH_SYNC.push());})()
        ]);
      } finally {clearTimeout(timer);release();}
      assert.equal(count,2);assert.equal(revisions[0],revisions[1]);assert.equal(conflicts,1);
      const row=(await api(f.user)).state.tasks[0];assert.equal(row.title,'Уточнённое название');assert.equal(row.done,true);
      await Promise.all([f.page,p].map(page=>page.evaluate(()=>window.DVIZH_SYNC.pull())));
      for(const page of [f.page,p]) {
        const task=await page.evaluate(()=>window.DVIZH_MANUAL_STATE.snapshot().tasks[0]);assert.equal(task.title,row.title);assert.equal(task.done,true);
      }
      assert.deepEqual(f.errors,[]);
    } finally {if(other)await other.close();await f.ctx.close();}
  });
  await run('HTML instead of save receipt cannot erase a task on the next pull',async()=>{
    const f=await fresh('daily-bad-receipt');
    try {
      await manual(f);await nav(f.page,'tasks');
      await f.ctx.route('**/api/state',r=>r.request().method()==='PUT'?r.fulfill({status:200,contentType:'text/html',body:'<html>Login instead of a receipt</html>'}):r.continue());
      await create(f.page,'Не терять задачу при ошибке сервера');await f.page.evaluate(()=>window.DVIZH_SYNC.push());
      assert.equal((await api(f.user)).state.tasks.length,0);
      assert.notEqual(await f.page.locator('#syncStatusDot').getAttribute('data-sync'),'ok');
      const remote=await api(f.user);remote.state.future.remote='kept';await api(f.user,'PUT',{baseRevision:remote.revision,state:remote.state});
      await f.page.evaluate(()=>window.DVIZH_SYNC.pull());assert.equal(await f.page.evaluate(()=>window.DVIZH_MANUAL_STATE.snapshot().tasks.length),1);
      await f.ctx.unroute('**/api/state');await saved(f,1);assert.deepEqual(f.errors,[]);
    } finally {await f.ctx.close();}
  });
  await run('AI draft -> Manual -> AI -> reload; never auto-submitted',async()=>{
    const f=await fresh('daily-ai-draft');
    try {
      await f.page.goto(origin+'/');await until(()=>f.page.locator('#aiInput').isEnabled(),'AI ready');
      await f.page.locator('#aiInput').fill('После занятий один небольшой шаг');await f.page.locator('#aiManual').click();
      await until(()=>f.page.evaluate(()=>Boolean(window.DVIZH_MANUAL_STATE)),'Manual navigation');
      await f.page.goto(origin+'/');await until(()=>f.page.locator('#aiInput').isEnabled(),'return AI');
      assert.equal(await f.page.locator('#aiInput').inputValue(),'После занятий один небольшой шаг');
      await f.page.reload();await until(()=>f.page.locator('#aiInput').isEnabled(),'reload AI');
      assert.equal(await f.page.locator('#aiInput').inputValue(),'После занятий один небольшой шаг');
      assert.equal(((await api(f.user)).state.aiHomeRequests || []).length,0);assert.deepEqual(f.errors,[]);
      await f.page.screenshot({path:path.join(__dirname,'daily-ai-draft.png')});
    } finally {await f.ctx.close();}
  });
  await run('AI text request + synthetic worker reply, preserving tasks and health',async()=>{
    const f=await fresh('daily-ai-text');
    try {
      await f.page.goto(origin+'/');await until(()=>f.page.locator('#aiInput').isEnabled(),'AI ready');
      await f.page.locator('#aiInput').fill('Что у меня запланировано?');await f.page.locator('#aiComposer').evaluate(e=>e.requestSubmit());
      await until(async()=>((await api(f.user)).state.aiHomeRequests || []).length===1,'one AI request');
      const row=await api(f.user),request=row.state.aiHomeRequests[0];request.status='done';
      row.state.aiHomeMessages.push({role:'assistant',content:'Тестовый ответ транспортного сценария, не ответ настоящей модели.'});
      row.state.aiHomeStatus={state:'ready',requestId:request.id};await api(f.user,'PUT',{baseRevision:row.revision,state:row.state});
      await until(()=>f.page.locator('#aiAnswer').isVisible(),'visible reply');
      assert.match(await f.page.locator('#aiAnswer').innerText(),/Тестовый ответ/);assert.equal(await f.page.locator('#aiInput').inputValue(),'');
      assert.equal((await api(f.user)).state.future.keep,true);assert.deepEqual(f.errors,[]);
    } finally {await f.ctx.close();}
  });
  await run('stalled bootstrap API cannot leave Manual blank forever',async()=>{
    const f=await fresh('daily-bootstrap-timeout');
    try {
      await f.ctx.route('**/api/state',()=>new Promise(()=>{}));
      await f.page.goto(origin+'/manual.html');
      await until(()=>f.page.evaluate(()=>Boolean(window.DVIZH_MANUAL_STATE)),'bounded 15-second bootstrap',22000);
      // A brand-new browser cannot have loaded hasSeenIntro while its API is stalled.
      await f.page.locator('[data-action="finish-intro"]').click();
      assert.notEqual(await f.page.locator('#syncStatusDot').getAttribute('data-sync'),'ok');
      await nav(f.page,'tasks');assert.deepEqual(f.errors,[]);
    } finally {await f.ctx.close();}
  });
  await run('all existing sections navigate without overflow or JavaScript exceptions',async()=>{
    const f=await fresh('daily-navigation');
    try {
      await manual(f);let navigations=0;f.page.on('framenavigated',frame=>{if(frame===f.page.mainFrame())navigations++;});
      for(const view of ['home','tasks','focus','week','training','social','proof','settings']) {
        await nav(f.page,view);assert.ok(await f.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),view+' mobile overflow');
      }
      assert.equal(navigations,0);assert.deepEqual(f.errors,[]);
    } finally {await f.ctx.close();}
  });
  fs.writeFileSync(path.join(__dirname,'browser-results.json'),JSON.stringify({environment:'isolated Chromium + temporary SQLite; no live AI/microphone',results},null,2)+'\n');
  console.log(`PASS ${results.length} real-browser daily flows`);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();
  if(server && server.exitCode===null){server.stdin.end('stop\n');const timer=setTimeout(()=>server.kill('SIGKILL'),5000);timer.unref();server.once('exit',()=>clearTimeout(timer));}
});
