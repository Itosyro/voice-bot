# v2.2 local implementation and test report

Implemented in `/home/exedev/.hermes/dev/dvizh/owner-maintenance-v2.2` only.
No access to feature job `20260909-115201-e37585`; no repository commit, push, deploy, sudo,
installer execution, production mutation, secrets or user database reads.

## Result

- Exact three privileged runtime targets with fixed source mapping, root:root 0755,
  strict fields, SHA256 and fixed Python syntax/service verification enums.
- Approval always required in auto; exact full APPROVE phrase, digest binding,
  single use and 1800-second TTL. Independent immutable Git blob/source validation
  and exact-commit green CI checks inside the gate, repeated before apply.
- Canonical paths, no-follow reads/writes, symlink-parent and nonregular-file
  rejection; extra/duplicate fields and mixed extra files rejected.
- All backups, SHA/UID/GID/mode mapping and original destinations verified before
  destination writes. Atomic replace and metadata/hash verification; all-file
  rollback, declared-service retry, health recheck and critical unconfirmed failure.
- Only the approval bridge may restart in this class, only with bridge bytes and
  explicit justification. Helpers are per-call. Installer UI patcher excluded.
- Existing push gate, controller, installer and installer-smoke workflow unchanged.
  The generic CI manifest check now uses the same strict validator. The v2 test
  workflow version check identifies the new local gate. Self-protection remains.
- Owner contract and skill distinguish local owner delivery from managed releases.

## Read-only baseline

Installed `/usr/local/sbin/dvizhrelease` was byte-identical to the initial repo gate
(`diff -u` exited 0). See `baseline-sha.txt`, `baseline-stat.txt`,
`baseline-service.txt`, and `baseline-imports.txt`.

All requested installed targets: regular, UID 0, GID 0, mode 755. Service unit:
long-running `/usr/bin/python3 /opt/dvizh-ai-approval/proposal_bridge.py`,
User/Group dvizh. Import statements are standard library only. Read-only inspection
of `install-dvizh-ai-approval.sh` confirms the UI patcher runs during installation;
`hermes-control-v1/dvizhctl` invokes both helpers per call.

Baseline commands and results:

```text
python3 -m unittest discover -s tests/hermes_autopilot -p test_release_gate.py -v
6 passed (baseline-release.txt)
python3 -m unittest discover -s tests/hermes_autopilot -p test_controller.py -v
5 passed (baseline-controller.txt)
```

## Original implementation RED/GREEN evidence

Each slice added tests, ran them RED before its implementation, then ran GREEN.
The command for each numbered pair was:

```text
python3 -m unittest discover -s tests/hermes_autopilot -p test_release_v22.py -v
```

| Slice | RED | GREEN | Evidence pair |
|---|---:|---:|---|
| Exact contract | 4 errors | 4 passed | `01-contract-{red,green}.txt` |
| Trusted sources / CI / approval | 5 failures | 13 passed | `02-trust-{red,green}.txt` |
| Backup / atomic apply / rollback | 4 failures, 2 errors | 28 passed | `03-transaction-{red,green}.txt` |
| Malformed inputs / metadata / root fixture denial | 4 failures | 45 passed | `04-hardening-{red,green}.txt` |
| CI contract / extra fields / restart boundary | 3 failures | 59 passed | `05-boundary-{red,green}.txt` |

The counts include inherited contract tests rerun in each fixture class. Additional
coverage runs three-file apply with real temp files and a real loopback HTTP server;
restart, GitHub and failure injection use mocks. No production code is executed by
syntax verification, and no real systemd restart runs in fixtures.

Original implementation commands and actual results (superseded by the review run below):

```text
python3 -m unittest discover -s tests/hermes_autopilot -p 'test_release*.py' -v
76 passed, exit 0 (final-release.txt)
python3 -m unittest discover -s tests/hermes_autopilot -p test_controller.py -v
5 passed, exit 0 (final-controller.txt)
python3 -m py_compile hermes-dev-v2/dvizhautopilot.py hermes-dev-v2/dvizhrelease.py hermes-dev-v2/dvizhgitpush.py tests/hermes_autopilot/test_release_v22.py
exit 0
python3 hermes-dev-v2/evidence/v2.2/check-static.py
3 existing non-installer workflow static sections passed, exit 0 (final-static.txt)
git diff --check
exit 0 (final-boundary.txt)
```

Installed gate and all three target SHA256 values were re-read and confirmed
unchanged. Repo push gate/controller/installer/installer-smoke bytes were compared
with `git show HEAD:<path>` and confirmed unchanged (`final-boundary.txt`).
The no-commit push-policy test checks all requested control-plane and friend-path
denials plus the three permitted source paths without making Git commits.

## Remaining blockers / exclusions

