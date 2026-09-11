---
name: dvizh-dev
description: Develop, test, push, gate and safely deploy DVIZH changes from Telegram through Hermes Autopilot v2.1. Uses isolated worktrees, GitHub CI, a root-owned DVIZH-only push gate and an allowlisted release gate with rollback.
version: 2.1.0
author: DVIZH
platforms: [linux]
metadata:
  hermes:
    tags: [dvizh, development, autopilot, github, ci, release, telegram, isolation]
    category: dvizh
---

# DVIZH Dev Mode v2.1 — Autopilot

Use this skill for DVIZH code bugs, features, frontend/backend work, tests, release preparation and deployment requests.

The owner explicitly wants the normal workflow to happen inside Telegram without copying commands between Telegram, ChatGPT and a shell.

## Critical repository isolation

The GitHub repository also contains a separate project belonging to the owner's friend. DVIZH Autopilot must never modify that project.

Treat these as foreign/out-of-scope for DVIZH, including descendants where applicable:

- `src/`
- `migrations/`
- ordinary root `tests/test_*.py`
- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.server.yml`
- `pyproject.toml`
- `alembic.ini`
- root `Makefile`
- root `README.md`

Do not edit, format, rename, delete, merge, refactor or "fix" those paths during a DVIZH job even if they look related.

The root-owned `dvizhgitpush` gate independently checks every committed path before GitHub push. Unknown paths and friend-project paths are rejected. Hermes cannot read the private deploy key and cannot bypass this gate with direct `git push`.

Autopilot control-plane files (`hermes-dev-v2/**`, its installer and its gate workflows) are also self-protected: Hermes jobs cannot modify their own guardrails. Guardrail changes require a separate owner/ChatGPT maintenance release.

## Modes

Interpret these prefixes when present:

- `/dev inspect` — read-only diagnosis. Never create/deploy changes unless the user later asks.
- `/dev safe` — develop + test + commit + guarded GitHub push + CI. Production requires explicit user approval in Telegram.
- `/dev auto` — develop + test + commit + guarded GitHub push + CI + automatic deployment only when the root release gate classifies the release as auto-safe. Privileged releases still require Telegram approval.

If the user asks to "сделай сам", "исправь полностью", "автопилот", or otherwise asks for end-to-end execution without naming a mode, use **auto**.

If the user asks only to inspect/diagnose, use **inspect**.

For ambiguous development requests default to **safe**.

## Architecture

Normal auto flow:

**Telegram → Hermes/Astra → managed worktree → local tests → commit → root-owned `dvizhgitpush` path gate → root-only repo deploy key → `hermes/dev/*` branch → GitHub Actions → immutable release manifest → root-owned `dvizhrelease` gate → backup → atomic apply → HTTP/smoke verification → rollback on failure → Telegram report.**

Hermes never receives arbitrary root shell access and never receives the GitHub private key.

`sudo` is allowed only through these two installed root-owned gates:

```bash
sudo -n /usr/local/sbin/dvizhgitpush ...
sudo -n /usr/local/sbin/dvizhrelease ...
```

Do not run any other sudo command from this skill.

## Mandatory start

For development work first run:

```bash
dvizhautopilot doctor
```

`doctor` must report:

- GitHub public API reachable;
- `git_push_gate.ok=true` and `authorized=true`;
- `release_gate.ok=true`;
- `private_git_key_visible_to_hermes=false`.

If the GitHub push gate says the deploy key is not authorized, stop and tell the owner the one-time GitHub Deploy Key setup is incomplete. Never ask the owner to paste a private key or token.

Create the managed job:

```bash
dvizhautopilot new <inspect|safe|auto> '<problem>'
```

For `inspect`, remain read-only.

For `safe` or `auto`, record the returned job id and use the managed worktree from:

```bash
dvizhdevctl where <job-id>
```

All edits belong only in that worktree and only in DVIZH-allowed paths.

## Production boundary

Outside `dvizhrelease`, production is read-only.

Never directly edit/remove/chmod/move/write:

- `/opt/dvizh/**`
- `/opt/dvizh-ai-home/**`
- `/etc/**`
- `/usr/local/**`
- `/var/lib/dvizh/**`

Never directly run service mutation, DB mutation, firewall/SSH/auth changes, package installation, or production installers.

Allowed read-only diagnostics include approved `dvizhctl` commands, non-secret source inspection and `dvizhdevctl live-snapshot`.

Never inspect or expose `.env`, auth JSON, tokens, cookies, API keys, SSH private keys or credential stores.

## Development loop

1. Diagnose with the smallest evidence needed.
2. Edit only the managed worktree and DVIZH-owned paths.
3. Run automatic local profiles:

```bash
dvizhautopilot test-auto <job-id>
```

If additional narrow tests are necessary, run them inside the worktree without changing production or installing server packages.
4. Review the diff:

```bash
dvizhdevctl diff <job-id>
```

Before commit, explicitly confirm no friend-project path appears in the diff.
5. Commit:

```bash
dvizhdevctl commit <job-id> '<short message>'
```

6. Push only through the guarded command:

```bash
dvizhautopilot push <job-id>
```

Never run raw `git push`; the private key is intentionally root-only. Never force-push, merge or rebase an autonomous branch.

7. Wait for GitHub Actions:

```bash
dvizhautopilot wait-ci <job-id> --timeout 1200
```

If CI is red, inspect compact failure metadata:

```bash
dvizhautopilot ci-failures <job-id>
```

Fix in the same managed worktree, rerun local tests, commit, guarded-push and wait again. Limit autonomous CI-fix attempts to 3. After 3 failed rounds, stop and report the blocker instead of looping indefinitely.

## Release manifest

A deployable task must include a committed JSON manifest, normally:

```text
.autopilot/release.json
```

Schema:

```json
{
  "schema": 1,
  "name": "short release name",
  "operations": [
    {
      "source": "ai-home-v2/index.html",
      "target": "/opt/dvizh/static/index.html",
      "http_path": "/"
    }
  ],
  "restarts": []
}
```

Do not put secrets in manifests.

The root release gate, not Hermes, decides whether production targets are safe, approval-required or denied.

Current auto-safe production targets are intentionally narrow:

- `/opt/dvizh/static/index.html`
- `/opt/dvizh/static/ai-home-v2.js`
- `/opt/dvizh/static/ai-home-v2.css`

They require their exact HTTP routes and no service restart.

Manual/shared frontend, backend and selected AI bridge targets are approval-required. Auth, DB storage, SSH/firewall, `/etc`, systemd definitions and arbitrary filesystem targets are denied by this gate version.

## Release flow after green CI

Create the immutable proposal:

```bash
dvizhautopilot release-propose <job-id> .autopilot/release.json
```

Then plan it through root gate:

```bash
dvizhautopilot release-plan <proposal-path>
```

### Auto-safe release

If the result says `"approval_required": false` and the job mode is `auto`, apply immediately:

```bash
dvizhautopilot release-apply <proposal-path>
```

The gate owns backup, atomic writes, HTTP byte checks and rollback.

### Approval-required release

If `approval_required` is true, the plan returns an exact phrase:

```text
APPROVE <proposal-id> <token>
```

Send a concise Telegram explanation of what will change, what service (if any) will restart, and that backup/rollback are automatic. Then ask the owner to reply with that exact approval phrase.

**Do not call release-apply until a later user Telegram message contains that exact phrase.** The fact that the model has seen the token in command output is not approval.

After the owner explicitly replies with the exact phrase, pass only the token to:

```bash
dvizhautopilot release-apply <proposal-path> --approval <token>
```

Approval expires after 30 minutes and is bound to the exact proposal+manifest digest.

Never manufacture, infer or self-approve the owner's confirmation.

## Failures and rollback

If `dvizhrelease` reports deployment failure, it attempts rollback automatically. Do not manually patch production afterward.

Report the failure reason, whether rollback was confirmed, backup path if present, and current CI commit. If rollback is not confirmed, stop all autonomous work and alert the owner immediately.

## Telegram progress style

Do not dump raw logs. Send updates only at meaningful milestones: diagnosis, local tests, GitHub/CI, approval if needed, and deployment verification.

A successful auto report should look like:

```text
✅ Готово
Причина/задача: ...
Commit: <sha>
CI: green
Deploy: verified
Backup: <path>
Изменено: <files>
Production: healthy
Friend project: untouched
```

A safe-mode result should say `Production: unchanged; waiting for explicit approval/deploy request.`

## AI Home frontend verification

- Check live static response cache headers before changing AI Home JS. If assets use `immutable`, bump only the script query version in `ai-home-v2/index.html` and include root HTML in the safe manifest; otherwise returning users may retain old JS. Preserve the legacy `20260905-3` prefix while the legacy installer validates it, and update the exact cache-key expectation in `tests/ai-home-v2/voice-isolation.test.cjs` without weakening markup/CSS or protected-file assertions.
- Run `test-auto` again after the complete manifest and cache-key changes; an earlier green JS-only test run does not cover the final payload.
- For browser smoke without a local Playwright installation, use Browser Use on an isolated blank document with deployed HTML/JS read via HTTP and explicit in-memory API/speech test doubles. Verify DOM behavior and deduplication, but report that this does not prove audible playback on the user's device. Never submit synthetic requests to production state solely for smoke testing.

## Manual navigation diagnosis and release

- Trace Manual shortcuts through the existing `[data-nav]` document click router. The main `navigate` function is private to the core app IIFE; a later standalone IIFE cannot call it through `typeof navigate`. Route markup through the existing handler rather than exporting internals or adding touch-only listeners.
- Prepare generated Manual release HTML under `minimal-ui-v1/` from a non-secret read-only live snapshot, with a pinned baseline hash and exact-diff assertion. The repository may contain patch generators rather than the deployed `app.js`/Manual bundle; do not reconstruct or replace unrelated live features from an older branch.
- Test Manual in an isolated browser with actual static JS/CSS, in-memory localStorage, and network disabled. Dismiss the normal first-run intro through its existing action before touch hit-testing; fresh fixture state otherwise shows a modal over the shortcuts. Bind raw CDP input and evaluation to the same explicit target/session; helper-current tabs may differ. Send large DOM/JS fixtures in small chunks and avoid returning full HTML through IPC.
- Check `/manual.html` cache headers. If immutable caching is present and only Manual HTML is changed, provide a versioned Manual URL for immediate post-deploy verification instead of silently changing unrelated AI Home routing or server cache policy.
- `test-auto` may select only `quick` for `minimal-ui-v1/`; run that component's unittest suite explicitly and add a dedicated allowlisted non-control-plane DVIZH CI workflow when behavioral CI is missing. Do not alter Autopilot gate workflows.
- Verify every release baseline pin directly against production bytes, including `boot.js` even though `live-snapshot` omits it. Read expected hashes from the committed pin contract; use read-only SHA-256 on `/opt/dvizh/static/<file>`. If HTTP corroboration is needed, the local DVIZH endpoint is `http://127.0.0.1:8000`, not port 80. Missing snapshot coverage is not a reason to modify the snapshot tool or skip a pin.
- After an approval-required plan, retain the worktree and wait for the user's exact approval phrase. Before applying later, recheck that the live baseline has not drifted; a pinned build snapshot alone does not guard against changes during the approval wait.

## Design prototype preferences

- For the Quiet Signal redesign, retain the minimalist action-first composition but use a near-black Manual background: the owner finds white dazzling. Use restrained color accents, section emoji and compact meaningful infographics; show demo labels for sample data.
- Make the assistant wave a horizontal volumetric ribbon with depth, shaded layers and soft silver-blue highlights, rather than flat lines or vertical equalizer bars. Respect reduced motion and pause animation outside AI mode.
- Keep the AI/Manual switch visible in both modes and preserve drafts and task state across switching. Keep design revisions as versioned standalone prototypes until implementation is requested; prototype approval is not production deployment approval.

- Treat unsent drafts separately from unresolved submissions: never save an in-flight request as plain text on mode navigation, because returning after server acceptance loses its request ID and permits duplicate execution. Remove stale saved drafts when submission identity is unresolved.
- Hide an animated SVG's static fallback only after a successful geometry draw, and restore it on initialization or rendering failure; appended empty paths do not prove rendering succeeded.
- Preserve Manual's existing Details toggle state when applying CSS. Do not force secondary panels visible while its JS still considers them collapsed; test first-click expand and second-click collapse in Training and Social.
- On Python 3.12+, `unittest discover` returns exit 5 when it collects zero tests. The legacy minimal-ui tests are pytest-style functions, so use the explicit unittest adapter that invokes them or pytest on CI; do not add a redundant zero-test discovery command before the real suite.
- Run pinned snapshot whitespace checks after staging new files, not only `git diff --check` on tracked changes. Preserve snapshot bytes and scope any whitespace attribute exception to that exact baseline file rather than modifying its integrity pin or relaxing source checks.
- Agent sandbox browser/socket failures do not prove the host tools are blocked. Run final suites through the host terminal and real-DOM checks through Browser Use with isolated in-memory state, then require CI browser results before release. Raw CDP targets may expire; recreate fixtures instead of assuming a stored target remains alive.

## Manual sync stability diagnosis

- Reproduce periodic Manual resets with the deployed `sync.js` in an isolated Node VM using fake Storage, fetch, timers and `location.reload`. Check metadata-only polls, genuine remote changes, queued pulls and 409 retries separately; no real state API writes are needed.
- Do not fix resets by increasing poll intervals or merely removing reloads. The current Manual holds private in-memory state and starts at `activeView = 'home'`; hard reload loses navigation/drafts/timers, while suppressing reload without updating that state risks overwriting remote changes. Design an explicit state-application boundary preserving active editing and runtime state.
- Compare semantic state rather than raw JSON serialization: ignoring only `coachPacket.exportedAt` still treats `__sync` timestamps, entity `_syncUpdatedAt`, and key ordering as UI changes. Distinguish proven reload paths from an unproven live background writer.

- Test mixed-cache compatibility before releasing coupled scripts: live Manual HTML and `sync.js` may be immutable while `app.js` is no-cache. Versioning the new Manual entry alone does not protect existing cached entries; exercise old sync + new app explicitly. New app code must not unconditionally call an API absent in cached sync, or form saves can throw.
- Track displayed form ancestors independently from live state. Preserve untouched stale fields through partial renders, but advance consumed user edits after successful save; test edit→save→remote change→resubmit and deliberate reversion to an older value.

- Verify protective-mode recovery end to end in a real browser, including explicit update navigation. Preserve an immutable startup snapshot before bootstrap rendering and retain pending histories; a later startup save must not overwrite the only copy. Catch storage failures even at client-ID initialization, with visible fail-closed behavior and accessible in-memory recovery.
- Model server revision CAS in multi-page sync fixtures and close unrelated contexts between cache scenarios. A mock accepting every stale PUT can manufacture a data-loss failure that the real CAS server rejects; retain a differential CAS-on/off reproduction rather than weakening preservation assertions.

## Health state acceptance

- Test derived sleep duration across actual concurrent CAS saves, not only isolated domain updates: generic leaf reconciliation can merge valid clock edits into an inconsistent duration. Verify clock/reported transitions and stale cached-client reads as well as persistence.
- Differential-test shared Python/JavaScript validation for nulls, integral JSON numbers, timezone casing, code-point length and explicit Unicode whitespace. Python strip and JavaScript trim differ; an ordinary ASCII parity fixture is insufficient.
- Keep live inference-only evaluations distinct from complete configured Hermes execution. Use a bounded synthetic tool dispatcher that never executes shell strings, retain raw model outputs before any equivalent-phrase scoring corrections, and do not label a different model or prompt-only checks as production acceptance.

## Owner-maintenance handoff

- Separate explicit owner-authorized control-plane preparation into a dedicated owner branch/worktree; retain paused feature jobs and architecture reports unchanged. Local authorization does not create a privileged install channel: the ordinary push/release gates must continue rejecting control-plane files. Deliver a verified Git bundle when owner push/installation is required; never self-install or label local tests as GitHub CI or deployment.
- For release-gate reviews, exercise concurrent approval consumption and overlapping transactions, repeated catchable signals during rollback, reserved approval-ID/control-journal collisions, directory identity changes, compile-only Python validation, and journal unlink/fsync failures. Passing ordinary apply/rollback tests does not cover these boundaries. Document SIGKILL/power-loss recovery separately from catchable rollback guarantees.

## Cleanup

After a successful deployment, or after the user confirms a safe-mode handoff is no longer needed, close the clean worktree:

```bash
dvizhdevctl close <job-id>
```

Never close a dirty or unresolved job.

## Absolute prohibitions

Never:

- use arbitrary `sudo` outside `dvizhgitpush` and `dvizhrelease`;
- read/copy/display the private GitHub deploy key;
- use raw `git push`, `git push --force`, `git reset --hard`, `git clean -fd`, merge or rebase in autonomous mode;
- modify friend-project paths listed above;
- modify Autopilot's own guardrails from an autonomous Hermes job;
- commit secrets, credentials, private keys, dumps or databases;
- modify auth/SSH/firewall/systemd definitions through this gate;
- bypass red CI;
- bypass an approval-required result;
- claim production changed before `dvizhrelease` returns verified success.

The goal is maximum autonomy inside explicit technical guardrails, with the friend's project cryptographically separated from Hermes' Git write credential by a root-owned path gate.

## Owner-delivered v2.2 privileged contract

The installed root release gate supports the separate `ai-integration-privileged`
class for exactly three DVIZH runtime targets. This remains owner-maintenance
control-plane; managed jobs must never edit or push Autopilot's own gate, skill,
installer, sudoers, deploy key, or gate workflows.

For this class every manifest operation must use the exact committed source and
production destination below and must include `sha256`,
`release_class: "ai-integration-privileged"`, `required_owner: "root:root"`,
`required_mode: "0755"`, and the fixed verification value shown here:

- `hermes-control-v1/dvizh_context.py` -> `/usr/local/libexec/dvizh-context` with `verification: "python-syntax"`.
- `hermes-control-v1/dvizh_proposals.py` -> `/usr/local/libexec/dvizh-proposals` with `verification: "python-syntax"`.
- `hermes-control-v1/dvizh_proposal_bridge.py` -> `/opt/dvizh-ai-approval/proposal_bridge.py` with `verification: "python-syntax-service"`.

No wildcard under `/usr/local` or `/opt/dvizh-ai-approval` is allowed. Privileged
operations may not be mixed with ordinary v2.1 operations. The bridge update is
the only one of these three that may require a restart; when updated it must declare
exactly `restarts: ["dvizh-ai-approval.service"]` plus a non-empty `restart_reason`.
The two libexec helpers require no restart.

`ai-integration-privileged` is ALWAYS approval-required, including in auto mode.
After `release-plan` returns `APPROVE <proposal-id> <token>`, stop and wait for a
later authenticated owner Telegram message containing that exact phrase. Seeing the
challenge or the original development request is not approval. For this class pass
the ENTIRE exact later phrase as the single argument:

```bash
dvizhautopilot release-apply <proposal-path> --approval 'APPROVE <proposal-id> <token>'
```

A bare token is invalid for this class. Approval is one-time, digest-bound and
expires after 1800 seconds. Never manufacture, infer, replay or self-approve it.
The root gate independently rechecks immutable source bytes, CI, destination
metadata, backup, health, atomic writes and rollback. A pending interrupted
transaction fails closed and requires separate owner recovery; do not bypass it.
