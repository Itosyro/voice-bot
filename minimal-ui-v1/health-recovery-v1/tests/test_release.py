import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from test_domain import ROOT
REPO=ROOT.parents[1]

class ReleaseTests(unittest.TestCase):
    def test_pins_and_exact_authorized_sync_delta(self):
        self.assertEqual(hashlib.sha256((ROOT/"ARCHITECTURE-AUDIT.md").read_bytes()).hexdigest(),"b75e24f749be034729b16ad34892f4abbaa4ed66d3fd1e6adfbb3e14d09ad32b")
        pins=json.loads((ROOT/'baseline/pins.json').read_text())
        for file,pin in pins.items():
            self.assertEqual(hashlib.sha256((ROOT/'baseline'/file).read_bytes()).hexdigest(),pin['sha256'])
        for file in ['boot.js','index.html','ai-home-v2.js','ai-home-v2.css','styles.css','sw.js']:
            self.assertEqual((ROOT/'dist'/file).read_bytes(),(ROOT/'baseline/static'/file).read_bytes())
        sync=(ROOT/'baseline/static/sync.js').read_text()
        start=sync.index('  function reconcile(');end=sync.index('  // One-time upgrade:',start)
        expected=sync[:start]+(ROOT/'sync-health.js').read_text()+sync[start:end].replace('reconcile(', 'reconcileJSON(')+sync[end:]
        expected=expected.replace('    state.__sync = sync;\n    return state;', '    state.__sync = sync;\n    return normalizeHealthSleep(state);',1)
        self.assertEqual((ROOT/'dist/sync.js').read_text(),expected)
        html=(ROOT/'dist/manual.html').read_text()
        self.assertIn((ROOT/'baseline/static/manual.html').read_text().split('<style id="quiet-signal-manual-v2">')[1].split('</style>')[0],html)
    def test_self_contained_helpers_manifests(self):
        manifest=json.loads((ROOT/'manifests/health-recovery-privileged.json').read_text())
        expected={'/usr/local/libexec/dvizh-context':('hermes-control-v1/dvizh_context.py','python-syntax'),'/usr/local/libexec/dvizh-proposals':('hermes-control-v1/dvizh_proposals.py','python-syntax'),'/opt/dvizh-ai-approval/proposal_bridge.py':('hermes-control-v1/dvizh_proposal_bridge.py','python-syntax-service')}
        self.assertEqual({r['target'] for r in manifest['operations']},set(expected))
        for row in manifest['operations']:
            self.assertEqual((row['source'],row['verification']),expected[row['target']])
            self.assertEqual(row['sha256'],hashlib.sha256((REPO/row['source']).read_bytes()).hexdigest())
            self.assertEqual(row['required_owner'],'root:root');self.assertEqual(row['required_mode'],'0755');self.assertEqual(row['release_class'],'ai-integration-privileged')
            source=(REPO/row['source']).read_text();compile(source,row['source'],'exec')
            self.assertNotIn('from domain import',source)
        self.assertEqual(manifest['restarts'],['dvizh-ai-approval.service']);self.assertTrue(manifest['restart_reason'])
        for name in ['frontend','ai-home']:
            ordinary=json.loads((ROOT/f'manifests/health-recovery-{name}.json').read_text())
            self.assertTrue(all(r['target'] not in expected for r in ordinary['operations']))
            for row in ordinary['operations']:
                # Installed v2.2 accepts SHA only on privileged operations.
                self.assertTrue(set(row) <= {'source', 'target', 'http_path'})
                self.assertTrue((REPO/row['source']).is_file())
    def test_builder_reproducible(self):
        paths=[*list((ROOT/'dist').glob('*')),*list((ROOT/'manifests').glob('health-recovery-*.json')),*(REPO/'hermes-control-v1'/name for name in ['dvizh_context.py','dvizh_proposals.py','dvizh_proposal_bridge.py']),REPO/'ai-home-v2/ai_home_bridge.py']
        before={str(p):p.read_bytes() for p in paths}
        subprocess.check_call(['python3',str(ROOT/'build.py')])
        self.assertEqual(before,{str(p):p.read_bytes() for p in paths})