1. Separate owner delivery is required. The standard gate denies self-installation;
   the unchanged installer still pins v2.1. No owner install is claimed or attempted.
2. The authenticated Telegram boundary must establish a later message from the
   owner. The CLI enforces the exact phrase and challenge but cannot independently
   prove authorship or chronology from a string. This must be verified in owner
   delivery before enabling privileged production use.
3. No real GitHub CI run was created or claimed green under the no-push constraint.
   CI rejection/success paths used controlled API fixtures. Production root-owned
   metadata and real service/health behavior need owner delivery validation; local
   fixtures substitute the current unprivileged UID/GID for root ownership.
4. The original pass excluded `test_git_push_gate.py` because it creates temporary
   Git commits. The independent review explicitly authorized fixture commits, and
   the full suite now includes these tests (see below). Installer execution/smoke
   stages remain excluded; only existing static non-installer guards were run.


## Independent v2.2 review fixes — 2026-09-09

Scope: owner-local release gate, regression tests, this evidence, and the owner
contract. Pre-existing workflow and skill edits were left as found. No production
commands, sudo, root shell, installer execution, self-deploy, repository commit or
push. Friend/feature code was not changed. Git commits made by the full unittest
suite exist only in its temporary Git fixtures, as explicitly authorized.

Implemented findings:

1. A root-owned regular mode-0600 flock in the existing approval directory spans
   the entire plan or apply, including challenge creation/claim, rollback,
   restart/health and final verification. Nested entry points share the held lock.
   Consumption validates and durably unlinks a challenge under that lock. A real
   two-process regression reproduces two successful claims on RED and exactly
   one claim on GREEN. A concurrent plan and second apply wait for the first
   transaction to finish.
2. `BaseException` rollback handles KeyboardInterrupt; CLI SIGINT/SIGTERM/SIGHUP
   use the same path, with subsequent catchable signals ignored during rollback.
   A fsynced fixed `pending.json` references the durable mapping before writes.
   Pending or malformed markers block all new plan/apply work. Confirmed final or
   rollback verification clears the journal durably; critical rollback retains it.
   Real forked processes exercise SIGTERM restoration and SIGKILL detection.
3. Root-owned, non-group/world-writable privileged ancestors are mandatory.
   No-follow parent descriptors are pinned through the transaction. Canonical
   identity is checked before writes and at final verification. Rollback preserves
   the pinned object if its parent is renamed and reports CRITICAL instead of
   trusting old-looking bytes at a replacement canonical path. Mapping records
   parent device/inode IDs. Fixture ancestors now explicitly use mode 0755;
   writable-parent tests are rejected under the existing TEST_MODE as well.
4. Both initial and final source validation use `compile(..., "exec",
   dont_inherit=True)` without execution. Module-level `return` is rejected;
   a valid candidate containing a top-level sentinel write never executes.
5. Existing AI Home prefix operations safely create missing parents through
   no-follow descriptors. Previously absent files are removed on rollback, and
   absence before the first write is a confirmed rollback. Empty newly created
   directories may remain. Symlink parents are still denied.

All final/rollback file SHA256, UID, GID, mode and parent identities (or absence)
are rechecked AFTER service restarts and HTTP/health checks. Regressions inject
post-health bytes/mode drift and post-rollback restart byte drift. Existing
1800-second TTL, exact class/targets, immutable regular source, independent CI,
self-protection and restart constraints remain covered by the full suite.

### Actual RED/GREEN evidence

| Run | Actual result | Evidence |
|---|---|---|
| Initial review regressions against the pre-fix worktree | 30 tests; 11 failures, 1 error | `06-review-red.txt` |
| Corrected v2.1 token fixture, focused parent-creation reversion | 4 tests; 2 failures, 1 error, exit 1 | `06-parent-red.txt` |
| Final expanded review regressions | 36 tests passed, exit 0 | `06-review-green.txt` |
| Full requested discovery, including temporary Git fixture commits | 123 tests passed, exit 0 | `07-full-green.txt` |
| Existing non-installer workflow static checks | All 3 sections passed, exit 0 | `07-review-static.txt` |

The initial RED run's two new-path tests used the privileged full phrase for a
v2.1 bare-token operation and therefore failed at approval validation; those two
results are NOT evidence of the parent-creation defect. After correcting that
fixture, the focused RED run temporarily disabled descriptor parent creation
(and omitted missing-parent pins), reproduced apply/rollback missing-parent
failures, and restored the implementation in `finally`. That run is explicitly a
controlled reversion, not a claim of a second pristine pre-fix baseline. The
initial RED accurately reproduces the other findings, including the two-claim
race, KeyboardInterrupt escape, SIGTERM termination, missing SIGKILL marker,
false rollback confirmation after rename, accepted module-level return, writable
ancestors, and missed post-health/rollback metadata drift.

