# STOP — V2.3 SECURITY REVIEW FAILED — DO NOT INSTALL

This bundle is a review/rework candidate, NOT an approved owner installation package.
Independent reviewer: proc_74b75155c22a, passed=false.
Base: da7395e436563774a29f7694b258bd85987bed2f.
No production installation, push, sudo expansion, skill replacement or business code change occurred.

## Blocking security findings

1. CRITICAL — dvizhrelease trusted_health executes newly supplied context code as root. Exact paths, hashes and syntax checks do not confine code side effects. A harmless temp fixture demonstrated a write outside target policy. Drop privileges and enforce confinement; do not ship automatic root candidate execution.
2. CRITICAL (inherited, statically identified) — dvizhgitpush invokes root Git against caller-controlled repository configuration/hooks. Redistribution must eliminate executable config/hook surfaces and test them without privileged execution.
3. HIGH — owner_install imports candidate gate before digest validation, then hashes and rereads payloads separately. A temp fixture demonstrated digest/installed-byte mismatch. Require independently trusted bootstrap and exact verified buffers from immutable staging.
4. HIGH — CI success is checked but workflow/validator contents are not independently pinned. Release authorization must independently reject protected-path alterations and untrusted workflow substitution.
5. HIGH — bearer approval phrase cannot authenticate later owner consent. Existing orchestration rule is a trust assumption, not cryptographic owner-message provenance. Do not claim the gate proves a later Telegram message.
6. MEDIUM — regression harness Python hooks are not OS isolation; child executables are not confined. Remove unconditional untouched assertions and use real containment or narrowly audited fixtures.

## Logic / acceptance gaps

- proposals-only smoke does not exercise the changed proposals helper; service generic health is not component-specific functional proof.
- runtime-only changes may receive syntax checks without required behavioral CI.
- Jump exact source is not materialized; schema-2 workflow/base rollout needs owner coordination.
- Broad AI Home archive suite: 72 passed, 26 failed (required scripts/history absent), NOT GREEN.
- Manual/shared frontend remains approval-required. Automatic promotion is intentionally withheld until binding browser regression coverage exists.
- Exhaustive Jump/social/training/facts, audible device voice, real owner install/recovery and live CI are not verified.

## Actual executed results

- Orchestrator reran owner suite: 148 tests PASS, command exit 0.
- Independent reviewer ran 22 new tests in temporary copies, PASS; adversarial fixtures still exposed the critical/high findings above.
- Implementation run of pinned Health Recovery: 41 Python, 6 Node, 4 Chromium scenarios PASS; AI Home bridge 2 PASS.
- Five implementation/harness correction rounds used; no unbounded further fixes. Security findings are not waived.
- Read-only SHA baseline confirms installed gates, local dvizh-dev skill and captured production artifacts unchanged.

## Delivery / restart / rollback status

Do not execute owner_install.py --apply from this candidate. No install authorization is requested.
The proposed transaction rollback contract is documented in OWNER-HANDOFF.md but cannot undo arbitrary candidate root side effects; it is not sufficient to resolve finding 1.
Current production remains gate 2026.09.10-dvizh-release-gate.2.2.1-state-root with /var/lib/dvizh-release-gate. /var/lib/dvizh ownership unchanged.
No unrelated jobs closed. Friend files unchanged.
