> Latest protective-mode cycle: **43/43 mandatory Node tests pass**, including server height160 / quarantined age20 / zero stale PUT. Explicit version-2 update retains drafts in a verified archive for manual recovery; automatic form restore is unavailable and warned before navigation. Browser checks remain sandbox-blocked. See [current candidate report](CANDIDATE-REPORT.md). Stopped for independent review. Earlier status below is historical.

> Latest mixed-cache cycle: app capability guard fixes OLD sync + NEW app saves. **NEW sync + OLD app remains unsafe after remote edits**, with a failing standalone safety diagnostic. See [current candidate report](CANDIDATE-REPORT.md). 37 main-suite tests pass; browser runs are sandbox-blocked. No release approval.

> Independent-review update: host parent Chromium test passed (owner-supplied result). `.autopilot/browser-tools` is parent-owned and untouched. Restricted reruns and the new cache test are blocked as detailed in [CANDIDATE-REPORT.md](CANDIDATE-REPORT.md). Current candidate includes generated Manual HTML with versioned sync delivery and a schema-1 release proposal; historical snapshots and evidence below remain unchanged.

> Historical diagnosis. The implemented candidate, offline reproduction instructions, RED/GREEN evidence and limits are in [CANDIDATE-REPORT.md](CANDIDATE-REPORT.md). The original producer diagnostic below is not part of candidate CI.

# DVIZH Manual reload diagnosis — 2026-09-09

The proven defect is that sync uses full-page reloads to apply remote state, while Manual keeps its selected view only in memory and initializes it to `home` (Сейчас). Both polling and conflict handling can cause the reload, including cases with no meaningful remote edit. This diagnosis reproduces actual production `location.reload()` calls with synthetic data. It does **not** establish which live revision/writer caused a particular observed incident; no user state, database, credentials, API responses, or runtime logs were read.

All new files are in this directory. Production was read-only; no production API requests, module execution with production DB access, edits outside this directory, commits, pushes, or deployments were performed. `sync.js` was read in full. Source fingerprints are in [source-sha256.txt](source-sha256.txt).

## Deterministic reproduction

From the worktree root:

```sh
node minimal-ui-v1/sync-stability/reproduce.cjs
python3 -B minimal-ui-v1/sync-stability/check-producer.py
```

Node version used: v26.8.1. No dependencies/install required. Exact captured output: [node-output.txt](node-output.txt), [producer-output.txt](producer-output.txt).

`reproduce.cjs` evaluates the unmodified `/opt/dvizh/static/sync.js` inside a fresh Node VM for each case. It provides isolated fake Storage, fetch, clock/Date, timers, DOM, navigator, and location. The initial GET returns synthetic revision 10 into empty local storage; bootstrap makes no PUT and no reload. Actual `boot.js` is then evaluated; fake script loading dispatches its load event to call `markAppLoaded()`. **The full app is not evaluated**; its route reset is traced from source below. Subsequent GET/PUT responses come exclusively from an asserted FIFO in memory. `location.reload` records invocations rather than navigating. No real fetch is available in the VM.

| Synthetic event after bootstrap | Actual reload calls | Fake PUTs |
|---|---:|---:|
| Poll revision 11, identical state, newer response-envelope `updatedAt` | 0 | 0 |
| Poll: only `jumpLab.coachPacket.exportedAt` changes | 0 | 0 |
| Poll: only `__sync.updatedAt` changes | 1 at 8120 ms | 0 |
| Poll: only task `_syncUpdatedAt` changes | 1 at 8120 ms | 0 |
| Poll: task object key order changes, same values | 1 at 8120 ms | 0 |
| Poll: both `exportedAt` and `__sync.updatedAt` change | 1 at 8120 ms | 0 |
| Poll: actual remote task title/timestamp change | 1 at 8120 ms | 0 |
| Local write → 409 with identical state → successful retry | 1 at 570 ms | 2 |
| Local write → 409 with remote task addition → successful retry | 1 at 570 ms | 2 |
| Queued local write → identical newer pull → successful push | 1 at 570 ms | 1 |

Assertions verify remote state is stored in each poll case; the conflict retry uses base revisions 10 then 11 and preserves the synthetic local edit and remote task addition. These are targeted examples, not a proof that all production state fields merge safely. The fake clock starts at 0; poll fires at 8000 and schedules reload 120 ms later. Local pushes debounce for 450 ms and schedule reload 120 ms after success.

## Three hypotheses

**1. Polling reload: proven.** [sync.js:398](/opt/dvizh/static/sync.js:398) skips pulls only when not ready, pushing, or the document is hidden. It accepts a revision greater than local metadata, normalizes the remote state (or merges if queued), persists it, and schedules `location.reload()` if the app is loaded and `manualJumpChanged` is true. The comparison at lines 391–414 clones the **whole state** and removes only `jumpLab.coachPacket.exportedAt`. It retains sync clocks, entity clocks, other projection metadata, and JSON property order. Its name does not mean it compares only Jump/Training. Focus and visibility-return events also call pull, so reloads need not wait for the next 8-second interval.

