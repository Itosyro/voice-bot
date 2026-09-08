// Offline browser checks. All requests are fulfilled locally; no live API access.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const routes = ['home','tasks','focus','proof','week','training','social','settings'];
const browserPath = process.env.CHROMIUM_EXECUTABLE;

async function fixture(width=390, height=844) {
  const browser = await chromium.launch({headless:true, executablePath:browserPath, args:['--no-sandbox']});
  const context = await browser.newContext({viewport:{width,height}, reducedMotion:'reduce', serviceWorkers:'block'});
  await context.route('**/*', route => {
    const name = new URL(route.request().url()).pathname;
    const files = {'/manual.html':'../release/manual.html', '/styles.css':'baseline/styles.css', '/app.js':'baseline/app.js', '/boot.js':'baseline/boot.js'};
    if (files[name]) return route.fulfill({body:fs.readFileSync(path.join(root,files[name])), contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html', headers:{'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'none'"}});
    if (name==='/sync.js') return route.fulfill({contentType:'text/javascript',body:'window.DVIZH_SYNC_READY = Promise.resolve();'});
    if (name==='/') return route.fulfill({contentType:'text/html',body:'<title>AI destination</title>'});
    return route.fulfill({status:404,body:''});
  });
  const page = await context.newPage();
  const errors=[]; page.on('pageerror', e=>errors.push(e.message));
  await page.goto('https://quiet-manual.test/manual.html');
  await page.locator('[data-action="finish-intro"]').click();
  return {browser,page,errors};
}

for (const width of [320,390,760,900,1440]) test(`mode header and all routes reachable at ${width}px`, async()=>{
  const {browser,page,errors}=await fixture(width);
  try {
    const header=page.locator('.qs-mode-header');
    for (const link of await header.locator('a').all()) {
      const box=await link.boundingBox();
      assert.ok(box.width>=44 && box.height>=44);
    }
    await header.locator('a').first().focus();
    assert.equal(await header.locator('a').first().evaluate(el=>getComputedStyle(el).outlineStyle),'solid');
    const nav=width<=760?'.mobile-nav':'.nav-list';
    for (const route of routes) {
      const button=page.locator(`${nav} [data-nav="${route}"]`);
      assert.ok(await button.isVisible(), `${route} visible`);
      await button.click();
      assert.ok(await page.locator(`#view-${route}`).isVisible());
      assert.equal(await page.locator('.view:visible').count(),1);
      assert.ok(await header.isVisible());
      assert.equal((await header.boundingBox()).y,0);
      if (route==='training' || route==='social') {
        const panels=await page.locator(`#view-${route} [data-minimal-secondary]`).all();
        assert.ok(panels.length>0, 'secondary panels retained');
        const details=page.locator(`#view-${route} [data-minimal-details-toggle]`);
        for (const panel of panels) assert.ok(await panel.isHidden(), 'details initially closed');
        await details.click();
        for (const panel of panels) assert.ok(await panel.isVisible(), 'first click expands details');
        await details.click();
        for (const panel of panels) assert.ok(await panel.isHidden(), 'second click collapses details');
      }
    }
    for (const route of ['proof','training','social']) {
      await page.locator(`${nav} [data-nav="settings"]`).click();
      await page.locator(`.minimal-ui-shortcuts [data-nav="${route}"]`).click();
      assert.ok(await page.locator(`#view-${route}`).isVisible());
    }
    await page.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));
    assert.equal((await header.boundingBox()).y,0);
    assert.ok(await page.locator('#taskModal').isHidden());
    await header.locator('a[href="/"]').click();
    assert.equal(new URL(page.url()).pathname,'/');
    assert.deepEqual(errors,[]);
  } finally {await browser.close();}
});

test('dark palette overrides minimal on/off, tone and theme; live timer remains data-driven',async()=>{
  const {browser,page}=await fixture();
  try {
    for (const minimal of [true,false]) for (const tone of ['direct','calm']) for (const theme of ['light','dark']) {
      await page.evaluate(({minimal,tone,theme})=>{
        document.documentElement.classList.toggle('dvizh-minimal-ui',minimal);
        document.documentElement.dataset.theme=theme;
        document.body.dataset.theme=theme; document.body.dataset.tone=tone;
      },{minimal,tone,theme});
      for (const selector of ['body','.panel','.rescue-card','.modal','.toast','input','textarea']) {
        const style=await page.locator(selector).first().evaluate(el=>({bg:getComputedStyle(el).backgroundColor,fg:getComputedStyle(el).color}));
        assert.ok(style.bg.match(/\d+/g).slice(0,3).every(v=>Number(v)<45), `${selector} dark: ${style.bg}`);
      }
      const button=page.locator('.button-primary').first();
      assert.equal(await button.evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(157, 224, 189)');
    }
    await page.locator('.mobile-nav [data-nav="focus"]').click();
    const ring=page.locator('#timerRing');
    const before=await ring.evaluate(el=>getComputedStyle(el).backgroundImage);
    // This is the same existing custom-property output updateTimerUI writes.
    await ring.evaluate(el=>el.style.setProperty('--progress','180deg'));
    const after=await ring.evaluate(el=>getComputedStyle(el).backgroundImage);
    assert.notEqual(before,after); assert.ok(after.includes('180deg'));
    assert.ok(after.includes('157, 224, 189'));
    assert.equal(await page.locator('#timerDisplay').count(),1);
    const cssErrors=await page.evaluate(()=>{const s=document.querySelector('#quiet-signal-manual-v2').sheet; return !s || !s.cssRules.length;});
    assert.equal(cssErrors,false);
  } finally {await browser.close();}
});
