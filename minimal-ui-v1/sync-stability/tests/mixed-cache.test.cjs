const {test}=require('node:test');
const assert=require('node:assert/strict');
const {domHarness}=require('./dom-harness.cjs');

for(const app of ['baseline','release']) for(const sync of ['baseline','release']) {
 test(`cache matrix: ${app} app + ${sync} sync + pinned boot saves real forms`,async()=>{
  const h=await domHarness(s=>{
   s.jumpLab.profile={age:19,heightCm:156};
   s.socialHub={profile:{weeklyGoal:2,courageLevel:1,commentWindow1:'13:00',commentWindow2:'20:00'},content:[],webCommands:[]};
  },{app,sync});
  try {
   const {w}=h, patchedStorage=w.Storage.prototype.setItem;
   const submit=async id=>{w.document.querySelector(id).dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();assert.deepEqual(h.errors,[]);};
   h.click('[data-nav="training"]');w.document.querySelector('#jumpAge').value='20';
   await submit('#jumpProfileForm');
   const saved=()=>app==='baseline'&&sync==='release'?w.DVIZH_SYNC.pendingLocal:h.state();
   assert.equal(saved().jumpLab.profile.age,20);
   assert.equal(saved().jumpLab.webCommands.at(-1).profile.age,20);
   h.click('[data-nav="social"]');w.document.querySelector('#socialWeeklyGoal').value='4';
   await submit('#socialSettingsForm');
   assert.equal(saved().socialHub.profile.weeklyGoal,4);
   assert.equal(saved().socialHub.webCommands.at(-1).profile.weeklyGoal,4);
   h.click('[data-nav="tasks"]');h.click('[data-action="edit-task"]');
   w.document.querySelector('#taskTitle').value='Saved cache matrix draft';
   await submit('#taskForm');assert.equal(saved().tasks[0].title,'Saved cache matrix draft');
   await h.advance(450);
   if(app==='baseline'&&sync==='release') {
    assert.equal(h.requests.filter(r=>r.method==='PUT').length,0);
    assert.equal(saved().tasks[0].title,'Saved cache matrix draft');
    return;
   }
   assert.equal(h.remote().jumpLab.profile.age,20);
   assert.equal(h.remote().socialHub.profile.weeklyGoal,4);
   assert.equal(h.remote().tasks[0].title,'Saved cache matrix draft');
   assert.equal(w.Storage.prototype.setItem,patchedStorage,'app must not install another sync/storage patch');
   assert.equal(typeof w.DVIZH_SYNC.reconcile,sync==='release'?'function':'undefined');
  } finally {h.dom.window.close();}
 });
}

for(const app of ['baseline','release']) for(const sync of ['baseline','release']) {
 test(`cache matrix remote acceptance: ${app} app + ${sync} sync exposes legacy reload/memory limits`,async()=>{
  const h=await domHarness(s=>{s.jumpLab.profile={age:19,heightCm:156};},{app,sync});
  try {
   h.click('[data-nav="training"]');await h.advance(450); // Acknowledge app initialization writes before remote projection.
   await h.pull(s=>{s.jumpLab.profile.heightCm=160;});await h.advance(120);
   assert.equal(h.state().jumpLab.profile.heightCm,160);
   assert.equal(h.navigationErrors.length,sync==='baseline'?1:0,'legacy sync still attempts its original reload (jsdom cannot navigate)');
   assert.equal(h.w.document.querySelector('#jumpHeight').value,'156');
   if(app==='release') assert.equal(h.w.DVIZH_MANUAL_STATE.snapshot().jumpLab.profile.heightCm,sync==='release'?160:156);
   else assert.equal(h.w.DVIZH_MANUAL_STATE,undefined,'old app has no private-memory acceptance hook');
   assert.deepEqual(h.errors,[]);
  } finally {h.dom.window.close();}
 });
}
