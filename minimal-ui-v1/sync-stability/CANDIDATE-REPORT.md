> Current owner-authorized protective-mode cycle: the mandatory reverse-cache gate is GREEN. **43/43 Node tests pass. Browser verification remains blocked by this sandbox.** This section supersedes earlier mixed-cache blocker/status and version-1 delivery statements below. Stopped for independent review; no release approval or deployment.

## Protective-mode candidate — 2026-09-09

The generated sync waits for pinned boot's `markAppLoaded()` before checking `typeof DVIZH_MANUAL_STATE.applyRemote`. Bootstrap still fetches state but defers all PUTs until the app has loaded. Compatible apps use the existing reconciliation path and upload scheduling. An app without the boundary enters sticky protective mode: uploads/retries are blocked, pending timers cannot send, and existing polls continue accepting canonical server snapshots independently of quarantined local saves. Later installation of a hook does not silently resume uploads. The OLD sync / NEW app capability guard remains intact.

The state key contains accepted server data in protective mode. Local save snapshots and their retained history use `dvizh-sync-quarantine-v1`; the current pending snapshot is also retained in memory. They are never merged into an upload automatically. Old app forms/private memory remain intact, so their displayed content can remain stale. The mandatory actual Manual/app/boot/sync test submits age 20 after remote height 160 and asserts **server height 160, canonical height 160, pending age 20, zero PUTs**. Existing compatible conflict/retry tests remain mandatory.

A persistent Russian notice explains the mode and offers **«Обновить Manual»**. Only that user action captures form controls/contenteditable text and pending history in a verified `dvizh-manual-recovery-v1` archive. It then explicitly warns that automatic form filling/command replay is unavailable and asks whether to proceed to `/manual.html?v=20260909-sync-stability-2`. Cancellation retains the current page and archive. The updated compatible app offers **«Показать сохранённые черновики»**, exposing a read-only copy for manual transfer after reviewing current server values. No draft or stale command is automatically applied. Existing archives are retained. Failed persistence or selected file attachments block navigation and display a Russian recovery warning and copyable archive; pending-storage failures retain the current edit in memory and warn immediately.

**Recovery limitation:** recovery is a read-only JSON archive for explicit manual transfer, not automatic restoration of editor contexts, timer execution, files, or form submissions. Users are warned before leaving. Password controls are excluded; file contents cannot be captured and require manual preservation. Archive/history storage grows with retained snapshots and can hit quota; memory-only retention does not survive closing the page. Verified localStorage cannot guarantee survival of later browser eviction. The update destination must serve the candidate app; if it still serves the old app, protection remains and stored archives are retained. No production proxy/service-worker verification was performed.

The new immutable delivery key is `20260909-sync-stability-2` for both Manual entry and sync script. Boot remains a pinned test input and denied release target. Poll 8000 ms, debounce 450 ms, retry 1600 ms remain unchanged; no polling loop, second sync, forced overwrite, automatic reload/navigation, or clearing operation was introduced.

### Exact observed RED / GREEN

- Original full `tests/run.cjs`: the standalone mandatory reverse diagnostic failed with **156 !== 160**, even while Node's registered tests reported 37/37. [Original RED](evidence/protective-red.txt).
- Converted the reverse diagnostic into a registered mandatory `node:test`, and changed the old-app/new-sync matrix to require quarantine. Before implementation: **38 tests, 36 pass, 2 fail** (missing pending API and server height 156). [Registered RED](evidence/protective-tests-red.txt).
- First implementation: **38/38 pass**. [First GREEN](evidence/protective-first-green.txt).
- Added four actual-app startup/recovery tests: **2 pass, 2 fail**. One found loss of prior quarantine on another boot (fixed by retaining history); the other exposed a jsdom same-URL navigation test setup issue (corrected to start at the unversioned old entry). [Recovery RED](evidence/protective-recovery-red.txt). After fixes: **42/42 pass**. [GREEN](evidence/protective-green.txt).
- Added quota coverage. An initial failure showed the test was injecting storage failure after sync had captured native methods; moved injection before sync evaluation. That is a harness correction, not a claimed product RED. [Harness failure](evidence/protective-quota-harness-failure.txt).
- Final mandatory full run: **43 tests, 43 pass, 0 fail, 0 skipped**, including real old/release apps, pinned boot and generated Manual/sync, startup writes, repeated polls/manual/online requests, preserved focused drafts, pending history, explicit update/cancel and recovery on another app boot, and real injected persistence failures. [Final GREEN](evidence/protective-final-green.txt).

