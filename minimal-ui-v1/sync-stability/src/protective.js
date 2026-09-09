  // Capability is decided only by boot's app-load signal. Until then uploads wait.
  const PENDING_KEY = 'dvizh-sync-quarantine-v1';
  const RECOVERY_KEY = 'dvizh-manual-recovery-v1';
  const UPDATE_URL = '/manual.html?v=20260909-sync-stability-2';
  let protective = false;
  const previousQuarantine = safeParse(startupRead(PENDING_KEY));
  let pendingLocal = previousQuarantine?.state || null;
  const quarantineHistory = [...(previousQuarantine?.history || []), ...(pendingLocal ? [{state:clone(pendingLocal),baseState:previousQuarantine.baseState,revision:previousQuarantine.revision}] : [])];
  const startupLocal = normalizeState(initialLocalSnapshot);
  const startupSnapshots = [];
  let recoveryError = storageStartupError ? 'Не удалось сохранить данные в хранилище. Защитный режим: отправка отключена. Не закрывайте страницу; скопируйте резервную копию ниже.' : '';
  function quarantine(value) {
    if (pendingLocal) quarantineHistory.push({state:clone(pendingLocal),baseState:clone(meta.baseState),revision:meta.revision});
    pendingLocal = clone(value);
    try {
      const encoded = JSON.stringify({state: pendingLocal, baseState: meta.baseState, revision: meta.revision, history:quarantineHistory});
      nativeSet.call(localStorage, PENDING_KEY, encoded);
      if (nativeGet.call(localStorage, PENDING_KEY) !== encoded) throw Error('storage verification');
    } catch { recoveryError = 'Не удалось сохранить локальные изменения. Не закрывайте страницу: скопируйте резервную копию ниже.'; }
    showProtection();
  }
  function recoveryText() {
    return JSON.stringify({pending: {state:pendingLocal,history:quarantineHistory},
      previousRecovery:safeParse(startupRead(RECOVERY_KEY)),
      forms: [...document.querySelectorAll('form')].map(form => ({id:form.id,
        fields:[...form.querySelectorAll('input:not([type="password"]),textarea,select')].map(el => ({id:el.id,name:el.name,type:el.type,
          value:el.value,checked:el.checked,selected:el.tagName==='SELECT'?[...el.selectedOptions].map(o=>o.value):undefined}))})),
      editable:[...document.querySelectorAll('[contenteditable="true"]')].map(el=>({id:el.id,text:el.textContent})),
      view:document.querySelector('.view.active')?.id || '', savedAt:isoNow()}, null, 2);
  }
  function showProtection() {
    let panel = document.getElementById('syncUpdateRequired');
    if (!panel) {
      panel = document.createElement('aside');
      panel.id = 'syncUpdateRequired';
      panel.setAttribute('role','alert');
      panel.style.cssText = 'position:fixed;bottom:12px;left:12px;right:12px;z-index:100000;background:#fff;color:#111;padding:16px;border:2px solid #b45309;max-height:45vh;overflow:auto';
      const message = document.createElement('p'); message.dataset.updateMessage = '';
      const button = document.createElement('button'); button.type='button'; button.textContent='Обновить Manual';
      button.dataset.manualUpdate = UPDATE_URL;
      button.addEventListener('click', () => {
        const backup = panel.querySelector('textarea');
        try {
          const text = recoveryText(); backup.value=text; backup.hidden=false;
          if ([...document.querySelectorAll('input[type="file"]')].some(el=>el.files.length)) throw Error('files');
          nativeSet.call(localStorage, RECOVERY_KEY, text);
          if (nativeGet.call(localStorage, RECOVERY_KEY) !== text) throw Error('storage verification');
          // No stale snapshot or command is replayed. Recovery is an explicit,
          // read-only archive on the updated page for manual transfer/review.
          if (!window.confirm('Черновики сохранены в резервной копии. Автоматическое заполнение форм и отправка отложенных изменений недоступны. После обновления откройте «Показать сохранённые черновики» и перенесите нужные значения вручную. Продолжить?')) return;
          location.assign(UPDATE_URL);
        } catch {
          recoveryError='Восстановление не гарантировано (хранилище или вложения недоступны). Обновление отменено. Скопируйте резервную копию и сохраните вложения вручную; не закрывайте страницу.';
          showProtection();
        }
      });
      const backup=document.createElement('textarea'); backup.readOnly=true; backup.hidden=true; backup.setAttribute('aria-label','Резервная копия черновиков');
      panel.append(message,button,backup); document.body.appendChild(panel);
    }
    panel.querySelector('[data-update-message]').textContent = recoveryError || 'Требуется обновление Manual. Защитный режим: изменения остаются на этом устройстве и не отправляются. Серверные данные защищены. Перед обновлением будет сохранена резервная копия форм для ручного восстановления.';
    if(recoveryError) {const backup=panel.querySelector('textarea');backup.hidden=false;backup.value=recoveryText();}
  }
  function showRecovery() {
    const archive=nativeGet.call(localStorage, RECOVERY_KEY);
    const pending=nativeGet.call(localStorage, PENDING_KEY);
    if(!archive && !pending) return;
    const panel=document.createElement('aside');panel.id='syncDraftRecovery';
    const label=document.createElement('p');label.textContent='Есть сохранённые черновики и отложенные изменения. Автовосстановление недоступно. Проверьте текущие данные и перенесите нужные значения вручную; резервная копия не отправляется на сервер.';
    const button=document.createElement('button');button.type='button';button.textContent='Показать сохранённые черновики';
    const text=document.createElement('textarea');text.readOnly=true;text.hidden=true;text.setAttribute('aria-label','Сохранённые черновики');text.value=JSON.stringify({forms:safeParse(archive),quarantined:safeParse(pending)},null,2);
    button.addEventListener('click',()=>{text.hidden=false;text.focus();text.select();});
    panel.append(label,button,text);document.body.prepend(panel);
  }
  function checkAppCapability() {
    if (protective) return; // A late hook cannot silently resume quarantined writes.
    if (storageStartupError || typeof window.DVIZH_MANUAL_STATE?.applyRemote !== 'function') {
      protective = true;
      clearTimeout(pushTimer);
      if (startupLocal) quarantine(startupLocal);
      for (const snapshot of startupSnapshots) quarantine(snapshot);
      if (meta.baseState && !storageStartupError) nativeSet.call(localStorage, STATE_KEY, JSON.stringify(meta.baseState));
      queued = false;
      showProtection();
    } else {

      if (queued) queuePush();
      showRecovery();
    }
  }
