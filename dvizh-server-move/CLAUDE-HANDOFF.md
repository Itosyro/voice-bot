# DVIZH: server move and Claude Code handoff

Prepared 2026-09-15. Goal: move the ENTIRE workload off an expiring exe.dev server, preserving live data, Hermes, configuration, development state and any co-hosted project. Minimize owner commands. Do not redesign the app or upgrade Autopilot during migration.

## Current status — do not overclaim

- Source: rikarishi-dvizh, owner shell exedev@rikarishi-dvizh.
- Repository: Itosyro/voice-bot. Old app URL: https://rikarishi-dvizh.exe.xyz/.
- Last production release reported in the owner's terminal screenshot: f6b8959c7d05eea434fbe25937b6428b70ed1716.
- Backup reported for that release: /var/lib/dvizh-release-gate/backups/autopilot.nc8ze2zo. This is NOT a whole-server/database backup.
- Candidate base: 946419c5b41f29c84b4a4597ee86f8e44b7092a8. Old source branch: chatgpt/dvizh-daily-stability-2026-09-14. Release branch: hermes/dev/owner-daily-stability-20260914. Resolve current refs before use.
- This branch adds only READ-ONLY migration inventory. No source or target SSH/admin connection, backup, transfer, restore or DNS switch has been performed by this task.
- preflight.py at 7cc5287fd365e461de6ae8d3b3319d1fbbb8aca6: SHA256 f05500ae14e939ad4e8683507d69152fe15637c7e643b20e2fd71b624d7afc4d; Git blob 51233a22b0f32213c66f8f49cbe6009d497c7804. Tested locally with 21 unit/fixture tests; not a real migration/restore test.

## Inventory

Run the hash-verified script in an OWNER sudo session on the OLD server. It inventories OS/architecture, sizes, users/groups without password fields, system unit metadata, user unit filenames, packages, local rootful Docker mounts, data path metadata and PUBLIC static code hashes. Health is the local /api/health JSON contract (ok=true, app=dvizh), not /api/ai-home/health.

It does not open environment VALUES, key contents, task data or auth identity contents; does not install packages, stop/start services or run agents. It writes only a private metadata report in a fresh /var/tmp/dvizh-migration-*/inventory.json (0700 directory / 0600 file, retrievable by sudo caller). --json prints the metadata instead of saving it. This is NOT A BACKUP.

Read the full JSON and gaps, not only the brief summary. Live user-manager state, rootless/remote Docker, external databases and provider-side integrations remain unverified. Do not infer that missing known paths mean no other data exists.

## Known contract to confirm live

- /opt/dvizh/static holds the active UI; /opt/dvizh* holds service modules; /var/lib/dvizh holds data; /etc/dvizh holds environment/configuration.
- Hermes has /home/exedev/.hermes, development worktrees, memory/skills/history, an executable/virtual environment and USER systemd service hermes-gateway.service. Preserve hidden home files, user units/drop-ins and linger, not only system units. Internal API previously 127.0.0.1:8642.
- The app has its own auth gateway: documented on 127.0.0.1:8002, forwarding to backend 127.0.0.1:8000. Preserve auth DB and /var/lib/dvizh/auth-identity.json so the same user sees the same data. Do not register a fresh user or insert marker tasks.
- exe.dev provides external HTTPS/TLS/proxy and may inject API credentials OUTSIDE the VM. Filesystem copying cannot transfer those services or ownership of exe.xyz. Confirm a new domain/HTTPS ingress and integrations.
- Expose the verified authentication gateway, never the unauthenticated backend or Hermes API. Reject public client-supplied identity headers; retain the auth gateway's identity handling.
- Service examples in the repository: dvizh, dvizh-auth, dvizh-telegram, dvizh-bridge, dvizh-web-week, dvizh-web-editor, dvizh-training, dvizh-jump, dvizh-social, dvizh-ai-approval, dvizh-ai-home. Enumerate actual live units and all other workloads.

## Isolation and privileges

