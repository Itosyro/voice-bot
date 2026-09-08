import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_manual_navigation_release as builder
from patch_minimal_ui import patch_index


class ReleaseTests(unittest.TestCase):
    def test_payload_changes_only_the_three_original_attributes(self):
        payload = (ROOT / 'release/manual.html').read_bytes()
        text = payload.decode('utf-8')
        for route in ('proof', 'training', 'social'):
            old = f'<button type="button" class="ghost" data-nav="{route}">'
            self.assertEqual(text.count(old), 1)
            text = text.replace(old, old.replace('data-nav', 'data-minimal-nav'))
        baseline = text.encode('utf-8')
        self.assertEqual(hashlib.sha256(baseline).hexdigest(), builder.BASE_SHA256)
        self.assertEqual(builder.build(baseline), payload)
        self.assertEqual(patch_index(payload.decode()), payload.decode())

    def test_builder_refuses_a_changed_baseline(self):
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            builder.build(b'<html>unexpected production change</html>')

    def test_manifest_targets_only_manual_without_restart(self):
        manifest = json.loads((ROOT.parent / '.autopilot/release.json').read_text())
        self.assertEqual(manifest['schema'], 1)
        self.assertEqual(manifest['restarts'], [])
        self.assertEqual(manifest['operations'], [{
            'source': 'minimal-ui-v1/release/manual.html',
            'target': '/opt/dvizh/static/manual.html',
            'http_path': '/manual.html',
        }])


if __name__ == '__main__':
    unittest.main()
