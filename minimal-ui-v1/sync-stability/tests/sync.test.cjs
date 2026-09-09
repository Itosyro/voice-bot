const {test} = require('node:test');
const assert = require('node:assert/strict');
const {harness, fixture, T1} = require('./harness.cjs');
test('poll applies remote without reload, including metadata and key order', async () => {
  for (const change of [s => s.tasks[0].title = 'Remote', s => s.__sync.updatedAt = T1,
    s => s.tasks[0]._syncUpdatedAt = T1,
    s => s.tasks[0] = Object.fromEntries(Object.entries(s.tasks[0]).reverse())]) {
    const h = await harness(); const remote = fixture(); change(remote);
    let applied; h.context.DVIZH_MANUAL_STATE = {applyRemote(s) {applied = s;}};
    h.respond('GET', {state:remote, revision:11}); await h.advance(8120);
    assert.equal(h.reloads.length, 0); assert.deepEqual(JSON.parse(JSON.stringify(applied)), h.state());
    assert.equal(h.context.DVIZH_SYNC.revision, 11);
  }
});
test('three-way 409 keeps local field, remote sibling and additions; retry has accepted revision', async () => {
  const h = await harness(); const local = h.state(); local.tasks[0].title='Local'; h.write(local);
  const remote=fixture(); remote.tasks[0].micro='Remote micro'; remote.trainingHub={profile:{planEnabled:true},webCommands:[]};
  h.respond('PUT', {state:remote,revision:11},409); h.respond('PUT',{revision:12});
  await h.advance(600);
  const sent=h.requests.filter(r=>r.method==='PUT');
  assert.equal(sent.length,2); assert.equal(sent[1].body.baseRevision,11);
  assert.equal(sent[1].body.state.tasks[0].title,'Local');
  assert.equal(sent[1].body.state.tasks[0].micro,'Remote micro');
  assert.equal(sent[1].body.state.trainingHub.profile.planEnabled,true);
  assert.equal(h.reloads.length,0);
});
test('queued pull three-way preserves local and remote fields', async () => {
  const h=await harness(); const local=h.state(); local.tasks[0].title='Local'; h.write(local);
  const remote=fixture(); remote.tasks[0].micro='Remote micro';
  h.respond('GET',{state:remote,revision:11}); await h.context.DVIZH_SYNC.pull();
  assert.equal(h.state().tasks[0].title,'Local'); assert.equal(h.state().tasks[0].micro,'Remote micro');
});
test('pending GET serializes PUT and drains queued pulls', async () => {
  const h=await harness(); let release; const wait=new Promise(r=>release=r);
  const remote=fixture(); remote.tasks[0].micro='Remote micro';
  h.replies.push({method:'GET',status:200,body:{state:remote,revision:11},wait});
  const pull=h.context.DVIZH_SYNC.pull(); await h.flush();
  const local=h.state(); local.tasks[0].title='During GET'; h.write(local);
  await h.context.DVIZH_SYNC.push();
  assert.equal(h.requests.length,2,'no concurrent PUT against stale revision');
  release(); await pull; await h.flush();
  assert.equal(h.state().tasks[0].title,'During GET'); assert.equal(h.state().tasks[0].micro,'Remote micro');
});
test('edit while PUT is pending remains queued; pull requests coalesce and retry uses latest edit',async()=>{
 const h=await harness();let release;const wait=new Promise(r=>release=r);
 let local=h.state();local.tasks[0].title='First';h.write(local);
 h.replies.push({method:'PUT',status:200,body:{revision:11},wait});const push=h.context.DVIZH_SYNC.push();await h.flush();
 local=h.state();local.tasks[0].title='Second';h.write(local);
 await h.context.DVIZH_SYNC.pull();await h.context.DVIZH_SYNC.pull();
 const remote=fixture();remote.tasks[0].title='First';remote.tasks[0].micro='Remote after PUT';
 h.respond('GET',{state:remote,revision:12});release();await push;await h.flush();
 assert.equal(h.requests.filter(r=>r.method==='GET').length,2);assert.equal(h.state().tasks[0].title,'Second');
 h.respond('PUT',{revision:13});await h.advance(1700);
 assert.equal(h.requests.at(-1).body.state.tasks[0].title,'Second');assert.equal(h.requests.at(-1).body.state.tasks[0].micro,'Remote after PUT');
 assert.equal(h.requests.at(-1).body.baseRevision,12);
});
test('second 409 is bounded then queued retry reconciles newer remote deletion and command ack',async()=>{
 const h=await harness();const local=h.state();local.jumpLab.webCommands=[{id:'new',action:'profile_update',profile:{age:20}}];h.write(local);
 const first=fixture();first.jumpLab.webCommands=[];
 const second=fixture();second.tasks=[];second.__sync.deletedTasks={'synthetic-task':T1};second.jumpLab.commandResults=[{id:'old',status:'ok'}];second.jumpLab.webCommands=[];
 h.respond('PUT',{state:first,revision:11},409);h.respond('PUT',{state:second,revision:12},409);await h.context.DVIZH_SYNC.push();
 assert.equal(h.requests.filter(r=>r.method==='PUT').length,2);
 h.respond('PUT',{state:second,revision:12},409);h.respond('PUT',{revision:13});await h.advance(1700);
 assert.equal(h.state().tasks.length,0);assert.equal(h.state().jumpLab.webCommands[0].id,'new');assert.equal(h.state().jumpLab.commandResults[0].id,'old');
});
test('offline local reset never bypasses revision conflict',async()=>{
 const h=await harness();h.context.navigator.onLine=false;
 h.context.localStorage.removeItem('dvizh-state-v1');const reset=fixture();reset.tasks=[];h.write(reset);
 h.replies.push({method:'PUT',error:'offline'});await h.context.DVIZH_SYNC.push();
 h.context.navigator.onLine=true;h.respond('PUT',{revision:11});await h.context.DVIZH_SYNC.push();
 assert.equal(h.requests.at(-1).body.force,false,'reset must still participate in revision CAS');
 assert.ok(h.state().__sync.resetAt);assert.equal(h.state().tasks.length,0);
});
test('bootstrap GET cannot overwrite edits made before ready',async()=>{
 const h=await harness({beforeReady:c=>{const s=fixture();s.tasks[0].title='Bootstrap edit';c.localStorage.setItem('dvizh-state-v1',JSON.stringify(s));}});
 assert.equal(h.state().tasks[0].title,'Bootstrap edit');assert.equal(h.requests.at(-1).method,'PUT');
});
test('offline upgrade without stored base retains local edits on first successful pull',async()=>{
 const local=fixture();local.tasks[0].title='Offline edit';local.tasks[0]._syncUpdatedAt=T1;
 const h=await harness({local,meta:{revision:10},offline:true});const remote=fixture();remote.tasks.push({id:'remote-new',title:'Remote'});
 h.respond('GET',{state:remote,revision:11});await h.context.DVIZH_SYNC.pull();
 assert.equal(h.state().tasks[0].title,'Offline edit');assert.equal(h.state().tasks.length,2);
});
test('remote reset supersedes offline edits, and acknowledged command is not resurrected',async()=>{
 const base=fixture();base.jumpLab.webCommands=[{id:'ack',action:'old'}];
 const h=await harness({local:base,meta:{revision:10,baseState:base},offline:true});
 let local=h.state();local.tasks[0].title='Offline';local.jumpLab.webCommands.push({id:'new',action:'new'});h.write(local);
 const remote=JSON.parse(JSON.stringify(base));remote.jumpLab.webCommands=[];remote.jumpLab.commandResults=[{id:'ack',status:'ok'}];
 h.respond('GET',{state:remote,revision:11});await h.context.DVIZH_SYNC.pull();
 assert.deepEqual(h.state().jumpLab.webCommands.map(x=>x.id),['new']);
 const reset=fixture();reset.tasks=[];reset.__sync.resetAt=T1;reset.__sync.updatedAt=T1;
 h.respond('GET',{state:reset,revision:12});await h.context.DVIZH_SYNC.pull();assert.equal(h.state().tasks.length,0);
 assert.equal(h.state().jumpLab.webCommands,undefined);
});
test('tombstone in accepted state suppresses an older concurrent entity edit',async()=>{
 const h=await harness();const local=h.state();local.tasks[0].title='Local';h.write(local);
 const remote=fixture();remote.__sync.deletedTasks={'synthetic-task':T1};
 h.respond('GET',{state:remote,revision:11});await h.context.DVIZH_SYNC.pull();assert.equal(h.state().tasks.length,0);
});
test('projection slots reconcile by stable code when ids are absent',async()=>{
 const base=fixture();base.trainingHub={planSlots:[{code:'upper_a',startLocal:'19:00',durationMinutes:75}]};
 const h=await harness({local:base,meta:{revision:10,baseState:base},offline:true});const local=h.state();local.trainingHub.planSlots[0].startLocal='18:00';h.write(local);
 const remote=JSON.parse(JSON.stringify(base));remote.trainingHub.planSlots[0].durationMinutes=60;remote.trainingHub.planSlots.push({code:'lower_a',startLocal:'20:00'});
 h.respond('GET',{state:remote,revision:11});await h.context.DVIZH_SYNC.pull();
 assert.equal(h.state().trainingHub.planSlots.length,2);assert.equal(h.state().trainingHub.planSlots[0].startLocal,'18:00');assert.equal(h.state().trainingHub.planSlots[0].durationMinutes,60);
});
test('first upgrade without a base keeps authoritative remote projections and pending local commands',async()=>{
 const local=fixture();local.trainingHub={profile:{planEnabled:false},sessions:[],webCommands:[{id:'pending',action:'session_log'}]};
 const remote=fixture();remote.trainingHub={profile:{planEnabled:true},sessions:[{id:'remote',activity:'recovery'}],webCommands:[]};
 const h=await harness({local,remote,meta:{revision:9},upgrade:true});
 assert.equal(h.state().trainingHub.profile.planEnabled,true);assert.equal(h.state().trainingHub.sessions[0].id,'remote');assert.equal(h.state().trainingHub.webCommands[0].id,'pending');
});