The same repo has a friend's separate project. Do not edit its src/**, migrations/**, ordinary root tests/test_*.py, Dockerfile, compose files, pyproject.toml, alembic.ini, root Makefile or README. Whole-server migration includes discovering/backing up any co-hosted workload AS-IS, not rewriting it or stopping it without a maintenance plan.

Do not merge to main or bypass the existing release approval boundaries. Preserve actual installed gates/state/keys with existing permissions; do not grant Hermes extra sudo or read access to the private deploy key. Trusted Runtime stays OFF. Never clear a pending journal to unblock migration.

Foundation dd0c856ddd491beaad10568861fe760d12148835 is a separate approved candidate, NOT proof it is installed. Last screenshot version literals: controller 2026.09.08-hermes-autopilot.2; push gate 2026.09.08-dvizh-git-push-gate.1; release gate 2026.09.10-dvizh-release-gate.2.2.1-state-root. Recheck, do not upgrade while moving.

## Implement actual migration after inventory and target are known

1. Resolve target SSH/admin access, OS/release/architecture/disk and final HTTPS address. Prefer matching source OS/architecture initially. Stop on UID/GID conflicts, incompatible runtime or insufficient disk. Never request passwords/private keys in chat; never disable SSH host-key verification.
2. Build an explicit COMPLETE persistent-data plan: live /opt, /usr/local, relevant /etc, /var/lib, /srv, /home, /root, hidden .git/.env/.hermes/runtime, system/user units, cron/timers, every volume/bind mount, database dumps, package/runtime versions, integration credentials and development worktrees. Do not treat a short hardcoded path list as complete.
3. First create a recoverable encrypted backup OUTSIDE the expiring server. Verify retrieval/decryption independently. Keep credentials out of GitHub, terminal logs and public URLs. Preserve ACLs/xattrs/owners/modes/symlinks/hardlinks. Inventory separately mounted filesystems; one-file-system must not silently skip them.
4. Make an early bulk copy while appropriate, then request a precise maintenance confirmation and stop all writers/agents/bots/timers or use validated native snapshots. Handle SQLite WAL/SHM and every PostgreSQL/MySQL/Redis instance correctly. A live filesystem copy is not a consistent final snapshot. Keep source paused until target acceptance or explicit rollback.
5. Restore to STAGING on the target. Preserve the new machine's SSH host keys/owner access, machine-id, boot/kernel, cloud-init/network/fstab. Never blindly replace passwd/shadow/sudoers/firewall or unpack arbitrary archive paths over /. Reconcile reviewed application identities/configs without expanding privileges.
6. Restore exact working files/data and runtimes, not latest GitHub code or example fixtures. Verify hashes, metadata and DB integrity. Keep target workers isolated until cutover: do not run two Telegram pollers, Hermes agents or scheduled jobs against real state.
7. Configure HTTPS and preserved login identity. Handle provider-side integrations through owner-authorized reconnection. Do not silently remove authentication to get a green health check.
8. Check read-only health/auth denial first, then owner login/data, Manual/AI, actual Android text/voice/TTS and restart survival. Do not synthesize real user data. Before switching origin, ensure browser-local pending changes are synced and do not clear old site storage.
9. Switch traffic/bookmarks/webhooks after final data sync. Report snapshot time, backup path/digest, exact code, service states, source final state, URL and rollback. Never automatically delete the old VM. Retain an independent backup.

## Missing inputs

Full live inventory, target details/admin route, HTTPS domain/DNS ownership, time until trial ends, maintenance window, external databases/integrations/co-hosted workloads. Ask briefly; let inventory answer the technical questions.

Sources: inspect, DO NOT execute historical installers:
- Repository at f6b8959c7d05eea434fbe25937b6428b70ed1716: install-dvizh-ai-home.sh, dvizh-auth-release/README.md, install-dvizh-hermes-control.sh.
- https://exe.dev/docs/proxy
- https://exe.dev/docs/faq/copy-files
