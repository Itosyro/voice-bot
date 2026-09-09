from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_release_gate import load_gate, blob

TARGETS = {
    '/usr/local/libexec/dvizh-context': ('hermes-control-v1/dvizh_context.py', 'python-syntax'),
    '/usr/local/libexec/dvizh-proposals': ('hermes-control-v1/dvizh_proposals.py', 'python-syntax'),
    '/opt/dvizh-ai-approval/proposal_bridge.py': ('hermes-control-v1/dvizh_proposal_bridge.py', 'python-syntax-service'),
}
CLASS = 'ai-integration-privileged'


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.fs = self.root / 'fs'
        self.source.mkdir(); self.fs.mkdir()
        self.g = load_gate(self.root, self.source, self.fs, self.root / 'approvals', self.root / 'backups', 'http://127.0.0.1:1')
        self.proposal = {'schema': 1, 'id': 'release-test', 'job_id': 'job', 'mode': 'auto', 'repo': self.g.REPO, 'branch': 'hermes/dev/test', 'commit': 'a' * 40, 'manifest': '.autopilot/release.json'}
        self.rows = []
        self.old = b'# original\n'
        self.new = b'# replacement\n'
        for target, (source, verification) in TARGETS.items():
            p = self.source / source; p.parent.mkdir(exist_ok=True); p.write_bytes(self.new)
            p = self.fs / target.lstrip('/'); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(self.old); p.chmod(0o755)
            self.rows.append(dict(source=source, target=target, sha256=hashlib.sha256(self.new).hexdigest(), release_class=CLASS, required_owner='root:root', required_mode='0755', verification=verification))
        self.manifest = {'schema': 1, 'operations': self.rows, 'restarts': ['dvizh-ai-approval.service'], 'restart_reason': 'Load the updated long-running approval bridge.'}
        # Privileged fixture ancestors model the required non-writable root tree.
        for directory in [self.fs, *(p for p in self.fs.rglob('*') if p.is_dir())]:
            directory.chmod(0o755)

    def plan(self):
        return self.g.validate_manifest(self.proposal, self.manifest)

    def test_exact_class_always_approval(self):
        result = self.plan()
        self.assertEqual(result['risk'], CLASS)
        self.assertTrue(result['approval_required'])
        self.assertEqual(set(self.g.PRIVILEGED_TARGETS), set(TARGETS))

    def test_helpers_need_no_restart_bridge_requires_justification(self):
        self.manifest['operations'] = self.rows[:2]
        self.manifest['restarts'] = []; self.manifest.pop('restart_reason')
        self.assertTrue(self.plan()['approval_required'])
        self.manifest['restarts'] = ['dvizh-ai-approval.service']
        with self.assertRaises(self.g.GateError): self.plan()
        self.manifest['operations'] = self.rows
        for reason in ('', None):
            self.manifest['restart_reason'] = reason
            with self.assertRaises(self.g.GateError): self.plan()

    def test_reject_extra_fields_missing_fields_wrong_policy(self):
        self.plan()
        for key, value in [('required_owner', 'dvizh:dvizh'), ('required_mode', '0777'), ('verification', 'curl https://evil'), ('sha256', 'bad'), ('release_class', 'safe'), ('source', 'hermes-dev-v2/dvizhrelease.py'), ('command', 'id'), ('http_path', 'https://evil')]:
            with self.subTest(key=key), patch.dict(self.rows[0], {key: value}):
                with self.assertRaises(self.g.GateError): self.plan()
        for key in self.rows[0].copy():
            value = self.rows[0].pop(key)
            with self.assertRaises(self.g.GateError): self.plan()
            self.rows[0][key] = value
        self.manifest['files'] = ['extra']
        with self.assertRaises(self.g.GateError): self.plan()

    def test_raw_paths_and_exact_target_denials(self):
        self.plan()
        for target in ['/usr/local/libexec/./dvizh-context', '/usr/local//libexec/dvizh-context', '/usr/local/libexec/x/../dvizh-context', '/usr/local/libexec/dvizh-context/', '//usr/local/libexec/dvizh-context', '/usr/local/libexec/dvizh-context-extra', '/opt/dvizh-ai-approval/patch_ai_approval_ui.py', '/usr/local/sbin/dvizhrelease', '/etc/systemd/system/dvizh-ai-approval.service']:
            with self.subTest(target=target), patch.dict(self.rows[0], {'target': target}):
                with self.assertRaises(self.g.GateError): self.plan()
        for source in ['./hermes-control-v1/dvizh_context.py', 'hermes-control-v1//dvizh_context.py', 'hermes-control-v1/../hermes-control-v1/dvizh_context.py']:
            with patch.dict(self.rows[0], {'source': source}):
                with self.assertRaises(self.g.GateError): self.plan()


