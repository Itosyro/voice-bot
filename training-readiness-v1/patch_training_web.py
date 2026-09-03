#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

MARKER_HTML = '<!-- DVIZH_TRAINING_VIEW_V1 -->'
MARKER_JS = 'const DVIZH_TRAINING_WEB_V1 = true;'
MARKER_CSS = '/* DVIZH_TRAINING_WEB_V1 */'

TRAINING_SECTION = r'''      <!-- DVIZH_TRAINING_VIEW_V1 -->
      <section class="view" id="view-training" data-view="training">
        <div class="section-heading page-heading training-heading">
          <div>
            <p class="eyebrow">ТРЕНИРОВКИ · ВОССТАНОВЛЕНИЕ · ВОЛЕЙБОЛ</p>
            <h2>Не угадывай, сколько сегодня вывозишь</h2>
          </div>
          <span class="soft-label" id="trainingSyncStatus">синхронизация</span>
        </div>

        <div class="training-layout">
          <article class="panel training-readiness-card" id="trainingReadinessCard">
            <div class="training-card-head">
              <div><p class="eyebrow">ГОТОВНОСТЬ СЕГОДНЯ</p><h3 id="trainingReadinessTitle">Ещё не проверена</h3></div>
              <strong class="training-score" id="trainingReadinessScore">—</strong>
            </div>
            <p id="trainingStrengthAdvice">Одна минута на сон, энергию, боль и забитость — затем ДВИЖ даст предел нагрузки.</p>
            <p id="trainingVolleyballAdvice"></p>
            <div id="trainingReasons" class="training-reasons"></div>
            <div class="training-actions">
              <button class="primary" type="button" data-training-action="open-readiness">🧠 Пройти готовность</button>
              <button class="ghost" type="button" data-training-action="open-session">📝 Записать тренировку</button>
            </div>
          </article>

          <article class="panel training-load-card">
            <p class="eyebrow">НАГРУЗКА</p>
            <div class="training-metrics">
              <div><b id="trainingLoad7d">0</b><span>AU за 7 дней</span></div>
              <div><b id="trainingBaseline">—</b><span>среднее/нед</span></div>
              <div><b id="trainingLower36">0</b><span>ноги за 36 ч</span></div>
            </div>
            <small>AU = минуты × RPE. Это простой ориентир нагрузки, а не диагноз и не медицинский допуск.</small>
          </article>
        </div>

        <section class="panel training-form-panel" id="trainingReadinessFormPanel" hidden>
          <form id="trainingReadinessForm">
            <div class="training-form-head"><div><p class="eyebrow">МИНУТНЫЙ ЧЕК</p><h3>Что реально с телом сегодня</h3></div><button type="button" class="ghost small" data-training-action="close-readiness">Закрыть</button></div>
            <div class="training-form-grid">
              <label><span>Сон, часов</span><input id="trainingSleepHours" type="number" min="0" max="16" step="0.5" value="7.5" required></label>
              <label><span>Качество сна</span><select id="trainingSleepQuality"><option value="0">провал</option><option value="1">плохо</option><option value="2" selected>нормально</option><option value="3">хорошо</option></select></label>
              <label><span>Энергия</span><select id="trainingEnergy"><option value="0">0 · лежу</option><option value="1">1 · мало</option><option value="2" selected>2 · норм</option><option value="3">3 · много</option></select></label>
              <label><span>Забитость мышц</span><select id="trainingSoreness"><option value="0" selected>0 · свежий</option><option value="1">1 · слегка</option><option value="2">2 · заметно</option><option value="3">3 · сильно</option></select></label>
              <label><span>Боль, меняющая движение</span><select id="trainingPain"><option value="0" selected>0 · нет</option><option value="1">1 · слабая</option><option value="2">2 · заметная</option><option value="3">3 · сильная</option></select></label>
              <label><span>Стресс</span><select id="trainingStress"><option value="0">0 · тихо</option><option value="1">1 · немного</option><option value="2" selected>2 · высоко</option><option value="3">3 · шторм</option></select></label>
              <label class="training-wide"><span>Самочувствие</span><select id="trainingIllness"><option value="none" selected>здоров</option><option value="mild">лёгкая простуда без температуры</option><option value="systemic">температура / ломота / выраженная слабость</option></select></label>
              <label class="training-danger training-wide"><input id="trainingRedFlag" type="checkbox"><span>Есть боль/давление в груди, обморок или необычная сильная одышка</span></label>
            </div>
            <div class="training-form-actions"><button type="submit" class="primary">Рассчитать готовность</button><small>При опасном симптоме приложение не разрешает тренировку и советует медицинскую помощь.</small></div>
          </form>
        </section>

        <section class="panel training-form-panel" id="trainingSessionFormPanel" hidden>
          <form id="trainingSessionForm">
            <div class="training-form-head"><div><p class="eyebrow">ЖУРНАЛ НАГРУЗКИ</p><h3>Записать тренировку</h3></div><button type="button" class="ghost small" data-training-action="close-session">Закрыть</button></div>
            <div class="training-form-grid">
              <label><span>Тип</span><select id="trainingActivity"><option value="upper_a">Верх A</option><option value="lower_a">Низ A</option><option value="upper_b">Верх B</option><option value="lower_b">Низ B</option><option value="volleyball">🏐 Волейбол</option><option value="recovery">Восстановление</option><option value="other">Другое</option></select></label>
              <label><span>Минуты</span><input id="trainingDuration" type="number" min="1" max="720" step="5" value="75" required></label>
              <label><span>RPE 0–10</span><input id="trainingRpe" type="number" min="0" max="10" step="1" value="6" required></label>
              <label><span>Результат</span><select id="trainingResult"><option value="done" selected>сделал</option><option value="partial">часть</option><option value="skipped">пропустил</option></select></label>
              <label><span>Боль после 0–3</span><select id="trainingPainAfter"><option value="0" selected>0 · нет</option><option value="1">1 · слабая</option><option value="2">2 · заметная</option><option value="3">3 · сильная</option></select></label>
              <label><span>Прыжки, примерно</span><input id="trainingJumps" type="number" min="0" max="2000" step="5" placeholder="только для волейбола"></label>
            </div>
            <div class="training-form-actions"><button type="submit" class="primary">Сохранить нагрузку</button><small>После записи выполненный спортивный блок отмечается и в недельном расписании.</small></div>
          </form>
        </section>

        <div class="training-layout training-lower-grid">
          <article class="panel">
            <div class="training-card-head"><div><p class="eyebrow">4× UPPER / LOWER</p><h3>План недели</h3></div><button type="button" class="ghost small" id="trainingPlanButton" data-training-action="enable-plan">Включить</button></div>
            <div id="trainingPlanSlots" class="training-plan-list"></div>
            <small>Базово: ПН Верх A, ВТ Низ A, ЧТ Верх B, СБ Низ B. Дни и время меняются в разделе «Неделя».</small>
          </article>
          <article class="panel">
            <p class="eyebrow">БЛИЖАЙШИЕ СПОРТИВНЫЕ БЛОКИ</p>
            <div id="trainingUpcoming" class="training-upcoming-list"></div>
          </article>
        </div>

        <article class="panel training-history-panel">
          <div class="training-card-head"><div><p class="eyebrow">ИСТОРИЯ</p><h3>Последние тренировки</h3></div><button type="button" class="ghost small" data-training-action="open-session">＋ Записать</button></div>
          <div id="trainingHistory" class="training-history"></div>
        </article>
      </section>
'''

