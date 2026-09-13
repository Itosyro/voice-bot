"""Loopback-only real DVIZH HTTP/SQLite fixture; no production identity or API."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('daily_fixture_backend', ROOT / 'baseline/helpers/server.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)
static = Path(sys.argv[1]).resolve(strict=True)
with tempfile.TemporaryDirectory(prefix='dvizh-daily-db-') as tmp:
    store = backend.StateStore(Path(tmp) / 'fixture.db')
    for number in range(1, 10):
        state = {'version': 1, 'tasks': [], 'hasSeenIntro': True, 'tone': 'calm',
                 'checkins': {}, 'plans': {}, 'sessions': [], 'proofs': [],
                 'future': {'keep': True}, 'healthRecovery': {'version': 1, 'timezone': 'UTC'}}
        store.put(f'daily-browser-{number}', 'browser@example.invalid', state, 0)
    server = backend.DVIZHServer(('127.0.0.1', 0), backend.Handler, store=store, static_dir=static)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(json.dumps({'port': server.server_port}), flush=True)
    try:
        for line in sys.stdin:
            if line.strip() == 'stop':
                break
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
