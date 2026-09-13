'use strict';
// Actual HTTP and SQLite; only browser storage, rendering and timers are fixtures.
const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const source = fs.readFileSync(process.env.DVIZH_SYNC_SOURCE || path.join(__dirname, '../dist/sync.js'), 'utf8');
const STATE = 'dvizh-state-v1', META = 'dvizh-sync-meta-v1';
const seed = () => ({version:1,tasks:[],hasSeenIntro:true,future:{keep:true}});
const task = id => ({id,title:`Fixture task ${id}`,done:false,createdAt:'2026-09-13T10:00:00.000Z'});
let child, origin, exited;
before(async () => {
  child = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, 'serve_sync_fixture.py')], {stdio:['pipe','pipe','pipe']});
  exited = once(child, 'exit');
  const output = await new Promise((resolve,reject) => {
    let text = '', errors = '';
    const timer = setTimeout(() => reject(new Error(`fixture startup timeout: ${errors}`)), 5000);
    child.stderr.on('data', data => {errors += data;});
    child.on('error', error => {clearTimeout(timer);reject(error);});
    child.once('exit', code => {clearTimeout(timer);reject(new Error(`fixture exited ${code}: ${errors}`));});
    child.stdout.on('data', data => {text += data;if(text.includes('\n')){clearTimeout(timer);resolve(text.split('\n')[0]);}});
  });
  const {port} = JSON.parse(output);
  assert.ok(Number.isInteger(port) && port > 0 && port < 65536);
  origin = `http://127.0.0.1:${port}`;
});
after(async () => {
  if (!child || child.exitCode !== null) return;
  child.stdin.end('stop\n');
  const timer = setTimeout(() => child.kill('SIGKILL'), 5000);
  try {await exited;} finally {clearTimeout(timer);}
});
async function snapshot(user) {
  const result = await fetch(origin + '/api/state', {headers:{'X-ExeDev-UserID':user,'X-ExeDev-Email':`${user}@example.invalid`},signal:AbortSignal.timeout(5000)});
  assert.equal(result.status,200);
  return result.json();
}
async function client(user, backing = new Map([[STATE,JSON.stringify(seed())]])) {
  class Storage {
    getItem(k) {return backing.get(k) ?? null;}
    setItem(k,v) {backing.set(k,String(v));}
    removeItem(k) {backing.delete(k);}
  }
  const storage = new Storage(), dot = {dataset:{},classList:{toggle(){}}};
  const c = {backing,storage,conflicts:0,putFault:null,
    state:()=>JSON.parse(storage.getItem(STATE)),meta:()=>JSON.parse(storage.getItem(META)),
    save(fn){const value=c.state();fn(value);storage.setItem(STATE,JSON.stringify(value));}};
  const ctx = vm.createContext({Storage,localStorage:storage,navigator:{onLine:true},console,
    document:{readyState:'complete',visibilityState:'visible',addEventListener(){},querySelectorAll(){return []},
      getElementById(id){return id==='syncStatusDot' ? dot : null;}},
    setTimeout:()=>1,clearTimeout(){},
    async fetch(url,options={}) {
      assert.equal(url,'/api/state');
      const isPut=options.method==='PUT';
      if(isPut)assert.equal(JSON.parse(options.body).force,false);
      const fault=isPut?c.putFault:null;
      if(isPut)c.putFault=null;
      if(fault==='not-saved')return {ok:true,status:200,json:async()=>{throw new SyntaxError('fixture HTML');}};
      const result=await fetch(origin+url,{...options,headers:{...options.headers,'X-ExeDev-UserID':user,'X-ExeDev-Email':`${user}@example.invalid`},redirect:'error',signal:AbortSignal.timeout(5000)});
      if(result.status===409)c.conflicts++;
      if(fault==='lost-receipt'){
        assert.equal(result.status,200);await result.arrayBuffer();
        return {ok:true,status:200,json:async()=>{throw new SyntaxError('fixture damaged receipt');}};
      }
      return result;
    }});
  ctx.window=ctx;ctx.setInterval=()=>1;ctx.addEventListener=()=>{};
  ctx.DVIZH_MANUAL_STATE={applyRemote(){}};
  vm.runInContext(source,ctx,{filename:'sync.js'});
  await ctx.DVIZH_SYNC_READY;ctx.DVIZH_SYNC.markAppLoaded();
  c.push=()=>ctx.DVIZH_SYNC.push();c.pull=()=>ctx.DVIZH_SYNC.pull();c.status=()=>dot.dataset.sync;
  return c;
}
test('HTTP/SQLite: create, reopen, complete and read from another client', {timeout:10000}, async()=>{
  const user='lifecycle-test',a=await client(user);
  a.save(v=>v.tasks.push(task('one')));await a.push();assert.equal(a.status(),'ok');
  const reopened=await client(user,a.backing);assert.equal(reopened.state().tasks[0].id,'one');
  reopened.save(v=>{v.tasks[0].done=true;v.tasks[0].completedAt='2026-09-13T10:05:00.000Z';});await reopened.push();
  const remote=await snapshot(user),other=await client(user);
  assert.equal(remote.state.tasks.length,1);assert.equal(remote.state.tasks[0].done,true);
  assert.equal(other.state().tasks[0].done,true);assert.deepEqual(remote.state.future,{keep:true});
});
test('HTTP/SQLite: two client writes use actual 409 and retain both tasks', {timeout:10000},async()=>{
  const user='conflict-test',a=await client(user);await a.push();const b=await client(user);
  a.save(v=>v.tasks.push(task('a')));b.save(v=>v.tasks.push(task('b')));
  await a.push();await b.push();assert.equal(b.conflicts,1);
  assert.deepEqual((await snapshot(user)).state.tasks.map(t=>t.id).sort(),['a','b']);
  await a.pull();assert.equal(a.state().tasks.length,2);
});
test('HTTP/SQLite: accepted write with lost receipt retries without duplication', {timeout:10000},async()=>{
  const user='lost-receipt-test',a=await client(user);await a.push();
  a.save(v=>v.tasks.push(task('one')));const before=a.meta();a.putFault='lost-receipt';
  await a.push();assert.deepEqual(a.meta(),before);assert.notEqual(a.status(),'ok');
  assert.equal((await snapshot(user)).state.tasks.length,1);
  await a.push();assert.equal(a.conflicts,1);assert.equal(a.status(),'ok');
  assert.equal((await snapshot(user)).state.tasks.length,1);
});
test('HTTP/SQLite: false success cannot erase unsent task after another client saves', {timeout:10000},async()=>{
  const user='false-success-test',a=await client(user);await a.push();const b=await client(user);
  a.save(v=>v.tasks.push(task('unsent')));a.putFault='not-saved';await a.push();
  b.save(v=>v.tasks.push(task('other')));await b.push();
  await a.pull();assert.deepEqual(a.state().tasks.map(t=>t.id).sort(),['other','unsent']);
  await a.push();assert.deepEqual((await snapshot(user)).state.tasks.map(t=>t.id).sort(),['other','unsent']);
});
