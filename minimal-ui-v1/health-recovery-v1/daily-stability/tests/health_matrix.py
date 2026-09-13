#!/usr/bin/env python3
"""Run unchanged Health browser assertions against NEW assets in an isolated copy."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile

DAILY = Path(__file__).resolve().parents[1]
HEALTH = DAILY.parent
REPO = HEALTH.parents[1]
SCRIPTS = ('browser.cjs', 'mixed-cache.cjs', 'approval-browser.cjs', 'sync-concurrent-browser.cjs')

def main():
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (HEALTH / 'dist').iterdir()}
    with tempfile.TemporaryDirectory(prefix='dvizh-health-new-client-') as temporary:
        mirror = Path(temporary)
        copied = mirror / 'minimal-ui-v1/health-recovery-v1'
        shutil.copytree(HEALTH, copied, ignore=shutil.ignore_patterns('daily-stability', '__pycache__', '*.png'))
        shutil.copytree(REPO / 'hermes-control-v1', mirror / 'hermes-control-v1', ignore=shutil.ignore_patterns('__pycache__'))
        for asset in (DAILY / 'dist').iterdir():
            shutil.copyfile(asset, copied / 'dist' / asset.name)
        # Do not call the historical builder: that would silently test old clients.
        for script in SCRIPTS:
            assert (copied / 'tests' / script).read_bytes() == (HEALTH / 'tests' / script).read_bytes()
            subprocess.run(['node', str(copied / 'tests' / script)], check=True, timeout=90)
        for image in (copied / 'tests').glob('*.png'):
            shutil.copyfile(image, DAILY / 'tests' / ('daily-health-' + image.name))
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
    print('PASS: four unchanged Health browser runners tested against new daily clients; historical assets untouched')

if __name__ == '__main__':
    main()
