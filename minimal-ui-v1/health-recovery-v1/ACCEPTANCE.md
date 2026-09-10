# Health Recovery v1 — implementation and acceptance

Implemented in managed worktree `20260909-115201-e37585`. Nothing released or committed.
The saved `ARCHITECTURE-AUDIT.md` remains byte-for-byte unchanged (SHA256
`b75e24f749be034729b16ad34892f4abbaa4ed66d3fd1e6adfbb3e14d09ad32b`).
The audit's historical deployment blocker was superseded by the user-confirmed,
installed gate 2.2 mappings; the audit itself was not rewritten.

## Completed implementation

- Versioned `state.healthRecovery` in the existing per-user JSON/CAS API. No SQL
  migration or server change. Existing state fields, future domain/record fields,
  training projections and legacy 0–3 inputs are retained. Future domain versions
  refuse writes instead of downgrading data.
- Sleep by local **wake day** with explicit IANA timezone, start/end clock times
  crossing midnight, or reported minutes, quality 1–5, note and manual/AI source.
  Partial edits retain other fields. Reported duration replaces clock fields.
  Latest record, history, and seven-calendar-day mean count recorded days only.
  Clock duration is explicitly wall-clock duration; on a clock-change night the
  user can enter actual elapsed minutes. Equal start/end times require clarification.
- Supplements with user free-text name/dose, stable schedule and slot IDs, exact
  times, Monday=0 weekdays, enabled state and note. Today shows only enabled slots
  for that weekday. Taken/skipped/pending identity is day/schedule/slot; duplicate
  marks are idempotent. Historical name/dose/time/timezone snapshots survive
  schedule edits and disabling. UI supports create, edit, multiple slots, marking,
  disabling, and history. No dose is inferred by the domain or UI.
- One health check-in per local day: partial energy/mood/stress/soreness/wellbeing
  1–5 and notes, with validation. This does not replace legacy `checkins` or write
  `trainingHub`. The home section is one compact line plus an entry button.
- Transparent, nonclinical recovery estimate: high/normal/low/insufficient data;
  explicit thresholds, missing/stale sleep and check-in factors, and unchanged
  training/Jump readiness references with current/stale/undated/missing labels.
  The recovery estimate does not override a red training signal. No automatic
  plan, load, readiness projection, or dose changes.
- Manual → More → Health; compact lines, native forms, history in details, no
  bottom tabs. Existing routes remain available in More and desktop navigation.
  Deployed Quiet Signal style block is retained verbatim. Existing AI Home assets,
  voice frontend and boot are retained byte-for-byte. Sync has only the authorized
  health derived-field delta, checked against the pinned base. No MutationObserver
  remains in the generated app, and no new timer, reload or repaint loop was added.
  Existing sync/approval polling was not replaced with a new mechanism.
- Forms use the actual app closure, `formBases`, `rememberForm`, `saveState`, and
  `DVIZH_MANUAL_STATE`. Submits send changed fields and rebase stable slot arrays;
  remote updates do not replace active health forms. Old/new app/HTML combinations
  preserve remote health during stale legacy saves. Old app + new HTML leaves new
  forms disabled with an update message. New app + old HTML runs legacy features.
- Existing context helper exposes stored health in today/week/health/full while
  preserving existing web/telegram/status/read_only contracts. Its `health.day`
  uses saved health timezone; the outer day/timezone retain their old contracts.
- Existing proposal store, approval token and CAS bridge support typed health
  actions. New schedules need explicit dose, slots and weekdays before a proposal
  can be queued; updates use `update:true` and an existing ID. Proposals remain
  inert until authenticated UI approval. UI displays exact proposed values.
  Health approvals require `healthVersion:1` from the new confirmation UI; old
  UI commands cannot apply health without its complete field confirmation.
  Existing task/schedule/day-plan handlers remain available. Applied proposal IDs
  prevent replay across queue/state acknowledgement boundaries.
- AI Home uses its **existing real Hermes request path**, with an additive system
  prompt specifying actual `dvizhctl context`/`dvizhctl propose` tools, exact typed
  schemas, approval handling, query-only behavior, ambiguity clarification and
  no fabricated ratings/doses. “Sore legs” and “feels great” are notes, not invented
  numeric soreness/wellbeing. No keyword/regex substitute for Hermes was added.

