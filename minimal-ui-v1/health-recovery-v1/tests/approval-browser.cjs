const assert=require('node:assert/strict'),path=require('node:path'),{spawn}=require('node:child_process'),readline=require('node:readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'/home/exedev/.hermes/dev/dvizh/browser-tools-sync-stability/node_modules/playwright');
(async()=>{
 const server=spawn('python3',[path.join(__dirname,'serve_fixture.py'),'--approval']);
 const lines=readline.createInterface({input:server.stdout});
 const next=()=>new Promise(r=>lines.once('line',s=>r(JSON.parse(s))));
 const {port}=await next();
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/home/exedev/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',headless:true,args:['--no-sandbox']});
 try{
 const context=await browser.newContext({extraHTTPHeaders:{'X-ExeDev-UserID':'browser-test','X-ExeDev-Email':'browser@example.invalid'},serviceWorkers:'block'}),page=await context.newPage();
 await page.goto(`http://127.0.0.1:${port}/manual.html`);await page.waitForFunction(()=>window.DVIZH_MANUAL_STATE);
 assert.equal(await page.evaluate(()=>window.DVIZH_MANUAL_STATE.snapshot().healthRecovery),undefined);
 const panel=page.locator('#aiProposalPanel');
 await panel.waitFor({state:'visible',timeout:3000});
 const text=await panel.textContent();
 assert.match(text,/one exact user scoop/);assert.match(text,/08:00/);assert.match(text,/20:00/);assert.match(text,/Europe\/Moscow/);
 await page.locator('[data-ai-proposal-decision=approve]').click();await page.evaluate(()=>window.DVIZH_SYNC.push());
 assert.equal(await page.evaluate(()=>window.DVIZH_MANUAL_STATE.snapshot().healthRecovery),undefined);
 const done=next();server.stdin.write('process\n');const result=await done;assert.equal(result.applied,true);
 await page.evaluate(()=>window.DVIZH_SYNC.pull());
 const state=await page.evaluate(()=>window.DVIZH_MANUAL_STATE.snapshot());
 assert.equal(state.healthRecovery.schedules.ai_schedule.dose,'one exact user scoop');assert.equal(state.aiProposalCommands.length,0);
 console.log('PASS browser confirmation: exact proposed dose/times/zone visible; inert before approval; existing command bridge applies to temporary API');
 }finally{await browser.close();server.kill();lines.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