Commands used (worktree root):

```sh
JSDOM_PATH=/home/exedev/.hermes/hermes-agent/node_modules/jsdom node minimal-ui-v1/sync-stability/tests/run.cjs
node minimal-ui-v1/sync-stability/build.cjs --check
node minimal-ui-v1/sync-stability/reproduce.cjs
PLAYWRIGHT_PATH=/home/exedev/.hermes/dev/dvizh/browser-tools-sync-stability/node_modules/playwright CHROMIUM_PATH=/home/exedev/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome node minimal-ui-v1/sync-stability/tests/cache-browser.cjs
PLAYWRIGHT_PATH=/home/exedev/.hermes/dev/dvizh/browser-tools-sync-stability/node_modules/playwright CHROMIUM_PATH=/home/exedev/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome node minimal-ui-v1/sync-stability/tests/browser.cjs
```

[Build check](evidence/protective-build.txt) and [pinned reproduction](evidence/protective-reproduction.txt) pass. Release files, source/artifact manifest hashes, and `candidate.diff` were regenerated. Generated sync and extended browser runner pass syntax checking. The HTTP-cache runner now includes reverse-cache no-PUT/height160/age20 plus explicit update and unsaved-age21 archive recovery, but was **blocked at localhost bind: EPERM** ([output](evidence/protective-cache-browser.txt)). The DOM browser runner was **blocked during Chromium launch: socket permission failure/SIGTRAP** ([output](evidence/protective-browser.txt)). Neither is claimed GREEN; host/CI browser verification remains outstanding.

All cycle writes are under `minimal-ui-v1/sync-stability/**`. Existing workflow and release proposal were left unchanged. No production writes, friend/control paths, credentials, installation, commit, push or deployment actions. Independent review must assess the explicit manual-archive recovery UX and complete browser verification.

---

> Latest owner-authorized additional cycle: mixed-cache app guard implemented; **reverse-cache safety remains an independent-review blocker**. See the final section. Earlier cycle limits/results below are historical and superseded only by this explicit authorization.

# Manual sync stability — independent-review candidate

Implemented and tested in the managed worktree only. **Not committed, pushed, deployed, or applied to production.** Release artifacts are [app.js](release/app.js), [sync.js](release/sync.js), and [manual.html](release/manual.html), generated from the current deployed Quiet Signal code, not the older repository Manual. Review the exact [candidate diff](candidate.diff) and [manifest](release-manifest.json).

The four authorized production static files were copied byte-for-byte into `baseline/`. [Baseline pins](baseline-pins.json) cover app.js, sync.js, manual.html and boot.js. A final read-only hash comparison confirmed all four production files remained identical: [verification](evidence/production-readonly.txt). No production API, database, credentials, user state, background producer or control-plane operation was used. `boot.js` is a **denied release target**; it exists only as a pinned test input. Manual HTML changes only `<script src="sync.js">` to `<script src="sync.js?v=20260909-sync-stability-1">`. CSS, the Quiet Signal design/extension, and boot loading behavior remain unchanged. The generated HTML is now a pinned, reproducible release artifact.

## Behavior and boundary