## Verified locally

The full command in `TEST-COMMANDS.md` passes:

- **37 Python unittest executions**: sleep, missing data, timezone validation,
  partial updates, rating ranges, multiple slots, duplicates, disabled schedules,
  dose snapshots, future-field/version handling, browser/Python domain parity,
  readiness references, helper compatibility, and reproducible release output.
- **Actual pinned HTTP state server** on ephemeral loopback ports with temporary
  SQLite state and synthetic identities: inert proposals → existing queue →
  authenticated approval commands → CAS state writes → actual context functions;
  conflict retry preserving a concurrent unrelated field; rejected bad tokens;
  unauthenticated HTTP 401; per-user isolation; legacy task approval; replay;
  and old-UI health approval refusal. No production identity or DB is used.
- **Chromium mobile feature flow**: no-data display, record/edit sleep, midnight,
  visible seven-day mean, schedules with two slots, duplicate taken, skipped,
  disable/edit with retained historical dose, partial check-in, real form-ancestor
  rebase, actual temporary API persistence, legacy routes, no page reload, and
  no horizontal overflow. Screenshot is generated as `tests/mobile.png` (ignored
  locally; uploaded by CI).
- **Chromium mixed-cache flow**: old app/new HTML, new app/old HTML, old app/old
  HTML with the pinned deployed sync; remote health survives stale legacy saves.
- **Chromium proposal confirmation flow**: exact dose/times/timezone shown,
  no health write before approval, UI command consumed by the existing Python
  bridge against the temporary API, and resulting schedule stored.
- Installed gate 2.2 `validate_manifest` was called read-only on the three concrete
  manifests: privileged package classified `ai-integration-privileged`, both
  ordinary packages classified `approval`; all require orchestrator approval.
- `git diff --check` passes. Generated helpers compile without an extra runtime
  module; generated app parses; repeated offline builds reproduce release bytes.

The TDD sequence was exercised per slice: missing sleep domain → implementation;
unsupported supplements/check-ins → implementation; unsupported proposal actions
against the temporary API → bridge/context integration; absent Health UI → browser
implementation; disabled-form mixed-cache failure → capability handling; missing
exact proposal dose → confirmation rendering; old-UI health approval incorrectly
succeeding → version check. Failed fixture setup errors were corrected and the
intended failures re-run before implementing their features.

## Independent findings regression follow-up (2026-09-10)

Each fix followed an observed failing regression before implementation:

| Finding | RED observation | GREEN contract |
| --- | --- | --- |
| S1 | Nested dangerous slot keys accepted; app merge changed `({}).polluted` | Python and JS recursively reject `__proto__`, `constructor`, `prototype` in input; recursive app merge uses own properties and data-property assignment, preserving arbitrary remote JSON without traversing prototypes. Node and real browser sync/app regressions pass. |
| L1 | Sanitized/malformed records and timezone crashed context; malformed summary parity failed | Defensive read projections omit unreadable and future-dated records and unsupported versions, validate numeric inputs, tolerate missing containers/timezones, and preserve sanitized source state. All four context views and Python/JS malformed-summary parity pass. |
| L2 | IDs `a` and `b` produced identical partial confirmations | Resolved name and schedule ID, slot IDs, and before/after dose, time, weekdays, enabled and timezone are shown. Missing targets remain identified as missing. |
| L3 | Display September 10, click after midnight wrote September 11 | Buttons capture displayed day and timezone; advancing the browser clock and editing the timezone input still writes the displayed identity. No timer, observer or reload added. |
| L4 | JS accepted empty source/timezone and Python accepted boolean versions | Explicit empty/null/boolean source/timezone values fail consistently; only numeric version 1 is accepted. Boolean health approval capability cannot write. |
| Legacy helpers | Generated proposals lost `VISIBLE_STATUSES`; malformed web state caused a new context crash | Status export and CLI choices retained; unavailable web state retains legacy handling. Legacy task creation/completion and day-plan approval pass; Hermes still cannot self-resolve applied/failed. |
| Voice isolation | Historical full-repo assertion failed on the health context helper | Historical assertion reads immutable voice release `4c74d5216e2cfcca5a14bdaf179cf520aecfd685` against its original base. A separate current-feature contract compares every existing tracked file with immutable managed base, allowing exactly the three Hermes helpers and the isolation test itself; generated actual voice/AI assets remain identical to pinned snapshots. No directory-wide current exclusions or skipped tests. |

