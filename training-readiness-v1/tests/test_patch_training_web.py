from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).parents[2]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader
    spec.loader.exec_module(module)
    return module


week = load("training_test_week_patch", REPO / "web-week-v1" / "patch_web.py")
editor = load("training_test_editor_patch", REPO / "web-week-editor-v1" / "patch_web_editor.py")
training = load("training_test_training_patch", REPO / "training-readiness-v1" / "patch_training_web.py")


def base_assets() -> tuple[str, str, str, str]:
    html = '''<html><body>
        <button class="nav-item" data-nav="settings"><span>···</span><b>Настройки</b></button>
      <section class="view" id="view-settings" data-view="settings">
      <button data-nav="proof"><span>↗</span><small>Факты</small></button>
      <button data-nav="settings"><span>···</span><small>Ещё</small></button>
</body></html>'''
    js = '''const VIEW_COPY = { direct: {
      proof: 'Факты сильнее ощущения «я ничего не делаю».',
      settings: 'x'
}, calm: {
      proof: 'Посмотри на реальные шаги, которые уже были.',
      settings: 'y'
}};
function navigate(view) {
    if (!['home', 'tasks', 'focus', 'proof', 'settings'].includes(view)) return;
    if (view === 'proof') renderProof();
}
  function renderSettings() {}
function renderAll() {
    renderProof();
    renderSettings();
}
const actions = {
        'install-app': installApp,
        'reset-app': resetApp
};'''
    css = '.mobile-nav { grid-template-columns: repeat(5, 1fr); }\n'
    sw = "const CACHE = 'dvizh-v1';\n"
    return html, js, css, sw


def fully_patched_assets() -> tuple[str, str, str, str]:
    html, js, css, sw = base_assets()
    html = editor.patch_index(week.patch_index(html))
    js = editor.patch_app(week.patch_app(js))
    css = editor.patch_css(week.patch_css(css))
    sw = editor.patch_sw(week.patch_sw(sw))
    return html, js, css, sw


def test_training_patch_is_idempotent_and_preserves_week_editor():
    html, js, css, sw = fully_patched_assets()
    h1 = training.patch_index(html)
    j1 = training.patch_app(js)
    c1 = training.patch_css(css)
    s1 = training.patch_sw(sw)

    assert training.MARKER_HTML in h1
    assert training.MARKER_JS in j1
    assert training.MARKER_CSS in c1
    assert "dvizh-training-web-v1" in s1
    assert "DVIZH_WEEK_EDITOR_V1" in h1
    assert "DVIZH_WEEK_EDITOR_V1" in j1
    assert "weekEditorForm" in h1
    assert "trainingReadinessForm" in h1
    assert "trainingHub" in j1
    assert "data-nav=\"training\"" in h1

    assert training.patch_index(h1) == h1
    assert training.patch_app(j1) == j1
    assert training.patch_css(c1) == c1
    assert training.patch_sw(s1) == s1


def test_training_patch_requires_existing_week_view():
    html, js, css, sw = base_assets()
    try:
        training.patch_index(html)
    except RuntimeError:
        pass
    else:
        raise AssertionError("training patch accepted an app without the week view")
