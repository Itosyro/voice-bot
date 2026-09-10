# Owner maintenance v2.2 — local delivery contract

This worktree contains an uninstalled release gate extension. Separate owner
control-plane delivery is required. Neither the standard release gate nor the
managed push gate can deliver their own code, tests, skill, installer or workflows.
The unchanged installer pins the previous immutable v2.1 payload. Do not run it
expecting v2.2. No sudoers or root model configuration change is part of this work.

## Exact privileged contract

The release class is `ai-integration-privileged`; it always requires a later owner
approval, including in auto mode. Each operation must have exactly these fields:

```json
{
  "source": "hermes-control-v1/dvizh_context.py",
  "target": "/usr/local/libexec/dvizh-context",
  "sha256": "<64 lowercase hex digits of the committed source bytes>",
  "release_class": "ai-integration-privileged",
  "required_owner": "root:root",
  "required_mode": "0755",
  "verification": "python-syntax"
}
```

| Exact source | Exact target | Verification |
|---|---|---|
| `hermes-control-v1/dvizh_context.py` | `/usr/local/libexec/dvizh-context` | `python-syntax` |
| `hermes-control-v1/dvizh_proposals.py` | `/usr/local/libexec/dvizh-proposals` | `python-syntax` |
| `hermes-control-v1/dvizh_proposal_bridge.py` | `/opt/dvizh-ai-approval/proposal_bridge.py` | `python-syntax-service` |

All three destinations must already be regular files, UID 0, GID 0, mode 0755.
These values come from read-only installed-file stat, saved in the evidence.
A privileged manifest may contain a subset of these three files, with no duplicates,
extra files or mixed v2.1 operations. Canonical source and destination strings are
required before path normalization; symlinks, including parents, and nonregular
files are denied. Git tree entries must be regular blobs (100644 or 100755).
The manifest is bound to its Git blob at the exact proposal commit. The gate fetches
the immutable tree itself and compares both Git blob IDs and the declared SHA256
against bytes it downloaded, including the final refetch before writing.

Top-level manifest keys are `schema` (1), optional `name` and `commit`, `operations`,
optional `restarts`, and `restart_reason` only with a bridge update. No command,
URL, health endpoint or shell fragment can be supplied for privileged verification.
The fixed enums compile Python source to a code object without executing or
importing the candidate; invalid module-level statements such as `return` fail.
All privileged applies check fixed service activity and `/api/health` before and
after the transaction. They do not execute helpers that might read user databases.

The installed bridge imports standard-library modules only. The other file in its
installation directory, `patch_ai_approval_ui.py`, is invoked by the installer;
it is not a runtime import and is not an allowed destination.

The helpers are invoked per call by `dvizhctl`; no restart is needed. The bridge
is a long-running Python process, `User=dvizh`, `Group=dvizh`, in
`/etc/systemd/system/dvizh-ai-approval.service`. An operation updating that bridge
must declare `restarts: ["dvizh-ai-approval.service"]` and a nonempty
`restart_reason` explaining why it must reload. This is the only restart allowed
for this class. Existing v2.1 targets and restart permissions remain separate.

## Approval and CI

The gate independently requires the managed push CI workflow for the exact commit
and branch, and all returned runs must be completed/successful. Missing, truncated,
red, pending or wrong-commit CI fails closed. No caller-provided CI claim is trusted.

Plan returns `APPROVE <proposal-id> <token>`. A later authenticated owner message
must contain that exact phrase. For this class, pass the entire phrase as the
single `--approval` argument; the existing controller forwards it unchanged.
Bare tokens are rejected. The challenge is single-use, digest-bound to the exact
proposal plus manifest, and valid for 1800 seconds. Future timestamps are rejected.
Development authorization and seeing the token are not release approval.

The CLI can verify possession and exact content of a phrase; it cannot independently
authenticate Telegram authorship or message chronology. That remains a trust
requirement of the authenticated owner-message boundary, as in v2.1. Separate owner
delivery must validate that integration before enabling privileged production use.

