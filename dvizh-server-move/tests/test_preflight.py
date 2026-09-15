import contextlib
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

spec = importlib.util.spec_from_file_location('preflight', Path(__file__).resolve().parents[1]/'preflight.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class InventoryTests(unittest.TestCase):
    def test_os_not_executed_and_only_allowlist(self):
        self.assertEqual(m.parse_os('ID=ubuntu\nVERSION_ID="24.04"\nSECRET=hunter2\nEVIL=$(touch /tmp/bad)'), {'ID':'ubuntu','VERSION_ID':'24.04'})
    def test_terminal_controls(self):
        self.assertEqual(m.printable('a\x1b[2J\nb'), 'a?[2J?b')
    def test_unit_names_filtered(self):
        x=m.parse_units('dvizh.service loaded active running app\nfoo.timer loaded active waiting\n$(bad).service loaded active\n')
        self.assertEqual([i['unit'] for i in x],['dvizh.service','foo.timer'])
    def test_env_values_and_exec_never_included(self):
        x=m.parse_properties('Id=x.service\nUser=bob\nEnvironment=API_KEY=topsecret\nExecStart=/bin/x --token=topsecret\nEnvironmentFiles=/etc/dvizh/a.env\n')
        self.assertNotIn('topsecret',json.dumps(x)); self.assertIn('EnvironmentFiles',x)
    def test_missing_meta(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(m.file_meta(Path(d)/'absent')['present'])
    def test_directory_not_hashed(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertNotIn('sha256',m.file_meta(d,hash_code=True))
    def test_secret_metadata_only(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'secret.env';p.write_text('NEVER PRINT ME')
            with patch.object(Path,'read_bytes',side_effect=AssertionError('read')):
                out=m.file_meta(p)
            self.assertNotIn('sha256',out);self.assertNotIn('NEVER PRINT',json.dumps(out))
    def test_symlinks_not_followed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'secret';p.write_text('NEVER PRINT ME');l=Path(d)/'link';l.symlink_to(p)
            out=m.file_meta(l,hash_code=True)
            self.assertEqual(out['kind'],'symlink');self.assertNotIn('sha256',out)
    def test_static_sha_exact(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'index.html';p.write_bytes(b'public')
            self.assertEqual(m.file_meta(p,True)['sha256'],m.hashlib.sha256(b'public').hexdigest())
    def test_fifo_not_opened(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'pipe';os.mkfifo(p)
            self.assertEqual(m.file_meta(p,True)['kind'],'special')
    def test_large_code_not_opened(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'large';p.touch();os.truncate(p,9*1024*1024)
            self.assertNotIn('sha256',m.file_meta(p,True))
    def test_report_private_and_new(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.dict(os.environ,{'SUDO_UID':''}):
                a=m.save_report({'a':1},d); b=m.save_report({'a':2},d)
            self.assertNotEqual(a,b)
            self.assertEqual(stat.S_IMODE(a.stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE(a.parent.stat().st_mode),0o700)
            self.assertEqual(json.loads(a.read_text()),{'a':1})
    def test_report_no_existing_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            protected=Path(d)/'inventory.json';protected.write_text('unchanged')
            with patch.dict(os.environ,{'SUDO_UID':''}):m.save_report({'a':1},d)
            self.assertEqual(protected.read_text(),'unchanged')
    def test_probe_env_sanitized_and_no_shell(self):
        with patch.object(m.shutil,'which',return_value='/usr/bin/systemctl'), patch.object(m.subprocess,'run') as r:
            r.return_value=subprocess.CompletedProcess([],0,'safe','SECRET'); self.assertEqual(m.Probe().run(['systemctl','show']),'safe')
            kw=r.call_args.kwargs
            self.assertNotIn('shell',kw);self.assertEqual(kw['stdin'],subprocess.DEVNULL)
            self.assertEqual(set(kw['env']),{'PATH','LC_ALL','LANG','HOME','SYSTEMD_PAGER','SYSTEMD_COLORS'})
    def test_probe_failure_no_stderr_leak(self):
        q=m.Probe()
        with patch.object(m.shutil,'which',return_value='/usr/bin/docker'),patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'secret','secret')):
            self.assertIsNone(q.run(['docker','ps']));self.assertNotIn('secret',str(q.gaps))
    def test_missing_binary_recorded(self):
        q=m.Probe()
        with patch.object(m.shutil,'which',return_value=None):self.assertIsNone(q.run(['missing']))
        self.assertEqual(q.gaps,['missing:not_installed'])
    def test_timeout_recorded(self):
        q=m.Probe()
        with patch.object(m.shutil,'which',return_value='/usr/bin/du'),patch.object(m.subprocess,'run',side_effect=subprocess.TimeoutExpired('du',1)):
            self.assertIsNone(q.run(['du']))
        self.assertEqual(q.gaps,['du:timeout'])
    def test_deadline_no_execution(self):
        q=m.Probe(seconds=-1)
        with patch.object(m.shutil,'which',return_value='/usr/bin/du'),patch.object(m.subprocess,'run') as r:
            self.assertIsNone(q.run(['du']));r.assert_not_called()
    def test_docker_local_explicit_fields(self):
        class Q:
            gaps=[]
            def __init__(self):self.calls=[]
            def run(self,args):
                self.calls.append(args)
                if 'ps' in args:return 'a'*64+'\n'
                return json.dumps({'id':'a'*64,'mounts':[{'Type':'volume','Source':'/vol','Destination':'/data','Driver':'secret','Options':'PASSWORD'}]})
        q=Q()
        with patch.object(Path,'exists',return_value=True):out=m.docker_inventory(q)
        self.assertNotIn('PASSWORD',json.dumps(out))
        for call in q.calls:self.assertEqual(call[:3],['docker','--host','unix:///var/run/docker.sock'])
        self.assertNotIn('.Config.Env',' '.join(q.calls[-1]))
    def test_non_root_stops(self):
        with patch.object(m.os,'geteuid',return_value=1000),patch.object(m.sys,'argv',['preflight']),patch.object(m,'collect') as collect,contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(),2);collect.assert_not_called()
    def test_collect_fake_host_never_calls_writes(self):
        calls=[]
        def run(self,args,timeout=12):
            calls.append(args)
            if args[:2]==['systemctl','list-units']:return 'dvizh.service loaded active running app\n'
            if args[:2]==['systemctl','show']:return 'Id=dvizh.service\nActiveState=active\nUser=dvizh\n'
            if args[0]=='curl':return '{"ok":true,"app":"dvizh"}'
            if args[0]=='dpkg-query':return 'python3\t3.12\tinstalled\nold\t1.0\tconfig-files\n'
            if args[0]=='du':return '1024 /x\n'
            if args[0]=='findmnt':return '{"filesystems":[]}'
            return ''
        with patch.object(m.Probe,'run',run),patch.object(m,'directory_names',return_value=[]),patch.object(m,'account_rows',return_value=[]),patch.object(m,'docker_inventory',return_value={'containers':[]}):r=m.collect()
        self.assertTrue(r['application_health']['ok'])
        self.assertFalse(r['backup_created']);self.assertFalse(r['migration_performed']);self.assertFalse(r['production_changed'])
        self.assertEqual(r['installed_debian_packages'],[['python3','3.12']])
        for a in calls:
            self.assertNotIn('start',a);self.assertNotIn('stop',a);self.assertNotIn('restart',a)
        self.assertEqual(len([x for x in calls if x[0]=='curl']),1)
        self.assertEqual([x for x in calls if x[0]=='curl'][0][-1],'http://127.0.0.1:8000/api/health')

if __name__=='__main__':unittest.main(verbosity=2)
