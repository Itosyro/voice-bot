const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = __dirname;
const pins = require('./baseline-pins.json');
for (const [name, hash] of Object.entries(pins)) {
  const bytes = fs.readFileSync(path.join(root, 'baseline', name));
  if (crypto.createHash('sha256').update(bytes).digest('hex') !== hash) throw Error(`Baseline pin mismatch: ${name}`);
}
const transform = require('./src/transform.cjs');
const artifacts = {};
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
for (const name of ['app.js', 'sync.js', 'manual.html']) {
  const result = transform(name, fs.readFileSync(path.join(root, 'baseline', name), 'utf8'));
  artifacts[name] = digest(result);
  const target = path.join(root, 'release', name);
  if (process.argv.includes('--check')) {
    if (fs.readFileSync(target, 'utf8') !== result) throw Error(`Generated drift: ${name}`);
  } else fs.writeFileSync(target, result);
}
const manifest = JSON.stringify({
  schema: 1, status: 'candidate-for-independent-review', baseline: pins, artifacts,
  sources: Object.fromEntries(['build.cjs', 'src/transform.cjs', 'src/reconcile.js', 'src/app-boundary.js', 'src/protective.js'].map(name => [name, digest(fs.readFileSync(path.join(root, name)))])),
  contracts: {bootTarget:'denied', manualHtml:'pinned baseline; only sync script query changed', manualEntry:'/manual.html?v=20260909-sync-stability-2', syncEntry:'/sync.js?v=20260909-sync-stability-2', cacheAssumptions:{manualHtml:'public, max-age=604800, immutable',syncJs:'public, max-age=604800, immutable',appJs:'no-cache',queryKeysDistinct:true}, design:'deployed Quiet Signal', pollMs:8000, pushDebounceMs:450,
    pollingLoopsAdded:0, reloadCalls:0, stateBoundary:'DVIZH_MANUAL_STATE.applyRemote',
    cacheCompatibility:{oldSyncNewApp:'original saves/commands; legacy reload behavior remains',newSyncNewApp:'full reconciliation boundary',newSyncOldApp:'protective after markAppLoaded: canonical server state separate from quarantined writes; no PUT; user-action versioned update with verified draft archive and explicit manual recovery'},
    conflictPolicy:'three-way changed local leaf wins; identity deletion wins; newest reset wins',
    displayPolicy:'DOM-free remote acceptance; explicit navigation/user rendering exposes new data',
    api:'/api/state; revision CAS including reset; one immediate 409 retry then existing retry delay',
    targets:['app.js','sync.js','manual.html'], productionTouched:false}
}, null, 2) + '\n';
const manifestPath = path.join(root, 'release-manifest.json');
if (process.argv.includes('--check')) {
  if (fs.readFileSync(manifestPath, 'utf8') !== manifest) throw Error('Manifest drift');
  if (fs.readdirSync(path.join(root, 'release')).sort().join(',') !== 'app.js,manual.html,sync.js') throw Error('Unexpected release target');
} else fs.writeFileSync(manifestPath, manifest);
console.log(process.argv.includes('--check') ? 'PASS pinned reproducible build --check' : 'Built app.js + sync.js + manual.html from pinned baseline');