## Transaction and failure handling

A root-owned, mode-0600 `transaction.lock` in the existing approval-state directory
is held with `flock` across plan validation/challenge creation and across approval
claim, apply, restart/health, final verification, and any rollback. All entry points
share it, including direct challenge consumption. Challenge validation and durable
removal occur under this lock, so concurrent consumers cannot both claim a token.
No second plan or apply can overlap a transaction or its rollback.

The gate prefetches and verifies all sources, checks destination metadata and
health, saves every old file, and writes a durable `mapping.json` with destination,
backup path, old SHA256, UID, GID, mode, and parent device/inode identity. It verifies all backup bytes and metadata,
the mapping and unchanged destinations before the first destination write.
Backup failure therefore produces zero destination writes.

Privileged target ancestors must be root-owned and not group/world writable,
including `/` and every intermediate directory. Existing unsafe ancestor ownership
or permissions fail closed; the gate does not repair installed permissions.
TEST_MODE fixtures use the invoking UID and fixture root, with the same writable
ancestor rejection inside that root. There is no additional security override.
Destination parent descriptors remain open for the transaction, with canonical
identity checks before writes and during final verification. If an ancestor moves,
rollback uses the pinned original directory object; it never reports confirmed
rollback merely because a replacement at the canonical path contains old bytes.

The existing v2.1 `/opt/dvizh-ai-home/` allowlist again supports missing parents,
created through no-follow directory descriptors. Rollback of a previously absent
file succeeds even when the first write never created it; newly created empty
parent directories may remain. Symlink ancestors remain forbidden.

Writes use no-follow parent directory descriptors and same-directory exclusive
temporary files: write, flush, chown, chmod, fsync, replace, directory fsync, then
read-back SHA and metadata verification. Verification parses bytes rather than
running user-selected code as root. Fixture overrides are rejected for root calls.

Before the first destination write, the gate fsyncs a fixed `pending.json` journal
in `/var/lib/dvizh/autopilot-approvals`, referencing the durable backup mapping and
its SHA256. Any pending marker, including a malformed one, blocks subsequent plans,
claims, and applies. It is removed and the state directory fsynced only after a
verified final release or verified rollback. Unconfirmed rollback retains it.
No recovery command, caller-selected journal path, or arbitrary restore path is
introduced. Interrupted state requires separate owner recovery and verification
before clearing this fixed marker; this local work does not perform that recovery.

Any apply, verification, health or restart failure attempts restoration of every
file and its recorded metadata. It retries every declared service restart after
restoration, including one whose first restart failed, and rechecks health.
Restoration catches `BaseException`, including `KeyboardInterrupt`. CLI SIGINT,
SIGTERM and SIGHUP enter the same rollback path; further catchable termination
signals are ignored while restoration runs. Restoration continues after individual
errors. After restart and all HTTP/health checks, every final or restored file is
rechecked for SHA256, UID, GID and mode (or verified absent), plus canonical parent
identity. Unverified restoration or unhealthy
rollback is a critical failure; report it to the owner and stop autonomous work.

SIGKILL, machine loss, or power failure cannot be caught: partial deployed bytes
can remain until owner intervention. The durable marker detects an interrupted
pending transaction on the next invocation and fails closed; it does not itself
restore files or make a multi-file release atomic. A kill before journal creation
cannot leave deployed file bytes; a kill after verified completion but before
marker removal may conservatively require owner review. Durability relies on the
filesystem honoring fsync. Parent descriptors do not survive process death, so an
owner must verify canonical identity as well as backup bytes/metadata and service
health during recovery, rather than blindly restoring pathname strings.

## Local validation and delivery limits

See [evidence report](evidence/v2.2/REPORT.md) for exact commands, RED/GREEN results,
read-only baseline, exclusions and remaining owner-delivery checks. No production
apply, installer, sudo, commit, push or service mutation is authorized here.
