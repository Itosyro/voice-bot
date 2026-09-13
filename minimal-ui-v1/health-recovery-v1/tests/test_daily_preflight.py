"""Diagnostic safety checks using temporary files and explicit subprocess/HTTP fakes."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('daily_preflight_test_subject', ROOT/'preflight_daily.py')
subject = importlib.util.module_from_spec(spec); spec.loader.exec_module(subject)

class PreflightTests(unittest.TestCase):
    def test_regular_file_is_read_not_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'source.py';p.write_bytes(b'VERSION = "safe.1"\nraise RuntimeError("must never execute")\n')
            result=subject.fingerprint(p)
            self.assertEqual(result['version'],'safe.1')
            self.assertEqual(result['sha256'],hashlib.sha256(p.read_bytes()).hexdigest())
    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'file').write_text('not followed');(root/'link').symlink_to(root/'file')
            self.assertIn('error',subject.fingerprint(root/'link'))
    def test_missing_file_reports_error(self):
        with tempfile.TemporaryDirectory() as tmp:self.assertEqual(subject.fingerprint(Path(tmp)/'missing')['error'],'FileNotFoundError')
    def test_oversized_source_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'large';p.write_bytes(b'x'*20)
            with patch.object(subject,'MAX_BYTES',10):self.assertEqual(subject.fingerprint(p)['error'],'unsupported_file')
    def test_fifo_never_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'fifo';os.mkfifo(p)
            self.assertEqual(subject.fingerprint(p)['error'],'unsupported_file')
    def test_diagnostic_requests_only_static_health_and_service_status(self):
        http_paths=[];commands=[]
        def fingerprint(p):return {'blob':subject.TARGETS.get(p.name,('unknown',''))[0],'sha256':'fixture'}
        def http(p):http_paths.append(p);return {'status':200,'sha256':'fixture'}
        def run(args,**kwargs):commands.append(args);return type('Result',(),{'stdout':'active\n'})()
        output=io.StringIO()
        with patch.object(subject,'fingerprint',fingerprint),patch.object(subject,'http',http),patch.object(subject.subprocess,'run',run),contextlib.redirect_stdout(output):subject.main()
        result=json.loads(output.getvalue())
        self.assertTrue(result['read_only']);self.assertFalse(result['installed_by_this_command'])
        self.assertTrue(all(p.startswith(('/?','/sync.js?','/ai-home-v2.js?','/manual.html?','/api/ai-home/health')) for p in http_paths))
        self.assertNotIn('/api/state',' '.join(http_paths))
        self.assertEqual(len(commands),3)
        self.assertTrue(all(c[:2]==['/usr/bin/systemctl','is-active'] for c in commands))
        self.assertFalse(result['candidate_inputs_match'])
    def test_health_false_is_not_converted_to_success(self):
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return b'{"ok":false,"sensitive":"not printed"}'
        class Opener:
            def open(self,request,timeout):
                self_url=request.full_url
                assert self_url=='http://127.0.0.1:8000/api/ai-home/health'
                return Response()
        with patch.object(subject.urllib.request,'build_opener',return_value=Opener()):result=subject.http('/api/ai-home/health')
        self.assertFalse(result['reported_ok']);self.assertNotIn('sensitive',json.dumps(result))
    def test_redirect_handler_does_not_follow_remote_location(self):
        self.assertIsNone(subject.NoRedirect().redirect_request(None,None,302,'redirect',{},'https://example.invalid'))

if __name__=='__main__':unittest.main()
