---
name: dvizh-dev
description: Safely diagnose and fix DVIZH code from Hermes using isolated git worktrees, tests, GitHub branches, CI, and inert deploy proposals. Use for bugs, frontend/backend code fixes, regressions, CI failures, and development tasks. Never mutate production directly.
version: 1.0.0
author: DVIZH
platforms: [linux]
metadata:
  hermes:
    tags: [dvizh, development, debugging, git, worktree, ci, telegram]
    category: dvizh
---

# DVIZH Dev Mode

Use this skill when the user asks Hermes to diagnose, fix, refactor, test, or prepare deployment of DVIZH code. This is the development path for requests such as:

- «ручной режим прыгает, найди причину и исправь»;
- «почини баг и прогони тесты»;
- «сделай фикс в ветке и проверь CI»;
- «подготовь безопасный деплой».

For planning/tasks/schedule changes inside DVIZH itself, use the separate `dvizh-server` skill and inert task/schedule proposals instead.

## Absolute production boundary

Production is read-only to Hermes Dev Mode.

**Never** directly edit, replace, move, truncate, chmod, delete, or generate files under:

- `/opt/dvizh`;
- `/etc/dvizh`;
- `/var/lib/dvizh` except through an already-approved narrow helper from another skill;
- `/etc/systemd`, `/usr/local`, proxy/firewall/auth configuration.

Never run `sudo`, `su`, `systemctl restart/start/stop/enable/disable`, package installation, database mutation, web-state mutation, or a production installer from Dev Mode.

Do not use `git reset --hard`, `git clean -fd`, `git push --force`, `git checkout` on an existing production/server checkout, or edit code in place outside the managed worktree.

`dvizhdevctl` intentionally has **no deploy/apply command**. A deploy proposal is inert text until the user separately approves and executes it.

## Source of truth for development work

Use:

```bash
dvizhdevctl
```

Start by checking:

```bash
dvizhdevctl config
dvizhdevctl live-snapshot
```

The live snapshot only hashes selected web/server files and checks service active state. It does not read secrets or mutate production.

## Mandatory bug-fix workflow

### 1. Diagnose read-only

Before changing code, inspect the smallest necessary live evidence.

Prefer:

```bash
dvizhctl status
dvizhctl doctor
dvizhctl logs <allowed-service> 80
dvizhdevctl live-snapshot
```

You may read non-secret production source files such as `/opt/dvizh/server.py`, `/opt/dvizh/static/app.js`, `/opt/dvizh/static/manual.html` when needed to understand a bug, but **never modify them**.

Never inspect `.env`, tokens, auth identity, cookies, credentials, private keys, API keys, or shell histories.

State your diagnosis and evidence before making a fix.

### 2. Create an isolated job/worktree

Create exactly one managed worktree for the bug:

```bash
dvizhdevctl new '<plain-language problem>'
```

Record the returned `id`, `branch`, and `worktree`.

All development edits must happen only inside that returned worktree.

```bash
dvizhdevctl where <job-id>
```

Do not edit the controller's base repo and do not reuse some unrelated checkout.

### 3. Make the smallest fix in the worktree

Change only what is needed. Preserve existing stable behavior outside the bug.

For a production-only regression whose exact current source is not yet represented in Git, create a reproducible patch/installer plus tests in the worktree rather than editing production directly.

Do not add MutationObserver/timer/hotfix loops as a shortcut for UI bugs unless the architecture explicitly requires them and tests justify them.

### 4. Test before commit

Always start with:

```bash
dvizhdevctl test <job-id> quick
```

Then run the narrowest relevant profile:

```bash
dvizhdevctl test <job-id> ai-home-v2
dvizhdevctl test <job-id> hermes-control
dvizhdevctl test <job-id> telegram
dvizhdevctl test <job-id> hermes-dev
```

If no predefined profile fully covers the change, you may run additional **non-destructive tests inside the managed worktree only**. Do not install packages on the server to make tests pass. If a dependency is missing, report it and use CI where possible.

A failed test is not permission to deploy or modify production.

### 5. Review the exact diff

Before commit:

```bash
dvizhdevctl diff <job-id>
```

Check for accidental files, secrets, unrelated changes, generated artifacts, and broad rewrites.

`dvizhdevctl commit` refuses common secret/credential-shaped paths and oversized files.

### 6. Commit and push without force

```bash
dvizhdevctl commit <job-id> '<short commit message>'
dvizhdevctl push <job-id>
```

The branch must remain under `hermes/dev/` and push is always non-force.

If push authentication is unavailable, stop and tell the user exactly that Git push credentials need one-time configuration. Do not ask for tokens in Telegram and do not print credentials.

### 7. Wait for CI

Check:

```bash
dvizhdevctl ci <job-id>
```

Do not claim the fix is ready while `green` is false. If CI fails, inspect the GitHub Actions failure, modify only the same worktree, rerun tests, commit, push, and check the new HEAD again.

### 8. Prepare an inert deploy proposal

Only after the current branch HEAD is confirmed on origin and CI is fully green may you run:

```bash
dvizhdevctl deploy-propose <job-id> <relative-installer.sh>
```

This produces:

- exact branch and commit SHA;
- exact installer path;
- Git blob identity;
- immutable raw GitHub URL;
- one user-run `curl ... | sudo bash` command;
- status `pending-user-approval`.

It does **not** execute the command.

Tell the user clearly:

**«Фикс готов и CI зелёный, но на сервер ещё ничего не установлено.»**

Never execute the proposed command yourself through Dev Mode.

## Telegram interaction style

When the user writes a natural request such as:

> Гермес, ручной режим снова прыгает. Исправь сам, прод не трогай.

Work through the full workflow without making the user copy intermediate shell commands.

Send compact progress updates only at meaningful milestones:

1. diagnosis found;
2. worktree/branch created;
3. tests passed or failed;
4. commit/push result;
5. CI result;
6. final deploy proposal waiting for approval.

Do not flood Telegram with raw logs. Summarize and include only the important error excerpt when something fails.

A good final Telegram result looks like:

```text
Найдена причина: sync/render полностью пересобирал экран при каждом обновлении состояния.
Исправлено в hermes/dev/...
Tests: ✅
CI: ✅
Изменено: 2 файла
Commit: abc1234

Деплой НЕ выполнен.
Подготовлен immutable deploy proposal: deploy-...
```

## Status and inspection

List recent jobs:

```bash
dvizhdevctl status
```

One job:

```bash
dvizhdevctl status <job-id>
```

Show diff:

```bash
dvizhdevctl diff <job-id>
```

Close a completed clean worktree:

```bash
dvizhdevctl close <job-id>
```

A dirty worktree cannot be closed by the helper. Never delete it manually just to hide unfinished changes.

## Security rules

Never include secret material in commits, diffs, Telegram replies, test logs, or prompts.

Do not inspect:

- `~/.hermes/.env`;
- `~/.hermes/auth.json`;
- `~/.codex/auth.json`;
- `/etc/dvizh/*.env`;
- `/var/lib/dvizh/auth-identity.json`;
- SSH private keys or credential stores.

Do not ask the user to paste API keys/tokens into Telegram.

If a task requires root access to implement safely, prepare code + tests + immutable deploy proposal and stop for explicit user approval.

## Verification rule

After every development task, report separately:

- **diagnosis/evidence**;
- **files changed**;
- **tests**;
- **commit/branch**;
- **CI status**;
- **production status** — explicitly `unchanged` until a user-approved deployment actually succeeds.
