const fs = require('node:fs');
const path = require('node:path');
module.exports = (name, source) => {
  const replace = (old, next) => {
    if (source.split(old).length !== 2) throw Error(`Expected one pinned anchor in ${name}: ${old.slice(0,80)}`);
    source = source.replace(old, next);
  };
  if (name === 'manual.html') {
    replace('<script src="sync.js"></script>', '<script src="sync.js?v=20260909-sync-stability-2"></script>');
  }
  if (name === 'sync.js') {
    replace("  const clientId = nativeGet.call(localStorage, CLIENT_KEY) || uid();\n  nativeSet.call(localStorage, CLIENT_KEY, clientId);", `  let storageStartupError = false;
  function startupRead(key) {
    try { return nativeGet.call(localStorage, key); }
    catch { storageStartupError = true; return null; }
  }
  const initialLocalSnapshot = safeParse(startupRead(STATE_KEY));
  const clientId = startupRead(CLIENT_KEY) || uid();
  try { nativeSet.call(localStorage, CLIENT_KEY, clientId); }
  catch { storageStartupError = true; }`);
    replace('safeParse(nativeGet.call(localStorage, META_KEY))', 'safeParse(startupRead(META_KEY))');
    replace('  async function initialSync() {', '  async function initialSync() {\n    if (storageStartupError) { ready = true; protective = true; if (startupLocal) quarantine(startupLocal); else showProtection(); return; }\n    inFlight = true;');
    replace('        nativeSet.call(localStorage, STATE_KEY, JSON.stringify(chosen));', `        const latest = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY)));
        if (latest && !same(latest, local)) chosen = reconcile(local || undefined, latest, chosen);
        needsUpload = !same(chosen, remoteState);
        nativeSet.call(localStorage, STATE_KEY, JSON.stringify(chosen));`);
    replace('      ready = true;\n      if (error.status === 401)', '      ready = true;\n      queued = Boolean(normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY))));\n      if (error.status === 401)');
    replace('    pollTimer = window.setInterval', '    inFlight = false;\n    if (queued) queuePush();\n    pollTimer = window.setInterval');
    replace('    state.__sync = sync;', `    state.tasks = state.tasks.filter(row => !sync.deletedTasks[row.id] || parseTime(row._syncUpdatedAt) > parseTime(sync.deletedTasks[row.id]));
    state.proofs = state.proofs.filter(row => !sync.deletedProofs[row.id] || parseTime(row._syncUpdatedAt) > parseTime(sync.deletedProofs[row.id]));
    state.__sync = sync;`);
    replace(`  function manualJumpRenderState(state) {
    const copy = clone(state);
    const packet = copy?.jumpLab?.coachPacket;
    if (packet && typeof packet === 'object') delete packet.exportedAt;
    return copy;
  }

`, '');
    replace('      const manualJumpChanged = JSON.stringify(manualJumpRenderState(local)) !== JSON.stringify(manualJumpRenderState(merged));\n', '');
    replace('baseRevision: meta.revision, force })', 'baseRevision: meta.revision, force: false })');
    replace('  function persistMeta() {', fs.readFileSync(path.join(__dirname, 'reconcile.js'), 'utf8') + '\n  function persistMeta() {');
    replace('    clientId\n  };', '    clientId,\n    baseState: meta.baseState || null\n  };');
    replace('const merged = mergeStates(latestLocal, body.state);', 'const merged = meta.baseState ? reconcile(meta.baseState, latestLocal, normalizeState(body.state)) : upgradeMerge(latestLocal, body.state);\n      meta.baseState = normalizeState(body.state);');
    replace('    meta.revision = Number(body.revision) || meta.revision;', '    meta.baseState = clone(state);\n    meta.revision = Number(body.revision) || meta.revision;');
    replace('        const remoteState = normalizeState(remote.state);', '        const remoteState = normalizeState(remote.state);\n        const previousBase = meta.baseState;\n        meta.baseState = clone(remoteState);');
    replace('          chosen = mergeStates(local, remoteState);', '          chosen = previousBase ? reconcile(previousBase, local, remoteState) : upgradeMerge(local, remoteState);');
    replace('    pull: () => pullLatest({ manual: true }),', '    reconcile,\n    pull: () => pullLatest({ manual: true }),');
    replace('  let inFlight = false;', '  let inFlight = false;\n  let pulling = false;\n  let pendingPull = false;');
    replace('    if (inFlight) {', '    if (inFlight || pulling) {');
    replace("    if (!ready || inFlight || document.visibilityState === 'hidden') return;", "    if (!ready || document.visibilityState === 'hidden') return;\n    if (inFlight || pulling) { pendingPull = true; return; }\n    pulling = true;");
    replace('const merged = queued ? mergeStates(local, remote.state) : normalizeState(remote.state);', 'const merged = meta.baseState ? reconcile(meta.baseState, local, normalizeState(remote.state)) : (queued ? upgradeMerge(local, remote.state) : normalizeState(remote.state));\n      meta.baseState = normalizeState(remote.state);');
    replace("      inFlight = false;", "      inFlight = false;\n      if (pendingPull) { pendingPull = false; void pullLatest(); }");
    replace("    }\n  }\n\n  Storage.prototype.setItem", "    } finally {\n      pulling = false;\n      if (queued) queuePush();\n      if (pendingPull) { pendingPull = false; void pullLatest(); }\n    }\n  }\n\n  Storage.prototype.setItem");
    replace('let reloadAfterSync = false;', `function applyRemote(state) {
    window.DVIZH_MANUAL_STATE?.applyRemote(clone(state));
  }`);
    replace('      reloadAfterSync = appLoaded;\n      return sendState', '      applyRemote(merged);\n      return sendState');
    replace(`      if (reloadAfterSync) {
        reloadAfterSync = false;
        window.setTimeout(() => location.reload(), 120);
        return;
      }`, '');
    replace(`        reloadAfterSync = appLoaded;
      } else if (appLoaded && manualJumpChanged) {
        window.setTimeout(() => location.reload(), 120);
      }`, `      }
      applyRemote(merged);`);
  }
  if (name === 'sync.js') {
    replace('  function persistMeta() {', fs.readFileSync(path.join(__dirname, 'protective.js'), 'utf8') + '\n  function persistMeta() {');
    replace('markAppLoaded() { appLoaded = true; }', 'get protective() { return protective; },\n    get pendingLocal() { return clone(pendingLocal); },\n    markAppLoaded() { appLoaded = true; checkAppCapability(); }');
    replace('        if (needsUpload) await sendState(chosen);', '        if (needsUpload) queued = true;');
    replace('        if (local) await sendState(local, { force: true });', '        if (local) queued = true;');
    replace('    if (!ready) return;\n    queued = true;', '    queued = true;\n    if (!ready || !appLoaded || protective) return;');
    replace('    if (!ready) return;\n    if (inFlight || pulling)', '    if (!ready || !appLoaded || protective) return;\n    if (inFlight || pulling)');
    replace('  async function sendState(state, { force = false, retry = true } = {}) {', '  async function sendState(state, { force = false, retry = true } = {}) {\n    if (!appLoaded || protective) return;');
    replace('    const stamped = stampState(next, previous);', '    if (!appLoaded) startupSnapshots.push(clone(next));\n    if (protective || storageStartupError) { quarantine(next); return; }\n    const stamped = stampState(next, previous);');
    replace('      pendingResetAt = isoNow();', '      if (protective) { showProtection(); return; }\n      pendingResetAt = isoNow();');
    replace('      const local = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY)));', `      if (storageStartupError) { showProtection(); return; }
      if (protective) {
        meta.baseState = normalizeState(remote.state);
        meta.revision = remoteRevision;
        meta.lastSyncedAt = remote.updatedAt || isoNow();
        nativeSet.call(localStorage, STATE_KEY, JSON.stringify(meta.baseState));
        persistMeta();
        showProtection();
        return;
      }
      const local = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY)));`);
    replace('  function setStatus(kind, text) {', "  function setStatus(kind, text) {\n    if (protective) { kind = 'error'; text = 'Требуется обновление Manual. Изменения сохранены только локально.'; }");
  }
  if (name === 'app.js') {
    replace("    if (view === 'focus') renderFocus();", "    if (view === 'home') { renderHeader(); renderCheckin(); renderSuggestion(); renderDailyPlan(); }\n    if (view === 'tasks') renderTasks();\n    if (view === 'settings') renderSettings();\n    if (view === 'focus') renderFocus();");
    for (const [signature, id] of [
      ['openTaskEditor(taskId = null)', 'taskForm'],
      ["weekEditorOpen(itemId = '')", 'weekEditorForm'],
      ['jumpFillExercise(row=null)', 'jumpExerciseForm'],
      ['socialFillForm(row=null)', 'socialContentForm']
    ]) replace(`  function ${signature} {`, `  function ${signature} {\n    rememberForm('${id}');`);


    replace('  function jumpEnqueue(action,payload={}) {', "  function jumpEnqueue(action,payload={}) {\n    rebaseCommand('jumpLab', action, payload);");
    replace('  function socialEnqueue(action,payload={}) {', "  function socialEnqueue(action,payload={}) {\n    rebaseCommand('socialHub', action, payload);");
    replace('  function weekEnqueue(action, payload = {}) {', "  function weekEnqueue(action, payload = {}) {\n    rebaseCommand('weeklySchedule', action, payload);");
    const jumpProfileFields = Object.fromEntries([...source.matchAll(/jumpValue\('(#\w+)',p\.(\w+)[^;]*\);/g)].map(match => [match[1].slice(1), match[2]]));
    if (Object.keys(jumpProfileFields).length !== 25) throw Error('Jump profile form mapping drift');
    replace('  init();', `  const renderJumpWithState = renderJumpLab;
  renderJumpLab = function () {
    renderJumpWithState();
    rememberForm('jumpProfileForm');
  };
  const renderSocialWithState = renderSocial;
  renderSocial = function () {
    renderSocialWithState();
    rememberForm('socialSettingsForm');
  };
  init();`);
    replace("  let activeView = 'home';", '  const jumpProfileFields = ' + JSON.stringify(jumpProfileFields) + ';\n' + fs.readFileSync(path.join(__dirname, 'app-boundary.js'), 'utf8') + "\n  let activeView = 'home';");
    replace('    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));', `    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    if (stored && canReconcile()) {
      updateStateObject(state, window.DVIZH_SYNC.reconcile(submitBase || stateBase, state, stored));
    }
    submitBase = null;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    for (const {before, field, value} of consumedFields) before[field] = value;
    consumedFields = [];
    stateBase = stateCopy(state);`);
  }
  return source;
};
