"""Deterministic DVIZH client-only deltas; never reads or writes production.

Source inputs are the unchanged Health Recovery generated client snapshots.
No schema, role, permission, assistant prompt or application design changes.
"""
RELEASE_KEY = "20260913-daily-stability-1"

def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected exactly one source anchor: {old[:100]!r}; found {text.count(old)}')
    return text.replace(old, new, 1)


def patch_ai(text):
    text = once(text, "  async function request(token, method = 'GET', revision, state) {", '''  function canonicalState(value) {
    if (Array.isArray(value)) return value.map(canonicalState);
    if (object(value)) return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonicalState(value[key])]));
    return value;
  }

  async function request(token, method = 'GET', revision, state) {''')
    text = once(text, "        if (payload.ok !== true) throw fault('payload');", '''        // A proxy's {ok:true} or an unrelated snapshot is not a save receipt.
        // The existing CAS API echoes the exact state at baseRevision + 1.
        if (payload.ok !== true || !Number.isSafeInteger(payload.revision) || payload.revision !== revision + 1
          || !object(payload.state) || JSON.stringify(canonicalState(payload.state)) !== JSON.stringify(canonicalState(state))) throw fault('payload');''')
    text = once(text, "          await request(token, 'PUT', revision, state);", "          pending.mayHaveBeenSent = true;\n          await request(token, 'PUT', revision, state);")
    text = once(text, "          if (error.code !== 'conflict') throw error;", "          if (error.code !== 'conflict') throw error;\n          pending.mayHaveBeenSent = false; // A CAS rejection did not accept this write.")
    text = once(text, "      if (submission) return;", "      if (submission?.mayHaveBeenSent) return;")
    text = once(text, "      // An unresolved write may already be accepted. Never replay it as a draft.", "      // Exclude only a dispatched ambiguous write. A failed preflight GET has\n      // not submitted the user's text and must not destroy the ordinary draft.")
    return text


def patch_sync(text):
    text = once(text, "  function persistMeta() {\n    nativeSet.call(localStorage, META_KEY, JSON.stringify(meta));\n  }", '''  function persistMeta(next = meta) {
    // Storage.setItem can throw (for example, quota). Do not advance in-memory
    // authority until its receipt is durable, or a retry can delete remote data.
    nativeSet.call(localStorage, META_KEY, JSON.stringify(next));
    meta = next;
  }''')
    text = once(text, '  async function requestState() {', '''  async function readStateResponse(options) {
    const controller = typeof AbortController === 'function' ? new AbortController() : null;
    let timer;
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => {
        const error = new Error('Сервер синхронизации не ответил вовремя.');
        error.code = 'sync_timeout';
        reject(error);
        controller?.abort();
      }, 15000);
    });
    try {
      const work = (async () => {
        const response = await fetch('/api/state', {...options, ...(controller ? {signal: controller.signal} : {})});
        const body = await response.json().catch(() => null);
        return {response, body};
      })();
      // Includes stalled response bodies, not just the initial fetch/headers.
      return await Promise.race([work, deadline]);
    } finally { clearTimeout(timer); }
  }

  async function requestState() {''')
    text = once(text, "    const response = await fetch('/api/state', { credentials: 'same-origin', cache: 'no-store' });\n    const body = await response.json().catch(() => null);", "    const {response, body} = await readStateResponse({ credentials: 'same-origin', cache: 'no-store' });")
    text = once(text, "    if (!validStateReply(body, true) || body.ok === false) throw unconfirmedStateReply();", "    if (!validStateReply(body, true) || body.ok === false || body.revision < meta.revision) throw unconfirmedStateReply();")
    text = once(text, "    const response = await fetch('/api/state', {\n      method: 'PUT',", "    const sentRevision = meta.revision;\n    const {response, body} = await readStateResponse({\n      method: 'PUT',")
    text = once(text, "body: JSON.stringify({ state, baseRevision: meta.revision, force: false })", "body: JSON.stringify({ state, baseRevision: sentRevision, force: false })")
    text = once(text, "    const body = await response.json().catch(() => null);\n    if (response.status === 409", "    if (response.status === 409")
    text = once(text, "      if (!validStateReply(body)) throw unconfirmedStateReply();", "      if (!validStateReply(body) || body.revision <= sentRevision) throw unconfirmedStateReply();")
    text = once(text, '''      meta.baseState = normalizeState(body.state);
      nativeSet.call(localStorage, STATE_KEY, JSON.stringify(merged));
      meta.revision = Number(body.revision) || 0;
      persistMeta();''', '''      nativeSet.call(localStorage, STATE_KEY, JSON.stringify(merged));
      persistMeta({...meta, baseState: normalizeState(body.state), revision: body.revision});''')
    text = once(text, '''    if (!validStateReply(body) || body.ok === false || !same(body.state, state)) throw unconfirmedStateReply();
    meta.baseState = clone(state);
    meta.revision = Number(body.revision) || meta.revision;
    meta.lastSyncedAt = body.updatedAt || isoNow();
    persistMeta();''', '''    if (!validStateReply(body) || body.ok !== true || body.revision !== sentRevision + 1 || !same(body.state, state)) throw unconfirmedStateReply();
    persistMeta({...meta, baseState: clone(state), revision: body.revision, lastSyncedAt: body.updatedAt || isoNow()});''')
    text = once(text, '''        meta.baseState = normalizeState(remote.state);
        meta.revision = remoteRevision;
        meta.lastSyncedAt = remote.updatedAt || isoNow();
        nativeSet.call(localStorage, STATE_KEY, JSON.stringify(meta.baseState));
        persistMeta();''', '''        const remoteState = normalizeState(remote.state);
        nativeSet.call(localStorage, STATE_KEY, JSON.stringify(remoteState));
        persistMeta({...meta, baseState: remoteState, revision: remoteRevision, lastSyncedAt: remote.updatedAt || isoNow()});''')
    text = once(text, '''      meta.baseState = normalizeState(remote.state);
      nativeSet.call(localStorage, STATE_KEY, JSON.stringify(merged));
      meta.revision = remoteRevision;
      meta.lastSyncedAt = remote.updatedAt || isoNow();
      persistMeta();''', '''      nativeSet.call(localStorage, STATE_KEY, JSON.stringify(merged));
      persistMeta({...meta, baseState: normalizeState(remote.state), revision: remoteRevision, lastSyncedAt: remote.updatedAt || isoNow()});''')
    text = once(text, '        meta.baseState = clone(remoteState);\n', '')
    text = once(text, '''        meta.revision = Number(remote.revision) || 0;
        meta.lastSyncedAt = remote.updatedAt || isoNow();
        persistMeta();''', '''        persistMeta({...meta, baseState: clone(remoteState), revision: remote.revision, lastSyncedAt: remote.updatedAt || isoNow()});''')
    text = once(text, '        meta.revision = 0;\n        persistMeta();', '        persistMeta({...meta, revision: 0, baseState: null});')
    return text


