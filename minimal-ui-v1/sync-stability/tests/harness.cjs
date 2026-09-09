'use strict';
// No network implementation is exposed to the VM. All state is synthetic.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const sourcePath = require('node:path').join(__dirname, '../release/sync.js');
const source = fs.readFileSync(sourcePath, 'utf8');
const boot = fs.readFileSync(require('node:path').join(__dirname, '../baseline/boot.js'), 'utf8');
const KEY = 'dvizh-state-v1';
const T0 = '2026-01-01T00:00:00.000Z';
const T1 = '2026-01-01T00:01:00.000Z';
const copy = x => JSON.parse(JSON.stringify(x));
const fixture = () => ({version: 1, createdAt: T0, hasSeenIntro: true,
  tasks: [{id: 'synthetic-task', title: 'Synthetic task', createdAt: T0, _syncUpdatedAt: T0}],
  sessions: [], proofs: [], checkins: {}, plans: {}, ladder: {},
  jumpLab: {coachPacket: {exportedAt: T0, summary: 'Synthetic packet'}},
  __sync: {updatedAt: T0, settingsUpdatedAt: T0, resetAt: null,
    deletedTasks: {}, deletedProofs: {}, ladderUpdatedAt: {}, clientId: 'synthetic-client'}});
async function harness(options = {}) {
  let now = 0, nextId = 0;
  const timers = new Map(), replies = [], requests = [], reloads = [], scripts = [];
  class Storage {
    constructor() { this.values = new Map(); }
    getItem(k) { return this.values.get(String(k)) ?? null; }
    setItem(k, v) { this.values.set(String(k), String(v)); }
    removeItem(k) { this.values.delete(String(k)); }
  }
  const localStorage = new Storage();
  localStorage.setItem('dvizh-client-id-v1', 'synthetic-client');
  if (options.local) localStorage.setItem(KEY, JSON.stringify(options.local));
  if (options.meta) localStorage.setItem('dvizh-sync-meta-v1', JSON.stringify(options.meta));
  const timer = (fn, delay, interval = false) => {
    const id = ++nextId; timers.set(id, {fn, at: now + delay, delay, interval}); return id;
  };
  const listeners = {};
  const document = {readyState: 'complete', visibilityState: 'visible',
    getElementById: () => null, addEventListener: (k, fn) => { listeners[k] = fn; },
    createElement: () => ({events: {}, addEventListener(k, fn) { this.events[k] = fn; }}),
    body: {appendChild(script) { scripts.push(script.src); script.events.load(); }}};
  class FakeDate extends Date {
    constructor(...args) { super(...(args.length ? args : [Date.parse(T0) + now])); }
    static now() { return Date.parse(T0) + now; }
  }
  const context = vm.createContext({Storage, localStorage, document, Date: FakeDate,
    navigator: {onLine: true}, location: {pathname: '/manual.html', reload() { reloads.push(now); }},
    setTimeout: (fn, ms) => timer(fn, ms), clearTimeout: id => timers.delete(id),
    setInterval: (fn, ms) => timer(fn, ms, true), clearInterval: id => timers.delete(id),
    addEventListener: (k, fn) => { listeners[k] = fn; }, console,
    fetch: async (url, options = {}) => {
      assert.equal(url, '/api/state');
      const method = options.method || 'GET';
      const reply = replies.shift();
      requests.push({method, body: options.body && JSON.parse(options.body)});
      assert.ok(reply, `Unexpected fake fetch ${method}`);
      assert.equal(method, reply.method);
      if (reply.wait) await reply.wait;
      if (reply.error) throw new Error(reply.error);
      return {status: reply.status, ok: reply.status < 400, json: async () => copy(reply.body)};
    }});
  context.window = context;
  const respond = (method, body, status = 200) => replies.push({method, body, status});
  const flush = async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); };
  const advance = async ms => {
    const end = now + ms;
    while (true) {
      const entry = [...timers].filter(([, t]) => t.at <= end).sort((a,b) => a[1].at - b[1].at || a[0] - b[0])[0];
      if (!entry) break;
      const [id, t] = entry; now = t.at;
      if (t.interval) t.at += t.delay; else timers.delete(id);
      await t.fn(); await flush();
    }
    now = end; await flush();
  };
  if (options.offline) replies.push({method:'GET',error:'offline'});
  else respond('GET', {state: options.remote || fixture(), revision: 10, updatedAt: T0});
  if (options.beforeReady || options.upgrade) respond('PUT',{revision:11});
  vm.runInContext(source, context, {filename: sourcePath});
  options.beforeReady?.(context);
  await context.DVIZH_SYNC_READY;
  assert.deepEqual(reloads, []);
  context.DVIZH_MANUAL_STATE = {applyRemote() {}}; // Unit tests model a compatible app; actual mixed apps run in dom-harness.
  vm.runInContext(boot, context, {filename: '/opt/dvizh/static/boot.js'});
  await flush();
  if (options.beforeReady || options.upgrade) await advance(450);
  assert.deepEqual(scripts, ['./app.js']); // Fake load event; app itself is traced separately.
  if (!options.beforeReady && !options.upgrade) assert.equal(requests.length, 1); // Bootstrap from empty storage must not upload.
  return {context, respond, advance, reloads, requests, replies, flush, listeners,
    state: () => JSON.parse(localStorage.getItem(KEY)),
    write: state => localStorage.setItem(KEY, JSON.stringify(state))};
}

module.exports = {harness, fixture, copy, T0, T1};
