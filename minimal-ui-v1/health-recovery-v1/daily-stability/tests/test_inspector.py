"""The read-only morning diagnostic is tested only on temporary fixtures."""
import importlib.util
import io
import json
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from email.message import Message

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('daily_inspector',ROOT/'inspect-installed.py')
inspector=importlib.util.module_from_spec(spec);spec.loader.exec_module(inspector)

class InspectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.file=self.root/'fixture.py';self.file.write_text("VERSION = '2026.09.14-fixture.1'\nraise RuntimeError('must never execute')\n")

    def test_fingerprint_and_literal_do_not_execute_code(self):
        before=self.file.read_bytes();result=inspector.fingerprint(self.file)
        self.assertEqual(result['bytes'],len(before));self.assertEqual(inspector.version_literal(self.file),{'version_literal':'2026.09.14-fixture.1','executed':False})
        self.assertEqual(self.file.read_bytes(),before)

    def test_rejects_file_symlink(self):
        link=self.root/'link.py';link.symlink_to(self.file)
        self.assertEqual(inspector.fingerprint(link)['match'],'UNREADABLE_STOP')

    def test_rejects_ancestor_symlink(self):
        directory=self.root/'linkdir';directory.symlink_to(self.root,target_is_directory=True)
        self.assertEqual(inspector.fingerprint(directory/self.file.name)['match'],'UNREADABLE_STOP')

    def test_rejects_multiple_links(self):
        os.link(self.file,self.root/'second.py')
        self.assertEqual(inspector.fingerprint(self.file)['match'],'UNREADABLE_STOP')

    def test_html_status_200_is_not_a_healthy_application(self):
        class Response(io.BytesIO):
            status=200
            headers=Message()
        Response.headers['Content-Type']='text/html'
        with patch.object(inspector.urllib.request,'build_opener') as factory:
            factory.return_value.open.return_value=Response(b'<html>not an API</html>')
            self.assertFalse(inspector.health()['ok'])

    def test_whitelisted_json_health_omits_private_extra_fields(self):
        class Response(io.BytesIO):
            status=200
            headers=Message()
        Response.headers['Content-Type']='application/json'
        with patch.object(inspector.urllib.request,'build_opener') as factory:
            factory.return_value.open.return_value=Response(json.dumps({'ok':True,'app':'dvizh','private_extra':'do not print'}).encode())
            result=inspector.health();self.assertTrue(result['ok']);self.assertNotIn('private_extra',result)

if __name__=='__main__':
    unittest.main()