Commands:

```text
python3 -m unittest discover -s tests/hermes_autopilot -p test_release_v22_review.py -v
python3 -m unittest discover -s tests/hermes_autopilot -p test_release_v22_review.py -k ai_home -k absent_target -v
python3 -m unittest discover -s tests/hermes_autopilot -v
python3 hermes-dev-v2/evidence/v2.2/check-static.py
python3 -m py_compile hermes-dev-v2/dvizhrelease.py tests/hermes_autopilot/test_release_v22.py tests/hermes_autopilot/test_release_v22_review.py
git diff --check
```

Counts include inherited/imported fixture tests; the new file defines 18 review
regressions. Compilation and diff checks exited 0. All writes and signals in
regressions target temporary fixture files/processes, with systemd and GitHub
mocked. No production service or installed payload was exercised in this pass.

### Recovery limitation

SIGKILL and power loss cannot invoke rollback. Partial new bytes can persist;
the next invocation fails closed on the pending marker. No automatic crash
recovery or arbitrary recovery CLI/path was added. Separate owner recovery must
verify backup SHA/metadata, target parent identity, restored bytes/metadata and
post-restart health before clearing the fixed marker. Descriptors do not survive
process death. Filesystem fsync durability is required. A kill after successful
verification but before marker removal can conservatively block a completed
release. The owner contract documents these limits; this local change remains
uninstalled and does not repair or clear any production state.

## Second and final autonomous review cycle — 2026-09-09

Only the three requested issues were changed in this cycle: the release gate,
three regression methods in the existing review test file, and local evidence.
All work stayed in the owner maintenance worktree. No production access, sudo,
installer, repository commit or push, or friend/feature worktree access occurred.
The full maintenance suite uses temporary Git fixture commits, as in the prior run.

1. Approval challenges now live under `APPROVAL_ROOT/challenges/`; the fixed
   transaction lock and pending journal retain their existing control paths.
   Reserved control IDs are rejected both during proposal validation and direct
   challenge access. IDs must match the complete allowed string (1–160 ASCII
   letters/digits/underscore/dot/hyphen); there is no sanitization, truncation or
   fallback identity. Immutable Git SHA/blob, branch and source validation remain
   intact. Existing challenges in the former namespace require a fresh plan;
   existing pending markers remain blocking and are never migrated or deleted.
2. The installed termination handler consults mutable `rolling_back` on every
   call and sets it before raising on first termination. Rollback setup sets the
   same flag before changing handlers and retains it through restoration and
   result construction. A forked regression sends two actual SIGTERMs, with the
   second delivered synchronously before the first rollback handler replacement.
   It verifies both confirmed restoration and CRITICAL unconfirmed restoration
   with a retained blocking marker when restoration writes fail.
3. Apply and rollback share guarded durable journal cleanup. Unlink/fsync failure
   attempts to restore the original journal and raises a structured CRITICAL
   GateError. Apply still restores files but retains the failure and marker;
   rollback cleanup cannot escape as a raw OSError or claim confirmed completion.
   The regression injects a real post-unlink directory-fsync exception on each
   path and verifies restored files, a re-armed pending journal, and rejection of
   subsequent plan and apply calls. If storage also refuses journal re-arming,
   the CRITICAL error explicitly reports that failure; physical durability cannot
   be guaranteed on failed storage.

Actual commands and results:

```text
python3 -m unittest discover -s tests/hermes_autopilot -p test_release_v22_review.py -k test_final -v
RED before implementation: 3 tests, 7 failures, 2 errors (exit 1)
  08-final-review-red.txt
GREEN after implementation: 3 tests passed (exit 0)
  08-final-review-green.txt
python3 -m unittest discover -s tests/hermes_autopilot -v
126 tests passed in 6.025s (exit 0), 09-final-full.txt
python3 hermes-dev-v2/evidence/v2.2/check-static.py
All 3 static sections passed (exit 0), 09-final-static.txt
python3 -m py_compile hermes-dev-v2/dvizhrelease.py tests/hermes_autopilot/test_release_v22_review.py
exit 0
git diff --check
exit 0
```

RED subtests share each method's fixture: after the reserved `pending` ID creates
its marker, remaining reserved-ID attempts encounter that lockout; after the
first two-signal case escapes restoration, its second case encounters the pending
marker. Those follow-on failures are not independent defect reproductions. The
first cases directly demonstrate both defects; GREEN exercises all cases. The
rollback fsync RED case directly demonstrates the raw OSError, while the apply
case demonstrates an incorrectly cleared marker/noncritical result.
Counts in full discovery include inherited/imported fixture tests. No broader
application or installer suite is claimed; full discovery here is the complete
`tests/hermes_autopilot` maintenance suite, preserving the prior review scope.
