"""Build the five daily-use client updates offline from immutable snapshots.

Does not install, contact a server, change tracked historical Health Recovery
artifacts, or grant any authority. Output must be a new directory.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from client_resilience import (RELEASE_KEY, apply_ai_client, apply_sync_client,
                               apply_ai_entry, apply_manual_entry)
from manual_submit_resilience import apply_manual_client

ROOT = Path(__file__).resolve().parent
BASE_COMMIT = '9d492693de2c7cf66350293afcf42b74edeebaef'
INPUT_BLOBS = {
    'app.js': '89fa0ccaa3b72f28571042f8b820ea7238c41731',
    'ai-home-v2.js': '075cea330640ab94da266365a87c81c769e0d467',
    'sync.js': 'd1a935c1451d58b5671bc3553db0864a5caf2746',
    'index.html': '271d72f3f6b5021240b32ee1a90f76d56de4ddbc',
    'manual.html': 'c94da18a1d5e2b87be7ddb09e4cb4548504e1928',
}
TRANSFORMS = {'app.js': apply_manual_client, 'ai-home-v2.js': apply_ai_client, 'sync.js': apply_sync_client,
              'index.html': apply_ai_entry, 'manual.html': apply_manual_entry}


def blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def render(source: Path = ROOT / 'dist') -> dict[str, bytes]:
    result = {}
    for name, expected in INPUT_BLOBS.items():
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Not a regular source file: {name}')
        data = path.read_bytes()
        if blob(data) != expected:
            raise ValueError(f'Unexpected immutable source bytes: {name}')
        result[name] = TRANSFORMS[name](data.decode('utf-8')).encode('utf-8')
    return result


def build(destination: Path, source: Path = ROOT / 'dist') -> dict:
    payload = render(source)
    # Refuse existing destinations: this utility is not an in-place updater.
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    rows = []
    for name, data in payload.items():
        (destination / name).write_bytes(data)
        rows.append({'file': name, 'sha256': hashlib.sha256(data).hexdigest(),
                     'base_blob': INPUT_BLOBS[name], 'bytes': len(data)})
    manifest = {'schema': 1, 'release_key': RELEASE_KEY,
                'baseline_commit': BASE_COMMIT, 'installed': False,
                'files': rows, 'restarts': [],
                'note': 'Source-built candidate only. Not an authorized production release proposal.'}
    (destination / 'BUILD.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))
