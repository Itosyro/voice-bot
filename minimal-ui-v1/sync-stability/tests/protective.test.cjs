const {test}=require('node:test');
const assert=require('node:assert/strict');
const {domHarness}=require('./dom-harness.cjs');
const {fixture}=require('./harness.cjs');
const KEY='dvizh-state-v1', RECOVERY='dvizh-manual-recovery-v1', PENDING='dvizh-sync-quarantine-v1';
const versions={app:'baseline',sync:'release'};
const setup=s=>{s.jumpLab.profile={age:19,heightCm:156};};
test('actual boot gates capability after loaded, retaining local startup write without bootstrap PUT',async()=>{
 let before=false;
 const h=await domHarness(setup,{...versions,beforeReady(w){const state=fixture();state.jumpLab.profile={age:20,heightCm:156};w.localStorage.setItem(KEY,JSON.stringify(state));},async beforeBoot(w){
  before=true;assert.equal(w.DVIZH_SYNC.protective,false);assert.equal(w.document.querySelector('#syncUpdateRequired'),null);
  await w.DVIZH_SYNC.push();
 }});
 try {
  assert.ok(before);assert.equal(h.w.DVIZH_SYNC.protective,true);
  assert.equal(h.w.DVIZH_SYNC.pendingLocal.jumpLab.profile.age,20);
  await h.advance(9000);assert.equal(h.requests.filter(r=>r.method==='PUT').length,0);
 }finally{h.dom.window.close();}
});
test('protective repeated polls/manual/online cannot upload; dirty form identity retained; archives survive update',async()=>{
 const h=await domHarness(setup,versions);
 try {
  h.dom.reconfigure({url:'http://dvizh.test/manual.html'});
  const w=h.w;h.click('[data-nav="training"]');const age=w.document.querySelector('#jumpAge');age.value='21';age.focus();
  for(let i=0;i<3;i++){await h.pull(s=>{s.jumpLab.profile.heightCm=160+i;});await w.DVIZH_SYNC.push();}
  w.dispatchEvent(new w.Event('online'));await h.flush();await h.advance(9000);
  assert.equal(w.document.querySelector('#jumpAge'),age);assert.equal(age.value,'21');assert.equal(w.document.activeElement,age);
  assert.equal(h.navigationErrors.length,0);assert.equal(h.requests.filter(r=>r.method==='PUT').length,0);
  let confirms=0;w.confirm=message=>{confirms++;assert.match(message,/Автоматическое заполнение.*недоступны/);return false;};
  h.click('[data-manual-update]');assert.equal(confirms,1);assert.equal(h.navigationErrors.length,0);
  const archive=w.localStorage.getItem(RECOVERY);assert.equal(JSON.parse(archive).forms.find(f=>f.id==='jumpProfileForm').fields.find(f=>f.id==='jumpAge').value,'21');
  assert.equal(age.value,'21');
  w.confirm=()=>true;h.click('[data-manual-update]');assert.equal(h.navigationErrors.length,1,'only explicit confirmed update attempts navigation');
  assert.equal(w.document.querySelector('[data-manual-update]').dataset.manualUpdate,'/manual.html?v=20260909-sync-stability-2');
  const next=await domHarness(setup,{app:'release',sync:'release',storage:{[RECOVERY]:archive}});
  try{assert.equal(next.w.DVIZH_SYNC.protective,false);next.click('#syncDraftRecovery button');const text=next.w.document.querySelector('#syncDraftRecovery textarea');assert.equal(text.hidden,false);assert.ok(text.value.includes('21'));assert.equal(next.w.localStorage.getItem(RECOVERY),archive);assert.equal(next.state().jumpLab.profile.age,19);}finally{next.dom.window.close();}
 }finally{h.dom.window.close();}
});
test('failed draft persistence blocks navigation, displays recoverable copy and explicit Russian warning',async()=>{
 const h=await domHarness(setup,{...versions,beforeSync(w){const native=w.Storage.prototype.setItem;w.Storage.prototype.setItem=function(k,v){if(k===RECOVERY)throw Error('quota');return native.call(this,k,v);};}});
 try {h.click('[data-nav="tasks"]');h.click('[data-action="edit-task"]');const title=h.w.document.querySelector('#taskTitle');title.value='Unsaved safe draft';h.w.confirm=()=>{throw Error('must not confirm');};h.click('[data-manual-update]');
  assert.equal(h.navigationErrors.length,0);assert.equal(title.value,'Unsaved safe draft');assert.match(h.w.document.querySelector('#syncUpdateRequired').textContent,/Восстановление не гарантировано/);
  assert.ok(h.w.document.querySelector('#syncUpdateRequired textarea').value.includes('Unsaved safe draft'));assert.deepEqual(h.errors,[]);
 }finally{h.dom.window.close();}
});
test('quarantine survives another old-app boot without discarding earlier pending edits',async()=>{
 const old={state:{...fixture(),jumpLab:{profile:{age:20},webCommands:[]}},history:[]};
 const h=await domHarness(setup,{...versions,storage:{[PENDING]:JSON.stringify(old)}});
 try {assert.ok(h.w.localStorage.getItem(PENDING).includes('"age":20'));const current=h.state();current.jumpLab.profile.age=22;h.w.localStorage.setItem(KEY,JSON.stringify(current));const saved=JSON.parse(h.w.localStorage.getItem(PENDING));assert.ok(JSON.stringify(saved).includes('"age":20'));assert.equal(saved.state.jumpLab.profile.age,22);}finally{h.dom.window.close();}
});
test('quarantine quota failure retains pending edit in memory and warns without stale PUT',async()=>{
 const h=await domHarness(setup,{...versions,beforeSync(w){const native=w.Storage.prototype.setItem;w.Storage.prototype.setItem=function(k,v){if(k===PENDING)throw Error('quota');return native.call(this,k,v);};}});
 try {h.click('[data-nav="training"]');await h.pull(s=>{s.jumpLab.profile.heightCm=160;});h.w.document.querySelector('#jumpAge').value='20';h.w.document.querySelector('#jumpProfileForm').dispatchEvent(new h.w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();await h.advance(1700);
  assert.equal(h.w.DVIZH_SYNC.pendingLocal.jumpLab.profile.age,20);assert.equal(h.state().jumpLab.profile.heightCm,160);assert.equal(h.remote().jumpLab.profile.heightCm,160);assert.equal(h.requests.filter(r=>r.method==='PUT').length,0);assert.match(h.w.document.querySelector('#syncUpdateRequired').textContent,/Не удалось сохранить/);assert.deepEqual(h.errors,[]);
 }finally{h.dom.window.close();}
});
for(const pendingAges of [[],[26,27]])test(`stored original age25 survives old app bootstrap and recovery (pending=${pendingAges})`,async()=>{
 const original=fixture();original.tone='direct';setup(original);original.jumpLab.profile.age=25;
 const h=await domHarness(setup,{...versions,storage:{[KEY]:JSON.stringify(original)},beforeReady(w){
  for(const age of pendingAges){const next=JSON.parse(JSON.stringify(original));next.jumpLab.profile.age=age;w.localStorage.setItem(KEY,JSON.stringify(next));}
 }});
 try {
  const saved=JSON.parse(h.w.localStorage.getItem(PENDING));
  const ages=[saved.state,...saved.history.map(x=>x.state)].map(s=>s.jumpLab.profile.age);
  for(const age of [25,...pendingAges])assert.ok(ages.includes(age),`missing original/pending age ${age}: ${ages}`);
  h.w.confirm=()=>false;h.click('[data-manual-update]');
  const archive=JSON.parse(h.w.localStorage.getItem(RECOVERY));
  for(const age of [25,...pendingAges])assert.ok([archive.pending.state,...archive.pending.history.map(x=>x.state)].some(s=>s.jumpLab.profile.age===age));
  await h.advance(9000);assert.equal(h.requests.filter(r=>r.method==='PUT').length,0);assert.deepEqual(h.errors,[]);
 }finally{h.dom.window.close();}
});
for(const allWrites of [false,true])test(`startup clientId quota failure is visible and recoverable (all writes=${allWrites})`,async()=>{
 const original=fixture();original.tone='direct';setup(original);original.jumpLab.profile.age=25;
 const h=await domHarness(setup,{app:'release',sync:'release',storage:{[KEY]:JSON.stringify(original)},beforeBoot(w){assert.equal(w.DVIZH_SYNC.protective,true);assert.equal(w.document.querySelector('#syncUpdateRequired textarea').hidden,false);},beforeSync(w){
  const native=w.Storage.prototype.setItem;w.Storage.prototype.setItem=function(k,v){if(allWrites||k==='dvizh-client-id-v1')throw new w.DOMException('Quota exceeded','QuotaExceededError');return native.call(this,k,v);};
 }});
 try {
  assert.equal(h.w.DVIZH_SYNC.protective,true);
  const panel=h.w.document.querySelector('#syncUpdateRequired');assert.equal(panel.getAttribute('role'),'alert');assert.match(panel.textContent,/хранилищ|сохранить/);
  const backup=panel.querySelector('textarea');assert.equal(backup.hidden,false);assert.ok(backup.getAttribute('aria-label'));assert.ok(backup.value.includes('"age": 25'));
  await h.w.DVIZH_SYNC.pull();await h.w.DVIZH_SYNC.push();h.w.dispatchEvent(new h.w.Event('online'));await h.advance(9000);
  assert.equal(h.requests.filter(r=>r.method==='PUT').length,0);assert.deepEqual(h.errors,[]);
 }finally{h.dom.window.close();}
});
for(const cas of [false,true])test(`cache fixture delayed earlier-tab bootstrap PUT explains height regression (CAS=${cas})`,async()=>{
 const {stateServer}=require('./state-server.cjs');
 // The first context has just navigated to the release and still has its
 // bootstrap debounce pending when cache-browser resets the shared server.
 const earlier=await domHarness(setup,{app:'release',sync:'release'});
 const service=stateServer(earlier.remote(),{cas});earlier.dom.window.close();
 const first=await domHarness(()=>{},{app:'release',sync:'release',service});
 let reverse,next;
 try {
  service.state.jumpLab.profile={age:19,heightCm:156};service.revision++;
  reverse=await domHarness(()=>{},{...versions,service});reverse.click('[data-nav="training"]');
  await reverse.pull(s=>{s.jumpLab.profile.heightCm=160;});
  reverse.w.document.querySelector('#jumpAge').value='20';
  reverse.w.document.querySelector('#jumpProfileForm').dispatchEvent(new reverse.w.Event('submit',{bubbles:true,cancelable:true}));
  reverse.w.document.querySelector('#jumpAge').value='21';
  await reverse.w.DVIZH_SYNC.push();assert.equal(service.state.jumpLab.profile.heightCm,160);
  assert.equal(reverse.requests.filter(r=>r.method==='PUT').length,0);
  reverse.w.confirm=()=>false;reverse.click('[data-manual-update]');
  const storage=Object.fromEntries([KEY,'dvizh-sync-meta-v1',PENDING,RECOVERY].map(k=>[k,reverse.w.localStorage.getItem(k)]));
  next=await domHarness(()=>{},{app:'release',sync:'release',service,storage});
  // Deterministically fire the earlier tab's delayed bootstrap upload.
  await first.advance(450);
  assert.ok(first.requests.some(r=>r.method==='PUT'));
  assert.equal(service.state.jumpLab.profile.heightCm,cas?160:156);
  await next.advance(9000);
  assert.equal(service.state.jumpLab.profile.heightCm,160,'updated tab eventually flushes its own bootstrap; the reported immediate checkpoint above must still be safe');
  next.click('#syncDraftRecovery button');
  const recovered=JSON.parse(next.w.document.querySelector('#syncDraftRecovery textarea').value);
  assert.equal(recovered.forms.forms.find(f=>f.id==='jumpProfileForm').fields.find(f=>f.id==='jumpAge').value,'21');
  assert.equal(recovered.quarantined.state.jumpLab.profile.age,20);
  for(const h of [first,reverse,next])assert.deepEqual(h.errors,[]);
 }finally{first.dom.window.close();reverse?.dom.window.close();next?.dom.window.close();}
});
