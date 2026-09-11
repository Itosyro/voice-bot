"""Retirement contract for the superseded schema-2 runtime deployment feature.

Its positive runtime-auto/mixed-batch assertions are intentionally replaced:
v2.3.2 restores schema 1; v2.2 suites exercise its actual transaction behavior.
"""
import unittest
from test_hardening_v231 import module

class RetiredRuntimeTests(unittest.TestCase):
    def test_all_former_runtime_auto_targets_require_owner_approval(self):
        g=module('dvizhrelease')
        for target in ('/usr/local/libexec/dvizh-context','/usr/local/libexec/dvizh-proposals',
                       '/opt/dvizh-ai-approval/proposal_bridge.py','/opt/dvizh-ai-home/ai_home_bridge.py'):
            with self.subTest(target=target):
                self.assertIn(g.target_risk(target), ('approval',g.PRIVILEGED_CLASS))
                with self.assertRaisesRegex(g.GateError,'schema 1'):
                    g.validate_manifest({'mode':'auto'}, {'schema':2,'operations':[{'target':target}]})

    def test_only_existing_three_static_targets_auto(self):
        g=module('dvizhrelease')
        self.assertEqual(set(g.SAFE_TARGETS), {'/opt/dvizh/static/index.html',
            '/opt/dvizh/static/ai-home-v2.js','/opt/dvizh/static/ai-home-v2.css'})
        for name in ('manual.html','app.js','sync.js','styles.css','sw.js'):
            self.assertEqual(g.target_risk('/opt/dvizh/static/'+name),'approval')
        self.assertEqual(g.target_risk('/opt/dvizh/server.py'),'approval')

    def test_root_state_fix_preserved(self):
        g=module('dvizhrelease')
        self.assertEqual(str(g.APPROVAL_ROOT),'/var/lib/dvizh-release-gate/approvals')
        self.assertEqual(str(g.BACKUP_ROOT),'/var/lib/dvizh-release-gate/backups')
