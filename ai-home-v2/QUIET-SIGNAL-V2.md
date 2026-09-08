# Quiet Signal v2 — AI Home implementation

Implemented in the managed worktree only. Production `/opt/dvizh/static/index.html`,
`ai-home-v2.js`, and `ai-home-v2.css` were read and compared without modification.
The approved `20260908-203740-979887/minimal-ui-v1/design/quiet-signal-v2.html`
was read without modification. No commit, push, deployment, sudo, dependency
installation, secret access, or changes to Manual/root application sources.

## Exact edited paths

- `ai-home-v2/index.html`
- `ai-home-v2/ai-home-v2.css`
- `ai-home-v2/ai-home-v2.js`
- `ai-home-v2/QUIET-SIGNAL-V2.md` (this report)
- `tests/ai-home-v2/client.test.cjs`
- `tests/ai-home-v2/quiet-signal.test.cjs`
- `tests/ai-home-v2/browser_test.py`
- `tests/ai-home-v2/voice-isolation.test.cjs`
- `tests/ai-home-v2/stable_voice_release_test.py`

## Behavior and design

Visible ДВИЖ / QUIET SIGNAL header, current ИИ link, and real Ручной anchor
`/manual.html?v=20260908-quiet-signal-2`. The composer microphone retains
`aiOrb`, recognition permission handling, long hold, Alt+M, Escape, and text
commands. Auth retains its original root/preview destination logic. API request,
revision/conflict, ambiguous-write reconciliation, timeout and polling behavior
remain intact. No mock requests, sample answers, or state controls were added.

The ribbon uses the approved prototype's projected twisted surface algorithm:
32 shaded strips, depth ordering, perspective, and state-dependent amplitude.
Animation is optional, guarded against throwing/missing SVG, media-query and
animation APIs, bounded in time step, paused on pagehide/visibility/reduced motion,
and backed by static SVG. Speaking begins with utterance `onstart`, ends with
`onend`/error/cancellation, and ignores stale callbacks. Listening/thinking follow
the real client state. No CDN or new runtime dependency.

The live speech implementation was absent from the repository base. It is now
preserved: initial history stays silent; fresh request IDs dedupe automatic
speech; all answer text is chunked at <=220 UTF-16 units without splitting pairs;
Russian voices are requeried; strong utterance references and cancellation remain.

Dark palette, mint send button, short visible help, >=44px controls, scrollable
answers and content, keyboard viewport height/offset, safe-area padding, and
pinch-zoom preservation. New answers scroll into view once; repeated snapshots
preserve answer scroll. CSS and JS versions retain the legacy `20260905-3` prefix
and add `quiet-signal-2` (JS also retains the live speech version lineage).

Manual navigation alone may save one unsent draft in sessionStorage, at most
12,000 characters. Restoration expires after ten minutes (not a timed deletion
while Manual is open). Unresolved submissions and stale saved drafts are excluded
to prevent replay under a new request ID. A saved draft is consumed on load or
BFCache return. Empty,
mode-command, oversized, credential-like, JWT and long token-like text is not
stored. Malformed/expired records and unavailable storage are harmless. No
localStorage, API state, answers, auth credentials or voice interim transcript is
persisted by this feature. Content heuristics cannot identify every possible
secret; this is a conservative filter, not a general secret classifier.

## TDD evidence

Each implementation cycle followed its failing regression run:

| Cycle | RED evidence | GREEN |
|---|---|---|
| Live speech preservation | `live speech fix...`: expected 1 utterance, got 0; 64 pass / 1 fail | 65 client tests pass after restoring live JS |
| Ribbon/state/Manual draft | expected 32 strips, got 0; `onstart is not a function`; Manual navigation array empty | 69 client tests pass |
| Shell/layout | missing header/Manual/ribbon and `--ai-top` | 2 Quiet Signal tests pass |
| Answer visibility / credential filter | expected one scroll, got 0; JWT was stored | 73 client tests pass |
| BFCache draft cleanup | expected zero stored records, got 1 | final 78 client tests pass |

Raw execution evidence is in `/tmp/ai-red-speech.log`,
`/tmp/ai-red-ribbon.log`, `/tmp/ai-red-layout.log`,
`/tmp/ai-red-edges.log`, `/tmp/ai-red-bfcache.log`, and corresponding
`/tmp/ai-green-*.log` / `/tmp/ai-final-*.log` files in this VM.
Additional coverage checks actual speech errors, history suppression, Unicode
chunking, voice selection, modified anchor clicks, state transitions, renderer
failures, draft bounds/expiry/storage denial and keyboard viewport offsets.

Existing behavioral assertions were retained. Intentional expectations changed:
old black/no-nav/orb-span visuals, requested Manual navigation destination, and
old markup/CSS byte equality. The historical stable voice installer now reads
its original pinned Git fixture rather than the intentionally changed working
UI; its original blob hashes, rollback and protected-file checks remain intact.
The generic installer still validates `location.assign(manualTarget())`.
Browser screenshots use repository `test-results/`, matching the existing CI
artifact upload. The implementation sandbox could not run Chromium; the host
subsequently verified the real client through an isolated CDP browser fixture.

## Implementation sandbox verification (historical)

Commands run before implementation and again after final implementation:

```
node --test tests/ai-home-v2/*.test.cjs
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests/ai-home-v2 -p '*_test.py'
```

Baseline Node: 4 test files passed, 4 failed. Final Node: 5 passed (including new
Quiet Signal tests), same 4 failed. The affected files are bootstrap,
promote-bootstrap, promote-relative-path-fix and voice-isolation; direct runs
identify `spawnSync git EPERM` in the managed environment. No assertions were
removed to suppress these failures.

Direct final client run: **78/78 pass**. Installer: **16/16 pass**. Quiet Signal:
**2/2 pass**. Routing: **2/2 pass**. Service routing: **3/3 pass**.
`node --check ai-home-v2/ai-home-v2.js` and `git diff --check` pass.

Python baseline and final: 10 tests, 9 errors (socket creation denied and missing
Playwright); historical pinned-asset check passes. Full browser tests could not
execute. Cached Chromium was also tried without installation, but exited 133:
`setsockopt: Operation not permitted`. No rendered screenshots or visual QA pass
are claimed. Desktop/mobile/real keyboard, device microphone and device speech
verification remain required in an environment that permits browser execution.
