'use strict';
// No network implementation is exposed to the VM. All state is synthetic.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const sourcePath = require('node:path').join(__dirname, 'baseline/sync.js');
const source = fs.readFileSync(sourcePath, 'utf8');
const boot = fs.readFileSync(require('node:path').join(__dirname, 'baseline/boot.js'), 'utf8');
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
async function harness() {
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
  respond('GET', {state: fixture(), revision: 10, updatedAt: T0});
  vm.runInContext(source, context, {filename: sourcePath});
  await context.DVIZH_SYNC_READY;
  assert.deepEqual(reloads, []);
  vm.runInContext(boot, context, {filename: '/opt/dvizh/static/boot.js'});
  await flush();
  assert.deepEqual(scripts, ['./app.js']); // Fake load event; app itself is traced separately.
  assert.equal(requests.length, 1); // Bootstrap from empty storage must not upload.
  return {context, respond, advance, reloads, requests, replies,
    state: () => JSON.parse(localStorage.getItem(KEY)),
    write: state => localStorage.setItem(KEY, JSON.stringify(state))};
}
async function pollCase(name, mutate, expected) {
  const h = await harness();
  const remote = fixture(); mutate(remote);
  h.respond('GET', {state: remote, revision: 11, updatedAt: T1});
  await h.advance(8000);
  assert.equal(h.context.DVIZH_SYNC.revision, 11);
  assert.deepEqual(h.state(), remote);
  assert.equal(h.reloads.length, 0);
  await h.advance(120);
  assert.equal(h.reloads.length, expected);
  assert.equal(h.requests.filter(r => r.method === 'PUT').length, 0);
  assert.equal(h.replies.length, 0);
  console.log(`PASS poll ${name}: reloads=${h.reloads.length} at=${JSON.stringify(h.reloads)}ms fakePUTs=0 remoteStored=true`);
}
(async () => {
  console.log(`Source ${sourcePath} sha256=${crypto.createHash('sha256').update(source).digest('hex')}`);
  await pollCase('revision/envelope timestamp only', () => {}, 0);
  await pollCase('coachPacket.exportedAt only', s => { s.jumpLab.coachPacket.exportedAt = T1; }, 0);
  await pollCase('__sync.updatedAt only', s => { s.__sync.updatedAt = T1; }, 1);
  await pollCase('entity _syncUpdatedAt only', s => { s.tasks[0]._syncUpdatedAt = T1; }, 1);
  await pollCase('task key order only', s => { s.tasks[0] = Object.fromEntries(Object.entries(s.tasks[0]).reverse()); }, 1);
  await pollCase('exportedAt + __sync.updatedAt', s => { s.jumpLab.coachPacket.exportedAt = T1; s.__sync.updatedAt = T1; }, 1);
  await pollCase('real remote task change', s => { s.tasks[0].title = 'Remote edit'; s.tasks[0]._syncUpdatedAt = T1; }, 1);
  for (const realChange of [false, true]) {
    const h = await harness();
    const local = h.state(); local.tasks[0].title = 'Local edit'; h.write(local);
    const remote = h.state();
    if (realChange) remote.tasks.push({id: 'remote-task', title: 'Remote addition', createdAt: T1, _syncUpdatedAt: T1});
    h.respond('PUT', {state: remote, revision: 11}, 409);
    h.respond('PUT', {revision: 12, updatedAt: T1});
    await h.advance(450);
    assert.equal(h.reloads.length, 0);
    await h.advance(120);
    assert.deepEqual(h.reloads, [570]);
    const puts = h.requests.filter(r => r.method === 'PUT');
    assert.deepEqual(puts.map(r => r.body.baseRevision), [10, 11]);
    assert.equal(h.state().tasks[0].title, 'Local edit');
    assert.equal(h.state().tasks.length, realChange ? 2 : 1);
    assert.equal(h.replies.length, 0);
    console.log(`PASS 409 ${realChange ? 'real remote change' : 'identical state'}: reloads=1 at=[570]ms fakePUTs=2 revisions=10,11 mergedEditsPreserved=true`);
  }
  {
    const h = await harness();
    h.write(h.state()); // Debounced push is queued, but not in flight.
    const remote = h.state();
    h.respond('GET', {state: remote, revision: 11, updatedAt: T1});
    await h.context.DVIZH_SYNC.pull();
    h.respond('PUT', {revision: 12, updatedAt: T1});
    await h.advance(570);
    assert.deepEqual(h.reloads, [570]);
    assert.deepEqual(h.state(), remote);
    console.log('PASS queued pull identical state: reloads=1 at=[570]ms fakePUTs=1');
  }
  // The historical SW diagnostic is outside the four-file pinned baseline.
  console.log('All assertions passed. Fetch was entirely fake; no production API requests.');
})().catch(error => { console.error(error); process.exitCode = 1; });