JS_TRAINING = r'''
  const DVIZH_TRAINING_WEB_V1 = true;
  const TRAINING_DAY_NAMES = ['ПН','ВТ','СР','ЧТ','ПТ','СБ','ВС'];
  const TRAINING_ACTIVITY_NAMES = {upper_a:'Верх A',lower_a:'Низ A',upper_b:'Верх B',lower_b:'Низ B',volleyball:'Волейбол',recovery:'Восстановление',other:'Другая'};

  function trainingHub() {
    if (!state.trainingHub || typeof state.trainingHub !== 'object') {
      state.trainingHub = {version:1,profile:{planEnabled:false},planSlots:[],sessions:[],upcoming:[],metrics:{load7d:0,baselineWeeklyLoad:null,lowerLoad36h:0},readiness:null,webCommands:[],commandResults:[]};
    }
    if (!Array.isArray(state.trainingHub.webCommands)) state.trainingHub.webCommands = [];
    if (!Array.isArray(state.trainingHub.planSlots)) state.trainingHub.planSlots = [];
    if (!Array.isArray(state.trainingHub.sessions)) state.trainingHub.sessions = [];
    if (!Array.isArray(state.trainingHub.upcoming)) state.trainingHub.upcoming = [];
    return state.trainingHub;
  }

  function trainingCommandId() { return `web-training-${Date.now()}-${Math.random().toString(36).slice(2,9)}`; }
  function trainingEnqueue(action, payload={}) {
    const hub=trainingHub();
    const command={id:trainingCommandId(),action,...payload,createdAt:nowIso()};
    hub.webCommands=[...hub.webCommands.slice(-19),command];
    hub.webUpdatedAt=nowIso();
    saveState();
    return command;
  }

  function trainingClientReadiness(input) {
    let score=100; const reasons=[]; let stop=false; let urgent=false;
    const sleep=Number(input.sleepHours||0), sq=Number(input.sleepQuality||0), energy=Number(input.energy||0), sore=Number(input.soreness||0), pain=Number(input.pain||0), stress=Number(input.stress||0);
    if (input.redFlag) { stop=true; urgent=true; reasons.push('Есть опасный симптом: тренировку не начинать.'); }
    if (input.illness==='systemic') { stop=true; reasons.push('Температура, ломота или выраженная слабость.'); }
    else if (input.illness==='mild') { score-=12; reasons.push('Лёгкая простуда: только лёгкая нагрузка.'); }
    if (pain>=3) { stop=true; reasons.push('Сильная или ограничивающая движение боль.'); } else if (pain===2) { score-=24; reasons.push('Заметная боль.'); } else if (pain===1) score-=8;
    if (sleep<5) { score-=30; reasons.push('Сна меньше 5 часов.'); } else if (sleep<6) { score-=20; reasons.push('Сна меньше 6 часов.'); } else if (sleep<7) { score-=10; reasons.push('Сна меньше 7 часов.'); }
    score-=(3-sq)*6; score-=({0:32,1:20,2:7,3:0}[energy]||0); score-=({0:0,1:5,2:15,3:27}[sore]||0); score-=({0:0,1:3,2:9,3:16}[stress]||0);
    if (energy<=1) reasons.push('Энергии мало.'); if (sore>=2) reasons.push('Мышцы заметно не восстановились.'); if (stress>=2) reasons.push('Высокая психическая нагрузка.');
    const context=trainingHub().todayContext||{}, metrics=trainingHub().metrics||{};
    if (context.volleyball_today && context.lower_today) { score-=14; reasons.push('Волейбол и низ попали на один день.'); }
    if (context.volleyball_today && Number(metrics.lowerLoad36h||0)>=450) { score-=22; reasons.push('Высокая нагрузка на ноги за 36 часов.'); }
    else if (context.volleyball_today && Number(metrics.lowerLoad36h||0)>=250) { score-=12; reasons.push('Ноги уже нагружались за 36 часов.'); }
    score=Math.max(0,Math.min(100,Math.round(score)));
    let status,label,strength_text,volleyball_text,rpe_cap,volume_factor;
    if (stop||score<45) { status='red';label='Красный день';strength_text='Без тяжёлой силовой. Отдых или очень лёгкое восстановление без боли.';volleyball_text='Полноценный волейбол и прыжковую работу сегодня пропусти.';rpe_cap=3;volume_factor=0; }
    else if (score<75) { status='yellow';label='Жёлтый день';strength_text='Убери 30–50% объёма, без отказа и максимумов.';volleyball_text='Техника/приём/подача или короткая игра; сократи прыжки.';rpe_cap=6;volume_factor=.6; }
    else { status='green';label='Зелёный день';strength_text='Можно плановую силовую, оставляя запас и не работая через боль.';volleyball_text='Можно играть по плану, контролируя самочувствие.';rpe_cap=8;volume_factor=1; }
    if (!reasons.length) reasons.push('Сон, энергия, боль и недавняя нагрузка выглядят нормально.');
    return {score,status,label,strength_text,volleyball_text,rpe_cap,volume_factor,reasons:reasons.slice(0,8),urgent};
  }

  function renderTraining() {
    const hub=trainingHub(); const readiness=hub.readiness?.result||hub.optimisticReadiness||null;
    const card=$('#trainingReadinessCard'), title=$('#trainingReadinessTitle'), score=$('#trainingReadinessScore');
    if (card) card.dataset.status=readiness?.status||'unknown';
    if (title) title.textContent=readiness?.label||'Ещё не проверена';
    if (score) score.textContent=readiness?`${Number(readiness.score||0)}/100`:'—';
    const strength=$('#trainingStrengthAdvice'); if (strength) strength.textContent=readiness?`Силовая: ${readiness.strength_text||'—'}`:'Одна минута на сон, энергию, боль и забитость — затем ДВИЖ даст предел нагрузки.';
    const volley=$('#trainingVolleyballAdvice'); if (volley) volley.textContent=readiness?`Волейбол: ${readiness.volleyball_text||'—'}`:'';
    const reasons=$('#trainingReasons'); if (reasons) reasons.innerHTML=readiness?`<b>Предел: RPE ${Number(readiness.rpe_cap||0)}/10</b>${(readiness.reasons||[]).map(x=>`<span>• ${escapeHtml(x)}</span>`).join('')}`:'';
    const metrics=hub.metrics||{}; if ($('#trainingLoad7d')) $('#trainingLoad7d').textContent=String(metrics.load7d||0); if ($('#trainingBaseline')) $('#trainingBaseline').textContent=metrics.baselineWeeklyLoad==null?'—':String(metrics.baselineWeeklyLoad); if ($('#trainingLower36')) $('#trainingLower36').textContent=String(metrics.lowerLoad36h||0);
    const planEnabled=Boolean(hub.profile?.planEnabled); const planButton=$('#trainingPlanButton'); if (planButton) { planButton.textContent=planEnabled?'Пауза':'Включить'; planButton.dataset.trainingAction=planEnabled?'disable-plan':'enable-plan'; }
    const slots=$('#trainingPlanSlots'); if (slots) slots.innerHTML=(hub.planSlots||[]).length?(hub.planSlots||[]).map(slot=>`<div class="training-plan-row"><b>${escapeHtml(TRAINING_DAY_NAMES[Number(slot.weekday||0)]||'—')} ${escapeHtml(slot.startLocal||'')}</b><span>${escapeHtml(slot.title||slot.code)} · ${Number(slot.durationMinutes||0)} мин</span></div>`).join(''):'<div class="training-empty">План ещё не включён.</div>';
    const upcoming=$('#trainingUpcoming'); if (upcoming) upcoming.innerHTML=(hub.upcoming||[]).filter(x=>x.status==='pending').slice(0,8).map(x=>`<div class="training-upcoming-row"><b>${escapeHtml(x.dueDate||'')} · ${escapeHtml(x.title||'')}</b><span>${x.kind==='volleyball'?'🏐':'🏋️'} ${escapeHtml(x.code||'')}</span></div>`).join('')||'<div class="training-empty">На ближайшие дни спортивных блоков нет.</div>';
    const history=$('#trainingHistory'); if (history) history.innerHTML=(hub.sessions||[]).slice(0,12).map(x=>`<div class="training-history-row"><div><b>${escapeHtml(x.activityLabel||TRAINING_ACTIVITY_NAMES[x.activity]||x.activity)}</b><span>${escapeHtml(x.date||'')} · ${Number(x.durationMinutes||0)} мин · RPE ${Number(x.rpe||0)}</span></div><strong>${Number(x.load||0)} AU</strong></div>`).join('')||'<div class="training-empty">Пока нет записанных тренировок.</div>';
    const sync=$('#trainingSyncStatus'); if (sync) { const pending=(hub.webCommands||[]).length; sync.textContent=pending?`сохраняю: ${pending}`:(hub.syncedAt?'синхронизировано':'ждём синхронизацию'); }
  }

  function trainingOpen(id, open=true) { const el=$(id); if (el) { el.hidden=!open; if (open) el.scrollIntoView({behavior:'smooth',block:'nearest'}); } }
  function trainingDefaultPlan() { return [{code:'upper_a',title:'Силовая · Верх A',weekday:0,startLocal:'19:00',durationMinutes:75},{code:'lower_a',title:'Силовая · Низ A',weekday:1,startLocal:'19:00',durationMinutes:75},{code:'upper_b',title:'Силовая · Верх B',weekday:3,startLocal:'19:00',durationMinutes:75},{code:'lower_b',title:'Силовая · Низ B',weekday:5,startLocal:'14:00',durationMinutes:75}]; }

  document.addEventListener('click', event => {
    const button=event.target.closest('[data-training-action]'); if (!button) return;
    const action=button.dataset.trainingAction;
    if (action==='open-readiness') trainingOpen('#trainingReadinessFormPanel',true);
    else if (action==='close-readiness') trainingOpen('#trainingReadinessFormPanel',false);
    else if (action==='open-session') trainingOpen('#trainingSessionFormPanel',true);
    else if (action==='close-session') trainingOpen('#trainingSessionFormPanel',false);
    else if (action==='enable-plan') { const hub=trainingHub(); trainingEnqueue('plan_enable'); hub.profile={...(hub.profile||{}),planEnabled:true}; if (!(hub.planSlots||[]).length) hub.planSlots=trainingDefaultPlan(); saveState(); renderTraining(); showToast('План 4× включается. Дни и время можно менять в «Неделе».'); }
    else if (action==='disable-plan') { const hub=trainingHub(); trainingEnqueue('plan_disable'); hub.profile={...(hub.profile||{}),planEnabled:false}; saveState(); renderTraining(); showToast('План поставлен на паузу.'); }
  });

  document.addEventListener('submit', event => {
    if (event.target?.id==='trainingReadinessForm') {
      event.preventDefault(); const payload={sleepHours:Number($('#trainingSleepHours').value),sleepQuality:Number($('#trainingSleepQuality').value),energy:Number($('#trainingEnergy').value),soreness:Number($('#trainingSoreness').value),pain:Number($('#trainingPain').value),stress:Number($('#trainingStress').value),illness:$('#trainingIllness').value,redFlag:Boolean($('#trainingRedFlag').checked)};
      if (!Number.isFinite(payload.sleepHours)||payload.sleepHours<0||payload.sleepHours>16) return showToast('Проверь часы сна.');
      const result=trainingClientReadiness(payload); const hub=trainingHub(); trainingEnqueue('readiness_save',payload); hub.optimisticReadiness=result; hub.readiness={localDate:localDateKey(new Date()),result,updatedAt:nowIso(),source:'web-pending'}; saveState(); trainingOpen('#trainingReadinessFormPanel',false); renderTraining(); showToast(result.status==='red'?'Сегодня не давим нагрузку.':'Готовность рассчитана.');
    }
    if (event.target?.id==='trainingSessionForm') {
      event.preventDefault(); const activity=$('#trainingActivity').value,durationMinutes=Number($('#trainingDuration').value),rpe=Number($('#trainingRpe').value),result=$('#trainingResult').value,painAfter=Number($('#trainingPainAfter').value),jumps=$('#trainingJumps').value===''?null:Number($('#trainingJumps').value);
      if (!Number.isFinite(durationMinutes)||durationMinutes<1||durationMinutes>720||!Number.isFinite(rpe)||rpe<0||rpe>10) return showToast('Проверь минуты и RPE.');
      const command=trainingEnqueue('session_log',{activity,durationMinutes,rpe,result,painAfter,jumps}); const hub=trainingHub(); hub.sessions=[{id:`web-temp-${command.id}`,activity,activityLabel:TRAINING_ACTIVITY_NAMES[activity]||activity,date:localDateKey(new Date()),durationMinutes,rpe,load:result==='skipped'?0:durationMinutes*rpe,result,painAfter,jumps,createdAt:nowIso(),source:'web-pending'},...(hub.sessions||[])]; saveState(); trainingOpen('#trainingSessionFormPanel',false); renderTraining(); showToast('Тренировка записывается.');
    }
  });
'''