`DVIZH_MANUAL_STATE.applyRemote(snapshot)` reconciles the app's private state without writing DOM, saving, navigating, replacing timer objects, or recreating nodes. Both poll and 409 acceptance use it. All `location.reload()` calls are removed from generated sync.js. Metadata and object-key-order differences still advance accepted state/revision, but cannot replace the page or forms.

The deliberate display policy is **deferred rendering**: remote data enters storage and memory immediately; existing user rendering actions and explicit navigation expose it. Home, Tasks and Settings navigation now refresh their displays too. Background sync updates its existing status indicators, but does not repaint content. An idle view may therefore continue displaying its previous projection until navigation or another existing rendering action. This is a material candidate tradeoff for independent review, not a claim of immediate live visual updates.

Form bases survive blur and remote acceptance. Submit merges the user's changes against the form's displayed base and the latest stored state. Actual editor refills refresh their base; merely showing a form does not. Ancestors survive submit microtasks. Partial Jump renders advance only displayed fields and retain the focused field ancestor; Social settings renders refresh every displayed field. Jump profile defaults are recorded as displayed defaults so submitting an untouched default cannot undo a newly supplied remote value. Jump, Social and Week update commands also rebase their payload fields; preserving only optimistic state would leave a later server command capable of undoing the remote edit. Existing objects with IDs are updated in place where needed so a handler's retained entity references remain useful across its internal saves.

The three-way sync ancestor is persisted as `baseState` alongside revision in the existing sync metadata entry. Changed local leaves win simultaneous edits to the same leaf; unchanged leaves take remote values. Arrays with unique `id`, `commandId`, `code`, or `exerciseKey` merge by that identity. Deleting an existing identified record wins over editing it; task/proof tombstones are respected. A newly observed reset wins by its reset timestamp, with remote winning equal timestamps. Unidentified arrays are atomic values.

GET and PUT are serialized. Events requesting a pull during an active request coalesce into a pending pull. Edits during requests remain queued and are reconciled against the accepted response; a successful PUT records the actual submitted snapshot as the ancestor, not subsequent edits. A 409 gets one immediate retry, then the existing delayed retry behavior. Reset PUTs now use revision comparison too, rather than force-overwriting the server. Bootstrap also checks for writes made while its GET was pending. Offline startup retains its outbox intent.

Older clients have no saved ancestor. The first-upgrade fallback retains the existing core timestamp merge, takes remote projections as authoritative, and retains local pending commands by identity (excluding identifiable command results). After accepting a revision, normal three-way reconciliation applies. No algorithm can reconstruct an ancestor the old client never saved.

Polling stays **8000 ms**, write debounce **450 ms**, and the existing retry delay **1600 ms**. No interval was added or increased; sync was not disabled.

## Reproduce and verify

These dependency-free commands use checked-in sources and synthetic responses only; they work without `/opt` or network access:

```sh
node minimal-ui-v1/sync-stability/reproduce.cjs
node minimal-ui-v1/sync-stability/build.cjs --check
node minimal-ui-v1/sync-stability/tests/sync.test.cjs
node minimal-ui-v1/sync-stability/tests/contracts.test.cjs
```

`reproduce.cjs` reproduces the old reload defect against the **pinned baseline**, not the candidate. Its previous unpinned service-worker subsection is intentionally excluded. Historical producer/source findings remain in REPORT.md and their original output files; `check-producer.py` is a historical, environment-dependent diagnostic, not a candidate/CI command.

To regenerate the candidate, run `node minimal-ui-v1/sync-stability/build.cjs`. The builder checks all four baseline hashes and exact single-occurrence patch anchors, generates app.js, sync.js and manual.html, and produces a deterministic manifest with artifact and builder/source hashes. `--check` compares byte-for-byte and rejects drift, a changed manifest, or extra release targets.

For the actual Manual DOM and browser suites:

```sh
cd minimal-ui-v1/sync-stability
npm install --ignore-scripts --no-audit --no-fund
npm test
npx playwright install chromium
npm run test:browser
```

