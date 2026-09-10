const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'..'),DAY='2026-09-10',copy=v=>JSON.parse(JSON.stringify(v));
const seed=()=>({version:1,tasks:[],healthRecovery:{version:1,timezone:'UTC',sleep:{[DAY]:{day:DAY,start:'23:00',end:'07:00',startDay:'2026-09-09',durationMinutes:480,durationKind:'clock',note:'keep',source:'manual',future:42}}}});
async function setup(old=false){
 const server={state:seed(),revision:1,puts:[],conflicts:0,barrier:null};
 function client(legacy=false){
  class Storage{constructor(){this.data={}}getItem(k){return this.data[k]??null}setItem(k,v){this.data[k]=String(v)}removeItem(k){delete this.data[k]}}
  const storage=new Storage(),document={readyState:'loading',addEventListener(){},querySelectorAll(){return []},getElementById(){return null}};
  const ctx=vm.createContext({Storage,localStorage:storage,document,Intl,Date,console,setTimeout:()=>1,clearTimeout(){},fetch:async(url,opts={})=>{
   if(opts.method==='PUT'){
    const body=JSON.parse(opts.body);server.puts.push(body);
    if(server.barrier)await server.barrier();
    if(body.baseRevision!==server.revision){server.conflicts++;return {status:409,ok:false,json:async()=>copy(server)}}
    server.state=copy(body.state);server.revision++;
   }
   return {status:200,ok:true,json:async()=>({state:copy(server.state),revision:server.revision})};
  }});
  ctx.window=ctx;ctx.setInterval=()=>1;ctx.addEventListener=()=>{};
  ctx.DVIZH_MANUAL_STATE={applyRemote:s=>{ctx.current=copy(s)}};
  vm.runInContext(fs.readFileSync(path.join(root,legacy?'baseline/static/sync.js':'dist/sync.js'),'utf8'),ctx);
  vm.runInContext(fs.readFileSync(path.join(root,'domain.js'),'utf8'),ctx);
  return {ctx,storage,async ready(){await ctx.DVIZH_SYNC_READY;ctx.DVIZH_SYNC.markAppLoaded();ctx.current=JSON.parse(storage.getItem('dvizh-state-v1'))},save(fields,other={}){ctx.DVIZH_HEALTH.apply(ctx.current,'health_sleep',{day:DAY,timezone:'UTC',...fields});Object.assign(ctx.current,other);storage.setItem('dvizh-state-v1',JSON.stringify(ctx.current))},push:()=>ctx.DVIZH_SYNC.push(),pull:()=>ctx.DVIZH_SYNC.pull()};
 }
 const a=client(),b=client(old);await Promise.all([a.ready(),b.ready()]);
 function barrier(){let count=0,release;const gate=new Promise(r=>release=r);server.barrier=async()=>{if(++count===2){server.barrier=null;release()}await gate}}
 return {server,a,b,barrier};
}
test('actual concurrent PUT/CAS merges two clock edits and independent fields',async()=>{
 const {server,a,b,barrier}=await setup();
 a.save({end:'08:00',note:'local note'},{independentA:1});b.save({start:'22:00',quality:4},{independentB:2});barrier();
 await Promise.all([a.push(),b.push()]);assert.equal(server.conflicts,1);
 const row=server.state.healthRecovery.sleep[DAY];assert.equal(row.start,'22:00');assert.equal(row.end,'08:00');assert.equal(row.durationMinutes,600);assert.equal(row.startDay,'2026-09-09');
 assert.equal(row.note,'local note');assert.equal(row.quality,4);assert.equal(row.future,42);assert.equal(row.source,'ai');assert.equal(server.state.independentA,1);assert.equal(server.state.independentB,2);
 await Promise.all([a.pull(),b.pull()]);for(const c of [a,b]){assert.equal(JSON.parse(c.storage.getItem('dvizh-state-v1')).healthRecovery.sleep[DAY].durationMinutes,600);assert.equal(c.ctx.DVIZH_HEALTH.summary(c.ctx.current,DAY).sleep.last.durationMinutes,600)}
});
test('clock/reported transitions preserve temporal bundle and independent edits in both conflict directions',async()=>{
 for(const localReported of [true,false]){
  const {server,a,b}=await setup();
  a.save(localReported?{durationMinutes:400,note:'reported'}:{end:'08:00',quality:5});
  b.save(localReported?{end:'08:00',quality:5}:{durationMinutes:400,note:'reported'});
  await a.push();await b.push();const row=server.state.healthRecovery.sleep[DAY];
  assert.equal(row.durationKind,'reported');assert.equal(row.durationMinutes,400);for(const k of ['start','end','startDay'])assert.equal(Object.hasOwn(row,k),false);
  assert.equal(row.quality,5);assert.equal(row.note,'reported');assert.equal(row.future,42);
 }
});
test('cached prefeature sync may persist stale derived data; new client repairs on read and next save',async()=>{
 const {server,a,b}=await setup(true);
 a.save({end:'08:00'});b.save({start:'22:00'});await a.push();await b.push();
 assert.equal(server.state.healthRecovery.sleep[DAY].durationMinutes,540); // Real old writer regression fixture.
 await a.pull();assert.equal(a.ctx.DVIZH_HEALTH.summary(a.ctx.current,DAY).sleep.last.durationMinutes,600);
 a.save({note:'new note'});await a.push();assert.equal(server.state.healthRecovery.sleep[DAY].durationMinutes,600);
 assert.equal(server.state.healthRecovery.sleep[DAY].note,'new note');
});
test('reported to clock transition wins over reported-duration edit without losing note/source',async()=>{
 for(const clockFirst of [true,false]){
  const {server,a,b}=await setup();a.save({durationMinutes:400,source:'manual'});await a.push();await b.pull();
  a.save(clockFirst?{start:'06:00',end:'08:00',source:'manual'}:{durationMinutes:420,note:'independent'});
  b.save(clockFirst?{durationMinutes:420,note:'independent'}:{start:'06:00',end:'08:00',source:'manual'});
  await a.push();await b.push();const row=server.state.healthRecovery.sleep[DAY];
  assert.equal(row.durationKind,'clock');assert.equal(row.durationMinutes,120);assert.equal(row.startDay,DAY);assert.equal(row.note,'independent');assert.equal(row.future,42);
 }
});
