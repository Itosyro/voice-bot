---
name: dvizh-dev
description: Safely diagnose and fix DVIZH code from Hermes using isolated git worktrees, local tests, commits, and a ChatGPT handoff package. Use for bugs, frontend/backend code fixes, regressions, and development tasks. Never mutate production directly.
version: 1.1.0
author: DVIZH
platforms: [linux]
metadata:
  hermes:
    tags: [dvizh, development, debugging, git, worktree, handoff, telegram]
    category: dvizh
---

# DVIZH Dev Mode

Use this skill when the user asks Hermes to diagnose, fix, refactor, test, or prepare a DVIZH code change.

Examples:

- «ручной режим прыгает, найди причину и исправь»;
- «почини баг и прогони тесты»;
- «подготовь фикс, но прод не трогай».

For planning/tasks/schedule changes inside DVIZH itself, use the separate `dvizh-server` skill and inert task/schedule proposals instead.

## Architecture — local Hermes, GitHub through ChatGPT

Hermes does **not** need GitHub credentials.

Default flow:

**Telegram → Hermes → managed local worktree → tests → local commit → handoff package → user sends result to ChatGPT → ChatGPT pushes to GitHub/runs CI/prepares release.**

Do not ask the user to configure `gh auth`, GitHub tokens, PATs, SSH deploy keys, or other GitHub credentials for Hermes.

Do not run `dvizhdevctl push`, `dvizhdevctl ci`, or `dvizhdevctl deploy-propose` in the normal workflow. Those legacy commands may exist for compatibility, but this skill does not use them.

## Absolute production boundary

Production is read-only to Hermes Dev Mode.

**Never** directly edit, replace, move, truncate, chmod, delete, or generate files under:

- `/opt/dvizh`;
- `/etc/dvizh`;
- `/var/lib/dvizh` except through an already-approved narrow helper from another skill;
- `/etc/systemd`, `/usr/local`, proxy/firewall/auth configuration.

Never run `sudo`, `su`, `systemctl restart/start/stop/enable/disable`, package installation, database mutation, web-state mutation, or a production installer from Dev Mode.

Do not use `git reset --hard`, `git clean -fd`, `git push --force`, or edit code in place outside the managed worktree.

## Source of truth

Use:

```bash
dvizhdevctl
```

Start with:

```bash
dvizhdevctl config
dvizhdevctl live-snapshot
```

The live snapshot only hashes selected production files and checks service active state. It does not read secrets or mutate production.

## Mandatory bug-fix workflow

### 1. Diagnose read-only

Inspect the smallest necessary evidence.

Prefer:

```bash
dvizhctl status
dvizhctl doctor
dvizhctl logs <allowed-service> 80
dvizhdevctl live-snapshot
```

You may read non-secret production source files when necessary to understand a bug, but never modify them.

Never inspect `.env`, tokens, auth identity, cookies, credentials, private keys, API keys, or shell histories.

State the diagnosis and evidence before making a fix.

### 2. Create one managed worktree

```bash
dvizhdevctl new '<plain-language problem>'
```

Record the returned `id`, `branch`, and `worktree`.

All development edits must happen only inside that worktree.

```bash
dvizhdevctl where <job-id>
```

Do not reuse an unrelated checkout or edit a production/server checkout.

### 3. Make the smallest fix

Change only what is needed and preserve stable behavior outside the bug.

For a production-only component whose exact current source is not represented in GitHub as a normal file, it is acceptable to reconstruct the relevant source in the managed worktree or create a reproducible patch/installer plus regression tests. The final handoff must contain the exact committed diff.

Do not add MutationObserver/timer/hotfix loops as a shortcut for UI bugs unless architecture explicitly requires them and tests justify them.

### 4. Test before commit

Always start with:

```bash
dvizhdevctl test <job-id> quick
```

Then run the narrowest relevant profile if it actually exists in that worktree:

```bash
dvizhdevctl test <job-id> ai-home-v2
dvizhdevctl test <job-id> hermes-control
dvizhdevctl test <job-id> telegram
```

Do **not** run the `hermes-dev` profile against an older base branch that does not contain `hermes-dev-v1`; that is not a product failure.

If no predefined profile covers the change, run additional non-destructive tests inside the managed worktree only. Do not install packages on the server merely to make tests pass.

### 5. Review and commit

Review:

```bash
dvizhdevctl diff <job-id>
```

Check for unrelated files, secrets, generated artifacts, and broad rewrites.

Then commit locally:

```bash
dvizhdevctl commit <job-id> '<short commit message>'
```

`dvizhdevctl commit` refuses common secret/credential-shaped paths and oversized files.

### 6. Export the handoff — stop before GitHub

After the worktree is clean and the local commit exists, run:

```bash
dvizhdevhandoff <job-id>
```

The exporter produces a manifest containing:

- job ID and problem;
- base branch and exact base SHA;
- exact local HEAD SHA;
- commit list;
- changed paths;
- exact `git diff --binary` from base → HEAD;
- SHA256 of the patch;
- explicit `production_status: unchanged`.

For a small patch, `patch_inline` is included. Paste it verbatim in the Telegram result so the user can forward it to ChatGPT.

For a larger patch, the exporter creates a `.patch` file under Hermes' private dev state. If the Telegram runtime supports file attachments, send that patch file as a document. Never include credentials or secret files.

**Stop here. Do not push to GitHub. Do not wait for GitHub CI. Do not create a deploy command.** ChatGPT owns the GitHub/CI/release side of the workflow.

## Telegram interaction style

When the user says something like:

> Гермес, ручной режим снова прыгает. Исправь сам, прод не трогай.

Handle diagnosis → worktree → fix → tests → local commit → handoff without asking the user to copy intermediate shell commands.

Send compact progress updates only at meaningful milestones:

1. diagnosis found;
2. worktree created;
3. tests passed/failed;
4. local commit created;
5. handoff package ready.

Do not flood Telegram with raw logs.

A good final result:

```text
Найдена причина: ...
Исправлено локально в managed worktree.
Tests: ✅
Local commit: <sha>
Changed: <files>
Production: unchanged
GitHub credentials: not required

HANDOFF FOR CHATGPT:
Base: <base-sha>
Head: <local-head-sha>
Patch SHA256: <sha256>
<exact patch_inline if small>
```

The user can send that final result to ChatGPT; ChatGPT will reproduce/push the change, run GitHub CI, and prepare the immutable deployment path.

## Status and cleanup

List jobs:

```bash
dvizhdevctl status
```

One job:

```bash
dvizhdevctl status <job-id>
```

Do not close the worktree until ChatGPT confirms the handoff was accepted and the GitHub-side change exists.

Then a clean completed worktree may be closed:

```bash
dvizhdevctl close <job-id>
```

A dirty worktree cannot be closed by the helper.

## Security rules

Never include secret material in commits, diffs, handoff packages, Telegram replies, test logs, or prompts.

Do not inspect:

- `~/.hermes/.env`;
- `~/.hermes/auth.json`;
- `~/.codex/auth.json`;
- `/etc/dvizh/*.env`;
- `/var/lib/dvizh/auth-identity.json`;
- SSH private keys or credential stores.

Do not ask the user to paste API keys/tokens into Telegram.

If a task requires root access to apply safely, prepare code + tests + handoff and stop. Production deployment remains a separate user-approved step after ChatGPT/GitHub CI.

## Verification rule

After every development task report separately:

- **diagnosis/evidence**;
- **files changed**;
- **tests**;
- **local commit/branch**;
- **handoff manifest/patch SHA256**;
- **production status** — explicitly `unchanged` until a user-approved deployment actually succeeds.
