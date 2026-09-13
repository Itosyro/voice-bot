'use strict';
// Execute the complete generated AI client against isolated DOM/API fixtures.
// No network, production state, real microphone or external dependencies.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const sourcePath = process.env.DVIZH_DRAFT_CLIENT || path.join(root, 'dist/ai-home-v2.js');
const source = fs.readFileSync(sourcePath, 'utf8');
const KEY = 'dvizh.ai-home-v2.manual-draft';
const TTL = 10 * 60 * 1000;
const NOW = Date.parse('2026-09-13T12:00:00Z');
const clone = value => JSON.parse(JSON.stringify(value));
const flush = () => new Promise(resolve => setImmediate(resolve));

class Events {
  constructor() { this.listeners = new Map(); }
  addEventListener(name, callback) {
    const list = this.listeners.get(name) || [];
    list.push(callback); this.listeners.set(name, list);
  }
  emit(name, props = {}) {
    const event = {button: 0, preventDefault() {}, ...props};
    for (const callback of this.listeners.get(name) || []) callback(event);
  }
}
class Element extends Events {
  constructor() {
    super();
    this.value = ''; this.textContent = ''; this.hidden = false;
    this.disabled = false; this.scrollHeight = 36; this.scrollTop = 0;
    this.style = {setProperty() {}};
    this.classList = {toggle() {}};
  }
  setAttribute() {}
  focus() {}
  scrollIntoView() {}
  requestSubmit() { this.emit('submit'); }
}
function apiFixture(initial = {}) {
  return {state: clone(initial), revision: 1, puts: 0, gets: 0, ambiguous: false, auth: false};
}
function page({storage = new Map(), api = apiFixture(), now = NOW, storageThrows = false} = {}) {
  const window = new Events();
  const document = new Events();
  document.hidden = false;
  const elements = new Map(['aiApp','aiOrb','aiStatus','aiAnswer','aiComposer','aiInput','aiSend','aiAuth','aiAuthLink','aiManual'].map(id => [id, new Element()]));
  document.getElementById = id => elements.get(id) || null;
  const timers = new Map(); let timerId = 0;
  const navigations = [], recognizers = [];
  let stoppedTracks = 0;
  class Recognition {
    constructor() { recognizers.push(this); this.aborted = false; }
    start() { this.onstart?.(); }
    abort() { this.aborted = true; }
    stop() { this.onend?.(); }
  }
  const speech = [];
  window.SpeechRecognition = Recognition;
  window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
  window.speechSynthesis = {cancel() {}, getVoices: () => [], speak: value => speech.push(value.text)};
  window.innerHeight = 800;
  Object.defineProperty(window, 'sessionStorage', {get() {
    if (storageThrows) throw new Error('storage disabled');
    return {getItem: key => storage.get(key) ?? null, setItem: (key,value) => storage.set(key,String(value)), removeItem: key => storage.delete(key)};
  }});
  class Clock extends Date {
    constructor(...args) { super(...(args.length ? args : [now])); }
    static now() { return now; }
  }
  const fetch = async (url, options) => {
    assert.equal(url, '/api/state');
    if (api.auth) return {status: 401, ok: false};
    if(api.failGet && options.method !== 'PUT') throw new TypeError('preflight offline');
    if (options.method === 'PUT') {
      api.puts++;
      const body = JSON.parse(options.body);
      if(api.conflict) return {status:409,ok:false};
      if(api.putReply) return {status:200,ok:true,json:async()=>api.putReply(body)};
      if (body.baseRevision !== api.revision) return {status: 409, ok: false};
      api.state = clone(body.state); api.revision++;
      if (api.ambiguous) throw new TypeError('response lost after accepted write');
      return {status: 200, ok: true, json: async () => ({ok: true, state: clone(api.state), revision: api.revision})};
    }
    api.gets++;
    return {status: 200, ok: true, json: async () => ({state: clone(api.state), revision: api.revision})};
  };
  const context = vm.createContext({window, document, location: {pathname:'/', assign: url => navigations.push(url)}, fetch,
    AbortController, Date: Clock, performance: {now: () => 0},
    navigator: {mediaDevices: {getUserMedia: async () => ({getTracks: () => [{stop() { stoppedTracks++; }}]})}},
    setTimeout(callback, delay) { const id = ++timerId; timers.set(id, {callback, delay}); return id; },
    clearTimeout(id) { timers.delete(id); }, console});
  vm.runInContext(source, context, {filename: sourcePath, timeout: 1000});
  return {window, document, api, storage, navigations, recognizers, speech, timers,
    input: elements.get('aiInput'), answer: elements.get('aiAnswer'),
    submit: () => elements.get('aiComposer').emit('submit'),
    manual: () => elements.get('aiManual').emit('click'),
    record: () => elements.get('aiOrb').emit('click'),
    hide() { document.hidden = true; document.emit('visibilitychange'); },
    show() { document.hidden = false; document.emit('visibilitychange'); },
    stoppedTracks: () => stoppedTracks};
}

