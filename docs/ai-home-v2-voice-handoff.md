# Stable AI Home v2 voice handoff

Scope: local source preparation only; no live promotion, GitHub push, API writes,
service operations, server policy changes, or installation.

Evidence: managed base ba8214911f5942fdbf36269e1e992eb7607b40f8
ai-home-v2/ai-home-v2.js exactly matched the read-only live stable JS.
The live ai-home-v2-voice.js differed only in the voice block. The owner has
confirmed that preview permission, recognition, Hermes request and answer work
on Android. That device verification is of preview, not this new stable build.

Changes:
- Transfer preview permission priming and cancellable voice session into stable JS.
- Await getUserMedia({audio:true}), release tracks in finally, then construct/start
  SpeechRecognition or webkitSpeechRecognition. No recognition after denial or
  cancelled/hidden session. Missing mediaDevices fails closed to text.
- Preserve stable text/API/answer/hold navigation code and CSS.
- HTML differs only in JS query version (20260905-3.1-voice-20260908) for immutable-cache busting.
- No shared Manual/SW assets, backend, auth, Jump Lab or state schema changes.

Tests use deterministic DOM/browser API doubles and temporary installer sites,
never the live API. Voice covers permission order, track release, denial/error,
late grants after cancel/Escape/hide, webkit, listening/thinking/answer, and text.
Isolation compares non-AI production sources with the exact managed base.
Old bootstrap tests use their actual pinned release via git show rather than
passing the new working tree to immutable old checks. Full git history containing
d6418224eae292417a645b2a73da157d939526b9 and the managed base is required for these tests.
Do not weaken blob verification or change old release pins to accommodate this diff.

Verification in managed worktree:
- quick passed (git diff --check).
- ai-home-v2 profile passed: 99 Node tests, 2 Python bridge contract tests,
  JavaScript syntax check. No live API calls in tests.
- Independent read-only Codex review: passed, no security or logic blockers.
- Browser smoke was attempted but could not start: ModuleNotFoundError for
  playwright in the available Python. No packages installed on the server.
  Run browser CI and verify the accepted stable build on Android before release.
- Read-only final live-snapshot hashes and service states match the initial snapshot.

GitHub/CI/release work belongs to ChatGPT after accepting this handoff.
The existing old pinned installers do NOT publish this new source. The generic
installer deliberately refuses a preview update when assets are already used by
stable root. Prepare a separately reviewed immutable stable-update release from
accepted source; preserve Manual/SW assets and publish the updated JS cache-key
with its JS. This handoff does not contain or execute a deployment command.
The already-working microphone=(self) policy is a prerequisite, not part of this diff.
