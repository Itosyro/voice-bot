(() => {
  'use strict';

  const API = '/api/state';
  const HTTP_TIMEOUT_MS = 15000;
  const POLL_MS = 900;
  const POLL_TIMEOUT_MS = 190000;
  const MAX_ROWS = 24;
  const app = document.getElementById('aiApp');
  const orb = document.getElementById('aiOrb');
  const status = document.getElementById('aiStatus');
  const answer = document.getElementById('aiAnswer');
  const composer = document.getElementById('aiComposer');
  const input = document.getElementById('aiInput');
  const send = document.getElementById('aiSend');
  const auth = document.getElementById('aiAuth');
  const authLink = document.getElementById('aiAuthLink');
  if (![app, orb, status, answer, composer, input, send, auth, authLink].every(Boolean)) return;

  // One operation per visible page. The epoch invalidates every late callback.
  let epoch = 0;
  let pageAlive = true;
  let operation = null;
  let busy = false;
  let voice = null;
  let submission = null;
  let pollTimer = null;
  let pollDeadline = 0;
  let holdStartedAt = null;
  let holdOpenedManual = false;
  // A fresh page session starts visually empty. Open this gate only after this
  // page has observed an active request (including one resumed after reload).
  let responseGateOpen = false;
  const controllers = new Set();
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const rows = value => Array.isArray(value) ? value.filter(object) : [];
  const activeRequest = state => rows(state.aiHomeRequests)
    .find(row => ['pending', 'processing'].includes(String(row.status || 'pending')));
  const alive = token => token === epoch && pageAlive && !document.hidden;
  const fault = code => Object.assign(new Error(code), { code });
  const assertAlive = token => { if (!alive(token)) throw fault('cancelled'); };
  const requestId = () => `ai2-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;

  function controls() {
    input.disabled = busy || Boolean(voice);
    send.disabled = busy || Boolean(voice);
    orb.setAttribute('aria-pressed', String(Boolean(voice)));
  }

  function setBusy(value) {
    busy = value;
    controls();
  }

  function setStatus(text, mode = 'idle') {
    if (status.textContent !== text) status.textContent = text;
    for (const name of ['listening', 'thinking', 'error']) {
      app.classList.toggle(`is-${name}`, mode === name);
    }
  }

  function showAnswer(text = '') {
    const clean = String(text).trim();
    // Do not reset the user's scroll or live region on an unchanged answer.
    if (answer.textContent !== clean) {
      answer.textContent = clean;
      answer.scrollTop = 0;
    }
    answer.hidden = !clean;
  }

  function resizeInput() {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 132)}px`;
  }

  function viewport() {
    if (!alive(epoch)) return;
    const view = window.visualViewport;
    if (view && view.scale !== 1) return;
    app.style.setProperty('--ai-height', `${Math.round(view?.height || window.innerHeight)}px`);
  }

  function clearPoll() {
    if (pollTimer !== null) clearTimeout(pollTimer);
    pollTimer = null;
  }

  function stopPolling() {
    clearPoll();
    pollDeadline = 0;
  }

  function showError(text = 'Не удалось подтвердить отправку. Текст сохранён; повторная попытка сначала проверит запрос.') {
    stopPolling();
    setBusy(false);
    setStatus(text, 'error');
  }

  function showAuth() {
    stopPolling();
    cancelVoice();
    authLink.href = manualTarget();
    auth.hidden = false;
    composer.hidden = true;
    setBusy(true);
    showAnswer();
    setStatus('Нужен вход.');
  }

  async function request(token, method = 'GET', revision, state) {
    assertAlive(token);
    const controller = new AbortController();
    controllers.add(controller);
    let timedOut = false;
    // Only a network deadline: never an animation or DOM repair loop.
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, HTTP_TIMEOUT_MS);
    try {
      const options = {
        method, credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
        headers: { Accept: 'application/json' }
      };
      if (method === 'PUT') {
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify({ baseRevision: revision, state });
      }
      const response = await fetch(API, options);
      assertAlive(token);
      if ([401, 403].includes(response.status)) throw fault('auth');
      if (response.status === 409) throw fault('conflict');
      if (!response.ok) throw fault('network');
      const payload = await response.json();
      assertAlive(token);
      if (!object(payload)) throw fault('payload');
      if (method === 'PUT') {
        if (payload.ok !== true) throw fault('payload');
      } else if (!object(payload.state) || !Number.isSafeInteger(payload.revision) || payload.revision < 0) {
        throw fault('payload');
      }
      return payload;
    } catch (error) {
      if (!alive(token)) throw fault('cancelled');
      if (timedOut) throw fault('timeout');
      throw error;
    } finally {
      clearTimeout(timer);
      controllers.delete(controller);
    }
  }

  function schedulePoll(delay = POLL_MS) {
    clearPoll();
    if (!alive(epoch)) return;
    pollTimer = setTimeout(() => { pollTimer = null; sync(); }, delay);
  }

  function acknowledge(state) {
    if (!submission || !rows(state.aiHomeRequests).some(row => row.id === submission.id)) return;
    if (input.value.trim() === submission.text) {
      input.value = '';
      resizeInput();
    }
    submission = null;
  }

  function render(state) {
    auth.hidden = true;
    composer.hidden = false;
    acknowledge(state);
    if (activeRequest(state)) {
      responseGateOpen = true;
      showAnswer();
      if (!pollDeadline) pollDeadline = Date.now() + POLL_TIMEOUT_MS;
      if (Date.now() >= pollDeadline) {
        showError('Ответ ещё не пришёл. Запрос не отправлен повторно. Вернись на экран, чтобы проверить ответ.');
        return;
      }
      setBusy(true);
      setStatus('Думаю…', 'thinking');
      schedulePoll();
      return;
    }
    stopPolling();
    setBusy(false);
    // Do not resurrect a saved answer/error just because a new page session
    // performed its initial state read. The home must enter visually empty.
    if (!responseGateOpen) {
      showAnswer();
      setStatus('');
      return;
    }
    if (state.aiHomeStatus?.state === 'error') {
      showAnswer();
      showError('ИИ не смог ответить. Можно отправить сообщение ещё раз.');
      return;
    }
    const last = rows(state.aiHomeMessages).filter(row => row.role === 'assistant').at(-1);
    showAnswer(last?.content || '');
    setStatus('');
  }

  async function run(task) {
    if (operation || !alive(epoch)) return;
    const job = { token: epoch };
    operation = job;
    try {
      await task(job.token);
    } catch (error) {
      if (!alive(job.token)) return;
      if (error.code === 'auth') showAuth();
      else if (pollDeadline && Date.now() < pollDeadline) {
        setStatus('Связь прервалась. Проверяю ответ…', 'thinking');
        schedulePoll(1600);
      } else showError();
    } finally {
      if (operation === job) operation = null;
    }
  }

  function sync() {
    if (voice) return;
    return run(async token => {
      setBusy(true);
      const { state } = await request(token);
      render(state);
    });
  }

  function enqueue(text) {
    const clean = String(text || '').trim().slice(0, 12000);
    if (['/manual', 'ручной режим', 'открой ручной режим'].includes(clean.toLocaleLowerCase('ru-RU'))) {
      openManual();
      return;
    }
    if (!clean || busy || voice || operation || !alive(epoch)) return;
    clearPoll();
    return run(async token => {
      setBusy(true);
      showAnswer();
      setStatus('Думаю…', 'thinking');
      // Retain the id after an ambiguous PUT failure. Never blindly replay a write.
      if (!submission || submission.text !== clean) submission = { id: requestId(), text: clean };
      const pending = submission;
      for (let attempt = 0; attempt < 6; attempt += 1) {
        const { revision, state: current } = await request(token);
        if (rows(current.aiHomeRequests).some(row => row.id === pending.id) || activeRequest(current)) {
          render(current);
          return;
        }
        const state = JSON.parse(JSON.stringify(current));
        state.aiHomeRequests = [...rows(state.aiHomeRequests), {
          id: pending.id, text: pending.text, status: 'pending', createdAt: new Date().toISOString()
        }].slice(-MAX_ROWS);
        state.aiHomeMessages = [...rows(state.aiHomeMessages), { role: 'user', content: pending.text }].slice(-MAX_ROWS);
        state.aiHomeStatus = { state: 'queued', requestId: pending.id, updatedAt: new Date().toISOString() };
        try {
          await request(token, 'PUT', revision, state);
          acknowledge(state);
          pollDeadline = Date.now() + POLL_TIMEOUT_MS;
          render(state);
          return;
        } catch (error) {
          if (error.code !== 'conflict') throw error;
        }
      }
      showError('ДВИЖ занят синхронизацией. Текст сохранён, попробуй ещё раз.');
    });
  }

  function cancelVoice(restore = true) {
    const session = voice;
    if (!session) return;
    voice = null;
    const instance = session.instance;
    instance.onstart = instance.onresult = instance.onerror = instance.onend = null;
    try { instance.abort(); } catch (_) {}
    if (restore) { input.value = session.draft; resizeInput(); }
    controls();
  }

  function startVoice() {
    if (voice) {
      try { voice.instance.stop(); } catch (_) { cancelVoice(); setStatus(''); }
      return;
    }
    if (busy || operation || !alive(epoch)) return;
    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Ctor) {
      input.focus();
      setStatus('Голосовой ввод здесь недоступен. Напиши.');
      return;
    }
    let instance;
    try { instance = new Ctor(); }
    catch (_) { setStatus('Не удалось включить микрофон. Напиши.'); return; }
    const session = { instance, token: epoch, draft: input.value, finalText: '' };
    voice = session; // Reserve before onstart: rapid taps cannot start two microphones.
    controls();
    instance.lang = 'ru-RU';
    instance.continuous = false;
    instance.interimResults = true;
    const current = () => voice === session && alive(session.token);
    const combined = text => [session.draft.trim(), text.trim()].filter(Boolean).join(' ').slice(0, 12000);
    instance.onstart = () => { if (current()) setStatus('Слушаю…', 'listening'); };
    instance.onresult = event => {
      if (!current()) return;
      const final = [], interim = [];
      for (const result of Array.from(event.results)) {
        (result.isFinal ? final : interim).push(String(result[0]?.transcript || ''));
      }
      session.finalText = final.join(' ').trim();
      input.value = combined([...final, ...interim].join(' '));
      resizeInput();
    };
    instance.onerror = event => {
      if (!current()) return;
      cancelVoice();
      setStatus(['not-allowed', 'service-not-allowed'].includes(event.error)
        ? 'Нет доступа к микрофону. Можно написать.' : 'Не расслышал. Можно сказать ещё раз.');
    };
    instance.onend = () => {
      if (!current()) return;
      const text = session.finalText;
      cancelVoice(!text);
      if (text) { input.value = combined(text); resizeInput(); enqueue(input.value); }
      else setStatus('Не расслышал. Можно сказать ещё раз.');
    };
    try { instance.start(); }
    catch (_) { cancelVoice(); input.focus(); setStatus('Не удалось включить микрофон. Напиши.'); }
  }

  function cancelManualHold() {
    holdStartedAt = null;
  }

  function suspend() {
    pageAlive = false;
    epoch += 1;
    clearPoll();
    cancelManualHold();
    cancelVoice();
    for (const controller of controllers) controller.abort();
    controllers.clear();
    operation = null;
  }

  function resume() {
    pageAlive = true;
    viewport();
    sync();
  }

  function manualTarget() {
    const raw = String(location.pathname || '/');
    const path = raw.length > 1 ? raw.replace(/\/+$/, '') : raw;
    return path === '/' || path === '/index.html' ? '/manual.html' : '/';
  }

  function openManual() {
    suspend();
    location.assign(manualTarget());
  }

  composer.addEventListener('submit', event => { event.preventDefault(); enqueue(input.value); });
  input.addEventListener('input', resizeInput);
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
      event.preventDefault();
      composer.requestSubmit();
    }
  });
  orb.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    cancelManualHold();
    holdOpenedManual = false;
    holdStartedAt = performance.now();
  });
  orb.addEventListener('pointerup', () => {
    if (holdStartedAt === null) return;
    const heldFor = performance.now() - holdStartedAt;
    cancelManualHold();
    if (heldFor >= 1100) { holdOpenedManual = true; openManual(); }
  });
  for (const type of ['pointercancel', 'pointerleave']) orb.addEventListener(type, cancelManualHold);
  orb.addEventListener('contextmenu', event => event.preventDefault());
  orb.addEventListener('click', event => {
    event.preventDefault();
    if (holdOpenedManual) { holdOpenedManual = false; return; }
    startVoice();
  });
  window.addEventListener('keydown', event => {
    if (event.altKey && event.code === 'KeyM') { event.preventDefault(); openManual(); }
    if (event.key === 'Escape' && voice) { cancelVoice(); setStatus(''); }
  });
  window.addEventListener('pagehide', suspend);
  window.addEventListener('pageshow', event => { if (event.persisted || !pageAlive) resume(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) suspend(); else resume(); });
  window.addEventListener('online', () => { if (alive(epoch)) sync(); });
  window.addEventListener('resize', viewport);
  window.visualViewport?.addEventListener('resize', viewport);
  viewport();
  sync();
})();
