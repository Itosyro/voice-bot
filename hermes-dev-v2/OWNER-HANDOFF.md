# STOP — v2.3.1 independent review FAIL — DO NOT INSTALL

Final status: see SECURITY-REVIEW-V231.md and evidence/v231/INDEPENDENT-REVIEW.json.
The implementation-stage notes below predate the independent review and final
orchestrator verification. They are historical, not the final delivery status.

Do not install this candidate. Base is
`fbbfad02e61882c174660a3ef7db384546d80e6a`; no commit or push was made.
Five internal test-fix cycles are exhausted. No independent review was performed.
See DESIGN.md for unresolved critical/high findings, including runtime confinement,
privilege-separated Git and independently enforced CI pins. These are not waived.

The owner installer is now a standalone bootstrap with buffered digest verification.
Before ANY execution, a future independent owner process must authenticate its
complete bytes and dependencies from a separately trusted channel. Verify the
composite payload digest as sorted filename + NUL + binary SHA256(content), then
SHA256 of the concatenation. Inputs: owner_install.py, dvizhautopilot.py,
dvizhrelease.py, dvizhgitpush.py, TRUSTED-MODE-v2.3.md. Never use candidate imports
to establish bootstrap trust. No approved bootstrap SHA or installation command
is issued in this handoff. The old shell installer still pins its older version;
it is not a v2.3.1 upgrade route.

The live local skill was not accessed or edited by this task. Only the additive
policy in this repository changed. No production files were imported, installed
or intentionally read for tests. This statement describes actions performed;
there was no live-file hash audit, and no universal untouched assertion is made.
All test execution was in disposable copies under OS namespace containment.
No keys, secrets, sudoers, systemd configuration or ownership were changed.
No friend source files or unrelated jobs were changed in the workspace.

## Rollback and doctor

Installer fixture rollback verifies all backups before writes and restores all
original bytes/UID/GID/modes on caught failure, retaining pending on uncertainty.
It does not restart services. For interrupted recovery, an independent owner must
verify journal kind, mapping SHA, backup identities and metadata before restoring
all listed originals. Never delete a pending marker just to unblock work. No live
rollback or power-loss recovery was attempted.

Candidate root doctor currently fails closed with “v2.3.1 hardening incomplete”.
It must not be interpreted as deployable. Unprivileged fixture doctor still tests
policy and pending-state reporting. No live doctor or key authorization was run.
Only after implementation and independent review may production doctor semantics,
protected CI rollout/base coordination and immutable bootstrap pins be finalized.

The root control state contract is `/var/lib/dvizh-release-gate` only.
`/var/lib/dvizh` ownership must remain unchanged. Restart map is in DESIGN.md.

## Test evidence

Actual commands, exit statuses, cycle ledger and remaining dependency blockers are
in evidence/v231/REPORT.md. Owner suite: 154 PASS. Health: 41 Python and 6 Node
PASS, browser blocked by absent Playwright. AI Home: 99/100 PASS, routing probe
fails because awk's alternatives target is not present inside isolation. Full
repository pytest cannot start: pytest is absent. Tests were not weakened or
friend files changed to obtain green. Audible/device and exhaustive feature
acceptance remain unverified.
