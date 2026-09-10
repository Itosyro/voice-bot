# Round 2: bounded live semantic evaluation

**12 PASS, 1 FAIL, 0 ERROR, 0 NOT_RUN** after the established offline review. Raw scoring remains **10 PASS, 3 FAIL**. All 13 scenarios completed with 33 requests/responses, 20 synthetic tool calls and 8 pending proposals. Both prior semantic failures now pass: evening clarification gives no unsupplied dose/time examples, and readiness explicitly distinguishes health 1–5 from training 0–3.

Remaining failure: `checkin_feels_great` includes `energy: 3` alongside the appended note. This is the fixture's existing score, explicitly described as unchanged, not an invented score. The unchanged assertion requires no numeric rating fields for this note-only case, so **FAIL is retained**. No semantic assertion was relaxed and no model request was repeated to improve the score.

The existing offline logic recognizes the correct `7:00` weekly mean and removes the historically documented extra context prerequisite for evening clarification while checking for numeric dose/time examples. These explain the two raw-to-reviewed status changes. The review script only updates historical explanatory text and replaces prior-run hardcoded request/proposal counts with evidence-derived accounting checks; its semantic checks are unchanged. A quoting error in that explanatory edit was corrected before offline review completed; it made no inference calls and did not change raw evidence.

| Scenario | Result | Independent inspection |
| --- | --- | --- |
| sleep_times | PASS | Exact overnight clock payload; 450 minutes, previous-day start, no quality invented. |
| sleep_duration | PASS | 420 minutes only; no clock times or quality supplied. |
| sleep_quality | PASS | Quality 4; existing 480-minute sleep preserved by domain merge. |
| sleep_week | PASS | Three recorded days and correct 7:00 mean. Existing equivalent-notation review applies. |
| magnesium_taken | PASS | Exact current magnesium schedule/slot and taken status. |
| vitamind_taken | PASS | Exact current vitamin D schedule/slot and taken status. |
| omega_skip | PASS | Exact current omega schedule/slot and skipped status. |
| multiple_slot_ambiguity | PASS | Asks which of the two actual slots; no proposal. |
| evening_schedule | PASS | Open question asks dose, weekdays and exact time; no numeric examples, default days, or proposal. Existing no-context-required review applies. |
| checkin_explicit_notes | PASS | Explicit energy 2/stress 4; previous note retained and sore legs appended, no numeric soreness. |
| checkin_feels_great | FAIL | FAIL retained: payload repeats existing energy=3 although this case requires note-only fields. Value matches fixture and is described as unchanged; no invented wellbeing score. No assertion waiver. |
| readiness_reasons | PASS | Explicit health 1–5 versus separate training 0–3 explanation; missing/stale records and source references identified. |
| today_summary | PASS | Fresh today context, current synthetic task, health summary and separate scales; no proposal. Closing moderate-training suggestion is unsolicited narrative advice, not a tool action; existing matrix does not assess all advice. |

## Scope and containment

Requested model stayed `gpt-5.5`; every response returned `gpt-5.5-2026-04-23`. Used only the established `https://llm.int.exe.xyz/v1/responses` inference route, documented by [exe.dev LLM integration](https://exe.dev/docs/integrations-llm.md). No model guessing, switching, availability probe, credential/config access or changes. Public documentation was read separately; live harness network requests were inference only.

**The configured production model was not tested. This inference evaluation validates real model tool choice and arguments, not the complete production Hermes agent.** Actual bridge message definitions and installed terminal schema were extracted from nonsecret source; all returned terminal strings were parsed as data by the synthetic dispatcher. Production tool calls and agent API calls: **0**. No production storage, approval/application, profile edits, sudo, commit or push.

The live harness is byte-identical to round one. All 14 preflight guards passed. Bounds stayed 13 scenarios × 4 steps, 6 tool calls and 90 seconds per scenario, zero retries, 1,800 maximum output tokens per request. All synthetic saved states remained unchanged and all proposals pending. Total provider usage: {"input_tokens": 116093, "output_tokens": 2678, "total_tokens": 118771}.

## Current-source validation and evidence

All **8 actual returned payloads** passed current-domain syntax and existence/merge validation at run completion and again during offline review, using separate synthetic copies. All evaluated messages match the current built bridge; the complete current AI-PROMPT is embedded exactly. Prompt SHA-256: `7bf098c6280b658a748cdac5d7c0b3279add02b8c5823f7c6588c969df96913f`. No source drift occurred during this run or review. Since round one, bridge, domain, prompt, context and proposal helper hashes changed; those are observed pre-existing changes, not edits by this evaluation.

Before rerunning, all 10 existing semantic-live files (including scripts, raw red evidence, review, snapshots and reports) were copied byte-for-byte to `semantic-live-round1-*`; [archive manifest](semantic-live-round1-manifest.json) records their hashes. Round-one reviewed result remains 11 PASS / 2 FAIL.

- [Raw evidence](semantic-live-alternative-evidence.json): unchanged returned model messages, requests, original assertions/scores and actual payloads. SHA-256: `cd398c899f64f417d68b8c2b0dda68f4a01b814ac8be3b2d56256b3eb3f9de13`.
- [Offline review](semantic-live-alternative-review.json) and [independent inspection](semantic-live-alternative-inspection.json).
- Source snapshots: [start](semantic-live-alternative-snapshot.json), [finish](semantic-live-alternative-final-snapshot.json), [review](semantic-live-alternative-review-snapshot.json).
- [Round-two archive manifest](semantic-live-round2-manifest.json): retained byte-identical copies of completed round-two artifacts, including raw scores and responses. Hashes establish integrity; these are ordinary filesystem copies, not a write-once storage service.

Only `semantic-live*` files in this tests directory were written. Neither prompt nor implementation changed. These narrow checks do not certify every narrative recommendation, production execution, or behavior across future stochastic runs.
