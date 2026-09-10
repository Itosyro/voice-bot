# Staged release handoff — not executed

The orchestrator owns commit/push/CI and must stop for the required approvals.
The manifests contain no guessed commit: the orchestrator must bind its eventual
reviewed commit when creating release proposals. Rebuild before that commit so
manifest SHA256 values match the exact generated helper bytes. Do not combine
ordinary and privileged operations in one manifest.

## Packages and order

1. `minimal-ui-v1/health-recovery-v1/manifests/health-recovery-frontend.json`: generated `app.js`, `manual.html`,
   and `sync.js` with the exact health derived-field delta over its pinned base.
   Sync first, app second, HTML third; no restart.
   This makes manual health entry and exact proposal confirmation available
   independently of the helper upgrade. New app with old HTML is supported;
   old app with new HTML exposes an update message and disabled health forms.
2. `minimal-ui-v1/health-recovery-v1/manifests/health-recovery-privileged.json`: **only** the exact mappings below.
   Restart `dvizh-ai-approval.service` for the new typed handlers, with the declared
   `restart_reason`. Existing handlers continue to operate. The self-contained
   sources embed `domain.py`; no new runtime helper or path is required.
3. `minimal-ui-v1/health-recovery-v1/manifests/health-recovery-ai-home.json`: `ai-home-v2/ai_home_bridge.py` to the
   existing `/opt/dvizh-ai-home/ai_home_bridge.py`, then the declared
   `dvizh-ai-home.service` restart. Enables the additive health tool instructions
   in new Hermes requests only after the context, proposals and approval bridge
   support them. Voice and AI Home frontend files are unchanged.

| Source | Exact target | Verification |
| --- | --- | --- |
| `hermes-control-v1/dvizh_context.py` | `/usr/local/libexec/dvizh-context` | `python-syntax` |
| `hermes-control-v1/dvizh_proposals.py` | `/usr/local/libexec/dvizh-proposals` | `python-syntax` |
| `hermes-control-v1/dvizh_proposal_bridge.py` | `/opt/dvizh-ai-approval/proposal_bridge.py` | `python-syntax-service` |

Each privileged row has its generated SHA256, `release_class` set to
`ai-integration-privileged`, `required_owner` `root:root`, and `required_mode`
`0755`. Ordinary rows intentionally omit those privileged-only fields because
installed gate 2.2 rejects them on ordinary operations.

## Tested intermediate combinations

| Combination | Behavior |
| --- | --- |
| New frontend / old helpers | Manual health works; old helper rejects health proposal actions without applying anything. Legacy actions still available. |
| Old proposal helper / new approval bridge | Old actions remain accepted; helper still rejects new actions. |
| New proposal helper / old approval bridge | Health proposals remain queued and unexposed; no accidental application. |
| Old Manual / new approval bridge | Legacy approvals work; health approvals without `healthVersion:1` are refused and remain pending. |
| New Manual / new approval bridge | Exact values displayed and approved through the same token/CAS command path; tested with a real temporary API. |
| Old/new Manual HTML and app with deployed sync | Stale legacy saves retain health; unavailable forms fail closed; no reload. |
| New context / old state | Missing health is represented as insufficient data, without creating canonical records or changing legacy fields. |

Avoid running stale repository frontend installers after these packages: they can
replace deployed Quiet Signal/sync with an older build. `baseline/pins.json` records
actual installed static/helper source paths and hashes; `build.py` is fully offline
and starts from those immutable snapshots. The installed proposal helper baseline
was `.1`, unlike the repo `.2`; generated sources explicitly start from installed
behavior and add terminal-status listing plus typed health actions.

## Acceptance after approval

Use `ACCEPTANCE.md` to distinguish verified local checks from unrun checks. A live
Hermes semantic test must be explicitly authorized because a successful record
request creates a proposal in the live queue. Confirm sleep, schedule ambiguity,
partial check-ins without fabricated ratings, query-only week/remaining/readiness,
and exact authenticated approval on the actual model. Test live voice only under
that separate authorization. Do not reinterpret local message-boundary tests as
live model acceptance.

A rollback of frontend/helpers must preserve `healthRecovery` in state. Old deployed
sync/app retain unknown fields, but old UI cannot edit health. A cached prefeature
sync can persist stale derived clock durations; new JS and Python readers recompute
these from the clocks, and new sync normalizes them on the next save. Do not delete health
records or replay pending proposals automatically. The proposal ledger and intake
identities are retained to prevent duplicate application on a later upgrade.
