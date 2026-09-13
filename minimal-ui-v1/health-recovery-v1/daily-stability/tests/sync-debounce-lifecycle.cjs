'use strict';
// Whole sync client, no real network; verify the scheduled write is consumed by a manual flush.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(process.env.DVIZH_SYNC_SOURCE||path.join(__dirname,'../dist/sync.js'),'utf8');
const STATE='dvizh-state-v1',copy=value=>JSON.parse(JSON.stringify(value));
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const flush=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
async function fixture(){
  const backing=new Map(),timers=new Map();let seq=0;
  class Storage{getItem(k){return backing.get(k)??null;}setItem(k,v){backing.set(k,String(v));}removeItem(k){backing.delete(k);}}
  const storage=new Storage(),dot={dataset:{},classList:{toggle(){}}};
  const server={state:{version:1,tasks:[],hasSeenIntro:true},revision:10,puts:[],hold:null};
  const ctx=vm.createContext({Storage,localStorage:storage,AbortController,navigator:{onLine:true},console,
    document:{readyState:'complete',visibilityState:'visible',addEventListener(){},querySelectorAll(){return [];},getElementById:id=>id==='syncStatusDot'?dot:null},
    setTimeout(fn,delay){const id=++seq;timers.set(id,{fn,delay});return id;},clearTimeout(id){timers.delete(id);},
    async fetch(url,options={}){
      assert.equal(url,'/api/state');
      if(options.method==='PUT'){
        const body=JSON.parse(options.body);assert.equal(body.force,false);server.puts.push(copy(body));
        if(server.hold){const gate=server.hold;server.hold=null;gate.started.resolve();await gate.release.promise;}
        assert.equal(body.baseRevision,server.revision);server.state=copy(body.state);server.revision++;
      }
      return {ok:true,status:200,json:async()=>({ok:true,state:copy(server.state),revision:server.revision})};
    }});
  ctx.window=ctx;ctx.addEventListener=()=>{};ctx.setInterval=()=>1;ctx.DVIZH_MANUAL_STATE={applyRemote(){}};
  vm.runInContext(source,ctx);await ctx.DVIZH_SYNC_READY;ctx.DVIZH_SYNC.markAppLoaded();
  const save=fn=>{const state=JSON.parse(storage.getItem(STATE));fn(state);storage.setItem(STATE,JSON.stringify(state));};
  save(state=>state.tasks.push({id:'fixture-task',title:'One task',done:false,createdAt:'2026-09-13T10:00:00.000Z'}));
  return {server,timers,save,push:()=>ctx.DVIZH_SYNC.push(),status:()=>dot.dataset.sync};
}
test('explicit flush consumes its pending debounce instead of writing twice',async()=>{
  const f=await fixture();assert.ok([...f.timers.values()].some(t=>t.delay===450));
  await f.push();assert.equal([...f.timers.values()].filter(t=>t.delay===450).length,0);
  assert.equal(f.server.puts.length,1);assert.equal(f.status(),'ok');
});
test('consuming debounce retains later edits queued during an in-flight write',async()=>{
  const f=await fixture(),gate={started:deferred(),release:deferred()};f.server.hold=gate;
  const pending=f.push();await gate.started.promise;
  assert.equal([...f.timers.values()].filter(t=>t.delay===450).length,0);
  f.save(state=>state.tasks[0].done=true);gate.release.resolve();await pending;
  assert.equal(f.server.state.tasks[0].done,false);assert.notEqual(f.status(),'ok');
  const retry=[...f.timers.values()].find(t=>t.delay===1600);assert.ok(retry);retry.fn();await flush();
  assert.equal(f.server.state.tasks[0].done,true);assert.equal(f.server.puts.length,2);
});
