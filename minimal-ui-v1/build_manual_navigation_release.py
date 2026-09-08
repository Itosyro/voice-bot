"""Build the narrowly pinned Manual payload; never write to production."""
from pathlib import Path
import hashlib
from patch_minimal_ui import patch_index

BASE_SHA256 = '79268a83f3c5ca776a3576e51841aba98433f11b6f2e42ceaf89f7d544ce67f4'


def build(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != BASE_SHA256:
        raise ValueError('Manual baseline changed; inspect it before preparing a release')
    text = source.decode('utf-8')
    expected = text
    for route in ('proof', 'training', 'social'):
        old = f'data-minimal-nav="{route}"'
        if text.count(old) != 1:
            raise ValueError(f'Expected exactly one shortcut: {route}')
        expected = expected.replace(old, f'data-nav="{route}"')
    actual = patch_index(text)
    if actual != expected:
        raise ValueError('Migration changed more than the three route attributes')
    return actual.encode('utf-8')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('baseline', type=Path)
    args = parser.parse_args()
    # Destination is fixed inside this module's checkout, not caller-controlled.
    target = Path(__file__).resolve().parent / 'release' / 'manual.html'
    payload = build(args.baseline.read_bytes())
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(payload)
    print(f'{target}: {len(payload)} bytes; only three navigation attributes changed')