The feature entry point runs 37 Python tests, two Node regression tests, JS syntax,
and all three Chromium flows. `dvizhautopilot test-auto 20260909-115201-e37585`
passes `quick`, `ai-home-v2`, and `hermes-control`. The installed Hermes-control
profile checks syntax; the feature suite supplies its behavioral regressions.
Generated assets, self-contained helpers and manifests were rebuilt offline and
reproducibility checked. Existing legacy helper functions were compared by AST:
none removed; only the expected health dispatch/context/validation functions differ.

Local RED logs are saved as ignored `tests/findings-red.log`; GREEN logs are
`tests/findings-green.log` and `tests/test-auto-green.log`. This follow-up made no
live model call, production access, release action, commit or push, and did not
edit `semantic-live*`, guardrails, friend assets, gate workflows or the audit.

## Missing / not claimed

- **Live Hermes semantic evaluation was not run.** The natural utterance suite
  verifies the actual bridge's message/prompt boundary for sleep times/duration,
  sleep-week queries, taken/skipped/remaining, ambiguous schedule creation,
  energy 2 / sore legs / feels great / stress 4, readiness and today summary.
  Typed proposal persistence and real browser confirmation are independently
  exercised. These tests do **not** prove that a live Hermes model chooses the
  right tool/payload for each utterance. No mocked or fixture model is presented
  as live semantic evidence. A live run that creates proposals would write the
  production queue and is outside this session's authorization.
- Hosted GitHub CI has not run. The narrow workflow is supplied; its browser tool
  installation and runner environment remain for CI verification.
- No production device smoke, live microphone/transcription test, production
  state save, service restart, release proposal, commit, push, or deployment was
  performed. Voice frontend bytes and the AI Home transport/history code are
  preserved, but no claim is made about a new live microphone test.
- Pre-730b36925e arbitrary historical client builds are not represented by the
  old/new asset matrix; it uses the pinned actual deployed app/sync. The existing
  deployed sync's capability quarantine is preserved unchanged.

There is no known API constraint blocking the local implementation. Full live
acceptance remains incomplete for the reasons above; do not mark live semantic,
CI, or production acceptance green based on this local report.

## Final authorized review round — R1 / R2

R1: the pinned builder adds only `sync-health.js` and a normalization call to
`sync.js`; the original JSON reconciler is retained as `reconcileJSON`. Clock
sleep derives `durationMinutes` and `startDay` after reconciliation and during
normalization. A clock/reported mode change selects the temporal fields from the
branch changing mode (local wins if both change modes); note, source, quality,
unknown fields and independent state edits retain the existing leaf merge.
Reported duration remains authoritative and removes clock fields. Legacy rows
without a duration kind retain that representation; paired clocks are derived.
Both Python and JS summary readers recompute clock values without mutating input.

An unmodified cached prefeature sync can still persist stale derived clock data.
This is reproduced, not claimed fixed inside that old executable: updated readers
recompute it and updated sync repairs it on read/next save. The server API and CAS
contract are unchanged. This is not a guarantee that every old writer stores a
normalized duration before an updated writer next saves.

R2 shared input policy:

| Input | Policy in Python and JS |
| --- | --- |
| Explicit null for typed fields | Reject; omission alone means retain/default. In particular null start/end cannot reuse the previous clock. |
| Integral JSON numbers | Accept `3` and `3.0` for ratings/weekdays; reject booleans, numeric strings and fractions there. Durations continue to allow finite fractions in 1..1440. Integral duration/rating summary text is identical. |
| Timezone case | Accept IANA names/aliases case-insensitively, preserve the supplied spelling, resolve case-insensitively in Python context date calculation. Reject fixed-offset strings such as `+01:00`, unknown names and host-local/pseudo zones (`localtime`, `Factory`). |
| Text length | Count Unicode code points before trimming: note at most 1000; supplement name/dose at most 240. A 600-emoji note is valid; 1001 is invalid. |
| Clock digits | Exact ASCII HH:MM in both runtimes. |

