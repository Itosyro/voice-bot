"""L1/L2 regressions; run only through regression_health.py."""
import contextlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from test_hardening_v231 import module

ROOT = Path(__file__).resolve().parents[2]


def workflow_blocks():
    lines = (ROOT/'.github/workflows/dvizh-hermes-autopilot-v2-tests.yml').read_text().splitlines()
    blocks = []
    for index, line in enumerate(lines):
        if line == '        run: |':
            block = []
            for following in lines[index+1:]:
                if following and not following.startswith('          '):
                    break
                block.append(following[10:])
            # Installation preparation remains prohibited; execute static blocks only.
            if not any('PREPARE_ONLY' in item for item in block):
                blocks.append('\n'.join(block))
    return blocks


class WorkflowContracts(unittest.TestCase):
    def test_all_exact_versions(self):
        blocks = workflow_blocks()
        commands = [line for block in blocks for line in block.splitlines()
                    if line.startswith("grep -Fq 'VERSION = ")]
        self.assertEqual(len(commands), 3)
        for command in commands:
            with self.subTest(command=command):
                result = subprocess.run(['/bin/bash', '-c', command], cwd=ROOT, capture_output=True)
                self.assertEqual(result.returncode, 0, command)

    def test_actual_static_workflow_blocks(self):
        blocks = workflow_blocks()
        self.assertEqual(len(blocks), 3)
        for index, block in enumerate(blocks):
            with self.subTest(block=index):
                result = subprocess.run(['/bin/bash', '-c', block], cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)


