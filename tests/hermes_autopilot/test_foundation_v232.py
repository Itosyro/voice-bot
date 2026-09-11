import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_git_push_gate import fixture, git, load_gate, JOB_ID
from test_hardening_v231 import module

class FoundationTests(unittest.TestCase):
    def test_protected_add_remove_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            home, wt, base, branch = fixture(td)
            p = wt/'.github/workflows/dvizh-hermes-autopilot.yml'
            p.parent.mkdir(parents=True); p.write_text('always green')
            git(wt,'add','.'); git(wt,'commit','-m','protected')
            p.unlink(); (wt/'ai-home-v2/index.html').write_text('allowed')
            git(wt,'add','-A'); git(wt,'commit','-m','hide')
            g = load_gate(home,base)
            with self.assertRaises(g.GateError):
                g.changed_paths(wt,base,git(wt,'rev-parse','HEAD'))

    def test_harmless_fsmonitor_does_not_execute(self):
        with tempfile.TemporaryDirectory() as td:
            home, wt, base, branch = fixture(td)
            marker=Path(td)/'marker'; hook=Path(td)/'hook'
            hook.write_text('#!/bin/sh\nprintf harmless > '+str(marker)+'\n'); hook.chmod(0o755)
            git(wt,'config','core.fsmonitor',str(hook))
            g=load_gate(home,base)
            g.validate_worktree(home,JOB_ID,{'worktree':str(wt),'branch':branch})
            self.assertFalse(marker.exists())

    def test_schema_two_retired(self):
        g=module('dvizhrelease')
        with self.assertRaises(g.GateError):
            g.validate_manifest({'mode':'auto'},{'schema':2,'operations':[],'restarts':[]})

    def test_root_entry_not_quarantined(self):
        for name in ('dvizhrelease','dvizhgitpush'):
            g=module(name)
            with patch.object(g.os,'geteuid',return_value=0):
                g.require_root()

    def test_export_is_immutable_and_copies_no_config(self):
        with tempfile.TemporaryDirectory() as td:
            home,wt,base,branch=fixture(td)
            (wt/'ai-home-v2/index.html').write_text('validated')
            git(wt,'add','.');git(wt,'commit','-m','validated')
            head=git(wt,'rev-parse','HEAD');g=load_gate(home,base)
            marker=Path(td)/'marker'; hook=Path(td)/'hook'
            hook.write_text('#!/bin/sh\necho harmless > '+str(marker)+'\n');hook.chmod(0o755)
            include=Path(td)/'included';include.write_text('[core]\n fsmonitor = '+str(hook)+'\n sshCommand = '+str(hook)+'\n[credential]\n helper = !'+str(hook)+'\n')
            git(wt,'config','include.path',str(include));git(wt,'config','core.hooksPath',str(Path(td)))
            for name in ('pre-push','post-checkout','post-index-change'):
                (Path(td)/name).write_bytes(hook.read_bytes());(Path(td)/name).chmod(0o755)
            with patch.dict(os.environ,{'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'core.fsmonitor','GIT_CONFIG_VALUE_0':str(hook),'GIT_EXTERNAL_DIFF':str(hook),'GIT_SSH_COMMAND':str(hook)}):
                with g.immutable_export(wt,head) as clean:
                    config=(clean/'config').read_text()
                    self.assertNotIn('include',config);self.assertNotIn(str(hook),config)
                    self.assertEqual(g.changed_paths(clean,base,head),['ai-home-v2/index.html'])
                    # Ref movement after export cannot change the exported identity.
                    git(wt,'update-ref','HEAD',base)
                    self.assertEqual(g.run(g.git_args(clean,'show',head+':ai-home-v2/index.html')).stdout,'validated')
            self.assertFalse(marker.exists())

    def test_remote_green_cannot_authorize_changed_pins_or_hidden_history(self):
        g=module('dvizhrelease')
        base='a'*40;middle='b'*40;head='c'*40
        pins={p:'d'*40 for p in g.PIN_PATHS}
        tree={p:dict(type='blob',mode='100644',sha=v) for p,v in pins.items()}
        final=dict(tree);final['ai-home-v2/index.html']=dict(type='blob',mode='100644',sha='e'*40)
        intermediate=dict(final);intermediate['hermes-dev-v2/hidden.py']=dict(type='blob',mode='100644',sha='f'*40)
        def api(url):
            sha=url.rsplit('/',1)[-1]
            return {'sha':sha,'parents':[{'sha':middle if sha==head else base}]}
        with patch.object(g,'owner_manifest',return_value={'base':base,'pins':pins}), patch.object(g,'api_json',side_effect=api),patch.object(g,'source_tree',side_effect=lambda sha:{base:tree,middle:intermediate,head:final}[sha]):
            with self.assertRaisesRegex(g.GateError,'protected history'):g.verify_owner_history({'commit':head})
            final['hermes-dev-v2/dvizhrelease.py']=dict(type='blob',mode='100644',sha='0'*40)
            with self.assertRaisesRegex(g.GateError,'pin mismatch'):g.verify_owner_history({'commit':head})

    def test_bootstrap_wrong_digest_does_not_execute_installer(self):
        import subprocess
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);marker=p/'executed'
            (p/'owner_install.py').write_text('open('+repr(str(marker))+',"w").write("harmless")\n')
            bootstrap=Path(__file__).resolve().parents[2]/'hermes-dev-v2/bootstrap_v232.py'
            result=subprocess.run(['/usr/bin/python3','-I','-S',str(bootstrap),str(p),'0'*64,'0'*64],capture_output=True)
            self.assertNotEqual(result.returncode,0);self.assertFalse(marker.exists())
            self.assertIn(b'payload mismatch',result.stderr)

    def test_bootstrap_external_launcher_rejects_before_execution(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);marker=p/'executed';bootstrap=p/'bootstrap.py'
            bootstrap.write_text('open('+repr(str(marker))+',"w").write("harmless")\n')
            doc=(Path(__file__).resolve().parents[2]/'hermes-dev-v2/BOOTSTRAP-v232.md').read_text()
            launcher=doc.split('```python\n')[1].split('```')[0]
            result=subprocess.run(['/usr/bin/python3','-I','-S','-c',launcher,str(bootstrap),'0'*64,str(p),'0'*64,'0'*64],capture_output=True)
            self.assertNotEqual(result.returncode,0);self.assertFalse(marker.exists())

    def test_root_caller_git_launch_drops_uid_gid_groups_and_environment(self):
        import subprocess
        g=module('dvizhgitpush')
        with patch.object(g.os,'geteuid',return_value=0), patch.object(g,'invoking_identity',return_value=(1234,1235)), patch.object(g.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')) as launch, patch.dict(os.environ,{'GIT_CONFIG_PARAMETERS':'malicious','LD_PRELOAD':'malicious','PYTHONPATH':'malicious','SSH_AUTH_SOCK':'malicious'}):
            g.run(g.git_args(Path('/caller/worktree'),'status','--porcelain'))
        kw=launch.call_args.kwargs
        self.assertEqual((kw['user'],kw['group'],kw['extra_groups']),(1234,1235,[]))
        self.assertEqual(kw['cwd'],'/')
        for key in ('GIT_CONFIG_PARAMETERS','LD_PRELOAD','PYTHONPATH','SSH_AUTH_SOCK'):
            self.assertNotIn(key,kw['env'])

    def test_ci_always_green_with_missing_jobs_rejected(self):
        g=module('dvizhrelease');head='a'*40
        run=dict(id=123,run_number=1,path='.github/workflows/dvizh-hermes-autopilot.yml',head_sha=head,head_branch='hermes/dev/test',event='push',status='completed',conclusion='success')
        def api(url):
            if '/jobs?' in url:return dict(total_count=0,jobs=[])
            return dict(total_count=1,workflow_runs=[run])
        with patch.object(g,'TEST_MODE',False),patch.object(g,'verify_owner_history') as history,patch.object(g,'api_json',side_effect=api):
            with self.assertRaisesRegex(g.GateError,'jobs missing'):g.verify_ci(dict(commit=head,branch='hermes/dev/test'),require_ai=True)
            history.assert_called_once()

    def test_bootstrap_ignores_adjacent_python_modules(self):
        import hashlib
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);marker=p/'imported'
            for name in ('hashlib','json','sitecustomize'):
                (p/(name+'.py')).write_text('open('+repr(str(marker))+',"w").write("harmless")\n')
            stub=b"def gate_for(): return None\ndef prepare(g,p,d): return []\n"
            (p/'owner_install.py').write_bytes(stub)
            src=Path(__file__).resolve().parents[2]/'hermes-dev-v2/bootstrap_v232.py'
            (p/'bootstrap.py').write_bytes(src.read_bytes())
            cp=subprocess.run(['/usr/bin/python3','-I','-S',str(p/'bootstrap.py'),str(p),hashlib.sha256(stub).hexdigest(),'0'*64],cwd=p,capture_output=True)
            self.assertEqual(cp.returncode,0,cp.stderr);self.assertFalse(marker.exists())

    def test_verified_bootstrap_rejects_nonregular_input_without_following_link(self):
        import hashlib
        g=module('bootstrap_v232')
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);data=b'# harmless approved bytes\n'
            (p/'real').write_bytes(data);(p/'link').symlink_to(p/'real')
            with self.assertRaises((OSError,RuntimeError)):
                g.verified_bytes(p/'link',hashlib.sha256(data).hexdigest())

    def test_actual_installer_uses_last_verified_buffers_after_replacement(self):
        import shutil
        g=module('owner_install')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);fs=root/'fs';fs.mkdir();payload=root/'payload'
            shutil.copytree(Path(__file__).resolve().parents[2]/'hermes-dev-v2',payload)
            for target in g.TARGETS:
                dest=fs/target.lstrip('/');dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(b'# old\n');dest.chmod(0o755)
            for directory in [fs,*(p for p in fs.rglob('*') if p.is_dir())]:directory.chmod(0o755)
            gate=g.gate_for(fs,fixture=True);expected=g.payload_digest(payload)
            approved=(payload/'dvizhrelease.py').read_bytes();original=g.prepare;calls=[]
            def prepare(*args):
                rows=original(*args);calls.append(True)
                if len(calls)==2:(payload/'dvizhrelease.py').write_bytes(b'# harmless replacement\n')
                return rows
            with patch.object(g,'prepare',side_effect=prepare):
                result=g.install(gate,payload,expected)
            self.assertEqual(result['status'],'installed')
            self.assertEqual((fs/'usr/local/sbin/dvizhrelease').read_bytes(),approved)

    def test_external_launcher_executes_exact_verified_bootstrap_buffer(self):
        import hashlib
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);src=p/'bootstrap.py';marker=p/'unverified'
            malicious='open('+repr(str(marker))+',"w").write("harmless")\n'
            approved=('from pathlib import Path\nPath('+repr(str(src))+').write_text('+repr(malicious)+')\ndef bootstrap(*args,**kwargs): return "verified-buffer"\n').encode()
            src.write_bytes(approved)
            doc=(Path(__file__).resolve().parents[2]/'hermes-dev-v2/BOOTSTRAP-v232.md').read_text()
            launcher=doc.split('```python\n')[1].split('```')[0]
            cp=subprocess.run(['/usr/bin/python3','-I','-S','-c',launcher,str(src),hashlib.sha256(approved).hexdigest(),str(p),'0'*64,'0'*64],capture_output=True)
            self.assertEqual(cp.returncode,0,cp.stderr);self.assertFalse(marker.exists())
            self.assertIn(b'verified-buffer',cp.stdout);self.assertEqual(src.read_text(),malicious)

    def test_exact_workflow_version_assertion(self):
        g=module('dvizhrelease')
        workflow=(Path(__file__).resolve().parents[2]/'.github/workflows/dvizh-hermes-autopilot-v2-tests.yml').read_text()
        self.assertIn('VERSION = "'+g.VERSION+'"',workflow)

    def test_valid_history_and_pins_remain_functional(self):
        g=module('dvizhrelease');base='a'*40;head='b'*40
        pins={p:'c'*40 for p in g.PIN_PATHS}
        old={p:dict(type='blob',mode='100644',sha=v) for p,v in pins.items()}
        new=dict(old);new['ai-home-v2/index.html']=dict(type='blob',mode='100644',sha='d'*40)
        with patch.object(g,'owner_manifest',return_value={'base':base,'pins':pins}),patch.object(g,'source_tree',side_effect=lambda sha:old if sha==base else new),patch.object(g,'api_json',return_value={'sha':head,'parents':[{'sha':base}]}):
            g.verify_owner_history({'commit':head})

    def test_push_uses_captured_commit_after_caller_ref_and_config_change(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            home,wt,base,branch=fixture(td)
            (wt/'ai-home-v2/index.html').write_text('captured')
            git(wt,'add','.');git(wt,'commit','-m','captured')
            head=git(wt,'rev-parse','HEAD');g=load_gate(home,base);original=g.run;pushes=[]
            def run(args,**kwargs):
                if 'push' in args:
                    pushes.append(args)
                    self.assertIn(head+':refs/heads/'+branch,args)
                    self.assertNotIn(str(wt),args)
                    return subprocess.CompletedProcess(args,0,'simulated transport','')
                return original(args,**kwargs)
            def pins(*args):
                git(wt,'update-ref','HEAD',base)
                git(wt,'config','core.sshCommand','/bin/false')
            with patch.object(g,'TEST_MODE',False),patch.object(g,'require_root'),patch.object(g,'caller_home',return_value=('tester',home)),patch.object(g,'verify_local_pins',side_effect=pins),patch.object(g,'ssh_env',return_value={'GIT_SSH_COMMAND':'/bin/false'}),patch.object(g,'run',side_effect=run):
                self.assertEqual(g.push(JOB_ID)['head'],head)
            self.assertEqual(len(pushes),1)