If a local push is queued, lines 420–422 set `reloadAfterSync = appLoaded` without checking `manualJumpChanged`. The queued-pull test demonstrates this additional path without a 409.

**2. Conflict reload: proven, requires a local upload.** [sync.js:318](/opt/dvizh/static/sync.js:318) handles a 409 containing state by merging the latest stored local state, persisting the server revision, setting `reloadAfterSync = appLoaded`, and retrying once. A successful `pushLatest()` schedules reload at [sync.js:374](/opt/dvizh/static/sync.js:374). There is no semantic-change check. An entirely idle tab does not need this path to reproduce the bug: polling alone suffices. The harness proves the success-after-conflict case, not network-failure timing variants.

The server's [revision check and increment](/opt/dvizh/server.py:95) explain the conflict: stale `baseRevision` gets 409 with current state; every accepted PUT increments revision, even without an identical-content early return. Revision change alone still does not trigger the ordinary nonqueued browser reload, as the control test proves.

**3. Service worker reload: unsupported by current source.** [app.js:2100](/opt/dvizh/static/app.js:2100) registers `./sw.js`; it has no `controllerchange` reload handler. Current [sw.js](/opt/dvizh/static/sw.js:1) calls `skipWaiting`, deletes caches, claims clients, and forwards GET requests with `no-store`. It does not call client navigation or send a reload message. Its actual install/activate/fetch handlers run in an isolated VM with fake caches/clients/fetch and produce only those expected operations. `manual.html` loads sync then boot, and boot only waits for sync and loads app. This rules out an explicit SW reload mechanism in these current files, not unknown historical code already installed in a user's browser.

## Why Training returns to Сейчас, and what else is lost

- [manual.html:203](/opt/dvizh/static/manual.html:203) marks `view-home` active; desktop/mobile home navigation also starts active. Scripts are loaded at lines 1017–1018.
- [boot.js:4](/opt/dvizh/static/boot.js:4) waits for `DVIZH_SYNC_READY`, then loads app.js and marks it loaded on the load event.
- [app.js:163](/opt/dvizh/static/app.js:163) reads persisted state and independently initializes `activeView = 'home'`.
- [navigate():333](/opt/dvizh/static/app.js:333) sets that variable, toggles DOM classes, updates the title, and renders Training. It does not persist the view in a URL, history state, or storage. Reloading `/manual.html` therefore cannot restore Training.
- [app.js:173](/opt/dvizh/static/app.js:173) initializes focus time from configured duration, `running: false`, and `startedAt: null`. Rescue timer state also starts fresh. Unsaved DOM form values, open panels, and transient editor state disappear when the document is replaced.

This route conclusion is a source trace, not a claimed full-browser end-to-end test. The reload invocations themselves are dynamically tested.

## Background producers: what current source actually establishes

The relevant recurring producer is the **Jump web bridge**, [jump_web_bridge.py:464](/opt/dvizh-jump/dvizh_jump/jump_web_bridge.py:464). Its default interval is **5 seconds**, configurable through `DVIZH_JUMP_INTERVAL` (line 69); the recurring loop is at line 516. Each successful cycle builds `jumpLab`, including `coachPacket = store.export_bundle(chat_id)` (line 423). [jump_store.py:745](/opt/dvizh-jump/dvizh_jump/jump_store.py:745) creates a fresh `exportedAt` each export.

However, **the currently installed producer explicitly suppresses export-timestamp-only uploads**: `normalized()` at line 429 excludes `syncedAt`, optimistic fields, `selectedDay`, and nested `coachPacket.exportedAt`. `merge_projection()` at line 443 returns unchanged if that comparison matches; `sync_once()` skips PUT on unchanged. When content differs, it adds `jumpLab.syncedAt` and uploads using the fetched revision.

`check-producer.py` AST-selects and executes only the actual pure `canonical`, `normalized`, and `merge_projection` functions with synthetic input. It proves:

```text
PASS actual Jump merge_projection: exportedAt-only changed=False => sync_once skips PUT
PASS actual Jump merge_projection: exercise addition changed=True, stamps syncedAt, preserves input
```

Thus, “Jump exports every five seconds, therefore every five seconds it writes state and reloads Manual” is **not supported by these current files**. Neither producer nor ordinary consumer treats `exportedAt` alone as a change. The `exportedAt + __sync.updatedAt` harness case is deliberately synthetic, not a claim that Jump stamps `__sync.updatedAt`.

Other source-confirmed recurring publishers are Training (default 5 seconds, `training_web_bridge.py:373`), Social (5 seconds, `social_web_bridge.py:317`), Weekly (15 seconds, `weekly_web_bridge.py:387`), and Telegram integration (20 seconds, `bridge.py:665`). Their source gates uploads on changes; Training excludes `syncedAt`, Social retains its previous timestamp during comparison, Weekly compares its projection fields, and integration stamps `lastSyncAt` only after a detected difference. They can publish real changes while Manual is idle, but their polling intervals alone do not prove recurring writes. Training's `sync_slots_from_schedule()` does update slot timestamps every projection build, but those slot timestamps are not emitted in `trainingHub.planSlots`; that DB-side timestamp churn is not by itself proof of web revision churn. These statements come from source only; no stores or services were run.

