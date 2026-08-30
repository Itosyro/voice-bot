import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parents[2]


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec); sys.modules[name]=mod; spec.loader.exec_module(mod); return mod


def test_editor_patch_upgrades_week_v1_and_is_idempotent():
    week=load('week_patch_for_editor', ROOT/'web-week-v1'/'patch_web.py')
    editor=load('editor_patch', ROOT/'web-week-editor-v1'/'patch_web_editor.py')
    html='''<html><body>\n        <button class="nav-item" data-nav="settings"><span>···</span><b>Настройки</b></button>\n      <section class="view" id="view-settings" data-view="settings">\n      <button data-nav="proof"><span>↗</span><small>Факты</small></button>\n      <button data-nav="settings"><span>···</span><small>Ещё</small></button>\n</body></html>'''
    js='''const VIEW_COPY = { direct: {\n      proof: 'Факты сильнее ощущения «я ничего не делаю».',\n      settings: 'x'\n}, calm: {\n      proof: 'Посмотри на реальные шаги, которые уже были.',\n      settings: 'y'\n}};\nfunction navigate(view) {\n    if (!['home', 'tasks', 'focus', 'proof', 'settings'].includes(view)) return;\n    if (view === 'proof') renderProof();\n}\n  function renderSettings() {}\nfunction renderAll() {\n    renderProof();\n    renderSettings();\n}\nconst actions = {\n        'install-app': installApp,\n        'reset-app': resetApp\n};'''
    css='.mobile-nav { grid-template-columns: repeat(5, 1fr); }\n'
    sw="const CACHE = 'dvizh-v1';\n"
    html=week.patch_index(html); js=week.patch_app(js); css=week.patch_css(css); sw=week.patch_sw(sw)
    with tempfile.TemporaryDirectory() as raw:
        root=Path(raw)
        for name,value in [('index.html',html),('app.js',js),('styles.css',css),('sw.js',sw)]: (root/name).write_text(value,encoding='utf-8')
        editor.patch_root(root)
        first={name:(root/name).read_text(encoding='utf-8') for name in ('index.html','app.js','styles.css','sw.js')}
        assert editor.MARKER_HTML in first['index.html']
        assert editor.MARKER_JS in first['app.js']
        assert editor.MARKER_CSS in first['styles.css']
        assert 'weekEditorForm' in first['index.html']
        assert "weekEnqueue('create'" in first['app.js']
        assert 'dvizh-week-editor-v1' in first['sw.js']
        editor.patch_root(root)
        second={name:(root/name).read_text(encoding='utf-8') for name in first}
        assert first == second
