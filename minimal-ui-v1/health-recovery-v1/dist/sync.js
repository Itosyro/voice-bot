(() => {
  'use strict';

  const STATE_KEY = 'dvizh-state-v1';
  const META_KEY = 'dvizh-sync-meta-v1';
  const CLIENT_KEY = 'dvizh-client-id-v1';
  const POLL_MS = 8000;
  const PUSH_DELAY_MS = 450;

  const nativeGet = Storage.prototype.getItem;
  const nativeSet = Storage.prototype.setItem;
  const nativeRemove = Storage.prototype.removeItem;

  const isoNow = () => new Date().toISOString();
  const parseTime = value => {
    const time = Date.parse(value || '');
    return Number.isFinite(time) ? time : 0;
  };
  const later = (a, b) => parseTime(a) >= parseTime(b) ? a : b;
  const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  const safeParse = value => {
    try { return value ? JSON.parse(value) : null; } catch { return null; }
  };
  const clone = value => value == null ? value : JSON.parse(JSON.stringify(value));

  let storageStartupError = false;
  function startupRead(key) {
    try { return nativeGet.call(localStorage, key); }
    catch { storageStartupError = true; return null; }
  }
  const initialLocalSnapshot = safeParse(startupRead(STATE_KEY));
  const clientId = startupRead(CLIENT_KEY) || uid();
  try { nativeSet.call(localStorage, CLIENT_KEY, clientId); }
  catch { storageStartupError = true; }

  let meta = safeParse(startupRead(META_KEY)) || {};
  meta = {
    revision: Number(meta.revision) || 0,
    lastSyncedAt: meta.lastSyncedAt || null,
    clientId,
    baseState: meta.baseState || null
  };

  let ready = false;
  let appLoaded = false;
  let pushTimer = null;
  let inFlight = false;
  let pulling = false;
  let pendingPull = false;
  let queued = false;
  let forceNext = false;
  let pendingResetAt = null;
  let pollTimer = null;
  function applyRemote(state) {
    window.DVIZH_MANUAL_STATE?.applyRemote(clone(state));
  }

  // Three-way JSON reconciliation. Local changed leaves win simultaneous edits;
  // deletion of an existing record wins over edits. Identity arrays merge by id.
  function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === 'object') return Object.fromEntries(
      Object.keys(value).sort().map(key => [key, canonical(value[key])]));
    return value;
  }
  const same = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
  // Authorized health-only delta: derived sleep fields are never independent leaves.
  function normalizeHealthSleep(state) {
    const h = state?.healthRecovery;
    if (!h || (h.version !== undefined && h.version !== 1) || !h.sleep || Array.isArray(h.sleep)) return state;
    for (const [day, row] of Object.entries(h.sleep)) {
      if (!row || typeof row !== 'object' || Array.isArray(row)) continue;
      if (row.durationKind === 'reported') {
        for (const key of ['start','end','startDay']) delete row[key];
      } else if (row.durationKind === 'clock' || (!Object.hasOwn(row,'durationKind') && Object.hasOwn(row,'start') && Object.hasOwn(row,'end'))) {
        const clock = value => typeof value === 'string' && /^([01]\d|2[0-3]):[0-5]\d$/.test(value) ? +value.slice(0,2)*60 + +value.slice(3) : NaN;
        const a=clock(row.start), b=clock(row.end), minutes=(b-a+1440)%1440;
        const date = new Date(day+'T00:00:00Z');
        if (minutes && /^\d{4}-\d{2}-\d{2}$/.test(day) && Number.isFinite(+date) && date.toISOString().slice(0,10)===day) {
          row.durationMinutes=minutes;
          row.startDay=new Date(+date-(a>b?86400000:0)).toISOString().slice(0,10);
        } else {
          delete row.durationMinutes;
          delete row.startDay;
        }
      }
    }
    return state;
  }
  function reconcile(base, local, remote) {
    const result = reconcileJSON(base, local, remote);
    const reset = result?.__sync?.resetAt;
    if (reset && reset !== base?.__sync?.resetAt) return normalizeHealthSleep(result);
    const h=result?.healthRecovery;
    if (h && (h.version === undefined || h.version === 1)) {
      const mode = row => row?.durationKind || (row?.start !== undefined && row?.end !== undefined ? 'clock' : 'reported');
      for (const [day,row] of Object.entries(h.sleep || {})) {
        const b=base?.healthRecovery?.sleep?.[day], l=local?.healthRecovery?.sleep?.[day], r=remote?.healthRecovery?.sleep?.[day];
        if (!row || typeof row !== 'object' || Array.isArray(row) || !l || !r || mode(l)===mode(r)) continue;
        // Mode changes select only the temporal bundle. All other leaves retain
        // the existing three-way merge, including note, quality and future fields.
        const winner = mode(l)!==mode(b) ? l : r;
        for (const key of ['durationKind','durationMinutes','start','end','startDay']) {
          if (Object.hasOwn(winner,key)) row[key]=clone(winner[key]);
          else delete row[key];
        }
      }
    }
    return normalizeHealthSleep(result);
  }
  function reconcileJSON(base, local, remote, entity = false) {
    const localReset = local?.__sync?.resetAt;
    const remoteReset = remote?.__sync?.resetAt;
    const baseReset = base?.__sync?.resetAt;
    if (remoteReset && remoteReset !== baseReset && parseTime(remoteReset) >= parseTime(localReset)) return clone(remote);
    if (localReset && localReset !== baseReset && parseTime(localReset) > parseTime(remoteReset)) return clone(local);
    if (same(local, base)) return clone(remote);
    if (same(remote, base) || same(local, remote)) return clone(local);
    if (local === undefined || (entity && base !== undefined && remote === undefined)) return undefined;
    const identified = (value, key) => Array.isArray(value) && value.every(row => row && typeof row === 'object' && row[key] != null)
      && new Set(value.map(row => String(row[key]))).size === value.length;
    const identity = ['id', 'commandId', 'code', 'exerciseKey'].find(key => identified(local, key) && identified(remote, key) && (base === undefined || identified(base, key)));
    if (identity) {
      const index = rows => new Map((rows || []).map(row => [String(row[identity]), row]));
      const b=index(base), l=index(local), r=index(remote);
      return [...new Set([...l.keys(), ...r.keys()])].map(id => reconcileJSON(b.get(id),l.get(id),r.get(id), true)).filter(row => row !== undefined);
    }
    const record = value => value && typeof value === 'object' && !Array.isArray(value);
    if (record(local) && record(remote) && (base === undefined || record(base))) {
      const result = {};
      for (const key of new Set([...Object.keys(base || {}), ...Object.keys(local), ...Object.keys(remote)])) {
        const value = reconcileJSON(base?.[key], local[key], remote[key]);
        if (value !== undefined) Object.defineProperty(result,key,{value,enumerable:true,writable:true,configurable:true});
      }
      return result;
    }
    return clone(local);
  }
  // One-time upgrade: older clients did not retain a common ancestor. Keep the
  // legacy core timestamp merge, but never use its settings winner for projections.
  function upgradeMerge(localInput, remoteInput) {
    const local = normalizeState(localInput), remote = normalizeState(remoteInput);
    const merged = mergeStates(local, remote);
    if (!local || !remote) return merged;
    if (parseTime(local.__sync.resetAt) > parseTime(remote.__sync.updatedAt) || parseTime(remote.__sync.resetAt) > parseTime(local.__sync.updatedAt)) return merged;
    const core = new Set(['version','createdAt','hasSeenIntro','tone','focusDuration','selectedFocusTaskId','tasks','sessions','proofs','checkins','plans','ladder','__sync']);
    for (const key of Object.keys(remote)) if (!core.has(key)) merged[key] = clone(remote[key]);
    for (const key of ['trainingHub','jumpLab','weeklySchedule','socialHub']) {
      if (!local[key] && !remote[key]) continue;
      const results = remote[key]?.commandResults || [];
      const acknowledged = new Set(results.flatMap(row => [row.id, row.commandId]).filter(id => id != null).map(String));
      const commands = reconcile([], local[key]?.webCommands || [], remote[key]?.webCommands || []).filter(row => !acknowledged.has(String(row.id)));
      merged[key] ||= {};
      if (commands.length || remote[key]?.webCommands) merged[key].webCommands = commands;
    }
    if (local.aiProposalCommands || remote.aiProposalCommands) merged.aiProposalCommands = reconcile([], local.aiProposalCommands || [], remote.aiProposalCommands || []);
    return merged;
  }

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

  function persistMeta() {
    nativeSet.call(localStorage, META_KEY, JSON.stringify(meta));
  }

  function maxTimestampMap(a = {}, b = {}) {
    const result = { ...a };
    for (const [key, value] of Object.entries(b || {})) {
      if (parseTime(value) > parseTime(result[key])) result[key] = value;
    }
    return result;
  }

  function comparable(value) {
    if (!value || typeof value !== 'object') return value;
    const copy = { ...value };
    delete copy._syncUpdatedAt;
    return copy;
  }

  function equalEntity(a, b) {
    return JSON.stringify(comparable(a)) === JSON.stringify(comparable(b));
  }

  function baseSync(state) {
    const current = state?.__sync && typeof state.__sync === 'object' ? state.__sync : {};
    return {
      updatedAt: current.updatedAt || state?.updatedAt || state?.createdAt || isoNow(),
      settingsUpdatedAt: current.settingsUpdatedAt || state?.updatedAt || state?.createdAt || isoNow(),
      resetAt: current.resetAt || null,
      deletedTasks: { ...(current.deletedTasks || {}) },
      deletedProofs: { ...(current.deletedProofs || {}) },
      ladderUpdatedAt: { ...(current.ladderUpdatedAt || {}) },
      clientId: current.clientId || clientId
    };
  }

  function normalizeState(input) {
    if (!input || typeof input !== 'object' || input.version !== 1 || !Array.isArray(input.tasks)) return null;
    const state = clone(input);
    const sync = baseSync(state);
    state.tasks = state.tasks.map(task => ({
      ...task,
      _syncUpdatedAt: task._syncUpdatedAt || task.updatedAt || task.completedAt || task.createdAt || sync.updatedAt
    }));
    state.sessions = Array.isArray(state.sessions) ? state.sessions.map(item => ({
      ...item,
      _syncUpdatedAt: item._syncUpdatedAt || item.updatedAt || item.createdAt || sync.updatedAt
    })) : [];
    state.proofs = Array.isArray(state.proofs) ? state.proofs.map(item => ({
      ...item,
      _syncUpdatedAt: item._syncUpdatedAt || item.updatedAt || item.createdAt || sync.updatedAt
    })) : [];
    state.checkins = state.checkins && typeof state.checkins === 'object' ? state.checkins : {};
    state.plans = state.plans && typeof state.plans === 'object' ? state.plans : {};
    state.ladder = state.ladder && typeof state.ladder === 'object' ? state.ladder : {};
    for (const stepId of Object.keys(state.ladder)) {
      sync.ladderUpdatedAt[stepId] ||= sync.settingsUpdatedAt;
    }
    state.tasks = state.tasks.filter(row => !sync.deletedTasks[row.id] || parseTime(row._syncUpdatedAt) > parseTime(sync.deletedTasks[row.id]));
    state.proofs = state.proofs.filter(row => !sync.deletedProofs[row.id] || parseTime(row._syncUpdatedAt) > parseTime(sync.deletedProofs[row.id]));
    state.__sync = sync;
    return normalizeHealthSleep(state);
  }

  function stampState(nextInput, previousInput, now = isoNow()) {
    const next = normalizeState(nextInput);
    if (!next) return nextInput;
    const previous = normalizeState(previousInput);
    const oldSync = previous?.__sync || baseSync(null);
    const sync = {
      ...oldSync,
      ...(next.__sync || {}),
      deletedTasks: { ...(oldSync.deletedTasks || {}), ...(next.__sync?.deletedTasks || {}) },
      deletedProofs: { ...(oldSync.deletedProofs || {}), ...(next.__sync?.deletedProofs || {}) },
      ladderUpdatedAt: { ...(oldSync.ladderUpdatedAt || {}), ...(next.__sync?.ladderUpdatedAt || {}) },
      updatedAt: now,
      clientId
    };

    const previousTasks = new Map((previous?.tasks || []).map(task => [task.id, task]));
    const nextTaskIds = new Set();
    next.tasks = next.tasks.map(task => {
      nextTaskIds.add(task.id);
      const old = previousTasks.get(task.id);
      const changed = !old || !equalEntity(task, old);
      const stamped = { ...task, _syncUpdatedAt: changed ? now : (old._syncUpdatedAt || task._syncUpdatedAt || now) };
      if (parseTime(stamped._syncUpdatedAt) > parseTime(sync.deletedTasks[task.id])) delete sync.deletedTasks[task.id];
      return stamped;
    });
    for (const old of previous?.tasks || []) {
      if (!nextTaskIds.has(old.id)) sync.deletedTasks[old.id] = now;
    }

    const previousProofs = new Map((previous?.proofs || []).map(item => [item.id, item]));
    const nextProofIds = new Set();
    next.proofs = next.proofs.map(item => {
      nextProofIds.add(item.id);
      const old = previousProofs.get(item.id);
      const changed = !old || !equalEntity(item, old);
      const stamped = { ...item, _syncUpdatedAt: changed ? now : (old._syncUpdatedAt || item._syncUpdatedAt || now) };
      if (parseTime(stamped._syncUpdatedAt) > parseTime(sync.deletedProofs[item.id])) delete sync.deletedProofs[item.id];
      return stamped;
    });
    for (const old of previous?.proofs || []) {
      if (!nextProofIds.has(old.id)) sync.deletedProofs[old.id] = now;
    }

    const previousSessions = new Map((previous?.sessions || []).map(item => [item.id, item]));
    next.sessions = next.sessions.map(item => {
      const old = previousSessions.get(item.id);
      return { ...item, _syncUpdatedAt: old?._syncUpdatedAt || item._syncUpdatedAt || item.createdAt || now };
    });

    const oldLadder = previous?.ladder || {};
    for (const stepId of new Set([...Object.keys(oldLadder), ...Object.keys(next.ladder || {})])) {
      if (Boolean(oldLadder[stepId]) !== Boolean(next.ladder?.[stepId])) sync.ladderUpdatedAt[stepId] = now;
      else sync.ladderUpdatedAt[stepId] ||= oldSync.ladderUpdatedAt?.[stepId] || sync.settingsUpdatedAt;
    }

    const settingsChanged = !previous || [
      'tone', 'hasSeenIntro', 'focusDuration', 'selectedFocusTaskId'
    ].some(key => JSON.stringify(previous[key]) !== JSON.stringify(next[key]));
    if (settingsChanged) sync.settingsUpdatedAt = now;
    if (pendingResetAt) {
      sync.resetAt = pendingResetAt;
      pendingResetAt = null;
    }
    next.__sync = sync;
    return next;
  }

  function chooseEntity(a, b) {
    if (!a) return b ? clone(b) : null;
    if (!b) return clone(a);
    const aTime = a._syncUpdatedAt || a.updatedAt || a.completedAt || a.createdAt;
    const bTime = b._syncUpdatedAt || b.updatedAt || b.completedAt || b.createdAt;
    return clone(parseTime(aTime) >= parseTime(bTime) ? a : b);
  }

  function mergeEntityArray(localItems = [], remoteItems = [], tombstones = {}) {
    const localMap = new Map(localItems.filter(item => item?.id).map(item => [item.id, item]));
    const remoteMap = new Map(remoteItems.filter(item => item?.id).map(item => [item.id, item]));
    const ids = new Set([...localMap.keys(), ...remoteMap.keys()]);
    const preferredOrder = [...localItems, ...remoteItems].map(item => item?.id).filter(Boolean);
    const resultMap = new Map();
    for (const id of ids) {
      const item = chooseEntity(localMap.get(id), remoteMap.get(id));
      if (!item) continue;
      const itemTime = item._syncUpdatedAt || item.updatedAt || item.completedAt || item.createdAt;
      if (parseTime(tombstones[id]) >= parseTime(itemTime)) continue;
      resultMap.set(id, item);
    }
    const result = [];
    for (const id of preferredOrder) {
      if (resultMap.has(id)) {
        result.push(resultMap.get(id));
        resultMap.delete(id);
      }
    }
    result.push(...resultMap.values());
    return result;
  }

  function mergeRecord(localRecord = {}, remoteRecord = {}, timestampField) {
    const result = {};
    const keys = new Set([...Object.keys(localRecord || {}), ...Object.keys(remoteRecord || {})]);
    for (const key of keys) {
      const a = localRecord?.[key];
      const b = remoteRecord?.[key];
      if (!a) result[key] = clone(b);
      else if (!b) result[key] = clone(a);
      else result[key] = clone(parseTime(a[timestampField]) >= parseTime(b[timestampField]) ? a : b);
    }
    return result;
  }

  function mergeStates(localInput, remoteInput) {
    const local = normalizeState(localInput);
    const remote = normalizeState(remoteInput);
    if (!local) return remote;
    if (!remote) return local;

    const localSync = local.__sync;
    const remoteSync = remote.__sync;
    if (parseTime(localSync.resetAt) > parseTime(remoteSync.updatedAt)) return local;
    if (parseTime(remoteSync.resetAt) > parseTime(localSync.updatedAt)) return remote;

    const deletedTasks = maxTimestampMap(localSync.deletedTasks, remoteSync.deletedTasks);
    const deletedProofs = maxTimestampMap(localSync.deletedProofs, remoteSync.deletedProofs);
    const localSettingsWins = parseTime(localSync.settingsUpdatedAt) >= parseTime(remoteSync.settingsUpdatedAt);
    const settingsSource = localSettingsWins ? local : remote;
    const otherSource = localSettingsWins ? remote : local;

    const merged = {
      ...clone(otherSource),
      ...clone(settingsSource),
      version: 1,
      tasks: mergeEntityArray(local.tasks, remote.tasks, deletedTasks),
      sessions: mergeEntityArray(local.sessions, remote.sessions, {}),
      proofs: mergeEntityArray(local.proofs, remote.proofs, deletedProofs),
      checkins: mergeRecord(local.checkins, remote.checkins, 'updatedAt'),
      plans: mergeRecord(local.plans, remote.plans, 'generatedAt'),
      ladder: {},
      createdAt: parseTime(local.createdAt) && parseTime(local.createdAt) <= parseTime(remote.createdAt) ? local.createdAt : remote.createdAt,
    };

    const ladderUpdatedAt = maxTimestampMap(localSync.ladderUpdatedAt, remoteSync.ladderUpdatedAt);
    for (const stepId of new Set([...Object.keys(local.ladder || {}), ...Object.keys(remote.ladder || {})])) {
      const localTime = localSync.ladderUpdatedAt?.[stepId];
      const remoteTime = remoteSync.ladderUpdatedAt?.[stepId];
      merged.ladder[stepId] = parseTime(localTime) >= parseTime(remoteTime)
        ? Boolean(local.ladder?.[stepId])
        : Boolean(remote.ladder?.[stepId]);
    }

    merged.hasSeenIntro = Boolean(settingsSource.hasSeenIntro || otherSource.hasSeenIntro);
    merged.__sync = {
      updatedAt: later(localSync.updatedAt, remoteSync.updatedAt),
      settingsUpdatedAt: later(localSync.settingsUpdatedAt, remoteSync.settingsUpdatedAt),
      resetAt: later(localSync.resetAt, remoteSync.resetAt),
      deletedTasks,
      deletedProofs,
      ladderUpdatedAt,
      clientId
    };
    return merged;
  }

  function meaningfulState(stateInput) {
    const state = normalizeState(stateInput);
    if (!state) return false;
    if (state.hasSeenIntro) return true;
    if (state.sessions.length || state.proofs.length) return true;
    if (Object.keys(state.checkins || {}).length) return true;
    if (state.tasks.some(task => task.done || task.updatedAt || parseTime(task._syncUpdatedAt) > parseTime(task.createdAt) + 1000)) return true;
    return state.tasks.length !== 6;
  }

  function storeState(state, { stamp = false } = {}) {
    const previous = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY)));
    const normalized = stamp ? stampState(state, previous) : normalizeState(state);
    if (!normalized) return null;
    nativeSet.call(localStorage, STATE_KEY, JSON.stringify(normalized));
    return normalized;
  }

  function setStatus(kind, text) {
    if (protective) { kind = 'error'; text = 'Требуется обновление Manual. Изменения сохранены только локально.'; }
    const apply = () => {
      const textNode = document.getElementById('syncStatusText');
      const settingsNode = document.getElementById('syncSettingsStatus');
      const dot = document.getElementById('syncStatusDot');
      if (textNode) textNode.textContent = text;
      if (settingsNode) settingsNode.textContent = text;
      if (dot) {
        dot.dataset.sync = kind;
        dot.classList.toggle('is-syncing', kind === 'syncing');
        dot.classList.toggle('is-offline', kind === 'offline' || kind === 'error');
      }
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apply, { once: true });
    else apply();
  }

  async function requestState() {
    const response = await fetch('/api/state', { credentials: 'same-origin', cache: 'no-store' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(body.message || body.error || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return body;
  }

  async function sendState(state, { force = false, retry = true } = {}) {
    if (!appLoaded || protective) return;
    const response = await fetch('/api/state', {
      method: 'PUT',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state, baseRevision: meta.revision, force: false })
    });
    const body = await response.json().catch(() => ({}));
    if (response.status === 409 && retry && body.state) {
      const latestLocal = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY))) || state;
      const merged = meta.baseState ? reconcile(meta.baseState, latestLocal, normalizeState(body.state)) : upgradeMerge(latestLocal, body.state);
      meta.baseState = normalizeState(body.state);
      nativeSet.call(localStorage, STATE_KEY, JSON.stringify(merged));
      meta.revision = Number(body.revision) || 0;
      persistMeta();
      applyRemote(merged);
      return sendState(merged, { force: false, retry: false });
    }
    if (!response.ok) {
      const error = new Error(body.message || body.error || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    meta.baseState = clone(state);
    meta.revision = Number(body.revision) || meta.revision;
    meta.lastSyncedAt = body.updatedAt || isoNow();
    persistMeta();
    return body;
  }

  function queuePush({ force = false } = {}) {
    if (force) forceNext = true;
    queued = true;
    if (!ready || !appLoaded || protective) return;
    clearTimeout(pushTimer);
    pushTimer = setTimeout(() => pushLatest(), PUSH_DELAY_MS);
    setStatus('syncing', 'Сохраняю изменения…');
  }

  async function pushLatest() {
    if (!ready || !appLoaded || protective) return;
    if (inFlight || pulling) {
      queued = true;
      return;
    }
    const state = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY)));
    if (!state) return;
    inFlight = true;
    queued = false;
    const force = forceNext;
    forceNext = false;
    setStatus('syncing', 'Синхронизация…');
    try {
      await sendState(state, { force });
      setStatus('ok', 'Синхронизировано на телефоне и ноутбуке.');

    } catch (error) {
      if (error.status === 401) setStatus('error', 'Нужно войти в exe.dev. Локальные данные сохранены.');
      else setStatus('offline', 'Нет связи с сервером. Сохраню и отправлю позже.');
      forceNext ||= force;
      queued = true;
    } finally {
      inFlight = false;
      if (pendingPull) { pendingPull = false; void pullLatest(); }
      if (queued && navigator.onLine) {
        clearTimeout(pushTimer);
        pushTimer = setTimeout(() => pushLatest(), 1600);
      }
    }
  }

  async function pullLatest({ manual = false } = {}) {
    if (!ready || document.visibilityState === 'hidden') return;
    if (inFlight || pulling) { pendingPull = true; return; }
    pulling = true;
    if (manual) setStatus('syncing', 'Проверяю сервер…');
    try {
      const remote = await requestState();
      if (!remote.state) {
        if (normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY)))) queuePush();
        return;
      }
      const remoteRevision = Number(remote.revision) || 0;
      if (remoteRevision <= meta.revision) {
        if (manual) setStatus('ok', 'Всё уже синхронизировано.');
        return;
      }
      if (storageStartupError) { showProtection(); return; }
      if (protective) {
        meta.baseState = normalizeState(remote.state);
        meta.revision = remoteRevision;
        meta.lastSyncedAt = remote.updatedAt || isoNow();
        nativeSet.call(localStorage, STATE_KEY, JSON.stringify(meta.baseState));
        persistMeta();
        showProtection();
        return;
      }
      const local = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY)));
      const merged = meta.baseState ? reconcile(meta.baseState, local, normalizeState(remote.state)) : (queued ? upgradeMerge(local, remote.state) : normalizeState(remote.state));
      meta.baseState = normalizeState(remote.state);
      nativeSet.call(localStorage, STATE_KEY, JSON.stringify(merged));
      meta.revision = remoteRevision;
      meta.lastSyncedAt = remote.updatedAt || isoNow();
      persistMeta();
      setStatus('ok', 'Получены изменения с другого устройства.');
      if (queued) {
        queuePush();
      }
      applyRemote(merged);
    } catch (error) {
      if (manual) setStatus(error.status === 401 ? 'error' : 'offline', error.status === 401 ? 'Нужно войти в exe.dev.' : 'Сервер сейчас недоступен.');
    } finally {
      pulling = false;
      if (queued) queuePush();
      if (pendingPull) { pendingPull = false; void pullLatest(); }
    }
  }

  Storage.prototype.setItem = function patchedSetItem(key, value) {
    if (this !== localStorage || key !== STATE_KEY) return nativeSet.call(this, key, value);
    const next = safeParse(String(value));
    const previous = safeParse(nativeGet.call(localStorage, STATE_KEY));
    if (!appLoaded) startupSnapshots.push(clone(next));
    if (protective || storageStartupError) { quarantine(next); return; }
    const stamped = stampState(next, previous);
    nativeSet.call(localStorage, STATE_KEY, JSON.stringify(stamped));
    queuePush();
  };

  Storage.prototype.removeItem = function patchedRemoveItem(key) {
    if (this === localStorage && key === STATE_KEY) {
      if (protective) { showProtection(); return; }
      pendingResetAt = isoNow();
      forceNext = true;
      meta.revision = Number(meta.revision) || 0;
      persistMeta();
    }
    return nativeRemove.call(this, key);
  };

  async function initialSync() {
    if (storageStartupError) { ready = true; protective = true; if (startupLocal) quarantine(startupLocal); else showProtection(); return; }
    inFlight = true;
    setStatus('syncing', 'Подключаю синхронизацию…');
    const local = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY)));
    try {
      const remote = await requestState();
      if (remote.state) {
        const remoteState = normalizeState(remote.state);
        const previousBase = meta.baseState;
        meta.baseState = clone(remoteState);
        let chosen;
        let needsUpload = false;
        if (!local) {
          chosen = remoteState;
        } else if (meta.revision === 0 && !meaningfulState(local)) {
          chosen = remoteState;
        } else {
          chosen = previousBase ? reconcile(previousBase, local, remoteState) : upgradeMerge(local, remoteState);
          needsUpload = JSON.stringify(chosen) !== JSON.stringify(remoteState);
        }
        const latest = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY)));
        if (latest && !same(latest, local)) chosen = reconcile(local || undefined, latest, chosen);
        needsUpload = !same(chosen, remoteState);
        nativeSet.call(localStorage, STATE_KEY, JSON.stringify(chosen));
        meta.revision = Number(remote.revision) || 0;
        meta.lastSyncedAt = remote.updatedAt || isoNow();
        persistMeta();
        ready = true;
        if (needsUpload) queued = true;
      } else {
        meta.revision = 0;
        persistMeta();
        ready = true;
        if (local) queued = true;
      }
      setStatus('ok', 'Синхронизировано на телефоне и ноутбуке.');
    } catch (error) {
      ready = true;
      queued = Boolean(normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY))));
      if (error.status === 401) setStatus('error', 'Открой через exe.dev и войди в аккаунт.');
      else setStatus('offline', 'Сервер недоступен. Приложение работает локально.');
    }

    inFlight = false;
    if (queued) queuePush();
    pollTimer = window.setInterval(() => pullLatest(), POLL_MS);
    window.addEventListener('online', () => { setStatus('syncing', 'Интернет вернулся. Синхронизирую…'); pushLatest().then(() => pullLatest()); });
    window.addEventListener('offline', () => setStatus('offline', 'Нет интернета. Изменения сохранены локально.'));
    window.addEventListener('focus', () => pullLatest());
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') pullLatest(); });
    document.addEventListener('click', event => {
      const button = event.target.closest('[data-sync-now]');
      if (!button) return;
      event.preventDefault();
      pushLatest().then(() => pullLatest({ manual: true }));
    });
  }

  window.DVIZH_SYNC = {
    reconcile,
    pull: () => pullLatest({ manual: true }),
    push: () => pushLatest(),
    get revision() { return meta.revision; },
    get protective() { return protective; },
    get pendingLocal() { return clone(pendingLocal); },
    markAppLoaded() { appLoaded = true; checkAppCapability(); }
  };
  window.DVIZH_SYNC_READY = initialSync();
})();
