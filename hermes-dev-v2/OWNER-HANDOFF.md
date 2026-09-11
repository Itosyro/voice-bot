# STOP: v2.3 candidate failed security review — DO NOT INSTALL

See SECURITY-REVIEW-V23.md. This handoff describes an unapproved candidate,
not an installation-ready release. Critical findings override preparation results.

# Owner handoff — v2.3 local review

**Local implementation; not installed, committed, pushed or bundled.**
Five fix rounds used. No further autonomous corrections were made after round 5.
The old 126 tests remain unchanged; final owner-suite result: **148 tests, PASS**.
See `evidence/v23-verification.json` for commands, outcomes and coverage gaps.

## Review and installation contract

Review the diff and source/target table in DESIGN.md first. Business code and
friend-project files are unchanged. The installed gate still identifies itself
as 2.2.1-state-root, and the installed skill equals the captured fixture byte for
byte. The old bootstrap `install-dvizh-hermes-autopilot.sh` is unchanged and still
pins its old release: **do not use it to upgrade to v2.3**.

The new offline owner entry point is `hermes-dev-v2/owner_install.py`. Default
execution only prepares; `--apply` requires root and an independently reviewed
`--expected-payload-sha256`. No execution of that production installer was done.
Do not add the owner installer to sudoers. The ordinary gates must continue to
reject every owner control-plane source and test.

The digest is SHA256 over sorted payload filename + NUL + binary SHA256(content),
for the installer, controller, release gate, push gate and additive policy. An
owner can compute it using `payload_digest(Path('hermes-dev-v2'))` from the
reviewed installer. Verification of that digest must occur through the independent
owner review channel; a digest calculated from an unreviewed tree is not approval.
A future bundle/publish step must pin the reviewed payload and record the digest.

No production provisioning or CI publication is authorized by this handoff.
Before an eventual owner installation, coordinate the schema-2 gate workflow and
managed branch base: the currently installed/published old workflow may reject
schema 2. Review/publish owner guardrail changes through the separate owner path,
never an ordinary Hermes feature push. Preserve the existing shared ancestry base
or explicitly review a new immutable base together with both gates and CI.

## Rollback and interrupted recovery

Automatic rollback covers caught failures: verify backups, restore all files with
original UID/GID/mode, restart mapped old services for application transactions,
and repeat fixed smoke. Owner installer transactions do not restart services.
Pending journal and mapping identify the exact backup set. Never erase a pending
marker merely to unblock the next task. There is deliberately no arbitrary-path
or shell recovery capability in the gate.

For SIGKILL/power loss, a separate owner must inspect the journal kind and mapping,
verify mapping SHA and every backup SHA/metadata, restore every listed original
through a reviewed recovery procedure, verify canonical paths and all bytes, then
restart only recorded mapped services and recheck health. Clear pending only when
restoration is confirmed. Filesystem/power-loss durability and production recovery
are **NOT VERIFIED** here. Preserve the backups for independent review.

## Doctor expectations and open deployment blockers

Release doctor reports version 2.3, production_schema=2, the gate state root,
immutable shared base, exact target policies/service union, and pending=false.
A pending journal makes ok=false. Its ok field is a tool/pending diagnostic,
not proof of target metadata, GitHub CI, or domain functionality: preflight and
apply provide those checks. Controller doctor must separately report guarded-push
authorization and private_git_key_visible_to_hermes=false. Neither live doctor nor
key/auth checks were executed in this maintenance task.

Jump's installed module and service were inspected by nonsecret source/stat:
`/opt/dvizh-jump/dvizh_jump/jump_web_bridge.py`, root:root 0755,
`dvizh-jump.service`, module ExecStart. Its mapped repository source is not yet
materialized: the repository stores the old Jump release as encoded parts.
**Jump release remains blocked** until an ordinary reviewed DVIZH change supplies
the exact mapped source with tests and immutable CI. No feature source was added
to this owner branch. No alternative source or old nonexistent target is accepted.

The exact full approval phrase cannot itself authenticate a Telegram sender.
The installed skill must enforce the later user message and no-self-approval rule;
independent review should assess that orchestration boundary.

Local feature regressions are isolated at health commit
`9d492693de2c7cf66350293afcf42b74edeebaef`. They are not GitHub CI or production
acceptance. Missing/exhaustive acceptance remains **NOT VERIFIED**, particularly
production smoke/restarts, recovery under actual power loss, audible speech on
the owner's device, complete Jump/social/training/facts acceptance, and binding
Manual auto-safe browser CI. Keep Manual/shared frontend approval-required.

## Executed isolated regression results

| Suite at requested health commit | Result |
|---|---|
| Health acceptance | PASS: 41 Python tests, 6 Node tests, 4 real browser scenarios |
| AI Home bridge fixture | PASS: 2 tests |
| Broad AI Home archive contracts | 98 total: 72 passed, 26 failed |

The 26 failures require root installer/diagnostic scripts or historical Git objects
not included in the selected archive. The broad suite is **NOT VERIFIED**. They
were retained as real failures, not changed to skips or “green.” The final harness
correction (Node lookup in its clean PATH) was fix round 5; no more fixes followed.
The passing health browser scenarios cover persistence, legacy routes, no reload,
old/new cache combinations, explicit proposal confirmation and concurrent CAS.
They do not provide every requested Quiet Signal/toggle/Jump acceptance assertion.
