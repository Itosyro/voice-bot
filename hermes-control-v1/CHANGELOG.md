# Changelog

## 2026.09.05-hermes-control.2

- Added read-only `dvizhctl` status/doctor/logs/path/version commands.
- Added Hermes `dvizh-server` skill.
- Added automatic redaction for common Telegram/OpenAI/GitHub/Bearer/secret assignment patterns in logs.
- Added locked bootstrap installer with backup/rollback.
- Added CI for syntax, safety refusals, mocked health checks, locked payload and redaction.