test('reload restores the exact unsent draft without PUT or old answer', async () => {
  const storage = new Map(), api = apiFixture({aiHomeMessages:[{role:'assistant',content:'historical reply'}]});
  const a = page({storage, api}); await flush();
  a.input.value = '  Завтра закончить одну задачу\nи погулять 🚶  ';
  a.window.emit('pagehide', {persisted:false});
  const b = page({storage, api}); await flush();
  assert.equal(b.input.value, a.input.value);
  assert.equal(b.answer.hidden, true);
  assert.equal(api.puts, 0); assert.deepEqual(b.speech, []);
  assert.equal(storage.has(KEY), false);
});

test('visibilitychange saves before a mobile browser discards the page', async () => {
  const storage = new Map(), a = page({storage}); await flush();
  a.input.value = 'Мой план на сегодня'; a.hide();
  const b = page({storage}); await flush();
  assert.equal(b.input.value, 'Мой план на сегодня'); assert.equal(b.api.puts, 0);
});

test('hide/show keeps the live draft and a later reload saves newer edits', async () => {
  const storage = new Map(), a = page({storage}); await flush();
  a.input.value = 'Первая мысль'; a.hide();
  assert.equal(JSON.parse(storage.get(KEY)).text, 'Первая мысль');
  a.show(); await flush();
  assert.equal(a.input.value, 'Первая мысль'); assert.equal(storage.has(KEY), false);
  a.input.value = 'Уточнённая мысль'; a.window.emit('pagehide');
  const b = page({storage}); await flush();
  assert.equal(b.input.value, 'Уточнённая мысль'); assert.equal(b.api.puts, 0);
});

test('Manual round trip still preserves the draft without an automatic send', async () => {
  const storage = new Map(), a = page({storage}); await flush();
  a.input.value = 'Сначала посмотреть расписание'; a.manual();
  assert.deepEqual(a.navigations, ['/manual.html?v=20260914-daily-stability-1']);
  a.window.emit('pagehide');
  const b = page({storage}); await flush();
  assert.equal(b.input.value, 'Сначала посмотреть расписание'); assert.equal(b.api.puts, 0);
});

test('BFCache return preserves the live DOM and consumes the storage copy', async () => {
  const storage = new Map(), a = page({storage}); await flush();
  a.input.value = 'Вернуться к плану'; a.window.emit('pagehide', {persisted:true});
  a.window.emit('pageshow', {persisted:true}); await flush();
  assert.equal(a.input.value, 'Вернуться к плану'); assert.equal(storage.has(KEY), false);
  assert.equal(a.api.puts, 0);
});

test('TTL remains ten minutes and expired drafts are discarded', async () => {
  const storage = new Map(), a = page({storage}); await flush();
  a.input.value = 'Временный черновик'; a.hide();
  assert.equal(JSON.parse(storage.get(KEY)).expires, NOW + TTL);
  const b = page({storage, now:NOW + TTL}); await flush();
  assert.equal(b.input.value, ''); assert.equal(storage.has(KEY), false);
});

test('empty drafts remove stale copies', async () => {
  const storage = new Map(), a = page({storage}); await flush();
  storage.set(KEY, JSON.stringify({text:'stale',expires:NOW+TTL}));
  a.input.value = '   '; a.window.emit('pagehide');
  assert.equal(storage.has(KEY), false);
});

test('existing sensitive-text and length exclusions remain in force', async () => {
  for (const text of ['пароль пример', 'api_key example', '-----BEGIN PRIVATE KEY-----', 'A'.repeat(40), 'я '.repeat(6001), '/manual']) {
    const storage = new Map(), a = page({storage}); await flush();
    a.input.value = text; a.hide();
    assert.equal(storage.has(KEY), false, text.slice(0,40));
  }
});

test('an ambiguous accepted PUT is not restored or replayed after reload', async () => {
  const storage = new Map(), api = apiFixture({tasks:[{id:'fixture-task',title:'untouched'}],futureField:{version:9}});
  api.ambiguous = true;
  const a = page({storage, api}); await flush();
  a.input.value = 'Добавить задачу'; a.submit(); await flush();
  assert.equal(api.puts, 1); assert.equal(a.input.value, 'Добавить задачу');
  a.window.emit('pagehide'); assert.equal(storage.has(KEY), false);
  const b = page({storage, api}); await flush();
  assert.equal(b.input.value, ''); assert.equal(api.puts, 1);
  assert.equal(api.state.aiHomeRequests.length, 1);
  assert.deepEqual(api.state.tasks, [{id:'fixture-task',title:'untouched'}]);
  assert.deepEqual(api.state.futureField, {version:9});
});

