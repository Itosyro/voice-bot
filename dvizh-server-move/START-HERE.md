# Start here: DVIZH server move

Status: ONLY the inventory script and continuation handoff exist. No whole-server backup has been made, no target restore installer has been completed, and no migration has been performed. Do not call this a one-command completed migration.

First run this single paste on the OLD server from the owner shell, not exe.dev Lobby. It downloads immutable code and verifies SHA256 on the exact buffered bytes before executing the read-only collector with sudo. It writes a private metadata report only. No packages, service restarts, app writes, task data exports or credential contents.

```bash
(set -euo pipefail; f="$(mktemp)"; trap 'rm -f "$f"' EXIT; curl -fsSL --connect-timeout 10 --max-time 60 'https://raw.githubusercontent.com/Itosyro/voice-bot/7cc5287fd365e461de6ae8d3b3319d1fbbb8aca6/dvizh-server-move/preflight.py' -o "$f"; sudo /usr/bin/python3 -I -S -c 'import sys,hashlib; b=sys.stdin.buffer.read(1048577); h=hashlib.sha256(b).hexdigest(); h==sys.argv[1] or sys.exit("SHA256 mismatch; nothing executed"); sys.argv=["dvizh-migration-preflight"]; exec(compile(b,"<verified-preflight>","exec"),{"__name__":"__main__"})' 'f05500ae14e939ad4e8683507d69152fe15637c7e643b20e2fd71b624d7afc4d' < "$f")
```

Return the summary and keep the JSON at the printed REPORT path. Review gaps and the complete JSON before creating the source export plan. Do not send .env files, keys, passwords or task databases into chat. A private metadata report is NOT a backup and does not protect against server expiration.

Next: confirm target OS/architecture/disk/admin SSH and HTTPS domain, produce a consistent encrypted backup outside the expiring server, then implement a checked restore and cutover matching that inventory. The owner wants a small number of copy/paste commands and no redesign. Keep old server intact until new app/data/auth and workers are verified. Read CLAUDE-HANDOFF.md before doing any writes.

Local tests: 21 unit/fixture checks passed; buffered verifier positive/negative checks passed; launch command passes bash syntax check. No production transfer/restore tests have been claimed.
