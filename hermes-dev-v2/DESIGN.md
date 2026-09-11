# Trusted DVIZH Mode v2.3 — local owner maintenance

Implementation base: `da7395e436563774a29f7694b258bd85987bed2f`.
This is an uncommitted owner control-plane change, not a feature release.

## Contract and trust

Production plan/apply accepts manifest schema **2**. The unchanged schema-1
fixtures retain their historical validation/apply behavior only in unprivileged
TEST_MODE; root execution rejects fixture overrides. Structural validation alone
still understands schema 1 for historical workflow tests. It cannot authorize a
production apply. Proposal envelope remains schema 1.

Each schema-2 operation has exactly `source`, `target`, `sha256`, `release_class`,
`required_owner`, `required_mode`, `verification`. Values must equal TARGET_POLICY;
SHA256 must match immutable downloaded bytes. No manifest HTTP path or executable
command is accepted. Fixed HTTP routes and restart names come from the target map.

| Target | Exact source | Class; mode; verification; restart |
|---|---|---|
| `/opt/dvizh/static/index.html` | `ai-home-v2/index.html` | auto-safe; 0644; http-bytes; none |
| `/opt/dvizh/static/ai-home-v2.js` | `ai-home-v2/ai-home-v2.js` | auto-safe; 0644; http-bytes; none |
| `/opt/dvizh/static/ai-home-v2.css` | `ai-home-v2/ai-home-v2.css` | auto-safe; 0644; http-bytes; none |
| `/usr/local/libexec/dvizh-context` | `hermes-control-v1/dvizh_context.py` | trusted-runtime; 0755; python-context; none |
| `/usr/local/libexec/dvizh-proposals` | `hermes-control-v1/dvizh_proposals.py` | trusted-runtime; 0755; python-context; none |
| `/opt/dvizh-ai-approval/proposal_bridge.py` | `hermes-control-v1/dvizh_proposal_bridge.py` | trusted-runtime; 0755; python-service-context; dvizh-ai-approval.service |
| `/opt/dvizh-ai-home/ai_home_bridge.py` | `ai-home-v2/ai_home_bridge.py` | trusted-runtime; 0755; python-service-context; dvizh-ai-home.service |
| `/opt/dvizh-jump/dvizh_jump/jump_web_bridge.py` | `jump-goal-release/dvizh_jump/jump_web_bridge.py` | trusted-runtime; 0755; python-service-context; dvizh-jump.service |
| `/opt/dvizh/server.py` | `minimal-ui-v1/health-recovery-v1/baseline/helpers/server.py` | approval-required; 0755; python-service-context; dvizh.service |

Five additional **exact** approval-required static mappings use the same basename
under `minimal-ui-v1/health-recovery-v1/dist/`: `manual.html`, `app.js`, `sync.js`,
`styles.css`, `sw.js`. These are individual entries, not a prefix permission.
They require 0644, http-bytes, and no restart. Every target requires root:root;
fixture tests substitute the invoking UID/GID.

Unknown/sensitive backend, auth, storage, systemd, control-plane targets, wildcard
and traversing paths are denied. Manual promotion to auto-safe is deferred:
there is no binding managed-CI browser contract covering every required route,
unsaved state, reload, Quiet Signal, and toggle behavior for these exact sources.
The server source is intentionally a baseline source and still requires approval;
it is not permission to substitute an arbitrary backend file.

## Execution and failure boundaries

The root gate checks managed branch HEAD, complete merge-free ancestry from the
existing managed base `accb555b0da3b90eed9d1708ee68a286506d4feb`, immutable manifest
blob, every regular Git blob and SHA256, Python compile-only syntax where mapped,
exact destination metadata and non-writable root-owned/group ancestors, and all
CI runs for the exact branch/commit. Required CI is the push-triggered
`.github/workflows/dvizh-hermes-autopilot.yml`. Apply repeats verification.

`preflight` is a read-only preview: no state creation, challenge, backups or writes.
It rejects pending recovery and takes a nonblocking shared lock when the existing
lock exists. It is not an authorization; apply revalidates everything. Plan may
create the root-owned lock and an approval challenge. “Before first write” in the
transaction means before the first **destination** write: durable backup and
journal writes necessarily precede destination replacement.

The exclusive transaction flock covers plan/challenge/apply. All sources and
metadata are checked before backup preparation. All backups and the durable
mapping verify before any destination write. The fsynced pending journal records
backup mapping SHA, commit and mapped restart union. Open parent descriptors remain
pinned through atomic replace and rollback. All files restore on middle failure,
including files after the failing operation; every mapped old service restarts
and health is checked again. Any unconfirmed restoration keeps recovery blocked.
Catchable signals trigger rollback; SIGKILL/power loss leaves pending recovery.

Only the target-derived service union is allowed, including mixed batches.
Pre/post checks require prior service activity, MainPID > 0, fixed `/api/health`
JSON `ok=true`, and for Python targets fixed `dvizh-context today` JSON with
`read_only=true` and `web.ok=true`. Static responses must equal deployed bytes;
rollback responses must equal original hashes. Commands use fixed argv, never a
manifest shell. Helper output and HTTP bodies are not included in error reports.
These checks do not prove every domain feature or audible speech on a user device.

Auto mode needs approval only if any row is approval-required. Safe mode always
requires it. Every v2.3 approval uses the exact full later `APPROVE id TOKEN`
phrase, digest binding, one-time consumption and TTL 1800. The additive skill
forbids self-approval. The gate verifies the phrase, not Telegram sender provenance;
a trusted later-user-message decision remains an orchestration responsibility.

## Owner upgrade

The installed nonsecret 2.2.1-state-root gate supplied the root-state correction:
`/var/lib/dvizh-release-gate/{approvals,backups}`. `/var/lib/dvizh` is never chmodded
or chowned. Observed metadata: application state 997:988 0750; gate state 0:0 0700.

`owner_install.py` is a separate offline owner upgrade, not a sudo-authorized
command. It upgrades only the three existing gates/controller plus the fixed
exedev dvizh-dev skill. No keys, sudoers, services, business files, or other
profiles are touched. Its payload digest includes the installer and all payload
files. Existing gates must be root:root 0755 and the skill exedev's 0600 file.
It verifies every backup before writes and uses the same lock/pending journal.

The original skill bytes are retained as an exact prefix. One explicit appended
section supersedes old limits and token-only instructions. Identical reinstallation
is a no-op; conflicting markers fail closed. The installer preserves backups,
metadata and restores all destinations on caught failure. It is upgrade-only:
missing files require separate owner provisioning, not implicit creation.
