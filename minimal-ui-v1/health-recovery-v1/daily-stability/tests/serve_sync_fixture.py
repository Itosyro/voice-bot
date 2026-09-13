"""Loopback-only integration fixture using the unchanged, pinned DVIZH backend."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
source = Path(os.environ.get('DVIZH_TEST_SERVER_SOURCE', ROOT.parent / 'baseline/helpers/server.py'))
spec = importlib.util.spec_from_file_location('dvizh_sync_fixture_server', source)
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

with tempfile.TemporaryDirectory(prefix='dvizh-sync-test-') as tmp:
    root = Path(tmp)
    static_dir = root / 'empty-static'
    static_dir.mkdir()
    store = backend.StateStore(root / 'fixture.db')
    server = backend.DVIZHServer(('127.0.0.1', 0), backend.Handler,
                                 store=store, static_dir=static_dir)
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