def patch_storage(text):
    helper = '''  function acceptRemoteState(state, nextMeta) {
    const previous = nativeGet.call(localStorage, STATE_KEY);
    nativeSet.call(localStorage, STATE_KEY, JSON.stringify(state));
    try { persistMeta(nextMeta); }
    catch (error) {
      // A merged remote value must not become an apparent local edit after a
      // quota failure/reload. Restore the previous snapshot with its old receipt.
      try {
        if (previous === null) nativeRemove.call(localStorage, STATE_KEY);
        else nativeSet.call(localStorage, STATE_KEY, previous);
      } catch (_) {
        // Reuse the existing fail-closed recovery surface; never keep uploading
        // an inconsistent pair. A browser that cannot persist must stay open.
        protective = true;
        storageStartupError = true;
        clearTimeout(pushTimer);
        recoveryError = 'Хранилище недоступно. Отправка остановлена. Не закрывайте страницу: скопируйте резервную копию.';
        try { quarantine(state); } catch (_) { pendingLocal = clone(state); }
      }
      throw error;
    }
  }

'''
    text = once(text, '  function maxTimestampMap(', helper+'  function maxTimestampMap(')
    text = once(text, '''      nativeSet.call(localStorage, STATE_KEY, JSON.stringify(merged));
      persistMeta({...meta, baseState: normalizeState(body.state), revision: body.revision});''', '''      acceptRemoteState(merged, {...meta, baseState: normalizeState(body.state), revision: body.revision});''')
    text = once(text, '''        nativeSet.call(localStorage, STATE_KEY, JSON.stringify(remoteState));
        persistMeta({...meta, baseState: remoteState, revision: remoteRevision, lastSyncedAt: remote.updatedAt || isoNow()});''', '''        acceptRemoteState(remoteState, {...meta, baseState: remoteState, revision: remoteRevision, lastSyncedAt: remote.updatedAt || isoNow()});''')
    text = once(text, '''      nativeSet.call(localStorage, STATE_KEY, JSON.stringify(merged));
      persistMeta({...meta, baseState: normalizeState(remote.state), revision: remoteRevision, lastSyncedAt: remote.updatedAt || isoNow()});''', '''      acceptRemoteState(merged, {...meta, baseState: normalizeState(remote.state), revision: remoteRevision, lastSyncedAt: remote.updatedAt || isoNow()});''')
    text = once(text, '''        nativeSet.call(localStorage, STATE_KEY, JSON.stringify(chosen));
        persistMeta({...meta, baseState: clone(remoteState), revision: remote.revision, lastSyncedAt: remote.updatedAt || isoNow()});''', '''        acceptRemoteState(chosen, {...meta, baseState: clone(remoteState), revision: remote.revision, lastSyncedAt: remote.updatedAt || isoNow()});''')
    return text


