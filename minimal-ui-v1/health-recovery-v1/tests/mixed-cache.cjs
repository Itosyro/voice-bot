const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'/home/exedev/.hermes/dev/dvizh/browser-tools-sync-stability/node_modules/playwright');
const root=path.resolve(__dirname,'..');
(async()=>{
 const server=spawn('python3',[path.join(__dirname,'serve_fixture.py')]);
 const port=await new Promise((res,rej)=>{server.stdout.once('data',b=>res(JSON.parse(b).port));server.once('exit',c=>rej(Error(c)))});
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/home/exedev/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',headless:true,args:['--no-sandbox']});
 try{
 for(const combo of ['old-app-new-html','new-app-old-html','old-app-old-html','old-app-old-sync','new-app-old-sync']){
  const context=await browser.newContext({extraHTTPHeaders:{'X-ExeDev-UserID':'browser-test','X-ExeDev-Email':'browser@example.invalid'},serviceWorkers:'block'});
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  let oldSyncLoads=0;
  if(combo.endsWith('old-sync'))await page.route('**/sync.js*',r=>{oldSyncLoads++;return r.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(root,'baseline/static/sync.js'),'utf8')})});
  if(combo.startsWith('old-app'))await page.route('**/app.js',r=>r.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(root,'baseline/static/app.js'),'utf8')}));
  if(combo.endsWith('old-html'))await page.route('**/manual.html',r=>r.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(root,'baseline/static/manual.html'),'utf8')}));
  await page.goto(`http://127.0.0.1:${port}/manual.html`);await page.waitForFunction(()=>window.DVIZH_MANUAL_STATE);
  if(combo.endsWith('old-sync'))assert.equal(oldSyncLoads,1,combo);
  let nav=0;page.on('framenavigated',()=>nav++);
  // Remote health arrives while the old application has a stale state/form ancestor.
  let response=await (await context.request.get(`http://127.0.0.1:${port}/api/state`)).json();
  response.state.healthRecovery={version:1,timezone:'Europe/Moscow',future:{keep:42},sleep:{'2026-09-10':{day:'2026-09-10',durationMinutes:450,quality:4}}};
  await context.request.put(`http://127.0.0.1:${port}/api/state`,{data:{baseRevision:response.revision,state:response.state}});
  await page.evaluate(()=>window.DVIZH_SYNC.pull());
  // Existing Manual check-in save cannot erase the unfamiliar health domain.
  await page.locator('[data-checkin="energy"] [data-value="2"]').click();
  await page.evaluate(()=>window.DVIZH_SYNC.push());
  response=await (await context.request.get(`http://127.0.0.1:${port}/api/state`)).json();
  assert.equal(response.state.healthRecovery.future.keep,42,combo);assert.equal(response.state.healthRecovery.sleep['2026-09-10'].quality,4,combo);
  assert.equal(nav,0,combo);assert.deepEqual(errors,[],combo);
  if(combo==='old-app-new-html'){
    assert.equal(await page.locator('#healthSleepForm button[type=submit]').isDisabled(),true);
    await page.locator('.sidebar [data-nav="settings"]').click();
    assert.equal(await page.locator('#healthCapability').isVisible(),true);
    assert.match(await page.locator('#healthCapability').textContent(),/Обнови Manual/);
  }
  await context.close();
 }
 console.log('PASS mixed cache: old/new app+HTML combinations, stale legacy saves retain remote health, no reload');
 }finally{await browser.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