The full Node suite evaluates actual generated sync/app JS and pinned boot.js inside Node VMs; jsdom parses the generated Manual HTML. It does not substitute the app with a state stub. The separate dependency-free sync suite uses small DOM/storage/fetch/clock doubles to control network races precisely. DOM tests cover actual task and Training forms, Jump profile commands/defaults, private memory, blurred drafts, editor reopen, active Training view, modal state, node identity, focus, input and document selection, scroll, detail state, and both running timers.

Local environment: Node v26.8.1, jsdom 29.1.1, Playwright 1.62.1. The existing jsdom installation was loaded read-only with `JSDOM_PATH=/home/exedev/.hermes/hermes-agent/node_modules/jsdom`. No dependency installation was issued by this run. The package declares exact direct dev dependency versions; transitive dependencies are not lockfile-pinned. Generated release bytes themselves have no npm dependency.

[CI workflow](../../../.github/workflows/dvizh-sync-stability.yml) performs offline reproduction/build checking, Node VM/DOM tests, and the actual Chromium suite. It has read-only repository permission and no deployment step. Its YAML parsed successfully locally; CI has not been run here.

## Exact RED/GREEN evidence

Each implementation slice followed an observed failing assertion with its minimum repair and a passing run before moving on. Counts below refer to the suite run for that slice, not all suites together. The additional Training draft regression was already green when added, and required no implementation change.

| Slice | Actual RED result | GREEN result | Captured output |
|---|---|---|---|
| 01 Poll application | 0 pass / 1 fail; reload `1 !== 0` | 1 / 0 | [RED](evidence/01-red.txt), [GREEN](evidence/01-green.txt) |
| 02 Three-way 409 | 1 / 1; remote sibling missing | 2 / 0 | [RED](evidence/02-red.txt), [GREEN](evidence/02-green.txt) |
| 03 Queued pull / GET serialization | 2 / 2; lost sibling and concurrent PUT | 4 / 0 | [RED](evidence/03-red.txt), [GREEN](evidence/03-green.txt) |
| 04 Actual app boundary | 0 / 1; private-state hook absent | 1 / 0 | [RED](evidence/04-red.txt), [GREEN](evidence/04-green.txt) |
| 05 Profile command | 1 / 1; missing command, then stale `156 !== 160` | 2 / 0 | [RED](evidence/05-red.txt), [intermediate RED](evidence/05-red-command.txt), [GREEN](evidence/05-green.txt) |
| 06 Pending PUT / retries / reset | 6 / 1; reset bypassed CAS | 7 / 0 | [RED](evidence/06-red.txt), [GREEN](evidence/06-green.txt) |
| 07 Bootstrap / offline upgrade | 7 / 2; edits overwritten | 9 / 0 | [RED](evidence/07-red.txt), [GREEN](evidence/07-green.txt) |
| 08 Reopened form / transient UI | 3 / 1; previous remote field resubmitted | 4 / 0 | [RED](evidence/08-red.txt), [GREEN](evidence/08-green.txt) |
| 09 Reset / ack / tombstone | 10 / 1; deleted task remained | 11 / 0 | [RED](evidence/09-red.txt), [GREEN](evidence/09-green.txt) |
| 10 Rendered defaults | 4 / 1; untouched default overwrote remote | 5 / 0 | [RED](evidence/10-red.txt), [GREEN](evidence/10-green.txt) |
| 11 Intentional navigation | 5 / 1; Tasks display remained stale | 6 / 0 | [RED](evidence/11-red.txt), [GREEN](evidence/11-green.txt) |
| 12 Contract manifest | 0 / 1; manifest absent | 1 / 0 | [RED](evidence/12-red.txt), [GREEN](evidence/12-green.txt) |
| 13 Projection identity | 11 / 1; code-keyed slot lost | 12 / 0 | [RED](evidence/13-red.txt), [GREEN](evidence/13-green.txt) |
| 14 First upgrade projections | 12 / 1; stale local projection won | 13 / 0 | [RED](evidence/14-red.txt), [GREEN](evidence/14-green.txt) |

