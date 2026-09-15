import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

MOD = Path(__file__).resolve().parents[1] / 'inventory.py'
spec = importlib.util.spec_from_file_location('inventory', MOD)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SECRET = 'DO-NOT-SHOW-THIS-PRIVATE-VALUE'
CID = 'a' * 64


class Runner:
    def __init__(self):
        self.calls = []
    def __call__(self, args, timeout=8):
        self.calls.append(args)
        data = ''
        if args[:2] == ['systemctl', 'list-unit-files']:
            data = 'dvizh.service enabled\ndvizh-auth.service enabled\nhermes-api.service enabled\nsshd.service enabled\n'
        elif args[:2] == ['systemctl', 'show']:
            n = args[-1]
            if n in ('dvizh.service', 'dvizh-auth.service', 'hermes-api.service', 'my-worker.service'):
                data = f'LoadState=loaded\nActiveState=active\nUser=dvizh\nGroup=dvizh\nFragmentPath=/etc/systemd/system/{n}\nEnvironmentFiles=/etc/dvizh/auth.env (ignore_errors=no)\nEnvironment=API_KEY={SECRET}\n'
            else:
                data = 'LoadState=not-found\n'
        elif args[0] == 'du':
            data = '1048576\t' + args[-1] + '\n'
        elif args[0] == 'dpkg-query':
            data = 'python3\t3.12.3\tamd64\npython3.12\t3.12.3\tamd64\nnot-selected\t1\tamd64\n'
        elif args[0] == 'ss':
            data = 'LISTEN 0 128 127.0.0.1:8000 0.0.0.0:*\nLISTEN 0 128 127.0.0.1:8002 0.0.0.0:*\n'
        elif args[:2] == ['docker', 'ps']:
            data = CID + '\n'
        elif args[:2] == ['docker', 'inspect']:
            data = json.dumps({'image_id': 'sha256:' + 'b' * 64, 'running': True,
                'mounts': [{'Type': 'volume', 'Source': '/var/lib/docker/volumes/example/_data', 'Destination': '/data', 'DO_NOT_PRINT': SECRET}],
                'Config': {'Env': [SECRET]}})
        return {'status': 'ok', 'output': data}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for d in ('opt/dvizh/static', 'home/exedev/.hermes', 'root', 'etc/systemd/system', 'etc/dvizh',
                  'usr/local/bin', 'usr/local/sbin', 'usr/local/libexec', 'var/lib/dvizh', 'proc/self'):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        (self.root/'etc/os-release').write_text('ID=ubuntu\nVERSION_ID="24.04"\nPRETTY_NAME="Ubuntu 24.04 LTS"\nOTHER=' + SECRET)
        (self.root/'etc/dvizh/auth.env').write_text('API_KEY=' + SECRET)
        (self.root/'home/exedev/.hermes/config.yaml').write_text('token: ' + SECRET)
        (self.root/'var/lib/dvizh/state.db').write_text(SECRET)
        (self.root/'etc/systemd/system/my-worker.service').write_text('ExecStart=/bin/echo ' + SECRET)
        (self.root/'etc/systemd/system/job.timer').write_text('secret=' + SECRET)
        (self.root/'proc/self/mountinfo').write_text('22 1 8:1 / / rw,relatime - ext4 /dev/vda1 rw\n24 22 0:20 / /data rw - ext4 /dev/vdb rw\n')
        for n in m.KNOWN:
            (self.root/'opt/dvizh/static'/n).write_text('test-' + n)
        self.runner = Runner()
        self.inv = m.Inventory(self.root, self.runner)

    def test_does_not_open_env_or_database(self):
        orig_open = os.open
        def guard(path, *args, **kwargs):
            if str(path).endswith(('.env', '.db', 'config.yaml')):
                self.fail('Opened credential/database file: ' + str(path))
            return orig_open(path, *args, **kwargs)
        with patch.object(m.os, 'open', side_effect=guard):
            result = self.inv.collect(with_health=False)
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertFalse(result['database_files_opened'])
        self.assertFalse(result['credential_contents_read'])

    def test_no_commands_modify_or_stop_services(self):
        self.inv.collect(with_health=False)
        self.assertTrue(self.runner.calls)
        for args in self.runner.calls:
            self.assertIn(args[0], ('du', 'systemctl', 'dpkg-query', 'ss', 'docker'))
            self.assertNotIn('stop', args)
            self.assertNotIn('restart', args)
            self.assertNotIn('enable', args)
            self.assertNotIn('Environment', ''.join(args)) if args[:2] != ['systemctl', 'show'] else None
            if args[:2] == ['systemctl', 'show']:
                props = next(x for x in args if x.startswith('--property='))
                self.assertNotIn('ExecStart', props)
                self.assertNotIn('Environment,', props)

    def test_custom_service_discovered_without_reading_contents(self):
        r = self.inv.units()
        self.assertIn('my-worker.service', [u['name'] for u in r['items']])
        self.assertIn('job.timer', r['local_triggers'])
        self.assertNotIn(SECRET, json.dumps(r))

    def test_docker_no_config_or_environment(self):
        result = self.inv.docker()
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['containers'][0]['mounts'][0]['Source'], '/var/lib/docker/volumes/example/_data')
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertNotIn('Config', json.dumps(result))

    def test_docker_failure_is_not_an_empty_docker_inventory(self):
        bad = m.Inventory(self.root, lambda args, **kw: {'status': 'failed', 'output': ''})
        result = bad.docker()
        self.assertEqual(result['status'], 'failed')
        self.assertIsNone(result['containers'])

    def test_hashes_are_compared_to_exact_last_release(self):
        hashes = {n: hashlib.sha256(('test-' + n).encode()).hexdigest() for n in m.KNOWN}
        with patch.dict(m.KNOWN, hashes, clear=True):
            r = self.inv.collect(with_health=False)
            self.assertTrue(all(d.get('matches_last_confirmed_release') for d in r['static_files'].values()))
            (self.root/'opt/dvizh/static/sync.js').write_text('changed')
            r = self.inv.collect(with_health=False)
            self.assertFalse(r['static_files']['sync.js']['matches_last_confirmed_release'])

    def test_code_symlink_not_hashed(self):
        target = self.root/'opt/dvizh/static/sync.js'
        target.unlink()
        target.symlink_to(self.root/'var/lib/dvizh/state.db')
        result = self.inv.collect(with_health=False)
        self.assertIn('error', result['static_files']['sync.js'])

    def test_missing_code_is_unknown_not_healthy(self):
        (self.root/'opt/dvizh/static/app.js').unlink()
        result = self.inv.collect(with_health=False)
        self.assertIn('error', result['static_files']['app.js'])

    def test_report_and_summary_admit_no_migration_no_backup(self):
        result = self.inv.collect(with_health=False)
        self.assertFalse(result['migration_performed'])
        self.assertFalse(result['backup_created'])
        self.assertFalse(result['service_changes'])
        output = m.summary(result)
        self.assertIn('NO INSTALL / NO BACKUP', output)
        self.assertIn('not a complete backup manifest', output)
        self.assertLess(len(output.splitlines()), 42)
        self.assertNotIn(SECRET, output)

    def test_missing_os_is_unknown(self):
        (self.root/'etc/os-release').unlink()
        r = self.inv.collect(with_health=False)
        self.assertEqual(r['os']['error'], 'os_release_unavailable')

    def test_os_standard_vendor_symlink_supported(self):
        vendor = self.root/'usr/lib/os-release'
        vendor.parent.mkdir(parents=True)
        vendor.write_text('ID=debian\nVERSION_ID="13"\n')
        p = self.root/'etc/os-release'; p.unlink(); p.symlink_to(vendor)
        r = self.inv.collect(with_health=False)
        self.assertEqual(r['os']['ID'], 'debian')

    def test_service_query_failure_explicit(self):
        run = self.runner
        def fail(args, **kwargs):
            if args[:2] == ['systemctl', 'show']:
                return {'status': 'timeout', 'output': ''}
            return run(args, **kwargs)
        r = m.Inventory(self.root, fail).units()
        self.assertTrue(all(x['query_status'] == 'timeout' for x in r['items']))

    def test_backup_directories_included_as_paths_only(self):
        names = {x['path'] for x in self.inv.paths()}
        for path in ('/var/lib/dvizh-release-gate', '/home/exedev/.hermes', '/usr/local', '/etc/systemd/system', '/var/lib/docker/volumes', '/srv'):
            self.assertIn(path, names)


