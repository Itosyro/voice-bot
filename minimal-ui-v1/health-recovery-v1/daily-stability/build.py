#!/usr/bin/env python3
"""Reproduce client-only daily fixes from immutable Health Recovery snapshots.

Never touches production, historical generated files, or control-plane components.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HEALTH = ROOT.parent
REPO = HEALTH.parents[1]
FILES = ('ai-home-v2.js', 'sync.js', 'app.js', 'index.html', 'manual.html')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate() -> dict[str, bytes]:
    pins = json.loads((ROOT / 'source-pins.json').read_text())
    source = {}
    for name, expected in pins['sha256'].items():
        raw = (HEALTH / 'dist' / name).read_bytes()
        if digest(raw) != expected:
            raise ValueError(f'Historical snapshot changed: {name}; do not overwrite newer application files')
        source[name] = raw
    spec = importlib.util.spec_from_file_location('client_resilience', HEALTH / 'client_resilience.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RELEASE_KEY = '20260914-daily-stability-1'
    output = {f'dist/{name}': raw for name, raw in source.items()}
    for name, function in [('ai-home-v2.js', module.apply_ai_client), ('sync.js', module.apply_sync_client),
                           ('index.html', module.apply_ai_entry), ('manual.html', module.apply_manual_entry)]:
        text = function(source[name].decode('utf-8'))
        if name == 'ai-home-v2.js':
            text = module.once(text,
                '      if (submission?.mayHaveBeenSent) return;\n      const text = voice ? voice.draft : input.value;',
                '      const text = voice ? voice.draft : input.value;\n      // A different newly typed draft was never submitted.\n      if (submission?.mayHaveBeenSent && text.trim().slice(0, 12000) === submission.text) return;')
        if name == 'sync.js':
            text = module.once(text, '    inFlight = true;\n    queued = false;',
                '    clearTimeout(pushTimer);\n    pushTimer = null;\n    inFlight = true;\n    queued = false;')
        output[f'dist/{name}'] = text.encode('utf-8')
    # Missing/unknown display preference must not crash navigation after a remote pull.
    # This is a read-only display fallback; never invent or overwrite a saved preference.
    app = source['app.js'].decode('utf-8')
    if app.count('VIEW_COPY[state.tone]') != 4:
        raise ValueError('Expected four tone-dependent render sites')
    app = app.replace('VIEW_COPY[state.tone]', "VIEW_COPY[state.tone === 'calm' ? 'calm' : 'direct']")
    output['dist/app.js'] = app.encode('utf-8')
    prefix = ROOT.relative_to(REPO).as_posix()
    manifest = {'schema': 1, 'name': module.RELEASE_KEY, 'operations': [
        {'source': f'{prefix}/dist/{name}', 'target': f'/opt/dvizh/static/{name}',
         'http_path': '/' if name == 'index.html' else '/' + name}
        for name in ('sync.js', 'app.js', 'ai-home-v2.js', 'index.html', 'manual.html')], 'restarts': []}
    payload = {'schema': 1, 'release': module.RELEASE_KEY, 'source_commit': pins['commit'],
               'production_installed': False, 'requires_owner_approval': True,
               'changed_files': list(FILES),
               'files': {name: {'before_sha256': digest(source[name]),
                                'after_sha256': digest(output[f'dist/{name}']),
                                'changed': name in FILES} for name in sorted(source)},
               'builder_sha256': digest(Path(__file__).read_bytes()),
               'client_resilience_sha256': digest((HEALTH / 'client_resilience.py').read_bytes())}
    for name, value in [('release.json', manifest), ('PAYLOAD.json', payload)]:
        output[name] = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')
    return output


def build(check: bool = False) -> None:
    output = generate()
    for rel, raw in output.items():
        target = ROOT / rel
        if check:
            if not target.is_file() or target.read_bytes() != raw:
                raise ValueError(f'Generated file is missing or differs: {rel}')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    if {p.name for p in (ROOT / 'dist').iterdir()} != {p.name for p in (HEALTH / 'dist').iterdir()}:
        raise ValueError('Unexpected generated static target')
    print(f'PASS: {len(output)} reproducible artifacts; exactly five client files change; no service restart')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    build(parser.parse_args().check)
