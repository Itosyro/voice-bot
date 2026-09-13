# DVIZH daily stability — source candidate, not a production installation

Goal: use the existing planner reliably, without redesigning it or extending Autopilot.
Working branch: `chatgpt/dvizh-daily-stability-2026-09-14`.

## Product changes

The offline builder reproduces nine static assets from the immutable Health Recovery snapshot. Exactly five change: `sync.js`, `app.js`, `ai-home-v2.js`, `index.html`, `manual.html`. `styles.css`, `ai-home-v2.css`, `boot.js` and `sw.js` remain byte-identical. No server code, schema, helper, policy, credentials, service configuration or personal data is changed.

- Preserve eligible unsent AI text across reload, page hide and the AI/Manual round trip. A dispatched request with an uncertain outcome is not restored as a replayable draft. A different, newly typed draft after that uncertain request is preserved.
- Validate the actual state-save receipt before advancing the revision and merge ancestor. HTML, missing fields, a wrong snapshot or an invalid revision cannot acknowledge an unsent task. Actual HTTP/SQLite conflict and lost-receipt tests retain one task, not a duplicate.
- Bound sync HTTP requests, including response-body decoding, to 15 seconds. Late responses cannot overwrite newer accepted state. Queued edits do not show a false synchronized status.
- Recover the state/metadata pair when local-storage persistence fails. If compensation also fails, retain the pending snapshot through the existing protective mechanism and block further uploads; do not silently continue with inconsistent metadata.
- Consume the edit debounce when an explicit flush starts. Do not issue a redundant delayed write after the flush. Edits made during an in-flight request still have their next upload.
- Use a read-only display fallback at four `VIEW_COPY` lookups when a saved tone preference is missing or unsupported. This fixes an observed navigation exception without inventing or overwriting a saved preference.

The parent `client_resilience.py` was present at `673104d61ed0dabfb72dcb91eb6d3eefcdbc8bd4` but was not integrated into the historical builder. This directory integrates it separately; it does not rewrite historical generated artifacts or their original acceptance contract.

## Verified evidence

Runtime code at `29a9b0cc0bbda5a703c3f3f665e7560bcba84cbf` passed:

- Daily CI: https://github.com/Itosyro/voice-bot/actions/runs/34784783741
- Existing Health CI: https://github.com/Itosyro/voice-bot/actions/runs/34784783761
- 76 client regression tests, including 4 against the actual temporary HTTP/SQLite backend; 8 build/scope contracts; 6 tests of the read-only inspector.
- 9 real Chromium daily flows: create/reload/complete/fresh client, API offline/reconnect, focused form preservation, simultaneous title/completion edits with a real 409, false HTML receipt, AI/Manual draft round trip, synthetic AI transport reply, stalled bootstrap, and existing navigation without horizontal overflow or JavaScript exceptions.
- 4 unchanged Health browser runners against the NEW generated assets in a disposable mirror: health entry/history, mixed-cache compatibility, exact proposal confirmation, and simultaneous sleep edits.
- The historical Health suite (41 Python, 6 Node and 4 browser runners) also remains independently exercised against its historical assets.

The successful daily artifact is `10325723808`, ZIP SHA256 `1d027f81497d7b480458f332f0905c884e1c480a5182b4ed3f0397380453811f`. Its `COMMIT` and 151 exported source Git blobs were verified; all 11 generated files were compared byte-for-byte with the local build. Subsequent documentation-only commits do not change these runtime bytes; use their own CI results rather than assuming a new head is green.

Earlier failures are retained, not relabeled as successful runs. The missing-tone browser failure was a product defect. The intro-dialog and hidden edit-button failures were test interaction mistakes, corrected without disabling assertions. One historical Health concurrent runner at `54560cea...` observed two conflicts instead of its expected one; the same historical suite passed in the independent daily job on that head. A pending-debounce defect was separately reproduced and fixed in the NEW client with two RED/GREEN tests; this does not claim to repair an already cached historical executable. No historical assertion was weakened.

## Reproduce

From a checkout containing the DVIZH source paths:

```sh
python3 minimal-ui-v1/health-recovery-v1/daily-stability/build.py
node --test minimal-ui-v1/health-recovery-v1/daily-stability/tests/*lifecycle.cjs
python3 minimal-ui-v1/health-recovery-v1/daily-stability/tests/test_contract.py
python3 minimal-ui-v1/health-recovery-v1/daily-stability/tests/test_inspector.py
python3 minimal-ui-v1/health-recovery-v1/daily-stability/build.py --check
```

The daily GitHub workflow additionally provisions isolated Playwright/Chromium tools and runs `tests/browser-daily.cjs` and `tests/health_matrix.py`. The latter copies the original test scripts unchanged into a temporary mirror and serves the new assets without calling the historical builder. It never touches a live application.

## Next release step — preserve the owner's data and current deployment

`inspect-installed.py` is a READ-ONLY preflight, not an installer. Run as the normal server owner, without sudo. It fingerprints the fixed DVIZH program-file allowlist, reads only safe literal component version strings (AST, never import/execute), checks three service states, and validates JSON from `/api/health`. It does not read `/api/state`, identity files, databases, private keys, environment files or tokens. A missing/unreadable/different file is a stop condition, not permission to replace it.

Before producing an installation command, compare the actual installed static/backend bytes with the tested source contract and determine the supported installed release contract. Do not assume an old handoff is the live state. Use the existing owner-approved release workflow. Do not manufacture managed job IDs, bypass the release gate, widen Hermes permissions, or start managed jobs while the Foundation transition is unresolved.

`dist/`, `PAYLOAD.json` and `release.json` are generated CI artifacts, not committed raw-GitHub payload paths. The generated release manifest is a five-file deployment blueprint. Do NOT submit it to a gate which requires committed sources until the exact built payload has been published through the appropriate supported release path. This package does not contain a production installer. Preserve current bytes/UID/GID/modes and obtain the required exact approval before any installation. Do not use stale frontend installers or replace the entire site with an older repository tree.

## Limits, not promises

- Drafts retain the existing same-tab sessionStorage policy and ten-minute lifetime; this is not permanent cross-tab or overnight draft storage.
- The offline test makes the state API unavailable while static assets remain reachable. Full cold-start offline PWA support is NOT claimed; the existing network-only service worker is unchanged.
- The AI response in the browser transport test is a synthetic fixture, not real Hermes inference. Real microphone recognition, spoken output, production approval and device testing remain separate owner actions.
- Local browser navigation was blocked by the execution environment. Real browser acceptance was performed on GitHub-hosted disposable runners, not claimed as local or production verification.
- No production installation, production backup, server permission change, main update or friend-project change was performed by this work.

The first-day acceptance after an approved update is one real task: create it, reopen the app, complete it, and confirm the mark persists. Then verify one genuine AI request without creating synthetic personal records.