CSS_TRAINING = r'''

/* DVIZH_TRAINING_WEB_V1 */
.training-heading { align-items: flex-end; }
.training-layout { display:grid; grid-template-columns:minmax(0,1.45fr) minmax(260px,.55fr); gap:14px; margin-bottom:14px; }
.training-readiness-card { border-color:rgba(255,255,255,.12); }
.training-readiness-card[data-status="green"] { border-color:rgba(180,255,60,.48); box-shadow:inset 0 0 0 1px rgba(180,255,60,.08); }
.training-readiness-card[data-status="yellow"] { border-color:rgba(255,205,80,.48); }
.training-readiness-card[data-status="red"] { border-color:rgba(255,90,90,.58); }
.training-card-head,.training-form-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.training-card-head h3,.training-form-head h3 { margin:4px 0 0; }
.training-score { font-size:clamp(22px,3vw,38px); color:var(--lime); white-space:nowrap; }
.training-readiness-card[data-status="yellow"] .training-score { color:#ffd05c; }
.training-readiness-card[data-status="red"] .training-score { color:#ff7272; }
.training-reasons { display:grid; gap:5px; color:var(--muted); font-size:11px; margin:12px 0; }
.training-reasons b { color:var(--text); }
.training-actions,.training-form-actions { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:14px; }
.training-metrics { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin:12px 0; }
.training-metrics div { border:1px solid var(--line); border-radius:12px; padding:10px; display:grid; gap:2px; }
.training-metrics b { font-size:20px; color:var(--lime); }
.training-metrics span,.training-load-card small,.training-form-actions small { color:var(--muted); font-size:9px; line-height:1.4; }
.training-form-panel { margin-bottom:14px; }
.training-form-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-top:16px; }
.training-form-grid label { display:grid; gap:6px; }
.training-form-grid label>span { color:var(--muted); font-size:10px; font-weight:800; }
.training-form-grid input,.training-form-grid select { width:100%; border:1px solid var(--line); background:var(--panel-2); color:var(--text); border-radius:10px; padding:10px; font:inherit; }
.training-form-grid .training-wide { grid-column:span 2; }
.training-form-grid .training-danger { display:flex; align-items:center; border:1px solid rgba(255,90,90,.35); border-radius:10px; padding:10px; }
.training-form-grid .training-danger input { width:auto; }
.training-lower-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
.training-plan-list,.training-upcoming-list,.training-history { display:grid; gap:8px; margin:12px 0; }
.training-plan-row,.training-upcoming-row,.training-history-row { display:flex; justify-content:space-between; gap:12px; align-items:center; padding:10px; border:1px solid var(--line); border-radius:11px; background:rgba(255,255,255,.02); }
.training-plan-row b { color:var(--lime); min-width:84px; }
.training-plan-row span,.training-upcoming-row span,.training-history-row span { color:var(--muted); font-size:10px; }
.training-upcoming-row,.training-history-row { align-items:flex-start; }
.training-history-row div { display:grid; gap:3px; }
.training-history-row strong { color:var(--lime); white-space:nowrap; }
.training-empty { color:var(--faint); border:1px dashed var(--line); border-radius:10px; padding:12px; font-size:10px; }
@media (max-width:900px) { .training-layout,.training-lower-grid { grid-template-columns:1fr; } .training-form-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .mobile-nav { grid-template-columns:repeat(7,1fr)!important; } .mobile-nav button small { font-size:7px; } }
@media (max-width:560px) { .training-form-grid { grid-template-columns:1fr; } .training-form-grid .training-wide { grid-column:auto; } .training-metrics { grid-template-columns:repeat(3,minmax(0,1fr)); } .training-metrics b { font-size:16px; } .training-plan-row { align-items:flex-start; display:grid; } }
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_index(text: str) -> str:
    if MARKER_HTML in text:
        return text
    text = replace_once(
        text,
        '        <button class="nav-item" data-nav="week"><span>▦</span><b>Неделя</b></button>\n        <button class="nav-item" data-nav="settings"><span>···</span><b>Настройки</b></button>',
        '        <button class="nav-item" data-nav="week"><span>▦</span><b>Неделя</b></button>\n        <button class="nav-item" data-nav="training"><span>🏋</span><b>Тренировки</b></button>\n        <button class="nav-item" data-nav="settings"><span>···</span><b>Настройки</b></button>',
        "sidebar training nav",
    )
    text = replace_once(text, '      <section class="view" id="view-settings" data-view="settings">', TRAINING_SECTION + '\n      <section class="view" id="view-settings" data-view="settings">', "training section")
    text = replace_once(
        text,
        '      <button data-nav="week"><span>▦</span><small>Неделя</small></button>\n      <button data-nav="settings"><span>···</span><small>Ещё</small></button>',
        '      <button data-nav="week"><span>▦</span><small>Неделя</small></button>\n      <button data-nav="training"><span>🏋</span><small>Тренировки</small></button>\n      <button data-nav="settings"><span>···</span><small>Ещё</small></button>',
        "mobile training nav",
    )
    return text


def patch_app(text: str) -> str:
    if MARKER_JS in text:
        return text
    text = replace_once(text, "      week: 'Неделя без каши: жизнь, дела и восстановление в одном месте.',\n      settings:", "      week: 'Неделя без каши: жизнь, дела и восстановление в одном месте.',\n      training: 'Тренируйся по готовности, а не по чувству вины.',\n      settings:", "direct training copy")
    text = replace_once(text, "      week: 'Посмотри на ближайшие семь дней без попытки забить каждый час.',\n      settings:", "      week: 'Посмотри на ближайшие семь дней без попытки забить каждый час.',\n      training: 'Проверь сон, боль и энергию перед нагрузкой.',\n      settings:", "calm training copy")
    text = replace_once(text, "    if (!['home', 'tasks', 'focus', 'proof', 'week', 'settings'].includes(view)) return;", "    if (!['home', 'tasks', 'focus', 'proof', 'week', 'training', 'settings'].includes(view)) return;", "navigate training")
    text = replace_once(text, "    if (view === 'week') renderWeek();", "    if (view === 'week') renderWeek();\n    if (view === 'training') renderTraining();", "render training view")
    text = replace_once(text, "  function renderSettings() {", JS_TRAINING + "\n  function renderSettings() {", "training js")
    text = replace_once(text, "    renderWeek();\n    renderSettings();", "    renderWeek();\n    renderTraining();\n    renderSettings();", "render all training")
    return text


def patch_css(text: str) -> str:
    return text if MARKER_CSS in text else text.rstrip() + CSS_TRAINING + "\n"


def patch_sw(text: str) -> str:
    if "dvizh-training-web-v1" in text:
        return text
    changed, count = re.subn(r"(const\s+CACHE\s*=\s*['\"])([^'\"]+)(['\"])", r"\1dvizh-training-web-v1\3", text, count=1)
    if count != 1:
        raise RuntimeError("service worker cache anchor not found")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    files = {name: root / name for name in ("index.html", "app.js", "styles.css", "sw.js")}
    for path in files.values():
        if not path.is_file():
            raise SystemExit(f"missing {path}")
    original = {name: path.read_text(encoding="utf-8") for name, path in files.items()}
    patched = {
        "index.html": patch_index(original["index.html"]),
        "app.js": patch_app(original["app.js"]),
        "styles.css": patch_css(original["styles.css"]),
        "sw.js": patch_sw(original["sw.js"]),
    }
    if args.check:
        for name, value in patched.items():
            if not value:
                raise SystemExit(f"empty patched {name}")
        print("training web patch check=ok")
        return 0
    for name, value in patched.items():
        files[name].write_text(value, encoding="utf-8")
    print("training web patch=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
