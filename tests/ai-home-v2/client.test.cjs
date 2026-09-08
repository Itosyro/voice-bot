'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../ai-home-v2/ai-home-v2.js'), 'utf8');
const copy = value => JSON.parse(JSON.stringify(value));
const settle = async () => { for (let i = 0; i < 12; i++) await new Promise(setImmediate); };
const reply = (payload, status = 200) => ({ status, ok: status >= 200 && status < 300, json: async () => copy(payload) });
const active = () => ({ aiHomeRequests: [{ id: 'existing', text: 'test', status: 'processing' }] });
const done = () => ({ aiHomeRequests: [{ id: 'existing', status: 'done' }], aiHomeMessages: [{ role: 'assistant', content: 'Готово' }], aiHomeStatus: { state: 'ready' } });

class Target {
  constructor() { this.listeners = new Map(); }
  addEventListener(name, fn) {
    const list = this.listeners.get(name) || [];
    list.push(fn); this.listeners.set(name, list);
  }
  emit(name, detail = {}) {
    const event = { button: 0, preventDefault() { this.prevented = true; }, ...detail };
    for (const fn of this.listeners.get(name) || []) fn(event);
    return event;
  }
}
class Element extends Target {
  constructor() {
    super(); this.textContent = ''; this.value = ''; this.hidden = false;
    this.disabled = false; this.scrollTop = 0; this.scrollHeight = 52;
    this.attributes = {}; this.classes = new Set();
    this.classList = { toggle: (name, enabled) => enabled ? this.classes.add(name) : this.classes.delete(name) };
    this.style = { setProperty(name, value) { this[name] = value; } };
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  focus() { this.focused = true; }
  requestSubmit() { this.emit('submit'); }
  set innerHTML(_) { throw Error('HTML injection is forbidden'); }
}
function make({ state = {}, handler, speech = true, hidden = false, autoStart = true, mediaDevices, pathname = '/ai-home-v2-preview.html', setup } = {}) {
  const clock = { now: 1000, next: 0, timers: new Map() };
  const setTimer = (fn, delay) => { const id = ++clock.next; clock.timers.set(id, { at: clock.now + delay, fn }); return id; };
  clock.advance = async ms => {
    const until = clock.now + ms;
    while (true) {
      const next = [...clock.timers].filter(([, task]) => task.at <= until).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      clock.now = next[1].at; clock.timers.delete(next[0]); next[1].fn(); await settle();
    }
    clock.now = until; await settle();
  };
  const document = new Target(); document.hidden = hidden;
  const elements = Object.fromEntries(['aiApp','aiOrb','aiStatus','aiAnswer','aiComposer','aiInput','aiSend','aiAuth','aiAuthLink'].map(id => [id, new Element()]));
  document.getElementById = id => elements[id];
  elements.aiAnswer.hidden = elements.aiAuth.hidden = true;
  const window = new Target(); window.innerHeight = 800;
  window.visualViewport = new Target(); Object.assign(window.visualViewport, { scale: 1, height: 800 });
  const recognitions = [];
  class Recognition {
    constructor() { recognitions.push(this); this.started = this.stopped = this.aborted = 0; }
    start() { this.started++; if (autoStart) this.onstart?.(); }
    stop() { this.stopped++; }
    abort() { this.aborted++; this.onend?.(); }
    result(text, final = true) {
      const row = [{ transcript: text }]; row.isFinal = final;
      this.onresult?.({ resultIndex: 0, results: [row] });
    }
  }
  if (speech) window.SpeechRecognition = Recognition;
  const store = { revision: 1, state: copy(state) };
  const calls = [], navigations = [];
  let sequence = 0;
  function normal(options) {
    if (options.method === 'GET') return reply(store);
    const payload = JSON.parse(options.body);
    if (payload.baseRevision !== store.revision) return reply({}, 409);
    store.state = payload.state; store.revision++;
    return reply({ ok: true, revision: store.revision });
  }
  const fetch = async (url, options) => {
    calls.push({ url, ...options });
    return (handler ? await handler({ url, options, store, normal: () => normal(options) }) : undefined) || normal(options);
  };
  class ClockDate extends Date {
    constructor(...args) { super(...(args.length ? args : [clock.now])); }
    static now() { return clock.now; }
  }
  const sandbox = { window, document, fetch, location: { pathname, assign: url => navigations.push(url) },
    AbortController, console, performance: { now: () => clock.now }, Date: ClockDate, setTimeout: setTimer, clearTimeout: id => clock.timers.delete(id),
    crypto: { randomUUID: () => `test-${++sequence}` } };
  Object.defineProperty(sandbox, 'caches', { get() { throw Error('shared caches accessed'); } });
  Object.defineProperty(sandbox, 'navigator', { get() {
    return { mediaDevices: mediaDevices === undefined ? { getUserMedia: async () => ({ getTracks: () => [] }) } : mediaDevices,
      get serviceWorker() { throw Error('service worker accessed'); } };
  } });
  setup?.({ window, document, elements, sandbox });
  vm.runInNewContext(source, sandbox);
  const send = async text => { elements.aiInput.value = text; elements.aiComposer.emit('submit'); await settle(); };
  const hide = () => { document.hidden = true; document.emit('visibilitychange'); };
  const show = () => { document.hidden = false; document.emit('visibilitychange'); };
  const puts = () => calls.filter(call => call.method === 'PUT');
  return { ...elements, window, document, store, calls, clock, send, puts, hide, show, recognitions, navigations };
}

test('stable root primes permission and stops every track before recognition, then shows answer', async () => {
  let resolve, asked = 0, stopped = 0;
  const h = make({ pathname: '/', mediaDevices: { getUserMedia(options) {
    assert.deepEqual(copy(options), { audio: true }); asked++;
    return new Promise(done => { resolve = done; });
  } } });
  await settle(); h.aiOrb.emit('click'); await settle();
  assert.equal(asked, 1); assert.equal(h.recognitions.length, 0);
  resolve({ getTracks: () => [1, 2].map(() => ({ stop() {
    assert.equal(h.recognitions.length, 0); stopped++;
  } })) });
  await settle(); assert.equal(stopped, 2);
  assert.equal(h.recognitions[0].started, 1); assert.ok(h.aiApp.classes.has('is-listening'));
  h.recognitions[0].result('Голос'); h.recognitions[0].onend(); await settle();
  assert.equal(h.puts().length, 1); assert.equal(h.store.state.aiHomeRequests[0].text, 'Голос');
  assert.ok(h.aiApp.classes.has('is-thinking'));
  h.store.state = done(); await h.clock.advance(900);
  assert.equal(h.aiAnswer.hidden, false); assert.equal(h.aiAnswer.textContent, 'Готово');
  assert.equal(h.clock.timers.size, 0);
});

for (const name of ['NotAllowedError', 'SecurityError', 'NotFoundError', 'NotReadableError', 'AbortError', 'UnknownError']) {
  test(`permission ${name} never starts recognition and text still works`, async () => {
    const h = make({ pathname: '/', mediaDevices: { getUserMedia: async () => { throw Object.assign(Error('permission'), { name }); } } });
    await settle(); h.aiInput.value = 'Черновик'; h.aiOrb.emit('click'); await settle();
    assert.equal(h.recognitions.length, 0); assert.equal(h.puts().length, 0);
    assert.equal(h.aiInput.value, 'Черновик'); assert.equal(h.aiInput.disabled, false);
    assert.ok(h.aiApp.classes.has('is-error')); assert.equal(h.clock.timers.size, 0);
    await h.send('Текст'); assert.equal(h.puts().length, 1);
  });
}
for (const cancel of ['tap', 'escape', 'hide']) test(`late permission after ${cancel} releases tracks without recognition`, async () => {
  let resolve, stopped = 0;
  const h = make({ mediaDevices: { getUserMedia: () => new Promise(done => { resolve = done; }) } });
  await settle(); h.aiOrb.emit('click'); await settle();
  if (cancel === 'tap') h.aiOrb.emit('click');
  else if (cancel === 'escape') h.window.emit('keydown', { key: 'Escape' });
  else h.hide();
  resolve({ getTracks: () => [{ stop() { stopped++; } }] }); await settle();
  assert.equal(stopped, 1); assert.equal(h.recognitions.length, 0);
  assert.equal(h.puts().length, 0); assert.equal(h.clock.timers.size, 0);
});
test('text at stable root does not request microphone and unsupported speech stays usable', async () => {
  let asked = 0;
  const h = make({ pathname: '/', speech: false, mediaDevices: { getUserMedia() { asked++; throw Error('must not run'); } } });
  await settle(); h.aiOrb.emit('click'); await settle(); assert.equal(h.aiInput.focused, true);
  await h.send('Текст'); assert.equal(asked, 0); assert.equal(h.puts().length, 1);
});
test('webkit recognition uses the same permission flow', async () => {
  let asked = 0;
  const h = make({ mediaDevices: { getUserMedia: async () => { asked++; return { getTracks: () => [] }; } } });
  h.window.webkitSpeechRecognition = h.window.SpeechRecognition; delete h.window.SpeechRecognition;
  await settle(); h.aiOrb.emit('click'); await settle();
  assert.equal(asked, 1); assert.equal(h.recognitions[0].started, 1);
});

test('missing mediaDevices does not bypass permission priming', async () => {
  const h = make({ mediaDevices: null }); await settle(); h.aiOrb.emit('click'); await settle();
  assert.equal(h.recognitions.length, 0); assert.equal(h.aiInput.disabled, false);
  assert.ok(h.aiApp.classes.has('is-error'));
});

// This is a deterministic DOM/event contract harness, NOT a real-browser test.
test('idle boot reads once, never writes or schedules a perpetual poll', async () => {
  const h = make(); await settle(); h.window.emit('pageshow', { persisted: false }); await settle();
  assert.equal(h.calls.length, 1); assert.equal(h.puts().length, 0); assert.equal(h.clock.timers.size, 0);
  assert.equal(h.aiInput.disabled, false);
});
test('one submitted message preserves tasks, proposals and unknown state fields', async () => {
  const protectedState = { tasks: [{ id: 'task', title: 'Keep' }], aiProposals: [{ id: 'p', status: 'pending' }], future: { key: [1, 2] }, training: { load: 5 } };
  const h = make({ state: protectedState }); await settle(); await h.send('Привет');
  assert.equal(h.puts().length, 1);
  for (const key of Object.keys(protectedState)) assert.deepEqual(h.store.state[key], protectedState[key]);
  assert.equal(h.store.state.aiHomeRequests[0].text, 'Привет'); assert.equal(h.aiInput.value, '');
  assert.equal(h.aiInput.disabled, true); assert.equal(h.aiStatus.textContent, 'Думаю…');
  assert.ok(h.calls.every(call => call.url === '/api/state' && call.credentials === 'same-origin'));
});
test('double submit produces a single write', async () => {
  const h = make(); await settle(); h.aiInput.value = 'Один';
  for (let i = 0; i < 20; i++) h.aiComposer.emit('submit');
  await settle(); assert.equal(h.puts().length, 1);
});
test('active request polls until answer, then stops', async () => {
  const h = make({ state: active() }); await settle(); assert.equal(h.aiInput.disabled, true);
  h.store.state = done(); await h.clock.advance(900);
  assert.equal(h.aiAnswer.textContent, 'Готово'); assert.equal(h.aiInput.disabled, false);
  assert.equal(h.clock.timers.size, 0); assert.equal(h.puts().length, 0);
});
test('a request started by another tab is not duplicated', async () => {
  const h = make(); await settle(); h.store.state = active(); await h.send('Мой черновик');
  assert.equal(h.puts().length, 0); assert.equal(h.aiInput.value, 'Мой черновик');
});
test('409 retry rereads and preserves concurrent data', async () => {
  let conflict = true;
  const h = make({ handler: ({ options, store }) => {
    if (options.method === 'PUT' && conflict) { conflict = false; store.revision++; store.state.tasks = ['concurrent']; return reply({}, 409); }
  } });
  await settle(); await h.send('План');
  assert.equal(h.puts().length, 2); assert.deepEqual(h.store.state.tasks, ['concurrent']);
  assert.equal(h.store.state.aiHomeRequests.length, 1);
});
test('revision conflict retries are bounded and preserve the draft', async () => {
  const h = make({ handler: ({ options }) => options.method === 'PUT' ? reply({}, 409) : undefined });
  await settle(); await h.send('Не потеряй');
  assert.equal(h.puts().length, 6); assert.equal(h.aiInput.value, 'Не потеряй'); assert.equal(h.aiInput.disabled, false);
  assert.equal(h.clock.timers.size, 0);
});
test('ambiguous successful PUT is reconciled by id instead of written again', async () => {
  let fail = true;
  const h = make({ handler: ({ options, normal }) => {
    if (options.method === 'PUT' && fail) { fail = false; normal(); throw Error('connection lost after commit'); }
  } });
  await settle(); await h.send('Один раз'); assert.equal(h.aiInput.value, 'Один раз');
  await h.send('Один раз'); assert.equal(h.puts().length, 1); assert.equal(h.aiInput.value, '');
});
test('hung HTTP fetch is aborted and controls recover', async () => {
  const h = make({ handler: ({ options }) => new Promise((_, reject) => options.signal.addEventListener('abort', () => reject(Error('abort')))) });
  await settle(); assert.equal(h.aiInput.disabled, true); await h.clock.advance(15000);
  assert.equal(h.calls[0].signal.aborted, true); assert.equal(h.aiInput.disabled, false); assert.equal(h.clock.timers.size, 0);
});
test('HTTP timeout also covers a stalled JSON body', async () => {
  const h = make({ handler: ({ options }) => ({ ok: true, status: 200, json: () => new Promise((_, reject) => options.signal.addEventListener('abort', () => reject(Error('body aborted')))) }) });
  await settle(); await h.clock.advance(15000); assert.equal(h.aiInput.disabled, false); assert.equal(h.clock.timers.size, 0);
});
for (const code of [401, 403]) test(`GET ${code} presents auth without writes`, async () => {
  const h = make({ handler: () => reply({}, code) }); await settle();
  assert.equal(h.aiAuth.hidden, false); assert.equal(h.aiComposer.hidden, true); assert.equal(h.puts().length, 0);
});
test('PUT 401 preserves draft and enters auth', async () => {
  const h = make({ handler: ({ options }) => options.method === 'PUT' ? reply({}, 401) : undefined });
  await settle(); await h.send('Черновик'); assert.equal(h.aiAuth.hidden, false); assert.equal(h.aiInput.value, 'Черновик');
});
test('auth can recover on a subsequent visible-page read', async () => {
  let denied = true;
  const h = make({ handler: () => denied ? reply({}, 401) : undefined }); await settle();
  denied = false; h.hide(); h.show(); await settle(); assert.equal(h.aiAuth.hidden, true); assert.equal(h.aiComposer.hidden, false);
});
for (const payload of [{}, { state: [], revision: 1 }, { state: {}, revision: -1 }, { state: {}, revision: 'oops' }]) {
  test(`malformed GET fails closed: ${JSON.stringify(payload)}`, async () => {
    const h = make({ handler: () => reply(payload) }); await settle(); await h.send('test');
    assert.equal(h.puts().length, 0); assert.equal(h.aiInput.disabled, false);
  });
}
test('non-successful PUT payload does not clear input or automatically retry', async () => {
  const h = make({ handler: ({ options }) => options.method === 'PUT' ? reply({ ok: false }) : undefined });
  await settle(); await h.send('test'); assert.equal(h.aiInput.value, 'test'); assert.equal(h.puts().length, 1); assert.equal(h.clock.timers.size, 0);
});
test('polling never overlaps a pending HTTP request', async () => {
  let readCount = 0;
  const h = make({ state: active(), handler: ({ options }) => {
    if (options.method === 'GET' && ++readCount > 1) return new Promise((_, reject) => options.signal.addEventListener('abort', () => reject(Error('abort'))));
  } });
  await settle(); await h.clock.advance(5000); assert.equal(h.calls.length, 2);
});
test('polling an endless pending request has a finite deadline', async () => {
  const h = make({ state: active() }); await settle(); await h.clock.advance(192000);
  assert.equal(h.aiInput.disabled, false); assert.equal(h.clock.timers.size, 0); assert.equal(h.puts().length, 0);
});
test('polling network errors also stops at the deadline', async () => {
  let boot = true;
  const h = make({ state: active(), handler: () => { if (boot) { boot = false; return; } throw Error('offline'); } });
  await settle(); await h.clock.advance(192000);
  assert.equal(h.aiInput.disabled, false); assert.equal(h.clock.timers.size, 0);
});
test('repeated BFCache hide/show cycles restore pending polling', async () => {
  const h = make({ state: active() }); await settle();
  for (let i = 0; i < 3; i++) {
    h.window.emit('pagehide', { persisted: true }); await settle(); assert.equal(h.clock.timers.size, 0);
    h.window.emit('pageshow', { persisted: true }); await settle(); assert.equal(h.aiInput.disabled, true);
  }
  h.store.state = done(); await h.clock.advance(900); assert.equal(h.aiAnswer.textContent, 'Готово');
});
test('visibility hide aborts work and visible resumes with one read', async () => {
  const h = make({ state: active() }); await settle(); const before = h.calls.length;
  h.hide(); await h.clock.advance(5000); assert.equal(h.calls.length, before);
  h.show(); await settle(); assert.equal(h.calls.length, before + 1);
});
test('an initially hidden page does not start network activity', async () => {
  const h = make({ hidden: true }); await settle(); assert.equal(h.calls.length, 0);
  h.show(); await settle(); assert.equal(h.calls.length, 1);
});
test('late GET cannot repaint a hidden page or restart its poll', async () => {
  let resolve;
  const h = make({ handler: () => new Promise(done => { resolve = done; }) }); await settle();
  h.window.emit('pagehide'); const previous = h.aiStatus.textContent;
  resolve(reply({ revision: 1, state: done() })); await settle();
  assert.equal(h.aiStatus.textContent, previous); assert.equal(h.aiAnswer.textContent, ''); assert.equal(h.clock.timers.size, 0);
});
test('old operation completion cannot release a new visible-page operation', async () => {
  const pending = [];
  const h = make({ handler: () => new Promise(resolve => pending.push(resolve)) }); await settle();
  h.hide(); h.show(); await settle(); pending[0](reply({ revision: 1, state: {} })); await settle();
  h.window.emit('online'); await settle(); assert.equal(h.calls.length, 2);
  pending[1](reply({ revision: 1, state: {} })); await settle(); assert.equal(h.aiInput.disabled, false);
});
test('hide during accepted PUT never replays it after returning', async () => {
  let resolve;
  const h = make({ handler: ({ options, normal }) => {
    if (options.method === 'PUT') { normal(); return new Promise(done => { resolve = done; }); }
  } });
  await settle(); await h.send('Один раз'); h.hide(); h.show(); await settle();
  assert.equal(h.puts().length, 1); assert.equal(h.aiInput.value, '');
  resolve(reply({ ok: true })); await settle(); assert.equal(h.puts().length, 1);
});
test('answer remains literal text and unchanged refresh preserves scroll', async () => {
  const state = done(); state.aiHomeMessages[0].content = '<img src=x onerror=alert(1)>\nОтвет';
  const h = make({ state }); await settle(); h.aiAnswer.scrollTop = 120;
  h.window.emit('online'); await settle(); assert.equal(h.aiAnswer.scrollTop, 120); assert.equal(h.aiAnswer.textContent, state.aiHomeMessages[0].content);
});
test('IME composition and Shift+Enter do not submit', async () => {
  const h = make(); await settle(); h.aiInput.value = 'test';
  h.aiInput.emit('keydown', { key: 'Enter', isComposing: true }); h.aiInput.emit('keydown', { key: 'Enter', keyCode: 229 });
  h.aiInput.emit('keydown', { key: 'Enter', shiftKey: true }); await settle(); assert.equal(h.puts().length, 0);
  h.aiInput.emit('keydown', { key: 'Enter' }); await settle(); assert.equal(h.puts().length, 1);
});
test('unsupported speech falls back to focused text input', async () => {
  const h = make({ speech: false }); await settle(); h.aiOrb.emit('click'); await settle();
  assert.equal(h.aiInput.focused, true); assert.equal(h.puts().length, 0);
});
test('microphone permission error cannot send the existing draft via late onend', async () => {
  const h = make(); await settle(); h.aiInput.value = 'Старый черновик'; h.aiOrb.emit('click'); await settle();
  const mic = h.recognitions[0], lateEnd = mic.onend;
  mic.onerror({ error: 'not-allowed' }); lateEnd(); await settle();
  assert.equal(h.aiInput.value, 'Старый черновик'); assert.equal(h.puts().length, 0); assert.equal(mic.aborted, 1);
});
test('interim-only speech never autosends a draft', async () => {
  const h = make(); await settle(); h.aiInput.value = 'Черновик'; h.aiOrb.emit('click'); await settle();
  h.recognitions[0].result('неуверенно', false); h.recognitions[0].onend(); await settle();
  assert.equal(h.puts().length, 0); assert.equal(h.aiInput.value, 'Черновик');
});
test('final transcript sends exactly once and appends to draft', async () => {
  const h = make(); await settle(); h.aiInput.value = 'План:'; h.aiOrb.emit('click'); await settle();
  const mic = h.recognitions[0], lateEnd = mic.onend; mic.result('тренировка'); mic.onend(); lateEnd(); await settle();
  assert.equal(h.puts().length, 1); assert.equal(h.store.state.aiHomeRequests[0].text, 'План: тренировка');
});
test('speech error after a final result still does not autosend', async () => {
  const h = make(); await settle(); h.aiOrb.emit('click'); await settle(); const mic = h.recognitions[0], lateEnd = mic.onend;
  mic.result('Не отправлять'); mic.onerror({ error: 'network' }); lateEnd(); await settle(); assert.equal(h.puts().length, 0);
});
test('Escape aborts voice and ignores late results', async () => {
  const h = make(); await settle(); h.aiInput.value = 'Исходный'; h.aiOrb.emit('click'); await settle();
  const mic = h.recognitions[0], lateEnd = mic.onend; mic.result('диктовка');
  h.window.emit('keydown', { key: 'Escape' }); lateEnd(); await settle();
  assert.equal(h.aiInput.value, 'Исходный'); assert.equal(h.puts().length, 0);
});
test('leaving while listening cannot send a hidden request', async () => {
  const h = make(); await settle(); h.aiOrb.emit('click'); await settle(); const mic = h.recognitions[0], lateEnd = mic.onend;
  mic.result('Не отправлять'); h.window.emit('pagehide'); lateEnd(); await settle();
  assert.equal(h.puts().length, 0); assert.equal(h.clock.timers.size, 0);
});
test('rapid microphone taps reserve one recognition before onstart', async () => {
  const h = make({ autoStart: false }); await settle(); h.aiOrb.emit('click'); await settle(); h.aiOrb.emit('click'); await settle();
  assert.equal(h.recognitions.length, 1); assert.equal(h.recognitions[0].stopped, 1);
});
test('manual hold remains available while thinking without starting speech', async () => {
  const h = make({ state: active() }); await settle(); h.aiOrb.emit('pointerdown'); await h.clock.advance(1100); h.aiOrb.emit('pointerup');
  h.aiOrb.emit('click'); await settle(); assert.deepEqual(h.navigations, ['/manual.html?v=20260908-quiet-signal-2']); assert.equal(h.recognitions.length, 0); assert.equal(h.clock.timers.size, 0);
});
test('cancelled hold does not navigate', async () => {
  const h = make(); await settle(); h.aiOrb.emit('pointerdown'); h.aiOrb.emit('pointercancel'); await h.clock.advance(1200);
  assert.equal(h.navigations.length, 0);
});
test('pagehide cancels a held manual gesture', async () => {
  const h = make(); await settle(); h.aiOrb.emit('pointerdown'); h.window.emit('pagehide'); await h.clock.advance(1200);
  assert.equal(h.navigations.length, 0);
});
test('manual command and keyboard shortcut navigate without state writes', async () => {
  const h = make(); await settle(); await h.send('/manual'); assert.deepEqual(h.navigations, ['/manual.html?v=20260908-quiet-signal-2']); assert.equal(h.puts().length, 0);
  const busy = make({ state: active() }); await settle(); busy.window.emit('keydown', { altKey: true, code: 'KeyM' }); assert.equal(busy.navigations[0], '/manual.html?v=20260908-quiet-signal-2');
});
test('viewport updates only the isolated root and does not override pinch zoom', async () => {
  const h = make(); await settle(); h.window.visualViewport.height = 380; h.window.visualViewport.emit('resize');
  assert.equal(h.aiApp.style['--ai-height'], '380px'); h.window.visualViewport.scale = 2;
  h.window.visualViewport.height = 200; h.window.visualViewport.emit('resize'); assert.equal(h.aiApp.style['--ai-height'], '380px');
  assert.equal(h.clock.timers.size, 0);
});
test('standalone source has no shared-worker/cache mutation, DOM observer or interval', () => {
  assert.doesNotMatch(source, /MutationObserver|setInterval\s*\(|serviceWorker|caches\s*\.|innerHTML\s*=/);
  const html = fs.readFileSync(path.join(__dirname, '../../ai-home-v2/index.html'), 'utf8');
  assert.doesNotMatch(html, /(?:src|href)=["']\/?(?:app\.js|styles\.css)/);
  assert.match(html, /interactive-widget=resizes-content/); assert.match(html, /20260905-3/);
});
test('final plus interim result sends and clears only the final transcript', async () => {
  const h = make(); await settle(); h.aiOrb.emit('click'); await settle(); const mic = h.recognitions[0];
  const final = [{ transcript: 'Готовый текст' }]; final.isFinal = true;
  const interim = [{ transcript: 'неуверенный хвост' }]; interim.isFinal = false;
  mic.onresult({ resultIndex: 0, results: [final, interim] }); mic.onend(); await settle();
  assert.equal(h.store.state.aiHomeRequests[0].text, 'Готовый текст'); assert.equal(h.aiInput.value, '');
});

test('idle and completed answer do not add a greeting or follow-up on the empty home', async () => {
  const h = make(); await settle(); assert.equal(h.aiStatus.textContent, '');
  h.store.state = done(); h.window.emit('online'); await settle(); assert.equal(h.aiStatus.textContent, '');
});
for (const pathname of ['/', '/index.html', '/index.html/']) test(`promoted ${pathname} uses manual.html, including auth`, async () => {
  const h = make({ pathname, handler: () => reply({}, 401) }); await settle();
  assert.equal(h.aiAuthLink.href, '/manual.html');
  h.window.emit('keydown', { altKey: true, code: 'KeyM' }); assert.deepEqual(h.navigations, ['/manual.html?v=20260908-quiet-signal-2']);
});
test('preview auth leads to stable root instead of missing manual.html', async () => {
  const h = make({ handler: () => reply({}, 401) }); await settle(); assert.equal(h.aiAuthLink.href, '/');
});
test('long hold waits for release and never starts speech after navigation', async () => {
  const h = make(); await settle(); h.aiOrb.emit('pointerdown'); await h.clock.advance(1200);
  assert.equal(h.navigations.length, 0); assert.equal(h.clock.timers.size, 0);
  h.aiOrb.emit('pointerup'); h.aiOrb.emit('click'); await settle(); assert.deepEqual(h.navigations, ['/manual.html?v=20260908-quiet-signal-2']);
  assert.equal(h.recognitions.length, 0);
});


test('live speech fix: history silent, fresh completion chunked once, cancellation invalidates callbacks', async () => {
  const spoken = []; let cancelled = 0;
  const h = make({ setup({window}) {
    window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
    window.speechSynthesis = { speak(u) { spoken.push(u); }, cancel() { cancelled++; }, getVoices: () => [{lang:'ru-RU'}] };
  }});
  await settle();
  const text = 'Ответ '.repeat(100) + '😀';
  h.store.state = {aiHomeStatus:{state:'ready',requestId:'fresh'},aiHomeMessages:[{role:'assistant',content:text}]};
  h.window.emit('online'); await settle();
  assert.equal(spoken.length, 1);
  for (let i=0; i<spoken.length; i++) { assert.ok(spoken[i].text.length <= 220); spoken[i].onend(); }
  assert.equal(spoken.map(u=>u.text).join(''),text);
  const count=spoken.length; h.window.emit('online'); await settle(); assert.equal(spoken.length,count);
  h.store.state.aiHomeStatus.requestId='second'; h.window.emit('online'); await settle();
  const late=spoken.at(-1).onend; h.hide(); late(); assert.equal(spoken.length,count+1); assert.ok(cancelled);
});

function visualSetup({window, document, elements}) {
  for (const id of ['aiRibbonMesh','aiManual']) elements[id] = new Element();
  elements.aiRibbonMesh.children=[];
  elements.aiRibbonMesh.append = p => { const a=elements.aiRibbonMesh.children; const i=a.indexOf(p); if(i>=0)a.splice(i,1); a.push(p); };
  document.createElementNS = () => new Element();
  const frames=new Map(); let id=0;
  window.requestAnimationFrame=fn=>{frames.set(++id,fn);return id;};
  window.cancelAnimationFrame=id=>frames.delete(id);
  const motion=new Target(); motion.matches=false; window.matchMedia=()=>motion;
  window.frames=frames; window.motion=motion;
  window.tick=time=>{const batch=[...frames.values()];frames.clear();batch.forEach(fn=>fn(time));};
}
test('ribbon has shaded geometry, one frame loop, hidden/reduced/pagehide lifecycle', async () => {
  const h=make({setup:visualSetup}); await settle();
  const mesh=h.aiRibbonMesh;
  assert.equal(mesh.children.length,32); assert.equal(h.window.frames.size,1);
  const initial=mesh.children.map(p=>p.attributes.d).join('');
  h.window.tick(100); h.window.tick(150);
  assert.notEqual(mesh.children.map(p=>p.attributes.d).join(''),initial);
  assert.ok(new Set(mesh.children.map(p=>p.style.fill)).size>20);
  h.hide(); assert.equal(h.window.frames.size,0);
  h.show(); await settle(); assert.equal(h.window.frames.size,1);
  h.window.motion.matches=true;h.window.motion.emit('change');assert.equal(h.window.frames.size,0);
  h.window.motion.matches=false;h.window.motion.emit('change');assert.equal(h.window.frames.size,1);
  h.window.emit('pagehide');assert.equal(h.window.frames.size,0);
});
test('speaking follows actual utterance start/end, never queued speech or late callbacks', async () => {
  const spoken=[];
  const h=make({setup(args){visualSetup(args);args.window.SpeechSynthesisUtterance=class {};args.window.speechSynthesis={speak:u=>spoken.push(u),cancel(){}};}});
  await settle();h.store.state={aiHomeStatus:{state:'ready',requestId:'new'},aiHomeMessages:[{role:'assistant',content:'Ответ'}]};
  h.window.emit('online');await settle();assert.ok(!h.aiApp.classes.has('is-speaking'));
  spoken[0].onstart();assert.ok(h.aiApp.classes.has('is-speaking'));
  spoken[0].onend();assert.ok(!h.aiApp.classes.has('is-speaking'));
  h.store.state.aiHomeStatus.requestId='next';h.window.emit('online');await settle();
  const late=spoken[1].onstart;h.hide();late();assert.ok(!h.aiApp.classes.has('is-speaking'));
});
test('broken animation APIs cannot break requests or microphone controls', async () => {
  const h=make({setup(args){visualSetup(args);args.window.requestAnimationFrame=()=>{throw Error('unsupported');};}});
  await settle();await h.send('Работает');assert.equal(h.puts().length,1);
});
test('visible Manual link saves only bounded draft for one return; blocked storage is harmless', async () => {
  const data=new Map(); const storage={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};
  const setup=args=>{visualSetup(args);args.window.sessionStorage=storage;};
  const h=make({setup});await settle();h.aiInput.value='Мой черновик';h.aiManual.emit('click');
  assert.deepEqual(h.navigations,['/manual.html?v=20260908-quiet-signal-2']);assert.equal(data.size,1);
  const back=make({setup});await settle();assert.equal(back.aiInput.value,'Мой черновик');assert.equal(data.size,0);
  const blocked=make({setup(args){visualSetup(args);Object.defineProperty(args.window,'sessionStorage',{get(){throw Error('blocked');}});}});
  await settle();blocked.aiManual.emit('click');assert.equal(blocked.navigations.length,1);
});

test('new answer scrolls into view once without resetting repeated answer scroll', async()=>{
 let scrolls=0;
 const h=make({setup({elements}){elements.aiAnswer.scrollIntoView=()=>scrolls++;}});
 await settle();await h.send('Вопрос');h.store.state=done();await h.clock.advance(900);
 assert.equal(scrolls,1);h.aiAnswer.scrollTop=80;h.window.emit('online');await settle();
 assert.equal(scrolls,1);assert.equal(h.aiAnswer.scrollTop,80);
});
test('draft excludes credentials, oversized text and mode commands, expires and rejects malformed records',async()=>{
 const key='dvizh.ai-home-v2.manual-draft', data=new Map();
 const storage={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};
 const setup=args=>{visualSetup(args);args.window.sessionStorage=storage;};
 for(const value of ['token=abc','пароль: abc','sk-proj-abcd','a'.repeat(12001),'/manual','eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyIjoxfQ.signature']){
  const h=make({setup});await settle();h.aiInput.value=value;h.aiManual.emit('click');assert.equal(data.size,0,value.slice(0,30));
 }
 for(const raw of ['{',JSON.stringify({text:'expired',expires:999}),JSON.stringify({text:12,expires:2000}),JSON.stringify({text:'future',expires:999999999})]){
  data.set(key,raw);const h=make({setup});await settle();assert.equal(h.aiInput.value,'');assert.equal(data.size,0);
 }
});
test('ribbon failures after startup and missing SVG support leave API flow intact',async()=>{
 for(const failure of ['draw','svg','motion']){
  const h=make({setup(args){visualSetup(args);
   if(failure==='svg')args.document.createElementNS=undefined;
   if(failure==='motion')args.window.matchMedia=()=>{throw Error('unavailable');};
  }});await settle();
  if(failure==='draw'){h.aiRibbonMesh.children[0].setAttribute=()=>{throw Error('renderer');};h.window.tick(30);assert.equal(h.window.frames.size,0);}
  await h.send('Текст');assert.equal(h.puts().length,1);
 }
});
test('ribbon tracks recognition and thinking; interrupted speech returns idle',async()=>{
 const h=make({setup:visualSetup});await settle();assert.equal(h.aiApp.attributes['data-signal-state'],'idle');
 h.aiOrb.emit('click');await settle();assert.equal(h.aiApp.attributes['data-signal-state'],'listening');
 h.recognitions[0].result('Вопрос');h.recognitions[0].onend();await settle();assert.equal(h.aiApp.attributes['data-signal-state'],'thinking');
 h.store.state=done();await h.clock.advance(900);assert.equal(h.aiApp.attributes['data-signal-state'],'idle');
});

test('speech history stays silent; unsupported output and synth errors retain readable answers',async()=>{
 for(const synthMode of ['supported','missing','throws']){
  const spoken=[];
  const state={aiHomeStatus:{state:'ready',requestId:'history'},aiHomeMessages:[{role:'assistant',content:'История'}]};
  const h=make({state,setup({window}){
   if(synthMode!=='missing'){window.SpeechSynthesisUtterance=class {};window.speechSynthesis={cancel(){},speak:u=>{if(synthMode==='throws')throw Error('audio unavailable');spoken.push(u);}};}
  }});await settle();assert.equal(spoken.length,0);assert.equal(h.aiAnswer.hidden,true);
  h.store.state.aiHomeStatus.requestId='fresh';h.window.emit('online');await settle();assert.equal(h.aiAnswer.hidden,false);
  if(synthMode==='supported'){assert.equal(spoken.length,1);spoken[0].onstart();assert.ok(h.aiApp.classes.has('is-speaking'));spoken[0].onerror();assert.ok(!h.aiApp.classes.has('is-speaking'));}
  h.window.emit('online');await settle();assert.equal(spoken.length,synthMode==='supported'?1:0);
  assert.equal(h.aiInput.disabled,false);
 }
});
test('speech chunk boundaries preserve surrogate pairs and loaded Russian voices',async()=>{
 const spoken=[];const russian={lang:'ru-RU'};
 const h=make({setup({window}){window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};window.speechSynthesis={cancel(){},speak:u=>spoken.push(u),getVoices:()=>[russian]};}});
 await settle();const text='x'.repeat(219)+'😀'+'я'.repeat(300);
 h.store.state={aiHomeStatus:{state:'ready',requestId:'unicode'},aiHomeMessages:[{role:'assistant',content:text}]};h.window.emit('online');await settle();
 for(let i=0;i<spoken.length;i++){const u=spoken[i];assert.equal(u.voice,russian);assert.doesNotMatch(u.text,/[\uD800-\uDBFF]$/);u.onend();}
 assert.equal(spoken.map(u=>u.text).join(''),text);
});
test('modified Manual click keeps native navigation and writes no draft',async()=>{
 let writes=0;const h=make({setup(args){visualSetup(args);args.window.sessionStorage={getItem(){},removeItem(){},setItem(){writes++;}};}});
 await settle();h.aiInput.value='Черновик';const event=h.aiManual.emit('click',{ctrlKey:true});assert.ok(!event.prevented);assert.equal(writes,0);assert.equal(h.navigations.length,0);
});
test('keyboard viewport follows offset scroll and preserves pinch zoom',async()=>{
 const h=make();await settle();h.window.visualViewport.offsetTop=120;h.window.visualViewport.height=320;h.window.visualViewport.emit('scroll');
 assert.equal(h.aiApp.style['--ai-top'],'120px');assert.equal(h.aiApp.style['--ai-height'],'320px');
 h.window.visualViewport.scale=2;h.window.visualViewport.offsetTop=200;h.window.visualViewport.emit('scroll');assert.equal(h.aiApp.style['--ai-top'],'120px');
});

test('back-forward cache return consumes saved draft without overwriting in-memory text',async()=>{
 const data=new Map();const h=make({setup(args){visualSetup(args);args.window.sessionStorage={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};}});
 await settle();h.aiInput.value='Черновик';h.aiManual.emit('click');assert.equal(data.size,1);
 h.window.emit('pageshow',{persisted:true});await settle();assert.equal(data.size,0);assert.equal(h.aiInput.value,'Черновик');
});

 test('unresolved accepted PUT is never restored as an ordinary Manual draft', async()=>{
 const key='dvizh.ai-home-v2.manual-draft', data=new Map();
 const setup=args=>{visualSetup(args);args.window.sessionStorage={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};};
 let release;
 const h=make({setup,handler:({options,normal})=>{
   if(options.method==='PUT'){const accepted=normal();return new Promise(resolve=>{release=()=>resolve(accepted);});}
 }});
 await settle();await h.send('Добавь задачу');assert.equal(h.puts().length,1);
 data.set(key,JSON.stringify({text:'Старый черновик',expires:2000}));
 h.window.emit('keydown',{key:'m',code:'KeyM',altKey:true});
 assert.equal(data.size,0,'remove stale draft and exclude unresolved submission');
 assert.equal(h.navigations.length,1);
 release();await settle();
 const state=copy(h.store.state);state.aiHomeRequests[0].status='done';
 state.aiHomeStatus={state:'ready',requestId:state.aiHomeRequests[0].id};
 state.aiHomeMessages.push({role:'assistant',content:'Задача добавлена'});
 const back=make({setup,state});await settle();assert.equal(back.aiInput.value,'');
 back.aiInput.emit('keydown',{key:'Enter'});await settle();assert.equal(back.puts().length,0);
 });
 for(const failure of ['listener','runtime','request-missing','cancel-missing','request-throws']) test(`ribbon fallback readiness: ${failure}`,async()=>{
 const h=make({setup(args){visualSetup(args);
  if(failure==='listener')args.window.motion.addEventListener=()=>{throw Error('listener unavailable');};
  if(failure==='request-missing')delete args.window.requestAnimationFrame;
  if(failure==='cancel-missing')delete args.window.cancelAnimationFrame;
  if(failure==='request-throws')args.window.requestAnimationFrame=()=>{throw Error('animation unavailable');};
 }});await settle();
 if(failure==='runtime'){
  assert.equal(h.aiRibbonMesh.attributes['data-ready'],'true');
  h.aiRibbonMesh.children[0].setAttribute=()=>{throw Error('late draw failure');};h.window.tick(30);
 }
 const failed=['listener','runtime','request-throws'].includes(failure);
 assert.equal(h.aiRibbonMesh.attributes['data-ready'],failed?'false':'true');
 if(!failed)assert.ok(h.aiRibbonMesh.children.every(p=>p.attributes.d?.endsWith('Z')));
 assert.equal(h.window.frames.size,0);
 await h.send('Работает');assert.equal(h.puts().length,1);
 });
