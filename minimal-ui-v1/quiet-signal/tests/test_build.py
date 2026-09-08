import hashlib
import re
from html.parser import HTMLParser
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    'manual.html': 'c0e5ea92c829807320db58e4ed015215f8cbea59b03c5d7ed3bdb80ecce3696f',
    'styles.css': '4fc9de09753daffb3dcacba770684b7f6a152c23a9956fb85a797beba068c8c5',
    'app.js': '392b49d5e28438a7cf9ca8753d3f3bbcd307b77417e8f2c39b11cd28682f71ba',
    'boot.js': '1c766410e239a8092de001d6450da6fabcdd552a91f7de593abb0d626fbb0500',
}

def builder():
    spec = importlib.util.spec_from_file_location('quiet_manual', ROOT / 'build_manual.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class BuildTests(unittest.TestCase):
    def test_pinned_snapshot(self):
        for name, digest in PINS.items():
            path = ROOT / 'baseline' / name
            self.assertTrue(path.is_file(), f'missing pinned {name}')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_deterministic_identity_and_reject_drift(self):
        mod = builder()
        source = (ROOT / 'baseline/manual.html').read_bytes()
        self.assertEqual(mod.build(), mod.build())
        self.assertEqual(mod.build(source), mod.build())
        for changed in (source + b' ', source.replace(b'data-nav="proof"', b'data-minimal-nav="proof"')):
            with self.assertRaisesRegex(ValueError, 'baseline'):
                mod.build(changed)

class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=False)
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, attrs))


class AdditiveTests(unittest.TestCase):
    def test_exact_additions_preserve_all_original_bytes(self):
        mod = builder()
        source = (ROOT / 'baseline/manual.html').read_bytes()
        result = mod.build()
        style = mod.style_block()
        header = (ROOT / 'mode_header.html').read_bytes()
        self.assertEqual(result.count(style), 1)
        self.assertEqual(result.count(header), 1)
        self.assertEqual(result.replace(style, b'', 1).replace(header, b'', 1), source)
        self.assertEqual(result, source.replace(b'</head>', style + b'</head>', 1)
                         .replace(b'<body>', b'<body>' + header, 1))
        # Includes every old ID, attribute, form/input/action, inline style and script.
        old = Elements(source.decode()).tags
        stripped = result.replace(style, b'', 1).replace(header, b'', 1)
        self.assertEqual(Elements(stripped.decode()).tags, old)
        for tag in ('script', 'style'):
            pattern = rb'<' + tag.encode() + rb'\b[^>]*>.*?</' + tag.encode() + rb'>'
            actual = result.replace(style, b'', 1) if tag == 'style' else result
            self.assertEqual(re.findall(pattern, actual, re.S), re.findall(pattern, source, re.S))
        self.assertNotIn(b'data-minimal-nav=', result)
        for route in ('proof', 'training', 'social'):
            self.assertIn(f'class="ghost" data-nav="{route}"'.encode(), result)

    def test_accessible_mode_links_without_route_handler(self):
        result = builder().build().decode()
        headers = re.findall(r'<header class="qs-mode-header">.*?</header>', result, re.S)
        self.assertEqual(len(headers), 1)
        tags = Elements(headers[0]).tags
        nav = next(dict(attrs) for tag, attrs in tags if tag == 'nav')
        self.assertEqual(nav['aria-label'], 'Режим работы')
        links = [dict(attrs) for tag, attrs in tags if tag == 'a']
        self.assertEqual([link['href'] for link in links], ['/', '/manual.html'])
        self.assertEqual(links[1]['aria-current'], 'page')
        self.assertTrue(all('data-nav' not in link and 'onclick' not in link for link in links))
        self.assertIn('>ИИ</a>', headers[0])
        self.assertIn('>Ручной</a>', headers[0])

    def test_css_insert_rejects_html_and_external_or_executable_content(self):
        mod = builder()
        self.assertIn(b'<style', mod.style_block())
        for css in ('</style><script>alert(1)</script>', '@import "x.css";',
                    'body{background:url(https://example.com)}', 'a{width:expression(1)}',
                    r'a{background:u\72l(x)}'):
            with self.subTest(css=css), self.assertRaises(ValueError):
                mod.style_block(css.encode())

if __name__ == '__main__':
    unittest.main()
