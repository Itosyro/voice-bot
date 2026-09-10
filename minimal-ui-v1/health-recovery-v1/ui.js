// Runs inside the deployed app closure: use its state, form ancestors and save path.
const healthDisplayed=new WeakMap();
const healthLabels={energy:'Энергия',mood:'Настроение',stress:'Стресс',soreness:'Болезненность мышц',wellbeing:'Общее самочувствие'};
const healthLevels={high:'Высокая',normal:'Обычная',low:'Низкая',insufficient_data:'Недостаточно данных'};
const healthStatus={taken:'Принято',skipped:'Пропущено',pending:'Ожидает'};
const healthEscape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const healthId=()=>crypto.randomUUID().replaceAll('-','');
function healthTimezone(){return $('#healthTimezone').value.trim();}
function healthDay(){return healthDomain.today(healthTimezone());}
function healthRead(form){
  const result={};
  for(const el of form.elements){if(!el.name||el.name==='weekday')continue;result[el.name]=el.type==='checkbox'?el.checked:el.value;}
  if(form.getAttribute('id')==='healthScheduleForm'){
    result.weekdays=[...form.querySelectorAll('[name=weekday]:checked')].map(el=>Number(el.value));
    result.slots=[...form.querySelectorAll('[data-slot-row]')].map(el=>({id:el.dataset.slotRow,time:el.querySelector('[data-slot-time]').value}));
  }
  return result;
}
function healthRemember(form){healthDisplayed.set(form,healthRead(form));rememberForm(form.getAttribute('id'));}
function healthFill(form,day){
  const kind=form.getAttribute('id')==='healthSleepForm'?'sleep':'checkins',row=state.healthRecovery?.[kind]?.[day]||{};
  for(const el of form.elements){if(!el.name)continue;el.value=el.name==='day'?day:(el.name==='durationMinutes'&&row.durationKind==='clock'?'':row[el.name]??'');}
  healthRemember(form);
}
function healthSlot(slot={id:healthId(),time:''}){
  const row=document.createElement('div');row.className='health-pair';row.dataset.slotRow=slot.id;
  row.innerHTML=`<label>Время <input type="time" data-slot-time required value="${healthEscape(slot.time)}"></label><button type="button" data-remove-slot>Убрать время</button>`;
  $('#healthSlots').append(row);
}
function healthScheduleEdit(id){
  const form=$('#healthScheduleForm'),row=state.healthRecovery?.schedules?.[id]||{id:healthId(),enabled:true,weekdays:[0,1,2,3,4,5,6],slots:[{id:healthId(),time:''}]};
  for(const el of form.elements){if(!el.name||el.name==='weekday')continue;if(el.type==='checkbox')el.checked=row[el.name];else el.value=row[el.name]??'';}
  for(const el of form.querySelectorAll('[name=weekday]'))el.checked=row.weekdays.includes(Number(el.value));
  $('#healthSlots').replaceChildren();row.slots.forEach(healthSlot);healthRemember(form);
}
function healthFactor(text){
  if(text.includes(' context ')){const [name,,freshness]=text.split(' ');return `${name==='training'?'Тренировки':'Jump'}: ${{missing:'нет готовности',undated:'дата готовности не указана',current:'готовность за сегодня',stale:'готовность за другой день'}[freshness]}`;}
  if(text==='missing sleep')return 'Сон не записан';if(text==='stale sleep')return 'Сон есть только за прошлые дни';
  if(text==='missing check-in')return 'Самочувствие не записано';if(text==='stale check-in')return 'Самочувствие есть только за прошлые дни';
  if(text.startsWith('missing '))return `Нет оценки: ${healthLabels[text.slice(8)]||text.slice(8)}`;
  for(const [key,label]of Object.entries(healthLabels))if(text.startsWith(key+' '))return label+text.slice(key.length);
  if(text.startsWith('sleep '))return 'Сон: '+text.split(' ')[1]+' мин. Менее 360 мин или качество 1–2 снижает оценку.';
  return 'Тренировки: исходная готовность 0–3 без пересчёта. Учитывай текущий контекст тренировок и Jump отдельно.';
}
function renderHealthToday(){
  const target=$('#healthToday');if(!target)return;
  const tz=state.healthRecovery?.timezone||Intl.DateTimeFormat().resolvedOptions().timeZone;
  let summary;try{summary=healthDomain.summary(state,healthDomain.today(tz));}catch{return;}
  target.innerHTML=`<span>Восстановление · ${healthEscape(healthLevels[summary.readiness.level])}${summary.checkin?' · '+healthDomain.ratings.filter(k=>summary.checkin[k]!==undefined).map(k=>healthLabels[k]+' '+healthEscape(summary.checkin[k])+'/5').join(' · '):''}</span> <button type="button" data-open-health>Отметить самочувствие</button>`;
}
function renderHealth(){
  const day=healthDay(),summary=healthDomain.summary(state,day),sleep=summary.sleep;
  $('#healthSummary').innerHTML=`<p>Сегодня · ${healthEscape(day)} · ${healthEscape(healthTimezone())}</p><p>Последний сон: ${sleep.last?healthEscape(sleep.last.day)+' · '+healthEscape(sleep.last.durationMinutes)+' мин':'Нет данных'}. Среднее за 7 дней: ${sleep.mean7Minutes===null?'Нет данных':Math.round(sleep.mean7Minutes)+' мин'} (${sleep.recordedDays} записанных дней).</p><details><summary>Готовность: ${healthLevels[summary.readiness.level]}</summary><p>Ориентир для самонаблюдения, не медицинская оценка. Низкая: сон &lt; 360 мин, качество ≤ 2, энергия/настроение/самочувствие ≤ 2 или стресс/болезненность ≥ 4. Высокая: ≥ 420 мин, энергия и самочувствие ≥ 4, без низких факторов. Иначе обычная. Без сегодняшнего сна и хотя бы одной оценки — недостаточно данных.</p><p>Эта оценка восстановления не отменяет исходные ограничения тренировок и Jump. Их сигналы: ${healthEscape(Object.entries(summary.readiness.context).map(([k,v])=>{const r=v.readiness?.result||v.readiness;return `${k==='training'?'Тренировки':'Jump'} — ${r?`статус ${r.status??'не указан'}, балл ${r.score??'не указан'}`:'нет данных'}`;}).join('; '))}</p><ul>${summary.readiness.factors.map(f=>`<li>${healthEscape(healthFactor(f))}</li>`).join('')}</ul><button type="button" data-nav="training">Тренировки и Jump · исходная готовность</button></details>`;
  $('#healthIntakes').innerHTML=summary.supplements.today.map(r=>`<div data-intake-row><p>${healthEscape(r.snapshot.time)} · ${healthEscape(r.snapshot.name)} · ${healthEscape(r.snapshot.dose)} · ${healthStatus[r.status]}</p>${['taken','skipped','pending'].map(status=>`<button type="button" data-mark-day="${healthEscape(day)}" data-mark-zone="${healthEscape(healthTimezone())}" data-mark-status="${status}" data-schedule="${healthEscape(r.scheduleId)}" data-slot="${healthEscape(r.slotId)}" aria-pressed="${r.status===status}">${healthStatus[status]}</button>`).join('')}</div>`).join('')||'<p>Нет включённых добавок на сегодня.</p>';
  $('#healthSchedules').innerHTML=Object.values(state.healthRecovery?.schedules||{}).map(s=>`<p>${healthEscape(s.name)} · ${healthEscape(s.dose)} · ${s.enabled?'Включено':'Отключено'} <button type="button" data-edit-schedule="${healthEscape(s.id)}">Изменить</button></p>`).join('')||'<p>Нет расписаний.</p>';
  const h=state.healthRecovery||{};
  $('#healthHistory').innerHTML='<h3>Сон</h3>'+Object.entries(h.sleep||{}).sort(([a],[b])=>b.localeCompare(a)).map(([d,r])=>`<div class="health-history-row">${healthEscape(d)} · ${healthEscape(r.durationMinutes)} мин · качество ${healthEscape(r.quality??'не указано')} · ${healthEscape(r.source)} · ${healthEscape(r.note)} <button type="button" data-edit-sleep="${healthEscape(d)}">Изменить сон</button></div>`).join('')+'<h3>Добавки</h3>'+summary.supplements.history.map(r=>`<p>${healthEscape(r.day)} ${healthEscape(r.snapshot.time)} · ${healthEscape(r.snapshot.name)} · ${healthEscape(r.snapshot.dose)} · ${healthStatus[r.status]}</p>`).join('')+'<h3>Самочувствие</h3>'+Object.entries(h.checkins||{}).sort(([a],[b])=>b.localeCompare(a)).map(([d,r])=>`<p>${healthEscape(d)} · ${healthDomain.ratings.filter(k=>r[k]!==undefined).map(k=>healthLabels[k]+' '+healthEscape(r[k])+'/5').join(' · ')} · ${healthEscape(r.note)} <button type="button" data-edit-checkin="${healthEscape(d)}">Изменить отметку</button></p>`).join('');
  renderHealthToday();
}
function healthOpen(){
  navigate('settings');$('#healthRecovery').hidden=false;
  try{renderHealth();healthFill($('#healthSleepForm'),healthDay());healthFill($('#healthCheckinForm'),healthDay());}catch(e){$('#healthError').textContent=e.message;}
  $('#healthRecovery').scrollIntoView({block:'start'});
}
function initHealth(){
  if(!$('#healthRecovery'))return;
  if(!canReconcile())return;
  $('#healthCapability').hidden=true;
  $('#healthOpen').disabled=false;
  document.querySelectorAll('[data-open-health]').forEach(el=>el.disabled=false);
  document.querySelectorAll('[data-health-capability]').forEach(el=>el.disabled=false);
  $('#healthTimezone').value=state.healthRecovery?.timezone||Intl.DateTimeFormat().resolvedOptions().timeZone;
  $('#healthRatings').innerHTML=healthDomain.ratings.map(k=>`<label>${healthLabels[k]} <select name="${k}"><option value="">Не указано</option>${[1,2,3,4,5].map(n=>`<option>${n}</option>`).join('')}</select></label>`).join('');
  $('#healthWeekdays').insertAdjacentHTML('beforeend',['Пн','Вт','Ср','Чт','Пт','Сб','Вс'].map((v,i)=>`<label><input type="checkbox" name="weekday" value="${i}" checked> ${v}</label>`).join(''));
  healthScheduleEdit();renderHealthToday();
  document.addEventListener('click',event=>{
    const el=event.target.closest('button');if(!el)return;
    if(el.closest('.health-more')&&(el.dataset.nav||el.hasAttribute('data-open-health')))el.closest('details').open=false;
    try{
      if(el.id==='healthOpen'||el.hasAttribute('data-open-health'))healthOpen();
      if(el.id==='healthNewSchedule')healthScheduleEdit();
      if(el.hasAttribute('data-edit-schedule'))healthScheduleEdit(el.dataset.editSchedule);
      if(el.hasAttribute('data-add-slot'))healthSlot();
      if(el.hasAttribute('data-remove-slot'))el.closest('[data-slot-row]').remove();
      for(const [attr,formid]of [['editSleep','healthSleepForm'],['editCheckin','healthCheckinForm']])if(el.dataset[attr]){const form=$('#'+formid);healthFill(form,el.dataset[attr]);form.closest('details').open=true;form.scrollIntoView({block:'start'});}
      if(el.dataset.markStatus){healthDomain.apply(state,'health_supplement_mark',{day:el.dataset.markDay,timezone:el.dataset.markZone,source:'manual',scheduleId:el.dataset.schedule,slotId:el.dataset.slot,status:el.dataset.markStatus});saveState();renderHealth();}
    }catch(e){$('#healthError').textContent=e.message;}
  });
  for(const [id,action]of [['healthSleepForm','health_sleep'],['healthCheckinForm','health_checkin'],['healthScheduleForm','health_supplement_schedule']]){
    const form=$('#'+id);
    form.addEventListener('change',event=>{if(event.target.name==='day')healthFill(form,event.target.value);});
    if(action==='health_sleep')form.addEventListener('input',event=>{if(['start','end'].includes(event.target.name))form.elements.durationMinutes.value='';if(event.target.name==='durationMinutes'){form.elements.start.value='';form.elements.end.value='';}});
    form.addEventListener('submit',event=>{
      event.preventDefault();$('#healthError').textContent='';
      try{
        if(!canReconcile())throw Error('Обнови Manual перед сохранением здоровья');
        const values=healthRead(form),before=healthDisplayed.get(form)||{},p={day:values.day||healthDay(),timezone:healthTimezone(),source:'manual'};
        const schedule=action==='health_supplement_schedule',existing=schedule?state.healthRecovery?.schedules?.[values.id]:state.healthRecovery?.[action==='health_sleep'?'sleep':'checkins']?.[values.day];
        for(const [k,v]of Object.entries(values)){
          if(k==='day'||k==='id')continue;
          if(existing&&JSON.stringify(v)===JSON.stringify(before[k]))continue;
          if(v===''&&k!=='note')continue;
          p[k]=['durationMinutes','quality',...healthDomain.ratings].includes(k)?Number(v):v;
        }
        if(schedule){p.id=values.id;if(existing&&p.slots)p.slots=window.DVIZH_SYNC.reconcile(before.slots,p.slots,existing.slots);}
        healthDomain.apply(state,action,p);saveState();
        if(schedule)healthScheduleEdit(values.id);else healthFill(form,values.day);
        renderHealth();showToast('Сохранено');
      }catch(e){$('#healthError').textContent=e.message;}
    });
  }
}
function healthProposalDetail(proposal){
  const p=proposal.payload||{},parts=[];
  const labels={day:'День',timezone:'Часовой пояс',name:'Название',dose:'Твоя доза',start:'Начало',end:'Конец',durationMinutes:'Минуты сна',quality:'Качество 1–5',...healthLabels,note:'Заметка'};
  for(const [key,label]of Object.entries(labels))if(key in p)parts.push(`${label}: ${p[key]}`);
  if(proposal.action==='health_supplement_schedule'){
    const before=state.healthRecovery?.schedules?.[p.id];
    const exists=before&&typeof before==='object';
    parts.push(`Расписание ID: ${p.id ?? 'не указан'} · ${exists?before.name:(p.name??'не найдено; уточни цель')}`);
    const days=v=>Array.isArray(v)?v.map(d=>['Пн','Вт','Ср','Чт','Пт','Сб','Вс'][d]).join(', '):'не указано';
    const slots=v=>Array.isArray(v)?v.map(s=>`${s.id}: ${s.time}`).join(', '):'не указано';
    for(const [key,label,format]of [['dose','Доза',v=>v??'не указано'],['slots','Слоты ID / время',slots],['weekdays','Дни',days],['enabled','Включено',v=>v===undefined?'не указано':String(v)],['timezone','Часовой пояс',v=>v??'не указано']]){
      const old=exists?before[key]:undefined,after=Object.hasOwn(p,key)?p[key]:old;
      parts.push(`${label}: ${format(old)} → ${format(after)}`);
    }
  }
  if(p.slots)parts.push('Времена: '+p.slots.map(s=>s.time).join(', '));
  if(p.weekdays)parts.push('Дни: '+p.weekdays.map(d=>['Пн','Вт','Ср','Чт','Пт','Сб','Вс'][d]).join(', '));
  if('enabled'in p)parts.push(p.enabled?'Включить':'Отключить');
  if(p.update)parts.push('Изменить существующее расписание');
  if(p.scheduleId){const schedule=state.healthRecovery?.schedules?.[p.scheduleId],slot=schedule?.slots?.find(s=>s.id===p.slotId);parts.push(schedule?`${schedule.name} · ${schedule.dose} · ${slot?.time||p.slotId}`:`Расписание ${p.scheduleId}, слот ${p.slotId}`);}
  if(p.status)parts.push(healthStatus[p.status]||p.status);
  return parts.join(' · ');
}