Differential cases cover UTC casing, Europe/Moscow, America/New_York,
Asia/Kolkata, Asia/Kathmandu, Australia/Lord_Howe, Pacific/Chatham, Etc/GMT+5,
invalid zones, nulls, integral/fractional numbers, booleans and code-point limits.
The concurrent browser regression holds two real HTTP PUTs at the same revision,
requires one 409 retry, and checks 22:00–08:00 / 600 on the temporary server and
both clients, including independent fields. Deterministic sync tests additionally
cover both mode transition directions and cached prefeature writers. Browser
mixed-cache cases assert that the pinned old sync was actually served.

Evidence: `tests/round2-red.log` captures the pre-fix sync/parity failures and the
real browser failure with pinned baseline sync (540 != 600).
`tests/round2-green.log` records the rebuilt full feature suite;
`tests/round2-test-auto-green.log` records the installed test-auto profiles.
Preservation tests compare the exact authorized health sync delta against pinned
bytes; all other previously protected generated assets remain byte-identical.
All three manifests are rebuilt with source SHA256 values.

This round made no production, sudo, commit, push, friend, guardrail,
architecture-audit or semantic-live artifact edits. Semantic inference evidence
belongs to the separate agent and is not an acceptance claim of this round.

## Additional owner-authorized narrow correction cycle 1 / maximum 5

Existing job: 20260909-115201-e37585. Only cycle 1 executed; no extra retry or correction cycle.

RED before source edits: `cycle1-red.log`, 2 tests with 37 failures (36 whitespace subcases and missing prompt contract). The previous round-2 feels-great semantic failure remains immutable evidence. GREEN: `cycle1-green.log`, both tests pass (198 differential cases across 30 whitespace and 3 non-whitespace code points, name/dose/note, empty and padded text). No existing tests/assertions weakened or removed.

Explicit text policy: trim only U+0009–000D, U+001C–0020, U+0085, U+00A0, U+1680, U+2000–200A, U+2028, U+2029, U+202F, U+205F, U+3000, U+FEFF at boundaries. Interior characters remain; name/dose must remain nonempty; empty notes are valid; pre-trim code-point length limits unchanged. This frozen Python/ECMAScript union is explicit in both helpers.

Prompt requires only user-changed fields, required identities, and note-only feels-great updates even when energy:3 already exists. Domain partial-update behavior and architecture are unchanged.

Rebuilt full health runner: 41 Python tests, 6 Node tests, 4 Chromium flows PASS, including temporary HTTP/CAS concurrency, generated-byte reproducibility over 16 artifacts and preservation checks. Existing job test-auto: quick, ai-home-v2, hermes-control PASS. See `cycle1-full-green.log` and `cycle1-test-auto-green.log`.

Real inference round 3: same guarded alternative harness (only output namespace changed), same route https://llm.int.exe.xyz/v1/responses, requested gpt-5.5, returned gpt-5.5-2026-04-23. 33 requests/responses, 20 synthetic tool calls, 8 pending synthetic proposals. Zero production tool/agent API calls. No source drift; all 8 returned payloads revalidated. No model retries.

Raw: 12/13 PASS, 1 FAIL (evening_schedule required_context=false). Separate established offline review: 13/13 PASS; clarification may ask missing dose/time/weekdays without reading context. Raw failure is retained, not rewritten. Independent offline inspection of all outputs is saved separately. Feels-great passes the original strict assertion and exact payload keys are day/timezone/note: `{"day":"2026-09-10","timezone":"Europe/Moscow","note":"Ранее: прогулка у реки. feels great"}`. No energy or other structured rating is repeated. Note-only scoring is unchanged.

Round-1/2 and other prior semantic files (32 files) plus ARCHITECTURE-AUDIT.md are hash-verified unchanged in `cycle1-preserved-evidence.json`. Round-3 raw/snapshot/review artifacts have their own SHA256 manifest. The audit stays unchanged.

Both requested local blockers are resolved in this cycle. This is bounded inference-only acceptance, not full production Hermes acceptance. Hosted CI, production smoke and release remain unperformed. No commit, push, deployment, production writes, sudo, credentials/config reads, other profiles, friend paths, control-plane changes, new job or architecture change was performed in this cycle. No next cycle started.
