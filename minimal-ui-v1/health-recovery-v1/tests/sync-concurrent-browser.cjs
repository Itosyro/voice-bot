const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'/home/exedev/.hermes/dev/dvizh/browser-tools-sync-stability/node_modules/playwright');
const DAY='2026-09-10';
(async()=>{
 const server=spawn('python3',[path.join(__dirname,'serve_fixture.py')]);
 const port=await new Promise((resolve,reject)=>{server.stdout.once('data',b=>resolve(JSON.parse(b).port));server.once('exit',c=>reject(Error(c)))});
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/home/exedev/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',headless:true,args:['--no-sandbox']});
 try{
  const options={extraHTTPHeaders:{'X-ExeDev-UserID':'browser-test','X-ExeDev-Email':'browser@example.invalid'},serviceWorkers:'block'};
  const contexts=await Promise.all([browser.newContext(options),browser.newContext(options)]),url=`http://127.0.0.1:${port}`;
  let remote=await (await contexts[0].request.get(url+'/api/state')).json();
  remote.state.healthRecovery={version:1,timezone:'UTC',sleep:{[DAY]:{day:DAY,start:'23:00',end:'07:00',startDay:'2026-09-09',durationMinutes:480,durationKind:'clock',note:'keep',source:'manual',future:42}}};
  assert.equal((await contexts[0].request.put(url+'/api/state',{data:{baseRevision:remote.revision,state:remote.state}})).status(),200);
  const pages=await Promise.all(contexts.map(c=>c.newPage())),errors=[];
  let baselineLoads=0;
  for(const page of pages){
   page.on('pageerror',e=>errors.push(e.message));
   if(process.argv.includes('--baseline-sync'))await page.route('**/sync.js*',route=>{baselineLoads++;return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(__dirname,'../baseline/static/sync.js'),'utf8')})});
  }
  await Promise.all(pages.map(async page=>{await page.goto(url+'/manual.html');await page.waitForFunction(()=>window.DVIZH_HEALTH&&window.DVIZH_SYNC&&window.DVIZH_MANUAL_STATE);await page.evaluate(()=>window.DVIZH_SYNC_READY)}));
  if(process.argv.includes('--baseline-sync'))assert.equal(baselineLoads,2);
  // Hold both real HTTP PUTs until both clients have saved from the same revision.
  let release,count=0,conflicts=0;const gate=new Promise(r=>release=r),revisions=[];
  for(const page of pages){
   page.on('response',r=>{if(r.url().endsWith('/api/state')&&r.status()===409)conflicts++});
   await page.route('**/api/state',async route=>{
    if(route.request().method()==='PUT'&&count<2){revisions.push(route.request().postDataJSON().baseRevision);if(++count===2)release();await gate}
    await route.continue();
   });
  }
  await Promise.all(pages.map((page,i)=>page.evaluate(async({i,day})=>{
   const state=JSON.parse(localStorage.getItem('dvizh-state-v1'));
   window.DVIZH_HEALTH.apply(state,'health_sleep',{day,timezone:'UTC',source:'manual',...(i?{start:'22:00',quality:4}:{end:'08:00',note:'local note'})});
   state['independent'+i]={keep:true};localStorage.setItem('dvizh-state-v1',JSON.stringify(state));await window.DVIZH_SYNC.push();
  },{i,day:DAY})));
  assert.equal(count,2);assert.equal(revisions[0],revisions[1]);assert.equal(conflicts,1);
  remote=await (await contexts[0].request.get(url+'/api/state')).json();const row=remote.state.healthRecovery.sleep[DAY];
  assert.equal(row.start,'22:00');assert.equal(row.end,'08:00');assert.equal(row.durationMinutes,600);assert.equal(row.startDay,'2026-09-09');assert.equal(row.note,'local note');assert.equal(row.quality,4);assert.equal(row.source,'manual');assert.equal(row.future,42);
  assert.deepEqual(remote.state.independent0,{keep:true});assert.deepEqual(remote.state.independent1,{keep:true});
  await Promise.all(pages.map(page=>page.evaluate(()=>window.DVIZH_SYNC.pull())));
  for(const page of pages)assert.equal(await page.evaluate(day=>JSON.parse(localStorage.getItem('dvizh-state-v1')).healthRecovery.sleep[day].durationMinutes,DAY),600);
  assert.deepEqual(errors,[]);
  console.log('PASS real concurrent browser saves: same revision, HTTP 409 retry, 22–08/600 persisted, independent edits and both readbacks retained');
 }finally{await browser.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
