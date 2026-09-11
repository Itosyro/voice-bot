# v2.3.2 external bootstrap authentication contract

Local implementation, awaiting independent review and owner authentication. No
release digest in this repository constitutes approval. Do not execute an
unauthenticated candidate installer to learn its digest.

The owner must receive through an authenticated channel independent of the
candidate repository: (1) the launcher text below, (2) SHA256 of reviewed
bootstrap_v232.py, (3) SHA256 of reviewed owner_install.py, (4) the complete
payload digest, and (5) the approved owner-approval.json content. The installed
OS /usr/bin/python3 and its standard library are trust anchors. This contract
cannot authenticate that OS or the external owner channel itself.

The independent reviewer computes the payload digest from sorted filenames:
for each installer TARGETS source plus owner_install.py, concatenate UTF-8 name,
NUL, and binary SHA256 of the bytes, then SHA256 the concatenation. Read-only
review may compute this without importing any candidate code.

The owner copies the reviewed payload into root-owned staging whose entire
ancestor chain is root-owned and not group/world writable. Supply paths and
externally authenticated digests as arguments to this independently reviewed
launcher, using `/usr/bin/python3 -I -S -c '<launcher text>' ...`. The launcher
buffers the bootstrap once, checks the external digest, and executes that same
buffer. Hashing a pathname and later executing the pathname is forbidden.

```python
import hashlib, os, re, stat, sys
path, expected, payload, installer_digest, payload_digest = sys.argv[1:6]
assert sys.flags.isolated and sys.flags.no_site
assert re.fullmatch('[0-9a-f]{64}', expected)
fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
with os.fdopen(fd, 'rb') as stream:
    metadata = os.fstat(stream.fileno())
    assert stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1
    data = stream.read(5_000_001)
assert len(data) <= 5_000_000
assert hashlib.sha256(data).hexdigest() == expected
scope = {'__name__': 'authenticated_bootstrap'}
exec(compile(data, '<authenticated bootstrap>', 'exec', dont_inherit=True), scope)
print(scope['bootstrap'](payload, installer_digest, payload_digest, apply=False))
```

This is a preparation launcher, not an installation authorization. A later
owner-authorized installation uses the same independently reviewed launcher
with apply=True. Neither command has been run against production in this task.
Payload replacement after buffering either causes digest rejection or installs
exactly the approved bytes. There are no adjacent candidate imports. Python
isolated mode disables PYTHONPATH, user site and current-directory imports;
-S also suppresses site processing.

The owner approval manifest belongs at the fixed root-owned path
`/var/lib/dvizh-release-gate/owner-approval.json` (regular single-link file,
root:root, no group/world write, with trusted ancestors). Its exact shape is:
`{"schema":1,"version":"2.3.2","base":"<independent immutable commit>","pins":{...}}`.
Pins are Git blob IDs for all five PIN_PATHS listed in each gate. The independent
base must contain those exact approved blobs. The manifest lives outside Git;
neither the workflow nor validator embeds its own digest. Gate authorization
checks the external manifest, not an inventory shipped by the candidate.

No approved v2.3.2 base commit or authenticated digest has been supplied yet.
Creating that owner-reviewed base and installing its approval manifest are
external rollout prerequisites, not work authorized in this local task.

## L1/L2 rework inventory (pending independent review)

The uncommitted rework from `afd44df10909f365b39216e7676498d48c59870a`
is identified in `evidence/v232-fix/INVENTORY.json`. It contains exact computed
Git blob IDs for all five protected paths, bootstrap and installer SHA256, and
the complete sorted-name payload digest described above. Recompute with
`python3 hermes-dev-v2/evidence/v232-fix/inventory.py`; the computation reads
candidate bytes without importing or executing the installer or gates.

These values are an unauthenticated review inventory, never an owner manifest.
The workflow and both gate blobs changed for L1/L2, so prior blob inventories
and prior payload digests cannot identify this candidate. Independent review
and external owner authentication remain mandatory. Align the approved base
across both manifests, `DVIZH_OWNER_FOUNDATION_BASE`, and the controller's
managed-job base branch. Neither this document nor successful fixture doctors
supplies that approval. Trusted runtime auto remains OFF; Manual/server require
approval and Jump remains DENY. No bootstrap/install command was executed.
