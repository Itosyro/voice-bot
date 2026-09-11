# OWNER MAINTENANCE v2.3.1 — incomplete, pending independent review

Base: `fbbfad02e61882c174660a3ef7db384546d80e6a`.
Local changes only. Five internal test-fix cycles exhausted; DO NOT INSTALL.
This document supersedes the v2.3 design. SECURITY-REVIEW-V23.md remains the
original independent review; this task is not an independent review.

## Implemented and tested

The release health probe no longer executes the deployed context helper. It
checks fixed service status/PID and HTTP health only. These are availability
checks, not binding proof of candidate component behavior. Root entry points
in both gates now reject production execution because required boundaries are
incomplete. This quarantine is a blocker, not a substitute for implementing them.

The offline owner installer no longer imports adjacent release code. Its
filesystem/transaction primitives are standalone source within owner_install.py.
It reads payloads into byte buffers, verifies their composite digest, and uses
those exact buffers for installation. Root staging must have root-owned,
non-writable ancestors/files. Candidate bytes are syntax-compiled, never imported.
The bootstrap itself must be independently trusted BEFORE execution: self-hashing
or a digest supplied by the candidate cannot establish that trust. Only stdlib
imports are used. Fixture tests cover payload reread races and rollback; this is
not proof of power-loss behavior or every possible staging race.

The regression harness uses temporary complete Git clones, with unchanged
candidate/test bytes inside mount, PID, network and user namespaces. It exposes
system runtime directories read-only, a copied Node executable, and the disposable
clone; host /home, /etc, /usr/local, application state and sockets are absent.
No Python rewriting/audit hook is used. Probes test host sentinel invisibility,
child-shell invisibility, network rejection, zero capabilities and no_new_privs.
Inherited supplementary IDs are unmapped except invoking GID; this local harness
is NOT the required production privilege-drop boundary with stripped groups.
Full history includes health commit `9d492693de2c7cf66350293afcf42b74edeebaef`.

## Exact proposed policy

| Target | Source | Class | Mode | Restart |
|---|---|---|---|---|
| /opt/dvizh/static/index.html | ai-home-v2/index.html | auto-safe | 0644 | none |
| /opt/dvizh/static/ai-home-v2.js | ai-home-v2/ai-home-v2.js | auto-safe | 0644 | none |
| /opt/dvizh/static/ai-home-v2.css | ai-home-v2/ai-home-v2.css | auto-safe | 0644 | none |
| /usr/local/libexec/dvizh-context | hermes-control-v1/dvizh_context.py | trusted-runtime | 0755 | none |
| /usr/local/libexec/dvizh-proposals | hermes-control-v1/dvizh_proposals.py | trusted-runtime | 0755 | none |
| /opt/dvizh-ai-approval/proposal_bridge.py | hermes-control-v1/dvizh_proposal_bridge.py | trusted-runtime | 0755 | dvizh-ai-approval.service |
| /opt/dvizh-ai-home/ai_home_bridge.py | ai-home-v2/ai_home_bridge.py | trusted-runtime | 0755 | dvizh-ai-home.service |
| /opt/dvizh/server.py | minimal-ui-v1/health-recovery-v1/baseline/helpers/server.py | approval-required | 0755 | dvizh.service |

`manual.html`, `app.js`, `sync.js`, `styles.css`, `sw.js` each map from the
same basename in `minimal-ui-v1/health-recovery-v1/dist/` to
`/opt/dvizh/static/`, approval-required, 0644, no restart. All owners root:root.
Schema-2 restarts must equal the target-derived union. Jump is denied in both
schemas; its service is removed from the legacy restart allowlist. Schema-1
behavior remains historical unprivileged fixtures only, including other legacy
allowlist differences. No production schema-1 authorization is intended.

## Unresolved critical/high requirements — no waiver

1. Component-specific behavioral checks bound to candidate bytes in an explicitly
   unprivileged fixed sandbox with stripped environment/groups, no_new_privs and
   confinement (or a fixed trusted service API) are NOT implemented. Running as
   dvizh alone is insufficient: that account can reach secrets, friend data and
   control-plane surfaces. Exact paths and hashes do not confine execution.
2. Privilege-separated caller repository export and root-owned sanitized immutable
   Git object boundary are NOT implemented. Legacy push code still contains
   caller-repository Git and inherited environment/config surfaces. Root entry
   rejection prevents using that path; do not remove it as a readiness switch.
   Malicious Git config/hook/include/ssh/credential fixtures remain required.
3. Owner-approved workflow/validator blob pins and per-commit protected-path
   history enforcement independent of CI are NOT implemented. CI remains unsafe
   for authorization. `CI-PINS-v231.json` records observed bytes, not approved pins.
4. Bootstrap independent approval, immutable staging concurrency tests, live
   recovery and actual owner installation remain unverified. The bootstrap shares
   extracted primitive logic and needs independent scrutiny.
5. The v2.2 later-message orchestration rule remains an explicitly accepted trust
   limitation. Bearer approval does not prove Telegram identity or message origin.

## Transaction contract retained

All payloads and metadata validate before backup preparation; all backups and
mapping verify before the first destination write. Durable pending journal,
exclusive lock and pinned parent descriptors cover the mixed static/runtime
transaction. Caught failures restore every target and mapped old service; failed
restoration retains the journal. Interrupted journals block subsequent operations.
Control state remains only `/var/lib/dvizh-release-gate`; no `/var/lib/dvizh`
ownership change. Production correctness cannot be inferred from fixture tests.

See OWNER-HANDOFF.md and evidence/v231/REPORT.md for actual results and blockers.
