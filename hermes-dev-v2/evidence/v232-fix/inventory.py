"""Read-only candidate inventory; no candidate imports, writes or approval."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def literal(relative, name):
    tree = ast.parse((ROOT/relative).read_bytes())
    return next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in node.targets))


def identity(relative):
    data = (ROOT/relative).read_bytes()
    blob = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    actual = subprocess.check_output(['git', 'hash-object', '--no-filters', relative], cwd=ROOT, text=True).strip()
    assert blob == actual
    return dict(git_blob=blob, sha256=hashlib.sha256(data).hexdigest())


pins = literal('hermes-dev-v2/dvizhgitpush.py', 'PIN_PATHS')
assert pins == literal('hermes-dev-v2/dvizhrelease.py', 'PIN_PATHS')
names = set(literal('hermes-dev-v2/owner_install.py', 'TARGETS').values()) | {'owner_install.py'}
digest = hashlib.sha256()
for name in sorted(names):
    digest.update(name.encode()+b'\0'+hashlib.sha256((ROOT/'hermes-dev-v2'/name).read_bytes()).digest())
paths = pins | {'hermes-dev-v2/'+name for name in names} | {
    'hermes-dev-v2/bootstrap_v232.py', 'hermes-dev-v2/BOOTSTRAP-v232.md',
    'hermes-dev-v2/OWNER-HANDOFF.md', 'tests/hermes_autopilot/test_v232_blockers.py'}
print(json.dumps(dict(status='PENDING_INDEPENDENT_REVIEW_DO_NOT_INSTALL',
    rework_base='afd44df10909f365b39216e7676498d48c59870a',
    owner_approval_issued=False, approved_replacement_base=None,
    protected_git_blob_inventory={p:identity(p)['git_blob'] for p in sorted(pins)},
    candidate_files={p:identity(p) for p in sorted(paths)},
    payload_names=sorted(names), payload_sha256=digest.hexdigest()), indent=2, sort_keys=True))
