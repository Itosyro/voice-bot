# Daily-use client resilience — source candidate, not deployed

Scope: the existing DVIZH planner only. No changes to main, the friend's files,
Foundation candidate, gates, sudoers, authorization, services or production data.
The historical Health Recovery snapshots and their builder/tests are unchanged.

## What this candidate fixes

- Reuse the filtered AI session draft on pagehide/hidden/reload and AI/Manual
  navigation. The existing ten-minute sessionStorage lifetime is unchanged.
- Do not treat HTTP 200 or a bare `{ok:true}` as proof of a state save. Check
  the exact echoed state and CAS revision. Keep unconfirmed text/tasks local.
- Retain an ordinary draft when the preflight GET failed. Do not automatically
  replay an ambiguous, already-dispatched AI write or unconfirmed voice text.
- Bound a stalled sync request, including its response body, to 15 seconds.
- Do not advance the in-memory sync ancestor before metadata persistence.
  Roll back a partial local state/receipt pair; stop uploads if recovery storage
  also fails instead of treating remote data as deletions or local edits.
- Preserve form ancestors throughout a native submit event. A microtask cleanup
  previously ran between capture and target listeners in Chromium and erased
  the ancestor before task save, overwriting a concurrent microstep edit.
- Update only relevant immutable asset/navigation keys. No redesign or new schema.

## Build contract

From a checkout of this branch at a verified immutable commit:

```sh
python3 minimal-ui-v1/health-recovery-v1/build_daily.py --output /tmp/dvizh-daily-new-output
```

The output path must not exist. The builder reads exact Git-blob-pinned inputs
from `dist/` and creates only `app.js`, `ai-home-v2.js`, `sync.js`, `index.html`,
`manual.html` and `BUILD.json` there. It has no network or installation operation.
Do not run it on `/opt` or copy an old `dist/` over production: historical dist
is intentionally unchanged, whereas this candidate is built separately.

## Evidence and checks

Run the existing `tests/run.sh` through the existing Health CI. New unittest
modules are discovered normally; no workflow change is required. They build
all five candidate files, assert exact hashes, run eight native browser/HTTP
flows, and reuse the four unchanged Health browser flows on an isolated copy
with the candidate clients. Original preservation checks still run separately.

Historical native run 34783098169: six of eight passed; two test selectors chose
hidden/duplicate controls. The selectors were scoped without weakening checks.
Run 34783268374: seven of eight passed; the remaining real concurrent task-edit
failure reproduced the native submit cleanup defect. Run 34783567857 on
9970fd976cc79276b04e21457e59abaaeca3de24 passed all eight daily browser flows,
51 unittest executions, six Node tests and four historical Health browser flows.
The additional candidate-Health matrix in this commit must be verified by its
own CI run; do not infer success from the earlier run.

## Deployment remains a separate approval boundary

`preflight_daily.py` only reports static/backend fingerprints, static HTTP byte
comparisons, existing component version literals, three service active states
and a read-only health request. It reads no application state, credentials or
private keys, executes no gates and performs no installation or service changes.
Its compatibility result is not a release approval or pending-journal check.

Before production: obtain live fingerprints, confirm the actual installed
release contract and pending transaction status, create a legitimate proposal
for these exact five payloads with the required owner approval, preserve backups
and then verify HTTP bytes and native-device behavior. Do not fabricate a
managed job, clear a pending journal, bypass a gate, update the Foundation
candidate, or use a legacy installer to work around a refusal.

Not claimed: production installation, actual Android microphone/recognition,
live Hermes semantics, offline first load, indefinite draft retention after
closing a browser, or an error-free final product. The read-only bridge result
provided by the owner before this work does not verify these new client changes.