test('confirmed sends clear the draft and never reappear on reload', async () => {
  const storage = new Map(), api = apiFixture(), a = page({storage, api}); await flush();
  a.input.value = 'Отправленная мысль'; a.submit(); await flush();
  assert.equal(a.input.value, ''); assert.equal(api.puts, 1);
  a.hide(); a.window.emit('pagehide');
  const b = page({storage, api}); await flush();
  assert.equal(b.input.value, ''); assert.equal(api.puts, 1);
});

test('pagehide during recognition saves only the original typed draft', async () => {
  const storage = new Map(), a = page({storage}); await flush();
  a.input.value = 'Мой исходный текст'; a.record(); await flush();
  const recognition = a.recognizers[0]; assert.ok(recognition);
  const result = [{transcript:'неподтверждённая речь'}]; result.isFinal = false;
  recognition.onresult({results:[result]});
  assert.match(a.input.value, /неподтверждённая/);
  a.hide(); a.window.emit('pagehide');
  assert.equal(recognition.aborted, true); assert.equal(a.stoppedTracks(), 1);
  const b = page({storage}); await flush();
  assert.equal(b.input.value, 'Мой исходный текст'); assert.equal(a.api.puts, 0);
});

test('disabled sessionStorage does not block cancellation or navigation', async () => {
  const a = page({storageThrows:true}); await flush();
  a.input.value = 'Черновик в памяти'; a.record(); await flush();
  assert.doesNotThrow(() => a.manual());
  assert.equal(a.recognizers[0].aborted, true);
  assert.equal(a.navigations.length, 1);
});

test('malformed and implausible storage records are consumed safely', async () => {
  for (const raw of ['{', 'null', JSON.stringify({text:'test',expires:NOW+TTL+1}), 'x'.repeat(75001)]) {
    const storage = new Map([[KEY,raw]]), a = page({storage}); await flush();
    assert.equal(a.input.value, ''); assert.equal(storage.has(KEY), false);
  }
});

test('restored text is sent exactly once only after an explicit submit', async () => {
  const storage = new Map([[KEY,JSON.stringify({text:'Прогулка после работы',expires:NOW+TTL})]]);
  const api = apiFixture({unrelated:{preserved:true}}), a = page({storage, api}); await flush();
  assert.equal(api.puts, 0); a.submit(); await flush();
  assert.equal(api.puts, 1); assert.equal(a.input.value, '');
  assert.deepEqual(api.state.unrelated, {preserved:true});
});

test('fresh tabs do not share an unsent draft', async () => {
  const a = page(); await flush(); a.input.value = 'Только в этой вкладке'; a.hide();
  const b = page(); await flush(); assert.equal(b.input.value, '');
});

// Failures before dispatch must never be confused with an accepted request.
test('a failed preflight GET retains the unsent text across a reload',async()=>{
  const storage=new Map(),api=apiFixture(),a=page({storage,api});await flush();
  api.failGet=true;a.input.value='Завтра прогуляться';a.submit();await flush();
  assert.equal(api.puts,0);a.hide();api.failGet=false;const b=page({storage,api});await flush();
  assert.equal(b.input.value,'Завтра прогуляться');assert.equal(api.puts,0);
});
test('repeated CAS rejections retain the ordinary draft, without a queued request',async()=>{
  const storage=new Map(),api=apiFixture(),a=page({storage,api});await flush();
  api.conflict=true;a.input.value='Спланировать день';a.submit();await flush();
  assert.equal(api.state.aiHomeRequests,undefined);a.hide();const b=page({storage,api});await flush();
  assert.equal(b.input.value,'Спланировать день');
});
for(const [label,make] of [
  ['ok-only',()=>({ok:true})],
  ['missing state',()=>({ok:true,revision:2})],
  ['wrong revision',b=>({ok:true,state:b.state,revision:999})],
  ['wrong snapshot',()=>({ok:true,state:{unrelated:true},revision:2})],
  ['not explicitly accepted',b=>({state:b.state,revision:2})]
])test(`AI Home rejects false PUT receipt: ${label}`,async()=>{
  const storage=new Map(),api=apiFixture(),a=page({storage,api});await flush();
  api.putReply=make;a.input.value='Один запрос';a.submit();await flush();
  assert.equal(a.input.value,'Один запрос','unconfirmed request must not clear the input');
  assert.equal(api.puts,1);a.hide();assert.equal(storage.has(KEY),false,'ambiguous dispatched text must not become an auto-replay draft');
});
test('typing a NEW draft after an ambiguous send preserves only the new text on reload',async()=>{
  const storage=new Map(),api=apiFixture(),a=page({storage,api});await flush();
  api.ambiguous=true;a.input.value='Старый отправленный запрос';a.submit();await flush();
  assert.equal(api.puts,1);a.input.value='Новая, ещё не отправленная мысль';a.hide();
  const b=page({storage,api});await flush();
  assert.equal(b.input.value,'Новая, ещё не отправленная мысль');assert.equal(api.puts,1);
  assert.equal(api.state.aiHomeRequests.length,1);
});
