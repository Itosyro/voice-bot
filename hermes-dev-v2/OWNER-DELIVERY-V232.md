# v2.3.2 Foundation — final owner delivery (independent review PASS)

This final status supersedes pending/blocked status text in historical DESIGN,
OWNER-HANDOFF, BOOTSTRAP and prior evidence inventories. Those files retain their
reviewed bytes; their procedural trust, staging and rollback requirements remain.
Original failed reports are preserved, not silently changed into passing reports.

Rework parent: afd44df10909f365b39216e7676498d48c59870a.
Bundle prerequisite: da7395e436563774a29f7694b258bd85987bed2f.
Final immutable candidate/tree/bundle identities are in the accompanying external
DELIVERY.json to avoid a self-referential commit hash.

Independent verdict: evidence/v232-fix/INDEPENDENT-REVIEW.json passed=true,
security_concerns=[], logic_errors=[]. Only L1/L2 changed in this rework.
Owner suite: 160 executions PASS, independently rerun and orchestrator rerun.
All three actual protected static workflow blocks PASS (not a live GitHub CI run).
Doctor contract independently exercised valid/missing/malformed/invalid types,
missing pins/duplicate JSON/symlink/ancestor symlink/hardlink/FIFO/unsafe metadata/
oversize/deep JSON cases, gate parity, read-only snapshots and aggregation.

## Immutable installation payload

Payload SHA256: 6b2e84e9f3e8baef9737e997a6f9c934ea93268fddaee06f1c8390b1131d6872
Bootstrap SHA256: 1cbdc117a5256382643aeb2de1dc7d5e2aa700799e1f6c0ebe60e841adfc01c2
Installer SHA256: c976026e09807a235b46dc4349469c5669149ff54387238038ff1cc45ea91a0b

Exact Git blob pins:
- .github/workflows/dvizh-hermes-autopilot-installer-smoke.yml: abbdad371aed2ad198213ec7853f20fabfe72796
- .github/workflows/dvizh-hermes-autopilot-v2-tests.yml: ec53f5005632b551dd93192668000faac5be3c62
- .github/workflows/dvizh-hermes-autopilot.yml: c5783874ebd2abb3ba1e2f10eabd1c70847c7791
- hermes-dev-v2/dvizhgitpush.py: 6a0d7f2d8067784d8b1b9e96e79d0f050a3b8a58
- hermes-dev-v2/dvizhrelease.py: 76068f4fd797e86b3142a946c62268ac9524f834

## Owner-only installation boundary

Code/package is ready for owner-controlled installation, NOT already installed
or authorized by these candidate files. Authenticate these identities through an
independent owner channel. Use the exact buffered external launcher documented in
BOOTSTRAP-v232.md and bootstrap_v232.py with the independently authenticated
bootstrap, installer and payload digests. Trust /usr/bin/python3 and stdlib; use
-I -S. Use root-owned staging with trusted ancestors, never hash a candidate
pathname then execute that pathname separately. Do not use the legacy shell
installer as a v2.3.2 upgrade route. Installer updates only the three existing
control-plane executables; local skill, sudoers, keys and application files are
not installer targets.

Owner must independently approve the final candidate (or a separately reviewed
base with identical five blobs), provision fixed
/var/lib/dvizh-release-gate/owner-approval.json using the documented exact schema,
and align DVIZH_OWNER_FOUNDATION_BASE plus the managed-job base branch.
An owner-approval template in the external delivery archive is NOT authorization;
do not install it merely because it shipped with the candidate.
No new root permission is granted by this delivery. Do not change /var/lib/dvizh.

## Rollback and interruption

Installer validates all original target bytes/metadata and backup records before
replacement and installs only the verified buffers. Caught failures restore all
original files/UID/GID/modes. It does not restart services. Uncertain restoration
or interruption retains the journal and blocks another transaction. Owner recovery
must authenticate journal/mapping and backup bytes/metadata before restoring every
original; never clear pending merely to unblock a gate. Preserve the backup path
reported by the owner installation. No live rollback/power-loss recovery tested.

## Doctor expectations after owner provisioning

Controller: 2026.09.11-hermes-autopilot.2.3.2
Push gate: 2026.09.11-dvizh-git-push-gate.2.3.2
Release gate: 2026.09.11-dvizh-release-gate.2.3.2
Both doctors: owner_authorized=true only when their actual owner_manifest contract
accepts the file. Missing/invalid authorization => owner_authorized=false and
ok=false, without raw manifest/token output or writes. Push transport authorized
is distinct from owner authorization. Overall ok also requires tools/transport and
no pending transaction; a valid manifest is not permission to bypass those checks.
Private deploy key remains invisible to Hermes. Only three static targets auto;
existing runtime/Manual/server approval; Jump DENY; schema 2/trusted-runtime OFF.

## Verified limits

No production modification, owner installation, --apply, push, sudoers/key change,
live skill edit, friend change or unrelated job action. Eleven captured nonsecret
installed gate/skill/runtime hashes were compared unchanged before final delivery.
Actual root identity transition, live GitHub CI/transport, owner provisioning and
OS-crash recovery are owner-side acceptance, not claimed as locally exercised.
The retained v2.2 approval phrase is an orchestration boundary, not cryptographic
Telegram identity attestation. Review PASS is bounded, not universal security proof.
