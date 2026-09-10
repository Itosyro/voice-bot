# Health and recovery v1 — pre-implementation audit

Status: blocked on deployment scope; no implementation or production changes.
Managed auto job: 20260909-115201-e37585.

## Existing contracts

- /opt/dvizh/server.py StateStore.put and Handler.do_PUT: per-user JSON state with revision CAS. Reuse without SQL migration; no forced writes.
- /opt/dvizh/static/sync.js normalizeState/reconcile/upgradeMerge/sendState: preserve unknown fields and three-way reconciliation; new forms must use app.js formBases and DVIZH_MANUAL_STATE rather than reload/repaint loops.
- Existing check-ins/readiness use 0–3 scales, not requested 1–5. trainingHub is producer-owned and replaced by projection; do not add canonical records inside it or silently reinterpret legacy values.
- Dedicated sleep timestamps/history and dose/slot-based supplements were not found. Proposed versioned healthRecovery domain stores these additions in existing state, with explicit user timezone, stable day/slot identities and provenance. Existing readiness consumers must remain compatible, not become divergent sources.
- Readiness v1 must be nonclinical, explain missing/stale inputs and never automatically alter training or doses.

## Integration blocker

Actual AI Home bridge /opt/dvizh-ai-home/ai_home_bridge.py calls Hermes with a prompt instructing dvizhctl context. /usr/local/libexec/dvizh-context selects narrow state fields and does not expose the proposed domain. Existing /usr/local/libexec/dvizh-proposals and /opt/dvizh-ai-approval/proposal_bridge.py support task_create/task_complete/schedule_move/day_plan only. Full health context and typed approved health actions require extending these existing components, not building a bypass or parallel backend.

Installed /usr/local/sbin/dvizhrelease explicitly denies /usr/local/ and does not allow /opt/dvizh-ai-approval/. Its restart allowlist excludes the approval service. Ordinary APPROVE cannot authorize denied targets. No change to gate/control-plane may be made autonomously. A separate owner-authorized maintenance release must provide a narrow verified deployment route before the complete feature can ship.

## Baseline safety

Worktree base accb555b0da3b90eed9d1708ee68a286506d4feb lags deployed frontend. Audit compared live app.js, sync.js and manual.html against commit 730b36925e1536bc4229dc0223578101246b7249 generated release and found byte-exact matches. Pin actual deployed files individually before implementation; do not regenerate from stale patchers. Deployed proposal helper version differs from repository version.

## Verification performed

Autopilot doctor passed (authorized guarded push, release gate healthy, private deploy key not visible). dvizhctl status returned nine active application services. Read-only Codex architecture audit completed successfully; independent direct read confirmed gate DENY_PREFIXES includes /usr/local/ and only AI Home directory is prefix-allowed.

No credentials or production database inspected. No application-data writes, production edits, commits, pushes or deploy attempted. No friend-project files modified. Feature tests/CI/browser smoke not run because implementation is blocked; do not report feature complete.
