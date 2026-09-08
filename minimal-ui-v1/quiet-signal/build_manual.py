"""Offline, additive Manual release builder. Never reads the installed app."""
import argparse
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE = ROOT.parent / 'release/manual.html'
PINS = {
    'manual.html': 'c0e5ea92c829807320db58e4ed015215f8cbea59b03c5d7ed3bdb80ecce3696f',
    'styles.css': '4fc9de09753daffb3dcacba770684b7f6a152c23a9956fb85a797beba068c8c5',
    'app.js': '392b49d5e28438a7cf9ca8753d3f3bbcd307b77417e8f2c39b11cd28682f71ba',
    'boot.js': '1c766410e239a8092de001d6450da6fabcdd552a91f7de593abb0d626fbb0500',
}


def style_block(css=None):
    if css is None:
        css = (ROOT / 'manual.css').read_bytes()
    # Deliberately narrow CSS subset: no HTML breakout, escapes, imports or URLs.
    clean = re.sub(rb'/\*.*?\*/', b'', css, flags=re.S)
    if b'<' in css or b'\\' in css or re.search(rb'@import|url\s*\(|expression\s*\(', clean, re.I):
        raise ValueError('unsafe CSS insertion')
    return b'<style id="quiet-signal-manual-v2">\n' + css + b'</style>\n'


def build(source=None):
    for name, digest in PINS.items():
        if hashlib.sha256((ROOT / 'baseline' / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'baseline integrity failure: {name}')
    if source is None:
        source = (ROOT / 'baseline/manual.html').read_bytes()
    if hashlib.sha256(source).hexdigest() != PINS['manual.html']:
        raise ValueError('baseline integrity failure: supplied manual.html')
    style = style_block()
    header = (ROOT / 'mode_header.html').read_bytes()
    if source.count(b'</head>') != 1 or source.count(b'<body>') != 1:
        raise ValueError('baseline insertion anchors must be unique')
    return source.replace(b'</head>', style + b'</head>', 1).replace(b'<body>', b'<body>' + header, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify release without writing')
    args = parser.parse_args()
    result = build()
    if args.check:
        if not RELEASE.is_file() or RELEASE.read_bytes() != result:
            raise SystemExit('release differs; run build_manual.py')
        print('Manual release is reproducible')
    else:
        RELEASE.parent.mkdir(exist_ok=True)
        RELEASE.write_bytes(result)


if __name__ == '__main__':
    main()