Prior candidate combined run (historical evidence): **21 tests, 21 passed, 0 failed, 0 skipped** ([full output](evidence/final-node.txt)). Build `--check` passed ([output](evidence/final-build.txt)); generated app/sync and the browser runner passed Node syntax checks. The baseline-only reload reproduction passed ([output](evidence/pinned-reproduction.txt)).

Artifact SHA-256:

Current exact artifact hashes are recorded in [release-manifest.json](release-manifest.json) and verified by `build --check`.

## Residual limits and scope

- The **host parent Chromium test passed**, as supplied by the owner. `.autopilot/browser-tools` is **parent-owned** and was read only, never installed into or changed here. This restricted rerun used `PLAYWRIGHT_PATH` from that directory but was blocked: its installed Playwright expects unavailable Chromium headless shell revision 1243 ([output](evidence/review-browser.txt)). The new real HTTP-cache browser test was blocked at localhost bind with `EPERM` ([output](evidence/review-cache-browser.txt)). The parent pass is not a claim that these newly revised browser/cache tests passed. Both remain required in CI; jsdom does not validate real layout, IME, background throttling or paint geometry.
- Remote content rendering is deliberately deferred as described above. Existing user-triggered renders can still reset unrelated form controls as in production; this candidate prevents sync-triggered replacement, not every existing application UI behavior.
- Same-leaf conflicts use deterministic local preference, not a conflict-resolution dialog. Arrays without a supported unique identity remain atomic. The DOM matrix includes repeated Jump, Social settings/content and Week saves and state/command preservation, but is not exhaustive across every editor and producer schema.
- First-upgrade core merging has the unavoidable old-client ancestor limitation. Command acknowledgement inference on that first upgrade only uses supplied result identities. Server-side command execution, schema migrations, storage quota failure, browser eviction, malformed server payloads and real multi-tab storage contention were not integration-tested. Keeping a full ancestor in metadata increases localStorage use.
- The review supplies live cache policy: Manual HTML and sync.js are immutable with max-age 604800, while app.js is no-cache. Offline contracts verify distinct versioned URLs and unchanged boot/app resolution. The new browser test warms old HTML/sync/app in a real HTTP cache, then checks the versioned entry boots generated files and old immutable URLs remain cached. It uses synthetic local headers/state and blocks service workers; production proxy query handling and installed service-worker behavior remain unverified. Existing unversioned entries may remain stale; the owner must use the versioned Manual entry after any separately authorized release.
- Writes are confined to `minimal-ui-v1/sync-stability/**`, `.github/workflows/dvizh-sync-stability.yml`, and `.autopilot/release.json`. The schema-1 release proposal maps the three generated artifacts to exact `/opt/dvizh/static/{app.js,sync.js,manual.html}` targets and `/{app.js,sync.js,manual.html}` HTTP routes, with `restarts: []`. No boot target, AI index, friend/control files, production writes, commits, pushes or deployment actions. Original test evidence and production snapshots remain pinned and untouched; new results use `review-*` evidence files.

Stopped for independent re-review. No release action has been taken.

## Independent-review repairs — 2026-09-09

Owner entry to supply after a separately authorized release: **`/manual.html?v=20260909-sync-stability-1`**. No AI index change is included. HTML changes only the sync script query to that same unique release version. An unversioned HTML cache hit can otherwise retain unversioned stale sync for seven days even when app.js revalidates.

TDD: [form RED](evidence/review-forms-red.txt) reproduced Jump `156 !== 160` on the second focused submission and Week `60 !== 80` on the second no-refill submission, before the fix. [Form GREEN](evidence/review-forms-green.txt) passed all 10 tests at that stage. The Jump regression also makes a third remote age change after a partial render, verifying refreshed sibling ancestors. Social settings full renders already passed; Social content now has analogous repeated-save coverage. [Cache contract RED](evidence/review-cache-red.txt) failed before adding HTML and the release proposal; [GREEN](evidence/review-cache-green.txt) passed after generation.

