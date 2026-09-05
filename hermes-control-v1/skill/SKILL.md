---
name: dvizh-server
description: Safely inspect and diagnose the DVIZH planner server through the read-only dvizhctl interface. Use for DVIZH status, health checks, service logs, outages, sync problems, and server diagnostics.
version: 1.0.0
author: DVIZH
platforms: [linux]
metadata:
  hermes:
    tags: [dvizh, server, diagnostics, planner, telegram]
    category: dvizh
---

# DVIZH Server Operations

Use this skill whenever the user asks about the DVIZH server, its services, Telegram/web synchronization, health, logs, or whether the app is running.

## Source of truth

The current read-only operational interface is:

```bash
dvizhctl
```

Prefer it over ad-hoc shell commands for DVIZH diagnostics.

## Safe procedure

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

4. Summarize the cause in plain language. Distinguish confirmed evidence from guesses.

## Safety boundary — mandatory

`dvizhctl` v1 is intentionally **read-only**.

Do not bypass it with direct mutating shell commands. In particular, unless a future DVIZH approval tool explicitly grants the action, do **not**:

- restart/stop/start/enable/disable systemd units;
- run `sudo` for DVIZH changes;
- edit, move, truncate, or delete DVIZH files;
- change SQLite rows or schema;
- inspect or print `.env`, `auth.json`, bot tokens, API keys, passwords, cookies, or credential stores;
- run package installation/update commands;
- deploy, rollback, `git reset`, `git checkout`, `git clean`, or overwrite working trees;
- change firewall, proxy, exe.dev, auth, or system configuration.

If the user asks for one of those actions, first diagnose read-only, explain the exact proposed change, and say that the current Hermes control layer requires a separate approval path before mutation. Do not silently work around that boundary.

## Secrets

Never include secrets in chat output. If logs accidentally expose something token-like, redact it before replying.

Do not inspect `~/.hermes/.env`, `~/.hermes/auth.json`, `~/.codex/auth.json`, or DVIZH secret files as part of routine diagnosis.

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

## Useful prompts and expected behavior

User: "Проверь ДВИЖ"

Procedure: `dvizhctl status`; if any non-active service appears, `dvizhctl doctor`; inspect only the failing service logs.

User: "Почему не синхронизируется Telegram и сайт?"

Procedure: status → doctor → recent logs for `dvizh-bridge`, `dvizh-web-week`, and/or `dvizh-web-editor` as indicated by evidence.

User: "Перезапусти social"

Procedure: inspect status/logs first, explain the likely fix, then state that restart is intentionally not available in the current read-only control layer and requires explicit mutation approval support.

## Verification

After any diagnostic workflow, report:

- which services are healthy/unhealthy;
- what evidence supports the conclusion;
- whether any change was made (normally: **no changes made**).
