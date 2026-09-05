(() => {
  'use strict';

  const API = '/api/state';
  const MAX_REQUESTS = 24;
  const MAX_MESSAGES = 24;
  const POLL_MS = 900;
  const POLL_TIMEOUT_MS = 190000;

  const app = document.getElementById('aiApp');
  const orb = document.getElementById('aiOrb');
  const status = document.getElementById('aiStatus');
  const answer = document.getElementById('aiAnswer');
  const composer = document.getElementById('aiComposer');
  const input = document.getElementById('aiInput');
  const send = document.getElementById('aiSend');
  const auth = document.getElementById('aiAuth');

  let recognition = null;
  let listening = false;
  let busy = false;
  let pollTimer = null;
  let pollStartedAt = 0;
  let pageAlive = true;
  let holdTimer = null;
  let holdOpenedManual = false;

  function nowIso() {
    return new Date().toISOString();
  }

  function requestId() {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
      return `ai2-${crypto.randomUUID()}`;
    }
    return `ai2-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value || {}));
  }

  function rows(value) {
    return Array.isArray(value) ? value.filter(item => item && typeof item === 'object') : [];
  }

  function messages(value) {
    return rows(value).filter(item => {
      const role = String(item.role || '');
      return (role === 'user' || role === 'assistant') && String(item.content || '').trim();
    });
  }

  function latestAssistant(state) {
    const list = messages(state.aiHomeMessages);
    for (let i = list.length - 1; i >= 0; i -= 1) {
      if (list[i].role === 'assistant') return String(list[i].content || '').trim();
    }
    return '';
  }

  function activeRequest(state) {
    const list = rows(state.aiHomeRequests);
    for (let i = list.length - 1; i >= 0; i -= 1) {
      const s = String(list[i].status || 'pending');
      if (s === 'pending' || s === 'processing') return list[i];
    }
    return null;
  }

  function latestError(state) {
    const list = rows(state.aiHomeRequests);
    for (let i = list.length - 1; i >= 0; i -= 1) {
      if (String(list[i].status || '') === 'error') {
        return String(list[i].error || state.aiHomeStatus?.message || '').trim();
      }
    }
    return String(state.aiHomeStatus?.state || '') === 'error'
      ? String(state.aiHomeStatus?.message || '').trim()
      : '';
  }

  function setMode(mode) {
    app.classList.toggle('is-listening', mode === 'listening');
    app.classList.toggle('is-thinking', mode === 'thinking');
    app.classList.toggle('is-error', mode === 'error');
  }

  function setBusy(value) {
    busy = Boolean(value);
    input.disabled = busy;
    send.disabled = busy;
  }

  function setStatus(text, mode = 'idle') {
    status.textContent = text;
    setMode(mode);
  }

  function showAnswer(text) {
    const clean = String(text || '').trim();
    answer.textContent = clean;
    answer.hidden = !clean;
    if (clean) answer.scrollTop = 0;
  }

  function showAuth() {
    auth.hidden = false;
    composer.hidden = true;
    setBusy(true);
    showAnswer('');
    setStatus('Нужен вход.', 'idle');
  }

  function showError(text = 'Не получилось. Попробуй ещё раз.') {
    setBusy(false);
    showAnswer('');
    setStatus(text, 'error');
  }

  async function clearLegacyCaches() {
    try {
      if ('caches' in window) {
        const keys = await caches.keys();
        await Promise.all(keys.map(key => caches.delete(key)));
      }
    } catch (_) {}
    try {
      if ('serviceWorker' in navigator) {
        const regs = await navigator.serviceWorker.getRegistrations();
        await Promise.all(regs.map(reg => reg.unregister().catch(() => false)));
      }
    } catch (_) {}
  }

  async function readState() {
    const response = await fetch(API, {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Accept': 'application/json' }
    });
    if (response.status === 401 || response.status === 403) {
      const error = new Error('auth');
      error.code = 'auth';
      throw error;
    }
    if (!response.ok) throw new Error(`state GET ${response.status}`);
    const payload = await response.json();
    if (!payload || typeof payload !== 'object' || !payload.state || typeof payload.state !== 'object') {
      throw new Error('invalid state payload');
    }
    return {
      revision: Number(payload.revision || 0),
      state: payload.state
    };
  }

  async function writeState(revision, state) {
    const response = await fetch(API, {
      method: 'PUT',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ baseRevision: Number(revision || 0), state })
    });
    if (response.status === 401 || response.status === 403) {
      const error = new Error('auth');
      error.code = 'auth';
      throw error;
    }
    if (response.status === 409) {
      const error = new Error('conflict');
      error.code = 'conflict';
      throw error;
    }
    if (!response.ok) throw new Error(`state PUT ${response.status}`);
    const payload = await response.json();
    if (!payload || payload.ok !== true) throw new Error('state update refused');
    return payload;
  }

  function renderState(state) {
    const active = activeRequest(state);
    if (active) {
      setBusy(true);
      showAnswer('');
      setStatus(String(active.status || '') === 'processing' ? 'Думаю…' : 'Собираю контекст…', 'thinking');
      return { active: true, requestId: String(active.id || '') };
    }

    const error = latestError(state);
    if (error && String(state.aiHomeStatus?.state || '') === 'error') {
      showError('Не получилось. Можно отправить ещё раз.');
      return { active: false, error: true };
    }

    const text = latestAssistant(state);
    setBusy(false);
    showAnswer(text);
    setStatus(text ? 'Что дальше?' : 'Скажи, что происходит.', 'idle');
    return { active: false };
  }

  function stopPolling() {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = null;
    pollStartedAt = 0;
  }

  function schedulePoll(delay = POLL_MS) {
    if (!pageAlive) return;
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(pollOnce, delay);
  }

  async function pollOnce() {
    pollTimer = null;
    if (!pageAlive) return;
    if (pollStartedAt && Date.now() - pollStartedAt > POLL_TIMEOUT_MS) {
      stopPolling();
      showError('Ответ занимает слишком долго. Попробуй ещё раз.');
      return;
    }
    try {
      const { state } = await readState();
      const result = renderState(state);
      if (result.active) schedulePoll();
      else stopPolling();
    } catch (error) {
      if (error && error.code === 'auth') {
        stopPolling();
        showAuth();
        return;
      }
      schedulePoll(1600);
    }
  }

  function startPolling() {
    pollStartedAt = Date.now();
    schedulePoll(450);
  }

  async function enqueue(text) {
    const clean = String(text || '').trim();
    if (!clean || busy) return;

    const lowered = clean.toLocaleLowerCase('ru-RU');
    if (lowered === '/manual' || lowered === 'ручной режим' || lowered === 'открой ручной режим') {
      location.assign('/manual.html');
      return;
    }

    const id = requestId();
    setBusy(true);
    showAnswer('');
    setStatus('Собираю контекст…', 'thinking');

    for (let attempt = 0; attempt < 6; attempt += 1) {
      try {
        const { revision, state: current } = await readState();
        const state = clone(current);
        const requests = rows(state.aiHomeRequests);
        if (!requests.some(item => String(item.id || '') === id)) {
          requests.push({
            id,
            text: clean.slice(0, 12000),
            status: 'pending',
            createdAt: nowIso()
          });
        }
        state.aiHomeRequests = requests.slice(-MAX_REQUESTS);

        const history = messages(state.aiHomeMessages);
        const last = history[history.length - 1];
        if (!last || last.role !== 'user' || String(last.content || '').trim() !== clean) {
          history.push({ role: 'user', content: clean.slice(0, 12000) });
        }
        state.aiHomeMessages = history.slice(-MAX_MESSAGES);
        state.aiHomeStatus = { state: 'queued', requestId: id, updatedAt: nowIso() };

        await writeState(revision, state);
        input.value = '';
        resizeInput();
        startPolling();
        return;
      } catch (error) {
        if (error && error.code === 'conflict') {
          await new Promise(resolve => setTimeout(resolve, 80 + attempt * 70));
          continue;
        }
        if (error && error.code === 'auth') {
          showAuth();
          return;
        }
        console.error(error);
        showError();
        return;
      }
    }
    showError('ДВИЖ сейчас занят синхронизацией. Попробуй ещё раз.');
  }

  function resizeInput() {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 132)}px`;
  }

  function speechCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function stopVoice() {
    if (!recognition) return;
    try { recognition.stop(); } catch (_) {}
  }

  function startVoice() {
    if (busy) return;
    const Ctor = speechCtor();
    if (!Ctor) {
      input.focus();
      setStatus('Голосовой ввод здесь недоступен. Напиши.', 'idle');
      return;
    }
    if (listening && recognition) {
      stopVoice();
      return;
    }

    const instance = new Ctor();
    recognition = instance;
    instance.lang = 'ru-RU';
    instance.continuous = false;
    instance.interimResults = true;
    let finalText = '';

    instance.onstart = () => {
      listening = true;
      setStatus('Слушаю…', 'listening');
    };
    instance.onresult = event => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const part = String(event.results[i][0]?.transcript || '');
        if (event.results[i].isFinal) finalText += part;
        else interim += part;
      }
      input.value = (finalText || interim).trim();
      resizeInput();
    };
    instance.onerror = () => {
      listening = false;
      recognition = null;
      setStatus('Не расслышал. Можно сказать ещё раз.', 'idle');
    };
    instance.onend = () => {
      listening = false;
      recognition = null;
      const text = (finalText || input.value || '').trim();
      if (text) enqueue(text);
      else setStatus('Скажи, что происходит.', 'idle');
    };

    try { instance.start(); }
    catch (_) {
      listening = false;
      recognition = null;
      input.focus();
    }
  }

  function beginManualHold() {
    holdOpenedManual = false;
    if (holdTimer) clearTimeout(holdTimer);
    holdTimer = setTimeout(() => {
      holdOpenedManual = true;
      location.assign('/manual.html');
    }, 1100);
  }

  function cancelManualHold() {
    if (holdTimer) clearTimeout(holdTimer);
    holdTimer = null;
  }

  async function boot() {
    await clearLegacyCaches();
    try {
      const { state } = await readState();
      const result = renderState(state);
      if (result.active) startPolling();
    } catch (error) {
      if (error && error.code === 'auth') showAuth();
      else showError('Не удалось связаться с ДВИЖем.');
    }
  }

  composer.addEventListener('submit', event => {
    event.preventDefault();
    enqueue(input.value);
  });

  input.addEventListener('input', resizeInput);
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      composer.requestSubmit();
    }
  });

  orb.addEventListener('pointerdown', beginManualHold);
  orb.addEventListener('pointerup', cancelManualHold);
  orb.addEventListener('pointercancel', cancelManualHold);
  orb.addEventListener('pointerleave', cancelManualHold);
  orb.addEventListener('click', event => {
    event.preventDefault();
    if (holdOpenedManual) {
      holdOpenedManual = false;
      return;
    }
    startVoice();
  });

  window.addEventListener('pageshow', () => {
    if (!pollTimer && !busy) {
      readState().then(({ state }) => {
        const result = renderState(state);
        if (result.active) startPolling();
      }).catch(() => {});
    }
  });

  window.addEventListener('pagehide', () => {
    pageAlive = false;
    stopPolling();
    stopVoice();
  }, { once: true });

  boot();
})();
