import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('inventory', Path(__file__).resolve().parents[1] / 'inventory.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
    def tearDown(self): self.temp.cleanup()
    def write(self, name, contents=b'content'):
        p = self.root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(contents); return p

    def test_regular_file_hash(self):
        p = self.write('app.js', b'hello')
        self.assertEqual(m.fingerprint(p)['sha256'], hashlib.sha256(b'hello').hexdigest())
    def test_rejects_leaf_symlink(self):
        p = self.write('secret'); (self.root/'link').symlink_to(p)
        with self.assertRaises(OSError): m.read_fixed(self.root/'link')
    def test_rejects_ancestor_symlink(self):
        p = self.write('real/secret'); (self.root/'alias').symlink_to(self.root/'real', target_is_directory=True)
        with self.assertRaises(OSError): m.read_fixed(self.root/'alias'/'secret')
    def test_rejects_hardlink(self):
        p = self.write('one'); os.link(p, self.root/'two')
        with self.assertRaises(ValueError): m.read_fixed(p)
    def test_rejects_fifo_without_hanging(self):
        p = self.root/'fifo'; os.mkfifo(p)
        with self.assertRaises(ValueError): m.read_fixed(p)
    def test_limit_is_enforced(self):
        p = self.write('big', b'a'*100)
        with self.assertRaises(ValueError): m.read_fixed(p, 50)
    def test_relative_path_rejected(self):
        with self.assertRaises(ValueError): m.read_fixed(Path('relative'))
    def test_parent_path_rejected(self):
        with self.assertRaises(ValueError): m.read_fixed(self.root/'..'/'file')
    def test_missing_is_not_empty_or_success(self):
        self.assertIn('error', m.fingerprint(self.root/'missing'))
        self.assertEqual(m.metadata(self.root/'missing')['kind'], 'absent')
    def test_scan_does_not_read_database_or_secrets(self):
        self.write('state.db', b'DO_NOT_READ_DATABASE_CONTENTS')
        self.write('.hermes/.env', b'API_TOKEN=secret-value')
        with patch.object(m, 'read_fixed', side_effect=AssertionError('content read forbidden')):
            r = m.scan([self.root])
        dump = json.dumps(r)
        self.assertNotIn('DO_NOT_READ_DATABASE_CONTENTS', dump)
        self.assertNotIn('secret-value', dump)
        self.assertEqual(len(r['database_candidates']), 1)
        self.assertFalse(r['is_complete_server_inventory'])
    def test_scan_skips_dependencies_not_application_data(self):
        self.write('node_modules/lib/state.db'); self.write('.hermes/state.db')
        r = m.scan([self.root])
        self.assertEqual(len(r['database_candidates']), 1)
        self.assertIn('.hermes', r['database_candidates'][0]['path'])
    def test_scan_records_limit(self):
        for i in range(5): self.write(str(i)+'.db')
        r = m.scan([self.root], max_entries=2)
        self.assertIn('scan_limit_reached', r['limited_or_unreadable'])
    def test_scan_does_not_follow_directory_symlinks(self):
        self.write('data/state.db'); (self.root/'link').symlink_to(self.root/'data', target_is_directory=True)
        r = m.scan([self.root])
        self.assertEqual(len(r['database_candidates']), 1)
        self.assertTrue(r['symlinks_not_followed'])
    def test_sanitizes_terminal_controls_and_known_token_formats(self):
        s = m.clean('\x1b[31m\nkey=gho_ABCDEFGHIJKLMNO')
        self.assertNotIn('\x1b', s); self.assertNotIn('\n', s); self.assertNotIn('gho_', s)
    def test_run_has_no_inherited_environment_or_stdin(self):
        with patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ok')) as r:
            self.assertEqual(m.run(['/bin/true']), (0, 'ok'))
        args = r.call_args.kwargs
        self.assertEqual(args['env'], m.SAFE_ENV)
        self.assertEqual(args['stdin'], subprocess.DEVNULL)
        self.assertNotIn('shell', args)
    def test_command_timeout_reported(self):
        with patch.object(m.subprocess, 'run', side_effect=subprocess.TimeoutExpired('x',1)):
            self.assertEqual(m.run(['x']), (99,''))
    def test_unit_queries_omit_secrets_and_actions(self):
        replies = [(0, 'dvizh.service loaded active running DVIZH\n'), (0, 'Id=dvizh.service\nActiveState=active\nFragmentPath=/etc/systemd/system/dvizh.service\n')]
        with patch.object(m, 'run', side_effect=replies) as r:
            d=m.units()
        self.assertEqual(d['units'][0]['Id'],'dvizh.service')
        call = r.call_args.args[0]
        prop = next(x for x in call if x.startswith('--property='))
        self.assertNotIn('ExecStart',prop)
        self.assertNotIn('Environment,',prop)
        self.assertNotIn('restart',call); self.assertNotIn('stop',call)
    def test_docker_uses_local_engine_only_and_excludes_env(self):
        rows=[(0,'a'*64+'\n'), (0,json.dumps({'id':'a'*64,'name':'/bot','image':'bot:stable','running':True,'mounts':[{'Type':'volume','Source':'/var/lib/docker/volumes/db/_data','Destination':'/data','Options':{'password':'never-print'}}]})), (0,'/var/lib/docker\n')]
        with patch.object(m.shutil,'which',return_value='/usr/bin/docker'), patch.object(m,'run',side_effect=rows) as r:
            d=m.docker_metadata()
        self.assertNotIn('never-print',json.dumps(d))
        for call in r.call_args_list:
            argv=call.args[0]
            self.assertEqual(argv[1:3],['--host','unix:///var/run/docker.sock'])
            self.assertNotIn('Config.Env',' '.join(argv))
    def test_no_redirects(self):
        self.assertIsNone(m.NoRedirect().redirect_request(None,None,None,None,None,None))
    def test_non_root_exits_before_scan(self):
        with patch.object(m.os, 'geteuid',return_value=1000), patch.object(m.sys,'argv',['inventory']), patch.object(m,'collect') as collect, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(),2)
            collect.assert_not_called()

if __name__=='__main__': unittest.main(verbosity=2)
