import importlib.util
import sys
from pathlib import Path

MODULE = Path(__file__).parents[1] / 'patch_web.py'
spec = importlib.util.spec_from_file_location('patch_web', MODULE)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
assert spec.loader
spec.loader.exec_module(mod)


def test_patchers_are_idempotent():
    html = '''<html><body>\n        <button class="nav-item" data-nav="settings"><span>···</span><b>Настройки</b></button>\n      <section class="view" id="view-settings" data-view="settings">\n      <button data-nav="proof"><span>↗</span><small>Факты</small></button>\n      <button data-nav="settings"><span>···</span><small>Ещё</small></button>\n</body></html>'''
    js = '''const VIEW_COPY = { direct: {\n      proof: 'Факты сильнее ощущения «я ничего не делаю».',\n      settings: 'x'\n}, calm: {\n      proof: 'Посмотри на реальные шаги, которые уже были.',\n      settings: 'y'\n}};\nfunction navigate(view) {\n    if (!['home', 'tasks', 'focus', 'proof', 'settings'].includes(view)) return;\n    if (view === 'proof') renderProof();\n}\n  function renderSettings() {}\nfunction renderAll() {\n    renderProof();\n    renderSettings();\n}\nconst actions = {\n        'install-app': installApp,\n        'reset-app': resetApp\n};'''
    css = '.mobile-nav { grid-template-columns: repeat(5, 1fr); }\n'
    sw = "const CACHE = 'dvizh-v1';\n"
    h1 = mod.patch_index(html); j1 = mod.patch_app(js); c1 = mod.patch_css(css); s1 = mod.patch_sw(sw)
    assert mod.MARKER_HTML in h1
    assert mod.MARKER_JS in j1
    assert mod.MARKER_CSS in c1
    assert 'dvizh-week-web-v1' in s1
    assert mod.patch_index(h1) == h1
    assert mod.patch_app(j1) == j1
    assert mod.patch_css(c1) == c1
    assert mod.patch_sw(s1) == s1
