---
name: dvizh-dev
description: Develop, test, push, gate and safely deploy DVIZH changes from Telegram through Hermes Autopilot v2. Uses isolated worktrees, GitHub CI and a root-owned allowlisted release gate with rollback.
version: 2.0.0
author: DVIZH
platforms: [linux]
metadata:
  hermes:
    tags: [dvizh, development, autopilot, github, ci, release, telegram]
    category: dvizh
---

# DVIZH Dev Mode v2 — Autopilot

Use this skill for DVIZH code bugs, features, frontend/backend work, tests, release preparation and deployment requests.

The owner explicitly wants the normal workflow to happen inside Telegram without copying commands between Telegram, ChatGPT and a shell.

## Modes

Interpret these prefixes when present:

- `/dev inspect` — read-only diagnosis. Never create/deploy changes unless the user later asks.
- `/dev safe` — develop + test + commit + GitHub push + CI. Production requires explicit user approval in Telegram.
- `/dev auto` — develop + test + commit + GitHub push + CI + automatic deployment **only when the root gate classifies the release as auto-safe**. Privileged releases still require Telegram approval.

If the user asks to "сделай сам", "исправь полностью", "автопилот", or otherwise asks for end-to-end execution without naming a mode, use **auto**.

If the user asks only to inspect/diagnose, use **inspect**.

For ambiguous development requests default to **safe**.

## Architecture

Normal auto flow:

**Telegram → Hermes/Astra → managed worktree → local tests → commit → dedicated GitHub deploy key → `hermes/dev/*` branch → GitHub Actions → immutable release manifest → root-owned `dvizhrelease` gate → backup → atomic apply → HTTP/smoke verification → rollback on failure → Telegram report.**

The model never receives arbitrary root shell access. `sudo` is allowed only through the installed root-owned gate:

```bash
sudo -n /usr/local/sbin/dvizhrelease ...
```

Do not run any other sudo command from this skill.

## Mandatory start

For development work first run:

```bash
dvizhautopilot doctor
```

If `ok` is false because the GitHub write deploy key is not authorized, stop and tell the user that the one-time GitHub deploy-key setup is still incomplete. Never ask the user to paste a private key or token.

Create the managed job:

```bash
dvizhautopilot new <inspect|safe|auto> '<problem>'
```

For `inspect`, remain read-only.

For `safe` or `auto`, record the returned job id and use the managed worktree from:

```bash
dvizhdevctl where <job-id>
```

All edits belong only in that worktree.

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
2. Edit only the managed worktree.
3. Run automatic local profiles:

```bash
dvizhautopilot test-auto <job-id>
```

If additional narrow tests are necessary, run them inside the worktree without changing production or installing server packages.
4. Review the diff:

```bash
dvizhdevctl diff <job-id>
```

5. Commit:

```bash
dvizhdevctl commit <job-id> '<short message>'
```

6. Push through the dedicated repo-scoped SSH deploy key:

```bash
dvizhautopilot push <job-id>
```

Never force-push.

7. Wait for GitHub Actions:

```bash
dvizhautopilot wait-ci <job-id> --timeout 1200
```

If CI is red, inspect compact failure metadata:

```bash
dvizhautopilot ci-failures <job-id>
```

Fix in the same managed worktree, rerun local tests, commit, push and wait again. Limit autonomous CI-fix attempts to 3. After 3 failed rounds, stop and report the blocker instead of looping indefinitely.

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

The root gate, not Hermes, decides whether targets are safe, approval-required or denied.

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

If the result says:

```json
"approval_required": false
```

and the job mode is `auto`, apply immediately:

```bash
dvizhautopilot release-apply <proposal-path>
```

The gate owns backup, atomic writes, HTTP byte checks and rollback.

### Approval-required release

If `approval_required` is true, the plan returns an exact phrase:

```text
APPROVE <proposal-id> <token>
```

Send a concise Telegram explanation of what will change, what service (if any) will restart, and that backup/rollback are automatic. Then ask the owner to reply with that **exact approval phrase**.

**Do not call release-apply until a later user Telegram message contains that exact phrase.** The fact that the model has seen the token in command output is not approval.

After the owner explicitly replies with the exact phrase, pass only the token to:

```bash
dvizhautopilot release-apply <proposal-path> --approval <token>
```

Approval expires after 30 minutes and is bound to the exact proposal+manifest digest.

Never manufacture, infer or self-approve the owner's confirmation.

## Failures and rollback

If `dvizhrelease` reports deployment failure, it attempts rollback automatically. Do not manually patch production afterward.

Report:

- failure reason;
- whether rollback was confirmed;
- backup path if present;
- current CI commit.

If rollback is not confirmed, stop all autonomous work and alert the owner immediately.

## Telegram progress style

Do not dump raw logs. Send updates only at meaningful milestones:

- diagnosis found;
- local tests green;
- GitHub/CI green or red;
- approval needed (only when needed);
- deployment + smoke verification result.

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
```

A safe-mode result should say `Production: unchanged; waiting for explicit approval/deploy request.`

## Cleanup

After a successful deployment, or after the user confirms a safe-mode handoff is no longer needed, close the clean worktree:

```bash
dvizhdevctl close <job-id>
```

Never close a dirty or unresolved job.

## Absolute prohibitions

Never:

- use arbitrary `sudo` outside `/usr/local/sbin/dvizhrelease`;
- use `git push --force`, `git reset --hard`, `git clean -fd`;
- commit secrets, credentials, private keys, dumps or databases;
- modify auth/SSH/firewall/systemd definitions through this gate;
- bypass red CI;
- bypass an approval-required result;
- claim production changed before `dvizhrelease` returns verified success.

The goal is maximum autonomy **inside explicit technical guardrails**, not unrestricted shell power.
