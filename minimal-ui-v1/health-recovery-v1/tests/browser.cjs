const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || '/home/exedev/.hermes/dev/dvizh/browser-tools-sync-stability/node_modules/playwright');
const root=path.resolve(__dirname,'..');
(async()=>{
 const server=spawn('python3',[path.join(__dirname,'serve_fixture.py')]);
 const port=await new Promise((resolve,reject)=>{server.stdout.once('data',b=>resolve(JSON.parse(b.toString()).port));server.once('exit',c=>reject(Error('server '+c)));});
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH || '/home/exedev/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',headless:true,args:['--no-sandbox']});
 try {
 const context=await browser.newContext({viewport:{width:390,height:844},extraHTTPHeaders:{'X-ExeDev-UserID':'browser-test','X-ExeDev-Email':'browser@example.invalid'},serviceWorkers:'block'});
 const page=await context.newPage(); await page.clock.setFixedTime(new Date('2026-09-10T12:00:00Z')); const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(`http://127.0.0.1:${port}/manual.html`);
 await page.waitForFunction(()=>window.DVIZH_MANUAL_STATE);
 let navigations=0; page.on('framenavigated',f=>{if(f===page.mainFrame()) navigations++});
 await page.locator('.health-more summary').click();
 await page.locator('.health-more [data-nav="settings"]').click();
 await page.locator('#healthOpen').click({timeout:3000});
 assert.deepEqual(errors,[]);
 assert.equal(await page.locator('#healthError').textContent(),'');
 assert.match(await page.locator('#healthSummary').innerText(),/Нет данных/);
 const sleep=page.locator('#healthSleepForm');
 await sleep.locator('[name=day]').fill('2026-09-10'); await sleep.locator('[name=day]').dispatchEvent('change');
 await sleep.locator('[name=start]').fill('23:30'); await sleep.locator('[name=end]').fill('07:00');
 await sleep.locator('[name=quality]').selectOption('4');
 await sleep.locator('button[type=submit]').click();
 await page.waitForFunction(()=>window.DVIZH_MANUAL_STATE.snapshot().healthRecovery?.sleep?.['2026-09-10']?.durationMinutes===450);
 await sleep.locator('[name=quality]').selectOption('3'); await sleep.locator('button[type=submit]').click();
 assert.equal(await page.evaluate(()=>window.DVIZH_MANUAL_STATE.snapshot().healthRecovery.sleep['2026-09-10'].quality),3);
 await sleep.locator('[name=day]').fill('2026-09-08'); await sleep.locator('[name=day]').dispatchEvent('change');
 await sleep.locator('[name=durationMinutes]').fill('390'); await sleep.locator('button[type=submit]').click();
 const stats=await page.evaluate(()=>window.DVIZH_HEALTH.summary(window.DVIZH_MANUAL_STATE.snapshot(),'2026-09-10'));
 assert.equal(stats.sleep.mean7Minutes,420); assert.equal(stats.sleep.recordedDays,2);
 assert.match(await page.locator('#healthSummary').innerText(),/420 мин.*2 записанных дней/);
 // Schedules expose stable individual slots and a free-text dose.
 await page.getByText('Расписания добавок',{exact:true}).click();
 const schedule=page.locator('#healthScheduleForm');
 await schedule.locator('[name=name]').fill('My supplement'); await schedule.locator('[name=dose]').fill('one user scoop');
 await schedule.locator('[data-slot-time]').fill('08:00'); await schedule.locator('[data-add-slot]').click();
 await schedule.locator('[data-slot-time]').nth(1).fill('20:00');
 await schedule.locator('button[type=submit]').click();
 assert.equal(await page.locator('#healthError').textContent(),'');
 // The visible day/zone owns this mark even if midnight passes or zone input changes.
 assert.match(await page.locator('#healthSummary').innerText(),/2026-09-10/);
 await page.clock.setFixedTime(new Date('2026-09-11T12:00:00Z'));
 await page.locator('#healthTimezone').fill('Pacific/Honolulu');
 await page.locator('[data-mark-status=taken]').first().click();
 const midnight=await page.evaluate(()=>Object.values(window.DVIZH_MANUAL_STATE.snapshot().healthRecovery.intakes)[0]);
 assert.equal(midnight.day,'2026-09-10');assert.notEqual(midnight.timezone,'Pacific/Honolulu');
 await page.clock.setFixedTime(new Date('2026-09-10T12:00:00Z'));
 await page.locator('#healthTimezone').fill(midnight.timezone);
 await page.locator('#healthOpen').click();
 await page.locator('[data-mark-status=taken]').first().click();
 await page.locator('[data-mark-status=taken]').first().click();
 assert.equal(await page.evaluate(()=>Object.keys(window.DVIZH_MANUAL_STATE.snapshot().healthRecovery.intakes).length),1);
 await page.locator('[data-mark-status=skipped]').nth(1).click();
 assert.equal(await page.locator('#healthIntakes [data-intake-row]').count(),2);
 await page.locator('[data-edit-schedule]').first().click();
 await schedule.locator('[name=dose]').fill('changed user dose'); await schedule.locator('[name=enabled]').uncheck(); await schedule.locator('button[type=submit]').click();
 assert.equal(await page.locator('#healthIntakes [data-intake-row]').count(),0);
 assert.match(await page.locator('#healthHistory').textContent(),/one user scoop/);
 const checkin=page.locator('#healthCheckinForm');
 await checkin.locator('[name=energy]').selectOption('2'); await checkin.locator('[name=note]').fill('sore legs'); await checkin.locator('button[type=submit]').click();
 await checkin.locator('[name=stress]').selectOption('4'); await checkin.locator('button[type=submit]').click();
 const ci=await page.evaluate(()=>Object.values(window.DVIZH_MANUAL_STATE.snapshot().healthRecovery.checkins)[0]);
 assert.equal(ci.energy,2); assert.equal(ci.stress,4); assert.equal(ci.soreness,undefined);
 // Untrusted fields use the real sync reconciliation and recursive app merge.
 const remoteSafe=await page.evaluate(()=>{
   const before=({}).polluted,s=window.DVIZH_MANUAL_STATE.snapshot();
   s.future=JSON.parse('{"keep":true,"__proto__":{"polluted":true},"constructor":{"prototype":{"polluted":true}}}');
   window.DVIZH_MANUAL_STATE.applyRemote(s);
   const stored=window.DVIZH_MANUAL_STATE.snapshot().future;
   return {safe:({}).polluted===before,preserved:Object.hasOwn(stored,'__proto__')&&stored.__proto__.polluted===true};
 });
 assert.equal(remoteSafe.safe,true);assert.equal(remoteSafe.preserved,true);
 // Open form ancestor: a remote field update must survive saving a different field.
 await sleep.locator('[name=day]').fill('2026-09-10'); await sleep.locator('[name=day]').dispatchEvent('change');
 await page.evaluate(()=>{const s=window.DVIZH_MANUAL_STATE.snapshot();s.healthRecovery.sleep['2026-09-10'].quality=5; window.DVIZH_MANUAL_STATE.applyRemote(s); localStorage.setItem('dvizh-state-v1',JSON.stringify(s));});
 await sleep.locator('[name=note]').fill('edited locally'); await sleep.locator('button[type=submit]').click();
 assert.equal(await page.evaluate(()=>window.DVIZH_MANUAL_STATE.snapshot().healthRecovery.sleep['2026-09-10'].quality),5);
 await page.evaluate(()=>window.DVIZH_SYNC.push());
 const stored=await (await context.request.get(`http://127.0.0.1:${port}/api/state`)).json();
 assert.equal(stored.state.future.keep,true); assert.equal(stored.state.healthRecovery.sleep['2026-09-10'].note,'edited locally');
 for(const route of ['home','tasks','week','training','social','proof','settings']) {
   await page.locator('.health-more summary').click();
   await page.locator(`.health-more [data-nav="${route}"]`).click();
   assert.equal(await page.locator(`#view-${route}`).evaluate(e=>e.classList.contains('is-active')),true);
 }
 assert.equal(navigations,0); assert.deepEqual(errors,[]);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 assert.doesNotMatch(fs.readFileSync(path.join(root,'dist/app.js'),'utf8'),/MutationObserver/);
 await page.locator('#healthTitle').scrollIntoViewIfNeeded();
 await page.screenshot({path:path.join(root,'tests/mobile.png')});
 await page.evaluate(()=>{const s=window.DVIZH_MANUAL_STATE.snapshot();s.healthRecovery.sleep['2026-09-10'].durationMinutes='<img src=x data-untrusted-health>';window.DVIZH_MANUAL_STATE.applyRemote(s);});
 await page.locator('#healthOpen').click();
 assert.equal(await page.locator('#healthRecovery img').count(),0);
 console.log('PASS browser: sleep/edit/midnight/mean, supplements, check-in, form rebase, API persistence, legacy routes, no reload, mobile');
 } finally {await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
