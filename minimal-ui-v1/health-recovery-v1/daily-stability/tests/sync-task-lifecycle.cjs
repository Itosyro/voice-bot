'use strict';
// Executes the complete shipped sync client, not a reimplementation of its merge.
// All state, transport, storage and timers are isolated fixtures. No network I/O.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(process.env.DVIZH_SYNC_SOURCE || path.join(__dirname, '../dist/sync.js'), 'utf8');
const STATE = 'dvizh-state-v1', META = 'dvizh-sync-meta-v1';
const copy = x => x === undefined ? undefined : JSON.parse(JSON.stringify(x));
const T = '2026-09-13T10:00:00.000Z';
const task = (id, title = id) => ({id, title, done:false, createdAt:T});
const seed = () => ({version:1, createdAt:T, hasSeenIntro:true, tasks:[], sessions:[], proofs:[], checkins:{}, plans:{}, ladder:{}, future:{keep:true}});
const reply = (body, status=200) => ({status, ok:status >= 200 && status < 300, json:async()=>copy(body)});
const html = () => ({status:200,ok:true,json:async()=>{throw new SyntaxError('HTML is not JSON');}});
const deferred = () => {let resolve; const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function server(initial = seed()) {
  const s = {state:copy(initial), revision:initial ? 10 : 0, puts:[], conflicts:0, offline:false, nextGet:null, nextPut:null, holdPut:null};
  s.external = fn => {fn(s.state);s.revision++;};
  s.snapshot = () => ({ok:true, state:copy(s.state), revision:s.revision, updatedAt:T});
  s.request = async (url, options={}) => {
    assert.equal(url, '/api/state', 'the harness must not make real requests');
    if (s.offline) throw new TypeError('network fixture offline');
    if (options.method !== 'PUT') {
      if (s.nextGet) {const f=s.nextGet;s.nextGet=null;return f();}
      return reply(s.snapshot());
    }
    const body = JSON.parse(options.body);
    assert.equal(body.force, false, 'all writes must retain optimistic concurrency');
    s.puts.push(copy(body));
    if (s.holdPut) {const gate=s.holdPut;s.holdPut=null;gate.started.resolve();await gate.release.promise;}
    if (s.nextPut) {const f=s.nextPut;s.nextPut=null;return f(body);}
    if (s.state !== null && body.baseRevision !== s.revision) {
      s.conflicts++;
      return reply({...s.snapshot(),ok:false},409);
    }
    s.state=copy(body.state);s.revision++;
    return reply(s.snapshot());
  };
  return s;
}
async function client(s, backing = new Map(), {loaded=true, faults={}}={}) {
  class Storage {
    getItem(k) {faults.get?.(k);return backing.has(k) ? backing.get(k) : null;}
    setItem(k,v) {faults.set?.(k,String(v));backing.set(k,String(v));}
    removeItem(k) {faults.remove?.(k);backing.delete(k);}
  }
  const storage=new Storage(), timers=new Map(), listeners=new Map();let sequence=0;
  const statuses=[];
  const nodes = new Map();
  nodes.set('syncStatusText',{set textContent(v){statuses.push(v);this.text=v;}, get textContent(){return this.text;}});
  nodes.set('syncSettingsStatus',{});
  nodes.set('syncStatusDot',{dataset:{},classList:{toggle(){}}});
  const document={readyState:'complete',visibilityState:'visible',getElementById:id=>nodes.get(id)||null,
    addEventListener(type,fn){listeners.set(type,fn);},querySelectorAll(){return []}};
  const ctx=vm.createContext({AbortController,Storage,localStorage:storage,document,navigator:{onLine:!s.offline},console,
    setTimeout(fn,delay){const id=++sequence;timers.set(id,{fn,delay});return id;},
    clearTimeout(id){timers.delete(id);}, fetch:s.request});
  ctx.window=ctx;ctx.setInterval=()=>1;ctx.addEventListener=(name,fn)=>listeners.set(name,fn);
  const c={ctx,storage,backing,timers,faults,listeners,statuses,current:null,applied:[],
    state:()=>JSON.parse(storage.getItem(STATE)),meta:()=>JSON.parse(storage.getItem(META)),
    status:()=>nodes.get('syncStatusDot').dataset.sync,
    save(fn){const state=c.state();fn(state);storage.setItem(STATE,JSON.stringify(state));c.current=c.state();},
    push:()=>ctx.DVIZH_SYNC.push(),pull:()=>ctx.DVIZH_SYNC.pull()};
  ctx.DVIZH_MANUAL_STATE={applyRemote(state){c.applied.push(copy(state));c.current=copy(state);}};
  vm.runInContext(source,ctx,{filename:'sync.js'});
  await ctx.DVIZH_SYNC_READY;
  if(loaded)ctx.DVIZH_SYNC.markAppLoaded();
  c.current=c.state();
  return c;
}
function savedLocally(c) {const state=c.state();state.tasks.push(task('local','One real-sized fixture task'));c.storage.setItem(STATE,JSON.stringify(state));}
function assertUnacknowledged(c, before, message='write not acknowledged') {
  assert.deepEqual(c.meta(),before,message);
  assert.ok(c.state().tasks.some(t=>t.id==='local'),'local task remains recoverable');
  assert.notEqual(c.status(),'ok','must not claim synchronized');
}

test('daily path: create, reload, complete, reload and read on a second device',async()=>{
  const s=server(),a=await client(s);savedLocally(a);await a.push();
  const reloaded=await client(s,a.backing);assert.equal(reloaded.state().tasks[0].id,'local');
  reloaded.save(v=>{v.tasks[0].done=true;v.tasks[0].completedAt=T;});await reloaded.push();
  const reopened=await client(s,a.backing),other=await client(s);
  for(const c of [reopened,other]){assert.equal(c.state().tasks.length,1);assert.equal(c.state().tasks[0].done,true);assert.deepEqual(c.state().future,{keep:true});}
});
test('offline edits survive a page reload and upload after reconnection',async()=>{
  const s=server(),a=await client(s);s.offline=true;a.ctx.navigator.onLine=false;
  savedLocally(a);await a.push();assert.equal(s.state.tasks.length,0);
  const b=await client(s,a.backing);assert.equal(b.state().tasks.length,1);
  s.offline=false;b.ctx.navigator.onLine=true;await b.push();assert.equal(s.state.tasks[0].id,'local');
});
test('two device creations survive the actual client CAS conflict path',async()=>{
  const s=server(),a=await client(s),b=await client(s);
  a.save(v=>v.tasks.push(task('a')));b.save(v=>v.tasks.push(task('b')));
  await a.push();await b.push();assert.equal(s.conflicts,1);
  assert.deepEqual(s.state.tasks.map(t=>t.id).sort(),['a','b']);
  await a.pull();assert.equal(a.state().tasks.length,2);
});
test('completion and title edits on different devices merge without reverting completion',async()=>{
  const state=seed();state.tasks=[task('shared')];const s=server(state),a=await client(s),b=await client(s);
  a.save(v=>{v.tasks[0].done=true;v.tasks[0].completedAt=T;});
  b.save(v=>{v.tasks[0].title='Edited elsewhere';});await a.push();await b.push();
  assert.equal(s.state.tasks[0].done,true);assert.equal(s.state.tasks[0].title,'Edited elsewhere');
});
test('a deleted task does not reappear after another device edits it',async()=>{
  const state=seed();state.tasks=[task('shared')];const s=server(state),a=await client(s),b=await client(s);
  a.save(v=>{v.tasks=[];});b.save(v=>{v.tasks[0].title='Old tab';});await a.push();await b.push();
  assert.equal(s.state.tasks.length,0);
});
test('edits made while a PUT is waiting are kept for the next upload',async()=>{
  const s=server(),a=await client(s);savedLocally(a);
  const gate={started:deferred(),release:deferred()};s.holdPut=gate;const pending=a.push();await gate.started.promise;
  a.save(v=>{v.tasks[0].done=true;v.tasks[0].completedAt=T;});gate.release.resolve();await pending;
  assert.equal(a.state().tasks[0].done,true);await a.push();assert.equal(s.state.tasks[0].done,true);
});
for(const [name,response] of [
  ['HTML instead of JSON',html],['empty JSON',()=>reply({})],['JSON array',()=>reply([])],
  ['missing revision',()=>reply({state:seed()})],['string revision',()=>reply({state:seed(),revision:'11'})],
  ['negative revision',()=>reply({state:seed(),revision:-1})],['fractional revision',()=>reply({state:seed(),revision:10.5})],
  ['server explicitly rejected',()=>reply({ok:false,state:seed(),revision:11})],
])test(`unconfirmed PUT: ${name} cannot advance the merge ancestor`,async()=>{
  const s=server(),a=await client(s);savedLocally(a);const before=copy(a.meta());s.nextPut=response;
  await a.push();assertUnacknowledged(a,before);
});
test('unconfirmed PUT followed by a remote change cannot erase an unsent task',async()=>{
  const s=server(),a=await client(s);savedLocally(a);s.nextPut=html;await a.push();
  s.external(v=>{v.tone='calm';});await a.pull();
  assert.ok(a.state().tasks.some(t=>t.id==='local'),'unsent task was mistaken for a remote deletion');
  await a.push();assert.equal(s.state.tasks.length,1);assert.equal(s.state.tone,'calm');
});
test('a successful-looking response for a different state is not a save receipt',async()=>{
  const s=server(),a=await client(s);savedLocally(a);const before=copy(a.meta());
  s.nextPut=()=>reply({ok:true,state:seed(),revision:11});await a.push();assertUnacknowledged(a,before);
});
test('server saved but receipt was lost: retry keeps one task, not a duplicate',async()=>{
  const s=server(),a=await client(s);savedLocally(a);const before=copy(a.meta());
  s.nextPut=body=>{s.state=copy(body.state);s.revision++;return html();};await a.push();assertUnacknowledged(a,before);
  await a.push();assert.equal(s.conflicts,1);assert.equal(s.state.tasks.length,1);assert.equal(a.ctx.DVIZH_SYNC.revision,s.revision);
});
for(const [name,snapshot] of [
  ['unsupported version',{version:2,tasks:[]}],['missing task list',{version:1}],['array state',[]]
])test(`invalid 409 ${name} cannot replace local storage`,async()=>{
  const s=server(),a=await client(s);savedLocally(a);const before=copy(a.meta());
  s.nextPut=()=>reply({ok:false,state:snapshot,revision:11},409);await a.push();assertUnacknowledged(a,before);
  assert.equal(s.puts.length,1,'invalid conflict must not be retried with a fabricated empty state');
});
for(const [name,response] of [
  ['HTML',html],['missing state',()=>reply({ok:true,revision:11})],
  ['unsupported state',()=>reply({ok:true,revision:11,state:{version:2,tasks:[]}})],
  ['false empty response',()=>reply({ok:true,state:null,revision:11})],
])test(`invalid GET ${name} preserves cached task and revision on reload`,async()=>{
  const s=server(),a=await client(s);savedLocally(a);const cached=a.storage.getItem(STATE),before=copy(a.meta());
  s.nextGet=response;const b=await client(s,a.backing);
  assert.equal(b.storage.getItem(STATE),cached);assert.deepEqual(b.meta(),before);
});
test('invalid later GET cannot null out saved local data',async()=>{
  const s=server(),a=await client(s);savedLocally(a);const before=copy(a.meta()),local=copy(a.state());
  s.nextGet=()=>reply({ok:true,revision:11,state:{version:2,tasks:[]}});await a.pull();
  assert.deepEqual(a.meta(),before);assert.deepEqual(a.state(),local);
});
test('401 and 500 keep edits locally and retry only through the normal CAS path',async()=>{
  for(const status of [401,500]){
    const s=server(),a=await client(s);savedLocally(a);const before=copy(a.meta());s.nextPut=()=>reply(null,status);
    await a.push();assertUnacknowledged(a,before);await a.push();assert.equal(s.state.tasks.length,1);
  }
});
test('a fresh account accepts null state at revision zero and creates revision one',async()=>{
  const s=server(null),backing=new Map([[STATE,JSON.stringify(seed())]]),a=await client(s,backing);
  savedLocally(a);await a.push();assert.equal(s.revision,1);assert.equal(a.ctx.DVIZH_SYNC.revision,1);
});
test('acknowledgment of the older snapshot does not display all changes as synced',async()=>{
  const s=server(),a=await client(s);savedLocally(a);
  const gate={started:deferred(),release:deferred()};s.holdPut=gate;const pending=a.push();await gate.started.promise;
  a.save(v=>{v.tasks[0].done=true;});gate.release.resolve();await pending;
  assert.equal(s.state.tasks[0].done,false);assert.notEqual(a.status(),'ok');
  await a.push();assert.equal(a.status(),'ok');assert.equal(s.state.tasks[0].done,true);
});
test('cached unsent changes are not labeled synchronized before app load',async()=>{
  const s=server(),a=await client(s);savedLocally(a);
  const b=await client(s,a.backing,{loaded:false});assert.equal(b.state().tasks.length,1);assert.notEqual(b.status(),'ok');
});
test('health data and unknown fields survive task saves and conflict reconciliation',async()=>{
  const state=seed();state.healthRecovery={version:1,timezone:'UTC',sleep:{'2026-09-13':{day:'2026-09-13',durationKind:'reported',durationMinutes:435,note:'fixture only'}}};
  state.trainingHub={future:{untouched:true}};const s=server(state),a=await client(s),b=await client(s);
  savedLocally(a);b.save(v=>{v.healthRecovery.sleep['2026-09-13'].note='another fixture';});await b.push();await a.push();
  assert.equal(s.state.tasks.length,1);assert.equal(s.state.healthRecovery.sleep['2026-09-13'].durationMinutes,435);
  assert.equal(s.state.healthRecovery.sleep['2026-09-13'].note,'another fixture');assert.deepEqual(s.state.trainingHub,{future:{untouched:true}});
});

// Additional resilience regressions: receipts, stalled HTTP, and storage quota.
const flush = async () => {for(let i=0;i<20;i++)await Promise.resolve();};
async function expireRequest(c) {
  await flush();
  const timeout=[...c.timers.values()].find(t=>t.delay===15000);
  assert.ok(timeout,'every sync request, including its body, must have a finite deadline');
  timeout.fn();await flush();
}
for (const revision of [0,10,12,Number.MAX_SAFE_INTEGER+1]) test(`a PUT cannot confirm invalid revision ${revision}`,async()=>{
  const s=server(),a=await client(s);savedLocally(a);const before=copy(a.meta());
  s.nextPut=body=>reply({ok:true,state:copy(body.state),revision});
  await a.push();assertUnacknowledged(a,before);
});
test('a receipt without explicit ok=true is not a successful write',async()=>{
  const s=server(),a=await client(s);savedLocally(a);const before=copy(a.meta());
  s.nextPut=body=>reply({state:copy(body.state),revision:11});
  await a.push();assertUnacknowledged(a,before);
});
test('a stale GET cannot roll back an accepted revision',async()=>{
  const s=server(),a=await client(s);savedLocally(a);await a.push();const before=copy(a.meta());
  s.nextGet=()=>reply({ok:true,state:seed(),revision:1});await a.pull();
  assert.deepEqual(a.meta(),before);assert.equal(a.state().tasks[0].id,'local');
});
for (const revision of [9,10]) test(`invalid conflict revision ${revision} cannot retry a stale snapshot`,async()=>{
  const s=server(),a=await client(s);savedLocally(a);const before=copy(a.meta());
  s.nextPut=()=>reply({ok:false,state:seed(),revision},409);await a.push();
  assertUnacknowledged(a,before);assert.equal(s.puts.length,1);
});
for (const phase of ['headers','body']) test(`stalled GET ${phase} releases the sync lock and preserves edits`,async()=>{
  const s=server(),a=await client(s);savedLocally(a);const before=copy(a.meta());
  s.nextGet=()=>phase==='headers'?new Promise(()=>{}):{ok:true,status:200,json:()=>new Promise(()=>{})};
  const waiting=a.pull();await expireRequest(a);await waiting;
  assert.deepEqual(a.meta(),before);assert.equal(a.state().tasks[0].id,'local');
  await a.push();assert.equal(s.state.tasks[0].id,'local');
});
for (const phase of ['headers','body']) test(`stalled PUT ${phase} is unconfirmed and can retry without duplication`,async()=>{
  const s=server(),a=await client(s);savedLocally(a);const before=copy(a.meta());
  s.nextPut=body=>{s.state=copy(body.state);s.revision++;return phase==='headers'?new Promise(()=>{}):{ok:true,status:200,json:()=>new Promise(()=>{})};};
  const waiting=a.push();await expireRequest(a);await waiting;
  assertUnacknowledged(a,before);await a.push();assert.equal(s.state.tasks.length,1);assert.equal(a.status(),'ok');
});
test('late response after timeout cannot overwrite a later successful synchronization',async()=>{
  const s=server(),a=await client(s);savedLocally(a);const d=deferred();
  s.nextGet=()=>d.promise;const waiting=a.pull();await expireRequest(a);await waiting;
  await a.push();const before=copy(a.meta());d.resolve(reply({ok:true,state:seed(),revision:999}));await flush();
  assert.deepEqual(a.meta(),before);assert.equal(a.state().tasks[0].id,'local');
});
test('failed metadata persistence on PUT keeps the old receipt for a safe CAS retry',async()=>{
  const s=server(),a=await client(s);savedLocally(a);const before=copy(a.meta());
  a.faults.set=k=>{if(k===META)throw Error('fixture quota');};await a.push();
  assertUnacknowledged(a,before);assert.equal(a.ctx.DVIZH_SYNC.revision,before.revision);
  a.faults.set=null;await a.push();assert.equal(s.state.tasks.length,1);assert.equal(a.status(),'ok');
});
test('failed metadata persistence on pull restores the previous matching state and receipt',async()=>{
  const s=server(),a=await client(s);savedLocally(a);const before=copy(a.meta()),local=copy(a.state());
  s.external(v=>v.tasks.push(task('remote')));
  a.faults.set=k=>{if(k===META)throw Error('fixture quota');};await a.pull();
  assert.deepEqual(a.meta(),before);assert.deepEqual(a.state(),local);
  a.faults.set=null;const b=await client(s,a.backing);await b.push();
  assert.deepEqual(s.state.tasks.map(t=>t.id).sort(),['local','remote']);
});
test('failed metadata persistence during conflict retains both tasks on a later retry',async()=>{
  const s=server(),a=await client(s);savedLocally(a);const before=copy(a.meta()),local=copy(a.state());
  s.external(v=>v.tasks.push(task('remote')));
  a.faults.set=k=>{if(k===META)throw Error('fixture quota');};await a.push();
  assert.deepEqual(a.meta(),before);assert.deepEqual(a.state(),local);
  a.faults.set=null;await a.push();assert.deepEqual(s.state.tasks.map(t=>t.id).sort(),['local','remote']);
});
test('failure to restore storage enters protective mode and cannot keep uploading',async()=>{
  const s=server(),a=await client(s);savedLocally(a);s.external(v=>v.tasks.push(task('remote')));
  let stateWrites=0;a.faults.set=k=>{if(k===META || (k===STATE && ++stateWrites>1))throw Error('fixture quota');};
  await a.pull();assert.equal(a.ctx.DVIZH_SYNC.protective,true);
  assert.ok(a.ctx.DVIZH_SYNC.pendingLocal.tasks.some(t=>t.id==='local'));
  const puts=s.puts.length;a.faults.set=null;await a.push();assert.equal(s.puts.length,puts);
});