The direct writer of `__sync.updatedAt` is browser `stampState()` ([sync.js:108](/opt/dvizh/static/sync.js:108)): every intercepted state write stamps it, even a semantic no-op. A second tab/device saving can therefore supply the metadata-only poll fixture. App initialization can save a missing focus-task selection and an invalid/missing daily plan; these are conditional writes, not evidence of an unconditional repeating producer. App's 1400-ms `renderAiProposals` interval renders DOM and is not an upload loop.

The source-only boundary leaves the **actual live writer and changed field unresolved**. No claim is made about deployed process uptime, configured intervals, observed revision cadence, or a user's installed historical service worker. A later authorized runtime investigation could collect only revision numbers and changed field paths to distinguish these cases without dumping state values.

## Narrow repair options — not implemented

1. **Separate data synchronization from UI invalidation in sync.js and app.js.** Keep accepting/storing revisions and preserving all metadata. Use a stable, explicitly defined render comparison that ignores known transport metadata and property order. Do not remove clocks/tombstones from stored or uploaded state: they drive merge ordering and deletion semantics. A comparator correction alone stops false positives but still reloads on legitimate remote changes, so it is only part of a repair.

2. **Replace both reload paths with an explicit app state-application hook.** Update app's closure-held `state` from the accepted/merged snapshot without stamping it as a new local edit, and selectively refresh affected displays. Preserve `activeView`, open panels, dirty form values, cursor/focus/selection, scroll, and running timer objects/deadlines. Avoid an unconditional `renderAll()`: renderers assign form values and replace DOM. Queue conflicting remote edits for a dirty entity until submit/cancel, and reconcile submissions against the latest accepted base. Keep network sync progressing while the editor stays intact. Apply the same hook to ordinary pulls, queued pulls, and 409 retries.

3. **For a smaller staged UI change, defer display application while busy, while keeping the remote snapshot/revision and local outbox current.** Apply safely after the relevant form/timer becomes idle, or on an explicit update action. This still needs an in-memory state contract so the next save cannot serialize a stale app snapshot over remote data. Route persistence is useful for intentional page refresh but alone cannot preserve unsaved forms or running timers.

Before either state-application approach, account for domain ownership: existing `mergeStates()` merges core arrays/records, but arbitrary top-level fields such as `trainingHub`, `jumpLab`, and command outboxes inherit the settings winner through object spread (sync.js:234–246). Blindly reusing it is not a general guarantee that server projections and pending commands survive conflict. Preserve authoritative projections plus pending commands by identity and reconcile edited fields against their base. The harness's task-array preservation assertion is deliberately narrower than that requirement.

Producer-side cleanup should be based on an identified changing field and preserve actual remote edits. Keep the current Jump export-timestamp filter; adding it again would not fix this version. Increasing intervals, disabling sync, ignoring all remote Training changes, merely saving the route, or deleting reload calls while leaving app state stale do not satisfy the preservation requirements.

Acceptance coverage for a future fix should retain these fixtures and add actual dirty Training forms, an active timer, remote deletion/reset, pending command acknowledgements, simultaneous local/remote edits, and a save after remote application. No fix was implemented in this investigation.

## Second and final candidate review-fix cycle

The historical investigation above is unchanged. The candidate's consumed-field ancestor repair and actual generated-app/Manual jsdom RED/GREEN results are documented in [CANDIDATE-REPORT.md](CANDIDATE-REPORT.md#second-and-final-permitted-review-fix-cycle--consumed-field-ancestors): two reproduced failures, then 13/13 DOM tests and 29/29 combined tests passing. Generated artifacts/manifest were rebuilt, the build check passed, and candidate.diff was refreshed. This cycle writes only sync-stability files; release proposal targets are unchanged. Stopped for fresh final re-review, without claiming review approval.

## Protective-mode review follow-up (2026-09-09)

The owner-authorized candidate follow-up preserves immutable initial and pending snapshots and adds fail-closed startup storage recovery. It also reproduces the reported height-156 cache failure deterministically as a delayed earlier-context PUT accepted by the non-CAS synthetic server; browser scenarios are now isolated and the shared fixture enforces revision CAS without weakening the browser assertions. The full suite retains the previous 43 tests and passes 49/49. Build, manifest and candidate diff are regenerated. The exact host command remains blocked here by localhost `listen EPERM`, so no host-browser pass is claimed. See the [current candidate evidence and limits](CANDIDATE-REPORT.md#owner-authorized-protective-mode-review-fixes-2026-09-09). Stopped for independent re-review without commit, push or deployment.
