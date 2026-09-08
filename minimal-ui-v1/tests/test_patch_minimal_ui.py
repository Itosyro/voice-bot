from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

MODULE = Path(__file__).parents[1] / 'patch_minimal_ui.py'
spec = importlib.util.spec_from_file_location('minimal_ui_patch', MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def fixture_html() -> str:
    return '''<html><body>
      <section class="view" id="view-training" data-view="training"><div class="training-heading"></div></section>
      <section class="view" id="view-social" data-view="social"><div class="social-heading"></div></section>
      <section class="view" id="view-settings" data-view="settings"></section>
      <nav class="mobile-nav">
        <button data-nav="home"></button><button data-nav="tasks"></button><button data-nav="focus"></button>
        <button data-nav="proof"></button><button data-nav="week"></button><button data-nav="training"></button>
        <button data-nav="social"></button><button data-nav="settings"></button>
      </nav>
    </body></html>'''


# Frozen pre-fix HTML: migration tests must not follow the production template.
OLD_PANEL = '''        <!-- DVIZH_MINIMAL_UI_V1 -->
        <article class="panel minimal-ui-settings" id="minimalUiSettings">
          <div class="minimal-ui-settings-head">
            <div>
              <p class="eyebrow">ИНТЕРФЕЙС</p>
              <h3>Спокойный режим</h3>
              <p>Меньше крупных заголовков, декоративных карточек и пунктов в нижнем меню. Все функции остаются на месте.</p>
            </div>
            <button type="button" class="ghost small" id="minimalUiToggle" aria-pressed="true">Включён</button>
          </div>
          <div class="minimal-ui-shortcuts" aria-label="Дополнительные разделы">
            <span>Дополнительные разделы</span>
            <div>
              <button type="button" class="ghost" data-minimal-nav="proof">↗ Факты</button>
              <button type="button" class="ghost" data-minimal-nav="training">🏋 Тренировки</button>
              <button type="button" class="ghost" data-minimal-nav="social">📱 Соцсети</button>
            </div>
          </div>
        </article>
'''


class PatchTests(unittest.TestCase):
    def test_patch_is_idempotent(self) -> None:
        html = mod.patch_index(fixture_html())
        js = mod.patch_app('function navigate(view) {}\n')
        css = mod.patch_css('body{}\n')
        sw = mod.patch_sw("const CACHE = 'dvizh-social-hub-v1';\n")
        assert mod.MARKER_HTML in html
        assert 'id="minimalUiToggle"' in html
        assert 'data-nav="training"' in html
        assert mod.MARKER_JS in js
        assert "dvizh:minimal-ui:v1" in js
        assert "data-minimal-secondary" in js
        assert mod.MARKER_CSS in css
        assert '.mobile-nav [data-nav="social"]' in css
        assert mod.CACHE_NAME in sw
        assert mod.patch_index(html) == html
        assert mod.patch_app(js) == js
        assert mod.patch_css(css) == css
        assert mod.patch_sw(sw) == sw


    def test_patch_root(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        tmp_path = Path(temporary.name)
        (tmp_path / 'index.html').write_text(fixture_html(), encoding='utf-8')
        (tmp_path / 'app.js').write_text('function navigate(view) {}\n', encoding='utf-8')
        (tmp_path / 'styles.css').write_text('body{}\n', encoding='utf-8')
        (tmp_path / 'sw.js').write_text("const CACHE = 'dvizh-social-hub-v1';\n", encoding='utf-8')
        changed = mod.patch_root(tmp_path)
        assert set(changed) == {'index.html', 'app.js', 'styles.css', 'sw.js'}
        assert mod.patch_root(tmp_path) == []
        assert mod.patch_root(tmp_path, check_only=True) == []


class Buttons(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.buttons = []
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'button':
            self.current = [dict(attrs), '']

    def handle_data(self, data):
        if self.current is not None:
            self.current[1] += data

    def handle_endtag(self, tag):
        if tag == 'button' and self.current is not None:
            self.buttons.append(self.current)
            self.current = None


class ShortcutTests(unittest.TestCase):
    routes = {'proof': '↗ Факты', 'training': '🏋 Тренировки', 'social': '📱 Соцсети'}

    def assert_router_shortcuts(self, html):
        buttons = Buttons(html).buttons
        for route, label in self.routes.items():
            with self.subTest(route=route):
                matches = [attrs for attrs, text in buttons if text == label]
                self.assertEqual(len(matches), 1)
                # The existing document click handler selects [data-nav].
                self.assertEqual(matches[0].get('data-nav'), route)
                self.assertNotIn('data-minimal-nav', matches[0])
                self.assertEqual(matches[0]['class'], 'ghost')
                self.assertEqual(matches[0]['type'], 'button')

    def expected_panel(self):
        panel = OLD_PANEL
        for route in self.routes:
            panel = panel.replace(f'data-minimal-nav="{route}"', f'data-nav="{route}"')
        return panel

    def test_new_panel_uses_existing_router_and_preserves_design(self):
        html = mod.patch_index(fixture_html())
        self.assert_router_shortcuts(html)
        self.assertEqual(mod.SETTINGS_PANEL, self.expected_panel())
        self.assertIn(self.expected_panel().rstrip(), html)
        self.assertEqual(mod.patch_index(html), html)

    def test_marked_old_panel_migrates_and_is_idempotent(self):
        source = '<main>\n' + OLD_PANEL + '</main>'
        html = mod.patch_index(source)
        self.assert_router_shortcuts(html)
        self.assertEqual(html, '<main>\n' + self.expected_panel() + '</main>')
        self.assertEqual(mod.patch_index(html), html)

    def test_migration_leaves_unrelated_elements_untouched(self):
        unrelated = '<button type="button" class="ghost" data-minimal-nav="proof">↗ Факты</button>'
        other_panel = OLD_PANEL.replace('id="minimalUiSettings"', 'id="otherSettings"')
        panel = OLD_PANEL.replace('<div class="minimal-ui-settings-head">', unrelated + '<div class="minimal-ui-settings-head">')
        panel = panel.replace('<span>Дополнительные разделы</span>', '<button data-minimal-nav="week">Неделя</button><span>Дополнительные разделы</span>')
        expected = self.expected_panel().replace('<div class="minimal-ui-settings-head">', unrelated + '<div class="minimal-ui-settings-head">')
        expected = expected.replace('<span>Дополнительные разделы</span>', '<button data-minimal-nav="week">Неделя</button><span>Дополнительные разделы</span>')
        source = unrelated + other_panel + panel + unrelated
        html = mod.patch_index(source)
        self.assertEqual(html, unrelated + other_panel + expected + unrelated)
        self.assertEqual(mod.patch_index(html), html)

    def test_new_panel_leaves_unrelated_shortcuts_untouched(self):
        unrelated = '<button data-minimal-nav="training">Other</button>'
        source = unrelated + fixture_html() + unrelated
        html = mod.patch_index(source)
        self.assertTrue(html.startswith(unrelated))
        self.assertTrue(html.endswith(unrelated))
        self.assert_router_shortcuts(html)

    def test_patch_root_migration_changes_only_html(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contents = {
                'index.html': OLD_PANEL,
                'app.js': mod.patch_app('(() => { function navigate(view) {} })();\n'),
                'styles.css': mod.patch_css('body{}\n'),
                'sw.js': mod.patch_sw("const CACHE = 'old';\n"),
            }
            for name, content in contents.items():
                (root / name).write_text(content, encoding='utf-8')
            self.assertEqual(mod.patch_root(root), ['index.html'])
            self.assert_router_shortcuts((root / 'index.html').read_text(encoding='utf-8'))
            for name in ('app.js', 'styles.css', 'sw.js'):
                self.assertEqual((root / name).read_text(encoding='utf-8'), contents[name])
            self.assertEqual(mod.patch_root(root), [])
