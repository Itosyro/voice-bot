---
name: dvizh-server
description: Safely inspect DVIZH health and read the user's current DVIZH planning/training/social context through the read-only dvizhctl interface. Use for DVIZH status, day planning context, week, readiness, training, Jump Lab, Social Hub, sync problems, logs, and server diagnostics.
version: 1.1.0
author: DVIZH
platforms: [linux]
metadata:
  hermes:
    tags: [dvizh, server, diagnostics, planner, telegram, context, training]
    category: dvizh
---

# DVIZH Server + Context

Use this skill whenever the user asks about DVIZH, today's plan, the week, current tasks, readiness/training, Jump Lab, Social Hub, synchronization, or server health.

## Source of truth

The current operational interface is:

```bash
dvizhctl
```

Prefer it over ad-hoc shell/SQLite commands for DVIZH work.

## Read current user context

The context commands are read-only JSON snapshots. Use the narrowest useful view:

```bash
dvizhctl context today
```

For today's tasks/check-in/schedule and relevant training/social/jump state.

```bash
dvizhctl context week
```

For weekly schedule/rules and related plan information.

```bash
dvizhctl context training
```

For readiness, training plan and recent training sessions.

```bash
dvizhctl context jump
```

For Jump Lab profile/program/progress data.

```bash
dvizhctl context social
```

For Social Hub profile/content pipeline data.

```bash
dvizhctl context health
```

For current system/data health plus readiness/check-in context.

Use `dvizhctl context full` only when a broad cross-domain analysis genuinely needs it. Do not pull the full snapshot for a simple question.

The context helper internally uses the stable DVIZH identity and the production Telegram database, but outputs only sanitized read-only data. Do not bypass it by reading `/var/lib/dvizh`, SQLite, auth identity files, or credential files directly.

## Server diagnostics

1. Start with:

   ```bash
   dvizhctl status
   ```

2. If anything is unclear, unhealthy, or the user asks for a deeper check, run:

   ```bash
   dvizhctl doctor
   ```

3. If one service needs investigation, read only its recent logs:

   ```bash
   dvizhctl logs <service> 80
   ```

   Allowed service names are:

   - `dvizh`
   - `dvizh-auth`
   - `dvizh-telegram`
   - `dvizh-bridge`
   - `dvizh-web-week`
   - `dvizh-web-editor`
   - `dvizh-training`
   - `dvizh-jump`
   - `dvizh-social`

   `dvizhctl logs` automatically redacts common token/key/password patterns before output. Do not bypass this with direct `journalctl` for routine DVIZH diagnosis.

## Planning behavior

When the user asks questions such as:

- "Что мне сегодня делать?"
- "Какой сегодня план?"
- "Стоит ли сегодня волейбол?"
- "Что у меня на неделе?"
- "Как идёт прыжок/зал/соцсети?"

first retrieve the appropriate context view. Base the answer on actual DVIZH data instead of guessing from chat memory.

For now, context is **read-only**. You may propose a new plan or changes in plain language, but do not claim they were applied. A separate approval-controlled write layer will be added later.

## Safety boundary — mandatory

The current `dvizhctl` layer is intentionally **read-only**.

Do not bypass it with direct mutating shell commands. In particular, unless a future DVIZH approval tool explicitly grants the action, do **not**:

- restart/stop/start/enable/disable systemd units;
- run `sudo` for DVIZH changes except the internal `dvizhctl context` helper invoked by `dvizhctl` itself;
- edit, move, truncate, or delete DVIZH files;
- change SQLite rows or schema;
- inspect or print `.env`, `auth.json`, bot tokens, API keys, passwords, cookies, auth identity files, or credential stores;
- run package installation/update commands;
- deploy, rollback, `git reset`, `git checkout`, `git clean`, or overwrite working trees;
- change firewall, proxy, exe.dev, auth, or system configuration.

If the user asks for one of those actions, first diagnose read-only, explain the exact proposed change, and state that the current Hermes control layer requires a separate approval path before mutation. Do not silently work around that boundary.

## Secrets

Never include secrets in chat output. If any output still appears token-like, redact it before replying.

Do not inspect `~/.hermes/.env`, `~/.hermes/auth.json`, `~/.codex/auth.json`, DVIZH `.env` files, or `/var/lib/dvizh/auth-identity.json` directly.

## Service map

The production stack currently consists of:

- `dvizh.service` — main web/backend
- `dvizh-auth.service` — login/password gateway
- `dvizh-telegram.service` — DVIZH Telegram bot
- `dvizh-bridge.service` — core Telegram/web synchronization
- `dvizh-web-week.service` — weekly schedule projection
- `dvizh-web-editor.service` — web schedule editor bridge
- `dvizh-training.service` — readiness/training system
- `dvizh-jump.service` — Jump Lab
- `dvizh-social.service` — Social Hub
- user `hermes-gateway.service` — Hermes messaging/cron gateway

The public DVIZH endpoint is protected by the DVIZH auth gateway. Internal backend ports are not a reason to expose new public ports.

## Useful workflows

User: "Проверь ДВИЖ"

Procedure: `dvizhctl status`; if any non-active service appears, `dvizhctl doctor`; inspect only the failing service logs.

User: "Что у меня сегодня?"

Procedure: `dvizhctl context today`, then summarize the actual schedule/tasks/readiness. Keep the answer compact and action-oriented.

User: "Можно сегодня волейбол?"

Procedure: `dvizhctl context training`; use the latest readiness, recent sessions/load, and today's schedule. Do not invent medical clearance.

User: "Что с целью прыжка?"

Procedure: `dvizhctl context jump`; summarize latest measurements/program/progress and any review/safety state.

User: "Что делать с соцсетями сегодня?"

Procedure: `dvizhctl context social` plus `dvizhctl context today` if scheduling matters.

User: "Почему не синхронизируется Telegram и сайт?"

Procedure: status → doctor → recent logs for `dvizh-bridge`, `dvizh-web-week`, and/or `dvizh-web-editor` as indicated by evidence.

User: "Перезапусти social"

Procedure: inspect status/logs first, explain the likely fix, then state that restart is intentionally not available in the current read-only control layer and requires explicit mutation approval support.

## Verification

After any diagnostic workflow, report:

- which services are healthy/unhealthy;
- what evidence supports the conclusion;
- whether any change was made (normally: **no changes made**).

After a context workflow, distinguish:

- facts retrieved from DVIZH;
- your recommendation/inference;
- proposed changes that have **not** yet been applied.