Final verification: **27 Node/VM/jsdom/contract tests passed, 0 failed** ([output](evidence/review-final-node.txt)); reproducible `build --check` passed ([output](evidence/review-build.txt)); the existing pinned baseline reproduction passed ([output](evidence/review-pinned-reproduction.txt)). Browser limitations are recorded above. CI has not been run here.

## Second and final permitted review-fix cycle — consumed field ancestors

The independent re-review reproduced a focused Jump field whose submitted edit did not advance its displayed ancestor. This cycle changes only that transition: command rebasing records changed submitted field values before reconciliation; after successful localStorage persistence those consumed ancestors advance to the submitted values. Untouched stale field ancestors stay unchanged. The update occurs before the existing partial render remembers the form. No broad refactor was made.

Strict TDD used the actual generated app.js and Manual HTML with pinned boot.js in jsdom. Both new tests initialize focused height 156, edit and submit 157, acknowledge that save through the harness's existing 450 ms upload debounce, accept remote 160 while the display stays 157, then submit again. The unedited case must preserve state and command 160; explicit reversion to 156 must produce state and command 156.

- [Actual RED](evidence/final-cycle-forms-red.txt): 11 passed, 2 failed. Unedited resubmit produced state/command 157 instead of 160; intentional reversion produced state/command 160 instead of 156.
- [Actual GREEN](evidence/final-cycle-forms-green.txt): all 13 DOM tests passed, including all previous untouched stale field and partial-render cases.
- [Full verification](evidence/final-cycle-node.txt): 29 passed, 0 failed, 0 skipped, retaining all previous tests. Command: `JSDOM_PATH=/home/exedev/.hermes/hermes-agent/node_modules/jsdom node minimal-ui-v1/sync-stability/tests/run.cjs`.
- [Build verification](evidence/final-cycle-build.txt): `node minimal-ui-v1/sync-stability/build.cjs` regenerated the release artifacts and contract manifest; `--check` passed. `candidate.diff` was regenerated from the pinned baseline and generated artifacts. Artifact hashes are in `release-manifest.json`.

This cycle writes only `minimal-ui-v1/sync-stability/**`. `.autopilot/release.json` and its targets are unchanged, as verified by the retained exact release-proposal contract test. No production, friend/control, or workflow files were written; no commit, push, or deployment occurred. Browser/CI checks were not rerun in this cycle; previously recorded limitations still apply. These passing tests do not establish independent review approval. Stopped for fresh final re-review; no further repair cycle is authorized.


## Additional owner-authorized mixed-cache cycle — stop for independent review

The minimal app boundary now checks that `DVIZH_SYNC.reconcile` is a function before tracking form ancestors, capturing submission state, rebasing commands, applying remote memory, or reconciling a save. With pinned OLD sync and boot plus NEW app, the original app save/command path runs. No second sync instance, second Storage patch, data clearing, navigation or forced reload was added. Generated sync.js and Manual HTML bytes are unchanged by this cycle. NEW sync + NEW app retains the full fix.

Strict TDD: the new jsdom matrix first failed specifically for NEW app + OLD sync with `TypeError: window.DVIZH_SYNC.reconcile is not a function` during Jump age 19→20 submission ([RED](evidence/mixed-cache-red.txt)). After the capability guard, all four combinations save actual Jump, Social settings and task forms, verify persisted commands and uploaded state, and report no application exceptions. Separate matrix cases check remote storage/memory behavior and original legacy reload attempts ([8 matrix tests](evidence/mixed-cache-green.txt)). The combined suite retains all existing 29 tests: **37 passed, 0 failed, 0 skipped** ([output](evidence/mixed-cache-node.txt)).