class TrustTests(ContractTests):
    def publish(self):
        raw = json.dumps(self.manifest).encode()
        p = self.source / self.proposal['manifest']; p.parent.mkdir(exist_ok=True); p.write_bytes(raw)
        self.proposal['manifest_blob'] = blob(raw)
        self.proposal_path = self.root / 'proposal.json'
        self.proposal_path.write_text(json.dumps(self.proposal))
        tree = [{'path': str(p.relative_to(self.source)), 'type': 'blob', 'mode': '100644', 'sha': blob(p.read_bytes())} for p in self.source.rglob('*') if p.is_file()]
        self.tree = {'tree': tree, 'truncated': False}
        self.ci = {'total_count': 1, 'workflow_runs': [{'head_sha': 'a' * 40, 'head_branch': 'hermes/dev/test', 'event': 'push', 'path': '.github/workflows/dvizh-hermes-autopilot.yml', 'status': 'completed', 'conclusion': 'success'}]}
        self.api = patch.object(self.g, 'api_json', side_effect=lambda url: self.tree if '/git/trees/' in url else self.ci)
        self.api.start(); self.addCleanup(self.api.stop)

    def load(self):
        return self.g.load_and_plan(str(self.proposal_path))

    def test_trusted_download_sha_and_git_regular_blob(self):
        self.publish(); self.load()
        p = self.source / self.rows[0]['source']; p.write_bytes(b'# tampered\n')
        with self.assertRaises(self.g.GateError): self.load()
        p.write_bytes(self.new)
        for mode in ['120000', '160000', '040000']:
            self.tree['tree'][0]['mode'] = mode
            with self.assertRaises(self.g.GateError): self.load()

    def test_manifest_sha_and_independent_source_sha(self):
        self.rows[0]['sha256'] = '0' * 64
        self.publish()
        with self.assertRaises(self.g.GateError): self.load()
        self.rows[0]['sha256'] = hashlib.sha256(self.new).hexdigest()
        self.proposal['manifest_blob'] = '0' * 40
        self.proposal_path.write_text(json.dumps(self.proposal))
        with self.assertRaises(self.g.GateError): self.load()

    def test_ci_red_missing_pending_wrong_commit_and_truncated_tree(self):
        self.publish(); self.load()
        for key, value in [('conclusion', 'failure'), ('status', 'in_progress'), ('head_sha', 'b' * 40), ('event', 'workflow_dispatch'), ('path', 'other.yml')]:
            with patch.dict(self.ci['workflow_runs'][0], {key: value}):
                with self.assertRaises(self.g.GateError): self.load()
        with patch.dict(self.ci, {'workflow_runs': []}):
            with self.assertRaises(self.g.GateError): self.load()
        self.tree['truncated'] = True
        with self.assertRaises(self.g.GateError): self.load()

    def test_source_destination_and_proposal_symlinks_and_nonregular(self):
        self.publish(); self.load()
        paths = [self.source / self.rows[0]['source'], self.fs / self.rows[0]['target'].lstrip('/'), self.proposal_path]
        for path in paths:
            saved = path.with_suffix('.saved'); path.rename(saved)
            path.symlink_to(saved)
            with self.assertRaises(self.g.GateError): self.load()
            path.unlink(); saved.rename(path)
        for path in [self.source / 'hermes-control-v1', self.fs / 'usr/local/libexec']:
            saved = path.with_name(path.name + '-saved'); path.rename(saved); path.symlink_to(saved, target_is_directory=True)
            with self.assertRaises(self.g.GateError): self.load()
            path.unlink(); saved.rename(path)
        path = self.fs / self.rows[0]['target'].lstrip('/')
        path.unlink(); os.mkfifo(path)
        with self.assertRaises(self.g.GateError): self.load()

    def test_auto_missing_expired_wrong_digest_exact_phrase_and_replay(self):
        self.publish()
        planned = self.g.plan_release(str(self.proposal_path))
        for approval in [None, planned['approval_token'], 'APPROVE wrong token']:
            with self.assertRaises(self.g.GateError): self.g.apply(str(self.proposal_path), approval)
        approval_file = self.g.approval_file(self.proposal['id'])
        original = approval_file.read_bytes()
        for changes in [{'created': 1}, {'created': 10**12}, {'digest': 'wrong'}]:
            value = json.loads(original); value.update(changes); approval_file.write_text(json.dumps(value))
            with self.assertRaises(self.g.GateError): self.g.apply(str(self.proposal_path), planned['approval_phrase'])
        approval_file.write_bytes(original)
        with patch.object(self.g, 'apply_release', return_value={'ok': True}) as apply:
            self.g.apply(str(self.proposal_path), planned['approval_phrase'])
            apply.assert_called_once()
            with self.assertRaises(self.g.GateError): self.g.apply(str(self.proposal_path), planned['approval_phrase'])


