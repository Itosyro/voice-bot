"""Static cascade contracts; browser.cjs provides computed-style verification."""
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class StyleTests(unittest.TestCase):
    def setUp(self):
        self.css = (ROOT / 'manual.css').read_text()
        self.live = (ROOT / 'baseline/styles.css').read_text()

    def test_dark_tokens_win_over_both_live_modes(self):
        for declaration in ('--bg: #0b0e11', '--panel: #12191e', '--panel-2: #171e24',
                            '--text: #e5e9ec', '--muted: #9ba7af', '--lime: #9de0bd'):
            self.assertIn(declaration + ' !important', self.css)
        for selector in ('html:root body', 'html:root .rescue-card', 'html:root .modal',
                         'html:root .toast', 'html:root input', 'html:root textarea'):
            self.assertIn(selector, self.css)
        self.assertIn('html:root .button-primary', self.css)
        self.assertIn('background: var(--lime) !important', self.css)

    def test_mobile_routes_override_existing_hiding_without_removing_hooks(self):
        self.assertIn('.mobile-nav [data-nav="proof"]', self.live)
        self.assertIn('html:root .mobile-nav [data-nav]', self.css)
        self.assertIn('grid-template-columns: repeat(4, minmax(0, 1fr)) !important', self.css)
        self.assertIn('min-height: 44px !important', self.css)
        self.assertIn('env(safe-area-inset-bottom)', self.css)
        self.assertNotIn('.view:not([data-minimal-details])', self.css)
        self.assertIn('html:root [hidden]', self.css)
        # Existing explicit Details close/open states must still work.
        self.assertNotIn('.view:not([data-minimal-details="open"])', self.css)

    def test_real_data_infographics_only(self):
        for selector in ('#timerRing', '.day-proof.has-proof', '.training-metrics', '.social-column'):
            self.assertIn(selector, self.css)
        self.assertIn('var(--progress)', self.css)
        self.assertIn('.day-proof.has-proof strong', self.css)
        self.assertIn('<strong>${day.count}</strong>', (ROOT / 'baseline/app.js').read_text())
        # Do not freeze live progress or invent proportions/counts through CSS.
        self.assertNotRegex(self.css, r'--progress\s*:|counter\(|attr\(|content\s*:\s*[\'"][^\'"]+')
        self.assertNotRegex(self.css, r'width\s*:\s*\d+%')
        source = (ROOT / 'mode_header.html').read_text()
        texts = re.sub(r'<!--.*?-->', '', source, flags=re.S)
        texts = re.sub(r'<[^>]*>', ' ', texts)
        self.assertEqual(texts.split(), ['ДВИЖ','QUIET','SIGNAL','ИИ','Ручной'])

    def test_structural_css_safety(self):
        css = re.sub(r'/\*.*?\*/', '', self.css, flags=re.S)
        self.assertEqual(css.count('{'), css.count('}'))
        self.assertNotRegex(css, r'visibility\s*:\s*hidden|opacity\s*:\s*0\s*[;!}]|pointer-events\s*:\s*none')
        # Only native hidden elements may be hidden by this added sheet.
        hidden_rules = re.findall(r'([^{}]+)\{[^{}]*display\s*:\s*none[^{}]*\}', css)
        self.assertEqual([s.strip() for s in hidden_rules], ['html:root [hidden]'])
        self.assertNotRegex(css, r'\.view\s*\{[^}]*display\s*:')

if __name__ == '__main__':
    unittest.main()
