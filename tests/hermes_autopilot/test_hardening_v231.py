import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'hermes-dev-v2'/f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

class HardeningTests(unittest.TestCase):
    def test_regression_harness_does_not_substitute_candidate_bytes(self):
        source = (ROOT/'hermes-dev-v2/regression_health.py').read_text()
        self.assertNotIn('sitecustomize', source)
        self.assertNotIn("production='untouched'", source)
        self.assertIn('--unshare-all', source)

    def test_health_never_invokes_candidate_helper(self):
        g = module('dvizhrelease')
        plan = {'restarts': [], 'operations': [{'verification': 'python-context'}]}
        with patch.object(g, 'http_get', return_value=b'{"ok":true}'), patch.object(g, 'run') as run:
            g.trusted_health(plan)
            run.assert_not_called()

    def test_jump_denied_in_both_schemas(self):
        g = module('dvizhrelease')
        self.assertNotIn('/opt/dvizh-jump/dvizh_jump/jump_web_bridge.py', g.TARGET_POLICY)
        self.assertEqual(g.target_risk('/opt/dvizh/jump_web_bridge.py'), 'deny')
        manifest = {'schema': 1, 'operations': [{'source': 'jump-goal-release/dvizh_jump/jump_web_bridge.py', 'target': '/opt/dvizh/jump_web_bridge.py'}], 'restarts': []}
        with self.assertRaises(g.GateError): g.validate_manifest({'mode': 'auto'}, manifest)
        self.assertNotIn('dvizh-jump.service', g.ALLOWED_RESTARTS)

    def test_installer_never_imports_adjacent_candidate(self):
        installer = module('owner_install')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch('importlib.util.spec_from_file_location', side_effect=AssertionError('candidate import')):
                installer.gate_for(root, fixture=True)

    def test_installer_installs_the_digest_buffer_despite_reread_race(self):
        import shutil
        installer = module('owner_install')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); fs = root/'fs'; fs.mkdir()
            payload = root/'payload'; shutil.copytree(ROOT/'hermes-dev-v2', payload)
            for target in installer.TARGETS:
                dest = fs/target.lstrip('/'); dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(b'# old\n'); dest.chmod(0o600 if target == installer.SKILL_TARGET else 0o755)
            for directory in [fs, *(p for p in fs.rglob('*') if p.is_dir())]:
                directory.chmod(0o755)
            gate = installer.gate_for(fs, fixture=True)
            expected = installer.payload_digest(payload)
            original = gate.read_regular
            def race(path):
                data, metadata = original(path)
                if path == payload/'dvizhrelease.py':
                    path.write_bytes(b'# changed after buffering\n')
                return data, metadata
            with patch.object(gate, 'read_regular', side_effect=race):
                rows = installer.prepare(gate, payload, expected)
            row = next(r for r in rows if r['target']=='/usr/local/sbin/dvizhrelease')
            self.assertEqual(row['new'], (ROOT/'hermes-dev-v2/dvizhrelease.py').read_bytes())

    def test_incomplete_candidate_cannot_reach_privileged_git_or_apply(self):
        for name in ('dvizhgitpush', 'dvizhrelease'):
            gate = module(name)
            with self.subTest(name=name), patch.object(gate, 'TEST_MODE', False), patch.object(gate.os, 'geteuid', return_value=0), patch.object(gate, 'run') as run:
                with self.assertRaisesRegex(gate.GateError, 'v2.3.1.*incomplete'):
                    gate.require_root()
                run.assert_not_called()
