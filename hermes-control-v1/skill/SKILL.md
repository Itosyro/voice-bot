---
name: dvizh-server
description: Safely inspect DVIZH health, read the user's current planning/training/social context, and create inert AI change proposals through dvizhctl. Use for DVIZH status, day planning, week, readiness, training, Jump Lab, Social Hub, sync problems, logs, and proposed task/schedule changes.
version: 1.2.0
author: DVIZH
platforms: [linux]
metadata:
  hermes:
    tags: [dvizh, server, diagnostics, planner, telegram, context, training, proposals]
    category: dvizh
---

# DVIZH Server + Context + Proposals

Use this skill whenever the user asks about DVIZH, today's plan, the week, current tasks, readiness/training, Jump Lab, Social Hub, synchronization, server health, or wants to change a task/schedule.

## Source of truth

Use:

```bash
dvizhctl
```

Prefer it over ad-hoc shell/SQLite commands for DVIZH work.

## Read current user context

Use the narrowest useful view:

```bash
dvizhctl context today
dvizhctl context week
dvizhctl context training
dvizhctl context jump
dvizhctl context social
dvizhctl context health
```

Use `dvizhctl context full` only for genuine cross-domain analysis. The helper returns sanitized read-only data. Never bypass it by reading `/var/lib/dvizh`, SQLite databases, auth identity files, or credentials directly.

## AI proposals — safe staging only

When the user asks to change DVIZH, do **not** mutate the app directly. Create an inert proposal. A proposal is only a queued suggestion; it does not modify tasks, schedule, databases, services, or web state.

Allowed proposal actions:

- `task_create`
- `task_complete`
- `schedule_move`
- `day_plan`

Syntax:

```bash
dvizhctl propose <action> '<short human summary>' '<payload_json>'
```

Examples:

```bash
dvizhctl propose task_create 'Создать задачу: купить продукты' '{"title":"Купить продукты","area":"other"}'
```

```bash
dvizhctl propose task_complete 'Отметить задачу ПДД выполненной' '{"task_id":"<actual-id-from-context>"}'
```

```bash
dvizhctl propose schedule_move 'Перенести Зал верх на 20:00' '{"occurrence_id":"<actual-id-from-context>","start_local":"20:00"}'
```

List queued proposals:

```bash
dvizhctl proposals pending
```

Hermes may reject its own obsolete proposal:

```bash
dvizhctl proposal-reject <proposal_id>
```

### Critical approval rule

**Never call `apply`, `approve`, direct SQLite writes, web-state PUTs, or any other mutation to enact a proposal.** The current Hermes layer intentionally has no apply command.

The proposal must later be approved by the user **inside the authenticated DVIZH UI**. Until that UI approval exists and reports success, tell the user clearly: “Предложение создано, но ещё не применено.”

Do not create a proposal when the user is only brainstorming or asking “что лучше?”. Create one only when they actually ask to change something or explicitly ask you to stage a change.

Before a proposal, read the relevant context so IDs/current values are grounded in DVIZH and summarize the exact before → after change.

## Server diagnostics

1. Start with `dvizhctl status`.
2. If needed, run `dvizhctl doctor`.
3. For one service, use `dvizhctl logs <service> 80`.

Allowed services:

- `dvizh`
- `dvizh-auth`
- `dvizh-telegram`
- `dvizh-bridge`
- `dvizh-web-week`
- `dvizh-web-editor`
- `dvizh-training`
- `dvizh-jump`
- `dvizh-social`

`dvizhctl logs` redacts common token/key/password patterns. Do not bypass it with direct `journalctl` for routine DVIZH diagnosis.

## Planning behavior

For questions such as “Что мне сегодня делать?”, “Какой сегодня план?”, “Стоит ли сегодня волейбол?”, “Что у меня на неделе?”, first retrieve the appropriate context view and base the answer on actual DVIZH data.

Distinguish facts from recommendations. Do not claim a proposed change was applied.

## Safety boundary — mandatory

The current layer allows read-only inspection plus **inert proposal creation only**.

Do not bypass it with direct mutating shell commands. Do not:

- restart/stop/start/enable/disable systemd units;
- run `sudo` for DVIZH changes except the internal read-only `dvizhctl context` helper;
- edit/move/truncate/delete DVIZH files;
- change SQLite rows/schema;
- PUT/POST directly to DVIZH mutation APIs;
- inspect/print `.env`, `auth.json`, tokens, API keys, passwords, cookies, auth identity, credential stores;
- install/update packages;
- deploy/rollback/git reset/checkout/clean;
- change firewall/proxy/exe.dev/auth/system configuration.

If a requested action cannot be represented by the allowed proposal types, explain it and do not improvise a mutating workaround.

## Secrets

Never include secrets in chat output. Do not inspect `~/.hermes/.env`, `~/.hermes/auth.json`, `~/.codex/auth.json`, DVIZH `.env` files, or `/var/lib/dvizh/auth-identity.json` directly.

## Useful workflows

User: “Что у меня сегодня?” → `dvizhctl context today`, compact summary.

User: “Перенеси зал на 20:00” → read `context today/week`, identify actual occurrence, create `schedule_move` proposal, report proposal ID and that it is not applied yet.

User: “Добавь купить молоко” → read `context today` if timing matters, create `task_create` proposal, report proposal ID and pending state.

User: “Отметь ПДД выполненной” → read `context today`, identify exact task ID, create `task_complete` proposal, no direct completion.

User: “Составь мне план и примени” → build recommendation from context, create `day_plan` proposal. Do not apply until future DVIZH UI approval.

User: “Почему не синхронизируется Telegram и сайт?” → status → doctor → relevant redacted logs.

## Verification

After diagnostics report health/evidence and whether anything changed.
After context work separate facts from inference.
After proposal creation report:

- proposal ID;
- exact intended change;
- status `pending`;
- explicit statement that **nothing has been applied yet**.