class Helpers(unittest.TestCase):
    def test_secret_like_metadata_redacted(self):
        for text in ('ghp_1234567890abcdef', 'github_pat_ABC', 'sk-proj-1234567890abcdef', 'TOKEN=abc123', 'Bearer private'):
            self.assertNotIn(text, m.clean(text))
            self.assertIn('[redacted]', m.clean(text))

    def test_url_credentials_and_ansi_removed(self):
        out = m.clean('\x1b[31mhttps://user:pass@example.com/path\nnext')
        self.assertNotIn('user:pass', out)
        self.assertNotIn('\x1b', out)
        self.assertNotIn('\n', out)

    def test_kv_cannot_return_unselected_secret(self):
        result = m.kv('User=dvizh\nEnvironment=token=' + SECRET + '\nGroup=dvizh', ('User', 'Group'))
        self.assertEqual(result, {'User': 'dvizh', 'Group': 'dvizh'})

    def test_mount_sources_and_options_never_exposed(self):
        text = '20 1 0:4 / /srv\\040data rw,password=SECRET - nfs user:SECRET@remote:/vol rw,password=SECRET\n'
        result = m.mounts(text)
        self.assertEqual(result[0]['target'], '/srv data')
        self.assertNotIn('SECRET', json.dumps(result))

    def test_pseudo_mounts_excluded(self):
        self.assertEqual(m.mounts('1 1 0:1 / /proc rw - proc proc rw'), [])

    def test_read_bounded_and_no_fifo(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'file'; p.write_bytes(b'abc')
            self.assertEqual(m.read_regular(p), b'abc')
            with self.assertRaises(ValueError): m.read_regular(p, 2)
            fifo = Path(d)/'fifo'; os.mkfifo(fifo)
            with self.assertRaises(ValueError): m.read_regular(fifo)

    def test_ancestor_symlink_not_followed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'real').mkdir(); (root/'real/a').write_text(SECRET)
            (root/'alias').symlink_to(root/'real', target_is_directory=True)
            with self.assertRaises(ValueError): m.read_regular(root/'alias/a')

    def test_report_cannot_overwrite_or_follow_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'report.json'; m.save_report(p, {'schema': 1})
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError): m.save_report(p, {})
            link = Path(d)/'link'; link.symlink_to(p)
            with self.assertRaises(FileExistsError): m.save_report(link, {})
            self.assertEqual(json.loads(p.read_text()), {'schema': 1})

    def test_report_parent_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'dir').mkdir(); (root/'link').symlink_to(root/'dir')
            with self.assertRaises(ValueError): m.save_report(root/'link/report.json', {})

    def test_command_no_shell_no_failed_output(self):
        completed = subprocess.CompletedProcess([], 1, SECRET.encode(), SECRET.encode())
        with patch.object(m.shutil, 'which', return_value='/usr/bin/systemctl'), patch.object(m.subprocess, 'run', return_value=completed) as run:
            r = m.command(['systemctl', 'show'])
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(r['output'], '')
        self.assertNotIn('shell', run.call_args.kwargs)
        self.assertEqual(run.call_args.kwargs['stderr'], subprocess.DEVNULL)

    def test_command_timeout_has_no_raw_error(self):
        with patch.object(m.shutil, 'which', return_value='/usr/bin/du'), patch.object(m.subprocess, 'run', side_effect=subprocess.TimeoutExpired(SECRET, 1)):
            r = m.command(['du', '/'])
        self.assertEqual(r, {'status': 'timeout', 'output': ''})

    def test_missing_command_is_explicit(self):
        with patch.object(m.shutil, 'which', return_value=None):
            self.assertEqual(m.command(['nonexistent'])['status'], 'missing_command')

    def test_root_check_does_not_run_inventory(self):
        with patch.object(m.os, 'geteuid', return_value=1000), patch.object(m.sys, 'argv', ['inventory.py']), patch.object(m.Inventory, 'collect') as collect, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(), 2)
            collect.assert_not_called()


