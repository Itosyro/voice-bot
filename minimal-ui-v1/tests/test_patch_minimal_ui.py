from __future__ import annotations

import importlib.util
import sys
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


def test_patch_is_idempotent() -> None:
    html = mod.patch_index(fixture_html())
    js = mod.patch_app('function navigate(view) {}\n')
    css = mod.patch_css('body{}\n')
    sw = mod.patch_sw("const CACHE = 'dvizh-social-hub-v1';\n")
    assert mod.MARKER_HTML in html
    assert 'id="minimalUiToggle"' in html
    assert 'data-minimal-nav="training"' in html
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


def test_patch_root(tmp_path: Path) -> None:
    (tmp_path / 'index.html').write_text(fixture_html(), encoding='utf-8')
    (tmp_path / 'app.js').write_text('function navigate(view) {}\n', encoding='utf-8')
    (tmp_path / 'styles.css').write_text('body{}\n', encoding='utf-8')
    (tmp_path / 'sw.js').write_text("const CACHE = 'dvizh-social-hub-v1';\n", encoding='utf-8')
    changed = mod.patch_root(tmp_path)
    assert set(changed) == {'index.html', 'app.js', 'styles.css', 'sw.js'}
    assert mod.patch_root(tmp_path) == []
    assert mod.patch_root(tmp_path, check_only=True) == []
