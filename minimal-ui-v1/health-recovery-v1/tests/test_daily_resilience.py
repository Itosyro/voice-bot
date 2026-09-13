"""Exercise the cumulative daily-use client candidate without rewriting history."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
# The original Health builder and preservation/reproducibility checks remain intact.
sys.path.insert(0, str(ROOT))
import build_daily

EXPECTED = {
    'ai-home-v2.js': 'e449ac6a7abdc5eda6bba09b7fb86e0da72bf16854d5e8b6003a755cd602a1c3',
    'sync.js': 'd474da15914297cdcf064d50eb471172854f051c2bc5c645f2eb0b2a9345569f',
    'index.html': '656d6062346ae6b651eeaec2119fd800144e0854c9c55aced05b2f90edbabb43',
    'manual.html': '24161668ce78443cd83e7b0f09bff7ea7ff80a2277d63c24443e744c2debc868',
}


class DailyResilienceTests(unittest.TestCase):
    def test_exact_candidate_and_unchanged_design(self):
        before = {p.name: p.read_bytes() for p in (ROOT / 'dist').iterdir() if p.is_file()}
        payload = build_daily.render()
        self.assertEqual(set(payload), set(EXPECTED)|{'app.js'})
        for name, expected in EXPECTED.items():
            self.assertEqual(hashlib.sha256(payload[name]).hexdigest(), expected, name)
        print('DAILY_APP_SHA256='+hashlib.sha256(payload['app.js']).hexdigest(), flush=True)
        app = payload['app.js'].decode()
        self.assertIn('if (epoch !== submitEpoch) return;', app)
        self.assertNotIn('queueMicrotask(() => { submitBase = null;', app)
        self.assertEqual(app.count('const epoch = ++submitEpoch;'), 1)
        for name in ('index.html', 'manual.html'):
            old, new = before[name].decode(), payload[name].decode()
            # HTML alterations are only the declared asset/self-navigation keys.
            if name == 'index.html':
                old = old.replace('20260905-3.1-voice-20260908-speech-1-quiet-signal-2', build_daily.RELEASE_KEY).replace('20260908-quiet-signal-2', build_daily.RELEASE_KEY)
            else:
                old = old.replace('sync.js?v=20260909-sync-stability-2', 'sync.js?v='+build_daily.RELEASE_KEY).replace('href="/manual.html" aria-current="page"', 'href="/manual.html?v='+build_daily.RELEASE_KEY+'" aria-current="page"')
            self.assertEqual(old, new)
        with tempfile.TemporaryDirectory(prefix='daily-repro-') as tmp:
            one, two = Path(tmp)/'one', Path(tmp)/'two'
            build_daily.build(one); build_daily.build(two)
            self.assertEqual({p.name:p.read_bytes() for p in one.iterdir()}, {p.name:p.read_bytes() for p in two.iterdir()})
            with self.assertRaises(FileExistsError): build_daily.build(one)
            for name in ('sync.js','ai-home-v2.js','app.js'):
                subprocess.run(['node','--check',str(one/name)],check=True,timeout=20)
        self.assertEqual(before, {p.name:p.read_bytes() for p in (ROOT/'dist').iterdir() if p.is_file()})

    def test_native_browser_http_daily_flows(self):
        before = {p.name:p.read_bytes() for p in (ROOT/'dist').iterdir() if p.is_file()}
        with tempfile.TemporaryDirectory(prefix='daily-native-browser-') as tmp:
            static = Path(tmp)/'static'
            build_daily.build(static)
            # Actual app/boot/styles and helper snapshots stay byte-identical.
            # No generated replacement or UI stub substitutes for Manual.
            for name, data in before.items():
                if name not in build_daily.INPUT_BLOBS: (static/name).write_bytes(data)
            result = subprocess.run(['node',str(ROOT/'tests/daily-browser.cjs'),str(static)],
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=240)
            print(result.stdout, flush=True)
            self.assertEqual(result.returncode,0,'native daily browser acceptance failed:\n'+result.stdout)
        self.assertEqual(before,{p.name:p.read_bytes() for p in (ROOT/'dist').iterdir() if p.is_file()})
