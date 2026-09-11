
<!-- DVIZH TRUSTED MODE v2.3 -->
## Trusted DVIZH Mode v2.3 — explicit policy precedence

This appended section supersedes earlier three-cycle limits, token-only apply
instructions, and the old production class list. All other local instructions,
including Manual, Quiet Signal, sync, anti-reload and owner handoff, remain binding.

Default to five autonomous fix cycles for an authorized task, including local,
CI and deployment corrections. Ordinary retries within this budget do not need
repeated permission. Stop after five unsuccessful cycles with actual evidence
and blockers. A pending journal or unconfirmed rollback stops the loop immediately.

Use managed worktree → local tests → diff review → commit → guarded push → exact
commit CI → immutable schema-2 manifest → root gate preflight → verified backups
→ durable journal → atomic apply → fixed smoke → full rollback on failure.
Do not merge, force push, touch friend paths or modify these control-plane sources
from an autonomous job. Never read credentials or use an unrestricted root shell.

The gate's exact TARGET_POLICY controls source, target, root:root owner/group,
mode, verification enum, and service. No prefix, wildcard, arbitrary source,
extra operation, or manifest command is allowed. The original index/AI Home JS/CSS
are auto-safe. Only the five mapped context/proposals/approval bridge/AI Home
bridge/Jump bridge entries are trusted-runtime. Manual/shared frontend remains
approval-required until binding deterministic browser regressions cover routes,
unsaved state, no reload, Quiet Signal and toggle behavior. server.py remains
approval-required; sensitive or unknown backend is denied.

Auto mode may apply a mixed batch without prompting only when every operation
is auto-safe or trusted-runtime. Safe mode always needs explicit approval.
Restart services must equal the union derived from changed targets. All immutable
blobs, SHA256, CI, target metadata and backups must verify before destination
writes. Missing source materialization or smoke capability is a blocker.

When approval_required is true, wait for a later user message containing the
exact full `APPROVE <proposal-id> <token>` phrase; pass that full phrase as the
single --approval argument. Bare tokens are invalid. Approval is one-time,
digest-bound and expires in 1800 seconds. Seeing the challenge is never approval;
never self-approve. Replanning a challenge does not grant consent.

Report real local test counts, CI identity, gate outcome and rollback status.
Mark unavailable/exhaustive acceptance NOT VERIFIED. A fixture browser passing
is not production deployment or proof of audible playback on the owner's device.
Owner control-plane maintenance requires independent review and a separate
owner installation; do not install, commit, push or bundle without authorization.