| App | Sync | Verified behavior / limit |
|---|---|---|
| OLD | OLD | Original forms save/upload; original reload attempt on remote changes remains. |
| NEW | OLD | Forms save/upload without missing-capability crashes; original reload attempt remains. No claim of in-memory reconciliation. |
| OLD | NEW | Forms save/upload before remote edits, but **unsafe after remote acceptance**: no private-memory hook. This is not a full compatibility pass. |
| NEW | NEW | Full boundary and all existing reconciliation/form/timer tests pass; no reload attempt. |

**Unresolved reverse-cache blocker:** the pinned old app cannot consume `DVIZH_MANUAL_STATE.applyRemote`. A remote height 160 reaches storage while the old form/private state remains 156. Submitting age 20 subsequently uploads height 156 in both state and command, without an exception. The separate [reproducible safety diagnostic](tests/reverse-cache-diagnostic.cjs) deliberately asserts preservation of 160 and exits nonzero ([failing evidence](evidence/mixed-cache-reverse-diagnostic.txt)). It is separate from the 37-test suite, and its failure must not be hidden by that suite's green result. This cycle does **not** prevent that corruption. The app-only guard cannot alter the pinned old app. A question about authorizing a narrow sync safety fallback remains pending; no such fallback was implemented and no broader sync behavior was changed. The candidate is **not cleared for release**.

The unique owner entry remains **`/manual.html?v=20260909-sync-stability-1`**, with versioned sync and unchanged no-cache app loading through pinned boot. Legacy cache may retain old reload behavior, but NEW app saves no longer break merely because reconcile is absent. This entry requirement is not proof that every reverse-cache/offline combination is safe.

The real HTTP-cache browser runner now first opens cached unversioned OLD Manual/sync with revalidated NEW app and submits age 19→20, checking local command and server save before checking the versioned entry. Both browser runners accept `CHROMIUM_PATH` for the supplied existing binary. This sandbox blocked the cache runner at localhost bind (`EPERM`) and the DOM runner during Chromium launch (`SIGTRAP`); neither passed here ([cache output](evidence/mixed-cache-browser.txt), [DOM output](evidence/mixed-cache-browser-dom.txt)). Host parent can run the exact runners outside the sandbox with:

```sh
PLAYWRIGHT_PATH=/home/exedev/.hermes/dev/dvizh/browser-tools-sync-stability/node_modules/playwright CHROMIUM_PATH=/home/exedev/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome node minimal-ui-v1/sync-stability/tests/cache-browser.cjs
PLAYWRIGHT_PATH=/home/exedev/.hermes/dev/dvizh/browser-tools-sync-stability/node_modules/playwright CHROMIUM_PATH=/home/exedev/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome node minimal-ui-v1/sync-stability/tests/browser.cjs
JSDOM_PATH=/home/exedev/.hermes/hermes-agent/node_modules/jsdom node minimal-ui-v1/sync-stability/tests/reverse-cache-diagnostic.cjs
```

Artifacts, manifest and `candidate.diff` were regenerated. [Build and byte-for-byte check](evidence/mixed-cache-build.txt) passed; [pinned reload reproduction](evidence/mixed-cache-pinned-reproduction.txt) passed. The manifest explicitly records the unsafe reverse combination. All cycle writes are under `minimal-ui-v1/sync-stability/**`; the release proposal and workflow were unchanged. No production/secrets/friend/control accesses, installations, commits, pushes or deployment actions were performed. Stopped after the one authorized app fix cycle for independent review, with the reverse-cache blocker and host-browser verification outstanding.

## Owner-authorized protective-mode review fixes (2026-09-09)

This section supersedes earlier cycle status for the current candidate. Ready for independent re-review only; no release approval is claimed.

