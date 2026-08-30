import importlib.util
import py_compile
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).parents[2]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec); sys.modules[name]=mod; spec.loader.exec_module(mod); return mod


def test_week_projection_preserves_unprocessed_web_commands():
    patch=load('preserve_patch', ROOT/'web-week-editor-v1'/'patch_week_bridge_for_editor.py')
    source=(ROOT/'web-week-v1'/'weekly_web_bridge.py').read_text(encoding='utf-8')
    updated=patch.patch_text(source)
    assert patch.MARKER in updated
    assert patch.patch_text(updated) == updated
    with tempfile.TemporaryDirectory() as raw:
        path=Path(raw)/'bridge.py'; path.write_text(updated,encoding='utf-8'); py_compile.compile(str(path),doraise=True)
        bridge=load('patched_week_bridge',path)
        state={'weeklySchedule':{'version':1,'timezone':'UTC','rangeStart':'2026-08-29','rangeEnd':'2026-09-04','items':[],'occurrences':[], 'webCommands':[{'id':'c1','action':'create'}], 'webUpdatedAt':'now'}}
        projection={'version':1,'timezone':'UTC','rangeStart':'2026-08-29','rangeEnd':'2026-09-04','items':[{'id':'x'}],'occurrences':[]}
        merged,changed=bridge.merge_schedule(state,projection)
        assert changed is True
        assert merged['weeklySchedule']['webCommands'][0]['id']=='c1'
        assert merged['weeklySchedule']['webUpdatedAt']=='now'