def patch_sync_confirmation(sync):
    """Keep local edits pending until the state API supplies a valid save receipt."""
    helper = '''  // A successful HTTP status alone is not a state-save receipt (e.g. a
  // truncated response or an HTML login page). Never advance the merge ancestor
  // until the API confirms the snapshot; otherwise a later pull can erase it.
  function validStateReply(body, allowEmpty = false) {
    if (!body || Array.isArray(body) || !Number.isSafeInteger(body.revision) || body.revision < 0) return false;
    if (allowEmpty && body.state === null) return body.revision === 0;
    return body.revision > 0 && body.state && !Array.isArray(body.state)
      && body.state.version === 1 && Array.isArray(body.state.tasks);
  }

  function unconfirmedStateReply() {
    const error = new Error('Некорректный ответ сервера синхронизации.');
    error.code = 'unconfirmed_state';
    return error;
  }

'''
    sync = once(sync, '  async function requestState() {', helper + '  async function requestState() {')
    # Both GET and PUT must preserve HTTP error status when JSON is missing.
    old = '    const body = await response.json().catch(() => ({}));'
    if sync.count(old) != 2:
        raise ValueError('expected two state-response decoders')
    sync = sync.replace(old, '    const body = await response.json().catch(() => null);')
    old = 'new Error(body.message || body.error || `HTTP ${response.status}`)'
    if sync.count(old) != 2:
        raise ValueError('expected two HTTP error handlers')
    sync = sync.replace(old, 'new Error(body?.message || body?.error || `HTTP ${response.status}`)')
    sync = once(sync,
        '    return body;\n  }\n\n  async function sendState',
        '    if (!validStateReply(body, true) || body.ok === false) throw unconfirmedStateReply();\n    return body;\n  }\n\n  async function sendState')
    sync = once(sync,
        '    if (response.status === 409 && retry && body.state) {',
        '    if (response.status === 409 && retry && body?.state) {\n      if (!validStateReply(body)) throw unconfirmedStateReply();')
    sync = once(sync,
        '    meta.baseState = clone(state);',
        '    if (!validStateReply(body) || body.ok === false || !same(body.state, state)) throw unconfirmedStateReply();\n    meta.baseState = clone(state);')
    sync = once(sync,
        '  function setStatus(kind, text) {',
        '''  function setStatus(kind, text) {
    if (kind === 'ok' && queued) {
      kind = 'syncing';
      text = 'Изменения сохранены на этом устройстве. Ожидают отправки на сервер.';
    }''')
    sync = once(sync,
        "      else setStatus('offline', 'Нет связи с сервером. Сохраню и отправлю позже.');",
        "      else if (error.code === 'unconfirmed_state') setStatus('error', 'Сервер не подтвердил сохранение. Изменения остаются на этом устройстве; повторю отправку.');\n      else setStatus('offline', 'Нет связи с сервером. Сохраню и отправлю позже.');")
    return sync


def apply_ai_client(text):
    text = once(text, '  function suspend() {\n    stopSpeech();',
        '  function suspend() {\n    // Reuse the bounded, filtered Manual draft store on reload/mobile discard.\n    // saveDraft excludes unresolved writes and unconfirmed voice transcription.\n    saveDraft();\n    stopSpeech();')
    text = patch_ai(text)
    return once(text, "  function manualTarget() { return '/manual.html?v=20260908-quiet-signal-2'; }",
        "  function manualTarget() { return '/manual.html?v=" + RELEASE_KEY + "'; }")


def apply_sync_client(text):
    text = patch_storage(patch_sync(patch_sync_confirmation(text)))
    return once(text, "  const UPDATE_URL = '/manual.html?v=20260909-sync-stability-2';",
        "  const UPDATE_URL = '/manual.html?v=" + RELEASE_KEY + "';")


def apply_ai_entry(text):
    text = once(text,
        '/ai-home-v2.js?v=20260905-3.1-voice-20260908-speech-1-quiet-signal-2',
        '/ai-home-v2.js?v=' + RELEASE_KEY)
    return once(text, 'href="/manual.html?v=20260908-quiet-signal-2"',
        'href="/manual.html?v=' + RELEASE_KEY + '"')


def apply_manual_entry(text):
    text = once(text, '<script src="sync.js?v=20260909-sync-stability-2"></script>',
        '<script src="sync.js?v=' + RELEASE_KEY + '"></script>')
    return once(text, '<a href="/manual.html" aria-current="page">',
        '<a href="/manual.html?v=' + RELEASE_KEY + '" aria-current="page">')
