import importlib.util
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.fs=self.root/'fs';self.fs.mkdir(mode=0o755)
        spec=importlib.util.spec_from_file_location('owner_install',ROOT/'hermes-dev-v2/owner_install.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.original=(ROOT/'tests/hermes_autopilot/fixtures/local-dvizh-dev-v22.md').read_bytes()
        for target in self.m.TARGETS:
            dest=self.fs/target.lstrip('/');dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(self.original if target==self.m.SKILL_TARGET else b'# old gate\n')
            dest.chmod(0o600 if target==self.m.SKILL_TARGET else 0o755)
        for d in [self.fs,*(p for p in self.fs.rglob('*') if p.is_dir())]:d.chmod(0o755)
        self.payload=ROOT/'hermes-dev-v2'
        self.g=self.m.gate_for(self.fs,fixture=True)

    def install(self):
        return self.m.install(self.g,self.payload,self.m.payload_digest(self.payload))

    def test_only_gates_installed_and_idempotent(self):
        self.assertNotIn(self.m.SKILL_TARGET,self.m.TARGETS)
        result=self.install()
        for target,source in self.m.TARGETS.items():
            self.assertEqual((self.fs/target.lstrip('/')).read_bytes(),(self.payload/source).read_bytes())
        self.assertEqual(self.install()['status'],'unchanged')

    def test_bad_digest_zero_writes_and_no_secrets_or_sudo_targets(self):
        with patch.object(self.g,'atomic_write') as writes:
            with self.assertRaises(self.g.GateError):self.m.install(self.g,self.payload,'0'*64)
            writes.assert_not_called()
        self.assertEqual(set(self.m.TARGETS),{'/usr/local/bin/dvizhautopilot','/usr/local/sbin/dvizhrelease','/usr/local/sbin/dvizhgitpush'})

    def test_middle_failure_full_rollback(self):
        old={p:p.read_bytes() for p in self.fs.rglob('*') if p.is_file()}
        original=self.g.atomic_write;failed=False
        def write(path,*a,**kw):
            nonlocal failed
            if str(path).endswith('/usr/local/sbin/dvizhrelease') and not failed:failed=True;raise OSError('injected')
            return original(path,*a,**kw)
        with patch.object(self.g,'atomic_write',side_effect=write):
            with self.assertRaisesRegex(self.g.GateError,'rollback confirmed'):self.install()
        for p,data in old.items():self.assertEqual(p.read_bytes(),data)

    def test_destination_symlink_denied(self):
        path=self.fs/'usr/local/sbin/dvizhrelease'
        path.unlink();path.symlink_to(self.root/'other')
        with self.assertRaises(self.g.GateError):self.install()