class TransactionTests(TrustTests):
    def deploy(self):
        self.publish()
        planned = self.g.plan_release(str(self.proposal_path))
        return self.g.apply(str(self.proposal_path), planned['approval_phrase'])

    def assert_original(self):
        for row in self.rows:
            p = self.fs / row['target'].lstrip('/')
            self.assertEqual(p.read_bytes(), self.old)
            st = p.stat()
            self.assertEqual((st.st_uid, st.st_gid, st.st_mode & 0o7777), (os.getuid(), os.getgid(), 0o755))

    def test_all_backups_verified_before_first_write(self):
        original_write = self.g.atomic_write
        def fail_backup(path, *args, **kwargs):
            if path.parent.parent == self.g.BACKUP_ROOT and path.name.startswith('01-'):
                raise OSError('backup storage failed')
            if str(path).startswith(str(self.fs)):
                self.fail('production write before all backups completed')
            return original_write(path, *args, **kwargs)
        with patch.object(self.g, 'atomic_write', side_effect=fail_backup), patch.object(self.g, 'http_get', return_value=b'healthy'):
            with self.assertRaisesRegex((self.g.GateError, OSError), 'backup'): self.deploy()
        self.assert_original()

    def test_atomic_apply_records_metadata_and_hashes(self):
        with patch.object(self.g, 'http_get', return_value=b'healthy'):
            result = self.deploy()
        mapping = json.loads((Path(result['backup']) / 'mapping.json').read_text())
        self.assertEqual(len(mapping), 3)
        for record in mapping:
            self.assertEqual(record['sha256'], hashlib.sha256(self.old).hexdigest())
            self.assertEqual((record['uid'], record['gid'], record['mode']), (os.getuid(), os.getgid(), 0o755))
            self.assertEqual(Path(record['backup']).read_bytes(), self.old)
        for row in self.rows:
            p = self.fs / row['target'].lstrip('/')
            self.assertEqual(p.read_bytes(), self.new)
            self.assertEqual(p.stat().st_mode & 0o7777, 0o755)

    def test_partial_failure_restores_every_file_metadata_and_health(self):
        original = self.g.atomic_write
        writes = []
        def fail_second(path, data, *args, **kwargs):
            if str(path).startswith(str(self.fs)):
                writes.append(str(path))
                if len(writes) == 2:
                    path.chmod(0o600)
                    raise OSError('partial write failure')
            return original(path, data, *args, **kwargs)
        with patch.object(self.g, 'atomic_write', side_effect=fail_second), patch.object(self.g, 'http_get', return_value=b'healthy') as health:
            with self.assertRaisesRegex(self.g.GateError, 'rollback confirmed'): self.deploy()
            self.assertGreaterEqual(health.call_count, 2)
        self.assert_original()
        self.assertEqual(len(writes), 5)

    def test_restart_failure_restarts_restored_service_and_confirms_health(self):
        with patch.object(self.g, 'restart_service', side_effect=[self.g.GateError('restart failed'), None]) as restart, patch.object(self.g, 'http_get', return_value=b'healthy'):
            with self.assertRaisesRegex(self.g.GateError, 'rollback confirmed'): self.deploy()
            self.assertEqual(restart.call_count, 2)
        self.assert_original()

    def test_rollback_failure_is_critical_and_remaining_files_attempted(self):
        with patch.object(self.g, 'restart_service', side_effect=self.g.GateError('restart failed')), patch.object(self.g, 'http_get', return_value=b'healthy'):
            with self.assertRaisesRegex(self.g.GateError, 'CRITICAL.*rollback unconfirmed'): self.deploy()
        self.assert_original()

    def test_refetched_bytes_reverified_before_write(self):
        self.publish()
        planned = self.g.plan_release(str(self.proposal_path))
        original = self.g.fetch_bytes
        calls = 0
        def tamper(commit, source):
            nonlocal calls
            if source == self.rows[0]['source']:
                calls += 1
                if calls > 1: return b'# download substituted'
            return original(commit, source)
        with patch.object(self.g, 'fetch_bytes', side_effect=tamper):
            with self.assertRaises(self.g.GateError): self.g.apply(str(self.proposal_path), planned['approval_phrase'])
        self.assert_original()


