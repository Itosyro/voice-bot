# OWNER v2.3.2 foundation — local implementation awaiting independent review

This supersedes the v2.3/v2.3.1 runtime-auto design. Mandatory prior findings are
retained in SECURITY-REVIEW-V231.md and evidence/v231/INDEPENDENT-REVIEW.json.
This document is implementation evidence, not an independent security verdict.

## Restored release contract

The release implementation was restored from local Git base
`da7395e436563774a29f7694b258bd85987bed2f`, then given the root state fix,
Jump denial, read-only preflight and the foundation trust checks. Schema 1 is
again the production contract. Schema 2 is rejected by controller and gate.
There is no trusted-runtime automatic deployment, new release mapping, source
materialization, capability, restart permission or live-skill append.

Only existing index.html, ai-home-v2.js and ai-home-v2.css targets can be automatic
in auto mode with no restarts. Safe mode requires approval. Existing Manual/shared
frontend, server and /opt/dvizh-ai-home/ targets retain approval requirements.
The three exact privileged integration targets retain the v2.2 source/hash/mode
contract and full approval phrase. Privileged and ordinary files cannot be mixed
in one manifest. Jump targets and dvizh-jump.service remain denied. The existing
runtime prefix has deliberately not been expanded into new exact mappings.

Existing v2.2 transaction locking, pending journal, byte/metadata backup,
rollback, signal handling and bearer-approval limitations remain. The state root
is `/var/lib/dvizh-release-gate`; /var/lib/dvizh ownership is not changed.
Health uses fixed service/HTTP checks and never executes candidate context code.
Those checks do not prove runtime behavior; runtime changes require owner approval.

## Caller Git and immutable object boundary

Every Git command addressing the caller worktree is launched under sudo's
numeric invoking UID and primary GID, cross-checked against passwd and SUDO_USER.
Supplementary groups are emptied. The environment is constructed explicitly;
Git global/system config, replacement objects, hooks, fsmonitor, credential
helpers, external diff and executable transport overrides are disabled where
applicable. Caller repository config/includes remain untrusted and are parsed
only after the privilege drop. Git never runs as root in that worktree.

The exporter asks caller Git for the captured 40-hex commit's reachable pack.
Only pack bytes enter a private root-owned temporary bare repository, initialized
without templates. No caller config, hooks, refs, alternates, shallow metadata,
worktree files or Git environment are copied. Export has a 100 MB file-size limit
and timeouts. Root index-pack validates objects with --strict. Root rechecks
ancestry, every commit's paths, and approved base/head pins in this fresh repo.
The SSH push refspec names the exact validated SHA, never HEAD. Ref/config changes
after capture cannot alter the bytes authorized for push. No actual push was run.

The existing deploy-key location is retained. The SSH command uses the fixed
system SSH binary, no SSH config, explicit key, identities-only and strict known
host checking. This task did not read keys or verify production authentication.
Caller identity relies on the existing sudo env_reset/SUDO_UID provenance
contract; no sudo rule was added or changed.

## Independent workflow and history authorization

Both gates read only the fixed root-owned owner-approval.json under the control
state root. They reject writable ancestors, symlinks, nonregular/multilink files,
duplicate JSON fields, incomplete pins and invalid identities. The exact required
five workflow/validator blob pins and independent base come from that external
manifest, not candidate code or an environment variable.

Release verification uses HTTPS GitHub immutable commit/tree APIs without proxy
environment inheritance. It walks each single-parent commit back to the approved
base (at most 50), rejects protected changes including add/remove history, and
checks approved blobs in both base and candidate. CI success alone cannot bypass
this check. Exact-commit, branch, event, completed-success run metadata is required;
safety/gate jobs must succeed, plus AI contracts/browser jobs for static targets.
Skipped/missing jobs and incomplete API pages are rejected.

Push repeats scope validation against immutable exported objects. Protected
control-plane paths are denied on every commit, with merges disallowed. The
workflow uses the externally owner-controlled DVIZH_OWNER_FOUNDATION_BASE variable,
extracts validators from that immutable base and checks candidate blob identities.
It uses every commit's changed paths. The installed gate independently enforces
its own base/pins, so workflow self-reporting is not its authorization source.

The owner manifest is outside Git: the approved base contains the reviewed
workflows and validators, but not a digest of itself. This avoids a cyclic pin.
No approved v2.3.2 base or owner manifest has been fabricated in this worktree.

## Bootstrap and tests

BOOTSTRAP-v232.md specifies the external authenticated digest contract and a
buffered launcher under trusted `/usr/bin/python3 -I -S`. The launcher authenticates
bootstrap bytes before executing that exact buffer; bootstrap authenticates
standalone installer bytes before executing that exact buffer. No adjacent
candidate modules are imported. Installer validates the composite payload digest
and installs only verified in-memory gate buffers. It does not update the skill,
keys, sudoers, units, or application mappings. Staging ancestors and metadata are
checked. Replacements are rejected or leave the already verified buffer in use.

The complete available owner/security unittest suite runs in the existing bwrap
OS-isolation harness. Evidence/v232 records failing regressions, fixes and actual
adversarial probes. Obsolete schema-2 positive assertions were replaced with
retirement assertions; the restored v2.2 transaction/security suites remain.
Root launch parameters are tested with subprocess spies; the suite does not claim
to have exercised a real production root-to-user transition. Export/index-pack,
harmless malicious hooks/config, history edits, buffered races and rollback run
against disposable files and repositories. Network push and service effects are
mocked. Full feature/runtime acceptance is outside the user's revised scope.
