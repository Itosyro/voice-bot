'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../../ai-home-v2/ai-home-v2.js'), 'utf8');
const settle = async () => { for (let i = 0; i < 12; i++) await new Promise(setImmediate); };
const copy = value => JSON.parse(JSON.stringify(value));

class Target {
  constructor() { this.listeners = new Map(); }
  addEventListener(name, fn) {
    const list = this.listeners.get(name) || [];
    list.push(fn); this.listeners.set(name, list);
  }
  emit(name, detail = {}) {
    const event = { button: 0, preventDefault() {}, ...detail };
    for (const fn of this.listeners.get(name) || []) fn(event);
    return event;
  }
}

class Element extends Target {
  constructor() {
    super(); this.textContent = ''; this.value = ''; this.hidden = false;
    this.disabled = false; this.scrollHeight = 52; this.scrollTop = 0;
    this.attributes = {}; this.classes = new Set();
    this.classList = { toggle: (name, enabled) => enabled ? this.classes.add(name) : this.classes.delete(name) };
    this.style = { setProperty(name, value) { this[name] = value; } };
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  focus() { this.focused = true; }
  requestSubmit() { this.emit('submit'); }
  set innerHTML(_) { throw Error('innerHTML forbidden'); }
}

function make({ getUserMedia, state = {} } = {}) {
  const order = [];
  const recognitions = [];
  const puts = [];
  const tracks = [];
  const document = new Target(); document.hidden = false;
  const elements = Object.fromEntries(
    ['aiApp','aiOrb','aiStatus','aiAnswer','aiComposer','aiInput','aiSend','aiAuth','aiAuthLink']
      .map(id => [id, new Element()])
  );
  document.getElementById = id => elements[id];
  elements.aiAnswer.hidden = elements.aiAuth.hidden = true;

  class Recognition {
    constructor() { order.push('recognition:ctor'); recognitions.push(this); }
    start() { order.push('recognition:start'); this.onstart?.(); }
    stop() { order.push('recognition:stop'); }
    abort() { order.push('recognition:abort'); }
  }

  const window = new Target();
  Object.assign(window, { innerHeight: 800, SpeechRecognition: Recognition });
  window.visualViewport = new Target();
  Object.assign(window.visualViewport, { scale: 1, height: 800 });

  const stream = {
    getTracks() {
      const track = { stop() { order.push('track:stop'); track.stopped = true; } };
      tracks.push(track); return [track];
    }
  };
  const mediaDevices = {
    async getUserMedia(constraints) {
      order.push('gum:start');
      assert.deepEqual(constraints, { audio: true });
      if (getUserMedia) return getUserMedia({ order, stream });
      order.push('gum:granted');
      return stream;
    }
  };

  let revision = 1;
  let current = copy(state);
  const fetch = async (_url, options = {}) => {
    if ((options.method || 'GET') === 'PUT') {
      const payload = JSON.parse(options.body);
      current = payload.state; revision += 1; puts.push(payload);
      return { status: 200, ok: true, json: async () => ({ ok: true, revision }) };
    }
    return { status: 200, ok: true, json: async () => ({ revision, state: copy(current) }) };
  };

  const sandbox = {
    window, document, navigator: { mediaDevices }, fetch,
    location: { pathname: '/', assign() {} }, AbortController, console,
    performance: { now: () => 1 }, Date,
    setTimeout, clearTimeout,
    crypto: { randomUUID: () => 'voice-test' }
  };
  vm.runInNewContext(source, sandbox);
  return { ...elements, window, document, order, recognitions, puts, tracks, stream };
}

test('AI Home asks browser microphone permission before starting SpeechRecognition', async () => {
  const h = make(); await settle(); h.aiOrb.emit('click'); await settle();
  assert.deepEqual(h.order.slice(0, 4), ['gum:start', 'gum:granted', 'track:stop', 'recognition:ctor']);
  assert.equal(h.order[4], 'recognition:start');
  assert.equal(h.tracks.length, 1); assert.equal(h.tracks[0].stopped, true);
  assert.equal(h.aiStatus.textContent, 'Слушаю…');
});

test('permission denial preserves draft and never starts recognizer or writes state', async () => {
  const denied = Object.assign(new Error('denied'), { name: 'NotAllowedError' });
  const h = make({ getUserMedia: async () => { throw denied; } });
  await settle(); h.aiInput.value = 'Старый черновик'; h.aiOrb.emit('click'); await settle();
  assert.equal(h.recognitions.length, 0); assert.equal(h.puts.length, 0);
  assert.equal(h.aiInput.value, 'Старый черновик');
  assert.match(h.aiStatus.textContent, /Микрофон запрещён для этого сайта/);
  assert.equal(h.aiInput.disabled, false);
});

test('pagehide while permission is pending stops the late stream and cannot start speech', async () => {
  let release;
  const h = make({ getUserMedia: () => new Promise(resolve => { release = resolve; }) });
  await settle(); h.aiOrb.emit('click'); await settle();
  assert.equal(h.aiInput.disabled, true); assert.equal(h.recognitions.length, 0);
  h.window.emit('pagehide');
  release(h.stream); await settle();
  assert.equal(h.recognitions.length, 0); assert.equal(h.puts.length, 0);
  assert.equal(h.tracks.length, 1); assert.equal(h.tracks[0].stopped, true);
});

test('second tap cancels a pending permission request without a late recognizer', async () => {
  let release;
  const h = make({ getUserMedia: () => new Promise(resolve => { release = resolve; }) });
  await settle(); h.aiInput.value = 'Черновик'; h.aiOrb.emit('click'); await settle();
  h.aiOrb.emit('click');
  assert.equal(h.aiInput.value, 'Черновик'); assert.equal(h.aiInput.disabled, false);
  release(h.stream); await settle();
  assert.equal(h.recognitions.length, 0); assert.equal(h.puts.length, 0);
  assert.equal(h.tracks[0].stopped, true);
});

test('permission probe code stays isolated from service workers, caches and intervals', () => {
  assert.match(source, /getUserMedia\(\{ audio: true \}\)/);
  assert.match(source, /stopMicrophoneStream/);
  assert.doesNotMatch(source, /MutationObserver|setInterval\s*\(|serviceWorker|caches\s*\.|innerHTML\s*=/);
});
