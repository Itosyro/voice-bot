# Release blocked — cycle 1 verification handoff

Existing managed job `20260909-115201-e37585`. Two historical review/fix cycles remain recorded in prior evidence. Additional owner-authorized narrow correction **cycle 1 of maximum 5** is now complete; no further cycle started. No commit, push, release proposal or deployment performed. Saved ARCHITECTURE-AUDIT.md is unchanged; architecture was not revisited.

## Requested blockers resolved locally

- Python/JS now use the identical explicit whitespace union for name/dose/note. U+FEFF-only and U+0085-only doses both reject. RED evidence captured before source edits: 36 differential subcase failures plus missing prompt contract. All 198 new differential cases and the prompt test pass after the minimal fix.
- Prompt explicitly prohibits repeating structured fields not changed by the user. Round-3 feels-great payload contains exactly day/timezone/note, appends the existing note and omits existing energy:3 and all other ratings. Original strict note-only assertion remains unchanged.

## Actual verification

Rebuilt health runner: **41 Python, 6 Node, 4 Chromium flows PASS**, including generated reproducibility and temporary HTTP/CAS integration. Existing-job `test-auto`: **quick, ai-home-v2, hermes-control PASS**. Logs and exact cycle changes are under tests/cycle1-*.

Guarded alternative real inference round 3: same gpt-5.5 route, returned gpt-5.5-2026-04-23; 33 model requests/responses, 20 synthetic tool calls, 8 synthetic pending proposals. All 8 payloads revalidate; no source drift. **Raw 12/13 PASS, 1 FAIL**: evening_schedule did not read context before clarification. **Separate established review 13/13 PASS**: context is not required before asking missing dose/time/weekdays. No numeric examples supplied. Raw result retained without modification; note-only assertion not reinterpreted. Independent offline semantic inspection is separate from raw evidence.

Prior 32 semantic files and saved audit hash-match pre-cycle bytes. Round-3 raw requests/responses, snapshots, review, inspection and hashes are preserved separately; see tests/semantic-live-round3-alternative-report.md and tests/semantic-live-round3-manifest.json.

## Remaining release limitations

No requested local code/semantic blocker remains under the established review contract; the raw clarification-scoring failure is explicitly retained. This harness executes bounded synthetic dispatch only, not configured production-model/full live Hermes execution. Zero production tool or agent API calls; no production proposals/state touched. Full production Hermes acceptance, hosted CI and production smoke remain unverified.

Owner scope for this invocation ends with this correction/verification handoff. No commit/push/deploy authorized yet. Preserve existing RELEASE.md sequence and exact later approvals; do not infer release authorization or begin another correction cycle from the maximum-five allowance.