class DoctorAuthorization(unittest.TestCase):
    def test_manifest_cases_and_gate_parity(self):
        cases = ('valid', 'missing', 'malformed', 'symlink', 'ancestor_symlink',
                 'file_mode', 'file_uid', 'file_gid', 'directory_mode', 'directory_uid',
                 'directory_gid', 'hardlink', 'fifo', 'oversized', 'duplicate',
                 'wrong_version', 'wrong_schema', 'invalid_base', 'missing_pin',
                 'invalid_pin', 'pins_list', 'null', 'extra_field')
        for name in ('dvizhgitpush', 'dvizhrelease'):
            for case in cases:
                with self.subTest(gate=name, case=case), tempfile.TemporaryDirectory() as td:
                    g = module(name)
                    root = Path(td); trusted = root/'trust'; trusted.mkdir()
                    path = trusted/'owner-approval.json'
                    manifest = dict(schema=1, version='2.3.2', base='a'*40,
                                    pins={p:'b'*40 for p in g.PIN_PATHS})
                    if case == 'wrong_version': manifest['version'] = 'secret-canary'
                    if case == 'wrong_schema': manifest['schema'] = 2
                    if case == 'invalid_base': manifest['base'] = 'secret-canary'
                    if case == 'missing_pin': manifest['pins'].pop(next(iter(g.PIN_PATHS)))
                    if case == 'invalid_pin': manifest['pins'][next(iter(g.PIN_PATHS))] = 'secret-canary'
                    if case == 'pins_list': manifest['pins'] = sorted(g.PIN_PATHS)
                    if case == 'extra_field': manifest['secret-canary'] = 'secret-canary'
                    raw = json.dumps(manifest)
                    if case == 'malformed': raw = 'secret-canary{'
                    if case == 'oversized': raw = ' ' * 65537
                    if case == 'duplicate': raw = raw[:-1] + ',"version":"secret-canary"}'
                    if case == 'null': raw = 'null'
                    path.write_text(raw); path.chmod(0o600)
                    if case == 'missing': path.unlink()
                    if case == 'symlink':
                        path.rename(trusted/'real'); path.symlink_to(trusted/'real')
                    if case == 'ancestor_symlink':
                        (root/'link').symlink_to(trusted, target_is_directory=True); path = root/'link'/path.name
                    if case == 'hardlink': os.link(path, trusted/'second')
                    if case == 'fifo': path.unlink(); os.mkfifo(path)
                    if case == 'file_mode': path.chmod(0o622)
                    before = sorted((str(p.relative_to(root)), p.lstat().st_mode, p.lstat().st_size)
                                    for p in root.rglob('*'))
                    real_fstat = os.fstat
                    def metadata(fd):
                        st = real_fstat(fd)
                        directory = stat.S_ISDIR(st.st_mode)
                        # Model root ownership only; actual opens, nofollow, reads, modes/link counts remain real.
                        return types.SimpleNamespace(st_mode=(st.st_mode & ~0o022 if directory else st.st_mode) |
                            (0o022 if directory and case == 'directory_mode' else 0),
                            st_uid=1000 if case == ('directory_uid' if directory else 'file_uid') else 0,
                            st_gid=1000 if case == ('directory_gid' if directory else 'file_gid') else 0,
                            st_nlink=st.st_nlink)
                    with contextlib.ExitStack() as stack:
                        stack.enter_context(patch.object(g, 'OWNER_APPROVAL', path))
                        stack.enter_context(patch.object(g.os, 'fstat', side_effect=metadata))
                        stack.enter_context(patch.object(g, 'require_root'))
                        stack.enter_context(patch.object(g.shutil, 'which', return_value='/fixture/tool')) if name == 'dvizhrelease' else None
                        if name == 'dvizhrelease':
                            stack.enter_context(patch.object(g, 'APPROVAL_ROOT', root/'state'))
                            pins = {p:dict(type='blob', mode='100644', sha='b'*40) for p in g.PIN_PATHS}
                            stack.enter_context(patch.object(g, 'source_tree', return_value=pins))
                            stack.enter_context(patch.object(g, 'api_json', return_value={'sha':'c'*40, 'parents':[{'sha':'a'*40}]}))
                            authorize = lambda: g.verify_owner_history({'commit':'c'*40})
                        else:
                            key = root/'fixture-key'; key.write_text('fixture')
                            stack.enter_context(patch.object(g, 'KEY', key))
                            stack.enter_context(patch.object(g, 'ssh_env', return_value={}))
                            stack.enter_context(patch.object(g, 'run', return_value=subprocess.CompletedProcess([], 0, 'b'*40+'\n', 'secret-canary')))
                            authorize = lambda: g.verify_local_pins(root, 'a'*40, 'a'*40)
                        expected = case == 'valid'
                        if expected: authorize()
                        else:
                            with self.assertRaises(g.GateError): authorize()
                        with patch.object(g, 'owner_manifest', wraps=g.owner_manifest) as contract:
                            result = g.doctor()
                            self.assertEqual(contract.call_count, 1)
                        self.assertIs(result['owner_authorized'], expected)
                        self.assertIs(result['ok'], expected)
                        output = json.dumps(result)
                        for hidden in ('secret-canary', '"pins"', 'a'*40): self.assertNotIn(hidden, output)
                        if expected: authorize()
                        else:
                            with self.assertRaises(g.GateError): authorize()
                    if name == 'dvizhgitpush': key.unlink()
                    after = sorted((str(p.relative_to(root)), p.lstat().st_mode, p.lstat().st_size)
                                   for p in root.rglob('*'))
                    self.assertEqual(before, after)

    def test_other_prerequisites_and_controller_aggregation(self):
        for name in ('dvizhgitpush', 'dvizhrelease'):
            g = module(name)
            with tempfile.TemporaryDirectory() as td, contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(g, 'require_root'))
                stack.enter_context(patch.object(g, 'owner_manifest', return_value={}))
                if name == 'dvizhgitpush': stack.enter_context(patch.object(g, 'KEY', Path(td)/'missing'))
                else: stack.enter_context(patch.object(g.shutil, 'which', return_value=None))
                result = g.doctor()
                self.assertIs(result['owner_authorized'], True)
                self.assertIs(result['ok'], False)
        controller = module('dvizhautopilot')
        with patch.object(controller, 'api_json', return_value={}), patch.object(Path, 'is_file', return_value=True):
            for failed in (0, 1, None):
                results = [dict(ok=i != failed, owner_authorized=i != failed) for i in range(2)]
                with patch.object(controller, 'sudo_json', side_effect=results):
                    self.assertIs(controller.doctor()['ok'], failed is None)
