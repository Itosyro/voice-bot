# STOP — v2.3.2 L1/L2 rework pending independent review — DO NOT INSTALL

Rework base: `afd44df10909f365b39216e7676498d48c59870a`.
The prior failed verdict in SECURITY-REVIEW-V232.md and
evidence/v232/INDEPENDENT-REVIEW.json is retained unchanged. This candidate has
local L1/L2 fixes only; no new independent verdict or owner approval is issued.
See evidence/v232-fix/REPORT.md for RED/GREEN evidence and verification limits,
and evidence/v232-fix/INVENTORY.json for computed exact Git blob IDs and bootstrap,
installer and payload SHA256 identities. These are candidate inventory, not pins
issued by the owner. No approved immutable replacement base exists yet.

All three exact workflow VERSION assertions now match their actual sources.
Both doctors expose `owner_authorized` from the same `owner_manifest()` contract
used by their production gates; absent or invalid trust makes `ok` false.
Authorization status reads do not provision or modify the manifest. Push
transport `authorized` remains separate; its detail is a fixed status message.
A valid manifest alone does not establish tool/transport/pending-state readiness,
validate a proposed commit, or authorize installation.

The owner must independently approve the final immutable foundation base and
exact five blob pins, then coordinate both gate manifests, the workflow variable
`DVIZH_OWNER_FOUNDATION_BASE`, and the controller managed-job base branch.
The original historical base is not approval for this revised candidate.
Legacy installer smoke is v2.1 coverage, not v2.3.2 installation acceptance.

# OWNER v2.3.2 foundation handoff

Local implementation only; awaiting independent review. No installation approval,
independent PASS verdict, commit, push or bundle is issued here. Prior mandatory
review evidence is unchanged. See DESIGN.md for the implemented trust boundaries
and evidence/v232/REPORT.md for exact verification commands and limits.

The narrowed release contract is schema 1 from base
`da7395e436563774a29f7694b258bd85987bed2f`, retaining the root state fix and Jump DENY.
Only the three existing index/AI Home static targets can be automatic. Existing
privileged/runtime/Manual/server changes require owner approval. Schema 2 and
trusted-runtime auto deployment have been removed. No new mappings or source
materialization were introduced. The owner installer now targets only the three
existing control-plane executables; it does not append to the live skill.

The root gates have functional entry points with fixture overrides rejected.
Guarded push drops to the authenticated invoking UID/GID with empty groups for
caller Git, exports objects, validates a private sanitized repository, then names
the exact commit in the push refspec. Release authorization independently checks
owner-pinned blobs and every commit's protected paths through immutable APIs.

The external trust procedure is in BOOTSTRAP-v232.md. Before any future root
execution, an independent owner/reviewer must authenticate the launcher,
bootstrap SHA256, installer SHA256 and complete payload digest. Root-owned
staging and a trusted isolated system interpreter are required. Candidate hashes
or this implementation's test results are not owner approval.

Remaining rollout prerequisites and unverified limits:

- An independently reviewed immutable v2.3.2 base containing the exact new
  workflow/validator blobs does not yet exist as an approved commit. Committing
  or pushing one was explicitly prohibited in this task. The supplied historical
  base is a restoration source, not authorization for the revised CI blobs.
- The owner must provision the independently authenticated owner-approval.json
  at the fixed root control-state path, and coordinate the protected workflow's
  DVIZH_OWNER_FOUNDATION_BASE variable. The gate rejects absent/unapproved trust
  data. This is an authorization prerequisite, not unconditional root quarantine.
  The current installer does not create that owner authorization on the user's behalf.
- No authenticated external digest/channel, live CI, real root privilege drop,
  deploy-key/known-host authorization, production doctor, installation, service
  restart, actual push or power-loss recovery was exercised. System Python/Git/SSH,
  GitHub HTTPS/API and the existing sudo identity contract remain trust anchors.
  Workflow action dependencies still use their existing major-version references.
- The v2.2 bearer phrase is digest-bound, expiring and one-use; it does not prove
  a later Telegram owner's identity. Owner orchestration remains an assumption.
- Full runtime/feature regression is outside the revised scope. Generic service
  health is not claimed as behavioral proof for approved runtime changes.

Existing interrupted-transaction recovery remains an owner operation: authenticate
the journal/mapping and backup bytes/metadata before restoring originals. Retain
pending state on uncertainty; do not delete it simply to unblock the gate. No live
recovery or rollback procedure was executed here.

All workspace edits are confined to hermes-dev-v2, tests/hermes_autopilot and
protected owner workflows. No production files or installed code were executed
or imported; no keys/secrets/sudoers/unit files, friend source or unrelated jobs
were changed. No live-skill edits, sudo, system installation or --apply invocation
occurred. Disposable fixture installation functions were exercised by tests.