class HardeningTests(TrustTests):
    def test_no_mixed_extra_files(self):
        self.manifest['operations'].append({'source': 'ai-home-v2/index.html', 'target': '/opt/dvizh/static/index.html', 'http_path': '/'})
        with self.assertRaises(self.g.GateError): self.plan()

    def test_duplicate_json_keys_rejected(self):
        self.publish()
        raw = self.proposal_path.read_text()
        self.proposal_path.write_text(raw[:-1] + ', "mode": "safe"}')
        with self.assertRaises(self.g.GateError): self.load()

    def test_plan_rejects_metadata_drift(self):
        self.publish()
        (self.fs / self.rows[0]['target'].lstrip('/')).chmod(0o777)
        with self.assertRaises(self.g.GateError): self.load()

    def test_root_cannot_use_fixture_environment(self):
        with patch.object(self.g.os, 'geteuid', return_value=0):
            with self.assertRaises(self.g.GateError): self.g.require_root()

    def test_atomic_failure_and_metadata_order(self):
        p = self.fs / self.rows[0]['target'].lstrip('/')
        events = []
        originals = {name: getattr(self.g.os, name) for name in ['fchown', 'fchmod', 'fsync', 'replace']}
        def capture(name):
            def call(*args, **kwargs):
                events.append(name)
                return originals[name](*args, **kwargs)
            return call
        with patch.object(self.g.os, 'fchown', side_effect=capture('fchown')), patch.object(self.g.os, 'fchmod', side_effect=capture('fchmod')), patch.object(self.g.os, 'fsync', side_effect=capture('fsync')), patch.object(self.g.os, 'replace', side_effect=capture('replace')):
            self.g.atomic_write(p, self.new)
        self.assertEqual(events, ['fchown', 'fchmod', 'fsync', 'replace', 'fsync'])
        with patch.object(self.g.os, 'replace', side_effect=OSError('replace failed')):
            with self.assertRaises(OSError): self.g.atomic_write(p, self.old)
        self.assertEqual(p.read_bytes(), self.new)
        self.assertEqual(list(p.parent.glob('.*.autopilot.*')), [])

    def test_post_health_failure_and_rollback_health_failure(self):
        self.publish()
        planned = self.g.plan_release(str(self.proposal_path))
        with patch.object(self.g, 'http_get', side_effect=[b'healthy', self.g.GateError('health failed'), self.g.GateError('rollback health failed')]):
            with self.assertRaisesRegex(self.g.GateError, 'CRITICAL.*rollback unconfirmed'):
                self.g.apply(str(self.proposal_path), planned['approval_phrase'])
        for row in self.rows:
            self.assertEqual((self.fs / row['target'].lstrip('/')).read_bytes(), self.old)

    def test_backup_corruption_zero_destination_writes(self):
        self.publish()
        planned = self.g.plan_release(str(self.proposal_path))
        original = self.g.atomic_write
        def corrupt(path, data, *args, **kwargs):
            if str(path).startswith(str(self.fs)):
                self.fail('destination written after corrupt backup')
            original(path, data, *args, **kwargs)
            if path.name.startswith('01-'): path.write_bytes(b'corrupted')
        with patch.object(self.g, 'http_get', return_value=b'healthy'), patch.object(self.g, 'atomic_write', side_effect=corrupt):
            with self.assertRaises(self.g.GateError): self.g.apply(str(self.proposal_path), planned['approval_phrase'])

    def test_symlinked_source_directory_and_fifo_and_directory(self):
        self.publish()
        p = self.source / self.rows[0]['source']
        p.unlink(); os.mkfifo(p)
        with self.assertRaises(self.g.GateError): self.load()
        p.unlink(); p.mkdir()
        with self.assertRaises(self.g.GateError): self.load()

