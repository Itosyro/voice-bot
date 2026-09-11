"""v2.3 trust boundary tests; all I/O redirected into TemporaryDirectory."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_release_gate import load_gate, blob


class TrustedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'; self.source.mkdir()
        self.fs = self.root / 'fs'; self.fs.mkdir()
        self.g = load_gate(self.root, self.source, self.fs, self.root/'approvals', self.root/'backups', 'http://127.0.0.1:1')
        self.proposal = dict(schema=1, id='release-v23', job_id='job', mode='auto', repo=self.g.REPO,
                             branch='hermes/dev/test', commit='a'*40, manifest='.autopilot/release.json')
        self.manifest = dict(schema=2, operations=[], restarts=[])

    def add(self, target):
        policy = self.g.TARGET_POLICY[target]
        data = b'# replacement\n' if policy['mode'] == '0755' else b'new\n'
        source = self.source / policy['source']; source.parent.mkdir(parents=True, exist_ok=True); source.write_bytes(data)
        dest = self.fs / target.lstrip('/'); dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b'# old\n'); dest.chmod(int(policy['mode'], 8))
        self.manifest['operations'].append(dict(source=policy['source'], target=target,
            sha256=hashlib.sha256(data).hexdigest(), release_class=policy['class'],
            required_owner='root:root', required_mode=policy['mode'], verification=policy['verification']))
        self.manifest['restarts'] = sorted({self.g.TARGET_POLICY[r['target']]['service'] for r in self.manifest['operations']} - {None})
        return dest

    def publish(self):
        raw = json.dumps(self.manifest).encode()
        p = self.source / self.proposal['manifest']; p.parent.mkdir(exist_ok=True); p.write_bytes(raw)
        for d in [self.fs, *(p for p in self.fs.rglob('*') if p.is_dir())]: d.chmod(0o755)
        self.proposal['manifest_blob'] = blob(raw)
        self.path = self.root/'proposal.json'; self.path.write_text(json.dumps(self.proposal))
        self.tree = {'truncated': False, 'tree': [dict(path=str(p.relative_to(self.source)), type='blob', mode='100644', sha=blob(p.read_bytes())) for p in self.source.rglob('*') if p.is_file()]}
        self.ci = {'total_count': 1, 'workflow_runs': [dict(head_sha='a'*40, head_branch=self.proposal['branch'], event='push', path='.github/workflows/dvizh-hermes-autopilot.yml', status='completed', conclusion='success')]}
        def api(url):
            if '/git/trees/' in url: return self.tree
            if '/compare/' in url: return {'status': 'ahead', 'merge_base_commit': {'sha': self.g.TRUSTED_BASE}, 'total_commits': 1, 'commits': [{'parents': [{'sha': self.g.TRUSTED_BASE}]}]}
            return self.ci
        self.api = patch.object(self.g, 'api_json', side_effect=api); self.api.start(); self.addCleanup(self.api.stop)
        self.health = patch.object(self.g, 'check_health'); self.health.start(); self.addCleanup(self.health.stop)
        self.http = patch.object(self.g, 'http_get', side_effect=lambda route: (self.fs/'opt/dvizh/static'/('index.html' if route=='/' else route.lstrip('/'))).read_bytes())
        self.http.start(); self.addCleanup(self.http.stop)

    def test_mixed_runtime_auto_and_approval_union(self):
        self.add('/usr/local/libexec/dvizh-context'); self.add('/opt/dvizh-ai-home/ai_home_bridge.py'); self.add('/opt/dvizh/static/index.html')
        p = self.g.validate_manifest(self.proposal, self.manifest)
        self.assertFalse(p['approval_required']); self.assertEqual(p['restarts'], ['dvizh-ai-home.service'])
        self.add('/opt/dvizh/server.py')
        self.assertTrue(self.g.validate_manifest(self.proposal, self.manifest)['approval_required'])

    def test_exact_policy_mutations_deny(self):
        self.add('/usr/local/libexec/dvizh-context')
        row = self.manifest['operations'][0]
        for key, value in [('source','src/main.py'), ('source','hermes-control-v1/*.py'), ('source','../x'), ('target','/opt/dvizh-ai-home/unknown.py'), ('target','/etc/passwd'), ('target','/usr/local/sbin/dvizhrelease'), ('target','/opt/dvizh/static/../server.py'), ('required_owner','0:0'), ('required_mode','0777'), ('verification','shell'), ('release_class','auto-safe'), ('extraoperation','id'), ('sha256','x')]:
            with self.subTest(key=key, value=value), patch.dict(row, {key:value}):
                with self.assertRaises(self.g.GateError): self.g.validate_manifest(self.proposal,self.manifest)
        for service in ['ssh.service','dvizh-ai-home.service','dvizh.service','dvizh-ai-approval.service']:
            self.manifest['restarts']=[service]
            with self.assertRaises(self.g.GateError): self.g.validate_manifest(self.proposal,self.manifest)

    def test_manual_not_auto_without_binding_browser_evidence(self):
        for name in ['manual.html','app.js','sync.js','styles.css','sw.js']:
            self.manifest['operations']=[]; self.add('/opt/dvizh/static/'+name)
            self.assertTrue(self.g.validate_manifest(self.proposal,self.manifest)['approval_required'])

    def test_all_sources_and_metadata_preflight_zero_destination_writes(self):
        self.add('/usr/local/libexec/dvizh-context'); dest=self.add('/opt/dvizh/static/index.html'); self.publish()
        for mutation in ['sha','uid','gid','mode','symlink','ancestor']:
            with self.subTest(mutation=mutation):
                actual = self.g.read_regular
                def bad(path):
                    data, meta=actual(path)
                    if path == dest:
                        if mutation in ['uid','gid']: meta[mutation] += 1
                        if mutation=='mode': meta['mode']=0o666
                    return data,meta
                saved = dest.with_name('saved')
                if mutation=='sha': self.tree['tree'][0]['sha']='0'*40
                if mutation=='symlink': dest.rename(saved); dest.symlink_to(saved)
                if mutation=='ancestor': dest.parent.chmod(0o777)
                try:
                    with patch.object(self.g,'read_regular',side_effect=bad), patch.object(self.g,'atomic_write') as writes:
                        with self.assertRaises((self.g.GateError,OSError)): self.g.load_and_plan(str(self.path))
                        writes.assert_not_called()
                finally:
                    if mutation=='sha': self.tree['tree'][0]['sha']=blob((self.source/self.tree['tree'][0]['path']).read_bytes())
                    if mutation=='symlink': dest.unlink(); saved.rename(dest)
                    if mutation=='ancestor': dest.parent.chmod(0o755)

    def test_middle_write_failure_restores_mixed_batch_and_restarts_old(self):
        first=self.add('/usr/local/libexec/dvizh-context'); second=self.add('/opt/dvizh-ai-home/ai_home_bridge.py'); self.publish()
        original=self.g.atomic_write; failed=False
        def write(path,*args,**kwargs):
            nonlocal failed
            if path==second and not failed: failed=True; raise OSError('middle failure')
            return original(path,*args,**kwargs)
        with patch.object(self.g,'atomic_write',side_effect=write), patch.object(self.g,'restart_service') as restart:
            with self.assertRaisesRegex(self.g.GateError,'rollback confirmed'): self.g.apply(str(self.path),None)
            restart.assert_called_once_with('dvizh-ai-home.service')
        self.assertEqual(first.read_bytes(),b'# old\n'); self.assertEqual(second.read_bytes(),b'# old\n')
        self.assertFalse((self.g.APPROVAL_ROOT/'pending.json').exists())

    def test_safe_full_phrase_wrong_expired_digest_replay(self):
        self.add('/usr/local/libexec/dvizh-context'); self.proposal['mode']='safe'; self.publish()
        plan=self.g.plan_release(str(self.path)); challenge=self.g.approval_file(self.proposal['id'])
        original=challenge.read_bytes()
        for phrase in [None,plan['approval_token'],' '+plan['approval_phrase'],plan['approval_phrase']+' ', 'APPROVE wrong 12345678']:
            with self.assertRaises(self.g.GateError): self.g.apply(str(self.path),phrase)
        for changes in [{'created':1},{'created':10**12},{'digest':'wrong'}]:
            value=json.loads(original); value.update(changes); challenge.write_text(json.dumps(value))
            with self.assertRaises(self.g.GateError): self.g.apply(str(self.path),plan['approval_phrase'])
        challenge.write_bytes(original)
        self.assertTrue(self.g.apply(str(self.path),plan['approval_phrase'])['ok'])
        with self.assertRaises(self.g.GateError): self.g.apply(str(self.path),plan['approval_phrase'])

    def test_pending_blocks_plan_and_apply(self):
        self.add('/usr/local/libexec/dvizh-context'); self.publish()
        self.g.APPROVAL_ROOT.mkdir(mode=0o700); (self.g.APPROVAL_ROOT/'pending.json').write_text('{}')
        for fn in [lambda:self.g.plan_release(str(self.path)),lambda:self.g.apply(str(self.path),None)]:
            with self.assertRaisesRegex(self.g.GateError,'pending'): fn()

    def test_production_rejects_legacy_manifest(self):
        self.add('/usr/local/libexec/dvizh-context'); self.publish()
        with patch.object(self.g,'TEST_MODE',False), patch.object(self.g,'safe_json_file',return_value=(self.path,b'',self.proposal)), patch.object(self.g,'validate_branch'), patch.object(self.g,'load_manifest',return_value=({'schema':1},b'')):
            with self.assertRaisesRegex(self.g.GateError,'schema 2'): self.g.load_and_plan(str(self.path))

    def test_root_state_defaults(self):
        text=(Path(__file__).resolve().parents[2]/'hermes-dev-v2/dvizhrelease.py').read_text()
        self.assertNotIn('"/var/lib/dvizh/backups"',text)
        self.assertIn('"/var/lib/dvizh-release-gate/backups"',text)

    def test_ai_home_maps_actual_feature_source(self):
        self.assertEqual(self.g.TARGET_POLICY['/opt/dvizh-ai-home/ai_home_bridge.py']['source'], 'ai-home-v2/ai_home_bridge.py')

    def test_health_fixed_active_pid_api_context_no_diagnostics_leak(self):
        import subprocess
        self.add('/opt/dvizh-ai-home/ai_home_bridge.py')
        plan=self.g.validate_manifest(self.proposal,self.manifest)
        good_context=json.dumps({'read_only':True,'web':{'ok':True}})
        def run(argv, **kw):
            self.assertIn(argv, [['systemctl','show','--property=MainPID','--value','dvizh-ai-home.service'], ['/usr/local/libexec/dvizh-context','today']])
            return subprocess.CompletedProcess(argv,0,'123' if argv[0]=='systemctl' else good_context,'')
        with patch.object(self.g,'run',side_effect=run),patch.object(self.g,'http_get',return_value=b'{"ok":true}'),patch.object(self.g,'service_active',return_value=True):
            self.g.trusted_health(plan)
            with patch.object(self.g,'service_active',return_value=False):
                with self.assertRaises(self.g.GateError):self.g.trusted_health(plan)
            with patch.object(self.g,'run',return_value=subprocess.CompletedProcess([],0,'0','')):
                with self.assertRaises(self.g.GateError):self.g.trusted_health(plan)
            with patch.object(self.g,'http_get',return_value=b'{"ok":false,"secret":"DO_NOT_ECHO"}'):
                with self.assertRaises(self.g.GateError) as err:self.g.trusted_health(plan)
                self.assertNotIn('DO_NOT_ECHO',str(err.exception))

    def test_backup_failure_zero_target_writes(self):
        dest=self.add('/usr/local/libexec/dvizh-context'); self.publish(); original=self.g.atomic_write
        writes=[]
        def write(path,*args,**kwargs):
            if path.is_relative_to(self.fs):writes.append(path)
            if path.is_relative_to(self.g.BACKUP_ROOT):raise OSError('backup failure')
            return original(path,*args,**kwargs)
        with patch.object(self.g,'atomic_write',side_effect=write):
            with self.assertRaises(OSError):self.g.apply(str(self.path),None)
        self.assertEqual(writes,[]);self.assertEqual(dest.read_bytes(),b'# old\n')

    def test_restart_and_smoke_failure_restore_and_recheck(self):
        dest=self.add('/opt/dvizh-ai-home/ai_home_bridge.py');self.publish()
        for failing in ['restart','smoke']:
            with self.subTest(failing=failing):
                restart_values=[self.g.GateError('restart failed'),None] if failing=='restart' else [None,None]
                health_values=[None,self.g.GateError('smoke failed'),None] if failing=='smoke' else [None,None]
                with patch.object(self.g,'restart_service',side_effect=restart_values) as restart,patch.object(self.g,'check_health',side_effect=health_values) as health:
                    with self.assertRaisesRegex(self.g.GateError,'rollback confirmed'):self.g.apply(str(self.path),None)
                    self.assertEqual(restart.call_count,2);self.assertGreaterEqual(health.call_count,2)
                self.assertEqual(dest.read_bytes(),b'# old\n')

    def test_source_parent_symlink_and_git_mode(self):
        self.add('/usr/local/libexec/dvizh-context');self.publish()
        parent=self.source/'hermes-control-v1';saved=parent.with_name('saved');parent.rename(saved);parent.symlink_to(saved,target_is_directory=True)
        with self.assertRaises(self.g.GateError):self.g.load_and_plan(str(self.path))
        parent.unlink();saved.rename(parent)
        for mode in ['120000','160000','040000']:
            with patch.dict(self.tree['tree'][0],mode=mode):
                with self.assertRaises(self.g.GateError):self.g.load_and_plan(str(self.path))

    def test_ci_and_ancestry_fail_closed(self):
        self.add('/usr/local/libexec/dvizh-context');self.publish()
        for changes in [{'status':'in_progress'},{'conclusion':'failure'},{'head_sha':'b'*40},{'head_branch':'foreign'},{'event':'workflow_dispatch'}]:
            with patch.dict(self.ci['workflow_runs'][0],changes):
                with self.assertRaises(self.g.GateError):self.g.load_and_plan(str(self.path))
        with patch.object(self.g,'api_json',return_value={'status':'diverged'}):
            with self.assertRaises(self.g.GateError):self.g.verify_ancestry(self.proposal)

    def test_doctor_reports_policy_state_and_pending_without_reading_keys(self):
        self.g.APPROVAL_ROOT.mkdir(mode=0o700)
        with patch.object(self.g,'require_root'):
            report=self.g.doctor()
            self.assertEqual(report['state_root'],str(self.g.APPROVAL_ROOT.parent))
            self.assertEqual(report['production_schema'],2)
            self.assertFalse(report['pending'])
            (self.g.APPROVAL_ROOT/'pending.json').write_text('{}')
            self.assertFalse(self.g.doctor()['ok'])

    def test_all_target_ancestors_require_mapped_group(self):
        dest=self.add('/usr/local/libexec/dvizh-context');self.publish()
        original=self.g.os.fstat
        def bad(fd):
            st=original(fd)
            if self.g.stat.S_ISDIR(st.st_mode):
                values=list(st);values[5]=os.getegid()+1
                return os.stat_result(values)
            return st
        with patch.object(self.g.os,'fstat',side_effect=bad):
            with self.assertRaises(self.g.GateError):self.g.load_and_plan(str(self.path))

    def test_readonly_preflight_never_creates_state_or_writes(self):
        self.add('/usr/local/libexec/dvizh-context');self.publish()
        before={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(self.g,'atomic_write') as writes:
            result=self.g.preflight(str(self.path))
            self.assertEqual(result['status'],'preflight-verified')
            writes.assert_not_called()
        self.assertFalse(self.g.APPROVAL_ROOT.exists());self.assertFalse(self.g.BACKUP_ROOT.exists())
        after={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
