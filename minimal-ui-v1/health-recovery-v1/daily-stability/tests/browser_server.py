"""Loopback-only, disposable HTTP/SQLite server. No production access or identities."""
from pathlib import Path
import importlib.util
import json
import tempfile
import threading
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('daily_fixture_backend', ROOT.parent / 'baseline/helpers/server.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)
with tempfile.TemporaryDirectory(prefix='dvizh-daily-browser-') as temporary:
    server = backend.DVIZHServer(('127.0.0.1', 0), backend.Handler,
        store=backend.StateStore(Path(temporary) / 'fixture.sqlite'), static_dir=ROOT / 'dist')
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