class BoundaryTests(TrustTests):
    def test_privileged_restarts_only_approval_bridge(self):
        self.manifest['restarts'].append('dvizh.service')
        with self.assertRaises(self.g.GateError): self.plan()

    def test_proposal_extra_fields_denied(self):
        self.proposal['command'] = 'id'
        self.publish()
        with self.assertRaises(self.g.GateError): self.load()

    def test_guarded_push_control_plane_and_friend_denials_without_git(self):
        import importlib.util
        path = Path(__file__).resolve().parents[2] / 'hermes-dev-v2/dvizhgitpush.py'
        spec = importlib.util.spec_from_file_location('push_policy_v22', path)
        gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
        for name in ['hermes-dev-v2/dvizhrelease.py', 'tests/hermes_autopilot/test_release_v22.py', 'install-dvizh-hermes-autopilot.sh', '.github/workflows/dvizh-hermes-autopilot.yml', '.github/workflows/dvizh-hermes-autopilot-v2-tests.yml', '.github/workflows/dvizh-hermes-autopilot-installer-smoke.yml', 'src/a.py', 'migrations/a.py', 'tests/test_a.py', 'Dockerfile', 'docker-compose.yml', 'docker-compose.server.yml', 'pyproject.toml', 'alembic.ini', 'Makefile', 'README.md']:
            with self.subTest(name=name): self.assertFalse(gate.path_allowed(name))
        for source, _ in TARGETS.values(): self.assertTrue(gate.path_allowed(source))

    def test_workflow_accepts_privileged_contract_rejects_bad_policy(self):
        import subprocess
        root = Path(__file__).resolve().parents[2]
        workflow = (root / '.github/workflows/dvizh-hermes-autopilot.yml').read_text()
        start = workflow.index("          import json\n", workflow.index('Validate committed release manifest'))
        end = workflow.index("          PY", start)
        code = '\n'.join(line[10:] for line in workflow[start:end].splitlines())
        (self.source / 'hermes-dev-v2').symlink_to(root / 'hermes-dev-v2', target_is_directory=True)
        self.publish()
        def run():
            return subprocess.run(['python3', '-c', code], cwd=self.source, capture_output=True, text=True)
        result = run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.rows[0]['required_mode'] = '0777'
        (self.source / self.proposal['manifest']).write_text(json.dumps(self.manifest))
        self.assertNotEqual(run().returncode, 0)

    def test_rollback_file_failure_continues_other_restores(self):
        self.publish()
        planned = self.g.plan_release(str(self.proposal_path))
        original = self.g.atomic_write
        restores = []
        def fail_restore(path, data, *args, **kwargs):
            if str(path).startswith(str(self.fs)) and data == self.old:
                restores.append(path)
                if len(restores) == 1: raise OSError('restore failure')
            return original(path, data, *args, **kwargs)
        with patch.object(self.g, 'atomic_write', side_effect=fail_restore), patch.object(self.g, 'restart_service', side_effect=[self.g.GateError('restart failed'), None]), patch.object(self.g, 'http_get', return_value=b'healthy'):
            with self.assertRaisesRegex(self.g.GateError, 'CRITICAL.*rollback unconfirmed'):
                self.g.apply(str(self.proposal_path), planned['approval_phrase'])
        self.assertEqual(len(restores), 3)
        for row in self.rows[:2]: self.assertEqual((self.fs / row['target'].lstrip('/')).read_bytes(), self.old)


class LiveFixtureTests(TrustTests):
    def test_three_file_apply_with_real_local_http_and_temp_files(self):
        from test_release_gate import FixtureServer
        health = self.fs / 'api/health'; health.parent.mkdir(); health.write_bytes(b'{"ok":true}')
        self.publish()
        with FixtureServer(self.fs) as server:
            self.g.HTTP_BASE = server.base
            planned = self.g.plan_release(str(self.proposal_path))
            result = self.g.apply(str(self.proposal_path), planned['approval_phrase'])
        self.assertTrue(result['ok'])
        for row in self.rows:
            self.assertEqual((self.fs / row['target'].lstrip('/')).read_bytes(), self.new)

    def test_invalid_python_and_missing_target_fail_before_backup(self):
        self.new = b'def invalid syntax'
        for row in self.rows:
            (self.source / row['source']).write_bytes(self.new)
            row['sha256'] = hashlib.sha256(self.new).hexdigest()
        self.publish()
        with self.assertRaises(self.g.GateError): self.load()
        self.assertFalse(self.g.BACKUP_ROOT.exists())
        (self.fs / self.rows[0]['target'].lstrip('/')).unlink()
        with self.assertRaises(self.g.GateError): self.load()


if __name__ == '__main__': unittest.main()
