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
  // page has observed an active request or a fresh completion after its first read.
  let responseGateOpen = false;
  let speechBaseline = false;
  const completedSpeechRequests = new Set();
  // Hold the session and current utterance strongly until completion/cancellation.
  let speechOutput = null;
  const controllers = new Set();
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const rows = value => Array.isArray(value) ? value.filter(object) : [];
  const activeRequest = state => rows(state.aiHomeRequests)
    .find(row => ['pending', 'processing'].includes(String(row.status || 'pending')));
  const alive = token => token === epoch && pageAlive && !document.hidden;
  const fault = code => Object.assign(new Error(code), { code });
  const assertAlive = token => { if (!alive(token)) throw fault('cancelled'); };
  const requestId = () => `ai2-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;

  let uiMode = 'idle';
  let speaking = false;
  const ribbon = createRibbon();

  function updateSignal() {
    const mode = speaking ? 'speaking' : uiMode;
    app.classList.toggle('is-speaking', speaking);
    app.setAttribute('data-signal-state', mode);
    ribbon.update(mode, pageAlive && !document.hidden);
  }

  // Decorative enhancement: every browser/renderer failure stays outside the
  // request and microphone paths. A static SVG remains when unavailable.
  function createRibbon() {
    let frame = null, phase = 0, last = null, mode = 'idle', visible = true, failed = false;
    let mesh, reduced; const strips = [];
    const stop = () => {
      if (frame !== null) { try { window.cancelAnimationFrame(frame); } catch (_) {} }
      frame = null; last = null;
    };
    const fail = () => {
      failed = true; stop();
      try { mesh?.setAttribute('data-ready', 'false'); } catch (_) {}
    };
    const draw = () => {
      const amplitude = {idle:44,listening:65,thinking:52,speaking:76,error:16}[mode] || 44;
      const project = (u,t) => {
        const envelope = Math.pow(Math.sin(Math.PI*u),.7);
        const angle = u*Math.PI*3.6-phase*.7;
        const y = Math.sin(u*Math.PI*3-phase)*amplitude*envelope;
        const z = Math.cos(u*Math.PI*3-phase)*45*envelope;
        const yy = y+t*54*envelope*Math.cos(angle), zz = z+t*54*envelope*Math.sin(angle);
        const perspective = 720/(720-zz);
        return [500+(u*920-460)*perspective,150+yy*perspective,zz];
      };
      const ordered = strips.map((p,j) => {
        const lo=j/32*2-1, hi=(j+1)/32*2-1, points=[]; let depth=0;
        for(let i=0;i<=80;i++){const q=project(i/80,lo);points.push(q);depth+=q[2];}
        for(let i=80;i>=0;i--)points.push(project(i/80,hi));
        p.setAttribute('d',points.map((q,i)=>(i?'L':'M')+q[0].toFixed(2)+','+q[1].toFixed(2)).join('')+'Z');
        const shine=Math.pow(Math.max(0,Math.cos((lo+.22)*2.1)),5);
        p.style.fill='hsl('+(199+j/32*40)+' 36% '+(32+shine*48+j/32*8)+'%)';
        p.style.opacity=.7+shine*.26;
        return {p,depth};
      });
      ordered.sort((a,b)=>a.depth-b.depth).forEach(x=>mesh.append(x.p));
      mesh.setAttribute('data-ready', 'true');
    };
    const tick = time => {
      frame = null;
      if (failed || !visible || document.hidden || reduced?.matches) return;
      try {
        phase += Math.min(Math.max(time-(last ?? time),0),50)*(mode==='idle'?.0003:.0008);
        last=time; draw(); frame=window.requestAnimationFrame(tick);
      } catch (_) { fail(); }
    };
    const update = (next=mode, active=visible) => {
      mode=next; visible=active; stop();
      if(failed || !mesh || !visible || document.hidden) return;
      try {
        draw();
        if(!reduced?.matches && mode!=='error' && typeof window.requestAnimationFrame==='function' && typeof window.cancelAnimationFrame==='function') frame=window.requestAnimationFrame(tick);
      } catch (_) { fail(); }
    };
    try {
      mesh=document.getElementById('aiRibbonMesh');
      mesh?.setAttribute('data-ready', 'false');
      if(mesh && document.createElementNS) {
        reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)');
        for(let j=0;j<32;j++){const p=document.createElementNS('http://www.w3.org/2000/svg','path');mesh.append(p);strips.push(p);}
        if(reduced?.addEventListener) reduced.addEventListener('change',()=>update());
        else reduced?.addListener?.(()=>update());
      } else mesh=null;
    } catch (_) { fail(); }
    return {update};
  }

  function controls() {
    input.disabled = busy || Boolean(voice);
    send.disabled = busy || Boolean(voice);
    orb.setAttribute('aria-pressed', String(Boolean(voice)));
    orb.setAttribute('aria-label', voice ? 'Остановить запись' : 'Говорить с ДВИЖем');
  }

  function setBusy(value) {
    busy = value;
    controls();
  }

  function setStatus(text, mode = 'idle') {
    if (status.textContent !== text) status.textContent = text;
    uiMode = mode;
    updateSignal();
    for (const name of ['listening', 'thinking', 'error']) {
      app.classList.toggle(`is-${name}`, mode === name);
    }
  }

  function showAnswer(text = '') {
    const clean = String(text).trim();
    // Do not reset the user's scroll or live region on an unchanged answer.
    const changed = answer.textContent !== clean || answer.hidden;
    if (answer.textContent !== clean) {
      answer.textContent = clean;
      answer.scrollTop = 0;
    }
    answer.hidden = !clean;
    if (clean && changed) { try { answer.scrollIntoView?.({block: 'nearest', behavior: 'instant'}); } catch (_) {} }
  }

  function hideSavedAnswer(text = '') {
    const clean = String(text).trim();
    // Keep literal text stable for safe DOM semantics, but never expose a
    // persisted answer visually or to accessibility on a fresh page session.
    if (answer.textContent !== clean) answer.textContent = clean;
    answer.hidden = true;
  }

  function stopSpeech() {
    const session = speechOutput;
    speaking = false;
    updateSignal();
    speechOutput = null; // Invalidate callbacks before cancel(), which may fire events.
    if (session?.utterance) {
      session.utterance.onstart = session.utterance.onend = session.utterance.onerror = null;
      session.utterance = null;
    }
    try { window.speechSynthesis?.cancel(); } catch (_) {}
  }

  function speakAnswer(text) {
    stopSpeech();
    try {
      const synth = window.speechSynthesis;
      const Ctor = window.SpeechSynthesisUtterance;
      if (!synth || typeof synth.speak !== 'function' || typeof Ctor !== 'function') return;
      const session = { utterance: null, offset: 0 };
      speechOutput = session;
      const next = () => {
        if (speechOutput !== session || !alive(epoch) || voice) return;
        if (session.offset >= text.length) { speechOutput = null; return; }
        try {
          // Bound each browser utterance without dropping any text. Prefer a
          // word boundary and never split a UTF-16 surrogate pair.
          let end = Math.min(session.offset + 220, text.length);
          if (end < text.length) {
            const segment = text.slice(session.offset, end);
            const boundary = Math.max(segment.lastIndexOf(' '), segment.lastIndexOf('\n'));
            if (boundary > 0) end = session.offset + boundary + 1;
            else if (/[\uD800-\uDBFF]/.test(text[end - 1])) end--;
          }
          const utterance = new Ctor(text.slice(session.offset, end));
          session.offset = end;
          session.utterance = utterance;
          utterance.lang = 'ru-RU';
          // Requery for each chunk/reply: voices may initially be empty. The
          // language hint safely uses the browser default until voices load.
          try {
            const voices = Array.from(synth.getVoices?.() || []);
            const russian = voices.find(item => /^ru[-_]ru$/i.test(item.lang))
              || voices.find(item => /^ru(?:[-_]|$)/i.test(item.lang));
            if (russian) utterance.voice = russian;
          } catch (_) {}
          utterance.onstart = () => {
            if (speechOutput !== session || session.utterance !== utterance || !alive(epoch)) return;
            speaking = true; updateSignal();
          };
          utterance.onend = () => {
            if (speechOutput !== session || session.utterance !== utterance) return;
            speaking = false; updateSignal();
            utterance.onstart = utterance.onend = utterance.onerror = null;
            session.utterance = null;
            next();
          };
          utterance.onerror = () => {
            if (speechOutput === session && session.utterance === utterance) stopSpeech();
          };
          synth.speak(utterance);
        } catch (_) { if (speechOutput === session) stopSpeech(); }
      };
      next();
    } catch (_) { stopSpeech(); }
  }

  function observeSpeech(state) {
    const ready = state.aiHomeStatus;
    const id = ready?.state === 'ready' && ready.requestId;
    if (!speechBaseline) {
      speechBaseline = true;
      if (id) completedSpeechRequests.add(id);
      return; // The first snapshot is history, even if it has a ready answer.
    }
    if (!id || completedSpeechRequests.has(id)) return;
    completedSpeechRequests.add(id); // Errors/cancellation must never replay it.
    const last = rows(state.aiHomeMessages).filter(row => row.role === 'assistant').at(-1);
    const text = String(last?.content || '').trim();
    if (!text) return;
    responseGateOpen = true;
    speakAnswer(text);
  }

  function resizeInput() {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 132)}px`;
  }

  function viewport() {
    if (!alive(epoch)) return;
    const view = window.visualViewport;
    if (view && view.scale !== 1) return;
    app.style.setProperty('--ai-top', `${Math.round(view?.offsetTop || 0)}px`);
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
    stopSpeech();
    stopPolling();
    cancelVoice();
    authLink.href = authTarget();
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
    observeSpeech(state);
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
      const saved = rows(state.aiHomeMessages).filter(row => row.role === 'assistant').at(-1);
      hideSavedAnswer(saved?.content || '');
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
    stopSpeech();
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

  function microphoneDevices() {
    // Some embedded/test environments expose navigator through a throwing
    // getter. Treat that exactly like a browser without getUserMedia support.
    try { return globalThis.navigator?.mediaDevices || null; }
    catch (_) { return null; }
  }

  function stopMicrophoneStream(stream) {
    try {
      for (const track of Array.from(stream?.getTracks?.() || [])) track.stop?.();
    } catch (_) {}
  }

  function microphoneErrorText(error) {
    const name = String(error?.name || '');
    if (['NotAllowedError', 'PermissionDeniedError', 'SecurityError'].includes(name)) {
      return 'Микрофон запрещён для этого сайта. Разреши его в настройках браузера.';
    }
    if (name === 'NotFoundError') return 'Микрофон не найден на устройстве.';
    if (['NotReadableError', 'AbortError'].includes(name)) return 'Микрофон занят или временно недоступен.';
    return 'Не удалось открыть микрофон. Можно написать.';
  }

  function cancelVoice(restore = true) {
    const session = voice;
    if (!session) return;
    voice = null;
    const instance = session.instance;
    if (instance) {
      instance.onstart = instance.onresult = instance.onerror = instance.onend = null;
      try { instance.abort(); } catch (_) {}
    }
    if (restore) { input.value = session.draft; resizeInput(); }
    controls();
  }

  async function beginVoice(session, Ctor) {
    const current = () => voice === session && alive(session.token);
    const media = microphoneDevices();
    if (!media || typeof media.getUserMedia !== 'function') {
      cancelVoice();
      input.focus();
      setStatus('Безопасный доступ к микрофону недоступен. Можно написать.', 'error');
      return;
    }
    let stream = null;
    try {
      setStatus('Разрешаю микрофон…', 'listening');
      stream = await media.getUserMedia({ audio: true });
    } catch (error) {
      if (!current()) return;
      cancelVoice();
      setStatus(microphoneErrorText(error), 'error');
      return;
    } finally {
      // Recognition owns its capture; release even after cancellation/pagehide.
      stopMicrophoneStream(stream);
    }
    if (!current()) return;

    let instance;
    try { instance = new Ctor(); }
    catch (_) {
      if (current()) { cancelVoice(); setStatus('Не удалось включить распознавание речи. Можно написать.', 'error'); }
      return;
    }
    if (!current()) return;
    session.instance = instance;
    instance.lang = 'ru-RU';
    instance.continuous = false;
    instance.interimResults = true;
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
        ? 'Распознавание речи заблокировано браузером. Проверь доступ к микрофону.'
        : 'Не расслышал. Можно сказать ещё раз.', 'error');
    };
    instance.onend = () => {
      if (!current()) return;
      const text = session.finalText;
      cancelVoice(!text);
      if (text) { input.value = combined(text); resizeInput(); enqueue(input.value); }
      else setStatus('Не расслышал. Можно сказать ещё раз.');
    };
    try { instance.start(); }
    catch (_) {
      if (current()) { cancelVoice(); input.focus(); setStatus('Не удалось включить распознавание речи. Можно написать.', 'error'); }
    }
  }

  function startVoice() {
    if (voice) {
      if (voice.instance) {
        try { voice.instance.stop(); } catch (_) { cancelVoice(); setStatus(''); }
      } else {
        // A second tap while Android/browser permission UI is pending is cancel.
        cancelVoice();
        setStatus('');
      }
      return;
    }
    if (busy || operation || !alive(epoch)) return;
    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Ctor) {
      input.focus();
      setStatus('Голосовой ввод здесь недоступен. Напиши.');
      return;
    }
    stopSpeech();
    const session = { instance: null, token: epoch, draft: input.value, finalText: '' };
    voice = session; // Reserve before any permission promise or recognizer callback.
    controls();
    void beginVoice(session, Ctor);
  }

  function cancelManualHold() {
    holdStartedAt = null;
  }

  function suspend() {
    stopSpeech();
    pageAlive = false;
    updateSignal();
    epoch += 1;
    clearPoll();
    cancelManualHold();
    cancelVoice();
    for (const controller of controllers) controller.abort();
    controllers.clear();
    operation = null;
  }

  function resume() {
    // BFCache already retains the draft in the DOM; consume its storage copy.
    try { window.sessionStorage?.removeItem(DRAFT_KEY); } catch (_) {}
    pageAlive = true;
    updateSignal();
    viewport();
    sync();
  }

  function authTarget() {
    const raw = String(location.pathname || '/');
    const path = raw.length > 1 ? raw.replace(/\/+$/, '') : raw;
    return path === '/' || path === '/index.html' ? '/manual.html' : '/';
  }

  const DRAFT_KEY = 'dvizh.ai-home-v2.manual-draft';
  const DRAFT_TTL = 10 * 60 * 1000;
  const safeDraft = text => typeof text === 'string' && text.length <= 12000 &&
    !/(?:password|пароль|secret|token|api[_ -]?key|authorization|bearer|sk-[a-z0-9]|-----BEGIN .*PRIVATE KEY)/i.test(text) &&
    !/(?:eyJ[\w-]+\.[\w-]+\.[\w-]+|[A-Za-z0-9_+\/=-]{32,})/.test(text) &&
    !['/manual', 'ручной режим', 'открой ручной режим'].includes(text.trim().toLocaleLowerCase('ru-RU'));
  function saveDraft() {
    try {
      const storage = window.sessionStorage;
      storage?.removeItem(DRAFT_KEY);
      // An unresolved write may already be accepted. Never replay it as a draft.
      if (submission) return;
      const text = voice ? voice.draft : input.value;
      if (text.trim() && safeDraft(text)) storage?.setItem(DRAFT_KEY, JSON.stringify({text, expires:Date.now()+DRAFT_TTL}));
    } catch (_) {} // Disabled storage must never prevent navigation.
  }
  function restoreDraft() {
    try {
      const storage = window.sessionStorage, raw = storage?.getItem(DRAFT_KEY);
      storage?.removeItem(DRAFT_KEY); // One return only; never retain a submitted draft.
      if (!raw || raw.length > 75000) return;
      const value = JSON.parse(raw);
      if (safeDraft(value.text) && Number.isFinite(value.expires) && value.expires > Date.now() && value.expires <= Date.now()+DRAFT_TTL) input.value=value.text;
    } catch (_) {}
  }
  function manualTarget() { return '/manual.html?v=20260908-quiet-signal-2'; }

  function openManual() {
    saveDraft();
    suspend();
    location.assign(manualTarget());
  }
  document.getElementById('aiManual')?.addEventListener('click', event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault(); openManual();
  });
  restoreDraft();
  resizeInput();
  updateSignal();

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
  window.visualViewport?.addEventListener('scroll', viewport);
  viewport();
  sync();
})();