class Health(unittest.TestCase):
    def probe(self, body, status=200):
        class Response:
            def read(self, limit): return body[:limit]
        response = Response(); response.status = status
        class Connection:
            def request(self, method, path, headers):
                assert method == 'GET' and path == '/api/health'
            def getresponse(self): return response
            def close(self): pass
        with patch.object(m.http.client, 'HTTPConnection', return_value=Connection()):
            return m.health()

    def test_valid_dvizh_json_only(self):
        result = self.probe(b'{"ok":true,"app":"dvizh","users":3,"ignored":"private"}')
        self.assertTrue(result['ok'])
        self.assertNotIn('private', json.dumps(result))
        self.assertNotIn('users', result)

    def test_html_200_is_not_health_success(self):
        self.assertFalse(self.probe(b'<html>login</html>')['ok'])

    def test_wrong_app_or_false_or_nonobject_rejected(self):
        for b in (b'{"ok":true,"app":"other"}', b'{"ok":false,"app":"dvizh"}', b'[]', b'null'):
            with self.subTest(b=b): self.assertFalse(self.probe(b)['ok'])

    def test_non_200_and_oversized_rejected(self):
        self.assertFalse(self.probe(b'{"ok":true,"app":"dvizh"}', 503)['ok'])
        self.assertFalse(self.probe(b' ' * 32769)['ok'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
