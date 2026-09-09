const {test}=require('node:test');
const assert=require('node:assert/strict');
const {domHarness}=require('./dom-harness.cjs');
test('mandatory reverse cache: canonical height160 survives and quarantined age20 is retained',async()=>{
 const h=await domHarness(s=>{s.jumpLab.profile={age:19,heightCm:156};},{app:'baseline',sync:'release'});
 try {
  h.click('[data-nav="training"]');await h.advance(450);
  await h.pull(s=>{s.jumpLab.profile.heightCm=160;});
  h.w.document.querySelector('#jumpAge').value='20';
  h.w.document.querySelector('#jumpProfileForm').dispatchEvent(new h.w.Event('submit',{bubbles:true,cancelable:true}));
  await h.flush();await h.advance(450);
  assert.equal(h.remote().jumpLab.profile.heightCm,160,'server height160 must survive stale old-app save');
  assert.equal(h.state().jumpLab.profile.heightCm,160,'canonical storage must remain accepted server state');
  assert.equal(h.w.DVIZH_SYNC.pendingLocal.jumpLab.profile.age,20,'pending age20 must be retained separately');
  assert.equal(h.requests.filter(r=>r.method==='PUT').length,0);
  assert.deepEqual(h.errors,[]);
 } finally {h.dom.window.close();}
});
