const {test}=require('node:test');const assert=require('node:assert/strict');const {domHarness}=require('./dom-harness.cjs');
test('actual app/boot DOM: blurred task draft reconciles with live remote memory',async()=>{
 const h=await domHarness();try {
 const {w}=h;h.click('[data-nav="training"]');h.click('[data-action="edit-task"]');await h.advance(60);
 const title=w.document.querySelector('#taskTitle');title.value='Local draft';title.dispatchEvent(new w.Event('input',{bubbles:true}));title.blur();
 await h.pull(s=>{s.tasks[0].title='Remote title';s.tasks[0].micro='Remote micro';});
 assert.equal(title.value,'Local draft');assert.equal(w.document.querySelector('#taskMicro').value,'Base micro');
 assert.equal(w.document.querySelector('#view-training').classList.contains('is-active'),true);
 assert.equal(w.document.querySelector('#taskModal').hidden,false);
 assert.equal(w.DVIZH_MANUAL_STATE?.snapshot().tasks[0].micro,'Remote micro');
 w.document.querySelector('#taskForm').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
 assert.equal(h.state().tasks[0].title,'Local draft');assert.equal(h.state().tasks[0].micro,'Remote micro');assert.deepEqual(h.errors,[]);
 }finally{h.dom.window.close();}
});
test('Jump profile command rebases untouched fields as well as optimistic memory',async()=>{
 const h=await domHarness(s=>{s.jumpLab.profile={age:19,heightCm:156};});try{
 h.click('[data-nav="training"]');const {w}=h;w.document.querySelector('#jumpAge').value='20';
 await h.pull(s=>{s.jumpLab.profile.heightCm=160;});
 w.document.querySelector('#jumpProfileForm').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
 const s=h.state();assert.equal(s.jumpLab.webCommands.at(-1).profile.height_cm,160);
 assert.equal(s.jumpLab.webCommands.at(-1).profile.age,20);assert.equal(s.jumpLab.profile.heightCm,160);assert.equal(s.jumpLab.profile.age,20);
 assert.deepEqual(h.errors,[]);
 }finally{h.dom.window.close();}
});
test('reopened editor uses its newly displayed base for the next remote update',async()=>{
 const h=await domHarness();try{
 const {w}=h;h.click('[data-action="edit-task"]');await h.pull(s=>{s.tasks[0].micro='Remote one';});
 h.click('[data-action="edit-task"]'); // existing action repopulates the real form
 assert.equal(w.document.querySelector('#taskMicro').value,'Remote one');
 w.document.querySelector('#taskTitle').value='Edited after reopening';
 await h.pull(s=>{s.tasks[0].micro='Remote two';});
 w.document.querySelector('#taskForm').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
 assert.equal(h.state().tasks[0].micro,'Remote two');assert.equal(h.state().tasks[0].title,'Edited after reopening');
 }finally{h.dom.window.close();}
});
test('remote application preserves DOM identity, focus/selection, scroll, details and both live timers',async()=>{
 const h=await domHarness();try{
 const {w}=h;h.click('[data-nav="focus"]');h.click('[data-action="toggle-timer"]');h.click('[data-action="open-rescue"]');
 h.click('[data-nav="training"]');const view=w.document.querySelector('#view-training');view.dataset.minimalDetails='open';
 const field=w.document.querySelector('#taskTitle');field.value='draft';field.focus();
 if(field.type==='text')field.setSelectionRange(1,3);view.scrollTop=73;
 const selection=w.getSelection();const range=w.document.createRange();range.selectNodeContents(w.document.querySelector('#viewTitle'));selection.addRange(range);
 const selected=selection.toString();const rescue=w.document.querySelector('#rescueTimer');const before=Number(rescue.textContent);
 const focusBefore=w.document.querySelector('#timerDisplay')?.textContent;
 await h.pull(s=>{s.tasks[0].title='Timer-safe remote';s.__sync.updatedAt='2026-01-01T00:01:00Z';});
 assert.equal(w.document.activeElement,field);assert.equal(field.value,'draft');assert.equal(field.selectionStart,1);assert.equal(field.selectionEnd,3);assert.equal(selection.toString(),selected);assert.equal(view.scrollTop,73);
 assert.equal(view.dataset.minimalDetails,'open');assert.equal(w.document.querySelector('#rescueTimer'),rescue);assert.equal(w.document.querySelector('#rescueModal').hidden,false);
 await h.advance(2000);assert.equal(Number(rescue.textContent),before-2);
 assert.equal(view.classList.contains('is-active'),true);assert.deepEqual(h.errors,[]);
 assert.ok(focusBefore !== undefined,'timer display selector must exist');assert.notEqual(w.document.querySelector('#timerDisplay').textContent,focusBefore);
 }finally{h.dom.window.close();}
});
test('untouched rendered profile defaults cannot overwrite newly supplied remote fields',async()=>{
 const h=await domHarness(s=>{s.jumpLab.profile={age:19};});try{
 h.click('[data-nav="training"]');const {w}=h;assert.equal(w.document.querySelector('#jumpHeight').value,'156');w.document.querySelector('#jumpAge').value='20';
 await h.pull(s=>{s.jumpLab.profile.heightCm=160;});
 w.document.querySelector('#jumpProfileForm').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
 assert.equal(h.state().jumpLab.webCommands.at(-1).profile.height_cm,160);assert.equal(h.state().jumpLab.profile.heightCm,160);
 }finally{h.dom.window.close();}
});
test('intentional task navigation exposes accepted remote data without background DOM replacement',async()=>{
 const h=await domHarness();try{
 const list=h.w.document.querySelector('#taskList');const before=list.innerHTML;
 await h.pull(s=>{s.tasks[0].title='Remote visible after navigation';});assert.equal(list.innerHTML,before);
 h.click('[data-nav="tasks"]');assert.match(list.textContent,/Remote visible after navigation/);
 }finally{h.dom.window.close();}
});
test('blurred Training session draft survives remote projections and saves alongside remote sessions',async()=>{
 const h=await domHarness(s=>{s.trainingHub={profile:{planEnabled:false},sessions:[],planSlots:[],webCommands:[]};});try{
 const {w}=h;h.click('[data-nav="training"]');h.click('[data-training-action="open-session"]');
 const duration=w.document.querySelector('#trainingDuration');duration.focus();duration.value='45';duration.blur();
 await h.pull(s=>{s.trainingHub.sessions=[{id:'remote-session',activity:'recovery',durationMinutes:10,rpe:1}];s.trainingHub.metrics={load7d:10};});
 assert.equal(duration.value,'45');assert.equal(w.document.querySelector('#trainingSessionFormPanel').hidden,false);
 w.document.querySelector('#trainingSessionForm').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
 assert.equal(h.state().trainingHub.sessions.length,2);assert.equal(h.state().trainingHub.webCommands.at(-1).durationMinutes,45);
 assert.equal(h.state().trainingHub.metrics.load7d,10);assert.deepEqual(h.errors,[]);
 }finally{h.dom.window.close();}
});
test('repeated focused Jump submissions retain field-level DISPLAYED ancestors across partial renders',async()=>{
 const h=await domHarness(s=>{s.jumpLab.profile={age:19,heightCm:156};});try{
 const {w}=h;h.click('[data-nav="training"]');const form=w.document.querySelector('#jumpProfileForm'),height=w.document.querySelector('#jumpHeight');
 form.hidden=false;height.focus();assert.equal(w.document.activeElement,height);
 await h.pull(s=>{s.jumpLab.profile.heightCm=160;});
 form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();
 assert.equal(h.state().jumpLab.profile.heightCm,160);assert.equal(height.value,'156');
 assert.equal(h.state().jumpLab.webCommands.at(-1).profile.height_cm,160);
 form.hidden=false;await h.pull(s=>{s.jumpLab.profile.age=21;});
 form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();
 assert.equal(h.state().jumpLab.profile.heightCm,160);assert.equal(h.state().jumpLab.webCommands.at(-1).profile.height_cm,160);
 assert.equal(h.state().jumpLab.profile.age,21);assert.equal(w.document.querySelector('#jumpAge').value,'21');
 // Partial render refreshed age but retained focused height. The next age update
 // must compare against the newly displayed 21, not the original 19.
 form.hidden=false;await h.pull(s=>{s.jumpLab.profile.age=22;});
 form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();
 assert.equal(h.state().jumpLab.profile.age,22);assert.equal(h.state().jumpLab.webCommands.at(-1).profile.age,22);assert.equal(h.state().jumpLab.profile.heightCm,160);
 assert.deepEqual(h.errors,[]);
 }finally{h.dom.window.close();}
});
test('Social settings full render refreshes displayed ancestors even while focused',async()=>{
 const h=await domHarness(s=>{s.socialHub={profile:{weeklyGoal:2,courageLevel:1,commentWindow1:'13:00',commentWindow2:'20:00'},content:[],webCommands:[]};});try{
 const {w}=h;h.click('[data-nav="social"]');const form=w.document.querySelector('#socialSettingsForm');w.document.querySelector('#socialWeeklyGoal').focus();
 for(const goal of [3,4,5]){
 await h.pull(s=>{s.socialHub.profile.weeklyGoal=goal;});form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();
 assert.equal(h.state().socialHub.profile.weeklyGoal,goal);assert.equal(h.state().socialHub.webCommands.at(-1).profile.weeklyGoal,goal);assert.equal(w.document.querySelector('#socialWeeklyGoal').value,String(goal));
 }assert.deepEqual(h.errors,[]);
 }finally{h.dom.window.close();}
});
test('Week repeated submissions without refill preserve remote duration in state and commands',async()=>{
 const h=await domHarness(s=>{s.weeklySchedule={items:[{id:'week-one',title:'Practice',kind:'other',recurrence:'once',dateLocal:'2026-01-02',startLocal:'18:00',durationMinutes:60,reminderMinutes:30}],webCommands:[]};});try{
 const {w}=h;h.click('[data-nav="week"]');
 const button=w.document.createElement('button');button.dataset.weekRuleEdit='week-one';w.document.body.append(button);button.click();
 const form=w.document.querySelector('#weekEditorForm');
 assert.equal(w.document.querySelector('#weekEditorItemId').value,'week-one');
 for(const duration of [70,80]){
 w.document.querySelector('#weekEditorPanel').hidden=false;await h.pull(s=>{s.weeklySchedule.items[0].durationMinutes=duration;});
 form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();
 assert.equal(h.state().weeklySchedule.items[0].durationMinutes,duration);assert.equal(h.state().weeklySchedule.webCommands.at(-1).durationMinutes,duration);
 }assert.deepEqual(h.errors,[]);
 }finally{h.dom.window.close();}
});
test('Social content repeated submissions without refill preserve remote notes in state and command',async()=>{
 const h=await domHarness(s=>{s.socialHub={profile:{},content:[{id:1,title:'Clip',platform:'tiktok',contentFormat:'short_video',stage:'idea',notes:'Base notes'}],webCommands:[]};});try{
 const {w}=h;h.click('[data-nav="social"]');h.click('[data-social-action="edit-content"][data-content-id="1"]');
 const form=w.document.querySelector('#socialContentForm');
 for(const notes of ['Remote one','Remote two']){
 w.document.querySelector('#socialContentFormPanel').hidden=false;await h.pull(s=>{s.socialHub.content[0].notes=notes;});
 form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();
 assert.equal(h.state().socialHub.content[0].notes,notes);assert.equal(h.state().socialHub.webCommands.at(-1).content.notes,notes);
 }assert.deepEqual(h.errors,[]);
 }finally{h.dom.window.close();}
});
for (const revert of [false,true]) test(`consumed focused Jump ancestor: edit-submit-remote-${revert?'intentional reversion':'unedited resubmit'}`,async()=>{
 const h=await domHarness(s=>{s.jumpLab.profile={age:19,heightCm:156};});try{
 const {w}=h;h.click('[data-nav="training"]');
 const form=w.document.querySelector('#jumpProfileForm'),height=w.document.querySelector('#jumpHeight');
 form.hidden=false;height.focus();assert.equal(w.document.activeElement,height);assert.equal(height.value,'156');
 height.value='157';height.dispatchEvent(new w.Event('input',{bubbles:true}));
 const submit=async()=>{form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();};
 await submit();assert.equal(height.value,'157');
 assert.equal(h.state().jumpLab.profile.heightCm,157);assert.equal(h.state().jumpLab.webCommands.at(-1).profile.height_cm,157);
 await h.advance(450); // Acknowledge the submitted edit before the next remote revision.
 form.hidden=false;await h.pull(s=>{s.jumpLab.profile.heightCm=160;});
 assert.equal(w.DVIZH_MANUAL_STATE.snapshot().jumpLab.profile.heightCm,160);assert.equal(height.value,'157');
 assert.equal(w.document.activeElement,height);
 if(revert){height.value='156';height.dispatchEvent(new w.Event('input',{bubbles:true}));}
 await submit();
 assert.deepEqual({state:h.state().jumpLab.profile.heightCm,command:h.state().jumpLab.webCommands.at(-1).profile.height_cm},
 {state:revert?156:160,command:revert?156:160});
 assert.deepEqual(h.errors,[]);
 }finally{h.dom.window.close();}
});
