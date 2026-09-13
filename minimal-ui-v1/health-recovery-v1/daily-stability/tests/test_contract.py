"""Pure local build/scope contracts; no application/service/identity access."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('daily_builder', ROOT / 'build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

class BuildContract(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(builder.generate(), builder.generate())

    def test_scope_is_exactly_five_static_files(self):
        files = builder.generate()
        manifest = json.loads(files['release.json'])
        names = ['sync.js','app.js','ai-home-v2.js','index.html','manual.html']
        self.assertEqual([x['target'] for x in manifest['operations']], ['/opt/dvizh/static/'+x for x in names])
        self.assertEqual(manifest['restarts'], [])
        self.assertEqual(set(json.loads(files['PAYLOAD.json'])['changed_files']), set(names))
        for row in manifest['operations']:
            self.assertEqual(row['source'], 'minimal-ui-v1/health-recovery-v1/daily-stability/dist/'+row['target'].split('/')[-1])

    def test_design_boot_and_serviceworker_identical(self):
        files = builder.generate()
        for name in ['styles.css','ai-home-v2.css','boot.js','sw.js']:
            self.assertEqual(files['dist/'+name], (ROOT.parent/'dist'/name).read_bytes(), name)

    def test_manual_delta_is_only_four_display_fallbacks(self):
        files = builder.generate()
        original = (ROOT.parent/'dist/app.js').read_text()
        expected = original.replace('VIEW_COPY[state.tone]', "VIEW_COPY[state.tone === 'calm' ? 'calm' : 'direct']")
        self.assertEqual(original.count('VIEW_COPY[state.tone]'), 4)
        self.assertEqual(files['dist/app.js'].decode(), expected)

    def test_pending_and_cache_contracts(self):
        files = builder.generate()
        self.assertIn(b'text.trim().slice(0, 12000) === submission.text',files['dist/ai-home-v2.js'])
        for name in ['index.html','manual.html']:
            self.assertIn(b'20260914-daily-stability-1',files['dist/'+name])
        self.assertFalse(json.loads(files['PAYLOAD.json'])['production_installed'])
        self.assertTrue(json.loads(files['PAYLOAD.json'])['requires_owner_approval'])

    def fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix='daily-build-test-')
        self.addCleanup(temporary.cleanup)
        repo = Path(temporary.name)
        health = repo/'minimal-ui-v1/health-recovery-v1'
        daily = health/'daily-stability'
        daily.mkdir(parents=True)
        shutil.copyfile(ROOT/'build.py',daily/'build.py')
        shutil.copyfile(ROOT/'source-pins.json',daily/'source-pins.json')
        shutil.copyfile(ROOT.parent/'client_resilience.py',health/'client_resilience.py')
        shutil.copytree(ROOT.parent/'dist',health/'dist')
        return repo, health, daily

    def test_source_drift_stops_generation(self):
        repo, health, daily = self.fixture()
        (health/'dist/sync.js').write_text('unexpected source')
        with patch.multiple(builder, ROOT=daily, HEALTH=health, REPO=repo):
            with self.assertRaisesRegex(ValueError,'Historical snapshot changed'):
                builder.generate()
        self.assertFalse((daily/'dist').exists())

    def test_check_rejects_generated_drift(self):
        repo, health, daily = self.fixture()
        with patch.multiple(builder, ROOT=daily, HEALTH=health, REPO=repo):
            builder.build()
            (daily/'dist/sync.js').write_text('unexpected generated file')
            with self.assertRaisesRegex(ValueError,'differs'):
                builder.build(check=True)

    def test_extra_generated_targets_rejected(self):
        repo, health, daily = self.fixture()
        with patch.multiple(builder, ROOT=daily, HEALTH=health, REPO=repo):
            builder.build()
            (daily/'dist/unrelated.txt').write_text('unrelated')
            with self.assertRaisesRegex(ValueError,'Unexpected generated static target'):
                builder.build(check=True)

if __name__ == '__main__':
    unittest.main()