The sync captures the stored initial state before writing the client ID or starting remote bootstrap. That snapshot is independent of every intercepted pre-boot save. When the pinned old app loads, the original plus all pre-boot snapshots enter quarantine history, alongside any previous quarantine; the explicit update archive includes them. Tests cover stored Jump age 25 against remote age 19 both with ordinary old-app bootstrap and with additional pending ages 26 and 27.

Client-ID reads/writes and startup metadata reads are guarded. A startup storage failure enters protective mode before boot loads the app, skips initial synchronization, exposes a Russian alert and a labeled, visible, read-only recovery textarea, and intercepts subsequent state saves into quarantine. If quarantine persistence also fails, snapshots remain available in memory. Push/manual/online attempts cannot upload. Tests inject `QuotaExceededError` for the client-ID write alone and for every write, using the actual generated app and pinned boot; both preserve age 25 in recovery without application exceptions.

The cache fixture had two independent scenarios sharing server state while the first browser context remained open. Its pending release-bootstrap PUT could arrive after the reverse scenario advanced height from 156 to 160. The server previously accepted that stale revision unconditionally. The deterministic two-window regression reproduces **160 -> 156 at the immediate post-update checkpoint without CAS**, while confirming the protective window made zero PUTs before update. With CAS enabled, that same delayed request is rejected, reconciliation preserves height 160, and the archive retains saved age 20 and unsaved age 21. A later updated-tab bootstrap can repair the non-CAS fixture again; this does not excuse the failing immediate checkpoint. This establishes a fixture interference mechanism matching the host symptom, not an observed host-browser trace in this sandbox.

The browser runner now closes the first context before resetting the shared scenario. Browser and jsdom fixtures share `tests/state-server.cjs`: PUT accepts only the current `baseRevision`; conflicts return HTTP 409 with canonical state/revision and leave state unchanged. The browser's server-height-160, quarantine-age-20, unsaved-age-21 and zero-before-update-PUT assertions remain intact.

Evidence (commands run from `minimal-ui-v1/sync-stability` unless otherwise stated):

- [Initial RED](evidence/re-review-red.txt): five existing protective tests passed; the original/pending snapshot test failed with `missing original/pending age 25: 27`; both startup quota cases threw `DOMException`. Command: `JSDOM_PATH=/home/exedev/.hermes/hermes-agent/node_modules/jsdom node tests/protective.test.cjs`. During the first fix run the quota fixture also needed the app's required `tone` field; [intermediate output](evidence/re-review-first-green.txt) is retained.
- [Final full suite](evidence/re-review-final-green.txt): **49 passed, 0 failed, 0 skipped**, retaining all 43 existing tests and adding six tests. Command: `JSDOM_PATH=/home/exedev/.hermes/hermes-agent/node_modules/jsdom node tests/run.cjs`. Includes both CAS and deliberately non-CAS interference diagnostics; the latter asserts the unsafe fixture's regression rather than certifying it as safe.
- [Build/check](evidence/re-review-build.txt): `node build.cjs` and `node build.cjs --check` passed. `release/sync.js`, source/artifact hashes in `release-manifest.json`, and baseline-to-release `candidate.diff` were regenerated. Generated app/HTML behavior is unchanged by this review-fix cycle.
- [Host command before](evidence/re-review-host-before.txt) and [after](evidence/re-review-host-after.txt): `CHROMIUM_PATH=/home/exedev/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome PLAYWRIGHT_PATH=/home/exedev/.hermes/dev/dvizh/browser-tools-sync-stability/node_modules/playwright node tests/cache-browser.cjs` both exited 1 at `listen EPERM ... 127.0.0.1`, before Chromium could launch. **No host Chromium PASS is claimed**; the corrected runner still requires an unrestricted host rerun.

Only `minimal-ui-v1/sync-stability/**` was written during this cycle. Existing staged/unstaged work outside it was left untouched. No production, friend/control, or credential access; no commit, push, installation, or deployment. Stopped for independent re-review.
