# Health Recovery staged release progress

Job: 20260909-115201-e37585. Keep open until end-to-end acceptance.

## Frontend — deployed and verified

Source commit: 78c0c032221831a1f5bfb2941b5585a8175d9680.
Proposal: release-20260909-115201-e37585-78c0c03222.
Backup: /var/lib/dvizh-release-gate/backups/autopilot.pn0ervbn.
app.js, manual.html and sync.js match committed artifacts on disk and HTTP.
No restarts. Other pinned production files remain unchanged.

## Privileged integration — next approval boundary

Use manifests/health-recovery-privileged.json via the managed controller.
This documentation-only commit provides a distinct job+commit proposal identity;
it does not change any runtime payload or overwrite the deployed frontend proposal.
Targets are exactly dvizh-context, dvizh-proposals and proposal_bridge.py as
specified in RELEASE.md. Restart only dvizh-ai-approval.service.
No privileged apply without a later exact owner APPROVE phrase.

## Privileged integration — deployed and verified

Source commit: 64161df5cf3c29a41935c573095a5c077ecae7e3.
Proposal: release-20260909-115201-e37585-64161df5cf.
Backup: /var/lib/dvizh-release-gate/backups/autopilot.x9xf1m21.
All three installed payloads match committed bytes and SHA256, root:root 0755,
and Python syntax checks. Gate restarted dvizh-ai-approval.service successfully.
Approval and AI Home services are active; all nine dvizhctl status services active.
Live read-only health context passes through the authorized dvizhctl context health
surface. Direct unprivileged helper execution lacks database access as expected;
no permissions were changed. No synthetic production proposals were created.

## AI Home bridge — remains pending

After privileged apply and verification, prepare the final AI Home manifest with
a separate proposal identity. Require its own approval before apply. Do not
claim production end-to-end acceptance from isolated inference evidence.
