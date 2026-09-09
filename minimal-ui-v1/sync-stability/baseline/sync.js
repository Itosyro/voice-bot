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

  const clientId = nativeGet.call(localStorage, CLIENT_KEY) || uid();
  nativeSet.call(localStorage, CLIENT_KEY, clientId);

  let meta = safeParse(nativeGet.call(localStorage, META_KEY)) || {};
  meta = {
    revision: Number(meta.revision) || 0,
    lastSyncedAt: meta.lastSyncedAt || null,
    clientId
  };

  let ready = false;
  let appLoaded = false;
  let pushTimer = null;
  let inFlight = false;
  let queued = false;
  let forceNext = false;
  let pendingResetAt = null;
  let pollTimer = null;
  let reloadAfterSync = false;

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
    state.__sync = sync;
    return state;
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
    const response = await fetch('/api/state', {
      method: 'PUT',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state, baseRevision: meta.revision, force })
    });
    const body = await response.json().catch(() => ({}));
    if (response.status === 409 && retry && body.state) {
      const latestLocal = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY))) || state;
      const merged = mergeStates(latestLocal, body.state);
      nativeSet.call(localStorage, STATE_KEY, JSON.stringify(merged));
      meta.revision = Number(body.revision) || 0;
      persistMeta();
      reloadAfterSync = appLoaded;
      return sendState(merged, { force: false, retry: false });
    }
    if (!response.ok) {
      const error = new Error(body.message || body.error || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    meta.revision = Number(body.revision) || meta.revision;
    meta.lastSyncedAt = body.updatedAt || isoNow();
    persistMeta();
    return body;
  }

  function queuePush({ force = false } = {}) {
    if (force) forceNext = true;
    if (!ready) return;
    queued = true;
    clearTimeout(pushTimer);
    pushTimer = setTimeout(() => pushLatest(), PUSH_DELAY_MS);
    setStatus('syncing', 'Сохраняю изменения…');
  }

  async function pushLatest() {
    if (!ready) return;
    if (inFlight) {
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
      if (reloadAfterSync) {
        reloadAfterSync = false;
        window.setTimeout(() => location.reload(), 120);
        return;
      }
    } catch (error) {
      if (error.status === 401) setStatus('error', 'Нужно войти в exe.dev. Локальные данные сохранены.');
      else setStatus('offline', 'Нет связи с сервером. Сохраню и отправлю позже.');
      forceNext ||= force;
      queued = true;
    } finally {
      inFlight = false;
      if (queued && navigator.onLine) {
        clearTimeout(pushTimer);
        pushTimer = setTimeout(() => pushLatest(), 1600);
      }
    }
  }

  function manualJumpRenderState(state) {
    const copy = clone(state);
    const packet = copy?.jumpLab?.coachPacket;
    if (packet && typeof packet === 'object') delete packet.exportedAt;
    return copy;
  }

  async function pullLatest({ manual = false } = {}) {
    if (!ready || inFlight || document.visibilityState === 'hidden') return;
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
      const local = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY)));
      const merged = queued ? mergeStates(local, remote.state) : normalizeState(remote.state);
      const manualJumpChanged = JSON.stringify(manualJumpRenderState(local)) !== JSON.stringify(manualJumpRenderState(merged));
      nativeSet.call(localStorage, STATE_KEY, JSON.stringify(merged));
      meta.revision = remoteRevision;
      meta.lastSyncedAt = remote.updatedAt || isoNow();
      persistMeta();
      setStatus('ok', 'Получены изменения с другого устройства.');
      if (queued) {
        queuePush();
        reloadAfterSync = appLoaded;
      } else if (appLoaded && manualJumpChanged) {
        window.setTimeout(() => location.reload(), 120);
      }
    } catch (error) {
      if (manual) setStatus(error.status === 401 ? 'error' : 'offline', error.status === 401 ? 'Нужно войти в exe.dev.' : 'Сервер сейчас недоступен.');
    }
  }

  Storage.prototype.setItem = function patchedSetItem(key, value) {
    if (this !== localStorage || key !== STATE_KEY) return nativeSet.call(this, key, value);
    const next = safeParse(String(value));
    const previous = safeParse(nativeGet.call(localStorage, STATE_KEY));
    const stamped = stampState(next, previous);
    nativeSet.call(localStorage, STATE_KEY, JSON.stringify(stamped));
    queuePush();
  };

  Storage.prototype.removeItem = function patchedRemoveItem(key) {
    if (this === localStorage && key === STATE_KEY) {
      pendingResetAt = isoNow();
      forceNext = true;
      meta.revision = Number(meta.revision) || 0;
      persistMeta();
    }
    return nativeRemove.call(this, key);
  };

  async function initialSync() {
    setStatus('syncing', 'Подключаю синхронизацию…');
    const local = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY)));
    try {
      const remote = await requestState();
      if (remote.state) {
        const remoteState = normalizeState(remote.state);
        let chosen;
        let needsUpload = false;
        if (!local) {
          chosen = remoteState;
        } else if (meta.revision === 0 && !meaningfulState(local)) {
          chosen = remoteState;
        } else {
          chosen = mergeStates(local, remoteState);
          needsUpload = JSON.stringify(chosen) !== JSON.stringify(remoteState);
        }
        nativeSet.call(localStorage, STATE_KEY, JSON.stringify(chosen));
        meta.revision = Number(remote.revision) || 0;
        meta.lastSyncedAt = remote.updatedAt || isoNow();
        persistMeta();
        ready = true;
        if (needsUpload) await sendState(chosen);
      } else {
        meta.revision = 0;
        persistMeta();
        ready = true;
        if (local) await sendState(local, { force: true });
      }
      setStatus('ok', 'Синхронизировано на телефоне и ноутбуке.');
    } catch (error) {
      ready = true;
      if (error.status === 401) setStatus('error', 'Открой через exe.dev и войди в аккаунт.');
      else setStatus('offline', 'Сервер недоступен. Приложение работает локально.');
    }

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
    pull: () => pullLatest({ manual: true }),
    push: () => pushLatest(),
    get revision() { return meta.revision; },
    markAppLoaded() { appLoaded = true; }
  };
  window.DVIZH_SYNC_READY = initialSync();
})();
